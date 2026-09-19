"""
Read-only spectator API for the Starfarer webui.

Provides endpoints that let a human observer watch a game in progress
without mutating any state:

- ``GET /api/spectate/games`` — list known games with a small summary.
- ``GET /api/spectate/{game_id}/stream`` — Server-Sent Events stream that
  pushes a compact state snapshot (plus any new log entries since the
  previous push) whenever the game state changes.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from backend.api import stream_tickets
from backend.api.routes import _authorize_game
from backend.config import get_require_game_token
from backend.database import _safe_ship_credits, get_db_ctx
from backend.game.manager import (
    GAME_STORE,
    evict_if_needed,
    game_load,
    register_game,
    touch_game,
)
from backend.models.game_state import GameState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/spectate", tags=["spectate"])

POLL_INTERVAL_SECONDS = 1.0
HEARTBEAT_INTERVAL_SECONDS = 15.0
INITIAL_LOG_ENTRIES = 25


def _get_state(game_id: str) -> GameState | None:
    """Retrieve a game state from memory or the database (read-only lookup).

    Looks up the game ID in the in-memory ``GAME_STORE`` first so that a
    spectator observes the same live object the playing agent mutates.
    Falls back to loading from the database and caching the result. When
    caching triggers LRU eviction, games whose per-game lock is currently
    held are skipped so an in-flight mutation is never evicted.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: The :class:`GameState` if found, or ``None``.
    :rtype: GameState | None
    """
    if game_id in GAME_STORE:
        touch_game(game_id)
        return GAME_STORE[game_id]
    state = game_load(game_id)
    if state:
        register_game(state)
        from backend.api.routes import _locked_game_ids
        evict_if_needed(_locked_game_ids() | {game_id})
        return state
    return None


@router.get("/games")
def api_spectate_games(limit: int = 25) -> dict:
    """List known games for the spectator game picker.

    Games currently loaded in memory (i.e. actively being played on this
    server process) are flagged with ``active: true``.

    :param limit: Maximum number of games to return (clamped to 1-100).
    :type limit: int
    :returns: A dictionary with a ``games`` list sorted by most recently
        updated first.
    :rtype: dict
    :raises HTTPException: 403 if STARFARER_REQUIRE_GAME_TOKEN enforcement
        is enabled (the listing cannot be authorized per-game, so it is
        disabled while enforcement is on).
    """
    if get_require_game_token():
        raise HTTPException(
            status_code=403,
            detail="Spectate game listing disabled while game token enforcement is enabled",
        )
    limit = max(1, min(100, limit))
    games = []
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, ship_name, seed, updated_at, state_json FROM games "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    seen = set()
    for row in rows:
        try:
            state = json.loads(row["state_json"])
            if not isinstance(state, dict):
                continue
        except (json.JSONDecodeError, TypeError):
            continue
        seen.add(row["id"])
        games.append({
            "game_id": row["id"],
            "ship_name": row["ship_name"],
            "seed": row["seed"],
            "updated_at": row["updated_at"],
            "systems_visited": state.get("systems_visited", 0),
            "credits": _safe_ship_credits(state),
            "active": row["id"] in GAME_STORE,
        })
    # Include in-memory games that were never persisted yet.
    for game_id, state in list(GAME_STORE.items()):
        if game_id in seen:
            continue
        games.insert(0, {
            "game_id": game_id,
            "ship_name": state.ship.name,
            "seed": state.seed,
            "updated_at": state.game_started,
            "systems_visited": state.systems_visited,
            "credits": state.ship.credits,
            "active": True,
        })
    return {"games": games}


def _build_payload(state: GameState, since_log_id: int) -> tuple[dict, int]:
    """Build a spectator payload: state summary plus new log entries.

    :param state: The game state to snapshot.
    :type state: GameState
    :param since_log_id: Only log entries with an id greater than this
        value are included.
    :type since_log_id: int
    :returns: A tuple of ``(payload, last_log_id)``.
    :rtype: tuple[dict, int]
    """
    new_entries = [
        e for e in state.log_entries
        if isinstance(e.get("id"), int) and e["id"] > since_log_id
    ]
    last_log_id = max(
        (e["id"] for e in new_entries),
        default=since_log_id,
    )
    payload = {
        "summary": state.state_summary(),
        "pending_events": [e.to_dict() for e in state.events if not e.resolved],
        "new_log_entries": new_entries,
        "last_log_id": last_log_id,
    }
    return payload, last_log_id


def _state_signature(state: GameState) -> tuple:
    """Compute a cheap change-detection signature for a game state.

    :param state: The game state to fingerprint.
    :type state: GameState
    :returns: A hashable tuple that changes whenever anything a
        spectator cares about changes.
    :rtype: tuple
    """
    ship = state.ship
    return (
        state._next_log_id,
        ship.fuel, ship.hull, ship.morale, ship.credits,
        ship.cargo, ship.crew,
        ship.current_system_id, ship.current_body_id,
        state.systems_visited,
        len([e for e in state.events if not e.resolved]),
        len(state.discoveries),
    )


@router.post("/{game_id}/stream-ticket")
def api_create_stream_ticket(
    game_id: str,
    x_game_token: str | None = Header(default=None),
) -> dict:
    """Mint a short-lived, single-use ticket for the spectator SSE stream.

    Browsers cannot attach custom headers to ``EventSource`` connections,
    so a spectator cannot authenticate the stream with the ``X-Game-Token``
    header. To avoid placing the long-lived per-game token in a URL (where
    it would leak into logs, browser history and ``Referer`` headers), a
    client first calls this endpoint with the header token and receives a
    short-lived, single-use ticket that it then passes as the ``ticket``
    query parameter of ``GET /api/spectate/{game_id}/stream``.

    :param game_id: The unique identifier of the game to spectate.
    :type game_id: str
    :param x_game_token: Optional game token supplied via the
        ``X-Game-Token`` header. Required when token enforcement is on.
    :type x_game_token: str | None
    :returns: A dictionary with the opaque ``ticket`` string and the
        ``expires_in`` lifetime in seconds.
    :rtype: dict
    :raises HTTPException: 403 if token enforcement is enabled and the
        header token is missing or invalid; 404 if the game does not exist.
    """
    _authorize_game(game_id, x_game_token)
    if _get_state(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "ticket": stream_tickets.issue_stream_ticket(game_id),
        "expires_in": stream_tickets.STREAM_TICKET_TTL_SECONDS,
    }


@router.get("/{game_id}/stream")
async def api_spectate_stream(
    game_id: str,
    x_game_token: str | None = Header(default=None),
    ticket: str | None = None,
) -> StreamingResponse:
    """Stream game state changes to a spectator via Server-Sent Events.

    On connect, immediately sends a snapshot containing the state summary,
    pending events, and the most recent log entries. Afterwards, whenever
    the game state changes, pushes the updated summary together with all
    log entries added since the previous push. Sends a comment heartbeat
    while idle so proxies keep the connection open.

    When STARFARER_REQUIRE_GAME_TOKEN enforcement is enabled, the caller
    must authenticate either with the game's token via the
    ``X-Game-Token`` header, or with a short-lived, single-use ticket
    obtained from ``POST /api/spectate/{game_id}/stream-ticket`` and
    supplied via the ``ticket`` query parameter. The ticket exists solely
    because browsers cannot set headers on ``EventSource`` connections;
    the long-lived game token is deliberately never accepted in the URL so
    it cannot leak through logs, proxy caches, browser history or
    ``Referer`` headers.

    :param game_id: The unique identifier of the game to spectate.
    :type game_id: str
    :param x_game_token: Optional game token supplied via the
        ``X-Game-Token`` header.
    :type x_game_token: str | None
    :param ticket: Optional short-lived, single-use stream ticket supplied
        via the ``ticket`` query parameter.
    :type ticket: str | None
    :returns: A ``text/event-stream`` response.
    :rtype: StreamingResponse
    :raises HTTPException: 404 if the game does not exist; 403 if token
        enforcement is enabled and neither the header token nor a valid
        ticket authorizes the request.
    """
    if x_game_token is not None:
        _authorize_game(game_id, x_game_token)
    elif ticket is not None and stream_tickets.consume_stream_ticket(
        ticket, game_id
    ):
        pass
    else:
        _authorize_game(game_id, None)
    if _get_state(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")

    async def event_stream() -> AsyncGenerator[str, None]:
        """Yield Server-Sent Events for a spectator watching a game.

        Sends an initial snapshot with recent log entries and the current
        state summary, then polls for changes on a fixed interval. When
        the state changes, a new ``state`` event is yielded containing
        the updated summary and any log entries added since the last
        push. While the state remains unchanged, a comment heartbeat is
        emitted periodically to keep the connection alive. If the game is
        evicted from the in-memory store, an ``end`` event is sent to
        signal the client to reconnect.

        :yields: SSE-formatted strings: ``state`` events with a JSON
            payload, ``end`` events when the game is gone, and comment
            heartbeats (``: ping``) while idle.
        """
        state = _get_state(game_id)
        assert state is not None  # nosec B101 - runtime guard, not test assertion
        # Initial snapshot: include only the most recent log entries.
        initial_since = 0
        int_ids = [
            e["id"] for e in state.log_entries
            if isinstance(e.get("id"), int)
        ]
        if len(int_ids) > INITIAL_LOG_ENTRIES:
            initial_since = sorted(int_ids)[-INITIAL_LOG_ENTRIES - 1]
        payload, last_log_id = _build_payload(state, initial_since)
        last_signature = _state_signature(state)
        yield f"id: {last_log_id}\nevent: state\ndata: {json.dumps(payload)}\n\n"

        idle_time = 0.0
        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            state = GAME_STORE.get(game_id)
            if state is None:
                # Game evicted from memory (due to the LRU cap or an explicit
                # removal); end the stream so the client reconnects and
                # reloads the game from the database.
                yield "event: end\ndata: {}\n\n"
                return
            signature = _state_signature(state)
            if signature != last_signature:
                last_signature = signature
                payload, last_log_id = _build_payload(state, last_log_id)
                yield f"id: {last_log_id}\nevent: state\ndata: {json.dumps(payload)}\n\n"
                idle_time = 0.0
            else:
                idle_time += POLL_INTERVAL_SECONDS
                if idle_time >= HEARTBEAT_INTERVAL_SECONDS:
                    idle_time = 0.0
                    yield ": ping\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
