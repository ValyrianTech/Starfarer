function renderShipStatus(ship) {
  const panel = $('#ship-panel');
  if (!panel) return;

  const fuelPct = (ship.fuel / ship.max_fuel) * 100;
  const hullPct = (ship.hull / ship.max_hull) * 100;
  const moralePct = ship.morale;
  const cargoPct = (ship.cargo / ship.max_cargo) * 100;

  panel.innerHTML = `
    <div class="ui-panel" style="position:fixed;bottom:1rem;left:1rem;z-index:20;min-width:280px;" id="ship-status-panel">
      <div class="ui-panel-title">${ship.name} — Ship Status</div>
      <div class="stat-bar">
        <span class="stat-bar-label">Fuel</span>
        <div class="stat-bar-track"><div class="stat-bar-fill fuel" style="width:${fuelPct}%"></div></div>
        <span class="stat-value">${ship.fuel}/${ship.max_fuel}</span>
      </div>
      <div class="stat-bar">
        <span class="stat-bar-label">Hull</span>
        <div class="stat-bar-track"><div class="stat-bar-fill hull" style="width:${hullPct}%"></div></div>
        <span class="stat-value">${ship.hull}/${ship.max_hull}</span>
      </div>
      <div class="stat-bar">
        <span class="stat-bar-label">Morale</span>
        <div class="stat-bar-track"><div class="stat-bar-fill morale" style="width:${moralePct}%"></div></div>
        <span class="stat-value">${ship.morale}</span>
      </div>
      <div class="stat-bar">
        <span class="stat-bar-label">Cargo</span>
        <div class="stat-bar-track"><div class="stat-bar-fill cargo" style="width:${cargoPct}%"></div></div>
        <span class="stat-value">${ship.cargo}/${ship.max_cargo}</span>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:0.5rem;font-size:0.75rem;color:var(--color-text-dim);">
        <span>Crew: ${ship.crew}</span>
        <span>Credits: ${formatNumber(ship.credits)}</span>
        <span>Jump: ${ship.jump_range} LY</span>
      </div>
      <div style="display:flex;gap:0.4rem;margin-top:0.5rem;">
        <button data-action="show-galaxy" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Galaxy</button>
        <button data-action="show-log" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Log</button>
        <button data-action="show-lore" data-lore-nav="true" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Lore</button>
        <button data-action="save-game" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Save</button>
      </div>
    </div>
  `;
}

function updateShipStatus(ship) {
  renderShipStatus(ship);
  renderCargoPanel();
}

async function renderCargoPanel() {
  const gameId = GAME_ID;
  if (!gameId) return;

  if (!$('#cargo-panel')) {
    const container = document.createElement('div');
    container.innerHTML = `
      <div class="ui-panel" style="position:fixed;right:1rem;top:1rem;z-index:20;min-width:280px;" id="cargo-panel">
        <div class="ui-panel-title">Cargo Hold</div>
        <div style="margin-bottom:0.5rem;">
          <select id="cargo-sort-select" class="cargo-sort-select">
            <option value="value_desc">Value (High to Low)</option>
            <option value="value_asc">Value (Low to High)</option>
            <option value="name_asc">Name (A-Z)</option>
            <option value="name_desc">Name (Z-A)</option>
          </select>
          <div id="cargo-total-value" class="cargo-total-value">Total Value: —</div>
        </div>
        <div id="cargo-items-list"></div>
      </div>
    `;
    document.body.appendChild(container.firstElementChild);
    document.getElementById('cargo-sort-select').addEventListener('change', () => {
      renderCargoPanel();
    });
  }

  const select = document.getElementById('cargo-sort-select');
  const val = select ? select.value : 'value_desc';
  const [sortKey, order] = val.split('_');

  try {
    const data = await API.cargo(gameId, sortKey, order);

    const totalEl = document.getElementById('cargo-total-value');
    if (totalEl) totalEl.textContent = `Total Value: ${formatNumber(data.total_value || 0)} cr`;

    const top3Ids = new Set(
      [...data.cargo_items]
        .sort((a, b) => (b.value || 0) - (a.value || 0))
        .slice(0, 3)
        .map(i => i.id)
    );

    const listEl = document.getElementById('cargo-items-list');
    if (listEl) {
      if (data.cargo_items.length === 0) {
        listEl.innerHTML = '<div class="cargo-empty">Cargo hold is empty.</div>';
      } else {
        listEl.innerHTML = data.cargo_items.map(item => {
          const isTop3 = top3Ids.has(item.id);
          return `
            <div class="cargo-item${isTop3 ? ' cargo-item-top' : ''}">
              <div class="cargo-item-name">${isTop3 ? '<span class="cargo-star">\u2605</span>' : ''}${item.name}</div>
              <div class="cargo-item-meta">
                <span class="cargo-item-category">${item.category}</span>
                <span class="cargo-item-value">${formatNumber(item.value)} cr</span>
              </div>
            </div>
          `;
        }).join('');
      }
    }
  } catch (e) {
    console.error('Cargo panel error:', e);
  }
}
