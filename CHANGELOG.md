# Changelog

## [Unreleased]

### Added
- 5 new black hole system-specific events: Time Dilation Anomaly, Hawking Radiation Harvest, Spaghettification Near-Miss, Accretion Disk Prospecting, and Gravitational Lens Observation
- Reputation handling for `discovery` and `hazard` event types in `resolve_event()`
- Explicit handling for `narrative` event type (no reputation changes)
- Comprehensive test suite for black hole events and reputation bonuses

### Changed
- Refactored `resolve_event()` to use `_EVENT_REP_MAP` dictionary for event type → faction mapping
- Updated fuel pricing tests to use local variable names avoiding shadowing

### Fixed
- Narrative event type now correctly resolves without attempting reputation changes
- Discovery and hazard events now properly award faction reputation
- Contradictory outcome in Accretion Disk Prospecting event resolved
- Gravitational Lens Observation outcome no longer incorrectly claims lore fragment discovery
- `_get_eligible_templates` fallback behavior documented: when all templates with trigger conditions are filtered out, only templates with no trigger conditions are returned
- `trigger_event` low-morale path behavior documented: probability roll is skipped entirely when morale < 30
- Fragile RNG seed dependency in `test_black_hole_events_can_be_triggered` fixed by using mocked `random()`
