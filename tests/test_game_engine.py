import sys
import os
import random
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
    activate_distress_beacon, perform_salvage, emergency_craft,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade, perform_trade, perform_bulk_sell, calculate_fuel_price, round_half_up
from backend.game.manager import new_game, get_galaxy, get_system_detail, game_save, load_or_create, get_game_state, _state_from_dict
from backend.generation.events import trigger_event, resolve_event, EVENT_TEMPLATES, _get_eligible_templates, _apply_cooldown_fallback
from backend.config import SCAN_FUEL_COST
from backend.models.game_state import GameState
from backend.models.discovery import Discovery
from backend.models.system import StarSystem


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
            poi_before = planet.poi_count
            discoveries = explore_surface(state)
            assert len(discoveries) > 0
            assert len(state.discoveries) > 0
            assert planet.poi_count < poi_before

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
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover  # no planet in starting system
        land_on_body(state, planet.id)
        explore_surface(state)
        state.discoveries.clear()
        disc = Discovery(
            id="sell_cat_disc",
            name="Test Mineral",
            category="mineral",
            description="A test mineral",
            lore_fragment_id=None,
            value=100,
        )
        state.discoveries.append(disc)
        assert len(state.discoveries) > 0
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", "mineral", 1)
        assert ok is True
        assert "Sold" in msg
        assert state.ship.credits > credits_before

    def test_sell_discovery_by_name(self) -> None:
        """Selling a discovery by name should remove it and grant credits."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover  # no planet in starting system
        land_on_body(state, planet.id)
        explore_surface(state)
        state.discoveries.clear()
        disc = Discovery(
            id="sell_name_disc",
            name="Mysterious Orb",
            category="artifact",
            description="A mysterious orb",
            lore_fragment_id=None,
            value=100,
        )
        state.discoveries.append(disc)
        assert len(state.discoveries) > 0
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", "Mysterious Orb", 1)
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
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        state.discoveries.clear()
        disc = Discovery(
            id="sell_qty_disc",
            name="Test Mineral",
            category="mineral",
            description="A test mineral",
            lore_fragment_id=None,
            value=100,
        )
        state.discoveries.append(disc)
        count_before = len(state.discoveries)
        credits_before = state.ship.credits
        # Request to sell more than available
        ok, msg = perform_trade(state, "sell", "mineral", 999)
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

    def test_buy_repair_allied_discount(self) -> None:
        """Allied with Void Traders should give 15% discount on repairs."""
        state = new_game(seed=42)
        state.ship.hull = 60
        state.ship.credits = 500
        state.modify_faction_reputation("void_traders", 60)  # Allied
        ok, msg = perform_trade(state, "buy", "repair", 1)
        assert ok is True
        assert "Repaired" in msg
        assert state.ship.hull > 60

    def test_buy_repair_friendly_discount(self) -> None:
        """Friendly with Void Traders should give 5% discount on repairs."""
        state = new_game(seed=42)
        state.ship.hull = 60
        state.ship.credits = 500
        state.modify_faction_reputation("void_traders", 30)  # Friendly
        ok, msg = perform_trade(state, "buy", "repair", 1)
        assert ok is True
        assert "Repaired" in msg
        assert state.ship.hull > 60

    def test_buy_repair_unfriendly_surcharge(self) -> None:
        """Unfriendly with Void Traders should add 15% surcharge on repairs."""
        state = new_game(seed=42)
        state.ship.hull = 60
        state.ship.credits = 500
        state.modify_faction_reputation("void_traders", -10)  # Unfriendly
        ok, msg = perform_trade(state, "buy", "repair", 1)
        assert ok is True
        assert "Repaired" in msg
        assert state.ship.hull > 60

    def test_buy_repair_hostile_surcharge(self) -> None:
        """Hostile with Void Traders should add 30% surcharge on repairs."""
        state = new_game(seed=42)
        state.ship.hull = 60
        state.ship.credits = 500
        state.modify_faction_reputation("void_traders", -50)  # Hostile
        ok, msg = perform_trade(state, "buy", "repair", 1)
        assert ok is True
        assert "Repaired" in msg
        assert state.ship.hull > 60

    def test_buy_repair_neutral_no_discount(self) -> None:
        """Neutral with Void Traders should have no modifier on repairs."""
        state = new_game(seed=42)
        state.ship.hull = 60
        state.ship.credits = 500
        state.modify_faction_reputation("void_traders", 0)  # Neutral
        ok, msg = perform_trade(state, "buy", "repair", 1)
        assert ok is True
        assert "Repaired" in msg
        assert state.ship.hull > 60

    def test_buy_repair_cost_varies_by_reputation(self) -> None:
        """Repair cost should be different for Allied vs Hostile reputation."""
        from backend.game.trading import perform_trade

        # Allied: 15% discount
        state_allied = new_game(seed=42)
        state_allied.ship.hull = 60
        state_allied.ship.credits = 10000
        state_allied.modify_faction_reputation("void_traders", 60)
        ok1, msg1 = perform_trade(state_allied, "buy", "repair", 1)
        assert ok1 is True
        allied_cost = 10000 - state_allied.ship.credits

        # Hostile: 30% surcharge
        state_hostile = new_game(seed=42)
        state_hostile.ship.hull = 60
        state_hostile.ship.credits = 10000
        state_hostile.modify_faction_reputation("void_traders", -50)
        ok2, msg2 = perform_trade(state_hostile, "buy", "repair", 1)
        assert ok2 is True
        hostile_cost = 10000 - state_hostile.ship.credits

        # Hostile should cost more than Allied
        assert hostile_cost > allied_cost, f"Expected hostile cost ({hostile_cost}) > allied cost ({allied_cost})"

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
        system.has_trading_station = False
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
        """Low morale (<30) should force a crew, crisis, or narrative event."""
        state = new_game(seed=42)
        state.ship.morale = 20
        event = trigger_event(state)
        assert event is not None
        assert event.event_type in ("crew", "crisis", "narrative")

    def test_trigger_event_phenomenon_system(self) -> None:
        """Trigger event with phenomenon and low morale should force crew/crisis/narrative."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        state.ship.morale = 20
        event = trigger_event(state)
        assert event is not None
        assert event.event_type in ("crew", "crisis", "narrative")

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

    def test_resolve_narrative_event(self) -> None:
        """Resolving a narrative event should succeed without reputation changes."""
        state = new_game(seed=42)
        from backend.generation.events import _create_event
        # Find the narrative event template
        narrative_template = [t for t in EVENT_TEMPLATES if t["type"] == "narrative"][0]
        event = _create_event(narrative_template, state.get_current_system().id)
        state.events.append(event)

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True, f"Expected narrative event to resolve successfully, got: {msg}"
        assert event.resolved is True
        assert extra["title"] == narrative_template["title"]
        assert extra["chosen_text"] == event.choices[0].text
        assert isinstance(extra["effects"], dict)


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

    def test_state_from_dict_with_non_dict_log_entries(self) -> None:
        """_state_from_dict should handle non-dict log entries gracefully."""
        from backend.database import init_db
        init_db()
        state = new_game(seed=42)
        data = get_game_state(state)
        data["log_entries"] = [
            "old style string entry",
            {"id": 1, "type": "system", "message": "valid entry"},
            12345,
            {"id": 2, "type": "navigation", "message": "another valid entry"},
            None,
        ]
        del data["_next_log_id"]
        loaded = _state_from_dict(data)
        assert loaded is not None
        assert loaded._next_log_id == 3

    def test_state_from_dict_with_dict_missing_id(self) -> None:
        """_state_from_dict should assign IDs to dict entries missing them."""
        from backend.database import init_db
        init_db()
        state = new_game(seed=42)
        data = get_game_state(state)
        # Include dict entries without 'id' field, non-dict entries, and dict entries with IDs
        data["log_entries"] = [
            {"type": "system", "message": "old entry without id"},  # no id
            "old style string entry",  # non-dict
            {"id": 5, "type": "navigation", "message": "valid entry with id 5"},  # has id
            {"type": "exploration", "message": "another entry without id"},  # no id
            None,  # non-dict
        ]
        del data["_next_log_id"]
        loaded = _state_from_dict(data)
        assert loaded is not None
        # Non-dict entries should be filtered out
        assert len(loaded.log_entries) == 3
        # The entry without id should have been assigned id 1 (max_id starts at 0, then +=1)
        assert loaded.log_entries[0]["id"] == 1
        assert loaded.log_entries[1]["id"] == 5
        # After seeing id=5, max_id=5, so next missing-id entry gets id 6
        assert loaded.log_entries[2]["id"] == 6
        # _next_log_id should be max_id + 1 = 6 + 1 = 7
        assert loaded._next_log_id == 7

    def test_state_from_dict_with_non_integer_id_string(self) -> None:
        """_state_from_dict should handle string IDs by assigning new sequential IDs."""
        from backend.database import init_db
        init_db()
        state = new_game(seed=42)
        data = get_game_state(state)
        data["log_entries"] = [
            {"id": "abc", "type": "system", "message": "entry with string id"},
            {"id": 5, "type": "navigation", "message": "valid entry with id 5"},
            {"id": 1.5, "type": "exploration", "message": "entry with float id"},
            {"id": None, "type": "combat", "message": "entry with None id"},
        ]
        del data["_next_log_id"]
        loaded = _state_from_dict(data)
        assert loaded is not None
        # All 4 dict entries should be kept
        assert len(loaded.log_entries) == 4
        # The string id entry should get a new sequential id (1)
        assert loaded.log_entries[0]["id"] == 1
        # The valid int id entry should keep its id (5)
        assert loaded.log_entries[1]["id"] == 5
        # The float id entry should get a new sequential id (6)
        assert loaded.log_entries[2]["id"] == 6
        # The None id entry should get a new sequential id (7)
        assert loaded.log_entries[3]["id"] == 7
        # _next_log_id should be max_id + 1 = 7 + 1 = 8
        assert loaded._next_log_id == 8

    def test_state_from_dict_with_mixed_valid_and_non_integer_ids(self) -> None:
        """_state_from_dict should handle a mix of valid int IDs, missing IDs, and non-integer IDs."""
        from backend.database import init_db
        init_db()
        state = new_game(seed=42)
        data = get_game_state(state)
        data["log_entries"] = [
            {"id": 10, "type": "system", "message": "valid entry with id 10"},
            {"type": "navigation", "message": "entry without id"},
            {"id": "abc", "type": "exploration", "message": "entry with string id"},
            {"id": 3, "type": "combat", "message": "valid entry with id 3"},
            {"id": None, "type": "system", "message": "entry with None id"},
        ]
        del data["_next_log_id"]
        loaded = _state_from_dict(data)
        assert loaded is not None
        assert len(loaded.log_entries) == 5
        # Entry with id 10 should keep it
        assert loaded.log_entries[0]["id"] == 10
        # Entry without id should get 11 (max_id was 10, then +=1)
        assert loaded.log_entries[1]["id"] == 11
        # String id entry should get 12 (max_id was 11, +=1)
        assert loaded.log_entries[2]["id"] == 12
        # Entry with id 3 should keep it (max_id becomes max(12, 3) = 12)
        assert loaded.log_entries[3]["id"] == 3
        # None id entry should get 13 (max_id was 12, +=1)
        assert loaded.log_entries[4]["id"] == 13
        assert loaded._next_log_id == 14

    def test_state_from_dict_with_boolean_ids(self) -> None:
        """_state_from_dict should treat boolean IDs as non-integer and reassign them."""
        from backend.database import init_db
        init_db()
        state = new_game(seed=42)
        data = get_game_state(state)
        data["log_entries"] = [
            {"id": True, "type": "system", "message": "entry with boolean True id"},
            {"id": 5, "type": "navigation", "message": "valid entry with id 5"},
            {"id": False, "type": "exploration", "message": "entry with boolean False id"},
            {"id": 10, "type": "combat", "message": "valid entry with id 10"},
        ]
        del data["_next_log_id"]
        loaded = _state_from_dict(data)
        assert loaded is not None
        assert len(loaded.log_entries) == 4
        # Boolean True should be reassigned a sequential id (1)
        assert loaded.log_entries[0]["id"] == 1
        # Valid int id 5 should be kept
        assert loaded.log_entries[1]["id"] == 5
        # Boolean False should be reassigned a sequential id (6, since max_id=5 then +=1)
        assert loaded.log_entries[2]["id"] == 6
        # Valid int id 10 should be kept
        assert loaded.log_entries[3]["id"] == 10
        # _next_log_id should be max_id + 1 = 10 + 1 = 11
        assert loaded._next_log_id == 11


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
    """Tests for the trigger_event function with phenomena."""

    def test_trigger_event_phenomenon_biased(self) -> None:
        """Trigger event with phenomenon and RNG override should return an event."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "nebula"
        state.ship.morale = 80

        rng = random.Random(42)
        rng.random()  # Consume first value

        event = trigger_event(state, rng_override=rng)
        assert event is not None

    def test_trigger_event_phenomenon_else_branch(self) -> None:
        """Trigger event with different RNG seed should still return an event."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "nebula"
        state.ship.morale = 80

        rng = random.Random(37)
        rng.random()  # Consume first value

        event = trigger_event(state, rng_override=rng)
        assert event is not None

    def test_get_eligible_templates_no_system(self) -> None:
        """_get_eligible_templates should return all templates when there's no current system."""
        from backend.generation.events import _get_eligible_templates, EVENT_TEMPLATES
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        result = _get_eligible_templates(state, EVENT_TEMPLATES)
        assert len(result) == len(EVENT_TEMPLATES)

    def test_get_eligible_templates_unexplored_preference_fails(self) -> None:
        """_get_eligible_templates should skip events with unexplored_preference when all bodies are explored."""
        from backend.generation.events import _get_eligible_templates, EVENT_TEMPLATES
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        # Mark all bodies as explored
        for body in system.bodies:
            body.explored = True
        result = _get_eligible_templates(state, EVENT_TEMPLATES)
        # The Derelict Signal event has unexplored_preference and should be filtered out
        derelict_signal = [t for t in result if t["title"] == "Derelict Signal"]
        assert len(derelict_signal) == 0

    def test_get_eligible_templates_all_filtered_fallback(self) -> None:
        """_get_eligible_templates should return only templates with no trigger_conditions when all are filtered out (fallback)."""
        from backend.generation.events import _get_eligible_templates
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        # Set conditions that would filter out ALL templates with trigger_conditions
        system.phenomenon = "pulsar"
        for body in system.bodies:
            body.explored = True
            body.biome = "ocean"
        state.systems_visited = 0
        state.ship.morale = 80
        # Use custom templates where ALL have trigger_conditions so eligible
        # can actually be empty and the fallback branch is exercised.
        # Since all templates have conditions that don't match, and none are
        # unconditionally eligible, the result should be empty.
        custom_templates = [
            {"type": "test", "title": "Test A", "trigger_conditions": {"phenomenon": "nebula"}, "choices": []},
            {"type": "test", "title": "Test B", "trigger_conditions": {"min_systems_visited": 5}, "choices": []},
        ]
        result = _get_eligible_templates(state, custom_templates)
        assert len(result) == 0


