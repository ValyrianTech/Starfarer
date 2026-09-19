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
 * EventSource reconnects automatically; onReconnect fires when the
 * connection is re-established so the caller can refresh galaxy data.
 *
 * EventSource cannot set request headers, so a short-lived, single-use ticket
 * (minted with the `X-Game-Token` header) is passed as the `ticket` query
 * parameter instead of the long-lived game token. When no token is available
 * the stream is opened without a query parameter, which is correct while token
 * enforcement is disabled.
 */
export async function connectStream(gameId, { onState, onStatus }) {
  const url = new URL(`${BASE}/spectate/${gameId}/stream`, window.location.origin);
  const ticket = await fetchStreamTicket(gameId);
  if (ticket) {
    url.searchParams.set("ticket", ticket);
  }
  const source = new EventSource(url.toString());
  let hadError = false;

  source.addEventListener("open", () => {
    if (hadError) {
      hadError = false;
      onStatus("reconnected");
    } else {
      onStatus("connected");
    }
  });

  source.addEventListener("state", (evt) => {
    try {
      onState(JSON.parse(evt.data));
    } catch (err) {
      console.error("Bad state payload", err);
    }
  });

  source.addEventListener("end", () => {
    // Server ended the stream; EventSource will reconnect on its own.
    onStatus("lost");
  });

  source.addEventListener("error", () => {
    hadError = true;
    onStatus("lost");
  });

  return source;
}
