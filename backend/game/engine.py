"""
Core game engine module for navigation and exploration.

Provides functions for hyperspace jumps, system scanning, surface
landing, surface exploration, and nearby system discovery.
"""

import random
import uuid
import logging
from typing import Any, Optional

from backend.config import (
    JUMP_FUEL_COST_PER_LY, SCAN_FUEL_COST, EXPLORE_FUEL_COST,
    MORALE_DECAY_PER_JUMP,
)
from backend.models.game_state import GameState
from backend.models.ship import Ship
from backend.models.system import StarSystem, Body
from backend.models.discovery import Discovery
from backend.utils import deterministic_hash
from backend.generation.universe import distance_between
from backend.generation.lore import get_fragment_for_body


def can_jump(ship: Ship, target: StarSystem, current: Optional[StarSystem]) -> tuple[bool, float, str]:
    """Check whether a jump to a target system is possible.

    Validates that the ship has sufficient fuel and jump range to
    reach the target system from the current system.

    :param ship: The player's ship.
    :type ship: Ship
    :param target: The target star system to jump to.
    :type target: StarSystem
    :param current: The ship's current star system.
    :type current: StarSystem
    :returns: A tuple of ``(can_jump, fuel_cost, message)`` where
        ``can_jump`` indicates whether the jump is allowed,
        ``fuel_cost`` is the estimated fuel required, and ``message``
        is an empty string on success or an error description.
    :rtype: tuple[bool, float, str]
    """
    if ship.current_system_id == target.id:
        return False, 0, "Already in this system."
    if not current:
        return False, 0, "No current system."
    dist = distance_between(current, target)
    dist_ly = round(dist / 10.0, 1)
    fuel_cost = max(1, int(dist_ly * JUMP_FUEL_COST_PER_LY))
    if fuel_cost > ship.fuel:
        return False, fuel_cost, f"Not enough fuel. Need {fuel_cost}, have {ship.fuel}."
    if dist_ly > ship.jump_range:
        return False, fuel_cost, f"Distance {dist_ly} LY exceeds jump range {ship.jump_range}."
    return True, fuel_cost, ""


def perform_jump(state: GameState, target_system: StarSystem, fuel_cost: int | float) -> str:
    """Execute a hyperspace jump to the target star system.

    Deducts fuel, applies morale decay (modified by life support
    upgrades), updates the ship's location, marks the target system
    as visited, and logs the jump.

    :param state: The current game state.
    :type state: GameState
    :param target_system: The destination star system.
    :type target_system: StarSystem
    :param fuel_cost: The amount of fuel to deduct.
    :type fuel_cost: int
    :returns: A status message describing the jump result.
    :rtype: str
    """
    current = state.get_current_system() or state.systems.get(state.ship.current_system_id)
    state.ship.fuel -= int(fuel_cost)

    life_support_level = state.ship.morale_decay_reduction
    morale_decay = max(1, MORALE_DECAY_PER_JUMP - life_support_level)
    state.ship.morale = max(0, state.ship.morale - morale_decay)
    state.ship.current_system_id = target_system.id
    state.ship.current_body_id = None
    target_system.visited = True
    state.systems_visited = sum(1 for s in state.systems.values() if s.visited)

    if current:
        dist = distance_between(current, target_system)
        state.add_log("navigation", f"Jumped from {current.name} to {target_system.name} ({round(dist/10, 1)} LY). Fuel cost: {fuel_cost}.")
    else:
        state.add_log("navigation", f"Arrived at {target_system.name}.")

    if target_system.phenomenon != "none":
        state.add_log("discovery", f"Detected phenomenon: {target_system.phenomenon_desc}")

    return f"Jumped to {target_system.name}."


def perform_scan(state: GameState) -> str:
    """Scan the current star system for orbital bodies.

    Deducts scan fuel cost, marks the current system as scanned,
    and logs the number of bodies detected.

    :param state: The current game state.
    :type state: GameState
    :returns: A status message describing the scan result.
    :rtype: str
    """
    ship = state.ship
    if ship.fuel < SCAN_FUEL_COST:
        return "Not enough fuel to scan."
    system = state.get_current_system()
    if not system:
        return "No current system to scan."
    ship.fuel -= SCAN_FUEL_COST
    system.scanned = True
    state.add_log("exploration", f"Scanned {system.name}. {len(system.bodies)} orbital bodies detected.")
    return f"Scan complete. {len(system.bodies)} bodies found."


def get_nearby_systems(state: GameState) -> list[dict]:
    """Find all systems within jump range of the current system.

    Calculates distance and fuel cost to every other system in the
    galaxy and returns those within the ship's jump range, sorted
    by distance.

    :param state: The current game state.
    :type state: GameState
    :returns: A list of dictionaries with system info including
        id, name, distance_ly, fuel_cost, star_type, star_color,
        phenomenon, visited, scanned, and reachable flags.
    :rtype: list[dict]
    """
    ship = state.ship
    current = state.get_current_system()
    if not current:
        return []
    nearby: list[dict[str, Any]] = []
    for sys_id, sys_data in state.systems.items():
        if sys_id == ship.current_system_id:
            continue
        dist = distance_between(current, sys_data)
        dist_ly = round(dist / 10.0, 1)
        fuel_cost = max(1, int(dist_ly * JUMP_FUEL_COST_PER_LY))
        reachable = dist_ly <= ship.jump_range and fuel_cost <= ship.fuel
        nearby.append({
            "id": sys_data.id,
            "name": sys_data.name,
            "distance_ly": dist_ly,
            "fuel_cost": fuel_cost,
            "star_type": sys_data.star_type,
            "star_color": sys_data.star_color,
            "phenomenon": sys_data.phenomenon,
            "visited": sys_data.visited,
            "scanned": sys_data.scanned,
            "reachable": reachable,
        })
    nearby.sort(key=lambda s: s["distance_ly"])
    return nearby


