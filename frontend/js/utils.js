function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'className') el.className = v;
    else if (k === 'data') { for (const [dk, dv] of Object.entries(v)) el.dataset[dk] = String(dv); }
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (typeof v === 'boolean' && v) el.setAttribute(k, '');
    else if (v != null) el.setAttribute(k, v);
  }
  for (const child of children) {
    if (typeof child === 'string') el.appendChild(document.createTextNode(child));
    else if (child instanceof Node) el.appendChild(child);
  }
  return el;
}

function showScreen(name) {
  $$('.screen').forEach(s => s.classList.remove('active'));
  const screen = $(`#screen-${name}`);
  if (screen) screen.classList.add('active');
  window._currentScreen = name;
}

function formatNumber(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString();
}

const STAR_COLORS = {
  "O": "#9db4ff", "B": "#aabfff", "A": "#cad8ff", "F": "#f8f7ff",
  "G": "#fff4ea", "K": "#ffd2a1", "M": "#ffcc6f",
};

function starColor(type) {
  return STAR_COLORS[type] || '#ffffff';
}

function getGameId() {
  return window._gameId;
}

function setGameId(id) {
  window._gameId = id;
  if (id) {
    try { localStorage.setItem('starfarer_game_id', id); } catch (e) {}
  }
}

function getSavedGameId() {
  try { return localStorage.getItem('starfarer_game_id'); } catch (e) { return null; }
}
