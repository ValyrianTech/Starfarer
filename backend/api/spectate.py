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

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.database import get_db_ctx
from backend.game.manager import GAME_STORE, game_load
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
    Falls back to loading from the database and caching the result.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: The :class:`GameState` if found, or ``None``.
    :rtype: GameState | None
    """
    if game_id in GAME_STORE:
        return GAME_STORE[game_id]
    state = game_load(game_id)
    if state:
        GAME_STORE[game_id] = state
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
    """
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
            "credits": state.get("ship", {}).get("credits", 0),
            "active": row["id"] in GAME_STORE,
        })
    # Include in-memory games that were never persisted yet.
    for game_id, state in GAME_STORE.items():
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


@router.get("/{game_id}/stream")
async def api_spectate_stream(game_id: str) -> StreamingResponse:
    """Stream game state changes to a spectator via Server-Sent Events.

    On connect, immediately sends a snapshot containing the state summary,
    pending events, and the most recent log entries. Afterwards, whenever
    the game state changes, pushes the updated summary together with all
    log entries added since the previous push. Sends a comment heartbeat
    while idle so proxies keep the connection open.

    :param game_id: The unique identifier of the game to spectate.
    :type game_id: str
    :returns: A ``text/event-stream`` response.
    :rtype: StreamingResponse
    :raises HTTPException: 404 if the game does not exist.
    """
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
        assert state is not None
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
                # Game evicted from memory; end the stream so the client
                # reconnects (which reloads from the database).
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