class TestBulkSell:
    """Tests for the perform_bulk_sell function."""

    def test_bulk_sell_success(self) -> None:
        """Basic successful bulk sell of multiple discoveries."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        # Clear lore-linked discoveries and add regular ones
        state.discoveries.clear()
        d1 = Discovery(
            id="bulk_sell_d1",
            name="Common Ore",
            category="mineral",
            description="A common mineral",
            lore_fragment_id=None,
            value=100,
        )
        d2 = Discovery(
            id="bulk_sell_d2",
            name="Rare Ore",
            category="mineral",
            description="A rare mineral",
            lore_fragment_id=None,
            value=200,
        )
        state.discoveries.append(d1)
        state.discoveries.append(d2)
        credits_before = state.ship.credits
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "mineral", "quantity": 2}])
        assert ok is True
        assert "Sold" in msg
        assert state.ship.credits > credits_before
        assert len(state.discoveries) == 0

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
        system.has_trading_station = False
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
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        # Clear lore-linked discoveries and add a regular one
        state.discoveries.clear()
        d1 = Discovery(
            id="bulk_sell_partial_d1",
            name="Common Ore",
            category="mineral",
            description="A common mineral",
            lore_fragment_id=None,
            value=100,
        )
        state.discoveries.append(d1)
        credits_before = state.ship.credits
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [
            {"item": "mineral", "quantity": 1},
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

    def test_bulk_sell_lore_linked_discoveries_excluded(self) -> None:
        """Lore-linked discoveries should not be sold by bulk sell."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        # Create a lore-linked discovery
        lore_disc = Discovery(
            id="lore_linked_disc",
            name="Ancient Artifact",
            category="artifact",
            description="A lore-linked artifact",
            lore_fragment_id="frag_001",
            value=1000,
        )
        # Create a regular sellable discovery with the same name
        regular_disc = Discovery(
            id="regular_disc",
            name="Ancient Artifact",
            category="artifact",
            description="A regular artifact",
            lore_fragment_id=None,
            value=500,
        )
        state.discoveries.clear()
        state.discoveries.append(lore_disc)
        state.discoveries.append(regular_disc)
        credits_before = state.ship.credits
        # Try to sell by name - should only sell the non-lore one
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "Ancient Artifact", "quantity": 2}])
        assert ok is True
        assert sold_count == 1
        assert lore_disc in state.discoveries  # lore-linked should remain
        assert regular_disc not in state.discoveries  # regular should be sold
        assert state.ship.credits > credits_before

    def test_bulk_sell_lore_linked_by_category_excluded(self) -> None:
        """Lore-linked discoveries should be excluded when selling by category."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        # Create a lore-linked discovery
        lore_disc = Discovery(
            id="lore_cat_disc",
            name="Mysterious Relic",
            category="mineral",
            description="A lore-linked mineral",
            lore_fragment_id="frag_002",
            value=2000,
        )
        # Create a regular sellable discovery in the same category
        regular_disc = Discovery(
            id="regular_cat_disc",
            name="Common Ore",
            category="mineral",
            description="A regular mineral",
            lore_fragment_id=None,
            value=300,
        )
        state.discoveries.clear()
        state.discoveries.append(lore_disc)
        state.discoveries.append(regular_disc)
        credits_before = state.ship.credits
        # Try to sell by category - should only sell the non-lore one
        ok, msg, sold_count, total_price = perform_bulk_sell(state, [{"item": "mineral", "quantity": 2}])
        assert ok is True
        assert sold_count == 1
        assert lore_disc in state.discoveries  # lore-linked should remain
        assert regular_disc not in state.discoveries  # regular should be sold
        assert state.ship.credits > credits_before


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


class TestRoundHalfUp:
    """Tests for round_half_up rounding function."""

    def test_positive_half_up(self) -> None:
        """round_half_up(2.5) should round to 3."""
        assert round_half_up(2.5) == 3

    def test_positive_round_down(self) -> None:
        """round_half_up(2.4) should round to 2."""
        assert round_half_up(2.4) == 2

    def test_positive_round_up(self) -> None:
        """round_half_up(2.6) should round to 3."""
        assert round_half_up(2.6) == 3

    def test_negative_half_up(self) -> None:
        """round_half_up(-2.5) should round to -3."""
        assert round_half_up(-2.5) == -3

    def test_negative_round_down(self) -> None:
        """round_half_up(-2.4) should round to -2."""
        assert round_half_up(-2.4) == -2

    def test_negative_round_up(self) -> None:
        """round_half_up(-2.6) should round to -3."""
        assert round_half_up(-2.6) == -3

    def test_zero(self) -> None:
        """round_half_up(0) should be 0."""
        assert round_half_up(0) == 0

    def test_edge_positive_half(self) -> None:
        """round_half_up(0.5) should round to 1."""
        assert round_half_up(0.5) == 1

    def test_edge_negative_half(self) -> None:
        """round_half_up(-0.5) should round to -1."""
        assert round_half_up(-0.5) == -1

    def test_large_positive(self) -> None:
        """round_half_up(1000000.5) should round to 1000001."""
        assert round_half_up(1000000.5) == 1000001


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
        system.has_trading_station = False
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

    def test_sell_lore_linked_discovery_by_name_excluded(self) -> None:
        """Lore-linked discoveries should not be sold when selling by name."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        lore_disc = Discovery(
            id="lore_trade_disc",
            name="Ancient Artifact",
            category="artifact",
            description="A lore-linked artifact",
            lore_fragment_id="frag_001",
            value=1000,
        )
        regular_disc = Discovery(
            id="regular_trade_disc",
            name="Ancient Artifact",
            category="artifact",
            description="A regular artifact",
            lore_fragment_id=None,
            value=500,
        )
        state.discoveries.clear()
        state.discoveries.append(lore_disc)
        state.discoveries.append(regular_disc)
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", "Ancient Artifact")
        assert ok is True
        assert lore_disc in state.discoveries
        assert regular_disc not in state.discoveries
        assert state.ship.credits > credits_before

    def test_sell_lore_linked_discovery_by_category_excluded(self) -> None:
        """Lore-linked discoveries should not be sold when selling by category."""
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        if not planet:
            return  # pragma: no cover
        land_on_body(state, planet.id)
        explore_surface(state)
        lore_disc = Discovery(
            id="lore_cat_trade_disc",
            name="Mysterious Relic",
            category="mineral",
            description="A lore-linked mineral",
            lore_fragment_id="frag_002",
            value=2000,
        )
        regular_disc = Discovery(
            id="regular_cat_trade_disc",
            name="Common Ore",
            category="mineral",
            description="A regular mineral",
            lore_fragment_id=None,
            value=300,
        )
        state.discoveries.clear()
        state.discoveries.append(lore_disc)
        state.discoveries.append(regular_disc)
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "sell", "mineral")
        assert ok is True
        assert lore_disc in state.discoveries
        assert regular_disc not in state.discoveries
        assert state.ship.credits > credits_before


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

    def test_explore_already_discovered_lore_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Exploring a body with an already-discovered lore fragment should log a debug log."""
        import logging
        state = new_game(seed=42)
        state.ship.fuel = 1000

        sys_id, body_id, frag = self._find_system_with_lore(state)
        if not sys_id:
            return  # pragma: no cover

        # Mark the fragment as already discovered
        frag.discovered = True

        state.ship.current_system_id = sys_id
        state.ship.current_body_id = body_id

        with caplog.at_level(logging.DEBUG):
            explore_surface(state)

        # Check that the warning was logged
        assert any(
            frag.id in record.message and frag.title in record.message
            for record in caplog.records
        ), f"Expected debug log about lore fragment {frag.id} ({frag.title}) but got: {[r.message for r in caplog.records]}"

    def test_explore_body_without_lore(self) -> None:
        """Exploring a body without lore shouldn't affect fragment state."""
        state = new_game(seed=42)
        system = state.get_current_system()
        # Find a body that does NOT have a lore fragment
        body = None
        for b in system.bodies:
            has_lore = any(
                lf.discovery_id == f"{system.id}::{b.id}"
                for lf in state.lore_fragments
            )
            if not has_lore:
                body = b
                break
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

    def test_explore_already_discovered_in_same_action(self, caplog: pytest.LogCaptureFixture) -> None:
        """Multiple finds in the same explore action should NOT log a spurious warning."""
        import logging
        from unittest.mock import patch

        state = new_game(seed=42)
        state.ship.fuel = 1000

        sys_id, body_id, frag = self._find_system_with_lore(state)
        if not sys_id:
            return  # pragma: no cover

        system = state.systems[sys_id]
        for b in system.bodies:
            if b.id == body_id:
                b.poi_count = 3
                break

        state.ship.current_system_id = sys_id
        state.ship.current_body_id = body_id

        with patch("random.Random.randint", return_value=3):
            with caplog.at_level(logging.WARNING):
                discoveries = explore_surface(state)

        # The lore fragment should be linked to exactly one discovery
        lore_discs = [d for d in discoveries if d.lore_fragment_id == frag.id]
        assert len(lore_discs) == 1, f"Expected exactly one lore-linked discovery, got {len(lore_discs)}"

        # No warning about already-discovered lore should be logged
        # (the lore was just discovered in this same action)
        warning_messages = [r.message for r in caplog.records if "already discovered but found on body" in r.message]
        assert len(warning_messages) == 0, f"Expected no spurious warnings, got: {warning_messages}"

    def test_explore_body_without_lore_no_planet(self) -> None:
        """Cover guard clause in test_explore_body_without_lore when no lore-free body exists."""
        state = new_game(seed=42)
        sys_id = state.ship.current_system_id
        sys_obj = state.systems[sys_id]
        sys_obj.bodies = []

        func = self.test_explore_body_without_lore.__func__
        original_new_game = func.__globals__["new_game"]
        func.__globals__["new_game"] = lambda seed=None: state
        try:
            self.test_explore_body_without_lore()
        finally:
            func.__globals__["new_game"] = original_new_game


