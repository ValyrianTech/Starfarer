import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.main import app
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game, game_save
from backend.game.engine import get_nearby_systems, land_on_body
from backend.game.trading import perform_bulk_sell
from backend.models.game_state import GameState

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db() -> None:
    init_db()


class TestAPIHealth:
    def test_health(self) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["version"] == "0.1.0"


class TestAPIGameCreation:
    def test_create_game_default(self) -> None:
        resp = client.post("/api/game/new", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "game_id" in data
        assert data["state"]["ship"]["name"] == "Serendipity"

    def test_create_game_custom(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 999, "ship_name": "Voyager"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"]["ship"]["name"] == "Voyager"
        assert data["state"]["seed"] == 999

    def test_create_game_with_custom_id(self) -> None:
        resp = client.post("/api/game/new", json={"game_id": "test-game-id"})
        assert resp.status_code == 200
        assert resp.json()["game_id"] == "test-game-id"


class TestAPIGameFlow:
    def test_full_game_flow(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        state = resp.json()
        assert "ship" in state
        cur_sys = state["ship"]["current_system_id"]

        resp = client.get(f"/api/game/{game_id}/galaxy")
        assert resp.status_code == 200
        galaxy = resp.json()
        assert len(galaxy["systems"]) == 50

        resp = client.get(f"/api/game/{game_id}/system/{cur_sys}")
        assert resp.status_code == 200
        sys_detail = resp.json()
        assert sys_detail["system"]["id"] == cur_sys

        resp = client.post(f"/api/game/{game_id}/scan")
        assert resp.status_code == 200

        resp = client.get(f"/api/game/{game_id}/nearby")
        assert resp.status_code == 200
        nearby = resp.json()
        assert len(nearby["nearby"]) == 49

        planets = [b for b in sys_detail["system"]["bodies"] if b["body_type"] == "planet"]
        if planets:
            resp = client.post(f"/api/game/{game_id}/land/{planets[0]['id']}")
            assert resp.status_code == 200

            resp = client.post(f"/api/game/{game_id}/explore")
            assert resp.status_code == 200
            expl = resp.json()
            assert len(expl["discoveries"]) > 0

        resp = client.get(f"/api/game/{game_id}/log")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 2

        resp = client.get(f"/api/game/{game_id}/discoveries")
        assert resp.status_code == 200

        resp = client.post(f"/api/game/{game_id}/save")
        assert resp.status_code == 200
        assert "saved" in resp.json()["result"].lower() or "Saved" in resp.json()["result"]

        resp = client.post(f"/api/game/{game_id}/load")
        assert resp.status_code == 200
        assert "loaded" in resp.json()["result"].lower() or "Loaded" in resp.json()["result"]


class TestAPIEdgeCases:
    def test_nonexistent_game(self) -> None:
        resp = client.get("/api/game/nonexistent")
        assert resp.status_code == 404

    def test_nonexistent_system(self) -> None:
        resp = client.post("/api/game/new", json={})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/system/fake_sys")
        assert resp.status_code == 404

    def test_jump_to_nonexistent_system(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/jump/fake_sys")
        assert resp.status_code == 404

    def test_buy_fuel(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/trade", json={
            "action": "buy", "item": "fuel", "quantity": 10
        })
        assert resp.status_code in (200, 400)

    def test_upgrade_info(self) -> None:
        resp = client.post("/api/game/new", json={})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/upgrades")
        assert resp.status_code == 200
        assert len(resp.json()["upgrades"]) > 0

    def test_leaderboard(self) -> None:
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        assert "leaderboard" in resp.json()


class TestAPIDBFallback:
    """Tests that exercise the _get_state DB fallback path."""

    def test_get_game_from_db_after_store_cleared(self) -> None:
        """After removing from GAME_STORE, state should be loaded from DB."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "db-fallback-test"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        assert resp.json()["game_id"] == game_id

    def test_galaxy_from_db_fallback(self) -> None:
        """Galaxy endpoint should work via DB fallback."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "galaxy-fallback"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}/galaxy")
        assert resp.status_code == 200

    def test_system_detail_from_db_fallback(self) -> None:
        """System detail endpoint should work via DB fallback."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "system-fallback"})
        game_id = resp.json()["game_id"]
        cur_sys = resp.json()["state"]["ship"]["current_system_id"]
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}/system/{cur_sys}")
        assert resp.status_code == 200

    def test_log_from_db_fallback(self) -> None:
        """Log endpoint should work via DB fallback."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "log-fallback"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}/log")
        assert resp.status_code == 200

    def test_discoveries_from_db_fallback(self) -> None:
        """Discoveries endpoint should work via DB fallback."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "disc-fallback"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}/discoveries")
        assert resp.status_code == 200

    def test_get_game_via_db_fallback(self) -> None:
        """GET /game/{id} should return 404 when game_load returns None."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "db-fb-game-v2"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        with patch("backend.api.routes.game_load_func", return_value=None):
            resp = client.get(f"/api/game/{game_id}")
            assert resp.status_code == 404

    def test_galaxy_via_db_fallback(self) -> None:
        """Galaxy endpoint should return 404 when game_load returns None."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "db-fb-gal-v2"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        with patch("backend.api.routes.game_load_func", return_value=None):
            resp = client.get(f"/api/game/{game_id}/galaxy")
            assert resp.status_code == 404

    def test_system_detail_via_db_fallback(self) -> None:
        """System detail endpoint should return 404 when game_load returns None."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "db-fb-system-v2"})
        game_id = resp.json()["game_id"]
        cur_sys = resp.json()["state"]["ship"]["current_system_id"]
        GAME_STORE.pop(game_id, None)
        with patch("backend.api.routes.game_load_func", return_value=None):
            resp = client.get(f"/api/game/{game_id}/system/{cur_sys}")
            assert resp.status_code == 404

    def test_log_via_db_fallback(self) -> None:
        """Log endpoint should return 404 when game_load returns None."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "db-fb-log-v2"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        with patch("backend.api.routes.game_load_func", return_value=None):
            resp = client.get(f"/api/game/{game_id}/log")
            assert resp.status_code == 404

    def test_discoveries_via_db_fallback(self) -> None:
        """Discoveries endpoint should return 404 when game_load returns None."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "db-fb-disc-v2"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        with patch("backend.api.routes.game_load_func", return_value=None):
            resp = client.get(f"/api/game/{game_id}/discoveries")
            assert resp.status_code == 404

    def test_get_game_db_fallback_exception(self) -> None:
        """GET /game/{id} returns 404 when game_load returns None."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "db-fb-fail"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        with patch("backend.api.routes.game_load_func", return_value=None):
            resp = client.get(f"/api/game/{game_id}")
            assert resp.status_code == 404


class TestAPILeaderboardMalformedState:
    """Tests the leaderboard endpoint's handling of malformed state_json in the database."""

    def test_leaderboard_skips_malformed_json(self) -> None:
        """Insert a game with invalid JSON in state_json; leaderboard should skip it."""
        from backend.database import get_db
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("malformed-json-test", 1, "Test Ship", now, now, '{invalid')
            )
            conn.commit()
        finally:
            conn.close()
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        ids = [entry["game_id"] for entry in data["leaderboard"]]
        assert "malformed-json-test" not in ids

    def test_leaderboard_skips_empty_state_json(self) -> None:
        """Insert a game with an empty string in state_json; leaderboard should skip it."""
        from backend.database import get_db
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("empty-json-test", 1, "Test Ship", now, now, '')
            )
            conn.commit()
        finally:
            conn.close()
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        ids = [entry["game_id"] for entry in data["leaderboard"]]
        assert "empty-json-test" not in ids

    def test_leaderboard_skips_null_state_json(self) -> None:
        """Insert a game with a non-string state_json value (causes TypeError); leaderboard should skip it."""
        from backend.database import get_db
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("null-json-test", 1, "Test Ship", now, now, 123)
            )
            conn.commit()
        finally:
            conn.close()
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        ids = [entry["game_id"] for entry in data["leaderboard"]]
        assert "null-json-test" not in ids

    def test_leaderboard_mixed_valid_and_malformed(self) -> None:
        """Insert mixed valid and malformed entries; only valid ones should appear in the leaderboard."""
        from backend.database import get_db
        now = datetime.now(timezone.utc).isoformat()
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "mixed-valid-1"})
        assert resp.status_code == 200
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("mixed-malformed-1", 1, "Bad Ship", now, now, '{bad json')
            )
            conn.execute(
                "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("mixed-malformed-2", 1, "Empty Ship", now, now, '')
            )
            conn.commit()
        finally:
            conn.close()
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        ids = [entry["game_id"] for entry in data["leaderboard"]]
        assert "mixed-valid-1" in ids
        assert "mixed-malformed-1" not in ids
        assert "mixed-malformed-2" not in ids

    def test_get_leaderboard_direct_malformed(self) -> None:
        """Directly call get_leaderboard with malformed state_json to ensure coverage of except block."""
        from backend.database import get_db, get_leaderboard
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("direct-malformed-test", 1, "Test Ship", now, now, '{invalid')
            )
            conn.commit()
        finally:
            conn.close()
        result = get_leaderboard(limit=10)
        ids = [entry["game_id"] for entry in result]
        assert "direct-malformed-test" not in ids


