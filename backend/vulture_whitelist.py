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

"health"  # pragma: no cover  # noqa: B018
"api_new_game"  # pragma: no cover  # noqa: B018
"api_get_game"  # pragma: no cover  # noqa: B018
"api_galaxy"  # pragma: no cover  # noqa: B018
"api_system_detail"  # pragma: no cover  # noqa: B018
"api_jump"  # pragma: no cover  # noqa: B018
"api_land"  # pragma: no cover  # noqa: B018
"api_atmospheric_scan"  # pragma: no cover  # noqa: B018
"api_sub_surface_explore"  # pragma: no cover  # noqa: B018
"api_explore"  # pragma: no cover  # noqa: B018
"api_resolve_event"  # pragma: no cover  # noqa: B018
"api_log"  # pragma: no cover  # noqa: B018
"api_log_paginated"  # pragma: no cover  # noqa: B018
"api_discoveries"  # pragma: no cover  # noqa: B018
"api_cargo"  # pragma: no cover  # noqa: B018
"api_lore"  # pragma: no cover  # noqa: B018
"api_codex"  # pragma: no cover  # noqa: B018
"api_trade"  # pragma: no cover  # noqa: B018
"api_bulk_sell"  # pragma: no cover  # noqa: B018
"api_upgrade"  # pragma: no cover  # noqa: B018
"api_upgrades_info"  # pragma: no cover  # noqa: B018
"api_nearby"  # pragma: no cover  # noqa: B018
"api_distress"  # pragma: no cover  # noqa: B018
"api_salvage"  # pragma: no cover  # noqa: B018
"api_salvage_craft"  # pragma: no cover  # noqa: B018
"api_factions"  # pragma: no cover  # noqa: B018
"api_faction_detail"  # pragma: no cover  # noqa: B018
"api_faction_mission"  # pragma: no cover  # noqa: B018
"api_missions"  # pragma: no cover  # noqa: B018
"api_accept_mission"  # pragma: no cover  # noqa: B018
"api_complete_mission"  # pragma: no cover  # noqa: B018
"api_save"  # pragma: no cover  # noqa: B018
"api_load"  # pragma: no cover  # noqa: B018
"api_dismiss_hint"  # pragma: no cover  # noqa: B018
"api_leaderboard"  # pragma: no cover  # noqa: B018
"api_spectate_games"  # pragma: no cover  # noqa: B018
"api_system_ghosts"  # pragma: no cover  # noqa: B018
"api_leave_ghost"  # pragma: no cover  # noqa: B018
"api_crossroads_items"  # pragma: no cover  # noqa: B018
"api_donate_item"  # pragma: no cover  # noqa: B018
"api_claim_item"  # pragma: no cover  # noqa: B018
"api_crossroads_lore"  # pragma: no cover  # noqa: B018
"api_donate_lore"  # pragma: no cover  # noqa: B018
"api_claim_lore"  # pragma: no cover  # noqa: B018
"api_crossroads_messages"  # pragma: no cover  # noqa: B018
"api_post_message"  # pragma: no cover  # noqa: B018
"api_ripples"  # pragma: no cover  # noqa: B018
"api_acknowledge_ripple"  # pragma: no cover  # noqa: B018
"index"  # pragma: no cover  # noqa: B018
"application"  # pragma: no cover  # noqa: B018
"text_not_blank"  # pragma: no cover  # noqa: B018
"status"  # pragma: no cover  # noqa: B018
"row_factory"  # pragma: no cover  # noqa: B018
"side_effect"  # pragma: no cover  # noqa: B018
"cleanup_messages"  # pragma: no cover  # noqa: B018
"setup_db"  # pragma: no cover  # noqa: B018
"lore_frags"  # pragma: no cover  # noqa: B018
"GAME_NAME"  # pragma: no cover  # noqa: B018
"GAME_VERSION"  # pragma: no cover  # noqa: B018
"MAX_CARGO"  # pragma: no cover  # noqa: B018
"MAX_HULL"  # pragma: no cover  # noqa: B018
"MAX_FUEL"  # pragma: no cover  # noqa: B018
"MAX_MORALE"  # pragma: no cover  # noqa: B018
"MAX_CREW"  # pragma: no cover  # noqa: B018
"BIOME_COLORS"  # pragma: no cover  # noqa: B018
"ALL_DISCOVERY_CATEGORIES"  # pragma: no cover  # noqa: B018
