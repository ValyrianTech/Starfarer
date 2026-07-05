# Spectator Web UI Improvements — Progress & Handoff

Goal: make the spectator web UI (`webui/`) show far more of the game state than just
the galaxy — individual planets, landed-on bodies, system details, etc.
Agreed plan: 4 phases. All 4 phases are implemented (untested).

## Architecture recap

- `webui/` is a static Three.js app (vendored three.js via import map, no build step).
- Data sources:
  - `GET /api/game/{id}/galaxy` — one-time galaxy overview (`get_galaxy` in
    `backend/game/manager.py`).
  - `GET /api/spectate/{id}/stream` — SSE; each `state` event carries
    `{ summary, pending_events, new_log_entries, last_log_id }`.
    `summary.current_system` is the **full** `StarSystem.to_dict()` including all
    bodies (`biome`, `size`, `distance_from_star`, `poi_count`, `explored`, ...),
    and `summary.ship.current_body_id` says where the ship is landed.
- Body facts (backend): planet size 2–8, moon size 1–3; `distance_from_star` ∈ (0,1);
  body types: `planet`, `moon`, `asteroid_belt`; moon ids are `{parentBodyId}_m{n}`;
  biome colors live in `BIOME_COLORS` in `backend/config.py` (mirrored in JS).

## Phase 1 — HUD enrichment (DONE)

- `webui/index.html`: added `#hud-left` wrapper, `#system-panel` (name, type, tags,
  phenomenon desc, `#body-list`), and `#discovery-ticker` in the footer.
- `webui/js/hud.js`: added `_updateSystemPanel`, `_makeTag`, `_renderBodyList`
  (per-body row: ▼ landed / ✓ explored / · unexplored, biome + POI count),
  `_updateDiscoveryTicker` (filters `new_log_entries` for discovery/lore, flashes);
  `_updateShip` now shows breadcrumb "System › Body" via `current_body_id`.
- `webui/css/spectator.css`: styles for system panel, `.sys-tag`, `.body-row`
  (+`.landed` highlight), discovery ticker + `ticker-flash` animation.

## Phase 2 — System detail view (DONE)

- NEW `webui/js/system.js` — `SystemView` class:
  - `build(sysData, centerPos)` renders orbit rings, biome-colored planets
    (`MeshStandardMaterial` + PointLight at star), moons orbiting parents,
    asteroid-belt point rings, trading-station octahedron, name labels
    (dimmed when unexplored). Unexplored bodies darkened 0.5×.
  - `setLandedBody(bodyId)` — pulsing green ring on the landed planet.
  - `getBodyPosition(bodyId)` — world position for the ship to follow.
  - `update(t, dt)` — advances orbits, pulses highlight.
- `webui/js/scene.js`: added eased camera zoom (`setZoom(radius, height)`,
  `desiredOrbitRadius/Height` lerped in `_animate`).
- `webui/js/ship.js`: added `isJumping` getter and `follow(vec3, dt)` (per-frame
  lerp that doesn't reset the trail).
- `webui/js/galaxy.js`: exported `makeLabelSprite`.
- `webui/js/main.js`: zoom presets `ZOOM_GALAXY [210,110]`, `ZOOM_SYSTEM [95,48]`,
  `ZOOM_LANDED [42,18]`. Per-frame updater: jumping → galaxy zoom; landed → follow
  planet (+2.2 y hover) + landed zoom; else hover above star + system zoom.
  `syncSystemView()` rebuilds `SystemView` only when a signature
  (`sys.id` + explored flags) changes; `ship.jumpTo` now fires only on system change.

## Phase 3 — Galaxy enrichment (DONE)

- `backend/game/manager.py` `get_galaxy()`: now also returns
  `has_trading_station` and `system_type` per system.
- `webui/js/galaxy.js`: `_applyVisitedStyle` → `_applyKnowledgeStyle` with three
  states (visited / scanned intermediate / unknown dim); body-count sub-label and
  trading-station marker only visible once scanned or visited.
- `webui/js/main.js`: `loadGalaxy()` re-fetched when a `new_log_entries` item has
  `category === "scan"` (scan reveals map knowledge); ship position only snapped
  on first load.

## Phase 4 — Click-to-inspect visited systems (DONE)

- `webui/js/api.js`: added `fetchSystemDetail(gameId, sysId)` →
  `GET /api/game/{game_id}/system/{sys_id}`. Note: the backend endpoint does
  **not** gate on visited/scanned — gating is done client-side (spectator only
  inspects systems where `sys.visited || sys.scanned` per galaxy data).
- `webui/js/galaxy.js`: each star node gets an invisible oversized pick sphere
  (`SphereGeometry(4.5)`, `material.visible=false`, `userData.systemId`);
  added `getPickables()` and `getSystem(id)`.
- `webui/js/main.js`: `THREE.Raycaster` click/pointermove picking on the
  canvas (cursor becomes pointer over known stars). `inspectId` state acts as
  a focus-override in the per-frame updater: camera parks on the inspected
  star at `ZOOM_SYSTEM` while the ship marker keeps following its own logic.
  Click empty space, Esc, or the ✕ button (`#inspect-close`) returns to
  ship-following. Stale-response guard in `inspectSystem` (checks `inspectId`
  after await).
- `webui/index.html`: `#inspect-panel` added under `#hud-left` (name, type,
  close button, tags, phenomenon desc, `#inspect-body-list`).
- `webui/js/hud.js`: `_renderBodyList` now takes the target list element;
  added `showInspect(sys, currentBodyId)` (adds a "scanned only" tag for
  unvisited systems) and `hideInspect()`.
- `webui/css/spectator.css`: inspect-panel styles (amber border, close button,
  `.sys-tag.scanned`, scrollable body list). Panel is `pointer-events: auto`
  (hud/hud-left remain `none`), so the ✕ works and clicks elsewhere fall
  through to the canvas.

## Verification status

- No automated tests were run; nothing has been visually verified yet
  (no `node` on this machine for even a syntax check).
- To test: start backend (FastAPI serves `webui/`), open spectator page, pick a
  game, then via API: jump / scan / land / explore and watch:
  breadcrumb, body list, discovery ticker, planet orbits, landing zoom + green
  ring, scan lighting up systems + sub-labels/station markers.
- Known things to eyeball: orbit radii (`ORBIT_BASE 6`, `ORBIT_STEP 3.2` in
  `system.js`) vs. star spacing (~40–60 world units) for visual overlap;
  `PointLight` intensity 220 (three.js r155+ physical units) may need tuning;
  zoom preset values are guesses.
- Phase 4 things to eyeball: pick-sphere radius 4.5 vs. star spacing (clicks
  near overlapping stars), hover-raycast cost with many systems, whether
  inspecting the *current* system should instead show the SystemView planets
  (currently it only shows the panel + galaxy node).
