import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.generation.universe import generate_universe, distance_between
from backend.models.system import StarSystem
from backend.models.ship import Ship
from backend.models.game_state import GameState
from backend.models.event import Event, Choice
from backend.models.discovery import Discovery, LoreFragment
from backend.config import GALAXY_SYSTEM_COUNT


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
