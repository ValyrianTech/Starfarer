"""Tests for the served HOWTOPLAY.md documentation and version metadata.

Covers the unauthenticated ``GET /HOWTOPLAY.md`` and ``GET /api/howtoplay``
endpoints, the ``commit`` field on ``GET /api/health``, the lifespan boot
hook, and the ``backend.version`` helpers that resolve the deployed commit
SHA.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend import version
from backend.api import routes
from backend.main import app

client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestHowToPlayEndpoints:
    def test_root_howtoplay_returns_markdown(self) -> None:
        resp = client.get("/HOWTOPLAY.md")
        assert resp.status_code == 200
        content_type = resp.headers["content-type"]
        assert content_type.startswith("text/markdown")
        assert "charset=utf-8" in content_type
        expected = (REPO_ROOT / "HOWTOPLAY.md").read_text(encoding="utf-8")
        assert resp.content.decode("utf-8") == expected
        assert len(resp.content) > 0

    def test_api_howtoplay_matches_root_body(self) -> None:
        root = client.get("/HOWTOPLAY.md")
        alias = client.get("/api/howtoplay")
        assert root.status_code == 200
        assert alias.status_code == 200
        assert alias.content == root.content

    def test_endpoints_unauthenticated_with_enforcement_on(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        root = client.get("/HOWTOPLAY.md")
        alias = client.get("/api/howtoplay")
        assert root.status_code == 200
        assert alias.status_code == 200
        assert alias.content == root.content


class TestHealthCommit:
    def test_health_includes_commit_key(self) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "commit" in body
        assert body["status"] == "ok"

    def test_health_commit_none_when_git_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(routes, "resolve_commit_sha", lambda: None)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["commit"] is None


class TestVersionModule:
    def test_get_commit_sha_is_str_or_none(self) -> None:
        sha = version.get_commit_sha()
        assert sha is None or isinstance(sha, str)

    def test_get_commit_sha_none_when_run_raises(self, monkeypatch) -> None:
        monkeypatch.setattr(
            version.subprocess,
            "run",
            MagicMock(side_effect=FileNotFoundError("git not found")),
        )
        assert version.get_commit_sha() is None

    def test_get_commit_sha_none_when_returncode_nonzero(self, monkeypatch) -> None:
        completed = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--short", "HEAD"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )
        monkeypatch.setattr(version.subprocess, "run", MagicMock(return_value=completed))
        assert version.get_commit_sha() is None

    def test_get_commit_sha_none_when_stdout_empty(self, monkeypatch) -> None:
        completed = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--short", "HEAD"],
            returncode=0,
            stdout="\n",
            stderr="",
        )
        monkeypatch.setattr(version.subprocess, "run", MagicMock(return_value=completed))
        assert version.get_commit_sha() is None

    def test_get_commit_sha_strips_stdout_on_success(self, monkeypatch) -> None:
        completed = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--short", "HEAD"],
            returncode=0,
            stdout="  abc1234\n",
            stderr="",
        )
        monkeypatch.setattr(version.subprocess, "run", MagicMock(return_value=completed))
        assert version.get_commit_sha() == "abc1234"

    def test_resolve_commit_sha_caches(self, monkeypatch) -> None:
        version.reset_commit_sha_cache()
        completed = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--short", "HEAD"],
            returncode=0,
            stdout="abc1234\n",
            stderr="",
        )
        mock_run = MagicMock(return_value=completed)
        monkeypatch.setattr(version.subprocess, "run", mock_run)
        first = version.resolve_commit_sha()
        second = version.resolve_commit_sha()
        assert first == "abc1234"
        assert second == "abc1234"
        assert mock_run.call_count == 1
        version.reset_commit_sha_cache()

    def test_reset_commit_sha_cache_forces_re_resolution(self, monkeypatch) -> None:
        version.reset_commit_sha_cache()
        completed = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--short", "HEAD"],
            returncode=0,
            stdout="abc1234\n",
            stderr="",
        )
        mock_run = MagicMock(return_value=completed)
        monkeypatch.setattr(version.subprocess, "run", mock_run)
        version.resolve_commit_sha()
        assert mock_run.call_count == 1
        version.reset_commit_sha_cache()
        version.resolve_commit_sha()
        assert mock_run.call_count == 2
        version.reset_commit_sha_cache()

    def test_ensure_howtoplay_exists_returns_path(self) -> None:
        assert version.ensure_howtoplay_exists() == version.HOWTOPLAY_PATH

    def test_ensure_howtoplay_exists_raises_when_missing(self, monkeypatch) -> None:
        missing = Path("/nonexistent/definitely/missing/HOWTOPLAY.md")
        monkeypatch.setattr(version, "HOWTOPLAY_PATH", missing)
        with pytest.raises(RuntimeError):
            version.ensure_howtoplay_exists()

    def test_repo_root_howtoplay_path_sanity(self) -> None:
        assert version.REPO_ROOT / "HOWTOPLAY.md" == version.HOWTOPLAY_PATH


class TestLifespan:
    def test_lifespan_runs_without_error(self) -> None:
        from backend.main import lifespan

        async def run_lifespan() -> None:
            async with lifespan(app):
                pass

        asyncio.run(run_lifespan())
