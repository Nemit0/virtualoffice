// VDOS Dashboard JavaScript
const API_PREFIX = '/api/v1';
let selectedPeople = new Set();
let refreshIntervalId = null;
let currentRefreshInterval = 60000; // Start with 1 minute
let isSimulationRunning = false;
let autoRefreshEnabled = true; // Auto-refresh toggle state
let projects = []; // Array of project objects
let people_cache = []; // Cache of all people for project team selection
let emailMonitorPersonId = null;
let chatMonitorPersonId = null;
let emailFolder = 'inbox'; // 'inbox' | 'sent'
let emailCache = { inbox: [], sent: [] };
let emailSelected = { box: 'inbox', id: null };
let emailAutoOpenFirst = false;
let emailListFocusIndex = -1; // Track focused email in list for keyboard navigation
let emailSearchQuery = ''; // Current search query
let emailSearchTimeout = null; // Debounce timeout for search
let lastEmailRefresh = 0; // Timestamp of last email refresh for caching
let emailRenderCache = new Map(); // Cache for rendered email rows to avoid re-rendering
let emailSortCache = new Map(); // Cache for sorted email lists

function setStatus(message, isError = false) {
  const el = document.getElementById('status-message');
  el.textContent = message || '';
  el.className = isError ? 'error' : (message ? 'success' : '');
}

