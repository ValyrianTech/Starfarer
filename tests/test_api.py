import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db() -> None:
    init_db()


class TestAPIHealth:
    def test_health(self) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["version"] == "0.1.0"


class TestAPIGameCreation:
    def test_create_game_default(self) -> None:
        resp = client.post("/api/game/new", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "game_id" in data
        assert data["state"]["ship"]["name"] == "Serendipity"

    def test_create_game_custom(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 999, "ship_name": "Voyager"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"]["ship"]["name"] == "Voyager"
        assert data["state"]["seed"] == 999

    def test_create_game_with_custom_id(self) -> None:
        resp = client.post("/api/game/new", json={"game_id": "test-game-id"})
        assert resp.status_code == 200
        assert resp.json()["game_id"] == "test-game-id"


class TestAPIGameFlow:
    def test_full_game_flow(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        state = resp.json()
        assert "ship" in state
        cur_sys = state["ship"]["current_system_id"]

        resp = client.get(f"/api/game/{game_id}/galaxy")
        assert resp.status_code == 200
        galaxy = resp.json()
        assert len(galaxy["systems"]) == 50

        resp = client.get(f"/api/game/{game_id}/system/{cur_sys}")
        assert resp.status_code == 200
        sys_detail = resp.json()
        assert sys_detail["system"]["id"] == cur_sys

        resp = client.post(f"/api/game/{game_id}/scan")
        assert resp.status_code == 200

        resp = client.get(f"/api/game/{game_id}/nearby")
        assert resp.status_code == 200
        nearby = resp.json()
        assert len(nearby["nearby"]) == 49

        planets = [b for b in sys_detail["system"]["bodies"] if b["body_type"] == "planet"]
        if planets:
            resp = client.post(f"/api/game/{game_id}/land/{planets[0]['id']}")
            assert resp.status_code == 200

            resp = client.post(f"/api/game/{game_id}/explore")
            assert resp.status_code == 200
            expl = resp.json()
            assert len(expl["discoveries"]) > 0

        resp = client.get(f"/api/game/{game_id}/log")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 2

        resp = client.get(f"/api/game/{game_id}/discoveries")
        assert resp.status_code == 200

        resp = client.post(f"/api/game/{game_id}/save")
        assert resp.status_code == 200
        assert "saved" in resp.json()["result"].lower() or "Saved" in resp.json()["result"]

        resp = client.post(f"/api/game/{game_id}/load")
        assert resp.status_code == 200
        assert "loaded" in resp.json()["result"].lower() or "Loaded" in resp.json()["result"]


class TestAPIEdgeCases:
    def test_nonexistent_game(self) -> None:
        resp = client.get("/api/game/nonexistent")
        assert resp.status_code == 404

    def test_nonexistent_system(self) -> None:
        resp = client.post("/api/game/new", json={})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/system/fake_sys")
        assert resp.status_code == 404

    def test_jump_to_nonexistent_system(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/jump/fake_sys")
        assert resp.status_code == 404

    def test_buy_fuel(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/game/{game_id}/trade", json={
            "action": "buy", "item": "fuel", "quantity": 10
        })
        assert resp.status_code in (200, 400)

    def test_upgrade_info(self) -> None:
        resp = client.post("/api/game/new", json={})
        game_id = resp.json()["game_id"]
        resp = client.get(f"/api/game/{game_id}/upgrades")
        assert resp.status_code == 200
        assert len(resp.json()["upgrades"]) > 0

    def test_leaderboard(self) -> None:
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        assert "leaderboard" in resp.json()
