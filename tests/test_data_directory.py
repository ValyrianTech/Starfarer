import asyncio
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        from pathlib import Path

        import backend.config
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
        from backend.database import get_db, init_db, run_migrations
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
        from backend.database import get_db, init_db, run_migrations
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
        from backend.database import get_db, init_db, run_migrations
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
        import sqlite3

        from backend.database import run_migrations

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


class TestDatabaseSaveHistory:
    def _cleanup(self, game_id: str) -> None:
        from backend.database import get_db
        conn = get_db()
        try:
            conn.execute("DELETE FROM saves WHERE game_id = ?", (game_id,))
            conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
            conn.commit()
        finally:
            conn.close()

    def test_two_consecutive_saves_keep_two_rows(self) -> None:
        from backend.database import get_db, init_db, save_game
        game_id = "save-history-test-1"
        self._cleanup(game_id)
        init_db()
        state_a = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 10}
        state_b = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 20}
        try:
            save_game(game_id, state_a)
            save_game(game_id, state_b)
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM saves WHERE game_id = ?", (game_id,)
                ).fetchone()
                assert row[0] == 2
            finally:
                conn.close()
        finally:
            self._cleanup(game_id)

    def test_three_consecutive_saves_keep_three_rows(self) -> None:
        from backend.database import get_db, init_db, save_game
        game_id = "save-history-test-2"
        self._cleanup(game_id)
        init_db()
        state_a = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 10}
        state_b = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 20}
        state_c = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 30}
        try:
            save_game(game_id, state_a)
            save_game(game_id, state_b)
            save_game(game_id, state_c)
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM saves WHERE game_id = ?", (game_id,)
                ).fetchone()
                assert row[0] == 3
            finally:
                conn.close()
        finally:
            self._cleanup(game_id)

    def test_save_game_preserves_created_at(self) -> None:
        from backend.database import get_db, init_db, save_game
        game_id = "save-history-test-3"
        self._cleanup(game_id)
        init_db()
        state_a = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 10}
        state_b = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 20}
        try:
            save_game(game_id, state_a)
            conn = get_db()
            try:
                created_at_first = conn.execute(
                    "SELECT created_at FROM games WHERE id = ?", (game_id,)
                ).fetchone()["created_at"]
            finally:
                conn.close()
            save_game(game_id, state_b)
            conn = get_db()
            try:
                created_at_second = conn.execute(
                    "SELECT created_at FROM games WHERE id = ?", (game_id,)
                ).fetchone()["created_at"]
            finally:
                conn.close()
            assert created_at_first == created_at_second
        finally:
            self._cleanup(game_id)

    def test_load_save_returns_most_recent(self) -> None:
        from backend.database import init_db, load_save, save_game
        game_id = "save-history-test-4"
        self._cleanup(game_id)
        init_db()
        state_a = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 10}
        state_b = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 20}
        try:
            save_game(game_id, state_a)
            save_game(game_id, state_b)
            assert load_save(game_id) == state_b
        finally:
            self._cleanup(game_id)

    def test_create_game_upsert_does_not_delete_saves(self) -> None:
        from backend.database import create_game, get_db, init_db, save_game
        game_id = "save-history-test-5"
        self._cleanup(game_id)
        init_db()
        state_a = {"seed": 1, "ship": {"name": "Test Ship"}, "credits": 10}
        state_c = {"seed": 7, "ship": {"name": "Upsert Ship"}, "credits": 30}
        try:
            save_game(game_id, state_a)
            create_game(game_id, seed=7, ship_name="Upsert Ship", state=state_c)
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM saves WHERE game_id = ?", (game_id,)
                ).fetchone()
                assert row[0] == 1
            finally:
                conn.close()
        finally:
            self._cleanup(game_id)