async function fetchJson(url, options = {}) {
  const opts = { ...options };
  if (opts.body && !opts.headers) {
    opts.headers = { 'Content-Type': 'application/json' };
  }
  const response = await fetch(url, opts);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function parseCommaSeparated(value) {
  if (!value) return [];
  return value.split(',').map(entry => entry.trim()).filter(Boolean);
}

function parseLines(value) {
  if (!value) return [];
  return value.split('\\n').map(line => line.trim()).filter(Boolean);
}

function parseSchedule(text) {
  if (!text) return [];
  const lines = text.split('\\n').map(line => line.trim()).filter(Boolean);
  return lines.map(line => {
    const [range, ...rest] = line.split(' ');
    if (!range || !range.includes('-')) {
      return null;
    }
    const [start, end] = range.split('-');
    const activity = rest.join(' ').trim() || 'Focus block';
    return { start: start.trim(), end: end.trim(), activity };
  }).filter(Boolean);
}

function buildPersonCard(person, checked) {
  const card = document.createElement('div');
  card.className = 'person-card';
  const label = document.createElement('label');
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.value = person.id;
  checkbox.checked = checked;
  checkbox.addEventListener('change', () => {
    const id = Number(checkbox.value);
    if (checkbox.checked) {
      selectedPeople.add(id);
    } else {
      selectedPeople.delete(id);
    }
  });
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

function buildPlanCard(entry) {
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

async function refreshState() {
  const state = await fetchJson(`${API_PREFIX}/simulation`);
  document.getElementById('state-status').textContent = state.is_running ? 'running' : 'stopped';
  document.getElementById('state-current_tick').textContent = state.current_tick;
  document.getElementById('state-sim_time').textContent = state.sim_time || 'Day 0 00:00';
  document.getElementById('state-auto').textContent = state.auto_tick;

  // Load current tick interval
  try {
    const intervalData = await fetchJson(`${API_PREFIX}/simulation/ticks/interval`);
    document.getElementById('tick-interval').value = intervalData.tick_interval_seconds;
  } catch (err) {
    console.error('Failed to fetch tick interval:', err);
  }

  // Fetch and display auto-pause status
  try {
    const autoPauseStatus = await fetchJson(`${API_PREFIX}/simulation/auto-pause/status`);
    updateAutoPauseDisplay(autoPauseStatus);
  } catch (err) {
    console.error('Failed to fetch auto-pause status:', err);
    // Set default values if API call fails
    updateAutoPauseDisplay({
      auto_pause_enabled: false,
      active_projects_count: 0,
      future_projects_count: 0,
      should_pause: false,
      reason: 'Status unavailable'
    });
  }

  // Update refresh interval based on simulation state
  const wasRunning = isSimulationRunning;
  isSimulationRunning = state.is_running || state.auto_tick;

  // If state changed, update the refresh interval
  if (wasRunning !== isSimulationRunning) {
    setRefreshInterval(isSimulationRunning ? 5000 : 60000);
  }
}

async function refreshPeopleAndPlans() {
  const people = await fetchJson(`${API_PREFIX}/people`);
  people_cache = people; // Cache for project team selection
  const container = document.getElementById('people-container');
  const plansContainer = document.getElementById('plans-container');
  const currentSelection = new Set(Array.from(container.querySelectorAll('input[type=checkbox]')).filter(cb => cb.checked).map(cb => Number(cb.value)));
  if (selectedPeople.size === 0 && currentSelection.size > 0) {
    selectedPeople = currentSelection;
  }
  container.innerHTML = '';
  plansContainer.innerHTML = '';
  if (!people.length) {
    container.textContent = 'No personas registered.';
    return;
  }
  if (selectedPeople.size === 0) {
    people.forEach(person => selectedPeople.add(Number(person.id)));
  }
  people.forEach(person => {
    const checked = selectedPeople.has(Number(person.id));
    container.appendChild(buildPersonCard(person, checked));
  });
  const entries = await Promise.all(people.map(async person => {
    try {
      const [hourly, daily] = await Promise.all([
        fetchJson(`${API_PREFIX}/people/${person.id}/plans?plan_type=hourly&limit=1`),
        fetchJson(`${API_PREFIX}/people/${person.id}/daily-reports?limit=1`),
      ]);
      return {
        person,
        hourly: hourly && hourly.length ? hourly[0].content : '',
        daily: daily && daily.length ? daily[0].report : '',
      };
    } catch (err) {
      return { person, error: err.message || String(err) };
    }
  }));
  entries.forEach(entry => { plansContainer.appendChild(buildPlanCard(entry)); });
}

async function refreshPlannerMetrics() {
  const metrics = await fetchJson(`${API_PREFIX}/metrics/planner?limit=50`);
  const tbody = document.querySelector('#planner-table tbody');
  tbody.innerHTML = '';
  metrics.slice().reverse().forEach(row => {
    const tr = document.createElement('tr');
    const cells = [
      row.timestamp,
      row.method,
      row.result_planner,
      row.model,
      row.duration_ms,
      row.fallback ? `Yes${row.error ? ' (' + row.error + ')' : ''}` : 'No',
      JSON.stringify(row.context),
    ];
    cells.forEach(value => {
      const td = document.createElement('td');
      td.textContent = value == null ? '' : String(value);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

async function refreshTokenUsage() {
  const data = await fetchJson(`${API_PREFIX}/simulation/token-usage`);
  const tbody = document.querySelector('#token-table tbody');
  tbody.innerHTML = '';
  Object.entries(data.per_model || {}).forEach(([model, tokens]) => {
    const tr = document.createElement('tr');
    const tdModel = document.createElement('td');
    tdModel.textContent = model;
    const tdTokens = document.createElement('td');
    tdTokens.textContent = tokens;
    tr.appendChild(tdModel);
    tr.appendChild(tdTokens);
    tbody.appendChild(tr);
  });
}

async function refreshEvents() {
  const events = await fetchJson(`${API_PREFIX}/events`);
  const list = document.getElementById('events-list');
  list.innerHTML = '';
  events.slice(-10).reverse().forEach(evt => {
    const li = document.createElement('li');
    li.textContent = `#${evt.id} [${evt.type}] targets=${evt.target_ids.join(', ')} at tick ${evt.at_tick}`;
    list.appendChild(li);
  });
}

async function refreshActiveProjects() {
  try {
    const activeProjects = await fetchJson(`${API_PREFIX}/simulation/active-projects`);
    const container = document.getElementById('active-projects-container');
    container.innerHTML = '';

    if (!activeProjects || activeProjects.length === 0) {
      return; // Empty state handled by CSS ::before
    }

    activeProjects.forEach(item => {
      const project = item.project;
      const teamMembers = item.team_members || [];

      const card = document.createElement('div');
      card.className = 'active-project-item';

      const title = document.createElement('h4');
      title.textContent = `📋 ${project.project_name}`;
      card.appendChild(title);

      const summary = document.createElement('div');
      summary.className = 'project-info';
      summary.textContent = project.project_summary;
      card.appendChild(summary);

      const timeline = document.createElement('div');
      timeline.className = 'project-timeline';
      const endWeek = project.start_week + project.duration_weeks - 1;
      timeline.textContent = `📅 Week ${project.start_week} - ${endWeek} (${project.duration_weeks} weeks)`;
      card.appendChild(timeline);

      // Group team members by team
      const teamGroups = {};
      teamMembers.forEach(member => {
        const teamName = member.team_name || 'No Team';
        if (!teamGroups[teamName]) {
          teamGroups[teamName] = [];
        }
        teamGroups[teamName].push(member);
      });

      const teamDiv = document.createElement('div');
      teamDiv.className = 'project-team';

      Object.keys(teamGroups).sort().forEach((teamName, idx) => {
        if (idx > 0) {
          const separator = document.createElement('div');
          separator.style.marginTop = '8px';
          teamDiv.appendChild(separator);
        }

        const teamLabel = document.createElement('div');
        teamLabel.style.fontWeight = '600';
        teamLabel.style.marginBottom = '4px';
        teamLabel.textContent = `${teamName}:`;
        teamDiv.appendChild(teamLabel);

        teamGroups[teamName].forEach(member => {
          const memberSpan = document.createElement('span');
          memberSpan.className = 'team-member';
          memberSpan.textContent = `${member.name} (${member.role})`;
          teamDiv.appendChild(memberSpan);
        });
      });

      card.appendChild(teamDiv);
      container.appendChild(card);
    });
  } catch (err) {
    console.error('Error refreshing active projects:', err);
    // Don't show error to user, just log it
  }
}

async function refreshAll() {
  try {
    await refreshState();
    await refreshActiveProjects();
    await refreshPeopleAndPlans();
    await refreshPlannerMetrics();
    await refreshTokenUsage();
    await refreshEvents();
    await refreshEmailsTab();
    await refreshChatTab();
    setStatus('');
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

function gatherSelectedPersonIds() {
  return Array.from(document.querySelectorAll('#people-container input[type=checkbox]'))
    .filter(cb => cb.checked)
    .map(cb => Number(cb.value));
}

function gatherDeselectedPersonIds() {
  return Array.from(document.querySelectorAll('#people-container input[type=checkbox]'))
    .filter(cb => !cb.checked)
    .map(cb => Number(cb.value));
}

async function startSimulation() {
  const startBtn = document.getElementById('start-btn');
  
  // Prevent multiple clicks by disabling the button
  if (startBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  startBtn.disabled = true;
  const originalText = startBtn.textContent;
  startBtn.textContent = 'Starting...';
  startBtn.style.opacity = '0.6';
  
  try {
    const includeIds = gatherSelectedPersonIds();
    const excludeIds = gatherDeselectedPersonIds();
    const seedText = document.getElementById('random-seed').value.trim();
    const modelHint = document.getElementById('model-hint').value.trim();

    let payload;

    // If multi-project configuration is provided, use it
    if (projects.length > 0) {
      // Multi-project mode
      payload = {
        projects: projects.map(p => ({
          project_name: p.name,
          project_summary: p.summary,
          assigned_person_ids: p.team_ids,
          start_week: p.start_week,
          duration_weeks: p.duration_weeks
        }))
      };
    } else {
      // Backwards-compatible single project mode (legacy)
      const projectName = document.getElementById('project-name')?.value.trim() || 'Dashboard Project';
      const projectSummary = document.getElementById('project-summary')?.value.trim() || 'Generated from web dashboard';
      const duration = parseInt(document.getElementById('project-duration')?.value, 10) || 1;
      payload = {
        project_name: projectName,
        project_summary: projectSummary,
        duration_weeks: duration
      };
    }

    if (includeIds.length) { payload.include_person_ids = includeIds; }
    if (excludeIds.length) { payload.exclude_person_ids = excludeIds; }
    if (seedText) {
      const seed = Number(seedText);
      if (!Number.isNaN(seed)) { payload.random_seed = seed; }
    }
    if (modelHint) { payload.model_hint = modelHint; }

    setStatus('Starting simulation...');
    await fetchJson(`${API_PREFIX}/simulation/start`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    // Start auto-tick thread to enable automatic advancement
    setStatus('Starting auto-tick...');
    await fetchJson(`${API_PREFIX}/simulation/ticks/start`, {
      method: 'POST',
    });

    setStatus('Simulation started with auto-tick enabled');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    startBtn.disabled = false;
    startBtn.textContent = originalText;
    startBtn.style.opacity = '1';
  }
}

async function stopSimulation() {
  const stopBtn = document.getElementById('stop-btn');
  
  // Prevent multiple clicks by disabling the button
  if (stopBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  stopBtn.disabled = true;
  const originalText = stopBtn.textContent;
  stopBtn.textContent = 'Stopping...';
  stopBtn.style.opacity = '0.6';
  
  try {
    setStatus('Stopping simulation...');
    await fetchJson(`${API_PREFIX}/simulation/stop`, { method: 'POST' });
    setStatus('Simulation stopped');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    stopBtn.disabled = false;
    stopBtn.textContent = originalText;
    stopBtn.style.opacity = '1';
  }
}

async function resetSimulation() {
  const resetBtn = document.getElementById('reset-btn');
  
  // Prevent multiple clicks by disabling the button
  if (resetBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  resetBtn.disabled = true;
  const originalText = resetBtn.textContent;
  resetBtn.textContent = 'Resetting...';
  resetBtn.style.opacity = '0.6';
  
  try {
    setStatus('Resetting simulation...');
    await fetchJson(`${API_PREFIX}/simulation/reset`, { method: 'POST' });
    setStatus('Simulation reset');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    resetBtn.disabled = false;
    resetBtn.textContent = originalText;
    resetBtn.style.opacity = '1';
  }
}

async function fullResetSimulation() {
  const confirmed = confirm('This will DELETE ALL PERSONAS and reset the simulation. Continue?');
  if (!confirmed) return;
  
  const fullResetBtn = document.getElementById('full-reset-btn');
  
  // Prevent multiple clicks by disabling the button
  if (fullResetBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  fullResetBtn.disabled = true;
  const originalText = fullResetBtn.textContent;
  fullResetBtn.textContent = 'Resetting...';
  fullResetBtn.style.opacity = '0.6';
  
  try {
    setStatus('Performing full reset...');
    await fetchJson(`${API_PREFIX}/simulation/full-reset`, { method: 'POST' });
    setStatus('Full reset complete (personas deleted).');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    fullResetBtn.disabled = false;
    fullResetBtn.textContent = originalText;
    fullResetBtn.style.opacity = '1';
  }
}

async function advanceSimulation() {
  const advanceBtn = document.getElementById('advance-btn');
  
  // Prevent multiple clicks by disabling the button
  if (advanceBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  advanceBtn.disabled = true;
  const originalText = advanceBtn.textContent;
  advanceBtn.textContent = 'Advancing...';
  advanceBtn.style.opacity = '0.6';
  
  try {
    const ticks = parseInt(document.getElementById('advance-ticks').value, 10) || 1;
    const reason = document.getElementById('advance-reason').value.trim() || 'manual';
    await fetchJson(`${API_PREFIX}/simulation/advance`, {
      method: 'POST',
      body: JSON.stringify({ ticks, reason }),
    });
    setStatus(`Advanced ${ticks} tick(s)`);
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    advanceBtn.disabled = false;
    advanceBtn.textContent = originalText;
    advanceBtn.style.opacity = '1';
  }
}

async function startAutoTicks() {
  const autoStartBtn = document.getElementById('auto-start-btn');
  
  // Prevent multiple clicks by disabling the button
  if (autoStartBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  autoStartBtn.disabled = true;
  const originalText = autoStartBtn.textContent;
  autoStartBtn.textContent = 'Starting...';
  autoStartBtn.style.opacity = '0.6';
  
  try {
    await fetchJson(`${API_PREFIX}/simulation/ticks/start`, { method: 'POST' });
    setStatus('Automatic ticking enabled');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    autoStartBtn.disabled = false;
    autoStartBtn.textContent = originalText;
    autoStartBtn.style.opacity = '1';
  }
}

async function stopAutoTicks() {
  const autoStopBtn = document.getElementById('auto-stop-btn');
  
  // Prevent multiple clicks by disabling the button
  if (autoStopBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  autoStopBtn.disabled = true;
  const originalText = autoStopBtn.textContent;
  autoStopBtn.textContent = 'Stopping...';
  autoStopBtn.style.opacity = '0.6';
  
  try {
    await fetchJson(`${API_PREFIX}/simulation/ticks/stop`, { method: 'POST' });
    setStatus('Automatic ticking disabled');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    autoStopBtn.disabled = false;
    autoStopBtn.textContent = originalText;
    autoStopBtn.style.opacity = '1';
  }
}

async function updateTickInterval() {
  try {
    const interval = parseFloat(document.getElementById('tick-interval').value);
    if (isNaN(interval) || interval < 0 || interval > 60) {
      setStatus('Tick interval must be between 0 and 60 seconds', true);
      return;
    }
    const result = await fetchJson(`${API_PREFIX}/simulation/ticks/interval`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interval })
    });
    setStatus(result.message || `Tick interval set to ${interval}s`);
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

async function toggleAutoPause() {
  const toggleEl = document.getElementById('auto-pause-toggle');
  if (!toggleEl) return;
  
  const enabled = toggleEl.checked;
  
  // Log the toggle action for debugging
  console.log('[AUTO-PAUSE] User toggled auto-pause:', {
    requested_state: enabled,
    timestamp: new Date().toISOString()
  });
  
  try {
    setStatus('Updating auto-pause setting...');
    const result = await fetchJson(`${API_PREFIX}/simulation/auto-pause/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    });
    
    // Log the server response
    console.log('[AUTO-PAUSE] Server response to toggle:', {
      requested: enabled,
      actual: result.auto_pause_enabled,
      success: result.auto_pause_enabled === enabled,
      full_response: result,
      timestamp: new Date().toISOString()
    });
    
    // Update the toggle to reflect the actual server state
    toggleEl.checked = result.auto_pause_enabled;
    
    const statusMsg = result.auto_pause_enabled ? 'Auto-pause enabled' : 'Auto-pause disabled';
    setStatus(statusMsg);
    
    // Update the auto-pause display immediately
    updateAutoPauseDisplay(result);
    
  } catch (err) {
    // Log the error for debugging
    console.error('[AUTO-PAUSE] Failed to toggle auto-pause:', {
      requested_state: enabled,
      error: err.message || String(err),
      timestamp: new Date().toISOString()
    });
    
    // Revert the toggle on error
    toggleEl.checked = !enabled;
    setStatus(err.message || String(err), true);
  }
}

function toggleAutoRefresh() {
  const toggleEl = document.getElementById('auto-refresh-toggle');
  if (!toggleEl) return;
  
  autoRefreshEnabled = toggleEl.checked;
  
  // Store preference in localStorage for persistence
  localStorage.setItem('vdos-auto-refresh-enabled', autoRefreshEnabled.toString());
  
  console.log('[AUTO-REFRESH] User toggled auto-refresh:', {
    enabled: autoRefreshEnabled,
    timestamp: new Date().toISOString()
  });
  
  if (autoRefreshEnabled) {
    // Re-enable auto-refresh with current interval
    setRefreshInterval(currentRefreshInterval);
    setupChatAutoRefresh();
    setStatus('Auto-refresh enabled');
  } else {
    // Disable all auto-refresh intervals
    if (refreshIntervalId !== null) {
      clearInterval(refreshIntervalId);
      refreshIntervalId = null;
    }
    if (chatState.autoRefreshInterval) {
      clearInterval(chatState.autoRefreshInterval);
      chatState.autoRefreshInterval = null;
    }
    setStatus('Auto-refresh disabled');
  }
}

function loadAutoRefreshPreference() {
  // Load preference from localStorage
  const saved = localStorage.getItem('vdos-auto-refresh-enabled');
  if (saved !== null) {
    autoRefreshEnabled = saved === 'true';
  }
  
  // Update toggle to match preference
  const toggleEl = document.getElementById('auto-refresh-toggle');
  if (toggleEl) {
    toggleEl.checked = autoRefreshEnabled;
  }
  
  console.log('[AUTO-REFRESH] Loaded preference:', {
    enabled: autoRefreshEnabled,
    source: saved !== null ? 'localStorage' : 'default'
  });
}

function updateAutoPauseDisplay(autoPauseStatus) {
  // Comprehensive logging for auto-pause status debugging
  console.log('[AUTO-PAUSE] Status update:', {
    enabled: autoPauseStatus.auto_pause_enabled,
    should_pause: autoPauseStatus.should_pause,
    active_projects: autoPauseStatus.active_projects_count,
    future_projects: autoPauseStatus.future_projects_count,
    current_week: autoPauseStatus.current_week,
    current_tick: autoPauseStatus.current_tick,
    current_day: autoPauseStatus.current_day,
    reason: autoPauseStatus.reason,
    timestamp: new Date().toISOString()
  });
  
  // Check for auto-pause state changes and log them
  const currentState = {
    enabled: autoPauseStatus.auto_pause_enabled,
    should_pause: autoPauseStatus.should_pause,
    active_count: autoPauseStatus.active_projects_count || 0,
    future_count: autoPauseStatus.future_projects_count || 0
  };
  
  if (lastAutoPauseState) {
    if (currentState.should_pause !== lastAutoPauseState.should_pause) {
      if (currentState.should_pause) {
        console.warn('[AUTO-PAUSE] 🛑 Auto-pause condition triggered!', {
          week: autoPauseStatus.current_week,
          tick: autoPauseStatus.current_tick,
          reason: autoPauseStatus.reason,
          completed_projects: 'All projects completed',
          timestamp: new Date().toISOString()
        });
      } else {
        console.log('[AUTO-PAUSE] ✅ Auto-pause condition cleared', {
          week: autoPauseStatus.current_week,
          active_projects: currentState.active_count,
          future_projects: currentState.future_count,
          timestamp: new Date().toISOString()
        });
      }
    }
    
    if (currentState.active_count !== lastAutoPauseState.active_count) {
      console.log('[AUTO-PAUSE] Active projects changed:', {
        from: lastAutoPauseState.active_count,
        to: currentState.active_count,
        week: autoPauseStatus.current_week,
        timestamp: new Date().toISOString()
      });
    }
    
    if (currentState.future_count !== lastAutoPauseState.future_count) {
      console.log('[AUTO-PAUSE] Future projects changed:', {
        from: lastAutoPauseState.future_count,
        to: currentState.future_count,
        week: autoPauseStatus.current_week,
        timestamp: new Date().toISOString()
      });
    }
  }
  
  // Store current state for next comparison
  lastAutoPauseState = currentState;
  
  // Update auto-pause toggle to match server state
  const toggleEl = document.getElementById('auto-pause-toggle');
  if (toggleEl) {
    toggleEl.checked = autoPauseStatus.auto_pause_enabled;
  }
  
  // Update status display
  const autoPauseEl = document.getElementById('state-auto-pause');
  if (autoPauseEl) {
    autoPauseEl.textContent = autoPauseStatus.auto_pause_enabled ? 'Enabled' : 'Disabled';
    autoPauseEl.className = autoPauseStatus.auto_pause_enabled ? 'enabled' : 'disabled';
  }
  
  // Update project counts
  const activeProjectsEl = document.getElementById('state-active-projects');
  if (activeProjectsEl) {
    const count = autoPauseStatus.active_projects_count || 0;
    activeProjectsEl.textContent = count.toString();
    activeProjectsEl.className = (count === 0 && autoPauseStatus.auto_pause_enabled) ? 'warning' : '';
  }
  
  const futureProjectsEl = document.getElementById('state-future-projects');
  if (futureProjectsEl) {
    const count = autoPauseStatus.future_projects_count || 0;
    futureProjectsEl.textContent = count.toString();
    futureProjectsEl.className = (count === 0 && autoPauseStatus.auto_pause_enabled) ? 'warning' : '';
  }
  
  // Show/hide warning based on auto-pause conditions
  const warningEl = document.getElementById('auto-pause-warning');
  const warningTextEl = document.getElementById('auto-pause-warning-text');
  
  if (warningEl && warningTextEl) {
    const shouldShowWarning = autoPauseStatus.auto_pause_enabled && 
                             autoPauseStatus.should_pause && 
                             autoPauseStatus.reason;
    
    if (shouldShowWarning) {
      warningTextEl.textContent = autoPauseStatus.reason;
      warningEl.style.display = 'flex';
      warningEl.classList.remove('hidden');
      
      // Log warning display for debugging
      console.warn('[AUTO-PAUSE] Displaying warning to user:', autoPauseStatus.reason);
      
      // Announce warning to screen readers
      announceToScreenReader(`Auto-pause warning: ${autoPauseStatus.reason}`);
    } else {
      warningEl.style.display = 'none';
      warningEl.classList.add('hidden');
    }
  }
}

function populatePersonaForm(persona) {
  document.getElementById('persona-name').value = persona.name || '';
  document.getElementById('persona-role').value = persona.role || '';
  document.getElementById('persona-timezone').value = persona.timezone || 'UTC';
  document.getElementById('persona-hours').value = persona.work_hours || '09:00-17:00';
  document.getElementById('persona-break').value = persona.break_frequency || '50/10 cadence';
  document.getElementById('persona-style').value = persona.communication_style || 'Warm async';
  document.getElementById('persona-email').value = persona.email_address || '';
  document.getElementById('persona-chat').value = persona.chat_handle || '';
  document.getElementById('persona-team').value = persona.team_name || '';
  document.getElementById('persona-is-head').checked = Boolean(persona.is_department_head);
  document.getElementById('persona-skills').value = (persona.skills || []).join(', ');
  document.getElementById('persona-personality').value = (persona.personality || []).join(', ');
  document.getElementById('persona-objectives').value = (persona.objectives || []).join('\\n');
  document.getElementById('persona-metrics').value = (persona.metrics || []).join('\\n');
  document.getElementById('persona-guidelines').value = (persona.planning_guidelines || []).join('\\n');
  const schedule = (persona.schedule || []).map(block => `${block.start}-${block.end} ${block.activity || ''}`.trim()).join('\\n');
  document.getElementById('persona-schedule').value = schedule;
  document.getElementById('persona-playbook').value = JSON.stringify(persona.event_playbook || {}, null, 2);
  document.getElementById('persona-statuses').value = (persona.statuses || []).join('\\n');
}

function clearPersonaForm() {
  populatePersonaForm({});
  document.getElementById('persona-is-head').checked = false;
}

async function generatePersona() {
  const prompt = document.getElementById('persona-prompt').value.trim();
  if (!prompt) {
    setStatus('Enter a prompt before generating.', true);
    return;
  }
  try {
    setStatus('Generating persona...');
    const response = await fetchJson(`${API_PREFIX}/personas/generate`, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    });
    if (response && response.persona) {
      populatePersonaForm(response.persona);
      setStatus('Persona drafted. Review the fields and click Create Persona.');
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

function collectPersonaPayload() {
  const eventPlaybookText = document.getElementById('persona-playbook').value.trim();
  let eventPlaybook = {};
  if (eventPlaybookText) {
    try {
      eventPlaybook = JSON.parse(eventPlaybookText);
    } catch (err) {
      throw new Error('Invalid event playbook JSON');
    }
  }
  const schedule = parseSchedule(document.getElementById('persona-schedule').value);
  const teamName = document.getElementById('persona-team').value.trim();
  return {
    name: document.getElementById('persona-name').value.trim(),
    role: document.getElementById('persona-role').value.trim(),
    timezone: document.getElementById('persona-timezone').value.trim() || 'UTC',
    work_hours: document.getElementById('persona-hours').value.trim() || '09:00-17:00',
    break_frequency: document.getElementById('persona-break').value.trim() || '50/10 cadence',
    communication_style: document.getElementById('persona-style').value.trim() || 'Async',
    email_address: document.getElementById('persona-email').value.trim(),
    chat_handle: document.getElementById('persona-chat').value.trim(),
    team_name: teamName || null,
    is_department_head: document.getElementById('persona-is-head').checked,
    skills: parseCommaSeparated(document.getElementById('persona-skills').value),
    personality: parseCommaSeparated(document.getElementById('persona-personality').value),
    objectives: parseLines(document.getElementById('persona-objectives').value),
    metrics: parseLines(document.getElementById('persona-metrics').value),
    planning_guidelines: parseLines(document.getElementById('persona-guidelines').value),
    schedule,
    event_playbook: eventPlaybook,
    statuses: parseLines(document.getElementById('persona-statuses').value),
  };
}

async function createPersona() {
  let payload;
  try {
    payload = collectPersonaPayload();
  } catch (err) {
    setStatus(err.message || String(err), true);
    return;
  }
  if (!payload.name || !payload.role || !payload.email_address || !payload.chat_handle) {
    setStatus('Name, role, email, and chat handle are required.', true);
    return;
  }
  if (!payload.skills.length) {
    setStatus('Specify at least one skill.', true);
    return;
  }
  if (!payload.personality.length) {
    setStatus('Specify at least one personality trait.', true);
    return;
  }
  try {
    const created = await fetchJson(`${API_PREFIX}/people`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    setStatus(`Created persona ${payload.name}`);
    if (created && created.id) {
      selectedPeople.add(Number(created.id));
    }
    clearPersonaForm();
    await refreshPeopleAndPlans();
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

// Project Management Functions
function addProject() {
  const projectName = prompt("Enter project name:");
  if (!projectName) return;

  const projectSummary = prompt("Enter project summary:");
  if (!projectSummary) return;

  const startWeek = parseInt(prompt("Start week (1-52):", "1"));
  if (!startWeek || startWeek < 1) {
    setStatus("Invalid start week", true);
    return;
  }

  const durationWeeks = parseInt(prompt("Duration in weeks (1-52):", "1"));
  if (!durationWeeks || durationWeeks < 1) {
    setStatus("Invalid duration", true);
    return;
  }

  // Show team selection dialog
  showTeamSelectionDialog(projectName, projectSummary, startWeek, durationWeeks);
}

function showTeamSelectionDialog(projectName, projectSummary, startWeek, durationWeeks) {
  // Create a dialog for team selection
  const teamIds = [];
  const teams = getUniqueTeams();

  if (teams.length === 0) {
    setStatus("No teams available. Please create personas with team assignments first.", true);
    return;
  }

  let message = `Select teams for "${projectName}":\n\n`;
  teams.forEach((team, idx) => {
    message += `${idx + 1}. ${team.name} (${team.members.length} members)\n`;
  });
  message += `\nEnter team numbers separated by commas (e.g., "1,2"):`;

  const selection = prompt(message);
  if (!selection) return;

  const indices = selection.split(',').map(s => parseInt(s.trim()) - 1);
  indices.forEach(idx => {
    if (idx >= 0 && idx < teams.length) {
      teamIds.push(...teams[idx].memberIds);
    }
  });

  if (teamIds.length === 0) {
    setStatus("No valid teams selected", true);
    return;
  }

  const project = {
    name: projectName,
    summary: projectSummary,
    team_ids: teamIds,
    start_week: startWeek,
    duration_weeks: durationWeeks
  };

  projects.push(project);
  renderProjects();
  setStatus(`Added project: ${projectName}`);
}

function getUniqueTeams() {
  const teamsMap = new Map();

  people_cache.forEach(person => {
    const teamName = person.team_name || "No Team";
    if (!teamsMap.has(teamName)) {
      teamsMap.set(teamName, {
        name: teamName,
        members: [],
        memberIds: []
      });
    }
    teamsMap.get(teamName).members.push(person.name);
    teamsMap.get(teamName).memberIds.push(person.id);
  });

  return Array.from(teamsMap.values());
}

function removeProject(index) {
  if (confirm(`Remove project "${projects[index].name}"?`)) {
    projects.splice(index, 1);
    renderProjects();
    setStatus("Project removed");
  }
}

function renderProjects() {
  const container = document.getElementById('projects-list');
  container.innerHTML = '';

  projects.forEach((project, index) => {
    const card = document.createElement('div');
    card.className = 'project-card';

    const title = document.createElement('h4');
    title.textContent = project.name;
    card.appendChild(title);

    const summary = document.createElement('div');
    summary.className = 'project-info';
    summary.textContent = project.summary;
    card.appendChild(summary);

    const timeline = document.createElement('div');
    timeline.className = 'project-info';
    timeline.textContent = `📅 Week ${project.start_week} - ${project.start_week + project.duration_weeks - 1} (${project.duration_weeks} weeks)`;
    card.appendChild(timeline);

    const teamInfo = document.createElement('div');
    teamInfo.className = 'project-teams';
    const teamMembers = people_cache.filter(p => project.team_ids.includes(p.id)).map(p => p.name);
    teamInfo.textContent = `👥 Team: ${teamMembers.join(', ')}`;
    card.appendChild(teamInfo);

    const removeBtn = document.createElement('button');
    removeBtn.textContent = 'Remove';
    removeBtn.className = 'remove-project-btn';
    removeBtn.onclick = () => removeProject(index);
    card.appendChild(removeBtn);

    container.appendChild(card);
  });
}

function setRefreshInterval(intervalMs) {
  if (currentRefreshInterval === intervalMs && refreshIntervalId !== null) {
    return; // No change needed
  }

  currentRefreshInterval = intervalMs;

  // Clear existing interval
  if (refreshIntervalId !== null) {
    clearInterval(refreshIntervalId);
    refreshIntervalId = null;
  }

  // Only set new interval if auto-refresh is enabled
  if (autoRefreshEnabled) {
    refreshIntervalId = setInterval(refreshAll, intervalMs);
    console.log(`Dashboard refresh interval set to ${intervalMs / 1000}s`);
  } else {
    console.log('Dashboard auto-refresh is disabled');
  }
}

function init() {
  document.getElementById('start-btn').addEventListener('click', startSimulation);
  document.getElementById('stop-btn').addEventListener('click', stopSimulation);
  document.getElementById('reset-btn').addEventListener('click', resetSimulation);
  document.getElementById('full-reset-btn').addEventListener('click', fullResetSimulation);
  document.getElementById('advance-btn').addEventListener('click', advanceSimulation);
  document.getElementById('auto-start-btn').addEventListener('click', startAutoTicks);
  document.getElementById('auto-stop-btn').addEventListener('click', stopAutoTicks);
  document.getElementById('refresh-btn').addEventListener('click', refreshAll);
  document.getElementById('tick-interval').addEventListener('change', updateTickInterval);
  document.getElementById('auto-pause-toggle').addEventListener('change', toggleAutoPause);
  document.getElementById('auto-refresh-toggle').addEventListener('change', toggleAutoRefresh);
  document.getElementById('persona-generate-btn').addEventListener('click', generatePersona);
  document.getElementById('persona-create-btn').addEventListener('click', createPersona);
  document.getElementById('persona-clear-btn').addEventListener('click', clearPersonaForm);
  document.getElementById('add-project-btn').addEventListener('click', addProject);
  
  // Export/Import event listeners
  document.getElementById('export-personas-btn').addEventListener('click', exportPersonas);
  document.getElementById('import-personas-btn').addEventListener('click', importPersonas);
  document.getElementById('export-projects-btn').addEventListener('click', exportProjects);
  document.getElementById('import-projects-btn').addEventListener('click', importProjects);

  // Load auto-refresh preference from localStorage
  loadAutoRefreshPreference();

  // Initial refresh
  refreshAll();

  // Start with 1-minute interval (will auto-adjust based on simulation state)
  setRefreshInterval(60000);
}

// Export/Import Functions
async function exportPersonas() {
  const exportBtn = document.getElementById('export-personas-btn');
  
  // Prevent multiple clicks by disabling the button
  if (exportBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  exportBtn.disabled = true;
  const originalText = exportBtn.textContent;
  exportBtn.textContent = 'Exporting...';
  exportBtn.style.opacity = '0.6';
  
  try {
    setStatus('Exporting personas...');
    const data = await fetchJson(`${API_PREFIX}/export/personas`);
    
    // Create and download JSON file
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vdos-personas-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    setStatus(`Exported ${data.personas.length} personas successfully`);
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    exportBtn.disabled = false;
    exportBtn.textContent = originalText;
    exportBtn.style.opacity = '1';
  }
}

async function importPersonas() {
  const importBtn = document.getElementById('import-personas-btn');
  
  // Prevent multiple clicks by disabling the button
  if (importBtn.disabled) {
    return;
  }
  
  // Create file input
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.json';
  fileInput.style.display = 'none';
  
  fileInput.addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    // Disable button and update text to show it's processing
    importBtn.disabled = true;
    const originalText = importBtn.textContent;
    importBtn.textContent = 'Importing...';
    importBtn.style.opacity = '0.6';
    
    try {
      setStatus('Reading file...');
      const text = await file.text();
      const data = JSON.parse(text);
      
      setStatus('Importing personas...');
      const result = await fetchJson(`${API_PREFIX}/import/personas`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
      
      setStatus(result.message);
      if (result.errors && result.errors.length > 0) {
        console.warn('Import warnings:', result.errors);
      }
      
      // Refresh the personas list
      await refreshPeopleAndPlans();
      
    } catch (err) {
      if (err instanceof SyntaxError) {
        setStatus('Invalid JSON file format', true);
      } else {
        setStatus(err.message || String(err), true);
      }
    } finally {
      // Re-enable button and restore original text
      importBtn.disabled = false;
      importBtn.textContent = originalText;
      importBtn.style.opacity = '1';
      
      // Clean up file input
      document.body.removeChild(fileInput);
    }
  });
  
  document.body.appendChild(fileInput);
  fileInput.click();
}

async function exportProjects() {
  const exportBtn = document.getElementById('export-projects-btn');
  
  // Prevent multiple clicks by disabling the button
  if (exportBtn.disabled) {
    return;
  }
  
  // Disable button and update text to show it's processing
  exportBtn.disabled = true;
  const originalText = exportBtn.textContent;
  exportBtn.textContent = 'Exporting...';
  exportBtn.style.opacity = '0.6';
  
  try {
    setStatus('Exporting projects...');
    
    // Export current frontend projects array
    const exportData = {
      export_type: 'projects',
      export_timestamp: new Date().toISOString(),
      version: '1.0',
      projects: projects.map(p => ({
        project_name: p.name,
        project_summary: p.summary,
        start_week: p.start_week,
        duration_weeks: p.duration_weeks,
        assigned_person_ids: p.team_ids || []
      }))
    };
    
    // Create and download JSON file
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vdos-projects-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    setStatus(`Exported ${exportData.projects.length} projects successfully`);
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    exportBtn.disabled = false;
    exportBtn.textContent = originalText;
    exportBtn.style.opacity = '1';
  }
}

async function importProjects() {
  const importBtn = document.getElementById('import-projects-btn');
  
  // Prevent multiple clicks by disabling the button
  if (importBtn.disabled) {
    return;
  }
  
  // Create file input
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.json';
  fileInput.style.display = 'none';
  
  fileInput.addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    // Disable button and update text to show it's processing
    importBtn.disabled = true;
    const originalText = importBtn.textContent;
    importBtn.textContent = 'Importing...';
    importBtn.style.opacity = '0.6';
    
    try {
      setStatus('Reading file...');
      const text = await file.text();
      const data = JSON.parse(text);
      
      setStatus('Validating projects...');
      const result = await fetchJson(`${API_PREFIX}/import/projects`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
      
      if (result.error_count > 0) {
        setStatus(`Validation errors found: ${result.errors.join(', ')}`, true);
        return;
      }
      
      // Clear existing projects and load imported ones
      projects.length = 0;
      result.validated_projects.forEach(p => {
        projects.push({
          name: p.project_name,
          summary: p.project_summary,
          start_week: p.start_week,
          duration_weeks: p.duration_weeks,
          team_ids: p.assigned_person_ids || []
        });
      });
      
      // Re-render projects
      renderProjects();
      
      setStatus(result.message);
      if (result.errors && result.errors.length > 0) {
        console.warn('Import warnings:', result.errors);
      }
      
    } catch (err) {
      if (err instanceof SyntaxError) {
        setStatus('Invalid JSON file format', true);
      } else {
        setStatus(err.message || String(err), true);
      }
    } finally {
      // Re-enable button and restore original text
      importBtn.disabled = false;
      importBtn.textContent = originalText;
      importBtn.style.opacity = '1';
      
      // Clean up file input
      document.body.removeChild(fileInput);
    }
  });
  
  document.body.appendChild(fileInput);
  fileInput.click();
}

document.addEventListener('DOMContentLoaded', init);

// Global keyboard shortcuts
document.addEventListener('keydown', (e) => {
  // Only handle shortcuts when not typing in input fields
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
    return;
  }
  
  // Check if any modifier keys are pressed (except Shift for capital letters)
  if (e.ctrlKey || e.altKey || e.metaKey) {
    return;
  }
  
  const activeTab = document.querySelector('.tab-button.active')?.dataset.tab;
  
  switch (e.key.toLowerCase()) {
    case 'r':
      e.preventDefault();
      if (activeTab === 'emails') {
        refreshEmailsTab(true);
      } else if (activeTab === 'chat') {
        handleChatRefresh();
      }
      break;
      
    case 'm':
      e.preventDefault();
      if (activeTab === 'chat' && chatState.selectedConversationSlug) {
        handleMessageRefresh();
      }
      break;
      
    case 'p':
      e.preventDefault();
      if (activeTab === 'chat') {
        logPerformanceMetrics();
      }
      break;
      
    case 'i':
      e.preventDefault();
      if (activeTab === 'emails') {
        emailFolder = 'inbox';
        renderEmailPanels();
      }
      break;
      
    case 's':
      e.preventDefault();
      if (activeTab === 'emails') {
        emailFolder = 'sent';
        renderEmailPanels();
      }
      break;
  }
});

// ---------------- Tabs & Monitoring (Emails/Chat) -----------------
function setActiveTab(tabName) {
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
  if (emailsSection) {
    emailsSection.style.display = (tabName === 'emails') ? '' : 'none';
    emailsSection.setAttribute('aria-hidden', (tabName !== 'emails').toString());
  }
  if (chatSection) {
    chatSection.style.display = (tabName === 'chat') ? '' : 'none';
    chatSection.setAttribute('aria-hidden', (tabName !== 'chat').toString());
  }

  // Performance optimization: Clear caches when switching away from emails
  if (tabName !== 'emails') {
    // Limit cache size to prevent memory leaks
    if (emailRenderCache.size > 100) {
      emailRenderCache.clear();
    }
    if (emailSortCache.size > 20) {
      emailSortCache.clear();
    }
  }

  // Refresh when switching
  if (tabName === 'emails') {
    refreshEmailsTab();
    // Set focus to email list when switching to emails tab
    setTimeout(() => {
      const emailList = document.getElementById('email-list');
      if (emailList) {
        emailList.focus();
      }
    }, 100);
  }
  if (tabName === 'chat') {
    refreshChatTab();
    // Set focus to conversation search when switching to chat tab
    setTimeout(() => {
      const chatSearch = document.getElementById('chat-search');
      if (chatSearch) {
        chatSearch.focus();
      }
    }, 100);
  }
  
  // Announce tab change to screen readers
  announceToScreenReader(`Switched to ${tabName} tab`);
}

function ensurePersonaSelects() {
  const emailSelect = document.getElementById('email-person-select');
  const chatSelect = document.getElementById('chat-person-select');
  if (emailSelect) populatePersonaSelect(emailSelect, 'email');
  if (chatSelect) populatePersonaSelect(chatSelect, 'chat');
}

function populatePersonaSelect(selectEl, type) {
  // Preserve current selection
  const prev = Number(selectEl.value || 0) || null;
  selectEl.innerHTML = '';
  people_cache.forEach(p => {
    const opt = document.createElement('option');
    opt.value = String(p.id);
    opt.textContent = `${p.name} (${p.role})`;
    selectEl.appendChild(opt);
  });
  let chosen = prev && people_cache.some(p => p.id === prev) ? prev : (people_cache[0]?.id || null);
  if (type === 'email') emailMonitorPersonId = chosen;
  if (type === 'chat') chatMonitorPersonId = chosen;
  if (chosen != null) selectEl.value = String(chosen);

  // Attach change listener once
  if (!selectEl.dataset.bound) {
    selectEl.addEventListener('change', () => {
      const val = Number(selectEl.value);
      if (type === 'email') {
        emailMonitorPersonId = val;
        refreshEmailsTab();
      }
      if (type === 'chat') {
        // Clear conversation selection when persona changes
        if (chatMonitorPersonId !== val) {
          clearConversationSelection();
        }
        chatMonitorPersonId = val;
        refreshChatTab();
      }
    });
    selectEl.dataset.bound = '1';
  }
}

function renderEmailList(containerId, items) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  if (!items || items.length === 0) {
    container.textContent = 'No emails.';
    return;
  }
  items.forEach(msg => {
    const item = document.createElement('div');
    item.className = 'list-item email-item';

    // Header row (click to toggle)
    const header = document.createElement('div');
    header.className = 'subject-row';
    header.setAttribute('role', 'button');
    header.setAttribute('tabindex', '0');

    const title = document.createElement('div');
    title.className = 'title';
    title.textContent = msg.subject || '(no subject)';

    const rightMeta = document.createElement('div');
    rightMeta.className = 'meta';
    const sentAt = msg.sent_at || '';
    rightMeta.textContent = `#${msg.id} · ${sentAt}`;

    const chevron = document.createElement('span');
    chevron.className = 'chevron';
    chevron.textContent = '▶';
    rightMeta.appendChild(document.createTextNode(' '));
    rightMeta.appendChild(chevron);

    header.appendChild(title);
    header.appendChild(rightMeta);
    item.appendChild(header);

    // Collapsible details
    const details = document.createElement('div');
    details.className = 'details';

    const fromMeta = document.createElement('div');
    fromMeta.className = 'meta';
    fromMeta.textContent = `From: ${msg.sender || ''}`;
    details.appendChild(fromMeta);

    if (msg.to && msg.to.length) {
      const to = document.createElement('div');
      to.className = 'meta';
      to.textContent = `To: ${msg.to.join(', ')}`;
      details.appendChild(to);
    }
    if (msg.cc && msg.cc.length) {
      const cc = document.createElement('div');
      cc.className = 'meta';
      cc.textContent = `CC: ${msg.cc.join(', ')}`;
      details.appendChild(cc);
    }
    if (msg.bcc && msg.bcc.length) {
      const bcc = document.createElement('div');
      bcc.className = 'meta';
      bcc.textContent = `BCC: ${msg.bcc.join(', ')}`;
      details.appendChild(bcc);
    }

    const pre = document.createElement('pre');
    pre.textContent = msg.body || '';
    details.appendChild(pre);
    item.appendChild(details);

    function toggleOpen() {
      const isOpen = item.classList.toggle('open');
      chevron.textContent = isOpen ? '▼' : '▶';
    }
    header.addEventListener('click', toggleOpen);
    header.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleOpen();
      }
    });

    container.appendChild(item);
  });
}

async function refreshEmailsTab(forceRefresh = false) {
  // Populate selects if needed
  ensurePersonaSelects();
  if (!emailMonitorPersonId) return;
  
  // Performance optimization: Avoid unnecessary API calls
  const now = Date.now();
  const CACHE_DURATION = isSimulationRunning ? 15000 : 30000; // Shorter cache during active simulation
  if (!forceRefresh && (now - lastEmailRefresh) < CACHE_DURATION && 
      (emailCache.inbox.length > 0 || emailCache.sent.length > 0)) {
    renderEmailPanels();
    return;
  }
  
  // Update status indicator
  const statusEl = document.getElementById('email-last-refresh');
  if (statusEl) {
    statusEl.textContent = 'Refreshing...';
  }
  
  try {
    // Performance optimization: Use larger limit for better caching, but with pagination support
    const currentList = emailCache[emailFolder] || [];
    const limit = currentList.length > 100 ? 500 : 200;
    const data = await fetchJson(`${API_PREFIX}/monitor/emails/${emailMonitorPersonId}?box=all&limit=${limit}`);
    emailCache.inbox = data.inbox || [];
    emailCache.sent = data.sent || [];
    lastEmailRefresh = now;
    
    // Clear render cache when data changes
    emailRenderCache.clear();
    emailSortCache.clear();
    
    // If selection points to an email no longer present, clear it
    const selectedBoxList = emailCache[emailSelected.box] || [];
    if (!selectedBoxList.some(m => m.id === emailSelected.id)) {
      emailSelected.id = null;
      emailListFocusIndex = -1;
    }
    
    renderEmailPanels();
    
    // Update last refresh time
    if (statusEl) {
      const refreshTime = new Date();
      statusEl.textContent = `Last refreshed: ${refreshTime.toLocaleTimeString()}`;
    }
    
    if (emailAutoOpenFirst) {
      const list = emailCache[emailFolder] || [];
      if (list.length > 0) {
        emailSelected = { box: emailFolder, id: list[0].id };
        emailListFocusIndex = 0;
        renderEmailPanels();
        openEmailModal(list[0]);
      }
      emailAutoOpenFirst = false;
    }
    
    // Announce successful refresh
    const totalEmails = emailCache.inbox.length + emailCache.sent.length;
    announceToScreenReader(`Emails refreshed. ${totalEmails} total emails loaded.`);
    
    // Performance optimization: Periodic cache cleanup
    cleanupEmailCaches();
    
  } catch (err) {
    console.error('Failed to refresh emails tab:', err);
    if (statusEl) {
      statusEl.textContent = 'Refresh failed';
    }
    announceToScreenReader('Failed to refresh emails. Please try again.');
  }
}

function updateEmailFolderButtons() {
  updateFolderButtonStates();
  
  // Update folder title and count
  const folderTitle = document.getElementById('email-folder-title');
  const emailCount = document.getElementById('email-count');
  
  if (folderTitle) {
    folderTitle.textContent = emailFolder === 'inbox' ? 'Inbox' : 'Sent';
  }
  
  if (emailCount) {
    const currentList = emailCache[emailFolder] || [];
    const count = currentList.length;
    emailCount.textContent = count.toString();
    emailCount.setAttribute('aria-label', `${count} ${count === 1 ? 'email' : 'emails'}`);
  }
}

function renderEmailPanels() {
  updateEmailFolderButtons();
  let list = emailCache[emailFolder] || [];
  
  // Performance optimization: Use cached filtered results if available
  const cacheKey = `${emailFolder}_${emailSearchQuery}`;
  let filteredList = emailSortCache.get(cacheKey);
  
  if (!filteredList) {
    // Apply search filter if query exists
    if (emailSearchQuery.trim()) {
      filteredList = filterEmailsBySearch(list, emailSearchQuery);
    } else {
      filteredList = list;
    }
    
    // Cache the filtered and sorted result
    emailSortCache.set(cacheKey, filteredList);
  }
  
  renderEmailListPanel(filteredList);
  const sel = filteredList.find(m => m.id === emailSelected.id) || null;
  renderEmailDetail(sel);
}

// Performance optimization: Enhanced search with caching and indexing
function filterEmailsBySearch(emails, query) {
  if (!query.trim()) return emails;
  
  const searchTerms = query.toLowerCase().split(' ').filter(term => term.length > 0);
  
  // Performance optimization: Use cached search index if available
  const searchCacheKey = `search_${query}_${emails.length}`;
  let cachedResult = emailSortCache.get(searchCacheKey);
  
  if (cachedResult) {
    return cachedResult;
  }
  
  // Performance optimization: Pre-build search index for better performance on large lists
  const searchIndex = emails.map(email => ({
    email,
    searchText: [
      email.subject || '',
      email.sender || '',
      email.body || '',
      ...(email.to || []),
      ...(email.cc || [])
    ].join(' ').toLowerCase()
  }));
  
  const filteredEmails = searchIndex
    .filter(item => searchTerms.every(term => item.searchText.includes(term)))
    .map(item => item.email);
  
  // Cache the result for future use
  emailSortCache.set(searchCacheKey, filteredEmails);
  
  return filteredEmails;
}

// Debounced search handler with performance optimizations
function handleEmailSearch(query) {
  if (emailSearchTimeout) {
    clearTimeout(emailSearchTimeout);
  }
  
  // Performance optimization: Shorter debounce for better responsiveness
  const debounceTime = query.length > 3 ? 200 : 300;
  
  emailSearchTimeout = setTimeout(() => {
    emailSearchQuery = query;
    
    // Clear sort cache when search changes
    emailSortCache.clear();
    
    renderEmailPanels();
    
    // Announce search results to screen readers
    const currentList = emailCache[emailFolder] || [];
    const filteredList = query.trim() ? filterEmailsBySearch(currentList, query) : currentList;
    announceToScreenReader(`Search completed. ${filteredList.length} emails found.`);
  }, debounceTime);
}

// Performance optimization: Calculate optimal page size based on list size and performance
function getOptimalPageSize(totalItems) {
  if (totalItems < 200) return 50;
  if (totalItems < 500) return 75;
  if (totalItems < 1000) return 100;
  return 150; // For very large lists, use larger pages
}

// Performance monitoring utility
function measurePerformance(operation, fn) {
  const start = performance.now();
  const result = fn();
  const end = performance.now();
  
  if (end - start > 16) { // Log operations taking longer than one frame (16ms)
    console.log(`Performance: ${operation} took ${(end - start).toFixed(2)}ms`);
  }
  
  return result;
}

// Performance optimization: Extract email row creation for caching
function createEmailRow(msg, index, sortedItems) {
  const row = document.createElement('div');
  row.className = 'email-row';
  row.setAttribute('role', 'option');
  row.setAttribute('tabindex', '-1');
  row.setAttribute('data-email-id', msg.id);
  row.setAttribute('data-email-index', index);
  
  // Add ARIA attributes for accessibility
  const senderText = emailFolder === 'inbox' ? (msg.sender || 'Unknown') : (msg.to || []).join(', ') || 'Unknown';
  const subjectText = msg.subject || '(no subject)';
  const timeText = formatRelativeTime(msg.sent_at);
  const readStatus = msg.read ? 'read' : 'unread';
  
  row.setAttribute('aria-label', `Email from ${senderText}, subject: ${subjectText}, ${timeText}, ${readStatus}`);
  row.setAttribute('aria-selected', 'false');
  
  // Add unread state (assuming emails are unread by default unless marked otherwise)
  if (!msg.read) {
    row.classList.add('unread');
  }
  
  // Create main row structure
  const rowMain = document.createElement('div');
  rowMain.className = 'email-row-main';
  
  const rowContent = document.createElement('div');
  rowContent.className = 'email-row-content';
  
  // Sender/recipient information
  const sender = document.createElement('div');
  sender.className = 'email-sender';
  sender.textContent = senderText;
  sender.setAttribute('aria-hidden', 'true'); // Hidden from screen readers since it's in the row label
  
  // Subject
  const subject = document.createElement('div');
  subject.className = 'email-subject';
  subject.textContent = subjectText;
  subject.setAttribute('aria-hidden', 'true'); // Hidden from screen readers since it's in the row label
  
  // Timestamp with relative formatting
  const timestamp = document.createElement('div');
  timestamp.className = 'email-timestamp';
  timestamp.textContent = timeText;
  timestamp.setAttribute('aria-hidden', 'true'); // Hidden from screen readers since it's in the row label
  
  // Add title attribute for full timestamp on hover
  if (msg.sent_at) {
    const fullTime = new Date(msg.sent_at).toLocaleString();
    timestamp.title = `Sent: ${fullTime}`;
  }
  
  rowContent.appendChild(sender);
  rowContent.appendChild(subject);
  rowMain.appendChild(rowContent);
  rowMain.appendChild(timestamp);
  
  // Preview row
  const rowPreview = document.createElement('div');
  rowPreview.className = 'email-row-preview';
  
  // Email snippet/preview
  const snippet = document.createElement('div');
  snippet.className = 'email-snippet';
  const body = String(msg.body || '');
  snippet.textContent = body.length > 100 ? body.slice(0, 100) + '…' : body;
  snippet.setAttribute('aria-hidden', 'true'); // Hidden from screen readers to avoid redundancy
  
  // Thread count and metadata
  const metaContainer = document.createElement('div');
  metaContainer.className = 'email-meta';
  
  // Thread count indicator
  if (msg.thread_id) {
    // Count emails in the same thread (simplified - in real implementation this would come from API)
    const threadCount = sortedItems.filter(item => item.thread_id === msg.thread_id).length;
    if (threadCount > 1) {
      const threadIndicator = document.createElement('span');
      threadIndicator.className = 'thread-count';
      threadIndicator.textContent = threadCount.toString();
      threadIndicator.title = `${threadCount} messages in thread`;
      threadIndicator.setAttribute('aria-label', `Thread with ${threadCount} messages`);
      metaContainer.appendChild(threadIndicator);
    }
  }
  
  rowPreview.appendChild(snippet);
  rowPreview.appendChild(metaContainer);
  
  // Assemble the row
  row.appendChild(rowMain);
  row.appendChild(rowPreview);
  
  return row;
}

function renderEmailListPanel(items) {
  const listEl = document.getElementById('email-list');
  if (!listEl) return;
  
  // Performance optimization: Use DocumentFragment for batch DOM updates
  const fragment = document.createDocumentFragment();
  
  // Add ARIA attributes for accessibility
  listEl.setAttribute('role', 'listbox');
  listEl.setAttribute('aria-label', `${emailFolder === 'inbox' ? 'Inbox' : 'Sent'} emails`);
  
  if (!items || items.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'small';
    empty.style.padding = '12px';
    empty.textContent = 'No emails';
    empty.setAttribute('role', 'status');
    empty.setAttribute('aria-live', 'polite');
    listEl.innerHTML = '';
    listEl.appendChild(empty);
    renderEmailDetail(null);
    return;
  }
  
  // Performance optimization: Use cached sort if available
  const sortCacheKey = `sorted_${emailFolder}_${items.length}_${items[0]?.id || 0}`;
  let sortedItems = emailSortCache.get(sortCacheKey);
  
  if (!sortedItems) {
    // Sort emails by timestamp (newest first)
    sortedItems = [...items].sort((a, b) => {
      const timeA = new Date(a.sent_at || 0).getTime();
      const timeB = new Date(b.sent_at || 0).getTime();
      return timeB - timeA;
    });
    emailSortCache.set(sortCacheKey, sortedItems);
  }
  
  // Reset focus index if it's out of bounds
  if (emailListFocusIndex >= sortedItems.length) {
    emailListFocusIndex = sortedItems.length - 1;
  }
  
  // Performance optimization: Adaptive virtual scrolling based on performance
  const VIRTUAL_SCROLL_THRESHOLD = 100;
  const ITEMS_PER_PAGE = getOptimalPageSize(sortedItems.length);
  const shouldUseVirtualScrolling = sortedItems.length > VIRTUAL_SCROLL_THRESHOLD;
  
  let itemsToRender = sortedItems;
  if (shouldUseVirtualScrolling) {
    // Simple virtual scrolling - render only visible items plus buffer
    const startIndex = Math.max(0, emailListFocusIndex - ITEMS_PER_PAGE / 2);
    const endIndex = Math.min(sortedItems.length, startIndex + ITEMS_PER_PAGE);
    itemsToRender = sortedItems.slice(startIndex, endIndex);
    
    // Add virtual scroll indicators
    if (startIndex > 0) {
      const topIndicator = document.createElement('div');
      topIndicator.className = 'virtual-scroll-indicator';
      topIndicator.textContent = `... ${startIndex} more emails above`;
      fragment.appendChild(topIndicator);
    }
  }
  
  itemsToRender.forEach((msg, renderIndex) => {
    const index = shouldUseVirtualScrolling ? 
      sortedItems.findIndex(item => item.id === msg.id) : renderIndex;
    
    // Performance optimization: Check render cache first
    const renderCacheKey = `${msg.id}_${emailSelected.id === msg.id}_${emailFolder}`;
    let row = emailRenderCache.get(renderCacheKey);
    
    if (!row) {
      row = createEmailRow(msg, index, sortedItems);
      emailRenderCache.set(renderCacheKey, row.cloneNode(true));
    } else {
      // Use cached row but update dynamic attributes
      row = row.cloneNode(true);
      row.setAttribute('data-email-index', index);
    }
    
    // Update selection state for cached or new rows
    if (emailSelected.id === msg.id && emailSelected.box === emailFolder) {
      row.classList.add('selected');
      row.setAttribute('aria-selected', 'true');
      emailListFocusIndex = index;
    } else {
      row.classList.remove('selected');
      row.setAttribute('aria-selected', 'false');
    }
    
    // Event handlers (need to be re-attached for cached rows)
    row.addEventListener('click', () => {
      selectEmailByIndex(index);
    });
    
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        selectEmailByIndex(index);
      }
    });
    
    fragment.appendChild(row);
  });
  
  // Add bottom virtual scroll indicator if needed
  if (shouldUseVirtualScrolling && itemsToRender.length < sortedItems.length) {
    const remainingCount = sortedItems.length - (itemsToRender.length + (sortedItems.findIndex(item => item.id === itemsToRender[0].id)));
    if (remainingCount > 0) {
      const bottomIndicator = document.createElement('div');
      bottomIndicator.className = 'virtual-scroll-indicator';
      bottomIndicator.textContent = `... ${remainingCount} more emails below`;
      fragment.appendChild(bottomIndicator);
    }
  }
  
  // Performance optimization: Single DOM update with measurement
  measurePerformance('Email list DOM update', () => {
    listEl.innerHTML = '';
    listEl.appendChild(fragment);
  });
  
  // Set up keyboard navigation for the email list
  setupEmailListKeyboardNavigation(listEl, sortedItems);
}

// Helper function to format relative timestamps
function formatRelativeTime(timestamp) {
  if (!timestamp) return '';
  
  const now = new Date();
  const emailTime = new Date(timestamp);
  const diffMs = now.getTime() - emailTime.getTime();
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  
  if (diffMinutes < 1) {
    return 'Just now';
  } else if (diffMinutes < 60) {
    return `${diffMinutes} min ago`;
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  } else if (diffDays === 1) {
    return 'Yesterday';
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else {
    // For older emails, show the actual date
    return emailTime.toLocaleDateString();
  }
}

function formatAbsoluteTime(timestamp) {
  if (!timestamp) return '';

  const emailTime = new Date(timestamp);

  // Format: "Monday, October 22, 2025 at 2:30 PM"
  const dateOptions = {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  };

  const timeOptions = {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  };

  const datePart = emailTime.toLocaleDateString('en-US', dateOptions);
  const timePart = emailTime.toLocaleTimeString('en-US', timeOptions);

  return `${datePart} at ${timePart}`;
}

// Helper function to select email by index
function selectEmailByIndex(index) {
  const currentList = emailCache[emailFolder] || [];
  if (index >= 0 && index < currentList.length) {
    const sortedItems = [...currentList].sort((a, b) => {
      const timeA = new Date(a.sent_at || 0).getTime();
      const timeB = new Date(b.sent_at || 0).getTime();
      return timeB - timeA;
    });
    
    emailSelected = { box: emailFolder, id: sortedItems[index].id };
    emailListFocusIndex = index;
    renderEmailPanels();
    
    // Update focus for screen readers
    const emailRows = document.querySelectorAll('.email-row');
    emailRows.forEach((row, i) => {
      row.setAttribute('tabindex', i === index ? '0' : '-1');
      if (i === index) {
        row.focus();
      }
    });
  }
}

// Performance optimization: Throttled scroll handler for virtual scrolling
let scrollTimeout = null;
function handleEmailListScroll(listContainer, items) {
  if (scrollTimeout) return;
  
  scrollTimeout = setTimeout(() => {
    // Only re-render if we have a large list and virtual scrolling is active
    if (items.length > 100) {
      const scrollTop = listContainer.scrollTop;
      const containerHeight = listContainer.clientHeight;
      const itemHeight = 80; // Approximate email row height
      
      // Calculate which items should be visible
      const startIndex = Math.floor(scrollTop / itemHeight);
      const endIndex = Math.min(items.length, startIndex + Math.ceil(containerHeight / itemHeight) + 5);
      
      // Only re-render if the visible range has changed significantly
      if (Math.abs(startIndex - emailListFocusIndex) > 10) {
        renderEmailPanels();
      }
    }
    
    scrollTimeout = null;
  }, 100); // Throttle to 100ms
}

// Setup keyboard navigation for email list
function setupEmailListKeyboardNavigation(listEl, items) {
  // Remove any existing event listeners
  listEl.removeEventListener('keydown', handleEmailListKeydown);
  
  // Add keyboard navigation
  listEl.addEventListener('keydown', handleEmailListKeydown);
  
  // Performance optimization: Add throttled scroll handler for large lists
  const listContainer = listEl.closest('.email-list-container');
  if (listContainer && items.length > 100) {
    listContainer.removeEventListener('scroll', handleEmailListScroll);
    listContainer.addEventListener('scroll', () => handleEmailListScroll(listContainer, items), { passive: true });
  }
  
  // Set initial focus if we have a selected email
  if (emailListFocusIndex >= 0 && emailListFocusIndex < items.length) {
    const emailRows = listEl.querySelectorAll('.email-row');
    if (emailRows[emailListFocusIndex]) {
      emailRows[emailListFocusIndex].setAttribute('tabindex', '0');
    }
  } else if (items.length > 0) {
    // Set focus to first email if none selected
    emailListFocusIndex = 0;
    const firstRow = listEl.querySelector('.email-row');
    if (firstRow) {
      firstRow.setAttribute('tabindex', '0');
    }
  }
}

// Handle keyboard navigation in email list
function handleEmailListKeydown(e) {
  const currentList = emailCache[emailFolder] || [];
  if (currentList.length === 0) return;
  
  const emailRows = document.querySelectorAll('.email-row');
  const maxIndex = currentList.length - 1;
  
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault();
      if (emailListFocusIndex < maxIndex) {
        selectEmailByIndex(emailListFocusIndex + 1);
      }
      break;
      
    case 'ArrowUp':
      e.preventDefault();
      if (emailListFocusIndex > 0) {
        selectEmailByIndex(emailListFocusIndex - 1);
      }
      break;
      
    case 'Home':
      e.preventDefault();
      selectEmailByIndex(0);
      break;
      
    case 'End':
      e.preventDefault();
      selectEmailByIndex(maxIndex);
      break;
      
    case 'Enter':
    case ' ':
      e.preventDefault();
      if (emailListFocusIndex >= 0 && emailListFocusIndex <= maxIndex) {
        selectEmailByIndex(emailListFocusIndex);
      }
      break;
  }
}

function renderEmailDetail(msg) {
  const detailEl = document.getElementById('email-detail');
  if (!detailEl) return;
  detailEl.innerHTML = '';
  
  if (!msg) {
    const empty = document.createElement('div');
    empty.className = 'email-detail-placeholder';
    empty.innerHTML = `
      <div class="placeholder-icon" aria-hidden="true">✉️</div>
      <div class="placeholder-text">
        <h3 id="email-detail-heading">No email selected</h3>
        <p>Select an email from the list to view its contents</p>
      </div>
    `;
    detailEl.appendChild(empty);
    return;
  }
  
  // Create accessible email detail structure
  const detailHeader = document.createElement('div');
  detailHeader.className = 'email-detail-header';
  
  const subject = document.createElement('h3');
  subject.className = 'email-detail-subject';
  subject.id = 'email-detail-heading';
  subject.textContent = msg.subject || '(no subject)';
  
  const meta = document.createElement('div');
  meta.className = 'email-detail-meta';

  // Show both relative time and absolute timestamp
  const timestamp = document.createElement('span');
  timestamp.className = 'email-detail-timestamp';
  const relativeTime = formatRelativeTime(msg.sent_at);
  const absoluteTime = msg.sent_at ? formatAbsoluteTime(msg.sent_at) : '';
  timestamp.textContent = relativeTime;
  timestamp.title = absoluteTime; // Show full timestamp on hover

  const emailId = document.createElement('span');
  emailId.className = 'email-detail-id';
  emailId.textContent = `#${msg.id}`;
  emailId.title = 'Email ID';

  meta.appendChild(timestamp);
  meta.appendChild(emailId);
  detailHeader.appendChild(subject);
  detailHeader.appendChild(meta);
  detailEl.appendChild(detailHeader);

  // Add full timestamp row in addresses section
  const timestampRow = document.createElement('div');
  timestampRow.className = 'email-address-row';
  timestampRow.innerHTML = `
    <span class="email-address-label">Sent:</span>
    <span class="email-address-value">${absoluteTime || 'Unknown'}</span>
  `;
  detailEl.appendChild(timestampRow);

  // Email addresses section
  const addresses = document.createElement('div');
  addresses.className = 'email-detail-addresses';
  
  const from = document.createElement('div');
  from.className = 'email-address-row';
  from.innerHTML = `
    <span class="email-address-label">From:</span>
    <span class="email-address-value">${msg.sender || 'Unknown'}</span>
  `;
  addresses.appendChild(from);
  
  if (msg.to && msg.to.length) {
    const to = document.createElement('div');
    to.className = 'email-address-row';
    to.innerHTML = `
      <span class="email-address-label">To:</span>
      <span class="email-address-value">${msg.to.join(', ')}</span>
    `;
    addresses.appendChild(to);
  }
  
  if (msg.cc && msg.cc.length) {
    const cc = document.createElement('div');
    cc.className = 'email-address-row';
    cc.innerHTML = `
      <span class="email-address-label">CC:</span>
      <span class="email-address-value">${msg.cc.join(', ')}</span>
    `;
    addresses.appendChild(cc);
  }

  if (msg.bcc && msg.bcc.length) {
    const bcc = document.createElement('div');
    bcc.className = 'email-address-row';
    bcc.innerHTML = `
      <span class="email-address-label">BCC:</span>
      <span class="email-address-value">${msg.bcc.join(', ')}</span>
    `;
    addresses.appendChild(bcc);
  }

  if (msg.thread_id) {
    const thread = document.createElement('div');
    thread.className = 'email-address-row';
    thread.innerHTML = `
      <span class="email-address-label">Thread:</span>
      <span class="email-address-value">${msg.thread_id}</span>
    `;
    addresses.appendChild(thread);
  }
  
  detailEl.appendChild(addresses);

  // Email body section
  const bodyContainer = document.createElement('div');
  bodyContainer.className = 'email-detail-body';
  
  const bodyContent = document.createElement('pre');
  bodyContent.className = 'email-content';
  bodyContent.textContent = msg.body || '';
  bodyContent.setAttribute('aria-label', 'Email content');
  
  bodyContainer.appendChild(bodyContent);
  detailEl.appendChild(bodyContainer);
}

function openEmailModal(msg) {
  const modal = document.getElementById('email-modal');
  if (!modal) return;
  const titleEl = document.getElementById('email-modal-subject');
  const bodyEl = document.getElementById('email-modal-body');
  titleEl.textContent = msg.subject || '(no subject)';
  bodyEl.innerHTML = '';

  const headerMeta = document.createElement('div');
  headerMeta.className = 'meta';
  const formattedTime = msg.sent_at ? formatAbsoluteTime(msg.sent_at) : 'Unknown time';
  headerMeta.textContent = `#${msg.id} • ${formattedTime}`;
  bodyEl.appendChild(headerMeta);

  const from = document.createElement('div');
  from.className = 'address';
  from.textContent = `From: ${msg.sender || ''}`;
  bodyEl.appendChild(from);
  if (msg.to && msg.to.length) {
    const to = document.createElement('div');
    to.className = 'address';
    to.textContent = `To: ${msg.to.join(', ')}`;
    bodyEl.appendChild(to);
  }
  if (msg.cc && msg.cc.length) {
    const cc = document.createElement('div');
    cc.className = 'address';
    cc.textContent = `CC: ${msg.cc.join(', ')}`;
    bodyEl.appendChild(cc);
  }
  if (msg.thread_id) {
    const th = document.createElement('div');
    th.className = 'meta';
    th.textContent = `Thread: ${msg.thread_id}`;
    bodyEl.appendChild(th);
  }
  const pre = document.createElement('pre');
  pre.textContent = msg.body || '';
  bodyEl.appendChild(pre);

  modal.classList.add('show');
  modal.style.display = 'block';

  const closeBtn = document.getElementById('email-modal-close');
  const backdrop = modal.querySelector('.modal-backdrop');
  function close() { closeEmailModal(); }
  closeBtn.onclick = close;
  backdrop.onclick = close;
  document.addEventListener('keydown', escCloser);
  function escCloser(e) {
    if (e.key === 'Escape') {
      document.removeEventListener('keydown', escCloser);
      closeEmailModal();
    }
  }
}

function closeEmailModal() {
  const modal = document.getElementById('email-modal');
  if (!modal) return;
  modal.classList.remove('show');
  modal.style.display = 'none';
}

function renderChatList(containerId, items) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  if (!items || items.length === 0) {
    container.textContent = 'No messages.';
    return;
  }
  items.forEach(m => {
    const div = document.createElement('div');
    div.className = 'list-item';
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = `#${m.id} · ${m.sent_at || ''} · ${m.room_slug}`;
    div.appendChild(meta);
    const title = document.createElement('div');
    title.className = 'title';
    title.textContent = m.sender;
    div.appendChild(title);
    const pre = document.createElement('pre');
    pre.textContent = m.body || '';
    div.appendChild(pre);
    container.appendChild(div);
  });
}

// Chat client state management
let chatState = {
  selectedConversationSlug: null,
  selectedConversationType: null, // 'room' or 'dm'
  conversations: { rooms: [], dms: [] },
  currentMessages: [],
  isLoading: false,
  lastRefresh: null,
  searchQuery: '',
  messageSearchQuery: '',
  autoRefreshInterval: null,
  isNewConversationSelection: false,
  // Performance optimization state
  virtualScrolling: {
    enabled: false,
    itemHeight: 80, // Average message group height in pixels
    containerHeight: 0,
    scrollTop: 0,
    visibleStart: 0,
    visibleEnd: 0,
    totalItems: 0,
    renderBuffer: 5 // Extra items to render outside visible area
  },
  pagination: {
    enabled: false,
    pageSize: 50,
    currentPage: 0,
    totalPages: 0,
    hasMore: false
  },
  renderCache: new Map(), // Cache for rendered message elements
  performanceMetrics: {
    renderTimes: [],
    scrollEvents: 0,
    lastRenderTime: 0,
    averageRenderTime: 0
  }
};

// Performance monitoring functions
function startPerformanceTimer() {
  return performance.now();
}

function endPerformanceTimer(startTime, operation) {
  const endTime = performance.now();
  const duration = endTime - startTime;
  
  // Track performance metrics
  trackPerformanceMetric(operation, duration);
  
  return duration;
}

function trackPerformanceMetric(operation, duration) {
  // Ensure performance metrics object exists
  if (!chatState.performanceMetrics) {
    chatState.performanceMetrics = {
      renderTimes: [],
      averageRenderTime: 0,
      lastRenderTime: 0,
      scrollEvents: 0,
      cacheHits: 0,
      cacheMisses: 0
    };
  }
  
  // Track render times for performance analysis
  chatState.performanceMetrics.renderTimes.push({
    operation: operation,
    duration: duration,
    timestamp: Date.now()
  });
  
  // Keep only last 50 measurements to prevent memory bloat
  if (chatState.performanceMetrics.renderTimes.length > 50) {
    chatState.performanceMetrics.renderTimes.shift();
  }
  
  // Update average render time
  const recentTimes = chatState.performanceMetrics.renderTimes.slice(-10);
  chatState.performanceMetrics.averageRenderTime = 
    recentTimes.reduce((sum, metric) => sum + metric.duration, 0) / recentTimes.length;
  
  chatState.performanceMetrics.lastRenderTime = duration;
  
  // Log slow operations for debugging
  if (duration > 100) {
    console.warn(`Slow chat operation detected: ${operation} took ${duration.toFixed(2)}ms`);
  }
  
  return duration;
}

function showPerformanceWarning(duration, messageCount) {
  const warningEl = document.createElement('div');
  warningEl.className = 'performance-warning';
  warningEl.innerHTML = `
    <span class="warning-icon">⚠️</span>
    <span class="warning-text">Slow rendering: ${duration.toFixed(0)}ms for ${messageCount} messages</span>
    <button class="warning-close" onclick="this.parentElement.remove()">×</button>
  `;
  warningEl.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: rgba(245, 158, 11, 0.95);
    color: white;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    z-index: 1000;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    display: flex;
    align-items: center;
    gap: 8px;
  `;
  
  document.body.appendChild(warningEl);
  
  // Auto-remove after 5 seconds
  setTimeout(() => {
    if (warningEl.parentNode) {
      warningEl.parentNode.removeChild(warningEl);
    }
  }, 5000);
}

function showPerformanceIndicator(duration, operation) {
  const indicator = document.createElement('div');
  indicator.className = 'performance-indicator';
  
  let color = '#22c55e'; // Green for fast
  if (duration > 100) color = '#f59e0b'; // Yellow for slow
  if (duration > 200) color = '#ef4444'; // Red for very slow
  
  indicator.innerHTML = `
    <span class="indicator-icon">⚡</span>
    <span class="indicator-text">${operation}: ${duration.toFixed(0)}ms</span>
  `;
  indicator.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: ${color};
    color: white;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    z-index: 1000;
    opacity: 0.8;
    pointer-events: none;
  `;
  
  document.body.appendChild(indicator);
  
  // Fade out and remove
  setTimeout(() => {
    indicator.style.transition = 'opacity 0.5s';
    indicator.style.opacity = '0';
    setTimeout(() => {
      if (indicator.parentNode) {
        indicator.parentNode.removeChild(indicator);
      }
    }, 500);
  }, 2000);
}

function logPerformanceMetrics() {
  const metrics = chatState.performanceMetrics;
  console.group('Chat Performance Metrics');
  console.log(`Average render time: ${metrics.averageRenderTime.toFixed(2)}ms`);
  console.log(`Last render time: ${metrics.lastRenderTime.toFixed(2)}ms`);
  console.log(`Scroll events: ${metrics.scrollEvents}`);
  console.log(`Cache hits: ${metrics.cacheHits || 0}`);
  console.log(`Cache misses: ${metrics.cacheMisses || 0}`);
  const totalCacheAccess = (metrics.cacheHits || 0) + (metrics.cacheMisses || 0);
  if (totalCacheAccess > 0) {
    console.log(`Cache hit ratio: ${(((metrics.cacheHits || 0) / totalCacheAccess) * 100).toFixed(1)}%`);
  }
  console.log(`Render cache size: ${chatState.renderCache.size}`);
  console.log(`Virtual scrolling enabled: ${chatState.virtualScrolling.enabled}`);
  console.log(`Pagination enabled: ${chatState.pagination.enabled}`);
  
  // Show recent render times
  const recentTimes = metrics.renderTimes.slice(-10);
  console.log('Recent render times:', recentTimes.map(t => `${t.operation}: ${t.duration.toFixed(1)}ms`));
  console.groupEnd();
}

function shouldEnableVirtualScrolling() {
  // Enable virtual scrolling for conversations with many messages
  const messageCount = chatState.currentMessages.length;
  const averageRenderTime = chatState.performanceMetrics.averageRenderTime;
  
  // Enable if we have more than 100 messages OR if rendering is slow
  return messageCount > 100 || (messageCount > 50 && averageRenderTime > 50);
}

function shouldEnablePagination() {
  // Enable pagination for very large conversations
  const messageCount = chatState.currentMessages.length;
  return messageCount > 500; // Increased threshold for pagination
}

function optimizeRenderingPerformance() {
  // Performance optimization strategies
  const messageCount = chatState.currentMessages.length;
  const averageRenderTime = chatState.performanceMetrics.averageRenderTime;
  
  // Clear render cache if it's getting too large
  if (chatState.renderCache.size > 1000) {
    const entries = Array.from(chatState.renderCache.entries());
    // Keep only the most recent 500 entries
    const recentEntries = entries.slice(-500);
    chatState.renderCache.clear();
    recentEntries.forEach(([key, value]) => {
      chatState.renderCache.set(key, value);
    });
    console.log('Render cache optimized: cleared old entries');
  }
  
  // Adjust virtual scrolling parameters based on performance
  if (averageRenderTime > 100) {
    chatState.virtualScrolling.renderBuffer = Math.max(5, chatState.virtualScrolling.renderBuffer - 2);
    chatState.virtualScrolling.itemHeight = Math.max(60, chatState.virtualScrolling.itemHeight - 10);
  } else if (averageRenderTime < 30) {
    chatState.virtualScrolling.renderBuffer = Math.min(15, chatState.virtualScrolling.renderBuffer + 1);
    chatState.virtualScrolling.itemHeight = Math.min(120, chatState.virtualScrolling.itemHeight + 5);
  }
  
  // Log performance metrics for monitoring
  if (messageCount > 50) {
    console.log(`Chat Performance: ${messageCount} messages, ${averageRenderTime.toFixed(2)}ms avg render time`);
  }
}

// State persistence functions
function saveChatState() {
  try {
    const stateToSave = {
      selectedConversationSlug: chatState.selectedConversationSlug,
      selectedConversationType: chatState.selectedConversationType,
      personId: chatMonitorPersonId
    };
    localStorage.setItem('vdos_chat_state', JSON.stringify(stateToSave));
  } catch (err) {
    console.warn('Failed to save chat state:', err);
  }
}

function loadChatState() {
  try {
    const saved = localStorage.getItem('vdos_chat_state');
    if (saved) {
      const state = JSON.parse(saved);
      // Only restore state if it's for the same persona
      if (state.personId === chatMonitorPersonId) {
        chatState.selectedConversationSlug = state.selectedConversationSlug;
        chatState.selectedConversationType = state.selectedConversationType;
        return true;
      }
    }
  } catch (err) {
    console.warn('Failed to load chat state:', err);
  }
  return false;
}

// Chat search functionality
async function filterConversationsBySearch(conversations, searchQuery) {
  if (!searchQuery || !searchQuery.trim()) {
    return conversations;
  }
  
  const query = searchQuery.toLowerCase().trim();
  const searchTerms = query.split(' ').filter(term => term.length > 0);
  
  // Enhanced filtering with cross-conversation message content search
  const filteredConversations = [];
  
  for (const conversation of conversations) {
    let matchFound = false;
    let matchContext = '';
    
    // Search in conversation name
    if (conversation.name && searchTerms.some(term => 
        conversation.name.toLowerCase().includes(term))) {
      matchFound = true;
      matchContext = 'name';
    }
    
    // Search in participants for rooms
    if (!matchFound && conversation.participants && Array.isArray(conversation.participants)) {
      const participantMatch = conversation.participants.some(participant => 
        participant && searchTerms.some(term => 
          participant.toLowerCase().includes(term))
      );
      if (participantMatch) {
        matchFound = true;
        matchContext = 'participant';
      }
    }
    
    // Search in last message content and sender
    if (!matchFound && conversation.lastMessage) {
      const lastMsgBody = conversation.lastMessage.body || '';
      const lastMsgSender = conversation.lastMessage.sender || '';
      
      if (searchTerms.some(term => 
          lastMsgBody.toLowerCase().includes(term) || 
          lastMsgSender.toLowerCase().includes(term))) {
        matchFound = true;
        matchContext = 'recent_message';
      }
    }
    
    // Enhanced: Search in all messages for this conversation (cross-conversation search)
    if (!matchFound && chatMonitorPersonId) {
      try {
        // Fetch all messages for this conversation to search content
        const messages = await fetchConversationMessages(conversation.room_slug || conversation.slug);
        if (messages && messages.length > 0) {
          const messageMatch = messages.some(message => {
            const messageBody = (message.body || message.content || '').toLowerCase();
            const messageSender = (message.sender || '').toLowerCase();
            return searchTerms.some(term => 
              messageBody.includes(term) || messageSender.includes(term)
            );
          });
          
          if (messageMatch) {
            matchFound = true;
            matchContext = 'message_content';
          }
        }
      } catch (err) {
        // If we can't fetch messages, continue with other search criteria
        console.warn('Could not search messages for conversation:', conversation.name, err);
      }
    }
    
    if (matchFound) {
      // Add match context for better search result display
      const enhancedConversation = { 
        ...conversation, 
        searchMatchContext: matchContext,
        searchQuery: query
      };
      filteredConversations.push(enhancedConversation);
    }
  }
  
  return filteredConversations;
}

// Helper function to fetch messages for cross-conversation search
async function fetchConversationMessages(conversationSlug) {
  if (!chatMonitorPersonId || !conversationSlug) return [];
  
  try {
    const person = people_cache.find(p => p.id === chatMonitorPersonId);
    if (!person) return [];
    
    const response = await fetch(`http://127.0.0.1:8001/rooms/${conversationSlug}/messages`);
    if (!response.ok) return [];
    
    return await response.json();
  } catch (err) {
    console.warn('Error fetching conversation messages:', err);
    return [];
  }
}

function highlightSearchMatches(text, searchQuery) {
  if (!searchQuery || !searchQuery.trim() || !text) {
    return text;
  }
  
  const query = searchQuery.trim();
  const searchTerms = query.split(' ').filter(term => term.length > 0);
  
  let highlightedText = text;
  
  // Highlight each search term
  searchTerms.forEach(term => {
    const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    highlightedText = highlightedText.replace(regex, '<mark class="search-highlight">$1</mark>');
  });
  
  return highlightedText;
}

// Enhanced function to show search context in conversation items
function addSearchContextToConversation(conversationElement, conversation) {
  if (!conversation.searchMatchContext || !conversation.searchQuery) return;
  
  // Add search context indicator
  const contextIndicator = document.createElement('div');
  contextIndicator.className = 'search-context-indicator';
  
  let contextText = '';
  switch (conversation.searchMatchContext) {
    case 'name':
      contextText = 'Match in conversation name';
      break;
    case 'participant':
      contextText = 'Match in participant name';
      break;
    case 'recent_message':
      contextText = 'Match in recent message';
      break;
    case 'message_content':
      contextText = 'Match in message history';
      break;
    default:
      contextText = 'Search match found';
  }
  
  contextIndicator.innerHTML = `
    <span class="context-icon" aria-hidden="true">🔍</span>
    <span class="context-text">${contextText}</span>
  `;
  
  // Insert context indicator after conversation info
  const conversationInfo = conversationElement.querySelector('.conversation-info');
  if (conversationInfo) {
    conversationInfo.appendChild(contextIndicator);
  }
}

function highlightMessageSearchMatches(text, searchQuery) {
  if (!searchQuery || !searchQuery.trim() || !text) {
    return text;
  }
  
  const query = searchQuery.trim();
  const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  return text.replace(regex, '<mark class="message-search-highlight">$1</mark>');
}

// Message search state
let messageSearchResults = [];
let currentSearchResultIndex = -1;

function performMessageSearch(query) {
  // Clear previous search results
  clearMessageSearchHighlights();
  messageSearchResults = [];
  currentSearchResultIndex = -1;
  
  if (!query || !query.trim()) {
    renderMessageThread();
    return;
  }
  
  const searchTerm = query.toLowerCase().trim();
  
  // Find all messages that match the search query
  chatState.currentMessages.forEach((message, messageIndex) => {
    const messageBody = (message.body || message.content || '').toLowerCase();
    if (messageBody.includes(searchTerm)) {
      messageSearchResults.push({
        messageIndex,
        message,
        matchText: message.body || message.content || ''
      });
    }
  });
  
  // Re-render messages with search highlighting
  renderMessageThread();
  
  // Show search results count
  updateMessageSearchStatus();
  
  // Navigate to first result if any found
  if (messageSearchResults.length > 0) {
    currentSearchResultIndex = 0;
    scrollToSearchResult(currentSearchResultIndex);
  }
}

function clearMessageSearch() {
  const messageSearchInput = document.getElementById('message-search');
  const searchControls = document.getElementById('message-search-controls');
  
  if (messageSearchInput) {
    messageSearchInput.value = '';
  }
  
  if (searchControls) {
    searchControls.style.display = 'none';
  }
  
  chatState.messageSearchQuery = '';
  clearMessageSearchHighlights();
  messageSearchResults = [];
  currentSearchResultIndex = -1;
  renderMessageThread();
  updateMessageSearchStatus();
}

function clearMessageSearchHighlights() {
  const highlights = document.querySelectorAll('.message-search-highlight');
  highlights.forEach(highlight => {
    const parent = highlight.parentNode;
    parent.replaceChild(document.createTextNode(highlight.textContent), highlight);
    parent.normalize();
  });
}

function navigateToSearchResult(direction) {
  if (messageSearchResults.length === 0) return;
  
  if (direction === 'next') {
    currentSearchResultIndex = (currentSearchResultIndex + 1) % messageSearchResults.length;
  } else if (direction === 'previous') {
    currentSearchResultIndex = currentSearchResultIndex <= 0 
      ? messageSearchResults.length - 1 
      : currentSearchResultIndex - 1;
  }
  
  scrollToSearchResult(currentSearchResultIndex);
  updateMessageSearchStatus();
}

function scrollToSearchResult(resultIndex) {
  if (resultIndex < 0 || resultIndex >= messageSearchResults.length) return;
  
  const result = messageSearchResults[resultIndex];
  const messageGroups = document.querySelectorAll('.message-group');
  
  // Find the message group containing this message
  let targetGroup = null;
  let messageIndexInThread = 0;
  
  for (const group of messageGroups) {
    const messagesInGroup = group.querySelectorAll('.message-bubble');
    for (const bubble of messagesInGroup) {
      if (messageIndexInThread === result.messageIndex) {
        targetGroup = group;
        break;
      }
      messageIndexInThread++;
    }
    if (targetGroup) break;
  }
  
  if (targetGroup) {
    // Remove previous active search result highlighting
    document.querySelectorAll('.active-search-result').forEach(el => {
      el.classList.remove('active-search-result');
    });
    
    // Add active highlighting to current result
    targetGroup.classList.add('active-search-result');
    
    // Scroll to the message
    targetGroup.scrollIntoView({ 
      behavior: 'smooth', 
      block: 'center' 
    });
    
    // Announce to screen readers
    announceToScreenReader(`Search result ${resultIndex + 1} of ${messageSearchResults.length}`);
  }
}

function updateMessageSearchStatus() {
  const messageThread = document.getElementById('message-thread');
  const searchResultsCount = document.getElementById('search-results-count');
  const searchPrevBtn = document.getElementById('search-prev-btn');
  const searchNextBtn = document.getElementById('search-next-btn');
  const searchControls = document.getElementById('message-search-controls');
  
  if (messageThread) {
    if (messageSearchResults.length > 0) {
      messageThread.setAttribute('data-search-results', messageSearchResults.length);
      messageThread.setAttribute('data-current-result', currentSearchResultIndex + 1);
    } else {
      messageThread.removeAttribute('data-search-results');
      messageThread.removeAttribute('data-current-result');
    }
  }
  
  // Update search results count display
  if (searchResultsCount) {
    if (messageSearchResults.length > 0) {
      searchResultsCount.textContent = `${currentSearchResultIndex + 1} of ${messageSearchResults.length}`;
    } else if (chatState.messageSearchQuery && chatState.messageSearchQuery.trim()) {
      searchResultsCount.textContent = 'No results';
    } else {
      searchResultsCount.textContent = '';
    }
  }
  
  // Update navigation button states
  if (searchPrevBtn && searchNextBtn) {
    const hasResults = messageSearchResults.length > 0;
    searchPrevBtn.disabled = !hasResults;
    searchNextBtn.disabled = !hasResults;
  }
  
  // Hide search controls if no query
  if (searchControls && (!chatState.messageSearchQuery || !chatState.messageSearchQuery.trim())) {
    searchControls.style.display = 'none';
  }
}

function setupChatSearchHandlers() {
  const searchInput = document.getElementById('chat-search');
  const clearButton = document.getElementById('chat-search-clear');
  
  if (!searchInput || !clearButton) return;
  
  // Check if handlers are already set up to avoid duplicates
  if (searchInput.hasAttribute('data-handlers-setup')) return;
  searchInput.setAttribute('data-handlers-setup', 'true');
  
  let searchTimeout = null;
  
  // Handle search input with debouncing and enhanced animations
  searchInput.addEventListener('input', (e) => {
    const query = e.target.value;
    
    // Enhanced clear button animation
    if (query.trim()) {
      clearButton.classList.add('visible');
      searchInput.classList.add('has-content');
    } else {
      clearButton.classList.remove('visible');
      searchInput.classList.remove('has-content');
    }
    
    // Debounce search to avoid excessive filtering
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(async () => {
      chatState.searchQuery = query;
      
      // Add loading state to search input
      searchInput.classList.add('searching');
      
      try {
        await renderConversationSidebar();
        
        // Update search input state based on results
        const hasResults = [...chatState.conversations.rooms, ...chatState.conversations.dms].length > 0;
        if (query.trim()) {
          if (hasResults) {
            searchInput.classList.add('has-results');
            searchInput.classList.remove('no-results');
          } else {
            searchInput.classList.add('no-results');
            searchInput.classList.remove('has-results');
          }
        } else {
          searchInput.classList.remove('has-results', 'no-results');
        }
      } finally {
        searchInput.classList.remove('searching');
      }
    }, 300);
  });
  
  // Enhanced clear button with animation
  clearButton.addEventListener('click', async () => {
    // Add click animation
    clearButton.style.transform = 'scale(0.8)';
    setTimeout(() => {
      clearButton.style.transform = '';
    }, 150);
    
    searchInput.value = '';
    clearButton.classList.remove('visible');
    searchInput.classList.remove('has-content', 'has-results', 'no-results');
    chatState.searchQuery = '';
    await renderConversationSidebar();
    searchInput.focus();
  });
  
  // Setup message search handlers
  setupMessageSearchHandlers();
}

function setupMessageSearchHandlers() {
  const messageSearchInput = document.getElementById('message-search');
  const searchControls = document.getElementById('message-search-controls');
  const searchPrevBtn = document.getElementById('search-prev-btn');
  const searchNextBtn = document.getElementById('search-next-btn');
  const searchClearBtn = document.getElementById('search-clear-btn');
  
  if (!messageSearchInput) return;
  
  // Check if handlers are already set up to avoid duplicates
  if (messageSearchInput.hasAttribute('data-handlers-setup')) return;
  messageSearchInput.setAttribute('data-handlers-setup', 'true');
  
  let messageSearchTimeout = null;
  
  // Handle message search input with debouncing
  messageSearchInput.addEventListener('input', (e) => {
    const query = e.target.value;
    
    // Show/hide search controls
    if (searchControls) {
      searchControls.style.display = query.trim() ? 'flex' : 'none';
    }
    
    // Debounce search to avoid excessive processing
    clearTimeout(messageSearchTimeout);
    messageSearchTimeout = setTimeout(() => {
      chatState.messageSearchQuery = query;
      performMessageSearch(query);
    }, 300);
  });
  
  // Handle keyboard shortcuts for message search
  messageSearchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      clearMessageSearch();
      messageSearchInput.blur();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (e.shiftKey) {
        // Shift+Enter: Navigate to previous result
        navigateToSearchResult('previous');
      } else {
        // Enter: Navigate to next result
        navigateToSearchResult('next');
      }
    } else if (e.key === 'F3') {
      e.preventDefault();
      if (e.shiftKey) {
        navigateToSearchResult('previous');
      } else {
        navigateToSearchResult('next');
      }
    }
  });
  
  // Handle navigation button clicks
  if (searchPrevBtn) {
    searchPrevBtn.addEventListener('click', () => {
      navigateToSearchResult('previous');
    });
  }
  
  if (searchNextBtn) {
    searchNextBtn.addEventListener('click', () => {
      navigateToSearchResult('next');
    });
  }
  
  if (searchClearBtn) {
    searchClearBtn.addEventListener('click', () => {
      clearMessageSearch();
      messageSearchInput.focus();
    });
  }
  
  // Handle keyboard shortcuts
  searchInput.addEventListener('keydown', async (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      searchInput.value = '';
      clearButton.style.display = 'none';
      chatState.searchQuery = '';
      await renderConversationSidebar();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      // Focus first conversation result if available
      const firstConversation = document.querySelector('.conversation-item');
      if (firstConversation) {
        firstConversation.focus();
      }
    }
  });
}

// Missing helper functions for chat functionality
function renderChatPlaceholder() {
  const sidebar = document.getElementById('chat-rooms-list');
  const dmsList = document.getElementById('chat-dms-list');
  const messageThread = document.getElementById('message-thread');
  
  if (sidebar) {
    sidebar.innerHTML = '<div class="conversation-empty"><div class="empty-text">Select a persona to view conversations</div></div>';
  }
  if (dmsList) {
    dmsList.innerHTML = '<div class="conversation-empty"><div class="empty-text">Select a persona to view conversations</div></div>';
  }
  if (messageThread) {
    messageThread.innerHTML = `
      <div class="message-thread-placeholder">
        <div class="placeholder-icon" aria-hidden="true">💬</div>
        <div class="placeholder-text">
          <h4>No persona selected</h4>
          <p>Select a persona from the dropdown to view their conversations</p>
        </div>
      </div>
    `;
  }
  
  // Update counts
  const roomsCount = document.getElementById('rooms-count');
  const dmsCount = document.getElementById('dms-count');
  if (roomsCount) roomsCount.textContent = '(0)';
  if (dmsCount) dmsCount.textContent = '(0)';
}

function updateChatLoadingState(isLoading) {
  const chatBody = document.querySelector('.chat-client-body');
  if (chatBody) {
    if (isLoading) {
      chatBody.classList.add('chat-loading');
    } else {
      chatBody.classList.remove('chat-loading');
    }
  }
}

function renderChatError(message) {
  const sidebar = document.getElementById('chat-rooms-list');
  const dmsList = document.getElementById('chat-dms-list');
  const messageThread = document.getElementById('message-thread');
  
  const errorHtml = `
    <div class="conversation-empty">
      <div class="empty-icon" style="color: #dc2626;">⚠️</div>
      <div class="empty-text" style="color: #dc2626;">Error</div>
      <div class="empty-hint">${message}</div>
    </div>
  `;
  
  if (sidebar) sidebar.innerHTML = errorHtml;
  if (dmsList) dmsList.innerHTML = errorHtml;
  if (messageThread) {
    messageThread.innerHTML = `
      <div class="message-thread-placeholder">
        <div class="placeholder-icon" aria-hidden="true" style="color: #dc2626;">⚠️</div>
        <div class="placeholder-text">
          <h4 style="color: #dc2626;">Error loading conversations</h4>
          <p>${message}</p>
        </div>
      </div>
    `;
  }
}

function setupChatAutoRefresh() {
  // Clear existing auto-refresh if any
  if (chatState.autoRefreshInterval) {
    clearInterval(chatState.autoRefreshInterval);
    chatState.autoRefreshInterval = null;
  }
  
  // Set up auto-refresh if simulation is running and auto-refresh is enabled
  if (isSimulationRunning && autoRefreshEnabled) {
    chatState.autoRefreshInterval = setInterval(async () => {
      // Only refresh if chat tab is visible and not currently loading
      if (chatMonitorPersonId && 
          document.getElementById('tab-chat').style.display !== 'none' && 
          !chatState.isLoading) {
        
        try {
          // Update status to show auto-refresh is happening
          const statusEl = document.getElementById('chat-last-refresh');
          if (statusEl) {
            statusEl.textContent = 'Auto-refreshing...';
          }
          
          // Store current message count for comparison
          const previousMessageCount = chatState.currentMessages ? chatState.currentMessages.length : 0;
          
          // Refresh conversation list and selected conversation
          await refreshChatConversations();
          
          // If we have a selected conversation, refresh its messages
          if (chatState.selectedConversationSlug) {
            await refreshSelectedConversation();
          }
          
          // The scroll handling is now done in renderMessageThread()
          // which will automatically detect new messages and handle scroll appropriately
          
          // Update status indicator
          if (statusEl) {
            statusEl.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
          }
          
        } catch (err) {
          console.error('Auto-refresh failed:', err);
          const statusEl = document.getElementById('chat-last-refresh');
          if (statusEl) {
            statusEl.textContent = 'Auto-refresh failed';
          }
        }
      }
    }, 3000); // Refresh every 3 seconds
  }
}

function renderMessageViewPlaceholder() {
  const messageThread = document.getElementById('message-thread');
  const conversationTitle = document.querySelector('.conversation-name');
  const conversationMeta = document.querySelector('.conversation-meta');
  
  if (messageThread) {
    messageThread.innerHTML = `
      <div class="message-thread-placeholder">
        <div class="placeholder-icon" aria-hidden="true">💬</div>
        <div class="placeholder-text">
          <h4>No conversation selected</h4>
          <p>Select a conversation from the sidebar to view messages</p>
        </div>
      </div>
    `;
  }
  
  if (conversationTitle) {
    conversationTitle.textContent = 'Select a conversation';
  }
  
  if (conversationMeta) {
    conversationMeta.innerHTML = '';
  }
}

async function selectConversation(conversation) {
  // Update selection state
  chatState.selectedConversationSlug = conversation.slug;
  chatState.selectedConversationType = conversation.type;
  
  // Save state for persistence across refreshes
  saveChatState();
  
  // Enhanced UI selection with animations
  document.querySelectorAll('.conversation-item').forEach(item => {
    item.classList.remove('selected', 'selecting');
  });
  
  const selectedItem = document.querySelector(`[data-conversation-slug="${conversation.slug}"]`);
  if (selectedItem) {
    // Add selecting animation class
    selectedItem.classList.add('selecting');
    
    // Add selected class after a brief delay for animation
    setTimeout(() => {
      selectedItem.classList.add('selected');
      selectedItem.classList.remove('selecting');
    }, 200);
    
    // Smooth scroll to selected item if not visible
    selectedItem.scrollIntoView({ 
      behavior: 'smooth', 
      block: 'nearest',
      inline: 'nearest'
    });
  }
  
  // Load conversation messages with enhanced transitions
  await loadConversationMessages(conversation);
}

async function loadConversationMessages(conversation) {
  const messageThread = document.getElementById('message-thread');
  const conversationTitle = document.querySelector('.conversation-name');
  const conversationMeta = document.querySelector('.conversation-meta .participant-list');
  const messageCount = document.querySelector('.conversation-meta .message-count');
  
  if (!messageThread) return;
  
  try {
    // Update header
    if (conversationTitle) {
      conversationTitle.textContent = conversation.type === 'room' ? `#${conversation.name}` : conversation.name;
    }
    
    if (conversationMeta) {
      if (conversation.type === 'room') {
        conversationMeta.textContent = `${conversation.participantCount} members`;
      } else {
        const otherParticipant = conversation.participants?.find(p => p !== getCurrentPersonaHandle());
        conversationMeta.textContent = otherParticipant ? `with ${otherParticipant}` : 'Direct message';
      }
    }
    
    if (messageCount) {
      messageCount.textContent = `${conversation.messageCount} messages`;
    }
    
    // Show loading state
    messageThread.innerHTML = `
      <div class="message-thread-placeholder">
        <div class="placeholder-icon" aria-hidden="true">⏳</div>
        <div class="placeholder-text">
          <h4>Loading messages...</h4>
          <p>Please wait while we fetch the conversation history</p>
        </div>
      </div>
    `;
    
    // Fetch messages for this conversation
    let messages = [];
    if (conversation.type === 'room') {
      // Fetch room messages
      const response = await fetch(`http://127.0.0.1:8001/rooms/${encodeURIComponent(conversation.slug)}/messages`);
      if (response.ok) {
        messages = await response.json();
      }
    } else {
      // For DMs, we already have the messages from the conversation object
      messages = conversation.messages || [];
    }
    
    // Sort messages chronologically
    messages.sort((a, b) => new Date(a.sent_at) - new Date(b.sent_at));
    
    // Store messages in state
    chatState.currentMessages = messages;
    
    // Render messages (uses chatState.currentMessages)
    renderMessageThread();
    
  } catch (err) {
    console.error('Failed to load conversation messages:', err);
    messageThread.innerHTML = `
      <div class="message-thread-placeholder">
        <div class="placeholder-icon" aria-hidden="true" style="color: #dc2626;">⚠️</div>
        <div class="placeholder-text">
          <h4 style="color: #dc2626;">Failed to load messages</h4>
          <p>There was an error loading the conversation. Please try again.</p>
        </div>
      </div>
    `;
  }
}

function renderMessageThread(messages) {
  const messageThread = document.getElementById('message-thread');
  if (!messageThread) return;
  
  if (!messages || messages.length === 0) {
    messageThread.innerHTML = `
      <div class="message-thread-placeholder">
        <div class="placeholder-icon" aria-hidden="true">💬</div>
        <div class="placeholder-text">
          <h4>No messages yet</h4>
          <p>This conversation doesn't have any messages yet</p>
        </div>
      </div>
    `;
    return;
  }
  
  messageThread.innerHTML = '';
  
  // Group messages by sender and time proximity
  const messageGroups = [];
  let currentGroup = null;
  
  messages.forEach(message => {
    const messageTime = new Date(message.sent_at);
    const shouldStartNewGroup = !currentGroup || 
      currentGroup.sender !== message.sender ||
      (messageTime - new Date(currentGroup.lastMessageTime)) > 5 * 60 * 1000; // 5 minutes
    
    if (shouldStartNewGroup) {
      currentGroup = {
        sender: message.sender,
        messages: [message],
        firstMessageTime: message.sent_at,
        lastMessageTime: message.sent_at
      };
      messageGroups.push(currentGroup);
    } else {
      currentGroup.messages.push(message);
      currentGroup.lastMessageTime = message.sent_at;
    }
  });
  
  // Render message groups
  messageGroups.forEach(group => {
    const groupElement = createMessageGroup(group);
    messageThread.appendChild(groupElement);
  });
  
  // Scroll to bottom
  messageThread.scrollTop = messageThread.scrollHeight;
}

function createMessageGroup(group) {
  const groupDiv = document.createElement('div');
  groupDiv.className = 'message-group';
  groupDiv.setAttribute('data-sender', group.sender);
  
  // Group header
  const header = document.createElement('div');
  header.className = 'message-group-header';
  
  const senderName = document.createElement('span');
  senderName.className = 'sender-name';
  senderName.textContent = group.sender;
  
  const timestamp = document.createElement('span');
  timestamp.className = 'message-timestamp';
  timestamp.textContent = formatRelativeTime(group.firstMessageTime);
  timestamp.setAttribute('title', new Date(group.firstMessageTime).toLocaleString());
  
  header.appendChild(senderName);
  header.appendChild(timestamp);
  groupDiv.appendChild(header);
  
  // Message bubbles
  group.messages.forEach(message => {
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = message.body || '';
    bubble.appendChild(content);
    
    // Message metadata
    if (message.id || message.sent_at) {
      const meta = document.createElement('div');
      meta.className = 'message-meta';
      
      if (message.id) {
        const messageId = document.createElement('span');
        messageId.className = 'message-id';
        messageId.textContent = `#${message.id}`;
        meta.appendChild(messageId);
      }
      
      if (message.sent_at !== group.firstMessageTime) {
        const messageTime = document.createElement('span');
        messageTime.className = 'message-tick';
        messageTime.textContent = new Date(message.sent_at).toLocaleTimeString();
        meta.appendChild(messageTime);
      }
      
      if (meta.children.length > 0) {
        bubble.appendChild(meta);
      }
    }
    
    groupDiv.appendChild(bubble);
  });
  
  return groupDiv;
}

function formatRelativeTime(dateString) {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  
  return date.toLocaleDateString();
}

// Auto-scroll helper functions
function isScrolledToBottom(element, threshold = 10) {
  if (!element) return true;
  return element.scrollTop + element.clientHeight >= element.scrollHeight - threshold;
}

function scrollToBottom(element, smooth = false) {
  if (!element) return;
  
  if (smooth) {
    element.scrollTo({
      top: element.scrollHeight,
      behavior: 'smooth'
    });
  } else {
    element.scrollTop = element.scrollHeight;
  }
}

function showNewMessageIndicator(messageCount = 1) {
  // Remove existing indicator if present
  hideNewMessageIndicator();
  
  const threadEl = document.getElementById('message-thread');
  if (!threadEl) return;
  
  const indicator = document.createElement('div');
  indicator.id = 'new-message-indicator';
  indicator.className = 'new-message-indicator';
  indicator.innerHTML = `
    <span>↓ ${messageCount} new message${messageCount > 1 ? 's' : ''}</span>
  `;
  
  // Position indicator at bottom of message thread
  indicator.style.position = 'absolute';
  indicator.style.bottom = '20px';
  indicator.style.left = '50%';
  indicator.style.transform = 'translateX(-50%)';
  indicator.style.zIndex = '100';
  indicator.style.cursor = 'pointer';
  
  // Add click handler to scroll to bottom
  indicator.addEventListener('click', () => {
    scrollToBottom(threadEl, true);
    hideNewMessageIndicator();
  });
  
  // Add to message content container (parent of thread)
  const messageContent = document.querySelector('.chat-message-content');
  if (messageContent) {
    messageContent.style.position = 'relative';
    messageContent.appendChild(indicator);
  }
}

function hideNewMessageIndicator() {
  const indicator = document.getElementById('new-message-indicator');
  if (indicator) {
    indicator.remove();
  }
}

function setupScrollListener(threadEl) {
  if (!threadEl || threadEl.hasScrollListener) return;
  
  // Mark that we've added the listener to avoid duplicates
  threadEl.hasScrollListener = true;
  
  let scrollTimeout;
  
  threadEl.addEventListener('scroll', () => {
    // Clear existing timeout
    clearTimeout(scrollTimeout);
    
    // Debounce scroll events
    scrollTimeout = setTimeout(() => {
      if (isScrolledToBottom(threadEl)) {
        hideNewMessageIndicator();
      }
    }, 100);
  });
}

function navigateConversationList(direction, currentItem) {
  const allItems = Array.from(document.querySelectorAll('.conversation-item'));
  const currentIndex = allItems.indexOf(currentItem);
  
  if (currentIndex === -1) return;
  
  const nextIndex = currentIndex + direction;
  if (nextIndex >= 0 && nextIndex < allItems.length) {
    allItems[nextIndex].focus();
  }
}

function clearConversationSelection() {
  chatState.selectedConversationSlug = null;
  chatState.selectedConversationType = null;
  saveChatState();
  
  document.querySelectorAll('.conversation-item').forEach(item => {
    item.classList.remove('selected');
  });
  
  renderMessageViewPlaceholder();
}

async function refreshChatTab() {
  ensurePersonaSelects();
  if (!chatMonitorPersonId) {
    renderChatPlaceholder();
    return;
  }
  
  // Update status indicator
  const statusEl = document.getElementById('chat-last-refresh');
  if (statusEl) {
    statusEl.textContent = 'Refreshing...';
  }
  
  try {
    chatState.isLoading = true;
    updateChatLoadingState(true);
    
    // Fetch conversation data from multiple endpoints
    const persona = people_cache.find(p => p.id === chatMonitorPersonId);
    if (!persona || !persona.chat_handle) {
      throw new Error('Selected persona does not have a chat handle');
    }
    
    // Fetch user's rooms and DM messages in parallel with timeout
    const fetchPromises = [
      fetchUserRooms(persona.chat_handle),
      fetchJson(`${API_PREFIX}/monitor/chat/messages/${chatMonitorPersonId}?scope=all&limit=100`)
    ];
    
    // Add timeout to prevent hanging requests
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Request timeout - please check your connection')), 10000);
    });
    
    const [roomsData, messagesData] = await Promise.race([
      Promise.all(fetchPromises),
      timeoutPromise
    ]);
    
    // Process and organize conversation data
    chatState.conversations.rooms = await processRoomConversations(roomsData, messagesData.rooms || []);
    chatState.conversations.dms = processDMConversations(messagesData.dms || []);
    chatState.lastRefresh = new Date();
    
    // Load saved conversation selection state
    const hasRestoredState = loadChatState();
    
    // Render conversation sidebar
    await renderConversationSidebar();
    
    // Restore conversation selection if we have saved state
    if (hasRestoredState && chatState.selectedConversationSlug) {
      const conversation = [...chatState.conversations.rooms, ...chatState.conversations.dms]
        .find(c => c.slug === chatState.selectedConversationSlug);
      
      if (conversation) {
        // Update UI selection without triggering selectConversation to avoid recursion
        document.querySelectorAll('.conversation-item').forEach(item => {
          item.classList.remove('selected');
        });
        
        const selectedItem = document.querySelector(`[data-conversation-slug="${conversation.slug}"]`);
        if (selectedItem) {
          selectedItem.classList.add('selected');
        }
        
        await loadConversationMessages(conversation);
      } else {
        // Conversation no longer exists, clear selection
        chatState.selectedConversationSlug = null;
        chatState.selectedConversationType = null;
        saveChatState();
        renderMessageViewPlaceholder();
      }
    } else {
      renderMessageViewPlaceholder();
    }
    
    // Update status indicator
    if (statusEl) {
      statusEl.textContent = `Last updated: ${chatState.lastRefresh.toLocaleTimeString()}`;
    }
    
    // Setup auto-refresh if simulation is running
    setupChatAutoRefresh();
    
    // Setup search handlers (only once)
    setupChatSearchHandlers();
    
    // Setup responsive sidebar functionality
    setupChatResponsiveSidebar();
    
  } catch (err) {
    console.error('Failed to refresh chat tab:', err);
    if (statusEl) {
      statusEl.textContent = 'Refresh failed';
    }
    renderChatError('Failed to load conversations. Please try again.');
  } finally {
    chatState.isLoading = false;
    updateChatLoadingState(false);
  }
}

async function fetchUserRooms(chatHandle) {
  try {
    // Use the chat server API via the simulation manager proxy
    const response = await fetch(`http://127.0.0.1:8001/users/${encodeURIComponent(chatHandle)}/rooms`);
    if (!response.ok) {
      throw new Error(`Failed to fetch rooms: ${response.statusText}`);
    }
    return await response.json();
  } catch (err) {
    console.error('Failed to fetch user rooms:', err);
    return [];
  }
}

async function processRoomConversations(roomsMetadata, roomMessages) {
  // Filter out DM rooms since we handle those separately
  const actualRooms = roomsMetadata.filter(room => !room.is_dm);
  
  // Create a map of room messages by room slug for quick lookup
  const messagesByRoom = new Map();
  roomMessages.forEach(message => {
    const roomSlug = message.room_slug;
    if (!messagesByRoom.has(roomSlug)) {
      messagesByRoom.set(roomSlug, []);
    }
    messagesByRoom.get(roomSlug).push(message);
  });
  
  return actualRooms.map(room => {
    const roomMessages = messagesByRoom.get(room.slug) || [];
    const sortedMessages = roomMessages.sort((a, b) => new Date(b.sent_at) - new Date(a.sent_at));
    const lastMessage = sortedMessages[0] || null;
    
    return {
      slug: room.slug,
      name: room.name || room.slug || 'Unknown Room',
      type: 'room',
      participants: room.participants || [],
      participantCount: (room.participants || []).length,
      lastMessage: lastMessage,
      lastActivity: lastMessage?.sent_at || null,
      messageCount: roomMessages.length,
      unreadCount: 0 // TODO: Implement unread tracking
    };
  }).sort((a, b) => {
    // Sort by last activity, most recent first
    const timeA = new Date(a.lastActivity || 0);
    const timeB = new Date(b.lastActivity || 0);
    return timeB - timeA;
  });
}

function processDMConversations(dms) {
  // Group DM messages by conversation partner
  const dmGroups = new Map();
  const currentHandle = getCurrentPersonaHandle();
  
  dms.forEach(message => {
    // Extract other participant from DM room slug (format: "dm:handle1:handle2")
    let otherParticipant = null;
    
    if (message.room_slug && message.room_slug.startsWith('dm:')) {
      const parts = message.room_slug.split(':');
      if (parts.length >= 3) {
        // Find the participant that's not the current user
        otherParticipant = parts[1] === currentHandle ? parts[2] : parts[1];
      }
    }
    
    // Fallback: if we can't extract from room slug, use sender if it's not current user
    if (!otherParticipant && message.sender !== currentHandle) {
      otherParticipant = message.sender;
    }
    
    // Skip if we can't determine the other participant
    if (!otherParticipant) {
      console.warn('Could not determine other participant for DM message:', message);
      return;
    }
    
    if (!dmGroups.has(otherParticipant)) {
      dmGroups.set(otherParticipant, {
        slug: message.room_slug || `dm-${otherParticipant}`,
        name: otherParticipant,
        type: 'dm',
        participants: [currentHandle, otherParticipant],
        participantCount: 2,
        messages: [],
        lastActivity: null,
        messageCount: 0,
        unreadCount: 0
      });
    }
    
    const conversation = dmGroups.get(otherParticipant);
    conversation.messages.push(message);
    conversation.messageCount++;
    
    // Update last activity
    const messageTime = new Date(message.sent_at);
    if (!conversation.lastActivity || messageTime > new Date(conversation.lastActivity)) {
      conversation.lastActivity = message.sent_at;
      conversation.lastMessage = message;
    }
  });
  
  return Array.from(dmGroups.values()).sort((a, b) => {
    const timeA = new Date(a.lastActivity || 0);
    const timeB = new Date(b.lastActivity || 0);
    return timeB - timeA;
  });
}

function getCurrentPersonaHandle() {
  const persona = people_cache.find(p => p.id === chatMonitorPersonId);
  return persona?.chat_handle || 'unknown';
}

async function renderConversationSidebar() {
  await renderConversationSection('chat-rooms-list', chatState.conversations.rooms, 'rooms-count');
  await renderConversationSection('chat-dms-list', chatState.conversations.dms, 'dms-count');
}

async function renderConversationSection(containerId, conversations, countId) {
  const container = document.getElementById(containerId);
  const countEl = document.getElementById(countId);
  
  if (!container) return;
  
  // Filter conversations based on search query (now async)
  const filteredConversations = chatState.searchQuery.trim() ? 
    await filterConversationsBySearch(conversations, chatState.searchQuery) : conversations;
  
  // Update count to show filtered results
  if (countEl) {
    const totalCount = conversations.length;
    const filteredCount = filteredConversations.length;
    if (chatState.searchQuery.trim() && filteredCount !== totalCount) {
      countEl.textContent = `(${filteredCount}/${totalCount})`;
    } else {
      countEl.textContent = `(${totalCount})`;
    }
  }
  
  container.innerHTML = '';
  
  // Handle empty states
  if (conversations.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'conversation-empty';
    const isRooms = containerId.includes('rooms');
    empty.innerHTML = `
      <div class="empty-icon" aria-hidden="true">${isRooms ? '#' : '@'}</div>
      <div class="empty-text">${isRooms ? 'No rooms available' : 'No direct messages'}</div>
      <div class="empty-hint">${isRooms ? 'Rooms will appear here when the persona joins them' : 'Direct messages will appear here when conversations start'}</div>
    `;
    container.appendChild(empty);
    return;
  }
  
  // Handle no search results
  if (filteredConversations.length === 0 && chatState.searchQuery.trim()) {
    const empty = document.createElement('div');
    empty.className = 'conversation-empty search-empty';
    empty.innerHTML = `
      <div class="empty-icon" aria-hidden="true">🔍</div>
      <div class="empty-text">No matches found</div>
      <div class="empty-hint">Try a different search term</div>
    `;
    container.appendChild(empty);
    return;
  }
  
  // Render filtered conversations
  filteredConversations.forEach(conversation => {
    const item = createConversationItem(conversation);
    container.appendChild(item);
  });
}

function createConversationItem(conversation) {
  const item = document.createElement('div');
  item.className = 'conversation-item';
  item.setAttribute('data-conversation-slug', conversation.slug);
  item.setAttribute('data-conversation-type', conversation.type);
  item.setAttribute('role', 'button');
  item.setAttribute('tabindex', '0');
  item.setAttribute('aria-label', `${conversation.type === 'room' ? 'Room' : 'Direct message'}: ${conversation.name}`);
  
  // Mark as selected if this is the current conversation
  if (conversation.slug === chatState.selectedConversationSlug) {
    item.classList.add('selected');
  }
  
  // Conversation icon with type-specific styling
  const icon = document.createElement('div');
  icon.className = 'conversation-icon';
  icon.setAttribute('data-conversation-type', conversation.type);
  const iconSymbol = document.createElement('span');
  iconSymbol.className = 'room-type-icon';
  iconSymbol.textContent = conversation.type === 'room' ? '#' : '@';
  iconSymbol.setAttribute('aria-label', conversation.type === 'room' ? 'Room' : 'Direct Message');
  icon.appendChild(iconSymbol);
  
  // Conversation info
  const info = document.createElement('div');
  info.className = 'conversation-info';
  
  const name = document.createElement('div');
  name.className = 'conversation-name';
  // Apply search highlighting to conversation name
  if (chatState.searchQuery.trim()) {
    name.innerHTML = highlightSearchMatches(conversation.name, chatState.searchQuery);
  } else {
    name.textContent = conversation.name;
  }
  
  const preview = document.createElement('div');
  preview.className = 'conversation-preview';
  if (conversation.lastMessage) {
    const sender = conversation.lastMessage.sender === getCurrentPersonaHandle() ? 'You' : conversation.lastMessage.sender;
    const body = conversation.lastMessage.body || '';
    const previewText = `${sender}: ${body.length > 50 ? body.slice(0, 50) + '…' : body}`;
    
    // Apply search highlighting to preview text
    if (chatState.searchQuery.trim()) {
      preview.innerHTML = highlightSearchMatches(previewText, chatState.searchQuery);
    } else {
      preview.textContent = previewText;
    }
  } else {
    preview.textContent = 'No messages yet';
  }
  
  const meta = document.createElement('div');
  meta.className = 'conversation-meta';
  
  const time = document.createElement('span');
  time.className = 'conversation-time';
  if (conversation.lastActivity) {
    time.textContent = formatRelativeTime(conversation.lastActivity);
    time.setAttribute('title', new Date(conversation.lastActivity).toLocaleString());
  } else {
    time.textContent = 'No activity';
  }
  
  const participantInfo = document.createElement('span');
  participantInfo.className = 'participant-count';
  if (conversation.type === 'room') {
    participantInfo.textContent = `${conversation.participantCount} members`;
    participantInfo.setAttribute('title', `Room with ${conversation.participantCount} participants`);
  } else {
    // For DMs, show the other participant's name with status
    const otherParticipant = conversation.participants?.find(p => p !== getCurrentPersonaHandle());
    if (otherParticipant) {
      participantInfo.textContent = `with ${otherParticipant}`;
      participantInfo.setAttribute('title', `Direct message with ${otherParticipant}`);
      
      // Add status indicator for DM participant (async)
      addParticipantStatusToDM(participantInfo, otherParticipant);
    }
  }
  
  meta.appendChild(time);
  if (participantInfo.textContent) {
    meta.appendChild(participantInfo);
  }
  
  info.appendChild(name);
  info.appendChild(preview);
  info.appendChild(meta);
  
  // Add search context if this is a search result
  if (conversation.searchMatchContext && conversation.searchQuery) {
    addSearchContextToConversation(item, conversation);
  }
  
  // Badges (unread count, etc.)
  const badges = document.createElement('div');
  badges.className = 'conversation-badges';
  
  if (conversation.unreadCount > 0) {
    const unreadBadge = document.createElement('span');
    unreadBadge.className = 'unread-badge';
    unreadBadge.textContent = conversation.unreadCount.toString();
    badges.appendChild(unreadBadge);
  }
  
  // Assemble the item
  item.appendChild(icon);
  item.appendChild(info);
  item.appendChild(badges);
  
  // Add click handler
  item.addEventListener('click', () => selectConversation(conversation));
  item.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      selectConversation(conversation);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      navigateConversationList(e.key === 'ArrowDown' ? 1 : -1, item);
    }
  });
  
  return item;
}

async function selectConversation(conversation) {
  // Update selection state
  chatState.selectedConversationSlug = conversation.slug;
  chatState.selectedConversationType = conversation.type;
  
  // Save state for persistence across refreshes
  saveChatState();
  
  // Update UI selection
  document.querySelectorAll('.conversation-item').forEach(item => {
    item.classList.remove('selected');
  });
  
  const selectedItem = document.querySelector(`[data-conversation-slug="${conversation.slug}"]`);
  if (selectedItem) {
    selectedItem.classList.add('selected');
    
    // Ensure selected item is visible (scroll into view if needed)
    selectedItem.scrollIntoView({ 
      behavior: 'smooth', 
      block: 'nearest',
      inline: 'nearest'
    });
  }
  
  // Mark this as a new conversation selection for scroll behavior
  chatState.isNewConversationSelection = true;
  
  // Load and display messages for this conversation
  await loadConversationMessages(conversation);
}

async function loadConversationMessages(conversation, options = {}) {
  try {
    // Only show loading state if not silent refresh
    if (!options.silent) {
      updateMessageViewLoading(true);
    }
    
    let messages = [];
    
    if (conversation.type === 'dm') {
      // For DMs, use messages from the conversation object if available
      // Otherwise fetch fresh data from the API
      if (conversation.messages && conversation.messages.length > 0) {
        messages = conversation.messages;
      } else {
        // Fetch DM messages for this persona
        const data = await fetchJson(`${API_PREFIX}/monitor/chat/messages/${chatMonitorPersonId}?scope=dms&limit=100`);
        if (data && data.dms) {
          // Filter messages for this specific DM conversation
          const otherParticipant = conversation.participants.find(p => p !== getCurrentPersonaHandle());
          messages = data.dms.filter(msg => 
            (msg.sender === otherParticipant && msg.recipient === getCurrentPersonaHandle()) ||
            (msg.sender === getCurrentPersonaHandle() && msg.recipient === otherParticipant)
          );
          // Update the conversation object with the fetched messages
          conversation.messages = messages;
        }
      }
    } else {
      // For rooms, fetch messages from the chat server via proxy
      const data = await fetchJson(`${API_PREFIX}/monitor/chat/room/${conversation.slug}/messages?limit=100`);
      messages = data || [];
    }
    
    // Sort messages chronologically (oldest first, newest last)
    chatState.currentMessages = messages.sort((a, b) => {
      return new Date(a.sent_at) - new Date(b.sent_at);
    });
    
    renderMessageView(conversation);
    
  } catch (err) {
    console.error('Failed to load conversation messages:', err);
    renderMessageViewError('Failed to load messages for this conversation. Please try refreshing.');
  } finally {
    updateMessageViewLoading(false);
  }
}

function renderMessageView(conversation) {
  // Update conversation header
  const titleEl = document.querySelector('.conversation-name');
  const participantListEl = document.querySelector('.participant-list');
  const messageCountEl = document.querySelector('.message-count');
  
  if (titleEl) {
    const displayName = conversation.name || conversation.slug || 'Unknown Conversation';
    titleEl.textContent = conversation.type === 'room' ? `#${displayName}` : displayName;
  }
  
  if (participantListEl) {
    if (conversation.type === 'room') {
      const count = conversation.participantCount || (conversation.participants ? conversation.participants.length : 0);
      participantListEl.innerHTML = `
        <span class="participant-count">${count} members</span>
        <button class="participant-info-btn" onclick="showParticipantInfo('${conversation.slug}', '${conversation.type}')" 
                aria-label="Show participant details" title="View participant status and roles">
          <span aria-hidden="true">👥</span>
        </button>
      `;
      
      // Add participant status summary for rooms (async)
      addParticipantStatusSummaryToRoom(participantListEl, conversation);
    } else {
      // For DMs, show the other participant's name with status
      const otherParticipant = conversation.participants?.find(p => p !== getCurrentPersonaHandle());
      if (otherParticipant) {
        participantListEl.innerHTML = `
          <span class="dm-participant">with ${otherParticipant}</span>
          <button class="participant-info-btn" onclick="showParticipantInfo('${conversation.slug}', '${conversation.type}')" 
                  aria-label="Show participant details" title="View participant status and role">
            <span aria-hidden="true">👤</span>
          </button>
        `;
        
        // Add participant status for DMs (async)
        addParticipantStatusToDMHeader(participantListEl, otherParticipant);
      } else {
        participantListEl.textContent = 'Direct message';
      }
    }
  }
  
  if (messageCountEl) {
    const count = chatState.currentMessages.length;
    messageCountEl.textContent = `${count} message${count !== 1 ? 's' : ''}`;
  }
  
  // Render message thread
  renderMessageThread();
}

function renderMessageThread() {
  const startTime = startPerformanceTimer();
  const threadEl = document.getElementById('message-thread');
  if (!threadEl) return;
  
  // Run performance optimization before rendering
  optimizeRenderingPerformance();
  
  // Store scroll state before rendering
  const wasAtBottom = isScrolledToBottom(threadEl);
  const previousScrollTop = threadEl.scrollTop;
  const previousScrollHeight = threadEl.scrollHeight;
  const previousMessageCount = threadEl.querySelectorAll('.message-group').length;
  
  if (chatState.currentMessages.length === 0) {
    threadEl.innerHTML = '';
    const placeholder = document.createElement('div');
    placeholder.className = 'message-thread-placeholder';
    
    // Get the current conversation type for context-specific messaging
    const conversationType = chatState.selectedConversationType;
    const isRoom = conversationType === 'room';
    
    placeholder.innerHTML = `
      <div class="placeholder-icon">💬</div>
      <div class="placeholder-text">
        <h4>No messages yet</h4>
        <p>${isRoom ? 'This room doesn\'t have any messages yet.' : 'This conversation doesn\'t have any messages yet.'}</p>
        <p class="placeholder-hint">Messages will appear here as the simulation progresses.</p>
      </div>
    `;
    threadEl.appendChild(placeholder);
    endPerformanceTimer(startTime, 'renderMessageThread-empty');
    return;
  }
  
  // Group messages by sender and time proximity
  const messageGroups = groupMessagesBySender(chatState.currentMessages);
  
  // Determine if we should use performance optimizations
  const shouldUseVirtualScrolling = shouldEnableVirtualScrolling();
  const shouldUsePagination = shouldEnablePagination();
  
  // Log performance decision
  const messageCount = chatState.currentMessages.length;
  const avgRenderTime = chatState.performanceMetrics.averageRenderTime;
  
  if (shouldUsePagination) {
    console.log(`Using pagination for ${messageCount} messages (avg render: ${avgRenderTime.toFixed(2)}ms)`);
    renderMessageThreadWithPagination(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount);
  } else if (shouldUseVirtualScrolling) {
    console.log(`Using virtual scrolling for ${messageCount} messages (avg render: ${avgRenderTime.toFixed(2)}ms)`);
    renderMessageThreadWithVirtualScrolling(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount);
  } else {
    console.log(`Using standard rendering for ${messageCount} messages (avg render: ${avgRenderTime.toFixed(2)}ms)`);
    renderMessageThreadStandard(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount);
  }
  
  const renderDuration = endPerformanceTimer(startTime, 'renderMessageThread');
  
  // Show performance indicator if rendering was slow
  if (renderDuration > 100) {
    showPerformanceWarning(renderDuration, messageCount);
  }
}

function renderMessageThreadStandard(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount) {
  // Standard rendering for smaller conversations
  threadEl.innerHTML = '';
  
  const fragment = document.createDocumentFragment();
  messageGroups.forEach(group => {
    const groupEl = createMessageGroup(group);
    fragment.appendChild(groupEl);
  });
  threadEl.appendChild(fragment);
  
  handleScrollBehaviorAfterRender(threadEl, messageGroups.length, previousMessageCount, wasAtBottom, previousScrollTop, previousScrollHeight);
}

function renderMessageThreadWithVirtualScrolling(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount) {
  // Virtual scrolling for large conversations
  chatState.virtualScrolling.enabled = true;
  chatState.virtualScrolling.totalItems = messageGroups.length;
  
  // Create virtual scroll container
  threadEl.innerHTML = '';
  threadEl.classList.add('virtual-scroll-container');
  
  // Create spacer elements for virtual scrolling
  const topSpacer = document.createElement('div');
  topSpacer.className = 'virtual-scroll-spacer-top';
  topSpacer.style.height = '0px';
  
  const visibleContainer = document.createElement('div');
  visibleContainer.className = 'virtual-scroll-visible';
  
  const bottomSpacer = document.createElement('div');
  bottomSpacer.className = 'virtual-scroll-spacer-bottom';
  bottomSpacer.style.height = '0px';
  
  threadEl.appendChild(topSpacer);
  threadEl.appendChild(visibleContainer);
  threadEl.appendChild(bottomSpacer);
  
  // Initialize virtual scrolling parameters
  if (!chatState.virtualScrolling.itemHeight) {
    chatState.virtualScrolling.itemHeight = 80; // Estimated height per message group
  }
  
  // Calculate visible range
  updateVirtualScrollRange(threadEl);
  
  // Render only visible items
  renderVisibleMessageGroups(visibleContainer, messageGroups, topSpacer, bottomSpacer);
  
  // Set up virtual scroll listener
  setupVirtualScrollListener(threadEl, messageGroups);
  
  handleScrollBehaviorAfterRender(threadEl, messageGroups.length, previousMessageCount, wasAtBottom, previousScrollTop, previousScrollHeight);
  
  // Add performance indicator for virtual scrolling
  const indicator = document.createElement('div');
  indicator.className = 'performance-indicator virtual-scroll-indicator';
  indicator.innerHTML = `
    <span class="indicator-icon">⚡</span>
    <span class="indicator-text">Virtual scrolling enabled (${messageGroups.length} message groups)</span>
  `;
  indicator.style.cssText = `
    position: absolute;
    top: 10px;
    right: 10px;
    background: rgba(34, 197, 94, 0.9);
    color: white;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    z-index: 100;
    pointer-events: none;
  `;
  
  threadEl.style.position = 'relative';
  threadEl.appendChild(indicator);
  
  // Remove indicator after 3 seconds
  setTimeout(() => {
    if (indicator.parentNode) {
      indicator.parentNode.removeChild(indicator);
    }
  }, 3000);
}

function renderMessageThreadWithPagination(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount) {
  // Pagination for very large conversations
  chatState.pagination.enabled = true;
  chatState.pagination.totalPages = Math.ceil(messageGroups.length / chatState.pagination.pageSize);
  
  // If this is a new conversation or we're at the end, show the last page
  if (chatState.isNewConversationSelection || wasAtBottom) {
    chatState.pagination.currentPage = chatState.pagination.totalPages - 1;
  }
  
  threadEl.innerHTML = '';
  threadEl.classList.add('paginated-container');
  
  // Create pagination controls
  const paginationTop = createPaginationControls('top');
  const messageContainer = document.createElement('div');
  messageContainer.className = 'paginated-messages';
  const paginationBottom = createPaginationControls('bottom');
  
  threadEl.appendChild(paginationTop);
  threadEl.appendChild(messageContainer);
  threadEl.appendChild(paginationBottom);
  
  // Render current page
  renderMessagePage(messageContainer, messageGroups);
  
  handleScrollBehaviorAfterRender(messageContainer, messageGroups.length, previousMessageCount, wasAtBottom, previousScrollTop, previousScrollHeight);
}

function updateVirtualScrollRange(container) {
  const containerRect = container.getBoundingClientRect();
  chatState.virtualScrolling.containerHeight = containerRect.height;
  chatState.virtualScrolling.scrollTop = container.scrollTop;
  
  const itemHeight = chatState.virtualScrolling.itemHeight;
  const buffer = chatState.virtualScrolling.renderBuffer;
  
  chatState.virtualScrolling.visibleStart = Math.max(0, 
    Math.floor(chatState.virtualScrolling.scrollTop / itemHeight) - buffer);
  chatState.virtualScrolling.visibleEnd = Math.min(chatState.virtualScrolling.totalItems - 1,
    Math.floor((chatState.virtualScrolling.scrollTop + chatState.virtualScrolling.containerHeight) / itemHeight) + buffer);
}

function renderVisibleMessageGroups(container, messageGroups, topSpacer, bottomSpacer) {
  const { visibleStart, visibleEnd, itemHeight } = chatState.virtualScrolling;
  
  // Update spacer heights
  topSpacer.style.height = `${visibleStart * itemHeight}px`;
  bottomSpacer.style.height = `${(messageGroups.length - visibleEnd - 1) * itemHeight}px`;
  
  // Clear and render visible items
  container.innerHTML = '';
  const fragment = document.createDocumentFragment();
  
  for (let i = visibleStart; i <= visibleEnd; i++) {
    if (messageGroups[i]) {
      // Check cache first
      const cacheKey = `group-${i}-${JSON.stringify(messageGroups[i]).slice(0, 100)}`;
      let groupEl = chatState.renderCache.get(cacheKey);
      
      if (!groupEl) {
        groupEl = createMessageGroup(messageGroups[i]);
        groupEl.style.minHeight = `${chatState.virtualScrolling.itemHeight}px`;
        chatState.renderCache.set(cacheKey, groupEl.cloneNode(true));
      } else {
        groupEl = groupEl.cloneNode(true);
      }
      
      fragment.appendChild(groupEl);
    }
  }
  
  container.appendChild(fragment);
  
  // Clean up cache if it gets too large
  if (chatState.renderCache.size > 200) {
    const entries = Array.from(chatState.renderCache.entries());
    entries.slice(0, 100).forEach(([key]) => chatState.renderCache.delete(key));
  }
}

function setupVirtualScrollListener(container, messageGroups) {
  // Remove existing listener
  container.removeEventListener('scroll', handleVirtualScroll);
  
  // Add throttled scroll listener
  let scrollTimeout;
  function handleVirtualScroll() {
    chatState.performanceMetrics.scrollEvents++;
    
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(() => {
      updateVirtualScrollRange(container);
      const visibleContainer = container.querySelector('.virtual-scroll-visible');
      const topSpacer = container.querySelector('.virtual-scroll-spacer-top');
      const bottomSpacer = container.querySelector('.virtual-scroll-spacer-bottom');
      
      if (visibleContainer && topSpacer && bottomSpacer) {
        renderVisibleMessageGroups(visibleContainer, messageGroups, topSpacer, bottomSpacer);
      }
    }, 16); // ~60fps throttling
  }
  
  container.addEventListener('scroll', handleVirtualScroll, { passive: true });
}

function createPaginationControls(position) {
  const controls = document.createElement('div');
  controls.className = `pagination-controls pagination-${position}`;
  
  const info = document.createElement('span');
  info.className = 'pagination-info';
  
  const prevBtn = document.createElement('button');
  prevBtn.className = 'pagination-btn secondary';
  prevBtn.innerHTML = '← Previous';
  prevBtn.disabled = chatState.pagination.currentPage === 0;
  prevBtn.onclick = () => navigateToPage(chatState.pagination.currentPage - 1);
  
  const nextBtn = document.createElement('button');
  nextBtn.className = 'pagination-btn secondary';
  nextBtn.innerHTML = 'Next →';
  nextBtn.disabled = chatState.pagination.currentPage >= chatState.pagination.totalPages - 1;
  nextBtn.onclick = () => navigateToPage(chatState.pagination.currentPage + 1);
  
  const jumpToEnd = document.createElement('button');
  jumpToEnd.className = 'pagination-btn secondary';
  jumpToEnd.innerHTML = 'Latest';
  jumpToEnd.onclick = () => navigateToPage(chatState.pagination.totalPages - 1);
  
  updatePaginationInfo(info);
  
  controls.appendChild(prevBtn);
  controls.appendChild(info);
  controls.appendChild(nextBtn);
  controls.appendChild(jumpToEnd);
  
  return controls;
}

function updatePaginationInfo(infoEl) {
  const { currentPage, totalPages, pageSize } = chatState.pagination;
  const totalMessages = chatState.currentMessages.length;
  const startMessage = currentPage * pageSize + 1;
  const endMessage = Math.min((currentPage + 1) * pageSize, totalMessages);
  
  infoEl.textContent = `Page ${currentPage + 1} of ${totalPages} (Messages ${startMessage}-${endMessage} of ${totalMessages})`;
}

function navigateToPage(pageNumber) {
  if (pageNumber < 0 || pageNumber >= chatState.pagination.totalPages) return;
  
  chatState.pagination.currentPage = pageNumber;
  
  // Re-render the current page
  const messageContainer = document.querySelector('.paginated-messages');
  if (messageContainer) {
    const messageGroups = groupMessagesBySender(chatState.currentMessages);
    renderMessagePage(messageContainer, messageGroups);
  }
  
  // Update pagination controls
  document.querySelectorAll('.pagination-controls').forEach(controls => {
    const prevBtn = controls.querySelector('.pagination-btn:first-child');
    const nextBtn = controls.querySelector('.pagination-btn:nth-child(3)');
    const info = controls.querySelector('.pagination-info');
    
    if (prevBtn) prevBtn.disabled = chatState.pagination.currentPage === 0;
    if (nextBtn) nextBtn.disabled = chatState.pagination.currentPage >= chatState.pagination.totalPages - 1;
    if (info) updatePaginationInfo(info);
  });
}

function renderMessagePage(container, messageGroups) {
  const { currentPage, pageSize } = chatState.pagination;
  const startIndex = currentPage * pageSize;
  const endIndex = Math.min(startIndex + pageSize, messageGroups.length);
  
  container.innerHTML = '';
  const fragment = document.createDocumentFragment();
  
  for (let i = startIndex; i < endIndex; i++) {
    if (messageGroups[i]) {
      const groupEl = createMessageGroup(messageGroups[i]);
      fragment.appendChild(groupEl);
    }
  }
  
  container.appendChild(fragment);
}

function handleScrollBehaviorAfterRender(container, currentMessageCount, previousMessageCount, wasAtBottom, previousScrollTop, previousScrollHeight) {
  // Handle scroll behavior based on user's previous position and new messages
  setTimeout(() => {
    const hasNewMessages = currentMessageCount > previousMessageCount;
    const isNewSelection = chatState.isNewConversationSelection;
    
    // Clear the new selection flag
    chatState.isNewConversationSelection = false;
    
    if (isNewSelection || wasAtBottom || !hasNewMessages) {
      // New conversation selection, user was at bottom, or no new messages - scroll to bottom smoothly
      scrollToBottom(container, true);
      hideNewMessageIndicator();
    } else {
      // User was reading older messages - preserve position and show indicator
      const scrollDelta = container.scrollHeight - previousScrollHeight;
      container.scrollTop = previousScrollTop + scrollDelta;
      
      if (hasNewMessages) {
        showNewMessageIndicator(currentMessageCount - previousMessageCount);
      }
    }
    
    // Set up scroll listener for new message indicator
    setupScrollListener(container);
  }, 50);
}

function groupMessagesBySender(messages) {
  const groups = [];
  let currentGroup = null;
  
  // Filter out messages with missing required fields
  const validMessages = messages.filter(message => {
    if (!message || !message.sender || !message.sent_at) {
      console.warn('Skipping invalid message:', message);
      return false;
    }
    return true;
  });
  
  validMessages.forEach(message => {
    const messageTime = new Date(message.sent_at);
    
    // Check if we should start a new group
    const shouldStartNewGroup = !currentGroup || 
      currentGroup.sender !== message.sender ||
      (messageTime - new Date(currentGroup.lastMessageTime)) > 5 * 60 * 1000; // 5 minutes
    
    if (shouldStartNewGroup) {
      currentGroup = {
        sender: message.sender || 'Unknown',
        messages: [message],
        firstMessageTime: message.sent_at,
        lastMessageTime: message.sent_at
      };
      groups.push(currentGroup);
    } else {
      currentGroup.messages.push(message);
      currentGroup.lastMessageTime = message.sent_at;
    }
  });
  
  return groups;
}

function createMessageGroup(group) {
  const startTime = startPerformanceTimer();
  
  // Check if we have a cached version of this group
  const groupHash = generateGroupHash(group);
  const cacheKey = `messageGroup-${groupHash}`;
  
  if (chatState.renderCache.has(cacheKey)) {
    const cachedElement = chatState.renderCache.get(cacheKey);
    
    // Track cache hit
    if (!chatState.performanceMetrics.cacheHits) {
      chatState.performanceMetrics.cacheHits = 0;
    }
    chatState.performanceMetrics.cacheHits++;
    
    endPerformanceTimer(startTime, 'createMessageGroup-cached');
    return cachedElement.cloneNode(true);
  }
  
  // Track cache miss
  if (!chatState.performanceMetrics.cacheMisses) {
    chatState.performanceMetrics.cacheMisses = 0;
  }
  chatState.performanceMetrics.cacheMisses++;
  
  const groupEl = document.createElement('div');
  groupEl.className = 'message-group';
  groupEl.setAttribute('data-sender', group.sender);
  
  // Group header with sender name and timestamp
  const header = document.createElement('div');
  header.className = 'message-group-header';
  
  const senderName = document.createElement('span');
  senderName.className = 'sender-name';
  senderName.textContent = group.sender;
  
  const timestamp = document.createElement('span');
  timestamp.className = 'message-timestamp';
  timestamp.textContent = formatMessageTime(group.firstMessageTime);
  timestamp.title = new Date(group.firstMessageTime).toLocaleString();
  
  header.appendChild(senderName);
  header.appendChild(timestamp);
  groupEl.appendChild(header);
  
  // Message bubbles - use document fragment for better performance
  const bubbleFragment = document.createDocumentFragment();
  group.messages.forEach((message, index) => {
    const bubble = createMessageBubble(message, index === group.messages.length - 1);
    bubbleFragment.appendChild(bubble);
  });
  groupEl.appendChild(bubbleFragment);
  
  // Cache the element for future use
  chatState.renderCache.set(cacheKey, groupEl.cloneNode(true));
  
  // Limit cache size to prevent memory issues
  if (chatState.renderCache.size > 500) {
    const oldestKeys = Array.from(chatState.renderCache.keys()).slice(0, 100);
    oldestKeys.forEach(key => chatState.renderCache.delete(key));
  }
  
  endPerformanceTimer(startTime, 'createMessageGroup-new');
  return groupEl;
}

function generateGroupHash(group) {
  // Generate a hash for the message group to use as cache key
  const messageIds = group.messages.map(m => m.id || m.sent_at).join(',');
  return `${group.sender}-${group.firstMessageTime}-${messageIds.slice(0, 50)}`;
}

function createMessageBubbleOptimized(message, isLastInGroup) {
  // Optimized version with minimal DOM operations
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  
  // Build content string first, then set innerHTML once
  let contentHTML = '';
  
  // Handle message content with proper formatting
  const messageBody = message.body || message.content || '';
  if (messageBody.trim()) {
    let formattedContent = messageBody.replace(/\n/g, '<br>');
    
    // Apply search highlighting if there's an active search
    if (chatState.messageSearchQuery && chatState.messageSearchQuery.trim()) {
      formattedContent = highlightMessageSearchMatches(formattedContent, chatState.messageSearchQuery);
    }
    
    contentHTML = `<div class="message-content">${formattedContent}</div>`;
  } else {
    contentHTML = '<div class="message-content empty-message">[Empty message]</div>';
  }
  
  // Add metadata for the last message in group
  if (isLastInGroup) {
    let metaHTML = '<div class="message-meta">';
    
    if (message.id) {
      metaHTML += `<span class="message-id">#${message.id}</span>`;
    }
    
    if (message.tick) {
      metaHTML += `<span class="message-tick">Tick ${message.tick}</span>`;
    }
    
    if (message.status) {
      metaHTML += `<span class="message-status">${message.status}</span>`;
    }
    
    metaHTML += '</div>';
    
    if (metaHTML !== '<div class="message-meta"></div>') {
      contentHTML += metaHTML;
    }
  }
  
  bubble.innerHTML = contentHTML;
  return bubble;
}

function createMessageBubble(message, isLastInGroup) {
  // Use optimized version for better performance
  return createMessageBubbleOptimized(message, isLastInGroup);
}

// Participant status and information functions
async function showParticipantInfo(conversationSlug, conversationType) {
  try {
    // Get participant information for the conversation
    const participantInfo = await fetchParticipantInfo(conversationSlug, conversationType);
    
    // Create and show participant info modal
    createParticipantInfoModal(participantInfo, conversationSlug, conversationType);
  } catch (error) {
    console.error('Failed to load participant information:', error);
    setStatus('Failed to load participant information', true);
  }
}

async function fetchParticipantInfo(conversationSlug, conversationType) {
  const participants = [];
  
  if (conversationType === 'room') {
    // For rooms, get all participants from the conversation
    const conversation = chatState.conversations.rooms.find(c => c.slug === conversationSlug);
    if (conversation && conversation.participants) {
      for (const participantHandle of conversation.participants) {
        const participantData = await getParticipantDetails(participantHandle);
        participants.push(participantData);
      }
    }
  } else {
    // For DMs, get the other participant
    const conversation = chatState.conversations.dms.find(c => c.slug === conversationSlug);
    if (conversation && conversation.participants) {
      const otherParticipant = conversation.participants.find(p => p !== getCurrentPersonaHandle());
      if (otherParticipant) {
        const participantData = await getParticipantDetails(otherParticipant);
        participants.push(participantData);
      }
    }
  }
  
  return participants;
}

async function getParticipantDetails(chatHandle) {
  // Find the persona by chat handle
  const persona = people_cache.find(p => p.chat_handle === chatHandle);
  
  if (!persona) {
    return {
      handle: chatHandle,
      name: chatHandle,
      role: 'Unknown',
      status: 'Unknown',
      isDepartmentHead: false,
      teamName: null,
      availability: 'Unknown',
      workHours: '09:00-17:00',
      timezone: 'UTC',
      skills: [],
      isActive: false
    };
  }
  
  // Get current status from simulation if available
  let currentStatus = 'Working';
  let availability = 'Available';
  let isActive = false;
  
  try {
    // Try to get current status from simulation state
    const statusInfo = await fetchPersonaStatus(persona.id);
    currentStatus = statusInfo.status || 'Working';
    availability = statusInfo.availability || 'Available';
    isActive = statusInfo.isActive || false;
  } catch (error) {
    console.warn('Could not fetch persona status:', error);
    // Fallback to simulation state for basic availability
    try {
      const simState = await fetchJson(`${API_PREFIX}/simulation`);
      isActive = simState.is_running;
      if (!isActive) {
        currentStatus = 'OffDuty';
        availability = 'Offline';
      }
    } catch (simError) {
      console.warn('Could not fetch simulation state:', simError);
    }
  }
  
  return {
    handle: chatHandle,
    name: persona.name,
    role: persona.role,
    status: currentStatus,
    isDepartmentHead: persona.is_department_head || false,
    teamName: persona.team_name || null,
    availability: availability,
    workHours: persona.work_hours || '09:00-17:00',
    timezone: persona.timezone || 'UTC',
    skills: persona.skills || [],
    isActive: isActive
  };
}

async function fetchPersonaStatus(personaId) {
  try {
    // Get simulation state first
    const simState = await fetchJson(`${API_PREFIX}/simulation`);
    const isRunning = simState.is_running;
    const currentTick = simState.current_tick || 0;
    
    // Check if there's a status override for this persona
    let hasOverride = false;
    let overrideStatus = null;
    
    try {
      // Check for status overrides (this endpoint may not exist yet)
      const overrideResponse = await fetch(`${API_PREFIX}/people/${personaId}/status-override`);
      if (overrideResponse.ok) {
        const overrideData = await overrideResponse.json();
        if (overrideData && overrideData.until_tick > currentTick) {
          hasOverride = true;
          overrideStatus = overrideData.status;
        }
      }
    } catch (overrideError) {
      // Status override endpoint doesn't exist, continue with normal status
    }
    
    // Determine status based on override or simulation state
    let status, availability;
    
    if (hasOverride) {
      status = overrideStatus;
      switch (overrideStatus) {
        case 'SickLeave':
        case 'OnLeave':
          availability = 'Unavailable';
          break;
        case 'Absent':
        case 'Offline':
          availability = 'Away';
          break;
        default:
          availability = 'Available';
      }
    } else if (!isRunning) {
      status = 'OffDuty';
      availability = 'Offline';
    } else {
      // During simulation, determine status based on time and activity
      status = determineWorkingStatus(currentTick);
      availability = status === 'Working' ? 'Available' : 
                   status === 'Away' ? 'Away' : 'Busy';
    }
    
    return {
      status: status,
      availability: availability,
      isActive: isRunning,
      hasOverride: hasOverride,
      currentTick: currentTick
    };
  } catch (error) {
    console.warn('Could not fetch persona status:', error);
    
    // Fallback to basic status
    return {
      status: 'Unknown',
      availability: 'Unknown',
      isActive: false,
      hasOverride: false,
      currentTick: 0
    };
  }
}

function determineWorkingStatus(currentTick) {
  // Simple heuristic to determine working status based on tick
  // This could be enhanced with actual schedule information
  const ticksPerHour = 60; // Assuming 1 tick = 1 minute
  const ticksPerDay = ticksPerHour * 9; // 9-hour workday
  const dayTick = currentTick % ticksPerDay;
  const hourInDay = Math.floor(dayTick / ticksPerHour);
  
  // Lunch break around hour 4-5 (12:00-13:00)
  if (hourInDay >= 4 && hourInDay < 5) {
    return 'Away';
  }
  
  // Random breaks (simplified)
  if (dayTick % 120 < 15) { // 15-minute break every 2 hours
    return 'Away';
  }
  
  return 'Working';
}

function createParticipantInfoModal(participants, conversationSlug, conversationType) {
  // Remove existing modal if present
  const existingModal = document.getElementById('participant-info-modal');
  if (existingModal) {
    existingModal.remove();
  }
  
  // Create modal structure
  const modal = document.createElement('div');
  modal.id = 'participant-info-modal';
  modal.className = 'modal participant-modal';
  modal.style.display = 'block';
  
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  
  const dialog = document.createElement('div');
  dialog.className = 'modal-dialog participant-dialog';
  
  const header = document.createElement('div');
  header.className = 'modal-header';
  
  const title = document.createElement('div');
  title.className = 'modal-title';
  title.textContent = conversationType === 'room' 
    ? `Participants in #${conversationSlug}` 
    : `Conversation with ${participants[0]?.name || 'Unknown'}`;
  
  const closeBtn = document.createElement('button');
  closeBtn.className = 'secondary';
  closeBtn.textContent = 'Close';
  closeBtn.onclick = () => closeParticipantInfoModal();
  
  header.appendChild(title);
  header.appendChild(closeBtn);
  
  const body = document.createElement('div');
  body.className = 'modal-body participant-list-body';
  
  // Create participant list
  participants.forEach(participant => {
    const participantCard = createParticipantCard(participant);
    body.appendChild(participantCard);
  });
  
  if (participants.length === 0) {
    const emptyState = document.createElement('div');
    emptyState.className = 'participant-empty-state';
    emptyState.innerHTML = `
      <div class="empty-icon">👥</div>
      <div class="empty-text">No participant information available</div>
    `;
    body.appendChild(emptyState);
  }
  
  dialog.appendChild(header);
  dialog.appendChild(body);
  modal.appendChild(backdrop);
  modal.appendChild(dialog);
  
  // Add to document
  document.body.appendChild(modal);
  
  // Add event listeners
  backdrop.onclick = () => closeParticipantInfoModal();
  document.addEventListener('keydown', handleParticipantModalKeydown);
}

function createParticipantCard(participant) {
  const card = document.createElement('div');
  card.className = 'participant-card';
  
  // Status indicator with enhanced visual feedback
  const statusIndicator = document.createElement('div');
  statusIndicator.className = `participant-status-indicator ${getStatusClass(participant.status)}`;
  statusIndicator.setAttribute('aria-label', `Status: ${participant.status}`);
  statusIndicator.title = `${participant.status} - ${participant.availability}`;
  
  // Add pulsing animation for active users
  if (participant.isActive && participant.status === 'Working') {
    statusIndicator.classList.add('status-active-pulse');
  }
  
  // Participant info
  const info = document.createElement('div');
  info.className = 'participant-info';
  
  const nameRow = document.createElement('div');
  nameRow.className = 'participant-name-row';
  
  const name = document.createElement('span');
  name.className = 'participant-name';
  name.textContent = participant.name;
  
  const badges = document.createElement('div');
  badges.className = 'participant-badges';
  
  // Department head badge
  if (participant.isDepartmentHead) {
    const headBadge = document.createElement('span');
    headBadge.className = 'participant-badge head-badge';
    headBadge.textContent = 'Head';
    headBadge.title = 'Department Head';
    badges.appendChild(headBadge);
  }
  
  // Active status badge
  if (participant.isActive) {
    const activeBadge = document.createElement('span');
    activeBadge.className = 'participant-badge active-badge';
    activeBadge.textContent = 'Active';
    activeBadge.title = 'Currently in simulation';
    badges.appendChild(activeBadge);
  }
  
  nameRow.appendChild(name);
  nameRow.appendChild(badges);
  
  const role = document.createElement('div');
  role.className = 'participant-role';
  role.textContent = participant.role;
  
  const details = document.createElement('div');
  details.className = 'participant-details';
  
  // Team information
  if (participant.teamName) {
    const team = document.createElement('div');
    team.className = 'participant-detail-item';
    team.innerHTML = `<span class="detail-label">Team:</span> ${participant.teamName}`;
    details.appendChild(team);
  }
  
  // Status and availability
  const status = document.createElement('div');
  status.className = 'participant-detail-item';
  const statusText = participant.availability !== participant.status ? 
    `${participant.status} (${participant.availability})` : participant.availability;
  status.innerHTML = `<span class="detail-label">Status:</span> ${statusText}`;
  details.appendChild(status);
  
  // Work hours and timezone
  const workHours = document.createElement('div');
  workHours.className = 'participant-detail-item';
  workHours.innerHTML = `<span class="detail-label">Hours:</span> ${participant.workHours} (${participant.timezone})`;
  details.appendChild(workHours);
  
  // Skills (if available)
  if (participant.skills && participant.skills.length > 0) {
    const skills = document.createElement('div');
    skills.className = 'participant-detail-item';
    const skillsList = participant.skills.slice(0, 3).join(', ') + 
      (participant.skills.length > 3 ? ` (+${participant.skills.length - 3} more)` : '');
    skills.innerHTML = `<span class="detail-label">Skills:</span> ${skillsList}`;
    skills.title = participant.skills.join(', ');
    details.appendChild(skills);
  }
  
  info.appendChild(nameRow);
  info.appendChild(role);
  info.appendChild(details);
  
  card.appendChild(statusIndicator);
  card.appendChild(info);
  
  return card;
}

function getStatusClass(status) {
  switch (status) {
    case 'Working':
      return 'status-working';
    case 'Away':
    case 'Meeting':
    case 'Break':
      return 'status-away';
    case 'SickLeave':
    case 'Vacation':
    case 'OnLeave':
      return 'status-unavailable';
    case 'OffDuty':
    case 'Offline':
      return 'status-offline';
    case 'Absent':
      return 'status-absent';
    default:
      return 'status-unknown';
  }
}

async function addParticipantStatusToDM(participantInfoElement, chatHandle) {
  try {
    const participantDetails = await getParticipantDetails(chatHandle);
    
    // Create status indicator
    const statusIndicator = document.createElement('span');
    statusIndicator.className = `participant-status-dot ${getStatusClass(participantDetails.status)}`;
    statusIndicator.setAttribute('title', `${participantDetails.name}: ${participantDetails.status} - ${participantDetails.availability}`);
    statusIndicator.setAttribute('aria-label', `${participantDetails.name} is ${participantDetails.availability}`);
    
    // Add pulsing animation for active users
    if (participantDetails.isActive && participantDetails.status === 'Working') {
      statusIndicator.classList.add('status-active-pulse');
    }
    
    // Insert status indicator before the text
    participantInfoElement.insertBefore(statusIndicator, participantInfoElement.firstChild);
    
    // Update text to include status
    const originalText = participantInfoElement.textContent;
    participantInfoElement.innerHTML = '';
    participantInfoElement.appendChild(statusIndicator);
    
    const textSpan = document.createElement('span');
    textSpan.textContent = ` ${originalText}`;
    participantInfoElement.appendChild(textSpan);
    
  } catch (error) {
    console.warn('Could not add participant status to DM:', error);
  }
}

async function addParticipantStatusToDMHeader(participantListElement, chatHandle) {
  try {
    const participantDetails = await getParticipantDetails(chatHandle);
    
    // Find the dm-participant span
    const dmParticipantSpan = participantListElement.querySelector('.dm-participant');
    if (dmParticipantSpan) {
      // Create status indicator
      const statusIndicator = document.createElement('span');
      statusIndicator.className = `participant-status-dot ${getStatusClass(participantDetails.status)}`;
      statusIndicator.setAttribute('title', `${participantDetails.name}: ${participantDetails.status} - ${participantDetails.availability}`);
      statusIndicator.setAttribute('aria-label', `${participantDetails.name} is ${participantDetails.availability}`);
      
      // Add pulsing animation for active users
      if (participantDetails.isActive && participantDetails.status === 'Working') {
        statusIndicator.classList.add('status-active-pulse');
      }
      
      // Insert status indicator at the beginning of the span
      dmParticipantSpan.insertBefore(statusIndicator, dmParticipantSpan.firstChild);
      
      // Add status text
      const statusText = document.createElement('span');
      statusText.className = 'participant-status-text';
      statusText.textContent = ` (${participantDetails.availability})`;
      dmParticipantSpan.appendChild(statusText);
    }
    
  } catch (error) {
    console.warn('Could not add participant status to DM header:', error);
  }
}

async function addParticipantStatusSummaryToRoom(participantListElement, conversation) {
  try {
    if (!conversation.participants || conversation.participants.length === 0) {
      return;
    }
    
    // Get status for all participants
    const participantStatuses = await Promise.all(
      conversation.participants.map(async (handle) => {
        try {
          const details = await getParticipantDetails(handle);
          return details.status;
        } catch (error) {
          return 'Unknown';
        }
      })
    );
    
    // Count status types
    const statusCounts = participantStatuses.reduce((counts, status) => {
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    }, {});
    
    // Create status summary
    const statusSummary = document.createElement('div');
    statusSummary.className = 'participant-status-summary';
    
    // Show active/working count prominently
    const workingCount = statusCounts['Working'] || 0;
    const totalCount = participantStatuses.length;
    
    if (workingCount > 0) {
      const workingIndicator = document.createElement('span');
      workingIndicator.className = 'status-summary-item status-working';
      workingIndicator.textContent = `${workingCount} active`;
      workingIndicator.setAttribute('title', `${workingCount} of ${totalCount} participants are currently working`);
      statusSummary.appendChild(workingIndicator);
    }
    
    // Show away/unavailable count if any
    const awayCount = (statusCounts['Away'] || 0) + (statusCounts['Meeting'] || 0);
    const unavailableCount = (statusCounts['SickLeave'] || 0) + (statusCounts['Vacation'] || 0) + (statusCounts['OnLeave'] || 0);
    const offlineCount = (statusCounts['OffDuty'] || 0) + (statusCounts['Offline'] || 0);
    
    if (awayCount > 0) {
      const awayIndicator = document.createElement('span');
      awayIndicator.className = 'status-summary-item status-away';
      awayIndicator.textContent = `${awayCount} away`;
      awayIndicator.setAttribute('title', `${awayCount} participants are away or in meetings`);
      statusSummary.appendChild(awayIndicator);
    }
    
    if (unavailableCount > 0) {
      const unavailableIndicator = document.createElement('span');
      unavailableIndicator.className = 'status-summary-item status-unavailable';
      unavailableIndicator.textContent = `${unavailableCount} unavailable`;
      unavailableIndicator.setAttribute('title', `${unavailableCount} participants are on leave`);
      statusSummary.appendChild(unavailableIndicator);
    }
    
    if (offlineCount > 0) {
      const offlineIndicator = document.createElement('span');
      offlineIndicator.className = 'status-summary-item status-offline';
      offlineIndicator.textContent = `${offlineCount} offline`;
      offlineIndicator.setAttribute('title', `${offlineCount} participants are offline`);
      statusSummary.appendChild(offlineIndicator);
    }
    
    // Add the summary to the participant list element
    participantListElement.appendChild(statusSummary);
    
  } catch (error) {
    console.warn('Could not add participant status summary to room:', error);
  }
}

function closeParticipantInfoModal() {
  const modal = document.getElementById('participant-info-modal');
  if (modal) {
    modal.remove();
  }
  document.removeEventListener('keydown', handleParticipantModalKeydown);
}

function handleParticipantModalKeydown(e) {
  if (e.key === 'Escape') {
    closeParticipantInfoModal();
  }
}

// Performance monitoring and display functions
function showPerformanceIndicator(duration, operation) {
  // Only show for significant operations
  if (duration < 50) return;
  
  const indicator = document.getElementById('chat-performance-indicator') || createPerformanceIndicator();
  
  const isSlowOperation = duration > 100;
  indicator.className = `performance-indicator visible ${isSlowOperation ? 'slow' : 'fast'}`;
  indicator.textContent = `${operation}: ${duration.toFixed(1)}ms`;
  
  // Auto-hide after 3 seconds
  setTimeout(() => {
    indicator.classList.remove('visible');
  }, 3000);
}

function createPerformanceIndicator() {
  const indicator = document.createElement('div');
  indicator.id = 'chat-performance-indicator';
  indicator.className = 'performance-indicator';
  
  const chatContainer = document.querySelector('.chat-client-body');
  if (chatContainer) {
    chatContainer.style.position = 'relative';
    chatContainer.appendChild(indicator);
  }
  
  return indicator;
}

function logPerformanceMetrics() {
  const metrics = chatState.performanceMetrics;
  if (metrics.renderTimes.length === 0) return;
  
  const recentMetrics = metrics.renderTimes.slice(-10);
  const avgTime = recentMetrics.reduce((sum, m) => sum + m.duration, 0) / recentMetrics.length;
  const maxTime = Math.max(...recentMetrics.map(m => m.duration));
  const minTime = Math.min(...recentMetrics.map(m => m.duration));
  
  console.group('Chat Performance Metrics');
  console.log(`Average render time: ${avgTime.toFixed(2)}ms`);
  console.log(`Max render time: ${maxTime.toFixed(2)}ms`);
  console.log(`Min render time: ${minTime.toFixed(2)}ms`);
  console.log(`Total scroll events: ${metrics.scrollEvents}`);
  console.log(`Virtual scrolling enabled: ${chatState.virtualScrolling.enabled}`);
  console.log(`Pagination enabled: ${chatState.pagination.enabled}`);
  console.log(`Render cache size: ${chatState.renderCache.size}`);
  console.groupEnd();
}

function optimizeRenderingBasedOnMetrics() {
  const metrics = chatState.performanceMetrics;
  const messageCount = chatState.currentMessages.length;
  
  // Auto-enable optimizations based on performance
  if (metrics.averageRenderTime > 100 && messageCount > 50) {
    if (!chatState.virtualScrolling.enabled && !chatState.pagination.enabled) {
      console.log('Auto-enabling performance optimizations due to slow rendering');
      // Re-render with optimizations
      renderMessageThread();
    }
  }
  
  // Adjust virtual scrolling parameters based on performance
  if (chatState.virtualScrolling.enabled) {
    if (metrics.averageRenderTime > 50) {
      // Reduce render buffer for better performance
      chatState.virtualScrolling.renderBuffer = Math.max(2, chatState.virtualScrolling.renderBuffer - 1);
    } else if (metrics.averageRenderTime < 20) {
      // Increase render buffer for smoother scrolling
      chatState.virtualScrolling.renderBuffer = Math.min(10, chatState.virtualScrolling.renderBuffer + 1);
    }
  }
}

// Helper functions
function formatMessageTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffHours = diffMs / (1000 * 60 * 60);
  
  if (diffHours < 24) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } else {
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }
}

function formatRelativeTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  
  if (diffMinutes < 1) return 'now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}



function navigateConversationList(direction, currentItem) {
  const allItems = Array.from(document.querySelectorAll('.conversation-item'));
  const currentIndex = allItems.indexOf(currentItem);
  
  if (currentIndex === -1) return;
  
  let nextIndex = currentIndex + direction;
  
  // Wrap around if needed
  if (nextIndex < 0) {
    nextIndex = allItems.length - 1;
  } else if (nextIndex >= allItems.length) {
    nextIndex = 0;
  }
  
  const nextItem = allItems[nextIndex];
  if (nextItem) {
    nextItem.focus();
    nextItem.scrollIntoView({ 
      behavior: 'smooth', 
      block: 'nearest',
      inline: 'nearest'
    });
  }
}

// UI state management functions
function updateChatLoadingState(isLoading) {
  const chatBody = document.querySelector('.chat-client-body');
  if (chatBody) {
    chatBody.classList.toggle('chat-loading', isLoading);
  }
}

function updateMessageViewLoading(isLoading) {
  const messageContent = document.querySelector('.chat-message-content');
  if (messageContent) {
    messageContent.classList.toggle('chat-loading', isLoading);
  }
}

function clearConversationSelection() {
  chatState.selectedConversationSlug = null;
  chatState.selectedConversationType = null;
  
  // Reset performance optimizations for new conversation
  resetPerformanceOptimizations();
  
  saveChatState();
  
  // Clear UI selection
  document.querySelectorAll('.conversation-item').forEach(item => {
    item.classList.remove('selected');
  });
  
  renderMessageViewPlaceholder();
}

