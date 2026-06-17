import time

from fastapi import APIRouter, HTTPException

from backend.api.schemas import (
    NewGameRequest, ResolveEventRequest, TradeRequest, UpgradeRequest,
    HealthResponse,
)
from backend.game.manager import (
    GAME_STORE, new_game, get_galaxy, get_system_detail, game_save, game_load as game_load_func,
)
from backend.generation.events import trigger_event, resolve_event as resolve_event_func
from backend.game.engine import (
    can_jump, perform_jump, perform_scan, get_nearby_systems,
    land_on_body, explore_surface,
)
from backend.game.trading import get_upgrade_info, purchase_upgrade, perform_trade
from backend.database import get_leaderboard, load_game as db_load_game

START_TIME = time.time()

router = APIRouter(prefix="/api")


def _get_state(game_id: str):
    if game_id in GAME_STORE:
        return GAME_STORE[game_id]
    data = db_load_game(game_id)
    if data:
        state = game_load_func(game_id)
        if state:
            GAME_STORE[game_id] = state
            return state
    return None


def _save_state(game_id: str):
    if game_id in GAME_STORE:
        game_save(GAME_STORE[game_id])


@router.get("/health", response_model=HealthResponse)
def health():
    uptime = round(time.time() - START_TIME, 1)
    return HealthResponse(status="ok", version="0.1.0", uptime=f"{uptime}s")


@router.post("/game/new")
def api_new_game(req: NewGameRequest):
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
def api_get_game(game_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return _full_state_response(state)


@router.get("/game/{game_id}/galaxy")
def api_galaxy(game_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return get_galaxy(state)


@router.get("/game/{game_id}/system/{sys_id}")
def api_system_detail(game_id: str, sys_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    detail = get_system_detail(state, sys_id)
    if not detail:
        raise HTTPException(status_code=404, detail="System not found")
    return detail


@router.post("/game/{game_id}/jump/{sys_id}")
def api_jump(game_id: str, sys_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")

    if sys_id not in state.systems:
        raise HTTPException(status_code=404, detail="Target system not found")

    target = state.systems[sys_id]
    current = state.get_current_system()

    ok, fuel_cost, msg = can_jump(state.ship, target, current)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Cannot jump to {target.name}: {msg}")

    result = perform_jump(state, target, fuel_cost)
    game_save(state)

    event = trigger_event(state)
    if event:
        state.events.append(event)

    return {
        "result": result,
        "current_system": state.get_current_system().to_dict() if state.get_current_system() else None,
        "ship": state.ship.to_dict(),
        "pending_event": event.to_dict() if event and not event.resolved else None,
    }


@router.post("/game/{game_id}/scan")
def api_scan(game_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    result = perform_scan(state)
    game_save(state)

    event = trigger_event(state)
    if event:
        state.events.append(event)

    current = state.get_current_system()
    return {
        "result": result,
        "system": current.to_dict() if current else None,
        "ship": state.ship.to_dict(),
        "pending_event": event.to_dict() if event and not event.resolved else None,
    }


@router.post("/game/{game_id}/land/{body_id}")
def api_land(game_id: str, body_id: str):
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
def api_explore(game_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    discoveries = explore_surface(state)
    game_save(state)

    event = trigger_event(state)
    if event:
        state.events.append(event)

    return {
        "result": f"Explored. Found {len(discoveries)} points of interest.",
        "discoveries": [d.to_dict() for d in discoveries],
        "ship": state.ship.to_dict(),
        "pending_event": event.to_dict() if event and not event.resolved else None,
    }


@router.post("/game/{game_id}/event/{event_id}/resolve")
def api_resolve_event(game_id: str, event_id: str, req: ResolveEventRequest):
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
def api_log(game_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    entries = list(reversed(state.log_entries))
    return {
        "count": len(entries),
        "entries": entries,
    }


@router.get("/game/{game_id}/discoveries")
def api_discoveries(game_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "count": len(state.discoveries),
        "discoveries": [d.to_dict() for d in state.discoveries],
    }


@router.post("/game/{game_id}/trade")
def api_trade(game_id: str, req: TradeRequest):
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


@router.post("/game/{game_id}/upgrade")
def api_upgrade(game_id: str, req: UpgradeRequest):
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
def api_upgrades_info(game_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "upgrades": get_upgrade_info(state.ship),
        "credits": state.ship.credits,
    }


@router.get("/game/{game_id}/nearby")
def api_nearby(game_id: str):
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
def api_save(game_id: str):
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    game_save(state)
    return {"result": "Game saved.", "game_id": game_id}


@router.post("/game/{game_id}/load")
def api_load(game_id: str):
    state = game_load_func(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Save not found for this game")
    GAME_STORE[game_id] = state
    return {
        "result": "Game loaded.",
        "state": state.state_summary(),
    }


@router.get("/leaderboard")
def api_leaderboard():
    return {
        "leaderboard": get_leaderboard(limit=10),
    }


def _full_state_response(state):
    return {
        "game_id": state.id,
        "seed": state.seed,
        "ship": state.ship.to_dict(),
        "current_system": state.get_current_system().to_dict() if state.get_current_system() else None,
        "discoveries": [d.to_dict() for d in state.discoveries],
        "events_pending": [e.to_dict() for e in state.events if not e.resolved],
        "log_entries": list(reversed(state.log_entries))[:20],
        "systems_visited": state.systems_visited,
        "systems_total": len(state.systems),
        "game_started": state.game_started,
    }