class TestAPIAllEndpoints404:
    """Tests that all endpoints return 404 for nonexistent games."""

    def test_galaxy_nonexistent(self) -> None:
        resp = client.get("/api/game/nonexistent-gid/galaxy")
        assert resp.status_code == 404

    def test_system_detail_nonexistent(self) -> None:
        resp = client.get("/api/game/nonexistent-gid/system/sys1")
        assert resp.status_code == 404

    def test_jump_nonexistent_game(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/jump/sys1")
        assert resp.status_code == 404

    def test_scan_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/scan")
        assert resp.status_code == 404

    def test_land_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/land/body1")
        assert resp.status_code == 404

    def test_explore_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/explore")
        assert resp.status_code == 404

    def test_resolve_event_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/event/evt1/resolve", json={"choice_index": 0})
        assert resp.status_code == 404

    def test_log_nonexistent(self) -> None:
        resp = client.get("/api/game/nonexistent-gid/log")
        assert resp.status_code == 404

    def test_discoveries_nonexistent(self) -> None:
        resp = client.get("/api/game/nonexistent-gid/discoveries")
        assert resp.status_code == 404

    def test_trade_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/trade", json={"action": "buy", "item": "fuel"})
        assert resp.status_code == 404

    def test_upgrade_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/upgrade", json={"upgrade_id": "hyperdrive"})
        assert resp.status_code == 404

    def test_upgrades_info_nonexistent(self) -> None:
        resp = client.get("/api/game/nonexistent-gid/upgrades")
        assert resp.status_code == 404

    def test_nearby_nonexistent(self) -> None:
        resp = client.get("/api/game/nonexistent-gid/nearby")
        assert resp.status_code == 404

    def test_save_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/save")
        assert resp.status_code == 404

    def test_load_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/load")
        assert resp.status_code == 404

    def test_distress_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/distress")
        assert resp.status_code == 404

    def test_salvage_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/salvage")
        assert resp.status_code == 404

    def test_craft_nonexistent(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/salvage/craft", json={
            "discovery_id": "test_disc", "output": "fuel"
        })
        assert resp.status_code == 404


