window._dismissedRipples = window._dismissedRipples || new Set();

function renderGhostsTab(ghosts, totalGhosts) {
  const countEl = $('#system-ghosts-count');
  const listEl = $('#system-ghosts-list');
  if (!listEl) return;

  if (countEl) {
    const count = totalGhosts !== undefined ? totalGhosts : ghosts.length;
    countEl.textContent = count + ' ' + (count === 1 ? 'visitor' : 'visitors');
  }

  if (ghosts.length === 0) {
    listEl.innerHTML = '<div class="ghost-entry"><em>No past travellers detected in this system.</em></div>';
    return;
  }

  let html = '';
  for (const g of ghosts) {
    html += `
      <div class="ghost-entry">
        <div class="ghost-player">${escapeHtml(g.player_name)}</div>
        <div class="ghost-time">${new Date(g.timestamp).toLocaleString()}</div>
        ${g.message ? `<div class="ghost-message">"${escapeHtml(g.message)}"</div>` : ''}
        ${g.discoveries && g.discoveries.length > 0 ? `<div class="ghost-discoveries">Discovered: ${g.discoveries.map(function(d) { return escapeHtml(d); }).join(', ')}</div>` : ''}
      </div>`;
  }
  listEl.innerHTML = html;
}

async function renderCrossroadsView() {
  const container = $('#crossroads-content');
  if (!container) return;

  container.innerHTML = `
    <div class="crossroads-header fade-in">
      <h2>The Crossroads</h2>
      <p>A gathering point for travellers across all game sessions.</p>
    </div>
    <div class="crossroads-tabs">
      <button class="crossroads-tab active" data-crossroads-tab="items">Items</button>
      <button class="crossroads-tab" data-crossroads-tab="lore">Lore</button>
      <button class="crossroads-tab" data-crossroads-tab="messages">Messages</button>
    </div>
    <div id="crossroads-tab-content" class="crossroads-tab-content fade-in"></div>
  `;

  document.querySelectorAll('.crossroads-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      document.querySelectorAll('.crossroads-tab').forEach(function(t) { t.classList.remove('active'); });
      tab.classList.add('active');
      var tabName = tab.dataset.crossroadsTab;
      loadCrossroadsTab(tabName);
    });
  });

  loadCrossroadsTab('items');
}

async function loadCrossroadsTab(tabName) {
  const content = $('#crossroads-tab-content');
  if (!content) return;

  content.innerHTML = '<div class="loading">Loading...</div>';

  try {
    switch (tabName) {
      case 'items':
        await renderCrossroadsItems();
        break;
      case 'lore':
        await renderCrossroadsLore();
        break;
      case 'messages':
        await renderCrossroadsMessages();
        break;
    }
  } catch (e) {
    content.innerHTML = '<div class="error">Failed to load. Try again.</div>';
    console.error('Crossroads tab error:', e);
  }
}

async function renderCrossroadsItems() {
  const content = $('#crossroads-tab-content');
  if (!content) return;

  try {
    const data = await API.getCrossroadsItems();
    const items = data.items || [];

    let itemsHTML = '<div class="crossroads-section"><h3>Available Items</h3>';
    if (items.length === 0) {
      itemsHTML += '<p><em>No items available at the Crossroads right now.</em></p>';
    } else {
      itemsHTML += '<div class="crossroads-item-list">';
      for (const item of items) {
        itemsHTML += `
          <div class="crossroads-item-card">
            <div class="crossroads-item-name">${escapeHtml(item.item_name)} x${item.quantity}</div>
            <div class="crossroads-item-donor">Donated by ${escapeHtml(item.donor_name)}</div>
            ${item.message ? `<div class="crossroads-item-message">"${escapeHtml(item.message)}"</div>` : ''}
            <button data-action="claim-crossroads-item" data-item-id="${item.id}" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Claim</button>
          </div>`;
      }
      itemsHTML += '</div>';
    }
    itemsHTML += '</div>';

    itemsHTML += '<div class="crossroads-section"><h3>Donate an Item</h3>';
    itemsHTML += '<div style="display:flex;gap:0.5rem;align-items:center;">';
    itemsHTML += '<input id="donate-item-name" type="text" placeholder="Item name" style="flex:1;background:var(--color-panel-bg);border:1px solid var(--color-border);color:var(--color-text);padding:0.3rem;font-family:inherit;border-radius:4px;">';
    itemsHTML += '<input id="donate-item-qty" type="number" value="1" min="1" style="width:60px;background:var(--color-panel-bg);border:1px solid var(--color-border);color:var(--color-text);padding:0.3rem;font-family:inherit;border-radius:4px;">';
    itemsHTML += '<button data-action="donate-crossroads-item" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Donate</button>';
    itemsHTML += '</div>';
    itemsHTML += '<input id="donate-item-msg" type="text" placeholder="Optional message" style="width:100%;margin-top:0.3rem;background:var(--color-panel-bg);border:1px solid var(--color-border);color:var(--color-text);padding:0.3rem;font-family:inherit;border-radius:4px;">';
    itemsHTML += '</div>';

    content.innerHTML = itemsHTML;
  } catch (e) {
    content.innerHTML = '<div class="error">Failed to load items.</div>';
    console.error('Crossroads items error:', e);
  }
}

