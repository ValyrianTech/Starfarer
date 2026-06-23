"""
Data models for discoveries and lore fragments.

Defines the :class:`Discovery` and :class:`LoreFragment` dataclasses used
to represent points of interest found during exploration and the narrative
lore fragments scattered throughout the galaxy.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Discovery:
    """Represents a point of interest discovered during surface exploration.

    Discoveries are generated when exploring planets and moons. They have a
    category, value, and may be linked to lore fragments.
    """

    id: str
    category: str
    name: str
    description: str
    lore_fragment_id: Optional[str] = None
    value: int = 0
    system_id: str = ""
    body_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize the discovery to a dictionary.

        :returns: A dictionary representation of the discovery.
        :rtype: dict
        """
        return {
            "id": self.id,
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "lore_fragment_id": self.lore_fragment_id,
            "value": self.value,
            "system_id": self.system_id,
            "body_id": self.body_id,
            "sellable": self.lore_fragment_id is None,
        }

    def to_cargo_dict(self) -> dict:
        """Serialize the discovery as a cargo item dictionary.

        Returns a subset of fields relevant for cargo display,
        including a ``sellable`` flag that is ``True`` when the
        discovery is not linked to a lore fragment.

        :returns: A dictionary with cargo item fields.
        :rtype: dict
        """
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "value": self.value,
            "description": self.description,
            "sellable": self.lore_fragment_id is None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Discovery":
        """Deserialize a discovery from a dictionary.

        :param d: The dictionary containing discovery data.
        :type d: dict
        :returns: A new Discovery instance.
        :rtype: Discovery
        """
        return cls(
            id=d["id"],
            category=d["category"],
            name=d["name"],
            description=d["description"],
            lore_fragment_id=d.get("lore_fragment_id"),
            value=d.get("value", 0),
            system_id=d.get("system_id", ""),
            body_id=d.get("body_id"),
        )


@dataclass
class LoreFragment:
    """Represents a narrative lore fragment discovered in the game world.

    Lore fragments belong to story arcs and are revealed through exploration
    and discovery. Each fragment has a title and narrative text.
    """

    id: str
    arc: str
    title: str
    text: str
    discovered: bool = False
    discovery_id: Optional[str] = None
    fragment_number: int = -1
    discovery_location: str = ""
    discovery_date: str = ""
    hint: str = ""

    def to_dict(self) -> dict:
        """Serialize the lore fragment to a dictionary.

        :returns: A dictionary representation of the lore fragment.
        :rtype: dict
        """
        return {
            "id": self.id,
            "arc": self.arc,
            "title": self.title,
            "text": self.text,
            "discovered": self.discovered,
            "discovery_id": self.discovery_id,
            "fragment_number": self.fragment_number,
            "discovery_location": self.discovery_location,
            "discovery_date": self.discovery_date,
            "hint": self.hint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LoreFragment":
        """Deserialize a lore fragment from a dictionary.

        :param d: The dictionary containing lore fragment data.
        :type d: dict
        :returns: A new LoreFragment instance.
        :rtype: LoreFragment
        """
        return cls(
            id=d["id"],
            arc=d["arc"],
            title=d["title"],
            text=d["text"],
            discovered=d.get("discovered", False),
            discovery_id=d.get("discovery_id"),
            fragment_number=d.get("fragment_number", -1),
            discovery_location=d.get("discovery_location", ""),
            discovery_date=d.get("discovery_date", ""),
            hint=d.get("hint", ""),
        )
