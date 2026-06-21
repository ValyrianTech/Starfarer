"""
Core game engine module for navigation and exploration.

Provides functions for hyperspace jumps, system scanning, surface
landing, surface exploration, and nearby system discovery.
"""

import random
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
from backend.utils import deterministic_hash, seeded_random
from backend.generation.universe import distance_between
from backend.generation.lore import get_fragment_for_body

logger = logging.getLogger(__name__)


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

    state.increment_stranded_turns()

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

    if num_finds > 0:
        lore_frag = get_fragment_for_body(system.id, body.id, state.lore_fragments)
        lore_linked = False

        for i in range(num_finds):
            cat = item_rng.choice(["mineral", "artifact", "lifeform", "signal", "ruin"])
            disc = _generate_discovery(item_rng, cat, body, system)

            if lore_frag and not lore_frag.discovered and not lore_linked:
                # First discovery of this lore fragment — link it to this discovery
                disc.lore_fragment_id = lore_frag.id
                lore_frag.discovered = True
                lore_linked = True
                state.add_log("lore", f"Discovered lore fragment: {lore_frag.title} ({lore_frag.id}).")
            elif lore_frag and lore_frag.discovered and not lore_linked:
                # Lore fragment already discovered in a previous explore action (genuinely stale)
                logger.warning(f"Lore fragment {lore_frag.id} ({lore_frag.title}) already discovered but found on body {body.id}.")
                lore_linked = True

            discoveries.append(disc)
            state.discoveries.append(disc)

    ship.fuel -= EXPLORE_FUEL_COST

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
    d_id = f"{rng.getrandbits(48):012x}"
    name = rng.choice(names[category])
    desc = rng.choice(descs[category])
    value = rng.randint(10, 200)
    return Discovery(
        id=d_id, category=category, name=name, description=desc,
        value=value, system_id=system.id, body_id=body.id,
    )


CRAFT_CONVERSIONS = {
    "artifact": ("fuel", 5),
    "mineral": ("repair", 10),
    "lifeform": ("morale", 15),
    "signal": ("credits", 50),
}


