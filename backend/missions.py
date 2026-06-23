"""
Tiered faction mission system for Starfarer: Echoes of the Void.

Provides mission generation, daily mission tracking, and mission
completion logic integrated with the faction reputation system.
"""

from dataclasses import dataclass
from typing import Optional

from backend.utils import deterministic_hash, seeded_random
from backend.models.faction import get_faction, FACTION_DEFINITIONS


@dataclass
class FactionMission:
    """Represents a tiered faction mission offered at a trading station.

    Each mission has a tier (1-3) dictating its difficulty, costs,
    and rewards. Missions are procedurally generated based on the
    system, faction, and player reputation.
    """

    id: str
    faction_id: str
    tier: int
    title: str
    description: str
    objective_type: str
    objective_target: str
    fuel_cost: int
    credit_cost: int
    credit_reward: int
    reputation_reward: int
    item_reward: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "faction_id": self.faction_id,
            "tier": self.tier,
            "title": self.title,
            "description": self.description,
            "objective_type": self.objective_type,
            "objective_target": self.objective_target,
            "fuel_cost": self.fuel_cost,
            "credit_cost": self.credit_cost,
            "credit_reward": self.credit_reward,
            "reputation_reward": self.reputation_reward,
            "item_reward": self.item_reward,
        }


_MISSION_TEMPLATES: dict[int, dict[str, dict]] = {
    1: {
        "courier": {
            "title_prefixes": ["Urgent", "Routine", "Standard", "Quick"],
            "title_suffixes": ["Courier Run", "Delivery", "Data Transfer", "Parcel Drop"],
            "descriptions": [
                "Deliver a secure data packet to {target}.",
                "Transport critical supplies to {target}.",
                "Carry diplomatic correspondence to {target}.",
            ],
            "objective_type": "courier",
        },
        "survey": {
            "title_prefixes": ["Preliminary", "Routine", "Standard", "Basic"],
            "title_suffixes": ["Survey", "Scan Mission", "Reconnaissance", "Mapping"],
            "descriptions": [
                "Perform a surface scan of {target} for the faction.",
                "Survey {target} for potential resources.",
                "Map the orbital approach to {target}.",
            ],
            "objective_type": "survey",
        },
    },
    2: {
        "exploration": {
            "title_prefixes": ["Deep", "Extended", "Thorough", "Advanced"],
            "title_suffixes": ["Exploration", "Expedition", "Investigation", "Voyage"],
            "descriptions": [
                "Explore uncharted regions near {target} and report findings.",
                "Investigate anomalous signals originating from {target}.",
                "Conduct a geological survey of {target}'s surface.",
            ],
            "objective_type": "exploration",
        },
        "salvage": {
            "title_prefixes": ["Recovery", "Retrieval", "Extraction", "Salvage"],
            "title_suffixes": ["Operation", "Salvage Run", "Recovery Mission", "Cleanup"],
            "descriptions": [
                "Salvage valuable wreckage from the vicinity of {target}.",
                "Recover lost cargo containers near {target}.",
                "Extract and return debris samples from {target}.",
            ],
            "objective_type": "salvage",
        },
        "patrol": {
            "title_prefixes": ["Security", "Defense", "Guard", "Sentinel"],
            "title_suffixes": ["Patrol", "Watch", "Escort", "Sweep"],
            "descriptions": [
                "Patrol the space lanes around {target} for pirate activity.",
                "Escort a faction transport vessel through {target}.",
                "Maintain security presence in the {target} sector.",
            ],
            "objective_type": "patrol",
        },
    },
    3: {
        "special_ops": {
            "title_prefixes": ["Classified", "Black", "Covert", "Shadow"],
            "title_suffixes": ["Special Operation", "Covert Op", "Strategic Mission", "Strike"],
            "descriptions": [
                "Infiltrate {target} and retrieve classified faction intelligence.",
                "Deploy a stealth beacon at {target} for faction monitoring.",
                "Neutralize a threat to faction operations at {target}.",
            ],
            "objective_type": "special_ops",
        },
        "diplomatic": {
            "title_prefixes": ["High-Priority", "Critical", "Sensitive", "Urgent"],
            "title_suffixes": ["Diplomatic Mission", "Negotiation", "Summit", "Treaty"],
            "descriptions": [
                "Represent the faction at a diplomatic summit at {target}.",
                "Deliver sensitive negotiation terms to contacts at {target}.",
                "Secure a trade agreement with authorities at {target}.",
            ],
            "objective_type": "diplomatic",
        },
    },
}

_TIER_COSTS: dict[int, dict] = {
    1: {
        "fuel_cost": 3,
        "credit_cost": 10,
        "credit_reward_min": 50,
        "credit_reward_max": 100,
        "reputation_reward_min": 5,
        "reputation_reward_max": 10,
        "rep_required": 0,
    },
    2: {
        "fuel_cost": 6,
        "credit_cost": 25,
        "credit_reward_min": 150,
        "credit_reward_max": 300,
        "reputation_reward_min": 10,
        "reputation_reward_max": 15,
        "rep_required": 15,
    },
    3: {
        "fuel_cost": 10,
        "credit_cost": 50,
        "credit_reward_min": 400,
        "credit_reward_max": 800,
        "reputation_reward_min": 20,
        "reputation_reward_max": 30,
        "rep_required": 30,
    },
}


def _mission_seed(seed: int, system_id: str, faction_id: str) -> int:
    return deterministic_hash(seed, system_id, faction_id, "missions_v2")


