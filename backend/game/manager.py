"""
Game state management module.

Provides functions for creating new games, loading and saving game
state, serializing/deserializing state to/from dictionaries, and
querying galaxy and system data.
"""

import uuid

from backend.database import load_game, save_game as db_save, load_save
from backend.config import (
    DEFAULT_SEED, DEFAULT_SHIP_NAME, INITIAL_FUEL, INITIAL_HULL,
    INITIAL_CARGO, INITIAL_CREW, INITIAL_MORALE, INITIAL_CREDITS,
    INITIAL_JUMP_RANGE, INITIAL_SCANNER,
)
from backend.models.game_state import GameState
from backend.models.ship import Ship
from backend.models.faction import FactionRelation, FACTION_DEFINITIONS
from backend.generation.universe import generate_universe
from backend.game.engine import (
    get_nearby_systems,
)


def new_game(seed: int | None = None, ship_name: str | None = None) -> GameState:
    """Create a new game session with a procedurally generated universe.

    Generates a UUID for the game, creates the galaxy using the given
    (or default) seed, initializes the ship with default stats, and
    places the player in the first generated star system.

    :param seed: The universe generation seed. Uses ``DEFAULT_SEED`` (42)
        if ``None``.
    :type seed: int | None
    :param ship_name: The name of the player's ship. Uses
        ``DEFAULT_SHIP_NAME`` ("Serendipity") if ``None``.
    :type ship_name: str | None
    :returns: A fully initialized :class:`GameState`.
    :rtype: GameState
    """
    s = seed if seed is not None else DEFAULT_SEED
    name = ship_name if ship_name else DEFAULT_SHIP_NAME
    game_id = str(uuid.uuid4())

    systems, lore_fragments = generate_universe(s)
    first_sys_id = list(systems.keys())[0]

    ship = Ship(
        name=name, fuel=INITIAL_FUEL, hull=INITIAL_HULL,
        cargo=INITIAL_CARGO, crew=INITIAL_CREW, morale=INITIAL_MORALE,
        credits=INITIAL_CREDITS, jump_range=INITIAL_JUMP_RANGE, scanner=INITIAL_SCANNER,
        current_system_id=first_sys_id,
    )

    faction_relations = {
        fid: FactionRelation(faction_id=fid, reputation=0, known=False)
        for fid in FACTION_DEFINITIONS
    }

    state = GameState(
        id=game_id, seed=s, ship=ship, systems=systems,
        lore_fragments=lore_fragments, faction_relations=faction_relations,
    )
    first_sys = state.get_current_system()
    if first_sys:
        first_sys.visited = True
    state.systems_visited = 1
    state.add_log("system", f"New game started. Universe seed: {s}. Ship: {name}.")
    state.add_log("navigation", f"Began journey in the {first_sys.name if first_sys else 'Unknown'} system.")
    return state


def load_or_create(game_id: str, seed: int | None = None, ship_name: str | None = None) -> GameState:
    """Load an existing game or create a new one if not found.

    Attempts to load a persisted game by its ID. If no saved data
    exists, creates a new game with the given parameters and assigns
    the requested game_id.

    :param game_id: The unique identifier for the game.
    :type game_id: str
    :param seed: The universe generation seed for a new game.
    :type seed: int | None
    :param ship_name: The ship name for a new game.
    :type ship_name: str | None
    :returns: The loaded or newly created :class:`GameState`.
    :rtype: GameState
    """
    data = load_game(game_id)
    if data:
        return _state_from_dict(data)
    state = new_game(seed, ship_name)
    state.id = game_id
    return state


def get_game_state(state: GameState) -> dict:
    """Serialize the game state to a dictionary.

    :param state: The current game state.
    :type state: GameState
    :returns: A dictionary representation of the game state.
    :rtype: dict
    """
    return _state_to_dict(state)


def get_galaxy(state: GameState) -> dict:
    """Build a galaxy map overview from the current game state.

    Returns summary data for every system including coordinates,
    star type, phenomenon, visit/scan status, and body count.

    :param state: The current game state.
    :type state: GameState
    :returns: A dictionary with ``current_system_id``, ``systems``
        (list of system summaries), and ``systems_visited`` count.
    :rtype: dict
    """
    systems_data = []
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
    """Retrieve detailed information about a specific star system.

    Includes the full system data, whether it is the current system,
    and nearby systems if it is current.

    :param state: The current game state.
    :type state: GameState
    :param sys_id: The unique identifier of the star system.
    :type sys_id: str
    :returns: A dictionary with ``system``, ``is_current``, and
        ``nearby_systems`` keys, or ``None`` if the system is not
        found.
    :rtype: dict | None
    """
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
    """Persist the current game state to the database.

    Writes the game state to both the ``games`` and ``saves`` tables.

    :param state: The current game state.
    :type state: GameState
    """
    data = _state_to_dict(state)
    db_save(state.id, data)


