"""
Crossroads trading post for the 'Ghosts in the Void' system.

Provides functions for donating and claiming items and lore fragments,
and posting messages visible to all players at the Crossroads — the
shared gathering point for travellers across all game sessions.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.models.game_state import GameState
from backend.models.discovery import Discovery, LoreFragment
from backend.multiplayer.models import (
    CrossroadsItem, CrossroadsLore, CrossroadsMessage,
)
from backend.multiplayer.database import (
    save_crossroads_item, get_available_items, claim_item as db_claim_item,
    save_crossroads_lore, get_available_lore, claim_lore as db_claim_lore,
    save_crossroads_message, get_recent_messages,
)

MAX_MESSAGE_LENGTH = 500


def donate_item(
    game_state: GameState,
    item_name: str,
    quantity: int,
    message: Optional[str] = None,
) -> dict:
    """Donate an item from the player's cargo to the Crossroads.

    The item must exist in the player's discoveries. It is removed
    from the player's inventory and made available for other players
    to claim.

    :param game_state: The current game state.
    :type game_state: GameState
    :param item_name: The name of the item to donate (must match a discovery).
    :type item_name: str
    :param quantity: The quantity to donate.
    :type quantity: int
    :param message: An optional message to attach to the donation.
    :type message: str or None
    :returns: A dictionary with ``success`` flag and the donated item data.
    :rtype: dict
    """
    matching = [d for d in game_state.discoveries if d.name == item_name]
    if not matching:
        return {"success": False, "detail": f"No discovery named '{item_name}' in cargo."}

    actual_quantity = min(quantity, len(matching))
    indices_to_remove = []
    for i, d in enumerate(game_state.discoveries):
        if d.name == item_name and len(indices_to_remove) < actual_quantity:
            indices_to_remove.append(i)
    for i in sorted(indices_to_remove, reverse=True):
        game_state.discoveries.pop(i)

    item = CrossroadsItem(
        id=str(uuid.uuid4()),
        donor_game_id=game_state.id,
        donor_name=game_state.ship.name,
        item_name=item_name,
        quantity=actual_quantity,
        message=message,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_crossroads_item(item)
    game_state.add_log(
        "multiplayer",
        f"Donated {actual_quantity}x {item_name} to the Crossroads.",
        category="multiplayer",
        title="Item Donated",
        cargo_change=-actual_quantity,
    )
    return {"success": True, "donation": item.to_dict()}


def claim_item(item_id: str, game_state: GameState) -> dict:
    """Claim an item that was donated by another player at the Crossroads.

    The claimed item is added to the player's discoveries as a new
    :class:`Discovery` record.

    Uses an atomic database claim operation to eliminate the TOCTOU
    race condition between checking availability and claiming.

    :param item_id: The unique identifier of the item to claim.
    :type item_id: str
    :param game_state: The current game state.
    :type game_state: GameState
    :returns: A dictionary with ``success`` flag and item data or error detail.
    :rtype: dict
    """
    item_data = db_claim_item(item_id, game_state.id)
    if not item_data:
        return {"success": False, "detail": "Item not found or already claimed."}

    for _ in range(item_data["quantity"]):
        disc = Discovery(
            id=str(uuid.uuid4()),
            category="artifact",
            name=item_data["item_name"],
            description=f"A gift from {item_data['donor_name']} via the Crossroads.",
            value=0,
            system_id=game_state.ship.current_system_id or "",
        )
        game_state.discoveries.append(disc)

    game_state.add_log(
        "multiplayer",
        f"Claimed {item_data['quantity']}x {item_data['item_name']} from the Crossroads (donated by {item_data['donor_name']}).",
        category="multiplayer",
        title="Item Claimed",
        cargo_change=item_data["quantity"],
    )
    return {"success": True, "item": item_data}


def get_available_items_list() -> list[dict]:
    """Retrieve all unclaimed items available at the Crossroads.

    :returns: A list of available item dictionaries.
    :rtype: list[dict]
    """
    items = get_available_items()
    return [i.to_dict() for i in items]


def donate_lore(
    game_state: GameState,
    fragment_id: str,
    message: Optional[str] = None,
) -> dict:
    """Donate a discovered lore fragment to the Crossroads for other
    players to read.

    The player must have discovered the lore fragment before donating.

    :param game_state: The current game state.
    :type game_state: GameState
    :param fragment_id: The unique identifier of the lore fragment.
    :type fragment_id: str
    :param message: An optional message to attach to the donation.
    :type message: str or None
    :returns: A dictionary with ``success`` flag and lore donation data.
    :rtype: dict
    """
    fragment = None
    for lf in game_state.lore_fragments:
        if lf.id == fragment_id and lf.discovered:
            fragment = lf
            break
    if not fragment:
        return {"success": False, "detail": f"Lore fragment '{fragment_id}' not found or not yet discovered."}

    lore = CrossroadsLore(
        id=str(uuid.uuid4()),
        donor_game_id=game_state.id,
        donor_name=game_state.ship.name,
        fragment_id=fragment_id,
        message=message,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_crossroads_lore(lore)
    game_state.lore_fragments = [lf for lf in game_state.lore_fragments if lf.id != fragment_id]
    game_state.add_log(
        "multiplayer",
        f"Donated lore fragment '{fragment.title}' to the Crossroads.",
        category="multiplayer",
        title="Lore Donated",
    )
    return {"success": True, "donation": lore.to_dict()}


def claim_lore(donation_id: str, game_state: GameState) -> dict:
    """Claim a lore fragment donation from the Crossroads.

    The claimed lore fragment is marked as discovered in the player's
    game state, unlocking its narrative text.

    Uses an atomic database claim operation to eliminate the TOCTOU
    race condition between checking availability and claiming.

    :param donation_id: The unique identifier of the lore donation.
    :type donation_id: str
    :param game_state: The current game state.
    :type game_state: GameState
    :returns: A dictionary with ``success`` flag and lore data or error detail.
    :rtype: dict
    """
    lore_data = db_claim_lore(donation_id, game_state.id)
    if not lore_data:
        return {"success": False, "detail": "Lore donation not found or already claimed."}

    for lf in game_state.lore_fragments:
        if lf.id == lore_data["fragment_id"]:
            lf.discovered = True
            lf.discovery_timestamp = datetime.now(timezone.utc).isoformat()
            break

    game_state.add_log(
        "multiplayer",
        f"Claimed lore fragment '{lore_data['fragment_id']}' from the Crossroads (donated by {lore_data['donor_name']}).",
        category="multiplayer",
        title="Lore Claimed",
    )
    return {"success": True, "lore": lore_data}


def get_available_lore_list() -> list[dict]:
    """Retrieve all unclaimed lore donations available at the Crossroads.

    :returns: A list of available lore donation dictionaries.
    :rtype: list[dict]
    """
    items = get_available_lore()
    return [l.to_dict() for l in items]


def post_message(game_state: GameState, text: str) -> dict:
    """Post a message visible to all players at the Crossroads.

    Messages expire automatically after 7 days.

    :param game_state: The current game state.
    :type game_state: GameState
    :param text: The text content of the message.
    :type text: str
    :returns: A dictionary representation of the posted message.
    :rtype: dict
    """
    if not text or not text.strip():
        return {"success": False, "detail": "Message text cannot be empty."}
    if len(text) > MAX_MESSAGE_LENGTH:
        return {"success": False, "detail": f"Message text exceeds {MAX_MESSAGE_LENGTH} characters."}
    msg = CrossroadsMessage(
        id=str(uuid.uuid4()),
        game_id=game_state.id,
        player_name=game_state.ship.name,
        text=text,
        created_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    )
    save_crossroads_message(msg)
    game_state.add_log(
        "multiplayer",
        "Posted a message at the Crossroads.",
        category="multiplayer",
        title="Message Posted",
    )
    return msg.to_dict()


def get_messages() -> list[dict]:
    """Retrieve recent Crossroads messages that have not yet expired.

    :returns: A list of message dictionaries, newest first.
    :rtype: list[dict]
    """
    msgs = get_recent_messages(limit=50)
    return [m.to_dict() for m in msgs]
