import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.generation.universe import generate_universe, distance_between, _ensure_connectivity, NEIGHBOR_DISTANCE_THRESHOLD
from backend.models.system import StarSystem, Body
from backend.models.ship import Ship
from backend.models.game_state import GameState
from backend.models.event import Event, Choice
from backend.models.discovery import Discovery, LoreFragment
from backend.config import GALAXY_SYSTEM_COUNT
from backend.game.manager import new_game, _fixup_old_lore_fragment_numbers, _state_from_dict
import random


class TestUniverseGeneration:
    def test_generates_correct_number_of_systems(self) -> None:
        systems, lore = generate_universe(42)
        assert len(systems) == GALAXY_SYSTEM_COUNT
        assert len(lore) == 20

    def test_deterministic(self) -> None:
        s1, l1 = generate_universe(42)
        s2, l2 = generate_universe(42)
        assert set(s1.keys()) == set(s2.keys())
        for k in s1:
            assert s1[k].name == s2[k].name
            assert s1[k].x == s2[k].x
            assert s1[k].y == s2[k].y
            assert s1[k].star_type == s2[k].star_type

    def test_different_seeds_different_universes(self) -> None:
        s1, l1 = generate_universe(42)
        s2, l2 = generate_universe(99)

        def names(d: dict[str, StarSystem]) -> set[str]:
            return {s.name for s in d.values()}

        assert len(names(s1) & names(s2)) < 40

    def test_each_system_has_bodies(self) -> None:
        systems, lore = generate_universe(42)
        for system in systems.values():
            assert len(system.bodies) >= 1
            assert len(system.bodies) <= 20

    def test_each_system_has_valid_star_type(self) -> None:
        from backend.config import STAR_SPECTRAL_TYPES
        systems, lore = generate_universe(42)
        for system in systems.values():
            assert system.star_type in STAR_SPECTRAL_TYPES

    def test_bodies_have_valid_biomes(self) -> None:
        from backend.config import BIOME_TYPES
        systems, lore = generate_universe(42)
        for system in systems.values():
            for body in system.bodies:
                assert body.biome in BIOME_TYPES or body.body_type == "asteroid_belt"

    def test_distance_calculation(self) -> None:
        a = StarSystem(id="a", name="A", x=0, y=0, star_type="G", star_color="#fff",
                       phenomenon="none", phenomenon_desc="")
        b = StarSystem(id="b", name="B", x=30, y=40, star_type="K", star_color="#ffa",
                       phenomenon="none", phenomenon_desc="")
        d = distance_between(a, b)
        assert d == 50.0

    def test_body_name_unknown_type(self) -> None:
        """_generate_body_name should return a fallback name for unknown body types."""
        from backend.generation.universe import _generate_body_name
        rng = random.Random(42)
        name = _generate_body_name(rng, "UnknownType", 0, "Planet")
        assert isinstance(name, str)

    def test_biome_for_body_outer_orbit(self) -> None:
        """_biome_for_body should handle distance >= 1.0 (outer orbit)."""
        from backend.generation.universe import _biome_for_body
        rng = random.Random(42)
        biome = _biome_for_body(rng, "G", 1.5, "planet")
        assert biome in ("gas_giant", "tundra", "barren")

    def test_biome_for_body_gas_giant_path(self) -> None:
        """_biome_for_body should return gas_giant when rng.random() < 0.15."""
        from backend.generation.universe import _biome_for_body
        import unittest.mock as mock
        # Force the gas_giant branch by patching rng.random to return 0.1 (< 0.15)
        with mock.patch.object(random.Random, 'random', return_value=0.1):
            rng = random.Random(0)
            biome = _biome_for_body(rng, "G", 1.5, "planet")
            assert biome == "gas_giant"

    def test_biome_for_body_moon(self) -> None:
        """_biome_for_body should return a biome from the first 5 for moons."""
        from backend.generation.universe import _biome_for_body
        from backend.config import BIOME_TYPES
        rng = random.Random(42)
        biome = _biome_for_body(rng, "G", 0.5, "moon")
        assert biome in BIOME_TYPES[:5]

    def test_biome_for_body_asteroid(self) -> None:
        """_biome_for_body should return barren for asteroid belts."""
        from backend.generation.universe import _biome_for_body
        rng = random.Random(42)
        biome = _biome_for_body(rng, "G", 0.5, "asteroid_belt")
        assert biome == "barren"

    def test_body_description_valid(self) -> None:
        """_body_description should return a string for all known biomes."""
        from backend.generation.universe import _body_description
        from backend.config import BIOME_TYPES
        rng = random.Random(42)
        for biome in BIOME_TYPES:
            desc = _body_description(rng, "planet", biome, "G")
            assert isinstance(desc, str)
            assert len(desc) > 0


    def test_ensure_connectivity_single_pass(self) -> None:
        """_ensure_connectivity fixes a basic isolated system in one pass."""
        rng = random.Random(42)
        a = StarSystem(id="a", name="A", x=500, y=500, star_type="G",
                       star_color="#fff", phenomenon="none", phenomenon_desc="")
        b = StarSystem(id="b", name="B", x=565, y=500, star_type="K",
                       star_color="#ffa", phenomenon="none", phenomenon_desc="")
        systems = {"a": a, "b": b}

        _ensure_connectivity(systems, rng)

        assert distance_between(a, b) <= NEIGHBOR_DISTANCE_THRESHOLD

    def test_ensure_connectivity_multi_pass(self) -> None:
        """Fixing one isolated system creates another, requiring a second pass.

        Layout: A(500,500), B(565,500), C(565,560)
        - A-B = 65 > 60, A isolated
        - B-C = 60, B and C are neighbors

        Pass 1: A isolated, closest=B at 65. A moves toward B to (555,500).
                Now A-B = 10 ≤ 60, B-C = 60 ≤ 60. All connected.
        """
        rng = random.Random(42)
        a = StarSystem(id="a", name="A", x=500, y=500, star_type="G",
                       star_color="#fff", phenomenon="none", phenomenon_desc="")
        b = StarSystem(id="b", name="B", x=565, y=500, star_type="K",
                       star_color="#ffa", phenomenon="none", phenomenon_desc="")
        c = StarSystem(id="c", name="C", x=565, y=560, star_type="M",
                       star_color="#f00", phenomenon="none", phenomenon_desc="")
        systems = {"a": a, "b": b, "c": c}

        _ensure_connectivity(systems, rng)

        assert distance_between(a, b) <= NEIGHBOR_DISTANCE_THRESHOLD
        assert distance_between(b, c) <= NEIGHBOR_DISTANCE_THRESHOLD

    def test_ensure_connectivity_same_coordinates(self) -> None:
        """_ensure_connectivity handles systems that start at the same coordinates.

        When two systems share the same coordinates, they are already neighbors
        (distance 0 <= NEIGHBOR_DISTANCE_THRESHOLD). This test verifies that
        _ensure_connectivity correctly identifies them as connected and does not
        attempt to move them, while still connecting any truly isolated systems.
        """
        rng = random.Random(42)
        # A and B are at the same coordinates (500, 500) — they are neighbors
        # C is far away at (1000, 1000) — C is isolated
        a = StarSystem(id="a", name="A", x=500, y=500, star_type="G",
                       star_color="#fff", phenomenon="none", phenomenon_desc="")
        b = StarSystem(id="b", name="B", x=500, y=500, star_type="K",
                       star_color="#ffa", phenomenon="none", phenomenon_desc="")
        c = StarSystem(id="c", name="C", x=1000, y=1000, star_type="M",
                       star_color="#f00", phenomenon="none", phenomenon_desc="")
        systems = {"a": a, "b": b, "c": c}

        _ensure_connectivity(systems, rng)

        # After the fix, all systems should have a neighbor within threshold
        for system in systems.values():
            has_neighbor = False
            for other in systems.values():
                if system.id == other.id:
                    continue
                if distance_between(system, other) <= NEIGHBOR_DISTANCE_THRESHOLD:
                    has_neighbor = True
                    break
            assert has_neighbor, f"System {system.id} ({system.name}) has no neighbor"

    def test_ensure_connectivity_moves_isolated_system(self) -> None:
        """The isolated system moves toward its closest neighbor (not vice versa)."""
        rng = random.Random(42)
        # A is isolated (distance 65 > 60), B has no other neighbor
        a = StarSystem(id="a", name="A", x=500, y=500, star_type="G",
                       star_color="#fff", phenomenon="none", phenomenon_desc="")
        b = StarSystem(id="b", name="B", x=565, y=500, star_type="K",
                       star_color="#ffa", phenomenon="none", phenomenon_desc="")
        orig_a_x, orig_a_y = a.x, a.y
        orig_b_x, orig_b_y = b.x, b.y

        _ensure_connectivity({"a": a, "b": b}, rng)

        # A (isolated) should have moved toward B
        assert a.x != orig_a_x or a.y != orig_a_y, "Isolated system A should have moved"
        # B (neighbor) should NOT have moved
        assert b.x == orig_b_x and b.y == orig_b_y, "Neighbor B should NOT have moved"
        # After the fix, A and B should be within threshold
        assert distance_between(a, b) <= NEIGHBOR_DISTANCE_THRESHOLD

    def test_ensure_connectivity_three_isolated_systems(self) -> None:
        """Three isolated systems where two share the same closest neighbor.

        A(500,500), B(565,500), C(500,565)
        - All three are isolated from each other (all distances > 60)
        - A and C both have B as their closest neighbor initially
        - Processing A first moves it toward B, making A non-isolated
        - C's closest neighbor is now A (not B), so C moves toward A
        - After both moves, all three systems are connected
        """
        rng = random.Random(42)
        # A and C are both isolated from B (distance 65 > 60)
        # B is the closest neighbor for both A and C
        a = StarSystem(id="a", name="A", x=500, y=500, star_type="G",
                       star_color="#fff", phenomenon="none", phenomenon_desc="")
        b = StarSystem(id="b", name="B", x=565, y=500, star_type="K",
                       star_color="#ffa", phenomenon="none", phenomenon_desc="")
        c = StarSystem(id="c", name="C", x=500, y=565, star_type="M",
                       star_color="#f00", phenomenon="none", phenomenon_desc="")
        orig_b_x, orig_b_y = b.x, b.y

        _ensure_connectivity({"a": a, "b": b, "c": c}, rng)

        # B should NOT have moved (it's the neighbor, not the isolated system)
        assert b.x == orig_b_x and b.y == orig_b_y, "Neighbor B should NOT have moved"
        # Both A and C should now be within threshold of B
        assert distance_between(a, b) <= NEIGHBOR_DISTANCE_THRESHOLD, "A should be connected to B"
        assert distance_between(c, b) <= NEIGHBOR_DISTANCE_THRESHOLD, "C should be connected to B"

    def test_ensure_connectivity_exhausts_iters_fallback(self, caplog) -> None:
        """When max_iters is exhausted, the else block should log a warning and
        move isolated systems directly to within threshold distance."""
        import logging
        import unittest.mock as mock
        caplog.set_level(logging.WARNING)
        rng = random.Random(42)
        # Two systems extremely far apart - the ratio-based movement can't
        # close this gap in 100 iterations.  Patch galaxy bounds to prevent
        # clamping from bringing them within range.
        a = StarSystem(id="a", name="Alpha", x=50, y=50, star_type="G",
                       star_color="#fff", phenomenon="none", phenomenon_desc="")
        b = StarSystem(id="b", name="Beta", x=50000, y=50000, star_type="K",
                       star_color="#ffa", phenomenon="none", phenomenon_desc="")
        systems = {"a": a, "b": b}

        with mock.patch("backend.generation.universe.GALAXY_WIDTH", 1000000), \
             mock.patch("backend.generation.universe.GALAXY_HEIGHT", 1000000):
            _ensure_connectivity(systems, rng)

        # After the fallback, both systems should be within threshold
        assert distance_between(a, b) <= NEIGHBOR_DISTANCE_THRESHOLD, \
            "Fallback should move isolated system to within threshold"
        # The warning should have been logged
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("was isolated after 100 iterations; fallback repositioning applied." in msg for msg in warning_messages), \
            f"Expected warning about isolated system, got: {warning_messages}"

    def test_ensure_connectivity_exhausts_iters_multiple_isolated(self, caplog) -> None:
        """When multiple systems remain isolated after max_iters, each should
        get a warning and be moved to within threshold."""
        import logging
        import unittest.mock as mock
        caplog.set_level(logging.WARNING)
        rng = random.Random(42)
        # One central system and two extremely far away.  Patch galaxy bounds
        # to prevent clamping from bringing them within range.
        center = StarSystem(id="c", name="Center", x=500, y=500, star_type="G",
                            star_color="#fff", phenomenon="none", phenomenon_desc="")
        far1 = StarSystem(id="f1", name="FarOne", x=50000, y=50000, star_type="K",
                          star_color="#ffa", phenomenon="none", phenomenon_desc="")
        far2 = StarSystem(id="f2", name="FarTwo", x=100, y=51000, star_type="M",
                          star_color="#f00", phenomenon="none", phenomenon_desc="")
        systems = {"c": center, "f1": far1, "f2": far2}

        with mock.patch("backend.generation.universe.GALAXY_WIDTH", 1000000), \
             mock.patch("backend.generation.universe.GALAXY_HEIGHT", 1000000):
            _ensure_connectivity(systems, rng)

        # All systems should now be within threshold of at least one other
        for system in systems.values():
            has_neighbor = any(
                distance_between(system, other) <= NEIGHBOR_DISTANCE_THRESHOLD
                for other in systems.values()
                if other.id != system.id
            )
            assert has_neighbor, f"System {system.id} ({system.name}) still has no neighbor after fallback"
        # Should have logged warnings for both isolated systems
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_messages) >= 2, \
            f"Expected at least 2 warnings, got {len(warning_messages)}: {warning_messages}"


