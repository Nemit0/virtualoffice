// VDOS Dashboard JavaScript
const API_PREFIX = '/api/v1';
let selectedPeople = new Set();
let refreshIntervalId = null;
let currentRefreshInterval = 60000; // Start with 1 minute
let isSimulationRunning = false;
let projects = []; // Array of project objects
let people_cache = []; // Cache of all people for project team selection

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

async function refreshAll() {
  try {
    await refreshState();
    await refreshPeopleAndPlans();
    await refreshPlannerMetrics();
    await refreshTokenUsage();
    await refreshEvents();
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
        name: p.name,
        summary: p.summary,
        team_ids: p.team_ids,
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

  try {
    setStatus('Starting simulation...');
    await fetchJson(`${API_PREFIX}/simulation/start`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    setStatus('Simulation started');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

async function stopSimulation() {
  try {
    setStatus('Stopping simulation...');
    await fetchJson(`${API_PREFIX}/simulation/stop`, { method: 'POST' });
    setStatus('Simulation stopped');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

async function resetSimulation() {
  try {
    setStatus('Resetting simulation...');
    await fetchJson(`${API_PREFIX}/simulation/reset`, { method: 'POST' });
    setStatus('Simulation reset');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

async function fullResetSimulation() {
  const confirmed = confirm('This will DELETE ALL PERSONAS and reset the simulation. Continue?');
  if (!confirmed) return;
  try {
    setStatus('Performing full reset...');
    await fetchJson(`${API_PREFIX}/simulation/full-reset`, { method: 'POST' });
    setStatus('Full reset complete (personas deleted).');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

async function advanceSimulation() {
  const ticks = parseInt(document.getElementById('advance-ticks').value, 10) || 1;
  const reason = document.getElementById('advance-reason').value.trim() || 'manual';
  try {
    await fetchJson(`${API_PREFIX}/simulation/advance`, {
      method: 'POST',
      body: JSON.stringify({ ticks, reason }),
    });
    setStatus(`Advanced ${ticks} tick(s)`);
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

async function startAutoTicks() {
  try {
    await fetchJson(`${API_PREFIX}/simulation/ticks/start`, { method: 'POST' });
    setStatus('Automatic ticking enabled');
    await refreshAll();
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

async function stopAutoTicks() {
  try {
    await fetchJson(`${API_PREFIX}/simulation/ticks/stop`, { method: 'POST' });
    setStatus('Automatic ticking disabled');
    await refreshAll();
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
  document.getElementById('persona-generate-btn').addEventListener('click', generatePersona);
  document.getElementById('persona-create-btn').addEventListener('click', createPersona);
  document.getElementById('persona-clear-btn').addEventListener('click', clearPersonaForm);
  document.getElementById('add-project-btn').addEventListener('click', addProject);

  // Initial refresh
  refreshAll();

  // Start with 1-minute interval (will auto-adjust based on simulation state)
  setRefreshInterval(60000);
}

document.addEventListener('DOMContentLoaded', init);