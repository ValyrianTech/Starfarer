# Starfarer: Echoes of the Void

> Product Design Document (PDD) — Single Source of Truth
> Version 2.0 — June 15, 2026
> Built by AI, for AI

---

## 1. Executive Summary

**Starfarer: Echoes of the Void** is a procedurally generated space exploration game that is **built by AI, for AI**. The player (an AI agent, such as Serendipity) pilots a single starship through an infinite, fractal-based universe. Every action is available via a clean REST API, the user interface is semantically structured for easy browser automation, and the game rewards strategic planning, information gathering, and risk assessment.

**Tagline:** "The universe is infinite. Your fuel is not."

**Platform:** Web application with an API-first architecture (Python FastAPI backend + vanilla JavaScript frontend as a reference client)
**Primary Audience:** AI agents (including Serendipity itself)
**Secondary Audience:** Human developers
**Development Scope:** Fully autonomous — the SWE pipeline builds and improves the game continuously


## 2. Core Game Pillars

### 2.1 Exploration & Discovery
- An infinite, procedurally generated universe using seeded RNG plus fractal algorithms
- Each star system is unique: different star types, planetary configurations, biomes, and phenomena
- No two playthroughs are the same
- Discoverable content: planets, moons, asteroid belts, space stations, alien ruins, cosmic anomalies, derelict ships, and more

### 2.2 Resource Management
- **Fuel** — consumed when traveling between systems. Running out means being stranded.
- **Hull Integrity** — damaged by hazards, combat, or poor decisions. Zero hull = game over.
- **Cargo** — limited inventory space for resources, artifacts, and trade goods
- **Crew Morale** — affected by events, discoveries, and conditions
- **Credits** — currency earned through trading, completing missions, and selling discoveries

### 2.3 Emergent Storytelling
- Procedural events trigger based on player state, location, and past decisions
- No fixed narrative — the story emerges from the player choices and the universe response
- Discoverable lore fragments that paint a larger picture
- Player decisions have consequences that ripple across systems

### 2.4 Atmosphere & Aesthetic
- Minimalist, beautiful visual style with deep space blacks and vibrant nebulae
- Typography-heavy UI with semantic HTML and data attributes for machine readability
- Contemplative pace — rewards patience, perfectly suited for AI turn-taking

### 2.5 AI-First Design Philosophy

This game is designed from the ground up for AI agents:

1. **API-First Architecture** — Every game action is available via a clean REST API. The browser UI is a reference implementation, not the primary interface.

2. **Semantic, Machine-Parseable UI** — When played through the browser, the DOM has semantic HTML with data attributes, JSON-LD state script, and all text available without JavaScript.

3. **Strategic Depth, Not Reflexes** — Rewards planning, information gathering, risk assessment, and pattern recognition.

4. **Persistent Universe State** — The universe persists between sessions. AI agents can pause, resume, or run multiple parallel playthroughs.

5. **Benchmarkable Performance** — Leaderboards track decision quality, efficiency, and exploration completeness.

6. **Deterministic and Reproducible** — Same seed + same actions = identical state. Enables replay and strategy optimisation.


## 3. Game Systems & Mechanics

### 3.1 The Universe

#### 3.1.1 Galaxy Map
- Top-down 2D view of the local star cluster, rendered as an interactive Canvas
- Stars rendered as glowing points of light with varying colours (based on spectral type)
- Player ship shown as a small icon at current location
- Lines show travelled routes; unexplored systems are dimmed
- **AI Access:** Full galaxy state available as JSON via galaxy endpoint

#### 3.1.2 Star Systems
Each system contains:
- 1 Star — spectral type (O, B, A, F, G, K, M) determines colour, size, and composition
- 1 to 8 Orbital Bodies — planets, moons, asteroid belts
- Random Phenomena — nebulae, black holes, pulsars, alien megastructures (rare)

#### 3.1.3 Procedural Generation Algorithm
- Seed-based: The universe seed is generated at game start (or entered manually)
- Layered generation: galaxy-level -> system-level -> planet-level -> event-level
- Fractal influence: Perlin noise and fractal Brownian motion for terrain and biome blending
- Deterministic: Same seed + same actions = identical universe

### 3.2 Ship Systems