class TestShipModel:
    def test_ship_creation(self) -> None:
        ship = Ship()
        assert ship.name == "Serendipity"
        assert ship.fuel == 80
        assert ship.hull == 100
        assert ship.credits == 1000

    def test_ship_to_dict_and_back(self) -> None:
        ship = Ship(name="Test", fuel=50, credits=500, current_system_id="sys_1")
        d = ship.to_dict()
        restored = Ship.from_dict(d)
        assert restored.name == "Test"
        assert restored.fuel == 50
        assert restored.credits == 500
        assert restored.current_system_id == "sys_1"


class TestGameState:
    def test_state_creation(self) -> None:
        ship = Ship()
        state = GameState(id="test-1", seed=42, ship=ship)
        assert state.id == "test-1"
        assert state.seed == 42
        assert state.ship.name == "Serendipity"

    def test_add_log(self) -> None:
        ship = Ship()
        state = GameState(id="test-2", seed=42, ship=ship)
        state.add_log("test", "Test message")
        assert len(state.log_entries) == 1
        assert state.log_entries[0]["type"] == "test"
        assert state.log_entries[0]["message"] == "Test message"
        assert state.log_entries[0]["id"] == 1

    def test_add_log_id_starts_at_1(self) -> None:
        ship = Ship()
        state = GameState(id="test-2b", seed=42, ship=ship)
        state.add_log("test", "First entry")
        assert state.log_entries[0]["id"] == 1

    def test_add_log_id_persists_across_save_load(self) -> None:
        from backend.game.manager import _state_to_dict, _state_from_dict

        ship = Ship()
        state = GameState(id="test-persist", seed=42, ship=ship)
        state.add_log("test", "Entry 1")
        state.add_log("test", "Entry 2")
        state.add_log("test", "Entry 3")

        assert len(state.log_entries) == 3
        assert state.log_entries[0]["id"] == 1
        assert state.log_entries[1]["id"] == 2
        assert state.log_entries[2]["id"] == 3

        d = _state_to_dict(state)
        restored = _state_from_dict(d)

        restored.add_log("test", "Entry 4")
        restored.add_log("test", "Entry 5")

        assert len(restored.log_entries) == 5
        assert restored.log_entries[3]["id"] == 4
        assert restored.log_entries[4]["id"] == 5

    def test_apply_choice_outcome(self) -> None:
        ship = Ship(fuel=50, max_fuel=100)
        state = GameState(id="test-3", seed=42, ship=ship)
        effects = state.apply_choice_outcome("fuel:-10; credits:100")
        assert effects["fuel"] == -10
        assert effects["credits"] == 100
        assert state.ship.fuel == 40
        assert state.ship.credits == 1100

    def test_apply_choice_outcome_clamping(self) -> None:
        ship = Ship(fuel=5, hull=90)
        state = GameState(id="test-4", seed=42, ship=ship)
        state.apply_choice_outcome("fuel:-20")
        assert state.ship.fuel == 0

        state.apply_choice_outcome("hull:50")
        assert state.ship.hull == 100

    def test_apply_choice_outcome_morale(self) -> None:
        """apply_choice_outcome should parse and apply morale changes."""
        ship = Ship(morale=50)
        state = GameState(id="test-m", seed=42, ship=ship)
        effects = state.apply_choice_outcome("morale:20")
        assert effects["morale"] == 20
        assert state.ship.morale == 70

    def test_apply_choice_outcome_cargo(self) -> None:
        """apply_choice_outcome should parse and apply cargo changes."""
        ship = Ship(cargo=10, max_cargo=50)
        state = GameState(id="test-c", seed=42, ship=ship)
        effects = state.apply_choice_outcome("cargo:5")
        assert effects["cargo"] == 5
        assert state.ship.cargo == 15

    def test_apply_choice_outcome_crew(self) -> None:
        """apply_choice_outcome should parse and apply crew changes."""
        ship = Ship(crew=5, max_crew=10)
        state = GameState(id="test-crew", seed=42, ship=ship)
        effects = state.apply_choice_outcome("crew:-1")
        assert effects["crew"] == -1
        assert state.ship.crew == 4

    def test_apply_choice_outcome_multiple_stats(self) -> None:
        """apply_choice_outcome with all stat types should apply all effects."""
        ship = Ship(fuel=50, hull=50, morale=50, credits=500, cargo=10, crew=50, max_fuel=100, max_hull=100, max_cargo=50, max_crew=100)
        state = GameState(id="test-all", seed=42, ship=ship)
        effects = state.apply_choice_outcome("fuel:-10; hull:10; morale:5; credits:200; cargo:-2; crew:-1")
        assert effects["fuel"] == -10
        assert effects["hull"] == 10
        assert effects["morale"] == 5
        assert effects["credits"] == 200
        assert effects["cargo"] == -2
        assert effects["crew"] == -1
        assert state.ship.fuel == 40
        assert state.ship.hull == 60
        assert state.ship.morale == 55
        assert state.ship.credits == 700
        assert state.ship.cargo == 8
        assert state.ship.crew == 49

    def test_apply_choice_outcome_clamping_max_min(self) -> None:
        """apply_choice_outcome should clamp stats to min/max bounds."""
        ship = Ship(fuel=5, hull=95, morale=5, credits=10, cargo=0, crew=5, max_fuel=100, max_hull=100, max_cargo=50, max_crew=10)
        state = GameState(id="test-clamp", seed=42, ship=ship)
        state.apply_choice_outcome("fuel:-20; hull:20; morale:-10; credits:-50; cargo:-10; crew:-60")
        assert state.ship.fuel == 0
        assert state.ship.hull == 100
        assert state.ship.morale == 0
        assert state.ship.credits == 0
        assert state.ship.cargo == 0
        assert state.ship.crew == 0

        state.apply_choice_outcome("crew:200")
        assert state.ship.crew == state.ship.max_crew

    def test_apply_choice_outcome_warns_on_narrative_text(self, caplog) -> None:
        """apply_choice_outcome should warn about narrative text in outcome."""
        import logging
        caplog.set_level(logging.WARNING)
        ship = Ship(fuel=50, max_fuel=100)
        state = GameState(id="test-warn-narr", seed=42, ship=ship)
        effects = state.apply_choice_outcome("credits:50; fuel:-5; Discovered a hidden data cache.")
        assert effects["credits"] == 50
        assert effects["fuel"] == -5
        assert state.ship.credits == 1050
        assert state.ship.fuel == 45
        # Should have warned about the narrative part
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Discovered a hidden data cache" in msg for msg in warning_messages)

    def test_apply_choice_outcome_warns_on_typo(self, caplog) -> None:
        """apply_choice_outcome should warn about typos in stat names."""
        import logging
        caplog.set_level(logging.WARNING)
        ship = Ship(credits=500)
        state = GameState(id="test-warn-typo", seed=42, ship=ship)
        effects = state.apply_choice_outcome("credtis:50")
        assert effects["credits"] == 0  # No credits change since typo wasn't recognized
        assert state.ship.credits == 500
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("credtis:50" in msg for msg in warning_messages)

    def test_apply_choice_outcome_warns_on_unknown_stat(self, caplog) -> None:
        """apply_choice_outcome should warn about unknown stat prefixes."""
        import logging
        caplog.set_level(logging.WARNING)
        ship = Ship()
        state = GameState(id="test-warn-unknown", seed=42, ship=ship)
        effects = state.apply_choice_outcome("scanner:1; credits:50")
        assert effects["credits"] == 50
        assert effects["fuel"] == 0
        assert state.ship.credits == 1050
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("scanner:1" in msg for msg in warning_messages)
        # No warning for valid stat
        assert not any("credits:50" in msg for msg in warning_messages)

    def test_apply_choice_outcome_no_warning_on_valid_stats(self, caplog) -> None:
        """apply_choice_outcome should NOT warn when all parts are valid stats."""
        import logging
        caplog.set_level(logging.WARNING)
        ship = Ship(fuel=50, hull=50, morale=50, credits=500, cargo=10, crew=5, max_fuel=100, max_hull=100, max_cargo=50, max_crew=10)
        state = GameState(id="test-no-warn", seed=42, ship=ship)
        effects = state.apply_choice_outcome("fuel:-10; hull:10; morale:5; credits:200; cargo:-2; crew:-1")
        assert effects["fuel"] == -10
        assert effects["hull"] == 10
        assert effects["morale"] == 5
        assert effects["credits"] == 200
        assert effects["cargo"] == -2
        assert effects["crew"] == -1
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_messages) == 0, f"Expected no warnings but got: {warning_messages}"

    def test_apply_choice_outcome_warns_on_multiple_unrecognized_parts(self, caplog) -> None:
        """apply_choice_outcome should warn for each unrecognized part."""
        import logging
        caplog.set_level(logging.WARNING)
        ship = Ship()
        state = GameState(id="test-warn-multi", seed=42, ship=ship)
        effects = state.apply_choice_outcome("credits:50; Some narrative; scanner:1; Another note")
        assert effects["credits"] == 50
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_messages) == 3, f"Expected 3 warnings but got {len(warning_messages)}: {warning_messages}"
        assert any("Some narrative" in msg for msg in warning_messages)
        assert any("scanner:1" in msg for msg in warning_messages)
        assert any("Another note" in msg for msg in warning_messages)


