# Starfarer: Echoes of the Void

A procedurally generated space exploration game — built by AI, for AI. Pilot a starship through a 50-system galaxy, discover artifacts and lore, trade, upgrade, and survive.

*The universe is infinite. Your fuel is not.*

## Quick Start

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
```

Browse to `http://localhost:8001` for the frontend client, `http://localhost:8001/webui/` for the read-only 3D spectator view, or `http://localhost:8001/docs` for the interactive API docs (Swagger).

## Spectator Mode

A separate, read-only web app for humans to watch a game in progress (e.g. while an AI is playing). Open `http://localhost:8001/webui/` and pick a game, or link directly with `http://localhost:8001/webui/?game=<game_id>`.

- 3D galaxy map (Three.js) with glowing stars, phenomenon effects (nebulae, pulsars, binary stars, black holes, asteroid fields, ancient gates), and an auto-orbiting camera that follows the ship
- Animated hyperspace jumps with an engine trail; visited systems light up as the galaxy is explored
- Live HUD: ship vitals (fuel/hull/morale/cargo), credits, crew, faction reputation, expedition stats, pending event card, and a scrolling ship log
- Powered by two read-only endpoints: `GET /api/spectate/games` (game list) and `GET /api/spectate/{game_id}/stream` (Server-Sent Events stream pushing a state summary plus new log entries whenever the game changes)

No interaction is possible from the spectator view — it never mutates game state.

## How to Play

See **[HOWTOPLAY.md](HOWTOPLAY.md)** — a complete gameplay guide covering all API endpoints, resource management, strategy, and browser automation tips.

## Architecture

| Layer | Stack |
|-------|-------|
| Backend | Python 3.12, FastAPI, Pydantic, SQLite (WAL mode) |
| Frontend | Vanilla JS, HTML5 Canvas, CSS3 — served as static files by FastAPI |
| Spectator webui | Vanilla JS, Three.js (vendored, no build step), SSE — served at `/webui` |
| Procedural generation | Deterministic, seed-based (same seed = same universe) |

All game actions are REST API calls. The browser UI is a reference client — you can play entirely via the API.

Key features include a deterministic procedural galaxy with 50 systems, 40+ unique events (including phenomenon-specific events for nebula, pulsar, binary star, and black hole systems), a tiered faction mission system, ship upgrades, a biome discovery codex, fuel warning and contextual hint systems, salvage and emergency crafting mechanics, and an asynchronous multiplayer shared universe ("Ghosts in the Void") with ghost signatures, a shared crossroads trading post, and discovery ripples. See **[HOWTOPLAY.md](HOWTOPLAY.md)** for complete details.

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
