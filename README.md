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

## Quick Start

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
```

API docs: `http://localhost:8001/docs`
