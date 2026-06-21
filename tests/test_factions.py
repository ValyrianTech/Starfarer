import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import random
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game, game_save, game_load, _state_to_dict, _state_from_dict
from backend.models.game_state import GameState
from backend.models.faction import (
    Faction, FactionRelation, FACTION_DEFINITIONS, get_faction,
)
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
        state.faction_relations["stellar_cartographers"].reputation = 995
        state.modify_faction_reputation("stellar_cartographers", 50)
        assert state.faction_relations["stellar_cartographers"].reputation == 1000

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
    def test_void_traders_positive_reputation_discount(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("void_traders", 100)

        disc = Discovery(
            id="vt_test_disc", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits

        ok, msg = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        price_mod = 1.0 + (100 / 500.0)
        expected_min = int(100 * 0.7 * price_mod)
        expected_max = int(100 * 1.5 * price_mod)
        actual_credits = state.ship.credits - credits_before
        assert expected_min <= actual_credits <= expected_max

    def test_void_traders_negative_reputation_penalty(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("void_traders", -100)

        disc = Discovery(
            id="vt_neg_disc", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits

        ok, msg = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        price_mod = 1.0 + (-100 / 500.0)
        expected_min = int(100 * 0.7 * price_mod)
        expected_max = int(100 * 1.5 * price_mod)
        actual_credits = state.ship.credits - credits_before
        assert expected_min <= actual_credits <= expected_max

    def test_void_traders_faction_mod_clamped(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("void_traders", 500)

        disc = Discovery(
            id="vt_clamp_disc", category="artifact", name="Test Artifact",
            description="Test", value=100, system_id=system.id,
        )
        state.discoveries.append(disc)
        credits_before = state.ship.credits

        ok, msg = perform_trade(state, "sell", "artifact", 1)
        assert ok is True
        actual_credits = state.ship.credits - credits_before
        # faction_mod should be clamped to 1.2, so max is 100 * 1.5 * 1.2 = 180
        assert actual_credits <= int(100 * 1.5 * 1.2)

    def test_void_traders_no_effect_on_buy_fuel(self) -> None:
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.ship.fuel = 50
        state.modify_faction_reputation("void_traders", 100)
        credits_before = state.ship.credits

        ok, msg = perform_trade(state, "buy", "fuel", 10)
        assert ok is True
        assert state.ship.fuel > 50 or state.ship.credits < credits_before

    def test_void_traders_bulk_sell_faction_mod(self) -> None:
        from backend.models.discovery import Discovery
        state = new_game(seed=42)
        system = state.get_current_system()
        assert system is not None
        system.has_trading_station = True
        state.modify_faction_reputation("void_traders", -100)

        state.discoveries = [
            Discovery(id="bvt1", category="artifact", name="Ancient Relic",
                       description="Old relic", value=200, system_id=system.id),
        ]
        credits_before = state.ship.credits

        ok, msg, sold_count, total_price = perform_bulk_sell(
            state, [{"item": "artifact", "quantity": 1}]
        )
        assert ok is True
        actual_credits = total_price
        price_mod = 1.0 + (-100 / 500.0)
        expected_min = int(200 * 0.7 * price_mod)
        expected_max = int(200 * 1.5 * price_mod)
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
        from unittest.mock import MagicMock
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
