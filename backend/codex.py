"""Biome Discovery Codex — in-game knowledge about biomes and their discoveries."""

from __future__ import annotations
from typing import Optional
from backend.models.game_state import GameState

BIOME_CODEX_DATA = [
    {
        "biome_id": "ocean",
        "name": "Ocean",
        "description": "Vast water worlds with deep, unexplored trenches.",
        "value_rating": 5,
        "tier1_hint": "Ocean worlds: High potential for rare discoveries",
        "common_discoveries": ["Alien Devices", "Submerged Ruins", "Organic Compounds"],
    },
    {
        "biome_id": "jungle",
        "name": "Jungle",
        "description": "Dense, teeming with alien life.",
        "value_rating": 5,
        "tier1_hint": "Jungle worlds are teeming with life",
        "common_discoveries": ["Lifeforms", "Organic Compounds", "Ancient Temples"],
    },
    {
        "biome_id": "crystal",
        "name": "Crystal",
        "description": "Shimmering landscapes of mineral formations.",
        "value_rating": 4,
        "tier1_hint": "Crystal formations often hide valuable artifacts",
        "common_discoveries": ["Plasmic Crystals", "Memory Cores", "Glyph Tablets"],
    },
    {
        "biome_id": "volcanic",
        "name": "Volcanic",
        "description": "Molten rivers and unstable terrain.",
        "value_rating": 4,
        "tier1_hint": "Volcanic worlds hold rare minerals and alien technology",
        "common_discoveries": ["Obsidian Shards", "Stellar Fragments", "Alien Devices"],
    },
    {
        "biome_id": "desert",
        "name": "Desert",
        "description": "Arid, windswept plains of sand and rock.",
        "value_rating": 3,
        "tier1_hint": "Desert worlds hold ancient ruins beneath the sands",
        "common_discoveries": ["Ancient Relics", "Glyph Tablets", "Void Ore"],
    },
    {
        "biome_id": "tundra",
        "name": "Tundra",
        "description": "Frozen wastelands with subsurface oceans.",
        "value_rating": 2,
        "tier1_hint": "Tundra worlds preserve ancient secrets in the ice",
        "common_discoveries": ["Memory Cores", "Frozen Relics", "Subsurface Samples"],
    },
    {
        "biome_id": "barren",
        "name": "Barren",
        "description": "Lifeless rock with little of value.",
        "value_rating": 1,
        "tier1_hint": "Barren worlds are quick to survey but yield little",
        "common_discoveries": ["Void Ore", "Nebula Dust", "Stellar Fragments"],
    },
    {
        "biome_id": "gas_giant",
        "name": "Gas Giant",
        "description": "Massive gaseous planets with stormy atmospheres.",
        "value_rating": 2,
        "tier1_hint": "Gas giants are dangerous but may hide unique discoveries",
        "common_discoveries": ["Plasma Jelly", "Subspace Ripples", "Void Spores"],
    },
]


def get_codex(state: GameState) -> list[dict]:
    """Build the player's current codex based on scanner level and visited biomes.

    Tier 1 (scanner >= 0): Biome names, descriptions, and general hints.
    Tier 2 (scanner >= 1): Value ratings (star ratings 1-5).
    Tier 3 (scanner >= 2): Specific discovery types per biome.

    A biome is 'unlocked' if the player has visited it (tracked in state.biomes_visited).
    If a biome hasn't been visited yet, it's still shown but marked as not unlocked.

    :param state: The current game state.
    :returns: List of biome entry dicts.
    """
    scanner_level = state.ship.scanner
    codex_entries = []

    for biome in BIOME_CODEX_DATA:
        unlocked = biome["biome_id"] in state.biomes_visited
        entry = {
            "biome_id": biome["biome_id"],
            "name": biome["name"],
            "description": biome["description"] if unlocked else "???",
            "value_rating": biome["value_rating"] if scanner_level >= 1 else None,
            "hint": biome["tier1_hint"] if scanner_level >= 0 else None,
            "common_discoveries": biome["common_discoveries"] if scanner_level >= 2 and unlocked else [],
            "unlocked": unlocked,
        }
        codex_entries.append(entry)

    return codex_entries
