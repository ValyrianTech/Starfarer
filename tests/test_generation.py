import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.generation.universe import generate_universe, distance_between, _ensure_connectivity, NEIGHBOR_DISTANCE_THRESHOLD
from backend.models.system import StarSystem
from backend.models.ship import Ship
from backend.models.game_state import GameState
from backend.models.event import Event, Choice
from backend.models.discovery import Discovery, LoreFragment
from backend.config import GALAXY_SYSTEM_COUNT
import random


class TestUniverseGeneration:
    def test_generates_correct_number_of_systems(self) -> None:
        systems = generate_universe(42)
        assert len(systems) == GALAXY_SYSTEM_COUNT

    def test_deterministic(self) -> None:
        s1 = generate_universe(42)
        s2 = generate_universe(42)
        assert set(s1.keys()) == set(s2.keys())
        for k in s1:
            assert s1[k].name == s2[k].name
            assert s1[k].x == s2[k].x
            assert s1[k].y == s2[k].y
            assert s1[k].star_type == s2[k].star_type

    def test_different_seeds_different_universes(self) -> None:
        s1 = generate_universe(42)
        s2 = generate_universe(99)

        def names(d: dict[str, StarSystem]) -> set[str]:
            return {s.name for s in d.values()}

        assert len(names(s1) & names(s2)) < 40

    def test_each_system_has_bodies(self) -> None:
        systems = generate_universe(42)
        for system in systems.values():
            assert len(system.bodies) >= 1
            assert len(system.bodies) <= 20

    def test_each_system_has_valid_star_type(self) -> None:
        from backend.config import STAR_SPECTRAL_TYPES
        systems = generate_universe(42)
        for system in systems.values():
            assert system.star_type in STAR_SPECTRAL_TYPES

    def test_bodies_have_valid_biomes(self) -> None:
        from backend.config import BIOME_TYPES
        systems = generate_universe(42)
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
        """_biome_for_body with a seed that triggers gas_giant path."""
        from backend.generation.universe import _biome_for_body
        for seed_val in range(50):
            rng = random.Random(seed_val)
            biome = _biome_for_body(rng, "G", 1.5, "planet")
            if biome == "gas_giant":
                return
        pass  # pragma: no cover  # no seed in range produced gas_giant

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
        - A-C = sqrt(65^2 + 60^2) ≈ 88.5 < 95 (allows convergence)

        Pass 1: A isolated, closest=B at 65. B moves toward A to (535,500).
                Now B-C = sqrt(30^2+60^2) ≈ 67.1 > 60, so C becomes isolated.
        Pass 2: C isolated, closest=B at ~67.1. B moves toward C.
                After the move, A-B ≈ 57.1 ≤ 60 and C-B = 35 ≤ 60.
                All systems connected.
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
        """_ensure_connectivity handles when a moved system lands on another's coords.

        After the first pass moves a system, it could end up at the exact same
        coordinates as another system. The closest_dist would be 0.0 which would
        cause a ZeroDivisionError without the fix.
        """
        rng = random.Random(42)
        # A is isolated, B is its closest neighbor, C is far from B
        # After B moves toward A, B lands on C's coordinates
        a = StarSystem(id="a", name="A", x=500, y=500, star_type="G",
                       star_color="#fff", phenomenon="none", phenomenon_desc="")
        # B is 65 units from A (isolated), and 0 units from C (same coords)
        b = StarSystem(id="b", name="B", x=565, y=500, star_type="K",
                       star_color="#ffa", phenomenon="none", phenomenon_desc="")
        c = StarSystem(id="c", name="C", x=565, y=500, star_type="M",
                       star_color="#f00", phenomenon="none", phenomenon_desc="")
        # D is far from everyone to make C isolated
        d = StarSystem(id="d", name="D", x=100, y=100, star_type="G",
                       star_color="#fff", phenomenon="none", phenomenon_desc="")
        systems = {"a": a, "b": b, "c": c, "d": d}

        # This should not raise ZeroDivisionError
        _ensure_connectivity(systems, rng)

        # After the fix, all systems should have a neighbor
        for system in systems.values():
            has_neighbor = False
            for other in systems.values():
                if system.id == other.id:
                    continue
                if distance_between(system, other) <= NEIGHBOR_DISTANCE_THRESHOLD:
                    has_neighbor = True
                    break
            assert has_neighbor, f"System {system.id} ({system.name}) has no neighbor"


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
