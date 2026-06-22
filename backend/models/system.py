"""
Data models for star systems and celestial bodies.

Defines the :class:`Body` and :class:`StarSystem` dataclasses used to
represent planets, moons, asteroid belts, and their parent star systems
within the procedurally generated galaxy.
"""

from dataclasses import dataclass, field

VALID_SYSTEM_TYPES = frozenset({
    "civilized",
    "agricultural",
    "frontier",
    "nebula",
    "uncharted",
    "ancient",
})


def validate_system_type(system_type: str) -> None:
    """Validate that a system_type is one of the recognized values.

    :param system_type: The system type string to validate.
    :type system_type: str
    :raises ValueError: If the system_type is not in VALID_SYSTEM_TYPES.
    """
    if system_type not in VALID_SYSTEM_TYPES:
        raise ValueError(
            f"Unknown system_type: '{system_type}'. "
            f"Valid types: {', '.join(sorted(VALID_SYSTEM_TYPES))}"
        )


@dataclass
class Body:
    """Represents a celestial body (planet, moon, or asteroid belt).

    Each body has a type, biome, size, distance from its star, a
    descriptive text, a count of points of interest, and an exploration
    flag.
    """

    id: str
    name: str
    body_type: str
    biome: str
    size: int
    distance_from_star: float
    description: str = ""
    poi_count: int = 0
    explored: bool = False

    def to_dict(self) -> dict:
        """Serialize the body to a dictionary.

        :returns: A dictionary representation of the body.
        :rtype: dict
        """
        return {
            "id": self.id,
            "name": self.name,
            "body_type": self.body_type,
            "biome": self.biome,
            "size": self.size,
            "distance_from_star": self.distance_from_star,
            "description": self.description,
            "poi_count": self.poi_count,
            "explored": self.explored,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Body":
        """Deserialize a body from a dictionary.

        :param d: The dictionary containing body data.
        :type d: dict
        :returns: A new Body instance.
        :rtype: Body
        """
        return cls(
            id=d["id"],
            name=d["name"],
            body_type=d["body_type"],
            biome=d["biome"],
            size=d["size"],
            distance_from_star=d["distance_from_star"],
            description=d.get("description", ""),
            poi_count=d.get("poi_count", 0),
            explored=d.get("explored", False),
        )


@dataclass
class StarSystem:
    """Represents a star system in the procedurally generated galaxy.

    Each system has a position in galaxy space, a spectral type with
    associated color, an optional phenomenon (nebula, pulsar, etc.),
    and a list of orbiting celestial bodies.
    """

    id: str
    name: str
    x: float
    y: float
    star_type: str
    star_color: str
    phenomenon: str
    phenomenon_desc: str
    has_trading_station: bool = False
    bodies: list[Body] = field(default_factory=list)
    visited: bool = False
    scanned: bool = False
    system_type: str = "civilized"

    def to_dict(self) -> dict:
        """Serialize the star system to a dictionary.

        :returns: A dictionary representation of the star system.
        :rtype: dict
        """
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "star_type": self.star_type,
            "star_color": self.star_color,
            "phenomenon": self.phenomenon,
            "phenomenon_desc": self.phenomenon_desc,
            "has_trading_station": self.has_trading_station,
            "bodies": [b.to_dict() for b in self.bodies],
            "visited": self.visited,
            "scanned": self.scanned,
            "system_type": self.system_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StarSystem":
        """Deserialize a star system from a dictionary.

        :param d: The dictionary containing star system data.
        :type d: dict
        :returns: A new StarSystem instance.
        :rtype: StarSystem
        """
        return cls(
            id=d["id"],
            name=d["name"],
            x=d["x"],
            y=d["y"],
            star_type=d["star_type"],
            star_color=d["star_color"],
            phenomenon=d["phenomenon"],
            phenomenon_desc=d["phenomenon_desc"],
            has_trading_station=d.get("has_trading_station", False),
            bodies=[Body.from_dict(b) for b in d.get("bodies", [])],
            visited=d.get("visited", False),
            scanned=d.get("scanned", False),
            system_type=d.get("system_type", "civilized"),
        )
