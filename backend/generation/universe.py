import random
import math

from backend.config import (
    GALAXY_SYSTEM_COUNT, GALAXY_WIDTH, GALAXY_HEIGHT,
    STAR_SPECTRAL_TYPES, STAR_COLORS, SYSTEM_PHENOMENA, PHENOMENON_WEIGHTS,
    PLANET_NAMES, MOON_NAMES, BIOME_TYPES, MIN_ORBITALS, MAX_ORBITALS,
)
from backend.models.system import StarSystem, Body


def seeded_random(seed: int, *extra: str) -> random.Random:
    rng = random.Random(str(seed) + "".join(str(e) for e in extra))
    return rng


def _pick_weighted(rng: random.Random, items: list[str], weights: list[int]) -> str:
    return rng.choices(items, weights=weights, k=1)[0]


def _system_name(rng: random.Random, idx: int, x: float, y: float) -> str:
    prefixes = ["Proxima", "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Nova", "Kepler", "Gliese"]
    suffixes = ["Prime", "Majoris", "Minoris", "Centauri", "Draconis", "Lyrae", "Andromedae", "Cygni", "Rigel", "Vega"]
    sector = chr(65 + rng.randint(0, 25))
    num = rng.randint(100, 9999)
    if rng.random() < 0.4:
        return f"{rng.choice(prefixes)} {sector}{num}"
    else:
        return f"{rng.choice(suffixes)} {sector}{num}"


def _star_type(rng: random.Random) -> str:
    weights = [1, 3, 5, 10, 20, 25, 36]
    return rng.choices(STAR_SPECTRAL_TYPES, weights=weights, k=1)[0]


def _generate_body_name(rng: random.Random, body_type: str, idx: int, parent_name: str) -> str:
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
    galaxy_rng = seeded_random(seed, "galaxy_layout")
    system_rng = seeded_random(seed, "system_detail")

    systems = {}
    for i in range(system_count):
        sys = generate_system(system_rng, i, galaxy_rng)
        systems[sys.id] = sys

    _ensure_connectivity(systems, galaxy_rng)

    return systems


def _ensure_connectivity(systems: dict[str, StarSystem], rng: random.Random) -> None:
    sys_list = list(systems.values())
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
                target.x = sys.x + (target.x - sys.x) * (MAX_INITIAL_JUMP - 5) / closest_dist
                target.y = sys.y + (target.y - sys.y) * (MAX_INITIAL_JUMP - 5) / closest_dist


def distance_between(sys1: StarSystem, sys2: StarSystem) -> float:
    dx = sys1.x - sys2.x
    dy = sys1.y - sys2.y
    return math.sqrt(dx * dx + dy * dy)
