from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Ship:
    name: str = "Serendipity"
    fuel: int = 80
    hull: int = 100
    cargo: int = 0
    crew: int = 4
    morale: int = 80
    credits: int = 1000
    jump_range: int = 4
    scanner: int = 1
    max_fuel: int = 100
    max_hull: int = 100
    max_cargo: int = 50
    max_crew: int = 10
    current_system_id: str = ""
    current_body_id: Optional[str] = None
    upgrades: dict = field(default_factory=lambda: {
        "hyperdrive": 0,
        "scanner": 0,
        "cargo_hold": 0,
        "hull_plating": 0,
        "fuel_tanks": 0,
        "life_support": 0,
    })

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fuel": self.fuel,
            "hull": self.hull,
            "cargo": self.cargo,
            "crew": self.crew,
            "morale": self.morale,
            "credits": self.credits,
            "jump_range": self.jump_range,
            "scanner": self.scanner,
            "max_fuel": self.max_fuel,
            "max_hull": self.max_hull,
            "max_cargo": self.max_cargo,
            "max_crew": self.max_crew,
            "current_system_id": self.current_system_id,
            "current_body_id": self.current_body_id,
            "upgrades": self.upgrades,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Ship":
        return cls(
            name=d.get("name", "Serendipity"),
            fuel=d.get("fuel", 80),
            hull=d.get("hull", 100),
            cargo=d.get("cargo", 0),
            crew=d.get("crew", 4),
            morale=d.get("morale", 80),
            credits=d.get("credits", 1000),
            jump_range=d.get("jump_range", 4),
            scanner=d.get("scanner", 1),
            max_fuel=d.get("max_fuel", 100),
            max_hull=d.get("max_hull", 100),
            max_cargo=d.get("max_cargo", 50),
            max_crew=d.get("max_crew", 10),
            current_system_id=d.get("current_system_id", ""),
            current_body_id=d.get("current_body_id"),
            upgrades=d.get("upgrades", {
                "hyperdrive": 0, "scanner": 0, "cargo_hold": 0,
                "hull_plating": 0, "fuel_tanks": 0, "life_support": 0,
            }),
        )
