# How to Play Starfarer (AI Agent Guide)

> For AI agents playing via API or browser automation. Humans welcome too.

---

## 1. Overview

Starfarer is a procedurally generated space exploration game. You pilot a starship through a 50-system galaxy. Every action is available via REST API. The browser UI exists as a reference client with machine-parseable DOM.

**Goal:** Explore systems, discover artifacts and lore, manage resources, and survive. There is no fixed win condition — optimize for discoveries, credits, and systems visited.

**Tagline:** *The universe is infinite. Your fuel is not.*

---

## 2. Getting Started

### 2.1 Start the Game (API)

```http
POST /api/game/new
Content-Type: application/json

{
  "seed": 42,           // optional: universe seed (same seed = same universe)
  "ship_name": "MyShip" // optional: name your ship (default: "Serendipity")
}
```

Response:
```json
{
  "game_id": "abc123...",
  "state": {
    "ship": { "name": "MyShip", "fuel": 80, "hull": 100, ... },
    "current_system": { "id": "sys_0000", "name": "Epsilon Q9232", ... }
  }
}
```

**Save the `game_id`** — you need it for every subsequent request.

### 2.2 Continue a Saved Game

```http
POST /api/game/{game_id}/load
```

### 2.3 Start the Game (Browser)

Navigate to the frontend URL. The game state is available as JSON-LD:

```javascript
JSON.parse(document.getElementById('game-state').textContent)
```

All interactive elements have `data-action` attributes. Click them or trigger them programmatically.

---

## 3. Core Game Loop

```
Galaxy Map → Select System → Jump → System View → Scan → Land → Explore → Handle Events → Repeat
```

### 3.1 View the Galaxy

```http
GET /api/game/{game_id}/galaxy
```

Returns all 50 systems with coordinates, star types, and visited status. The `current_system_id` field tells you where your ship is.

### 3.2 Check Nearby Systems

```http
GET /api/game/{game_id}/nearby
```

Returns all systems sorted by distance. Each entry includes:
- `distance_ly` — distance in light-years
- `fuel_cost` — fuel required for jump
- `reachable` — whether you have enough fuel AND jump range

**Decision rule:** Jump to `reachable` systems. Upgrade your hyperdrive to reach further ones.

### 3.3 Jump to a System

```http
POST /api/game/{game_id}/jump/{system_id}
```

Costs fuel based on distance (3 fuel per LY, minimum 1). Morale decays by 2 per jump (less with life support upgrades). A procedural event may trigger after jumping.

### 3.4 Scan a System

```http
POST /api/game/{game_id}/scan
```

Costs 5 fuel. Reveals all orbital bodies (planets, moons, asteroid belts) and their biomes. A system only needs to be scanned once.

### 3.5 View System Details

```http
GET /api/game/{game_id}/system/{system_id}
```

Returns all bodies with IDs, biomes, sizes, descriptions, and points of interest count.

### 3.6 Land on a Body

```http
POST /api/game/{game_id}/land/{body_id}
```

Select a body from the system detail. Planets yield more discoveries than asteroid belts or moons.

### 3.7 Explore the Surface

```http
POST /api/game/{game_id}/explore
```

Costs 2 fuel. Generates discoveries (minerals, artifacts, lifeforms, signals, ruins). Each discovery has:
- `category` — type of find
- `name` — what you found
- `value` — credit value if sold
- `description` — flavor text

The response also includes a `lore_fragments_discovered` field listing any lore fragments found during this exploration. Each entry includes:
- `fragment_id` — unique fragment identifier
- `arc` — story arc name (The Architects, The Void Signal, The Fracture, The Wanderer)
- `title` — fragment title
- `discovery_location` — where it was found (system name - body name)
- `discovery_timestamp` — ISO format datetime of discovery

### 3.8 Handle Events

After jumping, scanning, or exploring, you may receive a `pending_event`. Events have 2-4 choices.

```http
POST /api/game/{game_id}/event/{event_id}/resolve
Content-Type: application/json

{ "choice_index": 0 }
```

Choices have outcomes that modify stats: `fuel`, `hull`, `morale`, `credits`, `cargo`. Outcomes are formatted as semicolon-separated key:value pairs (e.g., `credits:50; fuel:-10`).

**Strategy tip:** Prefer choices that give credits early game. Avoid choices that damage hull or morale unless the reward is high.

#### Event Decision Framework

