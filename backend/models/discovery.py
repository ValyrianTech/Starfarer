from dataclasses import dataclass
from typing import Optional


@dataclass
class Discovery:
    id: str
    category: str
    name: str
    description: str
    lore_fragment_id: Optional[str] = None
    value: int = 0
    system_id: str = ""
    body_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "lore_fragment_id": self.lore_fragment_id,
            "value": self.value,
            "system_id": self.system_id,
            "body_id": self.body_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Discovery":
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
    id: str
    arc: str
    title: str
    text: str
    discovered: bool = False
    discovery_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "arc": self.arc,
            "title": self.title,
            "text": self.text,
            "discovered": self.discovered,
            "discovery_id": self.discovery_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LoreFragment":
        return cls(
            id=d["id"],
            arc=d["arc"],
            title=d["title"],
            text=d["text"],
            discovered=d.get("discovered", False),
            discovery_id=d.get("discovery_id"),
        )
