import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game, game_save, game_load
from backend.codex import BIOME_CODEX_DATA, get_codex
from backend.models.game_state import GameState

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db() -> None:
    init_db()


def _make_game(seed: int = 42) -> GameState:
    state = new_game(seed=seed)
    return state


class TestBiomeCodexData:
    def test_all_biomes_present(self) -> None:
        expected_ids = {"ocean", "jungle", "crystal", "volcanic", "desert", "tundra", "barren", "gas_giant"}
        actual_ids = {b["biome_id"] for b in BIOME_CODEX_DATA}
        assert actual_ids == expected_ids

    def test_biome_data_structure(self) -> None:
        for biome in BIOME_CODEX_DATA:
            assert "biome_id" in biome
            assert "name" in biome
            assert "description" in biome
            assert "value_rating" in biome
            assert "tier1_hint" in biome
            assert "common_discoveries" in biome
            assert isinstance(biome["value_rating"], int)
            assert 1 <= biome["value_rating"] <= 5
            assert isinstance(biome["common_discoveries"], list)
            assert len(biome["common_discoveries"]) == 3

    def test_biome_ids_unique(self) -> None:
        ids = [b["biome_id"] for b in BIOME_CODEX_DATA]
        assert len(ids) == len(set(ids))

    def test_value_ratings_valid(self) -> None:
        for biome in BIOME_CODEX_DATA:
            assert biome["value_rating"] in (1, 2, 3, 4, 5)


class TestGetCodex:
    def test_all_biomes_present_in_codex(self) -> None:
        state = _make_game()
        entries = get_codex(state)
        assert len(entries) == len(BIOME_CODEX_DATA)
        biome_ids = {e["biome_id"] for e in entries}
        expected_ids = {b["biome_id"] for b in BIOME_CODEX_DATA}
        assert biome_ids == expected_ids

    def test_no_biomes_unlocked_by_default(self) -> None:
        state = _make_game()
        entries = get_codex(state)
        for entry in entries:
            assert entry["unlocked"] is False
            assert entry["description"] == "???"
            assert entry["hint"] is not None

    def test_visited_biome_is_unlocked(self) -> None:
        state = _make_game()
        state.biomes_visited.add("jungle")
        entries = get_codex(state)
        jungle = [e for e in entries if e["biome_id"] == "jungle"][0]
        assert jungle["unlocked"] is True
        assert jungle["description"] != "???"
        assert jungle["hint"] is not None

    def test_unvisited_biome_remains_locked(self) -> None:
        state = _make_game()
        state.biomes_visited.add("jungle")
        entries = get_codex(state)
        ocean = [e for e in entries if e["biome_id"] == "ocean"][0]
        assert ocean["unlocked"] is False
        assert ocean["description"] == "???"
        assert ocean["hint"] is not None

    def test_tier1_scanner_0_or_above(self) -> None:
        state = _make_game()
        state.ship.scanner = 0
        entries = get_codex(state)
        for entry in entries:
            assert "name" in entry
            assert "description" in entry
            assert "hint" in entry

    def test_tier2_value_ratings_with_scanner_1(self) -> None:
        state = _make_game()
        state.ship.scanner = 1
        entries = get_codex(state)
        for entry in entries:
            assert entry["value_rating"] is not None
            assert isinstance(entry["value_rating"], int)

    def test_tier2_value_ratings_hidden_scanner_0(self) -> None:
        state = _make_game()
        state.ship.scanner = 0
        entries = get_codex(state)
        for entry in entries:
            assert entry["value_rating"] is None

    def test_tier3_discoveries_with_scanner_2_and_unlocked(self) -> None:
        state = _make_game()
        state.ship.scanner = 2
        state.biomes_visited.add("jungle")
        entries = get_codex(state)
        jungle = [e for e in entries if e["biome_id"] == "jungle"][0]
        assert len(jungle["common_discoveries"]) == 3

    def test_tier3_discoveries_hidden_when_locked(self) -> None:
        state = _make_game()
        state.ship.scanner = 2
        entries = get_codex(state)
        for entry in entries:
            if not entry["unlocked"]:
                assert entry["common_discoveries"] == []

    def test_tier3_discoveries_hidden_scanner_1(self) -> None:
        state = _make_game()
        state.ship.scanner = 1
        state.biomes_visited.add("jungle")
        entries = get_codex(state)
        jungle = [e for e in entries if e["biome_id"] == "jungle"][0]
        assert jungle["common_discoveries"] == []

    def test_tier3_discoveries_hidden_scanner_0(self) -> None:
        state = _make_game()
        state.ship.scanner = 0
        state.biomes_visited.add("jungle")
        entries = get_codex(state)
        jungle = [e for e in entries if e["biome_id"] == "jungle"][0]
        assert jungle["common_discoveries"] == []

    def test_scanner_level_3_shows_all(self) -> None:
        state = _make_game()
        state.ship.scanner = 3
        state.biomes_visited.add("ocean")
        state.biomes_visited.add("desert")
        entries = get_codex(state)
        ocean = [e for e in entries if e["biome_id"] == "ocean"][0]
        desert = [e for e in entries if e["biome_id"] == "desert"][0]
        assert ocean["value_rating"] is not None
        assert desert["value_rating"] is not None
        assert len(ocean["common_discoveries"]) == 3
        assert len(desert["common_discoveries"]) == 3

    def test_initial_scanner_is_1(self) -> None:
        state = _make_game()
        assert state.ship.scanner == 1
        entries = get_codex(state)
        for entry in entries:
            assert entry["value_rating"] is not None


