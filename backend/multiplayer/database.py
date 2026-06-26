"""
Multiplayer persistence layer for the 'Ghosts in the Void' system.

Provides SQLite tables and CRUD functions for ghost signatures,
crossroads donations and messages, and discovery ripple events.
Uses the same database file as the main application via
``backend.database.get_db_ctx()``.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.database import get_db_ctx
from backend.multiplayer.models import (
    GhostSignature, CrossroadsItem, CrossroadsLore,
    CrossroadsMessage, RippleEvent,
)

_MULTIPLAYER_MIGRATIONS = """
    CREATE TABLE IF NOT EXISTS ghost_signatures (
        id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL,
        player_name TEXT NOT NULL,
        system_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        discoveries TEXT NOT NULL DEFAULT '[]',
        message TEXT,
        body_visits TEXT NOT NULL DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS crossroads_items (
        id TEXT PRIMARY KEY,
        donor_game_id TEXT NOT NULL,
        donor_name TEXT NOT NULL,
        item_name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        message TEXT,
        claimed INTEGER NOT NULL DEFAULT 0,
        claimer_game_id TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS crossroads_lore (
        id TEXT PRIMARY KEY,
        donor_game_id TEXT NOT NULL,
        donor_name TEXT NOT NULL,
        fragment_id TEXT NOT NULL,
        message TEXT,
        claimed INTEGER NOT NULL DEFAULT 0,
        claimer_game_id TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS crossroads_messages (
        id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL,
        player_name TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ripple_events (
        id TEXT PRIMARY KEY,
        source_game_id TEXT NOT NULL,
        source_player_name TEXT NOT NULL,
        source_system_id TEXT NOT NULL,
        target_system_id TEXT NOT NULL,
        discovery_type TEXT NOT NULL,
        discovery_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        acknowledged_by TEXT NOT NULL DEFAULT '[]'
    );

    CREATE INDEX IF NOT EXISTS idx_ghost_signatures_system
        ON ghost_signatures(system_id);
    CREATE INDEX IF NOT EXISTS idx_crossroads_items_claimed
        ON crossroads_items(claimed);
    CREATE INDEX IF NOT EXISTS idx_crossroads_lore_claimed
        ON crossroads_lore(claimed);
    CREATE INDEX IF NOT EXISTS idx_crossroads_messages_expires
        ON crossroads_messages(expires_at);
    CREATE INDEX IF NOT EXISTS idx_ripple_events_target
        ON ripple_events(target_system_id);
"""


def init_multiplayer_db() -> None:
    """Create multiplayer database tables if they do not already exist.

    Should be called at application startup alongside the main
    ``init_db()`` in ``backend.database``.
    """
    with get_db_ctx() as conn:
        conn.executescript(_MULTIPLAYER_MIGRATIONS)
        conn.commit()


def _load_json_column(value: str) -> list:
    """Safely load a JSON column value into a list.

    :param value: The raw JSON string from the database.
    :type value: str
    :returns: The deserialized list, or an empty list on error.
    :rtype: list
    """
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Ghost Signatures
# ---------------------------------------------------------------------------


def save_ghost_signature(ghost: GhostSignature) -> None:
    """Persist a ghost signature to the database.

    Uses INSERT OR REPLACE to handle both new and updated signatures.

    :param ghost: The ghost signature to save.
    :type ghost: GhostSignature
    """
    with get_db_ctx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ghost_signatures "
            "(id, game_id, player_name, system_id, timestamp, discoveries, message, body_visits) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ghost.id,
                ghost.game_id,
                ghost.player_name,
                ghost.system_id,
                ghost.timestamp,
                json.dumps(ghost.discoveries),
                ghost.message,
                json.dumps(ghost.body_visits),
            ),
        )
        conn.commit()


def get_ghost_signatures(system_id: str) -> list[GhostSignature]:
    """Retrieve all ghost signatures recorded for a given star system.

    :param system_id: The unique identifier of the star system.
    :type system_id: str
    :returns: A list of :class:`GhostSignature` instances.
    :rtype: list[GhostSignature]
    """
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT * FROM ghost_signatures WHERE system_id = ? ORDER BY timestamp DESC",
            (system_id,),
        ).fetchall()
    result: list[GhostSignature] = []
    for row in rows:
        result.append(GhostSignature(
            id=row["id"],
            game_id=row["game_id"],
            player_name=row["player_name"],
            system_id=row["system_id"],
            timestamp=row["timestamp"],
            discoveries=_load_json_column(row["discoveries"]),
            message=row["message"],
            body_visits=_load_json_column(row["body_visits"]),
        ))
    return result


# ---------------------------------------------------------------------------
# Crossroads Items
# ---------------------------------------------------------------------------


def save_crossroads_item(item: CrossroadsItem) -> None:
    """Persist a crossroads item donation to the database.

    :param item: The crossroads item to save.
    :type item: CrossroadsItem
    """
    with get_db_ctx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO crossroads_items "
            "(id, donor_game_id, donor_name, item_name, quantity, message, claimed, claimer_game_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.donor_game_id,
                item.donor_name,
                item.item_name,
                item.quantity,
                item.message,
                1 if item.claimed else 0,
                item.claimer_game_id,
                item.created_at,
            ),
        )
        conn.commit()


def get_available_items() -> list[CrossroadsItem]:
    """Retrieve all unclaimed crossroads items.

    :returns: A list of unclaimed :class:`CrossroadsItem` instances.
    :rtype: list[CrossroadsItem]
    """
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT * FROM crossroads_items WHERE claimed = 0 ORDER BY created_at DESC",
        ).fetchall()
    result: list[CrossroadsItem] = []
    for row in rows:
        result.append(CrossroadsItem(
            id=row["id"],
            donor_game_id=row["donor_game_id"],
            donor_name=row["donor_name"],
            item_name=row["item_name"],
            quantity=row["quantity"],
            message=row["message"],
            claimed=bool(row["claimed"]),
            claimer_game_id=row["claimer_game_id"],
            created_at=row["created_at"],
        ))
    return result


def claim_item(item_id: str, claimer_game_id: str) -> bool:
    """Mark a crossroads item as claimed by a player.

    Only succeeds if the item exists and has not already been claimed.

    :param item_id: The unique identifier of the item to claim.
    :type item_id: str
    :param claimer_game_id: The game ID of the claiming player.
    :type claimer_game_id: str
    :returns: ``True`` if the claim was successful, ``False`` otherwise.
    :rtype: bool
    """
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, claimed FROM crossroads_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if not row or row["claimed"]:
            return False
        conn.execute(
            "UPDATE crossroads_items SET claimed = 1, claimer_game_id = ? WHERE id = ?",
            (claimer_game_id, item_id),
        )
        conn.commit()
        return True


# ---------------------------------------------------------------------------
# Crossroads Lore
# ---------------------------------------------------------------------------


def save_crossroads_lore(lore: CrossroadsLore) -> None:
    """Persist a crossroads lore donation to the database.

    :param lore: The lore donation to save.
    :type lore: CrossroadsLore
    """
    with get_db_ctx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO crossroads_lore "
            "(id, donor_game_id, donor_name, fragment_id, message, claimed, claimer_game_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lore.id,
                lore.donor_game_id,
                lore.donor_name,
                lore.fragment_id,
                lore.message,
                1 if lore.claimed else 0,
                lore.claimer_game_id,
                lore.created_at,
            ),
        )
        conn.commit()


def get_available_lore() -> list[CrossroadsLore]:
    """Retrieve all unclaimed lore donations from the Crossroads.

    :returns: A list of unclaimed :class:`CrossroadsLore` instances.
    :rtype: list[CrossroadsLore]
    """
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT * FROM crossroads_lore WHERE claimed = 0 ORDER BY created_at DESC",
        ).fetchall()
    result: list[CrossroadsLore] = []
    for row in rows:
        result.append(CrossroadsLore(
            id=row["id"],
            donor_game_id=row["donor_game_id"],
            donor_name=row["donor_name"],
            fragment_id=row["fragment_id"],
            message=row["message"],
            claimed=bool(row["claimed"]),
            claimer_game_id=row["claimer_game_id"],
            created_at=row["created_at"],
        ))
    return result


def claim_lore(donation_id: str, claimer_game_id: str) -> bool:
    """Mark a crossroads lore donation as claimed by a player.

    Only succeeds if the lore donation exists and has not already
    been claimed.

    :param donation_id: The unique identifier of the lore donation.
    :type donation_id: str
    :param claimer_game_id: The game ID of the claiming player.
    :type claimer_game_id: str
    :returns: ``True`` if the claim was successful, ``False`` otherwise.
    :rtype: bool
    """
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, claimed FROM crossroads_lore WHERE id = ?",
            (donation_id,),
        ).fetchone()
        if not row or row["claimed"]:
            return False
        conn.execute(
            "UPDATE crossroads_lore SET claimed = 1, claimer_game_id = ? WHERE id = ?",
            (claimer_game_id, donation_id),
        )
        conn.commit()
        return True


# ---------------------------------------------------------------------------
# Crossroads Messages
# ---------------------------------------------------------------------------


def save_crossroads_message(msg: CrossroadsMessage) -> None:
    """Persist a player-posted message to the Crossroads.

    :param msg: The message to save.
    :type msg: CrossroadsMessage
    """
    with get_db_ctx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO crossroads_messages "
            "(id, game_id, player_name, text, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                msg.id,
                msg.game_id,
                msg.player_name,
                msg.text,
                msg.created_at,
                msg.expires_at,
            ),
        )
        conn.commit()


def get_recent_messages(limit: int = 50) -> list[CrossroadsMessage]:
    """Retrieve recent crossroads messages, excluding expired ones.

    :param limit: Maximum number of messages to return.
    :type limit: int
    :returns: A list of :class:`CrossroadsMessage` instances ordered
        by creation time descending.
    :rtype: list[CrossroadsMessage]
    """
    now = datetime.now(timezone.utc).isoformat()
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT * FROM crossroads_messages WHERE expires_at > ? "
            "ORDER BY created_at DESC LIMIT ?",
            (now, limit),
        ).fetchall()
    result: list[CrossroadsMessage] = []
    for row in rows:
        result.append(CrossroadsMessage(
            id=row["id"],
            game_id=row["game_id"],
            player_name=row["player_name"],
            text=row["text"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        ))
    return result


def cleanup_expired_messages() -> int:
    """Remove all crossroads messages that have passed their expiration time.

    :returns: The number of rows deleted.
    :rtype: int
    """
    now = datetime.now(timezone.utc).isoformat()
    with get_db_ctx() as conn:
        cursor = conn.execute(
            "DELETE FROM crossroads_messages WHERE expires_at <= ?",
            (now,),
        )
        conn.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Ripple Events
# ---------------------------------------------------------------------------


def save_ripple_event(ripple: RippleEvent) -> None:
    """Persist a discovery ripple event to the database.

    :param ripple: The ripple event to save.
    :type ripple: RippleEvent
    """
    with get_db_ctx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ripple_events "
            "(id, source_game_id, source_player_name, source_system_id, "
            "target_system_id, discovery_type, discovery_name, created_at, "
            "acknowledged_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ripple.id,
                ripple.source_game_id,
                ripple.source_player_name,
                ripple.source_system_id,
                ripple.target_system_id,
                ripple.discovery_type,
                ripple.discovery_name,
                ripple.created_at,
                json.dumps(ripple.acknowledged_by),
            ),
        )
        conn.commit()


def get_pending_ripples(game_id: str) -> list[RippleEvent]:
    """Retrieve ripple events for a game that have not been acknowledged.

    A ripple is pending if the given ``game_id`` is not yet in its
    ``acknowledged_by`` list and the event was created within the
    last 7 days.

    :param game_id: The unique identifier of the game.
    :type game_id: str
    :returns: A list of pending :class:`RippleEvent` instances.
    :rtype: list[RippleEvent]
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT * FROM ripple_events WHERE created_at > ? ORDER BY created_at DESC",
            (cutoff,),
        ).fetchall()
    result: list[RippleEvent] = []
    for row in rows:
        acked = _load_json_column(row["acknowledged_by"])
        if game_id not in acked:
            result.append(RippleEvent(
                id=row["id"],
                source_game_id=row["source_game_id"],
                source_player_name=row["source_player_name"],
                source_system_id=row["source_system_id"],
                target_system_id=row["target_system_id"],
                discovery_type=row["discovery_type"],
                discovery_name=row["discovery_name"],
                created_at=row["created_at"],
                acknowledged_by=acked,
            ))
    return result


def acknowledge_ripple(ripple_id: str, game_id: str) -> bool:
    """Mark a ripple event as acknowledged by a game.

    Only succeeds if the ripple exists and the game has not already
    acknowledged it.

    :param ripple_id: The unique identifier of the ripple event.
    :type ripple_id: str
    :param game_id: The game ID to add to the acknowledged_by list.
    :type game_id: str
    :returns: ``True`` if the acknowledgment was successful, ``False`` otherwise.
    :rtype: bool
    """
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, acknowledged_by FROM ripple_events WHERE id = ?",
            (ripple_id,),
        ).fetchone()
        if not row:
            return False
        acked = _load_json_column(row["acknowledged_by"])
        if game_id in acked:
            return False
        acked.append(game_id)
        conn.execute(
            "UPDATE ripple_events SET acknowledged_by = ? WHERE id = ?",
            (json.dumps(acked), ripple_id),
        )
        conn.commit()
        return True
