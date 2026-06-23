let _unreadLoreCount = 0;

function escapeHtml(str) {
  if (typeof str !== 'string') return str;
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

function renderLoreView(arcsData, progress, arcOrder) {
  const container = $('#lore-content');
  if (!container) return;

  const order = arcOrder || Object.keys(arcsData);
  let html = '<div id="lore-viewer" data-component="lore-viewer">';

  html += `
    <div class="lore-header fade-in">
      <h2>Lore Archives</h2>
      <p class="lore-progress">Fragments collected: ${progress.collected} / ${progress.total}</p>
      <div class="lore-overall-progress-bar">
        <div class="lore-overall-progress-fill" style="width:${progress.total > 0 ? (progress.collected / progress.total * 100) : 0}%"></div>
      </div>
    </div>
  `;

  html += '<nav class="lore-arc-tabs" data-component="lore-arc-tabs">';
  for (const arcId of order) {
    const arc = arcsData[arcId];
    if (!arc) continue;
    html += `<button class="lore-arc-tab" data-arc-id="${arcId}" data-fragments-collected="${arc.collected}" data-fragments-total="${arc.total}" data-action="select-lore-arc">${escapeHtml(arc.display_name)} <span class="tab-count">${arc.collected}/${arc.total}</span></button>`;
  }
  html += '</nav>';

  html += '<div class="lore-fragment-list" data-component="lore-fragment-list">';
  for (const arcId of order) {
    const arc = arcsData[arcId];
    if (!arc) continue;

    html += `<div class="lore-arc-panel" data-arc-panel="${arcId}">`;

    html += `
      <div class="arc-progress-bar-container">
        <div class="arc-progress-bar">
          <div class="arc-progress-fill" style="width:${arc.total > 0 ? (arc.collected / arc.total * 100) : 0}%"></div>
        </div>
        <span class="arc-progress-label">${arc.collected}/${arc.total} fragments collected</span>
      </div>
    `;

    const sorted = (arc.fragments || []).slice().sort((a, b) => {
      const na = a.fragment_number || 0;
      const nb = b.fragment_number || 0;
      return na - nb;
    });

    for (const frag of sorted) {
      const discovered = frag.discovered;
      html += `
        <article class="lore-fragment-card ${discovered ? 'discovered' : 'locked'}" data-fragment-id="${frag.id}" data-arc="${arcId}" data-collected="${discovered}">
          <div class="fragment-card-header">
            <span class="fragment-card-number">${escapeHtml(arc.display_name)} #${frag.fragment_number}/${arc.total}</span>
            <span class="fragment-card-status">${discovered ? 'DISCOVERED' : 'LOCKED'}</span>
          </div>
          <h3 class="fragment-card-title">${discovered ? escapeHtml(frag.title) : '???'}</h3>
          ${discovered ? `
            <div class="fragment-card-text">${escapeHtml(frag.text)}</div>
            <div class="fragment-card-meta">
              ${frag.discovery_location ? `<span class="fragment-location" title="Discovery location">${escapeHtml(frag.discovery_location)}</span>` : ''}
              ${frag.discovery_date ? `<span class="fragment-date" title="Discovery date">${escapeHtml(formatDiscoveryDate(frag.discovery_date))}</span>` : ''}
            </div>
          ` : `
            <div class="fragment-card-text locked-text">
              ${frag.hint ? `<p class="fragment-hint">Hint: ${escapeHtml(frag.hint)}</p>` : '<p class="fragment-hint">This fragment has not yet been discovered. Keep exploring.</p>'}
            </div>
          `}
        </article>
      `;
    }

    html += '</div>';
  }
  html += '</div>';

  html += '</div>';
  container.innerHTML = html;

  if (order.length > 0) {
    selectLoreArcTab(order[0]);
  }

  _unreadLoreCount = 0;
  updateLoreButtonGlow();
}

function selectLoreArcTab(arcId) {
  document.querySelectorAll('.lore-arc-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.arcId === arcId);
  });
  document.querySelectorAll('.lore-arc-panel').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.arcPanel === arcId);
  });
}

function formatDiscoveryDate(timestamp) {
  if (!timestamp) return '';
  try {
    const d = new Date(timestamp);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch (e) {
    return timestamp;
  }
}

function notifyLoreFragment(fragmentTitle) {
  _unreadLoreCount++;
  updateLoreButtonGlow();
  showLoreNotification(fragmentTitle);
}

function showLoreNotification(title) {
  const existing = $('#lore-notification');
  if (existing) existing.remove();

  const notif = h('div', {
    id: 'lore-notification',
    className: 'lore-notification fade-in'
  },
    h('div', { className: 'lore-notification-content' },
      h('span', { className: 'lore-notification-icon' }, '\uD83D\uDCDC'),
      h('span', {}, `Lore Fragment Discovered: ${escapeHtml(title)}`),
      h('button', {
        className: 'lore-notification-action ui-button',
        data: { action: 'show-lore' }
      }, 'View')
    )
  );

  document.body.appendChild(notif);

  setTimeout(() => {
    if (notif.parentNode) notif.remove();
  }, 8000);
}

function updateLoreButtonGlow() {
  const loreBtn = document.querySelector('[data-action="show-lore"][data-lore-nav]');
  if (!loreBtn) return;
  if (_unreadLoreCount > 0) {
    loreBtn.classList.add('lore-pulse');
  } else {
    loreBtn.classList.remove('lore-pulse');
  }
}

async function loadLore(gameId) {
  try {
    const data = await API.lore(gameId);
    renderLoreView(data.arcs, data.progress, data.arc_order);
  } catch (e) {
    console.error('Load lore error:', e);
  }
}
