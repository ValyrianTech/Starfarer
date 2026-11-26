"""Uniformity + documentation tests for the standard API response envelope.

Every mutating endpoint returns its human-readable outcome under the top-level
``result`` key and error text under ``detail``. There is no top-level
``message`` key. These tests lock that contract in so a future endpoint cannot
silently regress the agent-facing integration surface (see issue github-214).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from backend.game.manager import GAME_STORE
from backend.main import app
from backend.models.discovery import Discovery

client = TestClient(app)


def _new_game(game_id: str) -> str:
    """Create a fresh game and return its id."""
    resp = client.post("/api/game/new", json={"seed": 42, "game_id": game_id})
    assert resp.status_code == 200
    return resp.json()["game_id"]


def _assert_result(resp) -> dict:
    """Assert a 200 response carries a non-empty top-level ``result`` string."""
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert isinstance(data["result"], str)
    assert data["result"].strip()
    return data


class TestMutatingEndpointResultEnvelope:
    """Every mutating endpoint that returns 200 must include a non-empty result."""

    def test_new_game_returns_result(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "env-new-game"})
        data = _assert_result(resp)
        assert data["game_id"] == "env-new-game"

    def test_save_returns_result(self) -> None:
        game_id = _new_game("env-save")
        data = _assert_result(client.post(f"/api/game/{game_id}/save"))
        assert data["game_id"] == game_id

    def test_load_returns_result(self) -> None:
        game_id = _new_game("env-load")
        assert client.post(f"/api/game/{game_id}/save").status_code == 200
        _assert_result(client.post(f"/api/game/{game_id}/load"))

    def test_dismiss_hint_returns_result(self) -> None:
        game_id = _new_game("env-dismiss")
        data = _assert_result(
            client.post(f"/api/game/{game_id}/hints/dismiss", json={"hint_id": "no_such_hint"})
        )
        assert "dismissed" in data["result"].lower()

    def test_jump_returns_result(self) -> None:
        game_id = _new_game("env-jump")
        nearby = client.get(f"/api/game/{game_id}/nearby").json()
        reachable = [n for n in nearby["nearby"] if n["reachable"]]
        assert reachable, "expected at least one reachable system"
        data = _assert_result(client.post(f"/api/game/{game_id}/jump/{reachable[0]['id']}"))
        assert "current_system" in data

    def test_scan_returns_result(self) -> None:
        game_id = _new_game("env-scan")
        _assert_result(client.post(f"/api/game/{game_id}/scan"))

    def test_land_and_explore_return_result(self) -> None:
        game_id = _new_game("env-land")
        state = GAME_STORE[game_id]
        sys_detail = client.get(f"/api/game/{game_id}/system/{state.ship.current_system_id}").json()
        planets = [b for b in sys_detail["system"]["bodies"] if b["body_type"] == "planet"]
        assert planets, "expected the starting system to contain a planet"
        land = _assert_result(client.post(f"/api/game/{game_id}/land/{planets[0]['id']}"))
        assert "current_body_id" in land
        explore = _assert_result(client.post(f"/api/game/{game_id}/explore"))
        assert "discoveries" in explore

    def test_trade_returns_result(self) -> None:
        game_id = _new_game("env-trade")
        state = GAME_STORE[game_id]
        state.get_current_system().has_trading_station = True
        data = _assert_result(
            client.post(f"/api/game/{game_id}/trade", json={"action": "buy", "item": "fuel", "quantity": 1})
        )
        assert "ship" in data

    def test_bulk_sell_returns_result_and_trade_result(self) -> None:
        game_id = _new_game("env-bulk-sell")
        state = GAME_STORE[game_id]
        cur = state.get_current_system()
        cur.has_trading_station = True
        state.discoveries.append(
            Discovery(
                id="env-bulk-disc-1",
                category="artifact",
                name="Envelope Relic",
                description="Relic",
                value=200,
                system_id=cur.id,
            )
        )
        GAME_STORE[game_id] = state
        data = _assert_result(
            client.post(
                f"/api/game/{game_id}/trade/bulk-sell",
                json={"items": [{"item": "artifact", "quantity": 1}]},
            )
        )
        assert "trade_result" in data
        assert data["result"] == data["trade_result"]["message"]

    def test_upgrade_returns_result(self) -> None:
        game_id = _new_game("env-upgrade")
        upgrades = client.get(f"/api/game/{game_id}/upgrades").json()
        assert upgrades["upgrades"], "expected at least one purchasable upgrade"
        upgrade_id = upgrades["upgrades"][0]["id"]
        data = _assert_result(
            client.post(f"/api/game/{game_id}/upgrade", json={"upgrade_id": upgrade_id})
        )
        assert "ship" in data


class TestResponseEnvelopeDocumentation:
    """The served docs and OpenAPI description state the envelope clearly."""

    def test_howtoplay_documents_envelope(self) -> None:
        text = client.get("/HOWTOPLAY.md").content.decode("utf-8")
        assert "`result`" in text
        assert "`detail`" in text
        lowered = text.lower()
        assert "no `message`" in lowered or "no message" in lowered

    def test_openapi_description_documents_envelope(self) -> None:
        description = app.openapi()["info"]["description"]
        assert "result" in description
        assert "detail" in description
