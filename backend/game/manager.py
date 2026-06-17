import uuid
import json

from backend.database import create_game, load_game, update_game, save_game as db_save, load_save, get_leaderboard
from backend.config import (
    DEFAULT_SEED, DEFAULT_SHIP_NAME, INITIAL_FUEL, INITIAL_HULL,
    INITIAL_CARGO, INITIAL_CREW, INITIAL_MORALE, INITIAL_CREDITS,
    INITIAL_JUMP_RANGE, INITIAL_SCANNER,
)
from backend.models.game_state import GameState
from backend.models.ship import Ship
from backend.generation.universe import generate_universe
from backend.generation.events import trigger_event, resolve_event as resolve_event_internal
from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade, perform_trade


def new_game(seed: int | None = None, ship_name: str | None = None) -> GameState:
    s = seed if seed is not None else DEFAULT_SEED
    name = ship_name if ship_name else DEFAULT_SHIP_NAME
    game_id = str(uuid.uuid4())

    systems = generate_universe(s)
    first_sys_id = list(systems.keys())[0]

    ship = Ship(
        name=name, fuel=INITIAL_FUEL, hull=INITIAL_HULL,
        cargo=INITIAL_CARGO, crew=INITIAL_CREW, morale=INITIAL_MORALE,
        credits=INITIAL_CREDITS, jump_range=INITIAL_JUMP_RANGE, scanner=INITIAL_SCANNER,
        current_system_id=first_sys_id,
    )

    state = GameState(id=game_id, seed=s, ship=ship, systems=systems)
    first_sys = state.get_current_system()
    if first_sys:
        first_sys.visited = True
    state.systems_visited = 1
    state.add_log("system", f"New game started. Universe seed: {s}. Ship: {name}.")
    state.add_log("navigation", f"Began journey in the {first_sys.name} system.")
    return state


def load_or_create(game_id: str, seed: int | None = None, ship_name: str | None = None) -> GameState:
    data = load_game(game_id)
    if data:
        return _state_from_dict(data)
    state = new_game(seed, ship_name)
    state.id = game_id
    return state


def get_game_state(state: GameState) -> dict:
    return _state_to_dict(state)


def get_galaxy(state: GameState) -> dict:
    systems_data = []
    current = state.get_current_system()
    for sys_id, sys_data in state.systems.items():
        systems_data.append({
            "id": sys_data.id,
            "name": sys_data.name,
            "x": sys_data.x,
            "y": sys_data.y,
            "star_type": sys_data.star_type,
            "star_color": sys_data.star_color,
            "phenomenon": sys_data.phenomenon,
            "visited": sys_data.visited,
            "scanned": sys_data.scanned,
            "body_count": len(sys_data.bodies),
            "is_current": sys_id == state.ship.current_system_id,
        })
    return {
        "current_system_id": state.ship.current_system_id,
        "systems": systems_data,
        "systems_visited": state.systems_visited,
    }


def get_system_detail(state: GameState, sys_id: str) -> dict | None:
    system = state.systems.get(sys_id)
    if not system:
        return None
    is_current = sys_id == state.ship.current_system_id
    nearby = get_nearby_systems(state) if is_current else []
    return {
        "system": system.to_dict(),
        "is_current": is_current,
        "nearby_systems": nearby,
    }


def game_save(state: GameState) -> None:
    data = _state_to_dict(state)
    create_game(state.id, state.seed, state.ship.name, data)
    db_save(state.id, data)


def game_load(game_id: str) -> GameState | None:
    data = load_save(game_id)
    if not data:
        data = load_game(game_id)
    if not data:
        return None
    return _state_from_dict(data)


def _state_to_dict(state: GameState) -> dict:
    return {
        "id": state.id,
        "seed": state.seed,
        "ship": state.ship.to_dict(),
        "systems": {k: v.to_dict() for k, v in state.systems.items()},
        "events": [e.to_dict() for e in state.events],
        "discoveries": [d.to_dict() for d in state.discoveries],
        "lore_fragments": [l.to_dict() for l in state.lore_fragments],
        "log_entries": state.log_entries,
        "systems_visited": state.systems_visited,
        "game_started": state.game_started,
    }


def _state_from_dict(d: dict) -> GameState:
    from backend.models.system import StarSystem, Body
    from backend.models.event import Event, Choice
    from backend.models.discovery import Discovery, LoreFragment

    systems = {}
    for k, v in d.get("systems", {}).items():
        systems[k] = StarSystem.from_dict(v)

    events = [Event.from_dict(e) for e in d.get("events", [])]
    discoveries = [Discovery.from_dict(disc) for disc in d.get("discoveries", [])]
    lore = [LoreFragment.from_dict(l) for l in d.get("lore_fragments", [])]

    return GameState(
        id=d["id"],
        seed=d["seed"],
        ship=Ship.from_dict(d["ship"]),
        systems=systems,
        events=events,
        discoveries=discoveries,
        lore_fragments=lore,
        log_entries=d.get("log_entries", []),
        systems_visited=d.get("systems_visited", 0),
        game_started=d.get("game_started", ""),
    )


GAME_STORE: dict[str, GameState] = {}
