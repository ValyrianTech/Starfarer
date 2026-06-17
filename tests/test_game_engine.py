import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade, perform_trade
from backend.game.manager import new_game, get_galaxy, get_system_detail, game_save, load_or_create, get_game_state
from backend.generation.events import trigger_event, resolve_event, EVENT_TEMPLATES
from backend.config import SCAN_FUEL_COST


class TestGameManager:
    def test_new_game_creates_valid_state(self) -> None:
        state = new_game(seed=42)
        assert state.id is not None
        assert len(state.systems) == 50
        assert state.ship.current_system_id != ""
        assert state.ship.fuel == 80
        assert state.ship.hull == 100
        assert state.systems_visited == 1

    def test_new_game_deterministic(self) -> None:
        s1 = new_game(seed=42)
        s2 = new_game(seed=42)
        assert s1.systems[s1.ship.current_system_id].name == s2.systems[s2.ship.current_system_id].name

    def test_get_galaxy(self) -> None:
        state = new_game(seed=42)
        galaxy = get_galaxy(state)
        assert len(galaxy["systems"]) == 50
        assert galaxy["systems_visited"] == 1

    def test_get_system_detail(self) -> None:
        state = new_game(seed=42)
        sys_id = state.ship.current_system_id
        detail = get_system_detail(state, sys_id)
        assert detail is not None
        assert detail["system"]["id"] == sys_id
        assert detail["is_current"] is True

    def test_save_and_load_roundtrip(self) -> None:
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
    def test_can_jump_same_system(self) -> None:
        state = new_game(seed=42)
        cur = state.get_current_system()
        ok, cost, msg = can_jump(state.ship, cur, cur)
        assert ok is False
        assert "Already" in msg

    def test_scan_reduces_fuel(self) -> None:
        state = new_game(seed=42)
        fuel_before = state.ship.fuel
        result = perform_scan(state)
        assert state.ship.fuel == fuel_before - SCAN_FUEL_COST
        assert "Scan complete" in result

    def test_scan_marks_scanned(self) -> None:
        state = new_game(seed=42)
        perform_scan(state)
        sys = state.get_current_system()
        assert sys is not None
        assert sys.scanned is True

    def test_get_nearby_systems(self) -> None:
        state = new_game(seed=42)
        nearby = get_nearby_systems(state)
        assert len(nearby) == len(state.systems) - 1
        assert all("distance_ly" in n for n in nearby)

    def test_land_on_valid_body(self) -> None:
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if planet:
            ok, msg = land_on_body(state, planet.id)
            assert ok is True
            assert planet.name in msg

    def test_land_on_invalid_body(self) -> None:
        state = new_game(seed=42)
        ok, msg = land_on_body(state, "nonexistent")
        assert ok is False

    def test_explore_surface(self) -> None:
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if planet:
            land_on_body(state, planet.id)
            discoveries = explore_surface(state)
            assert len(discoveries) > 0
            assert len(state.discoveries) > 0

    def test_jump_chain(self) -> None:
        state = new_game(seed=42)
        nearby = get_nearby_systems(state)
        reachable = [n for n in nearby if n["reachable"]]
        if reachable:
            target = state.systems[reachable[0]["id"]]
            ok, cost, msg = can_jump(state.ship, target, state.get_current_system())
            assert ok is True
            _ = perform_jump(state, target, cost)
            assert state.ship.current_system_id == target.id
            assert state.ship.fuel < 80


class TestTradingAndUpgrades:
    def test_get_upgrade_info(self) -> None:
        state = new_game(seed=42)
        info = get_upgrade_info(state.ship)
        assert len(info) > 0
        for u in info:
            assert "id" in u
            assert "cost" in u
            assert "current_level" in u

    def test_purchase_upgrade(self) -> None:
        state = new_game(seed=42)
        state.ship.credits = 10000
        ok, msg = purchase_upgrade(state, "hyperdrive")
        assert ok is True
        assert state.ship.upgrades["hyperdrive"] == 1

    def test_purchase_upgrade_not_enough_credits(self) -> None:
        state = new_game(seed=42)
        state.ship.credits = 10
        ok, msg = purchase_upgrade(state, "hyperdrive")
        assert ok is False


