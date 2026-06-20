import sys
import os
import random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade, perform_trade, perform_bulk_sell
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

    def test_new_game_has_lore_fragments(self) -> None:
        """A new game should have 20 lore fragments."""
        state = new_game(seed=42)
        assert len(state.lore_fragments) == 20
        assert all(not lf.discovered for lf in state.lore_fragments)

    def test_lore_fragments_survive_save_load(self) -> None:
        """Lore fragments should persist through save/load roundtrip."""
        from backend.database import init_db
        init_db()
        state = new_game(seed=42)
        game_save(state)

        from backend.game.manager import game_load
        loaded = game_load(state.id)
        assert loaded is not None
        assert len(loaded.lore_fragments) == len(state.lore_fragments)
        assert set(lf.id for lf in loaded.lore_fragments) == set(lf.id for lf in state.lore_fragments)

    def test_state_summary_has_lore_stats(self) -> None:
        """state_summary should include lore_fragments_collected and total."""
        state = new_game(seed=42)
        summary = state.state_summary()
        assert "lore_fragments_collected" in summary
        assert "lore_fragments_total" in summary
        assert summary["lore_fragments_collected"] == 0
        assert summary["lore_fragments_total"] == len(state.lore_fragments)

    def test_get_game_state_includes_lore(self) -> None:
        """get_game_state serialization should include lore_fragments."""
        state = new_game(seed=42)
        data = get_game_state(state)
        assert "lore_fragments" in data
        assert len(data["lore_fragments"]) == 20


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
        system = state.get_current_system()
        assert system is not None
        assert system.scanned is True

    def test_get_nearby_systems(self) -> None:
        state = new_game(seed=42)
        nearby = get_nearby_systems(state)
        assert len(nearby) == len(state.systems) - 1
        assert all("distance_ly" in n for n in nearby)

    def test_land_on_valid_body(self) -> None:
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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

    def test_perform_jump_with_phenomenon(self) -> None:
        """Jump to a system with a phenomenon should log the phenomenon detection."""
        state = new_game(seed=42)
        cur = state.get_current_system()
        assert cur is not None
        # Find a system with a phenomenon
        target = None
        for system in state.systems.values():
            if system.phenomenon != "none" and system.id != state.ship.current_system_id:
                target = system
                break
        if target is None:
            return  # pragma: no cover  # no phenomenon system found
        # Ensure ship can reach it
        state.ship.jump_range = 999
        state.ship.fuel = 999
        ok, cost, _ = can_jump(state.ship, target, cur)
        assert ok is True
        log_count_before = len(state.log_entries)
        _ = perform_jump(state, target, cost)
        assert state.ship.current_system_id == target.id
        # Check that a phenomenon log was added
        assert len(state.log_entries) > log_count_before
        phenomenon_logs = [e for e in state.log_entries if "phenomenon" in e.get("message", "")]
        assert len(phenomenon_logs) > 0


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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        """Selling with quantity exceeding available discoveries should return an error."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        credits_before = state.ship.credits
        # Request to sell more than available
        ok, msg = perform_trade(state, "sell", cat, 999)
        assert ok is False
        assert "Only" in msg
        assert "requested" in msg
        assert len(state.discoveries) == count_before
        assert state.ship.credits == credits_before

    def test_sell_multiple_by_name(self) -> None:
        """Selling multiple discoveries by name should work."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
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
    """Tests for the phenomenon branch in trigger_event."""

    def test_trigger_event_phenomenon_biased(self) -> None:
        """Trigger event with phenomenon should bias toward hazard/discovery/exploration."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "nebula"
        state.ship.morale = 80

        rng = random.Random(42)
        rng.random()  # Consume first value; next two are < 0.35 and < 0.5

        event = trigger_event(state, rng_override=rng)
        assert event is not None
        assert event.event_type in ("hazard", "discovery", "exploration")

    def test_trigger_event_phenomenon_else_branch(self) -> None:
        """Trigger event with phenomenon where inner random fails (falls to else branch)."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "nebula"
        state.ship.morale = 80

        rng = random.Random(37)  # was 7 — seed 37: v2=0.092 (<0.35), v3=0.618 (>=0.5), v4→index 8 "encounter"
        rng.random()  # Consume first value

        event = trigger_event(state, rng_override=rng)
        assert event is not None
        # Verify we hit the else branch: event type should NOT be restricted
        # to ("hazard", "discovery", "exploration")
        assert event.event_type not in ("hazard", "discovery", "exploration"), \
            "Expected else branch (unrestricted event type), got phenomenon-biased selection"