function resetPerformanceOptimizations() {
  // Reset virtual scrolling state
  chatState.virtualScrolling.enabled = false;
  chatState.virtualScrolling.scrollTop = 0;
  chatState.virtualScrolling.visibleStart = 0;
  chatState.virtualScrolling.visibleEnd = 0;
  chatState.virtualScrolling.totalItems = 0;
  
  // Reset pagination state
  chatState.pagination.enabled = false;
  chatState.pagination.currentPage = 0;
  chatState.pagination.totalPages = 0;
  chatState.pagination.hasMore = false;
  
  // Clear render cache periodically to prevent memory leaks
  if (chatState.renderCache.size > 100) {
    chatState.renderCache.clear();
  }
  
  // Remove optimization classes from message thread
  const threadEl = document.getElementById('message-thread');
  if (threadEl) {
    threadEl.classList.remove('virtual-scroll-container', 'paginated-container');
  }
}

function renderChatPlaceholder() {
  const roomsList = document.getElementById('chat-rooms-list');
  const dmsList = document.getElementById('chat-dms-list');
  
  if (roomsList) {
    roomsList.innerHTML = '<div style="padding: 16px; text-align: center; color: #64748b;">Select a persona to view conversations</div>';
  }
  
  if (dmsList) {
    dmsList.innerHTML = '';
  }
  
  // Clear any existing selection when showing placeholder
  clearConversationSelection();
}

