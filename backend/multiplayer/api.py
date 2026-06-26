"""
Multiplayer API endpoints for the 'Ghosts in the Void' system.

Defines REST API routes for ghost signatures, crossroads donations
and messages, and discovery ripple events. All endpoints are mounted
under ``/api``.
"""

from threading import Lock

from fastapi import APIRouter, HTTPException

from backend.api.routes import _get_state, _save_state
from backend.multiplayer.schemas import (
    LeaveGhostRequest, DonateItemRequest, DonateLoreRequest,
    PostMessageRequest, ClaimItemRequest, ClaimLoreRequest,
)
from backend.multiplayer.ghosts import (
    record_ghost, get_system_ghosts,
)
from backend.multiplayer.crossroads import (
    donate_item, claim_item, get_available_items_list,
    donate_lore, claim_lore, get_available_lore_list,
    post_message, get_messages,
)
from backend.multiplayer.ripples import (
    create_ripple, get_pending_ripples, acknowledge_ripple,
)

router = APIRouter(prefix="/api")

_game_locks: dict[str, Lock] = {}
_lock_for_locks: Lock = Lock()
_lock_access_count: int = 0


def _get_lock(game_id: str) -> Lock:
    global _lock_access_count
    _lock_access_count += 1
    # Periodic cleanup of stale locks every 100 accesses
    # (called outside the lock to avoid deadlock with _cleanup_stale_locks)
    if _lock_access_count % 100 == 0:
        _cleanup_stale_locks()
    with _lock_for_locks:
        if game_id not in _game_locks:
            _game_locks[game_id] = Lock()
        return _game_locks[game_id]


def _cleanup_game_lock(game_id: str) -> None:
    _game_locks.pop(game_id, None)


def _cleanup_stale_locks() -> None:
    with _lock_for_locks:
        for gid in list(_game_locks.keys()):
            if _get_state(gid) is None:
                del _game_locks[gid]


def _check_game(game_id: str):
    """Validate that a game exists and return its state.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: The :class:`GameState` if found.
    :rtype: GameState
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        _cleanup_game_lock(game_id)
        raise HTTPException(status_code=404, detail="Game not found")
    return state


# ---------------------------------------------------------------------------
# Ghost Signatures
# ---------------------------------------------------------------------------


@router.get("/game/{game_id}/system/{sys_id}/ghosts")
def api_system_ghosts(game_id: str, sys_id: str) -> dict:
    """Retrieve ghost signatures left by other players in a star system.

    Ghost signatures are automatically recorded on jump, scan, and
    explore actions. They provide a trace of other travellers who
    have passed through the system.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param sys_id: The unique identifier of the star system.
    :type sys_id: str
    :returns: A dictionary with ``ghosts`` list of ghost signature dicts.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _check_game(game_id)
    ghosts = get_system_ghosts(sys_id)
    return {"ghosts": ghosts}


