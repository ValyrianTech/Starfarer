import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_test_db():
    tmp_dir = Path(tempfile.mkdtemp(prefix="starfarer_test_"))
    db_path = tmp_dir / "starfarer.db"

    os.environ["STARFARER_DATA_DIR"] = str(tmp_dir)

    from backend import database
    from backend.database import init_db, run_migrations
    from backend.multiplayer.database import init_multiplayer_db

    patcher_dir = patch.object(database, "DATA_DIR", tmp_dir)
    patcher_db = patch.object(database, "DB_PATH", db_path)
    patcher_dir.start()
    patcher_db.start()

    init_db()
    run_migrations()
    # Games default to shared_universe=True, so exploration endpoints write
    # ripple events; the multiplayer schema must exist for every test.
    init_multiplayer_db()

    yield

    patcher_db.stop()
    patcher_dir.stop()


@pytest.fixture(autouse=True)
def _opt_out_auth_by_default(monkeypatch):
    """Default the test suite to no per-game token enforcement.

    The application now enforces per-game tokens by default (secure
    baseline). The bulk of the test suite was written against the old
    default-off behavior, so we opt out via STARFARER_ALLOW_NO_AUTH for
    every test; tests that exercise enforcement explicitly delete this
    opt-out and set STARFARER_REQUIRE_GAME_TOKEN.
    """
    monkeypatch.setenv("STARFARER_ALLOW_NO_AUTH", "1")
    yield


@pytest.fixture(autouse=True)
def _isolate_dos_protections(monkeypatch):
    """Reset rate-limit/shared-universe state and default the DoS guards off.

    The application now rate-limits ``POST /api/game/new`` per client IP and
    caps the number of stored games by default. The bulk of the suite creates
    games in tight loops and would trip those limits, so we (1) reset the
    per-IP limiter and the shared-universe cache before and after each test to
    avoid cross-test leakage, and (2) default both ``STARFARER_NEW_GAME_RATE_LIMIT``
    and ``STARFARER_MAX_STORED_GAMES`` to ``0`` (unlimited). Tests that exercise
    the protections override these env vars and rely on the per-test reset.
    """
    from backend.api.routes import reset_new_game_rate_limiter
    from backend.game.manager import reset_shared_universe_cache

    reset_new_game_rate_limiter()
    reset_shared_universe_cache()
    monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "0")
    monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "0")
    yield
    reset_new_game_rate_limiter()
    reset_shared_universe_cache()
