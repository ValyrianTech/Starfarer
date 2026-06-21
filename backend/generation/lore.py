"""
Lore fragment distribution and discovery system.

Provides functions for generating lore fragment objects from content
definitions, distributing them deterministically across the galaxy,
and querying fragments by system or body.
"""

import random
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from backend.generation.lore_content import FRAGMENT_DATA
from backend.models.discovery import LoreFragment
from backend.models.system import StarSystem
from backend.utils import seeded_random

# Biome weights for fragment distribution: higher biome types are
# more likely to host lore fragments, rewarding thorough exploration.
BIOME_WEIGHTS = {
    "ocean": 5,
    "jungle": 5,
    "crystal": 5,
    "desert": 1,
    "tundra": 1,
    "volcanic": 1,
    "barren": 1,
    "gas_giant": 1,
}

MAX_FRAGMENTS_PER_SYSTEM = 2


def get_all_lore_fragments() -> list[LoreFragment]:
    """Create :class:`LoreFragment` objects from all defined content.
    :returns: A list of 20 :class:`LoreFragment` instances, one per fragment.
    :rtype: list[LoreFragment]
    """
    fragments: list[LoreFragment] = []
    for data in FRAGMENT_DATA:
        frag_id = f"lore_{data['arc']}_{data['fragment_number']}"
        fragments.append(LoreFragment(
            id=frag_id,
            arc=str(data["arc"]),
            title=str(data["title"]),
            text=str(data["text"]),
            fragment_number=data["fragment_number"],
        ))
    return fragments


def distribute_lore_fragments(
    seed: int,
    systems: dict[str, StarSystem],
    max_per_system: int = MAX_FRAGMENTS_PER_SYSTEM,
) -> dict[str, list[LoreFragment]]:
    """Assign lore fragments to celestial bodies across the galaxy.

    Uses a deterministic, seed-based RNG to distribute fragments so
    that the same seed always produces the same placements. Higher-value
    biomes (ocean, jungle, crystal) have a higher probability of hosting
    fragments.

    Each fragment is assigned a ``system_id`` and ``body_id`` recorded
    in the fragment's ``discovery_id`` field (format: ``"system_id::body_id"``).
    No system receives more than *max_per_system* fragments.

    :param seed: The universe generation seed.
    :type seed: int
    :param systems: The generated star systems keyed by system ID.
    :type systems: dict[str, StarSystem]
    :param max_per_system: Maximum fragments allowed per star system.
    :type max_per_system: int
    :returns: A mapping of system ID to the list of :class:`LoreFragment`
        objects assigned to that system.
    :rtype: dict[str, list[LoreFragment]]
    """
    rng = seeded_random(seed, "lore_distribution")
    fragments = get_all_lore_fragments()
    rng.shuffle(fragments)

    system_fragment_count: dict[str, int] = {}
    placement: dict[str, list[LoreFragment]] = {}
    used_bodies: set[tuple[str, str]] = set()

    for frag in fragments:
        try:
            chosen_sys_id, chosen_body_id = _pick_lore_location(
                rng, systems, system_fragment_count, max_per_system, used_bodies
            )
        except ValueError as e:
            logger.warning("No eligible location for fragment %s, skipping", frag.id)
            continue

        frag.discovery_id = f"{chosen_sys_id}::{chosen_body_id}"
        used_bodies.add((chosen_sys_id, chosen_body_id))

        system_fragment_count[chosen_sys_id] = \
            system_fragment_count.get(chosen_sys_id, 0) + 1

        if chosen_sys_id not in placement:
            placement[chosen_sys_id] = []
        placement[chosen_sys_id].append(frag)

    placed = sum(len(f) for f in placement.values())
    total = len(fragments)
    if placed == total:
        logging.info("All %d lore fragments placed successfully", placed)
    else:
        logging.info("Only %d/%d lore fragments could be placed", placed, total)
    return placement


def _pick_lore_location(
    rng: random.Random,
    systems: dict[str, StarSystem],
    counts: dict[str, int],
    max_per_system: int,
    used_bodies: set[tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """Pick a random system and body to host a lore fragment.

    Systems are weighted by the combined biome scores of their bodies.
    A random body within the chosen system is then selected. Systems
    already at *max_per_system* are excluded. Bodies already assigned
    to a fragment (in *used_bodies*) are excluded.

    :param rng: Seeded random number generator.
    :type rng: random.Random
    :param systems: All star systems keyed by ID.
    :type systems: dict[str, StarSystem]
    :param counts: Current fragment count per system.
    :type counts: dict[str, int]
    :param max_per_system: Maximum fragments per system.
    :type max_per_system: int
    :param used_bodies: Set of ``(system_id, body_id)`` tuples already assigned to a fragment.
        When ``None`` (the default), no bodies are pre-excluded — the parameter is
        treated as an empty set internally.
    :type used_bodies: set[tuple[str, str]] | None
    :returns: A tuple of ``(system_id, body_id)``.
    :rtype: tuple[str, str]
    :raises ValueError: If no eligible system is available.
    """
    if used_bodies is None:
        used_bodies = set()
    eligible_systems: list[str] = []
    weights: list[int] = []

    for sys_id, system in systems.items():
        if counts.get(sys_id, 0) >= max_per_system:
            continue
        score = 0
        has_available_body = False
        for body in system.bodies:
            if body.poi_count > 0:
                score += BIOME_WEIGHTS.get(body.biome, 1)
                if (sys_id, body.id) not in used_bodies:
                    has_available_body = True
        if score > 0 and has_available_body:
            eligible_systems.append(sys_id)
            weights.append(score)

    if not eligible_systems:
        raise ValueError("No eligible systems available for lore placement")

    chosen_sys_id = rng.choices(eligible_systems, weights=weights, k=1)[0]
    system = systems[chosen_sys_id]

    bodies = [b for b in system.bodies if b.poi_count > 0]
    eligible_bodies = [
        b for b in bodies
        if (chosen_sys_id, b.id) not in used_bodies
    ]
    body_weights = [BIOME_WEIGHTS.get(b.biome, 1) for b in eligible_bodies]
    chosen_body = rng.choices(eligible_bodies, weights=body_weights, k=1)[0]

    return chosen_sys_id, chosen_body.id


def get_fragment_for_body(
    system_id: str,
    body_id: str,
    lore_fragments: list[LoreFragment],
) -> Optional[LoreFragment]:
    """Return the lore fragment assigned to a specific body, if any.

    :param system_id: The ID of the star system.
    :type system_id: str
    :param body_id: The ID of the celestial body.
    :type body_id: str
    :param lore_fragments: All lore fragments in the game.
    :type lore_fragments: list[LoreFragment]
    :returns: The matching :class:`LoreFragment` or ``None``.
    :rtype: Optional[LoreFragment]
    """
    expected = f"{system_id}::{body_id}"
    for frag in lore_fragments:
        if frag.discovery_id == expected:
            return frag
    return None


def get_lore_fragments_for_system(
    system_id: str,
    lore_fragments: list[LoreFragment],
) -> list[LoreFragment]:
    """Return all lore fragments located in a given system.

    :param system_id: The ID of the star system.
    :type system_id: str
    :param lore_fragments: All lore fragments in the game.
    :type lore_fragments: list[LoreFragment]
    :returns: A list of :class:`LoreFragment` objects in that system.
    :rtype: list[LoreFragment]
    """
    results: list[LoreFragment] = []
    for frag in lore_fragments:
        if frag.discovery_id and frag.discovery_id.startswith(f"{system_id}::"):
            results.append(frag)
    return results
