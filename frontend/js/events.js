function showEventModal(eventData, gameId) {
  const overlay = h('div', { className: 'modal-overlay', id: 'event-modal' });

  let choicesHTML = '';
  for (let i = 0; i < eventData.choices.length; i++) {
    const c = eventData.choices[i];
    choicesHTML += `
      <button class="ui-button" data-action="resolve-event" data-event-id="${eventData.id}" data-choice-idx="${i}" style="margin-bottom:0.5rem;display:block;width:100%;text-align:left;">
        ${i + 1}. ${c.text}
      </button>`;
  }

  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-title">${eventData.title}</div>
      <div class="modal-body">${eventData.flavor}</div>
      ${choicesHTML}
    </div>
  `;

  document.body.appendChild(overlay);
}

function closeEventModal() {
  const modal = document.getElementById('event-modal');
  if (modal) modal.remove();
}
