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
from backend.game.manager import new_game
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
        assert any("remains isolated" in msg for msg in warning_messages), \
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
                            text="They came from beyond...", discovered=False)
        d = lore.to_dict()
        restored = LoreFragment.from_dict(d)
        assert restored.arc == "The Architects"
        assert restored.discovered is False


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