class TestEventModel:
    def test_event_to_dict_and_back(self) -> None:
        choices = [Choice(text="Do A", outcome="credits:50"), Choice(text="Do B", outcome="hull:-10")]
        event = Event(id="evt_1", title="Test Event", flavor="Something happened",
                      event_type="exploration", choices=choices, system_id="sys_1")
        d = event.to_dict()
        restored = Event.from_dict(d)
        assert restored.id == "evt_1"
        assert restored.title == "Test Event"
        assert len(restored.choices) == 2
        assert restored.choices[0].text == "Do A"

    def test_event_category_default_none(self) -> None:
        """Event category should default to None when not provided."""
        event = Event(id="evt_1", title="Test", flavor="...", event_type="exploration")
        assert event.category is None

    def test_event_category_explicit(self) -> None:
        """Event category should be set when provided."""
        event = Event(id="evt_1", title="Test", flavor="...", event_type="crisis", category="crisis")
        assert event.category == "crisis"

    def test_event_to_dict_includes_category(self) -> None:
        """to_dict should include the category field."""
        event = Event(id="evt_1", title="Test", flavor="...", event_type="crisis", category="crisis")
        d = event.to_dict()
        assert d["category"] == "crisis"

    def test_event_to_dict_category_none(self) -> None:
        """to_dict should include category=None when not set."""
        event = Event(id="evt_1", title="Test", flavor="...", event_type="exploration")
        d = event.to_dict()
        assert "category" in d
        assert d["category"] is None

    def test_event_from_dict_restores_category(self) -> None:
        """from_dict should restore the category field."""
        d = {
            "id": "evt_1",
            "title": "Test",
            "flavor": "...",
            "event_type": "crisis",
            "category": "crisis",
            "choices": [],
            "resolved": False,
            "chosen": None,
            "system_id": "",
        }
        event = Event.from_dict(d)
        assert event.category == "crisis"

    def test_event_from_dict_category_missing(self) -> None:
        """from_dict should default category to None when key is missing."""
        d = {
            "id": "evt_1",
            "title": "Test",
            "flavor": "...",
            "event_type": "exploration",
            "choices": [],
        }
        event = Event.from_dict(d)
        assert event.category is None

    def test_create_event_with_category(self) -> None:
        """_create_event should propagate category from template to Event."""
        from backend.generation.events import _create_event
        template = {
            "type": "crisis",
            "category": "crisis",
            "title": "Test Crisis",
            "flavor": "A crisis occurs.",
            "choices": [{"text": "Fix it", "outcome": "hull:-10"}],
        }
        event = _create_event(template, "sys_1")
        assert event.category == "crisis"

    def test_create_event_without_category(self) -> None:
        """_create_event should set category=None when template has no category key."""
        from backend.generation.events import _create_event
        template = {
            "type": "exploration",
            "title": "Test Exploration",
            "flavor": "You find something.",
            "choices": [{"text": "Investigate", "outcome": "credits:50"}],
        }
        event = _create_event(template, "sys_1")
        assert event.category is None


class TestDiscoveryModel:
    def test_discovery_to_dict_and_back(self) -> None:
        disc = Discovery(id="d_1", category="artifact", name="Ancient Key",
                         description="A strange key", value=100, system_id="sys_1")
        d = disc.to_dict()
        restored = Discovery.from_dict(d)
        assert restored.id == "d_1"
        assert restored.value == 100

    def test_lore_fragment_to_dict_and_back(self) -> None:
        lore = LoreFragment(id="l_1", arc="The Architects", title="First Contact",
                            text="They came from beyond...", discovered=False,
                            fragment_number=3)
        d = lore.to_dict()
        assert d["fragment_number"] == 3
        restored = LoreFragment.from_dict(d)
        assert restored.arc == "The Architects"
        assert restored.discovered is False
        assert restored.fragment_number == 3

    def test_lore_fragment_number_default(self) -> None:
        """LoreFragment fragment_number should default to -1."""
        lore = LoreFragment(id="l_test", arc="test", title="Test", text="Test text")
        assert lore.fragment_number == -1
        d = lore.to_dict()
        assert d["fragment_number"] == -1
        restored = LoreFragment.from_dict(d)
        assert restored.fragment_number == -1

    def test_lore_fragment_sortable_by_number(self) -> None:
        """fragment_number should provide a robust sort key (simulating frontend)."""
        fragments = [
            LoreFragment(id="lore_abc_3", arc="test", title="T3", text="...", fragment_number=3),
            LoreFragment(id="lore_abc_1", arc="test", title="T1", text="...", fragment_number=1),
            LoreFragment(id="lore_abc_2", arc="test", title="T2", text="...", fragment_number=2),
        ]
        sorted_frags = sorted(fragments, key=lambda f: f.fragment_number or 0)
        assert [f.fragment_number for f in sorted_frags] == [1, 2, 3]
        assert [f.title for f in sorted_frags] == ["T1", "T2", "T3"]

    def test_lore_fragment_sortable_with_none_or_zero(self) -> None:
        """Frontend sort key (fragment_number or 0) handles None and zero without breaking."""
        fragments = [
            LoreFragment(id="lore_abc_3", arc="test", title="T3", text="...", fragment_number=3),
            LoreFragment(id="lore_abc_none", arc="test", title="TNone", text="...", fragment_number=None),
            LoreFragment(id="lore_abc_1", arc="test", title="T1", text="...", fragment_number=1),
            LoreFragment(id="lore_abc_zero", arc="test", title="TZero", text="...", fragment_number=0),
            LoreFragment(id="lore_abc_2", arc="test", title="T2", text="...", fragment_number=2),
        ]
        sorted_frags = sorted(fragments, key=lambda f: f.fragment_number or 0)
        sort_keys = [f.fragment_number or 0 for f in sorted_frags]
        assert sort_keys == [0, 0, 1, 2, 3]
        none_zero_titles = {sorted_frags[0].title, sorted_frags[1].title}
        assert none_zero_titles == {"TNone", "TZero"}
        valid_titles = [f.title for f in sorted_frags[2:]]
        assert valid_titles == ["T1", "T2", "T3"]


class TestBodyModel:
    """Tests for Body model serialization."""

    def test_body_to_dict_and_back(self) -> None:
        """Body should roundtrip through to_dict/from_dict."""
        body = Body(id="b_1", name="Test Planet", body_type="planet",
                    biome="desert", size=5, distance_from_star=0.5,
                    description="A test planet.", poi_count=3, explored=True)
        d = body.to_dict()
        restored = Body.from_dict(d)
        assert restored.id == "b_1"
        assert restored.name == "Test Planet"
        assert restored.body_type == "planet"
        assert restored.biome == "desert"
        assert restored.size == 5
        assert restored.distance_from_star == 0.5
        assert restored.description == "A test planet."
        assert restored.poi_count == 3
        assert restored.explored is True

    def test_body_from_dict_defaults(self) -> None:
        """Body.from_dict should handle missing optional fields."""
        body = Body.from_dict({
            "id": "b_min", "name": "Min", "body_type": "moon",
            "biome": "barren", "size": 1, "distance_from_star": 0.3,
        })
        assert body.description == ""
        assert body.poi_count == 0
        assert body.explored is False


class TestStarSystemModel:
    """Tests for StarSystem model serialization."""

    def test_star_system_to_dict_and_back(self) -> None:
        """StarSystem should roundtrip through to_dict/from_dict with bodies."""
        b1 = Body(id="b1", name="Planet1", body_type="planet", biome="jungle",
                  size=4, distance_from_star=0.3, description="A jungle world.")
        system = StarSystem(id="s_1", name="Test System", x=100.0, y=200.0,
                            star_type="G", star_color="#fff", phenomenon="nebula",
                            phenomenon_desc="A nebula.", bodies=[b1],
                            visited=True, scanned=True)
        d = system.to_dict()
        restored = StarSystem.from_dict(d)
        assert restored.id == "s_1"
        assert restored.name == "Test System"
        assert restored.x == 100.0
        assert restored.y == 200.0
        assert restored.star_type == "G"
        assert restored.star_color == "#fff"
        assert restored.phenomenon == "nebula"
        assert restored.phenomenon_desc == "A nebula."
        assert restored.visited is True
        assert restored.scanned is True
        assert len(restored.bodies) == 1
        assert restored.bodies[0].name == "Planet1"

    def test_star_system_from_dict_defaults(self) -> None:
        """StarSystem.from_dict should handle missing optional fields."""
        system = StarSystem.from_dict({
            "id": "s_min", "name": "Min Sys", "x": 0.0, "y": 0.0,
            "star_type": "M", "star_color": "#f00", "phenomenon": "none",
            "phenomenon_desc": "",
        })
        assert system.bodies == []
        assert system.visited is False
        assert system.scanned is False

    def test_has_trading_station_generation(self) -> None:
        """Systems with phenomenon='none' have has_trading_station=True, others False."""
        systems, _ = generate_universe(42)
        for sys_id, system in systems.items():
            if system.phenomenon == "none":
                assert system.has_trading_station is True, \
                    f"System {sys_id} with phenomenon='none' should have has_trading_station=True"
            else:
                assert system.has_trading_station is False, \
                    f"System {sys_id} with phenomenon='{system.phenomenon}' should have has_trading_station=False"


class TestGameStateModel:
    """Additional tests for GameState model."""

    def test_state_summary_with_system(self) -> None:
        """state_summary should include current_system when one exists."""
        state = new_game(seed=42)
        summary = state.state_summary()
        assert summary["game_id"] == state.id
        assert summary["seed"] == state.seed
        assert summary["current_system"] is not None
        assert "ship" in summary
        assert "event_count" in summary
        assert "discovery_count" in summary
        assert "systems_visited" in summary
        assert "log_count" in summary
        assert "game_started" in summary

    def test_state_summary_no_current_system(self) -> None:
        """state_summary should have None current_system when no system."""
        ship = Ship(current_system_id="nonexistent")
        state = GameState(id="no-sys", seed=42, ship=ship)
        summary = state.state_summary()
        assert summary["current_system"] is None


class TestGenerationBodyDescription:
    """Tests for _body_description covering unknown biome fallback."""

    def test_body_description_unknown_biome(self) -> None:
        """_body_description should fall back to default for unknown biome."""
        from backend.generation.universe import _body_description
        import random as rnd_mod
        rng = rnd_mod.Random(42)
        desc = _body_description(rng, "planet", "unknown_biome_xyz", "G")
        assert isinstance(desc, str)
        assert len(desc) > 0
        assert desc == "An unremarkable celestial body."

    def test_body_description_all_known_biomes(self) -> None:
        """_body_description should return valid strings for all defined biomes."""
        from backend.generation.universe import _body_description
        from backend.config import BIOME_TYPES
        import random as rnd_mod
        rng = rnd_mod.Random(42)
        for biome in BIOME_TYPES:
            desc = _body_description(rng, "planet", biome, "G")
            assert isinstance(desc, str)
            assert len(desc) > 0
            assert desc != "An unremarkable celestial body."


class TestLoreContent:
    """Tests for lore fragment content definitions."""

    def test_has_20_fragments(self) -> None:
        """There should be exactly 20 lore fragments."""
        from backend.generation.lore_content import FRAGMENT_DATA
        assert len(FRAGMENT_DATA) == 20

    def test_five_fragments_per_arc(self) -> None:
        """Each arc should have exactly 5 fragments."""
        from backend.generation.lore_content import FRAGMENT_DATA, ARC_IDS
        for arc in ARC_IDS:
            count = sum(1 for f in FRAGMENT_DATA if f["arc"] == arc)
            assert count == 5, f"Arc {arc} has {count} fragments, expected 5"

    def test_fragment_numbers_are_sequential(self) -> None:
        """Fragment numbers within each arc should be 1-5."""
        from backend.generation.lore_content import FRAGMENT_DATA, ARC_IDS
        for arc in ARC_IDS:
            numbers = [f["fragment_number"] for f in FRAGMENT_DATA if f["arc"] == arc]
            assert sorted(numbers) == [1, 2, 3, 4, 5]

    def test_all_fragments_have_required_fields(self) -> None:
        """Each fragment must have arc, fragment_number, title, and text."""
        from backend.generation.lore_content import FRAGMENT_DATA
        for frag in FRAGMENT_DATA:
            assert "arc" in frag
            assert "fragment_number" in frag
            assert "title" in frag
            assert "text" in frag
            assert len(frag["title"]) > 0
            assert len(frag["text"]) > 0

    def test_arc_display_names_cover_all_arcs(self) -> None:
        """All arcs in ARC_IDS should have display names."""
        from backend.generation.lore_content import ARC_IDS, ARC_DISPLAY_NAMES
        for arc in ARC_IDS:
            assert arc in ARC_DISPLAY_NAMES
            assert len(ARC_DISPLAY_NAMES[arc]) > 0

    def test_unique_fragment_ids_generated(self) -> None:
        """get_all_lore_fragments should produce 20 unique IDs."""
        from backend.generation.lore import get_all_lore_fragments
        fragments = get_all_lore_fragments()
        ids = {f.id for f in fragments}
        assert len(ids) == 20
        assert len(fragments) == 20