def land_on_body(state: GameState, body_id: str) -> tuple[bool, str]:
    """Land the ship on a specified celestial body.

    Searches the current system's bodies for the given body ID,
    updates the ship's location, marks the body as explored, and
    logs the landing.

    :param state: The current game state.
    :type state: GameState
    :param body_id: The unique identifier of the body to land on.
    :type body_id: str
    :returns: A tuple of ``(success, message)``.
    :rtype: tuple[bool, str]
    """
    system = state.get_current_system()
    if not system:
        return False, "No current system."
    target = None
    for body in system.bodies:
        if body.id == body_id:
            target = body
            break
    if not target:
        return False, f"Body {body_id} not found in this system."
    state.ship.current_body_id = body_id
    target.explored = True
    state.add_log("exploration", f"Landed on {target.name}, a {target.biome} {target.body_type}.")
    return True, f"Landed on {target.name}."



def explore_surface(state: GameState) -> list[Discovery]:
    """Explore the surface of the currently landed-on body.

    Deducts explore fuel cost and generates a random number of
    discoveries based on the body's points of interest count.
    Discoveries are appended to the game state and returned.
    If a lore fragment is attached to the current body, it is
    linked to one of the generated discoveries.

    :param state: The current game state.
    :type state: GameState
    :returns: A list of newly generated :class:`Discovery` objects.
    :rtype: list[Discovery]
    """
    system = state.get_current_system()
    if not system:
        return []
    ship = state.ship
    if ship.fuel < EXPLORE_FUEL_COST:
        return []

    body = None
    for b in system.bodies:
        if b.id == ship.current_body_id:
            body = b
            break
    if not body:
        return []

    if body.poi_count == 0:
        return []

    discoveries = []
    item_rng = random.Random(state.seed + len(state.discoveries) + deterministic_hash(body.id))

    num_finds = min(body.poi_count, item_rng.randint(1, 3))

    ship.fuel -= EXPLORE_FUEL_COST

    lore_frag = get_fragment_for_body(system.id, body.id, state.lore_fragments)
    lore_assigned = False

    for i in range(num_finds):
        cat = item_rng.choice(["mineral", "artifact", "lifeform", "signal", "ruin"])
        disc = _generate_discovery(item_rng, cat, body, system)

        if lore_frag and not lore_assigned and not lore_frag.discovered:
            disc.lore_fragment_id = lore_frag.id
            lore_frag.discovered = True
            lore_assigned = True
            state.add_log("lore", f"Discovered lore fragment: {lore_frag.title} ({lore_frag.id}).")
        elif lore_frag and not lore_assigned and lore_frag.discovered:
            logging.warning(f"Lore fragment {lore_frag.id} ({lore_frag.title}) is already discovered but found on body {body.id}.")

        discoveries.append(disc)
        state.discoveries.append(disc)

    state.add_log("exploration", f"Explored {body.name}. Found {len(discoveries)} points of interest.")
    return discoveries


def _generate_discovery(rng: random.Random, category: str, body: Body, system: StarSystem) -> Discovery:
    """Generate a single discovery for a surface exploration.

    Creates a randomised discovery (mineral, artifact, lifeform,
    signal, or ruin) with a name, description, and credit value
    tied to the current system and body.

    :param rng: The seeded random number generator for discovery
        details.
    :type rng: random.Random
    :param category: The category of discovery (``"mineral"``,
        ``"artifact"``, ``"lifeform"``, ``"signal"``, or
        ``"ruin"``).
    :type category: str
    :param body: The celestial body being explored.
    :type body: Body
    :param system: The star system containing the body.
    :type system: StarSystem
    :returns: A newly generated :class:`Discovery`.
    :rtype: Discovery
    """
    names = {
        "mineral": ["Plasmic Crystal", "Void Ore", "Stellar Fragment", "Obsidian Shard", "Nebula Dust"],
        "artifact": ["Ancient Relic", "Alien Device", "Glyph Tablet", "Memory Core", "Void Key"],
        "lifeform": ["Glowvine", "Crystal Mite", "Void Spore", "Plasma Jelly", "Singing Stone"],
        "signal": ["Distress Beacon", "Encrypted Transmission", "Nav Echo", "Subspace Ripple", "Ghost Signal"],
        "ruin": ["Weathered Pillar", "Sunken Chamber", "Broken Obelisk", "Overgrown Temple", "Fallen Tower"],
    }
    descs = {
        "mineral": [
            "Rare mineral deposits glitter in the light.",
            "Crystalline structures pulse with latent energy.",
            "Valuable ore veins run deep into the crust.",
        ],
        "artifact": [
            "An object of unknown origin, clearly not natural.",
            "Strange markings cover its perfectly smooth surface.",
            "It hums faintly with an ancient power source.",
        ],
        "lifeform": [
            "A species unlike any in the database.",
            "Bioluminescent organisms thrive in this environment.",
            "Strange flora adapted to extreme conditions.",
        ],
        "signal": [
            "A repeating pattern suggests intelligent origin.",
            "The signal fades in and out, barely detectable.",
            "Coordinates are encoded within the transmission.",
        ],
        "ruin": [
            "Ancient architecture, weathered by millennia.",
            "Crumbling walls hint at a once-great civilization.",
            "Strange symbols cover every surface.",
        ],
    }
    d_id = str(uuid.uuid4())[:12]
    name = rng.choice(names[category])
    desc = rng.choice(descs[category])
    value = rng.randint(10, 200)
    return Discovery(
        id=d_id, category=category, name=name, description=desc,
        value=value, system_id=system.id, body_id=body.id,
    )