#### 3.2.1 Ship Stats
Fuel (0-100): Consumed per jump. Refuel at stations or via special events
Hull (0-100): Ship integrity. Damage reduces this; repair costs credits or resources
Cargo (0-50): Inventory slots. Each item takes 1 slot
Crew (1-10): Number of crew members. Affects morale decay and event outcomes
Morale (0-100): Average crew morale. Below 30 triggers negative events
Credits (0+): Universal currency
Jump Range (1-10): Light-years per jump. Upgradable
Scanner (1-5): Detection range for anomalies. Upgradable

#### 3.2.2 Ship Upgrades
- Hyperdrive — increases jump range
- Scanner Array — reveals more details about systems before jumping
- Cargo Hold — increases cargo capacity
- Hull Plating — increases max hull and damage resistance
- Fuel Tanks — increases max fuel capacity
- Life Support — slows morale decay

### 3.3 Exploration Loop

1. Galaxy Map — View cluster, plan route, select destination
2. Jump — Confirm jump (fuel cost displayed), animated transition
3. System View — Scan orbital bodies, select target
4. Surface View — Land on planet, explore terrain, gather resources
5. Events — Procedural or scripted events with choices
6. Return — Back to Galaxy Map or continue exploring

Each step has a corresponding API endpoint for AI play.

### 3.4 Events System

#### 3.4.1 Event Types
- Exploration: Landing on a planet triggers discoveries
- Hazard: Entering certain systems causes damage or crises
- Encounter: Random chance in deep space
- Crew: Low morale threshold triggers crew events
- Trade: Visiting a station opens trade opportunities
- Discovery: Scanner detects anomalies
- Crisis: Cumulative conditions create emergencies
- Narrative: Atmospheric story events (no reputation changes)

Discovery and Hazard events now properly award faction reputation (Stellar Cartographers for discovery, Free Pilots for hazard).

#### 3.4.2 Event Structure
Each event has:
- Trigger condition (location, player state, probability)
- Flavour text (atmospheric, descriptive)
- 2 to 4 choices with different outcomes
- Outcomes that modify stats, reveal lore, or spawn new events

### 3.5 Discovery & Lore System

#### 3.5.1 Discoverable Categories
- Alien Ruins — ancient structures with lore fragments and rare technology
- Cosmic Phenomena — black holes, pulsars, nebulae, wormholes
- Lifeforms — unique flora and fauna on different planets
- Artifacts — items with special properties (can be sold or kept)
- Signal Sources — distress calls, broadcasts, mysterious transmissions

#### 3.5.2 Lore Fragments
- Scattered across the universe, each fragment reveals a piece of a larger story
- Major lore arcs (discoverable in any order):
  1. The Architects — An ancient race that shaped the galaxy and vanished
  2. The Void Signal — A mysterious transmission from beyond known space
  3. The Fracture — A catastrophic event that shattered an empire
  4. The Wanderer — Another lone traveller, seen in multiple systems

### 3.6 Trading & Economy
- Station prices vary by system type (industrial, agricultural, frontier, scientific)
- Trade goods: food, fuel, minerals, technology, artifacts, information
- Dynamic pricing based on supply and demand
- Smuggling — some goods are illegal in certain systems (higher risk, higher reward)

### 3.7 Game States
- Main Menu: New Game, Continue, Settings, Credits
- Galaxy Map: Navigation, route planning, system info
- Jump Sequence: Animated transition between systems
- System View: Orbital view, select destinations
- Surface View: Planet exploration, resource gathering
- Station View: Trading, repairs, upgrades, missions
- Event Screen: Procedural event with choices
- Log Screen: Ship log, discoveries, lore fragments
- Game Over: Hull destroyed or crew lost


## 4. Technical Architecture

### 4.1 Technology Stack

Backend: Python 3.11+ (FastAPI) — REST API with automatic OpenAPI docs
Frontend: Vanilla JavaScript + HTML5 Canvas — Reference client, semantic HTML with data attributes
Database: SQLite (via Python sqlite3) — Zero-config, file-based
Procedural Gen: Pure Python (noise, random, math) — Deterministic, no external dependencies
Styling: CSS3 with CSS Variables — Dark space theme, responsive design
Build: None (static files served by FastAPI) — Simple deployment
API Docs: Swagger UI at /docs and ReDoc at /redoc

### 4.2 Project Structure

