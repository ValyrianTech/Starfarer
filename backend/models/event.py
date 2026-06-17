from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Choice:
    text: str
    outcome: str


@dataclass
class Event:
    id: str
    title: str
    flavor: str
    event_type: str
    choices: list[Choice] = field(default_factory=list)
    resolved: bool = False
    chosen: Optional[int] = None
    system_id: str = ""

    def to_dict(self) -> dict:
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