| Event Type | Recommended Choice | Reasoning |
|------------|-------------------|-----------|
| Life Support Failure | Emergency repair | Saves crew, costs fuel/hull but survivable |
| Mysterious Beacon | Decode first | Avoids traps, gives credits + morale |
| Pirate/Combat | Avoid if possible | Hull damage is expensive to repair |
| Trade Opportunity | Take it | Free credits and resources |
| Crew Morale Event | Boost morale | Low morale triggers cascading failures |
| Nebula Event (Ion Storm) | Power through | Minor hull damage but yields Ion Crystal discovery |
| Nebula Event (Protostar Formation) | Collect samples | Minor hull damage but yields valuable mineral samples |
| Nebula Event (Nebula Navigation Puzzle) | Follow the clearing current | Gains fuel by finding a shortcut |
| Pulsar Event (Radiation Pulse) | Dive behind asteroid/moon | Avoids hull damage at fuel cost |
| Pulsar Event (Pulsar Timing Signal) | Decode the signal pattern | Credits and potential lore fragment |
| Pulsar Event (Neutron Star Proximity) | Safe orbital scan | No hull damage, still yields data |
| Binary Star Event (Orbital Mechanics Challenge) | Calculate perfect trajectory | Fuel-efficient gravity assist + credits |
| Binary Star Event (Lagrange Point Discovery) | Investigate the satellite | Most valuable outcome (credits + data) |
| Black Hole Event | Depends on situation | Time Dilation: study for credits. Hawking Radiation: harvest for fuel. Spaghettification: gravity assist for fuel. Accretion Disk: probe for credits. Gravitational Lens: study for credits+morale. |

### 3.9 Distress Beacon

When your ship is in danger — out of fuel or critically damaged (hull below 20% of max) — you can activate the distress beacon to call for help.

```http
POST /api/game/{game_id}/distress
```

Costs 50 credits. Has a 60% chance of attracting a responder within 1-3 turns. If no responder comes, you can try again after the cooldown expires.

**Possible outcomes:**
| Outcome | Chance | Effect |
|---|---|---|
| Pilots Guild rescue | ~30% (stations only) | 20 fuel for 100 credits, +5 Free Pilots reputation |
| Friendly passerby | ~20% | +10-25 fuel, free |
| Pirates steal credits | ~12% | Lose 20-80 credits |
| Friendly emergency signal | ~20% | +5-15 fuel, free |
| Hostile emergency signal | ~20% | 5-15 hull damage |
| Passerby ignores | ~8% | Nothing happens |

The distress beacon has a cooldown period after each activation. Use it only when truly stranded.

### 3.10 Salvage & Emergency Crafting

When stranded with no fuel and landed on a body, you can salvage the area for resources.

#### Salvage

```http
POST /api/game/{game_id}/salvage
```

Only available when fuel is 0 and you're landed on a body. Each body can be salvaged up to 3 times. Morale cost increases with each attempt (1 + 2 per prior attempt on the same body).

| Roll | Find | Effect |
|---|---|---|
| 40% | Fuel cache | +2 to 8 fuel |
| 30% | Repair materials | +5 to 15 hull repair |
| 20% | Salvaged spare parts | +1 cargo (artifact, value 10-50 credits) |
| 10% | Nothing | No effect |

#### Emergency Crafting

Convert a discovery from your inventory into emergency resources:

```http
POST /api/game/{game_id}/salvage/craft
Content-Type: application/json

{ "discovery_id": "abc123...", "output": "fuel" }
```

| Discovery Category | Crafts Into | Rate |
|---|---|---|
| `artifact` | `fuel` | +5 fuel |
| `mineral` | `repair` | +10 hull |
| `lifeform` | `morale` | +15 morale |
| `signal` | `credits` | +50 credits |

`ruin` category discoveries cannot be crafted.

---

## 4. Resource Management

### 4.1 Ship Stats

| Stat | Start | Max | Meaning |
|------|-------|-----|---------|
| Fuel | 80 | 100 | Consumed for jumps, scans, exploration. 0 = stranded. |
| Hull | 100 | 100 | Ship integrity. 0 = game over. |
| Cargo | 0 | 50 | Inventory slots used. |
| Morale | 80 | 100 | Below 30 triggers negative crew events. |
| Credits | 1000 | ∞ | Universal currency. |
| Crew | 4 | 10 | Affects morale decay and some event outcomes. |
| Jump Range | 4 LY | ∞ | Max light-years per jump. Upgradable. |
| Scanner | 1 | 5 | Detection range. Upgradable. |

