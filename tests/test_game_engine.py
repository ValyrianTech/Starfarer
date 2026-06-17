import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade
from backend.game.manager import new_game, get_galaxy, get_system_detail, game_save
from backend.generation.events import trigger_event, resolve_event
from backend.config import SCAN_FUEL_COST


class TestGameManager:
    def test_new_game_creates_valid_state(self):
        state = new_game(seed=42)
        assert state.id is not None
        assert len(state.systems) == 50
        assert state.ship.current_system_id != ""
        assert state.ship.fuel == 80
        assert state.ship.hull == 100
        assert state.systems_visited == 1

    def test_new_game_deterministic(self):
        s1 = new_game(seed=42)
        s2 = new_game(seed=42)
        assert s1.systems[s1.ship.current_system_id].name == s2.systems[s2.ship.current_system_id].name

    def test_get_galaxy(self):
        state = new_game(seed=42)
        galaxy = get_galaxy(state)
        assert len(galaxy["systems"]) == 50
        assert galaxy["systems_visited"] == 1

    def test_get_system_detail(self):
        state = new_game(seed=42)
        sys_id = state.ship.current_system_id
        detail = get_system_detail(state, sys_id)
        assert detail is not None
        assert detail["system"]["id"] == sys_id
        assert detail["is_current"] is True

    def test_save_and_load_roundtrip(self):
        from backend.database import init_db
        init_db()
        state = new_game(seed=42)
        game_save(state)

        from backend.game.manager import game_load
        loaded = game_load(state.id)
        assert loaded is not None
        assert loaded.id == state.id
        assert loaded.seed == state.seed
        assert loaded.ship.name == state.ship.name
        assert loaded.ship.current_system_id == state.ship.current_system_id
        assert len(loaded.systems) == len(state.systems)
        assert len(loaded.log_entries) == len(state.log_entries)


class TestNavigation:
    def test_can_jump_same_system(self):
        state = new_game(seed=42)
        cur = state.get_current_system()
        ok, cost, msg = can_jump(state.ship, cur, cur)
        assert ok is False
        assert "Already" in msg

    def test_scan_reduces_fuel(self):
        state = new_game(seed=42)
        fuel_before = state.ship.fuel
        result = perform_scan(state)
        assert state.ship.fuel == fuel_before - SCAN_FUEL_COST
        assert "Scan complete" in result

    def test_scan_marks_scanned(self):
        state = new_game(seed=42)
        perform_scan(state)
        sys = state.get_current_system()
        assert sys.scanned is True

    def test_get_nearby_systems(self):
        state = new_game(seed=42)
        nearby = get_nearby_systems(state)
        assert len(nearby) == len(state.systems) - 1
        assert all("distance_ly" in n for n in nearby)

    def test_land_on_valid_body(self):
        state = new_game(seed=42)
        sys = state.get_current_system()
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if planet:
            ok, msg = land_on_body(state, planet.id)
            assert ok is True
            assert planet.name in msg

    def test_land_on_invalid_body(self):
        state = new_game(seed=42)
        ok, msg = land_on_body(state, "nonexistent")
        assert ok is False

    def test_explore_surface(self):
        state = new_game(seed=42)
        sys = state.get_current_system()
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if planet:
            land_on_body(state, planet.id)
            discoveries = explore_surface(state)
            assert len(discoveries) > 0
            assert len(state.discoveries) > 0

    def test_jump_chain(self):
        state = new_game(seed=42)
        nearby = get_nearby_systems(state)
        reachable = [n for n in nearby if n["reachable"]]
        if reachable:
            target = state.systems[reachable[0]["id"]]
            ok, cost, msg = can_jump(state.ship, target, state.get_current_system())
            assert ok is True
            result = perform_jump(state, target, cost)
            assert state.ship.current_system_id == target.id
            assert state.ship.fuel < 80


class TestTradingAndUpgrades:
    def test_get_upgrade_info(self):
        state = new_game(seed=42)
        info = get_upgrade_info(state.ship)
        assert len(info) > 0
        for u in info:
            assert "id" in u
            assert "cost" in u
            assert "current_level" in u

    def test_purchase_upgrade(self):
        state = new_game(seed=42)
        state.ship.credits = 10000
        ok, msg = purchase_upgrade(state, "hyperdrive")
        assert ok is True
        assert state.ship.upgrades["hyperdrive"] == 1

    def test_purchase_upgrade_not_enough_credits(self):
        state = new_game(seed=42)
        state.ship.credits = 10
        ok, msg = purchase_upgrade(state, "hyperdrive")
        assert ok is False


class TestEvents:
    def test_event_templates_exist(self):
        from backend.generation.events import EVENT_TEMPLATES
        assert len(EVENT_TEMPLATES) >= 8
        for t in EVENT_TEMPLATES:
            assert "title" in t
            assert "choices" in t
            assert len(t["choices"]) >= 2

    def test_trigger_event(self):
        state = new_game(seed=42)
        event = trigger_event(state)
        assert event is None or event.id is not None

    def test_resolve_event(self):
        state = new_game(seed=42)
        from backend.generation.events import resolve_event as resolve_ev
        from backend.generation.events import _create_event, EVENT_TEMPLATES
        event = _create_event(EVENT_TEMPLATES[0], "sys_0000")
        state.events.append(event)

        ok, msg, extra = resolve_ev(state, event.id, 0)
        assert ok is True
        assert event.resolved is True
        assert event.chosen == 0

    def test_resolve_invalid_event(self):
        state = new_game(seed=42)
        ok, msg, extra = resolve_event(state, "nonexistent", 0)
        assert ok is False
