// VDOS Dashboard JavaScript
const API_PREFIX = '/api/v1';
let selectedPeople = new Set();
let refreshIntervalId = null;
let currentRefreshInterval = 60000; // Start with 1 minute
let isSimulationRunning = false;
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
    setStatus('Simulation started');
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
  if (currentRefreshInterval === intervalMs) {
    return; // No change needed
  }

  currentRefreshInterval = intervalMs;

  // Clear existing interval
  if (refreshIntervalId !== null) {
    clearInterval(refreshIntervalId);
  }

  // Set new interval
  refreshIntervalId = setInterval(refreshAll, intervalMs);
  console.log(`Dashboard refresh interval set to ${intervalMs / 1000}s`);
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
  document.getElementById('persona-generate-btn').addEventListener('click', generatePersona);
  document.getElementById('persona-create-btn').addEventListener('click', createPersona);
  document.getElementById('persona-clear-btn').addEventListener('click', clearPersonaForm);
  document.getElementById('add-project-btn').addEventListener('click', addProject);
  
  // Export/Import event listeners
  document.getElementById('export-personas-btn').addEventListener('click', exportPersonas);
  document.getElementById('import-personas-btn').addEventListener('click', importPersonas);
  document.getElementById('export-projects-btn').addEventListener('click', exportProjects);
  document.getElementById('import-projects-btn').addEventListener('click', importProjects);

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
  if (tabName === 'chat') refreshChatTab();
  
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
      if (type === 'email') emailMonitorPersonId = val;
      if (type === 'chat') chatMonitorPersonId = val;
      if (type === 'email') refreshEmailsTab();
      if (type === 'chat') refreshChatTab();
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
  
  const timestamp = document.createElement('span');
  timestamp.className = 'email-detail-timestamp';
  timestamp.textContent = formatRelativeTime(msg.sent_at);
  
  const emailId = document.createElement('span');
  emailId.className = 'email-detail-id';
  emailId.textContent = `#${msg.id}`;
  
  meta.appendChild(timestamp);
  meta.appendChild(emailId);
  detailHeader.appendChild(subject);
  detailHeader.appendChild(meta);
  detailEl.appendChild(detailHeader);

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
  headerMeta.textContent = `#${msg.id} • ${msg.sent_at || ''}`;
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

async function refreshChatTab() {
  ensurePersonaSelects();
  if (!chatMonitorPersonId) return;
  try {
    const data = await fetchJson(`${API_PREFIX}/monitor/chat/messages/${chatMonitorPersonId}?scope=all&limit=100`);
    renderChatList('chat-dms-list', data.dms || []);
    renderChatList('chat-rooms-list', data.rooms || []);
  } catch (err) {
    console.error('Failed to refresh chat tab:', err);
  }
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
});

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
