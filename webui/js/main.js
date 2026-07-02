// Spectator entry point: game selection, scene boot, SSE wiring.

import { fetchGames, fetchGalaxy, connectStream } from "./api.js";
import { SpectatorScene } from "./scene.js";
import { Galaxy } from "./galaxy.js";
import { ShipMarker } from "./ship.js";
import { Hud } from "./hud.js";

const hud = new Hud();
let spectator = null;

async function boot() {
  const params = new URLSearchParams(window.location.search);
  const gameId = params.get("game");
  if (gameId) {
    startSpectating(gameId);
  } else {
    showGamePicker();
  }
}

async function showGamePicker() {
  const overlay = document.getElementById("picker-overlay");
  const list = document.getElementById("picker-list");
  const empty = document.getElementById("picker-empty");
  overlay.classList.remove("hidden");

  let games = [];
  try {
    games = (await fetchGames()).games;
  } catch (err) {
    console.error("Failed to fetch games", err);
  }

  if (games.length === 0) {
    empty.classList.remove("hidden");
    // Poll until a game appears.
    setTimeout(showGamePicker, 5000);
    return;
  }

  empty.classList.add("hidden");
  list.innerHTML = "";
  for (const game of games) {
    const item = document.createElement("div");
    item.className = "picker-item";

    const left = document.createElement("div");
    const name = document.createElement("div");
    name.className = "pi-name";
    name.textContent = game.ship_name;
    const meta = document.createElement("div");
    meta.className = "pi-meta";
    meta.textContent =
      `${game.systems_visited} systems · ${game.credits.toLocaleString()} cr · ` +
      `updated ${formatAgo(game.updated_at)}`;
    left.append(name, meta);
    item.appendChild(left);

    if (game.active) {
      const badge = document.createElement("span");
      badge.className = "pi-badge";
      badge.textContent = "ACTIVE";
      item.appendChild(badge);
    }

    item.addEventListener("click", () => {
      const url = new URL(window.location.href);
      url.searchParams.set("game", game.game_id);
      window.history.replaceState(null, "", url);
      overlay.classList.add("hidden");
      startSpectating(game.game_id);
    });
    list.appendChild(item);
  }
}

function formatAgo(isoString) {
  const then = new Date(isoString).getTime();
  if (Number.isNaN(then)) return "unknown";
  const secs = Math.max(0, (Date.now() - then) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

async function startSpectating(gameId) {
  const canvas = document.getElementById("scene");
  const scene = new SpectatorScene(canvas);
  const galaxy = new Galaxy(scene.scene);
  const ship = new ShipMarker(scene.scene);

  scene.addUpdater((t, dt) => galaxy.update(t, dt));
  scene.addUpdater((t, dt) => {
    ship.update(t, dt);
    scene.setFocus(ship.position);
  });

  let galaxyLoaded = false;

  async function loadGalaxy() {
    const data = await fetchGalaxy(gameId);
    galaxy.build(data);
    const pos = galaxy.getPosition(data.current_system_id);
    if (pos) ship.setPosition(pos);
    galaxyLoaded = true;
  }

  try {
    await loadGalaxy();
  } catch (err) {
    console.error("Failed to load galaxy", err);
    document.getElementById("picker-overlay").classList.remove("hidden");
    showGamePicker();
    return;
  }

  hud.show();
  hud.setConnection("connecting");

  spectator = connectStream(gameId, {
    onState(payload) {
      hud.setConnection("connected");
      hud.update(payload);

      const currentId = payload.summary.ship.current_system_id;
      if (galaxyLoaded && currentId) {
        galaxy.markVisited(currentId);
        const pos = galaxy.getPosition(currentId);
        if (pos) ship.jumpTo(pos);
      }
    },
    onStatus(status) {
      hud.setConnection(status);
      if (status === "reconnected") {
        // Refresh galaxy flags in case we missed jumps while disconnected.
        loadGalaxy().catch((err) => console.error("Galaxy refresh failed", err));
      }
    },
  });
}

boot();
