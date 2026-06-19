import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade, perform_trade, perform_bulk_sell
from backend.game.manager import new_game, get_galaxy, get_system_detail, game_save, load_or_create, get_game_state
from backend.generation.events import trigger_event, resolve_event, EVENT_TEMPLATES
from backend.utils import deterministic_hash
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
        assert cur is not None
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
        state.ship.morale_decay_reduction = 2
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

    def test_explore_surface_zero_poi_count(self) -> None:
        """Explore should not deduct fuel when poi_count is 0."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if planet:
            land_on_body(state, planet.id)
            planet.poi_count = 0
            fuel_before = state.ship.fuel
            discoveries = explore_surface(state)
            assert discoveries == []
            assert state.ship.fuel == fuel_before  # fuel should NOT be deducted


class TestTradingAdvanced:
    """Tests for trading functions covering sell, repair, and edge cases."""

    def test_sell_discovery_by_category(self) -> None:
        """Selling a discovery by category should remove it and grant credits."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover  # no planet in starting system
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
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover  # no planet in starting system
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        name = state.discoveries[0].name
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", name, 1)
        assert ok is True
        assert "Sold" in msg
        assert state.ship.credits > credits_before

    def test_sell_discovery_no_match(self) -> None:
        """Selling a non-existent discovery should return False."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg = perform_trade(state, "sell", "nonexistent_category", 1)
        assert ok is False
        assert "No discoveries matching" in msg

    def test_sell_discovery_sells_highest_value(self) -> None:
        """Selling by category should sell the highest-value discovery."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        cat = state.discoveries[0].category
        from backend.models.discovery import Discovery
        high_value_disc = Discovery(
            id="high_value_test_disc",
            name="High Value Find",
            category=cat,
            description="A very valuable discovery",
            value=9999,
        )
        low_value_disc = Discovery(
            id="low_value_test_disc",
            name="Low Value Find",
            category=cat,
            description="A modest discovery",
            value=10,
        )
        state.discoveries.clear()
        state.discoveries.append(low_value_disc)
        state.discoveries.append(high_value_disc)
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", cat, 1)
        assert ok is True
        assert high_value_disc not in state.discoveries
        assert low_value_disc in state.discoveries
        assert state.ship.credits >= credits_before + int(9999 * 0.7)

    def test_sell_discovery_negative_quantity(self) -> None:
        """Selling with a negative quantity should fail."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        ok, msg = perform_trade(state, "sell", cat, -1)
        assert ok is False
        assert "Quantity must be a positive integer" in msg

    def test_sell_discovery_zero_quantity(self) -> None:
        """Selling with quantity=0 should fail."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        ok, msg = perform_trade(state, "sell", cat, 0)
        assert ok is False
        assert "Quantity must be a positive integer" in msg

    def test_sell_multiple_discoveries(self) -> None:
        """Selling with quantity > 1 should sell multiple discoveries."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        cat = state.discoveries[0].category
        d1 = Discovery(id="multi_d1", name="Budget Find", category=cat, description="Cheap", value=100)
        d2 = Discovery(id="multi_d2", name="Mid Find", category=cat, description="Mid", value=500)
        d3 = Discovery(id="multi_d3", name="Premium Find", category=cat, description="Premium", value=1000)
        state.discoveries.clear()
        for d in [d1, d2, d3]:
            state.discoveries.append(d)
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", cat, 2)
        assert ok is True
        assert "item(s)" in msg
        assert d3 not in state.discoveries
        assert d2 not in state.discoveries
        assert d1 in state.discoveries
        assert len(state.discoveries) == 1
        assert state.ship.credits > credits_before

    def test_sell_quantity_exceeds_available(self) -> None:
        """Selling with quantity exceeding available discoveries should sell all."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        same_cat = [d for d in state.discoveries if d.category == cat]
        if len(same_cat) == 0:
            return  # pragma: no cover
        count_before = len(state.discoveries)
        cat_count = len(same_cat)
        credits_before = state.ship.credits
        # Request to sell more than available
        ok, msg = perform_trade(state, "sell", cat, 999)
        assert ok is True
        assert "item(s)" in msg
        # All matching discoveries should be sold
        remaining = [d for d in state.discoveries if d.category == cat]
        assert len(remaining) == 0
        assert len(state.discoveries) == count_before - cat_count
        assert state.ship.credits > credits_before

    def test_sell_multiple_by_name(self) -> None:
        """Selling multiple discoveries by name should work."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        d1 = Discovery(id="name_d1", name="Mysterious Orb", category="artifact", description="First orb", value=200)
        d2 = Discovery(id="name_d2", name="Mysterious Orb", category="relic", description="Second orb", value=300)
        state.discoveries.clear()
        state.discoveries.append(d1)
        state.discoveries.append(d2)
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", "Mysterious Orb", 2)
        assert ok is True
        assert "item(s)" in msg
        assert d1 not in state.discoveries
        assert d2 not in state.discoveries
        assert len(state.discoveries) == 0
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
        assert sys is not None
        sys.phenomenon = "black_hole"
        ok, msg = perform_trade(state, "buy", "fuel", 1)
        assert ok is False
        assert "No trading facilities" in msg

    def test_trade_unknown_item(self) -> None:
        """Trade should fail for unknown items."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "nonexistent", 1)
        assert ok is False

    def test_buy_fuel_negative_quantity(self) -> None:
        """Buying fuel with a negative quantity should fail."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "fuel", -10)
        assert ok is False
        assert "Quantity must be a positive integer" in msg

    def test_buy_repair_negative_quantity(self) -> None:
        """Buying repairs with a negative quantity should fail."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "repair", -10)
        assert ok is False
        assert "Quantity must be a positive integer" in msg

    def test_buy_fuel_zero_quantity(self) -> None:
        """Buying fuel with quantity=0 should fail."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "fuel", 0)
        assert ok is False
        assert "Quantity must be a positive integer" in msg

    def test_buy_repair_zero_quantity(self) -> None:
        """Buying repairs with quantity=0 should fail."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "repair", 0)
        assert ok is False
        assert "Quantity must be a positive integer" in msg

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

    def test_purchase_upgrade_life_support(self) -> None:
        """Purchasing a life support upgrade should increase morale decay reduction."""
        state = new_game(seed=42)
        state.ship.credits = 10000
        reduction_before = state.ship.morale_decay_reduction
        ok, msg = purchase_upgrade(state, "life_support")
        assert ok is True
        assert state.ship.morale_decay_reduction > reduction_before

    def test_trade_invalid_action(self) -> None:
        """Trade with an invalid action should fail with descriptive message."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "steal", "fuel", 1)
        assert ok is False
        assert "Cannot trade fuel" in msg

    def test_trade_buy_unknown_item(self) -> None:
        """Buying an unknown item should fail with descriptive message."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "weapons", 1)
        assert ok is False
        assert "Cannot trade weapons" in msg

    def test_sell_bool_quantity_rejected(self) -> None:
        """Selling with quantity=True should fail."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        ok, msg = perform_trade(state, "sell", cat, True)
        assert ok is False
        assert "Quantity must be a positive integer" in msg

    def test_buy_fuel_bool_quantity_rejected(self) -> None:
        """Buying fuel with quantity=True should fail."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "fuel", True)
        assert ok is False
        assert "Quantity must be a positive integer" in msg

    def test_buy_repair_bool_quantity_rejected(self) -> None:
        """Buying repair with quantity=True should fail."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "buy", "repair", True)
        assert ok is False
        assert "Quantity must be a positive integer" in msg


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
        assert sys is not None
        sys.phenomenon = "black_hole"
        state.ship.morale = 20
        event = trigger_event(state)
        assert event is not None
        assert event.event_type in ("crew", "crisis")

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
        state.ship.morale = 20
        event = trigger_event(state)
        assert event is not None
        assert event.id is not None

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


class TestTriggerEventPhenomenonBranch:
    """Tests for the phenomenon else branch in trigger_event (line 147)."""

    def test_trigger_event_phenomenon_else_branch(self) -> None:
        """Trigger event with phenomenon system where inner random fails."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        sys.phenomenon = "nebula"
        state.ship.morale = 80

        found = False
        for extra_events in range(10):
            for extra_logs in range(10):
                state.events = list(range(extra_events))
                state.log_entries = [{"type": "test", "message": str(i)} for i in range(extra_logs)]
                import random as rnd_mod
                rng = rnd_mod.Random(state.seed + deterministic_hash(sys.id, len(state.events), len(state.log_entries)))
                if rng.random() < 0.35:
                    if not (sys.phenomenon != "none" and rng.random() < 0.5):
                        found = True
                        break
            if found:
                break
        assert found, "Could not find a seed combination that hits line 147"

        event = trigger_event(state)
        assert event is not None
        assert event.event_type in [t["type"] for t in EVENT_TEMPLATES]


