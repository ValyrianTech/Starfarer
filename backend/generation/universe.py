"""
Procedural universe generation system.

Provides functions for generating a deterministic galaxy of star
systems with planets, moons, and celestial phenomena using a seed-based
random number generator. Also includes distance calculations and
connectivity enforcement.
"""

import random
import math

from backend.config import (
    GALAXY_SYSTEM_COUNT, GALAXY_WIDTH, GALAXY_HEIGHT,
    STAR_SPECTRAL_TYPES, STAR_COLORS, SYSTEM_PHENOMENA, PHENOMENON_WEIGHTS,
    PLANET_NAMES, MOON_NAMES, BIOME_TYPES, MIN_ORBITALS, MAX_ORBITALS,
)
from backend.models.system import StarSystem, Body


def seeded_random(seed: int, *extra: str) -> random.Random:
    """Create a deterministic random number generator from a seed.

    Combines the base seed with any number of extra string arguments
    to produce a reproducible RNG instance.

    :param seed: The base universe seed.
    :type seed: int
    :param extra: Additional strings to mix into the seed for
        independent RNG streams.
    :type extra: str
    :returns: A seeded :class:`random.Random` instance.
    :rtype: random.Random
    """
    rng = random.Random(str(seed) + "".join(str(e) for e in extra))
    return rng


def _pick_weighted(rng: random.Random, items: list[str], weights: list[int]) -> str:
    """Pick a random item from a list using weighted probabilities.

    Uses ``rng.choices`` to select one item from ``items`` according
    to the corresponding ``weights``.

    :param rng: The seeded random number generator.
    :type rng: random.Random
    :param items: The list of items to choose from.
    :type items: list[str]
    :param weights: The weight for each item, corresponding 1:1 with
        ``items``.
    :type weights: list[int]
    :returns: The selected item.
    :rtype: str
    """
    return rng.choices(items, weights=weights, k=1)[0]


def _system_name(rng: random.Random, idx: int, x: float, y: float) -> str:
    """Generate a pseudo-astronomical name for a star system.

    Combines a prefix or suffix with a random sector letter and
    number to produce names like "Proxima A342" or "Vega B7891".

    :param rng: The seeded random number generator.
    :type rng: random.Random
    :param idx: The index of this system in the generation sequence.
    :type idx: int
    :param x: The x-coordinate of the system in the galaxy.
    :type x: float
    :param y: The y-coordinate of the system in the galaxy.
    :type y: float
    :returns: A generated system name string.
    :rtype: str
    """
    prefixes = ["Proxima", "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Nova", "Kepler", "Gliese"]
    suffixes = ["Prime", "Majoris", "Minoris", "Centauri", "Draconis", "Lyrae", "Andromedae", "Cygni", "Rigel", "Vega"]
    sector = chr(65 + rng.randint(0, 25))
    num = rng.randint(100, 9999)
    if rng.random() < 0.4:
        return f"{rng.choice(prefixes)} {sector}{num}"
    else:
        return f"{rng.choice(suffixes)} {sector}{num}"


def _star_type(rng: random.Random) -> str:
    """Pick a random star spectral type using weighted probabilities.

    Uses the predefined ``STAR_SPECTRAL_TYPES`` with weights
    favouring cooler, more common stars (K, M) over rare hot stars
    (O, B).

    :param rng: The seeded random number generator.
    :type rng: random.Random
    :returns: A star spectral type letter (e.g. ``"G"``, ``"K"``).
    :rtype: str
    """
    weights = [1, 3, 5, 10, 20, 25, 36]
    return rng.choices(STAR_SPECTRAL_TYPES, weights=weights, k=1)[0]


