// Replay / Time Machine functionality
// Handles jumping to previous ticks and viewing historical data

import { API_PREFIX, fetchJson } from '../core/api.js';
import { setStatus } from '../utils/ui.js';

// ===== State =====
let replayMetadata = null;

// ===== API Calls =====

async function getReplayMetadata() {
  try {
    const data = await fetchJson(`${API_PREFIX}/replay/metadata`);
    replayMetadata = data;
    return data;
  } catch (err) {
    console.error('[REPLAY] Failed to fetch metadata:', err);
    throw err;
  }
}

async function jumpToTick(tick) {
  try {
    const data = await fetchJson(`${API_PREFIX}/replay/jump/${tick}`);
    return data;
  } catch (err) {
    console.error(`[REPLAY] Failed to jump to tick ${tick}:`, err);
    throw err;
  }
}

async function jumpToTime(day, hour, minute) {
  try {
    const data = await fetchJson(`${API_PREFIX}/replay/jump`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day, hour, minute })
    });
    return data;
  } catch (err) {
    console.error(`[REPLAY] Failed to jump to time D${day} ${hour}:${minute}:`, err);
    throw err;
  }
}

async function getCurrentTickData() {
  try {
    const data = await fetchJson(`${API_PREFIX}/replay/current`);
    return data;
  } catch (err) {
    console.error('[REPLAY] Failed to fetch current tick data:', err);
    throw err;
  }
}

async function resetToLive() {
  try {
    const data = await fetchJson(`${API_PREFIX}/replay/reset`);
    return data;
  } catch (err) {
    console.error('[REPLAY] Failed to reset to live mode:', err);
    throw err;
  }
}

// ===== UI Update Functions =====

