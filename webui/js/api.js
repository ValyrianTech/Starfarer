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
 * Connect to the SSE spectator stream for a game.
 * EventSource reconnects automatically; onReconnect fires when the
 * connection is re-established so the caller can refresh galaxy data.
 *
 * EventSource cannot set request headers, so the game token (when present) is
 * passed as the `token` query parameter, which the spectator stream accepts as a
 * supported alternative to the `X-Game-Token` header. The URL is left unchanged
 * when no token is available.
 */
export function connectStream(gameId, { onState, onStatus }) {
  const url = new URL(`${BASE}/spectate/${gameId}/stream`, window.location.origin);
  const token = getToken();
  if (token) {
    url.searchParams.set("token", token);
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
