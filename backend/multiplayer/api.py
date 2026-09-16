"""
Multiplayer API endpoints for the 'Ghosts in the Void' system.

Defines REST API routes for ghost signatures, crossroads donations
and messages, and discovery ripple events. All endpoints are mounted
under ``/api``.
"""

import hashlib
import math

from fastapi import APIRouter, Header, HTTPException

from backend.api.routes import (
    _authorize_game,
    _get_lock,
    _get_state,
    _save_state,
)
from backend.game.manager import GAME_STORE
from backend.models.game_state import GameState
from backend.multiplayer.crossroads import (
    claim_item,
    claim_lore,
    donate_item,
    donate_lore,
    get_available_items_list,
    get_available_lore_list,
    get_messages,
    post_message,
)
from backend.multiplayer.ghosts import (
    get_system_ghosts,
    record_ghost,
)
from backend.multiplayer.ripples import (
    acknowledge_ripple,
    get_pending_ripples,
)
from backend.multiplayer.schemas import (
    ClaimItemRequest,
    ClaimLoreRequest,
    DonateItemRequest,
    DonateLoreRequest,
    LeaveGhostRequest,
    PostMessageRequest,
)

router = APIRouter(prefix="/api")


def _game_exists(game_id: str) -> bool:
    """Check if a game exists without loading its full state.

    Checks the in-memory ``GAME_STORE`` first, then falls back to
    a lightweight database existence query.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: ``True`` if the game exists, ``False`` otherwise.
    :rtype: bool
    """
    if game_id in GAME_STORE:
        return True
    from backend.database import game_exists
    return game_exists(game_id)


def _check_game(game_id: str) -> GameState:
    """Validate that a game exists and return its state.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: The :class:`GameState` if found.
    :rtype: GameState
    :raises HTTPException: 404 if the game is not found.
    """
    state = _get_state(game_id)
    if not state:
        raise HTTPException(status_code=404, detail="Game not found")
    return state


def _safe_text(value: str | None, max_len: int = 500) -> str | None:
    """Truncate a free-text value to ``max_len`` characters.

    :param value: The text to sanitize, or ``None``.
    :type value: str | None
    :param max_len: The maximum number of characters to retain.
    :type max_len: int
    :returns: The truncated text, or ``None`` if ``value`` is ``None``.
    :rtype: str | None
    """
    if value is None:
        return None
    return value[:max_len]


def _opaque_donor_id(game_id: str) -> str:
    """Derive a short, stable, non-reversible opaque id from a game id.

    :param game_id: The raw donor game id.
    :type game_id: str
    :returns: A 12-character hex digest prefix of the game id.
    :rtype: str
    """
    return hashlib.sha256(game_id.encode()).hexdigest()[:12]


def _public_item_view(item: dict) -> dict:
    """Return a sanitized public view of a Crossroads item.

    Removes the donor/claimer game ids, truncates free-text fields,
    and adds a stable opaque ``donor_id`` so raw game ids are never
    exposed to other players.

    :param item: The item dict produced by ``CrossroadsItem.to_dict()``.
    :type item: dict
    :returns: A copy with sanitized fields plus an opaque ``donor_id``.
    :rtype: dict
    """
    view = dict(item)
    view.pop("donor_game_id", None)
    view.pop("claimer_game_id", None)
    view["donor_name"] = _safe_text(view["donor_name"], 100)
    view["message"] = _safe_text(view["message"], 500)
    view["donor_id"] = _opaque_donor_id(item["donor_game_id"])
    return view


def _public_lore_view(lore: dict) -> dict:
    """Return a sanitized public view of a Crossroads lore donation.

    Removes the donor/claimer game ids, truncates free-text fields,
    and adds a stable opaque ``donor_id`` so raw game ids are never
    exposed to other players.

    :param lore: The lore dict produced by ``CrossroadsLore.to_dict()``.
    :type lore: dict
    :returns: A copy with sanitized fields plus an opaque ``donor_id``.
    :rtype: dict
    """
    view = dict(lore)
    view.pop("donor_game_id", None)
    view.pop("claimer_game_id", None)
    view["donor_name"] = _safe_text(view["donor_name"], 100)
    view["message"] = _safe_text(view["message"], 500)
    view["donor_id"] = _opaque_donor_id(lore["donor_game_id"])
    return view


