import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game, game_save, game_load
from backend.hints import (
    Hint,
    HINT_DEFINITIONS,
    get_contextual_hints,
    _fuel_zero,
    _fuel_critical,
    _fuel_low_no_station,
    _first_uncharted,
    _hull_low,
    _cargo_full,
    _first_crisis,
    _morale_low,
    _format_message,
)
from backend.models.game_state import GameState
from backend.models.event import Event, Choice
from backend.config import INITIAL_FUEL, INITIAL_HULL, INITIAL_CARGO, INITIAL_CREW, INITIAL_MORALE

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db() -> None:
    init_db()


def _make_game(seed: int = 42) -> GameState:
    state = new_game(seed=seed)
    return state


class TestConditionFunctions:
    def test_fuel_zero_true(self) -> None:
        state = _make_game()
        state.ship.fuel = 0
        assert _fuel_zero(state, state.systems) is True

    def test_fuel_zero_false(self) -> None:
        state = _make_game()
        state.ship.fuel = 5
        assert _fuel_zero(state, state.systems) is False

    def test_fuel_critical_low(self) -> None:
        state = _make_game()
        state.ship.fuel = 1
        assert _fuel_critical(state, state.systems) is True

    def test_fuel_critical_upper_bound(self) -> None:
        state = _make_game()
        state.ship.fuel = 4
        assert _fuel_critical(state, state.systems) is True

    def test_fuel_critical_at_5(self) -> None:
        state = _make_game()
        state.ship.fuel = 5
        assert _fuel_critical(state, state.systems) is False

    def test_fuel_critical_zero(self) -> None:
        state = _make_game()
        state.ship.fuel = 0
        assert _fuel_critical(state, state.systems) is False

    def test_fuel_low_no_station_trigger(self) -> None:
        state = _make_game()
        state.ship.fuel = 7
        current = state.get_current_system()
        current.has_trading_station = False
        assert _fuel_low_no_station(state, state.systems) is True

    def test_fuel_low_no_station_fuel_ok(self) -> None:
        state = _make_game()
        state.ship.fuel = 20
        current = state.get_current_system()
        current.has_trading_station = False
        assert _fuel_low_no_station(state, state.systems) is False

    def test_fuel_low_no_station_has_station(self) -> None:
        state = _make_game()
        state.ship.fuel = 5
        current = state.get_current_system()
        current.has_trading_station = True
        assert _fuel_low_no_station(state, state.systems) is False

    def test_fuel_low_no_station_no_current_system(self) -> None:
        """When fuel < 10 and current system is None, should return False."""
        state = _make_game()
        state.ship.current_system_id = "nonexistent"
        state.ship.fuel = 8
        assert _fuel_low_no_station(state, state.systems) is False

    def test_fuel_low_no_station_negative_fuel(self) -> None:
        state = _make_game()
        state.ship.fuel = -5
        assert _fuel_low_no_station(state, state.systems) is False

    def test_first_uncharted_trigger(self) -> None:
        state = _make_game()
        state.systems_visited = 2
        current = state.get_current_system()
        current.visited = False
        current.has_trading_station = False
        assert _first_uncharted(state, state.systems) is True

    def test_first_uncharted_not_visited_2(self) -> None:
        state = _make_game()
        state.systems_visited = 3
        current = state.get_current_system()
        current.visited = False
        current.has_trading_station = False
        assert _first_uncharted(state, state.systems) is False

    def test_first_uncharted_has_station(self) -> None:
        state = _make_game()
        state.systems_visited = 2
        current = state.get_current_system()
        current.visited = False
        current.has_trading_station = True
        assert _first_uncharted(state, state.systems) is False

    def test_hull_low_true(self) -> None:
        state = _make_game()
        state.ship.hull = 10
        assert _hull_low(state, state.systems) is True

    def test_hull_low_false(self) -> None:
        state = _make_game()
        state.ship.hull = 80
        assert _hull_low(state, state.systems) is False

    def test_hull_low_boundary(self) -> None:
        state = _make_game()
        state.ship.hull = 24
        assert _hull_low(state, state.systems) is True

        state.ship.hull = 25
        assert _hull_low(state, state.systems) is False

    def test_cargo_full_true(self) -> None:
        state = _make_game()
        state.ship.cargo = 45
        state.ship.max_cargo = 50
        assert _cargo_full(state, state.systems) is True

    def test_cargo_full_false(self) -> None:
        state = _make_game()
        state.ship.cargo = 30
        state.ship.max_cargo = 50
        assert _cargo_full(state, state.systems) is False

    def test_cargo_full_zero_capacity(self) -> None:
        state = _make_game()
        state.ship.max_cargo = 0
        assert _cargo_full(state, state.systems) is False

    def test_cargo_full_exactly_80_percent(self) -> None:
        state = _make_game()
        state.ship.cargo = 40
        state.ship.max_cargo = 50
        assert _cargo_full(state, state.systems) is False

    def test_first_crisis_no_events(self) -> None:
        state = _make_game()
        assert _first_crisis(state, state.systems) is False

    def test_first_crisis_with_crisis_event(self) -> None:
        state = _make_game()
        crisis = Event(
            id="crisis_001",
            title="Crisis Event",
            flavor="A crisis occurs!",
            event_type="crisis",
            choices=[Choice(text="Fix it", outcome="fuel:-5")],
            resolved=False,
        )
        state.events.append(crisis)
        assert _first_crisis(state, state.systems) is True

    def test_first_crisis_already_in_log(self) -> None:
        state = _make_game()
        state.add_log("crisis", "A crisis happened.", category="crisis", title="Crisis Event")
        crisis = Event(
            id="crisis_001",
            title="Crisis Event",
            flavor="A crisis occurs!",
            event_type="crisis",
            choices=[Choice(text="Fix it", outcome="fuel:-5")],
            resolved=False,
        )
        state.events.append(crisis)
        assert _first_crisis(state, state.systems) is False

    def test_first_crisis_resolved_before_unresolved(self) -> None:
        """When a resolved crisis precedes an unresolved one, should return True."""
        state = _make_game()
        resolved_crisis = Event(
            id="crisis_001",
            title="Hull Breach",
            flavor="A hull breach!",
            event_type="crisis",
            choices=[Choice(text="Patch it", outcome="hull:-15")],
            resolved=True,
        )
        unresolved_crisis = Event(
            id="crisis_002",
            title="Life Support Failure",
            flavor="Life support failing!",
            event_type="crisis",
            choices=[Choice(text="Fix it", outcome="fuel:-5")],
            resolved=False,
        )
        state.events.append(resolved_crisis)
        state.events.append(unresolved_crisis)
        assert _first_crisis(state, state.systems) is True

    def test_first_crisis_unresolved_before_resolved(self) -> None:
        """When an unresolved crisis precedes a resolved one, should return True."""
        state = _make_game()
        unresolved_crisis = Event(
            id="crisis_001",
            title="Life Support Failure",
            flavor="Life support failing!",
            event_type="crisis",
            choices=[Choice(text="Fix it", outcome="fuel:-5")],
            resolved=False,
        )
        resolved_crisis = Event(
            id="crisis_002",
            title="Hull Breach",
            flavor="A hull breach!",
            event_type="crisis",
            choices=[Choice(text="Patch it", outcome="hull:-15")],
            resolved=True,
        )
        state.events.append(unresolved_crisis)
        state.events.append(resolved_crisis)
        assert _first_crisis(state, state.systems) is True

    def test_first_crisis_all_resolved(self) -> None:
        """When all crisis events are resolved, should return False."""
        state = _make_game()
        crisis1 = Event(
            id="crisis_001",
            title="Hull Breach",
            flavor="A hull breach!",
            event_type="crisis",
            choices=[Choice(text="Patch it", outcome="hull:-15")],
            resolved=True,
        )
        crisis2 = Event(
            id="crisis_002",
            title="Fire",
            flavor="Fire on board!",
            event_type="crisis",
            choices=[Choice(text="Extinguish", outcome="hull:-5")],
            resolved=True,
        )
        state.events.append(crisis1)
        state.events.append(crisis2)
        assert _first_crisis(state, state.systems) is False

    def test_morale_low_true(self) -> None:
        state = _make_game()
        state.ship.morale = 20
        assert _morale_low(state, state.systems) is True

    def test_morale_low_false(self) -> None:
        state = _make_game()
        state.ship.morale = 50
        assert _morale_low(state, state.systems) is False

    def test_morale_low_boundary(self) -> None:
        state = _make_game()
        state.ship.morale = 29
        assert _morale_low(state, state.systems) is True

        state.ship.morale = 30
        assert _morale_low(state, state.systems) is False


