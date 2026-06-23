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