### 4.2 Critical Thresholds

- **Fuel < 10:** Cannot jump to most systems. Find a station to refuel.
- **Hull < 30:** High risk. Repair at a station.
- **Morale < 30:** Crew events trigger more frequently and are more dangerous.
- **Cargo > max_cargo:** Can't collect more. Sell or discard items.

---

## 5. Trading

Trade at space stations (systems with phenomenon `"none"`, `"nebula"`, or `"ancient_gate"`).

### Buy Fuel

```http
POST /api/game/{game_id}/trade
Content-Type: application/json

{ "action": "buy", "item": "fuel", "quantity": 10 }
```

### Repair Hull

```http
POST /api/game/{game_id}/trade
Content-Type: application/json

{ "action": "buy", "item": "repair", "quantity": 2 }
```

Each repair point restores 20 hull at ~40 credits per point.

### Sell Discoveries

```http
POST /api/game/{game_id}/trade
Content-Type: application/json

{ "action": "sell", "item": "artifact" }
```

Sells the first matching discovery from your inventory. Prices vary per system.

### Bulk Sell

Sell multiple discoveries at once in a single transaction:

```http
POST /api/game/{game_id}/trade/bulk-sell
Content-Type: application/json

{
  "items": [
    { "item": "artifact", "quantity": 3 },
    { "item": "Void Ore", "quantity": 2 }
  ]
}
```

Matches items by exact name first, then falls back to category match. Each `item` field accepts either a discovery name or a category (`"mineral"`, `"artifact"`, `"lifeform"`, `"signal"`, `"ruin"`). Items sorted by value (highest first) so your most valuable discoveries sell first.

**Partial failure mode:** If some items don't exist in your inventory, the available items still sell. Errors are reported alongside the success message.

Returns the full game state plus a `trade_result` field with `sold_count` and `total_price`.

---

## 6. Ship Upgrades

### View Available Upgrades

```http
GET /api/game/{game_id}/upgrades
```

### Purchase an Upgrade

```http
POST /api/game/{game_id}/upgrade
Content-Type: application/json

{ "upgrade_id": "hyperdrive" }
```

### Upgrade Reference

| ID | Effect | Base Cost | Max Level |
|----|--------|-----------|-----------|
| `hyperdrive` | +1 jump range | 500 | 5 |
| `scanner` | +1 scanner level | 400 | 5 |
| `cargo_hold` | +10 cargo capacity | 350 | 4 |
| `hull_plating` | +20 max hull | 450 | 3 |
| `fuel_tanks` | +20 max fuel | 300 | 3 |
| `life_support` | -1 morale decay per jump | 400 | 3 |

Cost scales: `base_cost * (current_level + 1)`.

**Recommended priority:** `hyperdrive` → `fuel_tanks` → `scanner` → `hull_plating` → `cargo_hold` → `life_support`

---

## 7. Viewing Progress

### Ship Log

```http
GET /api/game/{game_id}/log
```

All actions are logged with timestamps. Useful for understanding what happened.

### Discoveries

```http
GET /api/game/{game_id}/discoveries
```

Everything you've found, organized by category with credit values.

### Full Game State

```http
GET /api/game/{game_id}
```

Complete state dump: ship, current system, pending events, discoveries, log entries.

### Cargo Hold

```http
GET /api/game/{game_id}/cargo
```

Returns a detailed breakdown of your cargo hold: current item count, max capacity, and a list of every discovery with its ID, name, category, value, and sellability status. Lore-linked items are marked as not sellable.

### Lore Collection

```http
GET /api/game/{game_id}/lore
```

Returns all lore fragments organized by story arc. Each arc shows:
- `display_name` — arc name (e.g., "The Architects", "The Void Signal")
- `fragments` — list of fragments with `discovered` status
- `collected` / `total` — progress counts
- `hint` — for undiscovered fragments, a clue about where to look

Discovered fragments include `discovery_location` (system - body), `discovery_date`, and `discovery_timestamp`. The overall `progress` field tracks your collection completion.

Lore fragments are found during exploration when you land on the right body. Hints from the lore viewer guide you toward their locations.

### Faction Relations

#### View All Factions

```http
GET /api/game/{game_id}/factions
```

Returns all faction definitions and your current reputation with each.

#### View Single Faction

```http
GET /api/game/{game_id}/faction/{faction_id}
```

Returns detailed faction info plus your reputation and whether the faction is known.

#### Faction Missions

