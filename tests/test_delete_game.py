import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from backend.database import game_exists, get_db, init_db
from backend.game.manager import GAME_STORE
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db() -> None:
    init_db()


def _new_game_via_api(**payload) -> dict:
    resp = client.post("/api/game/new", json=payload)
    assert resp.status_code == 200
    return resp.json()


def _save_count(game_id: str) -> int:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM saves WHERE game_id = ?", (game_id,)
        ).fetchone()
    finally:
        conn.close()
    return int(row[0])


def _delete_db_row(game_id: str) -> None:
    conn = get_db()
    try:
        conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()


class TestDeleteGame:
    def test_delete_removes_from_store_and_db(self) -> None:
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        assert gid in GAME_STORE
        assert game_exists(gid) is True
        assert _save_count(gid) > 0

        resp = client.delete(
            f"/api/game/{gid}", headers={"X-Game-Token": token}
        )
        assert resp.status_code == 200
        assert resp.json() == {"result": "Game deleted.", "game_id": gid}

        assert gid not in GAME_STORE
        assert game_exists(gid) is False
        assert _save_count(gid) == 0

    def test_delete_persisted_only_game(self) -> None:
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        GAME_STORE.pop(gid, None)
        try:
            assert gid not in GAME_STORE
            assert game_exists(gid) is True

            resp = client.delete(
                f"/api/game/{gid}", headers={"X-Game-Token": token}
            )
            assert resp.status_code == 200
            assert resp.json() == {"result": "Game deleted.", "game_id": gid}
            assert game_exists(gid) is False
            assert _save_count(gid) == 0
        finally:
            GAME_STORE.pop(gid, None)

    def test_delete_unknown_game_404(self) -> None:
        resp = client.delete("/api/game/no-such-game-xyz")
        assert resp.status_code == 404

    def test_delete_missing_token_403_when_enforced(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        try:
            resp = client.delete(f"/api/game/{gid}")
            assert resp.status_code == 403
            assert game_exists(gid) is True
            assert gid in GAME_STORE
        finally:
            GAME_STORE.pop(gid, None)
            _delete_db_row(gid)

    def test_delete_wrong_token_403_when_enforced(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        try:
            resp = client.delete(
                f"/api/game/{gid}", headers={"X-Game-Token": "wrong"}
            )
            assert resp.status_code == 403
            assert game_exists(gid) is True
            assert gid in GAME_STORE
        finally:
            GAME_STORE.pop(gid, None)
            _delete_db_row(gid)

    def test_delete_query_param_token_not_accepted(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            resp = client.delete(f"/api/game/{gid}", params={"token": token})
            assert resp.status_code == 403
            assert game_exists(gid) is True
        finally:
            GAME_STORE.pop(gid, None)
            _delete_db_row(gid)

    def test_delete_allowed_when_enforcement_disabled(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        resp = client.delete(f"/api/game/{gid}")
        assert resp.status_code == 200
        assert resp.json() == {"result": "Game deleted.", "game_id": gid}
        assert game_exists(gid) is False

    def test_delete_frees_storage_cap_slot(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "0")
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "1")

        GAME_STORE.clear()
        conn = get_db()
        try:
            conn.execute("DELETE FROM games")
            conn.commit()
        finally:
            conn.close()

        first = client.post("/api/game/new", json={})
        assert first.status_code == 200
        gid = first.json()["game_id"]
        token = first.json()["token"]

        try:
            second = client.post("/api/game/new", json={})
            assert second.status_code == 429

            resp = client.delete(
                f"/api/game/{gid}", headers={"X-Game-Token": token}
            )
            assert resp.status_code == 200

            third = client.post("/api/game/new", json={})
            assert third.status_code == 200
            third_gid = third.json()["game_id"]
        finally:
            GAME_STORE.pop(gid, None)
            if "third_gid" in locals():
                GAME_STORE.pop(third_gid, None)

    def test_delete_endpoint_in_openapi(self) -> None:
        schema = app.openapi()
        paths = schema["paths"]
        assert "/api/game/{game_id}" in paths
        assert "delete" in paths["/api/game/{game_id}"]
