"""
API route definitions for Starfarer: Echoes of the Void.

Defines all 19 REST API endpoints for game creation, state retrieval,
navigation, exploration, events, trading, upgrades, saving/loading,
and the leaderboard.
"""

import time

from fastapi import APIRouter, HTTPException

from backend.models.game_state import GameState
from backend.api.schemas import (
    BulkSellRequest, NewGameRequest, ResolveEventRequest, TradeRequest,
    UpgradeRequest, HealthResponse,
)
from backend.game.manager import (
    GAME_STORE, new_game, get_galaxy, get_system_detail, game_save, game_load as game_load_func,
)
from backend.generation.events import trigger_event, resolve_event as resolve_event_func
from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade, perform_trade, perform_bulk_sell
from backend.database import get_leaderboard
from backend.generation.lore_content import ARC_DISPLAY_NAMES

START_TIME = time.time()

router = APIRouter(prefix="/api")


def _get_state(game_id: str) -> GameState | None:
    """Retrieve a game state from memory or the database.

    Looks up the game ID in the in-memory ``GAME_STORE`` first.
    If not found, attempts to load it from the database and caches
    the result.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: The :class:`GameState` if found, or ``None``.
    :rtype: GameState | None
    """
    if game_id in GAME_STORE:
        return GAME_STORE[game_id]
    
    state = game_load_func(game_id)
    if state:
        GAME_STORE[game_id] = state
        return state
    
    return None


def _save_state(game_id: str) -> None:
    """Persist an in-memory game state to the database.

    Writes the game state from ``GAME_STORE`` to SQLite if the
    game is currently loaded in memory.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    """
    if game_id in GAME_STORE:
        game_save(GAME_STORE[game_id])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check endpoint.

    Returns the server status, version, and uptime since startup.

    :returns: A :class:`HealthResponse` with status ``"ok"``, the
        game version, and uptime string.
    :rtype: HealthResponse
    """
    uptime = round(time.time() - START_TIME, 1)
    return HealthResponse(status="ok", version="0.1.0", uptime=f"{uptime}s")


@router.post("/game/new")
def api_new_game(req: NewGameRequest) -> dict:
    """Create a new game session.

    Generates a procedurally created universe, initializes the ship,
    and persists the game state to the database.

    :param req: The new game request with optional seed, ship_name,
        and game_id.
    :type req: NewGameRequest
    :returns: A dictionary with ``game_id`` and a ``state`` summary.
    :rtype: dict
    """
    state = new_game(seed=req.seed, ship_name=req.ship_name)
    if req.game_id:
        state.id = req.game_id
    GAME_STORE[state.id] = state
    game_save(state)
    return {
        "game_id": state.id,
        "state": state.state_summary(),
    }


@router.get("/game/{game_id}")
def api_get_game(game_id: str) -> dict:
    """Retrieve the full game state for a given game ID.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with game_id, seed, ship, current system,
        discoveries, pending events, log entries, and stats.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return _full_state_response(state)


@router.get("/game/{game_id}/galaxy")
def api_galaxy(game_id: str) -> dict:
    """Retrieve galaxy map data for a game.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``current_system_id``, ``systems``
        (list of system summaries), and ``systems_visited`` count.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return get_galaxy(state)


@router.get("/game/{game_id}/system/{sys_id}")
def api_system_detail(game_id: str, sys_id: str) -> dict:
    """Retrieve detailed information for a specific star system.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param sys_id: The unique identifier of the star system.
    :type sys_id: str
    :returns: A dictionary with ``system``, ``is_current``, and
        ``nearby_systems``.
    :rtype: dict
    :raises HTTPException: 404 if the game or system is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    detail = get_system_detail(state, sys_id)
    if not detail:
        raise HTTPException(status_code=404, detail="System not found")
    return detail


@router.post("/game/{game_id}/jump/{sys_id}")
def api_jump(game_id: str, sys_id: str) -> dict:
    """Execute a hyperspace jump to the target star system.

    Validates jump feasibility, performs the jump, saves the game,
    and possibly triggers a procedural event.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param sys_id: The unique identifier of the target star system.
    :type sys_id: str
    :returns: A dictionary with ``result`` message, ``current_system``,
        ``ship`` status, and ``pending_event`` if triggered.
    :rtype: dict
    :raises HTTPException: 404 if the game or target system is not
        found; 400 if the jump is not possible.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")

    if sys_id not in state.systems:
        raise HTTPException(status_code=404, detail="Target system not found")

    target = state.systems[sys_id]
    current = state.get_current_system()
    if not current:
        raise HTTPException(status_code=400, detail="No current system")

    ok, fuel_cost, msg = can_jump(state.ship, target, current)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Cannot jump to {target.name}: {msg}")

    result = perform_jump(state, target, int(fuel_cost))

    event = trigger_event(state)
    if event:
        state.events.append(event)
    game_save(state)

    current_system = state.get_current_system()
    return {
        "result": result,
        "current_system": current_system.to_dict() if current_system else None,
        "ship": state.ship.to_dict(),
        "pending_event": event.to_dict() if event and not event.resolved else None,
    }


@router.post("/game/{game_id}/scan")
def api_scan(game_id: str) -> dict:
    """Scan the current star system for orbital bodies.

    Deducts fuel and reveals the bodies in the current system. May
    trigger a procedural event.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``result``, ``system``, ``ship``
        status, and ``pending_event`` if triggered.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    result = perform_scan(state)

    event = trigger_event(state)
    if event:
        state.events.append(event)  # pragma: no cover  # probabilistic event trigger
    game_save(state)

    current = state.get_current_system()
    return {
        "result": result,
        "system": current.to_dict() if current else None,
        "ship": state.ship.to_dict(),
        "pending_event": event.to_dict() if event and not event.resolved else None,
    }