function renderMessageViewPlaceholder() {
  const threadEl = document.getElementById('message-thread');
  if (!threadEl) return;
  
  threadEl.innerHTML = `
    <div class="message-thread-placeholder">
      <div class="placeholder-icon">💬</div>
      <div class="placeholder-text">
        <h4>No conversation selected</h4>
        <p>Select a conversation from the sidebar to view messages</p>
      </div>
    </div>
  `;
  
  // Clear conversation header
  const titleEl = document.querySelector('.conversation-name');
  const participantListEl = document.querySelector('.participant-list');
  const messageCountEl = document.querySelector('.message-count');
  
  if (titleEl) titleEl.textContent = 'Select a conversation';
  if (participantListEl) participantListEl.textContent = '';
  if (messageCountEl) messageCountEl.textContent = '';
}

function renderChatError(message) {
  const roomsList = document.getElementById('chat-rooms-list');
  const dmsList = document.getElementById('chat-dms-list');
  
  const errorHtml = `
    <div class="conversation-empty error-state">
      <div class="empty-icon" style="color: #dc2626;">⚠️</div>
      <div class="empty-text" style="color: #dc2626;">Connection Error</div>
      <div class="empty-hint">${message}</div>
      <button class="retry-btn secondary" onclick="handleChatRefresh()" style="margin-top: 12px;">
        <span aria-hidden="true">🔄</span> Retry
      </button>
    </div>
  `;
  
  if (roomsList) roomsList.innerHTML = errorHtml;
  if (dmsList) dmsList.innerHTML = errorHtml;
  
  // Also clear the message view
  renderMessageViewError('Unable to load conversations');
}

