// UI Utilities Module
// Common UI operations and DOM manipulation functions

/**
 * Display a status message to the user
 * @param {string} message - The message to display
 * @param {boolean} isError - Whether this is an error message
 */
export function setStatus(message, isError = false) {
  const el = document.getElementById('status-message');
  if (!el) return;
  el.textContent = message || '';
  el.className = isError ? 'error' : (message ? 'success' : '');
}

/**
 * Switch between dashboard tabs
 * @param {string} tabName - The name of the tab to switch to ('controls', 'emails', 'chat')
 */
export function switchTab(tabName) {
  const controlIds = [
    'control-panel', 'state-panel', 'active-projects-section', 'people-section',
    'persona-section', 'plans-section', 'metrics-section', 'token-section', 'events-section'
  ];

  // Update tab button ARIA states
  const tabButtons = document.querySelectorAll('.tab-button');
  tabButtons.forEach(btn => {
    const isActive = btn.dataset.tab === tabName;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', isActive.toString());
    btn.setAttribute('tabindex', isActive ? '0' : '-1');
  });

  const showControls = (tabName === 'controls');
  controlIds.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.display = showControls ? '' : 'none';
  });

  const emailsSection = document.getElementById('tab-emails');
  const chatSection = document.getElementById('tab-chat');
  const replaySection = document.getElementById('tab-replay');
  const clustersSection = document.getElementById('tab-clusters');

  if (emailsSection) {
    emailsSection.style.display = (tabName === 'emails') ? '' : 'none';
    emailsSection.setAttribute('aria-hidden', (tabName !== 'emails').toString());
  }
  if (chatSection) {
    chatSection.style.display = (tabName === 'chat') ? '' : 'none';
    chatSection.setAttribute('aria-hidden', (tabName !== 'chat').toString());
  }
  if (replaySection) {
    replaySection.style.display = (tabName === 'replay') ? '' : 'none';
    replaySection.setAttribute('aria-hidden', (tabName !== 'replay').toString());
  }
  if (clustersSection) {
    clustersSection.style.display = (tabName === 'clusters') ? '' : 'none';
    clustersSection.setAttribute('aria-hidden', (tabName !== 'clusters').toString());
  }

  // Announce tab change to screen readers
  announceToScreenReader(`Switched to ${tabName} tab`);
}

/**
 * Show a modal dialog
 * @param {string} modalId - The ID of the modal element to show
 */
export function showModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  
  modal.style.display = 'block';
  modal.setAttribute('aria-hidden', 'false');
  
  // Set focus to the first focusable element in the modal
  const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  if (focusable.length > 0) {
    focusable[0].focus();
  }
  
  // Announce modal opening to screen readers
  const modalTitle = modal.querySelector('h2, h3, [role="heading"]');
  if (modalTitle) {
    announceToScreenReader(`Dialog opened: ${modalTitle.textContent}`);
  }
}

/**
 * Hide a modal dialog
 * @param {string} modalId - The ID of the modal element to hide
 */
export function hideModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  
  modal.style.display = 'none';
  modal.setAttribute('aria-hidden', 'true');
  
  // Announce modal closing to screen readers
  announceToScreenReader('Dialog closed');
}

/**
 * Disable a button and optionally change its text
 * @param {string} buttonId - The ID of the button element
 * @param {string} loadingText - Optional text to display while disabled
 * @returns {string} The original button text
 */
export function disableButton(buttonId, loadingText = null) {
  const button = document.getElementById(buttonId);
  if (!button) return '';
  
  const originalText = button.textContent;
  button.disabled = true;
  button.style.opacity = '0.6';
  
  if (loadingText) {
    button.textContent = loadingText;
  }
  
  return originalText;
}

/**
 * Enable a button and restore its original text
 * @param {string} buttonId - The ID of the button element
 * @param {string} originalText - The original text to restore
 */
export function enableButton(buttonId, originalText) {
  const button = document.getElementById(buttonId);
  if (!button) return;
  
  button.disabled = false;
  button.style.opacity = '1';
  
  if (originalText) {
    button.textContent = originalText;
  }
}

/**
 * Announce a message to screen readers using ARIA live region
 * @param {string} message - The message to announce
 * @param {string} priority - The priority level ('polite' or 'assertive')
 */
export function announceToScreenReader(message, priority = 'polite') {
  // Find or create the live region
  let liveRegion = document.getElementById('sr-live-region');
  
  if (!liveRegion) {
    liveRegion = document.createElement('div');
    liveRegion.id = 'sr-live-region';
    liveRegion.setAttribute('role', 'status');
    liveRegion.setAttribute('aria-live', priority);
    liveRegion.setAttribute('aria-atomic', 'true');
    liveRegion.className = 'sr-only';
    liveRegion.style.position = 'absolute';
    liveRegion.style.left = '-10000px';
    liveRegion.style.width = '1px';
    liveRegion.style.height = '1px';
    liveRegion.style.overflow = 'hidden';
    document.body.appendChild(liveRegion);
  }
  
  // Update the live region with the message
  liveRegion.textContent = message;
  
  // Clear the message after a delay to allow for repeated announcements
  setTimeout(() => {
    liveRegion.textContent = '';
  }, 1000);
}

