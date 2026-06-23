"""
API route definitions for Starfarer: Echoes of the Void.

Defines all 19 REST API endpoints for game creation, state retrieval,
navigation, exploration, events, trading, upgrades, saving/loading,
and the leaderboard.
"""

import logging
import time

from fastapi import APIRouter, HTTPException

from backend.models.game_state import GameState
from backend.api.schemas import (
    AcceptMissionRequest, BulkSellRequest, CompleteMissionRequest, CraftRequest,
    NewGameRequest, ResolveEventRequest, TradeRequest, UpgradeRequest, HealthResponse,
)
from backend.game.manager import (
    GAME_STORE, new_game, get_galaxy, get_system_detail, game_save, game_load as game_load_func,
)
from backend.generation.events import trigger_event, resolve_event as resolve_event_func, decrement_cooldowns
from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
    activate_distress_beacon, perform_salvage, emergency_craft,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade, perform_trade, perform_bulk_sell
from backend.database import get_leaderboard
from backend.generation.lore_content import ARC_DISPLAY_NAMES
from backend.models.faction import get_faction, FACTION_DEFINITIONS
from backend.missions import (
    generate_missions, complete_mission,
)

logger = logging.getLogger(__name__)

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
        discoveries, cargo_capacity, pending events, log entries,
        and stats.
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

    decrement_cooldowns(state)
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

    decrement_cooldowns(state)
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
        list, ``ship`` status, ``lore_fragments_discovered``, and
        ``pending_event`` if triggered.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    discoveries = explore_surface(state)

    lore_fragment_map = {lf.id: lf for lf in state.lore_fragments}
    lore_fragments_found = []
    for disc in discoveries:
        if disc.lore_fragment_id and disc.lore_fragment_id in lore_fragment_map:
            lf = lore_fragment_map[disc.lore_fragment_id]
            lore_fragments_found.append({
                "id": lf.id,
                "title": lf.title,
                "arc": lf.arc,
            })

    decrement_cooldowns(state)
    event = trigger_event(state)
    if event:
        state.events.append(event)
    game_save(state)

    return {
        "result": f"Explored. Found {len(discoveries)} points of interest.",
        "discoveries": [d.to_dict() for d in discoveries],
        "ship": state.ship.to_dict(),
        "lore_fragments_discovered": lore_fragments_found,
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


@router.get("/game/{game_id}/cargo")
def api_cargo(game_id: str) -> dict:
    """Retrieve detailed cargo hold contents.

    Returns the current cargo count, cargo capacity, and a list of
    all discoveries held in the cargo hold with their details and
    sellability status. Lore-linked items are not sellable.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``cargo``, ``cargo_capacity``, and
        ``cargo_items`` list.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    cargo_items = [d.to_cargo_dict() for d in state.discoveries]
    return {
        "cargo": state.ship.cargo,
        "cargo_capacity": state.ship.max_cargo,
        "cargo_items": cargo_items,
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
            frag_dict = lore.to_dict()

            if lore.discovered and lore.discovery_id:
                parts = lore.discovery_id.split("::")
                if len(parts) == 2:
                    sys_id, body_id = parts
                    system = state.systems.get(sys_id)
                    if system:
                        body = None
                        for b in system.bodies:
                            if b.id == body_id:
                                body = b
                                break
                        body_name = body.name if body else body_id
                        frag_dict["discovery_location"] = f"{system.name} - {body_name}"
                    else:
                        # Fallback: use raw IDs so the user at least sees something
                        logger.warning(
                            "Lore fragment %s references unknown system %s (body %s) - possible orphaned reference",
                            lore.id, sys_id, body_id,
                        )
                        frag_dict["discovery_location"] = f"Unknown system ({sys_id}) - Body ({body_id})"

            if lore.discovery_timestamp:
                frag_dict["discovery_date"] = lore.discovery_timestamp

            arcs[arc]["fragments"].append(frag_dict)
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
    response["trade_result"] = {
        "sold_count": sold_count,
        "total_price": total_price,
    }
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


@router.post("/game/{game_id}/distress")
def api_distress(game_id: str) -> dict:
    """Activate the distress beacon to call for help.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``result``, ``outcome``, ``effects``,
        and ``ship`` status.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        beacon cannot be activated.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    result = activate_distress_beacon(state)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    game_save(state)
    return {
        "result": result["result"],
        "outcome": result["outcome"],
        "effects": result["effects"],
        "ship": state.ship.to_dict(),
    }


@router.post("/game/{game_id}/salvage")
def api_salvage(game_id: str) -> dict:
    """Perform a salvage operation on the current body.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``result``, ``find``, ``effects``,
        and ``ship`` status.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if
        salvage is not possible.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    result = perform_salvage(state)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    game_save(state)
    return {
        "result": result["result"],
        "find": result["find"],
        "effects": result["effects"],
        "ship": state.ship.to_dict(),
    }


@router.post("/game/{game_id}/salvage/craft")
def api_salvage_craft(game_id: str, req: CraftRequest) -> dict:
    """Emergency craft a discovery into resources.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param req: The craft request with discovery_id and output type.
    :type req: CraftRequest
    :returns: A dictionary with ``result``, ``crafted``, ``effects``,
        and ``ship`` status.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if
        crafting is not possible.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    result = emergency_craft(state, req.discovery_id, req.output)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    game_save(state)
    return {
        "result": result["result"],
        "crafted": result["crafted"],
        "effects": result["effects"],
        "ship": state.ship.to_dict(),
    }


@router.get("/game/{game_id}/factions")
def api_factions(game_id: str) -> dict:
    """Retrieve all faction definitions and the player's reputation with each.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``factions`` list of faction info dicts.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"factions": state.get_known_factions()}


@router.get("/game/{game_id}/faction/{faction_id}")
def api_faction_detail(game_id: str, faction_id: str) -> dict:
    """Retrieve detailed information about a specific faction.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param faction_id: The unique identifier of the faction.
    :type faction_id: str
    :returns: A dictionary with faction definition and reputation.
    :rtype: dict
    :raises HTTPException: 404 if the game or faction is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    faction = get_faction(faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail="Faction not found")
    relation = state.faction_relations.get(faction_id)
    return {
        "faction": {
            "id": faction.id,
            "name": faction.name,
            "description": faction.description,
            "alignment": faction.alignment,
            "home_system_id": faction.home_system_id,
        },
        "reputation": relation.reputation if relation else 0,
        "known": relation.known if relation else False,
    }


@router.post("/game/{game_id}/faction/{faction_id}/mission")
def api_faction_mission(game_id: str, faction_id: str) -> dict:
    """Run a faction mission to earn reputation with that faction.

    Uses the tiered mission system. Costs and rewards scale with the
    player's reputation — higher reputation unlocks higher-tier missions
    with better payouts.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param faction_id: The unique identifier of the faction.
    :type faction_id: str
    :returns: A dictionary with ``result`` message, ``effect``, ``reputation``,
        ``ship`` status, and ``mission`` details.
    :rtype: dict
    :raises HTTPException: 404 if the game or faction is not found; 400 if
        the mission cannot be attempted.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    faction = get_faction(faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail="Faction not found")

    current_system = state.get_current_system()
    if not current_system:
        raise HTTPException(status_code=400, detail="Not in a star system")
    if not current_system.has_trading_station:
        raise HTTPException(status_code=400, detail="No trading station in this system")

    from backend.utils import seeded_random, deterministic_hash

    missions = generate_missions(state, current_system, faction_id)
    if not missions:
        raise HTTPException(status_code=400, detail="No missions available from this faction")

    standard_missions = [m for m in missions if m.objective_type != "daily"]
    if not standard_missions:
        raise HTTPException(status_code=400, detail="No missions available from this faction")

    rng = seeded_random(
        deterministic_hash(state.seed, faction_id, str(len(state.log_entries))),
        "faction_mission",
    )
    mission = rng.choice(standard_missions)

    # Check if this mission was already completed
    completed_ids = {c.get("mission_id") for c in state.completed_missions}
    if mission.id in completed_ids:
        remaining = [m for m in standard_missions if m.id not in completed_ids]
        if not remaining:
            raise HTTPException(status_code=400, detail="No available missions")
        mission = rng.choice(remaining)

    # Check if this mission was already accepted (but not yet completed)
    if mission.id in state.accepted_missions:
        remaining = [m for m in standard_missions if m.id not in state.accepted_missions and m.id not in completed_ids]
        if not remaining:
            raise HTTPException(status_code=400, detail="No available missions")
        mission = rng.choice(remaining)

    if state.ship.fuel < mission.fuel_cost:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough fuel. Mission requires {mission.fuel_cost} fuel."
        )
    if state.ship.credits < mission.credit_cost:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough credits. Mission requires {mission.credit_cost} credits."
        )

    # Delegate to shared complete_mission() for consistent behavior
    completion_result = complete_mission(state, mission)

    # Ensure the faction is marked as known
    if faction_id in state.faction_relations:
        state.faction_relations[faction_id].known = True

    game_save(state)

    return {
        "result": (
            f"Mission '{mission.title}' for {faction.name} completed! "
            f"Reputation +{mission.reputation_reward}, Credits +{mission.credit_reward}."
        ),
        "effect": "success",
        "reputation": state.get_faction_reputation(faction_id),
        "ship": state.ship.to_dict(),
        "mission": {
            "id": mission.id,
            "title": mission.title,
            "tier": mission.tier,
            "fuel_cost": mission.fuel_cost,
            "credit_cost": mission.credit_cost,
        },
    }


@router.get("/game/{game_id}/missions")
def api_missions(game_id: str) -> dict:
    """Retrieve available tiered missions for the current system.

    Missions are generated procedurally based on the system type,
    the dominant faction present, and the player's reputation with
    that faction. Higher reputation unlocks higher-tier missions.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``system_id``, ``system_name``,
        ``faction_id``, ``faction_name``, ``missions`` list, and
        ``daily_available`` flag.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if
        not in a system or no trading station.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")

    current_system = state.get_current_system()
    if not current_system:
        raise HTTPException(status_code=400, detail="Not in a star system")
    if not current_system.has_trading_station:
        raise HTTPException(status_code=400, detail="No trading station in this system")

    from backend.utils import deterministic_hash

    faction_ids = list(FACTION_DEFINITIONS.keys())
    faction_idx = deterministic_hash(state.seed, current_system.id, "primary_faction") % len(faction_ids)
    primary_faction_id = faction_ids[faction_idx]

    missions = generate_missions(state, current_system, primary_faction_id)

    faction = get_faction(primary_faction_id)

    daily_available = any(m.objective_type == "daily" for m in missions)
    standard_missions = [m for m in missions if m.objective_type != "daily"]

    return {
        "system_id": current_system.id,
        "system_name": current_system.name,
        "faction_id": primary_faction_id,
        "faction_name": faction.name if faction else primary_faction_id,
        "missions": [m.to_dict() for m in standard_missions],
        "daily_mission": next(
            (m.to_dict() for m in missions if m.objective_type == "daily"), None
        ),
        "daily_available": daily_available,
    }


@router.post("/game/{game_id}/missions/{mission_id}/accept")
def api_accept_mission(game_id: str, mission_id: str, req: AcceptMissionRequest) -> dict:
    """Accept a faction mission.

    The mission must exist in the current system and not have been
    completed already. Costs are NOT deducted until the mission is
    completed.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param mission_id: The unique identifier of the mission to accept.
    :type mission_id: str
    :param req: The accept mission request body.
    :type req: AcceptMissionRequest
    :returns: A dictionary with ``result`` message, ``mission`` details,
        and ``ship`` status.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        mission cannot be accepted.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")

    current_system = state.get_current_system()
    if not current_system:
        raise HTTPException(status_code=400, detail="Not in a star system")
    if not current_system.has_trading_station:
        raise HTTPException(status_code=400, detail="No trading station in this system")

    if mission_id != req.mission_id:
        raise HTTPException(status_code=400, detail="Mission ID in path and body must match")

    for completed in state.completed_missions:
        if completed.get("mission_id") == mission_id:
            raise HTTPException(status_code=400, detail="Mission already completed")

    if mission_id in state.accepted_missions:
        raise HTTPException(status_code=400, detail="Mission already accepted")

    if req.faction_id:
        factions_to_check = [req.faction_id]
    else:
        # Restrict to the system's dominant faction to match GET /missions behavior
        from backend.utils import deterministic_hash
        faction_ids = list(FACTION_DEFINITIONS.keys())
        faction_idx = deterministic_hash(state.seed, current_system.id, "primary_faction") % len(faction_ids)
        primary_faction_id = faction_ids[faction_idx]
        factions_to_check = [primary_faction_id]

    mission_found = None
    for fid in factions_to_check:
        missions = generate_missions(state, current_system, fid)
        for m in missions:
            if m.id == mission_id:
                mission_found = m
                break
        if mission_found:
            break

    if not mission_found:
        raise HTTPException(status_code=400, detail="Mission not found in current system")

    if state.ship.fuel < mission_found.fuel_cost:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough fuel. Mission requires {mission_found.fuel_cost} fuel."
        )
    if state.ship.credits < mission_found.credit_cost:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough credits. Mission requires {mission_found.credit_cost} credits."
        )

    state.accepted_missions[mission_id] = mission_found.faction_id

    state.add_log(
        "faction",
        f"Accepted mission '{mission_found.title}' (Tier {mission_found.tier})."
    )

    game_save(state)

    return {
        "result": f"Mission '{mission_found.title}' accepted.",
        "mission": mission_found.to_dict(),
        "ship": state.ship.to_dict(),
    }


@router.post("/game/{game_id}/missions/{mission_id}/complete")
def api_complete_mission(game_id: str, mission_id: str, req: CompleteMissionRequest) -> dict:
    """Complete an accepted faction mission and claim rewards.

    The mission must exist in the current system, not have been
    completed already. Rewards (credits and reputation) are applied.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param mission_id: The unique identifier of the mission to complete.
    :type mission_id: str
    :param req: The complete mission request body.
    :type req: CompleteMissionRequest
    :returns: A dictionary with ``result`` message, ``mission`` details,
        ``rewards``, and ``ship`` status.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        mission cannot be completed.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")

    current_system = state.get_current_system()
    if not current_system:
        raise HTTPException(status_code=400, detail="Not in a star system")
    if not current_system.has_trading_station:
        raise HTTPException(status_code=400, detail="No trading station in this system")

    if mission_id != req.mission_id:
        raise HTTPException(status_code=400, detail="Mission ID in path and body must match")

    for completed in state.completed_missions:
        if completed.get("mission_id") == mission_id:
            raise HTTPException(status_code=400, detail="Mission already completed")

    if mission_id not in state.accepted_missions:
        raise HTTPException(status_code=400, detail="Mission has not been accepted")

    if req.faction_id:
        factions_to_check = [req.faction_id]
    else:
        factions_to_check = [state.accepted_missions[mission_id]]

    mission_found = None
    for fid in factions_to_check:
        missions = generate_missions(state, current_system, fid)
        for m in missions:
            if m.id == mission_id:
                mission_found = m
                break
        if mission_found:
            break

    if not mission_found:
        raise HTTPException(status_code=400, detail="Mission not found in current system")

    completion_result = complete_mission(state, mission_found)

    game_save(state)

    return {
        "result": f"Mission '{mission_found.title}' completed.",
        "mission": mission_found.to_dict(),
        "rewards": completion_result,
        "ship": state.ship.to_dict(),
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
        "cargo_capacity": state.ship.max_cargo,
        "events_pending": [e.to_dict() for e in state.events if not e.resolved],
        "log_entries": list(reversed(state.log_entries))[:20],
        "systems_visited": state.systems_visited,
        "systems_total": len(state.systems),
        "game_started": state.game_started,
        "lore_fragments_collected": state.lore_fragments_collected,
        "lore_fragments_total": len(state.lore_fragments),
        "factions": state.get_known_factions(),
        "reputation_summary": state.build_reputation_summary(),
    }
