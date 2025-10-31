// VDOS Dashboard State Management Module
// Centralized state management with reactive updates and localStorage persistence

// Internal state object - not directly accessible
const state = {
  // Persona selection
  selectedPeople: new Set(),
  peopleCache: [],
  
  // Projects
  projects: [],
  
  // Email state
  email: {
    monitorPersonId: null,
    folder: 'inbox', // 'inbox' | 'sent'
    cache: { inbox: [], sent: [] },
    selected: { box: 'inbox', id: null },
    autoOpenFirst: false,
    searchQuery: '',
    focusIndex: -1,
    searchTimeout: null,
    lastRefresh: 0,
    renderCache: new Map(),
    sortCache: new Map()
  },
  
  // Chat state
  chat: {
    monitorPersonId: null,
    selectedConversationSlug: null,
    selectedConversationType: null, // 'room' | 'dm'
    conversations: { rooms: [], dms: [] },
    currentMessages: [],
    isLoading: false,
    lastRefresh: null,
    searchQuery: '',
    messageSearchQuery: '',
    autoRefreshInterval: null,
    isNewConversationSelection: false,
    virtualScrolling: {
      enabled: false,
      itemHeight: 80,
      containerHeight: 0,
      scrollTop: 0,
      visibleStart: 0,
      visibleEnd: 0,
      totalItems: 0,
      renderBuffer: 5
    },
    pagination: {
      enabled: false,
      pageSize: 50,
      currentPage: 0,
      totalPages: 0,
      hasMore: false
    },
    renderCache: new Map(),
    performanceMetrics: {
      renderTimes: [],
      scrollEvents: 0,
      lastRenderTime: 0,
      averageRenderTime: 0,
      cacheHits: 0,
      cacheMisses: 0
    }
  },
  
  // Simulation state
  simulation: {
    isRunning: false,
    currentTick: 0,
    simTime: '',
    autoTick: false,
    autoPauseEnabled: false,
    lastAutoPauseState: null
  },
  
  // UI preferences
  ui: {
    autoRefreshEnabled: true,
    refreshInterval: 60000,
    refreshIntervalId: null,
    activeTab: 'overview',
    messageSearchResults: [],
    currentSearchResultIndex: -1,
    scrollTimeout: null,
    chatSidebarState: {
      isOpen: false,
      isMobile: false
    },
    toastContainer: null
  }
};

// Subscription system for reactive updates
const subscribers = new Map();

/**
 * Subscribe to state changes for a specific key path
 * @param {string} keyPath - Dot-notation path to state property (e.g., 'email.folder')
 * @param {Function} callback - Function to call when state changes
 * @returns {Function} Unsubscribe function
 */
export function subscribe(keyPath, callback) {
  if (!subscribers.has(keyPath)) {
    subscribers.set(keyPath, new Set());
  }
  subscribers.get(keyPath).add(callback);
  
  // Return unsubscribe function
  return () => {
    const subs = subscribers.get(keyPath);
    if (subs) {
      subs.delete(callback);
    }
  };
}

/**
 * Notify subscribers of state changes
 * @param {string} keyPath - Path that changed
 * @param {*} newValue - New value
 * @param {*} oldValue - Previous value
 */
function notifySubscribers(keyPath, newValue, oldValue) {
  const subs = subscribers.get(keyPath);
  if (subs) {
    subs.forEach(callback => {
      try {
        callback(newValue, oldValue);
      } catch (err) {
        console.error(`Error in state subscriber for ${keyPath}:`, err);
      }
    });
  }
}

// ============================================================================
// Persona Selection State
// ============================================================================

export function getSelectedPeople() {
  return new Set(state.selectedPeople);
}

export function setSelectedPeople(ids) {
  const oldValue = new Set(state.selectedPeople);
  state.selectedPeople = new Set(ids);
  notifySubscribers('selectedPeople', getSelectedPeople(), oldValue);
}

export function addSelectedPerson(id) {
  const oldValue = new Set(state.selectedPeople);
  state.selectedPeople.add(id);
  notifySubscribers('selectedPeople', getSelectedPeople(), oldValue);
}

export function removeSelectedPerson(id) {
  const oldValue = new Set(state.selectedPeople);
  state.selectedPeople.delete(id);
  notifySubscribers('selectedPeople', getSelectedPeople(), oldValue);
}

export function getPeopleCache() {
  return [...state.peopleCache];
}

export function setPeopleCache(people) {
  state.peopleCache = [...people];
  notifySubscribers('peopleCache', getPeopleCache(), null);
}