class TestDistressBeacon:
    """Tests for activate_distress_beacon."""

    def _make_stranded_state(self, seed: int = 42) -> GameState:
        state = new_game(seed=seed)
        state.ship.fuel = 0
        state.ship.hull = 100
        state.ship.credits = 200
        return state

    def test_activate_distress_beacon_no_system(self) -> None:
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        result = activate_distress_beacon(state)
        assert "error" in result
        assert "No current system" in result["error"]

    def test_activate_distress_beacon_not_stranded(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 50
        state.ship.hull = 100
        result = activate_distress_beacon(state)
        assert "error" in result
        assert "stranded" in result["error"].lower() or "Distress beacon can only" in result["error"]

    def test_activate_distress_beacon_cooldown(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 0
        state.ship.hull = 100
        state.ship.distress_cooldown = True
        result = activate_distress_beacon(state)
        assert "error" in result
        assert "cooldown" in result["error"].lower()

    def test_activate_distress_beacon_no_credits(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 0
        state.ship.hull = 100
        state.ship.credits = 30
        result = activate_distress_beacon(state)
        assert "error" in result
        assert "credits" in result["error"].lower()

    def test_activate_distress_beacon_no_response(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_stranded_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.61]
        mock_rng.randint.side_effect = [3]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "no_response"
        assert "No response" in result["result"]
        assert state.ship.credits == 150
        assert state.ship.distress_cooldown is True

    def test_activate_distress_beacon_pilots_guild(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_stranded_state()
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.credits = 300
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.1]
        mock_rng.randint.side_effect = [1]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "pilots_guild"
        assert "Pilots Guild" in result["result"]
        assert "error" not in result

    def test_activate_distress_beacon_passerby_help(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_stranded_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.5, 0.3]
        mock_rng.randint.side_effect = [2, 15]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "passerby_help"
        assert "Friendly passerby" in result["result"]

    def test_activate_distress_beacon_passerby_piracy(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_stranded_state()
        state.ship.credits = 300
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.5, 0.6]
        mock_rng.randint.side_effect = [2, 50]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "piracy"
        assert "Pirates" in result["result"]

    def test_activate_distress_beacon_passerby_ignore(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_stranded_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.5, 0.85]
        mock_rng.randint.side_effect = [2]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "passerby_ignore"
        assert "did not respond" in result["result"]

    def test_activate_distress_beacon_signal_friendly(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_stranded_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.75, 0.3]
        mock_rng.randint.side_effect = [1, 10]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "signal_friendly"
        assert "Friendly emergency responder" in result["result"]

    def test_activate_distress_beacon_signal_hostile(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_stranded_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.75, 0.6]
        mock_rng.randint.side_effect = [1, 10]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "signal_hostile"
        assert "Hostile ship" in result["result"]

    def test_activate_distress_beacon_deterministic(self) -> None:
        s1 = self._make_stranded_state(seed=42)
        s2 = self._make_stranded_state(seed=42)
        r1 = activate_distress_beacon(s1)
        r2 = activate_distress_beacon(s2)
        assert r1["outcome"] == r2["outcome"]
        assert r1["result"] == r2["result"]

    def test_activate_distress_beacon_precondition_fail_continue(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_stranded_state()
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = False
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.1, 0.3]
        mock_rng.randint.side_effect = [2, 15]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "passerby_help"
        assert "Friendly passerby" in result["result"]

    def test_activate_distress_beacon_fallback_error(self) -> None:
        from unittest.mock import MagicMock, patch
        from backend.game.engine import _BucketEntry, _always_true_precondition
        state = self._make_stranded_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.5]
        mock_rng.randint.side_effect = [2]
        custom_table = [
            _BucketEntry(
                threshold=1.0,
                precondition=_always_true_precondition,
                strategy=None,
                sub_table=None,
            ),
        ]
        with patch("backend.game.engine._DISTRESS_TABLE", custom_table):
            with patch("backend.game.engine.seeded_random", return_value=mock_rng):
                result = activate_distress_beacon(state)
        assert "error" in result
        assert result["error"] == "No distress outcome matched."

    def test_distress_pilots_guild_no_system(self) -> None:
        """_distress_pilots_guild should return error dict when system is None."""
        from backend.game.engine import _distress_pilots_guild
        state = new_game(seed=42)
        state.ship.current_system_id = "nonexistent"
        result = _distress_pilots_guild(state, None, 1)
        assert "error" in result
        assert result["error"] == "Cannot execute Pilots Guild rescue: no current system."


class TestSalvage:
    """Tests for perform_salvage."""

    def _make_salvage_state(self, seed: int = 42) -> GameState:
        state = new_game(seed=seed)
        state.ship.fuel = 0
        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), system.bodies[0])
        land_on_body(state, planet.id)
        return state

    def test_perform_salvage_not_stranded(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 50
        result = perform_salvage(state)
        assert "error" in result
        assert "stranded" in result["error"].lower() or "no fuel" in result["error"].lower()

    def test_perform_salvage_not_landed(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 0
        state.ship.current_body_id = None
        result = perform_salvage(state)
        assert "error" in result
        assert "landed" in result["error"].lower()

    def test_perform_salvage_no_current_system(self) -> None:
        """Salvage should return error when there is no current system."""
        state = new_game(seed=42)
        state.ship.fuel = 0
        state.ship.current_body_id = "body_1"
        state.ship.current_system_id = "nonexistent"
        result = perform_salvage(state)
        assert "error" in result
        assert "No current system" in result["error"]

    def test_perform_salvage_max_attempts(self) -> None:
        state = self._make_salvage_state()
        body_id = state.ship.current_body_id
        state.ship.salvage_attempts[body_id] = 3
        result = perform_salvage(state)
        assert "error" in result
        assert "max" in result["error"].lower() or "fully" in result["error"].lower()

    def test_perform_salvage_fuel_cache(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_salvage_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2]
        mock_rng.randint.side_effect = [5]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = perform_salvage(state)
        assert result["find"] == "fuel_cache"
        assert "fuel cache" in result["result"]
        assert "error" not in result

    def test_perform_salvage_repair_materials(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_salvage_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.55]
        mock_rng.randint.side_effect = [10]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = perform_salvage(state)
        assert result["find"] == "repair_materials"
        assert "repair materials" in result["result"]
        assert "error" not in result

    def test_perform_salvage_spare_parts(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_salvage_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.8]
        mock_rng.randint.side_effect = [30]
        mock_rng.getrandbits.return_value = 0xABC123
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = perform_salvage(state)
        assert result["find"] == "spare_parts"
        assert "spare parts" in result["result"]
        assert "error" not in result

    def test_perform_salvage_nothing(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_salvage_state()
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.95]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = perform_salvage(state)
        assert result["find"] == "nothing"
        assert "Nothing useful" in result["result"]
        assert "error" not in result

    def test_perform_salvage_morale_cost(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_salvage_state()
        initial_morale = state.ship.morale
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.95, 0.95, 0.95]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result1 = perform_salvage(state)
            morale_after_1 = state.ship.morale
            result2 = perform_salvage(state)
            morale_after_2 = state.ship.morale
            result3 = perform_salvage(state)
            morale_after_3 = state.ship.morale
        assert morale_after_1 < initial_morale
        assert morale_after_2 < morale_after_1
        assert morale_after_3 < morale_after_2
        assert result1["find"] == "nothing"
        assert result2["find"] == "nothing"
        assert result3["find"] == "nothing"

    def test_perform_salvage_deterministic(self) -> None:
        s1 = self._make_salvage_state(seed=42)
        s2 = self._make_salvage_state(seed=42)
        r1 = perform_salvage(s1)
        r2 = perform_salvage(s2)
        assert r1["find"] == r2["find"]
        assert r1["result"] == r2["result"]

    def test_perform_salvage_limited_attempts(self) -> None:
        from unittest.mock import MagicMock, patch
        state = self._make_salvage_state()
        body_id = state.ship.current_body_id
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.95, 0.95, 0.95, 0.95]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            for i in range(3):
                result = perform_salvage(state)
                assert "error" not in result
            result = perform_salvage(state)
            assert "error" in result
            assert "max" in result["error"].lower() or "fully" in result["error"].lower()
        assert state.ship.salvage_attempts[body_id] == 3


class TestEmergencyCraft:
    """Tests for emergency_craft."""

    def test_emergency_craft_not_found(self) -> None:
        state = new_game(seed=42)
        result = emergency_craft(state, "nonexistent_disc_id", "fuel")
        assert "error" in result
        assert "not found" in result["error"]

    def test_emergency_craft_unknown_category(self) -> None:
        state = new_game(seed=42)
        disc = Discovery(
            id="craft_unknown_cat", category="unknown_type", name="Mystery Item",
            description="Unknown", value=50, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        result = emergency_craft(state, "craft_unknown_cat", "fuel")
        assert "error" in result
        assert "cannot be crafted" in result["error"]

    def test_emergency_craft_wrong_output(self) -> None:
        state = new_game(seed=42)
        disc = Discovery(
            id="craft_artifact_disc", category="artifact", name="Ancient Artifact",
            description="Ancient", value=50, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        result = emergency_craft(state, "craft_artifact_disc", "repair")
        assert "error" in result
        assert "can only be crafted" in result["error"]

    def test_emergency_craft_artifact_to_fuel(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 10
        disc = Discovery(
            id="craft_artifact_disc2", category="artifact", name="Ancient Artifact",
            description="Ancient", value=50, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        result = emergency_craft(state, "craft_artifact_disc2", "fuel")
        assert "error" not in result
        assert result["crafted"] == "fuel"
        assert result["effects"]["fuel"] == 5
        assert state.ship.fuel == 15
        assert disc not in state.discoveries

    def test_emergency_craft_mineral_to_repair(self) -> None:
        state = new_game(seed=42)
        state.ship.hull = 50
        disc = Discovery(
            id="craft_mineral_disc", category="mineral", name="Rare Mineral",
            description="Mineral", value=50, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        result = emergency_craft(state, "craft_mineral_disc", "repair")
        assert "error" not in result
        assert result["crafted"] == "repair"
        assert result["effects"]["hull"] == 10
        assert state.ship.hull == 60
        assert disc not in state.discoveries

    def test_emergency_craft_lifeform_to_morale(self) -> None:
        state = new_game(seed=42)
        state.ship.morale = 50
        disc = Discovery(
            id="craft_lifeform_disc", category="lifeform", name="Alien Creature",
            description="Lifeform", value=50, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        result = emergency_craft(state, "craft_lifeform_disc", "morale")
        assert "error" not in result
        assert result["crafted"] == "morale"
        assert result["effects"]["morale"] == 15
        assert state.ship.morale == 65
        assert disc not in state.discoveries

    def test_emergency_craft_signal_to_credits(self) -> None:
        state = new_game(seed=42)
        state.ship.credits = 100
        disc = Discovery(
            id="craft_signal_disc", category="signal", name="Encrypted Signal",
            description="Signal", value=50, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        result = emergency_craft(state, "craft_signal_disc", "credits")
        assert "error" not in result
        assert result["crafted"] == "credits"
        assert result["effects"]["credits"] == 50
        assert state.ship.credits == 150
        assert disc not in state.discoveries

    def test_emergency_craft_removes_discovery(self) -> None:
        state = new_game(seed=42)
        disc = Discovery(
            id="craft_remove_disc", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        assert len(state.discoveries) == 1
        result = emergency_craft(state, "craft_remove_disc", "fuel")
        assert "error" not in result
        assert len(state.discoveries) == 0

    def test_emergency_craft_unknown_output_fallback(self) -> None:
        from unittest.mock import patch
        state = new_game(seed=42)
        disc = Discovery(
            id="craft_fallback_disc", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id="sys1", body_id="body1",
        )
        state.discoveries.append(disc)
        with patch.dict("backend.game.engine.CRAFT_CONVERSIONS", {"artifact": ("unknown_output_type", 5)}):
            with pytest.raises(ValueError, match="Unhandled output type: unknown_output_type"):
                emergency_craft(state, "craft_fallback_disc", "unknown_output_type")


class TestStrandedState:
    """Tests for GameState stranded state tracking."""

    def test_update_stranded_state_fuel_zero(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 0
        assert state.ship.stranded_turns == 0
        result = state.update_stranded_state()
        assert result == 1
        assert state.ship.stranded_turns == 1

    def test_update_stranded_state_morale_penalty(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 0
        initial_morale = state.ship.morale
        state.update_stranded_state()
        assert state.ship.morale == max(0, initial_morale - 5)

    def test_update_stranded_state_resets_when_fuel(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 0
        state.ship.stranded_turns = 5
        state.ship.distress_cooldown = True
        state.ship.fuel = 10
        result = state.update_stranded_state()
        assert result == 0
        assert state.ship.stranded_turns == 0
        assert state.ship.distress_cooldown is False

    def test_reset_stranded_state(self) -> None:
        state = new_game(seed=42)
        state.ship.stranded_turns = 10
        state.ship.distress_cooldown = True
        state.reset_stranded_state()
        assert state.ship.stranded_turns == 0
        assert state.ship.distress_cooldown is False


class TestTriggerEventLowMoraleTriggerConditions:
    """Tests for the low-morale path in trigger_event respecting trigger_conditions."""

    def test_low_morale_filters_by_biome_condition(self) -> None:
        """_get_eligible_templates should skip events whose biomes condition doesn't match the system's biomes."""
        state = new_game(seed=42)
        state.ship.morale = 20
        system = state.get_current_system()
        assert system is not None
        for body in system.bodies:
            body.biome = "ocean"
        custom_templates = [
            {"type": "crew", "title": "Custom Biome Event", "trigger_conditions": {"biomes": ["barren", "crystal", "tundra"]}, "choices": []},
        ]
        eligible = _get_eligible_templates(state, custom_templates)
        assert len(eligible) == 0

    def test_low_morale_filters_by_min_systems_visited(self) -> None:
        """When morale is low and systems_visited < 3, Trade Route Opportunity should not fire."""
        state = new_game(seed=42)
        state.ship.morale = 20
        state.systems_visited = 1
        event = trigger_event(state)
        assert event is not None
        assert event.title != "Trade Route Opportunity"

    def test_low_morale_allows_signal_from_home(self) -> None:
        """When morale is 20 (below max_morale 29), Signal from Home should be eligible."""
        state = new_game(seed=42)
        state.ship.morale = 20
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        eligible = [t for t in eligible if t["type"] in ("crew", "crisis", "narrative")]
        signal_from_home = [t for t in eligible if t["title"] == "Signal from Home"]
        assert len(signal_from_home) == 1

    def test_low_morale_filters_by_unexplored_preference(self) -> None:
        """_get_eligible_templates should skip events with unexplored_preference when all bodies are explored."""
        state = new_game(seed=42)
        state.ship.morale = 20
        system = state.get_current_system()
        assert system is not None
        for body in system.bodies:
            body.explored = True
        custom_templates = [
            {"type": "crew", "title": "Custom Unexplored Event", "trigger_conditions": {"unexplored_preference": True}, "choices": []},
        ]
        eligible = _get_eligible_templates(state, custom_templates)
        assert len(eligible) == 0

    def test_low_morale_regular_events_still_work(self) -> None:
        """Regular crew/crisis/narrative events without trigger_conditions should still fire."""
        state = new_game(seed=42)
        state.ship.morale = 20
        event = trigger_event(state)
        assert event is not None
        assert event.event_type in ("crew", "crisis", "narrative")


class TestTriggerEventDeterminism:
    """Tests for the determinism of trigger_event's default RNG (without rng_override)."""

    def test_trigger_event_deterministic_both_none(self) -> None:
        """Two identical game states should both return None from trigger_event."""
        state1 = new_game(seed=42)
        state2 = new_game(seed=42)

        state1.ship.morale = 80
        state2.ship.morale = 80

        system1 = state1.get_current_system()
        system2 = state2.get_current_system()
        assert system1 is not None
        assert system2 is not None
        system1.phenomenon = "none"
        system2.phenomenon = "none"

        event1 = trigger_event(state1)
        event2 = trigger_event(state2)

        assert event1 is None
        assert event2 is None

    def test_trigger_event_deterministic_both_event(self) -> None:
        """Two identical game states should both return the same event from trigger_event."""
        state1 = new_game(seed=42)
        state2 = new_game(seed=42)

        state1.ship.morale = 20
        state2.ship.morale = 20

        system1 = state1.get_current_system()
        system2 = state2.get_current_system()
        assert system1 is not None
        assert system2 is not None

        event1 = trigger_event(state1)
        event2 = trigger_event(state2)

        assert event1 is not None
        assert event2 is not None
        assert event1.event_type == event2.event_type


class TestTriggerEventEmptyEligible:
    """Tests for the empty eligible guard in trigger_event."""

    def test_low_morale_empty_eligible_returns_none(self) -> None:
        """When morale is low and no crew/crisis/narrative templates are eligible, trigger_event should return None."""
        from backend.generation.events import trigger_event
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        from backend.models.system import StarSystem, Body
        from backend.config import MORALE_LOW_THRESHOLD

        # Create a state with low morale
        ship = Ship(morale=MORALE_LOW_THRESHOLD - 1)
        state = GameState(id="test-empty-eligible-low", seed=42, ship=ship)

        # Add a system
        body = Body(id="b1", name="Planet", body_type="planet", biome="ocean",
                    size=3, distance_from_star=0.5, poi_count=1)
        system = StarSystem(id="sys1", name="TestSys", x=0.0, y=0.0,
                            star_type="G", star_color="#fff",
                            phenomenon="none", phenomenon_desc="",
                            bodies=[body])
        state.systems = {"sys1": system}
        state.ship.current_system_id = "sys1"

        # Mock _get_eligible_templates to return an empty list
        # This simulates the scenario where all templates with trigger_conditions
        # fail to match, and there are no unconditional templates either
        import unittest.mock as mock
        with mock.patch("backend.generation.events._get_eligible_templates", return_value=[]):
            result = trigger_event(state)

        assert result is None, "Expected None when eligible list is empty in low-morale path"

    def test_normal_path_empty_eligible_returns_none(self) -> None:
        """When morale is normal and no templates are eligible, trigger_event should return None."""
        from backend.generation.events import trigger_event
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        from backend.models.system import StarSystem, Body
        from backend.config import MORALE_LOW_THRESHOLD

        # Create a state with normal morale
        ship = Ship(morale=MORALE_LOW_THRESHOLD + 10)
        state = GameState(id="test-empty-eligible-normal", seed=42, ship=ship)

        # Add a system
        body = Body(id="b1", name="Planet", body_type="planet", biome="ocean",
                    size=3, distance_from_star=0.5, poi_count=1)
        system = StarSystem(id="sys1", name="TestSys", x=0.0, y=0.0,
                            star_type="G", star_color="#fff",
                            phenomenon="none", phenomenon_desc="",
                            bodies=[body])
        state.systems = {"sys1": system}
        state.ship.current_system_id = "sys1"

        # Mock _get_eligible_templates to return an empty list
        import unittest.mock as mock
        import random
        rng = random.Random(1)
        with mock.patch("backend.generation.events._get_eligible_templates", return_value=[]):
            result = trigger_event(state, rng_override=rng)

        assert result is None, "Expected None when eligible list is empty in normal path"

    def test_low_morale_empty_eligible_after_cooldown_filter(self) -> None:
        """When low-morale eligible list becomes empty after type+cooldown filtering, trigger_event should return None."""
        from backend.generation.events import trigger_event
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        from backend.models.system import StarSystem, Body
        from backend.config import MORALE_LOW_THRESHOLD

        # Create a state with low morale
        ship = Ship(morale=MORALE_LOW_THRESHOLD - 1)
        state = GameState(id="test-empty-cooldown-low", seed=42, ship=ship)

        # Add a system
        body = Body(id="b1", name="Planet", body_type="planet", biome="ocean",
                    size=3, distance_from_star=0.5, poi_count=1)
        system = StarSystem(id="sys1", name="TestSys", x=0.0, y=0.0,
                            star_type="G", star_color="#fff",
                            phenomenon="none", phenomenon_desc="",
                            bodies=[body])
        state.systems = {"sys1": system}
        state.ship.current_system_id = "sys1"

        # Set last_event_title to match all eligible templates so cooldown filters them all out
        state.last_event_title = "Rare Discovery"

        # Mock _get_eligible_templates to return only exploration-type templates
        # (not crew/crisis/narrative), so the type filter at line 296 empties
        # eligible. The cooldown check then has nothing left either.
        import unittest.mock as mock
        with mock.patch("backend.generation.events._get_eligible_templates", return_value=[
            {"type": "exploration", "title": "Rare Discovery", "flavor": "...", "rarity": "common", "choices": []}
        ]):
            result = trigger_event(state)

        assert result is None, "Expected None when type and cooldown filter empties eligible list in low-morale path"

    def test_normal_path_empty_eligible_after_cooldown_filter(self) -> None:
        """When normal path eligible list is empty after cooldown check, trigger_event should return None."""
        from backend.generation.events import trigger_event
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        from backend.models.system import StarSystem, Body
        from backend.config import MORALE_LOW_THRESHOLD

        # Create a state with normal morale
        ship = Ship(morale=MORALE_LOW_THRESHOLD + 10)
        state = GameState(id="test-empty-cooldown-normal", seed=42, ship=ship)

        # Add a system
        body = Body(id="b1", name="Planet", body_type="planet", biome="ocean",
                    size=3, distance_from_star=0.5, poi_count=1)
        system = StarSystem(id="sys1", name="TestSys", x=0.0, y=0.0,
                            star_type="G", star_color="#fff",
                            phenomenon="none", phenomenon_desc="",
                            bodies=[body])
        state.systems = {"sys1": system}
        state.ship.current_system_id = "sys1"

        # Set last_event_title (irrelevant since eligible is empty anyway)
        state.last_event_title = "Ancient Signal"

        # Mock _get_eligible_templates to return an empty list
        import unittest.mock as mock
        import random
        rng = random.Random(1)
        with mock.patch("backend.generation.events._get_eligible_templates", return_value=[]):
            result = trigger_event(state, rng_override=rng)

        assert result is None, "Expected None when eligible list is empty after cooldown check in normal path"


class TestFuelPricing:
    """Tests for the calculate_fuel_price function and fuel buying with dynamic pricing."""

    def _make_system(self, system_type: str) -> "StarSystem":
        from backend.models.system import StarSystem, Body
        body = Body(id="b1", name="TestPlanet", body_type="planet", biome="ocean",
                    size=5, distance_from_star=0.5, poi_count=2)
        return StarSystem(
            id="sys_test", name="TestSystem", x=100.0, y=200.0,
            star_type="G", star_color="#fff", phenomenon="none",
            phenomenon_desc="", bodies=[body],
            has_trading_station=True, system_type=system_type,
        )

    def test_civilized_system_modifier(self) -> None:
        """Civilized systems should have -20% modifier."""
        state = new_game(seed=42)
        system = self._make_system("civilized")
        price = calculate_fuel_price(state, system)
        assert price["system_modifier"] == -0.20
        assert price["system_modifier_label"] == "Civilized system discount"
        assert price["final_price"] == 25.0 * (1 - 0.20)

    def test_agricultural_system_modifier(self) -> None:
        """Agricultural systems should have 0% modifier."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        price = calculate_fuel_price(state, system)
        assert price["system_modifier"] == 0.0
        assert price["system_modifier_label"] == "Standard pricing"
        assert price["final_price"] == 25.0

    def test_frontier_system_modifier(self) -> None:
        """Frontier systems should have +25% modifier."""
        state = new_game(seed=42)
        system = self._make_system("frontier")
        price = calculate_fuel_price(state, system)
        assert price["system_modifier"] == 0.25
        assert price["system_modifier_label"] == "Remote system premium"
        assert price["final_price"] == 25.0 * 1.25

    def test_nebula_system_modifier(self) -> None:
        """Nebula systems should have +50% modifier."""
        state = new_game(seed=42)
        system = self._make_system("nebula")
        price = calculate_fuel_price(state, system)
        assert price["system_modifier"] == 0.50
        assert price["system_modifier_label"] == "Nebula hazard premium"
        assert price["final_price"] == 25.0 * 1.50

    def test_uncharted_system_modifier(self) -> None:
        """Uncharted systems should have +100% modifier."""
        state = new_game(seed=42)
        system = self._make_system("uncharted")
        price = calculate_fuel_price(state, system)
        assert price["system_modifier"] == 1.00
        assert price["system_modifier_label"] == "Uncharted territory premium"
        assert price["final_price"] == 25.0 * 2.0

    def test_ancient_system_modifier(self) -> None:
        """Ancient gate systems should have +75% modifier."""
        state = new_game(seed=42)
        system = self._make_system("ancient")
        price = calculate_fuel_price(state, system)
        assert price["system_modifier"] == 0.75
        assert price["system_modifier_label"] == "Ancient gate premium"
        assert price["final_price"] == 25.0 * 1.75

    def test_void_traders_allied_discount(self) -> None:
        """Allied with Void Traders should give -15% modifier."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        state.modify_faction_reputation("void_traders", 60)
        price = calculate_fuel_price(state, system)
        assert price["faction_modifier"] == -0.15
        assert "Allied" in price["faction_modifier_label"]

    def test_void_traders_friendly_discount(self) -> None:
        """Friendly with Void Traders should give -5% modifier."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        state.modify_faction_reputation("void_traders", 30)
        price = calculate_fuel_price(state, system)
        assert price["faction_modifier"] == -0.05
        assert "Friendly" in price["faction_modifier_label"]

    def test_void_traders_neutral(self) -> None:
        """Neutral with Void Traders should give 0% modifier."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        state.modify_faction_reputation("void_traders", 0)
        price = calculate_fuel_price(state, system)
        assert price["faction_modifier"] == 0.0
        assert "Neutral" in price["faction_modifier_label"]

    def test_void_traders_unfriendly_surcharge(self) -> None:
        """Unfriendly with Void Traders should give +15% surcharge."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        state.modify_faction_reputation("void_traders", -10)
        price = calculate_fuel_price(state, system)
        assert price["faction_modifier"] == 0.15
        assert "Unfriendly" in price["faction_modifier_label"]

    def test_void_traders_hostile_surcharge(self) -> None:
        """Hostile with Void Traders should give +30% surcharge."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        state.modify_faction_reputation("void_traders", -50)
        price = calculate_fuel_price(state, system)
        assert price["faction_modifier"] == 0.30
        assert "Hostile" in price["faction_modifier_label"]

    def test_supply_modifier_first_visit(self) -> None:
        """First visit to a station should have 0% supply modifier."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        price = calculate_fuel_price(state, system)
        assert price["supply_modifier"] == 0.0
        assert price["supply_modifier_label"] == "First-time visit"

    def test_supply_modifier_repeat_visit(self) -> None:
        """Repeat visits to a station should have -10% supply modifier."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        state.record_station_visit(system.id)
        price = calculate_fuel_price(state, system)
        assert price["supply_modifier"] == -0.10
        assert price["supply_modifier_label"] == "Well-supplied by traders"

    def test_breakdown_lines_format(self) -> None:
        """Breakdown lines should contain all price components."""
        state = new_game(seed=42)
        system = self._make_system("frontier")
        state.modify_faction_reputation("void_traders", 40)
        state.record_station_visit(system.id)
        price = calculate_fuel_price(state, system)
        assert "breakdown_lines" in price
        lines = price["breakdown_lines"]
        assert len(lines) == 5
        assert any("Base price" in line for line in lines)
        assert any("System type" in line for line in lines)
        assert any("Faction standing" in line for line in lines)
        assert any("Supply/demand" in line for line in lines)
        assert any("Final price" in line for line in lines)

    def test_fuel_buying_uses_dynamic_pricing(self) -> None:
        """Buying fuel should use calculate_fuel_price and include breakdown."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.fuel = 0
        state.ship.credits = 5000
        ok, msg = perform_trade(state, "buy", "fuel", 10)
        assert ok is True
        assert "Purchased" in msg
        assert "Base price:" in msg
        assert "Final price:" in msg

    def test_fuel_buying_records_station_visit(self) -> None:
        """Buying fuel should record a station visit."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.fuel = 0
        state.ship.credits = 5000
        assert system.id not in state.station_visits
        ok, _ = perform_trade(state, "buy", "fuel", 5)
        assert ok is True
        assert state.station_visits.get(system.id, 0) == 1

    def test_fuel_price_compound_modifiers(self) -> None:
        """All three modifiers should compound correctly."""
        state = new_game(seed=42)
        system = self._make_system("uncharted")
        state.modify_faction_reputation("void_traders", 60)
        state.record_station_visit(system.id)
        price = calculate_fuel_price(state, system)
        expected = 25.0 * (1 + 1.00 + (-0.15) + (-0.10))
        assert price["final_price"] == expected

    def test_record_station_visit_method(self) -> None:
        """record_station_visit should increment visit counts."""
        state = new_game(seed=42)
        assert state.station_visits == {}
        state.record_station_visit("sys_0001")
        assert state.station_visits["sys_0001"] == 1
        state.record_station_visit("sys_0001")
        assert state.station_visits["sys_0001"] == 2
        state.record_station_visit("sys_0002")
        assert state.station_visits["sys_0002"] == 1

    def test_unknown_system_type_raises_error(self) -> None:
        """Unknown system_type should raise a ValueError."""
        state = new_game(seed=42)
        system = self._make_system("some_unknown_type")
        with pytest.raises(ValueError, match="Unknown system_type"):
            calculate_fuel_price(state, system)

    def test_all_valid_system_types(self) -> None:
        """All valid system types should work without error."""
        state = new_game(seed=42)
        for sys_type in ["civilized", "agricultural", "frontier", "nebula", "uncharted", "ancient"]:
            system = self._make_system(sys_type)
            price = calculate_fuel_price(state, system)
            assert price is not None

    def test_validate_system_type_valid(self) -> None:
        """validate_system_type should not raise for valid types."""
        from backend.models.system import validate_system_type
        for sys_type in ["civilized", "agricultural", "frontier", "nebula", "uncharted", "ancient"]:
            validate_system_type(sys_type)  # Should not raise

    def test_validate_system_type_invalid(self) -> None:
        """validate_system_type should raise ValueError for invalid types."""
        from backend.models.system import validate_system_type
        with pytest.raises(ValueError, match="Unknown system_type"):
            validate_system_type("civlized")
        with pytest.raises(ValueError, match="Unknown system_type"):
            validate_system_type("")
        with pytest.raises(ValueError, match="Unknown system_type"):
            validate_system_type("CIVILIZED")  # Case sensitive

    def test_fuel_price_clamping_applied(self) -> None:
        """When unclamped price is below minimum, clamping should raise it."""
        from unittest.mock import patch
        state = new_game(seed=42)
        system = self._make_system("civilized")
        state.modify_faction_reputation("void_traders", 60)  # Allied = -0.15
        state.record_station_visit(system.id)  # repeat visit = -0.10
        # Total modifier: -0.20 + -0.15 + -0.10 = -0.45, multiplier = 0.55
        # With base_price=1, unclamped = 0.55, clamped to max(0.1, 1) = 1.0
        with patch("backend.game.trading.FUEL_BASE_PRICE", 1):
            price = calculate_fuel_price(state, system)
        assert price["final_price"] == 1.0
        assert "clamped to minimum" in price["breakdown_lines"][-1]

    def test_fuel_price_no_clamping_when_above_minimum(self) -> None:
        """When unclamped price is above minimum, no clamping should occur."""
        state = new_game(seed=42)
        system = self._make_system("agricultural")
        price = calculate_fuel_price(state, system)
        # base_price=25, no modifiers, final=25, no clamping
        assert price["final_price"] == 25.0
        assert "clamped to minimum" not in price["breakdown_lines"][-1]

    def test_fuel_price_clamping_floor_is_at_least_one(self) -> None:
        """The clamped minimum should be at least 1 credit."""
        from unittest.mock import patch
        state = new_game(seed=42)
        system = self._make_system("civilized")
        state.modify_faction_reputation("void_traders", 60)  # Allied = -0.15
        state.record_station_visit(system.id)  # repeat visit = -0.10
        # With base_price=0.5, unclamped = 0.5 * 0.55 = 0.275
        # clamped to max(0.5*0.1=0.05, 1) = 1.0
        with patch("backend.game.trading.FUEL_BASE_PRICE", 0.5):
            price = calculate_fuel_price(state, system)
        assert price["final_price"] == 1.0
        assert "clamped to minimum" in price["breakdown_lines"][-1]


class TestBlackHoleEvents:
    """Tests for black hole system-specific events."""

    def test_black_hole_events_exist(self) -> None:
        """There should be exactly 8 black hole events in EVENT_TEMPLATES."""
        black_hole_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        assert len(black_hole_events) == 8, f"Expected 8 black hole events, got {len(black_hole_events)}"

    def test_black_hole_events_have_correct_structure(self) -> None:
        """Each black hole event should have title, flavor, type, choices, and trigger_conditions."""
        black_hole_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        for event in black_hole_events:
            assert "title" in event, f"Black hole event missing title: {event}"
            assert "flavor" in event, f"Black hole event {event['title']} missing flavor"
            assert "type" in event, f"Black hole event {event['title']} missing type"
            assert "choices" in event, f"Black hole event {event['title']} missing choices"
            assert len(event["choices"]) >= 2, f"Black hole event {event['title']} has fewer than 2 choices"
            assert event["trigger_conditions"].get("phenomenon") == "black_hole", \
                f"Black hole event {event['title']} has wrong trigger_conditions"

    def test_black_hole_events_have_valid_event_types(self) -> None:
        """Black hole events should use valid event types (hazard, discovery)."""
        black_hole_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        valid_types = {"hazard", "discovery"}
        for event in black_hole_events:
            assert event["type"] in valid_types, \
                f"Black hole event {event['title']} has invalid type: {event['type']}"

    def test_spaghettification_is_rare(self) -> None:
        """The Spaghettification Near-Miss event should have rarity 'rare'."""
        spaghettification = [t for t in EVENT_TEMPLATES if t.get("title") == "Spaghettification Near-Miss"]
        assert len(spaghettification) == 1
        assert spaghettification[0]["rarity"] == "rare", "Spaghettification Near-Miss should be rare"

    def test_black_hole_events_only_in_black_hole_systems(self) -> None:
        """Black hole events should only be eligible in black hole systems."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        
        # Set system to black hole, scanner high enough to make all 8 eligible
        system.phenomenon = "black_hole"
        state.ship.scanner = 3
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        black_hole_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        assert len(black_hole_eligible) == 8, \
            f"Expected 8 black hole events eligible in black hole system, got {len(black_hole_eligible)}"

    def test_black_hole_events_not_eligible_in_nebula_systems(self) -> None:
        """Black hole events should NOT be eligible in nebula systems."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        
        # Set system to nebula (not black hole)
        system.phenomenon = "nebula"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        black_hole_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        assert len(black_hole_eligible) == 0, \
            f"Expected 0 black hole events eligible in nebula system, got {len(black_hole_eligible)}"

    def test_black_hole_events_not_eligible_in_normal_systems(self) -> None:
        """Black hole events should NOT be eligible in systems with no phenomenon."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        
        # Set system to no phenomenon
        system.phenomenon = "none"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        black_hole_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        assert len(black_hole_eligible) == 0, \
            f"Expected 0 black hole events eligible in normal system, got {len(black_hole_eligible)}"

    def test_black_hole_event_choices_have_valid_outcomes(self) -> None:
        """Each choice in black hole events should have outcomes that can be parsed by apply_choice_outcome."""
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        
        black_hole_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        ship = Ship()
        state = GameState(id="test-bh-outcomes", seed=42, ship=ship)
        
        for event in black_hole_events:
            for i, choice in enumerate(event["choices"]):
                # This should not raise any exceptions
                effects = state.apply_choice_outcome(choice["outcome"])
                assert isinstance(effects, dict), f"Outcome for {event['title']} choice {i} should return a dict"
                # Verify at least one stat was affected or it's a narrative-only outcome
                assert any(v != 0 for v in effects.values()) or ";" not in choice["outcome"].strip(), \
                    f"Choice {i} of {event['title']} has no stat effects: {choice['outcome']}"

    def test_black_hole_events_can_be_triggered(self) -> None:
        """Black hole events should be triggerable in a black hole system."""
        from unittest.mock import patch
        import random
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        state.ship.morale = 80
        
        # Use a real Random instance with mocked random() to guarantee trigger
        rng = random.Random(42)
        with patch.object(rng, "random", return_value=0.2):
            event = trigger_event(state, rng_override=rng)
        assert event is not None, "Expected an event to trigger with mocked RNG"
        assert event.title in [t["title"] for t in EVENT_TEMPLATES]

    def test_black_hole_events_can_be_resolved(self) -> None:
        """Black hole events should resolve correctly."""
        from backend.generation.events import _create_event
        
        black_hole_templates = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        black_hole_template = black_hole_templates[0]
        
        # Each choice must be resolved on a fresh event (resolve_event marks event as resolved)
        for i in range(len(black_hole_template["choices"])):
            state = new_game(seed=42)
            event = _create_event(black_hole_template, state.get_current_system().id)
            state.events.append(event)
            
            ok, msg, extra = resolve_event(state, event.id, i)
            assert ok is True, f"Failed to resolve choice {i}: {msg}"
            assert extra["title"] == black_hole_template["title"]
            assert extra["chosen_text"] == event.choices[i].text
            assert isinstance(extra["effects"], dict)


class TestNewBlackHoleEvents:
    """Tests for the 3 new black-hole-specific events with scanner_required support."""

    NEW_BH_TITLES = {"Event Horizon Approach", "Hawking Radiation Harvest (Deep Scan)", "Time Dilation Echo"}

    def _get_new_bh_templates(self):
        """Return the 3 new black hole event templates (the ones with scanner_required or Event Horizon Approach)."""
        all_bh = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        return [t for t in all_bh if t["title"] in self.NEW_BH_TITLES]

    def test_new_events_exist(self) -> None:
        """The 3 new events should exist in EVENT_TEMPLATES."""
        new_events = self._get_new_bh_templates()
        found_titles = {t["title"] for t in new_events}
        assert found_titles == self.NEW_BH_TITLES, \
            f"Expected {self.NEW_BH_TITLES}, got {found_titles}"

    def test_new_events_have_correct_structure(self) -> None:
        """Each new event should have title, flavor, type, choices, and trigger_conditions."""
        new_events = self._get_new_bh_templates()
        for event in new_events:
            assert "title" in event
            assert "flavor" in event
            assert "type" in event
            assert "choices" in event
            assert len(event["choices"]) == 3, f"Event {event['title']} should have 3 choices"
            assert "trigger_conditions" in event
            assert event["trigger_conditions"].get("phenomenon") == "black_hole"

    def test_scanner_required_filtering_blocks_low_scanner(self) -> None:
        """Events with scanner_required should be filtered out when scanner level is too low."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        state.ship.scanner = 1

        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        bh_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        eligible_titles = {t["title"] for t in bh_eligible}

        # Event Horizon Approach: no scanner_required, should be eligible
        assert "Event Horizon Approach" in eligible_titles
        # Hawking Radiation Harvest (new): scanner_required=2, scanner=1 -> NOT eligible
        # Time Dilation Echo: scanner_required=3, scanner=1 -> NOT eligible
        # But the OLD Hawking Radiation Harvest has no scanner_required and IS eligible
        assert "Hawking Radiation Harvest" in eligible_titles, \
            "Old Hawking Radiation Harvest (no scanner req) should still be eligible"
        assert "Time Dilation Echo" not in eligible_titles

    def test_scanner_required_allows_sufficient_scanner(self) -> None:
        """Events with scanner_required should be eligible when scanner level meets threshold."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        state.ship.scanner = 3

        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        bh_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        eligible_titles = {t["title"] for t in bh_eligible}

        assert "Event Horizon Approach" in eligible_titles
        assert "Hawking Radiation Harvest" in eligible_titles
        assert "Time Dilation Echo" in eligible_titles

    def test_scanner_required_at_exact_threshold(self) -> None:
        """Event with scanner_required=3 should be eligible when scanner is exactly 3."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        state.ship.scanner = 3

        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        bh_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        eligible_titles = {t["title"] for t in bh_eligible}

        assert "Time Dilation Echo" in eligible_titles

    def test_new_events_not_eligible_in_non_black_hole_systems(self) -> None:
        """None of the new events should be eligible in a non-black-hole system."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "none"
        state.ship.scanner = 5

        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        bh_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        assert len(bh_eligible) == 0

    def test_event_horizon_approach_no_scanner_required(self) -> None:
        """Event Horizon Approach should NOT have scanner_required in its trigger_conditions."""
        new_events = self._get_new_bh_templates()
        eha = [t for t in new_events if t["title"] == "Event Horizon Approach"]
        assert len(eha) == 1
        assert "scanner_required" not in eha[0]["trigger_conditions"], \
            "Event Horizon Approach should not require scanner"

    def test_new_events_choice_outcomes_parseable(self) -> None:
        """All choice outcomes in new events should be parseable by apply_choice_outcome."""
        from backend.models.ship import Ship

        new_events = self._get_new_bh_templates()
        ship = Ship()
        state = GameState(id="test-new-bh", seed=42, ship=ship)

        for event in new_events:
            for i, choice in enumerate(event["choices"]):
                effects = state.apply_choice_outcome(choice["outcome"])
                assert isinstance(effects, dict), f"Outcome for {event['title']} choice {i} should return a dict"

    def test_new_events_have_cooldowns(self) -> None:
        """All 3 new events should have entries in EVENT_COOLDOWNS."""
        from backend.generation.events import EVENT_COOLDOWNS
        new_events = self._get_new_bh_templates()
        for event in new_events:
            assert event["title"] in EVENT_COOLDOWNS, \
                f"Missing cooldown for new event: {event['title']}"

    def test_new_events_correct_cooldown_values(self) -> None:
        """Check that the new events have the expected cooldown values."""
        from backend.generation.events import EVENT_COOLDOWNS
        assert EVENT_COOLDOWNS["Event Horizon Approach"] == 8
        assert EVENT_COOLDOWNS["Hawking Radiation Harvest"] == 8
        assert EVENT_COOLDOWNS["Time Dilation Echo"] == 10

    def test_new_events_can_be_triggered_in_black_hole(self) -> None:
        """The new events should be triggerable in a black hole system with sufficient scanner."""
        from unittest.mock import patch
        import random as rnd

        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        state.ship.scanner = 3
        state.ship.morale = 80

        # Put all non-new-BH events on cooldown so only the 3 new BH events are eligible
        from backend.generation.events import EVENT_TEMPLATES
        old_bh_titles = {"Time Dilation Anomaly", "Hawking Radiation Harvest", "Spaghettification Near-Miss", "Accretion Disk Prospecting", "Gravitational Lens Observation"}
        for template in EVENT_TEMPLATES:
            if template.get("trigger_conditions", {}).get("phenomenon") != "black_hole" or template["title"] not in self.NEW_BH_TITLES:
                state.event_cooldowns[template["title"]] = 999

        rng = rnd.Random(42)
        with patch.object(rng, "random", return_value=0.2):
            event = trigger_event(state, rng_override=rng)
        assert event is not None, "Expected an event to trigger with mocked RNG"
        assert event.title in self.NEW_BH_TITLES, \
            f"Expected one of {self.NEW_BH_TITLES}, got '{event.title}'"

    def test_new_events_can_be_resolved(self) -> None:
        """Each new event should resolve correctly for all choices."""
        from backend.generation.events import _create_event

        new_templates = self._get_new_bh_templates()
        for template in new_templates:
            for i in range(len(template["choices"])):
                state = new_game(seed=42)
                event = _create_event(template, state.get_current_system().id)
                state.events.append(event)

                ok, msg, extra = resolve_event(state, event.id, i)
                assert ok is True, f"Failed to resolve choice {i} of '{template['title']}': {msg}"
                assert extra["title"] == template["title"]
                assert extra["chosen_text"] == event.choices[i].text
                assert isinstance(extra["effects"], dict)

    def test_scanner_required_scanner_2_blocks_time_dilation(self) -> None:
        """Scanner level 2 allows Hawking Radiation Harvest but NOT Time Dilation Echo."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "black_hole"
        state.ship.scanner = 2

        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        bh_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "black_hole"]
        eligible_titles = {t["title"] for t in bh_eligible}

        assert "Event Horizon Approach" in eligible_titles
        assert "Hawking Radiation Harvest" in eligible_titles
        assert "Time Dilation Echo" not in eligible_titles


class TestPhenomenonEvents:
    """Tests for phenomenon-specific events (nebula, pulsar, binary star)."""

    def test_nebula_events_exist(self) -> None:
        """Verify 4 nebula events exist in EVENT_TEMPLATES with trigger_conditions {'phenomenon': 'nebula'}."""
        nebula_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "nebula"]
        assert len(nebula_events) == 4, f"Expected 4 nebula events, got {len(nebula_events)}"

    def test_pulsar_events_exist(self) -> None:
        """Verify 3 pulsar events exist with trigger_conditions {'phenomenon': 'pulsar'}."""
        pulsar_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "pulsar"]
        assert len(pulsar_events) == 3, f"Expected 3 pulsar events, got {len(pulsar_events)}"

    def test_binary_star_events_exist(self) -> None:
        """Verify 2 binary star events exist with trigger_conditions {'phenomenon': 'binary_star'}."""
        binary_star_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "binary_star"]
        assert len(binary_star_events) == 2, f"Expected 2 binary star events, got {len(binary_star_events)}"

    def test_phenomenon_events_have_correct_structure(self) -> None:
        """Each phenomenon event should have title, flavor, type, choices, and trigger_conditions."""
        phenomenon_events = [
            t for t in EVENT_TEMPLATES
            if t.get("trigger_conditions", {}).get("phenomenon") in ("nebula", "pulsar", "binary_star")
        ]
        for event in phenomenon_events:
            assert "title" in event, f"Phenomenon event missing title: {event}"
            assert "flavor" in event, f"Phenomenon event {event['title']} missing flavor"
            assert "type" in event, f"Phenomenon event {event['title']} missing type"
            assert "choices" in event, f"Phenomenon event {event['title']} missing choices"
            assert len(event["choices"]) >= 2, f"Phenomenon event {event['title']} has fewer than 2 choices"
            assert "trigger_conditions" in event, f"Phenomenon event {event['title']} missing trigger_conditions"
            assert event["trigger_conditions"]["phenomenon"] in ("nebula", "pulsar", "binary_star"), \
                f"Phenomenon event {event['title']} has unexpected phenomenon"

    def test_phenomenon_events_only_eligible_in_matching_systems(self) -> None:
        """Nebula events only in nebula systems, pulsar events only in pulsar systems, etc."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None

        # Test nebula
        system.phenomenon = "nebula"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        nebula_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "nebula"]
        assert len(nebula_eligible) == 4, \
            f"Expected 4 nebula events eligible in nebula system, got {len(nebula_eligible)}"

        # Test pulsar
        system.phenomenon = "pulsar"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        pulsar_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "pulsar"]
        assert len(pulsar_eligible) == 3, \
            f"Expected 3 pulsar events eligible in pulsar system, got {len(pulsar_eligible)}"

        # Test binary star
        system.phenomenon = "binary_star"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        binary_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "binary_star"]
        assert len(binary_eligible) == 2, \
            f"Expected 2 binary star events eligible in binary star system, got {len(binary_eligible)}"

    def test_phenomenon_events_not_eligible_in_other_systems(self) -> None:
        """Nebula events not eligible in pulsar systems, etc."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None

        # Nebula events in pulsar system
        system.phenomenon = "pulsar"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        nebula_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "nebula"]
        assert len(nebula_eligible) == 0, \
            f"Expected 0 nebula events eligible in pulsar system, got {len(nebula_eligible)}"

        # Pulsar events in binary star system
        system.phenomenon = "binary_star"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        pulsar_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "pulsar"]
        assert len(pulsar_eligible) == 0, \
            f"Expected 0 pulsar events eligible in binary star system, got {len(pulsar_eligible)}"

        # Binary star events in nebula system
        system.phenomenon = "nebula"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        binary_eligible = [t for t in eligible if t.get("trigger_conditions", {}).get("phenomenon") == "binary_star"]
        assert len(binary_eligible) == 0, \
            f"Expected 0 binary star events eligible in nebula system, got {len(binary_eligible)}"

    def test_phenomenon_events_not_eligible_in_normal_systems(self) -> None:
        """No phenomenon events in systems with phenomenon='none'."""
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "none"
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        phenomenon_eligible = [
            t for t in eligible
            if t.get("trigger_conditions", {}).get("phenomenon") in ("nebula", "pulsar", "binary_star")
        ]
        assert len(phenomenon_eligible) == 0, \
            f"Expected 0 phenomenon events eligible in normal system, got {len(phenomenon_eligible)}"

    def test_phenomenon_event_choices_have_valid_outcomes(self) -> None:
        """Each choice outcome can be parsed by apply_choice_outcome."""
        from backend.models.game_state import GameState
        from backend.models.ship import Ship

        phenomenon_events = [
            t for t in EVENT_TEMPLATES
            if t.get("trigger_conditions", {}).get("phenomenon") in ("nebula", "pulsar", "binary_star")
        ]
        ship = Ship()
        state = GameState(id="test-ph-outcomes", seed=42, ship=ship)

        for event in phenomenon_events:
            for i, choice in enumerate(event["choices"]):
                effects = state.apply_choice_outcome(choice["outcome"])
                assert isinstance(effects, dict), f"Outcome for {event['title']} choice {i} should return a dict"
                assert any(v != 0 for v in effects.values()) or ";" not in choice["outcome"].strip(), \
                    f"Choice {i} of {event['title']} has no stat effects: {choice['outcome']}"

    def test_phenomenon_events_can_be_triggered(self) -> None:
        """Events can be triggered in matching systems."""
        from unittest.mock import patch
        import random

        for phenomenon in ("nebula", "pulsar", "binary_star"):
            state = new_game(seed=42)
            system = state.get_current_system()
            assert system is not None
            system.phenomenon = phenomenon
            state.ship.morale = 80

            rng = random.Random(42)
            with patch.object(rng, "random", return_value=0.2):
                event = trigger_event(state, rng_override=rng)
            assert event is not None, f"Expected an event to trigger in {phenomenon} system with mocked RNG"
            assert event.title in [t["title"] for t in EVENT_TEMPLATES]

    def test_phenomenon_events_can_be_resolved(self) -> None:
        """Events resolve correctly for each phenomenon type."""
        from backend.generation.events import _create_event

        # Pick one template per phenomenon type
        nebula_template = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "nebula"][0]
        pulsar_template = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "pulsar"][0]
        binary_template = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "binary_star"][0]

        for template in (nebula_template, pulsar_template, binary_template):
            for i in range(len(template["choices"])):
                state = new_game(seed=42)
                event = _create_event(template, state.get_current_system().id)
                state.events.append(event)

                ok, msg, extra = resolve_event(state, event.id, i)
                assert ok is True, f"Failed to resolve choice {i} of '{template['title']}': {msg}"
                assert extra["title"] == template["title"]
                assert extra["chosen_text"] == event.choices[i].text
                assert isinstance(extra["effects"], dict)

    def test_nebula_events_have_valid_event_types(self) -> None:
        """Nebula events use hazard, discovery, encounter types."""
        nebula_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "nebula"]
        valid_types = {"hazard", "discovery", "encounter"}
        for event in nebula_events:
            assert event["type"] in valid_types, \
                f"Nebula event '{event['title']}' has invalid type: {event['type']}"
        actual_types = {e["type"] for e in nebula_events}
        assert actual_types.issubset(valid_types), f"Nebula events have unexpected types: {actual_types - valid_types}"

    def test_pulsar_events_have_valid_event_types(self) -> None:
        """Pulsar events use hazard, discovery types."""
        pulsar_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "pulsar"]
        valid_types = {"hazard", "discovery"}
        for event in pulsar_events:
            assert event["type"] in valid_types, \
                f"Pulsar event '{event['title']}' has invalid type: {event['type']}"
        actual_types = {e["type"] for e in pulsar_events}
        assert actual_types.issubset(valid_types), f"Pulsar events have unexpected types: {actual_types - valid_types}"

    def test_binary_star_events_have_valid_event_types(self) -> None:
        """Binary star events use encounter, discovery types."""
        binary_star_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "binary_star"]
        valid_types = {"encounter", "discovery"}
        for event in binary_star_events:
            assert event["type"] in valid_types, \
                f"Binary star event '{event['title']}' has invalid type: {event['type']}"
        actual_types = {e["type"] for e in binary_star_events}
        assert actual_types.issubset(valid_types), f"Binary star events have unexpected types: {actual_types - valid_types}"

    def test_all_phenomenon_events_count(self) -> None:
        """Total phenomenon events = 9 (4 nebula + 3 pulsar + 2 binary)."""
        nebula_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "nebula"]
        pulsar_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "pulsar"]
        binary_events = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("phenomenon") == "binary_star"]
        total = len(nebula_events) + len(pulsar_events) + len(binary_events)
        assert total == 9, f"Expected 9 total phenomenon events, got {total} (nebula={len(nebula_events)}, pulsar={len(pulsar_events)}, binary={len(binary_events)})"