function renderMessageViewError(message) {
  const threadEl = document.getElementById('message-thread');
  if (!threadEl) return;
  
  threadEl.innerHTML = `
    <div class="message-thread-placeholder error-state">
      <div class="placeholder-icon" style="color: #dc2626;">⚠️</div>
      <div class="placeholder-text">
        <h4 style="color: #dc2626;">Error loading messages</h4>
        <p>${message}</p>
        <button class="retry-btn secondary" onclick="handleMessageRefresh()" style="margin-top: 12px;">
          <span aria-hidden="true">🔄</span> Retry
        </button>
      </div>
    </div>
  `;
}

// Refresh conversation list without full tab refresh
async function refreshChatConversations() {
  if (!chatMonitorPersonId) return;
  
  try {
    // Fetch conversation data from multiple endpoints
    const persona = people_cache.find(p => p.id === chatMonitorPersonId);
    if (!persona || !persona.chat_handle) {
      throw new Error('Selected persona does not have a chat handle');
    }
    
    // Fetch user's rooms and DM messages in parallel
    const [roomsData, messagesData] = await Promise.all([
      fetchUserRooms(persona.chat_handle),
      fetchJson(`${API_PREFIX}/monitor/chat/messages/${chatMonitorPersonId}?scope=all&limit=100`)
    ]);
    
    // Process and organize conversation data
    const previousRoomsCount = chatState.conversations.rooms.length;
    const previousDmsCount = chatState.conversations.dms.length;
    
    chatState.conversations.rooms = await processRoomConversations(roomsData, messagesData.rooms || []);
    chatState.conversations.dms = processDMConversations(messagesData.dms || []);
    chatState.lastRefresh = new Date();
    
    // Update conversation sidebar with new message indicators
    await renderConversationSidebar();
    
    // Restore conversation selection if it still exists
    if (chatState.selectedConversationSlug) {
      const selectedItem = document.querySelector(`[data-conversation-slug="${chatState.selectedConversationSlug}"]`);
      if (selectedItem) {
        selectedItem.classList.add('selected');
      }
    }
    
    // Show visual indicator if new conversations appeared
    const newRoomsCount = chatState.conversations.rooms.length;
    const newDmsCount = chatState.conversations.dms.length;
    
    if (newRoomsCount > previousRoomsCount || newDmsCount > previousDmsCount) {
      // Flash the sidebar to indicate new conversations
      const sidebar = document.querySelector('.chat-sidebar');
      if (sidebar) {
        sidebar.classList.add('new-content-flash');
        setTimeout(() => sidebar.classList.remove('new-content-flash'), 1000);
      }
    }
    
  } catch (err) {
    console.error('Failed to refresh conversations:', err);
  }
}

