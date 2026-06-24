"""Contextual hint system for Starfarer.

Provides real-time, contextual hints to help new players discover
survival mechanics (emergency crafting, distress beacon, salvage, etc.)
without intrusive tutorials.
"""

from __future__ import annotations
from typing import Callable

from backend.fuel import get_fuel_status
from backend.models.game_state import GameState
from backend.models.system import StarSystem


# ---------------------------------------------------------------------------
# Hint definition structure
# ---------------------------------------------------------------------------

class Hint:
    """A single contextual hint."""

    __slots__ = ("id", "severity", "message_template", "command", "condition", "priority")

    def __init__(
        self,
        hint_id: str,
        severity: str,
        message_template: str,
        condition: Callable[[GameState, dict[str, StarSystem]], bool],
        command: str | None = None,
        priority: int = 0,
    ) -> None:
        """Initialize a Hint instance.

        :param hint_id: Unique identifier for this hint.
        :type hint_id: str
        :param severity: Severity level (e.g. 'critical', 'warning', 'info', 'tip').
        :type severity: str
        :param message_template: Template string for the hint message, may contain placeholders.
        :type message_template: str
        :param condition: Callable that takes (GameState, dict[str, StarSystem]) and returns True if the hint should be shown.
        :type condition: Callable[[GameState, dict[str, StarSystem]], bool]
        :param command: Optional slash command associated with the hint.
        :type command: str | None
        :param priority: Priority value for ordering hints (higher = more important).
        :type priority: int
        """
        self.id = hint_id
        self.severity = severity
        self.message_template = message_template
        self.condition = condition
        self.command = command
        self.priority = priority

    def evaluate(self, game_state: GameState, systems: dict[str, StarSystem]) -> dict | None:
        """Evaluate this hint's condition and return a hint dict if triggered."""
        if self.condition(game_state, systems):
            return {
                "id": self.id,
                "severity": self.severity,
                "message": self.message_template,
                "command": self.command,
            }
        return None


# ---------------------------------------------------------------------------
# Condition functions
# ---------------------------------------------------------------------------

def _fuel_zero(game_state: GameState, systems: dict[str, StarSystem]) -> bool:
    """Fuel is exactly 0."""
    return game_state.ship.fuel == 0


def _fuel_critical(game_state: GameState, systems: dict[str, StarSystem]) -> bool:
    """Fuel is between 1 and 4 (low but not zero)."""
    return 1 <= game_state.ship.fuel < 5


def _fuel_low_no_station(game_state: GameState, systems: dict[str, StarSystem]) -> bool:
    """Fuel < 10 (but > 0) and current system has no trading station."""
    if game_state.ship.fuel >= 10:
        return False
    if game_state.ship.fuel <= 0:
        return False  # Can't move, so don't suggest heading to a station
    current = game_state.get_current_system()
    if current is None:
        return False
    if current.has_trading_station:
        return False
    return True


def _first_uncharted(game_state: GameState, systems: dict[str, StarSystem]) -> bool:
    """First time entering an uncharted (no station) system."""
    current = game_state.get_current_system()
    if current is None:
        return False
    if current.has_trading_station:
        return False
    if current.visited:
        return False
    # Standard case: first jump from starting system to uncharted
    if game_state.systems_visited == 2:
        return True
    # Fallback: player has visited at least one station, and no uncharted
    # system has been visited yet (covers edge case where starting system
    # has no station, so the player visits a station first, then enters
    # an uncharted system with systems_visited > 2)
    has_visited_station = any(s.visited and s.has_trading_station for s in systems.values())
    if has_visited_station:
        visited_uncharted = any(s.visited and not s.has_trading_station for s in systems.values())
        if not visited_uncharted:
            return True
    return False


def _hull_low(game_state: GameState, systems: dict[str, StarSystem]) -> bool:
    """Hull integrity below 25%."""
    return game_state.ship.hull < 25


def _cargo_full(game_state: GameState, systems: dict[str, StarSystem]) -> bool:
    """Cargo bay > 80% full."""
    if game_state.ship.max_cargo == 0:
        return False
    return (game_state.ship.cargo / game_state.ship.max_cargo) > 0.8


def _first_crisis(game_state: GameState, systems: dict[str, StarSystem]) -> bool:
    """First crisis event encountered."""
    for entry in game_state.log_entries:
        if entry.get("category") == "crisis":
            return False
    for event in game_state.events:
        if event.event_type == "crisis":
            if not event.resolved:
                return True
    return False


