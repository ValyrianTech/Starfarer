import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api import stream_tickets
from backend.config import (
    ALLOW_CREDENTIALS,
    get_allow_no_auth,
    get_require_game_token,
    resolve_allow_credentials,
)
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game
from backend.main import app
from backend.models.discovery import Discovery
from backend.models.game_state import GameState
from backend.multiplayer.database import init_multiplayer_db

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
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", value)
        assert get_require_game_token() is True

    @pytest.mark.parametrize("value", ["0", "no", "false", "off", ""])
    def test_falsy_values(self, monkeypatch, value: str) -> None:
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", value)
        assert get_require_game_token() is False

    def test_unset_is_true_secure_default(self, monkeypatch) -> None:
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        assert get_require_game_token() is True

    def test_allow_no_auth_wins_over_explicit_require(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        assert get_require_game_token() is False


class TestGetAllowNoAuth:
    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
    def test_truthy_values(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", value)
        assert get_allow_no_auth() is True

    @pytest.mark.parametrize("value", ["0", "no", "false", "off", ""])
    def test_falsy_values(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", value)
        assert get_allow_no_auth() is False

    def test_unset_is_false(self, monkeypatch) -> None:
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        assert get_allow_no_auth() is False


class TestIdorRegression:
    def test_donate_item_rejects_caller_without_valid_token(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        init_multiplayer_db()
        data = _new_game_via_api(shared_universe=True)
        gid = data["game_id"]
        token = data["token"]
        try:
            state = GAME_STORE[gid]
            state.discoveries.append(
                Discovery(
                    id="idor-artifact",
                    category="artifact",
                    name="Idor Artifact",
                    description="An artifact used by the IDOR regression test.",
                    value=100,
                    system_id="sys-1",
                )
            )
            payload = {"game_id": gid, "item_name": "Idor Artifact", "quantity": 1}

            resp = client.post("/api/crossroads/donate-item", json=payload)
            assert resp.status_code == 403

            resp = client.post(
                "/api/crossroads/donate-item",
                json=payload,
                headers={"X-Game-Token": "wrong"},
            )
            assert resp.status_code == 403

            resp = client.post(
                "/api/crossroads/donate-item",
                json=payload,
                headers={"X-Game-Token": token},
            )
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)


class TestSecureDefaultEndToEnd:
    def test_mutating_request_rejected_with_no_env_vars_set(self, monkeypatch) -> None:
        """With NEITHER STARFARER_REQUIRE_GAME_TOKEN nor STARFARER_ALLOW_NO_AUTH set,
        enforcement is ON by default (secure baseline): an unauthenticated mutating
        request must be rejected, and the correct token must be accepted."""
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        init_multiplayer_db()
        data = _new_game_via_api(shared_universe=True)
        gid = data["game_id"]
        token = data["token"]
        try:
            state = GAME_STORE[gid]
            state.discoveries.append(
                Discovery(
                    id="secure-default-artifact",
                    category="artifact",
                    name="Secure Default Artifact",
                    description="An artifact used for the secure-default end-to-end test.",
                    value=100,
                    system_id="sys-1",
                )
            )
            payload = {"game_id": gid, "item_name": "Secure Default Artifact", "quantity": 1}

            resp = client.post("/api/crossroads/donate-item", json=payload)
            assert resp.status_code == 403

            resp = client.post(
                "/api/crossroads/donate-item",
                json=payload,
                headers={"X-Game-Token": token},
            )
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)

    def test_mutating_request_allowed_with_explicit_opt_out(self, monkeypatch) -> None:
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
        init_multiplayer_db()
        data = _new_game_via_api(shared_universe=True)
        gid = data["game_id"]
        try:
            state = GAME_STORE[gid]
            state.discoveries.append(
                Discovery(
                    id="opt-out-artifact",
                    category="artifact",
                    name="Opt Out Artifact",
                    description="An artifact used for the opt-out end-to-end test.",
                    value=100,
                    system_id="sys-1",
                )
            )
            payload = {"game_id": gid, "item_name": "Opt Out Artifact", "quantity": 1}
            resp = client.post("/api/crossroads/donate-item", json=payload)
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)


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
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
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
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
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
            assert resp.status_code == 403
        finally:
            GAME_STORE.pop(gid, None)

    def test_empty_token_game_requires_token(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
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
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
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
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        resp = client.post("/api/game/nonexistent-xyz/scan")
        assert resp.status_code == 404

    def test_authorize_game_raises_404_for_unknown_game(self, monkeypatch) -> None:
        from fastapi import HTTPException

        from backend.api.routes import _authorize_game

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        assert "nonexistent-xyz" not in GAME_STORE
        with pytest.raises(HTTPException) as exc_info:
            _authorize_game("nonexistent-xyz", None)
        assert exc_info.value.status_code == 404

    def test_enforcement_disabled_allows_no_token(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
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
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
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
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
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
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
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


class TestMutatingEndpointEnforcement:
    def test_mutating_endpoints_enforce_token(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        init_multiplayer_db()
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            cases: list[tuple[str, str, dict | None]] = [
                ("jump", f"/api/game/{gid}/jump/bogus-system", None),
                ("scan", f"/api/game/{gid}/scan", None),
                ("land", f"/api/game/{gid}/land/bogus-body", None),
                ("atmospheric-scan", f"/api/game/{gid}/atmospheric-scan", None),
                ("sub-surface-explore", f"/api/game/{gid}/sub-surface-explore", None),
                ("explore", f"/api/game/{gid}/explore", None),
                ("resolve-event", f"/api/game/{gid}/event/bogus-event/resolve", {"choice_index": 0}),
                ("trade", f"/api/game/{gid}/trade", {"action": "buy", "item": "fuel", "quantity": 1}),
                ("bulk-sell", f"/api/game/{gid}/trade/bulk-sell", {"items": []}),
                ("upgrade", f"/api/game/{gid}/upgrade", {"upgrade_id": "bogus"}),
                ("distress", f"/api/game/{gid}/distress", None),
                ("salvage", f"/api/game/{gid}/salvage", None),
                ("salvage-craft", f"/api/game/{gid}/salvage/craft", {"discovery_id": "bogus", "output": "fuel"}),
                ("faction-mission", f"/api/game/{gid}/faction/bogus-faction/mission", None),
                ("accept-mission", f"/api/game/{gid}/missions/bogus-mission/accept", {"mission_id": "bogus-mission"}),
                ("complete-mission", f"/api/game/{gid}/missions/bogus-mission/complete", {"mission_id": "bogus-mission"}),
                ("save", f"/api/game/{gid}/save", None),
                ("load", f"/api/game/{gid}/load", None),
                ("dismiss-hint", f"/api/game/{gid}/hints/dismiss", {"hint_id": "bogus-hint"}),
                ("leave-ghost", f"/api/game/{gid}/leave-ghost", {}),
                ("donate-item", "/api/crossroads/donate-item", {"game_id": gid, "item_name": "bogus", "quantity": 1}),
                ("claim-item", "/api/crossroads/claim-item/bogus-item", {"game_id": gid}),
                ("donate-lore", "/api/crossroads/donate-lore", {"game_id": gid, "fragment_id": "bogus"}),
                ("claim-lore", "/api/crossroads/claim-lore/bogus-donation", {"game_id": gid}),
                ("post-message", "/api/crossroads/post-message", {"game_id": gid, "text": "hello"}),
                ("acknowledge-ripple", f"/api/game/{gid}/ripple/bogus-ripple/acknowledge", None),
            ]
            for name, url, body in cases:
                resp = client.post(url, json=body, headers={"X-Game-Token": "wrong"})
                assert resp.status_code == 403, f"{name}: wrong token should be 403, got {resp.status_code}"

                resp = client.post(url, json=body, headers={"X-Game-Token": token})
                assert resp.status_code != 403, f"{name}: header token should pass auth, got {resp.status_code}"

                resp = client.post(url, json=body, params={"token": token})
                assert resp.status_code == 403, f"{name}: query token must no longer authorize, got {resp.status_code}"
        finally:
            GAME_STORE.pop(gid, None)


class TestMultiplayerReadEndpointEnforcement:
    def test_ripples_requires_token(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        init_multiplayer_db()
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            resp = client.get(f"/api/game/{gid}/ripples")
            assert resp.status_code == 403

            resp = client.get(
                f"/api/game/{gid}/ripples", headers={"X-Game-Token": "wrong"}
            )
            assert resp.status_code == 403

            resp = client.get(
                f"/api/game/{gid}/ripples", headers={"X-Game-Token": token}
            )
            assert resp.status_code == 200
            assert "ripples" in resp.json()

            resp = client.get(f"/api/game/{gid}/ripples", params={"token": token})
            assert resp.status_code == 403
        finally:
            GAME_STORE.pop(gid, None)

    def test_system_ghosts_requires_token(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        init_multiplayer_db()
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        sys_id = GAME_STORE[gid].ship.current_system_id
        try:
            resp = client.get(f"/api/game/{gid}/system/{sys_id}/ghosts")
            assert resp.status_code == 403

            resp = client.get(
                f"/api/game/{gid}/system/{sys_id}/ghosts",
                headers={"X-Game-Token": token},
            )
            assert resp.status_code == 200
            assert "ghosts" in resp.json()

            resp = client.get(
                f"/api/game/{gid}/system/{sys_id}/ghosts", params={"token": token}
            )
            assert resp.status_code == 403
        finally:
            GAME_STORE.pop(gid, None)

    def test_multiplayer_read_endpoints_disabled_allows_no_token(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        init_multiplayer_db()
        data = _new_game_via_api()
        gid = data["game_id"]
        sys_id = GAME_STORE[gid].ship.current_system_id
        try:
            resp = client.get(f"/api/game/{gid}/ripples")
            assert resp.status_code == 200

            resp = client.get(f"/api/game/{gid}/system/{sys_id}/ghosts")
            assert resp.status_code == 200
        finally:
            GAME_STORE.pop(gid, None)


class TestSpectateEnforcement:
    def test_games_listing_disabled_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        resp = client.get("/api/spectate/games")
        assert resp.status_code == 403

    def test_games_listing_allowed_when_disabled(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        resp = client.get("/api/spectate/games")
        assert resp.status_code == 200

    def test_stream_requires_token_when_enabled(self, monkeypatch) -> None:
        import asyncio

        from fastapi import HTTPException

        from backend.api.spectate import api_spectate_stream

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
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

            chunk = asyncio.run(run_and_close(x_game_token=token))
            assert "event: state" in chunk

            # A freshly minted ticket authorizes the stream without a header.
            ticket = stream_tickets.issue_stream_ticket(gid)
            chunk = asyncio.run(run_and_close(ticket=ticket, x_game_token=None))
            assert "event: state" in chunk
        finally:
            GAME_STORE.pop(gid, None)

    def test_stream_rejects_invalid_ticket(self, monkeypatch) -> None:
        import asyncio

        from fastapi import HTTPException

        from backend.api.spectate import api_spectate_stream

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        try:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(
                    api_spectate_stream(
                        gid,
                        ticket="definitely-not-the-right-ticket",
                        x_game_token=None,
                    )
                )
            assert exc.value.status_code == 403
        finally:
            GAME_STORE.pop(gid, None)

    def test_stream_ticket_is_single_use(self, monkeypatch) -> None:
        import asyncio

        from fastapi import HTTPException

        from backend.api.spectate import api_spectate_stream

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        try:
            ticket = stream_tickets.issue_stream_ticket(gid)
            asyncio.run(api_spectate_stream(gid, ticket=ticket, x_game_token=None))

            # The same ticket cannot be redeemed a second time.
            with pytest.raises(HTTPException) as exc:
                asyncio.run(
                    api_spectate_stream(gid, ticket=ticket, x_game_token=None)
                )
            assert exc.value.status_code == 403
        finally:
            GAME_STORE.pop(gid, None)

    def test_stream_ticket_bound_to_other_game_rejected(self, monkeypatch) -> None:
        import asyncio

        from fastapi import HTTPException

        from backend.api.spectate import api_spectate_stream

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        other = _new_game_via_api()
        other_gid = other["game_id"]
        try:
            # Ticket minted for a DIFFERENT game must not authorize gid.
            ticket = stream_tickets.issue_stream_ticket(other_gid)
            with pytest.raises(HTTPException) as exc:
                asyncio.run(
                    api_spectate_stream(gid, ticket=ticket, x_game_token=None)
                )
            assert exc.value.status_code == 403
        finally:
            GAME_STORE.pop(gid, None)
            GAME_STORE.pop(other_gid, None)

    def test_stream_ticket_creation_endpoint(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            # Missing header token -> 403.
            resp = client.post(f"/api/spectate/{gid}/stream-ticket")
            assert resp.status_code == 403

            # Wrong header token -> 403.
            resp = client.post(
                f"/api/spectate/{gid}/stream-ticket",
                headers={"X-Game-Token": "wrong"},
            )
            assert resp.status_code == 403

            # Valid header token -> ticket + lifetime.
            resp = client.post(
                f"/api/spectate/{gid}/stream-ticket",
                headers={"X-Game-Token": token},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert isinstance(body["ticket"], str) and body["ticket"]
            assert body["expires_in"] == stream_tickets.STREAM_TICKET_TTL_SECONDS
        finally:
            GAME_STORE.pop(gid, None)

    def test_stream_ticket_creation_unknown_game_404(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        GAME_STORE.pop("no-such-game-xyz", None)
        # With enforcement on and an unknown game, auth fails closed with 404.
        resp = client.post(
            "/api/spectate/no-such-game-xyz/stream-ticket",
            headers={"X-Game-Token": "irrelevant"},
        )
        assert resp.status_code == 404

    def test_stream_ticket_creation_enforcement_disabled(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        try:
            resp = client.post(f"/api/spectate/{gid}/stream-ticket")
            assert resp.status_code == 200
            assert isinstance(resp.json()["ticket"], str)

            # Unknown game still returns 404 even with enforcement disabled.
            resp = client.post("/api/spectate/no-such-game-zzz/stream-ticket")
            assert resp.status_code == 404
        finally:
            GAME_STORE.pop(gid, None)

    def test_stream_idle_then_evicted_sends_end_event(self, monkeypatch) -> None:
        """A stream whose game is evicted emits an ``end`` event."""
        import asyncio

        from backend.api.spectate import api_spectate_stream

        monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
        monkeypatch.delenv("STARFARER_REQUIRE_GAME_TOKEN", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]

        async def drain() -> list:
            response = await api_spectate_stream(gid, x_game_token=None)
            agen = response.body_iterator
            chunks = []
            try:
                async for chunk in agen:
                    chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
                    if len(chunks) == 1:
                        # Simulate the game being evicted right after the
                        # initial snapshot so the next poll yields ``end``.
                        GAME_STORE.pop(gid, None)
                    if "event: end" in chunks[-1]:
                        break
            finally:
                await agen.aclose()
            return chunks

        chunks = asyncio.run(drain())
        assert any("event: state" in c for c in chunks)
        assert any("event: end" in c for c in chunks)
        GAME_STORE.pop(gid, None)

    def test_stream_ticket_rejected_then_consumed_when_bound(self, monkeypatch) -> None:
        """A mismatched ticket is consumed (single-use) on failed redemption."""
        import asyncio

        from fastapi import HTTPException

        from backend.api.spectate import api_spectate_stream

        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        data = _new_game_via_api()
        gid = data["game_id"]
        other = _new_game_via_api()
        other_gid = other["game_id"]
        try:
            ticket = stream_tickets.issue_stream_ticket(other_gid)
            with pytest.raises(HTTPException):
                asyncio.run(
                    api_spectate_stream(gid, ticket=ticket, x_game_token=None)
                )
            # Now that ticket (for other_gid) is gone and cannot authorize
            # other_gid via the header-less path either.
            assert (
                stream_tickets.consume_stream_ticket(ticket, other_gid) is False
            )
        finally:
            GAME_STORE.pop(gid, None)
            GAME_STORE.pop(other_gid, None)


class TestStreamTicketStore:
    """Unit tests for the short-lived, single-use stream-ticket store."""

    def test_consume_rejects_non_string_and_empty(self) -> None:
        assert stream_tickets.consume_stream_ticket(None, "g") is False
        assert stream_tickets.consume_stream_ticket("", "g") is False

    def test_issue_prunes_expired_tickets(self, monkeypatch) -> None:
        import backend.api.stream_tickets as st

        monkeypatch.setattr(st.time, "monotonic", lambda: 1000.0)
        stale = st.issue_stream_ticket("g")
        assert stale in st._STREAM_TICKETS

        # Advance well beyond the TTL, then issue another ticket; the stale
        # entry must be pruned by the opportunistic cleanup.
        monkeypatch.setattr(st.time, "monotonic", lambda: 1000.0 + st.STREAM_TICKET_TTL_SECONDS + 1)
        st.issue_stream_ticket("g")
        assert stale not in st._STREAM_TICKETS

    def test_consume_expired_ticket_returns_false(self, monkeypatch) -> None:
        import backend.api.stream_tickets as st

        monkeypatch.setattr(st.time, "monotonic", lambda: 500.0)
        ticket = st.issue_stream_ticket("g")

        monkeypatch.setattr(st.time, "monotonic", lambda: 500.0 + st.STREAM_TICKET_TTL_SECONDS + 1)
        assert st.consume_stream_ticket(ticket, "g") is False

    def test_consume_ticket_bound_to_other_game_false(self) -> None:
        ticket = stream_tickets.issue_stream_ticket("game-a")
        assert stream_tickets.consume_stream_ticket(ticket, "game-b") is False


class TestTokenNotInStateJson:
    def test_persisted_state_json_has_no_token_key(self) -> None:
        from backend.database import get_db

        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT state_json, token FROM games WHERE id = ?", (gid,)
                ).fetchone()
            finally:
                conn.close()
            assert row is not None
            raw = row["state_json"]
            assert "token" not in json.loads(raw)
            assert '"token"' not in raw
            assert row["token"] == token
        finally:
            GAME_STORE.pop(gid, None)

    def test_saves_state_json_has_no_token_key(self) -> None:
        from backend.database import get_db

        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            resp = client.post(f"/api/game/{gid}/save")
            assert resp.status_code == 200
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT state_json, token FROM saves WHERE game_id = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (gid,),
                ).fetchone()
            finally:
                conn.close()
            assert row is not None
            assert "token" not in json.loads(row["state_json"])
            assert row["token"] == token
        finally:
            GAME_STORE.pop(gid, None)

    def test_token_round_trips_through_column_only(self) -> None:
        from backend.game.manager import game_load

        data = _new_game_via_api()
        gid = data["game_id"]
        token = data["token"]
        try:
            GAME_STORE.pop(gid, None)
            state = game_load(gid)
            assert state is not None
            assert state.token == token
        finally:
            GAME_STORE.pop(gid, None)

    def test_create_game_strips_token_from_state_json(self) -> None:
        from backend.database import create_game, get_db

        gid = "token-strip-test"
        create_game(
            gid, 42, "TokShip",
            {"seed": 42, "ship": {"name": "TokShip"}, "token": "sekret"},
        )
        try:
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT state_json, token FROM games WHERE id = ?", (gid,)
                ).fetchone()
            finally:
                conn.close()
            assert row is not None
            assert "token" not in json.loads(row["state_json"])
            assert row["token"] == "sekret"
        finally:
            conn = get_db()
            try:
                conn.execute("DELETE FROM games WHERE id = ?", (gid,))
                conn.commit()
            finally:
                conn.close()

    def test_load_game_reattaches_token_from_column(self) -> None:
        from backend.database import create_game, get_db, load_game

        gid = "token-reattach-test"
        create_game(
            gid, 42, "TokShip",
            {"seed": 42, "ship": {"name": "TokShip"}, "token": "sekret"},
        )
        try:
            loaded = load_game(gid)
            assert loaded is not None
            assert loaded["token"] == "sekret"
        finally:
            conn = get_db()
            try:
                conn.execute("DELETE FROM games WHERE id = ?", (gid,))
                conn.commit()
            finally:
                conn.close()

    def test_migration_adds_token_column_to_preexisting_db(self, tmp_path) -> None:
        import sqlite3
        from unittest.mock import patch

        from backend.database import init_db

        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE games (
                id TEXT PRIMARY KEY,
                seed INTEGER NOT NULL,
                ship_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state_json TEXT NOT NULL
            );
            CREATE TABLE saves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                state_json TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()

        with patch("backend.database.DB_PATH", db_path), \
             patch("backend.database.DATA_DIR", tmp_path):
            init_db()

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            games_cols = {r["name"] for r in conn.execute("PRAGMA table_info(games)").fetchall()}
            saves_cols = {r["name"] for r in conn.execute("PRAGMA table_info(saves)").fetchall()}
        finally:
            conn.close()
        assert "token" in games_cols
        assert "token" in saves_cols


class TestLegacyTokenMigration:
    def test_load_game_recovers_embedded_token(self) -> None:
        from backend.database import get_db, load_game

        gid = "legacy-game-embedded-token"
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
                "VALUES (?, ?, ?, ?, ?, ?, '')",
                (
                    gid,
                    42,
                    "LegacyShip",
                    "2020-01-01T00:00:00+00:00",
                    "2020-01-01T00:00:00+00:00",
                    json.dumps({"seed": 42, "ship": {"name": "LegacyShip"}, "token": "legacy-sekret"}),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            loaded = load_game(gid)
            assert loaded is not None
            assert loaded["token"] == "legacy-sekret"

            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT state_json, token FROM games WHERE id = ?", (gid,)
                ).fetchone()
            finally:
                conn.close()
            assert row is not None
            assert row["token"] == "legacy-sekret"
            assert "token" not in json.loads(row["state_json"])
        finally:
            conn = get_db()
            try:
                conn.execute("DELETE FROM games WHERE id = ?", (gid,))
                conn.commit()
            finally:
                conn.close()

    def test_load_save_recovers_embedded_token(self) -> None:
        from backend.database import get_db, load_save

        gid = "legacy-save-embedded-token"
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
                "VALUES (?, ?, ?, ?, ?, ?, '')",
                (
                    gid,
                    42,
                    "LegacyShip",
                    "2020-01-01T00:00:00+00:00",
                    "2020-01-01T00:00:00+00:00",
                    json.dumps({"seed": 42}),
                ),
            )
            conn.execute(
                "INSERT INTO saves (game_id, saved_at, state_json, token) VALUES (?, ?, ?, '')",
                (
                    gid,
                    "2020-01-01T00:00:00+00:00",
                    json.dumps({"seed": 42, "token": "legacy-save-sekret"}),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            loaded = load_save(gid)
            assert loaded is not None
            assert loaded["token"] == "legacy-save-sekret"

            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT state_json, token FROM saves WHERE game_id = ? ORDER BY id DESC LIMIT 1",
                    (gid,),
                ).fetchone()
            finally:
                conn.close()
            assert row is not None
            assert row["token"] == "legacy-save-sekret"
            assert "token" not in json.loads(row["state_json"])
        finally:
            conn = get_db()
            try:
                conn.execute("DELETE FROM saves WHERE game_id = ?", (gid,))
                conn.execute("DELETE FROM games WHERE id = ?", (gid,))
                conn.commit()
            finally:
                conn.close()

    def test_legacy_row_without_embedded_token_falls_back_to_empty(self) -> None:
        from backend.database import get_db, load_game

        gid = "legacy-game-no-token"
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
                "VALUES (?, ?, ?, ?, ?, ?, '')",
                (
                    gid,
                    42,
                    "LegacyShip",
                    "2020-01-01T00:00:00+00:00",
                    "2020-01-01T00:00:00+00:00",
                    json.dumps({"seed": 42, "ship": {"name": "LegacyShip"}}),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            loaded = load_game(gid)
            assert loaded is not None
            assert loaded["token"] == ""

            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT state_json, token FROM games WHERE id = ?", (gid,)
                ).fetchone()
            finally:
                conn.close()
            assert row is not None
            assert row["token"] == ""
        finally:
            conn = get_db()
            try:
                conn.execute("DELETE FROM games WHERE id = ?", (gid,))
                conn.commit()
            finally:
                conn.close()

    def test_load_game_empty_column_does_not_clobber_present_token(self) -> None:
        from backend.database import get_db, load_game

        gid = "mixed-guard-game-present-token"
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
                "VALUES (?, ?, ?, ?, ?, ?, '')",
                (
                    gid,
                    42,
                    "MixedShip",
                    "2020-01-01T00:00:00+00:00",
                    "2020-01-01T00:00:00+00:00",
                    json.dumps({"seed": 42, "ship": {"name": "MixedShip"}, "token": "embedded-sekret"}),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            loaded = load_game(gid)
            assert loaded is not None
            assert loaded["token"] == "embedded-sekret"

            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT state_json, token FROM games WHERE id = ?", (gid,)
                ).fetchone()
            finally:
                conn.close()
            assert row is not None
            assert row["token"] == "embedded-sekret"
            assert "token" not in json.loads(row["state_json"])
        finally:
            conn = get_db()
            try:
                conn.execute("DELETE FROM games WHERE id = ?", (gid,))
                conn.commit()
            finally:
                conn.close()

    def test_load_game_empty_column_and_empty_embedded_returns_empty_string(self) -> None:
        from backend.database import get_db, load_game

        gid = "mixed-guard-game-empty-token"
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
                "VALUES (?, ?, ?, ?, ?, ?, '')",
                (
                    gid,
                    42,
                    "EmptyShip",
                    "2020-01-01T00:00:00+00:00",
                    "2020-01-01T00:00:00+00:00",
                    json.dumps({"seed": 42, "ship": {"name": "EmptyShip"}}),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            loaded = load_game(gid)
            assert loaded is not None
            assert loaded["token"] == ""
            assert loaded["seed"] == 42
        finally:
            conn = get_db()
            try:
                conn.execute("DELETE FROM games WHERE id = ?", (gid,))
                conn.commit()
            finally:
                conn.close()

    def test_load_save_empty_column_does_not_clobber_present_token(self) -> None:
        from backend.database import get_db, load_save

        gid = "mixed-guard-save-present-token"
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO games (id, seed, ship_name, created_at, updated_at, state_json, token) "
                "VALUES (?, ?, ?, ?, ?, ?, '')",
                (
                    gid,
                    7,
                    "MixedShip",
                    "2020-01-01T00:00:00+00:00",
                    "2020-01-01T00:00:00+00:00",
                    json.dumps({"seed": 7}),
                ),
            )
            conn.execute(
                "INSERT INTO saves (game_id, saved_at, state_json, token) VALUES (?, ?, ?, '')",
                (
                    gid,
                    "2020-01-01T00:00:00+00:00",
                    json.dumps({"seed": 7, "token": "save-embedded-sekret"}),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            loaded = load_save(gid)
            assert loaded is not None
            assert loaded["token"] == "save-embedded-sekret"

            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT state_json, token FROM saves WHERE game_id = ? ORDER BY id DESC LIMIT 1",
                    (gid,),
                ).fetchone()
            finally:
                conn.close()
            assert row is not None
            assert row["token"] == "save-embedded-sekret"
            assert "token" not in json.loads(row["state_json"])
        finally:
            conn = get_db()
            try:
                conn.execute("DELETE FROM saves WHERE game_id = ?", (gid,))
                conn.execute("DELETE FROM games WHERE id = ?", (gid,))
                conn.commit()
            finally:
                conn.close()