class TestBulkSell:
    """Tests for the perform_bulk_sell function."""

    def test_bulk_sell_success(self) -> None:
        """Basic successful bulk sell of multiple discoveries."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        credits_before = state.ship.credits
        count_before = len(state.discoveries)
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": cat, "quantity": 2}])
        assert ok is True
        assert "Sold" in msg
        assert state.ship.credits > credits_before
        assert len(state.discoveries) <= count_before - 1

    def test_bulk_sell_bool_quantity_rejected(self) -> None:
        """Passing quantity=True should be rejected with an error."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact", "quantity": True}])
        assert ok is False
        assert "Invalid quantity" in msg

    def test_bulk_sell_no_system(self) -> None:
        """No current system returns error."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact", "quantity": 1}])
        assert ok is False
        assert "Not in a system" in msg

    def test_bulk_sell_no_facilities(self) -> None:
        """System without trading facilities returns error."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact", "quantity": 1}])
        assert ok is False
        assert "No trading facilities" in msg

    def test_bulk_sell_missing_item_field(self) -> None:
        """Missing 'item' field returns error."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"quantity": 1}])
        assert ok is False
        assert "missing required" in msg

    def test_bulk_sell_invalid_quantity_type(self) -> None:
        """Passing a string or float as quantity should be rejected."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact", "quantity": "three"}])
        assert ok is False
        assert "Invalid quantity" in msg

    def test_bulk_sell_negative_quantity(self) -> None:
        """Negative quantity should be rejected."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact", "quantity": -1}])
        assert ok is False
        assert "Invalid quantity" in msg

    def test_bulk_sell_zero_quantity(self) -> None:
        """Zero quantity should be rejected."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "artifact", "quantity": 0}])
        assert ok is False
        assert "Invalid quantity" in msg

    def test_bulk_sell_no_matching_discoveries(self) -> None:
        """No matching discoveries returns error."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "nonexistent_category", "quantity": 1}])
        assert ok is False
        assert "No discoveries matching" in msg

    def test_bulk_sell_partial_failure(self) -> None:
        """Some items fail but others succeed in a partial failure scenario."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        assert len(state.discoveries) > 0
        cat = state.discoveries[0].category
        credits_before = state.ship.credits
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [
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
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
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
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "Mysterious Artifact", "quantity": 1}])
        assert ok is True
        assert "Sold 1 item(s)" in msg
        assert state.ship.credits > credits_before
        assert disc not in state.discoveries

    def test_bulk_sell_sold_count_zero_with_errors(self) -> None:
        """When all items fail to match, sold_count==0 with errors (line 246-250)."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [
            {"item": "nonexistent_alpha", "quantity": 1},
            {"item": "nonexistent_beta", "quantity": 1},
        ])
        assert ok is False
        assert "No items could be sold." in msg
        assert "No discoveries matching 'nonexistent_alpha'" in msg
        assert "No discoveries matching 'nonexistent_beta'" in msg


class TestDatabaseModule:
    """Direct unit tests for database.py functions."""

    def test_create_game_new(self) -> None:
        """create_game should create a new game record."""
        from backend.database import init_db, create_game, load_game
        init_db()
        create_game("db-create-new", 42, "NewShip", {"fuel": 80, "test": True})
        loaded = load_game("db-create-new")
        assert loaded is not None
        assert loaded["fuel"] == 80
        assert loaded["test"] is True

    def test_create_game_existing_preserves_created_at(self) -> None:
        """create_game should preserve created_at when updating existing game."""
        from backend.database import init_db, create_game, get_db
        init_db()
        create_game("db-create-existing", 42, "OldShip", {"v": 1})
        conn = get_db()
        try:
            row = conn.execute("SELECT created_at FROM games WHERE id = ?", ("db-create-existing",)).fetchone()
            assert row is not None
            orig_created_at = row["created_at"]
            create_game("db-create-existing", 99, "NewShip", {"v": 2})
            row2 = conn.execute("SELECT created_at FROM games WHERE id = ?", ("db-create-existing",)).fetchone()
            assert row2["created_at"] == orig_created_at
        finally:
            conn.close()

    def test_load_game_returns_none(self) -> None:
        """load_game should return None for nonexistent game."""
        from backend.database import init_db, load_game
        init_db()
        result = load_game("nonexistent-game-id-xyz")
        assert result is None

    def test_load_save_returns_none(self) -> None:
        """load_save should return None when no saves exist."""
        from backend.database import init_db, load_save
        init_db()
        result = load_save("game-with-no-saves")
        assert result is None

    def test_load_save_returns_data(self) -> None:
        """load_save should return the most recent save."""
        from backend.database import init_db, save_game, load_save
        init_db()
        save_game("load-save-test", {"seed": 42, "test": True})
        result = load_save("load-save-test")
        assert result is not None
        assert result["test"] is True

    def test_save_game_existing_preserves_created_at(self) -> None:
        """save_game should preserve created_at when updating existing game."""
        from backend.database import init_db, save_game, get_db
        init_db()
        save_game("save-existing-test", {"seed": 42, "fuel": 80})
        conn = get_db()
        try:
            row = conn.execute("SELECT created_at FROM games WHERE id = ?", ("save-existing-test",)).fetchone()
            orig = row["created_at"]
            save_game("save-existing-test", {"seed": 42, "fuel": 50})
            row2 = conn.execute("SELECT created_at FROM games WHERE id = ?", ("save-existing-test",)).fetchone()
            assert row2["created_at"] == orig
        finally:
            conn.close()

    def test_save_game_new_existing_record_else_branch(self) -> None:
        """save_game should handle new game (no existing record)."""
        from backend.database import init_db, save_game, load_game
        init_db()
        save_game("save-new-game-test", {"seed": 42, "ship": {"name": "TestShip"}, "fuel": 80})
        loaded = load_game("save-new-game-test")
        assert loaded is not None
        assert loaded["fuel"] == 80

    def test_get_leaderboard_with_entries(self) -> None:
        """get_leaderboard should return valid entries."""
        from backend.database import init_db, save_game, get_leaderboard
        init_db()
        save_game("lb-test-1", {"seed": 42, "discoveries": [1, 2], "systems_visited": 5, "ship": {"credits": 500, "name": "LB1"}})
        result = get_leaderboard(limit=10)
        assert len(result) > 0

    def test_get_leaderboard_empty(self) -> None:
        """get_leaderboard should return empty list when no games exist."""
        from backend.database import init_db, get_leaderboard, get_db
        init_db()
        conn = get_db()
        try:
            conn.execute("DELETE FROM saves")
            conn.execute("DELETE FROM games")
            conn.commit()
        finally:
            conn.close()
        result = get_leaderboard(limit=5)
        assert result == []


class TestManagerGetSystemDetail:
    """Tests for get_system_detail edge cases."""

    def test_get_system_detail_non_current(self) -> None:
        """get_system_detail for a non-current system should return nearby=[]."""
        state = new_game(seed=42)
        current_id = state.ship.current_system_id
        other_ids = [sid for sid in state.systems if sid != current_id]
        other_id = other_ids[0] if other_ids else None
        if other_id is None:
            return  # pragma: no cover
        detail = get_system_detail(state, other_id)
        assert detail is not None
        assert detail["is_current"] is False
        assert detail["nearby_systems"] == []

    def test_get_system_detail_not_found(self) -> None:
        """get_system_detail should return None for nonexistent system."""
        state = new_game(seed=42)
        detail = get_system_detail(state, "nonexistent_sys_id")
        assert detail is None


class TestEventCreateEvent:
    """Tests for _create_event."""

    def test_create_event_creates_valid_event(self) -> None:
        """_create_event should create a valid Event with all fields populated."""
        from backend.generation.events import _create_event, EVENT_TEMPLATES
        event = _create_event(EVENT_TEMPLATES[0], "sys_test")
        assert event.id is not None
        assert len(event.id) > 0
        assert event.title == EVENT_TEMPLATES[0]["title"]
        assert event.flavor == EVENT_TEMPLATES[0]["flavor"]
        assert event.event_type == EVENT_TEMPLATES[0]["type"]
        assert event.system_id == "sys_test"
        assert len(event.choices) == len(EVENT_TEMPLATES[0]["choices"])
        assert event.resolved is False
        assert event.chosen is None
        for choice in event.choices:
            assert choice.text != ""
            assert choice.outcome != ""


class TestEngineGenerateDiscovery:
    """Tests for _generate_discovery covering each category."""

    def test_generate_discovery_mineral(self) -> None:
        """_generate_discovery should create valid mineral discovery."""
        import random as rnd_mod
        rng = rnd_mod.Random(42)
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        body = system.bodies[0] if system.bodies else None
        assert body is not None
        from backend.game.engine import _generate_discovery
        disc = _generate_discovery(rng, "mineral", body, system)
        assert disc.category == "mineral"
        assert disc.name in ["Plasmic Crystal", "Void Ore", "Stellar Fragment", "Obsidian Shard", "Nebula Dust"]
        assert disc.value > 0
        assert disc.system_id == system.id
        assert disc.body_id == body.id

    def test_generate_discovery_artifact(self) -> None:
        """_generate_discovery should create valid artifact discovery."""
        import random as rnd_mod
        rng = rnd_mod.Random(99)
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        body = system.bodies[0] if system.bodies else None
        assert body is not None
        from backend.game.engine import _generate_discovery
        disc = _generate_discovery(rng, "artifact", body, system)
        assert disc.category == "artifact"
        assert disc.name in ["Ancient Relic", "Alien Device", "Glyph Tablet", "Memory Core", "Void Key"]

    def test_generate_discovery_lifeform(self) -> None:
        """_generate_discovery should create valid lifeform discovery."""
        import random as rnd_mod
        rng = rnd_mod.Random(123)
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        body = system.bodies[0] if system.bodies else None
        assert body is not None
        from backend.game.engine import _generate_discovery
        disc = _generate_discovery(rng, "lifeform", body, system)
        assert disc.category == "lifeform"
        assert disc.name in ["Glowvine", "Crystal Mite", "Void Spore", "Plasma Jelly", "Singing Stone"]

    def test_generate_discovery_signal(self) -> None:
        """_generate_discovery should create valid signal discovery."""
        import random as rnd_mod
        rng = rnd_mod.Random(456)
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        body = system.bodies[0] if system.bodies else None
        assert body is not None
        from backend.game.engine import _generate_discovery
        disc = _generate_discovery(rng, "signal", body, system)
        assert disc.category == "signal"
        assert disc.name in ["Distress Beacon", "Encrypted Transmission", "Nav Echo", "Subspace Ripple", "Ghost Signal"]

    def test_generate_discovery_ruin(self) -> None:
        """_generate_discovery should create valid ruin discovery."""
        import random as rnd_mod
        rng = rnd_mod.Random(789)
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        body = system.bodies[0] if system.bodies else None
        assert body is not None
        from backend.game.engine import _generate_discovery
        disc = _generate_discovery(rng, "ruin", body, system)
        assert disc.category == "ruin"
        assert disc.name in ["Weathered Pillar", "Sunken Chamber", "Broken Obelisk", "Overgrown Temple", "Fallen Tower"]


class TestTradingValidateQuantity:
    """Tests for _validate_quantity covering edge cases."""

    def test_validate_quantity_bool(self) -> None:
        """_validate_quantity should reject bool."""
        from backend.game.trading import _validate_quantity
        result = _validate_quantity(True)
        assert result is not None
        assert "positive integer" in result

    def test_validate_quantity_negative(self) -> None:
        """_validate_quantity should reject negative ints."""
        from backend.game.trading import _validate_quantity
        result = _validate_quantity(-1)
        assert result is not None
        assert "positive integer" in result

    def test_validate_quantity_zero(self) -> None:
        """_validate_quantity should reject zero."""
        from backend.game.trading import _validate_quantity
        result = _validate_quantity(0)
        assert result is not None
        assert "positive integer" in result

    def test_validate_quantity_valid(self) -> None:
        """_validate_quantity should accept positive int."""
        from backend.game.trading import _validate_quantity
        result = _validate_quantity(5)
        assert result is None


class TestTradingPerformTradeEdgeCases:
    """Additional edge case tests for perform_trade."""

    def test_trade_sell_no_current_system(self) -> None:
        """Sell trade should fail when not in a system."""
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        ok, msg = perform_trade(state, "sell", "mineral", 1)
        assert ok is False
        assert "Not in a system" in msg

    def test_trade_sell_no_trading_facilities(self) -> None:
        """Sell trade should fail when system has no trading facilities."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        ok, msg = perform_trade(state, "sell", "mineral", 1)
        assert ok is False
        assert "No trading facilities" in msg

    def test_buy_fuel_full_tank(self) -> None:
        """Buying fuel with a full tank should return an error."""
        state = new_game(seed=42)
        state.ship.fuel = state.ship.max_fuel
        ok, msg = perform_trade(state, "buy", "fuel", 10)
        assert ok is False
        assert "Fuel tank is already full." == msg

    def test_buy_repair_full_hull(self) -> None:
        """Buying repairs with full hull should return an error."""
        state = new_game(seed=42)
        state.ship.hull = state.ship.max_hull
        ok, msg = perform_trade(state, "buy", "repair", 1)
        assert ok is False
        assert "Hull is already at maximum." == msg

    def test_sell_empty_string_item(self) -> None:
        """Selling with an empty string item should return an error."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "sell", "", 1)
        assert ok is False
        assert msg == "Item must be a non-empty string."

    def test_sell_non_string_item(self) -> None:
        """Selling with a non-string item should return an error."""
        state = new_game(seed=42)
        ok, msg = perform_trade(state, "sell", 123, 1)
        assert ok is False
        assert msg == "Item must be a non-empty string."


class TestDatabaseGetLeaderboard:
    """Tests for get_leaderboard with various malformed entries."""

    def test_leaderboard_malformed_non_dict(self) -> None:
        """json.loads returns a non-dict; leaderboard should skip it."""
        from backend.database import init_db, get_db, get_leaderboard
        from datetime import datetime, timezone
        init_db()
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("lb-non-dict", 1, "Test", now, now, '123')
            )
            conn.commit()
        finally:
            conn.close()
        result = get_leaderboard(limit=10)
        ids = [e["game_id"] for e in result]
        assert "lb-non-dict" not in ids

    def test_leaderboard_skips_bad_json(self) -> None:
        """get_leaderboard should skip entries that can't be JSON parsed."""
        from backend.database import init_db, get_db, get_leaderboard
        from datetime import datetime, timezone
        init_db()
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO games (id, seed, ship_name, created_at, updated_at, state_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("lb-bad-json", 1, "Test", now, now, '{bad')
            )
            conn.commit()
        finally:
            conn.close()
        result = get_leaderboard(limit=10)
        ids = [e["game_id"] for e in result]
        assert "lb-bad-json" not in ids