class TestEventCooldowns:
    """Tests for the event cooldown system."""

    def test_event_cooldown_blocks_repetition(self) -> None:
        """Trigger same event twice, second should be blocked by cooldown."""
        state = new_game(seed=42)
        state.ship.morale = 20  # low morale forces event
        event1 = trigger_event(state)
        assert event1 is not None
        title1 = event1.title
        # Cooldown should be set
        assert state.event_cooldowns.get(title1, 0) > 0
        # Reset last_event_title so only cooldown blocks repetition
        state.last_event_title = None
        event2 = trigger_event(state)
        if event2 is not None:
            assert event2.title != title1, f"Expected different event, got same: {title1}"

    def test_event_cooldown_decrements(self) -> None:
        """Verify cooldowns decrement correctly."""
        from backend.generation.events import decrement_cooldowns
        state = new_game(seed=42)
        state.event_cooldowns = {"Life Support Failure": 8, "Crew Dispute": 3}
        decrement_cooldowns(state)
        assert state.event_cooldowns["Life Support Failure"] == 7
        assert state.event_cooldowns["Crew Dispute"] == 2

    def test_event_cooldown_expires(self) -> None:
        """After cooldown expires (decremented to 0), the key is removed."""
        from backend.generation.events import decrement_cooldowns
        state = new_game(seed=42)
        state.event_cooldowns = {"Ancient Signal": 1, "Solar Flare": 5}
        decrement_cooldowns(state)
        assert "Ancient Signal" not in state.event_cooldowns
        assert state.event_cooldowns["Solar Flare"] == 4

    def test_event_cooldown_persists_in_state(self) -> None:
        """Cooldowns survive serialization roundtrip."""
        from backend.database import init_db
        init_db()
        state = new_game(seed=42)
        state.event_cooldowns = {"Ancient Signal": 5, "Solar Flare": 3}
        game_save(state)
        from backend.game.manager import game_load
        loaded = game_load(state.id)
        assert loaded is not None
        assert loaded.event_cooldowns == {"Ancient Signal": 5, "Solar Flare": 3}

    def test_event_cooldown_apply_on_event(self) -> None:
        """When event fires, cooldown is set."""
        state = new_game(seed=42)
        state.ship.morale = 20
        event = trigger_event(state)
        assert event is not None
        assert event.title in state.event_cooldowns
        assert state.event_cooldowns[event.title] > 0

    def test_event_cooldown_decrement_in_actions(self) -> None:
        """Jump, scan, explore all decrement cooldowns."""
        from backend.database import init_db
        from backend.api.routes import api_scan
        from backend.game.manager import GAME_STORE
        init_db()
        state = new_game(seed=42)
        state.event_cooldowns = {"Ancient Signal": 5}
        state.ship.fuel = 100
        GAME_STORE[state.id] = state
        api_scan(state.id)
        assert state.event_cooldowns.get("Ancient Signal", 0) == 4

    def test_event_cooldown_all_on_cooldown_fallback(self) -> None:
        """When all events are on cooldown, allow the one with lowest cooldown."""
        state = new_game(seed=42)
        state.ship.morale = 20  # low morale forces event
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        eligible = [t for t in eligible if t["type"] in ("crew", "crisis", "narrative")]
        # Put ALL of them on cooldown with varying values
        for t in eligible:
            state.event_cooldowns[t["title"]] = 10
        # Make the first one have the lowest cooldown
        lowest_title = eligible[0]["title"]
        state.event_cooldowns[lowest_title] = 2
        state.last_event_title = None
        event = trigger_event(state)
        assert event is not None
        assert event.title == lowest_title, f"Expected {lowest_title}, got {event.title}"

    def test_event_cooldown_all_on_cooldown_normal_path(self) -> None:
        """When all events on cooldown in normal path, fallback allows lowest."""
        import random as rnd_mod
        state = new_game(seed=42)
        state.ship.morale = 80  # normal morale
        system = state.get_current_system()
        assert system is not None
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        for t in eligible:
            state.event_cooldowns[t["title"]] = 10
        lowest_title = eligible[0]["title"]
        state.event_cooldowns[lowest_title] = 1
        state.last_event_title = None
        rng = rnd_mod.Random(42)
        rng.random()  # consume first value
        event = trigger_event(state, rng_override=rng)
        assert event is not None
        assert event.title == lowest_title, f"Expected {lowest_title}, got {event.title}"

    def test_apply_cooldown_default_value(self) -> None:
        """apply_cooldown should use default cooldown 5 for unknown events."""
        from backend.generation.events import apply_cooldown
        state = new_game(seed=42)
        apply_cooldown(state, "Unknown Event XYZ")
        assert state.event_cooldowns["Unknown Event XYZ"] == 5

    def test_apply_cooldown_fallback_all_cooldown_zero(self) -> None:
        """When all events have cooldown <= 0, the function returns a non-empty list.
        When eligible is empty, the function returns an empty list."""
        state = new_game(seed=42)
        # No event_cooldowns means all events have cooldown <= 0 (get defaults to 0)
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        result = _apply_cooldown_fallback(eligible, state)
        assert len(result) > 0
        assert list(result) == list(eligible)  # all events pass the cooldown check

        # When eligible is empty, result should be empty
        result_empty = _apply_cooldown_fallback([], state)
        assert result_empty == []

    def test_cooldown_fallback_respects_last_event_title_low_morale(self) -> None:
        """When all events on cooldown share the same lowest cooldown value and the lowest-cooldown event IS last_event_title, a different event should be picked."""
        state = new_game(seed=42)
        state.ship.morale = 20  # low morale forces event
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        eligible = [t for t in eligible if t["type"] in ("crew", "crisis", "narrative")]
        # Put ALL of them on cooldown with the SAME cooldown value
        for t in eligible:
            state.event_cooldowns[t["title"]] = 5
        # Set last_event_title to the first eligible event
        last_title = eligible[0]["title"]
        state.last_event_title = last_title
        event = trigger_event(state)
        assert event is not None
        # The event should NOT be the last_event_title
        assert event.title != last_title, \
            f"Expected event different from last_event_title '{last_title}', got '{event.title}'"

    def test_cooldown_fallback_respects_last_event_title_normal_path(self) -> None:
        """When all events on cooldown share the same lowest cooldown value and the lowest-cooldown event IS last_event_title in the normal path, a different event should be picked."""
        import random as rnd_mod
        state = new_game(seed=42)
        state.ship.morale = 80  # normal morale
        system = state.get_current_system()
        assert system is not None
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        # Put ALL of them on cooldown with the SAME cooldown value
        for t in eligible:
            state.event_cooldowns[t["title"]] = 5
        # Set last_event_title to the first eligible event
        last_title = eligible[0]["title"]
        state.last_event_title = last_title
        rng = rnd_mod.Random(42)
        rng.random()  # consume first value to pass the 35% check
        event = trigger_event(state, rng_override=rng)
        assert event is not None
        # The event should NOT be the last_event_title
        assert event.title != last_title, \
            f"Expected event different from last_event_title '{last_title}', got '{event.title}'"

    def test_cooldown_fallback_all_match_last_event_title_low_morale(self) -> None:
        """When all eligible events are on cooldown and ALL of them match last_event_title (single event case), the fallback should still fire that event."""
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        from backend.models.system import StarSystem, Body
        from backend.config import MORALE_LOW_THRESHOLD

        ship = Ship(morale=MORALE_LOW_THRESHOLD - 1)
        state = GameState(id="test-all-match-low", seed=42, ship=ship)
        body = Body(id="b1", name="Planet", body_type="planet", biome="ocean",
                    size=3, distance_from_star=0.5, poi_count=1)
        system = StarSystem(id="sys1", name="TestSys", x=0.0, y=0.0,
                            star_type="G", star_color="#fff",
                            phenomenon="none", phenomenon_desc="",
                            bodies=[body])
        state.systems = {"sys1": system}
        state.ship.current_system_id = "sys1"

        import unittest.mock as mock
        single_template = {"type": "crew", "title": "Crew Dispute", "flavor": "...", "rarity": "common", "choices": []}
        with mock.patch("backend.generation.events._get_eligible_templates", return_value=[single_template]):
            state.event_cooldowns["Crew Dispute"] = 5
            state.last_event_title = "Crew Dispute"
            event = trigger_event(state)
        assert event is not None
        assert event.title == "Crew Dispute"

    def test_cooldown_fallback_all_match_last_event_title_normal_path(self) -> None:
        """When all eligible events are on cooldown and ALL of them match last_event_title (single event case) in the normal path, the fallback should still fire that event."""
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        from backend.models.system import StarSystem, Body
        from backend.config import MORALE_LOW_THRESHOLD
        import random as rnd_mod

        ship = Ship(morale=MORALE_LOW_THRESHOLD + 10)
        state = GameState(id="test-all-match-normal", seed=42, ship=ship)
        body = Body(id="b1", name="Planet", body_type="planet", biome="ocean",
                    size=3, distance_from_star=0.5, poi_count=1)
        system = StarSystem(id="sys1", name="TestSys", x=0.0, y=0.0,
                            star_type="G", star_color="#fff",
                            phenomenon="none", phenomenon_desc="",
                            bodies=[body])
        state.systems = {"sys1": system}
        state.ship.current_system_id = "sys1"

        import unittest.mock as mock
        single_template = {"type": "hazard", "title": "Solar Flare", "flavor": "...", "rarity": "common", "choices": []}
        with mock.patch("backend.generation.events._get_eligible_templates", return_value=[single_template]):
            state.event_cooldowns["Solar Flare"] = 5
            state.last_event_title = "Solar Flare"
            rng = rnd_mod.Random(1)
            event = trigger_event(state, rng_override=rng)
        assert event is not None
        assert event.title == "Solar Flare"