@router.post("/game/{game_id}/leave-ghost")
def api_leave_ghost(game_id: str, req: LeaveGhostRequest) -> dict:
    """Leave a ghost signature in the player's current star system.

    The ghost captures the player's discoveries and optional message
    for other players to discover.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param req: The leave-ghost request body with an optional message.
    :type req: LeaveGhostRequest
    :returns: A dictionary with ``ghost`` data.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _check_game(game_id)

    with _get_lock(game_id):
        current_system = state.get_current_system()
        if not current_system:
            raise HTTPException(status_code=400, detail="Not in a star system")

        ghost = record_ghost(state, current_system.id, message=req.message)
        _save_state(game_id)
    return {"ghost": ghost}


# ---------------------------------------------------------------------------
# Crossroads Items
# ---------------------------------------------------------------------------


@router.get("/crossroads/items")
def api_crossroads_items() -> dict:
    """Retrieve all unclaimed items available at the Crossroads.

    Items are donated by players and can be claimed by any other
    player for their own cargo.

    :returns: A dictionary with ``items`` list of available item dicts.
    :rtype: dict
    """
    items = get_available_items_list()
    return {"items": items}


@router.post("/crossroads/donate-item")
def api_donate_item(req: DonateItemRequest) -> dict:
    """Donate an item from a player's cargo to the Crossroads.

    The donated item is removed from the player's inventory and made
    available for other players to claim.

    :param req: The donate-item request body with game_id, item_name,
        quantity, and optional message.
    :type req: DonateItemRequest
    :returns: A dictionary with ``success`` flag and donation data,
        or an error.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        donation fails.
    """
    state = _check_game(req.game_id)
    with _get_lock(req.game_id):
        result = donate_item(state, req.item_name, req.quantity, message=req.message)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Donation failed"))
        _save_state(req.game_id)
    return result


@router.post("/crossroads/claim-item/{item_id}")
def api_claim_item(item_id: str, req: ClaimItemRequest) -> dict:
    """Claim an item from the Crossroads for a player's game.

    The claimed item is added to the player's discoveries.

    :param item_id: The unique identifier of the item to claim.
    :type item_id: str
    :param req: The claim-item request body with game_id.
    :type req: ClaimItemRequest
    :returns: A dictionary with ``success`` flag and item data or error.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if claim fails.
    """
    state = _check_game(req.game_id)
    with _get_lock(req.game_id):
        result = claim_item(item_id, state)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Claim failed"))
        _save_state(req.game_id)
    return result


# ---------------------------------------------------------------------------
# Crossroads Lore
# ---------------------------------------------------------------------------


@router.get("/crossroads/lore")
def api_crossroads_lore() -> dict:
    """Retrieve all unclaimed lore donations available at the Crossroads.

    Lore fragments donated by players can be claimed to unlock their
    narrative text in the claiming player's game.

    :returns: A dictionary with ``lore`` list of available lore dicts.
    :rtype: dict
    """
    lore = get_available_lore_list()
    return {"lore": lore}


@router.post("/crossroads/donate-lore")
def api_donate_lore(req: DonateLoreRequest) -> dict:
    """Donate a discovered lore fragment to the Crossroads.

    The lore fragment must have been discovered by the player first.

    :param req: The donate-lore request body with game_id, fragment_id,
        and optional message.
    :type req: DonateLoreRequest
    :returns: A dictionary with ``success`` flag and donation data,
        or an error.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        donation fails.
    """
    state = _check_game(req.game_id)
    with _get_lock(req.game_id):
        result = donate_lore(state, req.fragment_id, message=req.message)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Donation failed"))
        _save_state(req.game_id)
    return result


@router.post("/crossroads/claim-lore/{donation_id}")
def api_claim_lore(donation_id: str, req: ClaimLoreRequest) -> dict:
    """Claim a lore fragment from the Crossroads for a player's game.

    The claimed lore is marked as discovered in the player's game state.

    :param donation_id: The unique identifier of the lore donation.
    :type donation_id: str
    :param req: The claim-lore request body with game_id.
    :type req: ClaimLoreRequest
    :returns: A dictionary with ``success`` flag and lore data or error.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if claim fails.
    """
    state = _check_game(req.game_id)
    with _get_lock(req.game_id):
        result = claim_lore(donation_id, state)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Claim failed"))
        _save_state(req.game_id)
    return result


# ---------------------------------------------------------------------------
# Crossroads Messages
# ---------------------------------------------------------------------------


@router.get("/crossroads/messages")
def api_crossroads_messages() -> dict:
    """Retrieve recent messages posted at the Crossroads.

    Messages older than 7 days are automatically excluded.

    :returns: A dictionary with ``messages`` list of message dicts.
    :rtype: dict
    """
    msgs = get_messages()
    return {"messages": msgs}


@router.post("/crossroads/post-message")
def api_post_message(req: PostMessageRequest) -> dict:
    """Post a message visible to all players at the Crossroads.

    Messages expire automatically after 7 days.

    :param req: The post-message request body with game_id, text, and
        optional player_name.
    :type req: PostMessageRequest
    :returns: A dictionary with the posted message data.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _check_game(req.game_id)
    with _get_lock(req.game_id):
        msg = post_message(state, req.text)
        if isinstance(msg, dict) and not msg.get("success", True):
            raise HTTPException(status_code=400, detail=msg.get("detail", "Failed to post message"))
        _save_state(req.game_id)
    return {"message": msg}


# ---------------------------------------------------------------------------
# Ripple Events
# ---------------------------------------------------------------------------


@router.get("/game/{game_id}/ripples")
def api_ripples(game_id: str) -> dict:
    """Retrieve pending discovery ripple events for a game.

    Ripples are generated when other players make discoveries in
    nearby systems (within 5 LY). Ripples expire after 7 days.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A dictionary with ``ripples`` list of pending ripple dicts.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    state = _check_game(game_id)
    ripples = get_pending_ripples(state)
    return {"ripples": ripples}


@router.post("/game/{game_id}/ripple/{ripple_id}/acknowledge")
def api_acknowledge_ripple(game_id: str, ripple_id: str) -> dict:
    """Acknowledge a discovery ripple event.

    Once acknowledged, the ripple is removed from the player's
    pending ripples list.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param ripple_id: The unique identifier of the ripple event.
    :type ripple_id: str
    :returns: A dictionary with ``success`` flag.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found;
        400 if the ripple cannot be acknowledged.
    """
    state = _check_game(game_id)

    with _get_lock(game_id):
        result = acknowledge_ripple(ripple_id, state)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Failed to acknowledge ripple"))

        _save_state(game_id)
    return {"success": True}
