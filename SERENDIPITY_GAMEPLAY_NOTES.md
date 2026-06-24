# Serendipity's Starfarer Gameplay Notes

> Personal log and strategy guide for AI-agent playthroughs.
> Last updated: 15 June 2026

---

## 1. Getting Started

### 1.1 New Game
- Use the browser UI at `http://localhost:8001/`
- Set a fun seed (e.g., 42) and name your ship (default: "Serendipity")
- **Important:** After starting, immediately take a full-page snapshot (`interactive: false`) to read the system description and ship status

### 1.2 API vs Browser
- **Browser UI** is good for visual exploration and events
- **REST API** is more efficient for repetitive actions (land, explore, trade)
- To use the API, you need the `game_id` — find it in the embedded JSON-LD in the page source: `document.getElementById('game-state').textContent`
- API base URL: `http://localhost:8001/api/game/{game_id}`

---

## 2. Known Issues & Workarounds

### 2.1 Planet Interaction (CRITICAL)
- **Issue:** Planet names (e.g., "Pandora", "Umbriel") are displayed as plain text in the system view, not as clickable elements with `data-action` attributes in the browser snapshot
- **Workaround:** Use the REST API directly to land on bodies:
  ```
  POST /api/game/{game_id}/land/{body_id}
  ```
  You need the `body_id` from the system details endpoint:
  ```
  GET /api/game/{game_id}/system/{system_id}
  ```

### 2.2 Event Modal Overlay
- **Issue:** When an event modal is active, it intercepts all pointer events, making it impossible to click navigation buttons (Galaxy, Log, Save)
- **Workaround:** Always resolve events first by clicking one of the choice buttons (refs e5, e6, e7, etc.)
- **Tip:** After resolving, take a snapshot to confirm the modal is gone before proceeding

### 2.3 Navigation State Confusion
- **Issue:** Clicking "Back" from the Log view doesn't always return to the System View — it can stay in the Log view
- **Workaround:** Navigate via Galaxy view first (click "Galaxy", then "System View") to reset the navigation state
- **Better approach:** Use the API to get game state instead of navigating through the UI

### 2.4 Redundant Scanning
- **Issue:** I scanned the same system 5 times, wasting 25 fuel! The system only needs to be scanned once
- **Lesson:** Check if the system has already been scanned before clicking "Scan System"
- **Tip:** Look at the system description — if it lists orbital bodies with descriptions, it's already scanned
- **API check:** `GET /api/game/{game_id}/system/{system_id}` — if it returns body details, no need to scan again

### 2.5 Fuel Management
- **Issue:** Wasted fuel on redundant scans (5 fuel each × 4 extra scans = 20 fuel wasted!)
- **Lesson:** Always check if an action is necessary before performing it
- **Critical threshold:** Keep fuel above 15 at all times (enough for at least one jump)

---

## 3. Gameplay Strategy (Refined)

### 3.1 Early Game (Credits < 2000)
1. **Scan the starting system ONCE** — costs 5 fuel
2. **Get system details via API** to find body IDs
3. **Land on each body** via API — planets first (more discoveries)
4. **Explore each body** via API — costs 2 fuel per explore
5. **Sell all discoveries** to build credits
6. **Prioritize hyperdrive upgrade** (500 credits base)

### 3.2 Event Decision Framework
| Event Type | Recommended Choice | Reasoning |
|-----------|-------------------|-----------|
| Life Support Failure | Emergency repair | Saves crew, costs fuel/hull but survivable |
| Mysterious Beacon | Decode first | Avoids traps, gives credits + morale |
| Pirate/Combat | Avoid if possible | Hull damage is expensive to repair |
| Trade Opportunity | Take it | Free credits and resources |
| Crew Morale Event | Boost morale | Low morale triggers cascading failures |
| Black Hole Event | Depends on situation | Time Dilation: study for credits. Hawking Radiation: harvest for fuel. Spaghettification: gravity assist for fuel. Accretion Disk: probe for credits. Gravitational Lens: study for credits+morale. |

### 3.3 Resource Priorities
1. **Fuel** — lifeblood of exploration. Never go below 15.
2. **Hull** — repair at stations when below 40 (20 hull per repair point, ~40 credits)
3. **Morale** — keep above 40. Buy life support upgrade if it dips.
4. **Credits** — spend on upgrades, not consumables (unless critical)

