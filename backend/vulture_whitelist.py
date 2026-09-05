"""Vulture whitelist for Starfarer: Echoes of the Void.

This module suppresses false-positive "unused code" warnings emitted by the
`vulture` dead-code detector. It marks framework-magic names -- such as FastAPI
route decorators, Pydantic model fields, pytest fixtures, and mock attribute
assignments -- as well as public API constants as used via bare name
references. These names are resolved at runtime or through framework
introspection and are therefore not detected as used by static analysis alone.
"""

# Vulture whitelist: false positives from framework magic (FastAPI route
# decorators, Pydantic fields, pytest fixtures, mock attribute assignments)
# and public API constants. Bare name references mark these items as used.

"health"  # pragma: no cover
"api_new_game"  # pragma: no cover
"api_get_game"  # pragma: no cover
"api_galaxy"  # pragma: no cover
"api_system_detail"  # pragma: no cover
"api_jump"  # pragma: no cover
"api_land"  # pragma: no cover
"api_atmospheric_scan"  # pragma: no cover
"api_sub_surface_explore"  # pragma: no cover
"api_explore"  # pragma: no cover
"api_resolve_event"  # pragma: no cover
"api_log"  # pragma: no cover
"api_log_paginated"  # pragma: no cover
"api_discoveries"  # pragma: no cover
"api_cargo"  # pragma: no cover
"api_lore"  # pragma: no cover
"api_codex"  # pragma: no cover
"api_trade"  # pragma: no cover
"api_bulk_sell"  # pragma: no cover
"api_upgrade"  # pragma: no cover
"api_upgrades_info"  # pragma: no cover
"api_nearby"  # pragma: no cover
"api_distress"  # pragma: no cover
"api_salvage"  # pragma: no cover
"api_salvage_craft"  # pragma: no cover
"api_factions"  # pragma: no cover
"api_faction_detail"  # pragma: no cover
"api_faction_mission"  # pragma: no cover
"api_missions"  # pragma: no cover
"api_accept_mission"  # pragma: no cover
"api_complete_mission"  # pragma: no cover
"api_save"  # pragma: no cover
"api_load"  # pragma: no cover
"api_dismiss_hint"  # pragma: no cover
"api_leaderboard"  # pragma: no cover
"api_spectate_games"  # pragma: no cover
"api_system_ghosts"  # pragma: no cover
"api_leave_ghost"  # pragma: no cover
"api_crossroads_items"  # pragma: no cover
"api_donate_item"  # pragma: no cover
"api_claim_item"  # pragma: no cover
"api_crossroads_lore"  # pragma: no cover
"api_donate_lore"  # pragma: no cover
"api_claim_lore"  # pragma: no cover
"api_crossroads_messages"  # pragma: no cover
"api_post_message"  # pragma: no cover
"api_ripples"  # pragma: no cover
"api_acknowledge_ripple"  # pragma: no cover
"index"  # pragma: no cover
"application"  # pragma: no cover
"text_not_blank"  # pragma: no cover
"status"  # pragma: no cover
"row_factory"  # pragma: no cover
"side_effect"  # pragma: no cover
"cleanup_messages"  # pragma: no cover
"setup_db"  # pragma: no cover
"lore_frags"  # pragma: no cover
"GAME_NAME"  # pragma: no cover
"GAME_VERSION"  # pragma: no cover
"MAX_CARGO"  # pragma: no cover
"MAX_HULL"  # pragma: no cover
"MAX_FUEL"  # pragma: no cover
"MAX_MORALE"  # pragma: no cover
"MAX_CREW"  # pragma: no cover
"BIOME_COLORS"  # pragma: no cover
"ALL_DISCOVERY_CATEGORIES"  # pragma: no cover
