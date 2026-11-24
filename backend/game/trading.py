"""
Trading and ship upgrade system.

Provides functions for viewing available upgrades, purchasing ship
upgrades, and trading resources (fuel, repairs, selling discoveries)
at trading stations.
"""

import random

from backend.config import (
    CREW_HIRE_PRICE,
    FUEL_BASE_PRICE,
    UPGRADE_COST_SCHEDULES,
    UPGRADE_COSTS,
    UPGRADE_EFFECTS,
    UPGRADE_MAX_LEVELS,
)
from backend.models.game_state import GameState, rep_label
from backend.models.ship import Ship
from backend.models.system import StarSystem
from backend.utils import deterministic_hash


def round_half_up(x: float) -> int:
    """Round a float to the nearest integer, with .5 rounding up.

    Uses the "round half up" (or "commercial") rounding convention,
    which is not the same as Python's built-in ``round()`` (which
    rounds .5 to the nearest even integer). This function rounds
    .5 up for both positive and negative numbers.

    :param x: The number to round.
    :type x: float
    :returns: The rounded integer.
    :rtype: int
    """
    return int(x + 0.5 if x >= 0 else x - 0.5)


def upgrade_cost(upgrade_id: str, current_level: int) -> int:
    """Return the cost to purchase the next level of an upgrade.

    When the upgrade has an explicit per-level cost schedule in
    ``UPGRADE_COST_SCHEDULES`` and ``current_level`` is within range, the
    scheduled cost is used. Otherwise the cost falls back to the linear
    ``UPGRADE_COSTS[upgrade_id] * (current_level + 1)`` formula.

    :param upgrade_id: The identifier of the upgrade.
    :type upgrade_id: str
    :param current_level: The upgrade's current level (before purchase).
    :type current_level: int
    :returns: The cost in credits to advance to the next level.
    :rtype: int
    """
    schedule = UPGRADE_COST_SCHEDULES.get(upgrade_id)
    if schedule is not None and 0 <= current_level < len(schedule):
        return schedule[current_level]
    return UPGRADE_COSTS[upgrade_id] * (current_level + 1)


