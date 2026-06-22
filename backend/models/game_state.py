"""
Core game state data model.

Defines the :class:`GameState` dataclass which holds the complete state of
a game session including the ship, star systems, events, discoveries, lore,
and log entries.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid

from backend.models.ship import Ship
from backend.models.system import StarSystem
from backend.models.event import Event
from backend.models.discovery import Discovery, LoreFragment
from backend.models.faction import FactionRelation

logger = logging.getLogger(__name__)


@dataclass
class GameState:
    """Holds the complete state of a single game session.

    This is the central data structure that ties together the ship,
    all star systems, pending events, discoveries, lore fragments,
    and the ship's log. It is persisted to SQLite on save and
    reconstructed on load.
    """

    id: str
    seed: int
    ship: Ship
    systems: dict[str, StarSystem] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    discoveries: list[Discovery] = field(default_factory=list)
    lore_fragments: list[LoreFragment] = field(default_factory=list)
    log_entries: list[dict] = field(default_factory=list)
    faction_relations: dict[str, FactionRelation] = field(default_factory=dict)
    systems_visited: int = 0
    game_started: str = ""
    last_event_title: Optional[str] = None

    def __post_init__(self) -> None:
        """Initialize the ``game_started`` timestamp if not already set.

        Sets ``game_started`` to the current UTC ISO format timestamp
        when the game state is first created.
        """
        if not self.game_started:
            self.game_started = datetime.now(timezone.utc).isoformat()

    def get_current_system(self) -> Optional[StarSystem]:
        """Retrieve the star system the ship is currently in.

        :returns: The current :class:`StarSystem`, or ``None`` if the
            system ID is not found in the systems dictionary.
        :rtype: Optional[StarSystem]
        """
        return self.systems.get(self.ship.current_system_id)

    def add_log(self, entry_type: str, message: str) -> None:
        """Append a new entry to the ship's log.

        :param entry_type: The category of the log entry (e.g.
            ``"navigation"``, ``"exploration"``, ``"event"``).
        :type entry_type: str
        :param message: The human-readable log message.
        :type message: str
        """
        self.log_entries.append({
            "id": str(uuid.uuid4())[:8],
            "type": entry_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def apply_choice_outcome(self, outcome: str) -> dict:
        """Parse an outcome string and apply its effects to the ship.

        The outcome string uses a semicolon-separated ``key:value`` format
        (e.g. ``"credits:50; fuel:-10; hull:-5"``). Stat values are clamped
        to their valid ranges after application.

        :param outcome: Semicolon-separated stat effects.
        :type outcome: str
        :returns: A dictionary mapping stat names to their applied deltas.
        :rtype: dict
        """
        effects = {"fuel": 0, "hull": 0, "morale": 0, "credits": 0, "cargo": 0, "crew": 0}
        parts = outcome.split(";")
        for part in parts:
            part = part.strip()
            if part.startswith("fuel:"):
                effects["fuel"] = int(part.split(":")[1])
            elif part.startswith("hull:"):
                effects["hull"] = int(part.split(":")[1])
            elif part.startswith("morale:"):
                effects["morale"] = int(part.split(":")[1])
            elif part.startswith("credits:"):
                effects["credits"] = int(part.split(":")[1])
            elif part.startswith("cargo:"):
                effects["cargo"] = int(part.split(":")[1])
            elif part.startswith("crew:"):
                effects["crew"] = int(part.split(":")[1])
            else:
                # Narrative text or unrecognized stat - warn so typos aren't silently ignored
                logger.warning("Unrecognized outcome part: %s", part)
        self.ship.fuel = max(0, min(self.ship.max_fuel, self.ship.fuel + effects["fuel"]))
        self.ship.hull = max(0, min(self.ship.max_hull, self.ship.hull + effects["hull"]))
        self.ship.morale = max(0, min(100, self.ship.morale + effects["morale"]))
        self.ship.credits = max(0, self.ship.credits + effects["credits"])
        self.ship.cargo = max(0, min(self.ship.max_cargo, self.ship.cargo + effects["cargo"]))
        self.ship.crew = max(0, min(self.ship.max_crew, self.ship.crew + effects["crew"]))
        return effects

    @property
    def lore_fragments_collected(self) -> int:
        """Count of lore fragments that have been discovered.

        :returns: The number of discovered lore fragments.
        :rtype: int
        """
        return sum(1 for lf in self.lore_fragments if lf.discovered)

    def state_summary(self) -> dict:
        """Generate a compact summary of the current game state.

        :returns: A dictionary with key fields including game_id, seed,
            ship stats, current system, pending events count, discovery
            count, and systems visited.
        :rtype: dict
        """
        system = self.get_current_system()
        cargo_items = [d.to_cargo_dict() for d in self.discoveries]
        return {
            "game_id": self.id,
            "seed": self.seed,
            "ship": self.ship.to_dict(),
            "current_system": system.to_dict() if system else None,
            "event_count": len([e for e in self.events if not e.resolved]),
            "discovery_count": len(self.discoveries),
            "cargo_items": cargo_items,
            "systems_visited": self.systems_visited,
            "log_count": len(self.log_entries),
            "game_started": self.game_started,
            "lore_fragments_collected": self.lore_fragments_collected,
            "lore_fragments_total": len(self.lore_fragments),
            "faction_relations": self.get_known_factions(),
        }

    def get_faction_reputation(self, faction_id: str) -> int:
        """Get the reputation value with a given faction.

        :param faction_id: The unique identifier of the faction.
        :type faction_id: str
        :returns: The reputation value, or 0 if the faction is not tracked.
        :rtype: int
        """
        if faction_id in self.faction_relations:
            return self.faction_relations[faction_id].reputation
        return 0

    def modify_faction_reputation(self, faction_id: str, delta: int) -> None:
        """Modify reputation with a faction by a given delta.

        Creates a new :class:`FactionRelation` if the faction is not yet
        tracked. Reputation has no hard cap but is clamped to -1000..1000.

        :param faction_id: The unique identifier of the faction.
        :type faction_id: str
        :param delta: The amount to adjust reputation by (positive or negative).
        :type delta: int
        """
        if faction_id not in self.faction_relations:
            self.faction_relations[faction_id] = FactionRelation(
                faction_id=faction_id, reputation=0, known=False
            )
        self.faction_relations[faction_id].reputation = max(
            -1000, min(1000, self.faction_relations[faction_id].reputation + delta)
        )

    def get_known_factions(self) -> list[dict]:
        """Get a list of all known faction relations.

        :returns: A list of dictionaries with faction relation data.
        :rtype: list[dict]
        """
        from backend.models.faction import get_faction
        result = []
        for faction_id, relation in self.faction_relations.items():
            faction = get_faction(faction_id)
            result.append({
                "faction_id": faction_id,
                "name": faction.name if faction else faction_id,
                "description": faction.description if faction else "",
                "alignment": faction.alignment if faction else "",
                "home_system_id": faction.home_system_id if faction else None,
                "reputation": relation.reputation,
                "known": relation.known,
            })
        return result

    def update_stranded_state(self) -> int:
        """Update stranded state based on current fuel level.

        If the ship has no fuel, increments ``stranded_turns`` and applies
        a cumulative morale penalty of -5 per stranded turn. If the ship
        has fuel, resets the stranded state (``stranded_turns`` to 0,
        ``distress_cooldown`` to False).

        :returns: The updated stranded_turns count.
        :rtype: int
        """
        if self.ship.fuel == 0:
            self.ship.stranded_turns += 1
            self.ship.morale = max(0, min(100, self.ship.morale - 5))
            return self.ship.stranded_turns
        else:
            self.ship.stranded_turns = 0
            self.ship.distress_cooldown = False
            return 0

    def reset_stranded_state(self) -> None:
        """Reset stranded turns and distress cooldown to their defaults."""
        self.ship.stranded_turns = 0
        self.ship.distress_cooldown = False