def game_load(game_id: str) -> GameState | None:
    """Load a game state from the database by game ID.

    Attempts to load the most recent save first, then falls back to
    the main game record.

    :param game_id: The unique identifier for the game.
    :type game_id: str
    :returns: The deserialized :class:`GameState`, or ``None`` if
        no data is found.
    :rtype: GameState | None
    """
    data = load_save(game_id)
    if not data:
        data = load_game(game_id)
    if not data:
        return None
    return _state_from_dict(data)


def _state_to_dict(state: GameState) -> dict:
    """Serialize a :class:`GameState` to a plain dictionary.

    Converts all nested objects (ship, systems, events, discoveries,
    lore fragments) to their dictionary representations for database
    storage and JSON serialisation.

    :param state: The game state to serialize.
    :type state: GameState
    :returns: A dictionary representation of the game state.
    :rtype: dict
    """
    return {
        "id": state.id,
        "seed": state.seed,
        "ship": state.ship.to_dict(),
        "systems": {k: v.to_dict() for k, v in state.systems.items()},
        "events": [e.to_dict() for e in state.events],
        "discoveries": [d.to_dict() for d in state.discoveries],
        "lore_fragments": [lf.to_dict() for lf in state.lore_fragments],
        "log_entries": state.log_entries,
        "faction_relations": {
            k: {"faction_id": v.faction_id, "reputation": v.reputation, "known": v.known}
            for k, v in state.faction_relations.items()
        },
        "systems_visited": state.systems_visited,
        "game_started": state.game_started,
        "last_event_title": state.last_event_title,
        "jumps_since_rep_decay": state.jumps_since_rep_decay,
        "station_visits": state.station_visits,
        "event_cooldowns": state.event_cooldowns,
        "crisis_cooldown": state.crisis_cooldown,
        "completed_missions": state.completed_missions,
        "daily_missions_used": state.daily_missions_used,
        "accepted_missions": list(state.accepted_missions),
    }


def _state_from_dict(d: dict) -> GameState:
    """Deserialize a dictionary back into a :class:`GameState`.

    Reconstructs a full :class:`GameState` object from a dictionary,
    including all nested objects such as :class:`StarSystem`,
    :class:`Event`, :class:`Discovery`, and :class:`LoreFragment`.

    :param d: The dictionary representation of a game state.
    :type d: dict
    :returns: A fully reconstructed :class:`GameState`.
    :rtype: GameState
    """
    from backend.models.system import StarSystem
    from backend.models.event import Event
    from backend.models.discovery import Discovery, LoreFragment

    systems = {}
    for k, v in d.get("systems", {}).items():
        systems[k] = StarSystem.from_dict(v)

    events = [Event.from_dict(e) for e in d.get("events", [])]
    discoveries = [Discovery.from_dict(disc) for disc in d.get("discoveries", [])]
    lore = [LoreFragment.from_dict(lf) for lf in d.get("lore_fragments", [])]
    _fixup_old_lore_fragment_numbers(lore)

    faction_relations = {}
    for fid, fr_data in d.get("faction_relations", {}).items():
        faction_relations[fid] = FactionRelation(
            faction_id=fr_data["faction_id"],
            reputation=fr_data.get("reputation", 0),
            known=fr_data.get("known", False),
        )

    return GameState(
        id=d["id"],
        seed=d["seed"],
        ship=Ship.from_dict(d["ship"]),
        systems=systems,
        events=events,
        discoveries=discoveries,
        lore_fragments=lore,
        log_entries=d.get("log_entries", []),
        faction_relations=faction_relations,
        systems_visited=d.get("systems_visited", 0),
        game_started=d.get("game_started", ""),
        last_event_title=d.get("last_event_title"),
        jumps_since_rep_decay=d.get("jumps_since_rep_decay", 0),
        station_visits=d.get("station_visits", {}),
        event_cooldowns=d.get("event_cooldowns", {}),
        crisis_cooldown=d.get("crisis_cooldown", 0),
        completed_missions=d.get("completed_missions", []),
        daily_missions_used=d.get("daily_missions_used", {}),
        accepted_missions=set(d.get("accepted_missions", [])),
    )


def _fixup_old_lore_fragment_numbers(lore_fragments: list) -> None:
    """Fix up lore fragments that have ``fragment_number == -1`` by extracting
    the number from the fragment ID.  Fragment IDs follow the pattern
    ``lore_<arc>_<number>``, so the number is the last ``_``-delimited part.

    Old saves serialized before the ``fragment_number`` field was added will
    load with ``fragment_number=-1``.  This migration corrects those in place.

    :param lore_fragments: The list of :class:`LoreFragment` instances to fix.
    :type lore_fragments: list
    """
    for frag in lore_fragments:
        if frag.fragment_number == -1:
            try:
                frag.fragment_number = int(frag.id.rsplit("_", 1)[-1])
            except (ValueError, IndexError):
                pass


GAME_STORE: dict[str, GameState] = {}
