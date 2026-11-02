"""
Data models for discoveries and lore fragments.

Defines the :class:`Discovery` and :class:`LoreFragment` dataclasses used
to represent points of interest found during exploration and the narrative
lore fragments scattered throughout the galaxy.
"""

from dataclasses import dataclass
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce a value to an integer defensively.

    Persisted save data is not guaranteed to be well-formed, so this helper
    never assumes the value is an integer. Malformed values (including
    booleans) are treated as missing and return ``default``.

    :param value: The value to coerce.
    :type value: Any
    :param default: The value to return when ``value`` is not a non-bool
        integer.
    :type default: int
    :returns: ``value`` if it is a non-bool integer, otherwise ``default``.
    :rtype: int
    """
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _safe_str(value: Any, default: str) -> str:
    """Coerce a value to a string defensively.

    Persisted save data is not guaranteed to be well-formed, so this helper
    never assumes the value is a string. Malformed values are treated as
    missing and return ``default``.

    :param value: The value to coerce.
    :type value: Any
    :param default: The value to return when ``value`` is not a string.
    :type default: str
    :returns: ``value`` if it is a string, otherwise ``default``.
    :rtype: str
    """
    return value if isinstance(value, str) else default


def _safe_str_or_none(value: Any) -> str | None:
    """Coerce a value to a string-or-None defensively.

    Persisted save data is not guaranteed to be well-formed, so this helper
    never assumes the value is a string. Malformed values are treated as
    missing and return ``None``.

    :param value: The value to coerce.
    :type value: Any
    :returns: ``value`` if it is a string, otherwise ``None``.
    :rtype: str | None
    """
    return value if isinstance(value, str) else None


def _safe_bool(value: Any, default: bool = False) -> bool:
    """Coerce a value to a boolean defensively.

    Persisted save data is not guaranteed to be well-formed, so this helper
    never assumes the value is a boolean. Malformed values are treated as
    missing and return ``default``.

    :param value: The value to coerce.
    :type value: Any
    :param default: The value to return when ``value`` is not a boolean.
    :type default: bool
    :returns: ``value`` if it is a boolean, otherwise ``default``.
    :rtype: bool
    """
    return value if isinstance(value, bool) else default


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
    lore_fragment_id: str | None = None
    value: int = 0
    system_id: str = ""
    body_id: str | None = None

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

        Fields are coerced defensively so that corrupt persisted values
        cannot propagate malformed types (e.g. a non-integer ``value``)
        into downstream aggregation code.

        :param d: The dictionary containing discovery data.
        :type d: dict
        :returns: A new Discovery instance.
        :rtype: Discovery
        """
        return cls(
            id=str(d.get("id", "")),
            category=_safe_str(d.get("category"), "unknown"),
            name=_safe_str(d.get("name"), "Unknown"),
            description=_safe_str(d.get("description"), ""),
            lore_fragment_id=_safe_str_or_none(d.get("lore_fragment_id")),
            value=_safe_int(d.get("value", 0)),
            system_id=_safe_str(d.get("system_id"), ""),
            body_id=_safe_str_or_none(d.get("body_id")),
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
    discovery_id: str | None = None
    fragment_number: int = -1
    discovery_location: str = ""
    discovery_date: str = ""
    discovery_timestamp: str = ""
    hint: str = ""
    donated: bool = False

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
            "discovery_timestamp": self.discovery_timestamp,
            "hint": self.hint,
            "donated": self.donated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LoreFragment":
        """Deserialize a lore fragment from a dictionary.

        Fields are coerced defensively so that corrupt persisted values
        cannot propagate malformed types (e.g. a non-integer
        ``fragment_number``) into downstream code.

        :param d: The dictionary containing lore fragment data.
        :type d: dict
        :returns: A new LoreFragment instance.
        :rtype: LoreFragment
        """
        return cls(
            id=str(d.get("id", "")),
            arc=_safe_str(d.get("arc"), "unknown"),
            title=_safe_str(d.get("title"), "Unknown"),
            text=_safe_str(d.get("text"), ""),
            discovered=_safe_bool(d.get("discovered", False)),
            discovery_id=_safe_str_or_none(d.get("discovery_id")),
            fragment_number=_safe_int(d.get("fragment_number", -1), -1),
            discovery_location=_safe_str(d.get("discovery_location"), ""),
            discovery_date=_safe_str(d.get("discovery_date"), ""),
            discovery_timestamp=_safe_str(d.get("discovery_timestamp"), ""),
            hint=_safe_str(d.get("hint"), ""),
            donated=_safe_bool(d.get("donated", False)),
        )
