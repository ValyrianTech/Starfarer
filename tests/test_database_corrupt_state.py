import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from backend.database import get_db, init_db, load_game, load_save


@pytest.fixture(autouse=True)
def setup_db() -> None:
    init_db()


def _insert_game(game_id: str, state_json: str) -> None:
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
            "VALUES (?, ?, ?, ?, ?, ?, '')",
            (
                game_id,
                42,
                "CorruptShip",
                "2020-01-01T00:00:00+00:00",
                "2020-01-01T00:00:00+00:00",
                state_json,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_save(game_id: str, state_json: str) -> None:
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
            "VALUES (?, ?, ?, ?, ?, ?, '')",
            (
                game_id,
                42,
                "CorruptShip",
                "2020-01-01T00:00:00+00:00",
                "2020-01-01T00:00:00+00:00",
                '{"seed": 42}',
            ),
        )
        conn.execute(
            "INSERT INTO saves (game_id, saved_at, state_json, token) VALUES (?, ?, ?, '')",
            (game_id, "2020-01-01T00:00:00+00:00", state_json),
        )
        conn.commit()
    finally:
        conn.close()


def _cleanup(game_id: str) -> None:
    conn = get_db()
    try:
        conn.execute("DELETE FROM saves WHERE game_id = ?", (game_id,))
        conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()


class TestLoadGameCorruptState:
    def test_load_game_returns_none_for_non_dict_json(self) -> None:
        game_id = "corrupt-game-non-dict"
        _insert_game(game_id, "[]")
        try:
            assert load_game(game_id) is None
        finally:
            _cleanup(game_id)

    def test_load_game_returns_none_for_invalid_json(self) -> None:
        game_id = "corrupt-game-invalid-json"
        _insert_game(game_id, "not-json{")
        try:
            assert load_game(game_id) is None
        finally:
            _cleanup(game_id)


class TestLoadSaveCorruptState:
    def test_load_save_returns_none_for_non_dict_json(self) -> None:
        game_id = "corrupt-save-non-dict"
        _insert_save(game_id, "[]")
        try:
            assert load_save(game_id) is None
        finally:
            _cleanup(game_id)

    def test_load_save_returns_none_for_invalid_json(self) -> None:
        game_id = "corrupt-save-invalid-json"
        _insert_save(game_id, "{{")
        try:
            assert load_save(game_id) is None
        finally:
            _cleanup(game_id)
