"""
Faction data models for the Faction Reputation System.

Defines :class:`Faction` and :class:`FactionRelation` dataclasses
representing factions in the Starfarer universe and the player's
relationship with each.
"""

from dataclasses import dataclass


@dataclass
class Faction:
    """Represents a faction in the Starfarer universe.

    Each faction has a unique ID, display name, description, alignment
    type, and an optional home system.
    """

    id: str
    name: str
    description: str
    alignment: str
    home_system_id: str | None = None


@dataclass
class FactionRelation:
    """Represents the player's relationship with a faction.

    Tracks the current reputation value and whether the faction is
    known to the player.
    """

    faction_id: str
    reputation: int = 0
    known: bool = False


FACTION_DEFINITIONS: dict[str, Faction] = {
    "stellar_cartographers": Faction(
        id="stellar_cartographers",
        name="Stellar Cartographers Union",
        description="An explorer guild dedicated to mapping the uncharted regions of space. "
        "They value discovery and knowledge above all else.",
        alignment="explorer",
    ),
    "void_traders": Faction(
        id="void_traders",
        name="Void Traders Syndicate",
        description="A powerful corporate syndicate that controls trade routes across the galaxy. "
        "They reward loyalty with better prices but punish those who cross them.",
        alignment="corporate",
    ),
    "free_pilots": Faction(
        id="free_pilots",
        name="Free Pilots Guild",
        description="A loose coalition of independent pilots who look out for each other "
        "in the void. They respond to distress calls and value mutual aid.",
        alignment="explorer",
    ),
}


def get_faction(faction_id: str) -> Faction | None:
    """Look up a faction definition by its identifier.

    :param faction_id: The unique identifier of the faction.
    :type faction_id: str
    :returns: The :class:`Faction` if found, or ``None``.
    :rtype: Faction | None
    """
    return FACTION_DEFINITIONS.get(faction_id)