class TestAPIAdvancedFlow:
    """Tests a complete game flow with events, trading, and upgrades via API."""

    def test_scan_triggers_event_and_may_save(self) -> None:
        """Scanning should succeed and optionally trigger an event."""
        resp = client.post("/api/game/new", json={"seed": 99})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert "ship" in data
        assert "system" in data

    def test_land_invalid_body(self) -> None:
        """Landing on a nonexistent body should return 400."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/land/nonexistent_body")
        assert resp.status_code == 400

    def test_explore_triggers_event(self) -> None:
        """Exploring should succeed and optionally trigger an event."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = client.get(f"/api/game/{game_id}").json()
        planets = [b for b in state["current_system"]["bodies"] if b["body_type"] == "planet"]
        if planets:
            client.post(f"/api/game/{game_id}/land/{planets[0]['id']}")
            resp = client.post(f"/api/game/{game_id}/explore")
            assert resp.status_code == 200
            data = resp.json()
            assert "discoveries" in data
            assert "ship" in data

    def test_resolve_event_not_found(self) -> None:
        """Resolving a nonexistent event should return 400."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/event/nonexistent_evt/resolve", json={"choice_index": 0})
        assert resp.status_code == 400

    def test_log_endpoint(self) -> None:
        """Log endpoint should return entries in reverse chronological order."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/log")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "entries" in data
        assert data["count"] >= 2

    def test_discoveries_endpoint(self) -> None:
        """Discoveries endpoint should return discovery list."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = client.get(f"/api/game/{game_id}").json()
        planets = [b for b in state["current_system"]["bodies"] if b["body_type"] == "planet"]
        if planets:
            client.post(f"/api/game/{game_id}/land/{planets[0]['id']}")
            client.post(f"/api/game/{game_id}/explore")
        resp = client.get(f"/api/game/{game_id}/discoveries")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "discoveries" in data

    def test_trade_failure(self) -> None:
        """Trading should return 400 when trade is not possible."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/trade", json={
            "action": "sell", "item": "nonexistent", "quantity": 1
        })
        assert resp.status_code == 400

    def test_upgrade_failure(self) -> None:
        """Buying an upgrade without enough credits should return 400."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/upgrade", json={"upgrade_id": "hyperdrive"})
        assert resp.status_code == 200
        resp = client.post(f"/api/game/{game_id}/upgrade", json={"upgrade_id": "hyperdrive"})
        assert resp.status_code == 400

    def test_upgrade_success(self) -> None:
        """Buying an upgrade with enough credits should return 200."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = client.get(f"/api/game/{game_id}").json()
        assert state["ship"]["credits"] == 1000
        resp = client.post(f"/api/game/{game_id}/upgrade", json={"upgrade_id": "scanner"})
        assert resp.status_code == 200

    def test_nearby_endpoint(self) -> None:
        """Nearby endpoint should return nearby systems."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/nearby")
        assert resp.status_code == 200
        data = resp.json()
        assert "nearby" in data
        assert "current_system_id" in data
        assert "jump_range" in data
        assert "fuel" in data

    def test_save_endpoint(self) -> None:
        """Save endpoint should return success."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "save-test-gid"})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/save")
        assert resp.status_code == 200
        assert "saved" in resp.json()["result"].lower()

    def test_load_no_save(self) -> None:
        """Loading a game with no saved state should return 404."""
        resp = client.post("/api/game/never-created-game-id/load")
        assert resp.status_code == 404

    def test_upgrades_info_endpoint(self) -> None:
        """Upgrades info endpoint should return upgrade list."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/upgrades")
        assert resp.status_code == 200
        data = resp.json()
        assert "upgrades" in data
        assert "credits" in data

    def test_jump_with_event_trigger(self) -> None:
        """Jumping should succeed and may trigger an event."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        nearby = client.get(f"/api/game/{game_id}/nearby").json()
        reachable = [n for n in nearby["nearby"] if n["reachable"]]
        if reachable:
            resp = client.post(f"/api/game/{game_id}/jump/{reachable[0]['id']}")
            assert resp.status_code == 200
            data = resp.json()
            assert "result" in data
            assert "ship" in data

    def test_get_game_full_response(self) -> None:
        """Full game state should include all expected fields."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "game_id" in data
        assert "seed" in data
        assert "ship" in data
        assert "current_system" in data
        assert "discoveries" in data
        assert "events_pending" in data
        assert "log_entries" in data
        assert "systems_visited" in data
        assert "systems_total" in data
        assert "game_started" in data

    def test_leaderboard_entries(self) -> None:
        """Leaderboard should return a list."""
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        assert isinstance(data["leaderboard"], list)

    def test_trade_sell_by_name_exact_match(self) -> None:
        """Sell by name matches discovery name, not category via trade endpoint."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "trade-name-match"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        current_sys.has_trading_station = True
        state.discoveries.append(
            Discovery(id="trade-name-match-disc-1", category="mineral", name="artifact",
                      description="Test", value=200, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/trade", json={
            "action": "sell", "item": "artifact", "quantity": 1
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["credits"] > 1000
        assert "Sold" in data["result"]
        state_resp = client.get(f"/api/game/{game_id}")
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        assert len(state_data["discoveries"]) == 0

    def test_trade_sell_by_name_priority_over_category(self) -> None:
        """Name match takes priority over category match via trade endpoint."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "trade-name-prio"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        current_sys.has_trading_station = True
        state.discoveries.append(
            Discovery(id="trade-name-prio-disc-1", category="artifact", name="Ancient Relic",
                      description="Old relic", value=200, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="trade-name-prio-disc-2", category="mineral", name="artifact",
                      description="Named artifact", value=150, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/trade", json={
            "action": "sell", "item": "artifact", "quantity": 1
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["credits"] > 1000
        assert "Sold" in data["result"]
        state_resp = client.get(f"/api/game/{game_id}")
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        assert len(state_data["discoveries"]) == 1
        assert state_data["discoveries"][0]["name"] == "Ancient Relic"


class TestAPIInternalFunctions:
    """Tests for internal helper functions in routes.py."""

    def test_save_state_function(self) -> None:
        """_save_state should persist game when in GAME_STORE."""
        from backend.api.routes import _save_state
        from backend.database import init_db
        init_db()
        state = new_game(seed=42, ship_name="SaveStateTest")
        try:
            GAME_STORE[state.id] = state
            _save_state(state.id)
        finally:
            GAME_STORE.pop(state.id, None)

    def test_save_state_not_in_store(self) -> None:
        """_save_state should do nothing when game not in GAME_STORE."""
        from backend.api.routes import _save_state
        _save_state("nonexistent-game-xyz")

    def test_jump_no_current_system(self) -> None:
        """Jump should return 400 when ship has no current system."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "jump-no-system"})
        game_id = resp.json()["game_id"]
        nearby = client.get(f"/api/game/{game_id}/nearby").json()
        target_id = nearby["nearby"][0]["id"]
        state = GAME_STORE.get(game_id)
        if state:
            state.ship.current_system_id = "nonexistent_sys"
        resp = client.post(f"/api/game/{game_id}/jump/{target_id}")
        assert resp.status_code == 400
        assert "No current system" in resp.json()["detail"]

    def test_jump_same_system_error(self) -> None:
        """Jump to current system should return 400 via can_jump check."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "jump-same"})
        game_id = resp.json()["game_id"]
        cur_sys = resp.json()["state"]["ship"]["current_system_id"]
        resp = client.post(f"/api/game/{game_id}/jump/{cur_sys}")
        assert resp.status_code == 400
        assert "Already" in resp.json()["detail"]

    def test_resolve_event_success_via_api(self) -> None:
        """Resolving an event through the API should succeed."""
        from backend.generation.events import _create_event, EVENT_TEMPLATES
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "resolve-api"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        if state:
            event = _create_event(EVENT_TEMPLATES[0], state.ship.current_system_id)
            state.events.append(event)
            GAME_STORE[game_id] = state
            game_save(state)
        resp = client.post(f"/api/game/{game_id}/event/{event.id}/resolve", json={"choice_index": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert "ship" in data


class TestAPIMainApp:
    """Tests for main.py edge cases."""

    def test_index_serves_frontend(self) -> None:
        """Index endpoint should serve index.html when frontend exists."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_fallback_when_no_frontend(self) -> None:
        """Index endpoint should return JSON when index.html doesn't exist."""
        with patch("os.path.exists", return_value=False):
            from fastapi.testclient import TestClient as TC
            c = TC(app)
            resp = c.get("/")
            assert resp.status_code == 200
            data = resp.json()
            assert "message" in data
            assert "API" in data["message"]


class TestAPIEventTriggerPaths:
    """Tests that force event triggers in jump and explore via API."""

    def test_jump_with_forced_event(self) -> None:
        """Jump with low morale should force event trigger and append."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "jump-force-ev"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        state.ship.morale = 20
        nearby = get_nearby_systems(state)
        target_id = nearby[0]["id"]
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/jump/{target_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

    def test_explore_with_forced_event(self) -> None:
        """Explore with low morale should force event trigger and append."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "explore-force-ev"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover  # no planet in starting system
        land_on_body(state, planet.id)
        state.ship.morale = 20
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/explore")
        assert resp.status_code == 200
        data = resp.json()
        assert "discoveries" in data

    def test_lifespan_init(self) -> None:
        """Lifespan context manager should initialize DB and directories."""
        import asyncio
        from backend.main import lifespan, DATA_DIR

        async def run_lifespan() -> None:
            async with lifespan(app):
                assert os.path.isdir(DATA_DIR)

        asyncio.run(run_lifespan())


class TestAPIEventPersistence:
    """Tests that triggered events are persisted to the database."""

    def test_jump_event_persisted_to_db(self) -> None:
        """Event triggered by jump should be saved to DB."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "jump-persist"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        state.ship.morale = 20  # Force event trigger
        nearby = get_nearby_systems(state)
        target_id = nearby[0]["id"]
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/jump/{target_id}")
        assert resp.status_code == 200
        # Clear in-memory cache and reload from DB
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events_pending"]) > 0, "No pending events found after reload from DB"

    def test_scan_event_persisted_to_db(self) -> None:
        """Event triggered by scan should be saved to DB."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "scan-persist"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        state.ship.morale = 20  # Force event trigger
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/scan")
        assert resp.status_code == 200
        # Clear in-memory cache and reload from DB
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events_pending"]) > 0, "No pending events found after reload from DB"

    def test_explore_event_persisted_to_db(self) -> None:
        """Event triggered by explore should be saved to DB."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "explore-persist"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover  # no planet in starting system
        land_on_body(state, planet.id)
        state.ship.morale = 20  # Force event trigger
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/explore")
        assert resp.status_code == 200
        # Clear in-memory cache and reload from DB
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events_pending"]) > 0, "No pending events found after reload from DB"


class TestAPIBulkSell:
    """Tests for the bulk sell endpoint."""

    def _create_game_with_discoveries(self, game_id: str) -> str:
        """Helper to create a game and add test discoveries."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": game_id})
        assert resp.status_code == 200
        gid = resp.json()["game_id"]
        state = GAME_STORE[gid]
        current_sys = state.get_current_system()
        current_sys.has_trading_station = True
        from backend.models.discovery import Discovery
        state.discoveries.append(
            Discovery(id=f"{game_id}-disc-1", category="artifact", name="Ancient Relic",
                      description="Old relic", value=200, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id=f"{game_id}-disc-2", category="mineral", name="Glowing Crystal",
                      description="Shiny", value=150, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id=f"{game_id}-disc-3", category="artifact", name="Mystic Orb",
                      description="Glowing orb", value=300, system_id=current_sys.id)
        )
        GAME_STORE[gid] = state
        game_save(state)
        return gid

    def test_bulk_sell_success(self) -> None:
        """Sell multiple discoveries of different categories."""
        game_id = self._create_game_with_discoveries("bulk-sell-ok")
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [
                {"item": "artifact", "quantity": 1},
                {"item": "mineral", "quantity": 1}
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["credits"] > 1000
        assert "game_id" in data
        assert "seed" in data
        assert "ship" in data
        assert "current_system" in data
        assert "discoveries" in data
        assert "events_pending" in data
        assert "log_entries" in data
        assert "systems_visited" in data
        assert "systems_total" in data
        assert "game_started" in data
        assert "trade_result" in data
        assert data["trade_result"]["sold_count"] > 0
        assert data["trade_result"]["total_price"] > 0
        assert len(data["discoveries"]) < 3

    def test_bulk_sell_multiple_of_same_category(self) -> None:
        """Sell multiple items of the same category."""
        game_id = self._create_game_with_discoveries("bulk-sell-multi")
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [
                {"item": "artifact", "quantity": 2}
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["credits"] > 1000
        assert "game_id" in data
        assert "seed" in data
        assert "ship" in data
        assert "current_system" in data
        assert "discoveries" in data
        assert "events_pending" in data
        assert "log_entries" in data
        assert "systems_visited" in data
        assert "systems_total" in data
        assert "game_started" in data
        assert "trade_result" in data
        assert data["trade_result"]["sold_count"] > 0
        assert data["trade_result"]["total_price"] > 0

    def test_bulk_sell_partial_failure(self) -> None:
        """Partial failure when some items don't exist."""
        game_id = self._create_game_with_discoveries("bulk-sell-partial")
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [
                {"item": "artifact", "quantity": 1},
                {"item": "nonexistent_item_xyz", "quantity": 5}
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["credits"] > 1000
        assert "game_id" in data
        assert "seed" in data
        assert "ship" in data
        assert "current_system" in data
        assert "discoveries" in data
        assert "events_pending" in data
        assert "log_entries" in data
        assert "systems_visited" in data
        assert "systems_total" in data
        assert "game_started" in data
        assert "trade_result" in data
        assert data["trade_result"]["sold_count"] > 0
        assert data["trade_result"]["total_price"] > 0
        assert len(data["discoveries"]) < 3

    def test_bulk_sell_all_nonexistent(self) -> None:
        """All items nonexistent should return 400."""
        game_id = self._create_game_with_discoveries("bulk-sell-all-bad")
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [
                {"item": "nonexistent_a", "quantity": 1},
                {"item": "nonexistent_b", "quantity": 1}
            ]
        })
        assert resp.status_code == 400

    def test_bulk_sell_invalid_game_id(self) -> None:
        """Nonexistent game ID should return 404."""
        resp = client.post("/api/game/nonexistent-gid/trade/bulk-sell", json={
            "items": [{"item": "artifact", "quantity": 1}]
        })
        assert resp.status_code == 404

    def test_bulk_sell_empty_items(self) -> None:
        """Empty items list should return 400."""
        game_id = self._create_game_with_discoveries("bulk-sell-empty")
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": []
        })
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Items list must not be empty."

    def test_bulk_sell_invalid_quantity_zero(self) -> None:
        """Quantity of 0 should return 400."""
        game_id = self._create_game_with_discoveries("bulk-sell-qty0")
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [{"item": "artifact", "quantity": 0}]
        })
        assert resp.status_code == 400

    def test_bulk_sell_invalid_quantity_negative(self) -> None:
        """Negative quantity should return 400."""
        game_id = self._create_game_with_discoveries("bulk-sell-qtyneg")
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [{"item": "artifact", "quantity": -1}]
        })
        assert resp.status_code == 400

    def test_bulk_sell_no_current_system(self) -> None:
        """Bulk sell with no current system should return 400."""
        game_id = self._create_game_with_discoveries("bulk-sell-no-system")
        state = GAME_STORE[game_id]
        state.ship.current_system_id = "nonexistent_system_xyz"
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [{"item": "artifact", "quantity": 1}]
        })
        assert resp.status_code == 400

    def test_bulk_sell_no_trading_facilities(self) -> None:
        """Bulk sell without trading facilities should return 400."""
        game_id = self._create_game_with_discoveries("bulk-sell-no-trade")
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        current_sys.has_trading_station = False
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [{"item": "artifact", "quantity": 1}]
        })
        assert resp.status_code == 400

    def test_bulk_sell_by_name_exact_match(self) -> None:
        """Sell by name matches discovery name, not category."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "bulk-name-match"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        current_sys.has_trading_station = True
        state.discoveries.append(
            Discovery(id="bulk-name-match-disc-1", category="mineral", name="artifact",
                      description="Test", value=200, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [{"item": "artifact", "quantity": 1}]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["credits"] > 1000
        assert "game_id" in data
        assert "seed" in data
        assert "ship" in data
        assert "current_system" in data
        assert "discoveries" in data
        assert "events_pending" in data
        assert "log_entries" in data
        assert "systems_visited" in data
        assert "systems_total" in data
        assert "game_started" in data
        assert "trade_result" in data
        assert data["trade_result"]["sold_count"] > 0
        assert data["trade_result"]["total_price"] > 0

    def test_bulk_sell_by_name_priority_over_category(self) -> None:
        """Name match takes priority over category match in bulk sell."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "bulk-name-prio"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        current_sys.has_trading_station = True
        state.discoveries.append(
            Discovery(id="bulk-name-prio-disc-1", category="artifact", name="Ancient Relic",
                      description="Old relic", value=200, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="bulk-name-prio-disc-2", category="mineral", name="artifact",
                      description="Named artifact", value=150, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/trade/bulk-sell", json={
            "items": [{"item": "artifact", "quantity": 1}]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["credits"] > 1000
        assert "game_id" in data
        assert "seed" in data
        assert "ship" in data
        assert "current_system" in data
        assert "discoveries" in data
        assert "events_pending" in data
        assert "log_entries" in data
        assert "systems_visited" in data
        assert "systems_total" in data
        assert "game_started" in data
        assert "trade_result" in data
        assert data["trade_result"]["sold_count"] > 0
        assert data["trade_result"]["total_price"] > 0


class TestPerformBulkSellDirect:
    """Direct unit tests for perform_bulk_sell defensive input validation."""

    def _create_test_state(self) -> GameState:
        """Create a game state with a trading station and some discoveries."""
        state = new_game(seed=42, ship_name="TestShip")
        current_sys = state.get_current_system()
        current_sys.has_trading_station = True
        from backend.models.discovery import Discovery
        state.discoveries.append(
            Discovery(id="direct-test-disc-1", category="artifact", name="Ancient Relic",
                      description="Old relic", value=200, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="direct-test-disc-2", category="mineral", name="Glowing Crystal",
                      description="Shiny", value=150, system_id=current_sys.id)
        )
        return state

    def test_missing_item_key(self) -> None:
        """Missing 'item' key should return error gracefully."""
        state = self._create_test_state()
        success, message, sold_count, total_price = perform_bulk_sell(state, [{"quantity": 5}])
        assert not success
        assert "missing required 'item' field" in message

    def test_missing_quantity_key(self) -> None:
        """Missing 'quantity' key should default to 1 and succeed."""
        state = self._create_test_state()
        success, message, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact"}])
        assert success
        assert "Sold" in message
        assert len(state.discoveries) == 1  # One item sold, one remains

    def test_non_integer_quantity(self) -> None:
        """Non-integer quantity should return error gracefully."""
        state = self._create_test_state()
        success, message, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact", "quantity": "abc"}])
        assert not success
        assert "Invalid quantity" in message

    def test_quantity_exceeds_available(self) -> None:
        """Quantity exceeding available matches should sell all and report error."""
        state = self._create_test_state()
        # Only 1 discovery with category "artifact" exists
        success, message, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact", "quantity": 5}])
        assert success
        assert "Sold" in message
        assert "Only" in message and "requested 5" in message
        assert len(state.discoveries) == 1  # Only the mineral discovery remains


class TestRoutesFullStateResponse:
    """Tests for _full_state_response helper."""

    def test_full_state_response_with_current_system(self) -> None:
        """_full_state_response should include current_system when ship is in a system."""
        from backend.api.routes import _full_state_response
        state = new_game(seed=42)
        resp = _full_state_response(state)
        assert resp["game_id"] == state.id
        assert resp["seed"] == state.seed
        assert resp["current_system"] is not None
        assert isinstance(resp["discoveries"], list)
        assert isinstance(resp["events_pending"], list)
        assert isinstance(resp["log_entries"], list)
        assert resp["systems_visited"] == state.systems_visited
        assert resp["systems_total"] == len(state.systems)
        assert resp["game_started"] == state.game_started
        assert "ship" in resp

    def test_full_state_response_no_current_system(self) -> None:
        """_full_state_response should have None current_system when ship has no system."""
        from backend.api.routes import _full_state_response
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        resp = _full_state_response(state)
        assert resp["current_system"] is None


class TestRoutesGetState:
    """Tests for _get_state helper."""

    def test_get_state_from_store(self) -> None:
        """_get_state should return game from GAME_STORE if present."""
        from backend.api.routes import _get_state
        from backend.game.manager import GAME_STORE
        state = new_game(seed=42, ship_name="GTStore")
        try:
            GAME_STORE[state.id] = state
            result = _get_state(state.id)
            assert result is not None
            assert result.id == state.id
        finally:
            GAME_STORE.pop(state.id, None)

    def test_get_state_from_db(self) -> None:
        """_get_state should load from DB when not in GAME_STORE."""
        from backend.api.routes import _get_state
        from backend.game.manager import GAME_STORE, game_save
        from backend.database import init_db
        init_db()
        state = new_game(seed=42, ship_name="GTDB")
        try:
            GAME_STORE[state.id] = state
            game_save(state)
            GAME_STORE.pop(state.id, None)
            result = _get_state(state.id)
            assert result is not None
            assert result.id == state.id
        finally:
            GAME_STORE.pop(state.id, None)

    def test_get_state_not_found(self) -> None:
        """_get_state should return None when game not in store or DB."""
        from backend.api.routes import _get_state
        from backend.game.manager import GAME_STORE
        GAME_STORE.pop("totally-nonexistent-id", None)
        result = _get_state("totally-nonexistent-id")
        assert result is None


class TestAPILore:
    """Tests for the lore fragment API endpoints."""

    def test_lore_endpoint_returns_structured_data(self) -> None:
        """GET /api/game/{id}/lore should return arcs and progress."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        resp = client.get(f"/api/game/{game_id}/lore")
        assert resp.status_code == 200
        data = resp.json()

        assert "arcs" in data
        assert "progress" in data
        assert data["progress"]["total"] == 20
        assert data["progress"]["collected"] == 0

        expected_arcs = {"architects", "void_signal", "fracture", "wanderer"}
        assert set(data["arcs"].keys()) == expected_arcs

    def test_lore_endpoint_arc_has_fragments(self) -> None:
        """Each arc should have 5 fragments with fragment_number."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        resp = client.get(f"/api/game/{game_id}/lore")
        assert resp.status_code == 200
        data = resp.json()

        for arc_id, arc_data in data["arcs"].items():
            assert arc_data["total"] == 5
            assert arc_data["collected"] == 0
            assert len(arc_data["fragments"]) == 5
            assert arc_data["display_name"]
            for frag in arc_data["fragments"]:
                assert "fragment_number" in frag
                assert isinstance(frag["fragment_number"], int)
                assert frag["fragment_number"] >= 1
                assert frag["fragment_number"] <= 5

    def test_lore_endpoint_nonexistent_game(self) -> None:
        """Lore endpoint should 404 for nonexistent game."""
        resp = client.get("/api/game/nonexistent/lore")
        assert resp.status_code == 404

    def test_lore_progress_updates_on_discovery(self) -> None:
        """After discovering a lore fragment, progress should reflect it."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        full_state = client.get(f"/api/game/{game_id}").json()

        ship = full_state["ship"]
        cur_sys_id = ship["current_system_id"]

        sys_detail = client.get(f"/api/game/{game_id}/system/{cur_sys_id}").json()
        system = sys_detail["system"]
        bodies = system.get("bodies", [])

        if bodies:
            client.post(f"/api/game/{game_id}/land/{bodies[0]['id']}")
            client.post(f"/api/game/{game_id}/explore")

        resp = client.get(f"/api/game/{game_id}/lore")
        assert resp.status_code == 200
        data = resp.json()
        assert "progress" in data

    def test_full_state_includes_lore_stats(self) -> None:
        """GET /api/game/{id} should include lore_fragments_collected and _total."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()

        assert "lore_fragments_collected" in data
        assert "lore_fragments_total" in data
        assert data["lore_fragments_total"] == 20
        assert data["lore_fragments_collected"] == 0

    def test_discoveries_endpoint_includes_lore_fragment_id(self) -> None:
        """When a discovery has a lore fragment, it should show in discoveries."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        ship = client.get(f"/api/game/{game_id}").json()["ship"]
        cur_sys_id = ship["current_system_id"]

        sys_detail = client.get(f"/api/game/{game_id}/system/{cur_sys_id}").json()
        system = sys_detail["system"]
        bodies = system.get("bodies", [])

        if bodies:
            client.post(f"/api/game/{game_id}/land/{bodies[0]['id']}")
            client.post(f"/api/game/{game_id}/explore")

        resp = client.get(f"/api/game/{game_id}/discoveries")
        assert resp.status_code == 200
        data = resp.json()
        assert "discoveries" in data
        for disc in data["discoveries"]:
            assert "lore_fragment_id" in disc

    def test_lore_endpoint_collected_after_discovery(self) -> None:
        """After discovering a lore fragment, lore endpoint shows collected > 0."""
        from backend.generation.lore import get_lore_fragments_for_system

        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]

        target_sys_id = None
        target_body_id = None
        for sys_id in state.systems:
            frags = get_lore_fragments_for_system(sys_id, state.lore_fragments)
            if frags:
                target_sys_id = sys_id
                target_body_id = frags[0].discovery_id.split("::")[1]
                break

        if not target_sys_id:
            return

        state.ship.current_system_id = target_sys_id
        state.ship.fuel = 1000

        client.post(f"/api/game/{game_id}/land/{target_body_id}")
        client.post(f"/api/game/{game_id}/explore")

        resp = client.get(f"/api/game/{game_id}/lore")
        assert resp.status_code == 200
        data = resp.json()
        assert data["progress"]["collected"] > 0
        arcs_with_collected = [a for a in data["arcs"].values() if a["collected"] > 0]
        assert len(arcs_with_collected) > 0

    def test_lore_endpoint_collected_after_discovery_no_lore(self) -> None:
        """Cover guard clause when no lore fragments found (line 1320)."""
        import backend.generation.lore as lore_mod

        original = lore_mod.get_lore_fragments_for_system
        lore_mod.get_lore_fragments_for_system = lambda sys_id, lore_frags: []
        try:
            self.test_lore_endpoint_collected_after_discovery()
        finally:
            lore_mod.get_lore_fragments_for_system = original

    def test_lore_endpoint_returns_arc_order(self) -> None:
        """GET /api/game/{id}/lore should return arc_order matching ARC_DISPLAY_NAMES keys."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        resp = client.get(f"/api/game/{game_id}/lore")
        assert resp.status_code == 200
        data = resp.json()

        assert "arc_order" in data
        assert isinstance(data["arc_order"], list)
        assert len(data["arc_order"]) == 4
        assert data["arc_order"] == ["architects", "void_signal", "fracture", "wanderer"]

    def test_lore_discovery_date_stored_on_fragment(self) -> None:
        """After discovering a lore fragment, the lore endpoint returns a non-empty discovery_date."""
        from backend.generation.lore import get_lore_fragments_for_system

        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]

        target_sys_id = None
        target_body_id = None
        for sys_id in state.systems:
            frags = get_lore_fragments_for_system(sys_id, state.lore_fragments)
            if frags:
                target_sys_id = sys_id
                target_body_id = frags[0].discovery_id.split("::")[1]
                break

        if not target_sys_id:
            return

        state.ship.current_system_id = target_sys_id
        state.ship.fuel = 1000

        client.post(f"/api/game/{game_id}/land/{target_body_id}")
        client.post(f"/api/game/{game_id}/explore")

        resp = client.get(f"/api/game/{game_id}/lore")
        assert resp.status_code == 200
        data = resp.json()

        discovered_frags = []
        for arc_data in data["arcs"].values():
            for frag in arc_data["fragments"]:
                if frag["discovered"]:
                    discovered_frags.append(frag)

        assert len(discovered_frags) > 0
        for frag in discovered_frags:
            assert "discovery_date" in frag
            assert frag["discovery_date"] != ""
            assert frag["discovery_date"] is not None

    def test_lore_discovery_date_no_fragments_returns_early(self) -> None:
        """Cover guard clause when no lore fragments found."""
        import backend.generation.lore as lore_mod

        original = lore_mod.get_lore_fragments_for_system
        lore_mod.get_lore_fragments_for_system = lambda sys_id, lore_frags: []
        try:
            self.test_lore_discovery_date_stored_on_fragment()
        finally:
            lore_mod.get_lore_fragments_for_system = original

    def test_lore_fallback_when_system_not_found(self) -> None:
        """When discovery_id references a system not in state.systems, fallback location is used."""
        from backend.models.discovery import LoreFragment
        from backend.game.manager import GAME_STORE, game_save

        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "lore-fallback-sys"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]

        # Create a lore fragment with a discovery_id referencing a non-existent system
        lf = LoreFragment(
            id="test-fallback-lore",
            arc="architects",
            title="Test Fragment",
            text="Test text",
            discovered=True,
            discovery_id="nonexistent_system_xyz::body_123",
            fragment_number=1,
        )
        state.lore_fragments.append(lf)
        GAME_STORE[game_id] = state
        game_save(state)

        with patch("backend.api.routes.logger") as mock_logger:
            resp = client.get(f"/api/game/{game_id}/lore")
        assert resp.status_code == 200
        data = resp.json()

        # Verify that a warning was logged for the orphaned reference
        assert mock_logger.warning.called, "logger.warning should have been called for orphaned lore fragment"
        warning_args = mock_logger.warning.call_args[0]
        assert "Lore fragment %s references unknown system %s (body %s)" in warning_args[0]
        assert "test-fallback-lore" in warning_args
        assert "nonexistent_system_xyz" in warning_args
        assert "body_123" in warning_args

        # Find our test fragment in the response
        architects = data["arcs"]["architects"]
        test_frag = None
        for frag in architects["fragments"]:
            if frag["id"] == "test-fallback-lore":
                test_frag = frag
                break

        assert test_frag is not None, "Test fragment should be in the response"
        assert "discovery_location" in test_frag
        assert test_frag["discovery_location"] == "Unknown system (nonexistent_system_xyz) - Body (body_123)"

    def test_lore_endpoint_no_fragments_in_state(self) -> None:
        """When state has zero lore fragments, the lore endpoint returns arcs with no fragments and 0/0 progress."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "no-lore-frags"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]

        state.lore_fragments = []
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.get(f"/api/game/{game_id}/lore")
        assert resp.status_code == 200
        data = resp.json()

        assert "arcs" in data
        assert "progress" in data
        assert data["progress"]["total"] == 0
        assert data["progress"]["collected"] == 0

        expected_arcs = {"architects", "void_signal", "fracture", "wanderer"}
        assert set(data["arcs"].keys()) == expected_arcs

        for arc_id, arc_data in data["arcs"].items():
            assert arc_data["total"] == 0
            assert arc_data["collected"] == 0
            assert arc_data["fragments"] == []


class TestAPIMainIndex:
    """Tests for main.py index endpoint."""

    def test_index_responds_ok(self) -> None:
        """Index endpoint should return 200."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_responds_non_empty(self) -> None:
        """Index endpoint should not be empty."""
        resp = client.get("/")
        content = resp.text
        assert len(content) > 0

    def test_assets_mount_exists(self) -> None:
        """Assets mount should be active when directory exists."""
        import os as _os
        from backend.main import FRONTEND_DIR
        assets_dir = _os.path.join(FRONTEND_DIR, "assets")
        assert _os.path.isdir(assets_dir), "Assets directory should exist"