class TestLoreDistribution:
    """Tests for lore fragment distribution logic."""

    def test_distribute_all_20_fragments(self) -> None:
        """All 20 fragments should be assigned to systems."""
        from backend.generation.lore import distribute_lore_fragments

        systems, _ = generate_universe(42)
        placement = distribute_lore_fragments(42, systems)

        total_placed = sum(len(frags) for frags in placement.values())
        assert total_placed == 20

    def test_distribution_is_deterministic(self) -> None:
        """Same seed should produce identical fragment placement."""
        from backend.generation.lore import distribute_lore_fragments

        systems1, _ = generate_universe(42)
        systems2, _ = generate_universe(42)

        placement1 = distribute_lore_fragments(42, systems1)
        placement2 = distribute_lore_fragments(42, systems2)

        assert set(placement1.keys()) == set(placement2.keys())
        for sys_id in placement1:
            frags1 = sorted(placement1[sys_id], key=lambda f: f.id)
            frags2 = sorted(placement2[sys_id], key=lambda f: f.id)
            assert [f.id for f in frags1] == [f.id for f in frags2]

    def test_no_system_exceeds_max_fragments(self) -> None:
        """No system should have more than 2 lore fragments."""
        from backend.generation.lore import distribute_lore_fragments

        systems, _ = generate_universe(42)
        placement = distribute_lore_fragments(42, systems, max_per_system=2)

        for sys_id, frags in placement.items():
            assert len(frags) <= 2, f"System {sys_id} has {len(frags)} fragments"

    def test_fragments_have_discovery_id_set(self) -> None:
        """Each placed fragment should have discovery_id in format sys_id::body_id."""
        from backend.generation.lore import distribute_lore_fragments

        systems, _ = generate_universe(42)
        placement = distribute_lore_fragments(42, systems)

        for sys_id, frags in placement.items():
            for frag in frags:
                assert frag.discovery_id is not None
                parts = frag.discovery_id.split("::")
                assert len(parts) == 2
                assert parts[0] == sys_id

    def test_get_fragment_for_body(self) -> None:
        """get_fragment_for_body should return the correct fragment."""
        from backend.generation.lore import distribute_lore_fragments, get_fragment_for_body

        systems, _ = generate_universe(42)
        placement = distribute_lore_fragments(42, systems)
        all_frags = []
        for frags in placement.values():
            all_frags.extend(frags)

        for sys_id, frags in placement.items():
            for frag in frags:
                parts = frag.discovery_id.split("::")
                body_id = parts[1]
                result = get_fragment_for_body(sys_id, body_id, all_frags)
                assert result is not None
                assert result.id == frag.id

    def test_get_fragment_for_body_returns_none_for_no_match(self) -> None:
        """get_fragment_for_body should return None for non-matching body."""
        from backend.generation.lore import get_fragment_for_body
        from backend.generation.universe import generate_universe

        _, lore = generate_universe(42)
        result = get_fragment_for_body("sys_nonexistent", "body_nonexistent", lore)
        assert result is None

    def test_get_lore_fragments_for_system(self) -> None:
        """get_lore_fragments_for_system should return all fragments in a system."""
        from backend.generation.lore import distribute_lore_fragments, get_lore_fragments_for_system

        systems, _ = generate_universe(42)
        placement = distribute_lore_fragments(42, systems)
        all_frags = []
        for frags in placement.values():
            all_frags.extend(frags)

        for sys_id in list(placement.keys())[:5]:
            result = get_lore_fragments_for_system(sys_id, all_frags)
            assert len(result) == len(placement[sys_id])
            assert set(f.id for f in result) == set(f.id for f in placement[sys_id])

    def test_get_lore_fragments_for_system_empty(self) -> None:
        """get_lore_fragments_for_system should return empty for system with no fragments."""
        from backend.generation.lore import get_lore_fragments_for_system

        empty_sys_id = "sys_empty"
        result = get_lore_fragments_for_system(empty_sys_id, [])
        assert result == []

    def test_lore_fragments_present_in_generate_universe(self) -> None:
        """generate_universe should return 20 lore fragments as second tuple element."""
        systems, lore = generate_universe(42)
        assert len(lore) == 20
        assert len(systems) == 50

    def test_lore_distribution_covers_multiple_systems(self) -> None:
        """Lore fragments should be spread across more than one system."""
        from backend.generation.lore import distribute_lore_fragments

        systems, _ = generate_universe(42)
        placement = distribute_lore_fragments(42, systems)
        assert len(placement) > 1, "Fragments should be on multiple systems"

    def test_different_seeds_different_distribution(self) -> None:
        """Different seeds should produce different fragment placements."""
        from backend.generation.lore import distribute_lore_fragments

        systems1, _ = generate_universe(42)
        systems2, _ = generate_universe(99)

        placement1 = distribute_lore_fragments(42, systems1)
        placement2 = distribute_lore_fragments(99, systems2)

        ids1 = set()
        for frags in placement1.values():
            for f in frags:
                ids1.add(f.discovery_id)
        ids2 = set()
        for frags in placement2.values():
            for f in frags:
                ids2.add(f.discovery_id)
        assert ids1 != ids2, "Different seeds should produce different placements"

    def test_lore_distribution_with_custom_max_per_system(self) -> None:
        """Should respect custom max_per_system value."""
        from backend.generation.lore import distribute_lore_fragments

        systems, _ = generate_universe(42)
        placement = distribute_lore_fragments(42, systems, max_per_system=1)
        for sys_id, frags in placement.items():
            assert len(frags) <= 1, f"System {sys_id} has {len(frags)} fragments with max_per_system=1"

    def test_distribute_lore_graceful_when_no_systems_eligible(self) -> None:
        """distribute_lore_fragments returns empty when no systems are eligible (max=0)."""
        from backend.generation.lore import distribute_lore_fragments

        body = Body(
            id="b1", name="TestBody", body_type="planet", biome="barren",
            size=3, distance_from_star=0.5, poi_count=1
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body],
        )
        systems = {"s1": system}
        placement = distribute_lore_fragments(42, systems, max_per_system=0)
        assert placement == {}

    def test_distribute_lore_logs_on_partial_placement(self, caplog) -> None:
        """distribute_lore_fragments logs when not all fragments can be placed."""
        import logging
        caplog.set_level(logging.INFO)

        from backend.generation.lore import distribute_lore_fragments

        body = Body(
            id="b1", name="TestBody", body_type="planet", biome="barren",
            size=3, distance_from_star=0.5, poi_count=1
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body],
        )
        systems = {"s1": system}
        placement = distribute_lore_fragments(42, systems, max_per_system=1)
        assert len(placement) <= 1

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("lore fragments could be placed" in msg for msg in info_messages), \
            f"Expected partial placement info log, got: {info_messages}"

    def test_pick_lore_location_raises_when_no_eligible(self) -> None:
        """_pick_lore_location raises ValueError when all systems at max capacity."""
        from backend.generation.lore import _pick_lore_location

        body = Body(
            id="b1", name="TestBody", body_type="planet", biome="barren",
            size=3, distance_from_star=0.5, poi_count=1
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body],
        )
        systems = {"s1": system}
        counts = {"s1": 1}
        rng = random.Random(42)
        with pytest.raises(ValueError, match="No eligible systems available"):
            _pick_lore_location(rng, systems, counts, max_per_system=1)

    def test_lore_not_placed_on_zero_poi_bodies(self) -> None:
        """Lore fragments should not be placed on bodies with poi_count=0."""
        from backend.generation.lore import distribute_lore_fragments

        body1 = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=0
        )
        body2 = Body(
            id="b2", name="Body2", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=0
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body1, body2],
        )
        systems = {"s1": system}

        placement = distribute_lore_fragments(42, systems)
        assert placement == {}, "No fragments should be placed when all bodies have poi_count=0"

    def test_lore_placed_on_positive_poi_bodies(self) -> None:
        """Lore fragments should be placed on bodies with poi_count>0."""
        from backend.generation.lore import distribute_lore_fragments

        body1 = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=0
        )
        body2 = Body(
            id="b2", name="Body2", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=3
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body1, body2],
        )
        systems = {"s1": system}

        placement = distribute_lore_fragments(42, systems)
        assert len(placement) > 0
        for sys_id, frags in placement.items():
            for frag in frags:
                body_id = frag.discovery_id.split("::")[1]
                assert body_id == "b2", f"Fragment should be on body2, not {body_id}"

    def test_all_discovery_ids_are_unique(self) -> None:
        """All placed fragments must have unique discovery_ids (no body hosts two fragments)."""
        from backend.generation.lore import distribute_lore_fragments

        systems, _ = generate_universe(42)
        placement = distribute_lore_fragments(42, systems)

        discovery_ids: set[str] = set()
        for sys_id, frags in placement.items():
            for frag in frags:
                assert frag.discovery_id not in discovery_ids, \
                    f"Duplicate discovery_id: {frag.discovery_id}"
                discovery_ids.add(frag.discovery_id)

        # Ensure the count matches — no fragments got lost
        assert len(discovery_ids) == sum(len(frags) for frags in placement.values())

    def test_used_bodies_excluded_from_selection(self) -> None:
        """_pick_lore_location should not select bodies already in used_bodies."""
        from backend.generation.lore import _pick_lore_location
        import random as rnd_mod

        body1 = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body2 = Body(
            id="b2", name="Body2", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=1
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body1, body2],
        )
        systems = {"s1": system}
        counts: dict[str, int] = {}

        rng = rnd_mod.Random(42)

        # With body1 used, it must pick body2
        used: set[tuple[str, str]] = {("s1", "b1")}
        # Run multiple times to ensure only body2 is ever picked
        for _ in range(20):
            sys_id, body_id = _pick_lore_location(rng, systems, counts, 2, used)
            assert sys_id == "s1"
            assert body_id == "b2", f"Expected b2 but got {body_id} with used_bodies={used}"

    def test_pick_lore_location_raises_when_all_bodies_used(self) -> None:
        """_pick_lore_location raises ValueError when system has poi bodies but all are used."""
        from backend.generation.lore import _pick_lore_location
        import random as rnd_mod

        body1 = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body2 = Body(
            id="b2", name="Body2", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=1
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body1, body2],
        )
        systems = {"s1": system}
        counts: dict[str, int] = {}

        rng = rnd_mod.Random(42)
        # Both bodies are already used
        used: set[tuple[str, str]] = {("s1", "b1"), ("s1", "b2")}

        with pytest.raises(ValueError, match="No eligible systems available"):
            _pick_lore_location(rng, systems, counts, 2, used)

    def test_pick_lore_location_with_empty_used_bodies_and_zero_poi(self) -> None:
        """_pick_lore_location raises ValueError when all bodies have poi_count=0."""
        from backend.generation.lore import _pick_lore_location
        import random as rnd_mod

        body1 = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=0
        )
        body2 = Body(
            id="b2", name="Body2", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=0
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body1, body2],
        )
        systems = {"s1": system}
        counts: dict[str, int] = {}

        rng = rnd_mod.Random(42)
        used: set[tuple[str, str]] = set()

        with pytest.raises(ValueError, match="No eligible systems available"):
            _pick_lore_location(rng, systems, counts, 2, used)

    def test_pick_lore_location_default_used_bodies(self) -> None:
        """_pick_lore_location should work when called without used_bodies argument."""
        from backend.generation.lore import _pick_lore_location
        import random as rnd_mod

        body = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=1
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body],
        )
        systems = {"s1": system}
        counts: dict[str, int] = {}

        rng = rnd_mod.Random(42)
        sys_id, body_id = _pick_lore_location(rng, systems, counts, 2)
        assert sys_id == "s1"
        assert body_id == "b1"

    def test_distribute_fragments_no_duplicate_bodies(self) -> None:
        """With max_per_system=2, fragments on the same system must be on different bodies."""
        from backend.generation.lore import distribute_lore_fragments

        body1 = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body2 = Body(
            id="b2", name="Body2", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=1
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body1, body2],
        )
        systems = {"s1": system}

        placement = distribute_lore_fragments(42, systems, max_per_system=2)

        if "s1" in placement and len(placement["s1"]) == 2:
            body_ids = [frag.discovery_id.split("::")[1] for frag in placement["s1"]]
            assert body_ids[0] != body_ids[1], \
                f"Two fragments on same body: {body_ids}"

    def test_distribute_continues_when_all_bodies_used_in_system(self) -> None:
        """When a system's bodies are all used, distribute_lore_fragments should retry
        with a different system instead of breaking the loop."""
        from backend.generation.lore import distribute_lore_fragments

        # Create 3 systems, each with 2 bodies that have poi_count > 0
        # System 1: 2 bodies (ocean, jungle)
        # System 2: 2 bodies (ocean, jungle)
        # System 3: 2 bodies (ocean, jungle)
        body1 = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body2 = Body(
            id="b2", name="Body2", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body3 = Body(
            id="b3", name="Body3", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body4 = Body(
            id="b4", name="Body4", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body5 = Body(
            id="b5", name="Body5", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body6 = Body(
            id="b6", name="Body6", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=1
        )

        system1 = StarSystem(
            id="s1", name="Sys1", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body1, body2],
        )
        system2 = StarSystem(
            id="s2", name="Sys2", x=10.0, y=10.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body3, body4],
        )
        system3 = StarSystem(
            id="s3", name="Sys3", x=20.0, y=20.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body5, body6],
        )

        systems = {"s1": system1, "s2": system2, "s3": system3}

        # Place fragments with max_per_system=2. With 3 systems * 2 bodies each = 6 bodies,
        # we can place all 20 fragments? No, max_per_system=2 limits to 6 total.
        # But we want to test the continue behavior: set max_per_system=2 and place 6 fragments.
        # To trigger the continue path, we need a scenario where _pick_lore_location picks
        # a system whose bodies are all already used. We can force this by pre-populating
        # used_bodies for one system's bodies and using a small number of systems.
        
        # Use max_per_system=2 so each system can hold 2 fragments.
        # With 3 systems * 2 bodies each, we can place up to 6 fragments.
        # But we only have 20 fragments total, and only 6 eligible slots.
        # The function should place 6 fragments (2 per system).
        placement = distribute_lore_fragments(42, systems, max_per_system=2)
        
        total_placed = sum(len(frags) for frags in placement.values())
        # 3 systems * 2 fragments each = 6 max
        assert total_placed == 6, f"Expected 6 fragments placed, got {total_placed}"
        
        # Each system should have at most 2 fragments
        for sys_id, frags in placement.items():
            assert len(frags) <= 2, f"System {sys_id} has {len(frags)} fragments"
        
        # All discovery_ids should be unique (no duplicate bodies)
        discovery_ids = set()
        for sys_id, frags in placement.items():
            for frag in frags:
                assert frag.discovery_id not in discovery_ids, \
                    f"Duplicate discovery_id: {frag.discovery_id}"
                discovery_ids.add(frag.discovery_id)

    def test_distribute_continues_on_unexpected_value_error(self, caplog) -> None:
        """When _pick_lore_location raises an unexpected ValueError,
        distribute_lore_fragments should log a warning and continue to the next fragment."""
        import logging
        import unittest.mock as mock
        from backend.generation.lore import distribute_lore_fragments, _pick_lore_location

        caplog.set_level(logging.WARNING)

        # Create a system with bodies that can host fragments
        body1 = Body(
            id="b1", name="Body1", body_type="planet", biome="ocean",
            size=3, distance_from_star=0.5, poi_count=1
        )
        body2 = Body(
            id="b2", name="Body2", body_type="planet", biome="jungle",
            size=3, distance_from_star=0.5, poi_count=1
        )
        system = StarSystem(
            id="s1", name="TestSys", x=0.0, y=0.0,
            star_type="G", star_color="#fff",
            phenomenon="none", phenomenon_desc="",
            bodies=[body1, body2],
        )
        systems = {"s1": system}

        # Patch _pick_lore_location to raise ValueError on first call, then work normally
        call_count = [0]
        original_func = _pick_lore_location

        def mock_pick(rng, systems, counts, max_per_system, used_bodies=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("No eligible systems available for lore placement")
            return original_func(rng, systems, counts, max_per_system, used_bodies)

        with mock.patch("backend.generation.lore._pick_lore_location", side_effect=mock_pick):
            placement = distribute_lore_fragments(42, systems, max_per_system=2)

        # Should have placed fragments despite the first call raising an unexpected ValueError
        total_placed = sum(len(frags) for frags in placement.values())
        assert total_placed > 0, "Should have placed some fragments despite the error"

        # Should have logged a warning about the unexpected ValueError
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("No eligible location for fragment" in msg for msg in warning_messages), \
            f"Expected warning about no eligible location, got: {warning_messages}"


class TestLoreFragmentNumberFixup:
    """Tests for the _fixup_old_lore_fragment_numbers migration helper."""

    def test_fixup_extracts_number_from_id(self) -> None:
        """LoreFragment with id='lore_Architects_3' and fragment_number=-1 gets fixed to 3."""
        frags = [
            LoreFragment(id="lore_Architects_3", arc="architects", title="T3", text="...", fragment_number=-1),
        ]
        _fixup_old_lore_fragment_numbers(frags)
        assert frags[0].fragment_number == 3

    def test_fixup_leaves_already_correct_alone(self) -> None:
        """LoreFragment with id='lore_test_5' and fragment_number=5 stays at 5."""
        frags = [
            LoreFragment(id="lore_test_5", arc="test", title="T5", text="...", fragment_number=5),
        ]
        _fixup_old_lore_fragment_numbers(frags)
        assert frags[0].fragment_number == 5

    def test_fixup_graceful_bad_id(self) -> None:
        """LoreFragment with id='weird_id' and fragment_number=-1 stays -1 (fallback)."""
        frags = [
            LoreFragment(id="weird_id", arc="test", title="Weird", text="...", fragment_number=-1),
        ]
        _fixup_old_lore_fragment_numbers(frags)
        assert frags[0].fragment_number == -1

    def test_fixup_handles_multiple_fragments(self) -> None:
        """Fixup handles a mix of fragments correctly."""
        frags = [
            LoreFragment(id="lore_architects_1", arc="architects", title="T1", text="...", fragment_number=-1),
            LoreFragment(id="lore_void_signal_2", arc="void_signal", title="T2", text="...", fragment_number=-1),
            LoreFragment(id="lore_fracture_3", arc="fracture", title="T3", text="...", fragment_number=3),
            LoreFragment(id="bad_id", arc="test", title="Bad", text="...", fragment_number=-1),
        ]
        _fixup_old_lore_fragment_numbers(frags)
        assert frags[0].fragment_number == 1
        assert frags[1].fragment_number == 2
        assert frags[2].fragment_number == 3  # already correct, unchanged
        assert frags[3].fragment_number == -1  # bad ID, unchanged

    def test_state_from_dict_applies_fixup(self) -> None:
        """Loading a dict with old-style lore fragments (no fragment_number) gets correct numbers."""
        d = {
            "id": "test-fixup",
            "seed": 42,
            "ship": Ship(name="Test", current_system_id="s1").to_dict(),
            "systems": {
                "s1": StarSystem(
                    id="s1", name="Sys1", x=0.0, y=0.0, star_type="G",
                    star_color="#fff", phenomenon="none", phenomenon_desc="",
                ).to_dict(),
            },
            "events": [],
            "discoveries": [],
            "lore_fragments": [
                {"id": "lore_architects_1", "arc": "architects", "title": "T1", "text": "..."},
                {"id": "lore_architects_2", "arc": "architects", "title": "T2", "text": "..."},
                {"id": "lore_void_signal_5", "arc": "void_signal", "title": "T5", "text": "...", "fragment_number": 5},
            ],
            "log_entries": [],
            "systems_visited": 1,
            "game_started": "",
        }
        state = _state_from_dict(d)
        frags_by_id = {f.id: f for f in state.lore_fragments}
        assert frags_by_id["lore_architects_1"].fragment_number == 1
        assert frags_by_id["lore_architects_2"].fragment_number == 2
        assert frags_by_id["lore_void_signal_5"].fragment_number == 5


class TestOldSaveLogEntryIdCollision:
    """Tests for _next_log_id computation when loading old saves without _next_log_id."""

    def test_next_log_id_computed_from_max_existing_id(self) -> None:
        """_next_log_id should be max(existing log entry IDs) + 1 when missing from old save."""
        from backend.game.manager import _state_to_dict, _state_from_dict

        ship = Ship()
        state = GameState(id="test-old-save", seed=42, ship=ship)
        state.add_log("test", "Entry 1")
        state.add_log("test", "Entry 2")
        state.add_log("test", "Entry 3")

        assert len(state.log_entries) == 3
        assert state.log_entries[0]["id"] == 1
        assert state.log_entries[1]["id"] == 2
        assert state.log_entries[2]["id"] == 3

        d = _state_to_dict(state)
        # Simulate an old save by removing _next_log_id
        del d["_next_log_id"]
        assert "_next_log_id" not in d

        restored = _state_from_dict(d)

        # _next_log_id should be 4 (max existing ID 3 + 1)
        assert restored._next_log_id == 4

        # Adding a new log entry should get ID 4 (no collision)
        restored.add_log("test", "Entry 4")
        assert len(restored.log_entries) == 4
        assert restored.log_entries[3]["id"] == 4

    def test_next_log_id_defaults_to_1_with_empty_log(self) -> None:
        """_next_log_id should default to 1 when log_entries is empty and _next_log_id is missing."""
        from backend.game.manager import _state_to_dict, _state_from_dict

        ship = Ship()
        state = GameState(id="test-empty-log", seed=42, ship=ship)

        d = _state_to_dict(state)
        # Simulate old save without _next_log_id and with empty log
        del d["_next_log_id"]
        assert d.get("log_entries") == []

        restored = _state_from_dict(d)

        assert restored._next_log_id == 1

        # Adding a new log entry should get ID 1
        restored.add_log("test", "First entry")
        assert restored.log_entries[0]["id"] == 1

    def test_next_log_id_with_non_sequential_ids(self) -> None:
        """_next_log_id should be max ID + 1 even with non-sequential IDs (e.g., 5, 10, 3)."""
        from backend.game.manager import _state_to_dict, _state_from_dict

        ship = Ship()
        state = GameState(id="test-nonseq", seed=42, ship=ship)

        # Manually create non-sequential log entries (simulating edge case)
        state.log_entries = [
            {"id": 5, "type": "test", "message": "Entry 5", "timestamp": "", "title": "", "description": ""},
            {"id": 10, "type": "test", "message": "Entry 10", "timestamp": "", "title": "", "description": ""},
            {"id": 3, "type": "test", "message": "Entry 3", "timestamp": "", "title": "", "description": ""},
        ]
        state._next_log_id = 11

        d = _state_to_dict(state)
        del d["_next_log_id"]

        restored = _state_from_dict(d)

        # _next_log_id should be 11 (max ID 10 + 1)
        assert restored._next_log_id == 11

        # Adding a new log entry should get ID 11 (no collision)
        restored.add_log("test", "New entry")
        assert restored.log_entries[-1]["id"] == 11

    def test_next_log_id_does_not_regress_when_present_in_dict(self) -> None:
        """_next_log_id should not regress when present in dict but lower than max_id + 1.

        This tests the fix: _next_log_id = max(d.get("_next_log_id", max_id + 1), max_id + 1)
        """
        from backend.game.manager import _state_to_dict, _state_from_dict

        ship = Ship()
        state = GameState(id="test-regress", seed=42, ship=ship)
        state.add_log("test", "Entry 1")
        state.add_log("test", "Entry 2")
        state.add_log("test", "Entry 3")

        d = _state_to_dict(state)
        # _next_log_id is 4, max_id is 3
        assert d["_next_log_id"] == 4

        # Simulate the bug: _next_log_id in the dict is lower than max_id + 1
        # This can happen if the cleaning loop assigned IDs higher than the saved _next_log_id
        # For example, if a log entry had a non-integer ID that got reassigned
        d["_next_log_id"] = 2  # This is lower than max_id (3) + 1 = 4

        restored = _state_from_dict(d)

        # _next_log_id should be max_id + 1 = 4, NOT the regressed value 2
        assert restored._next_log_id == 4, f"Expected 4, got {restored._next_log_id}"

        # Adding a new log entry should get ID 4 (no collision)
        restored.add_log("test", "Entry 4")
        assert len(restored.log_entries) == 4
        assert restored.log_entries[3]["id"] == 4

    def test_next_log_id_does_not_regress_with_cleaned_entries(self) -> None:
        """_next_log_id should not regress when cleaning loop assigns higher IDs.

        Scenario: dict has _next_log_id=5 and log entries with IDs [1, "abc", 3, 4].
        The cleaning loop reassigns "abc" to ID 2, so max_id = 4.
        _next_log_id should be max(5, 4+1) = 5, not the regressed value.
        """
        from backend.game.manager import _state_to_dict, _state_from_dict

        ship = Ship()
        state = GameState(id="test-regress-clean", seed=42, ship=ship)
        state.add_log("test", "Entry 1")
        state.add_log("test", "Entry 2")
        state.add_log("test", "Entry 3")
        state.add_log("test", "Entry 4")

        d = _state_to_dict(state)
        # _next_log_id is 5, max_id is 4
        assert d["_next_log_id"] == 5

        # Now simulate: a log entry with a non-integer ID that gets reassigned during cleaning
        # The cleaning loop would assign it max_id + 1, making max_id higher
        d["log_entries"] = [
            {"id": 1, "type": "test", "message": "Entry 1", "timestamp": "", "title": "", "description": ""},
            {"id": "abc", "type": "test", "message": "Entry with non-int id", "timestamp": "", "title": "", "description": ""},
            {"id": 3, "type": "test", "message": "Entry 3", "timestamp": "", "title": "", "description": ""},
            {"id": 4, "type": "test", "message": "Entry 4", "timestamp": "", "title": "", "description": ""},
        ]
        # _next_log_id in dict is 5, but the cleaning loop will assign "abc" to ID 2
        # max_id after cleaning = max(1, 2, 3, 4) = 4
        # _next_log_id should be max(5, 4+1) = 5

        restored = _state_from_dict(d)

        assert restored._next_log_id == 5, f"Expected 5, got {restored._next_log_id}"

        # Adding a new log entry should get ID 5 (no collision)
        restored.add_log("test", "Entry 5")
        assert len(restored.log_entries) == 5
        assert restored.log_entries[4]["id"] == 5

    def test_next_log_id_uses_max_when_cleaning_assigns_higher_ids(self) -> None:
        """When cleaning assigns IDs higher than the saved _next_log_id, use max_id + 1.

        Scenario: dict has _next_log_id=3 and log entries with IDs [1, 2, "xyz"].
        The cleaning loop reassigns "xyz" to ID 3, so max_id = 3.
        _next_log_id should be max(3, 3+1) = 4, not 3.
        """
        from backend.game.manager import _state_to_dict, _state_from_dict

        ship = Ship()
        state = GameState(id="test-regress-clean2", seed=42, ship=ship)
        state.add_log("test", "Entry 1")
        state.add_log("test", "Entry 2")

        d = _state_to_dict(state)
        # _next_log_id is 3, max_id is 2
        assert d["_next_log_id"] == 3

        # Now simulate: a log entry with a non-integer ID that gets reassigned to ID 3
        # This means max_id becomes 3, which equals _next_log_id
        d["log_entries"] = [
            {"id": 1, "type": "test", "message": "Entry 1", "timestamp": "", "title": "", "description": ""},
            {"id": 2, "type": "test", "message": "Entry 2", "timestamp": "", "title": "", "description": ""},
            {"id": "xyz", "type": "test", "message": "Entry with non-int id", "timestamp": "", "title": "", "description": ""},
        ]
        # _next_log_id in dict is 3, but the cleaning loop will assign "xyz" to ID 3
        # max_id after cleaning = max(1, 2, 3) = 3
        # _next_log_id should be max(3, 3+1) = 4

        restored = _state_from_dict(d)

        assert restored._next_log_id == 4, f"Expected 4, got {restored._next_log_id}"

        # Adding a new log entry should get ID 4 (no collision)
        restored.add_log("test", "Entry 4")
        assert len(restored.log_entries) == 4
        assert restored.log_entries[3]["id"] == 4

    def test_next_log_id_warns_when_overridden(self, caplog) -> None:
        """A warning should be logged when _next_log_id from save data is lower than max_id + 1.

        This tests the warning added per PR #53 change request 5.
        """
        import logging
        from backend.game.manager import _state_to_dict, _state_from_dict

        ship = Ship()
        state = GameState(id="test-warn-override", seed=42, ship=ship)
        state.add_log("test", "Entry 1")
        state.add_log("test", "Entry 2")
        state.add_log("test", "Entry 3")

        d = _state_to_dict(state)
        # _next_log_id is 4, max_id is 3
        assert d["_next_log_id"] == 4

        # Simulate the bug: _next_log_id in the dict is lower than max_id + 1
        d["_next_log_id"] = 2  # This is lower than max_id (3) + 1 = 4

        with caplog.at_level(logging.WARNING):
            restored = _state_from_dict(d)

        # _next_log_id should be max_id + 1 = 4, NOT the regressed value 2
        assert restored._next_log_id == 4, f"Expected 4, got {restored._next_log_id}"

        # Verify the warning was logged
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_messages) >= 1, f"Expected at least 1 warning, got {len(warning_messages)}"
        assert any(
            "_next_log_id from save data (2) is lower than max_id + 1 (4)" in msg
            for msg in warning_messages
        ), f"Expected warning about _next_log_id override, got: {warning_messages}"


class TestAcceptedMissionsMigration:
    """Tests for the accepted_missions migration in _state_from_dict.

    Old saves stored accepted_missions values as plain faction_id strings.
    The migration converts them to {"faction_id": v} dicts.
    """

    def test_old_format_string_values_are_migrated(self) -> None:
        """Old-format string values should be converted to dict with all default fields."""
        from backend.game.manager import _state_from_dict
        from backend.models.ship import Ship
        from backend.models.system import StarSystem

        d = {
            "id": "test-migrate",
            "seed": 42,
            "ship": Ship(name="Test", current_system_id="s1").to_dict(),
            "systems": {
                "s1": StarSystem(
                    id="s1", name="Sys1", x=0.0, y=0.0, star_type="G",
                    star_color="#fff", phenomenon="none", phenomenon_desc="",
                ).to_dict(),
            },
            "events": [],
            "discoveries": [],
            "lore_fragments": [],
            "log_entries": [],
            "faction_relations": {},
            "systems_visited": 1,
            "game_started": "",
            "accepted_missions": {
                "mission_old_1": "stellar_cartographers",
                "mission_old_2": "void_traders",
            },
        }
        state = _state_from_dict(d)
        expected_defaults = {
            "faction_id": "stellar_cartographers",
            "tier": 1,
            "title": "Unknown Mission",
            "description": "Migrated from old save format.",
            "objective_type": "courier",
            "objective_target": "",
            "fuel_cost": 3,
            "credit_cost": 10,
            "credit_reward": 75,
            "reputation_reward": 7,
        }
        assert state.accepted_missions["mission_old_1"] == expected_defaults
        expected_defaults["faction_id"] = "void_traders"
        assert state.accepted_missions["mission_old_2"] == expected_defaults

    def test_new_format_dict_values_are_preserved(self) -> None:
        """New-format dict values should be preserved as-is."""
        from backend.game.manager import _state_from_dict
        from backend.models.ship import Ship
        from backend.models.system import StarSystem

        d = {
            "id": "test-preserve",
            "seed": 42,
            "ship": Ship(name="Test", current_system_id="s1").to_dict(),
            "systems": {
                "s1": StarSystem(
                    id="s1", name="Sys1", x=0.0, y=0.0, star_type="G",
                    star_color="#fff", phenomenon="none", phenomenon_desc="",
                ).to_dict(),
            },
            "events": [],
            "discoveries": [],
            "lore_fragments": [],
            "log_entries": [],
            "faction_relations": {},
            "systems_visited": 1,
            "game_started": "",
            "accepted_missions": {
                "mission_new_1": {
                    "faction_id": "stellar_cartographers",
                    "tier": 1,
                    "title": "Test Mission",
                },
            },
        }
        state = _state_from_dict(d)
        assert state.accepted_missions["mission_new_1"] == {
            "faction_id": "stellar_cartographers",
            "tier": 1,
            "title": "Test Mission",
        }

    def test_mixed_old_and_new_formats(self) -> None:
        """Mixed old-format strings and new-format dicts should both work."""
        from backend.game.manager import _state_from_dict
        from backend.models.ship import Ship
        from backend.models.system import StarSystem

        d = {
            "id": "test-mixed",
            "seed": 42,
            "ship": Ship(name="Test", current_system_id="s1").to_dict(),
            "systems": {
                "s1": StarSystem(
                    id="s1", name="Sys1", x=0.0, y=0.0, star_type="G",
                    star_color="#fff", phenomenon="none", phenomenon_desc="",
                ).to_dict(),
            },
            "events": [],
            "discoveries": [],
            "lore_fragments": [],
            "log_entries": [],
            "faction_relations": {},
            "systems_visited": 1,
            "game_started": "",
            "accepted_missions": {
                "mission_old": "stellar_cartographers",
                "mission_new": {
                    "faction_id": "void_traders",
                    "tier": 2,
                    "title": "Trade Run",
                },
            },
        }
        state = _state_from_dict(d)
        expected_old_defaults = {
            "faction_id": "stellar_cartographers",
            "tier": 1,
            "title": "Unknown Mission",
            "description": "Migrated from old save format.",
            "objective_type": "courier",
            "objective_target": "",
            "fuel_cost": 3,
            "credit_cost": 10,
            "credit_reward": 75,
            "reputation_reward": 7,
        }
        assert state.accepted_missions["mission_old"] == expected_old_defaults
        assert state.accepted_missions["mission_new"] == {
            "faction_id": "void_traders",
            "tier": 2,
            "title": "Trade Run",
        }

    def test_empty_accepted_missions(self) -> None:
        """Empty accepted_missions should result in an empty dict."""
        from backend.game.manager import _state_from_dict
        from backend.models.ship import Ship
        from backend.models.system import StarSystem

        d = {
            "id": "test-empty",
            "seed": 42,
            "ship": Ship(name="Test", current_system_id="s1").to_dict(),
            "systems": {
                "s1": StarSystem(
                    id="s1", name="Sys1", x=0.0, y=0.0, star_type="G",
                    star_color="#fff", phenomenon="none", phenomenon_desc="",
                ).to_dict(),
            },
            "events": [],
            "discoveries": [],
            "lore_fragments": [],
            "log_entries": [],
            "faction_relations": {},
            "systems_visited": 1,
            "game_started": "",
            "accepted_missions": {},
        }
        state = _state_from_dict(d)
        assert state.accepted_missions == {}

    def test_missing_accepted_missions_key(self) -> None:
        """Missing accepted_missions key should result in an empty dict."""
        from backend.game.manager import _state_from_dict
        from backend.models.ship import Ship
        from backend.models.system import StarSystem

        d = {
            "id": "test-missing",
            "seed": 42,
            "ship": Ship(name="Test", current_system_id="s1").to_dict(),
            "systems": {
                "s1": StarSystem(
                    id="s1", name="Sys1", x=0.0, y=0.0, star_type="G",
                    star_color="#fff", phenomenon="none", phenomenon_desc="",
                ).to_dict(),
            },
            "events": [],
            "discoveries": [],
            "lore_fragments": [],
            "log_entries": [],
            "faction_relations": {},
            "systems_visited": 1,
            "game_started": "",
        }
        state = _state_from_dict(d)
        assert state.accepted_missions == {}


class TestAncientGateSystemType:
    """Tests for the ancient_gate phenomenon producing the 'ancient' system type."""

    def test_ancient_gate_system_type(self) -> None:
        """Systems with ancient_gate phenomenon should have system_type='ancient'."""
        from backend.generation.universe import generate_system
        import random
        # Use a seed that produces ancient_gate phenomenon
        # We need to find a seed where phenomenon == "ancient_gate"
        found = False
        for seed in range(1000):
            rng = random.Random(seed)
            galaxy_rng = random.Random(seed + 1000)
            system = generate_system(rng, 0, galaxy_rng)
            if system.phenomenon == "ancient_gate":
                assert system.system_type == "ancient", \
                    f"Expected system_type='ancient' for ancient_gate, got '{system.system_type}'"
                found = True
                break
        assert found, "Could not find a seed that produces ancient_gate phenomenon in range 0-999"

    def test_ancient_gate_not_uncharted(self) -> None:
        """Systems with ancient_gate phenomenon should NOT have system_type='uncharted'."""
        from backend.generation.universe import generate_system
        import random
        found = False
        for seed in range(1000):
            rng = random.Random(seed)
            galaxy_rng = random.Random(seed + 1000)
            system = generate_system(rng, 0, galaxy_rng)
            if system.phenomenon == "ancient_gate":
                assert system.system_type != "uncharted", \
                    f"ancient_gate system should not be 'uncharted', got '{system.system_type}'"
                found = True
                break
        assert found, "Could not find a seed that produces ancient_gate phenomenon in range 0-999"

    def test_pulsar_and_black_hole_still_uncharted(self) -> None:
        """Pulsar and black_hole phenomena should still produce system_type='uncharted'."""
        from backend.generation.universe import generate_system
        import random
        found_pulsar = False
        found_black_hole = False
        for seed in range(1000):
            rng = random.Random(seed)
            galaxy_rng = random.Random(seed + 1000)
            system = generate_system(rng, 0, galaxy_rng)
            if system.phenomenon == "pulsar":
                assert system.system_type == "uncharted"
                found_pulsar = True
            if system.phenomenon == "black_hole":
                assert system.system_type == "uncharted"
                found_black_hole = True
            if found_pulsar and found_black_hole:
                break
        assert found_pulsar, "Could not find a seed that produces pulsar phenomenon in range 0-999"
        assert found_black_hole, "Could not find a seed that produces black_hole phenomenon in range 0-999"


class TestNewHazardEvents:
    """Tests for the new and updated hazard events."""

    def test_new_events_exist_in_templates(self) -> None:
        """Micrometeorite Storm and Quantum Fluctuation should be in EVENT_TEMPLATES."""
        from backend.generation.events import EVENT_TEMPLATES
        titles = {t["title"] for t in EVENT_TEMPLATES}
        assert "Micrometeorite Storm" in titles
        assert "Quantum Fluctuation" in titles

    def test_micrometeorite_storm_structure(self) -> None:
        """Micrometeorite Storm should have correct type, rarity, title, flavor, and choices."""
        from backend.generation.events import EVENT_TEMPLATES
        template = next(t for t in EVENT_TEMPLATES if t["title"] == "Micrometeorite Storm")
        assert template["type"] == "hazard"
        assert template["rarity"] == "common"
        assert len(template["flavor"]) > 0
        assert len(template["choices"]) == 3
        for choice in template["choices"]:
            assert "text" in choice
            assert "outcome" in choice
            assert len(choice["text"]) > 0
            assert len(choice["outcome"]) > 0

    def test_quantum_fluctuation_structure(self) -> None:
        """Quantum Fluctuation should have correct type, rarity, title, flavor, and choices."""
        from backend.generation.events import EVENT_TEMPLATES
        template = next(t for t in EVENT_TEMPLATES if t["title"] == "Quantum Fluctuation")
        assert template["type"] == "hazard"
        assert template["rarity"] == "rare"
        assert len(template["flavor"]) > 0
        assert len(template["choices"]) == 3
        for choice in template["choices"]:
            assert "text" in choice
            assert "outcome" in choice
            assert len(choice["text"]) > 0
            assert len(choice["outcome"]) > 0

    def test_updated_solar_flare_structure(self) -> None:
        """Updated Solar Flare should have the new flavor and choices."""
        from backend.generation.events import EVENT_TEMPLATES
        template = next(t for t in EVENT_TEMPLATES if t["title"] == "Solar Flare")
        assert template["type"] == "hazard"
        assert template["rarity"] == "common"
        assert "massive solar flare erupts from the star" in template["flavor"]
        choices_text = {c["text"] for c in template["choices"]}
        assert "Take cover behind the nearest planet" in choices_text
        assert "Deploy radiation shielding" in choices_text
        assert "Ride it out" in choices_text

    def test_updated_ion_storm_structure(self) -> None:
        """Updated Ion Storm should have the new flavor and choices."""
        from backend.generation.events import EVENT_TEMPLATES
        template = next(t for t in EVENT_TEMPLATES if t["title"] == "Ion Storm")
        assert template["type"] == "hazard"
        assert template["rarity"] == "uncommon"
        assert "Electromagnetic interference" in template["flavor"]
        choices_text = {c["text"] for c in template["choices"]}
        assert "Power down non-essential systems" in choices_text
        assert "Push through with emergency power" in choices_text
        assert "Wait it out" in choices_text

    def test_new_events_have_cooldowns(self) -> None:
        """Micrometeorite Storm and Quantum Fluctuation should have cooldowns."""
        from backend.generation.events import EVENT_COOLDOWNS
        assert "Micrometeorite Storm" in EVENT_COOLDOWNS
        assert "Quantum Fluctuation" in EVENT_COOLDOWNS
        assert EVENT_COOLDOWNS["Micrometeorite Storm"] == 3
        assert EVENT_COOLDOWNS["Quantum Fluctuation"] == 8

    def test_hazard_event_cooldown_scales_with_repeat_triggers(self) -> None:
        """Hazard event cooldown should increase when the same event is triggered repeatedly, but cap at 3x."""
        from backend.generation.events import apply_cooldown, EVENT_COOLDOWNS
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-hazard-scale", seed=42, ship=ship)

        title = "Micrometeorite Storm"
        base = EVENT_COOLDOWNS[title]

        # First trigger: multiplier = min(1, 3) = 1
        apply_cooldown(state, title, "hazard")
        assert state.event_cooldowns[title] == base * 1
        assert state.hazard_event_counts[title] == 1

        # Second trigger: multiplier = min(2, 3) = 2
        apply_cooldown(state, title, "hazard")
        assert state.event_cooldowns[title] == base * 2
        assert state.hazard_event_counts[title] == 2

        # Third trigger: multiplier = min(3, 3) = 3
        apply_cooldown(state, title, "hazard")
        assert state.event_cooldowns[title] == base * 3
        assert state.hazard_event_counts[title] == 3

        # Fourth trigger: multiplier = min(4, 3) = 3 (capped!)
        apply_cooldown(state, title, "hazard")
        assert state.event_cooldowns[title] == base * 3
        assert state.hazard_event_counts[title] == 4

        # Fifth trigger: multiplier = min(5, 3) = 3 (still capped)
        apply_cooldown(state, title, "hazard")
        assert state.event_cooldowns[title] == base * 3
        assert state.hazard_event_counts[title] == 5

    def test_phenomenon_gated_hazard_events_do_not_scale_cooldown(self) -> None:
        """Phenomenon-gated hazard events should NOT scale cooldown when triggered repeatedly."""
        from backend.generation.events import apply_cooldown, EVENT_COOLDOWNS
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-gated-scale", seed=42, ship=ship)

        # Ion Storm has trigger_conditions: {phenomenon: nebula}
        title = "Ion Storm"
        base = EVENT_COOLDOWNS[title]

        # First trigger: should use base cooldown (no scaling)
        apply_cooldown(state, title, "hazard")
        assert state.event_cooldowns[title] == base, f"Expected {base}, got {state.event_cooldowns[title]}"
        # hazard_event_counts should NOT be incremented for gated events
        assert title not in state.hazard_event_counts, f"Expected no hazard_event_counts entry for {title}"

        # Second trigger: still base cooldown (no scaling)
        apply_cooldown(state, title, "hazard")
        assert state.event_cooldowns[title] == base, f"Expected {base}, got {state.event_cooldowns[title]}"
        assert title not in state.hazard_event_counts

        # Third trigger: still base cooldown (no scaling)
        apply_cooldown(state, title, "hazard")
        assert state.event_cooldowns[title] == base, f"Expected {base}, got {state.event_cooldowns[title]}"
        assert title not in state.hazard_event_counts

    def test_mixed_hazard_events_scaling_and_non_scaling(self) -> None:
        """Non-gated hazard events should scale while gated ones don't, even in the same state."""
        from backend.generation.events import apply_cooldown, EVENT_COOLDOWNS
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-mixed-scale", seed=42, ship=ship)

        # Solar Flare has NO trigger_conditions - should scale
        solar_title = "Solar Flare"
        solar_base = EVENT_COOLDOWNS[solar_title]

        # Ion Storm has trigger_conditions - should NOT scale
        ion_title = "Ion Storm"
        ion_base = EVENT_COOLDOWNS[ion_title]

        # First trigger of Solar Flare: multiplier = min(1, 3) = 1
        apply_cooldown(state, solar_title, "hazard")
        assert state.event_cooldowns[solar_title] == solar_base * 1
        assert state.hazard_event_counts[solar_title] == 1

        # First trigger of Ion Storm: base cooldown (no scaling)
        apply_cooldown(state, ion_title, "hazard")
        assert state.event_cooldowns[ion_title] == ion_base
        assert ion_title not in state.hazard_event_counts

        # Second trigger of Solar Flare: multiplier = min(2, 3) = 2
        apply_cooldown(state, solar_title, "hazard")
        assert state.event_cooldowns[solar_title] == solar_base * 2
        assert state.hazard_event_counts[solar_title] == 2

        # Second trigger of Ion Storm: still base cooldown
        apply_cooldown(state, ion_title, "hazard")
        assert state.event_cooldowns[ion_title] == ion_base
        assert ion_title not in state.hazard_event_counts

        # Third trigger of Solar Flare: multiplier = min(3, 3) = 3
        apply_cooldown(state, solar_title, "hazard")
        assert state.event_cooldowns[solar_title] == solar_base * 3
        assert state.hazard_event_counts[solar_title] == 3

    def test_non_hazard_events_do_not_scale_cooldown(self) -> None:
        """Non-hazard events should not have scaled cooldowns and should not increment hazard_event_counts."""
        from backend.generation.events import apply_cooldown, EVENT_COOLDOWNS
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-nonhazard-scale", seed=42, ship=ship)

        title = "Ancient Signal"
        base = EVENT_COOLDOWNS.get(title, 5)

        # First trigger
        apply_cooldown(state, title, "exploration")
        assert state.event_cooldowns[title] == base
        assert state.hazard_event_counts == {}

        # Second trigger
        apply_cooldown(state, title, "exploration")
        assert state.event_cooldowns[title] == base
        assert state.hazard_event_counts == {}

    def test_micrometeorite_storm_can_be_triggered(self) -> None:
        """Micrometeorite Storm should be triggerable via the event system."""
        from backend.generation.events import trigger_event
        from backend.generation.universe import generate_universe
        from backend.models.ship import Ship
        import random

        systems, lore = generate_universe(42)
        ship = Ship(current_system_id=list(systems.keys())[0])
        state = GameState(id="test-trigger-mm", seed=42, ship=ship, systems=systems)

        # Set up conditions for the event to trigger
        state.event_cooldowns = {}
        state.last_event_title = None

        # Try multiple times with a known seed to trigger Micrometeorite Storm
        found = False
        for i in range(100):
            state.events = []
            rng = random.Random(1000 + i)
            event = trigger_event(state, rng_override=rng)
            if event and event.title == "Micrometeorite Storm":
                found = True
                assert event.event_type == "hazard"
                assert len(event.choices) == 3
                assert event.flavor is not None
                break

        assert found, "Micrometeorite Storm should be triggerable within 100 attempts"

    def test_quantum_fluctuation_can_be_triggered(self) -> None:
        """Quantum Fluctuation should be triggerable via the event system."""
        from backend.generation.events import trigger_event
        from backend.generation.universe import generate_universe
        from backend.models.ship import Ship
        import random

        systems, lore = generate_universe(42)
        ship = Ship(current_system_id=list(systems.keys())[0])
        state = GameState(id="test-trigger-qf", seed=42, ship=ship, systems=systems)

        state.event_cooldowns = {}
        state.last_event_title = None

        found = False
        for i in range(500):
            state.events = []
            rng = random.Random(2000 + i)
            event = trigger_event(state, rng_override=rng)
            if event and event.title == "Quantum Fluctuation":
                found = True
                assert event.event_type == "hazard"
                assert len(event.choices) == 3
                assert event.flavor is not None
                break

        assert found, "Quantum Fluctuation should be triggerable within 500 attempts"

    def test_cooldown_prevents_immediate_repeat(self) -> None:
        """Cooldown should prevent the same hazard event from triggering again immediately."""
        from backend.generation.events import trigger_event, apply_cooldown
        from backend.generation.universe import generate_universe
        from backend.models.ship import Ship
        import random

        systems, lore = generate_universe(42)
        ship = Ship(current_system_id=list(systems.keys())[0])
        state = GameState(id="test-cooldown-repeat", seed=42, ship=ship, systems=systems)

        # Set a cooldown for Micrometeorite Storm
        state.event_cooldowns["Micrometeorite Storm"] = 10
        state.last_event_title = None

        # The event should not be Micrometeorite Storm due to cooldown
        triggered_titles = set()
        for i in range(50):
            state.events = []
            rng = random.Random(3000 + i)
            event = trigger_event(state, rng_override=rng)
            if event:
                triggered_titles.add(event.title)

        assert "Micrometeorite Storm" not in triggered_titles, \
            "Micrometeorite Storm should not trigger when on cooldown"

    def test_hazard_event_counts_persists_across_triggers(self) -> None:
        """hazard_event_counts should accumulate across multiple trigger_event calls."""
        from backend.generation.events import trigger_event
        from backend.generation.universe import generate_universe
        from backend.models.ship import Ship
        import random

        systems, lore = generate_universe(42)
        ship = Ship(current_system_id=list(systems.keys())[0])
        state = GameState(id="test-persist-counts", seed=42, ship=ship, systems=systems)

        # Clear cooldowns so events can trigger
        state.event_cooldowns = {}
        state.last_event_title = None

        hazard_triggers = 0
        for i in range(200):
            state.events = []
            rng = random.Random(4000 + i)
            event = trigger_event(state, rng_override=rng)
            if event and event.event_type == "hazard":
                hazard_triggers += 1

        # hazard_event_counts should reflect total hazard triggers
        total_counts = sum(state.hazard_event_counts.values())
        assert total_counts == hazard_triggers, \
            f"hazard_event_counts sum ({total_counts}) should equal hazard triggers ({hazard_triggers})"

    def test_hazard_event_counts_decay_when_not_on_cooldown(self) -> None:
        """hazard_event_counts should decay by 1 when the event is not on cooldown."""
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-decay", seed=42, ship=ship)

        # Set up a hazard event count
        state.hazard_event_counts["Solar Flare"] = 5

        # No cooldown for Solar Flare, so it should decay
        decrement_cooldowns(state)

        assert state.hazard_event_counts["Solar Flare"] == 4

    def test_hazard_event_counts_do_not_decay_when_on_cooldown(self) -> None:
        """hazard_event_counts should NOT decay when the event is on cooldown."""
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-no-decay", seed=42, ship=ship)

        # Set up a hazard event count AND a cooldown for the same event
        state.hazard_event_counts["Solar Flare"] = 5
        state.event_cooldowns["Solar Flare"] = 3

        # Event is on cooldown, so count should NOT decay
        decrement_cooldowns(state)

        assert state.hazard_event_counts["Solar Flare"] == 5

    def test_hazard_event_counts_decay_to_zero_removes_entry(self) -> None:
        """When hazard_event_counts decays to 0, the entry should be removed."""
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-decay-zero", seed=42, ship=ship)

        # Set up a hazard event count of 1
        state.hazard_event_counts["Solar Flare"] = 1

        # Decay it to 0 - should remove the entry
        decrement_cooldowns(state)

        assert "Solar Flare" not in state.hazard_event_counts
        assert state.hazard_event_counts == {}

    def test_hazard_event_counts_decay_multiple_events(self) -> None:
        """Multiple hazard events should all decay independently."""
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-decay-multi", seed=42, ship=ship)

        # Set up multiple hazard event counts
        state.hazard_event_counts["Solar Flare"] = 5
        state.hazard_event_counts["Asteroid Swarm"] = 3
        state.hazard_event_counts["Micrometeorite Storm"] = 1

        # Put one event on cooldown to test it doesn't decay
        state.event_cooldowns["Asteroid Swarm"] = 2

        decrement_cooldowns(state)

        # Solar Flare (not on cooldown) should decay
        assert state.hazard_event_counts["Solar Flare"] == 4
        # Asteroid Swarm (on cooldown) should NOT decay
        assert state.hazard_event_counts["Asteroid Swarm"] == 3
        # Micrometeorite Storm (not on cooldown, count=1) should be removed
        assert "Micrometeorite Storm" not in state.hazard_event_counts

    def test_decrement_cooldowns_still_decrements_cooldowns(self) -> None:
        """The original cooldown decrement behavior should still work."""
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-original", seed=42, ship=ship)

        # Set up cooldowns
        state.event_cooldowns["Solar Flare"] = 3
        state.event_cooldowns["Ancient Signal"] = 1

        decrement_cooldowns(state)

        # Solar Flare cooldown should decrement from 3 to 2
        assert state.event_cooldowns["Solar Flare"] == 2
        # Ancient Signal cooldown should decrement from 1 to 0 and be removed
        assert "Ancient Signal" not in state.event_cooldowns

    def test_hazard_event_count_does_not_decay_on_cooldown_expiry_tick(self) -> None:
        """When a cooldown expires (reaches 0), the hazard_event_count should NOT decay on the same tick.
        
        This tests the fix for PR #58 change request 2: if an event had cooldown=1 and count=3,
        after decrement: cooldown expires (removed), but count should stay at 3 (not decay to 2).
        """
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-no-decay-on-expiry", seed=42, ship=ship)

        # Set up: cooldown=1 (will expire this tick), count=3
        state.event_cooldowns["Solar Flare"] = 1
        state.hazard_event_counts["Solar Flare"] = 3

        decrement_cooldowns(state)

        # Cooldown should have expired (removed)
        assert "Solar Flare" not in state.event_cooldowns
        # Count should NOT have decayed (stays at 3, not 2)
        assert state.hazard_event_counts["Solar Flare"] == 3, \
            f"Expected count to stay at 3, got {state.hazard_event_counts['Solar Flare']}"

    def test_hazard_event_count_decays_on_next_tick_after_cooldown_expiry(self) -> None:
        """After a cooldown expires, the count should decay on the NEXT tick, not the same tick."""
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-decay-next-tick", seed=42, ship=ship)

        # Set up: cooldown=1 (will expire this tick), count=3
        state.event_cooldowns["Solar Flare"] = 1
        state.hazard_event_counts["Solar Flare"] = 3

        # Tick 1: cooldown expires, count should NOT decay
        decrement_cooldowns(state)
        assert "Solar Flare" not in state.event_cooldowns
        assert state.hazard_event_counts["Solar Flare"] == 3

        # Tick 2: no cooldown, count SHOULD decay
        decrement_cooldowns(state)
        assert state.hazard_event_counts["Solar Flare"] == 2

    def test_hazard_event_count_preserved_when_cooldown_expires_and_still_on_cooldown(self) -> None:
        """Events on cooldown should still not have their count decay, even after the cooldown was just applied."""
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-preserved-on-cooldown", seed=42, ship=ship)

        # Set up: cooldown=3 (not expiring), count=5
        state.event_cooldowns["Solar Flare"] = 3
        state.hazard_event_counts["Solar Flare"] = 5

        decrement_cooldowns(state)

        # Cooldown should decrement to 2
        assert state.event_cooldowns["Solar Flare"] == 2
        # Count should NOT decay (event is on cooldown)
        assert state.hazard_event_counts["Solar Flare"] == 5

    def test_hazard_event_count_decay_multiple_ticks_with_mixed_cooldowns(self) -> None:
        """Multiple events with different cooldown states should all decay correctly."""
        from backend.generation.events import decrement_cooldowns
        from backend.models.ship import Ship

        ship = Ship()
        state = GameState(id="test-mixed-ticks", seed=42, ship=ship)

        # Event A: cooldown=1 (expiring this tick), count=3
        # Event B: cooldown=3 (not expiring), count=5
        # Event C: no cooldown, count=2
        state.event_cooldowns["Solar Flare"] = 1
        state.event_cooldowns["Asteroid Swarm"] = 3
        state.hazard_event_counts["Solar Flare"] = 3
        state.hazard_event_counts["Asteroid Swarm"] = 5
        state.hazard_event_counts["Micrometeorite Storm"] = 2

        # Tick 1
        decrement_cooldowns(state)
        # Solar Flare: cooldown expired, count stays at 3
        assert "Solar Flare" not in state.event_cooldowns
        assert state.hazard_event_counts["Solar Flare"] == 3
        # Asteroid Swarm: cooldown 3->2, count stays at 5
        assert state.event_cooldowns["Asteroid Swarm"] == 2
        assert state.hazard_event_counts["Asteroid Swarm"] == 5
        # Micrometeorite Storm: no cooldown, count 2->1
        assert state.hazard_event_counts["Micrometeorite Storm"] == 1

        # Tick 2
        decrement_cooldowns(state)
        # Solar Flare: no cooldown, count 3->2
        assert state.hazard_event_counts["Solar Flare"] == 2
        # Asteroid Swarm: cooldown 2->1, count stays at 5
        assert state.event_cooldowns["Asteroid Swarm"] == 1
        assert state.hazard_event_counts["Asteroid Swarm"] == 5
        # Micrometeorite Storm: no cooldown, count 1->0 and removed
        assert "Micrometeorite Storm" not in state.hazard_event_counts

        # Tick 3
        decrement_cooldowns(state)
        # Solar Flare: no cooldown, count 2->1
        assert state.hazard_event_counts["Solar Flare"] == 1
        # Asteroid Swarm: cooldown expired, count stays at 5
        assert "Asteroid Swarm" not in state.event_cooldowns
        assert state.hazard_event_counts["Asteroid Swarm"] == 5

        # Tick 4
        decrement_cooldowns(state)
        # Solar Flare: no cooldown, count 1->0 and removed
        assert "Solar Flare" not in state.hazard_event_counts
        # Asteroid Swarm: no cooldown, count 5->4
        assert state.hazard_event_counts["Asteroid Swarm"] == 4


class TestEventCooldowns:
    """Validation tests for EVENT_COOLDOWNS coverage."""

    def test_all_event_templates_have_cooldowns(self) -> None:
        """Every event title in EVENT_TEMPLATES must have a corresponding entry in EVENT_COOLDOWNS."""
        from backend.generation.events import EVENT_TEMPLATES, EVENT_COOLDOWNS

        for template in EVENT_TEMPLATES:
            title = template["title"]
            assert title in EVENT_COOLDOWNS, \
                f"Event template '{title}' is missing from EVENT_COOLDOWNS"