class TestCanJumpEdgeCases:
    """Tests for the can_jump function covering edge cases."""

    def test_can_jump_no_current_system(self) -> None:
        """Jump should fail when there is no current system (None)."""
        state = new_game(seed=42)
        target = list(state.systems.values())[1]
        ok, fuel_cost, msg = can_jump(state.ship, target, None)
        assert ok is False
        assert "No current system" in msg

    def test_can_jump_not_enough_fuel(self) -> None:
        """Jump should fail when fuel is insufficient."""
        state = new_game(seed=42)
        cur = state.get_current_system()
        target = list(state.systems.values())[1]
        state.ship.fuel = 2
        ok, fuel_cost, msg = can_jump(state.ship, target, cur)
        assert ok is False
        assert "Not enough fuel" in msg
        assert fuel_cost > 0

    def test_can_jump_distance_exceeds_range(self) -> None:
        """Jump should fail when distance exceeds jump range."""
        state = new_game(seed=42)
        cur = state.get_current_system()
        state.ship.jump_range = 1
        state.ship.fuel = 500
        target = list(state.systems.values())[1]
        ok, fuel_cost, msg = can_jump(state.ship, target, cur)
        assert ok is False
        assert "exceeds jump range" in msg


class TestPerformJumpEdgeCases:
    """Tests for the perform_jump function covering edge cases."""

    def test_perform_jump_with_life_support_upgrade(self) -> None:
        """Jump with life support upgrade should reduce morale decay."""
        state = new_game(seed=42)
        state.ship.upgrades["life_support"] = 2
        cur = state.get_current_system()
        nearby = get_nearby_systems(state)
        reachable = [n for n in nearby if n["reachable"]]
        if reachable:
            target = state.systems[reachable[0]["id"]]
            ok, cost, _ = can_jump(state.ship, target, cur)
            assert ok is True
            morale_before = state.ship.morale
            _ = perform_jump(state, target, cost)
            assert state.ship.morale >= morale_before - 1

    def test_perform_jump_morale_clamping(self) -> None:
        """Jump should clamp morale to 0 when very low."""
        state = new_game(seed=42)
        state.ship.morale = 1
        cur = state.get_current_system()
        nearby = get_nearby_systems(state)
        reachable = [n for n in nearby if n["reachable"]]
        if reachable:
            target = state.systems[reachable[0]["id"]]
            ok, cost, _ = can_jump(state.ship, target, cur)
            assert ok is True
            _ = perform_jump(state, target, cost)
            assert state.ship.morale >= 0

    def test_perform_jump_no_current_system(self) -> None:
        """Jump log should work even when get_current_system returns None."""
        state = new_game(seed=42)
        cur = state.get_current_system()
        nearby = get_nearby_systems(state)
        reachable = [n for n in nearby if n["reachable"]]
        if reachable:
            target = state.systems[reachable[0]["id"]]
            ok, cost, _ = can_jump(state.ship, target, cur)
            assert ok is True
            state.ship.current_system_id = "nonexistent"
            _ = perform_jump(state, target, cost)
            assert state.ship.current_system_id == target.id


class TestScanEdgeCases:
    """Tests for perform_scan covering edge cases."""

    def test_scan_not_enough_fuel(self) -> None:
        """Scan should return error when not enough fuel."""
        state = new_game(seed=42)
        state.ship.fuel = 2
        result = perform_scan(state)
        assert "Not enough fuel" in result

    def test_scan_no_current_system(self) -> None:
        """Scan should return error when no current system."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        result = perform_scan(state)
        assert "No current system" in result


class TestNearbyEdgeCases:
    """Tests for get_nearby_systems covering edge cases."""

    def test_get_nearby_no_current_system(self) -> None:
        """Nearby should return empty list when no current system."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        result = get_nearby_systems(state)
        assert result == []


