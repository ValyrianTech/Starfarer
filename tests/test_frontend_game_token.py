import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from backend.config import get_require_game_token
from backend.main import app

client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_JS = REPO_ROOT / "frontend" / "js"


def _read(relative: str) -> str:
    """Read a frontend JS source file as text."""
    return (FRONTEND_JS / relative).read_text()


class TestFrontendTokenHelpers:
    """The reference frontend must define localStorage-backed token helpers."""

    def test_utils_defines_get_game_token(self) -> None:
        content = _read("utils.js")
        assert "function getGameToken" in content
        assert "starfarer_game_token" in content
        assert "localStorage.getItem" in content

    def test_utils_defines_set_game_token(self) -> None:
        content = _read("utils.js")
        assert "function setGameToken" in content
        start = content.index("function setGameToken")
        region = content[start : start + 400]
        assert "localStorage.setItem" in region
        assert "starfarer_game_token" in region
        assert "localStorage.removeItem" in region
        assert "try" in region
        assert "catch" in region

    def test_token_key_matches_webui(self) -> None:
        frontend_utils = _read("utils.js")
        webui_api = (REPO_ROOT / "webui" / "js" / "api.js").read_text()
        assert "starfarer_game_token" in frontend_utils
        assert "starfarer_game_token" in webui_api


class TestFrontendApiCallSendsToken:
    """apiCall must attach the per-game token as an X-Game-Token header."""

    def test_api_call_adds_x_game_token_header(self) -> None:
        content = _read("api.js")
        assert "X-Game-Token" in content
        assert "getGameToken()" in content
        assert "if (token)" in content

    def test_api_call_still_sets_content_type(self) -> None:
        content = _read("api.js")
        assert "Content-Type" in content
        assert "application/json" in content

    def test_apicall_header_logic_simulation(self) -> None:
        def build_headers(token):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["X-Game-Token"] = token
            return headers

        assert build_headers(None) == {"Content-Type": "application/json"}
        assert build_headers("") == {"Content-Type": "application/json"}
        assert build_headers("abc") == {
            "Content-Type": "application/json",
            "X-Game-Token": "abc",
        }

        content = _read("api.js")
        assert "if (token) {" in content
        assert "headers['X-Game-Token'] = token" in content


class TestFrontendMainStoresToken:
    """main.js must persist the token returned by POST /api/game/new."""

    def test_new_game_branch_persists_token(self) -> None:
        content = _read("main.js")
        assert "setGameToken(data.token)" in content
        assert "if (data.token)" in content
        assert content.index("setGameId(GAME_ID)") < content.index(
            "setGameToken(data.token)"
        )

    def test_new_game_reads_token_field(self) -> None:
        content = _read("main.js")
        assert "data.token" in content


class TestFrontendTokenContract:
    """Backend contract: /api/game/new issues a token, and game endpoints
    enforce it via the X-Game-Token header when enforcement is on."""

    def test_new_game_returns_token_field(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 7})
        assert resp.status_code == 200
        token = resp.json().get("token")
        assert isinstance(token, str)
        assert token

    def test_galaxy_requires_header_when_enforced(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        assert get_require_game_token() is True

        resp = client.post("/api/game/new", json={"seed": 7})
        gid = resp.json()["game_id"]
        token = resp.json()["token"]

        resp = client.get(f"/api/game/{gid}/galaxy")
        assert resp.status_code == 403

        resp = client.get(
            f"/api/game/{gid}/galaxy", headers={"X-Game-Token": token}
        )
        assert resp.status_code == 200

    def test_header_with_wrong_token_is_403(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_REQUIRE_GAME_TOKEN", "1")
        monkeypatch.delenv("STARFARER_ALLOW_NO_AUTH", raising=False)
        assert get_require_game_token() is True

        resp = client.post("/api/game/new", json={"seed": 7})
        gid = resp.json()["game_id"]

        resp = client.get(
            f"/api/game/{gid}/galaxy", headers={"X-Game-Token": "wrong-token"}
        )
        assert resp.status_code == 403