def _generate_body_name(rng: random.Random, body_type: str, idx: int, parent_name: str) -> str:
    """Generate a name for a celestial body.

    Uses planet name pools for planets, moon name pools for moons,
    and a descriptive belt name for asteroid belts.

    :param rng: The seeded random number generator.
    :type rng: random.Random
    :param body_type: The type of body (``"planet"``, ``"moon"``, or
        ``"asteroid_belt"``).
    :type body_type: str
    :param idx: The index of this body in the orbital sequence.
    :type idx: int
    :param parent_name: The name of the parent star system.
    :type parent_name: str
    :returns: A generated body name string.
    :rtype: str
    """
    if body_type == "planet":
        name_pool = PLANET_NAMES.copy()
        rng.shuffle(name_pool)
        return f"{name_pool[0]} {idx + 1}"
    elif body_type == "moon":
        name_pool = MOON_NAMES.copy()
        rng.shuffle(name_pool)
        return f"{name_pool[0]}"
    elif body_type == "asteroid_belt":
        return f"{parent_name} Belt"
    return f"Body {idx}"


def _biome_for_body(rng: random.Random, star_type: str, distance: float, body_type: str) -> str:
    """Determine the biome type for a celestial body.

    Selects a biome based on the body type, its distance from the
    star, and the star's spectral type. Inner orbits tend toward
    volcanic or barren; outer orbits lean toward tundra or gas
    giants. Sun-like stars (G, K) in the habitable zone may produce
    jungle or ocean biomes.

    :param rng: The seeded random number generator.
    :type rng: random.Random
    :param star_type: The spectral type of the parent star.
    :type star_type: str
    :param distance: The body's distance from the star as a fraction
        of the system radius (0.0--1.0).
    :type distance: float
    :param body_type: The type of body (``"planet"``, ``"moon"``, or
        ``"asteroid_belt"``).
    :type body_type: str
    :returns: A biome type string (e.g. ``"desert"``, ``"jungle"``).
    :rtype: str
    """
    if body_type == "asteroid_belt":
        return "barren"
    if body_type == "moon":
        return rng.choice(BIOME_TYPES[:5])
    if distance < 0.3:
        return rng.choice(["volcanic", "barren", "crystal"])
    elif distance < 0.6:
        if star_type in ("G", "K"):
            return rng.choice(["jungle", "ocean", "desert", "tundra"])
        return rng.choice(["desert", "barren", "crystal"])
    elif distance < 1.0:
        return rng.choice(["tundra", "barren", "ocean", "desert"])
    else:
        if rng.random() < 0.15:
            return "gas_giant"
        return rng.choice(["tundra", "barren"])


def _body_description(rng: random.Random, body_type: str, biome: str, star_type: str) -> str:
    """Pick a flavour text description for a celestial body.

    Selects a random descriptive sentence from a biome-specific pool
    of flavour texts. Falls back to a generic description if the
    biome is unrecognised.

    :param rng: The seeded random number generator.
    :type rng: random.Random
    :param body_type: The type of body (``"planet"``, ``"moon"``,
        etc.).
    :type body_type: str
    :param biome: The biome of the body.
    :type biome: str
    :param star_type: The spectral type of the parent star.
    :type star_type: str
    :returns: A flavour text description string.
    :rtype: str
    """
    descs = {
        "desert": [
            "A vast expanse of rust-colored dunes stretches beneath twin suns.",
            "Windswept plateaus and deep canyons scar the arid surface.",
            "Ancient dry seabeds hint at a once-thriving ocean world.",
        ],
        "tundra": [
            "Endless ice plains glitter under the distant star.",
            "Frozen geysers erupt periodically, spraying crystalline mist.",
            "Subsurface oceans churn beneath kilometers of ice.",
        ],
        "jungle": [
            "Dense canopy teems with bioluminescent life.",
            "Thick vegetation covers every inch of the surface.",
            "The air is thick with spores and the sounds of alien wildlife.",
        ],
        "ocean": [
            "A deep blue world with no landmasses in sight.",
            "Endless storms churn the vast global ocean.",
            "Submerged mountain ranges create shallow archipelagos.",
        ],
        "volcanic": [
            "Rivers of molten rock flow across a perpetually dark surface.",
            "Towering volcanoes belch ash into the thick atmosphere.",
            "The ground trembles constantly with seismic activity.",
        ],
        "barren": [
            "A lifeless grey rock, cratered and silent.",
            "Nothing but dust and rock as far as sensors can detect.",
            "The remains of ancient structures protrude from the regolith.",
        ],
        "gas_giant": [
            "Swirling bands of colorful gas stretch across the horizon.",
            "Massive storms larger than entire planets rage below.",
            "Floating cities of a bygone era drift in the upper atmosphere.",
        ],
        "crystal": [
            "Massive crystalline formations refract light into prismatic displays.",
            "The entire surface seems to be made of translucent minerals.",
            "Strange energy patterns pulse through the crystal lattice.",
        ],
    }
    return rng.choice(descs.get(biome, ["An unremarkable celestial body."]))