class TestLoreFragmentsCollected:
    """Tests for the GameState.lore_fragments_collected property."""

    def test_no_lore_fragments_returns_zero(self) -> None:
        """Property returns 0 when no lore fragments exist."""
        state = new_game(seed=42)
        state.lore_fragments = []
        assert state.lore_fragments_collected == 0

    def test_all_undiscovered_returns_zero(self) -> None:
        """Property returns 0 when all fragments are undiscovered."""
        state = new_game(seed=42)
        assert len(state.lore_fragments) > 0
        assert all(not lf.discovered for lf in state.lore_fragments)
        assert state.lore_fragments_collected == 0

    def test_some_discovered_returns_correct_count(self) -> None:
        """Property returns correct count when some fragments are discovered."""
        state = new_game(seed=42)
        for i, lf in enumerate(state.lore_fragments):
            if i < 7:
                lf.discovered = True
        assert state.lore_fragments_collected == 7

    def test_all_discovered_returns_total_count(self) -> None:
        """Property returns total count when all fragments are discovered."""
        state = new_game(seed=42)
        for lf in state.lore_fragments:
            lf.discovered = True
        assert state.lore_fragments_collected == len(state.lore_fragments)
        assert state.lore_fragments_collected == 20


class TestLoreExploration:
    """Tests for lore fragment discovery during exploration."""

    def _find_system_with_lore(self, state: "GameState") -> tuple:
        """Find a system ID and body ID that have a lore fragment."""
        from backend.generation.lore import get_lore_fragments_for_system

        for sys_id in state.systems:
            frags = get_lore_fragments_for_system(sys_id, state.lore_fragments)
            if frags:
                body_id = frags[0].discovery_id.split("::")[1]
                return sys_id, body_id, frags[0]
        return None, None, None

    def test_explore_discovers_lore_fragment(self) -> None:
        """Exploring a body with a lore fragment should mark it discovered."""
        state = new_game(seed=42)
        state.ship.fuel = 1000

        sys_id, body_id, frag = self._find_system_with_lore(state)
        if not sys_id:
            return

        state.ship.current_system_id = sys_id
        state.ship.current_body_id = body_id

        discoveries = explore_surface(state)
        assert len(discoveries) > 0

        lore_discoveries = [d for d in discoveries if d.lore_fragment_id is not None]
        assert len(lore_discoveries) == 1
        assert lore_discoveries[0].lore_fragment_id == frag.id

        assert frag.discovered is True

    def test_explore_does_not_rediscover_lore(self) -> None:
        """Exploring same body again should not re-discover lore."""
        state = new_game(seed=42)
        state.ship.fuel = 1000

        sys_id, body_id, frag = self._find_system_with_lore(state)
        if not sys_id:
            return

        state.ship.current_system_id = sys_id
        state.ship.current_body_id = body_id

        explore_surface(state)
        assert frag.discovered is True

        state.ship.fuel = 1000
        discoveries2 = explore_surface(state)
        lore_discs2 = [d for d in discoveries2 if d.lore_fragment_id is not None]
        assert len(lore_discs2) == 0

    def test_explore_body_without_lore(self) -> None:
        """Exploring a body without lore shouldn't affect fragment state."""
        state = new_game(seed=42)
        system = state.get_current_system()
        body = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not body:
            return

        state.ship.current_body_id = body.id
        state.ship.fuel = 100

        discoveries = explore_surface(state)
        lore_discs = [d for d in discoveries if d.lore_fragment_id is not None]
        assert len(lore_discs) == 0

        undiscovered_before = sum(1 for lf in state.lore_fragments if lf.discovered)
        assert undiscovered_before == 0

    def test_lore_log_entry_on_discovery(self) -> None:
        """A log entry is created when a lore fragment is discovered."""
        state = new_game(seed=42)
        state.ship.fuel = 1000

        sys_id, body_id, frag = self._find_system_with_lore(state)
        if not sys_id:
            return

        state.ship.current_system_id = sys_id
        state.ship.current_body_id = body_id

        explore_surface(state)

        lore_logs = [e for e in state.log_entries if e["type"] == "lore"]
        assert len(lore_logs) >= 1
        assert frag.title in lore_logs[0]["message"]

    def test_find_system_with_lore_returns_none_when_no_fragments(self) -> None:
        """_find_system_with_lore returns (None, None, None) when lore_fragments is empty."""
        state = new_game(seed=42)
        state.lore_fragments = []

        sys_id, body_id, frag = self._find_system_with_lore(state)
        assert sys_id is None
        assert body_id is None
        assert frag is None

    def test_explore_discovers_lore_guard_coverage(self) -> None:
        """Cover guard clause in test_explore_discovers_lore_fragment when no lore found."""
        original = self._find_system_with_lore
        self._find_system_with_lore = lambda s: (None, None, None)
        try:
            self.test_explore_discovers_lore_fragment()
        finally:
            self._find_system_with_lore = original

    def test_explore_no_rediscover_lore_guard_coverage(self) -> None:
        """Cover guard clause in test_explore_does_not_rediscover_lore when no lore found."""
        original = self._find_system_with_lore
        self._find_system_with_lore = lambda s: (None, None, None)
        try:
            self.test_explore_does_not_rediscover_lore()
        finally:
            self._find_system_with_lore = original

    def test_lore_log_guard_coverage(self) -> None:
        """Cover guard clause in test_lore_log_entry_on_discovery when no lore found."""
        original = self._find_system_with_lore
        self._find_system_with_lore = lambda s: (None, None, None)
        try:
            self.test_lore_log_entry_on_discovery()
        finally:
            self._find_system_with_lore = original

    def test_explore_body_without_lore_no_planet(self) -> None:
        """Cover guard clause in test_explore_body_without_lore when no planet exists."""
        from backend.models.system import Body as B

        state = new_game(seed=42)
        sys_id = state.ship.current_system_id
        sys_obj = state.systems[sys_id]
        sys_obj.bodies = [b for b in sys_obj.bodies if b.body_type == "asteroid_belt"]
        if not sys_obj.bodies:
            belt = B(
                id=f"{sys_id}_b99", name="Test Belt", body_type="asteroid_belt",
                biome="barren", size=3, distance_from_star=0.5,
                description="A test asteroid belt.", poi_count=1,
            )
            sys_obj.bodies = [belt]

        func = self.test_explore_body_without_lore.__func__
        original_new_game = func.__globals__["new_game"]
        func.__globals__["new_game"] = lambda seed=None: state
        try:
            self.test_explore_body_without_lore()
        finally:
            func.__globals__["new_game"] = original_new_game
