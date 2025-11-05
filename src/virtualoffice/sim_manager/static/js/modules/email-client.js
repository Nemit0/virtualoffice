// Email Client Module
// Handles email display, search, and interaction

import { API_PREFIX, fetchJson } from '../core/api.js';
import { formatTimestamp, formatDuration, formatRelativeTime } from '../utils/formatting.js';
import { announceToScreenReader } from '../utils/ui.js';
import {
  getEmailMonitorPersonId,
  setEmailMonitorPersonId,
  getEmailFolder,
  setEmailFolder,
  getEmailCache,
  setEmailCache,
  getEmailSelected,
  setEmailSelected,
  getEmailSearchQuery,
  setEmailSearchQuery,
  getEmailFocusIndex,
  setEmailFocusIndex,
  getEmailRenderCache,
  getEmailSortCache,
  clearEmailCache as clearEmailCacheState,
  getIsSimulationRunning
} from '../core/state.js';

// Email state variables (migrated from dashboard.js)
let lastEmailRefresh = 0;
const EMAIL_PAGE_SIZE = 200;
let lastFetchLimit = EMAIL_PAGE_SIZE;
let emailAutoOpenFirst = false;
let emailSearchTimeout = null;
let scrollTimeout = null;

/**
 * Refresh the emails tab with optional force refresh
 * @param {boolean} forceRefresh - Force refresh even if cache is valid
 */