async function renderCrossroadsLore() {
  const content = $('#crossroads-tab-content');
  if (!content) return;

  try {
    const data = await API.getCrossroadsLore();
    const loreList = data.lore || [];

    let loreHTML = '<div class="crossroads-section"><h3>Available Lore Fragments</h3>';
    if (loreList.length === 0) {
      loreHTML += '<p><em>No lore fragments available at the Crossroads right now.</em></p>';
    } else {
      loreHTML += '<div class="crossroads-item-list">';
      for (const l of loreList) {
        loreHTML += `
          <div class="crossroads-item-card">
            <div class="crossroads-item-name">${escapeHtml(l.fragment_id)}</div>
            <div class="crossroads-item-donor">Donated by ${escapeHtml(l.donor_name)}</div>
            ${l.message ? `<div class="crossroads-item-message">"${escapeHtml(l.message)}"</div>` : ''}
            <button data-action="claim-crossroads-lore" data-lore-id="${l.id}" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Claim</button>
          </div>`;
      }
      loreHTML += '</div>';
    }
    loreHTML += '</div>';

    loreHTML += '<div class="crossroads-section"><h3>Donate a Lore Fragment</h3>';
    loreHTML += '<div style="display:flex;gap:0.5rem;align-items:center;">';
    loreHTML += '<input id="donate-lore-id" type="text" placeholder="Fragment ID (e.g. lore_architects_1)" style="flex:1;background:var(--color-panel-bg);border:1px solid var(--color-border);color:var(--color-text);padding:0.3rem;font-family:inherit;border-radius:4px;">';
    loreHTML += '<button data-action="donate-crossroads-lore" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Donate</button>';
    loreHTML += '</div>';
    loreHTML += '<input id="donate-lore-msg" type="text" placeholder="Optional message" style="width:100%;margin-top:0.3rem;background:var(--color-panel-bg);border:1px solid var(--color-border);color:var(--color-text);padding:0.3rem;font-family:inherit;border-radius:4px;">';
    loreHTML += '</div>';

    content.innerHTML = loreHTML;
  } catch (e) {
    content.innerHTML = '<div class="error">Failed to load lore.</div>';
    console.error('Crossroads lore error:', e);
  }
}

async function renderCrossroadsMessages() {
  const content = $('#crossroads-tab-content');
  if (!content) return;

  try {
    const data = await API.getCrossroadsMessages();
    const messages = data.messages || [];

    let msgsHTML = '<div class="crossroads-section"><h3>Recent Messages</h3>';
    if (messages.length === 0) {
      msgsHTML += '<p><em>No messages at the Crossroads yet.</em></p>';
    } else {
      msgsHTML += '<div class="crossroads-message-list">';
      for (const m of messages) {
        msgsHTML += `
          <div class="crossroads-message-card">
            <div class="crossroads-msg-player">${escapeHtml(m.player_name)}</div>
            <div class="crossroads-msg-time">${new Date(m.created_at).toLocaleString()}</div>
            <div class="crossroads-msg-text">${escapeHtml(m.text)}</div>
          </div>`;
      }
      msgsHTML += '</div>';
    }
    msgsHTML += '</div>';

    msgsHTML += '<div class="crossroads-section"><h3>Post a Message</h3>';
    msgsHTML += '<div style="display:flex;gap:0.5rem;align-items:center;">';
    msgsHTML += '<input id="post-msg-text" type="text" placeholder="Your message..." maxlength="500" style="flex:1;background:var(--color-panel-bg);border:1px solid var(--color-border);color:var(--color-text);padding:0.3rem;font-family:inherit;border-radius:4px;">';
    msgsHTML += '<button data-action="post-crossroads-message" class="ui-button" style="font-size:0.7rem;padding:0.3rem 0.5rem;">Post</button>';
    msgsHTML += '</div>';
    msgsHTML += '</div>';

    content.innerHTML = msgsHTML;
  } catch (e) {
    content.innerHTML = '<div class="error">Failed to load messages.</div>';
    console.error('Crossroads messages error:', e);
  }
}

