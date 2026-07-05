// Read-only API helpers for the spectator webui.

const BASE = "/api";

export async function fetchJSON(path) {
  const res = await fetch(`${BASE}${path}`);
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
 */
export function connectStream(gameId, { onState, onStatus }) {
  const source = new EventSource(`${BASE}/spectate/${gameId}/stream`);
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
