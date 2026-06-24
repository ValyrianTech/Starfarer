"""
Fuel warning status system for Starfarer.

Provides a helper that evaluates the player's current fuel level
relative to the nearest trading station and returns a warning
level and supporting information.
"""

from backend.generation.universe import distance_between
from backend.config import JUMP_FUEL_COST_PER_LY


def get_fuel_status(game_state, systems) -> dict:
    """Evaluate fuel status relative to the nearest trading station.

    :param game_state: The current GameState instance.
    :type game_state: GameState
    :param systems: Dictionary of system ID to StarSystem.
    :type systems: dict[str, StarSystem]
    :returns: A dict with level, message, current_fuel,
        fuel_for_round_trip, fuel_for_one_way, nearest_station_system,
        and nearest_station_distance.
    :rtype: dict
    """
    current_system = game_state.get_current_system()
    current_system_id = game_state.ship.current_system_id
    current_fuel = game_state.ship.fuel

    nearest_system = None
    nearest_distance = float("inf")

    if current_system:
        for sys_id, sys_data in systems.items():
            if sys_id == current_system_id and current_system.has_trading_station:
                continue
            if not sys_data.has_trading_station:
                continue
            dist = distance_between(current_system, sys_data)
            if dist < nearest_distance:
                nearest_distance = dist
                nearest_system = sys_data

    if nearest_system is None:
        if current_system and current_system.has_trading_station:
            return {
                "level": "green",
                "message": "",
                "current_fuel": current_fuel,
                "fuel_for_round_trip": 0,
                "fuel_for_one_way": 0,
                "nearest_station_system": current_system.name,
                "nearest_station_distance": 0.0,
            }
        return {
            "level": "unknown",
            "message": "No trading stations in known space",
            "current_fuel": current_fuel,
            "fuel_for_round_trip": 0,
            "fuel_for_one_way": 0,
            "nearest_station_system": None,
            "nearest_station_distance": 0.0,
        }

    distance_ly = nearest_distance / 10.0
    fuel_for_one_way = max(1, int(distance_ly * JUMP_FUEL_COST_PER_LY))
    fuel_for_round_trip = max(1, int(distance_ly * JUMP_FUEL_COST_PER_LY * 2))

    if current_fuel < 5:
        level = "critical"
        message = "CRITICAL: Fuel reserves nearly depleted"
    elif current_fuel < fuel_for_one_way:
        level = "red"
        message = "DANGER: Insufficient fuel to reach nearest station"
    elif current_fuel < fuel_for_round_trip:
        level = "yellow"
        message = "Warning: Insufficient fuel for round trip to nearest station"
    else:
        level = "green"
        message = ""

    return {
        "level": level,
        "message": message,
        "current_fuel": current_fuel,
        "fuel_for_round_trip": fuel_for_round_trip,
        "fuel_for_one_way": fuel_for_one_way,
        "nearest_station_system": nearest_system.name,
        "nearest_station_distance": round(nearest_distance / 10.0, 1),
    }