// ============================================================================
// Projects State
// ============================================================================

export function getProjects() {
  return [...state.projects];
}

export function setProjects(projects) {
  const oldValue = [...state.projects];
  state.projects = [...projects];
  notifySubscribers('projects', getProjects(), oldValue);
}

export function addProject(project) {
  const oldValue = [...state.projects];
  state.projects.push(project);
  notifySubscribers('projects', getProjects(), oldValue);
}

export function removeProject(index) {
  const oldValue = [...state.projects];
  state.projects.splice(index, 1);
  notifySubscribers('projects', getProjects(), oldValue);
}

export function clearProjects() {
  const oldValue = [...state.projects];
  state.projects = [];
  notifySubscribers('projects', getProjects(), oldValue);
}

// ============================================================================
// Email State
// ============================================================================

export function getEmailState() {
  return {
    monitorPersonId: state.email.monitorPersonId,
    folder: state.email.folder,
    cache: { ...state.email.cache },
    selected: { ...state.email.selected },
    autoOpenFirst: state.email.autoOpenFirst,
    searchQuery: state.email.searchQuery,
    focusIndex: state.email.focusIndex,
    lastRefresh: state.email.lastRefresh
  };
}

export function updateEmailState(updates) {
  const oldValue = getEmailState();
  Object.assign(state.email, updates);
  notifySubscribers('email', getEmailState(), oldValue);
}

export function getEmailMonitorPersonId() {
  return state.email.monitorPersonId;
}

export function setEmailMonitorPersonId(id) {
  const oldValue = state.email.monitorPersonId;
  state.email.monitorPersonId = id;
  notifySubscribers('email.monitorPersonId', id, oldValue);
}

export function getEmailFolder() {
  return state.email.folder;
}

export function setEmailFolder(folder) {
  const oldValue = state.email.folder;
  state.email.folder = folder;
  notifySubscribers('email.folder', folder, oldValue);
}

export function getEmailCache() {
  return { ...state.email.cache };
}

export function setEmailCache(cache) {
  state.email.cache = { ...cache };
  notifySubscribers('email.cache', getEmailCache(), null);
}

export function getEmailSelected() {
  return { ...state.email.selected };
}

export function setEmailSelected(selected) {
  const oldValue = { ...state.email.selected };
  state.email.selected = { ...selected };
  notifySubscribers('email.selected', getEmailSelected(), oldValue);
}

export function getEmailSearchQuery() {
  return state.email.searchQuery;
}

export function setEmailSearchQuery(query) {
  const oldValue = state.email.searchQuery;
  state.email.searchQuery = query;
  notifySubscribers('email.searchQuery', query, oldValue);
}

export function getEmailFocusIndex() {
  return state.email.focusIndex;
}

export function setEmailFocusIndex(index) {
  const oldValue = state.email.focusIndex;
  state.email.focusIndex = index;
  notifySubscribers('email.focusIndex', index, oldValue);
}

export function getEmailRenderCache() {
  return state.email.renderCache;
}

export function getEmailSortCache() {
  return state.email.sortCache;
}

export function clearEmailCache() {
  state.email.cache = { inbox: [], sent: [] };
  state.email.renderCache.clear();
  state.email.sortCache.clear();
  state.email.lastRefresh = 0;
  notifySubscribers('email.cache', getEmailCache(), null);
}

// ============================================================================
// Chat State
// ============================================================================

export function getChatState() {
  return {
    monitorPersonId: state.chat.monitorPersonId,
    selectedConversationSlug: state.chat.selectedConversationSlug,
    selectedConversationType: state.chat.selectedConversationType,
    conversations: { ...state.chat.conversations },
    currentMessages: [...state.chat.currentMessages],
    isLoading: state.chat.isLoading,
    lastRefresh: state.chat.lastRefresh,
    searchQuery: state.chat.searchQuery,
    messageSearchQuery: state.chat.messageSearchQuery,
    isNewConversationSelection: state.chat.isNewConversationSelection
  };
}

export function updateChatState(updates) {
  const oldValue = getChatState();
  Object.assign(state.chat, updates);
  notifySubscribers('chat', getChatState(), oldValue);
}

export function getChatMonitorPersonId() {
  return state.chat.monitorPersonId;
}

export function setChatMonitorPersonId(id) {
  const oldValue = state.chat.monitorPersonId;
  state.chat.monitorPersonId = id;
  notifySubscribers('chat.monitorPersonId', id, oldValue);
}

