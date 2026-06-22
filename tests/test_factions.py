import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game, game_save, game_load, _state_to_dict, _state_from_dict
from backend.models.faction import (
    Faction, FactionRelation, FACTION_DEFINITIONS, get_faction,
)
from backend.models.game_state import _rep_label
from backend.game.trading import perform_trade, perform_bulk_sell
from backend.game.engine import activate_distress_beacon
from backend.generation.events import resolve_event, EVENT_TEMPLATES, _create_event

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db() -> None:
    init_db()


class TestFactionModel:
    def test_faction_creation(self) -> None:
        faction = Faction(
            id="test_faction", name="Test Faction",
            description="A test faction.", alignment="explorer",
            home_system_id="sys_1",
        )
        assert faction.id == "test_faction"
        assert faction.name == "Test Faction"
        assert faction.description == "A test faction."
        assert faction.alignment == "explorer"
        assert faction.home_system_id == "sys_1"

    def test_faction_default_home_system(self) -> None:
        faction = Faction(
            id="test_faction", name="Test Faction",
            description="A test faction.", alignment="explorer",
        )
        assert faction.home_system_id is None

    def test_faction_relation_creation(self) -> None:
        relation = FactionRelation(faction_id="test_faction", reputation=10, known=True)
        assert relation.faction_id == "test_faction"
        assert relation.reputation == 10
        assert relation.known is True

    def test_faction_relation_defaults(self) -> None:
        relation = FactionRelation(faction_id="test_faction")
        assert relation.reputation == 0
        assert relation.known is False

    def test_get_faction_exists(self) -> None:
        faction = get_faction("stellar_cartographers")
        assert faction is not None
        assert faction.name == "Stellar Cartographers Union"

    def test_get_faction_not_exists(self) -> None:
        faction = get_faction("nonexistent_faction")
        assert faction is None

    def test_all_factions_have_required_fields(self) -> None:
        for fid, faction in FACTION_DEFINITIONS.items():
            assert faction.id == fid
            assert len(faction.name) > 0
            assert len(faction.description) > 0
            assert faction.alignment in ("explorer", "corporate")


