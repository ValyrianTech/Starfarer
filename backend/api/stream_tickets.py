"""Short-lived, single-use stream tickets for the spectator SSE endpoint.

The spectator Server-Sent Events endpoint (``GET /api/spectate/{game_id}/stream``)
is consumed by browser ``EventSource`` clients, which cannot set custom HTTP
headers. Embedding the long-lived per-game auth token in the request URL would
leak that credential into access logs, reverse-proxy logs, browser history and
``Referer`` headers. Instead, a caller first mints a short-lived, single-use
``ticket`` (authenticating with the ``X-Game-Token`` header) and passes only
that ticket in the stream URL. Tickets expire quickly and can be redeemed at
most once, so a leaked ticket has minimal value.
"""

import secrets
import threading
import time

# Tickets are intentionally short-lived: they only need to survive the brief
# window between minting and the browser opening the EventSource connection.
STREAM_TICKET_TTL_SECONDS = 30.0

# Maps ticket string -> (game_id, expiry in time.monotonic() seconds).
_STREAM_TICKETS: dict[str, tuple[str, float]] = {}
_STREAM_TICKETS_LOCK = threading.Lock()


def issue_stream_ticket(game_id: str) -> str:
    """Mint a fresh short-lived, single-use stream ticket for a game.

    Expired entries are pruned opportunistically before adding the new
    ticket so the in-memory store cannot grow without bound.

    :param game_id: The unique identifier of the game the ticket is bound to.
    :type game_id: str
    :returns: The opaque ticket string to pass as the ``ticket`` query
        parameter of the spectator stream.
    :rtype: str
    """
    now = time.monotonic()
    ticket = secrets.token_urlsafe(32)
    with _STREAM_TICKETS_LOCK:
        expired = [
            key for key, (_, expiry) in _STREAM_TICKETS.items() if expiry <= now
        ]
        for key in expired:
            _STREAM_TICKETS.pop(key, None)
        _STREAM_TICKETS[ticket] = (game_id, now + STREAM_TICKET_TTL_SECONDS)
    return ticket


def consume_stream_ticket(ticket: str, game_id: str) -> bool:
    """Redeem a stream ticket exactly once for the matching game.

    The ticket is always removed from the store when present (single-use),
    regardless of whether it is still valid, so a ticket can never be
    replayed. Returns ``True`` only when the ticket existed, was bound to
    the same ``game_id``, and had not yet expired.

    :param ticket: The ticket string supplied by the caller, or ``None``.
    :type ticket: str
    :param game_id: The unique identifier of the game being streamed.
    :type game_id: str
    :returns: ``True`` if the ticket authorized this request, else ``False``.
    :rtype: bool
    """
    if not isinstance(ticket, str) or not ticket:
        return False
    with _STREAM_TICKETS_LOCK:
        entry = _STREAM_TICKETS.pop(ticket, None)
    if entry is None:
        return False
    bound_game_id, expiry = entry
    if bound_game_id != game_id:
        return False
    return expiry > time.monotonic()
