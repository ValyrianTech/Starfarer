"""
Trading and ship upgrade system.

Provides functions for viewing available upgrades, purchasing ship
upgrades, and trading resources (fuel, repairs, selling discoveries)
at trading stations.
"""

import random

from backend.config import UPGRADE_COSTS, UPGRADE_EFFECTS, UPGRADE_MAX_LEVELS, FUEL_BASE_PRICE
from backend.utils import deterministic_hash
from backend.models.game_state import GameState, rep_label
from backend.models.ship import Ship
from backend.models.system import StarSystem


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


def _apply_free_pilots_morale_bonus(state: GameState) -> None:
    """Apply a morale bonus based on Free Pilots Guild reputation when trading.

    :param state: The current game state.
    :type state: GameState
    """
    rep = state.get_faction_reputation("free_pilots")
    bonus = min(max(rep, 0), 50) // 10
    if bonus > 0:
        state.ship.morale = min(100, state.ship.morale + bonus)


def _validate_quantity(quantity: int) -> str | None:
    """Validate that quantity is a positive integer.

    :param quantity: The quantity to validate.
    :type quantity: int
    :returns: An error message string if invalid, or None if valid.
    :rtype: str | None
    """
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return "Quantity must be a positive integer."
    return None


def calculate_fuel_price(state: GameState, system: StarSystem) -> dict:
    """Calculate fuel price at a station with a full breakdown.

    :param state: The current game state.
    :type state: GameState
    :param system: The star system where fuel is being purchased.
    :type system: StarSystem
    :returns: A dict with base_price, system_modifier, system_modifier_label,
        faction_modifier, faction_modifier_label, supply_modifier,
        supply_modifier_label, final_price, and breakdown_lines.
    :rtype: dict
    """
    from backend.models.system import validate_system_type
    validate_system_type(system.system_type)

    base_price = FUEL_BASE_PRICE

    system_modifiers = {
        "civilized": (-0.20, "Civilized system discount"),
        "agricultural": (0.0, "Standard pricing"),
        "frontier": (0.25, "Remote system premium"),
        "nebula": (0.50, "Nebula hazard premium"),
        "uncharted": (1.00, "Uncharted territory premium"),
    }
    system_modifier, system_modifier_label = system_modifiers.get(
        system.system_type, (0.0, "Standard pricing")
    )

    void_rep = state.get_faction_reputation("void_traders")
    void_label = rep_label(void_rep)
    if void_label == "Allied":
        faction_modifier = -0.15
        faction_modifier_label = "Void Traders - Allied discount"
    elif void_label == "Friendly":
        faction_modifier = -0.05
        faction_modifier_label = "Void Traders - Friendly discount"
    elif void_label in ("Unfriendly", "Hostile"):
        faction_modifier = 0.30 if void_label == "Hostile" else 0.15
        faction_modifier_label = f"Void Traders - {void_label} surcharge"
    else:
        faction_modifier = 0.0
        faction_modifier_label = "Void Traders - Neutral"

    visits = state.station_visits.get(system.id, 0)
    if visits > 0:
        supply_modifier = -0.10
        supply_modifier_label = "Well-supplied by traders"
    else:
        supply_modifier = 0.0
        supply_modifier_label = "First-time visit"

    final_price = base_price * (1 + system_modifier + faction_modifier + supply_modifier)
    unclamped = final_price
    final_price = max(final_price, base_price * 0.1, 1)
    clamped = final_price != unclamped

    breakdown_lines = [
        f"Base price: {base_price} credits/unit",
        f"System type ({system.system_type}): {system_modifier_label} ({system_modifier:+.0%})",
        f"Faction standing: {faction_modifier_label} ({faction_modifier:+.0%})",
        f"Supply/demand: {supply_modifier_label} ({supply_modifier:+.0%})",
    ]
    if clamped:
        breakdown_lines.append(f"Final price: {final_price:.1f} credits/unit (clamped to minimum)")
    else:
        breakdown_lines.append(f"Final price: {final_price:.1f} credits/unit")

    return {
        "base_price": base_price,
        "system_modifier": system_modifier,
        "system_modifier_label": system_modifier_label,
        "faction_modifier": faction_modifier,
        "faction_modifier_label": faction_modifier_label,
        "supply_modifier": supply_modifier,
        "supply_modifier_label": supply_modifier_label,
        "final_price": final_price,
        "breakdown_lines": breakdown_lines,
    }


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

    is_station = system.has_trading_station
    if not is_station:
        return False, "No trading facilities in this system."

    det_seed = deterministic_hash(state.seed, system.id, len(state.log_entries))
    rng = random.Random(det_seed)
    price_mod = rng.uniform(0.7, 1.5)

    stellar_rep = state.get_faction_reputation("stellar_cartographers")
    stellar_sell_mod = 1.0 + min(max(stellar_rep, 0), 50) / 200.0

    void_rep = state.get_faction_reputation("void_traders")
    void_buy_discount = 1.0 - min(max(void_rep, 0), 50) / 200.0

    trade_completed = False
    result_message = ""

    if action == "sell":
        error = _validate_quantity(quantity)
        if error:
            return False, error
        if not item or not isinstance(item, str):
            return False, "Item must be a non-empty string."
        # Try exact name match first
        name_matches = [d for d in state.discoveries if d.name == item]
        if name_matches:
            matching = name_matches
        else:
            # Fall back to category match
            matching = [d for d in state.discoveries if d.category == item]
        if not matching:
            return False, f"No discoveries matching '{item}' to sell."
        total_price = 0
        sold_items = []
        matching.sort(key=lambda d: d.value, reverse=True)
        if quantity > len(matching):
            return False, f"Only {len(matching)} item(s) found matching '{item}', requested {quantity}."
        to_sell = matching[:quantity]
        for disc in to_sell:
            sell_price = int(disc.value * price_mod * stellar_sell_mod)
            total_price += sell_price
            sold_items.append(disc.name)
            state.discoveries.remove(disc)
        state.ship.credits += total_price
        result_message = f"Sold {len(sold_items)} item(s) for {total_price} credits."
        state.add_log("trade", result_message)
        trade_completed = True

    elif action == "buy":
        if item == "fuel":
            error = _validate_quantity(quantity)
            if error:
                return False, error
            amount = min(quantity, state.ship.max_fuel - state.ship.fuel)
            if amount <= 0:
                return False, "Fuel tank is already full."
            price_info = calculate_fuel_price(state, system)
            cost = int(amount * price_info["final_price"])
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.fuel += amount
            breakdown_str = "\n".join(price_info["breakdown_lines"])
            result_message = f"Purchased {amount} fuel for {cost} credits.\n{breakdown_str}"
            state.add_log("trade", result_message)
            trade_completed = True

        elif item == "repair":
            error = _validate_quantity(quantity)
            if error:
                return False, error
            repair_amount = min(quantity * 20, state.ship.max_hull - state.ship.hull)
            if repair_amount <= 0:
                return False, "Hull is already at maximum."
            cost = int(repair_amount * 2 * void_buy_discount)
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.hull += repair_amount
            result_message = f"Repaired hull by {repair_amount} for {cost} credits."
            state.add_log("trade", result_message)
            trade_completed = True

    if trade_completed:
        state.record_station_visit(system.id)
        # Free Pilots Guild morale bonus applied once per successful trade
        # action, not per sub-action branch, to keep the call site singular.
        _apply_free_pilots_morale_bonus(state)
        return True, result_message

    return False, f"Cannot trade {item}."


