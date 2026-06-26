"""
Multiplayer data models for the 'Ghosts in the Void' system.

Defines dataclasses for ghost signatures, crossroads donations and
messages, and discovery ripple events shared across game sessions.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GhostSignature:
    """A trace left by a player in a star system for others to discover.

    Ghost signatures are recorded automatically on jump, scan, and
    explore actions. Other players visiting the same system can see
    these echoes of past travellers.
    """

    id: str
    game_id: str
    player_name: str
    system_id: str
    timestamp: str
    discoveries: list[str] = field(default_factory=list)
    message: Optional[str] = None
    body_visits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize the ghost signature to a dictionary.

        :returns: A dictionary representation of the ghost signature.
        :rtype: dict
        """
        return {
            "id": self.id,
            "game_id": self.game_id,
            "player_name": self.player_name,
            "system_id": self.system_id,
            "timestamp": self.timestamp,
            "discoveries": self.discoveries,
            "message": self.message,
            "body_visits": self.body_visits,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GhostSignature":
        """Deserialize a ghost signature from a dictionary.

        :param d: The dictionary containing ghost signature data.
        :type d: dict
        :returns: A new GhostSignature instance.
        :rtype: GhostSignature
        """
        return cls(
            id=d["id"],
            game_id=d["game_id"],
            player_name=d["player_name"],
            system_id=d["system_id"],
            timestamp=d["timestamp"],
            discoveries=d.get("discoveries", []),
            message=d.get("message"),
            body_visits=d.get("body_visits", []),
        )


@dataclass
class CrossroadsItem:
    """An item donated by a player at the Crossroads for others to claim."""

    id: str
    donor_game_id: str
    donor_name: str
    item_name: str
    quantity: int
    message: Optional[str] = None
    claimed: bool = False
    claimer_game_id: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        """Serialize the crossroads item to a dictionary.

        :returns: A dictionary representation of the crossroads item.
        :rtype: dict
        """
        return {
            "id": self.id,
            "donor_game_id": self.donor_game_id,
            "donor_name": self.donor_name,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "message": self.message,
            "claimed": self.claimed,
            "claimer_game_id": self.claimer_game_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CrossroadsItem":
        """Deserialize a crossroads item from a dictionary.

        :param d: The dictionary containing crossroads item data.
        :type d: dict
        :returns: A new CrossroadsItem instance.
        :rtype: CrossroadsItem
        """
        return cls(
            id=d["id"],
            donor_game_id=d["donor_game_id"],
            donor_name=d["donor_name"],
            item_name=d["item_name"],
            quantity=d.get("quantity", 1),
            message=d.get("message"),
            claimed=d.get("claimed", False),
            claimer_game_id=d.get("claimer_game_id"),
            created_at=d.get("created_at", ""),
        )


@dataclass
class CrossroadsLore:
    """A lore fragment donated by a player for others to claim."""

    id: str
    donor_game_id: str
    donor_name: str
    fragment_id: str
    message: Optional[str] = None
    claimed: bool = False
    claimer_game_id: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        """Serialize the crossroads lore donation to a dictionary.

        :returns: A dictionary representation of the lore donation.
        :rtype: dict
        """
        return {
            "id": self.id,
            "donor_game_id": self.donor_game_id,
            "donor_name": self.donor_name,
            "fragment_id": self.fragment_id,
            "message": self.message,
            "claimed": self.claimed,
            "claimer_game_id": self.claimer_game_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CrossroadsLore":
        """Deserialize a crossroads lore donation from a dictionary.

        :param d: The dictionary containing lore donation data.
        :type d: dict
        :returns: A new CrossroadsLore instance.
        :rtype: CrossroadsLore
        """
        return cls(
            id=d["id"],
            donor_game_id=d["donor_game_id"],
            donor_name=d["donor_name"],
            fragment_id=d["fragment_id"],
            message=d.get("message"),
            claimed=d.get("claimed", False),
            claimer_game_id=d.get("claimer_game_id"),
            created_at=d.get("created_at", ""),
        )


@dataclass
class CrossroadsMessage:
    """A player-posted message visible to all travellers at the Crossroads."""

    id: str
    game_id: str
    player_name: str
    text: str
    created_at: str
    expires_at: str

    def to_dict(self) -> dict:
        """Serialize the crossroads message to a dictionary.

        :returns: A dictionary representation of the message.
        :rtype: dict
        """
        return {
            "id": self.id,
            "game_id": self.game_id,
            "player_name": self.player_name,
            "text": self.text,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CrossroadsMessage":
        """Deserialize a crossroads message from a dictionary.

        :param d: The dictionary containing message data.
        :type d: dict
        :returns: A new CrossroadsMessage instance.
        :rtype: CrossroadsMessage
        """
        return cls(
            id=d["id"],
            game_id=d["game_id"],
            player_name=d["player_name"],
            text=d["text"],
            created_at=d["created_at"],
            expires_at=d["expires_at"],
        )


@dataclass
class RippleEvent:
    """A discovery ripple event shared with nearby systems.

    When a player makes a significant discovery, a ripple is created
    and propagated to nearby systems (within 5 LY) so other players
    can learn about it.
    """

    id: str
    source_game_id: str
    source_player_name: str
    source_system_id: str
    target_system_id: str
    discovery_type: str
    discovery_name: str
    created_at: str
    acknowledged_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize the ripple event to a dictionary.

        :returns: A dictionary representation of the ripple event.
        :rtype: dict
        """
        return {
            "id": self.id,
            "source_game_id": self.source_game_id,
            "source_player_name": self.source_player_name,
            "source_system_id": self.source_system_id,
            "target_system_id": self.target_system_id,
            "discovery_type": self.discovery_type,
            "discovery_name": self.discovery_name,
            "created_at": self.created_at,
            "acknowledged_by": self.acknowledged_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RippleEvent":
        """Deserialize a ripple event from a dictionary.

        :param d: The dictionary containing ripple event data.
        :type d: dict
        :returns: A new RippleEvent instance.
        :rtype: RippleEvent
        """
        return cls(
            id=d["id"],
            source_game_id=d["source_game_id"],
            source_player_name=d["source_player_name"],
            source_system_id=d["source_system_id"],
            target_system_id=d["target_system_id"],
            discovery_type=d["discovery_type"],
            discovery_name=d["discovery_name"],
            created_at=d["created_at"],
            acknowledged_by=d.get("acknowledged_by", []),
        )
