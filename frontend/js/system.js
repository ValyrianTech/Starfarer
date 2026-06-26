function renderSystemView(systemData, gameId) {
  const container = $('#system-content');
  if (!container) return;

  const sys = systemData.system;
  const nearby = systemData.nearby_systems || [];

  let bodiesHTML = '';
  if (sys.bodies && sys.bodies.length > 0) {
    bodiesHTML = '<div class="bodies-grid">';
    for (const body of sys.bodies) {
      bodiesHTML += `
        <div class="body-card" data-action="land" data-body-id="${body.id}">
          <div class="body-name">${escapeHtml(body.name)}</div>
          <div class="body-meta">${body.body_type} | Size ${body.size}</div>
          <div class="body-biome ${body.biome}">${escapeHtml(body.biome).replace('_', ' ')}</div>
          <div class="body-desc">${escapeHtml(body.description)}</div>
        </div>`;
    }
    bodiesHTML += '</div>';
  }

  let nearbyHTML = '';
  if (nearby.length > 0) {
    nearbyHTML = '<div class="system-nearby"><h3>Nearby Systems</h3><div class="nearby-list">';
    for (const n of nearby) {
      const reachable = n.reachable ? '' : 'style="opacity:0.4"';
      nearbyHTML += `<div class="nearby-item" data-action="jump-to" data-system-id="${n.id}" ${reachable}>
        ${escapeHtml(n.name)} <span class="dist">${n.distance_ly} LY</span>
      </div>`;
    }
    nearbyHTML += '</div></div>';
  }

  container.innerHTML = `
    <div class="system-header fade-in">
      <div class="name">${escapeHtml(sys.name)}</div>
      <div class="type">${sys.star_type}-type Star | ${sys.bodies.length} orbital bodies</div>
    </div>
    ${sys.phenomenon !== 'none' ? `<div class="system-phenomenon">${sys.phenomenon_desc || sys.phenomenon}</div>` : ''}
    ${bodiesHTML}
    <div class="system-actions">
      <button data-action="scan" class="ui-button">Scan System</button>
    </div>
    ${nearbyHTML}
  `;

  window._currentSystemId = sys.id;
}

function renderSurfaceView(bodyData, discoveries, gameId) {
  const container = $('#surface-content');
  if (!container) return;

  let discHTML = '';
  if (discoveries && discoveries.length > 0) {
    discHTML = '<div class="discovery-list">';
    for (const d of discoveries) {
      discHTML += `
        <div class="discovery-item fade-in">
          <div class="disc-category">${d.category}</div>
          <div class="disc-name">${d.name}</div>
          <div class="disc-desc">${d.description}</div>
          <div class="disc-value">Value: ${d.value} credits</div>
        </div>`;
    }
    discHTML += '</div>';
  }

  container.innerHTML = `
    <div class="surface-explore fade-in">
      <div class="surface-body-header">
        <div class="name">Surface: ${escapeHtml(bodyData.name || 'Unknown')}</div>
        <div>Biome: ${escapeHtml(bodyData.biome || '').replace('_', ' ')}</div>
      </div>
      <div style="text-align:center;margin-bottom:1rem;">
        <button data-action="explore" class="ui-button">Explore Surface</button>
        <button data-action="return-system" class="ui-button" style="margin-left:0.5rem;">Return to System</button>
      </div>
      ${discHTML}
    </div>
  `;
}