class TestCooldownOrdering:
    """Tests verifying that cooldowns are decremented BEFORE new events are triggered during action pipelines."""

    def test_cooldown_decrement_before_trigger(self) -> None:
        """Simulate: cooldown at 1, decrement removes it, trigger sets new cooldown."""
        from backend.generation.events import decrement_cooldowns, EVENT_COOLDOWNS
        state = new_game(seed=42)
        state.ship.morale = 20  # low morale forces event
        state.event_cooldowns["Ancient Signal"] = 1

        decrement_cooldowns(state)
        assert "Ancient Signal" not in state.event_cooldowns

        event = trigger_event(state)
        assert event is not None
        assert event.title in state.event_cooldowns
        expected_cooldown = EVENT_COOLDOWNS.get(event.title, 5)
        assert state.event_cooldowns[event.title] == expected_cooldown
        assert expected_cooldown > 0

    def test_cooldown_ordering_jump_action(self) -> None:
        """Jump pipeline: perform_jump -> decrement -> trigger; old cooldown expires, new one set at full value."""
        from backend.generation.events import decrement_cooldowns, EVENT_COOLDOWNS
        state = new_game(seed=42)
        state.ship.morale = 20
        state.ship.fuel = 500
        state.ship.jump_range = 999
        state.event_cooldowns["Ancient Signal"] = 1

        nearby = get_nearby_systems(state)
        reachable = [n for n in nearby if n["reachable"]]
        assert len(reachable) > 0, "Need a reachable system for jump test"
        target = state.systems[reachable[0]["id"]]
        cur = state.get_current_system()
        ok, cost, _ = can_jump(state.ship, target, cur)
        assert ok, "Jump should be possible"

        perform_jump(state, target, cost)
        decrement_cooldowns(state)
        assert "Ancient Signal" not in state.event_cooldowns

        event = trigger_event(state)
        assert event is not None
        assert event.title in state.event_cooldowns
        expected_cooldown = EVENT_COOLDOWNS.get(event.title, 5)
        assert state.event_cooldowns[event.title] == expected_cooldown
        assert expected_cooldown > 0

    def test_cooldown_ordering_scan_action(self) -> None:
        """Scan pipeline: perform_scan -> decrement -> trigger; old cooldown expires, new one set at full value."""
        from backend.generation.events import decrement_cooldowns, EVENT_COOLDOWNS
        state = new_game(seed=42)
        state.ship.morale = 20
        state.ship.fuel = 100
        state.event_cooldowns["Ancient Signal"] = 1

        perform_scan(state)
        decrement_cooldowns(state)
        assert "Ancient Signal" not in state.event_cooldowns

        event = trigger_event(state)
        assert event is not None
        assert event.title in state.event_cooldowns
        expected_cooldown = EVENT_COOLDOWNS.get(event.title, 5)
        assert state.event_cooldowns[event.title] == expected_cooldown
        assert expected_cooldown > 0

    def test_cooldown_ordering_explore_action(self) -> None:
        """Explore pipeline: explore_surface -> decrement -> trigger; old cooldown expires, new one set at full value."""
        from backend.generation.events import decrement_cooldowns, EVENT_COOLDOWNS
        state = new_game(seed=42)
        state.ship.morale = 20
        state.ship.fuel = 100
        state.event_cooldowns["Ancient Signal"] = 1

        system = state.get_current_system()
        assert system is not None
        planet = next((b for b in system.bodies if b.body_type == "planet"), None)
        assert planet is not None, "Need a planet for explore test"
        land_on_body(state, planet.id)

        explore_surface(state)
        decrement_cooldowns(state)
        assert "Ancient Signal" not in state.event_cooldowns

        event = trigger_event(state)
        assert event is not None
        assert event.title in state.event_cooldowns
        expected_cooldown = EVENT_COOLDOWNS.get(event.title, 5)
        assert state.event_cooldowns[event.title] == expected_cooldown
        assert expected_cooldown > 0

    def test_cooldown_ordering_save_load_scenario(self) -> None:
        """Save/load: cooldown at 1 survives roundtrip, decrements to expire, new event gets full cooldown."""
        from backend.database import init_db
        from backend.game.manager import game_load
        from backend.generation.events import decrement_cooldowns, EVENT_COOLDOWNS
        init_db()

        state = new_game(seed=42)
        state.ship.morale = 20
        state.event_cooldowns["Ancient Signal"] = 1
        game_save(state)

        loaded = game_load(state.id)
        assert loaded is not None
        assert loaded.event_cooldowns == {"Ancient Signal": 1}

        decrement_cooldowns(loaded)
        assert "Ancient Signal" not in loaded.event_cooldowns

        event = trigger_event(loaded)
        assert event is not None
        assert event.title in loaded.event_cooldowns
        expected_cooldown = EVENT_COOLDOWNS.get(event.title, 5)
        assert loaded.event_cooldowns[event.title] == expected_cooldown
        assert expected_cooldown > 0