def activate_distress_beacon(state: GameState) -> dict:
    """Activate the distress beacon to call for help when in trouble.

    Can only be used when fuel is at 0 or hull is critically low
    (below 20% of max), and when the distress cooldown is not active.
    Costs 50 credits. Has a 60% chance of attracting a rescue within
    1-3 turns.

    :param state: The current game state.
    :type state: GameState
    :returns: A dictionary with ``error`` on failure, or ``result``,
        ``outcome``, and ``effects`` on success.
    :rtype: dict
    """
    ship = state.ship
    system = state.get_current_system()

    if not system:
        return {"error": "No current system."}

    hull_threshold = int(ship.max_hull * 0.2)
    if ship.fuel > 0 and ship.hull >= hull_threshold:
        return {"error": "Distress beacon can only be activated when fuel is empty or hull is critically low (below 20%)."}

    if ship.distress_cooldown:
        return {"error": "Distress beacon is on cooldown. Wait for it to recharge."}

    if ship.credits < 50:
        return {"error": "Not enough credits. Distress beacon costs 50 credits."}

    ship.credits -= 50
    ship.distress_cooldown = True

    rng = seeded_random(state.seed, "distress", system.id)

    rescued = rng.random() < 0.6
    if not rescued:
        turns = rng.randint(2, 4)
        state.add_log("emergency", f"Distress beacon activated in {system.name}. No response yet — try again in {turns} turns.")
        return {
            "result": f"Distress beacon activated. No response yet — try again in {turns} turns.",
            "outcome": "no_response",
            "effects": {},
        }

    turns = rng.randint(1, 3)
    rescue_roll = rng.random()
    has_station = system.has_trading_station

    if has_station and rescue_roll < 0.3:
        ship.credits = max(0, ship.credits - 100)
        ship.fuel = min(ship.max_fuel, ship.fuel + 20)
        state.add_log("emergency", f"Pilots Guild answered your distress call in {system.name}. They delivered 20 fuel for 100 credits.")
        return {
            "result": f"Pilots Guild rescue! 20 fuel delivered for 100 credits. Arrived in {turns} turns.",
            "outcome": "pilots_guild",
            "effects": {"fuel": 20, "credits": -100},
        }
    elif rescue_roll < 0.7:
        passerby_roll = rng.random()
        if passerby_roll < 0.5:
            fuel_given = rng.randint(10, 25)
            ship.fuel = min(ship.max_fuel, ship.fuel + fuel_given)
            state.add_log("emergency", f"A friendly passerby answered your distress call and shared {fuel_given} fuel.")
            return {
                "result": f"Friendly passerby shared {fuel_given} fuel! Arrived in {turns} turns.",
                "outcome": "passerby_help",
                "effects": {"fuel": fuel_given},
            }
        elif passerby_roll < 0.8:
            credits_stolen = min(ship.credits, rng.randint(20, 80))
            ship.credits = max(0, ship.credits - credits_stolen)
            state.add_log("emergency", f"Pirates responded to your distress call and stole {credits_stolen} credits!")
            return {
                "result": f"Pirates answered your call and stole {credits_stolen} credits!",
                "outcome": "piracy",
                "effects": {"credits": -credits_stolen},
            }
        else:
            state.add_log("emergency", f"A ship passed nearby but did not respond to your distress call.")
            return {
                "result": "A ship passed nearby but did not respond.",
                "outcome": "passerby_ignore",
                "effects": {},
            }
    else:
        signal_roll = rng.random()
        if signal_roll < 0.5:
            fuel_given = rng.randint(5, 15)
            ship.fuel = min(ship.max_fuel, ship.fuel + fuel_given)
            state.add_log("emergency", f"An emergency signal brought a friendly responder who delivered {fuel_given} fuel.")
            return {
                "result": f"Friendly emergency responder delivered {fuel_given} fuel! Arrived in {turns} turns.",
                "outcome": "signal_friendly",
                "effects": {"fuel": fuel_given},
            }
        else:
            hull_damage = rng.randint(5, 15)
            ship.hull = max(0, ship.hull - hull_damage)
            state.add_log("emergency", f"A hostile ship intercepted your emergency signal and attacked, causing {hull_damage} hull damage.")
            return {
                "result": f"Hostile ship intercepted your signal! Took {hull_damage} hull damage.",
                "outcome": "signal_hostile",
                "effects": {"hull": -hull_damage},
            }


def perform_salvage(state: GameState) -> dict:
    """Salvage the surrounding area for resources when stranded.

    Only available when fuel is 0 and the ship is landed on a body.
    Each body can be salvaged up to 3 times. Morale cost increases
    with each attempt.

    :param state: The current game state.
    :type state: GameState
    :returns: A dictionary with ``error`` on failure, or ``result``,
        ``find``, and ``effects`` on success.
    :rtype: dict
    """
    ship = state.ship

    if ship.fuel > 0:
        return {"error": "Salvage is only possible when stranded with no fuel."}

    if not ship.current_body_id:
        return {"error": "Must be landed on a body to salvage."}

    body_id = ship.current_body_id
    current_attempts = ship.salvage_attempts.get(body_id, 0)

    if current_attempts >= 3:
        return {"error": "This area has been fully salvaged (max 3 attempts)."}

    morale_cost = 1 + 2 * current_attempts
    ship.morale = max(0, ship.morale - morale_cost)
    ship.salvage_attempts[body_id] = current_attempts + 1

    system = state.get_current_system()
    body = None
    if system:
        for b in system.bodies:
            if b.id == body_id:
                body = b
                break

    rng = seeded_random(state.seed, "salvage", body_id, str(current_attempts))
    roll = rng.random()

    if roll < 0.4:
        fuel_found = rng.randint(2, 8)
        ship.fuel = min(ship.max_fuel, ship.fuel + fuel_found)
        state.add_log("emergency", f"Salvaged a fuel cache on {body.name if body else body_id}: +{fuel_found} fuel.")
        return {
            "result": f"Found a fuel cache! +{fuel_found} fuel.",
            "find": "fuel_cache",
            "effects": {"fuel": fuel_found},
        }
    elif roll < 0.7:
        repair_amount = rng.randint(5, 15)
        ship.hull = min(ship.max_hull, ship.hull + repair_amount)
        state.add_log("emergency", f"Salvaged repair materials on {body.name if body else body_id}: +{repair_amount} hull repaired.")
        return {
            "result": f"Found repair materials! +{repair_amount} hull.",
            "find": "repair_materials",
            "effects": {"hull": repair_amount},
        }
    elif roll < 0.9:
        spare_value = rng.randint(10, 50)
        d_id = f"{rng.getrandbits(48):012x}"
        disc = Discovery(
            id=d_id, category="artifact", name="Salvaged Spare Parts",
            description="Recovered spare parts from a wreckage in the area.",
            value=spare_value, system_id=system.id if system else "",
            body_id=body_id,
        )
        state.discoveries.append(disc)
        state.add_log("emergency", f"Salvaged spare parts on {body.name if body else body_id} (value: {spare_value} credits).")
        return {
            "result": f"Found salvageable spare parts! Value: {spare_value} credits.",
            "find": "spare_parts",
            "effects": {"cargo": 1},
        }
    else:
        state.add_log("emergency", f"Salvage attempt on {body.name if body else body_id} turned up nothing useful.")
        return {
            "result": "Nothing useful found.",
            "find": "nothing",
            "effects": {},
        }


