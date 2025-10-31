// VDOS Dashboard JavaScript - Main Orchestrator
// This file coordinates all dashboard modules and manages the application lifecycle

// ===== MODULE IMPORTS =====

// Core modules
import { API_PREFIX, fetchJson } from './core/api.js';
import {
  getSelectedPeople,
  setSelectedPeople,
  getPeopleCache,
  setPeopleCache,
  getProjects,
  getEmailMonitorPersonId,
  setEmailMonitorPersonId,
  getChatMonitorPersonId,
  setChatMonitorPersonId,
  getAutoRefreshEnabled,
  setAutoRefreshEnabled,
  getRefreshInterval,
  setRefreshInterval as setRefreshIntervalState,
  getRefreshIntervalId,
  setRefreshIntervalId,
  getActiveTab,
  setActiveTab as setActiveTabState,
  getChatAutoRefreshInterval,
  setChatAutoRefreshInterval,
  saveState,
  loadState
} from './core/state.js';

// Utility modules
import {
  setStatus,
  switchTab,
  announceToScreenReader,
  ensurePersonaSelects
} from './utils/ui.js';
import {
  setupGlobalKeyboardHandlers
} from './utils/keyboard.js';

// Feature modules
import {
  startSimulation,
  stopSimulation,
  resetSimulation,
  fullResetSimulation,
  advanceSimulation,
  startAutoTicks,
  stopAutoTicks,
  updateTickInterval,
  toggleAutoPause,
  refreshSimulationState,
  refreshActiveProjects,
  setRefreshCallback
} from './modules/simulation.js';
import {
  createPersona,
  generatePersona,
  regenerateStyleExamples,
  refreshPeopleAndPlans,
  clearPersonaForm,
  openPreviewModal,
  closePreviewModal,
  transformPreviewMessage,
  exportPersonas,
  importPersonas
} from './modules/personas.js';
import {
  addProject,
  removeProject,
  exportProjects,
  importProjects
} from './modules/projects.js';
import {
  refreshEmailsTab,
  switchEmailFolder
} from './modules/email-client.js';
import {
  refreshChatTab,
  setupChatAutoRefresh
} from './modules/chat-client.js';
import {
  refreshPlannerMetrics,
  refreshTokenUsage,
  refreshEvents,
  refreshFilterMetrics
} from './modules/metrics.js';
import {
  toggleStyleFilter,
  refreshFilterStatus
} from './modules/style-filter.js';

// Performance monitoring
const PERF_START = performance.now();
console.log('[DEBUG] ========== DASHBOARD.JS LOADED ==========');
console.log('[DEBUG] Timestamp:', new Date().toISOString());

// ===== ORCHESTRATION FUNCTIONS =====

/**
 * Refresh simulation state and adjust refresh interval based on running status
 */
async function refreshState() {
  const stateInfo = await refreshSimulationState();
  
  // If state changed, update the refresh interval
  if (stateInfo.stateChanged) {
    setRefreshInterval(stateInfo.isRunning ? 5000 : 60000);
  }
}

/**
 * Refresh all dashboard data
 * This is the main coordination function that updates all modules
 */
export async function refreshAll() {
  try {
    await refreshState();
    await refreshActiveProjects();
    await refreshPeopleAndPlans();
    await refreshPlannerMetrics();
    await refreshTokenUsage();
    await refreshEvents();
    await refreshFilterStatus();
    await refreshFilterMetrics();
    await refreshEmailsTab();
    await refreshChatTab();
    setStatus('');
  } catch (err) {
    setStatus(err.message || String(err), true);
  }
}

/**
 * Toggle auto-refresh on/off
 */
function toggleAutoRefresh() {
  const toggleEl = document.getElementById('auto-refresh-toggle');
  if (!toggleEl) return;

  const enabled = toggleEl.checked;
  setAutoRefreshEnabled(enabled);

  console.log('[AUTO-REFRESH] User toggled auto-refresh:', {
    enabled: enabled,
    timestamp: new Date().toISOString()
  });

  if (enabled) {
    // Re-enable auto-refresh with current interval
    setRefreshInterval(getRefreshInterval());
    setupChatAutoRefresh();
    setStatus('Auto-refresh enabled');
  } else {
    // Disable all auto-refresh intervals
    const intervalId = getRefreshIntervalId();
    if (intervalId !== null) {
      clearInterval(intervalId);
      setRefreshIntervalId(null);
    }
    const chatIntervalId = getChatAutoRefreshInterval();
    if (chatIntervalId) {
      clearInterval(chatIntervalId);
      setChatAutoRefreshInterval(null);
    }
    setStatus('Auto-refresh disabled');
  }
}

/**
 * Load auto-refresh preference from state
 */
function loadAutoRefreshPreference() {
  const toggleEl = document.getElementById('auto-refresh-toggle');
  if (toggleEl) {
    toggleEl.checked = getAutoRefreshEnabled();
  }

  console.log('[AUTO-REFRESH] Loaded preference:', {
    enabled: getAutoRefreshEnabled(),
    source: 'state module'
  });
}

/**
 * Set the refresh interval and manage the interval timer
 */