class TestHintClass:
    def test_hint_attributes(self) -> None:
        hint = Hint(
            hint_id="test_hint",
            severity="warning",
            message_template="Test message",
            condition=lambda gs, s: True,
            command="/test",
            priority=50,
        )
        assert hint.id == "test_hint"
        assert hint.severity == "warning"
        assert hint.message_template == "Test message"
        assert hint.command == "/test"
        assert hint.priority == 50

    def test_hint_evaluate_true(self) -> None:
        state = _make_game()
        hint = Hint(
            hint_id="always_trigger",
            severity="info",
            message_template="Always shows",
            condition=lambda gs, s: True,
        )
        result = hint.evaluate(state, state.systems)
        assert result is not None
        assert result["id"] == "always_trigger"
        assert result["severity"] == "info"
        assert result["message"] == "Always shows"

    def test_hint_evaluate_false(self) -> None:
        state = _make_game()
        hint = Hint(
            hint_id="never_trigger",
            severity="info",
            message_template="Never shows",
            condition=lambda gs, s: False,
        )
        result = hint.evaluate(state, state.systems)
        assert result is None


class TestGetContextualHints:
    def test_no_hints_when_everything_ok(self) -> None:
        state = _make_game()
        hints = get_contextual_hints(state, state.systems)
        assert hints == []

    def test_fuel_zero_returns_critical_hint(self) -> None:
        state = _make_game()
        state.ship.fuel = 0
        hints = get_contextual_hints(state, state.systems)
        assert len(hints) >= 1
        assert hints[0]["id"] == "fuel_zero"
        assert hints[0]["severity"] == "critical"

    def test_fuel_critical_returns_warning(self) -> None:
        state = _make_game()
        state.ship.fuel = 3
        hints = get_contextual_hints(state, state.systems)
        assert any(h["id"] == "fuel_critical" for h in hints)

    def test_hull_low_returns_warning(self) -> None:
        state = _make_game()
        state.ship.hull = 10
        hints = get_contextual_hints(state, state.systems)
        assert any(h["id"] == "hull_low" for h in hints)

    def test_morale_low_returns_warning(self) -> None:
        state = _make_game()
        state.ship.morale = 15
        hints = get_contextual_hints(state, state.systems)
        assert any(h["id"] == "morale_low" for h in hints)

    def test_cargo_full_returns_info(self) -> None:
        state = _make_game()
        state.ship.cargo = 45
        hints = get_contextual_hints(state, state.systems)
        assert any(h["id"] == "cargo_full" for h in hints)

    def test_multiple_hints_returned(self) -> None:
        state = _make_game()
        state.ship.fuel = 3
        state.ship.hull = 10
        state.ship.cargo = 45
        hints = get_contextual_hints(state, state.systems)
        assert len(hints) >= 1

    def test_max_two_hints(self) -> None:
        state = _make_game()
        state.ship.fuel = 3
        state.ship.hull = 10
        state.ship.cargo = 45
        state.ship.morale = 15
        hints = get_contextual_hints(state, state.systems)
        assert len(hints) <= 2

    def test_no_current_system(self) -> None:
        state = _make_game()
        state.ship.current_system_id = ""
        hints = get_contextual_hints(state, state.systems)
        assert isinstance(hints, list)

    def test_fuel_low_no_station_no_current_system(self) -> None:
        """When fuel < 10 and there's no current system, _fuel_low_no_station should return False."""
        state = _make_game()
        state.ship.current_system_id = "nonexistent"
        state.ship.fuel = 8  # Less than 10, so first check passes
        hints = get_contextual_hints(state, state.systems)
        # No hints should be returned since there's no current system
        assert hints == []

    def test_critical_hint_not_dismissible(self) -> None:
        state = _make_game()
        state.ship.fuel = 0
        hints = get_contextual_hints(state, state.systems, dismissed_hints={"fuel_zero"})
        assert len(hints) >= 1
        assert hints[0]["id"] == "fuel_zero"

    def test_non_critical_hint_dismissed(self) -> None:
        state = _make_game()
        state.ship.hull = 10
        hints = get_contextual_hints(state, state.systems, dismissed_hints={"hull_low"})
        assert not any(h["id"] == "hull_low" for h in hints)

    def test_dismissed_hints_none_defaults_to_empty(self) -> None:
        state = _make_game()
        state.ship.hull = 10
        hints = get_contextual_hints(state, state.systems, dismissed_hints=None)
        assert any(h["id"] == "hull_low" for h in hints)

    def test_hints_returned_in_priority_order(self) -> None:
        state = _make_game()
        state.ship.fuel = 3
        state.ship.hull = 10
        hints = get_contextual_hints(state, state.systems)
        assert len(hints) >= 1
        if len(hints) >= 2:
            priorities = {}
            for hint_def in HINT_DEFINITIONS:
                priorities[hint_def.id] = hint_def.priority
            assert priorities[hints[0]["id"]] >= priorities[hints[1]["id"]]