def get_upgrade_info(ship: Ship) -> list[dict]:
    """Get information about all available ship upgrades.

    Computes the current level, max level, cost for next level, and
    effect for each upgrade type.

    ``can_upgrade`` means "below max level" (``current_level < max_level``)
    only. It does NOT reflect whether the ship can currently afford the
    upgrade. Use ``affordable`` to check affordability and
    ``blocked_reason`` to understand why an upgrade cannot be purchased
    right now.

    :param ship: The player's ship.
    :type ship: Ship
    :returns: A list of upgrade info dictionaries with keys: id, name,
        current_level, max_level, cost, effect, can_upgrade (True when
        below max level), affordable (True when credits >= cost), and
        blocked_reason (None when purchasable right now, otherwise
        ``"max level"`` when at max level, else ``"insufficient credits"``).
    :rtype: list[dict]
    """
    info = []
    for upgrade_id in UPGRADE_COSTS:
        current_level = ship.upgrades.get(upgrade_id, 0)
        max_level = UPGRADE_MAX_LEVELS[upgrade_id]
        cost = upgrade_cost(upgrade_id, current_level)
        can_upgrade = current_level < max_level
        affordable = ship.credits >= cost
        if not can_upgrade:
            blocked_reason = "max level"
        elif not affordable:
            blocked_reason = "insufficient credits"
        else:
            blocked_reason = None
        info.append({
            "id": upgrade_id,
            "name": upgrade_id.replace("_", " ").title(),
            "current_level": current_level,
            "max_level": max_level,
            "cost": cost,
            "effect": UPGRADE_EFFECTS[upgrade_id],
            "can_upgrade": can_upgrade,
            "affordable": affordable,
            "blocked_reason": blocked_reason,
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

    cost = upgrade_cost(upgrade_id, current_level)
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

    state.add_log("upgrade", f"Upgraded {upgrade_id} to level {current_level + 1}.", category="upgrade", title="Ship Upgrade")
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


def _lore_linked_discovery_error(item: str, is_category: bool = False) -> str:
    """Return the distinct error for attempting to sell an all-lore-linked item.

    When the match was by exact name (``is_category`` is False), the message
    uses the singular form (``"... is a lore-linked discovery ..."``). When the
    match was by category (``is_category`` is True), the message uses the
    plural form and refers to the discoveries as ``"them"``.

    :param item: The discovery name or category that was requested.
    :type item: str
    :param is_category: Whether the match was by category (plural wording)
        rather than by exact name (singular wording).
    :type is_category: bool
    :returns: The lore-linked sell error message.
    :rtype: str
    """
    if is_category:
        return f"Discoveries matching '{item}' are lore-linked and cannot be sold — donate them at the Crossroads instead."
    return f"'{item}' is a lore-linked discovery and cannot be sold — donate it at the Crossroads instead."


def _unfiltered_matches(discoveries: list, item: str) -> list:
    """Find discoveries matching ``item`` by exact name, then category.

    Unlike the sellable-filtered lookup, this returns ALL matches (including
    lore-linked discoveries) so callers can distinguish "no match at all"
    from "matched but nothing is sellable".

    :param discoveries: The candidate discoveries to search.
    :type discoveries: list
    :param item: The discovery name or category to match.
    :type item: str
    :returns: The list of matching discoveries (unfiltered by sellability).
    :rtype: list
    """
    name_matches = [d for d in discoveries if d.name == item]
    if name_matches:
        return name_matches
    return [d for d in discoveries if d.category == item]


def _sellable_matches(discoveries: list, item: str) -> list:
    """Find sellable discoveries matching ``item`` by exact name, then category.

    Sellable (``lore_fragment_id is None``) exact-name matches take
    precedence; if there are none, fall back to sellable category matches.
    This preserves the original sell precedence so that a lore-linked name
    match never shadows a sellable category match.

    :param discoveries: The candidate discoveries to search.
    :type discoveries: list
    :param item: The discovery name or category to match.
    :type item: str
    :returns: The list of sellable matching discoveries.
    :rtype: list
    """
    name_matches = [d for d in discoveries if d.name == item and d.lore_fragment_id is None]
    if name_matches:
        return name_matches
    return [d for d in discoveries if d.category == item and d.lore_fragment_id is None]


def _market_price_mod(state: GameState, system: StarSystem) -> float:
    """Return the stable per-(game, station) market price modifier.

    The modifier is derived deterministically from the game seed and the
    station's system id, so it does not change as the player takes actions
    or as the game log grows. It remains fixed for the lifetime of a game
    at a given station, preventing players from re-rolling prices by
    performing other actions between trades.

    :param state: The current game state.
    :type state: GameState
    :param system: The star system where the market is located.
    :type system: StarSystem
    :returns: A price multiplier in the range ``[0.7, 1.5)``.
    :rtype: float
    """
    det_seed = deterministic_hash(state.seed, system.id, "market_v1")
    rng = random.Random(det_seed)  # nosec B311 - game RNG, not crypto
    return rng.uniform(0.7, 1.5)


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
        "ancient": (0.75, "Ancient gate premium"),
        "uncharted": (1.00, "Uncharted territory premium"),
    }
    system_modifier, system_modifier_label = system_modifiers[system.system_type]

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
    purchasing fuel, repairing the hull, or hiring crew.

    :param state: The current game state.
    :type state: GameState
    :param action: Either ``"buy"`` or ``"sell"``.
    :type action: str
    :param item: The item to trade (e.g. ``"fuel"``, ``"repair"``,
        ``"crew"``, or a discovery category/name).
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

    price_mod = _market_price_mod(state, system)

    stellar_rep = state.get_faction_reputation("stellar_cartographers")
    stellar_sell_mod = 1.0 + min(max(stellar_rep, 0), 50) / 200.0

    trade_completed = False
    result_message = ""

    if action == "sell":
        error = _validate_quantity(quantity)
        if error:
            return False, error
        if not item or not isinstance(item, str):
            return False, "Item must be a non-empty string."
        # Sellable-first lookup (sellable name matches, else sellable category
        # matches) preserving the original precedence. We only consult the
        # unfiltered set to distinguish a genuinely-absent item from a
        # lore-linked (unsellable) one.
        matching = _sellable_matches(state.discoveries, item)
        if not matching:
            unfiltered = _unfiltered_matches(state.discoveries, item)
            if unfiltered:
                is_category = not any(d.name == item for d in unfiltered)
                return False, _lore_linked_discovery_error(item, is_category)
            return False, f"No discoveries matching '{item}' to sell."
        total_price = 0
        sold_items = []
        matching.sort(key=lambda d: d.value, reverse=True)
        if quantity > len(matching):
            return False, f"Only {len(matching)} item(s) found matching '{item}', requested {quantity}."
        to_sell = matching[:quantity]
        to_sell_ids = {disc.id for disc in to_sell}
        for disc in to_sell:
            sell_price = int(disc.value * price_mod * stellar_sell_mod)
            total_price += sell_price
            sold_items.append(disc.name)
        state.discoveries = [d for d in state.discoveries if d.id not in to_sell_ids]
        state.sync_cargo()
        state.ship.credits += total_price
        result_message = f"Sold {len(sold_items)} item(s) for {total_price} credits."
        system_name = system.name
        state.add_log("trade", result_message, category="trade", title="Trade", system=system_name, credits_change=total_price)
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
            final_unit_price = price_info["final_price"] * price_mod
            cost = round_half_up(amount * final_unit_price)
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.fuel += amount
            breakdown_lines = list(price_info["breakdown_lines"])
            breakdown_lines.insert(-1, f"Market conditions: {(price_mod - 1):+.0%}")
            breakdown_lines[-1] = f"Final price: {final_unit_price:.1f} credits/unit"
            breakdown_str = "\n".join(breakdown_lines)
            result_message = f"Purchased {amount} fuel for {cost} credits.\n{breakdown_str}"
            state.add_log("trade", result_message, category="trade", title="Trade", system=system.name, credits_change=-cost, fuel_change=amount)
            trade_completed = True

        elif item == "repair":
            error = _validate_quantity(quantity)
            if error:
                return False, error
            repair_amount = min(quantity * 20, state.ship.max_hull - state.ship.hull)
            if repair_amount <= 0:
                return False, "Hull is already at maximum."
            void_rep = state.get_faction_reputation("void_traders")
            void_label = rep_label(void_rep)
            if void_label == "Allied":
                void_repair_discount = 0.85
            elif void_label == "Friendly":
                void_repair_discount = 0.95
            elif void_label in ("Unfriendly", "Hostile"):
                void_repair_discount = 1.0 + (0.15 if void_label == "Unfriendly" else 0.30)
            else:
                void_repair_discount = 1.0
            cost = int(repair_amount * 2 * void_repair_discount)
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.hull += repair_amount
            result_message = f"Repaired hull by {repair_amount} for {cost} credits."
            state.add_log("trade", result_message, category="trade", title="Trade", system=system.name, credits_change=-cost, hull_change=repair_amount)
            trade_completed = True

        elif item == "crew":
            error = _validate_quantity(quantity)
            if error:
                return False, error
            hireable = min(quantity, state.ship.max_crew - state.ship.crew)
            if hireable <= 0:
                return False, "Crew roster is already full."
            cost = hireable * CREW_HIRE_PRICE
            if state.ship.credits < cost:
                return False, f"Not enough credits. Need {cost}."
            state.ship.credits -= cost
            state.ship.crew += hireable
            result_message = f"Hired {hireable} crew for {cost} credits."
            state.add_log("trade", result_message, category="trade", title="Trade", system=system.name, credits_change=-cost)
            trade_completed = True

    if trade_completed:
        state.record_station_visit(system.id)
        # Free Pilots Guild morale bonus applied once per successful trade
        # action, not per sub-action branch, to keep the call site singular.
        _apply_free_pilots_morale_bonus(state)
        return True, result_message

    return False, f"Cannot trade {item}."


def perform_bulk_sell(state: GameState, items: list[dict]) -> tuple[bool, str, int, int, list[str]]:
    """Sell multiple discoveries in a single transaction.

    Validates that all requested items exist in the ship's discoveries.
    Items that don't exist, or for which the requested quantity exceeds
    the number available, are reported as errors and are NOT sold. An
    entry requesting more units than are available is rejected (no units
    of that entry are sold) rather than being clamped. The sale of the
    remaining valid items still proceeds (partial failure).

    :param state: The current game state.
    :type state: GameState
    :param items: A list of dicts with ``"item"`` and ``"quantity"`` keys.
    :type items: list[dict]
    :returns: A tuple of ``(success, message, sold_count, total_price, errors)``
        where ``errors`` is the structured list of per-entry error strings
        (empty when no entries failed).
    :rtype: tuple[bool, str, int, int, list[str]]
    """
    system = state.get_current_system()
    if not system:
        return False, "Not in a system.", 0, 0, []

    is_station = system.has_trading_station
    if not is_station:
        return False, "No trading facilities in this system.", 0, 0, []

    price_mod = _market_price_mod(state, system)

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
        # Sellable-first lookup (sellable name matches, else sellable category
        # matches) preserving the original precedence.
        matching = _sellable_matches(available, item_name)
        if not matching:
            unfiltered = _unfiltered_matches(available, item_name)
            if unfiltered:
                is_category = not any(d.name == item_name for d in unfiltered)
                errors.append(_lore_linked_discovery_error(item_name, is_category))
            else:
                errors.append(f"No discoveries matching '{item_name}' to sell.")
            continue

        matching.sort(key=lambda d: d.value, reverse=True)
        if quantity > len(matching):
            errors.append(f"Only {len(matching)} item(s) found matching '{item_name}', requested {quantity}.")
            continue
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
        return False, msg, 0, 0, errors

    state.discoveries = [d for d in discoveries_snapshot if d.id not in sold_ids]

    state.ship.credits += total_price
    state.sync_cargo()
    _apply_free_pilots_morale_bonus(state)

    log_msg = f"Bulk sold {sold_count} item(s) for {total_price} credits."
    if errors:
        log_msg += f" ({len(errors)} partial failure(s))"
    state.add_log("trade", log_msg, category="trade", title="Bulk Sell", system=system.name, credits_change=total_price)

    success_msg = f"Sold {sold_count} item(s) for {total_price} credits."
    if errors:
        success_msg += " " + " ".join(errors)

    return True, success_msg, sold_count, total_price, errors
