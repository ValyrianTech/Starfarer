"""
Database module for persistent game state storage.

Provides functions for initializing the SQLite database, creating and
loading games, saving and restoring game states, and retrieving
leaderboard data.
"""

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.config import DATA_DIR, DB_PATH


def get_db() -> sqlite3.Connection:
    """Open a connection to the SQLite database.

    Creates the data directory if it does not exist, configures the
    connection for WAL journal mode and foreign key enforcement.

    :returns: An open SQLite connection with row factory set.
    :rtype: sqlite3.Connection
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db_ctx() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that provides a database connection.

    Yields an open :class:`sqlite3.Connection` that is automatically closed
    when the context exits, even if an exception occurs.

    :yields: An open SQLite database connection.
    :rtype: sqlite3.Connection
    :raises sqlite3.Error: If a database error occurs while opening or
        closing the connection.
    """
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database schema.

    Creates the ``games`` and ``saves`` tables and the ``idx_saves_game``
    index if they do not already exist. For pre-existing databases created
    before the ``token`` column was introduced, idempotently adds the
    ``token`` column to both tables.
    """
    with get_db_ctx() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                seed INTEGER NOT NULL,
                ship_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state_json TEXT NOT NULL,
                token TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS saves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                state_json TEXT NOT NULL,
                token TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_saves_game ON saves(game_id);
        """)
        _ensure_token_column(conn, "games")
        _ensure_token_column(conn, "saves")
        conn.commit()


def _ensure_token_column(conn: sqlite3.Connection, table: str) -> None:
    """Add the ``token`` column to a table if it does not already exist.

    Idempotent migration for databases created before the ``token`` column
    was introduced. Inspects the table schema via ``PRAGMA table_info`` and
    issues an ``ALTER TABLE`` only when the column is absent.

    :param conn: An open SQLite connection.
    :type conn: sqlite3.Connection
    :param table: The name of the table to migrate.
    :type table: str
    """
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if "token" not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN token TEXT NOT NULL DEFAULT ''")


def create_game(game_id: str, seed: int, ship_name: str, state: dict) -> None:
    """Create or replace a game record in the database.

    Creates or updates the main game record. If the game already exists
    its original ``created_at`` timestamp is preserved; otherwise the
    current time is used.

    :param game_id: The unique identifier for the game.
    :type game_id: str
    :param seed: The universe generation seed.
    :type seed: int
    :param ship_name: The name of the player's ship.
    :type ship_name: str
    :param state: The serialized game state dictionary.
    :type state: dict
    """
    token = state.get("token", "") if isinstance(state, dict) else ""
    state_data = dict(state) if isinstance(state, dict) else {}
    state_data.pop("token", None)
    with get_db_ctx() as conn:
        now = datetime.now(timezone.utc).isoformat()
        existing = conn.execute(
            "SELECT created_at FROM games WHERE id = ?",
            (game_id,),
        ).fetchone()
        if existing:
            created_at = existing["created_at"]
        else:
            created_at = now
        conn.execute(
            "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "seed=excluded.seed, "
            "ship_name=excluded.ship_name, "
            "updated_at=excluded.updated_at, "
            "state_json=excluded.state_json, "
            "token=excluded.token",
            (game_id, seed, ship_name, created_at, now, json.dumps(state_data), token),
        )
        conn.commit()


def _resolve_legacy_token(
    conn: sqlite3.Connection,
    data: dict,
    column_token: str,
    update_sql: str,
    update_params: tuple,
) -> str:
    """Resolve a row's effective token, migrating legacy embedded tokens.

    The ``token`` column is authoritative when it holds a non-empty value:
    in that case it is returned unchanged and ``data`` is left untouched.

    When the column is empty but the deserialized ``state_json`` still
    contains a truthy embedded ``token``, that value is recovered: it is
    written to the ``token`` column, scrubbed from ``state_json``, and
    persisted.

    When neither the column nor the embedded ``state_json`` holds a truthy
    token, an empty string is returned and ``data`` is left untouched so
    that callers can apply guarded fallback logic instead of clobbering any
    existing non-empty token already present in ``data``.

    :param conn: An open SQLite connection.
    :type conn: sqlite3.Connection
    :param data: The deserialized ``state_json`` dictionary.
    :type data: dict
    :param column_token: The value of the row's ``token`` column.
    :type column_token: str
    :param update_sql: Parameterized UPDATE statement used to persist the
        migrated token and scrubbed state.
    :type update_sql: str
    :param update_params: Parameters bound to ``update_sql``.
    :type update_params: tuple
    :returns: The effective token for the loaded row.
    :rtype: str
    """
    if column_token:
        return column_token
    embedded_token = data.get("token", "")
    if embedded_token:
        data.pop("token", None)
        conn.execute(update_sql, (embedded_token, json.dumps(data), *update_params))
        conn.commit()
        return embedded_token
    return ""


def load_game(game_id: str) -> dict | None:
    """Load a game's serialized state from the main games table.

    :param game_id: The unique identifier for the game.
    :type game_id: str
    :returns: The deserialized game state dictionary, or ``None`` if
        not found.
    :rtype: dict | None
    """
    with get_db_ctx() as conn:
        row = conn.execute("SELECT state_json, token FROM games WHERE id = ?", (game_id,)).fetchone()
        if row is None:
            return None
        data = json.loads(row["state_json"])
        token = _resolve_legacy_token(
            conn,
            data,
            row["token"],
            "UPDATE games SET token = ?, state_json = ? WHERE id = ?",
            (game_id,),
        )
        if token:
            data["token"] = token
        elif not data.get("token"):
            data["token"] = ""
    return data