function renderRippleNotification(ripple) {
  if (!ripple) return;

  var panel = $('#ripple-notification');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'ripple-notification';
    panel.className = 'ripple-notification ui-panel';
    panel.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:30;padding:1rem;min-width:300px;text-align:center;';
    document.body.appendChild(panel);
  }

  panel.innerHTML = `
    <div class="ui-panel-title">Discovery Ripple</div>
    <p>${escapeHtml(ripple.source_player_name)} discovered ${escapeHtml(ripple.discovery_name)} in a nearby system.</p>
    <p style="font-size:0.75rem;color:var(--color-text-dim);">${escapeHtml(ripple.discovery_type)} | ${new Date(ripple.created_at).toLocaleString()}</p>
    <button data-action="acknowledge-ripple" data-ripple-id="${ripple.id}" class="ui-button">Acknowledge</button>
  `;
  panel.style.display = 'block';
}

function initMultiplayerUI() {
  if (!window._sharedUniverse) return;

  API.getRipples(GAME_ID).then(function(data) {
    if (data && data.ripples && data.ripples.length > 0) {
      var unshown = data.ripples.filter(function(r) { return !window._dismissedRipples.has(r.id); });
      if (unshown.length > 0) {
        renderRippleNotification(unshown[0]);
      }
    }
  }).catch(function(e) {
    console.error('Failed to load ripples:', e);
  });
}

document.addEventListener('click', function(e) {
  var el = e.target;
  while (el && el !== document.body) {
    var action = el.dataset ? el.dataset.action : null;
    if (action) {
      handleMultiplayerAction(action, el);
      return;
    }
    el = el.parentElement;
  }
});

async function handleMultiplayerAction(action, target) {
  try {
    switch (action) {
      case 'claim-crossroads-item': {
        var itemId = target.dataset.itemId;
        if (!itemId) break;
        await API.claimItem(itemId, GAME_ID);
        await loadCrossroadsTab('items');
        break;
      }

      case 'donate-crossroads-item': {
        var itemName = document.getElementById('donate-item-name');
        var qty = document.getElementById('donate-item-qty');
        var msg = document.getElementById('donate-item-msg');
        if (!itemName || !itemName.value) {
          alert('Enter an item name.');
          break;
        }
        await API.donateItem(GAME_ID, itemName.value, parseInt(qty ? qty.value : 1) || 1, msg ? msg.value : null);
        await loadCrossroadsTab('items');
        break;
      }

      case 'claim-crossroads-lore': {
        var loreId = target.dataset.loreId;
        if (!loreId) break;
        await API.claimLore(loreId, GAME_ID);
        await loadCrossroadsTab('lore');
        break;
      }

      case 'donate-crossroads-lore': {
        var fragmentId = document.getElementById('donate-lore-id');
        var msg = document.getElementById('donate-lore-msg');
        if (!fragmentId || !fragmentId.value) {
          alert('Enter a fragment ID.');
          break;
        }
        await API.donateLore(GAME_ID, fragmentId.value, msg ? msg.value : null);
        await loadCrossroadsTab('lore');
        break;
      }

      case 'post-crossroads-message': {
        var textInput = document.getElementById('post-msg-text');
        if (!textInput || !textInput.value.trim()) {
          alert('Enter a message.');
          break;
        }
        await API.postMessage(GAME_ID, textInput.value.trim());
        await loadCrossroadsTab('messages');
        break;
      }

      case 'acknowledge-ripple': {
        var rippleId = target.dataset.rippleId;
        if (!rippleId) break;
        await API.acknowledgeRipple(GAME_ID, rippleId);
        window._dismissedRipples.add(rippleId);
        var panel = $('#ripple-notification');
        if (panel) panel.style.display = 'none';
        break;
      }
    }
  } catch (e) {
    console.error('Multiplayer action error:', e);
    alert('Error: ' + e.message);
  }
}