def emergency_craft(state: GameState, discovery_id: str, output: str) -> dict:
    """Convert a discovery into emergency resources via crafting.

    Each discovery category can be converted to a specific resource type
    at a set conversion rate.

    :param state: The current game state.
    :type state: GameState
    :param discovery_id: The unique ID of the discovery to convert.
    :type discovery_id: str
    :param output: The desired output type (fuel, repair, morale, credits).
    :type output: str
    :returns: A dictionary with ``error`` on failure, or ``result``,
        ``crafted``, and ``effects`` on success.
    :rtype: dict
    """
    matching_disc = None
    for disc in state.discoveries:
        if disc.id == discovery_id:
            matching_disc = disc
            break

    if not matching_disc:
        return {"error": f"Discovery {discovery_id} not found."}

    category = matching_disc.category

    if category not in CRAFT_CONVERSIONS:
        return {"error": f"Discovery type '{category}' cannot be crafted."}

    expected_output, rate = CRAFT_CONVERSIONS[category]

    if output != expected_output:
        return {"error": f"Discovery type '{category}' can only be crafted into '{expected_output}', not '{output}'."}

    state.discoveries.remove(matching_disc)

    ship = state.ship
    if output == "fuel":
        ship.fuel = min(ship.max_fuel, ship.fuel + rate)
        state.add_log("emergency", f"Emergency crafted {matching_disc.name} into +{rate} fuel.")
        return {
            "result": f"Crafted {matching_disc.name} into +{rate} fuel.",
            "crafted": "fuel",
            "effects": {"fuel": rate},
        }
    elif output == "repair":
        ship.hull = min(ship.max_hull, ship.hull + rate)
        state.add_log("emergency", f"Emergency crafted {matching_disc.name} into +{rate} hull repair.")
        return {
            "result": f"Crafted {matching_disc.name} into +{rate} hull repair.",
            "crafted": "repair",
            "effects": {"hull": rate},
        }
    elif output == "morale":
        ship.morale = min(100, ship.morale + rate)
        state.add_log("emergency", f"Emergency crafted {matching_disc.name} into +{rate} morale.")
        return {
            "result": f"Crafted {matching_disc.name} into +{rate} morale boost.",
            "crafted": "morale",
            "effects": {"morale": rate},
        }
    elif output == "credits":
        ship.credits += rate
        state.add_log("emergency", f"Emergency crafted {matching_disc.name} and sold for +{rate} credits.")
        return {
            "result": f"Crafted {matching_disc.name} and sold for +{rate} credits.",
            "crafted": "credits",
            "effects": {"credits": rate},
        }

    return {"error": f"Unknown output type: {output}"}
