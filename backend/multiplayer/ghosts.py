"""
Ghost signature management for the 'Ghosts in the Void' system.

Provides functions for recording and retrieving ghost signatures —
traces left by players in star systems that other travellers can
discover.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.models.game_state import GameState
from backend.multiplayer.models import GhostSignature
from backend.multiplayer.database import save_ghost_signature, get_ghost_signatures


def record_ghost(
    game_state: GameState,
    system_id: str,
    message: Optional[str] = None,
) -> dict:
    """Record a ghost signature for the current player at a given system.

    Captures the player's current discoveries and body visit history
    as a ghost visible to other players visiting the same system.

    :param game_state: The current game state.
    :type game_state: GameState
    :param system_id: The unique identifier of the star system.
    :type system_id: str
    :param message: An optional message to include with the ghost signature.
    :type message: str or None
    :returns: A dictionary representation of the recorded ghost signature.
    :rtype: dict
    """
    system_discoveries = [d for d in game_state.discoveries if d.system_id == system_id]
    ghost = GhostSignature(
        id=str(uuid.uuid4()),
        game_id=game_state.id,
        player_name=game_state.ship.name,
        system_id=system_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        discoveries=[d.name for d in system_discoveries],
        message=message,
        body_visits=list(set(d.body_id for d in system_discoveries if d.body_id is not None)),
    )
    save_ghost_signature(ghost)
    game_state.add_log(
        "multiplayer",
        f"Left a ghost signature in the system.",
        category="multiplayer",
        title="Ghost Signature Recorded",
        system=system_id,
    )
    return ghost.to_dict()


def get_system_ghosts(system_id: str) -> list[dict]:
    """Retrieve all ghost signatures for a given star system.

    :param system_id: The unique identifier of the star system.
    :type system_id: str
    :returns: A list of ghost signature dictionaries.
    :rtype: list[dict]
    """
    ghosts = get_ghost_signatures(system_id)
    return [g.to_dict() for g in ghosts]
