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
        <button data-action="save-game" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Save</button>
      </div>
    </div>
  `;
}

function updateShipStatus(ship) {
  renderShipStatus(ship);
}
