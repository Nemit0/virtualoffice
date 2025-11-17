// Simulation Control Module
// Handles all simulation lifecycle operations including start, stop, reset, advance, and auto-tick management

import { API_PREFIX, fetchJson } from '../core/api.js';
import { setStatus, announceToScreenReader } from '../utils/ui.js';
import {
  setIsSimulationRunning,
  getIsSimulationRunning,
  getSelectedPeople,
  getProjects,
  setLastAutoPauseState,
  getLastAutoPauseState,
  clearProjects
} from '../core/state.js';

// Import refreshAll to call after simulation operations
let refreshAllCallback = null;

/**
 * Set the refresh callback function
 * This should be called from dashboard.js to provide the refreshAll function
 */
export function setRefreshCallback(callback) {
  refreshAllCallback = callback;
}

/**
 * Refresh simulation state from the server
 * Updates current tick, sim time, auto-tick status, and tick interval
 */
export async function refreshSimulationState() {
  const state = await fetchJson(`${API_PREFIX}/simulation`);
  document.getElementById('state-status').textContent = state.is_running ? 'running' : 'stopped';
  document.getElementById('state-current_tick').textContent = state.current_tick;
  document.getElementById('state-auto').textContent = state.auto_tick;

  // Display simulation time from backend (canonical workday model)
  // Backend already applies hours_per_day * 60 ticks/day with 09:00 start.
  const simTimeEl = document.getElementById('state-sim_time');
  if (simTimeEl) {
    simTimeEl.textContent = state.sim_time;
    simTimeEl.title = 'Simulation time from server (workday model)';
  }

  // Derive project week from simulation day (5-day work weeks)
  let currentDay = 0;
  if (typeof state.sim_time === 'string') {
    const match = /^Day\s+(\d+)\s+/i.exec(state.sim_time);
    if (match) {
      currentDay = parseInt(match[1], 10) || 0;
    }
  }
  const currentWeek = currentDay > 0 ? Math.floor((currentDay - 1) / 5) + 1 : 0;

  const projectWeekEl = document.getElementById('state-project_week');
  if (projectWeekEl) {
    if (currentWeek > 0) {
      projectWeekEl.textContent = `Week ${currentWeek}`;
      projectWeekEl.title = `Week ${currentWeek} (5-day work weeks)`;
    } else {
      projectWeekEl.textContent = 'Week 0';
      projectWeekEl.title = 'Simulation not started';
    }
  }

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
  const wasRunning = getIsSimulationRunning();
  const isRunning = state.is_running || state.auto_tick;
  setIsSimulationRunning(isRunning);

  // Return state change information for caller to handle refresh interval updates
  return {
    wasRunning,
    isRunning,
    stateChanged: wasRunning !== isRunning
  };
}

/**
 * Refresh active projects display
 * Shows currently running projects with team members and timelines
 */
export async function refreshActiveProjects() {
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

/**
 * Start simulation with configured projects and personas
 * Supports both single-project (legacy) and multi-project modes
 */
export async function startSimulation() {
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

    // Require at least one project to be configured
    const projects = getProjects();
    if (projects.length === 0) {
      setStatus('Please add at least one project before starting the simulation', true);
      return;
    }

    // Multi-project mode
    const payload = {
      projects: projects.map(p => ({
        project_name: p.name,
        project_summary: p.summary,
        assigned_person_ids: p.team_ids,
        start_week: p.start_week,
        duration_weeks: p.duration_weeks
      }))
    };

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
    
    // Refresh dashboard after starting simulation
    if (refreshAllCallback) {
      await refreshAllCallback();
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    startBtn.disabled = false;
    startBtn.textContent = originalText;
    startBtn.style.opacity = '1';
  }
}

/**
 * Stop the running simulation
 */
export async function stopSimulation() {
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
    
    // Refresh dashboard after stopping simulation
    if (refreshAllCallback) {
      await refreshAllCallback();
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    stopBtn.disabled = false;
    stopBtn.textContent = originalText;
    stopBtn.style.opacity = '1';
  }
}

/**
 * Reset simulation (soft reset - keeps personas)
 */
export async function resetSimulation() {
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
    
    // Refresh dashboard after resetting simulation
    if (refreshAllCallback) {
      await refreshAllCallback();
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    resetBtn.disabled = false;
    resetBtn.textContent = originalText;
    resetBtn.style.opacity = '1';
  }
}

/**
 * Full reset simulation (deletes all personas)
 */
export async function fullResetSimulation() {
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

    // Clear frontend state (projects in localStorage)
    clearProjects();

    setStatus('Full reset complete (personas deleted).');

    // Refresh dashboard after full reset
    if (refreshAllCallback) {
      await refreshAllCallback();
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    fullResetBtn.disabled = false;
    fullResetBtn.textContent = originalText;
    fullResetBtn.style.opacity = '1';
  }
}

/**
 * Advance simulation by specified number of ticks
 */
export async function advanceSimulation() {
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
    
    // Refresh dashboard after advancing simulation
    if (refreshAllCallback) {
      await refreshAllCallback();
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    advanceBtn.disabled = false;
    advanceBtn.textContent = originalText;
    advanceBtn.style.opacity = '1';
  }
}

/**
 * Start automatic tick advancement
 */
export async function startAutoTicks() {
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
    
    // Refresh dashboard after starting auto-ticks
    if (refreshAllCallback) {
      await refreshAllCallback();
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    autoStartBtn.disabled = false;
    autoStartBtn.textContent = originalText;
    autoStartBtn.style.opacity = '1';
  }
}

/**
 * Stop automatic tick advancement
 */
export async function stopAutoTicks() {
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
    
    // Refresh dashboard after stopping auto-ticks
    if (refreshAllCallback) {
      await refreshAllCallback();
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    autoStopBtn.disabled = false;
    autoStopBtn.textContent = originalText;
    autoStopBtn.style.opacity = '1';
  }
}

/**
 * Update tick interval (time between automatic ticks)
 */
export async function updateTickInterval() {
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

/**
 * Toggle auto-pause feature (automatically pause when all projects complete)
 */
export async function toggleAutoPause() {
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

// ===== Helper Functions =====

/**
 * Gather selected person IDs from checkboxes
 * @private
 */
function gatherSelectedPersonIds() {
  return Array.from(document.querySelectorAll('#people-container input[type=checkbox]'))
    .filter(cb => cb.checked)
    .map(cb => Number(cb.value));
}

/**
 * Gather deselected person IDs from checkboxes
 * @private
 */
function gatherDeselectedPersonIds() {
  return Array.from(document.querySelectorAll('#people-container input[type=checkbox]'))
    .filter(cb => !cb.checked)
    .map(cb => Number(cb.value));
}

/**
 * Update auto-pause display elements
 * @private
 */
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

  const lastAutoPauseState = getLastAutoPauseState();
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
  setLastAutoPauseState(currentState);

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
