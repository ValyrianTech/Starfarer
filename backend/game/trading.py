import random
import uuid

from backend.config import UPGRADE_COSTS, UPGRADE_EFFECTS, UPGRADE_MAX_LEVELS
from backend.models.game_state import GameState
from backend.models.ship import Ship


def get_upgrade_info(ship: Ship) -> list[dict]:
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

    state.add_log("upgrade", f"Upgraded {upgrade_id} to level {current_level + 1}.")
    return True, f"Upgraded {upgrade_id} to level {current_level + 1}."


def perform_trade(state: GameState, action: str, item: str, quantity: int = 1) -> tuple[bool, str]:
    trade_prices = {
        "fuel": (30, 50),
        "food": (10, 25),
        "minerals": (40, 80),
        "technology": (60, 150),
        "artifacts": (80, 300),
        "information": (20, 100),
    }

    system = state.get_current_system()
    if not system:
        return False, "Not in a system."

    is_station = system.phenomenon in ("none", "nebula", "ancient_gate")
    if not is_station:
        return False, "No trading facilities in this system."

    rng = random.Random(state.seed + hash(system.id) + len(state.log_entries))
    price_mod = rng.uniform(0.7, 1.5)

    if action == "sell":
        for disc in state.discoveries:
            if disc.category == item or disc.name == item:
                sell_price = int(disc.value * price_mod * quantity)
                state.ship.credits += sell_price
                state.discoveries.remove(disc)
                state.add_log("trade", f"Sold {disc.name} for {sell_price} credits.")
                return True, f"Sold {disc.name} for {sell_price} credits."

    if action == "buy":
        if item == "fuel":
            amount = min(quantity, state.ship.max_fuel - state.ship.fuel)
            cost = int(amount * trade_prices.get("fuel", [30, 50])[0] * price_mod)
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.fuel += amount
            state.add_log("trade", f"Purchased {amount} fuel for {cost} credits.")
            return True, f"Purchased {amount} fuel for {cost} credits."

        if item == "repair":
            repair_amount = min(quantity * 20, state.ship.max_hull - state.ship.hull)
            cost = int(repair_amount * 2)
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.hull += repair_amount
            state.add_log("trade", f"Repaired hull by {repair_amount} for {cost} credits.")
            return True, f"Repaired hull by {repair_amount} for {cost} credits."

    return False, f"Cannot trade {item}."