async function refreshSelectedConversation() {
  if (!chatState.selectedConversationSlug) return;
  
  const startTime = startPerformanceTimer();
  
  const conversation = [...chatState.conversations.rooms, ...chatState.conversations.dms]
    .find(c => c.slug === chatState.selectedConversationSlug);
  
  if (conversation) {
    // Store current message count to detect new messages
    const previousMessageCount = chatState.currentMessages.length;
    
    // Load messages without showing full loading state (for auto-refresh)
    await loadConversationMessages(conversation, { silent: true });
    
    // Update message refresh timestamp
    const messageRefreshEl = document.getElementById('chat-message-last-refresh');
    if (messageRefreshEl) {
      messageRefreshEl.textContent = new Date().toLocaleTimeString();
    }
    
    // Show new message indicator if messages were added
    const newMessageCount = chatState.currentMessages.length;
    if (newMessageCount > previousMessageCount) {
      showNewMessageIndicator(newMessageCount - previousMessageCount);
    }
    
    // Check if we should optimize rendering based on performance
    optimizeRenderingBasedOnMetrics();
  }
  
  const duration = endPerformanceTimer(startTime, 'refreshSelectedConversation');
  showPerformanceIndicator(duration, 'Refresh');
}

// Enhanced manual refresh handlers with improved loading states and error handling
async function handleChatRefresh() {
  const refreshBtn = document.getElementById('chat-refresh-btn');
  const statusEl = document.getElementById('chat-last-refresh');
  
  // Prevent multiple simultaneous refresh operations
  if (chatState.isLoading || refreshBtn.disabled) {
    return;
  }
  
  // Update button state to show loading
  const originalBtnText = refreshBtn.innerHTML;
  refreshBtn.disabled = true;
  refreshBtn.innerHTML = '<span aria-hidden="true">⟳</span> Refreshing...';
  refreshBtn.classList.add('loading');
  
  // Update status indicator
  if (statusEl) {
    statusEl.textContent = 'Refreshing conversations...';
    statusEl.classList.add('refreshing');
  }
  
  try {
    // Perform the refresh operation
    await refreshChatTab();
    
    // Show success feedback
    if (statusEl) {
      statusEl.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
      statusEl.classList.remove('refreshing');
      statusEl.classList.add('success');
      
      // Remove success class after a short delay
      setTimeout(() => {
        statusEl.classList.remove('success');
      }, 2000);
    }
    
  } catch (error) {
    console.error('Chat refresh failed:', error);
    
    // Show error feedback with retry option
    if (statusEl) {
      statusEl.textContent = 'Refresh failed - Click to retry';
      statusEl.classList.remove('refreshing');
      statusEl.classList.add('error');
      
      // Make status clickable for retry
      statusEl.style.cursor = 'pointer';
      const retryHandler = () => {
        statusEl.style.cursor = '';
        statusEl.classList.remove('error');
        statusEl.removeEventListener('click', retryHandler);
        handleChatRefresh();
      };
      statusEl.addEventListener('click', retryHandler);
    }
    
    // Show user-friendly error message
    renderChatError('Failed to refresh conversations. Please check your connection and try again.');
    
  } finally {
    // Restore button state
    refreshBtn.disabled = false;
    refreshBtn.innerHTML = originalBtnText;
    refreshBtn.classList.remove('loading');
  }
}

async function handleMessageRefresh() {
  const refreshBtn = document.getElementById('message-refresh-btn');
  const statusEl = document.getElementById('chat-message-last-refresh');
  
  // Only refresh if we have a selected conversation
  if (!chatState.selectedConversationSlug) {
    return;
  }
  
  // Prevent multiple simultaneous refresh operations
  if (refreshBtn.disabled) {
    return;
  }
  
  // Update button state to show loading
  const originalBtnText = refreshBtn.innerHTML;
  refreshBtn.disabled = true;
  refreshBtn.innerHTML = '⟳';
  refreshBtn.classList.add('loading');
  
  // Update status indicator
  if (statusEl) {
    statusEl.textContent = 'Refreshing...';
  }
  
  try {
    // Find the current conversation
    const conversation = [...chatState.conversations.rooms, ...chatState.conversations.dms]
      .find(c => c.slug === chatState.selectedConversationSlug);
    
    if (conversation) {
      // Store current message count to detect new messages
      const previousMessageCount = chatState.currentMessages.length;
      
      // Refresh the selected conversation messages
      await loadConversationMessages(conversation, { silent: true });
      
      // Show success feedback
      if (statusEl) {
        statusEl.textContent = new Date().toLocaleTimeString();
      }
      
      // Show new message indicator if messages were added
      const newMessageCount = chatState.currentMessages.length;
      if (newMessageCount > previousMessageCount) {
        showNewMessageIndicator(newMessageCount - previousMessageCount);
      }
      
      // Announce to screen readers
      announceToScreenReader(`Messages refreshed. ${chatState.currentMessages.length} total messages.`);
      
    } else {
      throw new Error('Selected conversation not found');
    }
    
  } catch (error) {
    console.error('Message refresh failed:', error);
    
    // Show error feedback
    if (statusEl) {
      statusEl.textContent = 'Refresh failed';
    }
    
    // Show user-friendly error message
    renderMessageViewError('Failed to refresh messages. Please try again.');
    
    // Announce error to screen readers
    announceToScreenReader('Failed to refresh messages. Please try again.');
    
  } finally {
    // Restore button state
    refreshBtn.disabled = false;
    refreshBtn.innerHTML = originalBtnText;
    refreshBtn.classList.remove('loading');
  }
}

// Helper function to announce messages to screen readers
function announceToScreenReader(message) {
  // Create a temporary element for screen reader announcements
  const announcement = document.createElement('div');
  announcement.setAttribute('aria-live', 'polite');
  announcement.setAttribute('aria-atomic', 'true');
  announcement.className = 'sr-only';
  announcement.textContent = message;
  
  document.body.appendChild(announcement);
  
  // Remove after announcement
  setTimeout(() => {
    document.body.removeChild(announcement);
  }, 1000);
}

// Performance optimization: Cleanup email caches periodically
function cleanupEmailCaches() {
  // Limit cache sizes to prevent memory leaks
  if (emailRenderCache.size > 200) {
    // Keep only the most recent 100 entries
    const entries = Array.from(emailRenderCache.entries());
    emailRenderCache.clear();
    entries.slice(-100).forEach(([key, value]) => {
      emailRenderCache.set(key, value);
    });
  }
  
  if (emailSortCache.size > 50) {
    // Keep only the most recent 25 entries
    const entries = Array.from(emailSortCache.entries());
    emailSortCache.clear();
    entries.slice(-25).forEach(([key, value]) => {
      emailSortCache.set(key, value);
    });
  }
}

async function handleMessageRefresh() {
  const refreshBtn = document.getElementById('message-refresh-btn');
  const statusEl = document.getElementById('chat-message-last-refresh');
  
  // Check if we have a selected conversation
  if (!chatState.selectedConversationSlug) {
    return;
  }
  
  // Prevent multiple simultaneous refresh operations
  if (chatState.isLoading || refreshBtn.disabled) {
    return;
  }
  
  // Update button state to show loading
  const originalBtnText = refreshBtn.innerHTML;
  refreshBtn.disabled = true;
  refreshBtn.innerHTML = '⟳';
  refreshBtn.classList.add('loading');
  refreshBtn.setAttribute('aria-label', 'Refreshing messages...');
  
  // Show loading state for message view
  updateMessageViewLoading(true);
  
  try {
    // Perform the refresh operation
    await refreshSelectedConversation();
    
    // Show success feedback
    if (statusEl) {
      statusEl.textContent = new Date().toLocaleTimeString();
      statusEl.classList.add('success');
      
      // Remove success class after a short delay
      setTimeout(() => {
        statusEl.classList.remove('success');
      }, 1500);
    }
    
  } catch (error) {
    console.error('Message refresh failed:', error);
    
    // Show error feedback
    if (statusEl) {
      statusEl.textContent = 'Refresh failed';
      statusEl.classList.add('error');
      
      // Remove error class after a delay
      setTimeout(() => {
        statusEl.classList.remove('error');
      }, 3000);
    }
    
    // Show error in message view
    renderMessageViewError('Failed to refresh messages. Please try again.');
    
  } finally {
    // Restore button state
    refreshBtn.disabled = false;
    refreshBtn.innerHTML = originalBtnText;
    refreshBtn.classList.remove('loading');
    refreshBtn.setAttribute('aria-label', 'Refresh messages');
    
    // Remove loading state
    updateMessageViewLoading(false);
  }
}

// Show new message indicator when messages are added during refresh
function showNewMessageIndicator(newMessageCount) {
  const messageThread = document.getElementById('message-thread');
  if (!messageThread) return;
  
  // Create and show new message indicator
  const indicator = document.createElement('div');
  indicator.className = 'new-message-indicator';
  indicator.innerHTML = `
    <span class="new-message-text">
      ${newMessageCount} new message${newMessageCount > 1 ? 's' : ''}
    </span>
  `;
  
  // Position indicator at the bottom of the message thread
  indicator.style.position = 'absolute';
  indicator.style.bottom = '16px';
  indicator.style.left = '50%';
  indicator.style.transform = 'translateX(-50%)';
  indicator.style.zIndex = '20';
  
  messageThread.style.position = 'relative';
  messageThread.appendChild(indicator);
  
  // Auto-scroll to bottom to show new messages
  messageThread.scrollTop = messageThread.scrollHeight;
  
  // Remove indicator after 3 seconds
  setTimeout(() => {
    if (indicator.parentNode) {
      indicator.parentNode.removeChild(indicator);
    }
  }, 3000);
}

// Legacy function for backward compatibility
function renderChatList(containerId, items) {
  // This function is kept for backward compatibility but the new implementation
  // uses renderConversationSection instead
  console.warn('renderChatList is deprecated, use renderConversationSection instead');
}

// Bind tab buttons
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.tab-button');
  if (!btn) return;
  setActiveTab(btn.dataset.tab);
});

// Global keyboard shortcuts for email interface
document.addEventListener('keydown', (e) => {
  // Only handle shortcuts when emails tab is active
  const emailsTab = document.getElementById('tab-emails');
  if (!emailsTab || emailsTab.style.display === 'none') return;
  
  // Don't interfere with form inputs
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
    return;
  }
  
  switch (e.key.toLowerCase()) {
    case 'r':
      // Refresh emails (force refresh to bypass cache)
      e.preventDefault();
      refreshEmailsTab(true);
      announceToScreenReader('Refreshing emails');
      break;
      
    case 'i':
      // Switch to Inbox
      e.preventDefault();
      if (emailFolder !== 'inbox') {
        emailFolder = 'inbox';
        renderEmailPanels();
        announceToScreenReader('Switched to Inbox');
        // Update folder button focus
        const inboxBtn = document.getElementById('email-folder-inbox');
        if (inboxBtn) {
          inboxBtn.focus();
        }
      }
      break;
      
    case 's':
      // Switch to Sent (only if not Ctrl+S for save)
      if (!e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        if (emailFolder !== 'sent') {
          emailFolder = 'sent';
          renderEmailPanels();
          announceToScreenReader('Switched to Sent folder');
          // Update folder button focus
          const sentBtn = document.getElementById('email-folder-sent');
          if (sentBtn) {
            sentBtn.focus();
          }
        }
      }
      break;
      
    case '/':
      // Focus search input
      e.preventDefault();
      const searchInputElement = document.getElementById('email-search');
      if (searchInputElement) {
        searchInputElement.focus();
        announceToScreenReader('Search focused');
      }
      break;
      
    case 'escape':
      // Clear email selection and return focus to list, or clear search if search is focused
      e.preventDefault();
      const activeElement = document.activeElement;
      const searchInputEl = document.getElementById('email-search');
      
      if (activeElement === searchInputEl && searchInputEl.value.trim()) {
        // Clear search if search input is focused and has content
        searchInputEl.value = '';
        handleEmailSearch('');
        const searchClear = document.getElementById('email-search-clear');
        if (searchClear) {
          searchClear.style.display = 'none';
        }
        const emailList = document.getElementById('email-list');
        if (emailList) {
          emailList.classList.remove('searching');
        }
        announceToScreenReader('Search cleared');
      } else {
        // Clear email selection and return focus to list
        emailSelected.id = null;
        emailListFocusIndex = -1;
        renderEmailPanels();
        const emailList = document.getElementById('email-list');
        if (emailList) {
          emailList.focus();
        }
        announceToScreenReader('Email selection cleared');
      }
      break;
  }
});

// Global keyboard shortcuts for chat interface
document.addEventListener('keydown', async (e) => {
  // Only handle shortcuts when chat tab is active
  const chatTab = document.getElementById('tab-chat');
  if (!chatTab || chatTab.style.display === 'none') return;
  
  // Don't interfere with form inputs
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
    return;
  }
  
  switch (e.key.toLowerCase()) {
    case 'r':
      // Refresh chat conversations
      e.preventDefault();
      handleChatRefresh();
      announceToScreenReader('Refreshing chat conversations');
      break;
      
    case 'm':
      // Refresh current message thread
      e.preventDefault();
      if (chatState.selectedConversationSlug) {
        handleMessageRefresh();
        announceToScreenReader('Refreshing messages');
      }
      break;
      
    case '/':
      // Focus conversation search input
      e.preventDefault();
      const chatSearchInput = document.getElementById('chat-search');
      if (chatSearchInput) {
        chatSearchInput.focus();
        announceToScreenReader('Conversation search focused');
      }
      break;
      
    case 'escape':
      // Clear conversation selection or search
      e.preventDefault();
      const activeElement = document.activeElement;
      const searchInput = document.getElementById('chat-search');
      const messageSearch = document.getElementById('message-search');
      
      if (activeElement === searchInput && searchInput.value.trim()) {
        // Clear conversation search
        searchInput.value = '';
        const clearBtn = document.getElementById('chat-search-clear');
        if (clearBtn) {
          clearBtn.style.display = 'none';
        }
        // Trigger search to show all conversations
        chatState.searchQuery = '';
        await renderConversationSidebar();
        announceToScreenReader('Conversation search cleared');
      } else if (activeElement === messageSearch && messageSearch.value.trim()) {
        // Clear message search
        messageSearch.value = '';
        announceToScreenReader('Message search cleared');
      } else {
        // Clear conversation selection
        clearConversationSelection();
        announceToScreenReader('Conversation selection cleared');
      }
      break;
  }
});