function updateReplayIndicator(metadata) {
  const indicator = document.getElementById('replay-mode-indicator');
  const indicatorTime = document.getElementById('replay-indicator-time');
  const headerIndicator = document.getElementById('header-replay-indicator');

  if (metadata.is_replay) {
    // Calculate day and time from current tick using workday model
    const currentTick = metadata.current_tick;
    const ticksPerDay = metadata.ticks_per_day || 480;  // Default to 480 if not provided
    const baseHour = metadata.base_hour || 9;  // Default to 09:00 if not provided

    const day = Math.floor((currentTick - 1) / ticksPerDay) + 1;
    const tickOfDay = (currentTick - 1) % ticksPerDay;
    const hour = baseHour + Math.floor(tickOfDay / 60);
    const minute = tickOfDay % 60;
    const timeStr = `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;

    if (indicator && indicatorTime) {
      indicatorTime.textContent = `Viewing Day ${day}, ${timeStr} (Tick ${currentTick.toLocaleString()})`;
      indicator.style.display = 'flex';
    }

    // Show header indicator
    if (headerIndicator) {
      headerIndicator.style.display = 'inline-block';
    }
  } else {
    if (indicator) {
      indicator.style.display = 'none';
    }
    if (headerIndicator) {
      headerIndicator.style.display = 'none';
    }
  }
}

function updateReplayInfo(metadata) {
  const currentTickEl = document.getElementById('replay-current-tick');
  const maxTickEl = document.getElementById('replay-max-tick');
  const modeEl = document.getElementById('replay-mode');

  if (currentTickEl) {
    currentTickEl.textContent = metadata.current_tick.toLocaleString();
  }

  if (maxTickEl) {
    maxTickEl.textContent = metadata.max_generated_tick.toLocaleString();
  }

  if (modeEl) {
    modeEl.textContent = metadata.is_replay ? 'Replay' : 'Live';
    modeEl.className = metadata.is_replay ? 'value badge replay' : 'value badge live';
  }
}

function updateReplayStateTime(tickData) {
  const stateTimeEl = document.getElementById('replay-state-time');
  if (stateTimeEl && tickData) {
    stateTimeEl.textContent = `(Day ${tickData.day}, ${tickData.sim_time})`;
  }
}

function displayEmails(emails) {
  const emailsList = document.getElementById('replay-emails-list');
  if (!emailsList) return;

  if (!emails || emails.length === 0) {
    emailsList.innerHTML = '<p style="color: #64748b; text-align: center; padding: 20px;">No emails at this tick</p>';
    return;
  }

  const html = emails.map(email => `
    <div class="email-item" style="border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; margin-bottom: 8px;">
      <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
        <div style="flex: 1;">
          <strong style="color: #1e293b;">${escapeHtml(email.sender)}</strong>
          <div style="font-size: 12px; color: #64748b; margin-top: 2px;">
            To: ${email.recipients ? email.recipients.map(r => escapeHtml(r)).join(', ') : 'N/A'}
          </div>
        </div>
        <div style="font-size: 11px; color: #94a3b8; white-space: nowrap; margin-left: 12px;">
          ${email.sent_at || 'N/A'}
        </div>
      </div>
      <div style="font-weight: 600; color: #334155; margin-bottom: 6px;">
        ${escapeHtml(email.subject || '(No Subject)')}
      </div>
      <div style="font-size: 13px; color: #475569; line-height: 1.5; max-height: 100px; overflow-y: auto;">
        ${escapeHtml(email.body || '')}
      </div>
    </div>
  `).join('');

  emailsList.innerHTML = html;
}

function displayChats(chats) {
  const chatsList = document.getElementById('replay-chats-list');
  if (!chatsList) return;

  if (!chats || chats.length === 0) {
    chatsList.innerHTML = '<p style="color: #64748b; text-align: center; padding: 20px;">No chats at this tick</p>';
    return;
  }

  const html = chats.map(chat => `
    <div class="chat-item" style="border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; margin-bottom: 6px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
        <strong style="color: #1e293b; font-size: 13px;">${escapeHtml(chat.sender)}</strong>
        <span style="font-size: 11px; color: #94a3b8;">
          ${chat.sent_at || 'N/A'}
        </span>
      </div>
      <div style="font-size: 13px; color: #475569; line-height: 1.4;">
        ${escapeHtml(chat.body || '')}
      </div>
      <div style="font-size: 11px; color: #94a3b8; margin-top: 4px;">
        Room ID: ${chat.room_id}
      </div>
    </div>
  `).join('');

  chatsList.innerHTML = html;
}

function showError(message) {
  const errorEl = document.getElementById('replay-error');
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.style.display = 'block';
    setTimeout(() => {
      errorEl.style.display = 'none';
    }, 5000);
  }
}

function clearError() {
  const errorEl = document.getElementById('replay-error');
  if (errorEl) {
    errorEl.style.display = 'none';
  }
}

// ===== Helper Functions =====

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ===== Event Handlers =====

async function handleJumpToTime() {
  const dayInput = document.getElementById('replay-jump-day');
  const hourInput = document.getElementById('replay-jump-hour');
  const minuteInput = document.getElementById('replay-jump-minute');

  if (!dayInput || !hourInput || !minuteInput) {
    console.error('[REPLAY] Jump input fields not found');
    return;
  }

  const day = parseInt(dayInput.value, 10);
  const hour = parseInt(hourInput.value, 10);
  const minute = parseInt(minuteInput.value, 10);

  if (isNaN(day) || isNaN(hour) || isNaN(minute)) {
    showError('Please enter valid numbers for day, hour, and minute');
    return;
  }

  if (day < 1) {
    showError('Day must be 1 or greater');
    return;
  }

  if (hour < 0 || hour > 23) {
    showError('Hour must be between 0 and 23');
    return;
  }

  if (minute < 0 || minute > 59) {
    showError('Minute must be between 0 and 59');
    return;
  }

  clearError();

  try {
    setStatus('Jumping to time...', 'info');
    const tickData = await jumpToTime(day, hour, minute);

    // Update UI
    const metadata = await getReplayMetadata();
    updateReplayIndicator(metadata);
    updateReplayInfo(metadata);
    updateReplayStateTime(tickData);

    // Display emails and chats
    displayEmails(tickData.data?.emails || []);
    displayChats(tickData.data?.chats || []);

    setStatus(`Jumped to Day ${tickData.day}, ${tickData.sim_time} (Tick ${tickData.tick})`, 'success');
  } catch (err) {
    console.error('[REPLAY] Jump failed:', err);
    showError(`Failed to jump: ${err.message || 'Unknown error'}`);
    setStatus('Jump failed', 'error');
  }
}

async function handleResetToLive() {
  try {
    setStatus('Returning to live mode...', 'info');
    const metadata = await resetToLive();

    // Update UI
    updateReplayIndicator(metadata);
    updateReplayInfo(metadata);

    // Clear state display
    const stateTimeEl = document.getElementById('replay-state-time');
    if (stateTimeEl) {
      stateTimeEl.textContent = '';
    }

    // Clear emails and chats
    const emailsList = document.getElementById('replay-emails-list');
    const chatsList = document.getElementById('replay-chats-list');
    if (emailsList) {
      emailsList.innerHTML = '<p style="color: #64748b; text-align: center; padding: 20px;">Click "Jump to Time" to load emails at that tick</p>';
    }
    if (chatsList) {
      chatsList.innerHTML = '<p style="color: #64748b; text-align: center; padding: 20px;">Click "Jump to Time" to load chats at that tick</p>';
    }

    setStatus('Returned to live mode', 'success');
  } catch (err) {
    console.error('[REPLAY] Reset failed:', err);
    showError(`Failed to reset: ${err.message || 'Unknown error'}`);
    setStatus('Reset failed', 'error');
  }
}

function handleSecondaryTabSwitch(e) {
  const btn = e.target.closest('.tab-button-secondary');
  if (!btn) return;

  const tab = btn.dataset.tabSecondary;

  // Update active state
  document.querySelectorAll('.tab-button-secondary').forEach(b => {
    b.classList.remove('active');
  });
  btn.classList.add('active');

  // Show/hide content
  const emailsContent = document.getElementById('replay-emails-content');
  const chatsContent = document.getElementById('replay-chats-content');

  if (tab === 'replay-emails') {
    if (emailsContent) emailsContent.style.display = 'block';
    if (chatsContent) chatsContent.style.display = 'none';
  } else if (tab === 'replay-chats') {
    if (emailsContent) emailsContent.style.display = 'none';
    if (chatsContent) chatsContent.style.display = 'block';
  }
}

// ===== Initialization =====

export async function initReplay() {
  console.log('[REPLAY] Initializing replay module...');

  // Set up event listeners
  const jumpBtn = document.getElementById('replay-jump-btn');
  const resetBtn = document.getElementById('replay-reset-btn');
  const indicatorResetBtn = document.getElementById('replay-indicator-reset-btn');
  const tabsSecondary = document.querySelector('.tabs-secondary');

  if (jumpBtn) {
    jumpBtn.addEventListener('click', handleJumpToTime);
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', handleResetToLive);
  }

  if (indicatorResetBtn) {
    indicatorResetBtn.addEventListener('click', handleResetToLive);
  }

  if (tabsSecondary) {
    tabsSecondary.addEventListener('click', handleSecondaryTabSwitch);
  }

  // Load initial metadata
  try {
    const metadata = await getReplayMetadata();
    updateReplayIndicator(metadata);
    updateReplayInfo(metadata);
  } catch (err) {
    console.error('[REPLAY] Failed to load initial metadata:', err);
  }

  console.log('[REPLAY] Replay module initialized');
}

// ===== Exports =====

export {
  getReplayMetadata,
  jumpToTick,
  jumpToTime,
  getCurrentTickData,
  resetToLive,
  updateReplayIndicator,
  updateReplayInfo
};