class TestHintDefinitions:
    def test_hints_have_command_or_none(self) -> None:
        for hint in HINT_DEFINITIONS:
            assert hint.command is None or isinstance(hint.command, str)

    def test_hints_have_valid_severity(self) -> None:
        valid_severities = {"critical", "warning", "info", "tip"}
        for hint in HINT_DEFINITIONS:
            assert hint.severity in valid_severities, f"Invalid severity {hint.severity}"

    def test_hints_have_unique_ids(self) -> None:
        ids = [hint.id for hint in HINT_DEFINITIONS]
        assert len(ids) == len(set(ids))

    def test_hint_definitions_ordered_by_priority(self) -> None:
        priorities = [hint.priority for hint in HINT_DEFINITIONS]
        assert priorities == sorted(priorities, reverse=True)


class TestMessageFormatting:
    def test_no_format_needed(self) -> None:
        state = _make_game()
        msg = _format_message("Plain message", state, state.systems)
        assert msg == "Plain message"

    def test_format_with_station(self) -> None:
        state = _make_game()
        state.ship.fuel = 5
        current = state.get_current_system()
        current.has_trading_station = False
        msg = _format_message(
            "Consider heading to a station for refueling. Nearest station: {nearest_station} ({distance} LY)",
            state,
            state.systems,
        )
        assert "{nearest_station}" not in msg
        assert "{distance}" not in msg

    def test_fuel_low_no_station_formatted(self) -> None:
        state = _make_game()
        state.ship.fuel = 5
        current = state.get_current_system()
        current.has_trading_station = False
        hints = get_contextual_hints(state, state.systems)
        fuel_low_hints = [h for h in hints if h["id"] == "fuel_low_no_station"]
        assert len(fuel_low_hints) >= 0

    def test_format_with_no_nearest_station(self) -> None:
        state = _make_game()
        mock_status = {
            "nearest_station_system": None,
            "nearest_station_distance": 0.0,
        }
        with patch("backend.fuel.get_fuel_status", return_value=mock_status):
            msg = _format_message(
                "Nearest station: {nearest_station} ({distance} LY)",
                state,
                state.systems,
            )
        assert "Unknown" in msg
        assert "None" not in msg


