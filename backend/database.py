"""
Database module for persistent game state storage.

Provides functions for initializing the SQLite database, creating and
loading games, saving and restoring game states, and retrieving
leaderboard data.
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.config import DB_PATH, DATA_DIR


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
def get_db_ctx():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database schema.

    Creates the ``games`` and ``saves`` tables and the ``idx_saves_game``
    index if they do not already exist.
    """
    with get_db_ctx() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                seed INTEGER NOT NULL,
                ship_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS saves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                state_json TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_saves_game ON saves(game_id);
        """)
        conn.commit()


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
            "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
            (game_id, seed, ship_name, created_at, now, json.dumps(state)),
        )
        conn.commit()


def load_game(game_id: str) -> dict | None:
    """Load a game's serialized state from the main games table.

    :param game_id: The unique identifier for the game.
    :type game_id: str
    :returns: The deserialized game state dictionary, or ``None`` if
        not found.
    :rtype: dict | None
    """
    with get_db_ctx() as conn:
        row = conn.execute("SELECT state_json FROM games WHERE id = ?", (game_id,)).fetchone()
    if row:
        return json.loads(row["state_json"])
    return None


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
            seed = state.get("seed", 0)
            ship_data = state.get("ship", {})
            ship_name = ship_data.get("name", "Unknown") if isinstance(ship_data, dict) else "Unknown"
        conn.execute(
            "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
            (game_id, seed, ship_name, created_at, now, json.dumps(state)),
        )
        conn.execute(
            "INSERT INTO saves (game_id, saved_at, state_json) VALUES (?, ?, ?)",
            (game_id, now, json.dumps(state)),
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
            "SELECT state_json FROM saves WHERE game_id = ? ORDER BY id DESC LIMIT 1",
            (game_id,),
        ).fetchone()
    if row:
        return json.loads(row["state_json"])
    return None


def get_leaderboard(limit: int = 10) -> list[dict]:
    """Retrieve the top players from the leaderboard.

    :param limit: Maximum number of leaderboard entries to return.
    :type limit: int
    :returns: A list of leaderboard entry dictionaries containing
        game_id, ship_name, seed, last_played, discoveries count,
        systems_visited, and credits.
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
        results.append({
            "game_id": row["id"],
            "ship_name": row["ship_name"],
            "seed": row["seed"],
            "last_played": row["updated_at"],
            "discoveries": len(state.get("discoveries", [])),
            "systems_visited": state.get("systems_visited", 0),
            "credits": state.get("ship", {}).get("credits", 0),
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