def perform_bulk_sell(state: GameState, items: list[dict]) -> tuple[bool, str, int, int]:
    """Sell multiple discoveries in a single transaction.

    Validates that all requested items exist in the ship's discoveries.
    Items that don't exist are reported as errors, but the sale of
    available items still proceeds (partial failure).

    :param state: The current game state.
    :type state: GameState
    :param items: A list of dicts with ``"item"`` and ``"quantity"`` keys.
    :type items: list[dict]
    :returns: A tuple of ``(success, message, sold_count, total_price)``.
    :rtype: tuple[bool, str, int, int]
    """
    system = state.get_current_system()
    if not system:
        return False, "Not in a system.", 0, 0

    is_station = system.has_trading_station
    if not is_station:
        return False, "No trading facilities in this system.", 0, 0

    det_seed = deterministic_hash(state.seed, system.id, len(state.log_entries))
    rng = random.Random(det_seed)
    price_mod = rng.uniform(0.7, 1.5)

    stellar_rep = state.get_faction_reputation("stellar_cartographers")
    stellar_sell_mod = 1.0 + min(max(stellar_rep, 0), 50) / 200.0

    discoveries_snapshot = list(state.discoveries)

    sold_ids: set[str] = set()
    errors: list[str] = []
    total_price = 0
    sold_count = 0

    for item_dict in items:
        item_name = item_dict.get("item")
        quantity = item_dict.get("quantity", 1)

        if item_name is None:
            errors.append("Item entry missing required 'item' field.")
            continue

        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            errors.append(f"Invalid quantity {quantity} for '{item_name}'.")
            continue

        available = [d for d in discoveries_snapshot if d.id not in sold_ids]
        # Try exact name match first
        name_matches = [d for d in available if d.name == item_name]
        if name_matches:
            matching = name_matches
        else:
            # Fall back to category match
            matching = [d for d in available if d.category == item_name]
        if not matching:
            errors.append(f"No discoveries matching '{item_name}' to sell.")
            continue

        matching.sort(key=lambda d: d.value, reverse=True)
        if quantity > len(matching):
            errors.append(f"Only {len(matching)} item(s) found matching '{item_name}', requested {quantity}.")
            to_sell = matching
        else:
            to_sell = matching[:quantity]

        for disc in to_sell:
            sell_price = int(disc.value * price_mod * stellar_sell_mod)
            total_price += sell_price
            sold_count += 1
            sold_ids.add(disc.id)

    if sold_count == 0:
        msg = "No items could be sold."
        if errors:
            msg += " " + " ".join(errors)
        return False, msg, 0, 0

    state.discoveries = [d for d in discoveries_snapshot if d.id not in sold_ids]

    state.ship.credits += total_price
    _apply_free_pilots_morale_bonus(state)

    log_msg = f"Bulk sold {sold_count} item(s) for {total_price} credits."
    if errors:
        log_msg += f" ({len(errors)} partial failure(s))"
    state.add_log("trade", log_msg)

    success_msg = f"Sold {sold_count} item(s) for {total_price} credits."
    if errors:
        success_msg += " " + " ".join(errors)

    return True, success_msg, sold_count, total_price
