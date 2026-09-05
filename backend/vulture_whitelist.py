"""Vulture whitelist for Starfarer: Echoes of the Void.

This module suppresses false-positive "unused code" warnings emitted by the
`vulture` dead-code detector. It marks framework-magic names -- such as FastAPI
route decorators, Pydantic model fields, pytest fixtures, and mock attribute
assignments -- as well as public API constants as used via attribute
references. These names are resolved at runtime or through framework
introspection and are therefore not detected as used by static analysis alone.
"""


class Whitelist:
    """Helper class that allows mocking Python objects."""

    def __getattr__(self, _: str) -> None:
        pass


whitelist = Whitelist()

# FastAPI route handlers (registered via decorators)
whitelist.health  # noqa: B018
whitelist.api_new_game  # noqa: B018
whitelist.api_get_game  # noqa: B018
whitelist.api_galaxy  # noqa: B018
whitelist.api_system_detail  # noqa: B018
whitelist.api_jump  # noqa: B018
whitelist.api_land  # noqa: B018
whitelist.api_atmospheric_scan  # noqa: B018
whitelist.api_sub_surface_explore  # noqa: B018
whitelist.api_explore  # noqa: B018
whitelist.api_resolve_event  # noqa: B018
whitelist.api_log  # noqa: B018
whitelist.api_log_paginated  # noqa: B018
whitelist.api_discoveries  # noqa: B018
whitelist.api_cargo  # noqa: B018
whitelist.api_lore  # noqa: B018
whitelist.api_codex  # noqa: B018
whitelist.api_trade  # noqa: B018
whitelist.api_bulk_sell  # noqa: B018
whitelist.api_upgrade  # noqa: B018
whitelist.api_upgrades_info  # noqa: B018
whitelist.api_nearby  # noqa: B018
whitelist.api_distress  # noqa: B018
whitelist.api_salvage  # noqa: B018
whitelist.api_salvage_craft  # noqa: B018
whitelist.api_factions  # noqa: B018
whitelist.api_faction_detail  # noqa: B018
whitelist.api_faction_mission  # noqa: B018
whitelist.api_missions  # noqa: B018
whitelist.api_accept_mission  # noqa: B018
whitelist.api_complete_mission  # noqa: B018
whitelist.api_save  # noqa: B018
whitelist.api_load  # noqa: B018
whitelist.api_dismiss_hint  # noqa: B018
whitelist.api_leaderboard  # noqa: B018
whitelist.api_spectate_games  # noqa: B018
whitelist.api_system_ghosts  # noqa: B018
whitelist.api_leave_ghost  # noqa: B018
whitelist.api_crossroads_items  # noqa: B018
whitelist.api_donate_item  # noqa: B018
whitelist.api_claim_item  # noqa: B018
whitelist.api_crossroads_lore  # noqa: B018
whitelist.api_donate_lore  # noqa: B018
whitelist.api_claim_lore  # noqa: B018
whitelist.api_crossroads_messages  # noqa: B018
whitelist.api_post_message  # noqa: B018
whitelist.api_ripples  # noqa: B018
whitelist.api_acknowledge_ripple  # noqa: B018
whitelist.index  # noqa: B018

# Pydantic model fields/validators
whitelist.status  # noqa: B018
whitelist.text_not_blank  # noqa: B018

# Config constants
whitelist.GAME_NAME  # noqa: B018
whitelist.GAME_VERSION  # noqa: B018
whitelist.MAX_CARGO  # noqa: B018
whitelist.MAX_HULL  # noqa: B018
whitelist.MAX_FUEL  # noqa: B018
whitelist.MAX_MORALE  # noqa: B018
whitelist.MAX_CREW  # noqa: B018
whitelist.BIOME_COLORS  # noqa: B018
whitelist.ALL_DISCOVERY_CATEGORIES  # noqa: B018

# Pytest fixtures
whitelist.setup_db  # noqa: B018
whitelist.lore_frags  # noqa: B018
whitelist.cleanup_messages  # noqa: B018

# Mock attributes
whitelist.side_effect  # noqa: B018

# SQLite row_factory
whitelist.row_factory  # noqa: B018

# Lifespan parameter
whitelist.application  # noqa: B018
