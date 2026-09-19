// Read-only API helpers for the spectator webui.

const BASE = "/api";

/**
 * Resolve the current game token, in priority order:
 *   1. the `token` URL search parameter,
 *   2. `window.localStorage` under the key `starfarer_game_token`.
 * Returns `null` when no token is present. localStorage access is wrapped in a
 * try/catch so a disabled/blocked store never throws and falls through to null.
 */
export function getToken() {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("token");
  if (fromUrl) {
    return fromUrl;
  }
  try {
    return window.localStorage.getItem("starfarer_game_token") || null;
  } catch (err) {
    return null;
  }
}

/**
 * Persist (or clear) the game token in localStorage under the key
 * `starfarer_game_token`. A non-empty token is stored; a falsy value removes the
 * key. Guarded by try/catch so a disabled/blocked store never throws.
 */
export function setToken(tokenVal) {
  try {
    if (tokenVal) {
      window.localStorage.setItem("starfarer_game_token", tokenVal);
    } else {
      window.localStorage.removeItem("starfarer_game_token");
    }
  } catch (err) {
    // Ignore storage failures; token simply won't persist.
  }
}

export async function fetchJSON(path) {
  const token = getToken();
  const res = token
    ? await fetch(`${BASE}${path}`, { headers: { "X-Game-Token": token } })
    : await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json();
}

export function fetchGames() {
  return fetchJSON("/spectate/games");
}

export function fetchGalaxy(gameId) {
  return fetchJSON(`/game/${gameId}/galaxy`);
}

export function fetchFullState(gameId) {
  return fetchJSON(`/game/${gameId}`);
}

export function fetchSystemDetail(gameId, sysId) {
  return fetchJSON(`/game/${gameId}/system/${sysId}`);
}

/**
 * Mint a short-lived, single-use stream ticket for the spectator stream.
 *
 * The long-lived game token is sent via the `X-Game-Token` header so it is
 * never placed in a URL (where it would leak into logs, browser history and
 * `Referer` headers). Only the returned short-lived ticket is passed to the
 * EventSource URL. Returns `null` when no token is available or the ticket
 * request fails, so the caller can still open an unauthenticated stream (which
 * succeeds while token enforcement is disabled).
 */
async function fetchStreamTicket(gameId) {
  const token = getToken();
  if (!token) {
    return null;
  }
  try {
    const res = await fetch(`${BASE}/spectate/${gameId}/stream-ticket`, {
      method: "POST",
      headers: { "X-Game-Token": token },
    });
    if (!res.ok) {
      return null;
    }
    const body = await res.json();
    return body.ticket || null;
  } catch (err) {
    return null;
  }
}

/**
 * Connect to the SSE spectator stream for a game.
 *
 * EventSource cannot set request headers, so a short-lived, single-use ticket
 * (minted with the `X-Game-Token` header) is passed as the `ticket` query
 * parameter instead of the long-lived game token. When no token is available
 * the stream is opened without a query parameter, which is correct while token
 * enforcement is disabled.
 *
 * The ticket is single-use (consumed by the server on first connect), so the
 * browser's built-in EventSource reconnect cannot be used for the
 * authenticated path: it would retry the same URL with the already-consumed
 * ticket and get a 403. Instead, on any disconnect (network error or the
 * server's `end` event) we close the current source, mint a fresh ticket and
 * open a new EventSource ourselves, after a short backoff.
 *
 * The returned handle has a `close()` method that stops reconnection.
 */
export async function connectStream(gameId, { onState, onStatus }) {
  const baseUrl = new URL(
    `${BASE}/spectate/${gameId}/stream`,
    window.location.origin,
  );
  const RECONNECT_DELAY_MS = 1000;

  let source = null;
  let reconnectTimer = null;
  let hasConnected = false;
  let closed = false;

  function buildUrl(ticket) {
    const url = new URL(baseUrl.toString());
    if (ticket) {
      url.searchParams.set("ticket", ticket);
    }
    return url.toString();
  }

  function attach(nextSource) {
    nextSource.addEventListener("open", () => {
      if (hasConnected) {
        onStatus("reconnected");
      } else {
        hasConnected = true;
        onStatus("connected");
      }
    });

    nextSource.addEventListener("state", (evt) => {
      try {
        onState(JSON.parse(evt.data));
      } catch (err) {
        console.error("Bad state payload", err);
      }
    });

    nextSource.addEventListener("end", () => {
      onStatus("lost");
      scheduleReconnect();
    });

    nextSource.addEventListener("error", () => {
      onStatus("lost");
      scheduleReconnect();
    });
  }

  function scheduleReconnect() {
    if (closed || reconnectTimer !== null) {
      return;
    }
    // Close the current source so the browser's native retry is bypassed and
    // it does not re-attempt the stale (consumed-ticket) URL.
    if (source) {
      source.close();
      source = null;
    }
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      reconnect();
    }, RECONNECT_DELAY_MS);
  }

  async function reconnect() {
    if (closed) {
      return;
    }
    const ticket = await fetchStreamTicket(gameId);
    source = new EventSource(buildUrl(ticket));
    attach(source);
  }

  const ticket = await fetchStreamTicket(gameId);
  source = new EventSource(buildUrl(ticket));
  attach(source);

  return {
    close() {
      closed = true;
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (source) {
        source.close();
        source = null;
      }
    },
    get source() {
      return source;
    },
  };
}