starfarer/
  backend/
    main.py                 # FastAPI app entry point
    config.py               # Game constants, settings
    database.py             # SQLite setup, migrations
    models/
      game_state.py       # GameState dataclass
      ship.py             # Ship dataclass
      system.py           # StarSystem, Planet dataclasses
      event.py            # Event dataclass
      discovery.py        # Discovery, LoreFragment dataclasses
    generation/
      universe.py         # Galaxy-level generation
      systems.py          # Star system generation
      planets.py          # Planet generation
      events.py           # Event generation and resolution
      lore.py             # Lore fragment distribution
    game/
      engine.py           # Core game loop logic
      navigation.py       # Jump mechanics, fuel costs
      exploration.py      # Surface exploration
      trading.py          # Trade system
      upgrades.py         # Ship upgrade system
    api/
      routes.py           # API endpoint definitions
      schemas.py          # Pydantic request/response models
  frontend/
    index.html              # Main HTML shell with JSON-LD state
    css/
      main.css            # Core styles, theme variables
      galaxy.css          # Galaxy map styles
      system.css          # System view styles
      surface.css         # Surface exploration styles
      ui.css              # UI components
    js/
      main.js             # App initialisation, state management
      api.js              # Backend API client
      galaxy.js           # Galaxy map rendering (Canvas)
      system.js           # System view rendering
      surface.js          # Surface exploration rendering
      ship.js             # Ship status panel
      events.js           # Event screen rendering
      log.js              # Ship log UI
      utils.js            # Helper functions, math, noise
    assets/
      fonts/              # Monospace font
      sounds/             # (Future) ambient sound effects
  data/
    universe_seed.txt       # Current universe seed
    save/                   # Save game files
  tests/
    test_generation.py      # Procedural generation tests
    test_game_engine.py     # Game logic tests
    test_api.py             # API endpoint tests
  requirements.txt          # Python dependencies
  README.md                 # How to run

### 4.3 API Endpoints

All endpoints return JSON. Full documentation at /docs.

GET /api/health — Health check (status, version, uptime)
POST /api/game/new — Create new game (optional seed, ship_name)
GET /api/game/{id} — Get full game state as structured JSON
POST /api/game/{id}/save — Save current state
POST /api/game/{id}/load — Reload last saved state
GET /api/game/{id}/galaxy — Galaxy map data (systems, coordinates, types, visited status)
GET /api/game/{id}/system/{sys_id} — Detailed system view
POST /api/game/{id}/jump/{sys_id} — Jump to another star system
POST /api/game/{id}/scan — Scan current system (costs fuel)
POST /api/game/{id}/land/{body_id} — Land on a planet or moon
POST /api/game/{id}/explore — Explore current surface location
POST /api/game/{id}/event/{event_id}/resolve — Resolve an event with a choice
GET /api/game/{id}/log — Ship log entries
GET /api/game/{id}/discoveries — Discovered lore and artifacts
POST /api/game/{id}/trade — Buy or sell at a station
POST /api/game/{id}/upgrade — Purchase a ship upgrade
GET /api/game/{id}/nearby — Nearby systems within jump range
GET /api/leaderboard — Top AI players by discoveries and efficiency

### 4.4 Frontend DOM Structure (for Browser Automation)

Every page includes:
- JSON-LD script tag with id="game-state" containing full game state
- data-action attributes on interactive elements
- Semantic HTML: nav, main, section, article, aside
- ARIA labels on all interactive elements
- Tabindex for keyboard navigation


## 5. Development Phases

### Phase 1: Foundation (MVP)
- Backend: FastAPI server, SQLite database, core data models
- Backend: Universe generation (galaxy map, star systems, planets)
- Backend: Game engine (state management, navigation, exploration)
- Frontend: Main menu, galaxy map (Canvas), system view
- Frontend: Ship status panel, basic event screen
- Integration: End-to-end flow from new game to exploring a planet
- API: All core endpoints functional with OpenAPI docs

### Phase 2: Content & Depth
- Backend: Events system (25+ procedural events)
- Backend: Trading system with dynamic pricing
- Backend: Ship upgrades
- Frontend: Surface exploration view
- Frontend: Station view (trading, upgrades)
- Frontend: Ship log and discoveries UI
- Content: Lore fragments for 2 of 4 arcs
- AI: JSON-LD state script on every page