class TestGameStateFactions:
    def test_new_game_has_faction_relations(self) -> None:
        state = new_game(seed=42)
        assert len(state.faction_relations) == 3
        for fid in FACTION_DEFINITIONS:
            assert fid in state.faction_relations
            assert state.faction_relations[fid].reputation == 0
            assert state.faction_relations[fid].known is False

    def test_get_faction_reputation_existing(self) -> None:
        state = new_game(seed=42)
        state.faction_relations["stellar_cartographers"].reputation = 25
        assert state.get_faction_reputation("stellar_cartographers") == 25

    def test_get_faction_reputation_missing(self) -> None:
        state = new_game(seed=42)
        assert state.get_faction_reputation("nonexistent") == 0

    def test_modify_faction_reputation_existing(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 10)
        assert state.faction_relations["stellar_cartographers"].reputation == 10

    def test_modify_faction_reputation_new(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("new_faction", 15)
        assert "new_faction" in state.faction_relations
        assert state.faction_relations["new_faction"].reputation == 15

    def test_modify_faction_reputation_negative(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", -5)
        assert state.faction_relations["stellar_cartographers"].reputation == -5

    def test_modify_faction_reputation_clamping_high(self) -> None:
        state = new_game(seed=42)
        state.faction_relations["stellar_cartographers"].reputation = 95
        state.modify_faction_reputation("stellar_cartographers", 50)
        assert state.faction_relations["stellar_cartographers"].reputation == 100

    def test_modify_faction_reputation_clamping_low(self) -> None:
        state = new_game(seed=42)
        state.faction_relations["stellar_cartographers"].reputation = -995
        state.modify_faction_reputation("stellar_cartographers", -50)
        assert state.faction_relations["stellar_cartographers"].reputation == -1000

    def test_get_known_factions(self) -> None:
        state = new_game(seed=42)
        known = state.get_known_factions()
        assert len(known) == 3
        for entry in known:
            assert "faction_id" in entry
            assert "name" in entry
            assert "reputation" in entry
            assert "known" in entry
            assert entry["reputation"] == 0
            assert entry["known"] is False

    def test_get_known_factions_with_reputation(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 25)
        state.faction_relations["stellar_cartographers"].known = True
        known = state.get_known_factions()
        sc_entry = next(e for e in known if e["faction_id"] == "stellar_cartographers")
        assert sc_entry["reputation"] == 25
        assert sc_entry["known"] is True

    def test_state_summary_includes_factions(self) -> None:
        state = new_game(seed=42)
        summary = state.state_summary()
        assert "faction_relations" in summary
        assert len(summary["faction_relations"]) == 3


class TestFactionSerialization:
    def test_state_to_dict_includes_factions(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 15)
        data = _state_to_dict(state)
        assert "faction_relations" in data
        assert "stellar_cartographers" in data["faction_relations"]
        assert data["faction_relations"]["stellar_cartographers"]["reputation"] == 15

    def test_state_from_dict_loads_factions(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 20)
        state.faction_relations["stellar_cartographers"].known = True
        data = _state_to_dict(state)
        restored = _state_from_dict(data)
        assert "stellar_cartographers" in restored.faction_relations
        assert restored.faction_relations["stellar_cartographers"].reputation == 20
        assert restored.faction_relations["stellar_cartographers"].known is True

    def test_save_and_load_roundtrip_factions(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("void_traders", -10)
        state.faction_relations["void_traders"].known = True
        game_save(state)

        loaded = game_load(state.id)
        assert loaded is not None
        assert "void_traders" in loaded.faction_relations
        assert loaded.faction_relations["void_traders"].reputation == -10
        assert loaded.faction_relations["void_traders"].known is True

    def test_old_save_without_factions_loads(self) -> None:
        state = new_game(seed=42)
        data = _state_to_dict(state)
        del data["faction_relations"]
        restored = _state_from_dict(data)
        assert restored.faction_relations == {}


class TestFactionAPI:
    def test_get_factions(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/factions")
        assert resp.status_code == 200
        data = resp.json()
        assert "factions" in data
        assert len(data["factions"]) == 3

    def test_get_factions_nonexistent_game(self) -> None:
        resp = client.get("/api/game/nonexistent-gid/factions")
        assert resp.status_code == 404

    def test_get_faction_detail(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/faction/stellar_cartographers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["faction"]["name"] == "Stellar Cartographers Union"
        assert data["reputation"] == 0
        assert data["known"] is False

    def test_get_faction_detail_nonexistent_game(self) -> None:
        resp = client.get("/api/game/nonexistent-gid/faction/stellar_cartographers")
        assert resp.status_code == 404

    def test_get_faction_detail_nonexistent_faction(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/faction/nonexistent")
        assert resp.status_code == 404

    def test_faction_mission_success(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        state.ship.fuel = 100
        state.ship.credits = 500
        GAME_STORE[game_id] = state
        game_save(state)

        with patch("random.Random.random", return_value=0.3):
            with patch("random.Random.randint", return_value=20):
                resp = client.post(f"/api/game/{game_id}/faction/stellar_cartographers/mission")
        assert resp.status_code == 200
        data = resp.json()
        assert data["effect"] == "success"
        assert "reputation" in data
        assert "ship" in data

    def test_faction_mission_failure(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        state.ship.fuel = 100
        state.ship.credits = 500
        GAME_STORE[game_id] = state
        game_save(state)

        with patch("random.Random.random", return_value=0.95):
            with patch("random.Random.randint", return_value=10):
                resp = client.post(f"/api/game/{game_id}/faction/stellar_cartographers/mission")
        assert resp.status_code == 200
        data = resp.json()
        assert data["effect"] == "failure"
        assert "reputation" in data

    def test_faction_mission_not_enough_fuel(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        state.ship.fuel = 5
        state.ship.credits = 500
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.post(f"/api/game/{game_id}/faction/stellar_cartographers/mission")
        assert resp.status_code == 400
        assert "Not enough fuel" in resp.json()["detail"]

    def test_faction_mission_not_enough_credits(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        state.ship.fuel = 100
        state.ship.credits = 10
        GAME_STORE[game_id] = state
        game_save(state)

        resp = client.post(f"/api/game/{game_id}/faction/stellar_cartographers/mission")
        assert resp.status_code == 400
        assert "Not enough credits" in resp.json()["detail"]

    def test_faction_mission_nonexistent_game(self) -> None:
        resp = client.post("/api/game/nonexistent-gid/faction/stellar_cartographers/mission")
        assert resp.status_code == 404

    def test_faction_mission_nonexistent_faction(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/faction/nonexistent/mission")
        assert resp.status_code == 404

    def test_faction_mission_increases_reputation(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "mission-rep-inc"})
        game_id = resp.json()["game_id"]
        state = GAME_STORE.get(game_id)
        assert state is not None
        state.ship.fuel = 100
        state.ship.credits = 500
        GAME_STORE[game_id] = state
        game_save(state)

        with patch("random.Random.random", return_value=0.3):
            with patch("random.Random.randint", return_value=25):
                resp = client.post(f"/api/game/{game_id}/faction/void_traders/mission")
        assert resp.status_code == 200
        data = resp.json()
        assert data["effect"] == "success"
        assert data["reputation"] > 0

    def test_full_state_response_includes_factions(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "factions" in data
        assert len(data["factions"]) == 3


class TestTradingFactionIntegration:
    def test_stellar_cartographers_positive_reputation_bonus(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("stellar_cartographers", 50)

        disc = Discovery(
            id="vt_test_disc", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits

        ok, msg = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        price_mod = 1.0 + min(max(50, 0), 50) / 200.0
        expected_min = int(100 * 0.7 * price_mod)
        expected_max = int(100 * 1.5 * price_mod)
        actual_credits = state.ship.credits - credits_before
        assert expected_min <= actual_credits <= expected_max

    def test_stellar_cartographers_negative_reputation_no_bonus(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("stellar_cartographers", -100)

        disc = Discovery(
            id="vt_neg_disc", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits

        ok, msg = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        expected_min = int(100 * 0.7)
        expected_max = int(100 * 1.5)
        actual_credits = state.ship.credits - credits_before
        assert expected_min <= actual_credits <= expected_max

    def test_stellar_cartographers_faction_mod_clamped(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("stellar_cartographers", 60)

        disc = Discovery(
            id="vt_clamp_disc", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits

        ok, msg = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        actual_credits = state.ship.credits - credits_before
        # faction_mod should be clamped to 1.25, so max is 100 * 1.5 * 1.25 = 187 (rounded down)
        assert actual_credits <= int(100 * 1.5 * 1.25)

    def test_void_traders_discount_on_buy_fuel(self) -> None:
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.fuel = 0
        state.ship.credits = 5000

        # Buy fuel with 0 rep (baseline)
        state.modify_faction_reputation("void_traders", 0)
        credits_before = state.ship.credits
        ok, msg = perform_trade(state, "buy", "fuel", 10)
        assert ok is True
        base_cost = credits_before - state.ship.credits

        # Reset and buy fuel with 50 rep (discounted)
        state.ship.fuel = 0
        state.ship.credits = 5000
        state.modify_faction_reputation("void_traders", 50)
        ok, msg = perform_trade(state, "buy", "fuel", 10)
        assert ok is True
        discounted_cost = 5000 - state.ship.credits

        assert discounted_cost < base_cost

    def test_stellar_cartographers_bulk_sell_faction_mod(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("stellar_cartographers", -100)

        state.discoveries = [
            Discovery(id="bvt1", category="artifact", name="Ancient Relic",
                       description="Old relic", value=200, system_id=system.id),
        ]

        ok, msg, sold_count, total_price = perform_bulk_sell(
            state, [{"item": "artifact", "quantity": 1}]
        )
        assert ok is True
        actual_credits = total_price
        expected_min = int(200 * 0.7)
        expected_max = int(200 * 1.5)
        assert expected_min <= actual_credits <= expected_max


class TestEventFactionIntegration:
    def test_exploration_event_gives_stellar_cartographers_rep(self) -> None:
        state = new_game(seed=42)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "exploration")
        event = _create_event(template, "sys_0000")
        state.events.append(event)
        rep_before = state.get_faction_reputation("stellar_cartographers")

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        rep_after = state.get_faction_reputation("stellar_cartographers")
        assert rep_after > rep_before

    def test_trade_event_gives_void_traders_rep(self) -> None:
        state = new_game(seed=42)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "trade")
        event = _create_event(template, "sys_0000")
        state.events.append(event)
        rep_before = state.get_faction_reputation("void_traders")

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        rep_after = state.get_faction_reputation("void_traders")
        assert rep_after > rep_before

    def test_encounter_event_gives_free_pilots_rep(self) -> None:
        state = new_game(seed=42)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "encounter")
        event = _create_event(template, "sys_0000")
        state.events.append(event)
        rep_before = state.get_faction_reputation("free_pilots")

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        rep_after = state.get_faction_reputation("free_pilots")
        assert rep_after > rep_before

    def test_crisis_event_gives_free_pilots_rep(self) -> None:
        state = new_game(seed=42)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "crisis")
        event = _create_event(template, "sys_0000")
        state.events.append(event)
        rep_before = state.get_faction_reputation("free_pilots")

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        rep_after = state.get_faction_reputation("free_pilots")
        assert rep_after > rep_before


class TestDistressBeaconFactionIntegration:
    def test_pilots_guild_gives_free_pilots_rep(self) -> None:
        state = new_game(seed=42)
        state.ship.fuel = 0
        state.ship.hull = 100
        state.ship.credits = 300
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True

        rep_before = state.get_faction_reputation("free_pilots")
        mock_rng = MagicMock()
        mock_rng.random.side_effect = [0.2, 0.1]
        mock_rng.randint.side_effect = [1]
        with patch("backend.game.engine.seeded_random", return_value=mock_rng):
            result = activate_distress_beacon(state)
        assert result["outcome"] == "pilots_guild"
        rep_after = state.get_faction_reputation("free_pilots")
        assert rep_after == rep_before + 5


class TestFactionDBFallback:
    def test_factions_from_db_fallback(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "faction-fallback"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}/factions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["factions"]) == 3

    def test_faction_detail_from_db_fallback(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "faction-detail-fb"})
        game_id = resp.json()["game_id"]
        GAME_STORE.pop(game_id, None)
        resp = client.get(f"/api/game/{game_id}/faction/stellar_cartographers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["faction"]["name"] == "Stellar Cartographers Union"


class TestFactionEdgeCases:
    def test_faction_known_tracks_discovery(self) -> None:
        state = new_game(seed=42)
        assert state.faction_relations["void_traders"].known is False
        state.faction_relations["void_traders"].known = True
        assert state.faction_relations["void_traders"].known is True
        known = state.get_known_factions()
        vt = next(e for e in known if e["faction_id"] == "void_traders")
        assert vt["known"] is True

    def test_get_known_factions_with_missing_faction_definition(self) -> None:
        state = new_game(seed=42)
        state.faction_relations["unknown_faction"] = FactionRelation(
            faction_id="unknown_faction", reputation=50, known=True
        )
        known = state.get_known_factions()
        uf = next(e for e in known if e["faction_id"] == "unknown_faction")
        assert uf["name"] == "unknown_faction"
        assert uf["reputation"] == 50
        assert uf["known"] is True


class TestReputationCap:
    def test_reputation_capped_at_100(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 150)
        assert state.get_faction_reputation("stellar_cartographers") == 100

    def test_reputation_negative_floor_unchanged(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", -2000)
        assert state.get_faction_reputation("stellar_cartographers") == -1000

    def test_reputation_exactly_100(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("void_traders", 100)
        assert state.get_faction_reputation("void_traders") == 100
        state.modify_faction_reputation("void_traders", 10)
        assert state.get_faction_reputation("void_traders") == 100


class TestReputationDecay:
    def test_jumps_since_rep_decay_field_exists(self) -> None:
        state = new_game(seed=42)
        assert state.jumps_since_rep_decay == 0

    def test_jumps_since_rep_decay_serialization(self) -> None:
        state = new_game(seed=42)
        state.jumps_since_rep_decay = 5
        data = _state_to_dict(state)
        assert data["jumps_since_rep_decay"] == 5
        restored = _state_from_dict(data)
        assert restored.jumps_since_rep_decay == 5

    def test_rep_decay_on_jump(self) -> None:
        from backend.game.engine import perform_jump, can_jump
        from backend.generation.universe import distance_between
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 30)
        state.modify_faction_reputation("void_traders", 10)
        state.modify_faction_reputation("free_pilots", -5)

        systems = list(state.systems.values())
        # Find two systems within reasonable jump range
        sys_a = systems[0]
        sys_b = None
        for s in systems[1:]:
            if distance_between(sys_a, s) <= 50:
                sys_b = s
                break
        assert sys_b is not None

        state.ship.fuel = 500
        state.ship.jump_range = 20

        current_target = sys_b
        for _ in range(10):
            ok, fuel_cost, msg = can_jump(state.ship, current_target, state.get_current_system())
            assert ok, f'Jump failed: {msg}'
            perform_jump(state, current_target, int(fuel_cost))
            current_target = sys_a if current_target is sys_b else sys_b

        assert state.get_faction_reputation("stellar_cartographers") < 30
        assert state.get_faction_reputation("void_traders") < 10
        assert state.get_faction_reputation("free_pilots") > -5

    def test_rep_decay_resets_counter(self) -> None:
        from backend.game.engine import perform_jump, can_jump
        from backend.generation.universe import distance_between
        state = new_game(seed=42)
        state.modify_faction_reputation("void_traders", 30)

        systems = list(state.systems.values())
        sys_a = systems[0]
        sys_b = None
        for s in systems[1:]:
            if distance_between(sys_a, s) <= 50:
                sys_b = s
                break
        assert sys_b is not None

        state.ship.fuel = 500
        state.ship.jump_range = 20

        current_target = sys_b
        for _ in range(10):
            ok, fuel_cost, msg = can_jump(state.ship, current_target, state.get_current_system())
            assert ok, f'Jump failed: {msg}'
            perform_jump(state, current_target, int(fuel_cost))
            current_target = sys_a if current_target is sys_b else sys_b

        assert state.jumps_since_rep_decay == 0

    def test_rep_decay_zero_rep_unchanged(self) -> None:
        from backend.game.engine import perform_jump, can_jump
        from backend.generation.universe import distance_between
        state = new_game(seed=42)
        assert state.get_faction_reputation("stellar_cartographers") == 0

        systems = list(state.systems.values())
        sys_a = systems[0]
        sys_b = None
        for s in systems[1:]:
            if distance_between(sys_a, s) <= 50:
                sys_b = s
                break
        assert sys_b is not None

        state.ship.fuel = 500
        state.ship.jump_range = 20

        current_target = sys_b
        for _ in range(10):
            ok, fuel_cost, msg = can_jump(state.ship, current_target, state.get_current_system())
            assert ok, f'Jump failed: {msg}'
            perform_jump(state, current_target, int(fuel_cost))
            current_target = sys_a if current_target is sys_b else sys_b

        assert state.get_faction_reputation("stellar_cartographers") == 0

    def test_rep_decay_negative_toward_zero(self) -> None:
        from backend.game.engine import perform_jump, can_jump
        from backend.generation.universe import distance_between
        state = new_game(seed=42)
        state.modify_faction_reputation("free_pilots", -10)

        systems = list(state.systems.values())
        sys_a = systems[0]
        sys_b = None
        for s in systems[1:]:
            if distance_between(sys_a, s) <= 50:
                sys_b = s
                break
        assert sys_b is not None

        state.ship.fuel = 500
        state.ship.jump_range = 20

        current_target = sys_b
        for _ in range(10):
            ok, fuel_cost, msg = can_jump(state.ship, current_target, state.get_current_system())
            assert ok, f'Jump failed: {msg}'
            perform_jump(state, current_target, int(fuel_cost))
            current_target = sys_a if current_target is sys_b else sys_b

        assert state.get_faction_reputation("free_pilots") >= -9


class TestReputationTrading:
    def test_stellar_cartographers_sell_price_bonus(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True

        disc = Discovery(
            id="sc_test", category="mineral", name="Test Mineral",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits

        state.modify_faction_reputation("stellar_cartographers", 0)
        ok, _ = perform_trade(state, "sell", "mineral", 1)
        assert ok is True
        base_price = state.ship.credits - credits_before

        state.discoveries.append(disc)
        state.ship.credits = credits_before
        state.modify_faction_reputation("stellar_cartographers", 50)
        ok, _ = perform_trade(state, "sell", "mineral", 1)
        assert ok is True
        boosted_price = state.ship.credits - credits_before

        assert boosted_price > base_price

    def test_stellar_cartographers_sell_bonus_capped_at_50(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("stellar_cartographers", 50)

        disc = Discovery(
            id="sc_cap", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits
        with patch("random.Random.uniform", return_value=1.0):
            ok, _ = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        at50_price = state.ship.credits - credits_before

        state.discoveries.append(disc)
        state.ship.credits = credits_before
        state.modify_faction_reputation("stellar_cartographers", 60)
        with patch("random.Random.uniform", return_value=1.0):
            ok, _ = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        at60_price = state.ship.credits - credits_before

        assert at50_price == at60_price

    def test_stellar_cartographers_negative_rep_no_bonus(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True

        disc = Discovery(
            id="sc_neg", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits

        state.modify_faction_reputation("stellar_cartographers", -50)
        ok, _ = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        sell_price = state.ship.credits - credits_before
        # Should sell at base price_mod (0.7-1.5), no bonus from negative rep
        assert sell_price > 0

    def test_void_traders_buy_discount_fuel(self) -> None:
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.fuel = 0
        state.ship.credits = 5000

        state.modify_faction_reputation("void_traders", 0)
        credits_before = state.ship.credits
        ok, _ = perform_trade(state, "buy", "fuel", 10)
        assert ok is True
        base_cost = credits_before - state.ship.credits

        state.ship.fuel = 0
        state.ship.credits = 5000
        state.modify_faction_reputation("void_traders", 50)
        ok, _ = perform_trade(state, "buy", "fuel", 10)
        assert ok is True
        discounted_cost = 5000 - state.ship.credits

        assert discounted_cost < base_cost

    def test_void_traders_buy_discount_repair(self) -> None:
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.hull = 0
        state.ship.credits = 5000

        state.modify_faction_reputation("void_traders", 0)
        credits_before = state.ship.credits
        ok, _ = perform_trade(state, "buy", "repair", 2)
        assert ok is True
        base_cost = credits_before - state.ship.credits

        state.ship.hull = 0
        state.ship.credits = 5000
        state.modify_faction_reputation("void_traders", 50)
        ok, _ = perform_trade(state, "buy", "repair", 2)
        assert ok is True
        discounted_cost = 5000 - state.ship.credits

        assert discounted_cost < base_cost

    def test_void_traders_discount_capped_at_50(self) -> None:
        from backend.game.trading import calculate_fuel_price
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        state.modify_faction_reputation("void_traders", 50)
        price_50 = calculate_fuel_price(state, system)
        state.modify_faction_reputation("void_traders", 70)
        price_70 = calculate_fuel_price(state, system)
        assert price_50["faction_modifier"] == price_70["faction_modifier"]
        assert price_50["faction_modifier"] == -0.15

    def test_void_traders_negative_rep_no_discount(self) -> None:
        from backend.game.trading import calculate_fuel_price
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None

        state.modify_faction_reputation("void_traders", 0)
        price_neutral = calculate_fuel_price(state, system)

        state.modify_faction_reputation("void_traders", -50)
        price_hostile = calculate_fuel_price(state, system)

        assert price_neutral["faction_modifier"] == 0.0
        assert price_hostile["faction_modifier"] == 0.30

    def test_free_pilots_morale_on_sell(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.morale = 80
        state.modify_faction_reputation("free_pilots", 30)

        disc = Discovery(
            id="fp_morale", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        ok, _ = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        assert state.ship.morale > 80

    def test_free_pilots_morale_on_buy(self) -> None:
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.fuel = 0
        state.ship.credits = 5000
        state.ship.morale = 80
        state.modify_faction_reputation("free_pilots", 40)

        ok, _ = perform_trade(state, "buy", "fuel", 1)
        assert ok is True
        assert state.ship.morale > 80

    def test_free_pilots_morale_on_repair(self) -> None:
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.hull = 0
        state.ship.credits = 5000
        state.ship.morale = 80
        state.modify_faction_reputation("free_pilots", 10)

        ok, _ = perform_trade(state, "buy", "repair", 1)
        assert ok is True
        assert state.ship.morale > 80

    def test_free_pilots_morale_bonus_capped_at_50(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.morale = 90

        disc = Discovery(
            id="fp_cap", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        state.modify_faction_reputation("free_pilots", 50)
        ok, _ = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        morale_at_50 = state.ship.morale

        state.discoveries.append(disc)
        state.ship.morale = 90
        state.modify_faction_reputation("free_pilots", 60)
        ok, _ = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        morale_at_60 = state.ship.morale

        assert morale_at_50 == morale_at_60

    def test_free_pilots_no_rep_no_morale(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.morale = 80

        disc = Discovery(
            id="fp_none", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        ok, _ = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        assert state.ship.morale == 80

    def test_stellar_cartographers_bulk_sell_bonus(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True

        state.discoveries = [
            Discovery(id="bs1", category="mineral", name="Test Ore",
                       description="Ore", value=100, system_id=system.id),
            Discovery(id="bs2", category="artifact", name="Test Relic",
                       description="Relic", value=100, system_id=system.id),
        ]
        state.modify_faction_reputation("stellar_cartographers", 0)
        ok, _, _, price_no_rep = perform_bulk_sell(
            state, [{"item": "mineral", "quantity": 1}, {"item": "artifact", "quantity": 1}]
        )
        assert ok is True

        state.discoveries = [
            Discovery(id="bs3", category="mineral", name="Test Ore",
                       description="Ore", value=100, system_id=system.id),
            Discovery(id="bs4", category="artifact", name="Test Relic",
                       description="Relic", value=100, system_id=system.id),
        ]
        state.modify_faction_reputation("stellar_cartographers", 50)
        ok, _, _, price_with_rep = perform_bulk_sell(
            state, [{"item": "mineral", "quantity": 1}, {"item": "artifact", "quantity": 1}]
        )
        assert ok is True
        assert price_with_rep > price_no_rep


class TestReputationEventOutcomes:
    def test_stellar_cartographers_rep_bonus_on_exploration(self) -> None:
        from backend.generation.events import _create_event
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 25)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "exploration" and t["title"] == "Ancient Signal")
        event = _create_event(template, "sys_0000")
        state.events.append(event)
        credits_before = state.ship.credits
        morale_before = state.ship.morale

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        assert state.ship.credits > credits_before + 50  # +50 from signal + +10 from rep bonus
        assert state.ship.morale > morale_before  # morale from event + +1 from rep bonus

    def test_void_traders_rep_bonus_on_trade(self) -> None:
        from backend.generation.events import _create_event
        state = new_game(seed=42)
        state.modify_faction_reputation("void_traders", 25)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "trade" and t["title"] == "Passing Merchant")
        event = _create_event(template, "sys_0000")
        state.events.append(event)
        credits_before = state.ship.credits

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        assert state.ship.credits > credits_before + 150  # +150 from merchant + +10 bonus

    def test_free_pilots_rep_bonus_on_crisis(self) -> None:
        from backend.generation.events import _create_event
        state = new_game(seed=42)
        state.modify_faction_reputation("free_pilots", 25)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "crisis")
        event = _create_event(template, "sys_0000")
        state.events.append(event)
        morale_before = state.ship.morale

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        # Crisis event: hll:-20; fuel:-20 fixes life support. Morale should be boosted by +5 from rep
        assert state.ship.morale > morale_before + 5 - 25  # rough bound including event effects

    def test_free_pilots_rep_bonus_on_crew(self) -> None:
        from backend.generation.events import _create_event
        state = new_game(seed=42)
        state.modify_faction_reputation("free_pilots", 25)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "crew" and t["title"] == "Crew Dispute")
        event = _create_event(template, "sys_0000")
        state.events.append(event)
        morale_before = state.ship.morale

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        # Crew dispute: morale:15; fuel:-2 plus +5 morale from rep bonus
        assert state.ship.morale > morale_before

    def test_no_rep_bonus_below_20(self) -> None:
        from backend.generation.events import _create_event
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 15)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "exploration")
        event = _create_event(template, "sys_0000")
        state.events.append(event)

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True
        # Should not get the bonus credits (no +10), just the event outcome

    def test_reputation_change_log_entry(self) -> None:
        from backend.generation.events import _create_event
        state = new_game(seed=42)
        template = next(t for t in EVENT_TEMPLATES if t["type"] == "exploration")
        event = _create_event(template, "sys_0000")
        state.events.append(event)

        ok, msg, extra = resolve_event(state, event.id, 0)
        assert ok is True

        faction_logs = [e for e in state.log_entries if e["type"] == "faction"]
        assert len(faction_logs) >= 1
        assert any("Stellar Cartographers" in e["message"] for e in faction_logs)


class TestReputationEventThresholds:
    def test_min_reputation_condition_eligible(self) -> None:
        from backend.generation.events import _get_eligible_templates
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 25)
        rep_templates = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("min_reputation")]
        assert len(rep_templates) > 0
        eligible = _get_eligible_templates(state, rep_templates)
        assert len(eligible) > 0

    def test_min_reputation_condition_ineligible(self) -> None:
        from backend.generation.events import _get_eligible_templates
        state = new_game(seed=42)
        rep_templates = [t for t in EVENT_TEMPLATES if t.get("trigger_conditions", {}).get("min_reputation")]
        eligible = _get_eligible_templates(state, rep_templates)
        assert len(eligible) == 0

    def test_stellar_cartographers_restricted_coordinates_unlocked(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 25)
        template = next(t for t in EVENT_TEMPLATES if t["title"] == "Restricted Coordinates")
        from backend.generation.events import _create_event
        event = _create_event(template, "sys_0000")
        assert event is not None
        assert event.event_type == "exploration"

    def test_void_traders_black_market_unlocked(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("void_traders", 25)
        template = next(t for t in EVENT_TEMPLATES if t["title"] == "Black Market Access")
        from backend.generation.events import _create_event
        event = _create_event(template, "sys_0000")
        assert event is not None
        assert event.event_type == "trade"

    def test_free_pilots_crew_recruitment_unlocked(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("free_pilots", 25)
        template = next(t for t in EVENT_TEMPLATES if t["title"] == "Crew Recruitment Offer")
        from backend.generation.events import _create_event
        event = _create_event(template, "sys_0000")
        assert event is not None
        assert event.event_type == "crew"

    def test_allied_events_require_50_rep(self) -> None:
        from backend.generation.events import _get_eligible_templates
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 30)
        allied_templates = [
            t for t in EVENT_TEMPLATES
            if t.get("trigger_conditions", {}).get("min_reputation", {}).get("value") == 50
        ]
        eligible = _get_eligible_templates(state, allied_templates)
        assert len(eligible) == 0

    def test_allied_events_unlocked_at_50(self) -> None:
        from backend.generation.events import _get_eligible_templates
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 55)
        state.modify_faction_reputation("void_traders", 55)
        state.modify_faction_reputation("free_pilots", 55)
        allied_templates = [
            t for t in EVENT_TEMPLATES
            if t.get("trigger_conditions", {}).get("min_reputation", {}).get("value") == 50
        ]
        eligible = _get_eligible_templates(state, allied_templates)
        assert len(eligible) == 3


class TestReputationSummary:
    def test_reputation_summary_in_full_state(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "reputation_summary" in data
        assert "stellar_cartographers" in data["reputation_summary"]
        assert "void_traders" in data["reputation_summary"]
        assert "free_pilots" in data["reputation_summary"]

    def test_reputation_summary_neutral_label(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}")
        data = resp.json()
        for fid in ("stellar_cartographers", "void_traders", "free_pilots"):
            assert data["reputation_summary"][fid]["label"] == "Neutral"
            assert data["reputation_summary"][fid]["reputation"] == 0

    def test_reputation_summary_friendly_label(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 25)
        GAME_STORE[state.id] = state
        game_save(state)
        resp = client.get(f"/api/game/{state.id}")
        data = resp.json()
        assert data["reputation_summary"]["stellar_cartographers"]["label"] == "Friendly"

    def test_reputation_summary_allied_label(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("void_traders", 55)
        GAME_STORE[state.id] = state
        game_save(state)
        resp = client.get(f"/api/game/{state.id}")
        data = resp.json()
        assert data["reputation_summary"]["void_traders"]["label"] == "Allied"

    def test_reputation_summary_boundary_friendly_at_20(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("free_pilots", 20)
        GAME_STORE[state.id] = state
        game_save(state)
        resp = client.get(f"/api/game/{state.id}")
        data = resp.json()
        assert data["reputation_summary"]["free_pilots"]["label"] == "Friendly"

    def test_reputation_summary_boundary_allied_at_50(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 50)
        GAME_STORE[state.id] = state
        game_save(state)
        resp = client.get(f"/api/game/{state.id}")
        data = resp.json()
        assert data["reputation_summary"]["stellar_cartographers"]["label"] == "Allied"

    def test_full_state_response_unfriendly_label(self) -> None:
        """_full_state_response should show Unfriendly label for negative reputation."""
        from backend.api.routes import _full_state_response
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", -10)
        state.modify_faction_reputation("void_traders", -1)
        state.modify_faction_reputation("free_pilots", -19)
        resp = _full_state_response(state)
        rs = resp["reputation_summary"]
        assert rs["stellar_cartographers"]["label"] == "Unfriendly"
        assert rs["stellar_cartographers"]["reputation"] == -10
        assert rs["void_traders"]["label"] == "Unfriendly"
        assert rs["void_traders"]["reputation"] == -1
        assert rs["free_pilots"]["label"] == "Unfriendly"
        assert rs["free_pilots"]["reputation"] == -19

    def test_full_state_response_hostile_label(self) -> None:
        """_full_state_response should show Hostile label for very negative reputation."""
        from backend.api.routes import _full_state_response
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", -50)
        state.modify_faction_reputation("void_traders", -21)
        state.modify_faction_reputation("free_pilots", -1000)
        resp = _full_state_response(state)
        rs = resp["reputation_summary"]
        assert rs["stellar_cartographers"]["label"] == "Hostile"
        assert rs["stellar_cartographers"]["reputation"] == -50
        assert rs["void_traders"]["label"] == "Hostile"
        assert rs["void_traders"]["reputation"] == -21
        assert rs["free_pilots"]["label"] == "Hostile"
        assert rs["free_pilots"]["reputation"] == -1000

    def test_reputation_summary_negative_hostile(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("void_traders", -50)
        GAME_STORE[state.id] = state
        game_save(state)
        resp = client.get(f"/api/game/{state.id}")
        data = resp.json()
        assert data["reputation_summary"]["void_traders"]["label"] == "Hostile"

    def test_state_summary_includes_reputation_summary(self) -> None:
        state = new_game(seed=42)
        summary = state.state_summary()
        assert "reputation_summary" in summary
        for fid in ("stellar_cartographers", "void_traders", "free_pilots"):
            assert fid in summary["reputation_summary"]

    def test_state_summary_reputation_summary_values(self) -> None:
        state = new_game(seed=42)
        state.modify_faction_reputation("stellar_cartographers", 50)
        state.modify_faction_reputation("void_traders", 20)
        state.modify_faction_reputation("free_pilots", -21)
        summary = state.state_summary()
        rs = summary["reputation_summary"]
        assert rs["stellar_cartographers"]["reputation"] == 50
        assert rs["stellar_cartographers"]["label"] == "Allied"
        assert rs["void_traders"]["reputation"] == 20
        assert rs["void_traders"]["label"] == "Friendly"
        assert rs["free_pilots"]["reputation"] == -21
        assert rs["free_pilots"]["label"] == "Hostile"

    def test_rep_label_allied(self) -> None:
        assert _rep_label(50) == "Allied"
        assert _rep_label(100) == "Allied"

    def test_rep_label_friendly(self) -> None:
        assert _rep_label(20) == "Friendly"
        assert _rep_label(49) == "Friendly"

    def test_rep_label_neutral(self) -> None:
        assert _rep_label(0) == "Neutral"
        assert _rep_label(19) == "Neutral"

    def test_rep_label_unfriendly(self) -> None:
        assert _rep_label(-1) == "Unfriendly"
        assert _rep_label(-20) == "Unfriendly"

    def test_rep_label_hostile(self) -> None:
        assert _rep_label(-21) == "Hostile"
        assert _rep_label(-100) == "Hostile"