@router.post("/game/{game_id}/land/{body_id}")
def api_land(game_id: str, body_id: str) -> dict:
    """Land the ship on a specific celestial body.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param body_id: The unique identifier of the body to land on.
    :type body_id: str
    :returns: A dictionary with ``result`` message, ``ship`` status,
        and ``current_body_id``.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if
        landing is not possible.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    ok, msg = land_on_body(state, body_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    game_save(state)
    return {
        "result": msg,
        "ship": state.ship.to_dict(),
        "current_body_id": state.ship.current_body_id,
    }


@router.post("/game/{game_id}/explore")
def api_explore(game_id: str) -> dict:
    """Explore the surface of the currently landed-on body.

    Deducts fuel and generates discoveries based on the body's points
    of interest. May trigger a procedural event.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``result`` message, ``discoveries``
        list, ``ship`` status, and ``pending_event`` if triggered.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    discoveries = explore_surface(state)

    event = trigger_event(state)
    if event:
        state.events.append(event)
    game_save(state)

    return {
        "result": f"Explored. Found {len(discoveries)} points of interest.",
        "discoveries": [d.to_dict() for d in discoveries],
        "ship": state.ship.to_dict(),
        "pending_event": event.to_dict() if event and not event.resolved else None,
    }


@router.post("/game/{game_id}/event/{event_id}/resolve")
def api_resolve_event(game_id: str, event_id: str, req: ResolveEventRequest) -> dict:
    """Resolve a pending in-game event by choosing an outcome.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param event_id: The unique identifier of the event to resolve.
    :type event_id: str
    :param req: The resolve request containing the choice index.
    :type req: ResolveEventRequest
    :returns: A dictionary with ``result`` message, ``event`` details,
        and ``ship`` status.
    :rtype: dict
    :raises HTTPException: 404 if the game or event is not found;
        400 if the event is already resolved or the choice index is
        invalid.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    ok, msg, extra = resolve_event_func(state, event_id, req.choice_index)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    game_save(state)
    return {
        "result": msg,
        "event": extra,
        "ship": state.ship.to_dict(),
    }


@router.get("/game/{game_id}/log")
def api_log(game_id: str) -> dict:
    """Retrieve the ship's log entries in reverse chronological order.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``count`` and ``entries`` (list of
        log entry dicts).
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    entries = list(reversed(state.log_entries))
    return {
        "count": len(entries),
        "entries": entries,
    }


@router.get("/game/{game_id}/discoveries")
def api_discoveries(game_id: str) -> dict:
    """Retrieve all discoveries made during the game.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``count`` and ``discoveries`` (list of
        discovery dicts).
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "count": len(state.discoveries),
        "discoveries": [d.to_dict() for d in state.discoveries],
    }


@router.get("/game/{game_id}/lore")
def api_lore(game_id: str) -> dict:
    """Retrieve all lore fragments grouped by story arc.

    Returns lore fragments organized by arc with discovered/undiscovered
    status. Also includes overall collection progress.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``arcs`` (dict of arc ID to arc data)
        and ``progress`` (collected/total counts).
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")

    arcs: dict[str, dict] = {}
    for arc_id, display_name in ARC_DISPLAY_NAMES.items():
        arcs[arc_id] = {
            "arc_id": arc_id,
            "display_name": display_name,
            "fragments": [],
            "collected": 0,
            "total": 0,
        }

    for lore in state.lore_fragments:
        arc = lore.arc
        if arc in arcs:
            arcs[arc]["fragments"].append(lore.to_dict())
            arcs[arc]["total"] += 1
            if lore.discovered:
                arcs[arc]["collected"] += 1

    lore_collected = sum(1 for lf in state.lore_fragments if lf.discovered)
    lore_total = len(state.lore_fragments)

    return {
        "arcs": arcs,
        "arc_order": list(ARC_DISPLAY_NAMES.keys()),
        "progress": {
            "collected": lore_collected,
            "total": lore_total,
        },
    }


