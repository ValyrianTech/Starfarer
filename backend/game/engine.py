import random
import uuid

from backend.config import (
    JUMP_FUEL_COST_PER_LY, SCAN_FUEL_COST, EXPLORE_FUEL_COST,
    MORALE_DECAY_PER_JUMP,
)
from backend.models.game_state import GameState
from backend.models.ship import Ship
from backend.models.system import StarSystem, Body
from backend.models.discovery import Discovery
from backend.generation.universe import distance_between


def can_jump(ship: Ship, target: StarSystem, current: StarSystem) -> tuple[bool, float, str]:
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


def perform_jump(state: GameState, target_system: StarSystem, fuel_cost: int) -> str:
    current = state.get_current_system() or state.systems.get(state.ship.current_system_id)
    state.ship.fuel -= fuel_cost

    decay = 1
    if state.ship.upgrades.get("life_support", 0) > 0:
        decay = max(0, 1 - state.ship.upgrades["life_support"])

    state.ship.morale = max(0, state.ship.morale - (MORALE_DECAY_PER_JUMP * decay))
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
    ship = state.ship
    current = state.get_current_system()
    if not current:
        return []
    nearby = []
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

    ship.fuel -= EXPLORE_FUEL_COST

    discoveries = []
    item_rng = random.Random(state.seed + len(state.discoveries) + hash(body.id))

    num_finds = min(body.poi_count, item_rng.randint(1, 3))
    for i in range(num_finds):
        cat = item_rng.choice(["mineral", "artifact", "lifeform", "signal", "ruin"])
        disc = _generate_discovery(item_rng, cat, body, system, state)
        discoveries.append(disc)
        state.discoveries.append(disc)

    state.add_log("exploration", f"Explored {body.name}. Found {len(discoveries)} points of interest.")
    return discoveries


def _generate_discovery(rng: random.Random, category: str, body: Body, system: StarSystem, state: GameState) -> Discovery:
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
