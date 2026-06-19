"""
Trading and ship upgrade system.

Provides functions for viewing available upgrades, purchasing ship
upgrades, and trading resources (fuel, repairs, selling discoveries)
at trading stations.
"""

import hashlib
import random

from backend.config import UPGRADE_COSTS, UPGRADE_EFFECTS, UPGRADE_MAX_LEVELS
from backend.models.game_state import GameState
from backend.models.ship import Ship


def get_upgrade_info(ship: Ship) -> list[dict]:
    """Get information about all available ship upgrades.

    Computes the current level, max level, cost for next level, and
    effect for each upgrade type.

    :param ship: The player's ship.
    :type ship: Ship
    :returns: A list of upgrade info dictionaries with keys: id, name,
        current_level, max_level, cost, effect, and can_upgrade.
    :rtype: list[dict]
    """
    info = []
    for upgrade_id, cost in UPGRADE_COSTS.items():
        current_level = ship.upgrades.get(upgrade_id, 0)
        max_level = UPGRADE_MAX_LEVELS[upgrade_id]
        info.append({
            "id": upgrade_id,
            "name": upgrade_id.replace("_", " ").title(),
            "current_level": current_level,
            "max_level": max_level,
            "cost": cost * (current_level + 1),
            "effect": UPGRADE_EFFECTS[upgrade_id],
            "can_upgrade": current_level < max_level,
        })
    return info


def purchase_upgrade(state: GameState, upgrade_id: str) -> tuple[bool, str]:
    """Purchase a ship upgrade if the ship has sufficient credits.

    Validates that the upgrade exists, is not already at max level,
    and that the ship has enough credits. Applies the upgrade effect
    to the ship's stats and logs the purchase.

    :param state: The current game state.
    :type state: GameState
    :param upgrade_id: The identifier of the upgrade to purchase
        (e.g. ``"hyperdrive"``, ``"scanner"``).
    :type upgrade_id: str
    :returns: A tuple of ``(success, message)``.
    :rtype: tuple[bool, str]
    """
    if upgrade_id not in UPGRADE_COSTS:
        return False, f"Unknown upgrade: {upgrade_id}"

    ship = state.ship
    current_level = ship.upgrades.get(upgrade_id, 0)
    max_level = UPGRADE_MAX_LEVELS[upgrade_id]

    if current_level >= max_level:
        return False, f"{upgrade_id} is already at maximum level."

    cost = UPGRADE_COSTS[upgrade_id] * (current_level + 1)
    if ship.credits < cost:
        return False, f"Not enough credits. Need {cost}, have {ship.credits}."

    ship.credits -= cost
    ship.upgrades[upgrade_id] = current_level + 1

    effect = UPGRADE_EFFECTS[upgrade_id]
    if "jump_range" in effect:
        ship.jump_range += effect["jump_range"]
    if "scanner" in effect:
        ship.scanner += effect["scanner"]
    if "max_cargo" in effect:
        ship.max_cargo += effect["max_cargo"]
    if "max_hull" in effect:
        ship.max_hull += effect["max_hull"]
    if "max_fuel" in effect:
        ship.max_fuel += effect["max_fuel"]
    if "morale_decay_reduction" in effect:
        ship.morale_decay_reduction += effect["morale_decay_reduction"]

    state.add_log("upgrade", f"Upgraded {upgrade_id} to level {current_level + 1}.")
    return True, f"Upgraded {upgrade_id} to level {current_level + 1}."


def perform_trade(state: GameState, action: str, item: str, quantity: int = 1) -> tuple[bool, str]:
    """Perform a buy or sell trade action at the current system.

    Selling finds a matching discovery in the inventory and sells it
    at a market price modified by the system seed. Buying supports
    purchasing fuel or repairing the hull.

    :param state: The current game state.
    :type state: GameState
    :param action: Either ``"buy"`` or ``"sell"``.
    :type action: str
    :param item: The item to trade (e.g. ``"fuel"``, ``"repair"``,
        or a discovery category/name).
    :type item: str
    :param quantity: The quantity to buy or the multiplier for
        repairs.
    :type quantity: int
    :returns: A tuple of ``(success, message)``.
    :rtype: tuple[bool, str]
    """
    system = state.get_current_system()
    if not system:
        return False, "Not in a system."

    is_station = system.phenomenon in ("none", "nebula", "ancient_gate")
    if not is_station:
        return False, "No trading facilities in this system."

    seed_str = str(state.seed) + system.id + str(len(state.log_entries))
    det_seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    rng = random.Random(det_seed)
    price_mod = rng.uniform(0.7, 1.5)

    if action == "sell":
        matching = [d for d in state.discoveries if d.category == item or d.name == item]
        if not matching:
            return False, f"No discoveries matching '{item}' to sell."
        disc = max(matching, key=lambda d: d.value)
        sell_price = int(disc.value * price_mod)
        state.ship.credits += sell_price
        state.discoveries.remove(disc)
        state.add_log("trade", f"Sold {disc.name} for {sell_price} credits.")
        return True, f"Sold {disc.name} for {sell_price} credits."

    FUEL_BASE_PRICE = 30

    if action == "buy":
        if item == "fuel":
            if quantity <= 0:
                return False, "Quantity must be positive."
            amount = min(quantity, state.ship.max_fuel - state.ship.fuel)
            cost = int(amount * FUEL_BASE_PRICE * price_mod)
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.fuel += amount
            state.add_log("trade", f"Purchased {amount} fuel for {cost} credits.")
            return True, f"Purchased {amount} fuel for {cost} credits."

        if item == "repair":
            if quantity <= 0:
                return False, "Quantity must be positive."
            repair_amount = min(quantity * 20, state.ship.max_hull - state.ship.hull)
            cost = int(repair_amount * 2)
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.hull += repair_amount
            state.add_log("trade", f"Repaired hull by {repair_amount} for {cost} credits.")
            return True, f"Repaired hull by {repair_amount} for {cost} credits."

    return False, f"Cannot trade {item}."