// Performance optimization: Memory management and cache cleanup
function cleanupEmailCaches() {
  const MAX_RENDER_CACHE_SIZE = 200;
  const MAX_SORT_CACHE_SIZE = 50;
  
  // Clean up render cache if it gets too large
  if (emailRenderCache.size > MAX_RENDER_CACHE_SIZE) {
    const entries = Array.from(emailRenderCache.entries());
    // Keep only the most recent half
    const keepEntries = entries.slice(-Math.floor(MAX_RENDER_CACHE_SIZE / 2));
    emailRenderCache.clear();
    keepEntries.forEach(([key, value]) => emailRenderCache.set(key, value));
  }
  
  // Clean up sort cache if it gets too large
  if (emailSortCache.size > MAX_SORT_CACHE_SIZE) {
    const entries = Array.from(emailSortCache.entries());
    // Keep only the most recent half
    const keepEntries = entries.slice(-Math.floor(MAX_SORT_CACHE_SIZE / 2));
    emailSortCache.clear();
    keepEntries.forEach(([key, value]) => emailSortCache.set(key, value));
  }
}

// Helper function to announce messages to screen readers
function announceToScreenReader(message) {
  const announcement = document.createElement('div');
  announcement.setAttribute('aria-live', 'assertive');
  announcement.setAttribute('aria-atomic', 'true');
  announcement.className = 'sr-only';
  announcement.textContent = message;
  
  document.body.appendChild(announcement);
  
  // Remove the announcement after a short delay
  setTimeout(() => {
    if (document.body.contains(announcement)) {
      document.body.removeChild(announcement);
    }
  }, 1000);
}

// Folder toggle events (bound after DOM ready)
document.addEventListener('DOMContentLoaded', () => {
  // Optional URL parameters for debugging/testing:
  //   ?tab=emails&folder=sent&open=first&persona=ID
  try {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    const folder = params.get('folder');
    const open = params.get('open');
    const persona = params.get('persona');
    if (tab === 'emails') {
      setActiveTab('emails');
    }
    if (folder === 'sent') {
      emailFolder = 'sent';
    }
    if (open === 'first') {
      emailAutoOpenFirst = true;
    }
    if (persona) {
      const idNum = Number(persona);
      if (!Number.isNaN(idNum)) {
        emailMonitorPersonId = idNum;
      }
    }
  } catch (e) {
    // ignore
  }
  
  // Set up email search functionality
  const searchInput = document.getElementById('email-search');
  const searchClear = document.getElementById('email-search-clear');
  
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const query = e.target.value;
      handleEmailSearch(query);
      
      // Show/hide clear button
      if (searchClear) {
        searchClear.style.display = query.trim() ? 'block' : 'none';
      }
      
      // Add searching class for visual feedback
      const emailList = document.getElementById('email-list');
      if (emailList) {
        emailList.classList.toggle('searching', query.trim().length > 0);
      }
    });
    
    // Handle search shortcuts
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        searchInput.value = '';
        handleEmailSearch('');
        if (searchClear) {
          searchClear.style.display = 'none';
        }
        const emailList = document.getElementById('email-list');
        if (emailList) {
          emailList.classList.remove('searching');
          emailList.focus();
        }
      }
    });
  }
  
  if (searchClear) {
    searchClear.addEventListener('click', () => {
      if (searchInput) {
        searchInput.value = '';
        handleEmailSearch('');
        searchInput.focus();
      }
      searchClear.style.display = 'none';
      const emailList = document.getElementById('email-list');
      if (emailList) {
        emailList.classList.remove('searching');
      }
    });
  }
  const inboxBtn = document.getElementById('email-folder-inbox');
  const sentBtn = document.getElementById('email-folder-sent');
  const refreshBtn = document.getElementById('email-refresh-btn');
  
  if (inboxBtn) {
    inboxBtn.addEventListener('click', () => { 
      emailFolder = 'inbox'; 
      updateFolderButtonStates();
      renderEmailPanels(); 
      announceToScreenReader('Switched to Inbox');
    });
    
    inboxBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        inboxBtn.click();
      }
    });
  }
  
  if (sentBtn) {
    sentBtn.addEventListener('click', () => { 
      emailFolder = 'sent'; 
      updateFolderButtonStates();
      renderEmailPanels(); 
      announceToScreenReader('Switched to Sent folder');
    });
    
    sentBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        sentBtn.click();
      }
    });
  }
  
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      refreshEmailsTab();
      announceToScreenReader('Refreshing emails');
    });
  }
  
  // Set up chat interface event handlers
  setupChatEventHandlers();
});

function setupChatEventHandlers() {
  // Chat search functionality
  const chatSearchInput = document.getElementById('chat-search');
  const chatSearchClear = document.getElementById('chat-search-clear');
  
  if (chatSearchInput) {
    chatSearchInput.addEventListener('input', async (e) => {
      const query = e.target.value;
      chatState.searchQuery = query;
      
      // Show/hide clear button
      if (chatSearchClear) {
        chatSearchClear.style.display = query.trim() ? 'block' : 'none';
      }
      
      // Re-render conversation sidebar with filtered results
      await renderConversationSidebar();
    });
    
    chatSearchInput.addEventListener('keydown', async (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        chatSearchInput.value = '';
        chatState.searchQuery = '';
        if (chatSearchClear) {
          chatSearchClear.style.display = 'none';
        }
        await renderConversationSidebar();
      }
    });
  }
  
  if (chatSearchClear) {
    chatSearchClear.addEventListener('click', async () => {
      if (chatSearchInput) {
        chatSearchInput.value = '';
        chatState.searchQuery = '';
        chatSearchInput.focus();
      }
      chatSearchClear.style.display = 'none';
      await renderConversationSidebar();
    });
  }
  
  // Message search functionality
  const messageSearchInput = document.getElementById('message-search');
  if (messageSearchInput) {
    let messageSearchTimeout = null;
    
    messageSearchInput.addEventListener('input', (e) => {
      const query = e.target.value;
      chatState.messageSearchQuery = query;
      
      // Debounce search to avoid excessive re-rendering
      clearTimeout(messageSearchTimeout);
      messageSearchTimeout = setTimeout(() => {
        performMessageSearch(query);
      }, 300);
    });
    
    // Handle keyboard shortcuts for message search
    messageSearchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (e.shiftKey) {
          navigateToSearchResult('previous');
        } else {
          navigateToSearchResult('next');
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        clearMessageSearch();
        messageSearchInput.blur();
      }
    });
  }
  
  // Chat refresh button
  const chatRefreshBtn = document.getElementById('chat-refresh-btn');
  if (chatRefreshBtn) {
    chatRefreshBtn.addEventListener('click', async () => {
      await handleChatRefresh();
    });
  }
  
  // Message refresh button
  const messageRefreshBtn = document.getElementById('message-refresh-btn');
  if (messageRefreshBtn) {
    messageRefreshBtn.addEventListener('click', async () => {
      await handleMessageRefresh();
    });
  }
}

// Update folder button ARIA states
function updateFolderButtonStates() {
  const inboxBtn = document.getElementById('email-folder-inbox');
  const sentBtn = document.getElementById('email-folder-sent');
  
  if (inboxBtn && sentBtn) {
    const isInbox = emailFolder === 'inbox';
    
    inboxBtn.setAttribute('aria-selected', isInbox.toString());
    inboxBtn.setAttribute('tabindex', isInbox ? '0' : '-1');
    inboxBtn.classList.toggle('active', isInbox);
    
    sentBtn.setAttribute('aria-selected', (!isInbox).toString());
    sentBtn.setAttribute('tabindex', isInbox ? '-1' : '0');
    sentBtn.classList.toggle('active', !isInbox);
  }
}

// ===== RESPONSIVE CHAT SIDEBAR FUNCTIONALITY =====

// Chat responsive sidebar state
let chatSidebarState = {
  isOpen: false,
  isMobile: false,
  isTablet: false,
  mediaQueryListeners: []
};

function setupChatResponsiveSidebar() {
  // Check if already initialized to avoid duplicate setup
  if (chatSidebarState.mediaQueryListeners.length > 0) {
    return;
  }
  
  // Create sidebar toggle button if it doesn't exist
  createChatSidebarToggle();
  
  // Create sidebar overlay if it doesn't exist
  createChatSidebarOverlay();
  
  // Setup media query listeners for responsive behavior
  setupChatMediaQueries();
  
  // Setup event handlers
  setupChatSidebarEventHandlers();
  
  // Initial responsive state check
  updateChatResponsiveState();
}

function createChatSidebarToggle() {
  // Check if toggle button already exists
  if (document.getElementById('chat-sidebar-toggle')) {
    return;
  }
  
  const chatHeader = document.querySelector('.chat-client-header .chat-client-actions');
  if (!chatHeader) return;
  
  const toggleButton = document.createElement('button');
  toggleButton.id = 'chat-sidebar-toggle';
  toggleButton.className = 'chat-sidebar-toggle';
  toggleButton.setAttribute('aria-label', 'Toggle conversation sidebar');
  toggleButton.setAttribute('aria-expanded', 'false');
  toggleButton.innerHTML = `
    <span class="toggle-icon" aria-hidden="true">☰</span>
    <span class="sr-only">Toggle Sidebar</span>
  `;
  
  // Insert at the beginning of chat actions
  chatHeader.insertBefore(toggleButton, chatHeader.firstChild);
}

function createChatSidebarOverlay() {
  // Check if overlay already exists
  if (document.getElementById('chat-sidebar-overlay')) {
    return;
  }
  
  const chatLayout = document.querySelector('.chat-client-layout');
  if (!chatLayout) return;
  
  const overlay = document.createElement('div');
  overlay.id = 'chat-sidebar-overlay';
  overlay.className = 'chat-sidebar-overlay';
  overlay.setAttribute('aria-hidden', 'true');
  
  // Insert overlay as first child of chat layout
  chatLayout.insertBefore(overlay, chatLayout.firstChild);
}

function setupChatMediaQueries() {
  // Define breakpoints
  const mediaQueries = [
    { query: '(max-width: 768px)', type: 'mobile' },
    { query: '(min-width: 769px) and (max-width: 1024px)', type: 'tablet' },
    { query: '(min-width: 1025px)', type: 'desktop' }
  ];
  
  mediaQueries.forEach(({ query, type }) => {
    const mediaQuery = window.matchMedia(query);
    
    const handler = (e) => {
      if (e.matches) {
        chatSidebarState.isMobile = type === 'mobile';
        chatSidebarState.isTablet = type === 'tablet';
        updateChatResponsiveState();
      }
    };
    
    // Add listener
    mediaQuery.addListener(handler);
    chatSidebarState.mediaQueryListeners.push({ mediaQuery, handler });
    
    // Initial check
    handler(mediaQuery);
  });
}

function setupChatSidebarEventHandlers() {
  const toggleButton = document.getElementById('chat-sidebar-toggle');
  const overlay = document.getElementById('chat-sidebar-overlay');
  
  if (toggleButton) {
    toggleButton.addEventListener('click', toggleChatSidebar);
    
    // Keyboard support
    toggleButton.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleChatSidebar();
      }
    });
  }
  
  if (overlay) {
    overlay.addEventListener('click', closeChatSidebar);
    
    // Touch support for mobile
    overlay.addEventListener('touchstart', closeChatSidebar, { passive: true });
  }
  
  // Handle escape key to close sidebar
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && chatSidebarState.isOpen && (chatSidebarState.isMobile || chatSidebarState.isTablet)) {
      closeChatSidebar();
    }
  });
  
  // Handle window resize
  window.addEventListener('resize', debounce(updateChatResponsiveState, 250));
}

function updateChatResponsiveState() {
  const chatLayout = document.querySelector('.chat-client-layout');
  const toggleButton = document.getElementById('chat-sidebar-toggle');
  const overlay = document.getElementById('chat-sidebar-overlay');
  
  if (!chatLayout) return;
  
  // Remove all responsive classes
  chatLayout.classList.remove('sidebar-collapsed', 'sidebar-open');
  
  if (toggleButton) {
    if (chatSidebarState.isMobile || chatSidebarState.isTablet) {
      // Show toggle button for mobile and tablet
      toggleButton.style.display = 'inline-flex';
      
      // On mobile/tablet, sidebar starts collapsed
      if (!chatSidebarState.isOpen) {
        chatLayout.classList.add('sidebar-collapsed');
      } else {
        chatLayout.classList.add('sidebar-open');
      }
      
      // Update button state
      toggleButton.setAttribute('aria-expanded', chatSidebarState.isOpen.toString());
      toggleButton.classList.toggle('sidebar-open', chatSidebarState.isOpen);
      
      // Update overlay
      if (overlay) {
        overlay.classList.toggle('active', chatSidebarState.isOpen);
        overlay.setAttribute('aria-hidden', (!chatSidebarState.isOpen).toString());
      }
    } else {
      // Hide toggle button for desktop
      toggleButton.style.display = 'none';
      chatSidebarState.isOpen = false;
      
      // Hide overlay on desktop
      if (overlay) {
        overlay.classList.remove('active');
        overlay.setAttribute('aria-hidden', 'true');
      }
    }
  }
  
  // Handle body scroll lock for mobile sidebar
  if (chatSidebarState.isMobile) {
    if (chatSidebarState.isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  } else {
    document.body.style.overflow = '';
  }
}

function toggleChatSidebar() {
  if (chatSidebarState.isMobile || chatSidebarState.isTablet) {
    chatSidebarState.isOpen = !chatSidebarState.isOpen;
    updateChatResponsiveState();
    
    // Announce state change to screen readers
    const toggleButton = document.getElementById('chat-sidebar-toggle');
    if (toggleButton) {
      const message = chatSidebarState.isOpen ? 'Sidebar opened' : 'Sidebar closed';
      announceToScreenReader(message);
    }
    
    // Focus management
    if (chatSidebarState.isOpen) {
      // Focus the search input when sidebar opens
      setTimeout(() => {
        const searchInput = document.getElementById('chat-search');
        if (searchInput) {
          searchInput.focus();
        }
      }, 300); // Wait for animation to complete
    }
  }
}

function openChatSidebar() {
  if (!chatSidebarState.isOpen && (chatSidebarState.isMobile || chatSidebarState.isTablet)) {
    chatSidebarState.isOpen = true;
    updateChatResponsiveState();
  }
}

function closeChatSidebar() {
  if (chatSidebarState.isOpen && (chatSidebarState.isMobile || chatSidebarState.isTablet)) {
    chatSidebarState.isOpen = false;
    updateChatResponsiveState();
    
    // Return focus to toggle button
    const toggleButton = document.getElementById('chat-sidebar-toggle');
    if (toggleButton) {
      toggleButton.focus();
    }
  }
}

// Enhanced conversation selection for mobile - auto-close sidebar
function selectConversationResponsive(conversation) {
  // Call the original selectConversation function
  selectConversation(conversation);
  
  // Auto-close sidebar on mobile after selection
  if (chatSidebarState.isMobile && chatSidebarState.isOpen) {
    setTimeout(() => {
      closeChatSidebar();
    }, 300); // Small delay for better UX
  }
}

// Override the original selectConversation for responsive behavior
const originalSelectConversation = selectConversation;
selectConversation = function(conversation) {
  // Call original function
  originalSelectConversation.call(this, conversation);
  
  // Add responsive behavior
  if (chatSidebarState.isMobile && chatSidebarState.isOpen) {
    setTimeout(() => {
      closeChatSidebar();
    }, 300);
  }
};

// Touch gesture support for mobile sidebar
function setupChatTouchGestures() {
  const sidebar = document.querySelector('.chat-sidebar-pane');
  if (!sidebar) return;
  
  let touchStartX = 0;
  let touchStartY = 0;
  let isSwiping = false;
  
  sidebar.addEventListener('touchstart', (e) => {
    if (!chatSidebarState.isMobile) return;
    
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    isSwiping = false;
  }, { passive: true });
  
  sidebar.addEventListener('touchmove', (e) => {
    if (!chatSidebarState.isMobile || !chatSidebarState.isOpen) return;
    
    const touchX = e.touches[0].clientX;
    const touchY = e.touches[0].clientY;
    const deltaX = touchX - touchStartX;
    const deltaY = touchY - touchStartY;
    
    // Check if this is a horizontal swipe (more horizontal than vertical)
    if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 10) {
      isSwiping = true;
      
      // Swipe left to close sidebar
      if (deltaX < -50) {
        closeChatSidebar();
      }
    }
  }, { passive: true });
  
  sidebar.addEventListener('touchend', () => {
    isSwiping = false;
  }, { passive: true });
}

// Utility function for debouncing
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Utility function for screen reader announcements
function announceToScreenReader(message) {
  const announcement = document.createElement('div');
  announcement.setAttribute('aria-live', 'polite');
  announcement.setAttribute('aria-atomic', 'true');
  announcement.className = 'sr-only';
  announcement.textContent = message;
  
  document.body.appendChild(announcement);
  
  // Remove after announcement
  setTimeout(() => {
    document.body.removeChild(announcement);
  }, 1000);
}

// Auto-pause toggle function
async function toggleAutoPause() {
  const toggleEl = document.getElementById('auto-pause-toggle');
  if (!toggleEl) return;
  
  const enabled = toggleEl.checked;
  
  try {
    setStatus('Updating auto-pause setting...');
    const result = await fetchJson(`${API_PREFIX}/simulation/auto-pause/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    });
    
    // Update the toggle to reflect the actual server state
    toggleEl.checked = result.auto_pause_enabled;
    
    const statusMsg = result.auto_pause_enabled ? 'Auto-pause enabled' : 'Auto-pause disabled';
    setStatus(statusMsg);
    
    // Update the auto-pause display immediately
    updateAutoPauseDisplay(result);
    
    // Announce change to screen readers
    announceToScreenReader(statusMsg);
    
  } catch (err) {
    // Revert the toggle on error
    toggleEl.checked = !enabled;
    setStatus(err.message || String(err), true);
    announceToScreenReader('Failed to update auto-pause setting');
  }
}

// Toast notification system
let toastContainer = null;
let lastAutoPauseState = null;

function createToastContainer() {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    toastContainer.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 10000;
      display: flex;
      flex-direction: column;
      gap: 10px;
      pointer-events: none;
    `;
    document.body.appendChild(toastContainer);
  }
  return toastContainer;
}

function showToast(message, type = 'info', duration = 5000) {
  const container = createToastContainer();
  
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.style.cssText = `
    background: ${type === 'warning' ? '#f59e0b' : type === 'error' ? '#dc2626' : '#2563eb'};
    color: white;
    padding: 12px 16px;
    border-radius: 6px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    max-width: 350px;
    word-wrap: break-word;
    pointer-events: auto;
    cursor: pointer;
    transition: all 0.3s ease;
    transform: translateX(100%);
    opacity: 0;
  `;
  toast.textContent = message;
  
  // Add close functionality
  toast.addEventListener('click', () => {
    removeToast(toast);
  });
  
  container.appendChild(toast);
  
  // Animate in
  setTimeout(() => {
    toast.style.transform = 'translateX(0)';
    toast.style.opacity = '1';
  }, 10);
  
  // Auto-remove after duration
  setTimeout(() => {
    removeToast(toast);
  }, duration);
  
  // Announce to screen readers
  announceToScreenReader(message);
}

function removeToast(toast) {
  if (toast && toast.parentNode) {
    toast.style.transform = 'translateX(100%)';
    toast.style.opacity = '0';
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300);
  }
}

// Generate detailed warning message for approaching auto-pause conditions
function generateAutoPauseWarningMessage(autoPauseStatus) {
  const activeCount = autoPauseStatus.active_projects_count || 0;
  const futureCount = autoPauseStatus.future_projects_count || 0;
  const currentWeek = autoPauseStatus.current_week || 0;
  
  if (!autoPauseStatus.auto_pause_enabled) {
    return null;
  }
  
  // Critical warning - auto-pause will trigger
  if (autoPauseStatus.should_pause) {
    return {
      level: 'critical',
      title: 'Auto-pause will trigger',
      message: autoPauseStatus.reason || 'All projects have been completed',
      guidance: 'Auto-tick will be automatically disabled. You can restart it manually or add new projects to continue.'
    };
  }
  
  // Warning - no active projects but future projects exist
  if (activeCount === 0 && futureCount > 0) {
    return {
      level: 'warning',
      title: 'No active projects',
      message: `No projects are active in week ${currentWeek}, but ${futureCount} future project${futureCount > 1 ? 's' : ''} scheduled`,
      guidance: 'Simulation will continue until future projects start or complete.'
    };
  }
  
  // Warning - approaching completion
  if (activeCount === 1 && futureCount === 0) {
    return {
      level: 'warning',
      title: 'Last active project',
      message: `Only 1 project remains active in week ${currentWeek}`,
      guidance: 'Auto-pause will trigger when this project completes. Consider adding new projects to continue simulation.'
    };
  }
  
  // Info - low project count
  if (activeCount <= 2 && futureCount === 0) {
    return {
      level: 'info',
      title: 'Few projects remaining',
      message: `${activeCount} project${activeCount > 1 ? 's' : ''} active in week ${currentWeek}`,
      guidance: 'Consider planning additional projects to maintain simulation continuity.'
    };
  }
  
  return null;
}

// Update auto-pause display elements
function updateAutoPauseDisplay(autoPauseStatus) {
  // Check for auto-pause state changes to trigger notifications
  const currentState = {
    enabled: autoPauseStatus.auto_pause_enabled,
    shouldPause: autoPauseStatus.should_pause,
    activeProjects: autoPauseStatus.active_projects_count || 0,
    futureProjects: autoPauseStatus.future_projects_count || 0,
    reason: autoPauseStatus.reason
  };
  
  // Detect auto-pause trigger events
  if (lastAutoPauseState) {
    // Auto-pause was triggered (simulation was paused due to auto-pause)
    if (!lastAutoPauseState.shouldPause && currentState.shouldPause && currentState.enabled) {
      const message = `Auto-pause triggered: ${currentState.reason}`;
      showToast(message, 'warning', 8000);
      
      // Update status message in header
      setStatus(message, false);
      
      console.log('Auto-pause event:', {
        reason: currentState.reason,
        activeProjects: currentState.activeProjects,
        futureProjects: currentState.futureProjects,
        simulationWeek: autoPauseStatus.current_week
      });
    }
    
    // Warning when approaching auto-pause conditions
    else if (currentState.enabled && currentState.activeProjects === 0 && currentState.futureProjects === 0 && 
             (lastAutoPauseState.activeProjects > 0 || lastAutoPauseState.futureProjects > 0)) {
      showToast('Warning: No projects remaining. Auto-pause may trigger soon.', 'warning', 6000);
    }
    
    // Show toast for project count changes that might affect auto-pause
    else if (currentState.enabled && currentState.activeProjects !== lastAutoPauseState.activeProjects) {
      if (currentState.activeProjects === 1 && currentState.futureProjects === 0) {
        showToast('Warning: Only 1 active project remains. Auto-pause will trigger when it completes.', 'warning', 6000);
      } else if (currentState.activeProjects === 0 && currentState.futureProjects > 0) {
        showToast(`Info: No active projects in current week. ${currentState.futureProjects} future project${currentState.futureProjects > 1 ? 's' : ''} scheduled.`, 'info', 5000);
      }
    }
  }
  
  // Store current state for next comparison
  lastAutoPauseState = { ...currentState };
  
  // Update auto-pause toggle to match server state
  const toggleEl = document.getElementById('auto-pause-toggle');
  if (toggleEl) {
    toggleEl.checked = autoPauseStatus.auto_pause_enabled;
  }
  
  // Update status display
  const autoPauseEl = document.getElementById('state-auto-pause');
  if (autoPauseEl) {
    autoPauseEl.textContent = autoPauseStatus.auto_pause_enabled ? 'Enabled' : 'Disabled';
    autoPauseEl.className = autoPauseStatus.auto_pause_enabled ? 'enabled' : 'disabled';
  }
  
  // Update project counts with enhanced warning indicators
  const activeProjectsEl = document.getElementById('state-active-projects');
  if (activeProjectsEl) {
    const count = autoPauseStatus.active_projects_count || 0;
    activeProjectsEl.textContent = count.toString();
    
    // Enhanced warning classes based on project count and auto-pause status
    let className = '';
    if (autoPauseStatus.auto_pause_enabled) {
      if (count === 0) {
        className = 'critical';
      } else if (count === 1 && (autoPauseStatus.future_projects_count || 0) === 0) {
        className = 'warning';
      } else if (count <= 2 && (autoPauseStatus.future_projects_count || 0) === 0) {
        className = 'info';
      }
    }
    activeProjectsEl.className = className;
    
    // Add title attribute for additional context
    if (count === 0) {
      activeProjectsEl.title = 'No active projects - auto-pause may trigger';
    } else if (count === 1) {
      activeProjectsEl.title = 'Last active project - auto-pause will trigger when complete';
    } else {
      activeProjectsEl.title = `${count} active projects in current simulation week`;
    }
  }
  
  const futureProjectsEl = document.getElementById('state-future-projects');
  if (futureProjectsEl) {
    const count = autoPauseStatus.future_projects_count || 0;
    futureProjectsEl.textContent = count.toString();
    
    // Warning class when no future projects and auto-pause enabled
    const className = (count === 0 && autoPauseStatus.auto_pause_enabled && 
                      (autoPauseStatus.active_projects_count || 0) <= 1) ? 'warning' : '';
    futureProjectsEl.className = className;
    
    // Add title attribute for additional context
    if (count === 0) {
      futureProjectsEl.title = 'No future projects scheduled';
    } else {
      futureProjectsEl.title = `${count} project${count > 1 ? 's' : ''} scheduled to start in future weeks`;
    }
  }
  
  // Enhanced warning display with detailed information
  const warningEl = document.getElementById('auto-pause-warning');
  const warningTextEl = document.getElementById('auto-pause-warning-text');
  
  if (warningEl && warningTextEl) {
    const warningInfo = generateAutoPauseWarningMessage(autoPauseStatus);
    
    if (warningInfo) {
      // Update warning panel content with detailed information
      warningTextEl.innerHTML = `
        <strong>${warningInfo.title}</strong><br>
        ${warningInfo.message}<br>
        <small style="opacity: 0.8; font-size: 12px;">${warningInfo.guidance}</small>
      `;
      
      // Update warning panel styling based on severity
      warningEl.className = `auto-pause-warning ${warningInfo.level}`;
      warningEl.style.display = 'flex';
      warningEl.classList.remove('hidden');
      
      // Announce warning to screen readers with full context
      announceToScreenReader(`${warningInfo.title}: ${warningInfo.message}. ${warningInfo.guidance}`);
    } else {
      warningEl.style.display = 'none';
      warningEl.classList.add('hidden');
    }
  }
}

// Initialize touch gestures when chat tab is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Setup touch gestures with a delay to ensure elements are ready
  setTimeout(setupChatTouchGestures, 1000);
});

// Cleanup function for responsive sidebar
function cleanupChatResponsiveSidebar() {
  // Remove media query listeners
  chatSidebarState.mediaQueryListeners.forEach(({ mediaQuery, handler }) => {
    mediaQuery.removeListener(handler);
  });
  chatSidebarState.mediaQueryListeners = [];
  
  // Reset body overflow
  document.body.style.overflow = '';
  
  // Reset sidebar state
  chatSidebarState.isOpen = false;
  chatSidebarState.isMobile = false;
  chatSidebarState.isTablet = false;
}

// Export functions for external use if needed
window.chatResponsiveSidebar = {
  toggle: toggleChatSidebar,
  open: openChatSidebar,
  close: closeChatSidebar,
  cleanup: cleanupChatResponsiveSidebar
};