import sqlite3
import json
import os
from datetime import datetime, timezone

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "starfarer.db")


def get_db() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_db()
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
    conn.close()


def create_game(game_id: str, seed: int, ship_name: str, state: dict) -> None:
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
        (game_id, seed, ship_name, now, now, json.dumps(state)),
    )
    conn.commit()
    conn.close()


def load_game(game_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT state_json FROM games WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    if row:
        return json.loads(row["state_json"])
    return None


def update_game(game_id: str, state: dict) -> None:
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE games SET state_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(state), now, game_id),
    )
    conn.commit()
    conn.close()


def save_game(game_id: str, state: dict) -> None:
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    update_game(game_id, state)
    conn.execute(
        "INSERT INTO saves (game_id, saved_at, state_json) VALUES (?, ?, ?)",
        (game_id, now, json.dumps(state)),
    )
    conn.commit()
    conn.close()


def load_save(game_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT state_json FROM saves WHERE game_id = ? ORDER BY id DESC LIMIT 1",
        (game_id,),
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["state_json"])
    return None


def get_leaderboard(limit: int = 10) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, ship_name, seed, updated_at, state_json FROM games ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        state = json.loads(row["state_json"])
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