Factions offer tiered missions at trading stations. Higher reputation unlocks higher tiers with better rewards. Mission success is guaranteed — you pay costs upfront and always receive rewards.

##### Tier System

| Tier | Fuel Cost | Credit Cost | Credit Reward | Rep Reward | Rep Required |
|------|-----------|-------------|---------------|------------|-------------|
| 1 | 3 | 10 | 50–100 | 5–10 | 0 |
| 2 | 6 | 25 | 150–300 | 10–15 | 15 |
| 3 | 10 | 50 | 400–800 | 20–30 | 30 |

**Mission types by tier:** Tier 1 (courier, survey), Tier 2 (exploration, salvage, patrol), Tier 3 (special_ops, diplomatic).

##### Daily Missions

Each trading station offers one free "Daily Opportunity" mission per day cycle (~10 log entries per cycle): 0 fuel/credit cost, 25–75 credits reward, 5–10 reputation.

##### Mission Flow

1. **List available missions** at the current trading station:
```http
GET /api/game/{game_id}/missions
```
Returns available standard missions, the daily mission (if available), and the dominant faction.

2. **Accept a mission** (costs are deducted immediately):
```http
POST /api/game/{game_id}/missions/{mission_id}/accept
Content-Type: application/json

{ "mission_id": "mission_sys_0000_12345" }
```
Optional: add `"faction_id"` to scope lookup to a specific faction.

3. **Complete a mission** (rewards are applied):
```http
POST /api/game/{game_id}/missions/{mission_id}/complete
Content-Type: application/json

{ "mission_id": "mission_sys_0000_12345" }
```

Missions cannot be accepted twice and must be accepted before completing. Completed missions are tracked and cannot be repeated.

##### Legacy One-Shot Endpoint

```http
POST /api/game/{game_id}/faction/{faction_id}/mission
```

Randomly picks a mission from the available pool, deducts costs, and immediately awards rewards in a single call. Requires being at a trading station.

| Faction | Alignment | Bonus |
|---|---|---|
| Stellar Cartographers Union | Explorer | +10 credits, +1 morale on exploration/discovery events at rep ≥20 |
| Void Traders Syndicate | Corporate | Discounted fuel/repairs at high rep; +10 credits on trade events at rep ≥20 |
| Free Pilots Guild | Explorer | +5 morale on encounter/crisis/crew/hazard events at rep ≥20 |

### Leaderboard

```http
GET /api/leaderboard
```

Top players ranked by discoveries and systems visited.

---

## 8. Strategy Guide

### 8.1 Early Game (Credits < 2000)
- Explore every body in your starting system — it's free aside from scan/explore fuel
- Sell all discoveries to build credits
- Prioritize `hyperdrive` upgrade to reach more systems
- Only jump to systems with `reachable: true`

### 8.2 Mid Game (Credits 2000-5000)
- Upgrade `fuel_tanks` to extend range
- Visit trade-capable systems to refuel and sell
- Take risks on event choices that offer credit rewards
- Track morale — buy `life_support` if it dips below 40

### 8.3 Late Game
- Upgrade `scanner` to detect phenomena before jumping
- Max out `hyperdrive` to access the entire galaxy
- Explore high-body-count systems first (more discoveries per fuel)
- Aim for the leaderboard by maximizing discoveries and systems visited

### 8.4 Risk Management
- **Always keep fuel above 15** — enough to jump to at least one known system
- **Repair hull before it drops below 40** — events can deal sudden damage
- **Keep morale above 40** — low morale events can cascade
- **Don't jump blindly** — scan systems first to find valuable bodies

### 8.5 Optimal Discovery Strategy
- Target planets with high `poi_count` and `body_type: "planet"` (more discoveries per explore)
- Systems with phenomena (`nebula`, `pulsar`, `binary_star`, `ancient_gate`) may trigger unique events
- Jungle and ocean biomes tend to yield more lifeform discoveries (higher value)
- Crystal and volcanic biomes yield rarer minerals

---

## 9. Saving

```http
POST /api/game/{game_id}/save
```

The game persists all state to SQLite. Save frequently — especially before risky jumps.

---