/**
 * Ensure persona select dropdowns are populated
 * Populates both email and chat persona selection dropdowns
 * @param {Array} peopleCache - Array of persona objects
 * @param {number} emailMonitorPersonId - Currently selected email persona ID
 * @param {number} chatMonitorPersonId - Currently selected chat persona ID
 * @param {Function} onEmailChange - Callback when email persona changes
 * @param {Function} onChatChange - Callback when chat persona changes
 * @returns {Object} Updated monitor IDs {emailMonitorPersonId, chatMonitorPersonId}
 */
export function ensurePersonaSelects(peopleCache, emailMonitorPersonId, chatMonitorPersonId, onEmailChange, onChatChange) {
  const emailSelect = document.getElementById('email-person-select');
  const chatSelect = document.getElementById('chat-person-select');
  
  const result = {
    emailMonitorPersonId,
    chatMonitorPersonId
  };
  
  if (emailSelect) {
    result.emailMonitorPersonId = populatePersonaSelect(
      emailSelect, 
      'email', 
      peopleCache, 
      emailMonitorPersonId, 
      onEmailChange
    );
  }
  
  if (chatSelect) {
    result.chatMonitorPersonId = populatePersonaSelect(
      chatSelect, 
      'chat', 
      peopleCache, 
      chatMonitorPersonId, 
      onChatChange
    );
  }
  
  return result;
}

/**
 * Populate a persona select dropdown
 * @param {HTMLSelectElement} selectEl - The select element to populate
 * @param {string} type - The type of select ('email' or 'chat')
 * @param {Array} peopleCache - Array of persona objects
 * @param {number} currentPersonId - Currently selected persona ID
 * @param {Function} onChange - Callback when selection changes
 * @returns {number} The selected persona ID
 */
function populatePersonaSelect(selectEl, type, peopleCache, currentPersonId, onChange) {
  // Preserve current selection
  const prev = Number(selectEl.value || 0) || null;
  selectEl.innerHTML = '';
  
  peopleCache.forEach(p => {
    const opt = document.createElement('option');
    opt.value = String(p.id);
    opt.textContent = `${p.name} (${p.role})`;
    selectEl.appendChild(opt);
  });
  
  let chosen = prev && peopleCache.some(p => p.id === prev) ? prev : (peopleCache[0]?.id || null);
  let monitorPersonId = chosen;
  
  if (chosen != null) {
    selectEl.value = String(chosen);
  }

  // Attach change listener once
  if (!selectEl.dataset.bound) {
    selectEl.addEventListener('change', () => {
      const val = Number(selectEl.value);
      if (onChange) {
        onChange(val);
      }
    });
    selectEl.dataset.bound = '1';
  }
  
  return monitorPersonId;
}

/**
 * Build a persona card element
 * @param {Object} person - The persona object
 * @param {boolean} checked - Whether the checkbox should be checked
 * @returns {HTMLElement} The persona card element
 */
export function buildPersonCard(person, checked) {
  const card = document.createElement('div');
  card.className = 'person-card';
  
  const label = document.createElement('label');
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.value = person.id;
  checkbox.checked = checked;
  
  label.appendChild(checkbox);
  
  const title = document.createElement('span');
  const teamInfo = person.team_name ? ` - ${person.team_name}` : '';
  title.textContent = ` ${person.name} (${person.role})${teamInfo}`;
  label.appendChild(title);
  
  card.appendChild(label);
  
  const meta = document.createElement('div');
  meta.textContent = `${person.timezone} · ${person.work_hours}`;
  meta.className = 'small';
  card.appendChild(meta);
  
  return card;
}

/**
 * Build a plan card element showing hourly plan and daily report
 * @param {Object} entry - The plan entry object with person, hourly, daily, and optional error
 * @returns {HTMLElement} The plan card element
 */
export function buildPlanCard(entry) {
  const card = document.createElement('div');
  card.className = 'plan-card';
  
  const title = document.createElement('h3');
  const teamInfo = entry.person.team_name ? ` - ${entry.person.team_name}` : '';
  title.textContent = `${entry.person.name} (${entry.person.role})${teamInfo}`;
  card.appendChild(title);
  
  if (entry.error) {
    const error = document.createElement('div');
    error.textContent = `Error: ${entry.error}`;
    error.style.color = '#b91c1c';
    card.appendChild(error);
    return card;
  }
  
  const hourlyLabel = document.createElement('strong');
  hourlyLabel.textContent = 'Latest Hourly Plan:';
  card.appendChild(hourlyLabel);
  
  const hourlyPre = document.createElement('pre');
  hourlyPre.textContent = entry.hourly || '—';
  card.appendChild(hourlyPre);
  
  const dailyLabel = document.createElement('strong');
  dailyLabel.textContent = 'Latest Daily Report:';
  card.appendChild(dailyLabel);
  
  const dailyPre = document.createElement('pre');
  dailyPre.textContent = entry.daily || '—';
  card.appendChild(dailyPre);
  
  return card;
}
