"""
Discovery ripple events for the 'Ghosts in the Void' system.

Provides functions for creating and acknowledging ripple events —
signals propagated to nearby star systems when a player makes a
significant discovery, alerting other travellers in those systems.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.models.game_state import GameState
from backend.models.discovery import Discovery
from backend.models.system import StarSystem
from backend.generation.universe import distance_between
from backend.multiplayer.models import RippleEvent
from backend.multiplayer.database import (
    save_ripple_event, get_pending_ripples as db_get_pending_ripples,
    acknowledge_ripple as db_acknowledge_ripple,
)

_RIPPLE_RADIUS_LY = 5


def create_ripple(
    source_game_state: GameState,
    discovery: Discovery,
) -> dict:
    """Create ripple events for nearby systems when a discovery is made.

    Ripple events are propagated to all systems within 5 LY of the
    source system that are not the source itself. Each ripple is
    persisted for other players to discover within a 7-day lifetime.

    :param source_game_state: The game state of the discovering player.
    :type source_game_state: GameState
    :param discovery: The discovery that triggered the ripple.
    :type discovery: Discovery
    :returns: A dictionary with ``ripples_created`` count and the list
        of created ripple event data.
    :rtype: dict
    """
    source_system = source_game_state.get_current_system()
    if not source_system:
        return {"ripples_created": 0, "ripples": []}

    ripples: list[dict] = []
    for sys_id, sys_data in source_game_state.systems.items():
        if sys_id == source_system.id:
            continue
        dist = distance_between(source_system, sys_data)
        dist_ly = round(dist / 10.0, 1)
        if dist_ly > _RIPPLE_RADIUS_LY:
            continue

        ripple = RippleEvent(
            id=str(uuid.uuid4()),
            source_game_id=source_game_state.id,
            source_player_name=source_game_state.ship.name,
            source_system_id=source_system.id,
            target_system_id=sys_id,
            discovery_type=discovery.category,
            discovery_name=discovery.name,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_ripple_event(ripple)
        ripples.append(ripple.to_dict())

    if ripples:
        source_game_state.add_log(
            "multiplayer",
            f"Discovery ripple propagated to {len(ripples)} nearby systems.",
            category="multiplayer",
            title="Discovery Ripple",
        )

    return {"ripples_created": len(ripples), "ripples": ripples}


def get_pending_ripples(game_state: GameState) -> list[dict]:
    """Retrieve all pending ripple events for the player's current system.

    Ripple events are filtered to those within the 7-day lifetime
    and not yet acknowledged by this game session.

    :param game_state: The current game state.
    :type game_state: GameState
    :returns: A list of pending ripple event dictionaries.
    :rtype: list[dict]
    """
    ripples = db_get_pending_ripples(game_state.id)
    current_sys = game_state.get_current_system()
    if not current_sys:
        return []
    matching = [r for r in ripples if r.target_system_id == current_sys.id]
    return [r.to_dict() for r in matching]


def acknowledge_ripple(ripple_id: str, game_state: GameState) -> dict:
    """Acknowledge a ripple event for the current player.

    Once acknowledged, the ripple will no longer appear in the
    player's pending ripples list.

    :param ripple_id: The unique identifier of the ripple event.
    :type ripple_id: str
    :param game_state: The current game state.
    :type game_state: GameState
    :returns: A dictionary with ``success`` flag and the acknowledged
        ripple data, or an error detail.
    :rtype: dict
    """
    ok = db_acknowledge_ripple(ripple_id, game_state.id)
    if not ok:
        return {"success": False, "detail": "Ripple not found or already acknowledged."}

    game_state.add_log(
        "multiplayer",
        f"Acknowledged a discovery ripple.",
        category="multiplayer",
        title="Ripple Acknowledged",
    )
    return {"success": True}
