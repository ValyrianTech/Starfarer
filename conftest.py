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

    patcher_dir = patch.object(database, "DATA_DIR", tmp_dir)
    patcher_db = patch.object(database, "DB_PATH", db_path)
    patcher_dir.start()
    patcher_db.start()

    init_db()
    run_migrations()

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
