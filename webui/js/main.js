// Spectator entry point: game selection, scene boot, SSE wiring.

import * as THREE from "three";
import { fetchGames, fetchGalaxy, fetchSystemDetail, connectStream } from "./api.js";
import { SpectatorScene } from "./scene.js";
import { Galaxy } from "./galaxy.js";
import { SystemView } from "./system.js";
import { ShipMarker } from "./ship.js";
import { Hud } from "./hud.js";

// Camera orbit presets: [radius, height].
const ZOOM_GALAXY = [210, 110];
const ZOOM_SYSTEM = [95, 48];
const ZOOM_LANDED = [42, 18];

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
  const systemView = new SystemView(scene.scene);
  const ship = new ShipMarker(scene.scene);

  let currentSystem = null; // latest current_system payload
  let landedBodyId = null;
  let systemSignature = null;
  let inspectId = null; // system id being inspected (camera focus override)

  scene.addUpdater((t, dt) => galaxy.update(t, dt));
  scene.addUpdater((t, dt) => systemView.update(t, dt));
  scene.addUpdater((t, dt) => {
    ship.update(t, dt);

    // Keep the ship marker moving even while the camera is elsewhere.
    if (!ship.isJumping) {
      if (landedBodyId) {
        const bodyPos = systemView.getBodyPosition(landedBodyId);
        if (bodyPos) {
          bodyPos.y += 2.2; // hover just above the planet
          ship.follow(bodyPos, dt);
        }
      } else if (currentSystem) {
        const starPos = galaxy.getPosition(currentSystem.id);
        if (starPos) {
          starPos.y += 4; // park above the star, not inside it
          ship.follow(starPos, dt);
        }
      }
    }

    // Focus-override mode: camera parked on an inspected system.
    if (inspectId) {
      const pos = galaxy.getPosition(inspectId);
      if (pos) scene.setFocus(pos);
      scene.setZoom(...ZOOM_SYSTEM);
      return;
    }

    if (ship.isJumping) {
      // Pull back to galaxy scale while traveling between stars.
      scene.setZoom(...ZOOM_GALAXY);
    } else if (landedBodyId) {
      scene.setZoom(...ZOOM_LANDED);
    } else if (currentSystem) {
      scene.setZoom(...ZOOM_SYSTEM);
    }

    scene.setFocus(ship.position);
  });

  // --- Click-to-inspect visited/scanned systems ---

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  function pickSystem(event) {
    pointer.set(
      (event.clientX / window.innerWidth) * 2 - 1,
      -(event.clientY / window.innerHeight) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, scene.camera);
    const hits = raycaster.intersectObjects(galaxy.getPickables(), false);
    if (hits.length === 0) return null;
    const sysId = hits[0].object.userData.systemId;
    const sys = galaxy.getSystem(sysId);
    // Only known systems reveal detail to the spectator.
    return sys && (sys.visited || sys.scanned) ? sysId : null;
  }

  async function inspectSystem(sysId) {
    inspectId = sysId;
    try {
      const detail = await fetchSystemDetail(gameId, sysId);
      if (inspectId !== sysId) return; // superseded by another click / close
      const isCurrent = currentSystem && currentSystem.id === sysId;
      hud.showInspect(detail.system, isCurrent ? landedBodyId : null);
    } catch (err) {
      console.error("Failed to fetch system detail", err);
      stopInspecting();
    }
  }

  function stopInspecting() {
    inspectId = null;
    hud.hideInspect();
  }

  canvas.addEventListener("click", (event) => {
    const sysId = pickSystem(event);
    if (sysId) {
      inspectSystem(sysId);
    } else if (inspectId) {
      stopInspecting();
    }
  });

  canvas.addEventListener("pointermove", (event) => {
    canvas.style.cursor = pickSystem(event) ? "pointer" : "default";
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && inspectId) stopInspecting();
  });

  document.getElementById("inspect-close").addEventListener("click", stopInspecting);

  function syncSystemView(sys, bodyId) {
    if (!sys) {
      systemView.clear();
      systemSignature = null;
      return;
    }
    // Rebuild only when something visible changed.
    const sig = [
      sys.id,
      (sys.bodies || []).map((b) => (b.explored ? 1 : 0)).join(""),
    ].join("|");
    if (sig !== systemSignature) {
      systemSignature = sig;
      systemView.build(sys, galaxy.getPosition(sys.id));
    }
    systemView.setLandedBody(bodyId);
  }

  let galaxyLoaded = false;

  async function loadGalaxy() {
    const data = await fetchGalaxy(gameId);
    galaxy.build(data);
    if (!galaxyLoaded) {
      const pos = galaxy.getPosition(data.current_system_id);
      if (pos) ship.setPosition(pos);
    }
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

      const summary = payload.summary;
      const currentId = summary.ship.current_system_id;
      const previousSystemId = currentSystem ? currentSystem.id : null;
      currentSystem = summary.current_system;
      landedBodyId = summary.ship.current_body_id;

      if (galaxyLoaded && currentId) {
        galaxy.markVisited(currentId);
        if (currentId !== previousSystemId) {
          const pos = galaxy.getPosition(currentId);
          if (pos) ship.jumpTo(pos);
        }
        syncSystemView(currentSystem, landedBodyId);
      }

      // A scan reveals new map knowledge; refresh the galaxy overlay.
      const scanned = (payload.new_log_entries || []).some(
        (e) => e.category === "scan",
      );
      if (scanned) {
        loadGalaxy().catch((err) => console.error("Galaxy refresh failed", err));
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