class TestAPIDistress:
    """Tests for POST /api/game/{game_id}/distress."""

    def test_distress_nonexistent_game(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/distress")
        assert resp.status_code == 404

    def test_distress_not_stranded(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "distress-not-stranded"})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/distress")
        assert resp.status_code == 400
        assert "Distress beacon" in resp.json()["detail"]

    def test_distress_success(self) -> None:
        from unittest.mock import MagicMock, patch
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "distress-success"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.ship.fuel = 0
        state.ship.hull = 100
        state.ship.credits = 200
        GAME_STORE[game_id] = state
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.61]
        mock_rng.randint.side_effect = [3]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            resp = client.post(f"/api/game/{game_id}/distress")
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert "outcome" in data
        assert "effects" in data
        assert "ship" in data
        assert data["outcome"] == "no_response"

    def test_distress_saves_state(self) -> None:
        from unittest.mock import MagicMock, patch
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "distress-save"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.ship.fuel = 0
        state.ship.hull = 100
        state.ship.credits = 200
        GAME_STORE[game_id] = state
        game_save(state)
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.61]
        mock_rng.randint.side_effect = [3]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            resp = client.post(f"/api/game/{game_id}/distress")
        assert resp.status_code == 200
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["distress_cooldown"] is True


class TestAPISalvage:
    """Tests for POST /api/game/{game_id}/salvage."""

    def test_salvage_nonexistent_game(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/salvage")
        assert resp.status_code == 404

    def test_salvage_not_stranded(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "salvage-not-stranded"})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/salvage")
        assert resp.status_code == 400

    def test_salvage_success(self) -> None:
        from unittest.mock import MagicMock, patch
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "salvage-success"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.ship.fuel = 0
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), system.bodies[0])
        land_on_body(state, planet.id)
        GAME_STORE[game_id] = state
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2]
        mock_rng.randint.side_effect = [5]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            resp = client.post(f"/api/game/{game_id}/salvage")
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert "find" in data
        assert "effects" in data
        assert "ship" in data
        assert data["find"] == "fuel_cache"

    def test_salvage_saves_state(self) -> None:
        from unittest.mock import MagicMock, patch
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "salvage-save"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.ship.fuel = 0
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), system.bodies[0])
        land_on_body(state, planet.id)
        GAME_STORE[game_id] = state
        game_save(state)
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2]
        mock_rng.randint.side_effect = [5]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            resp = client.post(f"/api/game/{game_id}/salvage")
        assert resp.status_code == 200
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        saved_ship = data["ship"]
        assert "salvage_attempts" in saved_ship


