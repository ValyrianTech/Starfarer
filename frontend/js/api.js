const API_BASE = '/api';

async function apiCall(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) {
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(API_BASE + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

const API = {
  health: () => apiCall('GET', '/health'),
  newGame: (seed, shipName, gameId) =>
    apiCall('POST', '/game/new', { seed, ship_name: shipName, game_id: gameId }),
  getGame: (gameId) => apiCall('GET', `/game/${gameId}`),
  galaxy: (gameId) => apiCall('GET', `/game/${gameId}/galaxy`),
  systemDetail: (gameId, sysId) => apiCall('GET', `/game/${gameId}/system/${sysId}`),
  jump: (gameId, sysId) => apiCall('POST', `/game/${gameId}/jump/${sysId}`),
  scan: (gameId) => apiCall('POST', `/game/${gameId}/scan`),
  land: (gameId, bodyId) => apiCall('POST', `/game/${gameId}/land/${bodyId}`),
  explore: (gameId) => apiCall('POST', `/game/${gameId}/explore`),
  resolveEvent: (gameId, eventId, choiceIdx) =>
    apiCall('POST', `/game/${gameId}/event/${eventId}/resolve`, { choice_index: choiceIdx }),
  log: (gameId) => apiCall('GET', `/game/${gameId}/log`),
  discoveries: (gameId) => apiCall('GET', `/game/${gameId}/discoveries`),
  trade: (gameId, action, item, quantity) =>
    apiCall('POST', `/game/${gameId}/trade`, { action, item, quantity }),
  upgrade: (gameId, upgradeId) =>
    apiCall('POST', `/game/${gameId}/upgrade`, { upgrade_id: upgradeId }),
  upgradesInfo: (gameId) => apiCall('GET', `/game/${gameId}/upgrades`),
  nearby: (gameId) => apiCall('GET', `/game/${gameId}/nearby`),
  save: (gameId) => apiCall('POST', `/game/${gameId}/save`),
  load: (gameId) => apiCall('POST', `/game/${gameId}/load`),
  leaderboard: () => apiCall('GET', '/leaderboard'),
  lore: (gameId) => apiCall('GET', `/game/${gameId}/lore`),
  cargo: (gameId, sort = 'value', order = 'desc') => apiCall('GET', `/game/${gameId}/cargo?sort=${encodeURIComponent(sort)}&order=${encodeURIComponent(order)}`),
  codex: (gameId) => apiCall('GET', `/game/${gameId}/codex`),
};
