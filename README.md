# Starfarer: Echoes of the Void

A procedurally generated space exploration game — built by AI, for AI.

## Data Directory

Game state is stored in a persistent data directory decoupled from the repository. By default this is:

```
~/.starfarer/data/
```

Set the `STARFARER_DATA_DIR` environment variable to override:

```bash
export STARFARER_DATA_DIR=/path/to/custom/data
```

The directory is created automatically on first use and contains:

- `starfarer.db` — SQLite database with game and save state
- `save/` — Save file storage directory

## Migration System

The database uses a versioned migration system (`backend/database.py`). Migrations are defined in the `MIGRATIONS` list as `(version, sql)` tuples and run automatically on startup via `run_migrations()`. The `schema_version` table tracks which migrations have been applied. Only pending migrations are executed, making upgrades safe and idempotent.

## Deployment Considerations

- Set `STARFARER_DATA_DIR` to a persistent volume or dedicated data partition in production to ensure game state survives redeployments.
- The frontend is served as static files by FastAPI — no separate web server or build step is required.
- Database migrations run automatically at startup. No manual migration commands are needed.
- Default database path: `~/.starfarer/data/starfarer.db`

## Recent Updates

### Black Hole System Events
Five new events are now available exclusively in black hole systems:
- **Time Dilation Anomaly** (hazard) — Navigate the effects of extreme time dilation
- **Hawking Radiation Harvest** (discovery) — Harvest exotic energy from the event horizon
- **Spaghettification Near-Miss** (hazard, rare) — Escape the crushing tidal forces
- **Accretion Disk Prospecting** (discovery) — Mine valuable minerals from the accretion disk
- **Gravitational Lens Observation** (discovery) — Use the black hole as a natural telescope

These events are triggered automatically when your ship enters a system with a black hole phenomenon.

### Event Reputation System
All event types now have consistent faction reputation effects:
- **Exploration & Discovery** events grant Stellar Cartographers reputation
- **Trade** events grant Void Traders reputation
- **Encounter, Crisis, Crew & Hazard** events grant Free Pilots reputation
- **Narrative** events are atmospheric and do not affect reputation

### Lore Fragment Viewer & Discovery Metadata
- The lore viewer has been redesigned with tab-based navigation by story arc, progress bars, and detailed fragment cards
- Discovered fragments now show their discovery location (system name - body name) and discovery date, stored as a `discovery_timestamp` in ISO format datetime
- Undiscovered fragments display hints to guide exploration
- A notification toast appears when a new lore fragment is discovered, with a "View" button to open the lore viewer
- The Lore button pulses with a glow animation when there are unread fragments (uses `data-lore-nav="true"` attribute selector)
- The explore API response now includes a `lore_fragments_discovered` field listing any newly found fragments
- Lore fragment lookup in api_explore and api_lore changed from O(n²) to O(1) using hash maps
- Re-exploring an already-discovered lore fragment now logs at DEBUG level instead of WARNING
- Lore fragment discovery date extraction uses regex instead of fragile substring matching
- Lore fragment ID matching in log messages uses regex extraction instead of fragile substring matching
- The lore viewer container now has `data-component="lore-viewer"` instead of unused `data-game-id`
- `notifyLoreFragment` and `updateLoreButtonGlow` have safe fallback stubs in main.js when lore.js is not loaded
- The `_distress_pilots_guild` function now returns an error dict instead of raising ValueError when system is None

## Quick Start

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
```

API docs: `http://localhost:8001/docs`
