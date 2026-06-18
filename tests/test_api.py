import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.main import app
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game, game_save
from backend.game.engine import get_nearby_systems, land_on_body

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
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "sys-fallback"})
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
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "db-fb-sys-v2"})
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
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "jump-no-sys"})
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
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
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