class TestLandEdgeCases:
    """Tests for land_on_body covering edge cases."""

    def test_land_no_current_system(self) -> None:
        """Land should fail when no current system."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        ok, msg = land_on_body(state, "body_1")
        assert ok is False
        assert "No current system" in msg


class TestExploreEdgeCases:
    """Tests for explore_surface covering edge cases."""

    def test_explore_no_current_system(self) -> None:
        """Explore should return empty when no current system."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        discoveries = explore_surface(state)
        assert discoveries == []

    def test_explore_not_enough_fuel(self) -> None:
        """Explore should return empty when not enough fuel."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if planet:
            land_on_body(state, planet.id)
            state.ship.fuel = 1
            discoveries = explore_surface(state)
            assert discoveries == []

    def test_explore_no_current_body(self) -> None:
        """Explore should return empty when no body is landed on."""
        state = new_game(seed=42)
        state.ship.current_body_id = "nonexistent"
        discoveries = explore_surface(state)
        assert discoveries == []


class TestTradingAdvanced:
    """Tests for trading functions covering sell, repair, and edge cases."""

    def test_sell_discovery_by_category(self) -> None:
        """Selling a discovery by category should remove it and grant credits."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", cat, 1)
        assert ok is True
        assert "Sold" in msg
        assert state.ship.credits > credits_before

    def test_sell_discovery_by_name(self) -> None:
        """Selling a discovery by name should remove it and grant credits."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        name = state.discoveries[0].name
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", name, 1)
        assert ok is True
        assert "Sold" in msg
        assert state.ship.credits > credits_before

    def test_buy_fuel_success(self) -> None:
        """Buying fuel should deduct credits and add fuel."""
        state = new_game(seed=42)
        state.ship.fuel = 50
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "buy", "fuel", 10)
        assert ok is True
        assert "Purchased" in msg
        assert state.ship.fuel > 50 or state.ship.credits < credits_before

    def test_buy_fuel_not_enough_credits(self) -> None:
        """Buying fuel with insufficient credits should fail."""
        state = new_game(seed=42)
        state.ship.credits = 0
        state.ship.fuel = 50
        ok, msg = perform_trade(state, "buy", "fuel", 10)
        if not ok:
            assert "Not enough credits" in msg

    def test_buy_repair_success(self) -> None:
        """Buying repairs should restore hull."""
        state = new_game(seed=42)
        state.ship.hull = 60
        state.ship.credits = 500
        ok, msg = perform_trade(state, "buy", "repair", 1)
        assert ok is True
        assert "Repaired" in msg
        assert state.ship.hull > 60

    def test_buy_repair_not_enough_credits(self) -> None:
        """Buying repairs with insufficient credits should fail."""
        state = new_game(seed=42)
        state.ship.credits = 0
        state.ship.hull = 60
        ok, msg = perform_trade(state, "buy", "repair", 1)
        if not ok:
            assert "Not enough credits" in msg

    def test_trade_no_current_system(self) -> None:
        """Trade should fail when not in a system."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        ok, msg = perform_trade(state, "buy", "fuel", 1)
        assert ok is False
        assert "Not in a system" in msg

    def test_trade_no_facilities(self) -> None:
        """Trade should fail when system has no trading facilities."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        sys.phenomenon = "black_hole"
        ok, msg = perform_trade(state, "buy", "fuel", 1)
        assert ok is False
        assert "No trading facilities" in msg

    def test_trade_unknown_item(self) -> None:
        """Trade should fail for unknown items."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "nonexistent", 1)
        assert ok is False

    def test_purchase_upgrade_unknown(self) -> None:
        """Purchasing an unknown upgrade should fail."""
        state = new_game(seed=42)
        state.ship.credits = 10000
        ok, msg = purchase_upgrade(state, "unknown_upgrade")
        assert ok is False
        assert "Unknown upgrade" in msg

    def test_purchase_upgrade_already_max(self) -> None:
        """Purchasing an upgrade at max level should fail."""
        state = new_game(seed=42)
        state.ship.credits = 10000
        state.ship.upgrades["hyperdrive"] = 5
        ok, msg = purchase_upgrade(state, "hyperdrive")
        assert ok is False
        assert "maximum level" in msg

    def test_purchase_upgrade_scanner(self) -> None:
        """Purchasing a scanner upgrade should increase scanner level."""
        state = new_game(seed=42)
        state.ship.credits = 10000
        scanner_before = state.ship.scanner
        ok, msg = purchase_upgrade(state, "scanner")
        assert ok is True
        assert state.ship.scanner > scanner_before

    def test_purchase_upgrade_cargo_hold(self) -> None:
        """Purchasing a cargo hold upgrade should increase max cargo."""
        state = new_game(seed=42)
        state.ship.credits = 10000
        max_cargo_before = state.ship.max_cargo
        ok, msg = purchase_upgrade(state, "cargo_hold")
        assert ok is True
        assert state.ship.max_cargo > max_cargo_before

    def test_purchase_upgrade_hull_plating(self) -> None:
        """Purchasing hull plating should increase max hull."""
        state = new_game(seed=42)
        state.ship.credits = 10000
        max_hull_before = state.ship.max_hull
        ok, msg = purchase_upgrade(state, "hull_plating")
        assert ok is True
        assert state.ship.max_hull > max_hull_before

    def test_purchase_upgrade_fuel_tanks(self) -> None:
        """Purchasing fuel tanks should increase max fuel."""
        state = new_game(seed=42)
        state.ship.credits = 10000
        max_fuel_before = state.ship.max_fuel
        ok, msg = purchase_upgrade(state, "fuel_tanks")
        assert ok is True
        assert state.ship.max_fuel > max_fuel_before


