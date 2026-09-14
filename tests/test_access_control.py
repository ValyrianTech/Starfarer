import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.config import (
    ALLOW_CREDENTIALS,
    get_require_game_token,
    resolve_allow_credentials,
)
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game
from backend.main import app
from backend.models.game_state import GameState

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db() -> None:
    init_db()


def _new_game_via_api(**payload) -> dict:
    resp = client.post("/api/game/new", json=payload)
    assert resp.status_code == 200
    return resp.json()


class TestGetRequireGameToken:
    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
    def test_truthy_values(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", value)
        assert get_require_game_token() is True

    @pytest.mark.parametrize("value", ["0", "no", "false", "off", ""])
    def test_falsy_values(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", value)
        assert get_require_game_token() is False

    def test_unset_is_false(self, monkeypatch) -> None:
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        assert get_require_game_token() is False


class TestResolveAllowCredentials:
    def test_wildcard_returns_false(self) -> None:
        assert resolve_allow_credentials(["*"]) is False

    def test_specific_origin_returns_true(self) -> None:
        assert resolve_allow_credentials(["http://x"]) is True

    def test_wildcard_among_others_returns_false(self) -> None:
        assert resolve_allow_credentials(["http://x", "*"]) is False

    def test_empty_list_returns_true(self) -> None:
        assert resolve_allow_credentials([]) is True


class TestCORSConfig:
    def test_allow_credentials_default_true(self) -> None:
        assert ALLOW_CREDENTIALS is True

    def test_allow_credentials_matches_origins(self) -> None:
        assert ALLOW_CREDENTIALS == resolve_allow_credentials(config.ALLOWED_ORIGINS)


class TestNewGameToken:
    def test_new_game_returns_nonempty_token(self) -> None:
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            assert token
            assert isinstance(token, str)
        finally:
            GAME_STORE.pop(gid, None)

    def test_response_token_matches_stored_state(self) -> None:
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            assert gid in GAME_STORE
            assert GAME_STORE[gid].token == token
        finally:
            GAME_STORE.pop(gid, None)

    def test_new_game_token_persists_across_save_load(self) -> None:
        from backend.game.manager import game_load

        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            GAME_STORE.pop(gid, None)
            loaded = game_load(gid)
            assert loaded is not None
            assert loaded.token == token
        finally:
            GAME_STORE.pop(gid, None)


class TestEndpointEnforcement:
    def test_scan_requires_token_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            resp = client.post(f"/api/game/{gid}/scan")
            assert resp.status_code == 403

            resp = client.post(
                f"/api/game/{gid}/scan", headers={"X-Game-Token": "wrong"}
            )
            assert resp.status_code == 403

            resp = client.post(
                f"/api/game/{gid}/scan", headers={"X-Game-Token": token}
            )
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)

    def test_get_endpoints_require_token_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            resp = client.get(f"/api/game/{gid}")
            assert resp.status_code == 403

            resp = client.get(f"/api/game/{gid}", headers={"X-Game-Token": "wrong"})
            assert resp.status_code == 403

            resp = client.get(f"/api/game/{gid}", headers={"X-Game-Token": token})
            assert resp.status_code == 200

            resp = client.get(f"/api/game/{gid}", params={"token": token})
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)

    def test_empty_token_game_requires_token(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        state: GameState = new_game()
        state.token = ""
        GAME_STORE[state.id] = state
        try:
            resp = client.post(
                f"/api/game/{state.id}/scan",
                headers={"X-Game-Token": "anything"},
            )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Game token required"
        finally:
            GAME_STORE.pop(state.id, None)

    def test_enforcement_loads_state_from_db(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        GAME_STORE.pop(gid, None)
        try:
            assert gid not in GAME_STORE

            resp = client.post(f"/api/game/{gid}/scan")
            assert resp.status_code == 403

            resp = client.post(
                f"/api/game/{gid}/scan", headers={"X-Game-Token": token}
            )
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)

    def test_unknown_game_id_returns_404(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        resp = client.post("/api/game/nonexistent-xyz/scan")
        assert resp.status_code == 404

    def test_authorize_game_raises_404_for_unknown_game(self, monkeypatch) -> None:
        from fastapi import HTTPException

        from backend.api.routes import _authorize_game

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        assert "nonexistent-xyz" not in GAME_STORE
        with pytest.raises(HTTPException) as exc_info:
            _authorize_game("nonexistent-xyz", None)
        assert exc_info.value.status_code == 404

    def test_enforcement_disabled_allows_no_token(self, monkeypatch) -> None:
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        try:
            resp = client.post(f"/api/game/{gid}/scan")
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)


class TestReadEndpointEnforcement:
    @pytest.mark.parametrize(
        "path",
        [
            "",
            "/galaxy",
            "/log",
            "/log/paginated",
            "/discoveries",
            "/cargo",
            "/lore",
            "/codex",
            "/upgrades",
            "/nearby",
            "/factions",
            "/missions",
        ],
    )
    def test_read_endpoints_require_token(self, monkeypatch, path) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        current = GAME_STORE[gid].get_current_system()
        if current is not None:
            current.has_trading_station = True
        try:
            resp = client.get(f"/api/game/{gid}{path}")
            assert resp.status_code == 403

            resp = client.get(
                f"/api/game/{gid}{path}", headers={"X-Game-Token": token}
            )
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)

    def test_system_detail_requires_token(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        sys_id = GAME_STORE[gid].ship.current_system_id
        try:
            resp = client.get(f"/api/game/{gid}/system/{sys_id}")
            assert resp.status_code == 403

            resp = client.get(
                f"/api/game/{gid}/system/{sys_id}",
                headers={"X-Game-Token": token},
            )
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)

    def test_faction_detail_requires_token(self, monkeypatch) -> None:
        from backend.models.faction import FACTION_DEFINITIONS

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        faction_id = next(iter(FACTION_DEFINITIONS))
        try:
            resp = client.get(f"/api/game/{gid}/faction/{faction_id}")
            assert resp.status_code == 403

            resp = client.get(
                f"/api/game/{gid}/faction/{faction_id}",
                headers={"X-Game-Token": token},
            )
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)


class TestSpectateEnforcement:
    def test_games_listing_disabled_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        resp = client.get("/api/spectate/games")
        assert resp.status_code == 403

    def test_games_listing_allowed_when_disabled(self, monkeypatch) -> None:
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        resp = client.get("/api/spectate/games")
        assert resp.status_code == 200

    def test_stream_requires_token_when_enabled(self, monkeypatch) -> None:
        import asyncio

        from fastapi import HTTPException

        from backend.api.spectate import api_spectate_stream

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(api_spectate_stream(gid, x_game_token=None))
            assert exc.value.status_code == 403

            async def run_and_close(**kwargs) -> str:
                response = await api_spectate_stream(gid, **kwargs)
                assert response.media_type == "text/event-stream"
                agen = response.body_iterator
                try:
                    chunk = await agen.__anext__()
                finally:
                    await agen.aclose()
                return chunk if isinstance(chunk, str) else chunk.decode()

            chunk = asyncio.run(run_and_close(token=token, x_game_token=None))
            assert "event: state" in chunk

            chunk = asyncio.run(run_and_close(x_game_token=token))
            assert "event: state" in chunk
        finally:
            GAME_STORE.pop(gid, None)
