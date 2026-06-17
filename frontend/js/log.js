function showGameLog(logEntries) {
  const container = $('#log-content');
  if (!container) return;

  let html = '';
  if (logEntries && logEntries.length > 0) {
    for (const entry of logEntries) {
      const typeClass = entry.type || 'system';
      const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '';
      html += `
        <div class="log-entry" style="padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.05);">
          <span style="color:var(--color-text-dim);font-size:0.7rem;">[${time}]</span>
          <span style="color:var(--color-cyan);font-size:0.75rem;text-transform:uppercase;margin-left:0.5rem;">${typeClass}</span>
          <span style="margin-left:0.5rem;font-size:0.85rem;">${entry.message}</span>
        </div>`;
    }
  } else {
    html = '<div style="color:var(--color-text-dim);padding:1rem;">No log entries yet.</div>';
  }

  container.innerHTML = html;
}

async function loadLog(gameId) {
  try {
    const data = await API.log(gameId);
    showGameLog(data.entries);
  } catch (e) {
    console.error('Load log error:', e);
  }
}