class TestRecordBiomeVisit:
    def test_record_biome_visit_adds_to_set(self) -> None:
        state = _make_game()
        assert state.biomes_visited == set()
        state.record_biome_visit("jungle")
        assert "jungle" in state.biomes_visited

    def test_record_biome_visit_multiple(self) -> None:
        state = _make_game()
        state.record_biome_visit("jungle")
        state.record_biome_visit("desert")
        state.record_biome_visit("ocean")
        assert state.biomes_visited == {"jungle", "desert", "ocean"}

    def test_record_biome_visit_duplicate_noop(self) -> None:
        state = _make_game()
        state.record_biome_visit("jungle")
        state.record_biome_visit("jungle")
        assert state.biomes_visited == {"jungle"}


class TestBiomesVisitedFieldDefault:
    def test_new_game_biomes_visited_empty(self) -> None:
        state = _make_game()
        assert state.biomes_visited == set()
        assert isinstance(state.biomes_visited, set)


class TestCodexAPI:
    def test_api_codex_200(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp2 = client.get(f"/api/game/{game_id}/codex")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["game_id"] == game_id
        assert "codex" in data
        assert len(data["codex"]) == len(BIOME_CODEX_DATA)

    def test_api_codex_404(self) -> None:
        resp = client.get("/api/game/nonexistent/codex")
        assert resp.status_code == 404

    def test_api_codex_reflects_biome_visits(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.biomes_visited.add("jungle")
        resp2 = client.get(f"/api/game/{game_id}/codex")
        data = resp2.json()
        jungle = [e for e in data["codex"] if e["biome_id"] == "jungle"][0]
        assert jungle["unlocked"] is True

    def test_api_codex_reflects_scanner_level(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.ship.scanner = 0
        resp2 = client.get(f"/api/game/{game_id}/codex")
        data = resp2.json()
        for entry in data["codex"]:
            assert entry["value_rating"] is None


class TestExploreRecordsBiome:
    def _get_or_create_body_with_poi(self, state: GameState):
        """Find or create a body with poi_count > 0 in the current system."""
        from backend.models.system import Body

        current = state.get_current_system()
        for body in current.bodies:
            if body.poi_count > 0:
                return body

        # No body with POI found — create one so we don't need fallback logic
        body = Body(
            id="test-body-poi",
            name="Test Planet",
            body_type="planet",
            biome="jungle",
            size=3,
            distance_from_star=1.0,
            poi_count=3,
        )
        current.bodies.append(body)
        return body

    def test_explore_records_biome_visit(self) -> None:
        from backend.game.engine import explore_surface

        state = _make_game()
        target_body = self._get_or_create_body_with_poi(state)

        state.ship.current_body_id = target_body.id
        assert target_body.biome not in state.biomes_visited

        explore_surface(state)

        assert target_body.biome in state.biomes_visited

    def test_biome_visit_recorded_via_endpoint(self) -> None:
        from backend.database import init_db
        init_db()

        state = _make_game()
        target_body = self._get_or_create_body_with_poi(state)

        GAME_STORE[state.id] = state
        state.ship.current_body_id = target_body.id

        assert target_body.biome not in state.biomes_visited

        resp = client.post(f"/api/game/{state.id}/explore")
        assert resp.status_code == 200

        assert target_body.biome in state.biomes_visited

    def test_explore_does_not_record_empty_biome(self) -> None:
        from backend.game.engine import explore_surface

        state = _make_game()
        target_body = self._get_or_create_body_with_poi(state)

        target_body.biome = ""
        state.ship.current_body_id = target_body.id

        assert state.biomes_visited == set()

        explore_surface(state)

        assert state.biomes_visited == set()

    def test_get_or_create_body_creates_when_no_poi(self) -> None:
        state = _make_game()
        current = state.get_current_system()

        # Remove POI from all bodies to force creation fallback
        for body in current.bodies:
            body.poi_count = 0

        target_body = self._get_or_create_body_with_poi(state)

        assert target_body.id == "test-body-poi"
        assert target_body.poi_count == 3
        assert target_body in current.bodies

    def test_explore_does_not_record_none_biome(self) -> None:
        from backend.game.engine import explore_surface

        state = _make_game()
        target_body = self._get_or_create_body_with_poi(state)

        target_body.biome = None
        state.ship.current_body_id = target_body.id

        assert state.biomes_visited == set()

        explore_surface(state)

        assert state.biomes_visited == set()


class TestBiomesVisitedSerialization:
    def test_roundtrip_preserves_biomes_visited(self) -> None:
        from backend.database import init_db
        init_db()

        state = _make_game()
        state.biomes_visited.add("jungle")
        state.biomes_visited.add("desert")

        game_save(state)
        loaded = game_load(state.id)
        assert loaded is not None
        assert "jungle" in loaded.biomes_visited
        assert "desert" in loaded.biomes_visited

    def test_biomes_visited_in_state_to_dict(self) -> None:
        from backend.game.manager import _state_to_dict, _state_from_dict

        state = _make_game()
        state.biomes_visited.add("ocean")
        state.biomes_visited.add("tundra")

        d = _state_to_dict(state)
        assert "biomes_visited" in d
        assert isinstance(d["biomes_visited"], list)
        assert set(d["biomes_visited"]) == {"ocean", "tundra"}

        restored = _state_from_dict(d)
        assert "ocean" in restored.biomes_visited
        assert "tundra" in restored.biomes_visited

    def test_empty_biomes_visited_roundtrip(self) -> None:
        from backend.game.manager import _state_to_dict, _state_from_dict

        state = _make_game()
        d = _state_to_dict(state)
        restored = _state_from_dict(d)
        assert restored.biomes_visited == set()

    def test_old_save_without_biomes_visited(self) -> None:
        from backend.game.manager import _state_to_dict, _state_from_dict

        state = _make_game()
        d = _state_to_dict(state)
        del d["biomes_visited"]
        restored = _state_from_dict(d)
        assert restored.biomes_visited == set()


class TestGameStateResponseIncludesBiomesVisited:
    def test_game_state_response_includes_biomes_visited(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        state = GAME_STORE[game_id]
        state.biomes_visited.add("jungle")

        resp2 = client.get(f"/api/game/{game_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert "biomes_visited" in data
        assert "biomes_visited_count" in data
        assert data["biomes_visited"] == ["jungle"]
        assert data["biomes_visited_count"] == 1

    def test_game_state_summary_includes_biomes_visited(self) -> None:
        state = _make_game()
        state.biomes_visited.add("desert")
        summary = state.state_summary()
        assert "biomes_visited" in summary
        assert "biomes_visited_count" in summary
        assert summary["biomes_visited_count"] == 1
        assert "desert" in summary["biomes_visited"]