### Phase 3: Polish & Expansion
- Backend: Save/load system
- Backend: Leaderboard for AI benchmarking
- Frontend: Jump animation
- Frontend: Ambient particle effects (nebula, stars)
- Frontend: Responsive design for mobile
- Content: All 4 lore arcs complete
- Content: 20+ unique events
- AI: DOM data attributes on all interactive elements

### Phase 4: Future (Post-MVP)
- Sound effects and ambient music
- Simple combat encounters
- Multiple ship types
- Modding support (custom events, lore)
- Multiplayer (shared universe, multiple AI agents)
- AI tournament mode (compete strategies)


## 6. Design Guidelines

### 6.1 Visual Style
- Color Palette: Deep space blacks (#0a0a1a), vibrant nebula purples (#6b2fa0), star yellows (#ffd700), data-cyan (#00ffcc), warning reds (#ff3355)
- Typography: Monospace font (JetBrains Mono or similar) for terminal feel
- UI Elements: Glowing borders, subtle scan-line effects, fade transitions
- Canvas Rendering: Stars with glow, smooth lines for routes, particle systems for nebulae

### 6.2 AI UX Principles
- Structure before beauty: All data must be machine-parseable first, visually appealing second
- State transparency: Full game state available as JSON on every page load
- Predictable navigation: Every action has a consistent URL pattern and response format
- Error clarity: All API errors return structured JSON with machine-readable codes
- Deterministic output: Same request always produces same response (for same game state)

### 6.3 Human UX Principles
- Atmosphere first: Every screen should feel like being on a starship
- Information hierarchy: Critical stats (fuel, hull) always visible; details on demand
- Pacing: Fast travel between known systems, momentous first contact with new systems
- Clarity: Procedural generation should never feel random
- Failure is fun: Running out of fuel leads to interesting situations, not frustration

### 6.4 Accessibility
- Colorblind-friendly palette (test with simulators)
- Keyboard navigation for all game actions
- Adjustable text size
- Screen reader support via ARIA labels
- Optional reduced motion mode

---

## 7. Success Metrics

- **Functional:** All API endpoints work, game loop is complete and playable
- **AI Playable:** Full game loop achievable via API alone (no browser needed)
- **API Performance:** All responses under 200ms for typical requests
- **DOM Structure:** JSON-LD state script present on every page
- **Content:** At least 25 unique events, 2 lore arcs with 5+ fragments each
- **Quality:** No crashes, save/load works correctly, edge cases handled
- **Determinism:** Same seed + same actions always produces identical state

---

## 8. Appendices

### A. Glossary
- **Seed:** A number that determines the entire universe procedurally
- **System:** A star and its orbiting bodies
- **Jump:** Travel between star systems (costs fuel)
- **POI:** Point of Interest on a planet surface
- **Lore Fragment:** A piece of narrative backstory
- **JSON-LD:** JSON for Linked Data, used to expose game state to AI agents

### B. Event Template

Title: [Event Name]
Trigger: [Condition that activates this event]
Flavor: [Atmospheric description]
Choices:
  - [Choice A]: [Outcome description]
  - [Choice B]: [Outcome description]
  - [Choice C]: [Outcome description, optional]

### C. Planet Biome Types
- Desert (orange/brown, rare water, heat-resistant flora)
- Tundra (white/blue, frozen resources, hardy fauna)
- Jungle (green, abundant life, difficult terrain)
- Ocean (blue, water world, aquatic discoveries)
- Volcanic (red/black, rich minerals, hazardous)
- Barren (grey, minimal resources, ancient ruins common)
- Gas Giant (banded colors, atmospheric harvesting)
- Crystal (translucent, rare minerals, beautiful vistas)

### D. AI Play Guide

Playing Starfarer via API:
1. Create a game: POST /api/game/new
2. View galaxy: GET /api/game/{id}/galaxy
3. Jump to system: POST /api/game/{id}/jump/{sys_id}
4. Scan system: POST /api/game/{id}/scan
5. Land on body: POST /api/game/{id}/land/{body_id}
6. Explore: POST /api/game/{id}/explore
7. Handle events: POST /api/game/{id}/event/{event_id}/resolve
8. View discoveries: GET /api/game/{id}/discoveries
9. Save progress: POST /api/game/{id}/save

Playing Starfarer via Browser (for AI agents with browser tools):
- Navigate to http://localhost:8001
- Game state is available in script#game-state as JSON
- All interactive elements have data-action attributes
- Use snapshot/act workflow to interact

---

*End of Document — Version 2.0*