def _public_message_view(msg: dict) -> dict:
    """Return a sanitized public view of a Crossroads message.

    Removes the author's raw game id and truncates free-text fields
    so raw game ids and oversized text are never exposed to other
    players.

    :param msg: The message dict produced by ``CrossroadsMessage.to_dict()``.
    :type msg: dict
    :returns: A copy with sanitized fields.
    :rtype: dict
    """
    view = dict(msg)
    view.pop("game_id", None)
    view["player_name"] = _safe_text(view["player_name"], 100)
    view["text"] = _safe_text(view["text"], 500)
    return view


# ---------------------------------------------------------------------------
# Ghost Signatures
# ---------------------------------------------------------------------------


@router.get("/game/{game_id}/system/{sys_id}/ghosts")
def api_system_ghosts(
    game_id: str,
    sys_id: str,
    page: int = 1,
    per_page: int = 10,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Retrieve ghost signatures left by other players in a star system.

    Ghost signatures provide a trace of other travellers who
    have passed through the system. Supports pagination via optional
    ``page`` and ``per_page`` query parameters.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param sys_id: The unique identifier of the star system.
    :type sys_id: str
    :param page: The page number to retrieve (1-indexed, default 1).
    :type page: int
    :param per_page: Number of ghosts per page (max 50, default 10).
    :type per_page: int
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``ghosts``, ``page``, ``per_page``,
        ``total_ghosts``, and ``total_pages``.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    :raises HTTPException: 404 if page exceeds total pages with active ghosts.
    :raises HTTPException: 403 if token enforcement is enabled and the
        token is missing or invalid.
    """
    with _get_lock(game_id):
        _authorize_game(game_id, x_game_token or token)
        if not _game_exists(game_id):
            raise HTTPException(status_code=404, detail="Game not found")
        result = get_system_ghosts(sys_id, page=page, per_page=per_page)
        if page > result["total_pages"] and result["total_ghosts"] > 0:
            raise HTTPException(status_code=404, detail="Page out of range")
    return result


@router.post("/game/{game_id}/leave-ghost")
def api_leave_ghost(
    game_id: str,
    req: LeaveGhostRequest,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Leave a ghost signature in the player's current star system.

    The ghost captures the player's discoveries and optional message
    for other players to discover.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param req: The leave-ghost request body with an optional message.
    :type req: LeaveGhostRequest
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``ghost`` data.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    with _get_lock(game_id):
        _authorize_game(game_id, x_game_token or token)
        state = _check_game(game_id)
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
def api_crossroads_items(
    game_id: str,
    page: int = 1,
    per_page: int = 25,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Retrieve all unclaimed items available at the Crossroads.

    Items are donated by players and can be claimed by any other
    player for their own cargo. Supports pagination via optional
    ``page`` and ``per_page`` query parameters.

    :param game_id: The unique identifier of the caller's game.
    :type game_id: str
    :param page: The page number to retrieve (1-indexed, default 1).
    :type page: int
    :param per_page: Number of items per page (max 50, default 25).
    :type per_page: int
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``items``, ``page``, ``per_page``,
        ``total_items``, and ``total_pages``.
    :rtype: dict
    :raises HTTPException: 403/404 when token enforcement is enabled and the
        token is missing/invalid or the game cannot be resolved.
    """
    _authorize_game(game_id, x_game_token or token)
    page = max(1, page)
    per_page = max(1, min(per_page, 50))
    all_items = get_available_items_list()
    total = len(all_items)
    start = (page - 1) * per_page
    items = [_public_item_view(i) for i in all_items[start : start + per_page]]
    total_pages = math.ceil(total / per_page)
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total_items": total,
        "total_pages": total_pages,
    }


