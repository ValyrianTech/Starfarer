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
    systems_visited: int = 0
    game_started: str = ""

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
        return {
            "game_id": self.id,
            "seed": self.seed,
            "ship": self.ship.to_dict(),
            "current_system": system.to_dict() if system else None,
            "event_count": len([e for e in self.events if not e.resolved]),
            "discovery_count": len(self.discoveries),
            "systems_visited": self.systems_visited,
            "log_count": len(self.log_entries),
            "game_started": self.game_started,
            "lore_fragments_collected": self.lore_fragments_collected,
            "lore_fragments_total": len(self.lore_fragments),
        }