def generate_system(rng: random.Random, idx: int, galaxy_rng: random.Random) -> StarSystem:
    """Generate a single star system with all its orbiting bodies.

    Produces a star system with a random position in the galaxy,
    a spectral type, an optional phenomenon, and a randomized set
    of planets, moons, and asteroid belts.

    :param rng: Seeded RNG for system details (names, biomes, etc.).
    :type rng: random.Random
    :param idx: The index of this system in the generation sequence.
    :type idx: int
    :param galaxy_rng: Seeded RNG for system positions.
    :type galaxy_rng: random.Random
    :returns: A fully generated :class:`StarSystem`.
    :rtype: StarSystem
    """
    x = galaxy_rng.uniform(50, GALAXY_WIDTH - 50)
    y = galaxy_rng.uniform(50, GALAXY_HEIGHT - 50)

    sys_id = f"sys_{idx:04d}"
    name = _system_name(rng, idx, x, y)
    star_type = _star_type(rng)
    star_color = STAR_COLORS[star_type]
    phenomenon = _pick_weighted(rng, SYSTEM_PHENOMENA, PHENOMENON_WEIGHTS)

    phenom_descs = {
        "none": "Standard stellar neighborhood.",
        "nebula": "A colourful nebula bathes the system in ethereal light.",
        "asteroid_field": "A dense asteroid field surrounds the system.",
        "binary_star": "Two stars orbit each other in an eternal dance.",
        "pulsar": "A rapidly rotating neutron star sweeps the system with radiation.",
        "black_hole": "A dark singularity lurks at the system's edge.",
        "ancient_gate": "A massive alien structure orbits silently.",
    }
    phenomenon_desc = phenom_descs.get(phenomenon, "A curious phenomenon.")

    num_bodies = rng.randint(MIN_ORBITALS, min(MAX_ORBITALS, 3 + idx % 5))
    bodies = []
    for b_idx in range(num_bodies):
        body_type = rng.choice(["planet", "planet", "planet", "asteroid_belt", "planet"])
        body_id = f"{sys_id}_b{b_idx}"
        distance = (b_idx + 1) / (num_bodies + 1)
        biome = _biome_for_body(rng, star_type, distance, body_type)
        size = rng.randint(2, 8)
        body_name = _generate_body_name(rng, body_type, b_idx, name)
        desc = _body_description(rng, body_type, biome, star_type)
        poi_count = rng.randint(1, 4) if body_type == "planet" else 1
        body = Body(
            id=body_id, name=body_name, body_type=body_type,
            biome=biome, size=size, distance_from_star=round(distance, 2),
            description=desc, poi_count=poi_count,
        )
        bodies.append(body)

        if body_type == "planet" and size >= 4 and rng.random() < 0.4:
            moon_count = rng.randint(1, 3)
            for m_idx in range(moon_count):
                moon_id = f"{sys_id}_b{b_idx}_m{m_idx}"
                moon_name = _generate_body_name(rng, "moon", m_idx, body_name)
                moon_biome = _biome_for_body(rng, star_type, distance, "moon")
                moon = Body(
                    id=moon_id, name=moon_name, body_type="moon",
                    biome=moon_biome, size=rng.randint(1, 3),
                    distance_from_star=round(distance, 2),
                    description=_body_description(rng, "moon", moon_biome, star_type),
                    poi_count=rng.randint(1, 2),
                )
                bodies.append(moon)

    return StarSystem(
        id=sys_id, name=name, x=x, y=y,
        star_type=star_type, star_color=star_color,
        phenomenon=phenomenon, phenomenon_desc=phenomenon_desc,
        bodies=bodies,
    )


MAX_INITIAL_JUMP = 40
NEIGHBOR_DISTANCE_THRESHOLD = 60


