// Keyboard Navigation Module
// Centralized keyboard event handling for the VDOS dashboard

import { announceToScreenReader } from './ui.js';
import { 
  refreshEmailsTab, 
  switchEmailFolder,
  handleEmailKeyboard 
} from '../modules/email-client.js';
import { 
  handleChatKeyboard 
} from '../modules/chat-client.js';
import {
  getEmailFolder,
  setEmailFolder,
  getEmailSelected,
  setEmailSelected,
  getEmailFocusIndex,
  setEmailFocusIndex,
  getEmailCache,
  getChatState,
  setChatSelectedConversation
} from '../core/state.js';

// Keyboard shortcut registry
const keyboardShortcuts = new Map();

/**
 * Register a keyboard shortcut
 * @param {string} key - Key to listen for
 * @param {Function} handler - Handler function
 * @param {Object} options - Options (tab, modifiers, etc.)
 */
export function registerKeyboardShortcut(key, handler, options = {}) {
  const shortcutKey = `${key}_${options.tab || 'global'}`;
  keyboardShortcuts.set(shortcutKey, { handler, options });
}

/**
 * Setup global keyboard handlers
 * Initializes all keyboard event listeners for the dashboard
 */
export function setupGlobalKeyboardHandlers() {
  // Global keyboard shortcuts (work across all tabs)
  document.addEventListener('keydown', handleGlobalKeyboard);
  
  // Email-specific keyboard shortcuts
  document.addEventListener('keydown', handleEmailGlobalKeyboard);
  
  // Chat-specific keyboard shortcuts
  document.addEventListener('keydown', handleChatGlobalKeyboard);
  
  console.log('[Keyboard] Global keyboard handlers initialized');
}

/**
 * Handle global keyboard shortcuts (work across all tabs)
 * @param {KeyboardEvent} e - Keyboard event
 */
function handleGlobalKeyboard(e) {
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
      if (activeTab === 'chat') {
        const chatState = getChatState();
        if (chatState.selectedConversationSlug) {
          handleMessageRefresh();
        }
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
        switchEmailFolder('inbox');
      }
      break;

    case 's':
      e.preventDefault();
      if (activeTab === 'emails') {
        switchEmailFolder('sent');
      }
      break;
  }
}

/**
 * Handle email-specific keyboard shortcuts
 * @param {KeyboardEvent} e - Keyboard event
 */
function handleEmailGlobalKeyboard(e) {
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
      const currentFolder = getEmailFolder();
      if (currentFolder !== 'inbox') {
        setEmailFolder('inbox');
        // Trigger re-render through the email client module
        switchEmailFolder('inbox');
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
        const currentFolder = getEmailFolder();
        if (currentFolder !== 'sent') {
          setEmailFolder('sent');
          // Trigger re-render through the email client module
          switchEmailFolder('sent');
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
        // Trigger search clear through email client
        const event = new Event('input', { bubbles: true });
        searchInputEl.dispatchEvent(event);
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
        const emailSelected = getEmailSelected();
        emailSelected.id = null;
        setEmailSelected(emailSelected);
        setEmailFocusIndex(-1);
        // Trigger re-render through email client
        refreshEmailsTab();
        const emailList = document.getElementById('email-list');
        if (emailList) {
          emailList.focus();
        }
        announceToScreenReader('Email selection cleared');
      }
      break;
  }
}

/**
 * Handle chat-specific keyboard shortcuts
 * @param {KeyboardEvent} e - Keyboard event
 */
async function handleChatGlobalKeyboard(e) {
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
      const chatState = getChatState();
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
        const event = new Event('input', { bubbles: true });
        searchInput.dispatchEvent(event);
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
}

/**
 * Handle modal keyboard events (ESC to close)
 * @param {KeyboardEvent} e - Keyboard event
 * @param {Function} closeCallback - Function to call when ESC is pressed
 * @returns {Function} Cleanup function to remove the event listener
 */
export function handleModalKeyboard(e, closeCallback) {
  if (e.key === 'Escape') {
    closeCallback();
  }
}

/**
 * Setup modal keyboard handler with automatic cleanup
 * @param {Function} closeCallback - Function to call when ESC is pressed
 * @returns {Function} Cleanup function to remove the event listener
 */
export function setupModalKeyboardHandler(closeCallback) {
  const handler = (e) => handleModalKeyboard(e, closeCallback);
  document.addEventListener('keydown', handler);
  
  // Return cleanup function
  return () => {
    document.removeEventListener('keydown', handler);
  };
}

// Helper functions that need to be accessible from keyboard handlers
// These are imported from other modules or need to be exposed

/**
 * Handle chat refresh (called by keyboard shortcut)
 */
function handleChatRefresh() {
  // This function should be imported from chat-client module
  // For now, dispatch a custom event that the chat module can listen to
  const event = new CustomEvent('chat:refresh');
  document.dispatchEvent(event);
}

/**
 * Handle message refresh (called by keyboard shortcut)
 */
function handleMessageRefresh() {
  // This function should be imported from chat-client module
  // For now, dispatch a custom event that the chat module can listen to
  const event = new CustomEvent('chat:refreshMessages');
  document.dispatchEvent(event);
}

/**
 * Log performance metrics (called by keyboard shortcut)
 */
function logPerformanceMetrics() {
  // This function should be imported from chat-client module
  // For now, dispatch a custom event that the chat module can listen to
  const event = new CustomEvent('chat:logPerformance');
  document.dispatchEvent(event);
}

/**
 * Clear conversation selection (called by keyboard shortcut)
 */
function clearConversationSelection() {
  // Clear the selected conversation in state
  setChatSelectedConversation({ slug: null, type: null });
  
  // Dispatch event for chat module to handle
  const event = new CustomEvent('chat:clearSelection');
  document.dispatchEvent(event);
}

// Export all keyboard handling functions
export {
  handleEmailKeyboard,
  handleChatKeyboard
};