class TestHintsInGameStateResponse:
    def test_full_state_includes_hints(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        resp2 = client.get(f"/api/game/{game_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert "hints" in data
        assert isinstance(data["hints"], list)

    def test_full_state_hints_with_low_fuel(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        state = GAME_STORE[game_id]
        state.ship.fuel = 0

        resp2 = client.get(f"/api/game/{game_id}")
        data = resp2.json()
        assert "hints" in data
        hints = data["hints"]
        assert any(h["id"] == "fuel_zero" for h in hints)


class TestDismissHintAPI:
    def test_dismiss_hint(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        resp2 = client.post(
            f"/api/game/{game_id}/hints/dismiss",
            json={"hint_id": "cargo_full"},
        )
        assert resp2.status_code == 200
        assert "dismissed" in resp2.json()["result"]

    def test_dismiss_hint_game_not_found(self) -> None:
        resp = client.post(
            "/api/game/nonexistent/hints/dismiss",
            json={"hint_id": "test"},
        )
        assert resp.status_code == 404

    def test_dismissed_hints_persisted_in_memory(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        state = GAME_STORE[game_id]
        state.ship.hull = 10

        resp2 = client.post(
            f"/api/game/{game_id}/hints/dismiss",
            json={"hint_id": "hull_low"},
        )
        assert resp2.status_code == 200

        resp3 = client.get(f"/api/game/{game_id}")
        data = resp3.json()
        hints = data["hints"]
        assert not any(h["id"] == "hull_low" for h in hints)

    def test_critical_hint_cannot_be_dismissed(self) -> None:
        resp = client.post("/api/game/new", json={"seed": 42})
        game_id = resp.json()["game_id"]

        state = GAME_STORE[game_id]
        state.ship.fuel = 0

        resp2 = client.post(
            f"/api/game/{game_id}/hints/dismiss",
            json={"hint_id": "fuel_zero"},
        )
        assert resp2.status_code == 200

        resp3 = client.get(f"/api/game/{game_id}")
        data = resp3.json()
        hints = data["hints"]
        assert any(h["id"] == "fuel_zero" for h in hints)


class TestDismissedHintsPersistence:
    def test_dismissed_hints_survive_save_load(self) -> None:
        from backend.database import init_db
        init_db()

        state = _make_game()
        state.ship.hull = 10
        state.dismissed_hints.add("hull_low")
        state.dismissed_hints.add("cargo_full")

        game_save(state)
        loaded = game_load(state.id)
        assert loaded is not None
        assert "hull_low" in loaded.dismissed_hints
        assert "cargo_full" in loaded.dismissed_hints

    def test_dismissed_hints_roundtrip(self) -> None:
        from backend.database import init_db
        init_db()
        from backend.game.manager import _state_to_dict, _state_from_dict

        state = _make_game()
        state.dismissed_hints.add("test_hint_1")
        state.dismissed_hints.add("test_hint_2")

        d = _state_to_dict(state)
        assert "dismissed_hints" in d
        assert isinstance(d["dismissed_hints"], list)

        restored = _state_from_dict(d)
        assert "test_hint_1" in restored.dismissed_hints
        assert "test_hint_2" in restored.dismissed_hints

    def test_empty_dismissed_hints_roundtrip(self) -> None:
        from backend.game.manager import _state_to_dict, _state_from_dict

        state = _make_game()
        d = _state_to_dict(state)
        restored = _state_from_dict(d)
        assert restored.dismissed_hints == set()

    def test_old_save_without_dismissed_hints(self) -> None:
        from backend.game.manager import _state_to_dict, _state_from_dict

        state = _make_game()
        d = _state_to_dict(state)
        del d["dismissed_hints"]
        restored = _state_from_dict(d)
        assert restored.dismissed_hints == set()


class TestHintsEdgeCases:
    def test_game_state_with_zero_cargo_capacity(self) -> None:
        state = _make_game()
        state.ship.max_cargo = 0
        state.ship.cargo = 0
        assert _cargo_full(state, state.systems) is False

    def test_hints_with_all_conditions_met(self) -> None:
        state = _make_game()
        state.ship.fuel = 0
        state.ship.hull = 10
        state.ship.cargo = 45
        state.ship.morale = 20
        hints = get_contextual_hints(state, state.systems)
        assert len(hints) <= 2
        assert len(hints) > 0

    def test_hints_on_game_state_with_no_systems(self) -> None:
        state = _make_game()
        empty_systems = {}
        hints = get_contextual_hints(state, empty_systems)
        assert isinstance(hints, list)

    def test_first_crisis_detects_title_with_crisis(self) -> None:
        state = _make_game()
        event = Event(
            id="evt_001",
            title="Life Support Crisis",
            flavor="Crisis alert!",
            event_type="crisis",
            choices=[Choice(text="Fix", outcome="hull:-10")],
            resolved=False,
        )
        state.events.append(event)
        assert _first_crisis(state, state.systems) is True

    def test_first_crisis_resolved_crisis_event(self) -> None:
        state = _make_game()
        crisis = Event(
            id="crisis_002",
            title="Hull Breach",
            flavor="A hull breach!",
            event_type="crisis",
            choices=[Choice(text="Patch it", outcome="hull:-15")],
            resolved=True,
        )
        state.events.append(crisis)
        assert _first_crisis(state, state.systems) is False