def _morale_low(game_state: GameState, systems: dict[str, StarSystem]) -> bool:
    """Crew morale below 30."""
    return game_state.ship.morale < 30


# ---------------------------------------------------------------------------
# Hint definitions — ordered by priority (highest first)
# ---------------------------------------------------------------------------

HINT_DEFINITIONS: list[Hint] = [
    Hint(
        hint_id="fuel_zero",
        severity="critical",
        message_template="You're stranded! Use the distress beacon to call for help, or try emergency crafting to convert hull into fuel.",
        condition=_fuel_zero,
        command="/distress",
        priority=100,
    ),
    Hint(
        hint_id="fuel_critical",
        severity="warning",
        message_template="Fuel critically low. If stranded, remember you can craft emergency fuel from hull plating.",
        condition=_fuel_critical,
        command="/emergency-craft",
        priority=90,
    ),
    Hint(
        hint_id="fuel_low_no_station",
        severity="warning",
        message_template="Consider heading to a station for refueling. Nearest station: {nearest_station} ({distance} LY)",
        condition=_fuel_low_no_station,
        command=None,
        priority=50,
    ),
    Hint(
        hint_id="hull_low",
        severity="warning",
        message_template="Hull integrity low. Visit a trading station for repairs, or use credits to patch at the nearest station.",
        condition=_hull_low,
        command=None,
        priority=40,
    ),
    Hint(
        hint_id="morale_low",
        severity="warning",
        message_template="Crew morale is low. Low morale can affect event outcomes. Visit a station with amenities to boost morale.",
        condition=_morale_low,
        command=None,
        priority=30,
    ),
    Hint(
        hint_id="first_uncharted",
        severity="info",
        message_template="Uncharted systems have no trading stations. Ensure you have enough fuel for the return journey.",
        condition=_first_uncharted,
        command=None,
        priority=20,
    ),
    Hint(
        hint_id="cargo_full",
        severity="info",
        message_template="Cargo bay nearly full. Consider selling discoveries at the nearest trading station.",
        condition=_cargo_full,
        command=None,
        priority=10,
    ),
    Hint(
        hint_id="first_crisis",
        severity="tip",
        message_template="Crisis events require immediate action. Each choice has different costs — choose wisely.",
        condition=_first_crisis,
        command=None,
        priority=5,
    ),
]


def _format_message(template: str, game_state: GameState, systems: dict[str, StarSystem]) -> str:
    """Format a hint message template with dynamic values.

    Substitutes ``{nearest_station}`` and ``{distance}`` placeholders in the
    template string using the current fuel status information. If the template
    contains neither placeholder, it is returned unchanged.

    :param template: The hint message template string, which may contain
        ``{nearest_station}`` and/or ``{distance}`` format placeholders.
    :type template: str
    :param game_state: The current game state.
    :type game_state: GameState
    :param systems: Dictionary of all star systems, keyed by system name.
    :type systems: dict[str, StarSystem]
    :returns: The formatted message string with placeholders replaced.
    :rtype: str
    """
    if "{nearest_station}" in template or "{distance}" in template:
        fuel_status = get_fuel_status(game_state, systems)
        nearest = fuel_status.get("nearest_station_system")
        if nearest is None:
            nearest = "Unknown"
        distance = fuel_status.get("nearest_station_distance", 0.0)
        return template.format(nearest_station=nearest, distance=distance)
    return template


def get_contextual_hints(
    game_state: GameState,
    systems: dict[str, StarSystem],
    dismissed_hints: set[str] | None = None,
) -> list[dict]:
    """Evaluate all hint conditions and return active hints.

    Hints are returned in priority order. At most 2 hints are returned.
    Critical hints (fuel = 0) are always included and cannot be dismissed.

    :param game_state: The current game state.
    :param systems: Dictionary of all star systems.
    :param dismissed_hints: Set of hint IDs that the player has dismissed.
    :returns: A list of hint dicts with id, severity, message, and command.
    :rtype: list[dict]
    """
    if dismissed_hints is None:
        dismissed_hints = set()

    active_hints: list[dict] = []
    for hint_def in HINT_DEFINITIONS:
        result = hint_def.evaluate(game_state, systems)
        if result is None:
            continue

        if result["severity"] == "critical" or result["id"] not in dismissed_hints:
            result["message"] = _format_message(result["message"], game_state, systems)
            active_hints.append(result)

        if len(active_hints) >= 2:
            break

    return active_hints