export function getChatSelectedConversation() {
  return {
    slug: state.chat.selectedConversationSlug,
    type: state.chat.selectedConversationType
  };
}

export function setChatSelectedConversation(slug, type) {
  const oldValue = getChatSelectedConversation();
  state.chat.selectedConversationSlug = slug;
  state.chat.selectedConversationType = type;
  notifySubscribers('chat.selectedConversation', getChatSelectedConversation(), oldValue);
}

export function getChatConversations() {
  return { ...state.chat.conversations };
}

export function setChatConversations(conversations) {
  state.chat.conversations = { ...conversations };
  notifySubscribers('chat.conversations', getChatConversations(), null);
}

export function getChatCurrentMessages() {
  return [...state.chat.currentMessages];
}

export function setChatCurrentMessages(messages) {
  state.chat.currentMessages = [...messages];
  notifySubscribers('chat.currentMessages', getChatCurrentMessages(), null);
}

export function getChatSearchQuery() {
  return state.chat.searchQuery;
}

export function setChatSearchQuery(query) {
  const oldValue = state.chat.searchQuery;
  state.chat.searchQuery = query;
  notifySubscribers('chat.searchQuery', query, oldValue);
}

export function getChatVirtualScrolling() {
  return { ...state.chat.virtualScrolling };
}

export function updateChatVirtualScrolling(updates) {
  Object.assign(state.chat.virtualScrolling, updates);
  notifySubscribers('chat.virtualScrolling', getChatVirtualScrolling(), null);
}

export function getChatPagination() {
  return { ...state.chat.pagination };
}

export function updateChatPagination(updates) {
  Object.assign(state.chat.pagination, updates);
  notifySubscribers('chat.pagination', getChatPagination(), null);
}

export function getChatRenderCache() {
  return state.chat.renderCache;
}

export function getChatPerformanceMetrics() {
  return { ...state.chat.performanceMetrics };
}

export function updateChatPerformanceMetrics(updates) {
  Object.assign(state.chat.performanceMetrics, updates);
}

export function getChatAutoRefreshInterval() {
  return state.chat.autoRefreshInterval;
}

export function setChatAutoRefreshInterval(intervalId) {
  state.chat.autoRefreshInterval = intervalId;
}

// ============================================================================
// Simulation State
// ============================================================================

export function getSimulationState() {
  return {
    isRunning: state.simulation.isRunning,
    currentTick: state.simulation.currentTick,
    simTime: state.simulation.simTime,
    autoTick: state.simulation.autoTick,
    autoPauseEnabled: state.simulation.autoPauseEnabled
  };
}

export function updateSimulationState(updates) {
  const oldValue = getSimulationState();
  Object.assign(state.simulation, updates);
  notifySubscribers('simulation', getSimulationState(), oldValue);
}

export function getIsSimulationRunning() {
  return state.simulation.isRunning;
}

export function setIsSimulationRunning(isRunning) {
  const oldValue = state.simulation.isRunning;
  state.simulation.isRunning = isRunning;
  notifySubscribers('simulation.isRunning', isRunning, oldValue);
}

export function getLastAutoPauseState() {
  return state.simulation.lastAutoPauseState;
}

export function setLastAutoPauseState(autoPauseState) {
  state.simulation.lastAutoPauseState = autoPauseState;
}

// ============================================================================
// UI Preferences State
// ============================================================================

export function getUIState() {
  return {
    autoRefreshEnabled: state.ui.autoRefreshEnabled,
    refreshInterval: state.ui.refreshInterval,
    activeTab: state.ui.activeTab
  };
}

export function updateUIState(updates) {
  const oldValue = getUIState();
  Object.assign(state.ui, updates);
  notifySubscribers('ui', getUIState(), oldValue);
}

export function getAutoRefreshEnabled() {
  return state.ui.autoRefreshEnabled;
}

export function setAutoRefreshEnabled(enabled) {
  const oldValue = state.ui.autoRefreshEnabled;
  state.ui.autoRefreshEnabled = enabled;
  notifySubscribers('ui.autoRefreshEnabled', enabled, oldValue);
}

export function getRefreshInterval() {
  return state.ui.refreshInterval;
}

export function setRefreshInterval(interval) {
  const oldValue = state.ui.refreshInterval;
  state.ui.refreshInterval = interval;
  notifySubscribers('ui.refreshInterval', interval, oldValue);
}

export function getRefreshIntervalId() {
  return state.ui.refreshIntervalId;
}

