import sys
import os
import importlib
import asyncio
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestConfigDataDirectory:
    def test_data_dir_is_path_object(self) -> None:
        from backend.config import DATA_DIR, DB_PATH
        assert isinstance(DATA_DIR, Path)
        assert isinstance(DB_PATH, Path)

    def test_db_path_is_data_dir_subpath(self) -> None:
        from backend.config import DATA_DIR, DB_PATH
        assert DB_PATH == DATA_DIR / "starfarer.db"

    def test_data_dir_env_var_override(self, monkeypatch) -> None:
        import backend.config
        from pathlib import Path
        monkeypatch.setenv("STARFARER_DATA_DIR", "/tmp/test_starfarer_data_override")
        importlib.reload(backend.config)
        assert backend.config.DATA_DIR == Path("/tmp/test_starfarer_data_override")
        assert backend.config.DB_PATH == Path("/tmp/test_starfarer_data_override/starfarer.db")
        monkeypatch.delenv("STARFARER_DATA_DIR", raising=False)
        importlib.reload(backend.config)

    def test_data_dir_exists(self) -> None:
        from backend.config import DATA_DIR
        assert DATA_DIR.exists()
        assert DATA_DIR.is_dir()


class TestDatabaseMigrations:
    def test_migrations_list_structure(self) -> None:
        from backend.database import MIGRATIONS
        assert isinstance(MIGRATIONS, list)
        assert len(MIGRATIONS) > 0
        for migration in MIGRATIONS:
            assert len(migration) == 2
            assert isinstance(migration[0], int)
            assert isinstance(migration[1], str)

    def test_run_migrations_creates_schema_version(self) -> None:
        from backend.database import init_db, run_migrations, get_db
        init_db()
        run_migrations()
        conn = get_db()
        try:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
            assert row is not None
            assert row[0] >= 1
        finally:
            conn.close()

    def test_run_migrations_is_idempotent(self) -> None:
        from backend.database import init_db, run_migrations, get_db
        init_db()
        run_migrations()
        run_migrations()
        conn = get_db()
        try:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
            assert row is not None
            assert row[0] >= 1
        finally:
            conn.close()

    def test_run_migrations_records_current_version(self) -> None:
        from backend.database import init_db, run_migrations, get_db
        init_db()
        run_migrations()
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            ).fetchone()
            assert row is not None
            from backend.database import MIGRATIONS
            assert row["version"] == MIGRATIONS[-1][0]
        finally:
            conn.close()

    def test_run_migrations_without_init_db(self, tmp_path) -> None:
        from backend.database import run_migrations
        import sqlite3

        db_path = tmp_path / "test_clean.db"
        with patch("backend.database.DB_PATH", db_path), \
             patch("backend.database.DATA_DIR", tmp_path):
            run_migrations()

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()
            assert row is not None
            assert row[0] >= 1
        finally:
            conn.close()

    def test_run_migrations_closes_connection(self) -> None:
        from backend.database import run_migrations

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = [0]

        with patch("backend.database.get_db", return_value=mock_conn):
            run_migrations()

        mock_conn.close.assert_called_once()

    def test_run_migrations_closes_on_exception(self) -> None:
        from backend.database import run_migrations

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = RuntimeError("Simulated DB error")

        with patch("backend.database.get_db", return_value=mock_conn):
            try:
                run_migrations()
            except RuntimeError:
                pass

        mock_conn.close.assert_called_once()


class TestMainLifespan:
    def test_lifespan_calls_run_migrations(self) -> None:
        from backend.main import app, lifespan

        async def test() -> None:
            with patch("backend.main.run_migrations") as mock_rm:
                async with lifespan(app):
                    mock_rm.assert_called_once()

        asyncio.run(test())

    def test_lifespan_creates_save_directory(self) -> None:
        from backend.main import app, lifespan

        async def test() -> None:
            async with lifespan(app):
                from backend.config import DATA_DIR
                assert (DATA_DIR / "save").exists()

        asyncio.run(test())