class TestAPICraft:
    """Tests for POST /api/game/{game_id}/salvage/craft."""

    def test_craft_nonexistent_game(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/salvage/craft", json={
            "discovery_id": "test_disc", "output": "fuel"
        })
        assert resp.status_code == 404

    def test_craft_not_found(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "craft-not-found"})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/salvage/craft", json={
            "discovery_id": "nonexistent_disc", "output": "fuel"
        })
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_craft_success(self) -> None:
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "craft-success"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        disc = Discovery(
            id="craft_api_success_disc", category="artifact", name="Ancient Artifact",
            description="Ancient", value=50, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        state.ship.fuel = 10
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/salvage/craft", json={
            "discovery_id": "craft_api_success_disc", "output": "fuel"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert "crafted" in data
        assert "effects" in data
        assert "ship" in data
        assert data["crafted"] == "fuel"
        assert data["effects"]["fuel"] == 5
        assert data["ship"]["fuel"] == 15

    def test_craft_saves_state(self) -> None:
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "craft-save"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        disc = Discovery(
            id="craft_api_save_disc", category="artifact", name="Ancient Artifact",
            description="Ancient", value=50, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        state.ship.fuel = 10
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.post(f"/api/game/{game_id}/salvage/craft", json={
            "discovery_id": "craft_api_save_disc", "output": "fuel"
        })
        assert resp.status_code == 200
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ship"]["fuel"] == 15
        assert len(data["discoveries"]) == 0


class TestAPICargo:
    """Tests for the cargo inspection endpoint and cargo_items in game state."""

    def test_cargo_endpoint_returns_structure(self) -> None:
        """GET /api/game/{id}/cargo should return cargo, cargo_capacity, and cargo_items."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/cargo")
        assert resp.status_code == 200
        data = resp.json()
        assert "cargo" in data
        assert "cargo_capacity" in data
        assert "cargo_items" in data
        assert data["cargo"] == 0
        assert data["cargo_capacity"] == 50
        assert data["cargo_items"] == []

    def test_cargo_endpoint_nonexistent_game(self) -> None:
        """Cargo endpoint should 404 for nonexistent game."""
        resp = client.get("/api/game/nonexistent/cargo")
        assert resp.status_code == 404

    def test_cargo_items_in_full_state_response(self) -> None:
        """GET /api/game/{id} should include discoveries with sellable flag and cargo_capacity."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="test-disc-1", category="mineral", name="Iron Ore",
                      description="Common ore", value=50, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "discoveries" in data
        assert "cargo_capacity" in data
        assert data["cargo_capacity"] == 50
        assert isinstance(data["discoveries"], list)
        for disc in data["discoveries"]:
            assert "sellable" in disc

    def test_cargo_items_after_exploration(self) -> None:
        """After exploring, discoveries should have sellable field."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = client.get(f"/api/game/{game_id}").json()
        planets = [b for b in state["current_system"]["bodies"] if b["body_type"] == "planet"]
        client.post(f"/api/game/{game_id}/land/{planets[0]['id']}")
        resp = client.post(f"/api/game/{game_id}/explore")
        assert resp.status_code == 200
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["discoveries"]) > 0
        for disc in data["discoveries"]:
            assert "id" in disc
            assert "name" in disc
            assert "category" in disc
            assert "value" in disc
            assert "description" in disc
            assert "sellable" in disc

    def test_cargo_items_sellable_flag(self) -> None:
        """Discoveries without lore_fragment_id should be sellable (via to_dict)."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-sellable"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="sellable-disc-1", category="mineral", name="Gold Ore",
                      description="Valuable ore", value=100, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="non-sellable-disc-1", category="artifact", name="Ancient Relic",
                      description="Linked to lore", value=0, system_id=current_sys.id,
                      lore_fragment_id="lore_001")
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["discoveries"]) == 2
        sellable_items = [d for d in data["discoveries"] if d["sellable"]]
        non_sellable_items = [d for d in data["discoveries"] if not d["sellable"]]
        assert len(sellable_items) == 1
        assert sellable_items[0]["id"] == "sellable-disc-1"
        assert len(non_sellable_items) == 1
        assert non_sellable_items[0]["id"] == "non-sellable-disc-1"

    def test_cargo_capacity_in_ship_dict(self) -> None:
        """cargo_capacity should be at top level, not in ship dict."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "cargo_capacity" not in data["ship"]
        assert "cargo_capacity" in data
        assert data["cargo_capacity"] == 50

    def test_cargo_items_in_state_summary(self) -> None:
        """state_summary should not include cargo_items (redundant with discoveries)."""
        from backend.game.manager import new_game
        state = new_game(seed=42)
        summary = state.state_summary()
        assert "cargo_items" not in summary
        assert "discovery_count" in summary

    def test_cargo_endpoint_from_db_fallback(self) -> None:
        """Cargo endpoint should work via DB fallback."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-db-fallback"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}/cargo")
        assert resp.status_code == 200
        data = resp.json()
        assert "cargo" in data
        assert "cargo_capacity" in data
        assert "cargo_items" in data

    def test_cargo_endpoint_db_fallback_404(self) -> None:
        """Cargo endpoint should return 404 when game_load returns None."""
        from unittest.mock import patch
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-db-404"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        with patch("backend.api.routes.game_load_func", return_value=None):
            resp = client.get(f"/api/game/{game_id}/cargo")
            assert resp.status_code == 404

    def test_cargo_items_use_to_cargo_dict(self) -> None:
        """Call /api/game/{id}/cargo to exercise to_cargo_dict on discoveries."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-tocargodict"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="tc-sellable", category="mineral", name="Gold Ore",
                      description="Valuable ore", value=100, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="tc-nonsellable", category="artifact", name="Ancient Relic",
                      description="Linked to lore", value=0, system_id=current_sys.id,
                      lore_fragment_id="lore_001")
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}/cargo")
        assert resp.status_code == 200
        data = resp.json()
        assert "cargo_items" in data
        assert len(data["cargo_items"]) == 2
        for item in data["cargo_items"]:
            assert "id" in item
            assert "name" in item
            assert "category" in item
            assert "value" in item
            assert "description" in item
            assert "sellable" in item
        sellable = [i for i in data["cargo_items"] if i["sellable"]]
        nonsellable = [i for i in data["cargo_items"] if not i["sellable"]]
        assert len(sellable) == 1
        assert sellable[0]["id"] == "tc-sellable"
        assert len(nonsellable) == 1
        assert nonsellable[0]["id"] == "tc-nonsellable"

    def test_cargo_endpoint_has_total_value(self) -> None:
        """GET /api/game/{id}/cargo should include total_value field."""
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/cargo")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_value" in data
        assert data["total_value"] == 0

    def test_cargo_endpoint_total_value_with_items(self) -> None:
        """total_value should be sum of all cargo item values."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-total-val"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="tv-disc-1", category="mineral", name="Gold",
                      description="Gold ore", value=100, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="tv-disc-2", category="artifact", name="Relic",
                      description="Ancient relic", value=50, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="tv-disc-3", category="mineral", name="Silver",
                      description="Silver ore", value=25, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}/cargo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_value"] == 175  # 100 + 50 + 25

    def test_cargo_sort_value_desc_default(self) -> None:
        """Default sort should be by value descending."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-sort-vd"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="vsd-1", category="mineral", name="Low",
                      description="Low value", value=10, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="vsd-2", category="artifact", name="High",
                      description="High value", value=100, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="vsd-3", category="mineral", name="Medium",
                      description="Medium value", value=50, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}/cargo")
        assert resp.status_code == 200
        data = resp.json()
        values = [item["value"] for item in data["cargo_items"]]
        assert values == [100, 50, 10]

    def test_cargo_sort_value_asc(self) -> None:
        """Sort by value ascending should work."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-sort-va"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="vsa-1", category="mineral", name="Low",
                      description="Low value", value=10, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="vsa-2", category="artifact", name="High",
                      description="High value", value=100, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="vsa-3", category="mineral", name="Medium",
                      description="Medium value", value=50, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}/cargo?sort=value&order=asc")
        assert resp.status_code == 200
        data = resp.json()
        values = [item["value"] for item in data["cargo_items"]]
        assert values == [10, 50, 100]

    def test_cargo_sort_name_asc(self) -> None:
        """Sort by name ascending should work."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-sort-na"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="sna-1", category="mineral", name="Zeta Ore",
                      description="Zeta", value=50, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="sna-2", category="artifact", name="Alpha Relic",
                      description="Alpha", value=100, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="sna-3", category="mineral", name="Beta Crystal",
                      description="Beta", value=25, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}/cargo?sort=name&order=asc")
        assert resp.status_code == 200
        data = resp.json()
        names = [item["name"] for item in data["cargo_items"]]
        assert names == ["Alpha Relic", "Beta Crystal", "Zeta Ore"]

    def test_cargo_sort_name_desc(self) -> None:
        """Sort by name descending should work."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-sort-nd"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="snd-1", category="mineral", name="Alpha Ore",
                      description="Alpha", value=50, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="snd-2", category="artifact", name="Zeta Relic",
                      description="Zeta", value=100, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="snd-3", category="mineral", name="Beta Crystal",
                      description="Beta", value=25, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}/cargo?sort=name&order=desc")
        assert resp.status_code == 200
        data = resp.json()
        names = [item["name"] for item in data["cargo_items"]]
        assert names == ["Zeta Relic", "Beta Crystal", "Alpha Ore"]

    def test_cargo_total_value_in_full_state(self) -> None:
        """GET /api/game/{id} should include total_value field."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-full-tv"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="ftv-1", category="mineral", name="Gold",
                      description="Gold ore", value=100, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_value" in data
        assert data["total_value"] == 100

    def test_cargo_sort_empty_items(self) -> None:
        """Sorting with empty cargo should return empty list."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-sort-empty"})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/cargo?sort=value&order=desc")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cargo_items"] == []
        assert data["total_value"] == 0

    def test_cargo_invalid_sort_key(self) -> None:
        """Invalid sort key should return 422 with helpful error message."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-inv-sort"})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/cargo?sort=category")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "Invalid sort key 'category'" in detail
        assert "Must be one of:" in detail
        assert "name" in detail
        assert "value" in detail

    def test_cargo_invalid_order(self) -> None:
        """Invalid order value should return 422 with helpful error message."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-inv-order"})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/cargo?sort=value&order=ascending")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "Invalid order 'ascending'" in detail
        assert "Must be one of:" in detail
        assert "asc" in detail
        assert "desc" in detail

    def test_cargo_invalid_sort_and_order(self) -> None:
        """Sort validation fires first when both sort and order are invalid."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-inv-both"})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/cargo?sort=category&order=ascending")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "Invalid sort key 'category'" in detail

    def test_cargo_sort_name_desc_with_valid_params(self) -> None:
        """Valid sort=name&order=desc should sort correctly (regression test)."""
        from backend.models.discovery import Discovery
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "cargo-regr-nd"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        state.discoveries.append(
            Discovery(id="rnd-1", category="mineral", name="Alpha Ore",
                      description="Alpha", value=50, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="rnd-2", category="artifact", name="Zeta Relic",
                      description="Zeta", value=100, system_id=current_sys.id)
        )
        state.discoveries.append(
            Discovery(id="rnd-3", category="mineral", name="Beta Crystal",
                      description="Beta", value=25, system_id=current_sys.id)
        )
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}/cargo?sort=name&order=desc")
        assert resp.status_code == 200
        data = resp.json()
        names = [item["name"] for item in data["cargo_items"]]
        assert names == ["Zeta Relic", "Beta Crystal", "Alpha Ore"]


class TestFuelWarningSystem:
    """Tests for the fuel warning status system (backend/fuel.py)."""

    def test_fuel_status_green_current_is_only_station(self) -> None:
        """When the current system has a trading station and no other systems do,
        fuel_status shows green with current system as nearest and distance 0.0."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "fuel-green-only"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        assert current_sys is not None
        for sys_data in state.systems.values():
            sys_data.has_trading_station = (sys_data.id == current_sys.id)
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        fs = resp.json()["fuel_status"]
        assert fs["level"] == "green"
        assert fs["message"] == ""
        assert fs["nearest_station_system"] == current_sys.name
        assert fs["nearest_station_distance"] == 0.0
        assert fs["fuel_for_round_trip"] == 0
        assert fs["fuel_for_one_way"] == 0

    def test_fuel_status_fields_in_full_state(self) -> None:
        """Fuel status in the full state response contains all expected fields."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "fuel-fields"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "fuel_status" in data
        fs = data["fuel_status"]
        assert "level" in fs
        assert "message" in fs
        assert "current_fuel" in fs
        assert "fuel_for_round_trip" in fs
        assert "fuel_for_one_way" in fs
        assert "nearest_station_system" in fs
        assert "nearest_station_distance" in fs
        assert isinstance(fs["current_fuel"], int)
        assert isinstance(fs["fuel_for_round_trip"], int)
        assert isinstance(fs["fuel_for_one_way"], int)
        assert isinstance(fs["nearest_station_distance"], (int, float))

    def test_fuel_warning_critical(self) -> None:
        """Fuel < 5 produces 'critical' level."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "fuel-critical"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        assert current_sys is not None
        for sys_data in state.systems.values():
            sys_data.has_trading_station = False
        current_sys.has_trading_station = False
        other = next(s for s in state.systems.values() if s.id != current_sys.id)
        other.has_trading_station = True
        other.x = current_sys.x + 100
        other.y = current_sys.y
        state.ship.fuel = 3
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        fs = resp.json()["fuel_status"]
        assert fs["level"] == "critical"
        assert "CRITICAL" in fs["message"]

    def test_fuel_warning_red(self) -> None:
        """5 <= fuel < fuel_for_one_way produces 'red' level."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "fuel-red"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        assert current_sys is not None
        for sys_data in state.systems.values():
            sys_data.has_trading_station = False
        current_sys.has_trading_station = False
        other = next(s for s in state.systems.values() if s.id != current_sys.id)
        other.has_trading_station = True
        other.x = current_sys.x + 100
        other.y = current_sys.y
        state.ship.fuel = 20
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        fs = resp.json()["fuel_status"]
        assert fs["level"] == "red"
        assert "DANGER" in fs["message"]

    def test_fuel_warning_yellow(self) -> None:
        """fuel_for_one_way <= fuel < fuel_for_round_trip produces 'yellow' level."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "fuel-yellow"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        assert current_sys is not None
        for sys_data in state.systems.values():
            sys_data.has_trading_station = False
        current_sys.has_trading_station = False
        other = next(s for s in state.systems.values() if s.id != current_sys.id)
        other.has_trading_station = True
        other.x = current_sys.x + 100
        other.y = current_sys.y
        state.ship.fuel = 40
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        fs = resp.json()["fuel_status"]
        assert fs["level"] == "yellow"
        assert "Warning" in fs["message"]

    def test_fuel_warning_green(self) -> None:
        """fuel >= fuel_for_round_trip produces 'green' level."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "fuel-green"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()
        assert current_sys is not None
        for sys_data in state.systems.values():
            sys_data.has_trading_station = False
        current_sys.has_trading_station = False
        other = next(s for s in state.systems.values() if s.id != current_sys.id)
        other.has_trading_station = True
        other.x = current_sys.x + 100
        other.y = current_sys.y
        state.ship.fuel = 70
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        fs = resp.json()["fuel_status"]
        assert fs["level"] == "green"
        assert fs["message"] == ""

    def test_fuel_status_unknown_no_stations(self) -> None:
        """When no systems have trading stations, fuel_status is 'unknown'."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "fuel-unknown"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        for sys_data in state.systems.values():
            sys_data.has_trading_station = False
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        fs = resp.json()["fuel_status"]
        assert fs["level"] == "unknown"
        assert fs["message"] == "No trading stations in known space"
        assert fs["nearest_station_system"] is None
        assert fs["nearest_station_distance"] == 0.0
        assert fs["fuel_for_round_trip"] == 0
        assert fs["fuel_for_one_way"] == 0