**Reputation Note:** Faction reputation is a valuable resource. At reputation **20 or higher** with a faction, resolving events matching that faction's type triggers bonus rewards: Stellar Cartographers gives +10 credits and +1 morale per event, Void Traders gives +10 credits per event, and Free Pilots gives +5 morale per event. These bonuses stack with the event's normal outcome rewards.

### 3.4 Upgrade Priority
1. **Hyperdrive** (+1 jump range, 500 credits) — unlocks more systems
2. **Fuel Tanks** (+20 max fuel, 300 credits) — extends operational range
3. **Scanner** (+1 level, 400 credits) — detects phenomena before jumping
4. **Hull Plating** (+20 max hull, 450 credits) — survivability
5. **Cargo Hold** (+10 capacity, 350 credits) — more discoveries before selling
6. **Life Support** (-1 morale decay, 400 credits) — late-game quality of life

### 3.5 Biome Value Ranking (for exploration priority)
1. **Ocean** — high-value lifeforms
2. **Jungle** — high-value lifeforms
3. **Crystal** — rare minerals
4. **Volcanic** — rare minerals
5. **Desert** — moderate value
6. **Tundra** — moderate value
7. **Asteroid Belt** — lower value (skip if fuel is tight)

---

## 4. API Quick Reference (for direct use)

| Action | Endpoint | Notes |
|--------|----------|-------|
| Get game state | `GET /api/game/{id}` | Full state dump |
| Get system details | `GET /api/game/{id}/system/{sid}` | Get body IDs |
| Land on body | `POST /api/game/{id}/land/{bid}` | Use body_id from system details |
| Explore surface | `POST /api/game/{id}/explore` | Costs 2 fuel |
| Resolve event | `POST /api/game/{id}/event/{eid}/resolve` | Body: `{"choice_index": N}` |
| Sell discoveries | `POST /api/game/{id}/trade` | Body: `{"action": "sell", "item": "artifact"}` |
| Buy fuel | `POST /api/game/{id}/trade` | Body: `{"action": "buy", "item": "fuel", "quantity": N}` |
| Repair hull | `POST /api/game/{id}/trade` | Body: `{"action": "buy", "item": "repair", "quantity": N}` |
| View upgrades | `GET /api/game/{id}/upgrades` | Available upgrades |
| Buy upgrade | `POST /api/game/{id}/upgrade` | Body: `{"upgrade_id": "hyperdrive"}` |
| Nearby systems | `GET /api/game/{id}/nearby` | Sorted by distance |
| Jump to system | `POST /api/game/{id}/jump/{sid}` | Costs 3 fuel per LY |
| View paginated log | `GET /api/game/{id}/log/paginated?page=1&per_page=20&category=trade&search=artifact` | Paginated, filterable, searchable log |

---

## 5. Key Lessons Learned

1. **Don't scan a system more than once** — I wasted 20 fuel on this!
2. **Always resolve events before navigating** — the modal blocks all other interactions
3. **Use the API for repetitive tasks** — the browser UI is great for initial exploration but slow for grinding
4. **Check fuel before every action** — running out = game over
5. **Decode warnings before acting** — it saved me from a pirate trap and earned credits
6. **Emergency repairs save lives** — the 20 fuel/20 hull cost was worth it to keep all 4 crew members

---

*End of notes. The universe is infinite. My fuel is not.*

### 1.3 Finding the Game ID (CRITICAL - Updated 15 June 2026)
The game ID is **not** available in the static HTML source — the JSON-LD element (`<script id="game-state">`) is populated dynamically by JavaScript after the page loads, so `curl` or `ReadFile` on the raw HTML will only show `{}`.

**Method 1: SQLite Database (RELIABLE)**
The game stores all state in a SQLite database at:
```
/home/wouter/Repos/starfarer/data/starfarer.db
```
Query it with Python:
```python
import sqlite3
conn = sqlite3.connect('/home/wouter/Repos/starfarer/data/starfarer.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM games')
rows = cursor.fetchall()
# Each row: (id, seed, ship_name, created_at, updated_at, state_json)
# The most recent game is usually the last row
```
**Tip:** The `state_json` column contains the full game state as a JSON string — you can extract everything from there without even calling the API!

**Method 2: Browser JavaScript (if browser is open)**
Execute in the browser console:
```javascript
JSON.parse(document.getElementById('game-state').textContent).id
```
But this only works if the browser has already rendered the page with the game loaded.

**Method 3: API Health Check (if you know the ID)**
Once you have the ID, verify it works:
```
curl http://localhost:8001/api/game/{game_id}
```
Returns full game state including ship status, current system, discoveries, etc.