def generate_universe(seed: int, system_count: int = GALAXY_SYSTEM_COUNT) -> dict[str, StarSystem]:
    """Generate the complete galaxy of star systems.

    Creates the specified number of star systems using deterministic,
    seed-based RNGs for layout and details. Ensures every system has
    at least one neighbor within a reasonable distance.

    :param seed: The universe generation seed for deterministic
        reproducibility.
    :type seed: int
    :param system_count: The number of star systems to generate
        (defaults to ``GALAXY_SYSTEM_COUNT``).
    :type system_count: int
    :returns: A dictionary mapping system IDs to :class:`StarSystem`
        instances.
    :rtype: dict[str, StarSystem]
    """
    galaxy_rng = seeded_random(seed, "galaxy_layout")
    system_rng = seeded_random(seed, "system_detail")

    systems = {}
    for i in range(system_count):
        sys = generate_system(system_rng, i, galaxy_rng)
        systems[sys.id] = sys

    _ensure_connectivity(systems, galaxy_rng)

    return systems


def _ensure_connectivity(systems: dict[str, StarSystem], rng: random.Random) -> None:
    """Ensure every star system has at least one neighbor nearby.

    Uses a multi-pass approach: an initial pass detects and fixes isolated
    systems by moving their closest neighbor closer, followed by iterative
    verification passes that recheck all systems and apply the same fix
    until no isolated systems remain.  A maximum iteration limit prevents
    infinite loops.

    :param systems: The dictionary of star systems keyed by system ID.
    :type systems: dict[str, StarSystem]
    :param rng: The seeded random number generator.
    :type rng: random.Random
    """
    max_iters = 10

    def _find_and_fix_isolated(sys_list: list[StarSystem]) -> bool:
        """Run one pass: find isolated systems and fix them.

        :returns: ``True`` if any fixes were applied, ``False`` otherwise.
        :rtype: bool
        """
        fixed = False
        modifications = []  # List of (system, new_x, new_y) tuples

        for i, sys in enumerate(sys_list):
            has_neighbor = False
            for j, other in enumerate(sys_list):
                if i == j:
                    continue
                d = distance_between(sys, other)
                if d <= NEIGHBOR_DISTANCE_THRESHOLD:
                    has_neighbor = True
                    break
            if not has_neighbor:
                closest_idx = None
                closest_dist = float("inf")
                for j, other in enumerate(sys_list):
                    if i == j:
                        continue
                    d = distance_between(sys, other)
                    if d < closest_dist:
                        closest_dist = d
                        closest_idx = j
                if closest_idx is not None:
                    target = sys_list[closest_idx]
                    if closest_dist < 1e-9:  # pragma: no cover
                        # Systems are at the same coordinates; move the target slightly
                        target.x = rng.uniform(-5, 5)
                        target.y = rng.uniform(-5, 5)
                        target.x = max(50, min(GALAXY_WIDTH - 50, target.x))
                        target.y = max(50, min(GALAXY_HEIGHT - 50, target.y))
                        fixed = True
                        continue
                    new_x = sys.x + (target.x - sys.x) * (MAX_INITIAL_JUMP - 5) / closest_dist
                    new_y = sys.y + (target.y - sys.y) * (MAX_INITIAL_JUMP - 5) / closest_dist
                    new_x = max(50, min(GALAXY_WIDTH - 50, new_x))
                    new_y = max(50, min(GALAXY_HEIGHT - 50, new_y))
                    modifications.append((target, new_x, new_y))
                    fixed = True

        # Apply all modifications after iteration
        for target, new_x, new_y in modifications:
            target.x = new_x
            target.y = new_y

        return fixed

    for _ in range(max_iters):
        sys_list = list(systems.values())
        if not _find_and_fix_isolated(sys_list):
            break


def distance_between(sys1: StarSystem, sys2: StarSystem) -> float:
    """Calculate the Euclidean distance between two star systems.

    :param sys1: The first star system.
    :type sys1: StarSystem
    :param sys2: The second star system.
    :type sys2: StarSystem
    :returns: The straight-line distance in galaxy coordinate units.
    :rtype: float
    """
    dx = sys1.x - sys2.x
    dy = sys1.y - sys2.y
    return math.sqrt(dx * dx + dy * dy)