export function setRefreshIntervalId(id) {
  state.ui.refreshIntervalId = id;
}

export function getActiveTab() {
  return state.ui.activeTab;
}

export function setActiveTab(tab) {
  const oldValue = state.ui.activeTab;
  state.ui.activeTab = tab;
  notifySubscribers('ui.activeTab', tab, oldValue);
}

export function getMessageSearchResults() {
  return [...state.ui.messageSearchResults];
}

export function setMessageSearchResults(results) {
  state.ui.messageSearchResults = [...results];
  notifySubscribers('ui.messageSearchResults', getMessageSearchResults(), null);
}

export function getCurrentSearchResultIndex() {
  return state.ui.currentSearchResultIndex;
}

export function setCurrentSearchResultIndex(index) {
  const oldValue = state.ui.currentSearchResultIndex;
  state.ui.currentSearchResultIndex = index;
  notifySubscribers('ui.currentSearchResultIndex', index, oldValue);
}

export function getScrollTimeout() {
  return state.ui.scrollTimeout;
}

export function setScrollTimeout(timeout) {
  state.ui.scrollTimeout = timeout;
}

export function getChatSidebarState() {
  return { ...state.ui.chatSidebarState };
}

export function updateChatSidebarState(updates) {
  Object.assign(state.ui.chatSidebarState, updates);
  notifySubscribers('ui.chatSidebarState', getChatSidebarState(), null);
}

export function getToastContainer() {
  return state.ui.toastContainer;
}

export function setToastContainer(container) {
  state.ui.toastContainer = container;
}

// ============================================================================
// State Persistence (localStorage)
// ============================================================================

const STORAGE_KEY = 'vdos-dashboard-state';
const STORAGE_VERSION = 1;

/**
 * Save relevant state to localStorage
 */
export function saveState() {
  try {
    const persistedState = {
      version: STORAGE_VERSION,
      selectedPeople: Array.from(state.selectedPeople),
      projects: state.projects,
      email: {
        monitorPersonId: state.email.monitorPersonId,
        folder: state.email.folder
      },
      chat: {
        monitorPersonId: state.chat.monitorPersonId
      },
      ui: {
        autoRefreshEnabled: state.ui.autoRefreshEnabled,
        refreshInterval: state.ui.refreshInterval,
        activeTab: state.ui.activeTab
      }
    };
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persistedState));
    console.log('[STATE] State saved to localStorage');
  } catch (err) {
    console.error('[STATE] Failed to save state to localStorage:', err);
  }
}

/**
 * Load state from localStorage
 */
export function loadState() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      console.log('[STATE] No saved state found in localStorage');
      return;
    }
    
    const persistedState = JSON.parse(stored);
    
    // Check version compatibility
    if (persistedState.version !== STORAGE_VERSION) {
      console.warn('[STATE] Saved state version mismatch, ignoring');
      return;
    }
    
    // Restore state
    if (persistedState.selectedPeople) {
      state.selectedPeople = new Set(persistedState.selectedPeople);
    }
    
    if (persistedState.projects) {
      state.projects = persistedState.projects;
    }
    
    if (persistedState.email) {
      Object.assign(state.email, persistedState.email);
    }
    
    if (persistedState.chat) {
      Object.assign(state.chat, persistedState.chat);
    }
    
    if (persistedState.ui) {
      Object.assign(state.ui, persistedState.ui);
    }
    
    console.log('[STATE] State loaded from localStorage');
  } catch (err) {
    console.error('[STATE] Failed to load state from localStorage:', err);
  }
}

/**
 * Clear all persisted state
 */
export function clearPersistedState() {
  try {
    localStorage.removeItem(STORAGE_KEY);
    console.log('[STATE] Persisted state cleared');
  } catch (err) {
    console.error('[STATE] Failed to clear persisted state:', err);
  }
}

// Auto-save state on changes (debounced)
let saveTimeout = null;
function scheduleSave() {
  if (saveTimeout) {
    clearTimeout(saveTimeout);
  }
  saveTimeout = setTimeout(() => {
    saveState();
  }, 1000); // Save 1 second after last change
}

// Subscribe to key state changes for auto-save
subscribe('selectedPeople', scheduleSave);
subscribe('projects', scheduleSave);
subscribe('email.monitorPersonId', scheduleSave);
subscribe('chat.monitorPersonId', scheduleSave);
subscribe('ui.autoRefreshEnabled', scheduleSave);
subscribe('ui.activeTab', scheduleSave);

console.log('[STATE] State management module loaded');
