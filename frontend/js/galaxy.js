let galaxySystems = [];
let selectedSystemId = null;
let galaxyCameraX = 0;
let galaxyCameraY = 0;
let galaxyZoom = 1;

function renderGalaxy(systems, currentId, canvasId = 'galaxy-canvas') {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  galaxySystems = systems;
  const ctx = canvas.getContext('2d');
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width;
  canvas.height = rect.height;

  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  const padding = 60;
  const scaleX = (w - padding * 2) / 1200;
  const scaleY = (h - padding * 2) / 800;
  const scale = Math.min(scaleX, scaleY) * galaxyZoom;
  const offsetX = (w - 1200 * scale) / 2 + galaxyCameraX;
  const offsetY = (h - 800 * scale) / 2 + galaxyCameraY;

  ctx.save();
  ctx.translate(offsetX, offsetY);
  ctx.scale(scale, scale);

  for (const sys of systems) {
    const x = sys.x;
    const y = sys.y;
    const isCurrent = sys.id === currentId;
    const isSelected = sys.id === selectedSystemId;

    let radius = 2;
    if (sys.visited) radius = 3;
    if (isCurrent) radius = 5;
    if (isSelected) radius = 6;

    const color = starColor(sys.star_type);

    ctx.beginPath();
    ctx.arc(x, y, radius * 2, 0, Math.PI * 2);
    const glow = ctx.createRadialGradient(x, y, 0, x, y, radius * 4);
    glow.addColorStop(0, color);
    glow.addColorStop(0.3, color + '66');
    glow.addColorStop(1, 'transparent');
    ctx.fillStyle = glow;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fillStyle = sys.visited ? color : 'rgba(255,255,255,0.3)';
    if (isCurrent) {
      ctx.fillStyle = '#ffd700';
      ctx.shadowColor = '#ffd700';
      ctx.shadowBlur = 12;
    }
    ctx.fill();
    ctx.shadowBlur = 0;

    if (isSelected || isCurrent) {
      ctx.beginPath();
      ctx.arc(x, y, radius + 4, 0, Math.PI * 2);
      ctx.strokeStyle = isCurrent ? '#ffd700' : '#00ffcc';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    if (sys.visited && !isCurrent && galaxyZoom > 0.6) {
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.font = '8px monospace';
      ctx.fillText(sys.name, x + 8, y + 3);
    }
  }

  ctx.restore();
}

function setupGalaxyEvents(canvasId = 'galaxy-canvas') {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  let dragging = false;
  let dragStartX, dragStartY, camStartX, camStartY;

  canvas.onmousedown = (e) => {
    dragging = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    camStartX = galaxyCameraX;
    camStartY = galaxyCameraY;
  };

  canvas.onmousemove = (e) => {
    if (!dragging) return;
    galaxyCameraX = camStartX + (e.clientX - dragStartX);
    galaxyCameraY = camStartY + (e.clientY - dragStartY);
    renderGalaxy(galaxySystems, window._currentSystemId, canvasId);
  };

  canvas.onmouseup = (e) => {
    if (!dragging) { return; }
    dragging = false;
    const dx = e.clientX - dragStartX;
    const dy = e.clientY - dragStartY;
    if (Math.abs(dx) < 5 && Math.abs(dy) < 5) {
      handleGalaxyClick(e, canvasId);
    }
  };

  canvas.onwheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    galaxyZoom = Math.max(0.3, Math.min(3, galaxyZoom + delta));
    renderGalaxy(galaxySystems, window._currentSystemId, canvasId);
  };
}

function handleGalaxyClick(e, canvasId) {
  const canvas = document.getElementById(canvasId);
  const rect = canvas.getBoundingClientRect();
  const w = canvas.width;
  const h = canvas.height;
  const padding = 60;
  const scaleX = (w - padding * 2) / 1200;
  const scaleY = (h - padding * 2) / 800;
  const scale = Math.min(scaleX, scaleY) * galaxyZoom;
  const offsetX = (w - 1200 * scale) / 2 + galaxyCameraX;
  const offsetY = (h - 800 * scale) / 2 + galaxyCameraY;

  const mx = (e.clientX - rect.left - offsetX) / scale;
  const my = (e.clientY - rect.top - offsetY) / scale;

  let closest = null;
  let minDist = 30 / scale;
  for (const sys of galaxySystems) {
    const d = Math.hypot(sys.x - mx, sys.y - my);
    if (d < minDist) { minDist = d; closest = sys; }
  }

  if (closest) {
    selectedSystemId = closest.id;
    renderGalaxy(galaxySystems, window._currentSystemId, canvasId);
    showSystemInfo(closest);
  }
}

function showSystemInfo(sys) {
  const panel = $('#galaxy-system-info');
  if (!panel) return;
  panel.innerHTML = `
    <div class="name" style="color:${starColor(sys.star_type)}">${escapeHtml(sys.name)}</div>
    <div>Type: ${sys.star_type} | ${sys.phenomenon !== 'none' ? sys.phenomenon : 'Standard'}</div>
    <div>Bodies: ${sys.body_count} | Visited: ${sys.visited ? 'Yes' : 'No'}</div>
    <div style="margin-top:0.5rem;">
      ${sys.id !== window._currentSystemId ? `<button data-action="jump-to" data-system-id="${sys.id}" class="ui-button" style="font-size:0.8rem;">Jump to ${escapeHtml(sys.name)}</button>` : '<span style="color:var(--color-star)">Current location</span>'}
    </div>
  `;
}
