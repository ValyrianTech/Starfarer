# Changelog

## [Unreleased]

### Added
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

### Changed
- Refactored `resolve_event()` to use `_EVENT_REP_MAP` dictionary for event type → faction mapping
- Updated fuel pricing tests to use local variable names avoiding shadowing
- Re-exploring an already-discovered lore fragment now logs at DEBUG level instead of WARNING
- Lore fragment lookup in api_explore and api_lore changed from O(n²) to O(1) using hash maps
- Lore viewer HTML structure completely redesigned with arc tabs, progress bars, and fragment cards
- Lore button now has `data-lore-nav="true"` attribute for targeted pulse animation

### Fixed
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
