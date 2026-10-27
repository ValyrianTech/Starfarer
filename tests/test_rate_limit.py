import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from starlette.requests import Request

from fastapi.testclient import TestClient

from backend.api import routes
from backend.config import (
    get_max_stored_games,
    get_new_game_rate_limit,
    get_new_game_rate_window,
)
from backend.database import count_games, create_game
from backend.game import manager
from backend.main import app


class TestClientIp:
    def test_client_ip_returns_host(self) -> None:
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("10.0.0.1", 1234),
        })
        assert routes._client_ip(request) == "10.0.0.1"

    def test_client_ip_falls_back_when_no_client(self) -> None:
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
        })
        assert routes._client_ip(request) == "unknown"


class TestNewGameRateLimit:
    def test_rate_limit_triggers_429_with_retry_after(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "2")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_WINDOW", "60")
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "0")
        client = TestClient(app, client=("10.0.0.1", 1234))
        assert client.post("/api/game/new", json={}).status_code == 200
        assert client.post("/api/game/new", json={}).status_code == 200
        resp = client.post("/api/game/new", json={})
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") is not None
        assert int(resp.headers["retry-after"]) >= 1

    def test_unlimited_rate_limit_never_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "0")
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "0")
        client = TestClient(app, client=("10.0.0.2", 1234))
        for _ in range(5):
            resp = client.post("/api/game/new", json={})
            assert resp.status_code == 200

    def test_rate_limiter_ip_capacity_pruning(self, monkeypatch) -> None:
        monkeypatch.setattr(routes, "_MAX_RATE_LIMIT_IPS", 2)
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "100")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_WINDOW", "60")
        for i in range(3):
            routes._check_new_game_rate_limit(f"ip{i}")
        assert len(routes._new_game_rate_entries) == 2
        assert "ip0" not in routes._new_game_rate_entries


class TestEvictOldestRateLimitEntry:
    def test_empty_list_evicted_first(self, monkeypatch) -> None:
        routes.reset_new_game_rate_limiter()
        routes._new_game_rate_entries = {
            "empty": [],
            "active": [1.0, 2.0, 3.0],
        }
        routes._evict_oldest_rate_limit_entry()
        assert "empty" not in routes._new_game_rate_entries
        assert "active" in routes._new_game_rate_entries

    def test_empty_list_evicted_among_multiple_empty(self, monkeypatch) -> None:
        routes.reset_new_game_rate_limiter()
        routes._new_game_rate_entries = {
            "empty-a": [],
            "empty-b": [],
            "active": [100.0],
        }
        routes._evict_oldest_rate_limit_entry()
        assert len(routes._new_game_rate_entries) == 2
        assert "active" in routes._new_game_rate_entries
        remaining = set(routes._new_game_rate_entries) - {"active"}
        assert remaining & {"empty-a", "empty-b"} == remaining
        assert remaining

    def test_empty_entry_evicted_end_to_end_at_capacity(self, monkeypatch) -> None:
        routes.reset_new_game_rate_limiter()
        monkeypatch.setattr(routes, "_MAX_RATE_LIMIT_IPS", 2)
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "100")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_WINDOW", "60")
        routes._new_game_rate_entries = {
            "empty": [],
            "active": [1.0],
        }
        routes._check_new_game_rate_limit("new-ip")
        assert len(routes._new_game_rate_entries) == 2
        assert "empty" not in routes._new_game_rate_entries
        assert "new-ip" in routes._new_game_rate_entries
        assert "active" in routes._new_game_rate_entries


class TestStoredGameCap:
    def test_stored_game_cap_returns_429(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "10")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "0")
        monkeypatch.setattr(routes, "count_games", lambda: 10)
        client = TestClient(app)
        resp = client.post("/api/game/new", json={})
        assert resp.status_code == 429

    def test_cap_rejection_does_not_touch_game_store(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "10")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "0")
        monkeypatch.setattr(routes, "count_games", lambda: 10)
        before = dict(manager.GAME_STORE)
        client = TestClient(app, client=("10.0.0.99", 1234))
        resp = client.post("/api/game/new", json={})
        assert resp.status_code == 429
        assert manager.GAME_STORE == before
        assert manager.GAME_STORE.keys() == before.keys()
        assert all(manager.GAME_STORE[k] is v for k, v in before.items())

    def test_unlimited_stored_games_never_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "0")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "0")
        routes._enforce_stored_game_cap()


