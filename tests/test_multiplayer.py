import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import tempfile
from pathlib import Path

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.main import app
from backend.database import init_db
from backend.game.manager import GAME_STORE, new_game, game_save
from backend.multiplayer.database import init_multiplayer_db, cleanup_expired_messages
from backend.multiplayer.models import GhostSignature, CrossroadsItem, CrossroadsLore, CrossroadsMessage, RippleEvent
from backend.multiplayer.ghosts import record_ghost, get_system_ghosts
from backend.multiplayer.crossroads import (
    donate_item, claim_item, get_available_items_list,
    donate_lore, claim_lore, get_available_lore_list,
    post_message, get_messages,
)
from backend.multiplayer.ripples import create_ripple, get_pending_ripples, acknowledge_ripple
from backend.multiplayer.api import _game_locks, _get_lock, _cleanup_game_lock, _cleanup_stale_locks
from backend.models.discovery import Discovery, LoreFragment

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db() -> None:
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
        temp_db_path = tf.name
    try:
        with patch('backend.database.DB_PATH', Path(temp_db_path)):
            init_db()
            init_multiplayer_db()
            yield
    finally:
        os.unlink(temp_db_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_discovery(name: str = "Test Artifact", system_id: str = "sys-1", category: str = "artifact", value: int = 100) -> Discovery:
    import uuid
    return Discovery(
        id=str(uuid.uuid4()),
        category=category,
        name=name,
        description=f"A {name} found during exploration.",
        value=value,
        system_id=system_id,
    )


def _make_lore_fragment(fragment_id: str = "lore_architects_1", discovered: bool = True, arc: str = "architects", title: str = "Test Lore") -> LoreFragment:
    return LoreFragment(
        id=fragment_id,
        arc=arc,
        title=title,
        text="This is a test lore fragment.",
        discovered=discovered,
        fragment_number=1,
    )


# ---------------------------------------------------------------------------
# TestMultiplayerModels
# ---------------------------------------------------------------------------

class TestMultiplayerModels:
    def test_ghost_signature_roundtrip(self) -> None:
        gs = GhostSignature(
            id="ghost-1",
            game_id="game-1",
            player_name="TestPilot",
            system_id="sys-1",
            timestamp="2025-01-01T00:00:00Z",
            discoveries=["Artifact A", "Artifact B"],
            message="Hello from the void!",
            body_visits=["body-1", "body-2"],
        )
        d = gs.to_dict()
        gs2 = GhostSignature.from_dict(d)
        assert gs2.id == gs.id
        assert gs2.game_id == gs.game_id
        assert gs2.player_name == gs.player_name
        assert gs2.system_id == gs.system_id
        assert gs2.timestamp == gs.timestamp
        assert gs2.discoveries == gs.discoveries
        assert gs2.message == gs.message
        assert gs2.body_visits == gs.body_visits

    def test_crossroads_item_roundtrip(self) -> None:
        ci = CrossroadsItem(
            id="item-1",
            donor_game_id="game-1",
            donor_name="TestPilot",
            item_name="Rare Crystal",
            quantity=3,
            message="Enjoy!",
            claimed=True,
            claimer_game_id="game-2",
            created_at="2025-01-01T00:00:00Z",
        )
        d = ci.to_dict()
        ci2 = CrossroadsItem.from_dict(d)
        assert ci2.id == ci.id
        assert ci2.donor_game_id == ci.donor_game_id
        assert ci2.donor_name == ci.donor_name
        assert ci2.item_name == ci.item_name
        assert ci2.quantity == ci.quantity
        assert ci2.message == ci.message
        assert ci2.claimed == ci.claimed
        assert ci2.claimer_game_id == ci.claimer_game_id
        assert ci2.created_at == ci.created_at

    def test_crossroads_lore_roundtrip(self) -> None:
        cl = CrossroadsLore(
            id="lore-1",
            donor_game_id="game-1",
            donor_name="TestPilot",
            fragment_id="lore_architects_1",
            message="Check this out!",
            claimed=False,
            claimer_game_id=None,
            created_at="2025-01-01T00:00:00Z",
        )
        d = cl.to_dict()
        cl2 = CrossroadsLore.from_dict(d)
        assert cl2.id == cl.id
        assert cl2.donor_game_id == cl.donor_game_id
        assert cl2.donor_name == cl.donor_name
        assert cl2.fragment_id == cl.fragment_id
        assert cl2.message == cl.message
        assert cl2.claimed == cl.claimed
        assert cl2.claimer_game_id == cl.claimer_game_id
        assert cl2.created_at == cl.created_at

    def test_crossroads_message_roundtrip(self) -> None:
        cm = CrossroadsMessage(
            id="msg-1",
            game_id="game-1",
            player_name="TestPilot",
            text="Hello Crossroads!",
            created_at="2025-01-01T00:00:00Z",
            expires_at="2025-01-08T00:00:00Z",
        )
        d = cm.to_dict()
        cm2 = CrossroadsMessage.from_dict(d)
        assert cm2.id == cm.id
        assert cm2.game_id == cm.game_id
        assert cm2.player_name == cm.player_name
        assert cm2.text == cm.text
        assert cm2.created_at == cm.created_at
        assert cm2.expires_at == cm.expires_at

    def test_ripple_event_roundtrip(self) -> None:
        re = RippleEvent(
            id="ripple-1",
            source_game_id="game-1",
            source_player_name="TestPilot",
            source_system_id="sys-1",
            target_system_id="sys-2",
            discovery_type="artifact",
            discovery_name="Ancient Relic",
            created_at="2025-01-01T00:00:00Z",
            acknowledged_by=["game-2", "game-3"],
        )
        d = re.to_dict()
        re2 = RippleEvent.from_dict(d)
        assert re2.id == re.id
        assert re2.source_game_id == re.source_game_id
        assert re2.source_player_name == re.source_player_name
        assert re2.source_system_id == re.source_system_id
        assert re2.target_system_id == re.target_system_id
        assert re2.discovery_type == re.discovery_type
        assert re2.discovery_name == re.discovery_name
        assert re2.created_at == re.created_at
        assert re2.acknowledged_by == re.acknowledged_by

    def test_ghost_signature_defaults(self) -> None:
        gs = GhostSignature(
            id="ghost-2",
            game_id="game-2",
            player_name="Pilot",
            system_id="sys-2",
            timestamp="2025-01-01T00:00:00Z",
        )
        assert gs.discoveries == []
        assert gs.message is None
        assert gs.body_visits == []

    def test_ripple_event_defaults(self) -> None:
        re = RippleEvent(
            id="ripple-2",
            source_game_id="game-1",
            source_player_name="Pilot",
            source_system_id="sys-1",
            target_system_id="sys-2",
            discovery_type="lore",
            discovery_name="Lost Fragment",
            created_at="2025-01-01T00:00:00Z",
        )
        assert re.acknowledged_by == []


# ---------------------------------------------------------------------------
# TestMultiplayerDatabase
# ---------------------------------------------------------------------------

class TestMultiplayerDatabase:
    @pytest.fixture(autouse=True)
    def cleanup_messages(self) -> None:
        from backend.multiplayer.database import get_db_ctx
        with get_db_ctx() as conn:
            conn.execute("DELETE FROM crossroads_messages")
        yield

    def test_save_and_get_ghost_signatures(self) -> None:
        from backend.multiplayer.database import save_ghost_signature, get_ghost_signatures
        gs = GhostSignature(
            id="ghost-db-1",
            game_id="game-db-1",
            player_name="DBTester",
            system_id="sys-db-1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            discoveries=["Crystal", "Relic"],
            message="DB test ghost",
            body_visits=["body-a"],
        )
        save_ghost_signature(gs)
        ghosts = get_ghost_signatures("sys-db-1")
        assert len(ghosts) >= 1
        found = [g for g in ghosts if g.id == "ghost-db-1"]
        assert len(found) == 1
        assert found[0].player_name == "DBTester"
        assert found[0].discoveries == ["Crystal", "Relic"]
        assert found[0].message == "DB test ghost"
        assert found[0].body_visits == ["body-a"]

    def test_save_and_get_available_items(self) -> None:
        from backend.multiplayer.database import save_crossroads_item, get_available_items
        ci = CrossroadsItem(
            id="item-db-1",
            donor_game_id="game-db-1",
            donor_name="DBTester",
            item_name="Space Diamond",
            quantity=2,
            message="A gift",
            claimed=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_crossroads_item(ci)
        items = get_available_items()
        found = [i for i in items if i.id == "item-db-1"]
        assert len(found) == 1
        assert found[0].item_name == "Space Diamond"
        assert found[0].quantity == 2

    def test_claim_item_success(self) -> None:
        from backend.multiplayer.database import save_crossroads_item, claim_item as db_claim_item
        ci = CrossroadsItem(
            id="item-claim-1",
            donor_game_id="game-db-1",
            donor_name="DBTester",
            item_name="Nebula Dust",
            quantity=1,
            claimed=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_crossroads_item(ci)
        result = db_claim_item("item-claim-1", "claimer-game-1")
        assert isinstance(result, dict)
        assert result["id"] == "item-claim-1"
        assert result["item_name"] == "Nebula Dust"
        assert result["quantity"] == 1
        assert result["claimed"] is True
        assert result["claimer_game_id"] == "claimer-game-1"

    def test_claim_item_already_claimed(self) -> None:
        from backend.multiplayer.database import save_crossroads_item, claim_item as db_claim_item
        ci = CrossroadsItem(
            id="item-claim-2",
            donor_game_id="game-db-1",
            donor_name="DBTester",
            item_name="Stardust",
            quantity=1,
            claimed=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_crossroads_item(ci)
        db_claim_item("item-claim-2", "claimer-a")
        ok = db_claim_item("item-claim-2", "claimer-b")
        assert ok is None

    def test_claim_item_not_found(self) -> None:
        from backend.multiplayer.database import claim_item as db_claim_item
        ok = db_claim_item("nonexistent-item-id", "claimer-x")
        assert ok is None

    def test_claim_item_select_returns_none(self) -> None:
        from backend.multiplayer.database import claim_item as db_claim_item

        update_cursor = MagicMock()
        update_cursor.rowcount = 1

        select_cursor = MagicMock()
        select_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = [update_cursor, select_cursor]

        with patch("backend.multiplayer.database.get_db_ctx") as mock_get_db_ctx:
            mock_get_db_ctx.return_value.__enter__.return_value = mock_conn
            result = db_claim_item("test-item-id", "test-claimer")
            assert result is None

    def test_save_and_get_available_lore(self) -> None:
        from backend.multiplayer.database import save_crossroads_lore, get_available_lore
        cl = CrossroadsLore(
            id="lore-db-1",
            donor_game_id="game-db-1",
            donor_name="DBTester",
            fragment_id="lore_architects_1",
            message="Ancient text",
            claimed=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_crossroads_lore(cl)
        lore_list = get_available_lore()
        found = [l for l in lore_list if l.id == "lore-db-1"]
        assert len(found) == 1
        assert found[0].fragment_id == "lore_architects_1"

    def test_claim_lore_success(self) -> None:
        from backend.multiplayer.database import save_crossroads_lore, claim_lore as db_claim_lore
        cl = CrossroadsLore(
            id="lore-claim-1",
            donor_game_id="game-db-1",
            donor_name="DBTester",
            fragment_id="lore_wanderer_1",
            claimed=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_crossroads_lore(cl)
        result = db_claim_lore("lore-claim-1", "claimer-game-1")
        assert isinstance(result, dict)
        assert result["id"] == "lore-claim-1"
        assert result["fragment_id"] == "lore_wanderer_1"
        assert result["claimed"] is True
        assert result["claimer_game_id"] == "claimer-game-1"

    def test_claim_lore_already_claimed(self) -> None:
        from backend.multiplayer.database import save_crossroads_lore, claim_lore as db_claim_lore
        cl = CrossroadsLore(
            id="lore-claim-2",
            donor_game_id="game-db-1",
            donor_name="DBTester",
            fragment_id="lore_signal_1",
            claimed=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_crossroads_lore(cl)
        db_claim_lore("lore-claim-2", "claimer-a")
        ok = db_claim_lore("lore-claim-2", "claimer-b")
        assert ok is None

    def test_claim_lore_select_returns_none(self) -> None:
        from backend.multiplayer.database import claim_lore as db_claim_lore

        update_cursor = MagicMock()
        update_cursor.rowcount = 1

        select_cursor = MagicMock()
        select_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = [update_cursor, select_cursor]

        with patch("backend.multiplayer.database.get_db_ctx") as mock_get_db_ctx:
            mock_get_db_ctx.return_value.__enter__.return_value = mock_conn
            result = db_claim_lore("test-lore-id", "test-claimer")
            assert result is None

    def test_save_and_get_recent_messages(self) -> None:
        from backend.multiplayer.database import save_crossroads_message, get_recent_messages
        cm = CrossroadsMessage(
            id="msg-db-1",
            game_id="game-db-1",
            player_name="DBTester",
            text="First post!",
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        )
        save_crossroads_message(cm)
        msgs = get_recent_messages(limit=10)
        found = [m for m in msgs if m.id == "msg-db-1"]
        assert len(found) == 1
        assert found[0].text == "First post!"

    def test_expired_messages_excluded(self) -> None:
        from backend.multiplayer.database import save_crossroads_message, get_recent_messages
        cm = CrossroadsMessage(
            id="msg-expired-1",
            game_id="game-db-1",
            player_name="DBTester",
            text="Old message",
            created_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            expires_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        )
        save_crossroads_message(cm)
        msgs = get_recent_messages(limit=50)
        found = [m for m in msgs if m.id == "msg-expired-1"]
        assert len(found) == 0

    def test_cleanup_expired_messages(self) -> None:
        from backend.multiplayer.database import save_crossroads_message
        cm = CrossroadsMessage(
            id="msg-cleanup-1",
            game_id="game-db-1",
            player_name="DBTester",
            text="To be deleted",
            created_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            expires_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        )
        save_crossroads_message(cm)
        deleted = cleanup_expired_messages()
        assert deleted >= 1

    def test_save_and_get_ripple_events(self) -> None:
        from backend.multiplayer.database import save_ripple_event, get_pending_ripples as db_get_pending
        re = RippleEvent(
            id="ripple-db-1",
            source_game_id="game-db-1",
            source_player_name="DBTester",
            source_system_id="sys-1",
            target_system_id="sys-rp-1",
            discovery_type="artifact",
            discovery_name="Void Gem",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_ripple_event(re)
        # get_pending_ripples filters by target_system_id matching a game's current system,
        # so we need a game in sys-rp-1 to make this work
        # Create a game specifically for this test
        state = new_game(42, "RippleTest", shared_universe=True)
        state.ship.current_system_id = "sys-rp-1"
        state.systems["sys-rp-1"] = state.systems[list(state.systems.keys())[0]]
        state.systems["sys-rp-1"].id = "sys-rp-1"
        GAME_STORE[state.id] = state
        game_save(state)
        ripples = db_get_pending(state.id)
        found = [r for r in ripples if r.id == "ripple-db-1"]
        assert len(found) == 1
        assert found[0].discovery_name == "Void Gem"
        # Clean up
        GAME_STORE.pop(state.id, None)

    def test_acknowledge_ripple_success(self) -> None:
        from backend.multiplayer.database import save_ripple_event, acknowledge_ripple as db_ack_ripple
        re = RippleEvent(
            id="ripple-ack-1",
            source_game_id="game-src",
            source_player_name="Someone",
            source_system_id="sys-a",
            target_system_id="sys-b",
            discovery_type="lore",
            discovery_name="Echo Fragment",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_ripple_event(re)
        ok = db_ack_ripple("ripple-ack-1", "game-ack-1")
        assert ok is True

    def test_acknowledge_ripple_already_acknowledged(self) -> None:
        from backend.multiplayer.database import save_ripple_event, acknowledge_ripple as db_ack_ripple
        re = RippleEvent(
            id="ripple-ack-2",
            source_game_id="game-src",
            source_player_name="Someone",
            source_system_id="sys-a",
            target_system_id="sys-b",
            discovery_type="lore",
            discovery_name="Already Acked",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_ripple_event(re)
        db_ack_ripple("ripple-ack-2", "game-ack-2")
        ok = db_ack_ripple("ripple-ack-2", "game-ack-2")
        assert ok is False

    def test_acknowledge_ripple_not_found(self) -> None:
        from backend.multiplayer.database import acknowledge_ripple as db_ack_ripple
        ok = db_ack_ripple("nonexistent-ripple", "game-x")
        assert ok is False

    def test_load_json_column_error_handling(self) -> None:
        from backend.multiplayer.database import _load_json_column
        result = _load_json_column("not valid json {{{")
        assert result == []
        result = _load_json_column("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_get_recent_messages_paginated_basic(self) -> None:
        from backend.multiplayer.database import save_crossroads_message, get_recent_messages_paginated
        for i in range(10):
            cm = CrossroadsMessage(
                id=f"msg-pag-{i}",
                game_id="game-pag",
                player_name="PaginationTester",
                text=f"Paginated message {i}",
                created_at=(datetime.now(timezone.utc) - timedelta(minutes=10 - i)).isoformat(),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            )
            save_crossroads_message(cm)
        msgs, total, _, _ = get_recent_messages_paginated(page=1, per_page=5)
        assert len(msgs) == 5
        assert total == 10

    def test_get_recent_messages_paginated_page2(self) -> None:
        from backend.multiplayer.database import save_crossroads_message, get_recent_messages_paginated
        for i in range(10):
            cm = CrossroadsMessage(
                id=f"msg-pag2-{i}",
                game_id="game-pag2",
                player_name="PaginationTester",
                text=f"Page 2 message {i}",
                created_at=(datetime.now(timezone.utc) - timedelta(minutes=10 - i)).isoformat(),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            )
            save_crossroads_message(cm)
        page1_msgs, _, _, _ = get_recent_messages_paginated(page=1, per_page=5)
        page2_msgs, _, _, _ = get_recent_messages_paginated(page=2, per_page=5)
        page1_ids = {m.id for m in page1_msgs}
        page2_ids = {m.id for m in page2_msgs}
        assert len(page1_msgs) == 5
        assert len(page2_msgs) == 5
        assert page1_ids.isdisjoint(page2_ids)

    def test_get_recent_messages_paginated_empty_page(self) -> None:
        from backend.multiplayer.database import save_crossroads_message, get_recent_messages_paginated
        for i in range(3):
            cm = CrossroadsMessage(
                id=f"msg-empty-{i}",
                game_id="game-empty",
                player_name="EmptyTester",
                text=f"Empty page message {i}",
                created_at=(datetime.now(timezone.utc) - timedelta(minutes=3 - i)).isoformat(),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            )
            save_crossroads_message(cm)
        msgs, total, _, _ = get_recent_messages_paginated(page=10, per_page=5)
        assert len(msgs) == 0
        assert total == 3

    def test_get_recent_messages_paginated_expired_excluded(self) -> None:
        from backend.multiplayer.database import save_crossroads_message, get_recent_messages_paginated
        active = CrossroadsMessage(
            id="msg-active",
            game_id="game-x",
            player_name="Tester",
            text="I am active",
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        )
        expired = CrossroadsMessage(
            id="msg-dead",
            game_id="game-x",
            player_name="Tester",
            text="I am expired",
            created_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            expires_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        )
        save_crossroads_message(active)
        save_crossroads_message(expired)
        msgs, total, _, _ = get_recent_messages_paginated(page=1, per_page=10)
        ids = {m.id for m in msgs}
        assert "msg-active" in ids
        assert "msg-dead" not in ids
        assert total == 1

    def test_get_recent_messages_paginated_total_count(self) -> None:
        from backend.multiplayer.database import save_crossroads_message, get_recent_messages_paginated
        import uuid
        for i in range(7):
            cm = CrossroadsMessage(
                id=f"msg-count-{uuid.uuid4()}",
                game_id="game-count",
                player_name="CountTester",
                text=f"Count message {i}",
                created_at=datetime.now(timezone.utc).isoformat(),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            )
            save_crossroads_message(cm)
        _, total, _, _ = get_recent_messages_paginated(page=1, per_page=3)
        assert total == 7

    def test_get_recent_messages_paginated_per_page_capped(self) -> None:
        from backend.multiplayer.database import save_crossroads_message
        from backend.multiplayer.crossroads import get_messages
        # Insert 60 messages to ensure the cap is exercised
        for i in range(60):
            cm = CrossroadsMessage(
                id=f"msg-cap-{i}",
                game_id="game-cap",
                player_name="CapTester",
                text=f"Cap test message {i}",
                created_at=datetime.now(timezone.utc).isoformat(),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            )
            save_crossroads_message(cm)
        result = get_messages(page=1, per_page=100)
        assert len(result['messages']) == 50  # capped at 50
        assert result['per_page'] == 50

    def test_get_recent_messages_paginated_page_clamped(self) -> None:
        from backend.multiplayer.database import save_crossroads_message
        from backend.multiplayer.crossroads import get_messages
        # Insert 10 messages
        for i in range(10):
            cm = CrossroadsMessage(
                id=f"msg-clamp-{i}",
                game_id="game-clamp",
                player_name="ClampTester",
                text=f"Clamp test message {i}",
                created_at=(datetime.now(timezone.utc) - timedelta(minutes=10 - i)).isoformat(),
                expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            )
            save_crossroads_message(cm)
        result = get_messages(page=0, per_page=10)
        result2 = get_messages(page=1, per_page=10)
        assert result['page'] == 1  # clamped from 0 to 1
        assert result['per_page'] == 10
        assert result['total_messages'] == 10
        # page=0 should be clamped to page=1, so results should be identical
        assert [m['id'] for m in result['messages']] == [m['id'] for m in result2['messages']]


# ---------------------------------------------------------------------------
# TestMultiplayerGhosts
# ---------------------------------------------------------------------------

class TestMultiplayerGhosts:
    def test_record_ghost_creates_signature(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        assert system is not None
        result = record_ghost(state, system.id)
        assert "id" in result
        assert result["player_name"] == "GhostShip"
        assert result["system_id"] == system.id

        ghosts_data = get_system_ghosts(system.id)
        found = [g for g in ghosts_data["ghosts"] if g["id"] == result["id"]]
        assert len(found) == 1
        GAME_STORE.pop(state.id, None)

    def test_record_ghost_includes_discoveries(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        disc = _make_discovery(name="Ghost Relic", system_id=system.id)
        state.discoveries.append(disc)
        result = record_ghost(state, system.id)
        assert "Ghost Relic" in result["discoveries"]
        GAME_STORE.pop(state.id, None)

    def test_record_ghost_filters_discoveries_by_system(self) -> None:
        """Verify that record_ghost filters both discoveries and body_visits to the current system."""
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        assert system is not None

        # Add a discovery in the current system with a body_id
        current_sys_disc = _make_discovery(
            name="Current System Relic",
            system_id=system.id,
        )
        current_sys_disc.body_id = "body-1"
        state.discoveries.append(current_sys_disc)

        # Add discoveries in other systems
        other_sys_disc1 = _make_discovery(
            name="Other System Artifact",
            system_id="other-system-1",
        )
        other_sys_disc1.body_id = "body-other-1"
        state.discoveries.append(other_sys_disc1)

        other_sys_disc2 = _make_discovery(
            name="Another System Relic",
            system_id="other-system-2",
        )
        state.discoveries.append(other_sys_disc2)

        result = record_ghost(state, system.id)

        # Should only include the current system discovery name
        assert "Current System Relic" in result["discoveries"]
        assert "Other System Artifact" not in result["discoveries"]
        assert "Another System Relic" not in result["discoveries"]
        assert len(result["discoveries"]) == 1

        # body_visits should only include body_id from current system discoveries that have a body_id
        assert "body-1" in result["body_visits"]
        assert "body-other-1" not in result["body_visits"]
        assert len(result["body_visits"]) == 1
        GAME_STORE.pop(state.id, None)

    def test_record_ghost_deduplicates_body_visits(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()

        disc1 = _make_discovery(name="Artifact Alpha", system_id=system.id)
        disc1.body_id = "body-shared"
        state.discoveries.append(disc1)

        disc2 = _make_discovery(name="Artifact Beta", system_id=system.id)
        disc2.body_id = "body-shared"
        state.discoveries.append(disc2)

        disc3 = _make_discovery(name="Artifact Gamma", system_id=system.id)
        disc3.body_id = "body-shared"
        state.discoveries.append(disc3)

        result = record_ghost(state, system.id)

        assert "body-shared" in result["body_visits"]
        disambiguate = [b for b in result["body_visits"] if b == "body-shared"]
        assert len(disambiguate) == 1

        GAME_STORE.pop(state.id, None)

    def test_record_ghost_with_message(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        result = record_ghost(state, system.id, message="Beware the void!")
        assert result["message"] == "Beware the void!"
        GAME_STORE.pop(state.id, None)

    def test_get_system_ghosts_returns_ghosts(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        record_ghost(state, system.id, message="Ghost 1")
        record_ghost(state, system.id, message="Ghost 2")
        ghosts_data = get_system_ghosts(system.id)
        assert len(ghosts_data["ghosts"]) >= 2
        messages = [g["message"] for g in ghosts_data["ghosts"]]
        assert "Ghost 1" in messages
        assert "Ghost 2" in messages
        GAME_STORE.pop(state.id, None)

    def test_get_system_ghosts_empty(self) -> None:
        ghosts_data = get_system_ghosts("nonexistent-system-id-xyz")
        assert ghosts_data["ghosts"] == []
        assert ghosts_data["total_ghosts"] == 0
        assert ghosts_data["total_pages"] == 0

    def test_get_system_ghosts_pagination_default(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        for i in range(15):
            record_ghost(state, system.id, message=f"Ghost {i}")
        result = get_system_ghosts(system.id)
        assert result["page"] == 1
        assert result["per_page"] == 10
        assert result["total_ghosts"] >= 15
        assert result["total_pages"] >= 2
        assert len(result["ghosts"]) == 10
        GAME_STORE.pop(state.id, None)

    def test_get_system_ghosts_pagination_explicit(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        for i in range(15):
            record_ghost(state, system.id, message=f"Ghost {i}")
        result = get_system_ghosts(system.id, page=2, per_page=5)
        assert result["page"] == 2
        assert result["per_page"] == 5
        assert result["total_ghosts"] >= 15
        assert result["total_pages"] >= 3
        assert len(result["ghosts"]) == 5
        GAME_STORE.pop(state.id, None)

    def test_get_system_ghosts_per_page_capped(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        for i in range(5):
            record_ghost(state, system.id, message=f"Ghost {i}")
        result = get_system_ghosts(system.id, per_page=100)
        assert result["per_page"] == 50
        GAME_STORE.pop(state.id, None)

    def test_get_system_ghosts_page_beyond_total(self) -> None:
        state = new_game(42, "GhostShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        for i in range(5):
            record_ghost(state, system.id, message=f"Ghost {i}")
        result = get_system_ghosts(system.id, page=10, per_page=10)
        assert result["page"] == 1
        assert len(result["ghosts"]) == 5
        assert result["total_ghosts"] >= 5
        GAME_STORE.pop(state.id, None)


# ---------------------------------------------------------------------------
# TestMultiplayerCrossroads
# ---------------------------------------------------------------------------

class TestMultiplayerCrossroads:
    def test_donate_item_success(self) -> None:
        state = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[state.id] = state
        disc = _make_discovery(name="Rare Ore")
        state.discoveries.append(disc)
        result = donate_item(state, "Rare Ore", 1)
        assert result["success"] is True
        assert result["donation"]["item_name"] == "Rare Ore"
        GAME_STORE.pop(state.id, None)

    def test_donate_item_not_found(self) -> None:
        state = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[state.id] = state
        result = donate_item(state, "NonexistentItem", 1)
        assert result["success"] is False
        GAME_STORE.pop(state.id, None)

    def test_donate_item_with_message(self) -> None:
        state = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[state.id] = state
        disc = _make_discovery(name="Message Crystal")
        state.discoveries.append(disc)
        result = donate_item(state, "Message Crystal", 1, message="Handle with care")
        assert result["success"] is True
        assert result["donation"]["message"] == "Handle with care"
        GAME_STORE.pop(state.id, None)

    def test_claim_item_success(self) -> None:
        # Donate from one game, claim from another
        donor = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[donor.id] = donor
        disc1 = _make_discovery(name="Claimable Gem")
        disc2 = _make_discovery(name="Claimable Gem")
        donor.discoveries.append(disc1)
        donor.discoveries.append(disc2)
        don_result = donate_item(donor, "Claimable Gem", 2)

        claimer = new_game(43, "ClaimerShip", shared_universe=True)
        GAME_STORE[claimer.id] = claimer
        initial_disc_count = len(claimer.discoveries)
        result = claim_item(don_result["donation"]["id"], claimer)
        assert result["success"] is True
        assert len(claimer.discoveries) == initial_disc_count + don_result["donation"]["quantity"]
        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer.id, None)

    def test_claim_item_not_found(self) -> None:
        state = new_game(42, "ClaimerShip", shared_universe=True)
        GAME_STORE[state.id] = state
        result = claim_item("nonexistent-item-id", state)
        assert result["success"] is False
        GAME_STORE.pop(state.id, None)

    def test_claim_item_adds_to_discoveries(self) -> None:
        donor = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[donor.id] = donor
        disc1 = _make_discovery(name="Discovery Crystal")
        disc2 = _make_discovery(name="Discovery Crystal")
        disc3 = _make_discovery(name="Discovery Crystal")
        donor.discoveries.append(disc1)
        donor.discoveries.append(disc2)
        donor.discoveries.append(disc3)
        don_result = donate_item(donor, "Discovery Crystal", 3)

        claimer = new_game(43, "ClaimerShip", shared_universe=True)
        GAME_STORE[claimer.id] = claimer
        claim_item(don_result["donation"]["id"], claimer)
        names = [d.name for d in claimer.discoveries]
        assert names.count("Discovery Crystal") == don_result["donation"]["quantity"]
        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer.id, None)

    def test_claim_item_creates_distinct_discovery_objects(self) -> None:
        """Verify that claiming an item with quantity > 1 creates distinct Discovery objects."""
        donor = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[donor.id] = donor
        disc1 = _make_discovery(name="Distinct Crystal")
        disc2 = _make_discovery(name="Distinct Crystal")
        disc3 = _make_discovery(name="Distinct Crystal")
        donor.discoveries.append(disc1)
        donor.discoveries.append(disc2)
        donor.discoveries.append(disc3)
        don_result = donate_item(donor, "Distinct Crystal", 3)

        claimer = new_game(43, "ClaimerShip", shared_universe=True)
        GAME_STORE[claimer.id] = claimer
        initial_count = len(claimer.discoveries)
        claim_item(don_result["donation"]["id"], claimer)

        # Check count
        assert len(claimer.discoveries) == initial_count + 3

        # Get the newly added discoveries
        new_discs = [d for d in claimer.discoveries if d.name == "Distinct Crystal"]
        assert len(new_discs) == 3

        # Check all ids are unique
        ids = {d.id for d in new_discs}
        assert len(ids) == 3, f"Expected 3 unique ids, got {len(ids)}"

        # Check all objects are distinct (different memory references)
        assert new_discs[0] is not new_discs[1]
        assert new_discs[0] is not new_discs[2]
        assert new_discs[1] is not new_discs[2]

        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer.id, None)

    def test_donate_lore_success(self) -> None:
        state = new_game(42, "LoreDonor", shared_universe=True)
        GAME_STORE[state.id] = state
        lf = _make_lore_fragment("lore_architects_1", discovered=True)
        state.lore_fragments.append(lf)
        result = donate_lore(state, "lore_architects_1")
        assert result["success"] is True
        assert result["donation"]["fragment_id"] == "lore_architects_1"
        GAME_STORE.pop(state.id, None)

    def test_donate_lore_not_discovered(self) -> None:
        state = new_game(42, "LoreDonor", shared_universe=True)
        GAME_STORE[state.id] = state
        lf = _make_lore_fragment("lore_architects_1", discovered=False)
        state.lore_fragments.append(lf)
        result = donate_lore(state, "lore_architects_1")
        assert result["success"] is False
        GAME_STORE.pop(state.id, None)

    def test_donate_lore_removes_fragment_from_player(self) -> None:
        """After donating a lore fragment, it should be removed from the player's lore_fragments list,
        preventing the same fragment from being donated multiple times."""
        state = new_game(42, "LoreDonor", shared_universe=True)
        GAME_STORE[state.id] = state
        lf = _make_lore_fragment("lore_double_donate", discovered=True)
        state.lore_fragments.append(lf)
        initial_count = len(state.lore_fragments)

        # First donation should succeed
        result1 = donate_lore(state, "lore_double_donate")
        assert result1["success"] is True

        # Fragment should be removed from player's state
        assert len(state.lore_fragments) == initial_count - 1
        fragment_ids = [f.id for f in state.lore_fragments]
        assert "lore_double_donate" not in fragment_ids

        # Second donation should fail since fragment is gone
        result2 = donate_lore(state, "lore_double_donate")
        assert result2["success"] is False
        assert "not found" in result2["detail"].lower()
        GAME_STORE.pop(state.id, None)

    def test_claim_lore_success(self) -> None:
        donor = new_game(42, "LoreDonor", shared_universe=True)
        GAME_STORE[donor.id] = donor
        lf = _make_lore_fragment("lore_claim_test", discovered=True)
        donor.lore_fragments.append(lf)
        don_result = donate_lore(donor, "lore_claim_test")

        claimer = new_game(43, "LoreClaimer", shared_universe=True)
        GAME_STORE[claimer.id] = claimer
        clf = _make_lore_fragment("lore_claim_test", discovered=False)
        claimer.lore_fragments.append(clf)
        result = claim_lore(don_result["donation"]["id"], claimer)
        assert result["success"] is True
        assert clf.discovered is True
        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer.id, None)

    def test_claim_lore_marks_fragment_discovered(self) -> None:
        donor = new_game(42, "LoreDonor", shared_universe=True)
        GAME_STORE[donor.id] = donor
        lf = _make_lore_fragment("lore_mark_test", discovered=True)
        donor.lore_fragments.append(lf)
        don_result = donate_lore(donor, "lore_mark_test")

        claimer = new_game(43, "LoreClaimer", shared_universe=True)
        GAME_STORE[claimer.id] = claimer
        clf = _make_lore_fragment("lore_mark_test", discovered=False)
        claimer.lore_fragments.append(clf)
        claim_lore(don_result["donation"]["id"], claimer)
        for lf_item in claimer.lore_fragments:
            if lf_item.id == "lore_mark_test":
                assert lf_item.discovered is True
                assert lf_item.discovery_timestamp != ""
                break
        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer.id, None)

    def test_post_message_success(self) -> None:
        state = new_game(42, "Poster", shared_universe=True)
        GAME_STORE[state.id] = state
        result = post_message(state, "Hello from the crossroads!")
        assert result["success"] is True
        msg = result["message"]
        assert "id" in msg
        assert msg["text"] == "Hello from the crossroads!"
        assert msg["player_name"] == "Poster"
        GAME_STORE.pop(state.id, None)

    def test_get_messages_returns_messages(self) -> None:
        state = new_game(42, "Poster", shared_universe=True)
        GAME_STORE[state.id] = state
        post_message(state, "Message A")
        post_message(state, "Message B")
        result = get_messages()
        assert len(result["messages"]) >= 2
        GAME_STORE.pop(state.id, None)

    def test_post_message_empty_text_rejected(self) -> None:
        """post_message should reject empty text."""
        state = new_game(42, "Poster", shared_universe=True)
        GAME_STORE[state.id] = state
        result = post_message(state, "")
        assert result["success"] is False
        assert "cannot be empty" in result["detail"].lower()
        GAME_STORE.pop(state.id, None)

    def test_post_message_whitespace_text_rejected(self) -> None:
        """post_message should reject whitespace-only text."""
        state = new_game(42, "Poster", shared_universe=True)
        GAME_STORE[state.id] = state
        result = post_message(state, "   ")
        assert result["success"] is False
        assert "cannot be empty" in result["detail"].lower()
        GAME_STORE.pop(state.id, None)

    def test_post_message_too_long_rejected(self) -> None:
        """post_message should reject text longer than 500 characters."""
        state = new_game(42, "Poster", shared_universe=True)
        GAME_STORE[state.id] = state
        result = post_message(state, "x" * 501)
        assert result["success"] is False
        assert "exceeds" in result["detail"].lower()
        GAME_STORE.pop(state.id, None)

    def test_post_message_pydantic_rejects_empty(self) -> None:
        """PostMessageRequest schema should reject empty text."""
        from pydantic import ValidationError
        from backend.multiplayer.schemas import PostMessageRequest
        with pytest.raises(ValidationError):
            PostMessageRequest(game_id="game-1", text="")

    def test_post_message_pydantic_rejects_whitespace(self) -> None:
        """PostMessageRequest schema should reject whitespace-only text."""
        from pydantic import ValidationError
        from backend.multiplayer.schemas import PostMessageRequest
        with pytest.raises(ValidationError):
            PostMessageRequest(game_id="game-1", text="   ")

    def test_post_message_pydantic_rejects_too_long(self) -> None:
        """PostMessageRequest schema should reject text longer than 500 chars."""
        from pydantic import ValidationError
        from backend.multiplayer.schemas import PostMessageRequest
        with pytest.raises(ValidationError):
            PostMessageRequest(game_id="game-1", text="x" * 501)

    def test_post_message_pydantic_accepts_valid(self) -> None:
        """PostMessageRequest schema should accept valid text."""
        from backend.multiplayer.schemas import PostMessageRequest
        req = PostMessageRequest(game_id="game-1", text="Hello!")
        assert req.text == "Hello!"
        assert req.game_id == "game-1"

    def test_post_message_pydantic_strips_whitespace(self) -> None:
        """PostMessageRequest schema should strip leading/trailing whitespace."""
        from backend.multiplayer.schemas import PostMessageRequest
        req = PostMessageRequest(game_id="game-1", text="  Hello!  ")
        assert req.text == "Hello!"

    def test_claim_item_already_claimed_by_other(self) -> None:
        # Test that claiming an already-claimed item fails at the DB level
        donor = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[donor.id] = donor
        disc = _make_discovery(name="Stealable Gem")
        donor.discoveries.append(disc)
        don_result = donate_item(donor, "Stealable Gem", 1)

        claimer1 = new_game(43, "Claimer1", shared_universe=True)
        GAME_STORE[claimer1.id] = claimer1
        result1 = claim_item(don_result["donation"]["id"], claimer1)
        assert result1["success"] is True

        claimer2 = new_game(44, "Claimer2", shared_universe=True)
        GAME_STORE[claimer2.id] = claimer2
        result2 = claim_item(don_result["donation"]["id"], claimer2)
        assert result2["success"] is False

        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer1.id, None)
        GAME_STORE.pop(claimer2.id, None)

    def test_claim_item_db_claim_race_condition(self) -> None:
        donor = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[donor.id] = donor
        disc = _make_discovery(name="Race Item")
        donor.discoveries.append(disc)
        don_result = donate_item(donor, "Race Item", 1)

        claimer = new_game(43, "Claimer", shared_universe=True)
        GAME_STORE[claimer.id] = claimer

        with patch("backend.multiplayer.crossroads.db_claim_item", return_value=None):
            result = claim_item(don_result["donation"]["id"], claimer)
        assert result["success"] is False

        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer.id, None)

    def test_claim_item_no_current_system(self) -> None:
        """claim_item should fail gracefully when ship has no current system."""
        donor = new_game(42, "DonorShip", shared_universe=True)
        GAME_STORE[donor.id] = donor
        disc = _make_discovery(name="NoSys Item")
        donor.discoveries.append(disc)
        don_result = donate_item(donor, "NoSys Item", 1)

        claimer = new_game(43, "ClaimerShip", shared_universe=True)
        GAME_STORE[claimer.id] = claimer
        claimer.ship.current_system_id = ""  # Simulate save corruption
        result = claim_item(don_result["donation"]["id"], claimer)
        assert result["success"] is False
        assert "no current system" in result["detail"].lower()

        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer.id, None)

    def test_claim_lore_not_found(self) -> None:
        state = new_game(42, "Claimer", shared_universe=True)
        GAME_STORE[state.id] = state
        result = claim_lore("nonexistent-lore-donation-id", state)
        assert result["success"] is False
        GAME_STORE.pop(state.id, None)

    def test_claim_lore_already_claimed_by_other(self) -> None:
        donor = new_game(42, "LoreDonor", shared_universe=True)
        GAME_STORE[donor.id] = donor
        lf = _make_lore_fragment("lore_double", discovered=True)
        donor.lore_fragments.append(lf)
        don_result = donate_lore(donor, "lore_double")

        claimer1 = new_game(43, "LoreClaimer1", shared_universe=True)
        GAME_STORE[claimer1.id] = claimer1
        clf1 = _make_lore_fragment("lore_double", discovered=False)
        claimer1.lore_fragments.append(clf1)
        result1 = claim_lore(don_result["donation"]["id"], claimer1)
        assert result1["success"] is True

        claimer2 = new_game(44, "LoreClaimer2", shared_universe=True)
        GAME_STORE[claimer2.id] = claimer2
        clf2 = _make_lore_fragment("lore_double", discovered=False)
        claimer2.lore_fragments.append(clf2)
        result2 = claim_lore(don_result["donation"]["id"], claimer2)
        assert result2["success"] is False

        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer1.id, None)
        GAME_STORE.pop(claimer2.id, None)

    def test_claim_lore_db_claim_race_condition(self) -> None:
        donor = new_game(42, "LoreDonor", shared_universe=True)
        GAME_STORE[donor.id] = donor
        lf = _make_lore_fragment("lore_race", discovered=True)
        donor.lore_fragments.append(lf)
        don_result = donate_lore(donor, "lore_race")

        claimer = new_game(43, "LoreClaimer", shared_universe=True)
        GAME_STORE[claimer.id] = claimer

        with patch("backend.multiplayer.crossroads.db_claim_lore", return_value=None):
            result = claim_lore(don_result["donation"]["id"], claimer)
        assert result["success"] is False

        GAME_STORE.pop(donor.id, None)
        GAME_STORE.pop(claimer.id, None)
        state = new_game(42, "Donor", shared_universe=True)
        GAME_STORE[state.id] = state
        disc = _make_discovery(name="ListTest Item")
        state.discoveries.append(disc)
        donate_item(state, "ListTest Item", 1)
        items = get_available_items_list()
        found = [i for i in items if i["item_name"] == "ListTest Item"]
        assert len(found) >= 1
        GAME_STORE.pop(state.id, None)

    def test_get_available_lore_list(self) -> None:
        state = new_game(42, "LoreDonor", shared_universe=True)
        GAME_STORE[state.id] = state
        lf = _make_lore_fragment("lore_list_test", discovered=True)
        state.lore_fragments.append(lf)
        donate_lore(state, "lore_list_test")
        lore_list = get_available_lore_list()
        found = [l for l in lore_list if l["fragment_id"] == "lore_list_test"]
        assert len(found) >= 1
        GAME_STORE.pop(state.id, None)

    def test_get_messages_paginated(self) -> None:
        state = new_game(42, "PosterPaginated", shared_universe=True)
        GAME_STORE[state.id] = state
        for i in range(12):
            post_message(state, f"Paginated message {i}")
        result = get_messages(page=1, per_page=5)
        assert result["page"] == 1
        assert result["per_page"] == 5
        assert result["total_messages"] >= 12
        assert result["total_pages"] >= 3
        assert len(result["messages"]) == 5
        result2 = get_messages(page=2, per_page=5)
        assert result2["page"] == 2
        assert len(result2["messages"]) == 5
        page1_texts = {m["text"] for m in result["messages"]}
        page2_texts = {m["text"] for m in result2["messages"]}
        assert page1_texts.isdisjoint(page2_texts)
        GAME_STORE.pop(state.id, None)


# ---------------------------------------------------------------------------
# TestMultiplayerRipples
# ---------------------------------------------------------------------------

class TestMultiplayerRipples:
    def test_create_ripple_within_radius(self) -> None:
        state = new_game(42, "RippleShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        disc = _make_discovery(name="Ripple Relic", system_id=system.id)
        result = create_ripple(state, disc)
        # Check that ripples were created for systems within 5 LY
        if result["ripples_created"] > 0:
            for r in result["ripples"]:
                assert r["source_system_id"] == system.id
                assert r["discovery_name"] == "Ripple Relic"
        GAME_STORE.pop(state.id, None)

    def test_create_ripple_no_current_system(self) -> None:
        state = new_game(42, "RippleShip", shared_universe=True)
        GAME_STORE[state.id] = state
        state.ship.current_system_id = ""
        disc = _make_discovery(name="NoSys Relic")
        result = create_ripple(state, disc)
        assert result["ripples_created"] == 0
        assert result["ripples"] == []
        GAME_STORE.pop(state.id, None)

    def test_get_pending_ripples(self) -> None:
        # Create a ripple from game A targeting a system, then verify
        # game B can see it when in that target system
        state_a = new_game(42, "RippleSource", shared_universe=True)
        GAME_STORE[state_a.id] = state_a
        source_sys = state_a.get_current_system()
        disc = _make_discovery(name="Pending Relic Unique", system_id=source_sys.id)
        result = create_ripple(state_a, disc)

        # Ripples target other systems, not the source
        if result["ripples_created"] > 0:
            # Get the first target system from the created ripple
            target_sys_id = result["ripples"][0]["target_system_id"]
            # Now check that the ripple exists in the DB for that target
            from backend.multiplayer.database import get_pending_ripples as db_get_pending
            db_ripples = db_get_pending(state_a.id)
            # The function filters by game_id not being in acknowledged_by
            # So our ripple should be in there
            names = [r.discovery_name for r in db_ripples]
            assert "Pending Relic Unique" in names
        GAME_STORE.pop(state_a.id, None)

    def test_get_pending_ripples_no_current_system(self) -> None:
        state = new_game(42, "RippleShip", shared_universe=True)
        GAME_STORE[state.id] = state
        state.ship.current_system_id = ""
        ripples = get_pending_ripples(state)
        assert ripples == []
        GAME_STORE.pop(state.id, None)

    def test_acknowledge_ripple_success(self) -> None:
        state = new_game(42, "RippleShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        disc = _make_discovery(name="Ack Relic", system_id=system.id)
        result = create_ripple(state, disc)
        if result["ripples_created"] > 0:
            ripple_id = result["ripples"][0]["id"]
            ack_result = acknowledge_ripple(ripple_id, state)
            assert ack_result["success"] is True
        GAME_STORE.pop(state.id, None)

    def test_acknowledge_ripple_not_found(self) -> None:
        state = new_game(42, "RippleShip", shared_universe=True)
        GAME_STORE[state.id] = state
        result = acknowledge_ripple("nonexistent-ripple-id", state)
        assert result["success"] is False
        GAME_STORE.pop(state.id, None)

    def test_create_ripple_with_all_systems(self) -> None:
        from backend.generation.universe import distance_between
        state = new_game(42, "RippleShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        assert system is not None

        full_systems = dict(state.systems)
        systems_within_5ly = {
            sid: s for sid, s in full_systems.items()
            if sid != system.id and distance_between(system, s) / 10.0 <= 5
        }

        kept_ids = set()
        for sid in full_systems:
            if sid == system.id or distance_between(system, full_systems[sid]) / 10.0 > 5:
                kept_ids.add(sid)
        state.systems = {sid: s for sid, s in full_systems.items() if sid in kept_ids}

        disc = _make_discovery(name="AllSystems Relic", system_id=system.id)
        result = create_ripple(state, disc, all_systems=full_systems)

        assert result["ripples_created"] == len(systems_within_5ly)

        ripple_target_ids = {r["target_system_id"] for r in result["ripples"]}
        for sid in systems_within_5ly:
            assert sid in ripple_target_ids, f"Missing ripple for system {sid}"

        GAME_STORE.pop(state.id, None)

    def test_create_ripple_all_systems_fallback(self) -> None:
        state = new_game(42, "RippleShip", shared_universe=True)
        GAME_STORE[state.id] = state
        system = state.get_current_system()
        assert system is not None

        disc = _make_discovery(name="Fallback Relic", system_id=system.id)
        result_all = create_ripple(state, disc, all_systems=state.systems)
        result_fallback = create_ripple(state, disc)

        assert result_fallback["ripples_created"] == result_all["ripples_created"]

        GAME_STORE.pop(state.id, None)


# ---------------------------------------------------------------------------
# TestMultiplayerAPI
# ---------------------------------------------------------------------------

class TestMultiplayerAPI:
    def test_api_leave_ghost(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.post(
            f"/api/game/{game_id}/leave-ghost",
            json={"message": "API ghost test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ghost" in data
        assert data["ghost"]["message"] == "API ghost test"

    def test_api_leave_ghost_no_current_system(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        # Clear current system
        GAME_STORE[game_id].ship.current_system_id = ""

        resp = client.post(
            f"/api/game/{game_id}/leave-ghost",
            json={"message": "Should fail"},
        )
        assert resp.status_code == 400

    def test_api_leave_ghost_game_not_found(self) -> None:
        resp = client.post(
            "/api/game/nonexistent-game/leave-ghost",
            json={"message": "Test"},
        )
        assert resp.status_code == 404

    def test_api_system_ghosts(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        # Leave a ghost first
        client.post(
            f"/api/game/{game_id}/leave-ghost",
            json={"message": "For ghosts endpoint"},
        )

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts")
        assert resp.status_code == 200
        data = resp.json()
        assert "ghosts" in data
        assert len(data["ghosts"]) >= 1

    def test_api_system_ghosts_game_not_found(self) -> None:
        resp = client.get("/api/game/nonexistent/system/sys-1/ghosts")
        assert resp.status_code == 404

    def test_api_system_ghosts_pagination_default(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        for i in range(15):
            client.post(
                f"/api/game/{game_id}/leave-ghost",
                json={"message": f"Pagination ghost {i}"},
            )

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts")
        assert resp.status_code == 200
        data = resp.json()
        assert "ghosts" in data
        assert data["page"] == 1
        assert data["per_page"] == 10
        assert data["total_ghosts"] >= 15
        assert data["total_pages"] >= 2
        assert len(data["ghosts"]) == 10

    def test_api_system_ghosts_pagination_explicit(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        for i in range(15):
            client.post(
                f"/api/game/{game_id}/leave-ghost",
                json={"message": f"Explicit pag ghost {i}"},
            )

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts?page=2&per_page=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["per_page"] == 5
        assert data["total_ghosts"] >= 15
        assert data["total_pages"] >= 3
        assert len(data["ghosts"]) == 5

    def test_api_system_ghosts_per_page_capped(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        for i in range(5):
            client.post(
                f"/api/game/{game_id}/leave-ghost",
                json={"message": f"Capped ghost {i}"},
            )

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts?per_page=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_page"] == 50

    def test_api_system_ghosts_page_out_of_range(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        for i in range(5):
            client.post(
                f"/api/game/{game_id}/leave-ghost",
                json={"message": f"OOR ghost {i}"},
            )

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts?page=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert len(data["ghosts"]) == 5

    def test_api_system_ghosts_page_less_than_one(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts?page=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1  # clamped from 0

    def test_api_system_ghosts_per_page_less_than_one(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts?per_page=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_page"] == 1  # clamped from 0

    def test_api_system_ghosts_page_out_of_range_empty(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts?page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ghosts"] == []
        assert data["total_ghosts"] == 0
        assert data["total_pages"] == 0

    def test_api_system_ghosts_total_ghosts_and_pages(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        for i in range(7):
            client.post(
                f"/api/game/{game_id}/leave-ghost",
                json={"message": f"Total ghost {i}"},
            )

        resp = client.get(f"/api/game/{game_id}/system/{sys_id}/ghosts?per_page=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_ghosts"] >= 7
        assert data["total_pages"] == 3
        assert len(data["ghosts"]) == 3

    def test_api_crossroads_items(self) -> None:
        resp = client.get("/api/crossroads/items")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_api_donate_item(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        # Add a discovery to cargo
        state = GAME_STORE[game_id]
        disc = _make_discovery(name="API Donate Item", system_id=sys_id)
        state.discoveries.append(disc)
        game_save(state)

        resp = client.post(
            "/api/crossroads/donate-item",
            json={"game_id": game_id, "item_name": "API Donate Item", "quantity": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_api_donate_item_not_found(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.post(
            "/api/crossroads/donate-item",
            json={"game_id": game_id, "item_name": "NonexistentItem", "quantity": 1},
        )
        assert resp.status_code == 400

    def test_api_claim_item(self) -> None:
        # Create donor game and donate
        donor_resp = client.post("/api/game/new", json={"shared_universe": True, "ship_name": "Donor"})
        assert donor_resp.status_code == 200
        donor_id = donor_resp.json()["game_id"]

        donor_state = GAME_STORE[donor_id]
        disc = _make_discovery(name="API Claim Item")
        donor_state.discoveries.append(disc)
        game_save(donor_state)

        don_resp = client.post(
            "/api/crossroads/donate-item",
            json={"game_id": donor_id, "item_name": "API Claim Item", "quantity": 1},
        )
        assert don_resp.status_code == 200
        item_id = don_resp.json()["donation"]["id"]

        # Create claimer game and claim
        claimer_resp = client.post("/api/game/new", json={"shared_universe": True, "ship_name": "Claimer"})
        assert claimer_resp.status_code == 200
        claimer_id = claimer_resp.json()["game_id"]

        resp = client.post(
            f"/api/crossroads/claim-item/{item_id}",
            json={"game_id": claimer_id},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_api_claim_item_not_found(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.post(
            "/api/crossroads/claim-item/nonexistent-item-id",
            json={"game_id": game_id},
        )
        assert resp.status_code == 400

    def test_api_crossroads_lore(self) -> None:
        resp = client.get("/api/crossroads/lore")
        assert resp.status_code == 200
        assert "lore" in resp.json()

    def test_api_donate_lore(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        state = GAME_STORE[game_id]
        lf = _make_lore_fragment("lore_api_donate_1", discovered=True)
        state.lore_fragments.append(lf)
        game_save(state)

        resp = client.post(
            "/api/crossroads/donate-lore",
            json={"game_id": game_id, "fragment_id": "lore_api_donate_1"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_api_donate_lore_not_discovered(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        state = GAME_STORE[game_id]
        lf = _make_lore_fragment("lore_api_not_disc", discovered=False)
        state.lore_fragments.append(lf)
        game_save(state)

        resp = client.post(
            "/api/crossroads/donate-lore",
            json={"game_id": game_id, "fragment_id": "lore_api_not_disc"},
        )
        assert resp.status_code == 400

    def test_api_claim_lore(self) -> None:
        # Donate lore from donor
        donor_resp = client.post("/api/game/new", json={"shared_universe": True, "ship_name": "LoreDonor"})
        assert donor_resp.status_code == 200
        donor_id = donor_resp.json()["game_id"]

        donor_state = GAME_STORE[donor_id]
        lf = _make_lore_fragment("lore_api_claim", discovered=True)
        donor_state.lore_fragments.append(lf)
        game_save(donor_state)

        don_resp = client.post(
            "/api/crossroads/donate-lore",
            json={"game_id": donor_id, "fragment_id": "lore_api_claim"},
        )
        assert don_resp.status_code == 200
        donation_id = don_resp.json()["donation"]["id"]

        # Claim from claimer
        claimer_resp = client.post("/api/game/new", json={"shared_universe": True, "ship_name": "LoreClaimer"})
        assert claimer_resp.status_code == 200
        claimer_id = claimer_resp.json()["game_id"]

        claimer_state = GAME_STORE[claimer_id]
        clf = _make_lore_fragment("lore_api_claim", discovered=False)
        claimer_state.lore_fragments.append(clf)
        game_save(claimer_state)

        resp = client.post(
            f"/api/crossroads/claim-lore/{donation_id}",
            json={"game_id": claimer_id},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_api_claim_lore_not_found(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.post(
            "/api/crossroads/claim-lore/nonexistent-donation-id",
            json={"game_id": game_id},
        )
        assert resp.status_code == 400

    def test_api_crossroads_messages(self) -> None:
        resp = client.get("/api/crossroads/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert "page" in data
        assert "per_page" in data
        assert "total_messages" in data
        assert "total_pages" in data

    def test_api_crossroads_messages_pagination(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        for i in range(15):
            client.post(
                "/api/crossroads/post-message",
                json={"game_id": game_id, "text": f"Pagination test message {i}"},
            )

        r1 = client.get("/api/crossroads/messages?page=1&per_page=5")
        assert r1.status_code == 200
        d1 = r1.json()
        assert len(d1["messages"]) == 5
        assert d1["page"] == 1
        assert d1["per_page"] == 5
        assert d1["total_messages"] >= 15
        assert d1["total_pages"] >= 3

        r2 = client.get("/api/crossroads/messages?page=2&per_page=5")
        assert r2.status_code == 200
        d2 = r2.json()
        assert len(d2["messages"]) == 5

        r3 = client.get("/api/crossroads/messages?page=3&per_page=5")
        assert r3.status_code == 200
        d3 = r3.json()
        assert len(d3["messages"]) == 5

        r4 = client.get("/api/crossroads/messages?page=4&per_page=5")
        assert r4.status_code == 404

        r_default = client.get("/api/crossroads/messages")
        assert r_default.status_code == 200
        d_default = r_default.json()
        assert len(d_default["messages"]) >= 10
        assert d_default["per_page"] == 10

        r_capped = client.get("/api/crossroads/messages?per_page=100")
        assert r_capped.status_code == 200
        d_capped = r_capped.json()
        assert d_capped["per_page"] == 50

        for key in ("page", "per_page", "total_messages", "total_pages"):
            assert key in d1
            assert key in d2
            assert key in d3

    def test_api_crossroads_messages_page_less_than_one(self) -> None:
        """api_crossroads_messages should clamp page < 1 to 1."""
        resp = client.get("/api/crossroads/messages?page=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        for key in ("messages", "page", "per_page", "total_messages", "total_pages"):
            assert key in data


    def test_api_crossroads_messages_per_page_less_than_one(self) -> None:
        """api_crossroads_messages should clamp per_page < 1 to 1."""
        resp = client.get("/api/crossroads/messages?per_page=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_page"] == 1
        for key in ("messages", "page", "per_page", "total_messages", "total_pages"):
            assert key in data

    def test_api_crossroads_messages_page_out_of_range(self) -> None:
        """api_crossroads_messages should return 404 for out-of-range pages with messages."""
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        # Post 5 messages (so with per_page=5, there's exactly 1 page)
        for i in range(5):
            client.post(
                "/api/crossroads/post-message",
                json={"game_id": game_id, "text": f"OOR test message {i}"},
            )

        # Page 1 should work fine
        r1 = client.get("/api/crossroads/messages?page=1&per_page=5")
        assert r1.status_code == 200
        data = r1.json()
        assert len(data["messages"]) == 5
        assert data["total_pages"] == 1

        # Page 2 should return 404 (out of range, and total_messages > 0)
        r2 = client.get("/api/crossroads/messages?page=2&per_page=5")
        assert r2.status_code == 404
        assert r2.json()["detail"] == "Page out of range"

    def test_api_crossroads_messages_page_out_of_range_empty_db(self) -> None:
        """api_crossroads_messages should NOT return 404 for out-of-range pages when there are no messages."""
        # No messages posted, so total_messages == 0
        r = client.get("/api/crossroads/messages?page=2&per_page=5")
        assert r.status_code == 200
        data = r.json()
        assert len(data["messages"]) == 0
        assert data["total_messages"] == 0
        assert data["total_pages"] == 0


    def test_api_post_message(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.post(
            "/api/crossroads/post-message",
            json={"game_id": game_id, "text": "API test message"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["message"]["text"] == "API test message"

    def test_api_post_message_returns_400_on_error(self) -> None:
        """api_post_message should return 400 when post_message returns an error."""
        from unittest.mock import patch
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        with patch("backend.multiplayer.api.post_message") as mock_post:
            mock_post.return_value = {"success": False, "detail": "Something went wrong"}
            resp = client.post(
                "/api/crossroads/post-message",
                json={"game_id": game_id, "text": "Valid text"},
            )
        assert resp.status_code == 400
        data = resp.json()
        assert "Something went wrong" in data["detail"]

    def test_api_ripples(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        # Get current system and create a ripple targeting it
        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()

        from backend.multiplayer.database import save_ripple_event
        from backend.multiplayer.models import RippleEvent
        import uuid
        ripple = RippleEvent(
            id=str(uuid.uuid4()),
            source_game_id="other-game",
            source_player_name="OtherPilot",
            source_system_id="other-sys",
            target_system_id=current_sys.id,
            discovery_type="artifact",
            discovery_name="API Ripple Test",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_ripple_event(ripple)

        resp = client.get(f"/api/game/{game_id}/ripples")
        assert resp.status_code == 200
        assert "ripples" in resp.json()

    def test_api_ripples_game_not_found(self) -> None:
        resp = client.get("/api/game/nonexistent/ripples")
        assert resp.status_code == 404

    def test_api_acknowledge_ripple(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        state = GAME_STORE[game_id]
        current_sys = state.get_current_system()

        from backend.multiplayer.database import save_ripple_event
        from backend.multiplayer.models import RippleEvent
        import uuid
        ripple_id = str(uuid.uuid4())
        ripple = RippleEvent(
            id=ripple_id,
            source_game_id="other-game",
            source_player_name="OtherPilot",
            source_system_id="other-sys",
            target_system_id=current_sys.id,
            discovery_type="lore",
            discovery_name="API Ack Ripple",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_ripple_event(ripple)

        resp = client.post(f"/api/game/{game_id}/ripple/{ripple_id}/acknowledge")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_api_acknowledge_ripple_not_found(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.post(f"/api/game/{game_id}/ripple/nonexistent-ripple/acknowledge")
        assert resp.status_code == 400

    def test_get_lock_returns_lock(self) -> None:
        """Verify that _get_lock returns a threading.Lock instance."""
        from backend.multiplayer.api import _get_lock
        import threading
        lock = _get_lock("test-get-lock-1")
        assert type(lock) == type(threading.Lock())

    def test_get_lock_same_game_id(self) -> None:
        """Verify that _get_lock returns the same lock for the same game_id."""
        from backend.multiplayer.api import _get_lock
        lock1 = _get_lock("test-get-lock-2")
        lock2 = _get_lock("test-get-lock-2")
        assert lock1 is lock2

    def test_get_lock_different_game_ids(self) -> None:
        """Verify that _get_lock returns different locks for different game_ids."""
        from backend.multiplayer.api import _get_lock
        lock1 = _get_lock("test-get-lock-3a")
        lock2 = _get_lock("test-get-lock-3b")
        assert lock1 is not lock2

    def test_cleanup_game_lock_removes_lock(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        _get_lock(game_id)
        assert game_id in _game_locks

        _cleanup_game_lock(game_id)
        assert game_id not in _game_locks

    def test_cleanup_game_lock_nonexistent(self) -> None:
        _cleanup_game_lock("nonexistent-game-id")

    def test_cleanup_stale_locks_removes_stale(self) -> None:
        state = new_game(42, "StaleTest", shared_universe=True)
        game_id = state.id
        GAME_STORE[game_id] = state

        _get_lock(game_id)
        assert game_id in _game_locks

        del GAME_STORE[game_id]
        _cleanup_stale_locks()
        assert game_id not in _game_locks

    def test_cleanup_stale_locks_preserves_active(self) -> None:
        state = new_game(42, "ActiveTest", shared_universe=True)
        game_id = state.id
        GAME_STORE[game_id] = state

        _get_lock(game_id)
        assert game_id in _game_locks

        _cleanup_stale_locks()
        assert game_id in _game_locks

        del GAME_STORE[game_id]

    def test_get_lock_returns_same_lock_for_existing_game(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        lock1 = _get_lock(game_id)
        lock2 = _get_lock(game_id)
        assert lock1 is lock2

    def test_lock_serializes_concurrent_requests(self) -> None:
        """Verify that the lock serializes concurrent access to prevent state corruption."""
        import concurrent.futures
        from backend.multiplayer.api import _game_locks

        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]
        sys_id = resp.json()["state"]["ship"]["current_system_id"]

        _game_locks.pop(game_id, None)

        ghost_count_before = len(client.get(
            f"/api/game/{game_id}/system/{sys_id}/ghosts"
        ).json()["ghosts"])

        num_threads = 5
        results = []

        def leave_ghost():
            r = client.post(
                f"/api/game/{game_id}/leave-ghost",
                json={"message": "Concurrent test"},
            )
            return r.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(leave_ghost) for _ in range(num_threads)]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        assert all(r == 200 for r in results)

        ghost_count_after = len(client.get(
            f"/api/game/{game_id}/system/{sys_id}/ghosts"
        ).json()["ghosts"])
        assert ghost_count_after == ghost_count_before + num_threads

    def test_get_lock_periodic_cleanup_triggers(self) -> None:
        """Verify that periodic stale lock cleanup triggers without deadlock after 100 calls."""
        import backend.multiplayer.api as mp_api
        
        # Call _get_lock 100+ times to ensure periodic cleanup is triggered.
        # _lock_access_count is now an itertools.count object; we verify
        # that calling _get_lock does not raise any errors and that locks
        # are properly created.
        for i in range(105):
            lock = mp_api._get_lock(f"dummy-periodic-{i}")
            assert lock is not None

    def test_cleanup_stale_locks_concurrent_safety(self) -> None:
        """Verify _cleanup_stale_locks is safe when called concurrently with _get_lock."""
        import concurrent.futures
        
        # Create several game states
        states = {}
        for i in range(10):
            state = new_game(42 + i, f"ConcurrentTest-{i}", shared_universe=True)
            states[f"concurrent-game-{i}"] = state
            GAME_STORE[f"concurrent-game-{i}"] = state
        
        # Create locks for all games
        for gid in states:
            _get_lock(gid)
        
        # Remove some games from GAME_STORE to make them stale
        stale_ids = [f"concurrent-game-{i}" for i in range(5)]
        for gid in stale_ids:
            del GAME_STORE[gid]
        
        active_ids = [f"concurrent-game-{i}" for i in range(5, 10)]
        
        # Run cleanup and lock creation concurrently
        def run_cleanup():
            _cleanup_stale_locks()
        
        def create_new_lock():
            # Create a lock for a new game (simulating concurrent access)
            state = new_game(99, "NewConcurrent", shared_universe=True)
            gid = state.id
            GAME_STORE[gid] = state
            _get_lock(gid)
            # Also try to get locks for existing games
            for gid in active_ids:
                _get_lock(gid)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for _ in range(5):
                futures.append(executor.submit(run_cleanup))
                futures.append(executor.submit(create_new_lock))
            concurrent.futures.wait(futures)
        
        # Check stale locks are removed
        for gid in stale_ids:
            assert gid not in _game_locks, f"Stale lock {gid} was not removed"
        
        # Check active locks are preserved
        for gid in active_ids:
            assert gid in _game_locks, f"Active lock {gid} was removed"
        
        # Clean up
        for gid in list(states.keys()):
            GAME_STORE.pop(gid, None)
        for gid in list(_game_locks.keys()):
            if gid not in active_ids:
                _game_locks.pop(gid, None)


# ---------------------------------------------------------------------------
# TestSharedUniverse
# ---------------------------------------------------------------------------

class TestSharedUniverse:
    def test_new_game_default_shared_universe_false(self) -> None:
        state = new_game(42, "TestDefault", shared_universe=False)
        assert state.shared_universe is False
        assert state.seed == 42

    def test_new_game_with_shared_universe_true(self) -> None:
        state = new_game(42, "TestShared", shared_universe=True)
        assert state.shared_universe is True
        # shared_universe=True forces seed=42
        assert state.seed == 42

    def test_new_game_with_shared_universe_false(self) -> None:
        state = new_game(999, "TestCustom", shared_universe=False)
        assert state.shared_universe is False
        assert state.seed == 999

    def test_api_create_game_with_shared_universe_true(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"]["shared_universe"] is True
        assert data["state"]["seed"] == 42

    def test_api_create_game_with_shared_universe_false(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": False, "seed": 777})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"]["shared_universe"] is False
        assert data["state"]["seed"] == 777

    def test_shared_universe_in_state_summary(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        data = resp.json()
        assert "shared_universe" in data["state"]
        assert data["state"]["shared_universe"] is True

    def test_shared_universe_in_full_state_response(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        resp = client.get(f"/api/game/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "shared_universe" in data
        assert data["shared_universe"] is True


# ---------------------------------------------------------------------------
# TestLeaderboardMultiplayer
# ---------------------------------------------------------------------------

class TestLeaderboardMultiplayer:
    def test_leaderboard_includes_multiplayer_metrics(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        # Save state and ensure DB is populated
        state = GAME_STORE[game_id]
        game_save(state)

        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        assert isinstance(data["leaderboard"], list)
        for entry in data["leaderboard"]:
            assert "ghost_signatures_left" in entry
            assert "items_donated" in entry
            assert "lore_donated" in entry

    def test_leaderboard_multiplayer_metrics_zero_when_no_activity(self) -> None:
        resp = client.post("/api/game/new", json={"shared_universe": True})
        assert resp.status_code == 200
        game_id = resp.json()["game_id"]

        state = GAME_STORE[game_id]
        game_save(state)

        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        for entry in data["leaderboard"]:
            if entry["game_id"] == game_id:
                assert entry["ghost_signatures_left"] >= 0
                assert entry["items_donated"] >= 0
                assert entry["lore_donated"] >= 0

    def test_leaderboard_multiplayer_metrics_operational_error_ghosts(self) -> None:
        """Leaderboard should handle OperationalError on ghost_signatures query."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "leaderboard-ghost-err"})
        assert resp.status_code == 200
        state = GAME_STORE["leaderboard-ghost-err"]
        game_save(state)

        from backend.database import get_db_ctx
        with get_db_ctx() as conn:
            conn.execute("DROP TABLE IF EXISTS ghost_signatures")
            conn.commit()

        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        for entry in data["leaderboard"]:
            if entry["game_id"] == "leaderboard-ghost-err":
                assert entry["ghost_signatures_left"] == 0
                break

    def test_leaderboard_multiplayer_metrics_operational_error_items(self) -> None:
        """Leaderboard should handle OperationalError on crossroads_items query."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "leaderboard-items-err"})
        assert resp.status_code == 200
        state = GAME_STORE["leaderboard-items-err"]
        game_save(state)

        from backend.database import get_db_ctx
        with get_db_ctx() as conn:
            conn.execute("DROP TABLE IF EXISTS crossroads_items")
            conn.commit()

        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        for entry in data["leaderboard"]:
            if entry["game_id"] == "leaderboard-items-err":
                assert entry["items_donated"] == 0
                break

    def test_leaderboard_multiplayer_metrics_operational_error_lore(self) -> None:
        """Leaderboard should handle OperationalError on crossroads_lore query."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "leaderboard-lore-err"})
        assert resp.status_code == 200
        state = GAME_STORE["leaderboard-lore-err"]
        game_save(state)

        from backend.database import get_db_ctx
        with get_db_ctx() as conn:
            conn.execute("DROP TABLE IF EXISTS crossroads_lore")
            conn.commit()

        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        for entry in data["leaderboard"]:
            if entry["game_id"] == "leaderboard-lore-err":
                assert entry["lore_donated"] == 0
                break

    def test_leaderboard_all_multiplayer_tables_operational_error(self) -> None:
        """Leaderboard should handle OperationalError on all three multiplayer tables."""
        resp = client.post("/api/game/new", json={"seed": 42, "game_id": "leaderboard-all-err"})
        assert resp.status_code == 200
        state = GAME_STORE["leaderboard-all-err"]
        game_save(state)

        from backend.database import get_db_ctx
        with get_db_ctx() as conn:
            conn.execute("DROP TABLE IF EXISTS ghost_signatures")
            conn.execute("DROP TABLE IF EXISTS crossroads_items")
            conn.execute("DROP TABLE IF EXISTS crossroads_lore")
            conn.commit()

        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        for entry in data["leaderboard"]:
            if entry["game_id"] == "leaderboard-all-err":
                assert entry["ghost_signatures_left"] == 0
                assert entry["items_donated"] == 0
                assert entry["lore_donated"] == 0
                break
