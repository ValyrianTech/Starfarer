// DOM-based HUD: vitals bars, log feed, event card, faction badges.

const MAX_LOG_ENTRIES = 120;

const $ = (id) => document.getElementById(id);

export class Hud {
  constructor() {
    this.logFeed = $("log-feed");
    this.seenLogIds = new Set();
  }

  show() {
    $("hud").classList.remove("hidden");
  }

  setConnection(status) {
    const el = $("conn-status");
    el.classList.remove("connected", "connecting", "lost");
    if (status === "connected" || status === "reconnected") {
      el.classList.add("connected");
      el.textContent = "LIVE";
    } else if (status === "lost") {
      el.classList.add("lost");
      el.textContent = "SIGNAL LOST";
    } else {
      el.classList.add("connecting");
      el.textContent = "CONNECTING";
    }
  }

  update(payload) {
    const summary = payload.summary;
    this._updateShip(summary);
    this._updateExpedition(summary);
    this._updateFactions(summary);
    this._updateEventCard(payload.pending_events);
    this._appendLogEntries(payload.new_log_entries);
  }

  _updateShip(summary) {
    const ship = summary.ship;
    $("ship-name").textContent = ship.name.toUpperCase();
    const sys = summary.current_system;
    $("ship-location").textContent = sys ? sys.name : "Deep space";

    this._setBar("fuel", ship.fuel, ship.max_fuel);
    this._setBar("hull", ship.hull, ship.max_hull);
    this._setBar("morale", ship.morale, 100);
    this._setBar("cargo", ship.cargo, ship.max_cargo);
    $("val-credits").textContent = ship.credits.toLocaleString();
    $("val-crew").textContent = `${ship.crew}/${ship.max_crew}`;
  }

  _setBar(name, value, max) {
    const pct = max > 0 ? (value / max) * 100 : 0;
    const bar = $(`bar-${name}`);
    bar.style.width = `${pct}%`;
    bar.classList.toggle("low", pct <= 20);
    $(`val-${name}`).textContent = `${value}/${max}`;
  }

  _updateExpedition(summary) {
    $("val-systems").textContent = summary.systems_visited;
    $("val-discoveries").textContent = summary.discovery_count;
    $("val-lore").textContent =
      `${summary.lore_fragments_collected}/${summary.lore_fragments_total}`;
    $("val-biomes").textContent = summary.biomes_visited_count;
  }

  _updateFactions(summary) {
    const container = $("faction-list");
    container.innerHTML = "";
    const reps = summary.reputation_summary || {};
    for (const [factionId, info] of Object.entries(reps)) {
      const row = document.createElement("div");
      row.className = "faction-row";
      const name = document.createElement("span");
      name.className = "faction-name";
      name.textContent = factionId
        .split("_")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
      const badge = document.createElement("span");
      badge.className = `rep-badge ${info.label.toLowerCase()}`;
      badge.textContent = `${info.label} ${info.reputation >= 0 ? "+" : ""}${info.reputation}`;
      row.append(name, badge);
      container.appendChild(row);
    }
  }

  _updateEventCard(pendingEvents) {
    const card = $("event-card");
    if (!pendingEvents || pendingEvents.length === 0) {
      card.classList.add("hidden");
      return;
    }
    const evt = pendingEvents[0];
    $("event-title").textContent = evt.title;
    $("event-flavor").textContent = evt.flavor;
    const choicesEl = $("event-choices");
    choicesEl.innerHTML = "";
    evt.choices.forEach((choice, i) => {
      const div = document.createElement("div");
      div.className = "event-choice";
      const idx = document.createElement("span");
      idx.className = "choice-index";
      idx.textContent = `${i + 1}.`;
      div.append(idx, document.createTextNode(choice.text));
      choicesEl.appendChild(div);
    });
    card.classList.remove("hidden");
  }

  _appendLogEntries(entries) {
    if (!entries || entries.length === 0) return;
    const atBottom =
      this.logFeed.scrollHeight - this.logFeed.scrollTop - this.logFeed.clientHeight < 40;

    for (const entry of entries) {
      if (this.seenLogIds.has(entry.id)) continue;
      this.seenLogIds.add(entry.id);
      this.logFeed.appendChild(this._renderLogEntry(entry));
    }

    // Trim old entries.
    while (this.logFeed.children.length > MAX_LOG_ENTRIES) {
      this.logFeed.removeChild(this.logFeed.firstChild);
    }

    if (atBottom) {
      this.logFeed.scrollTop = this.logFeed.scrollHeight;
    }
  }

  _renderLogEntry(entry) {
    const row = document.createElement("div");
    const type = entry.type || "system";
    row.className = `log-entry t-${type}`;

    const tag = document.createElement("span");
    tag.className = "log-tag";
    tag.textContent = (entry.category || type).replace(/_/g, " ");

    const msg = document.createElement("span");
    msg.className = "log-msg";
    msg.textContent = entry.message;

    const deltas = this._renderDeltas(entry);
    if (deltas) msg.appendChild(deltas);

    row.append(tag, msg);
    return row;
  }

  _renderDeltas(entry) {
    const parts = [];
    const fields = [
      ["credits_change", "cr"],
      ["fuel_change", "fuel"],
      ["hull_change", "hull"],
      ["morale_change", "morale"],
      ["cargo_change", "cargo"],
    ];
    for (const [key, label] of fields) {
      const v = entry[key];
      if (typeof v === "number" && v !== 0) {
        parts.push({ v, label });
      }
    }
    if (parts.length === 0) return null;
    const span = document.createElement("span");
    span.className = "log-deltas";
    for (const { v, label } of parts) {
      const d = document.createElement("span");
      d.className = v > 0 ? "delta-pos" : "delta-neg";
      d.textContent = ` ${v > 0 ? "+" : ""}${v} ${label}`;
      span.appendChild(d);
    }
    return span;
  }
}
