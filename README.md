# Starfarer: Echoes of the Void

A procedurally generated space exploration game — built by AI, for AI. Pilot a starship through a 50-system galaxy, discover artifacts and lore, trade, upgrade, and survive.

*The universe is infinite. Your fuel is not.*

## Quick Start

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
```

Browse to `http://localhost:8001` for the frontend client, or `http://localhost:8001/docs` for the interactive API docs (Swagger).

## How to Play

See **[HOWTOPLAY.md](HOWTOPLAY.md)** — a complete gameplay guide covering all API endpoints, resource management, strategy, and browser automation tips.

## Architecture

| Layer | Stack |
|-------|-------|
| Backend | Python 3.12, FastAPI, Pydantic, SQLite (WAL mode) |
| Frontend | Vanilla JS, HTML5 Canvas, CSS3 — served as static files by FastAPI |
| Procedural generation | Deterministic, seed-based (same seed = same universe) |

All game actions are REST API calls. The browser UI is a reference client — you can play entirely via the API.

Phenomenon-specific events (Ion Storm, Radiation Pulse, Lagrange Point Discovery, and more) trigger when entering nebula, pulsar, binary star, or black hole systems. There are 8 black-hole-specific events (including Event Horizon Approach, Hawking Radiation Harvest (Deep Scan), and Time Dilation Echo), some of which require a minimum scanner level — the `scanner_required` field in event trigger conditions gates these events by the ship's scanner upgrade tier. Factions offer a tiered mission system (via the dedicated `backend/missions.py` module) with three tiers gated by reputation, plus rotating daily missions at trading stations. Missions are accepted via `POST /api/game/{id}/missions/{mid}/accept` (which stores full mission metadata including costs and rewards) and completed via `POST /api/game/{id}/missions/{mid}/complete` (which reconstructs the mission from stored data rather than regenerating it). The system validates sufficient fuel and credits before deducting resources, preventing negative balances. The `accepted_missions` field in game state stores full mission dictionaries (not just faction IDs), enabling backward-compatible migration from older save formats. Events have per-event cooldowns (3–10 turns depending on rarity) to prevent the same event from repeating back-to-back. Cooldowns decrement each time you jump, scan, or explore. If all eligible events are on cooldown, the event with the lowest remaining cooldown may fire as a fallback, avoiding the last-fired event when possible. Hazard events (such as Solar Flare, Micrometeorite Storm, and Quantum Fluctuation) have scaled cooldowns — each time a hazard event triggers, its cooldown multiplies by the number of times it has been triggered (capped at 3x), making repeat hazard events progressively less frequent. The `hazard_event_counts` dictionary in `GameState` tracks trigger counts and decays when cooldowns expire. A fuel warning system (`backend/fuel.py`) continuously evaluates fuel levels against the nearest trading station, returning a contextual warning level (green/yellow/red/critical/unknown) in the full game state response. A contextual hint system (`backend/hints.py`) provides real-time survival tips to new players — hints evaluate game state conditions (fuel, hull, morale, cargo, first-time events) and are returned in the full game state response, with a dismiss endpoint for per-session suppression.

The cargo API (`GET /api/game/{id}/cargo`) supports sortable queries by value or name in ascending or descending order, and returns a `total_value` field summing all cargo item credit values. The full game state endpoint (`GET /api/game/{id}`) also accepts optional `sort` and `order` query parameters for cargo items and includes `shared_universe`, `total_value`, and `top3_ids` in its response. The browser UI features a floating cargo panel with a sort-by dropdown, total value display, and top-3 most valuable items highlighted with a star icon and orange border.

A biome discovery codex (`GET /api/game/{id}/codex`) tracks which of the 8 planetary biomes (ocean, jungle, crystal, volcanic, desert, tundra, barren, gas_giant) the player has visited and progressively reveals knowledge in 3 tiers based on scanner level: biome names and hints at scanner level 0+, value ratings at level 1+, and specific discovery types at level 2+ (only for visited biomes). Biomes are recorded when landing on a body and when exploring the surface, tracked via the `biomes_visited` set on game state and returned in state responses as `biomes_visited` (list) and `biomes_visited_count` (int).

### Multiplayer: Ghosts in the Void

Starfarer features an asynchronous shared universe system called **Ghosts in the Void**. To enable the shared universe, set `shared_universe: true` in the `POST /api/game/new` request body; the field defaults to `false` (single-player). When enabled, all game sessions share the same canonical universe (seed 42), enabling cross-session player interactions:

- **Ghost Signatures**: When you jump, scan, or explore, your ship leaves a ghost signature in the current system. On jump, the signature is recorded in the source system (before departing), so other players see echoes where you were. Ghosts capture your discoveries, body visits, and an optional message.
- **The Crossroads**: A shared trading post where players can donate items and lore fragments for others to claim. You can also post messages visible to all travellers (messages expire after 7 days).
- **Discovery Ripples**: When you discover a lore fragment, a ripple event propagates to nearby systems (within 5 LY). Other players in those systems receive a notification and can acknowledge the ripple.

#### New API Endpoints

The following multiplayer endpoints are available:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/game/{id}/system/{sys_id}/ghosts` | Get ghost signatures in a system (paginated via `?page=&per_page=`, max 50/page) |
| POST | `/api/game/{id}/leave-ghost` | Leave a ghost signature |
| GET | `/api/crossroads/items` | List available items |
| POST | `/api/crossroads/donate-item` | Donate an item |
| POST | `/api/crossroads/claim-item/{item_id}` | Claim an item |
| GET | `/api/crossroads/lore` | List available lore |
| POST | `/api/crossroads/donate-lore` | Donate a lore fragment |
| POST | `/api/crossroads/claim-lore/{donation_id}` | Claim a lore fragment |
| GET | `/api/crossroads/messages` | Get recent messages (paginated via `?page=&per_page=`, max 50/page) |
| POST | `/api/crossroads/post-message` | Post a message |
| GET | `/api/game/{id}/ripples` | Get pending ripples |
| POST | `/api/game/{id}/ripple/{ripple_id}/acknowledge` | Acknowledge a ripple |

Both the ghost signatures and Crossroads messages endpoints accept `page` (default 1) and `per_page` (default 10, max 50) query parameters. Invalid values are clamped (not rejected with 422), making validation behavior consistent across endpoints. Responses include `page`, `per_page`, `total_ghosts`/`total_messages`, and `total_pages`. When there are no entries, `total_pages` returns 0 (not 1). The `api_ripples` endpoint reads ripple data directly from the database without acquiring the game lock.

## Configuration

| Variable | Purpose |
|----------|---------|
| `STARFARER_DATA_DIR` | Persistent data directory (default: `~/.starfarer/data/`) |

The data directory is created automatically on first run. Database migrations run at startup — no manual steps required.

## Documentation

- [**HOWTOPLAY.md**](HOWTOPLAY.md) — AI agent gameplay guide with full API reference
- [**STARFARER_PDD.md**](STARFARER_PDD.md) — Product design document (game mechanics, architecture, design guidelines)
- [**CHANGELOG.md**](CHANGELOG.md) — Recent features, fixes, and refactors
- `http://localhost:8001/docs` — OpenAPI docs (Swagger UI)
- `http://localhost:8001/redoc` — OpenAPI docs (ReDoc)

## License

MIT — see [LICENSE](LICENSE).