@router.post("/crossroads/donate-item")
def api_donate_item(
    req: DonateItemRequest,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Donate an item from a player's cargo to the Crossroads.

    The donated item is removed from the player's inventory and made
    available for other players to claim.

    :param req: The donate-item request body with game_id, item_name,
        quantity, and optional message.
    :type req: DonateItemRequest
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``success`` flag and donation data,
        or an error.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        donation fails.
    """
    with _get_lock(req.game_id):
        _authorize_game(req.game_id, x_game_token or token)
        state = _check_game(req.game_id)
        result = donate_item(state, req.item_name, req.quantity, message=req.message)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Donation failed"))
        _save_state(req.game_id)
    return result


@router.post("/crossroads/claim-item/{item_id}")
def api_claim_item(
    item_id: str,
    req: ClaimItemRequest,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Claim an item from the Crossroads for a player's game.

    The claimed item is added to the player's discoveries.

    :param item_id: The unique identifier of the item to claim.
    :type item_id: str
    :param req: The claim-item request body with game_id.
    :type req: ClaimItemRequest
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``success`` flag and item data or error.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if claim fails.
    """
    with _get_lock(req.game_id):
        _authorize_game(req.game_id, x_game_token or token)
        state = _check_game(req.game_id)
        result = claim_item(item_id, state)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Claim failed"))
        _save_state(req.game_id)
    return result


# ---------------------------------------------------------------------------
# Crossroads Lore
# ---------------------------------------------------------------------------


@router.get("/crossroads/lore")
def api_crossroads_lore(
    game_id: str,
    page: int = 1,
    per_page: int = 25,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Retrieve all unclaimed lore donations available at the Crossroads.

    Lore fragments donated by players can be claimed to unlock their
    narrative text in the claiming player's game. Supports pagination
    via optional ``page`` and ``per_page`` query parameters.

    :param game_id: The unique identifier of the caller's game.
    :type game_id: str
    :param page: The page number to retrieve (1-indexed, default 1).
    :type page: int
    :param per_page: Number of lore donations per page (max 50, default 25).
    :type per_page: int
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``lore``, ``page``, ``per_page``,
        ``total_lore``, and ``total_pages``.
    :rtype: dict
    :raises HTTPException: 403/404 when token enforcement is enabled and the
        token is missing/invalid or the game cannot be resolved.
    """
    _authorize_game(game_id, x_game_token or token)
    page = max(1, page)
    per_page = max(1, min(per_page, 50))
    all_lore = get_available_lore_list()
    total = len(all_lore)
    start = (page - 1) * per_page
    lore = [_public_lore_view(l) for l in all_lore[start : start + per_page]]
    total_pages = math.ceil(total / per_page)
    return {
        "lore": lore,
        "page": page,
        "per_page": per_page,
        "total_lore": total,
        "total_pages": total_pages,
    }


@router.post("/crossroads/donate-lore")
def api_donate_lore(
    req: DonateLoreRequest,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Donate a discovered lore fragment to the Crossroads.

    The lore fragment must have been discovered by the player first.

    :param req: The donate-lore request body with game_id, fragment_id,
        and optional message.
    :type req: DonateLoreRequest
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``success`` flag and donation data,
        or an error.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if the
        donation fails.
    """
    with _get_lock(req.game_id):
        _authorize_game(req.game_id, x_game_token or token)
        state = _check_game(req.game_id)
        result = donate_lore(state, req.fragment_id, message=req.message)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Donation failed"))
        _save_state(req.game_id)
    return result


@router.post("/crossroads/claim-lore/{donation_id}")
def api_claim_lore(
    donation_id: str,
    req: ClaimLoreRequest,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Claim a lore fragment from the Crossroads for a player's game.

    The claimed lore is marked as discovered in the player's game state.

    :param donation_id: The unique identifier of the lore donation.
    :type donation_id: str
    :param req: The claim-lore request body with game_id.
    :type req: ClaimLoreRequest
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``success`` flag and lore data or error.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found; 400 if claim fails.
    """
    with _get_lock(req.game_id):
        _authorize_game(req.game_id, x_game_token or token)
        state = _check_game(req.game_id)
        result = claim_lore(donation_id, state)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Claim failed"))
        _save_state(req.game_id)
    return result


# ---------------------------------------------------------------------------
# Crossroads Messages
# ---------------------------------------------------------------------------


@router.get("/crossroads/messages")
def api_crossroads_messages(
    game_id: str,
    page: int = 1,
    per_page: int = 10,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Retrieve recent messages posted at the Crossroads.

    Messages older than 7 days are automatically excluded. Supports
    pagination via optional ``page`` and ``per_page`` query parameters.

    :param game_id: The unique identifier of the caller's game.
    :type game_id: str
    :param page: The page number to retrieve (1-indexed, default 1).
    :type page: int
    :param per_page: Number of messages per page (max 50, default 10).
    :type per_page: int
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``messages`` list, ``page``, ``per_page``,
        ``total_messages``, and ``total_pages``.
    :rtype: dict
    :raises HTTPException: 404 if page exceeds total pages with active messages.
    :raises HTTPException: 403/404 when token enforcement is enabled and the
        token is missing/invalid or the game cannot be resolved.
    """
    _authorize_game(game_id, x_game_token or token)
    result = get_messages(page=page, per_page=per_page)
    if page > result["total_pages"] and result["total_messages"] > 0:
        raise HTTPException(status_code=404, detail="Page out of range")
    result["messages"] = [_public_message_view(m) for m in result["messages"]]
    return result


@router.post("/crossroads/post-message")
def api_post_message(
    req: PostMessageRequest,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Post a message visible to all players at the Crossroads.

    Messages expire automatically after 7 days.

    :param req: The post-message request body with game_id, text, and
        optional player_name.
    :type req: PostMessageRequest
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with the posted message data.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    """
    with _get_lock(req.game_id):
        _authorize_game(req.game_id, x_game_token or token)
        state = _check_game(req.game_id)
        msg = post_message(state, req.text)
        if isinstance(msg, dict) and not msg.get("success"):
            raise HTTPException(status_code=400, detail=msg.get("detail", "Failed to post message"))
        _save_state(req.game_id)
    return {"message": msg["message"]}


# ---------------------------------------------------------------------------
# Ripple Events
# ---------------------------------------------------------------------------


@router.get("/game/{game_id}/ripples")
def api_ripples(
    game_id: str,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Retrieve pending discovery ripple events for a game.

    Ripples are generated when other players make discoveries in
    nearby systems (within 5 LY). Ripples expire after 7 days.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``ripples`` list of pending ripple dicts.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found.
    :raises HTTPException: 403 if token enforcement is enabled and the
        token is missing or invalid.
    """
    with _get_lock(game_id):
        _authorize_game(game_id, x_game_token or token)
        state = _check_game(game_id)
    # Ripple data is read from the database, not from in-memory game state.
    # The game state is only used to determine the player's current system for filtering.
    ripples = get_pending_ripples(state)
    return {"ripples": ripples}


@router.post("/game/{game_id}/ripple/{ripple_id}/acknowledge")
def api_acknowledge_ripple(
    game_id: str,
    ripple_id: str,
    x_game_token: str | None = Header(default=None),
    token: str | None = None,
) -> dict:
    """Acknowledge a discovery ripple event.

    Once acknowledged, the ripple is removed from the player's
    pending ripples list.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :param ripple_id: The unique identifier of the ripple event.
    :type ripple_id: str
    :param x_game_token: The caller-supplied per-game token (X-Game-Token header).
    :type x_game_token: str | None
    :param token: The caller-supplied per-game token (query parameter).
    :type token: str | None
    :returns: A dictionary with ``success`` flag.
    :rtype: dict
    :raises HTTPException: 404 if the game is not found;
        400 if the ripple cannot be acknowledged.
    """
    with _get_lock(game_id):
        _authorize_game(game_id, x_game_token or token)
        state = _check_game(game_id)
        result = acknowledge_ripple(ripple_id, state)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("detail", "Failed to acknowledge ripple"))

        _save_state(game_id)
    return {"success": True}
