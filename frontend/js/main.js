let GAME_ID = null;

function notifyLoreFragment(title) {
  console.log('Lore fragment discovered (lore viewer not loaded):', title);
}

function updateLoreButtonGlow() {}

async function initApp() {
  const savedId = getSavedGameId();
  if (savedId) {
    try {
      const data = await API.getGame(savedId);
      if (data) {
        GAME_ID = savedId;
        setGameId(savedId);
        updateGameState(data);
        return;
      }
    } catch (e) {
      console.log('No saved game found, starting new.');
    }
  }
  showScreen('menu');
}

function updateGameState(data) {
  if (!data || !data.ship) return;

  window._currentSystemId = data.current_system ? data.current_system.id : null;
  updateShipStatus(data.ship);
  updateJSONLD(data);
  updateLoreButtonGlow();
}

function updateJSONLD(data) {
  let script = document.getElementById('game-state');
  if (!script) {
    script = document.createElement('script');
    script.type = 'application/ld+json';
    script.id = 'game-state';
    document.head.appendChild(script);
  }
  script.textContent = JSON.stringify(data, null, 2);
}

let galaxyEventsSetup = false;
async function loadGalaxyScreen() {
  try {
    const data = await API.galaxy(GAME_ID);
    renderGalaxy(data.systems, data.current_system_id);
    window._currentSystemId = data.current_system_id;
    if (!galaxyEventsSetup) {
      setupGalaxyEvents();
      galaxyEventsSetup = true;
    }
  } catch (e) {
    console.error('Galaxy load error:', e);
  }
}

async function loadSystemScreen(sysId) {
  try {
    const data = await API.systemDetail(GAME_ID, sysId);
    renderSystemView(data, GAME_ID);
    const gameData = await API.getGame(GAME_ID);
    updateGameState(gameData);
  } catch (e) {
    console.error('System load error:', e);
  }
}

async function handleAction(action, target) {
  try {
    switch (action) {
      case 'new-game': {
        const seedInp = $('#new-game-seed');
        const nameInp = $('#new-game-ship-name');
        const seed = seedInp ? parseInt(seedInp.value) || undefined : undefined;
        const name = nameInp ? nameInp.value || undefined : undefined;
        const data = await API.newGame(seed, name, GAME_ID || undefined);
        GAME_ID = data.game_id;
        setGameId(GAME_ID);
        updateGameState(data.state);

        const sysId = data.state.ship?.current_system_id || data.state.current_system?.id;
        if (sysId) {
          await loadSystemScreen(sysId);
          showScreen('system');
        }
        break;
      }

      case 'continue-game': {
        const savedId = getSavedGameId();
        if (!savedId) { alert('No saved game found.'); break; }
        try {
          const data = await API.load(savedId);
          GAME_ID = savedId;
          setGameId(savedId);
          updateGameState(data.state);

          const sysId = data.state.ship?.current_system_id || data.state.current_system?.id;
          if (sysId) {
            await loadSystemScreen(sysId);
            showScreen('system');
          }
        } catch (e) { alert('Could not load saved game.'); }
        break;
      }

      case 'show-galaxy': {
        await loadGalaxyScreen();
        showScreen('galaxy');
        const gameData = await API.getGame(GAME_ID);
        updateGameState(gameData);
        break;
      }

      case 'show-system': {
        const sysId = target?.dataset?.systemId || window._currentSystemId;
        if (sysId) {
          await loadSystemScreen(sysId);
          showScreen('system');
        }
        break;
      }

      case 'jump-to': {
        const sysId = target?.dataset?.systemId;
        if (!sysId) break;
        const data = await API.jump(GAME_ID, sysId);
        updateGameState(data);

        if (data.pending_event) {
          showEventModal(data.pending_event, GAME_ID);
        }
        await loadSystemScreen(sysId);
        showScreen('system');
        break;
      }

      case 'scan': {
        const data = await API.scan(GAME_ID);
        updateGameState(data);

        if (data.pending_event) {
          showEventModal(data.pending_event, GAME_ID);
        }
        const sysId = window._currentSystemId;
        if (sysId) await loadSystemScreen(sysId);
        break;
      }

      case 'land': {
        const bodyId = target?.dataset?.bodyId;
        if (!bodyId) break;
        const data = await API.land(GAME_ID, bodyId);
        updateGameState(data);

        const sysId = window._currentSystemId;
        const sysData = await API.systemDetail(GAME_ID, sysId);
        const body = sysData.system.bodies.find(b => b.id === bodyId);
        renderSurfaceView(body, [], GAME_ID);
        showScreen('surface');
        break;
      }

      case 'explore': {
        const data = await API.explore(GAME_ID);
        updateGameState(data);

        if (data.lore_fragments_discovered && data.lore_fragments_discovered.length > 0) {
          for (const frag of data.lore_fragments_discovered) {
            notifyLoreFragment(frag.title);
          }
        }

        if (data.pending_event) {
          showEventModal(data.pending_event, GAME_ID);
        }

        const sysId = window._currentSystemId;
        const sysData = await API.systemDetail(GAME_ID, sysId);
        const body = sysData.system.bodies.find(b => b.id === data.ship?.current_body_id);
        if (body) {
          renderSurfaceView(body, data.discoveries, GAME_ID);
        }
        break;
      }

      case 'resolve-event': {
        const eventId = target?.dataset?.eventId;
        const choiceIdx = parseInt(target?.dataset?.choiceIdx);
        if (!eventId || isNaN(choiceIdx)) break;
        const data = await API.resolveEvent(GAME_ID, eventId, choiceIdx);
        updateGameState(data);
        closeEventModal();
        break;
      }

      case 'return-system': {
        const sysId = window._currentSystemId;
        if (sysId) {
          await loadSystemScreen(sysId);
          showScreen('system');
        }
        break;
      }

      case 'show-log': {
        await loadLog(GAME_ID);
        showScreen('log');
        break;
      }

      case 'show-lore': {
        await loadLore(GAME_ID);
        _unreadLoreCount = 0;
        updateLoreButtonGlow();
        showScreen('lore');
        break;
      }

      case 'select-lore-arc': {
        const arcId = target?.dataset?.arcId;
        if (arcId) selectLoreArcTab(arcId);
        break;
      }

      case 'save-game': {
        await API.save(GAME_ID);
        break;
      }
    }
  } catch (e) {
    console.error('Action error:', e);
    alert('Error: ' + e.message);
  }
}

document.addEventListener('click', (e) => {
  let el = e.target;
  while (el && el !== document.body) {
    const action = el.dataset?.action;
    if (action) {
      e.preventDefault();
      handleAction(action, el);
      return;
    }
    el = el.parentElement;
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeEventModal();
  }
});

initApp();