export async function refreshEmailsTab(forceRefresh = false) {
  const emailMonitorPersonId = getEmailMonitorPersonId();
  if (!emailMonitorPersonId) return;

  // Performance optimization: Avoid unnecessary API calls
  const now = Date.now();
  const isSimulationRunning = getIsSimulationRunning();
  const CACHE_DURATION = isSimulationRunning ? 15000 : 30000;
  const emailCache = getEmailCache();
  
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
    // Performance optimization: Use larger limit for better caching
    const currentList = emailCache[getEmailFolder()] || [];
    const limit = currentList.length > 100 ? 500 : 200;
    lastFetchLimit = limit;
    const data = await fetchJson(`${API_PREFIX}/monitor/emails/${emailMonitorPersonId}?box=all&limit=${limit}`);
    
    setEmailCache({
      inbox: data.inbox || [],
      sent: data.sent || []
    });
    lastEmailRefresh = now;

    // Clear render cache when data changes
    const renderCache = getEmailRenderCache();
    const sortCache = getEmailSortCache();
    renderCache.clear();
    sortCache.clear();

    // If selection points to an email no longer present, clear it
    const emailSelected = getEmailSelected();
    const selectedBoxList = getEmailCache()[emailSelected.box] || [];
    if (!selectedBoxList.some(m => m.id === emailSelected.id)) {
      setEmailSelected({ box: emailSelected.box, id: null });
      setEmailFocusIndex(-1);
    }

    renderEmailPanels();

    // Update last refresh time
    if (statusEl) {
      const refreshTime = new Date();
      statusEl.textContent = `Last refreshed: ${refreshTime.toLocaleTimeString()}`;
    }

    if (emailAutoOpenFirst) {
      const list = getEmailCache()[getEmailFolder()] || [];
      if (list.length > 0) {
        setEmailSelected({ box: getEmailFolder(), id: list[0].id });
        setEmailFocusIndex(0);
        renderEmailPanels();
        openEmailModal(list[0]);
      }
      emailAutoOpenFirst = false;
    }

    // Announce successful refresh
    const totalEmails = getEmailCache().inbox.length + getEmailCache().sent.length;
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

/**
 * Switch between inbox and sent folders
 * @param {string} folder - 'inbox' or 'sent'
 */
export function switchEmailFolder(folder) {
  setEmailFolder(folder);
  setEmailSelected({ box: folder, id: null });
  setEmailFocusIndex(-1);
  renderEmailPanels();
  
  // Announce folder switch to screen readers
  announceToScreenReader(`Switched to ${folder === 'inbox' ? 'Inbox' : 'Sent'} folder`);
}

/**
 * Select an email by its ID
 * @param {number} id - Email ID
 */
export function selectEmail(id) {
  const emailFolder = getEmailFolder();
  setEmailSelected({ box: emailFolder, id: id });
  renderEmailPanels();
}

/**
 * Search emails with debouncing
 * @param {string} query - Search query
 */
export function searchEmails(query) {
  if (emailSearchTimeout) {
    clearTimeout(emailSearchTimeout);
  }

  // Performance optimization: Shorter debounce for better responsiveness
  const debounceTime = query.length > 3 ? 200 : 300;

  emailSearchTimeout = setTimeout(() => {
    setEmailSearchQuery(query);

    // Clear sort cache when search changes
    const sortCache = getEmailSortCache();
    sortCache.clear();

    renderEmailPanels();

    // Announce search results to screen readers
    const currentList = getEmailCache()[getEmailFolder()] || [];
    const filteredList = query.trim() ? filterEmailsBySearch(currentList, query) : currentList;
    announceToScreenReader(`Search completed. ${filteredList.length} emails found.`);
  }, debounceTime);
}

/**
 * Render email list with given items
 * @param {Array} items - Array of email objects
 */
export function renderEmailList(items) {
  const listEl = document.getElementById('email-list');
  if (!listEl) return;

  // Performance optimization: Use DocumentFragment for batch DOM updates
  const fragment = document.createDocumentFragment();

  // Add ARIA attributes for accessibility
  listEl.setAttribute('role', 'listbox');
  listEl.setAttribute('aria-label', `${getEmailFolder() === 'inbox' ? 'Inbox' : 'Sent'} emails`);

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
  const sortCache = getEmailSortCache();
  const sortCacheKey = `sorted_${getEmailFolder()}_${items.length}_${items[0]?.id || 0}`;
  let sortedItems = sortCache.get(sortCacheKey);

  if (!sortedItems) {
    // Sort emails by timestamp (newest first)
    sortedItems = [...items].sort((a, b) => {
      const timeA = new Date(a.sent_at || 0).getTime();
      const timeB = new Date(b.sent_at || 0).getTime();
      return timeB - timeA;
    });
    sortCache.set(sortCacheKey, sortedItems);
  }

  // Reset focus index if it's out of bounds
  let emailListFocusIndex = getEmailFocusIndex();
  if (emailListFocusIndex >= sortedItems.length) {
    emailListFocusIndex = sortedItems.length - 1;
    setEmailFocusIndex(emailListFocusIndex);
  }

  // Performance optimization: Adaptive virtual scrolling
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

  const renderCache = getEmailRenderCache();
  const emailSelected = getEmailSelected();
  const emailFolder = getEmailFolder();

  itemsToRender.forEach((msg, renderIndex) => {
    const index = shouldUseVirtualScrolling ?
      sortedItems.findIndex(item => item.id === msg.id) : renderIndex;

    // Performance optimization: Check render cache first
    const renderCacheKey = `${msg.id}_${emailSelected.id === msg.id}_${emailFolder}`;
    let row = renderCache.get(renderCacheKey);

    if (!row) {
      row = createEmailRow(msg, index, sortedItems);
      renderCache.set(renderCacheKey, row.cloneNode(true));
    } else {
      // Use cached row but update dynamic attributes
      row = row.cloneNode(true);
      row.setAttribute('data-email-index', index);
    }

    // Update selection state for cached or new rows
    if (emailSelected.id === msg.id && emailSelected.box === emailFolder) {
      row.classList.add('selected');
      row.setAttribute('aria-selected', 'true');
      setEmailFocusIndex(index);
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

  // Ensure Load More control exists and wire up action
  ensureLoadMoreControl(sortedItems);
}

/**
 * Render email detail view
 * @param {Object} msg - Email message object
 */
export function renderEmailDetail(msg) {
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
  timestamp.title = absoluteTime;

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

/**
 * Handle keyboard navigation in email list
 * @param {KeyboardEvent} event - Keyboard event
 */
export function handleEmailKeyboard(event) {
  const currentList = getEmailCache()[getEmailFolder()] || [];
  if (currentList.length === 0) return;

  const emailListFocusIndex = getEmailFocusIndex();
  const maxIndex = currentList.length - 1;

  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault();
      if (emailListFocusIndex < maxIndex) {
        selectEmailByIndex(emailListFocusIndex + 1);
      }
      break;

    case 'ArrowUp':
      event.preventDefault();
      if (emailListFocusIndex > 0) {
        selectEmailByIndex(emailListFocusIndex - 1);
      }
      break;

    case 'Home':
      event.preventDefault();
      selectEmailByIndex(0);
      break;

    case 'End':
      event.preventDefault();
      selectEmailByIndex(maxIndex);
      break;

    case 'Enter':
    case ' ':
      event.preventDefault();
      if (emailListFocusIndex >= 0 && emailListFocusIndex <= maxIndex) {
        selectEmailByIndex(emailListFocusIndex);
      }
      break;
  }
}

/**
 * Clear email cache
 */
export function clearEmailCache() {
  clearEmailCacheState();
  lastEmailRefresh = 0;
}

// ===== Helper Functions =====

/**
 * Render email panels (list and detail)
 */
function renderEmailPanels() {
  updateEmailFolderButtons();
  let list = getEmailCache()[getEmailFolder()] || [];

  // Performance optimization: Use cached filtered results if available
  const sortCache = getEmailSortCache();
  const emailSearchQuery = getEmailSearchQuery();
  const cacheKey = `${getEmailFolder()}_${emailSearchQuery}`;
  let filteredList = sortCache.get(cacheKey);

  if (!filteredList) {
    // Apply search filter if query exists
    if (emailSearchQuery.trim()) {
      filteredList = filterEmailsBySearch(list, emailSearchQuery);
    } else {
      filteredList = list;
    }

    // Cache the filtered and sorted result
    sortCache.set(cacheKey, filteredList);
  }

  renderEmailList(filteredList);
  const emailSelected = getEmailSelected();
  const sel = filteredList.find(m => m.id === emailSelected.id) || null;
  renderEmailDetail(sel);
}

/**
 * Ensure Load More control appears below list and handles older-page fetch.
 */
function ensureLoadMoreControl(sortedItems) {
  const container = document.querySelector('.email-list-container');
  if (!container) return;

  let btn = document.getElementById('email-load-more');
  if (!btn) {
    btn = document.createElement('button');
    btn.id = 'email-load-more';
    btn.className = 'secondary';
    btn.style.margin = '8px 12px';
    btn.textContent = 'Load more';
    btn.addEventListener('click', onLoadMoreClick);
    container.appendChild(btn);
  }
  // Always show; if nothing more returns, we can briefly indicate
  btn.disabled = false;
}

async function onLoadMoreClick() {
  try {
    const personId = getEmailMonitorPersonId();
    if (!personId) return;
    const folder = getEmailFolder();
    const cache = getEmailCache();
    const list = cache[folder] || [];
    if (list.length === 0) return;
    const oldestId = list.reduce((min, m) => Math.min(min, m.id), list[0].id);
    const url = `${API_PREFIX}/monitor/emails/${personId}?box=${folder}&limit=${EMAIL_PAGE_SIZE}&before_id=${oldestId}`;
    const data = await fetchJson(url);
    const incoming = (folder === 'inbox' ? (data.inbox || []) : (data.sent || []));
    if (!incoming.length) {
      // Nothing more to load
      const btn = document.getElementById('email-load-more');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'No more emails';
        setTimeout(() => { btn.textContent = 'Load more'; btn.disabled = false; }, 2000);
      }
      return;
    }
    // Merge and dedupe
    const byId = new Map();
    for (const m of list) byId.set(m.id, m);
    for (const m of incoming) byId.set(m.id, m);
    const merged = Array.from(byId.values());
    cache[folder] = merged;
    setEmailCache(cache);
    // Clear caches and re-render
    getEmailRenderCache().clear();
    getEmailSortCache().clear();
    renderEmailPanels();
  } catch (err) {
    console.error('Load more failed:', err);
  }
}

/**
 * Update email folder buttons
 */
function updateEmailFolderButtons() {
  updateFolderButtonStates();

  // Update folder title and count
  const folderTitle = document.getElementById('email-folder-title');
  const emailCount = document.getElementById('email-count');
  const emailFolder = getEmailFolder();

  if (folderTitle) {
    folderTitle.textContent = emailFolder === 'inbox' ? 'Inbox' : 'Sent';
  }

  if (emailCount) {
    const currentList = getEmailCache()[emailFolder] || [];
    const count = currentList.length;
    emailCount.textContent = count.toString();
    emailCount.setAttribute('aria-label', `${count} ${count === 1 ? 'email' : 'emails'}`);
  }
}

/**
 * Update folder button states
 */
function updateFolderButtonStates() {
  const inboxBtn = document.getElementById('inbox-btn');
  const sentBtn = document.getElementById('sent-btn');
  const emailFolder = getEmailFolder();

  if (inboxBtn && sentBtn) {
    if (emailFolder === 'inbox') {
      inboxBtn.classList.add('active');
      sentBtn.classList.remove('active');
    } else {
      sentBtn.classList.add('active');
      inboxBtn.classList.remove('active');
    }
  }
}

/**
 * Filter emails by search query
 * @param {Array} emails - Array of email objects
 * @param {string} query - Search query
 * @returns {Array} Filtered emails
 */
function filterEmailsBySearch(emails, query) {
  if (!query.trim()) return emails;

  const searchTerms = query.toLowerCase().split(' ').filter(term => term.length > 0);
  const sortCache = getEmailSortCache();

  // Performance optimization: Use cached search index if available
  const searchCacheKey = `search_${query}_${emails.length}`;
  let cachedResult = sortCache.get(searchCacheKey);

  if (cachedResult) {
    return cachedResult;
  }

  // Performance optimization: Pre-build search index
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

  // Cache the result
  sortCache.set(searchCacheKey, filteredEmails);

  return filteredEmails;
}

/**
 * Calculate optimal page size based on list size
 * @param {number} totalItems - Total number of items
 * @returns {number} Optimal page size
 */
function getOptimalPageSize(totalItems) {
  if (totalItems < 200) return 50;
  if (totalItems < 500) return 75;
  if (totalItems < 1000) return 100;
  return 150;
}

/**
 * Measure performance of an operation
 * @param {string} operation - Operation name
 * @param {Function} fn - Function to measure
 * @returns {*} Result of the function
 */
function measurePerformance(operation, fn) {
  const start = performance.now();
  const result = fn();
  const end = performance.now();

  if (end - start > 16) {
    console.log(`Performance: ${operation} took ${(end - start).toFixed(2)}ms`);
  }

  return result;
}

/**
 * Create an email row element
 * @param {Object} msg - Email message object
 * @param {number} index - Index in the list
 * @param {Array} sortedItems - Sorted array of emails
 * @returns {HTMLElement} Email row element
 */
function createEmailRow(msg, index, sortedItems) {
  const row = document.createElement('div');
  row.className = 'email-row';
  row.setAttribute('role', 'option');
  row.setAttribute('tabindex', '-1');
  row.setAttribute('data-email-id', msg.id);
  row.setAttribute('data-email-index', index);

  // Add ARIA attributes for accessibility
  const emailFolder = getEmailFolder();
  const senderText = emailFolder === 'inbox' ? (msg.sender || 'Unknown') : (msg.to || []).join(', ') || 'Unknown';
  const subjectText = msg.subject || '(no subject)';
  const timeText = formatRelativeTime(msg.sent_at);
  const readStatus = msg.read ? 'read' : 'unread';

  row.setAttribute('aria-label', `Email from ${senderText}, subject: ${subjectText}, ${timeText}, ${readStatus}`);
  row.setAttribute('aria-selected', 'false');

  // Add unread state
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
  sender.setAttribute('aria-hidden', 'true');

  // Subject
  const subject = document.createElement('div');
  subject.className = 'email-subject';
  subject.textContent = subjectText;
  subject.setAttribute('aria-hidden', 'true');

  // Timestamp with relative formatting
  const timestamp = document.createElement('div');
  timestamp.className = 'email-timestamp';
  timestamp.textContent = timeText;
  timestamp.setAttribute('aria-hidden', 'true');

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
  snippet.setAttribute('aria-hidden', 'true');

  // Thread count and metadata
  const metaContainer = document.createElement('div');
  metaContainer.className = 'email-meta';

  // Thread count indicator
  if (msg.thread_id) {
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


/**
 * Format absolute time
 * @param {string} timestamp - ISO timestamp
 * @returns {string} Absolute time string
 */
function formatAbsoluteTime(timestamp) {
  if (!timestamp) return '';

  const emailTime = new Date(timestamp);

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

/**
 * Select email by index
 * @param {number} index - Email index
 */
function selectEmailByIndex(index) {
  const currentList = getEmailCache()[getEmailFolder()] || [];
  if (index >= 0 && index < currentList.length) {
    const sortedItems = [...currentList].sort((a, b) => {
      const timeA = new Date(a.sent_at || 0).getTime();
      const timeB = new Date(b.sent_at || 0).getTime();
      return timeB - timeA;
    });

    setEmailSelected({ box: getEmailFolder(), id: sortedItems[index].id });
    setEmailFocusIndex(index);
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

/**
 * Handle email list scroll for virtual scrolling
 * @param {HTMLElement} listContainer - List container element
 * @param {Array} items - Array of email items
 */
function handleEmailListScroll(listContainer, items) {
  if (scrollTimeout) return;

  scrollTimeout = setTimeout(() => {
    // Only re-render if we have a large list and virtual scrolling is active
    if (items.length > 100) {
      const scrollTop = listContainer.scrollTop;
      const containerHeight = listContainer.clientHeight;
      const itemHeight = 80;

      // Calculate which items should be visible
      const startIndex = Math.floor(scrollTop / itemHeight);
      const endIndex = Math.min(items.length, startIndex + Math.ceil(containerHeight / itemHeight) + 5);

      // Only re-render if the visible range has changed significantly
      const emailListFocusIndex = getEmailFocusIndex();
      if (Math.abs(startIndex - emailListFocusIndex) > 10) {
        renderEmailPanels();
      }
    }

    scrollTimeout = null;
  }, 100);
}

/**
 * Setup keyboard navigation for email list
 * @param {HTMLElement} listEl - List element
 * @param {Array} items - Array of email items
 */
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
  const emailListFocusIndex = getEmailFocusIndex();
  if (emailListFocusIndex >= 0 && emailListFocusIndex < items.length) {
    const emailRows = listEl.querySelectorAll('.email-row');
    if (emailRows[emailListFocusIndex]) {
      emailRows[emailListFocusIndex].setAttribute('tabindex', '0');
    }
  } else if (items.length > 0) {
    // Set focus to first email if none selected
    setEmailFocusIndex(0);
    const firstRow = listEl.querySelector('.email-row');
    if (firstRow) {
      firstRow.setAttribute('tabindex', '0');
    }
  }
}

/**
 * Handle keyboard navigation in email list
 * @param {KeyboardEvent} e - Keyboard event
 */
function handleEmailListKeydown(e) {
  handleEmailKeyboard(e);
}

/**
 * Open email modal
 * @param {Object} msg - Email message object
 */
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

/**
 * Close email modal
 */
function closeEmailModal() {
  const modal = document.getElementById('email-modal');
  if (!modal) return;
  modal.classList.remove('show');
  modal.style.display = 'none';
}

/**
 * Cleanup email caches to prevent memory leaks
 */
function cleanupEmailCaches() {
  const renderCache = getEmailRenderCache();
  const sortCache = getEmailSortCache();

  // Limit cache size to prevent memory leaks
  if (renderCache.size > 100) {
    renderCache.clear();
  }
  if (sortCache.size > 20) {
    sortCache.clear();
  }
}