function setRefreshInterval(intervalMs) {
  const currentInterval = getRefreshInterval();
  const currentIntervalId = getRefreshIntervalId();
  
  if (currentInterval === intervalMs && currentIntervalId !== null) {
    return; // No change needed
  }

  setRefreshIntervalState(intervalMs);

  // Clear existing interval
  if (currentIntervalId !== null) {
    clearInterval(currentIntervalId);
    setRefreshIntervalId(null);
  }

  // Only set new interval if auto-refresh is enabled
  if (getAutoRefreshEnabled()) {
    const newIntervalId = setInterval(refreshAll, intervalMs);
    setRefreshIntervalId(newIntervalId);
    console.log(`Dashboard refresh interval set to ${intervalMs / 1000}s`);
  } else {
    console.log('Dashboard auto-refresh is disabled');
  }
}

/**
 * Handle tab switching with module-specific refresh logic
 */
function setActiveTab(tabName) {
  // Call the imported switchTab function for core tab switching logic
  switchTab(tabName);

  // Update state
  setActiveTabState(tabName);

  // Refresh when switching to specific tabs
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
}

/**
 * Wrapper function to ensure persona selects are populated
 */
export function ensurePersonaSelectsWrapper() {
  const peopleCache = getPeopleCache();
  const result = ensurePersonaSelects(
    peopleCache,
    getEmailMonitorPersonId(),
    getChatMonitorPersonId(),
    (val) => {
      setEmailMonitorPersonId(val);
      refreshEmailsTab();
    },
    (val) => {
      setChatMonitorPersonId(val);
      refreshChatTab();
    }
  );

  setEmailMonitorPersonId(result.emailMonitorPersonId);
  setChatMonitorPersonId(result.chatMonitorPersonId);
}

// ===== INITIALIZATION =====

/**
 * Initialize the dashboard application
 * Sets up all event listeners and starts the refresh cycle
 */
function init() {
  const initStart = performance.now();
  console.log('[DEBUG] Initializing dashboard...');
  
  // Load persisted state from localStorage
  loadState();
  
  // Set up refresh callback for simulation module
  setRefreshCallback(refreshAll);
  
  // Set up global keyboard handlers
  setupGlobalKeyboardHandlers();
  
  // Simulation control event listeners
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

  // Style filter toggle (optional - may not exist in all versions)
  const styleFilterToggle = document.getElementById('style-filter-toggle');
  if (styleFilterToggle) {
    styleFilterToggle.addEventListener('change', toggleStyleFilter);
    console.log('[DEBUG] Style filter toggle found and listener attached');
  } else {
    console.log('[DEBUG] Style filter toggle not found (optional element)');
  }

  // Persona management event listeners
  const generateBtn = document.getElementById('persona-generate-btn');
  console.log('[DEBUG] Generate button element:', generateBtn);
  console.log('[DEBUG] Generate button exists?', !!generateBtn);

  if (generateBtn) {
    generateBtn.addEventListener('click', function (event) {
      console.log('[DEBUG] ========== BUTTON CLICKED ==========');
      console.log('[DEBUG] Click event:', event);
      console.log('[DEBUG] Calling generatePersona...');
      generatePersona();
    });
    console.log('[DEBUG] Event listener attached to generate button');
    console.log('[DEBUG] Button disabled?', generateBtn.disabled);
  } else {
    console.error('[DEBUG] Generate button not found!');
  }
  
  document.getElementById('persona-create-btn').addEventListener('click', createPersona);
  document.getElementById('persona-clear-btn').addEventListener('click', clearPersonaForm);
  document.getElementById('regenerate-examples-btn').addEventListener('click', regenerateStyleExamples);
  document.getElementById('preview-filter-btn').addEventListener('click', openPreviewModal);
  document.getElementById('preview-close-btn').addEventListener('click', closePreviewModal);
  document.getElementById('preview-transform-btn').addEventListener('click', transformPreviewMessage);
  
  // Project management event listeners
  document.getElementById('add-project-btn').addEventListener('click', addProject);

  // Export/Import event listeners
  document.getElementById('export-personas-btn').addEventListener('click', exportPersonas);
  document.getElementById('import-personas-btn').addEventListener('click', importPersonas);
  document.getElementById('export-projects-btn').addEventListener('click', exportProjects);
  document.getElementById('import-projects-btn').addEventListener('click', importProjects);

  // Tab switching event listeners
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.tab-button');
    if (!btn) return;
    setActiveTab(btn.dataset.tab);
  });

  // Load auto-refresh preference from localStorage
  loadAutoRefreshPreference();

  // Initial refresh
  refreshAll();

  // Start with 1-minute interval (will auto-adjust based on simulation state)
  setRefreshInterval(60000);
  
  // Log initialization performance
  const initEnd = performance.now();
  const initTime = initEnd - initStart;
  const totalTime = initEnd - PERF_START;
  console.log(`[PERF] Dashboard initialization completed in ${initTime.toFixed(2)}ms`);
  console.log(`[PERF] Total module load + init time: ${totalTime.toFixed(2)}ms`);
  
  if (initTime > 100) {
    console.warn(`[PERF] Initialization time (${initTime.toFixed(2)}ms) exceeds target of 100ms`);
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', init);
