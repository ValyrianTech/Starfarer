"""
Data models for in-game events and their choices.

Defines the :class:`Choice` and :class:`Event` dataclasses used to
represent procedural events that occur during exploration and the
player's response options.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Choice:
    """Represents a single choice within an event.

    Each choice has descriptive text and an outcome string that encodes
    the effects of selecting it (e.g. ``"credits:50; fuel:-10"``).
    """

    text: str
    outcome: str


@dataclass
class Event:
    """Represents a procedural in-game event with multiple outcomes.

    Events are triggered during jumps, scans, and exploration. They present
    the player with a flavor description and a set of choices, each
    associated with stat-modifying outcomes.
    """

    id: str
    title: str
    flavor: str
    event_type: str
    choices: list[Choice] = field(default_factory=list)
    resolved: bool = False
    chosen: Optional[int] = None
    system_id: str = ""

    def to_dict(self) -> dict:
        """Serialize the event to a dictionary.

        :returns: A dictionary representation of the event.
        :rtype: dict
        """
        return {
            "id": self.id,
            "title": self.title,
            "flavor": self.flavor,
            "event_type": self.event_type,
            "choices": [{"text": c.text, "outcome": c.outcome} for c in self.choices],
            "resolved": self.resolved,
            "chosen": self.chosen,
            "system_id": self.system_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        """Deserialize an event from a dictionary.

        :param d: The dictionary containing event data.
        :type d: dict
        :returns: A new Event instance.
        :rtype: Event
        """
        choices = [Choice(text=c["text"], outcome=c["outcome"]) for c in d.get("choices", [])]
        return cls(
            id=d["id"],
            title=d["title"],
            flavor=d["flavor"],
            event_type=d["event_type"],
            choices=choices,
            resolved=d.get("resolved", False),
            chosen=d.get("chosen"),
            system_id=d.get("system_id", ""),
        )