def game_exists(game_id: str) -> bool:
    """Check if a game exists in the database without loading its full state.

    :param game_id: The unique identifier for the game.
    :type game_id: str
    :returns: ``True`` if the game exists, ``False`` otherwise.
    :rtype: bool
    """
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT 1 FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        return row is not None


def save_game(game_id: str, state: dict) -> None:
    """Save the current game state to both the games and saves tables.

    Creates or updates the main game record (preserving the original
    created_at timestamp) and inserts a new row into the saves history
    table.

    :param game_id: The unique identifier for the game.
    :type game_id: str
    :param state: The serialized game state dictionary.
    :type state: dict
    """
    token = state.get("token", "") if isinstance(state, dict) else ""
    state_data = dict(state) if isinstance(state, dict) else {}
    state_data.pop("token", None)
    with get_db_ctx() as conn:
        now = datetime.now(timezone.utc).isoformat()
        existing = conn.execute(
            "SELECT created_at, seed, ship_name FROM games WHERE id = ?",
            (game_id,),
        ).fetchone()
        if existing:
            created_at = existing["created_at"]
            seed = existing["seed"]
            ship_name = existing["ship_name"]
        else:
            # New game: seed and ship_name must be present in the state dict
            created_at = now
            seed = state_data.get("seed", 0)
            ship_data = state_data.get("ship", {})
            ship_name = ship_data.get("name", "Unknown") if isinstance(ship_data, dict) else "Unknown"
        conn.execute(
            "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "seed=excluded.seed, "
            "ship_name=excluded.ship_name, "
            "updated_at=excluded.updated_at, "
            "state_json=excluded.state_json, "
            "token=excluded.token",
            (game_id, seed, ship_name, created_at, now, json.dumps(state_data), token),
        )
        conn.execute(
            "INSERT INTO saves (game_id, saved_at, state_json, token) VALUES (?, ?, ?, ?)",
            (game_id, now, json.dumps(state_data), token),
        )
        conn.commit()


def load_save(game_id: str) -> dict | None:
    """Load the most recent save for a game from the saves table.

    :param game_id: The unique identifier for the game.
    :type game_id: str
    :returns: The deserialized game state dictionary, or ``None`` if
        no save exists.
    :rtype: dict | None
    """
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, state_json, token FROM saves WHERE game_id = ? ORDER BY id DESC LIMIT 1",
            (game_id,),
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["state_json"])
        token = _resolve_legacy_token(
            conn,
            data,
            row["token"],
            "UPDATE saves SET token = ?, state_json = ? WHERE id = ?",
            (row["id"],),
        )
        if token:
            data["token"] = token
        elif not data.get("token"):
            data["token"] = ""
    return data


def _safe_ship_credits(state: dict) -> int:
    """Extract the ship's credits from a deserialized game state defensively.

    Persisted state is not guaranteed to be well-formed, so this helper
    never assumes the ``ship`` value is a dictionary or that its
    ``credits`` field is an integer. Malformed values are treated as a
    missing ``credits`` value and return 0.

    :param state: The deserialized game state dictionary.
    :type state: dict
    :returns: The ship's credits as a non-negative integer, or 0 if the
        value is missing or malformed.
    :rtype: int
    """
    ship = state.get("ship")
    if not isinstance(ship, dict):
        return 0
    credits = ship.get("credits", 0)
    return credits if isinstance(credits, int) else 0


def get_leaderboard(limit: int = 10) -> list[dict]:
    """Retrieve the top players from the leaderboard.

    :param limit: Maximum number of leaderboard entries to return.
    :type limit: int
    :returns: A list of leaderboard entry dictionaries containing
        game_id, ship_name, seed, last_played, discoveries count,
        systems_visited, credits, ghost_signatures_left,
        items_donated, and lore_donated.
    :rtype: list[dict]
    """
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, ship_name, seed, updated_at, state_json FROM games ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        results = []
        for row in rows:
            try:
                state = json.loads(row["state_json"])
                if not isinstance(state, dict):
                    continue  # Skip malformed entries
            except (json.JSONDecodeError, TypeError):
                continue  # Skip malformed entries

            game_id = row["id"]

            try:
                ghost_count = conn.execute(
                    "SELECT COUNT(*) FROM ghost_signatures WHERE game_id = ?",
                    (game_id,),
                ).fetchone()[0]
            except sqlite3.OperationalError:
                ghost_count = 0

            try:
                items_donated = conn.execute(
                    "SELECT COUNT(*) FROM crossroads_items WHERE donor_game_id = ?",
                    (game_id,),
                ).fetchone()[0]
            except sqlite3.OperationalError:
                items_donated = 0

            try:
                lore_donated = conn.execute(
                    "SELECT COUNT(*) FROM crossroads_lore WHERE donor_game_id = ?",
                    (game_id,),
                ).fetchone()[0]
            except sqlite3.OperationalError:
                lore_donated = 0

            results.append({
                "game_id": game_id,
                "ship_name": row["ship_name"],
                "seed": row["seed"],
                "last_played": row["updated_at"],
                "discoveries": len(state.get("discoveries", [])),
                "systems_visited": state.get("systems_visited", 0),
                "credits": _safe_ship_credits(state),
                "ghost_signatures_left": ghost_count,
                "items_donated": items_donated,
                "lore_donated": lore_donated,
            })
    return results


MIGRATIONS = [
    (1, "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)"),
]


def run_migrations() -> None:
    """Run any pending migrations on the persistent database."""
    with get_db_ctx() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]
        for version, sql in MIGRATIONS:
            if version > current:
                conn.execute(sql)
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        conn.commit()