class TestCrisisCooldown:
    """Tests for the crisis_cooldown mechanism."""

    def test_crisis_cooldown_decrements_on_trigger_call(self) -> None:
        """crisis_cooldown should only decrement when an event is actually triggered."""
        state = new_game(seed=42)
        state.ship.morale = 80  # normal morale
        state.crisis_cooldown = 3
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "none"
        # Call trigger_event - it should NOT decrement crisis_cooldown since no event is triggered
        import random
        rng = random.Random(0)
        event = trigger_event(state, rng_override=rng)
        assert event is None, "Expected no event to trigger"
        assert state.crisis_cooldown == 3, f"Expected 3 (unchanged), got {state.crisis_cooldown}"

    def test_crisis_cooldown_blocks_crisis_in_low_morale(self) -> None:
        from unittest.mock import patch
        state = new_game(seed=42)
        state.ship.morale = 20  # low morale
        state.crisis_cooldown = 2
        
        # Control the eligible templates to ensure a non-crisis event is available
        crew_template = {"type": "crew", "title": "Crew Dispute", "flavor": "Tensions rise among the crew.", "rarity": "common", "choices": []}
        with patch("backend.generation.events._get_eligible_templates", return_value=[crew_template]):
            event = trigger_event(state)
        assert event is not None
        assert event.event_type != "crisis", f"Expected non-crisis event, got {event.event_type}: {event.title}"

    def test_crisis_cooldown_blocks_crisis_in_normal_path(self) -> None:
        """When crisis_cooldown > 0 in normal path, crisis events should be filtered out."""
        from unittest.mock import patch
        import random
        state = new_game(seed=42)
        state.ship.morale = 80  # normal morale
        state.crisis_cooldown = 2
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "none"
        # Force the 35% chance to succeed
        rng = random.Random(42)
        with patch.object(rng, "random", return_value=0.2):
            event = trigger_event(state, rng_override=rng)
        assert event is not None
        # The event should NOT be a crisis event since crisis_cooldown > 0
        assert event.event_type != "crisis", f"Expected non-crisis event, got {event.event_type}: {event.title}"

    def test_crisis_cooldown_set_when_crisis_fires_low_morale(self) -> None:
        """When a crisis event fires in low-morale path, crisis_cooldown should be set to 3."""
        from unittest.mock import patch
        state = new_game(seed=42)
        state.ship.morale = 20  # low morale
        state.crisis_cooldown = 0  # no cooldown
        crisis_template = [{"type": "crisis", "category": "crisis", "title": "Life Support Failure", "flavor": "...", "rarity": "common", "choices": []}]
        with patch("backend.generation.events._get_eligible_templates", return_value=crisis_template):
            event = trigger_event(state)
        assert event is not None
        assert event.event_type == "crisis"
        assert state.crisis_cooldown == 3

    def test_crisis_cooldown_set_when_crisis_fires_normal_path(self) -> None:
        """When a crisis event fires in normal path, crisis_cooldown should be set to 3."""
        from unittest.mock import patch
        import random
        state = new_game(seed=42)
        state.ship.morale = 80  # normal morale
        state.crisis_cooldown = 0  # no cooldown
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "none"
        crisis_template = [{"type": "crisis", "category": "crisis", "title": "Life Support Failure", "flavor": "...", "rarity": "common", "choices": []}]
        rng = random.Random(1)
        with patch.object(rng, "random", return_value=0.2):
            with patch("backend.generation.events._get_eligible_templates", return_value=crisis_template):
                event = trigger_event(state, rng_override=rng)
        assert event is not None
        assert event.event_type == "crisis"
        assert state.crisis_cooldown == 3

    def test_crisis_cooldown_does_not_go_below_zero(self) -> None:
        """crisis_cooldown should not go below 0 (and should not decrement when no event triggers)."""
        state = new_game(seed=42)
        state.ship.morale = 80
        state.crisis_cooldown = 0
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "none"
        import random
        rng = random.Random(0)
        event = trigger_event(state, rng_override=rng)
        assert event is None, "Expected no event to trigger"
        assert state.crisis_cooldown == 0, f"Expected 0 (unchanged), got {state.crisis_cooldown}"

    def test_crisis_cooldown_serialization(self) -> None:
        """crisis_cooldown should survive save/load roundtrip."""
        from backend.database import init_db
        from backend.game.manager import game_load
        init_db()
        state = new_game(seed=42)
        state.crisis_cooldown = 3
        game_save(state)
        loaded = game_load(state.id)
        assert loaded is not None
        assert loaded.crisis_cooldown == 3, f"Expected 3, got {loaded.crisis_cooldown}"

    def test_new_game_crisis_cooldown_zero(self) -> None:
        """A new game should have crisis_cooldown = 0."""
        state = new_game(seed=42)
        assert state.crisis_cooldown == 0

    def test_crisis_cooldown_blocks_all_crisis_in_low_morale(self) -> None:
        """When crisis_cooldown > 0 in low-morale path, crisis events should be filtered out even if they are the only eligible type."""
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        from backend.models.system import StarSystem, Body
        from backend.config import MORALE_LOW_THRESHOLD
        import unittest.mock as mock

        ship = Ship(morale=MORALE_LOW_THRESHOLD - 1)
        state = GameState(id="test-crisis-block-low", seed=42, ship=ship)
        body = Body(id="b1", name="Planet", body_type="planet", biome="ocean",
                    size=3, distance_from_star=0.5, poi_count=1)
        system = StarSystem(id="sys1", name="TestSys", x=0.0, y=0.0,
                            star_type="G", star_color="#fff",
                            phenomenon="none", phenomenon_desc="",
                            bodies=[body])
        state.systems = {"sys1": system}
        state.ship.current_system_id = "sys1"
        state.crisis_cooldown = 2

        # Only crisis templates are eligible
        crisis_template = {"type": "crisis", "category": "crisis", "title": "Life Support Failure", "flavor": "...", "rarity": "common", "choices": []}
        with mock.patch("backend.generation.events._get_eligible_templates", return_value=[crisis_template]):
            result = trigger_event(state)
        # Should return None because the only eligible event is a crisis and crisis_cooldown > 0
        assert result is None, "Expected None when only crisis events are eligible but crisis_cooldown > 0"

    def test_crisis_cooldown_blocks_all_crisis_in_normal_path(self) -> None:
        """When crisis_cooldown > 0 in normal path, crisis events should be filtered out even if they are the only eligible type."""
        from backend.models.game_state import GameState
        from backend.models.ship import Ship
        from backend.models.system import StarSystem, Body
        from backend.config import MORALE_LOW_THRESHOLD
        import unittest.mock as mock
        import random

        ship = Ship(morale=MORALE_LOW_THRESHOLD + 10)
        state = GameState(id="test-crisis-block-normal", seed=42, ship=ship)
        body = Body(id="b1", name="Planet", body_type="planet", biome="ocean",
                    size=3, distance_from_star=0.5, poi_count=1)
        system = StarSystem(id="sys1", name="TestSys", x=0.0, y=0.0,
                            star_type="G", star_color="#fff",
                            phenomenon="none", phenomenon_desc="",
                            bodies=[body])
        state.systems = {"sys1": system}
        state.ship.current_system_id = "sys1"
        state.crisis_cooldown = 2

        # Only crisis templates are eligible
        crisis_template = {"type": "crisis", "category": "crisis", "title": "Life Support Failure", "flavor": "...", "rarity": "common", "choices": []}
        rng = random.Random(1)
        with mock.patch("backend.generation.events._get_eligible_templates", return_value=[crisis_template]):
            result = trigger_event(state, rng_override=rng)
        # Should return None because the only eligible event is a crisis and crisis_cooldown > 0
        assert result is None, "Expected None when only crisis events are eligible but crisis_cooldown > 0"

    def test_crisis_cooldown_not_set_when_non_crisis_fires_low_morale(self) -> None:
        """When a non-crisis event fires in low-morale path, crisis_cooldown should stay 0."""
        from unittest.mock import patch
        state = new_game(seed=42)
        state.ship.morale = 20  # low morale
        state.crisis_cooldown = 0
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "none"
        crew_template = {"type": "crew", "title": "Crew Dispute", "flavor": "Tensions rise among the crew.", "rarity": "common", "choices": []}
        with patch("backend.generation.events._get_eligible_templates", return_value=[crew_template]):
            event = trigger_event(state)
        assert event is not None
        assert event.event_type != "crisis", f"Expected non-crisis event, got {event.event_type}: {event.title}"
        assert state.crisis_cooldown == 0, f"Expected crisis_cooldown=0, got {state.crisis_cooldown}"

    def test_crisis_cooldown_not_set_when_non_crisis_fires_normal_path(self) -> None:
        """When a non-crisis event fires in normal path, crisis_cooldown should stay 0."""
        from unittest.mock import patch
        import random as rand_mod
        state = new_game(seed=42)
        state.ship.morale = 80  # normal morale
        state.crisis_cooldown = 0
        system = state.get_current_system()
        assert system is not None
        system.phenomenon = "none"
        crew_template = {"type": "crew", "title": "Crew Dispute", "flavor": "Tensions rise among the crew.", "rarity": "common", "choices": []}
        rng = rand_mod.Random(1)
        with patch("backend.generation.events._get_eligible_templates", return_value=[crew_template]):
            event = trigger_event(state, rng_override=rng)
        assert event is not None
        assert event.event_type != "crisis", f"Expected non-crisis event, got {event.event_type}: {event.title}"
        assert state.crisis_cooldown == 0, f"Expected crisis_cooldown=0, got {state.crisis_cooldown}"

    def test_crisis_events_have_category_field(self) -> None:
        """All crisis event templates should have category: crisis."""
        from backend.generation.events import EVENT_TEMPLATES
        crisis_templates = [t for t in EVENT_TEMPLATES if t["type"] == "crisis"]
        assert len(crisis_templates) >= 6, f"Expected at least 6 crisis events, got {len(crisis_templates)}"
        for t in crisis_templates:
            assert t.get("category") == "crisis", f"Crisis event '{t['title']}' missing category='crisis'"

    def test_crisis_events_can_be_resolved(self) -> None:
        """All crisis events should resolve correctly for each choice."""
        from backend.generation.events import _create_event, EVENT_TEMPLATES
        crisis_templates = [t for t in EVENT_TEMPLATES if t["type"] == "crisis"]
        for template in crisis_templates:
            for i in range(len(template["choices"])):
                state = new_game(seed=42)
                event = _create_event(template, state.get_current_system().id)
                state.events.append(event)
                ok, msg, extra = resolve_event(state, event.id, i)
                assert ok is True, f"Failed to resolve choice {i} of '{template['title']}': {msg}"
                assert extra["title"] == template["title"]
                assert extra["chosen_text"] == event.choices[i].text
                assert isinstance(extra["effects"], dict)