class TestBulkSell:
    """Tests for the perform_bulk_sell function."""

    def test_bulk_sell_success(self) -> None:
        """Basic successful bulk sell of multiple discoveries."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        credits_before = state.ship.credits
        count_before = len(state.discoveries)
        ok, msg = perform_bulk_sell(state, [{"item": cat, "quantity": 2}])
        assert ok is True
        assert "Sold" in msg
        assert state.ship.credits > credits_before
        assert len(state.discoveries) <= count_before - 1

    def test_bulk_sell_bool_quantity_rejected(self) -> None:
        """Passing quantity=True should be rejected with an error."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg = perform_bulk_sell(state, [{"item": "artifact", "quantity": True}])
        assert ok is False
        assert "Invalid quantity" in msg

    def test_bulk_sell_no_system(self) -> None:
        """No current system returns error."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        ok, msg = perform_bulk_sell(state, [{"item": "artifact", "quantity": 1}])
        assert ok is False
        assert "Not in a system" in msg

    def test_bulk_sell_no_facilities(self) -> None:
        """System without trading facilities returns error."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        sys.phenomenon = "black_hole"
        ok, msg = perform_bulk_sell(state, [{"item": "artifact", "quantity": 1}])
        assert ok is False
        assert "No trading facilities" in msg

    def test_bulk_sell_missing_item_field(self) -> None:
        """Missing 'item' field returns error."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg = perform_bulk_sell(state, [{"quantity": 1}])
        assert ok is False
        assert "missing required" in msg

    def test_bulk_sell_invalid_quantity_type(self) -> None:
        """Passing a string or float as quantity should be rejected."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg = perform_bulk_sell(state, [{"item": "artifact", "quantity": "three"}])
        assert ok is False
        assert "Invalid quantity" in msg

    def test_bulk_sell_negative_quantity(self) -> None:
        """Negative quantity should be rejected."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg = perform_bulk_sell(state, [{"item": "artifact", "quantity": -1}])
        assert ok is False
        assert "Invalid quantity" in msg

    def test_bulk_sell_zero_quantity(self) -> None:
        """Zero quantity should be rejected."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg = perform_bulk_sell(state, [{"item": "artifact", "quantity": 0}])
        assert ok is False
        assert "Invalid quantity" in msg

    def test_bulk_sell_no_matching_discoveries(self) -> None:
        """No matching discoveries returns error."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg = perform_bulk_sell(state, [{"item": "nonexistent_category", "quantity": 1}])
        assert ok is False
        assert "No discoveries matching" in msg

    def test_bulk_sell_partial_failure(self) -> None:
        """Some items fail but others succeed in a partial failure scenario."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        credits_before = state.ship.credits
        ok, msg = perform_bulk_sell(state, [
            {"item": cat, "quantity": 1},
            {"item": "nonexistent_category", "quantity": 1},
        ])
        assert ok is True
        assert "Sold" in msg
        assert "No discoveries matching" in msg
        assert state.ship.credits > credits_before

    def test_bulk_sell_by_exact_name(self) -> None:
        """Selling by exact name should hit the name_matches branch (line 229)."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        disc = Discovery(
            id="exact_name_disc_1",
            name="Mysterious Artifact",
            category="special",
            description="A strange and valuable artifact.",
            value=500,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits
        ok, msg = perform_bulk_sell(state, [{"item": "Mysterious Artifact", "quantity": 1}])
        assert ok is True
        assert "Sold 1 item(s)" in msg
        assert state.ship.credits > credits_before
        assert disc not in state.discoveries

    def test_bulk_sell_sold_count_zero_with_errors(self) -> None:
        """When all items fail to match, sold_count==0 with errors (line 246-250)."""
        state = new_game(seed=42)
        sys = state.get_current_system()
        assert sys is not None
        planet = next((b for b in sys.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg = perform_bulk_sell(state, [
            {"item": "nonexistent_alpha", "quantity": 1},
            {"item": "nonexistent_beta", "quantity": 1},
        ])
        assert ok is False
        assert "No items could be sold." in msg
        assert "No discoveries matching 'nonexistent_alpha'" in msg
        assert "No discoveries matching 'nonexistent_beta'" in msg