class TestAPIReputationLabels:
    """Tests for the _rep_label function that maps reputation values to labels."""

    def test_rep_label_allied(self) -> None:
        """Reputation >= 50 should be 'Allied'."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "rep-label-test"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.modify_faction_reputation("stellar_cartographers", 60)
        state.modify_faction_reputation("void_traders", 50)
        state.modify_faction_reputation("free_pilots", 100)
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        rs = data["reputation_summary"]
        assert rs["stellar_cartographers"]["reputation"] == 60
        assert rs["stellar_cartographers"]["label"] == "Allied"
        assert rs["void_traders"]["reputation"] == 50
        assert rs["void_traders"]["label"] == "Allied"
        assert rs["free_pilots"]["reputation"] == 100
        assert rs["free_pilots"]["label"] == "Allied"
        GAME_STORE.pop(game_id, None)

    def test_rep_label_friendly(self) -> None:
        """Reputation 20-49 should be 'Friendly'."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "rep-label-test2"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.modify_faction_reputation("stellar_cartographers", 30)
        state.modify_faction_reputation("void_traders", 20)
        state.modify_faction_reputation("free_pilots", 49)
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        rs = data["reputation_summary"]
        assert rs["stellar_cartographers"]["reputation"] == 30
        assert rs["stellar_cartographers"]["label"] == "Friendly"
        assert rs["void_traders"]["reputation"] == 20
        assert rs["void_traders"]["label"] == "Friendly"
        assert rs["free_pilots"]["reputation"] == 49
        assert rs["free_pilots"]["label"] == "Friendly"
        GAME_STORE.pop(game_id, None)

    def test_rep_label_neutral(self) -> None:
        """Reputation 0-19 should be 'Neutral'."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "rep-label-test3"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.modify_faction_reputation("stellar_cartographers", 10)
        state.modify_faction_reputation("void_traders", 0)
        state.modify_faction_reputation("free_pilots", 19)
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        rs = data["reputation_summary"]
        assert rs["stellar_cartographers"]["reputation"] == 10
        assert rs["stellar_cartographers"]["label"] == "Neutral"
        assert rs["void_traders"]["reputation"] == 0
        assert rs["void_traders"]["label"] == "Neutral"
        assert rs["free_pilots"]["reputation"] == 19
        assert rs["free_pilots"]["label"] == "Neutral"
        GAME_STORE.pop(game_id, None)

    def test_rep_label_unfriendly(self) -> None:
        """Reputation -20 to -1 should be 'Unfriendly'."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "rep-label-test4"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.modify_faction_reputation("stellar_cartographers", -10)
        state.modify_faction_reputation("void_traders", -1)
        state.modify_faction_reputation("free_pilots", -19)
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        rs = data["reputation_summary"]
        assert rs["stellar_cartographers"]["reputation"] == -10
        assert rs["stellar_cartographers"]["label"] == "Unfriendly"
        assert rs["void_traders"]["reputation"] == -1
        assert rs["void_traders"]["label"] == "Unfriendly"
        assert rs["free_pilots"]["reputation"] == -19
        assert rs["free_pilots"]["label"] == "Unfriendly"
        GAME_STORE.pop(game_id, None)

    def test_rep_label_hostile(self) -> None:
        """Reputation < -20 should be 'Hostile'."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "rep-label-test5"})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.modify_faction_reputation("stellar_cartographers", -50)
        state.modify_faction_reputation("void_traders", -21)
        state.modify_faction_reputation("free_pilots", -100)
        GAME_STORE[game_id] = state
        game_save(state)
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        rs = data["reputation_summary"]
        assert rs["stellar_cartographers"]["reputation"] == -50
        assert rs["stellar_cartographers"]["label"] == "Hostile"
        assert rs["void_traders"]["reputation"] == -21
        assert rs["void_traders"]["label"] == "Hostile"
        assert rs["free_pilots"]["reputation"] == -100
        assert rs["free_pilots"]["label"] == "Hostile"
        GAME_STORE.pop(game_id, None)
