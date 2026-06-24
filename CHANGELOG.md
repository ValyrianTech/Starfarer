# Changelog

## [Unreleased]

### Added
- Sort and order query parameters to GET /api/game/{id}/cargo endpoint: `sort` (\"value\" or \"name\", default \"value\") and `order` (\"asc\" or \"desc\", default \"desc\")
- Sort and order query parameters to GET /api/game/{id} full game state endpoint (same values as cargo endpoint)
- `total_value` field to GET /api/game/{id}/cargo response (sum of all cargo item values)
- `total_value` field to GET /api/game/{id} full game state response
- `top3_ids` field to GET /api/game/{id}/cargo response (list of the 3 most valuable cargo item IDs)
- `top3_ids` field to GET /api/game/{id} full game state response (list of the 3 most valuable cargo item IDs)
- Cargo UI enhancement — floating cargo panel with sort-by dropdown (Value High-Low, Value Low-High, Name A-Z, Name Z-A), total value display in credits, top-3 most valuable items highlighted with star and orange border, empty state message when cargo is empty
- 9 new phenomenon-specific events: 4 nebula events (Ion Storm, Protostar Formation, Nebula Navigation Puzzle), 3 pulsar events (Radiation Pulse, Pulsar Timing Signal, Neutron Star Proximity), and 2 binary star events (Orbital Mechanics Challenge, Lagrange Point Discovery)
- 5 new black hole system-specific events: Time Dilation Anomaly, Hawking Radiation Harvest, Spaghettification Near-Miss, Accretion Disk Prospecting, and Gravitational Lens Observation
- Reputation handling for `discovery` and `hazard` event types in `resolve_event()`
- Explicit handling for `narrative` event type (no reputation changes)
- Comprehensive test suite for black hole events and reputation bonuses
- Lore fragment hints: All 20 lore fragments now have hint text shown for undiscovered fragments in the lore viewer
- Lore fragment discovery metadata: API now returns `discovery_location` and `discovery_date` for each discovered lore fragment
- Explore API response now includes `lore_fragments_discovered` field listing any lore fragments found during exploration
- Lore viewer UI overhaul: Tab-based navigation by arc, progress bars, fragment cards with location/date metadata
- Lore discovery notification toast: In-app notification when a lore fragment is discovered
- Lore button pulse animation: Lore button glows when new fragments are unread
- Safe fallback for unknown systems in lore discovery location (when system not found in state)
- Event cooldown system: per-event cooldowns prevent event repetition within a session
- `EVENT_COOLDOWNS` dictionary with configurable cooldown values per event title (3, 5, 6, 8, or 10 turns)
- `apply_cooldown()` and `decrement_cooldowns()` functions for cooldown lifecycle management
- `_apply_cooldown_fallback()` — fallback logic when all eligible events are on cooldown, picks the one with lowest remaining cooldown
- `event_cooldowns` field to `GameState` for persistent cooldown tracking across save/load
- Cooldown decrement in jump, scan, and explore API endpoints (called before event trigger)
- Comprehensive test suite for event cooldown behavior (210 lines)
- Tiered faction mission system with 3 tiers and scaling costs/rewards: Tier 1 (fuel=3, credits=10, reward=50-100 cr, 5-10 rep), Tier 2 (fuel=6, credits=25, reward=150-300 cr, 10-15 rep, rep≥15), Tier 3 (fuel=10, credits=50, reward=400-800 cr, 20-30 rep, rep≥30)
- Free daily mission ("Daily Opportunity") per system: 0 fuel/credit cost, 25-75 credits reward, 5-10 reputation
- Mission types per tier: Tier 1 (courier, survey), Tier 2 (exploration, salvage, patrol), Tier 3 (special_ops, diplomatic)
- New API endpoints: `GET /api/game/{id}/missions` (list available missions), `POST /api/game/{id}/missions/{mid}/accept` (accept mission, deduct costs), `POST /api/game/{id}/missions/{mid}/complete` (complete mission, claim rewards)
- New request schemas: `AcceptMissionRequest` and `CompleteMissionRequest` (both with `mission_id: str` and optional `faction_id: str`)
- New game state fields: `completed_missions` (list[dict]), `daily_missions_used` (dict[str, str]), `accepted_missions` (set[str])
- Fuel warning status system (`backend/fuel.py`): evaluates fuel level relative to the nearest trading station and returns a warning level (`green`, `yellow`, `red`, `critical`, `unknown`) with supporting information
- `fuel_status` field in full game state response (`GET /api/game/{id}`): includes `level`, `message`, `current_fuel`, `fuel_for_round_trip`, `fuel_for_one_way`, `nearest_station_system`, and `nearest_station_distance`
- Type annotations and docstrings for `missions.py` functions (`get_daily_mission_key`, `generate_missions`, `complete_mission`, `_mission_seed`, `FactionMission.to_dict`)
- Paginated log endpoint `GET /api/game/{game_id}/log/paginated` with query parameters `page` (int, default 1), `per_page` (int, default 20, max 100), `category` (str, optional filter), `search` (str, optional full-text search). Returns `log_entries`, `page`, `per_page`, `total_entries`, `total_pages`. Entries returned most-recent-first. Returns 404 if game not found.
- Enhanced log entry schema with structured metadata fields: `id` (sequential integer), `type`, `message`, `timestamp`, `category`, `title`, `description`, `system`, `body`, `credits_change`, `fuel_change`, `hull_change`, `morale_change`, `cargo_change`. The old `/api/game/{id}/log` endpoint is backward-compatible and also returns the new fields.
- Sequential integer log entry IDs with `_next_log_id` counter in GameState for collision prevention on save/load cycles
- Backward compatibility for old saves without `_next_log_id` (computed from max existing ID + 1, defaults to 1 if log is empty)

### Changed
- Added type annotations to `get_fuel_status` function parameters in `backend/fuel.py`
- Refactored `resolve_event()` to use `_EVENT_REP_MAP` dictionary for event type → faction mapping
- Updated fuel pricing tests to use local variable names avoiding shadowing
- Re-exploring an already-discovered lore fragment now logs at DEBUG level instead of WARNING
- Lore fragment lookup in api_explore and api_lore changed from O(n²) to O(1) using hash maps
- Lore viewer HTML structure completely redesigned with arc tabs, progress bars, and fragment cards
- Lore button now has `data-lore-nav="true"` attribute for targeted pulse animation
- `POST /api/game/{id}/faction/{fid}/mission` now uses tiered mission system: guaranteed success (no random success/failure), costs/rewards scale with reputation, requires being at a trading station, response includes `mission` field with details
- All game action log calls now include structured metadata fields (category, title, system, body, resource changes) for: jumps, scans, landings, exploration, distress calls, salvage, emergency crafting, trading, upgrades, missions, events, and faction reputation changes
- Mission completion log entry now includes `credits_change` metadata

### Fixed
- Query parameters now URL-encoded in `api.js` cargo method using `encodeURIComponent()`
- Validation of sort and order query parameters in API cargo endpoint returns 422 with helpful error messages for invalid values
- Narrative event type now correctly resolves without attempting reputation changes
- Discovery and hazard events now properly award faction reputation
- Contradictory outcome in Accretion Disk Prospecting event resolved
- Gravitational Lens Observation outcome no longer incorrectly claims lore fragment discovery
- `_get_eligible_templates` fallback behavior documented: when all templates with trigger conditions are filtered out, only templates with no trigger conditions are returned
- `trigger_event` low-morale path behavior documented: probability roll is skipped entirely when morale < 30
- Fragile RNG seed dependency in `test_black_hole_events_can_be_triggered` fixed by using mocked `random()`
- Lore viewer container now has proper `data-component="lore-viewer"` attribute instead of unused `data-game-id`
- `notifyLoreFragment` and `updateLoreButtonGlow` now have safe fallback stubs in main.js when lore.js is not loaded
- Lore fragment ID matching in log messages now uses regex extraction instead of fragile substring matching
- `_unreadLoreCount` is now reset to 0 when lore view is rendered (not when the user views it)
- Frontend lore viewer now uses `escapeHtml()` instead of `innerHTML` for rendering text content (security fix)
- `_distress_pilots_guild` now returns an error dict instead of raising ValueError when no current system
- Lore fragment discovery location fallback now uses informative "Unknown system" format with IDs
- `explore_surface` now correctly handles the `lore_linked` flag when `num_finds` is 0
- Lore fragment discovery date extraction now uses regex instead of fragile substring matching on log messages
- Lore fragment discovery now stores `discovery_timestamp` as ISO format datetime
- Cooldown fallback in `trigger_event` no longer bypasses last_event_title dedup when all eligible events share the same cooldown value
- Duplicated cooldown fallback logic in `trigger_event` consolidated into `_apply_cooldown_fallback()`
- Resolved inconsistent cooldown decrement timing: `resolve_event` route now ticks cooldowns after resolution instead of before
- In-place mutation of eligible list in `_apply_cooldown_fallback` fixed by using a copy of the list before sorting
- Off-by-one cooldown decrement order relative to event trigger fixed: cooldowns now decrement before the event trigger on jump, scan, and explore, ensuring correct timing on the first action
- `EVENT_COOLDOWNS` dictionary entries with no corresponding template no longer cause key errors during cooldown application
- `_apply_cooldown_fallback` no longer returns an empty list when eligible is non-empty but all events have cooldown <= 0
- `decrement_cooldowns` now uses `list(state.event_cooldowns.keys())` for safe iteration when deleting expired cooldowns
- Duplicate mission acceptance prevented via `accepted_missions` set tracking
- `accepted_missions` set now cleaned up on mission completion (`.discard()`)
- Completed missions now checked before applying rewards
- Free daily mission no longer selectable via random choice for standard mission slot
- Mission lookup now only generates missions for the relevant faction (not all factions)
- Log entry ID collision risk on save/load cycles
- `total_pages` returns 0 instead of 1 when there are 0 log entries in paginated endpoint

### Removed
- Dead code `get_available_events` (defined but never used in production)
- Unused imports: `get_daily_mission_key`, `_TIER_COSTS`, and `faction_id` variable
- Unused `uuid` import from `backend/models/game_state.py`
