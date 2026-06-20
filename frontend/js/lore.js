function renderLoreView(arcsData, progress, arcOrder) {
  const container = $('#lore-content');
  if (!container) return;

  let html = `
    <div class="lore-header fade-in">
      <h2>Lore Archives</h2>
      <p class="lore-progress">Fragments collected: ${progress.collected} / ${progress.total}</p>
    </div>
  `;

  for (const arcId of arcOrder) {
    const arc = arcsData[arcId];
    if (!arc) continue;

    html += `
      <div class="lore-arc fade-in">
        <div class="arc-header">
          <span class="arc-title">${arc.display_name}</span>
          <span class="arc-progress">${arc.collected}/${arc.total}</span>
        </div>
        <div class="arc-fragments">
    `;

    const sorted = (arc.fragments || []).slice().sort((a, b) => {
      const na = parseInt(a.id.split('_').pop()) || 0;
      const nb = parseInt(b.id.split('_').pop()) || 0;
      return na - nb;
    });

    for (const frag of sorted) {
      const discovered = frag.discovered;
      html += `
        <div class="lore-fragment ${discovered ? '' : 'locked'}">
          <div class="fragment-header">
            <span class="fragment-number">#${frag.id.split('_').pop()}</span>
            <span class="fragment-title">${discovered ? frag.title : 'Unknown Fragment'}</span>
            <span class="fragment-status">${discovered ? 'DISCOVERED' : 'LOCKED'}</span>
          </div>
          ${discovered ? `<div class="fragment-text">${frag.text}</div>` : '<div class="fragment-text">This fragment has not yet been discovered.</div>'}
        </div>`;
    }

    html += `
        </div>
      </div>
    `;
  }

  container.innerHTML = html;
}

async function loadLore(gameId) {
  try {
    const data = await API.lore(gameId);
    renderLoreView(data.arcs, data.progress, data.arc_order);
  } catch (e) {
    console.error('Load lore error:', e);
  }
}