class TestCountGames:
    def test_count_games(self) -> None:
        before = count_games()
        create_game(
            "count-games-test-id",
            42,
            "CountShip",
            {"seed": 42, "ship": {"name": "CountShip"}},
        )
        assert count_games() == before + 1


class TestConfigGetters:
    def test_defaults(self, monkeypatch) -> None:
        monkeypatch.delenv("STARFARER_NEW_GAME_RATE_LIMIT", raising=False)
        monkeypatch.delenv("STARFARER_NEW_GAME_RATE_WINDOW", raising=False)
        monkeypatch.delenv("STARFARER_MAX_STORED_GAMES", raising=False)
        assert get_new_game_rate_limit() == 30
        assert get_new_game_rate_window() == 60.0
        assert get_max_stored_games() == 100000

    def test_valid_values(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "5")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_WINDOW", "2.5")
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "123")
        assert get_new_game_rate_limit() == 5
        assert get_new_game_rate_window() == 2.5
        assert get_max_stored_games() == 123

    def test_invalid_values(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "abc")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_WINDOW", "not-a-float")
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "xyz")
        assert get_new_game_rate_limit() == 30
        assert get_new_game_rate_window() == 60.0
        assert get_max_stored_games() == 100000

    def test_empty_values(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "   ")
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_WINDOW", "")
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "  ")
        assert get_new_game_rate_limit() == 30
        assert get_new_game_rate_window() == 60.0
        assert get_max_stored_games() == 100000

    def test_zero_and_negative_semantics(self, monkeypatch) -> None:
        monkeypatch.setenv("STARFARER_NEW_GAME_RATE_LIMIT", "0")
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "0")
        assert get_new_game_rate_limit() == 0
        assert get_max_stored_games() == 0
        monkeypatch.setenv("STARFARER_MAX_STORED_GAMES", "-5")
        assert get_max_stored_games() == -5


class TestSharedUniverseCaching:
    def test_shared_universe_generated_once(self, monkeypatch) -> None:
        calls = {"n": 0}
        original = manager.generate_universe

        def counting(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(manager, "generate_universe", counting)
        manager.reset_shared_universe_cache()
        manager.new_game(seed=42)
        manager.new_game(seed=42)
        assert calls["n"] == 1

    def test_shared_universe_systems_are_independent(self) -> None:
        manager.reset_shared_universe_cache()
        game1 = manager.new_game(seed=42)
        game2 = manager.new_game(seed=42)
        sys_id = game1.ship.current_system_id
        sys1 = game1.systems[sys_id]
        sys2 = game2.systems[sys_id]
        assert sys1 is not sys2
        sys1.visited = False
        assert sys2.visited is True
        assert sys1.bodies is not sys2.bodies
        if sys1.bodies:
            sys1.bodies[0].poi_count = 12345
            assert sys2.bodies[0].poi_count != 12345

    def test_reset_shared_universe_cache(self, monkeypatch) -> None:
        calls = {"n": 0}
        original = manager.generate_universe

        def counting(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(manager, "generate_universe", counting)
        manager.reset_shared_universe_cache()
        manager.new_game(seed=42)
        assert calls["n"] == 1
        manager.reset_shared_universe_cache()
        manager.new_game(seed=42)
        assert calls["n"] == 2

    def test_non_shared_seed_still_generates(self, monkeypatch) -> None:
        calls = {"n": 0}
        original = manager.generate_universe

        def counting(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(manager, "generate_universe", counting)
        manager.reset_shared_universe_cache()
        manager.new_game(seed=123, shared_universe=False)
        assert calls["n"] == 1