@router.post("/game/{game_id}/trade")
def api_trade(game_id: str, req: TradeRequest) -> dict:
    """Perform a buy or sell trade action.

    Supports buying fuel, repairing hull, or selling discoveries
    at trading stations in accessible systems.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param req: The trade request with action (buy/sell), item, and
        quantity.
    :type req: TradeRequest
    :returns: A dictionary with ``result`` message and ``ship`` status.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        trade is not possible.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    ok, msg = perform_trade(state, req.action, req.item, req.quantity)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    game_save(state)
    return {
        "result": msg,
        "ship": state.ship.to_dict(),
    }


@router.post("/game/{game_id}/trade/bulk-sell")
def api_bulk_sell(game_id: str, req: BulkSellRequest) -> dict:
    """Sell multiple discoveries at once in a single transaction.

    Accepts a list of items with quantities. Items that don't exist
    in the ship's discoveries are reported as errors, but available
    items are still sold (partial failure mode).

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param req: The bulk sell request with a list of items.
    :type req: BulkSellRequest
    :returns: A dictionary with the full game state (same format as
        ``GET /api/game/{game_id}``).
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        sell is not possible.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")

    if not req.items:
        raise HTTPException(status_code=400, detail="Items list must not be empty.")

    items_dicts = [{"item": i.item, "quantity": i.quantity} for i in req.items]
    ok, msg, sold_count, total_price = perform_bulk_sell(state, items_dicts)

    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    game_save(state)
    response = _full_state_response(state)
    response["sold_count"] = sold_count
    response["total_price"] = total_price
    return response


@router.post("/game/{game_id}/upgrade")
def api_upgrade(game_id: str, req: UpgradeRequest) -> dict:
    """Purchase a ship upgrade.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param req: The upgrade request containing the upgrade_id to
        purchase.
    :type req: UpgradeRequest
    :returns: A dictionary with ``result`` message and ``ship`` status.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        upgrade is not possible.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    ok, msg = purchase_upgrade(state, req.upgrade_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    game_save(state)
    return {
        "result": msg,
        "ship": state.ship.to_dict(),
    }


@router.get("/game/{game_id}/upgrades")
def api_upgrades_info(game_id: str) -> dict:
    """Get information about all available ship upgrades.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``upgrades`` (list of upgrade info
        dicts) and ``credits``.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "upgrades": get_upgrade_info(state.ship),
        "credits": state.ship.credits,
    }


@router.get("/game/{game_id}/nearby")
def api_nearby(game_id: str) -> dict:
    """Get a list of nearby star systems within jump range.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``nearby``, ``current_system_id``,
        ``jump_range``, and ``fuel``.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "nearby": get_nearby_systems(state),
        "current_system_id": state.ship.current_system_id,
        "jump_range": state.ship.jump_range,
        "fuel": state.ship.fuel,
    }


@router.post("/game/{game_id}/save")
def api_save(game_id: str) -> dict:
    """Save the current game state to the database.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``result`` message and ``game_id``.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    game_save(state)
    return {"result": "Game saved.", "game_id": game_id}


@router.post("/game/{game_id}/load")
def api_load(game_id: str) -> dict:
    """Load the most recently saved state for a game.

    Retrieves the saved state from the database and restores it
    into the in-memory game store.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``result`` message and ``state``
        summary.
    :rtype: dict
    :raises HTTPException: 404 if no save is found for the game.
    """
    state = game_load_func(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Save not found for this game")
    GAME_STORE[game_id] = state
    return {
        "result": "Game loaded.",
        "state": state.state_summary(),
    }


@router.get("/leaderboard")
def api_leaderboard() -> dict:
    """Retrieve the top 10 players from the leaderboard.

    :returns: A dictionary with ``leaderboard`` (list of leaderboard
        entry dicts).
    :rtype: dict
    """
    return {
        "leaderboard": get_leaderboard(limit=10),
    }


def _full_state_response(state: GameState) -> dict:
    """Build the full game state response dictionary.

    Serializes all relevant game state fields into a dictionary
    suitable for the ``GET /game/{game_id}`` endpoint, including
    ship data, current system, discoveries, pending events, the
    most recent log entries, and visit statistics.

    :param state: The current game state.
    :type state: GameState
    :returns: A dictionary with all game state fields.
    :rtype: dict
    """
    current_system = state.get_current_system()
    return {
        "game_id": state.id,
        "seed": state.seed,
        "ship": state.ship.to_dict(),
        "current_system": current_system.to_dict() if current_system else None,
        "discoveries": [d.to_dict() for d in state.discoveries],
        "events_pending": [e.to_dict() for e in state.events if not e.resolved],
        "log_entries": list(reversed(state.log_entries))[:20],
        "systems_visited": state.systems_visited,
        "systems_total": len(state.systems),
        "game_started": state.game_started,
        "lore_fragments_collected": state.lore_fragments_collected,
        "lore_fragments_total": len(state.lore_fragments),
    }