def get_daily_mission_key(state, system_id: str) -> str:
    """Return a key string for the daily mission slot in a system.

    The key combines the system ID with a date derived from the
    number of systems visited, so daily missions refresh over time
    as the player explores new systems.

    :param state: The current game state.
    :type state: GameState
    :param system_id: The unique identifier of the star system.
    :type system_id: str
    :returns: A string key like ``"sys_01:5"``.
    :rtype: str
    """
    date_key = str(state.systems_visited // 3)
    return f"{system_id}:{date_key}"


def generate_missions(state, system, faction_id: str) -> list[FactionMission]:
    """Generate 2-3 tiered missions for a faction at a given system.

    Mission generation is deterministic based on seed, system, and
    faction. The available tiers depend on the player's reputation
    with the faction. A free daily mission is included if the
    system has not had its daily mission used on the current date.

    :param state: The current game state.
    :type state: GameState
    :param system: The star system offering missions.
    :type system: StarSystem
    :param faction_id: The faction offering missions.
    :type faction_id: str
    :returns: A list of generated :class:`FactionMission` objects.
    :rtype: list[FactionMission]
    """
    faction = get_faction(faction_id)
    if not faction:
        return []

    if not system.has_trading_station:
        return []

    rep = state.get_faction_reputation(faction_id)
    rng = seeded_random(_mission_seed(state.seed, system.id, faction_id), "generate")

    available_tiers = []
    for tier in [1, 2, 3]:
        if rep >= _TIER_COSTS[tier]["rep_required"]:
            available_tiers.append(tier)

    if not available_tiers:
        available_tiers = [1]

    num_missions = rng.randint(2, 3)
    missions = []

    for i in range(num_missions):
        tier = rng.choice(available_tiers)
        tier_templates = _MISSION_TEMPLATES[tier]
        mission_type_key = rng.choice(list(tier_templates.keys()))
        template = tier_templates[mission_type_key]

        prefix = rng.choice(template["title_prefixes"])
        suffix = rng.choice(template["title_suffixes"])
        title = f"{prefix} {suffix}"

        desc_template = rng.choice(template["descriptions"])

        if system.bodies:
            target_body = rng.choice(system.bodies)
            target_name = target_body.name
        else:
            target_name = f"deep space near {system.name}"

        description = desc_template.format(target=target_name)

        costs = _TIER_COSTS[tier]
        credit_reward = rng.randint(costs["credit_reward_min"], costs["credit_reward_max"])
        rep_reward = rng.randint(costs["reputation_reward_min"], costs["reputation_reward_max"])

        mission_id_num = deterministic_hash(
            state.seed, system.id, faction_id, "mission", str(i), str(tier)
        )
        mission_id = f"mission_{system.id}_{abs(mission_id_num) % 100000:05d}"

        missions.append(FactionMission(
            id=mission_id,
            faction_id=faction_id,
            tier=tier,
            title=title,
            description=description,
            objective_type=template["objective_type"],
            objective_target=target_name,
            fuel_cost=costs["fuel_cost"],
            credit_cost=costs["credit_cost"],
            credit_reward=credit_reward,
            reputation_reward=rep_reward,
        ))

    daily_key = get_daily_mission_key(state, system.id)
    date_part = daily_key.split(":", 1)[1] if ":" in daily_key else daily_key
    current_date_for_system = state.daily_missions_used.get(system.id)

    if current_date_for_system is None or current_date_for_system != date_part:
        free_mission = FactionMission(
            id=f"mission_daily_{system.id}",
            faction_id=faction_id,
            tier=1,
            title="Daily Opportunity",
            description=(
                f"A limited-time faction opportunity at {system.name}. "
                f"No fuel or credit cost to undertake."
            ),
            objective_type="daily",
            objective_target=system.id,
            fuel_cost=0,
            credit_cost=0,
            credit_reward=rng.randint(25, 75),
            reputation_reward=rng.randint(5, 10),
        )
        missions.append(free_mission)

    return missions


def complete_mission(state, mission: FactionMission) -> dict:
    """Apply mission rewards to the game state and record completion.

    Fuel and credit costs are deducted at completion time. Credits
    and reputation rewards are applied. The mission is added to
    ``completed_missions``. Daily missions update the
    ``daily_missions_used`` tracker.

    :param state: The current game state.
    :type state: GameState
    :param mission: The mission being completed.
    :type mission: FactionMission
    :returns: A dictionary with result details including credit and
        reputation rewards.
    :rtype: dict
    """
    state.ship.fuel -= mission.fuel_cost
    state.ship.credits -= mission.credit_cost

    state.ship.credits += mission.credit_reward
    state.modify_faction_reputation(mission.faction_id, mission.reputation_reward)

    faction = get_faction(mission.faction_id)
    faction_name = faction.name if faction else mission.faction_id

    state.add_log(
        "faction",
        f"Completed mission '{mission.title}' for {faction_name}. "
        f"Earned {mission.credit_reward} credits and {mission.reputation_reward} reputation."
    )

    state.completed_missions.append({
        "mission_id": mission.id,
        "faction_id": mission.faction_id,
        "title": mission.title,
        "tier": mission.tier,
    })

    state.accepted_missions.pop(mission.id, None)

    if mission.objective_type == "daily":
        daily_key = get_daily_mission_key(state, mission.objective_target)
        date_part = daily_key.split(":", 1)[1] if ":" in daily_key else daily_key
        state.daily_missions_used[mission.objective_target] = date_part

    return {
        "mission_id": mission.id,
        "title": mission.title,
        "faction_id": mission.faction_id,
        "credit_reward": mission.credit_reward,
        "reputation_reward": mission.reputation_reward,
        "new_reputation": state.get_faction_reputation(mission.faction_id),
    }