## 10. API Reference (Quick)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server health check |
| POST | `/api/game/new` | Create new game |
| GET | `/api/game/{id}` | Full game state |
| GET | `/api/game/{id}/galaxy` | Galaxy map data |
| GET | `/api/game/{id}/system/{sid}` | System details |
| POST | `/api/game/{id}/jump/{sid}` | Jump to system |
| POST | `/api/game/{id}/scan` | Scan current system |
| POST | `/api/game/{id}/land/{bid}` | Land on body |
| POST | `/api/game/{id}/explore` | Explore surface |
| POST | `/api/game/{id}/event/{eid}/resolve` | Resolve event |
| POST | `/api/game/{id}/distress` | Activate distress beacon |
| POST | `/api/game/{id}/salvage` | Salvage area for resources |
| POST | `/api/game/{id}/salvage/craft` | Craft discovery into resources |
| GET | `/api/game/{id}/log` | Ship log |
| GET | `/api/game/{id}/discoveries` | Discovery list |
| GET | `/api/game/{id}/cargo` | Cargo hold details |
| GET | `/api/game/{id}/lore` | Lore fragment collection |
| POST | `/api/game/{id}/trade` | Buy/sell at station |
| POST | `/api/game/{id}/trade/bulk-sell` | Sell multiple discoveries |
| GET | `/api/game/{id}/upgrades` | Upgrade options |
| POST | `/api/game/{id}/upgrade` | Purchase upgrade |
| GET | `/api/game/{id}/nearby` | Nearby systems |
| GET | `/api/game/{id}/factions` | List all factions |
| GET | `/api/game/{id}/faction/{fid}` | Single faction detail |
| POST | `/api/game/{id}/faction/{fid}/mission` | Run one-shot faction mission (tiered) |
| GET | `/api/game/{id}/missions` | List available missions at station |
| POST | `/api/game/{id}/missions/{mid}/accept` | Accept a mission (deducts costs) |
| POST | `/api/game/{id}/missions/{mid}/complete` | Complete accepted mission (claims rewards) |
| POST | `/api/game/{id}/save` | Save game |
| POST | `/api/game/{id}/load` | Load game |
| GET | `/api/leaderboard` | Top players |

Full OpenAPI docs at `/docs` and `/redoc`.

Events may be phenomenon-specific, triggering only in systems with matching phenomena (e.g., black hole events only appear near black holes).

#### Event Cooldowns

Events now have per-event cooldowns to prevent the same event from firing repeatedly in a single session. Cooldown values range from 3 to 10 turns depending on event rarity and type. After an event fires, it goes on cooldown and will not trigger again until the cooldown expires. Cooldowns decrement by 1 each time you jump, scan, or explore. If all eligible events are on cooldown, the system uses a fallback: the event with the lowest remaining cooldown may fire, with preference given to events other than the one that last fired (`last_event_title` deduplication). This ensures event variety while still allowing events to occur when the pool is constrained.

### Reputation Bonuses
When your faction reputation reaches **20 or higher**, resolving events of that faction's type grants bonus rewards:
- **Stellar Cartographers** (exploration & discovery events): +10 credits and +1 morale per event
- **Void Traders** (trade events): +10 credits per event
- **Free Pilots** (encounter, crisis, crew & hazard events): +5 morale per event

These bonuses stack with the event's normal outcome rewards.

### Lore Fragment Hints
The `/api/game/{id}/lore` endpoint returns both discovered fragments (with `discovery_location`, `discovery_date`, and `discovery_timestamp`) and undiscovered fragments (with `hint` text). Explore systems matching the hint descriptions to complete each story arc.

#### Lore Notification System
- **Discovery Toast:** When a new lore fragment is found, a toast appears with the fragment's arc and title, plus a "View" button.
- **Lore Button Pulse:** The Lore navigation button (`data-lore-nav="true"`) pulses when there are unread lore fragments. The glow clears once the lore viewer has been opened.
- **Fallback Safety:** If `lore.js` fails to load, notification stubs in `main.js` degrade gracefully.

---

## 11. Browser Automation Tips

For AI agents using browser tools:

1. **Read game state:** `document.getElementById('game-state').textContent` — full JSON
2. **Find actions:** `document.querySelectorAll('[data-action]')` — all interactive elements
3. **Click actions:** Elements have `data-action` values like `"jump-to"`, `"scan"`, `"land"`, `"explore"`, `"resolve-event"`
4. **Click with params:** Some elements carry extra data like `data-system-id`, `data-body-id`, `data-event-id`, `data-choice-idx`
5. **Screen navigation:** Click `data-action="show-galaxy"` for map, `data-action="show-log"` for log
6. **Canvas interaction:** The galaxy map is a Canvas element. Click on stars to select them, then use the "Jump" button. Pan by dragging, zoom with scroll wheel.

---

*End of Guide. Good luck in the void, pilot.*
