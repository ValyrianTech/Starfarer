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
- Powered by two read-only endpoints: `GET /api/spectate/games` (game list) and `GET /api/spectate/{game_id}/stream` (Server-Sent Events stream pushing a state summary plus new log entries whenever the game changes). When `STARFARER_REQUIRE_GAME_TOKEN` is enabled, the SSE stream requires the game token via the `X-Game-Token` header or a short-lived single-use stream ticket (see below) — the `token` query parameter is no longer accepted — and the game list is disabled (HTTP 403).

When `STARFARER_REQUIRE_GAME_TOKEN` is enabled, supply the game token to the spectator webui by opening it with an explicit `?game=<game_id>&token=<token>` URL, e.g. `http://localhost:8001/webui/?game=<game_id>&token=<token>`. The webui reads the token from the `token` URL parameter first, then from `localStorage` under the key `starfarer_game_token` (settable in the browser console via `localStorage.setItem('starfarer_game_token', '<token>')`); a token passed via the URL is persisted to `localStorage` so subsequent fetches reuse it. Because `EventSource` cannot set request headers, the long-lived game token is never placed in a URL: when enforcement is on, the webui mints a short-lived single-use stream ticket (via `POST /api/spectate/{game_id}/stream-ticket`, authenticating with the `X-Game-Token` header) and passes only that ticket as the `ticket` query parameter of the SSE stream. Since `GET /api/spectate/games` is disabled (403) while enforcement is on, open the webui with an explicit `?game=<id>&token=<token>` URL rather than relying on the game picker.

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

All game actions are REST API calls. The browser UI is a reference client — you can play entirely via the API. Game creation (`POST /api/game/new`) rejects duplicate caller-supplied game IDs with HTTP 409 Conflict.

Key features include a deterministic procedural galaxy with 50 systems, 40+ unique events (including additional phenomenon-specific events for nebula, pulsar, binary star, and black hole systems), a tiered faction mission system, ship upgrades, an expanded biome discovery codex (with rare discoveries and unique locations), scanner tier data that reveals value estimates, anomaly detection, and resource mapping at higher scanner levels, deep exploration mechanics (atmospheric scans, sub-surface exploration, rare motherlode finds, and diminishing returns that reward exploring new bodies), fuel warning and contextual hint systems, salvage and emergency crafting mechanics, and an asynchronous multiplayer shared universe ("Ghosts in the Void") with ghost signatures, a shared crossroads trading post, and discovery ripples. See **[HOWTOPLAY.md](HOWTOPLAY.md)** for complete details.

Both the ghost signatures and Crossroads messages endpoints accept `page` (default 1) and `per_page` (default 10, max 50) query parameters. Invalid values are clamped (not rejected with 422), making validation behavior consistent across endpoints. Responses include `page`, `per_page`, `total_ghosts`/`total_messages`, and `total_pages`. When there are no entries, `total_pages` returns 0 (not 1). The `api_ripples` endpoint reads ripple data directly from the database without acquiring the game lock. State-modifying API routes serialize access to a game's state with a per-game lock to prevent race conditions under concurrent requests. The in-memory game cache is bounded to `MAX_IN_MEMORY_GAMES` (200) games and evicts the least-recently-used games (persisting them to SQLite first) to cap memory use, while keeping currently-active (locked) games resident. Actively-watched spectator SSE streams also refresh their game's recency on each poll, so a game being streamed is not evicted mid-stream.

`POST /api/game/new` returns a per-game `token` alongside `game_id` and `state`. The leaderboard endpoint (`GET /api/leaderboard`) returns an opaque `entry_id` and never exposes the raw `game_id` or `seed` — a deliberate breaking change from the original design. When `STARFARER_REQUIRE_GAME_TOKEN` is enabled, all endpoints that access a specific game — both mutating and read-only GET endpoints — require that token via the `X-Game-Token` header only (the `token` query parameter is no longer accepted). The spectator SSE stream (`GET /api/spectate/{game_id}/stream`) authenticates via the `X-Game-Token` header or a short-lived single-use stream ticket (see Spectator Mode), and `GET /api/spectate/games` is disabled (HTTP 403) while enforcement is on. CORS credentials are automatically disabled when a wildcard origin is configured.

## Configuration

| Variable | Purpose |
|----------|---------|
| `STARFARER_DATA_DIR` | Persistent data directory (default: `~/.starfarer/data/`) |
| `STARFARER_ALLOWED_ORIGINS` | Comma-separated list of CORS allowed origins (default: local dev origins `http://localhost:3000`, `http://localhost:8080`, `http://localhost:8001`) |
| `STARFARER_REQUIRE_GAME_TOKEN` | When truthy (`1`, `true`, `yes`, `on`, case-insensitive), require the per-game token (supplied via the `X-Game-Token` header only; the `token` query parameter is no longer accepted) on all endpoints that access a specific game — mutating and read endpoints — plus spectator endpoints (default: off) |

The data directory is created automatically on first run. Database migrations run at startup — no manual steps required.

## Documentation

- [**HOWTOPLAY.md**](HOWTOPLAY.md) — AI agent gameplay guide with full API reference
- [**STARFARER_PDD.md**](STARFARER_PDD.md) — Product design document (game mechanics, architecture, design guidelines)
- [**CHANGELOG.md**](CHANGELOG.md) — Recent features, fixes, and refactors
- `http://localhost:8001/docs` — OpenAPI docs (Swagger UI)
- `http://localhost:8001/redoc` — OpenAPI docs (ReDoc)

## License

MIT — see [LICENSE](LICENSE).