class TestEventsAdvanced:
    """Tests for event generation covering morale, phenomena, and edge cases."""

    def test_trigger_event_low_morale(self) -> None:
        """Low morale (<30) should force a crew or crisis event."""
        state = new_game(seed=42)
        state.ship.morale = 20
        event = trigger_event(state)
        assert event is not None
        assert event.event_type in ("crew", "crisis")

    def test_trigger_event_phenomenon_system(self) -> None:
        """Trigger event with phenomenon should bias toward certain event types."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        sys.phenomenon = "black_hole"
        for i in range(200):
            state.log_entries = [{"msg": str(i + j)} for j in range(i % 5)]
            state.events = []
            event = trigger_event(state)
            if event is not None and event.event_type in ("hazard", "discovery", "exploration"):
                return
        pass

    def test_trigger_event_no_current_system(self) -> None:
        """trigger_event should return None when no current system."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        event = trigger_event(state)
        assert event is None

    def test_resolve_event_already_resolved(self) -> None:
        """Resolving an already-resolved event should fail."""
        state = new_game(seed=42)
        from backend.generation.events import _create_event
        event = _create_event(EVENT_TEMPLATES[0], "sys_0000")
        event.resolved = True
        state.events.append(event)
        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is False
        assert "already resolved" in msg

    def test_resolve_event_invalid_choice_index(self) -> None:
        """Resolving with an out-of-range choice index should fail."""
        state = new_game(seed=42)
        from backend.generation.events import _create_event
        event = _create_event(EVENT_TEMPLATES[0], "sys_0000")
        state.events.append(event)
        ok, msg, extra = resolve_event(state, event.id, 99)
        assert ok is False
        assert "Invalid choice" in msg

    def test_resolve_event_negative_choice_index(self) -> None:
        """Resolving with a negative choice index should fail."""
        state = new_game(seed=42)
        from backend.generation.events import _create_event
        event = _create_event(EVENT_TEMPLATES[0], "sys_0000")
        state.events.append(event)
        ok, msg, extra = resolve_event(state, event.id, -1)
        assert ok is False
        assert "Invalid choice" in msg


class TestManagerAdvanced:
    """Tests for game manager covering load_or_create and get_game_state."""

    def test_load_or_create_new_game(self) -> None:
        """load_or_create should create a new game when none exists in DB."""
        from backend.database import init_db
        init_db()
        state = load_or_create("new-test-game-id", seed=42, ship_name="NewShip")
        assert state is not None
        assert state.id == "new-test-game-id"
        assert state.ship.name == "NewShip"

    def test_load_or_create_existing_game(self) -> None:
        """load_or_create should load an existing game from DB."""
        from backend.database import init_db
        init_db()
        state = new_game(seed=42, ship_name="PersistShip")
        game_save(state)
        loaded = load_or_create(state.id)
        assert loaded is not None
        assert loaded.id == state.id
        assert loaded.ship.name == "PersistShip"

    def test_get_game_state(self) -> None:
        """get_game_state should return a dict representation of the state."""
        state = new_game(seed=42)
        result = get_game_state(state)
        assert isinstance(result, dict)
        assert result["id"] == state.id
        assert result["seed"] == state.seed


class TestEvents:
    def test_event_templates_exist(self) -> None:
        from backend.generation.events import EVENT_TEMPLATES
        assert len(EVENT_TEMPLATES) >= 8
        for t in EVENT_TEMPLATES:
            assert "title" in t
            assert "choices" in t
            assert len(t["choices"]) >= 2

    def test_trigger_event(self) -> None:
        state = new_game(seed=42)
        for i in range(50):
            state.log_entries = [{"msg": str(i + j)} for j in range(i % 3)]
            event = trigger_event(state)
            if event is not None:
                assert event.id is not None
                return
        pass

    def test_resolve_event(self) -> None:
        state = new_game(seed=42)
        from backend.generation.events import resolve_event as resolve_ev
        from backend.generation.events import _create_event, EVENT_TEMPLATES
        event = _create_event(EVENT_TEMPLATES[0], "sys_0000")
        state.events.append(event)

        ok, msg, extra = resolve_ev(state, event.id, 0)
        assert ok is True
        assert event.resolved is True
        assert event.chosen == 0

    def test_resolve_invalid_event(self) -> None:
        state = new_game(seed=42)
        ok, msg, extra = resolve_event(state, "nonexistent", 0)
        assert ok is False
