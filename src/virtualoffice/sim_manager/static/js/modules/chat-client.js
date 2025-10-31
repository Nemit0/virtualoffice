// Chat Client Module
// Handles chat display, conversation selection, and messaging functionality

import { API_PREFIX, fetchJson } from '../core/api.js';
import { announceToScreenReader } from '../utils/ui.js';
import { formatRelativeTime } from '../utils/formatting.js';
import {
  getChatState,
  updateChatState,
  getChatMonitorPersonId,
  setChatMonitorPersonId,
  getChatSelectedConversation,
  setChatSelectedConversation,
  getChatConversations,
  setChatConversations,
  getChatCurrentMessages,
  setChatCurrentMessages,
  getChatSearchQuery,
  setChatSearchQuery,
  getChatVirtualScrolling,
  updateChatVirtualScrolling,
  getChatPagination,
  updateChatPagination,
  getChatRenderCache,
  getChatPerformanceMetrics,
  updateChatPerformanceMetrics,
  getChatAutoRefreshInterval,
  setChatAutoRefreshInterval,
  getPeopleCache,
  getIsSimulationRunning,
  getAutoRefreshEnabled
} from '../core/state.js';

// Export chat state for backward compatibility
export let chatState = {
  get selectedConversationSlug() { return getChatSelectedConversation().slug; },
  set selectedConversationSlug(value) { 
    const current = getChatSelectedConversation();
    setChatSelectedConversation({ ...current, slug: value });
  },
  get selectedConversationType() { return getChatSelectedConversation().type; },
  set selectedConversationType(value) {
    const current = getChatSelectedConversation();
    setChatSelectedConversation({ ...current, type: value });
  },
  get conversations() { return getChatConversations(); },
  set conversations(value) { setChatConversations(value); },
  get currentMessages() { return getChatCurrentMessages(); },
  set currentMessages(value) { setChatCurrentMessages(value); },
  get isLoading() { return getChatState().isLoading; },
  set isLoading(value) { updateChatState({ isLoading: value }); },
  get lastRefresh() { return getChatState().lastRefresh; },
  set lastRefresh(value) { updateChatState({ lastRefresh: value }); },
  get searchQuery() { return getChatSearchQuery(); },
  set searchQuery(value) { setChatSearchQuery(value); },
  get messageSearchQuery() { return getChatState().messageSearchQuery; },
  set messageSearchQuery(value) { updateChatState({ messageSearchQuery: value }); },
  get autoRefreshInterval() { return getChatAutoRefreshInterval(); },
  set autoRefreshInterval(value) { setChatAutoRefreshInterval(value); },
  get isNewConversationSelection() { return getChatState().isNewConversationSelection; },
  set isNewConversationSelection(value) { updateChatState({ isNewConversationSelection: value }); },
  get virtualScrolling() { return getChatVirtualScrolling(); },
  get pagination() { return getChatPagination(); },
  get renderCache() { return getChatRenderCache(); },
  get performanceMetrics() { return getChatPerformanceMetrics(); }
};

// Message search state
let messageSearchResults = [];
let currentSearchResultIndex = -1;

// Search debounce timeout
let conversationSearchTimeout = null;

// Helper function to get current persona handle
function getCurrentPersonaHandle() {
  const peopleCache = getPeopleCache();
  const chatMonitorPersonId = getChatMonitorPersonId();
  const persona = peopleCache.find(p => p.id === chatMonitorPersonId);
  return persona?.chat_handle || 'unknown';
}

// Performance monitoring functions
function startPerformanceTimer() {
  return performance.now();
}

function endPerformanceTimer(startTime, operation) {
  const endTime = performance.now();
  const duration = endTime - startTime;
  trackPerformanceMetric(operation, duration);
  return duration;
}

function trackPerformanceMetric(operation, duration) {
  const metrics = getChatPerformanceMetrics();
  
  if (!metrics.renderTimes) {
    metrics.renderTimes = [];
  }
  
  metrics.renderTimes.push({
    operation: operation,
    duration: duration,
    timestamp: Date.now()
  });

  // Keep only last 50 measurements
  if (metrics.renderTimes.length > 50) {
    metrics.renderTimes.shift();
  }

  // Update average render time
  const recentTimes = metrics.renderTimes.slice(-10);
  metrics.averageRenderTime =
    recentTimes.reduce((sum, metric) => sum + metric.duration, 0) / recentTimes.length;
  metrics.lastRenderTime = duration;

  updateChatPerformanceMetrics(metrics);

  if (duration > 100) {
    console.warn(`Slow chat operation detected: ${operation} took ${duration.toFixed(2)}ms`);
  }

  return duration;
}

function showPerformanceIndicator(duration, operation) {
  const indicator = document.createElement('div');
  indicator.className = 'performance-indicator';

  let color = '#22c55e';
  if (duration > 100) color = '#f59e0b';
  if (duration > 200) color = '#ef4444';

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

// State persistence functions
function saveChatState() {
  try {
    const chatMonitorPersonId = getChatMonitorPersonId();
    const selectedConv = getChatSelectedConversation();
    const stateToSave = {
      selectedConversationSlug: selectedConv.slug,
      selectedConversationType: selectedConv.type,
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
      const chatMonitorPersonId = getChatMonitorPersonId();
      if (state.personId === chatMonitorPersonId) {
        setChatSelectedConversation({
          slug: state.selectedConversationSlug,
          type: state.selectedConversationType
        });
        return true;
      }
    }
  } catch (err) {
    console.warn('Failed to load chat state:', err);
  }
  return false;
}

// Fetch user rooms from chat server
async function fetchUserRooms(chatHandle) {
  try {
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

// Process room conversations
async function processRoomConversations(roomsMetadata, roomMessages) {
  const actualRooms = roomsMetadata.filter(room => !room.is_dm);
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
      unreadCount: 0
    };
  }).sort((a, b) => {
    const timeA = new Date(a.lastActivity || 0);
    const timeB = new Date(b.lastActivity || 0);
    return timeB - timeA;
  });
}

// Process DM conversations
function processDMConversations(dms) {
  const dmGroups = new Map();
  const currentHandle = getCurrentPersonaHandle();

  dms.forEach(message => {
    let otherParticipant = null;

    if (message.room_slug && message.room_slug.startsWith('dm:')) {
      const parts = message.room_slug.split(':');
      if (parts.length >= 3) {
        otherParticipant = parts[1] === currentHandle ? parts[2] : parts[1];
      }
    }

    if (!otherParticipant && message.sender !== currentHandle) {
      otherParticipant = message.sender;
    }

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

// Render conversation sidebar
async function renderConversationSidebar() {
  const conversations = getChatConversations();
  await renderConversationSection('chat-rooms-list', conversations.rooms, 'rooms-count');
  await renderConversationSection('chat-dms-list', conversations.dms, 'dms-count');
}

async function renderConversationSection(containerId, conversations, countId) {
  const container = document.getElementById(containerId);
  const countEl = document.getElementById(countId);

  if (!container) return;

  const searchQuery = getChatSearchQuery();
  const filteredConversations = searchQuery.trim() ?
    await filterConversationsBySearch(conversations, searchQuery) : conversations;

  if (countEl) {
    const totalCount = conversations.length;
    const filteredCount = filteredConversations.length;
    if (searchQuery.trim() && filteredCount !== totalCount) {
      countEl.textContent = `(${filteredCount}/${totalCount})`;
    } else {
      countEl.textContent = `(${totalCount})`;
    }
  }

  container.innerHTML = '';

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

  if (filteredConversations.length === 0 && searchQuery.trim()) {
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

  const selectedConv = getChatSelectedConversation();
  if (conversation.slug === selectedConv.slug) {
    item.classList.add('selected');
  }

  const icon = document.createElement('div');
  icon.className = 'conversation-icon';
  icon.setAttribute('data-conversation-type', conversation.type);
  const iconSymbol = document.createElement('span');
  iconSymbol.className = 'room-type-icon';
  iconSymbol.textContent = conversation.type === 'room' ? '#' : '@';
  iconSymbol.setAttribute('aria-label', conversation.type === 'room' ? 'Room' : 'Direct Message');
  icon.appendChild(iconSymbol);

  const info = document.createElement('div');
  info.className = 'conversation-info';

  const name = document.createElement('div');
  name.className = 'conversation-name';
  const searchQuery = getChatSearchQuery();
  if (searchQuery.trim()) {
    name.innerHTML = highlightSearchMatches(conversation.name, searchQuery);
  } else {
    name.textContent = conversation.name;
  }

  const preview = document.createElement('div');
  preview.className = 'conversation-preview';
  if (conversation.lastMessage) {
    const sender = conversation.lastMessage.sender === getCurrentPersonaHandle() ? 'You' : conversation.lastMessage.sender;
    const body = conversation.lastMessage.body || '';
    const previewText = `${sender}: ${body.length > 50 ? body.slice(0, 50) + '…' : body}`;
    if (searchQuery.trim()) {
      preview.innerHTML = highlightSearchMatches(previewText, searchQuery);
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
    const otherParticipant = conversation.participants?.find(p => p !== getCurrentPersonaHandle());
    if (otherParticipant) {
      participantInfo.textContent = `with ${otherParticipant}`;
      participantInfo.setAttribute('title', `Direct message with ${otherParticipant}`);
    }
  }

  meta.appendChild(time);
  if (participantInfo.textContent) {
    meta.appendChild(participantInfo);
  }

  info.appendChild(name);
  info.appendChild(preview);
  info.appendChild(meta);

  const badges = document.createElement('div');
  badges.className = 'conversation-badges';

  if (conversation.unreadCount > 0) {
    const unreadBadge = document.createElement('span');
    unreadBadge.className = 'unread-badge';
    unreadBadge.textContent = conversation.unreadCount.toString();
    badges.appendChild(unreadBadge);
  }

  item.appendChild(icon);
  item.appendChild(info);
  item.appendChild(badges);

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

// Search functionality
async function filterConversationsBySearch(conversations, searchQuery) {
  if (!searchQuery || !searchQuery.trim()) {
    return conversations;
  }

  const query = searchQuery.toLowerCase().trim();
  const searchTerms = query.split(' ').filter(term => term.length > 0);
  const filteredConversations = [];

  for (const conversation of conversations) {
    let matchFound = false;

    if (conversation.name && searchTerms.some(term =>
      conversation.name.toLowerCase().includes(term))) {
      matchFound = true;
    }

    if (!matchFound && conversation.participants && Array.isArray(conversation.participants)) {
      const participantMatch = conversation.participants.some(participant =>
        participant && searchTerms.some(term =>
          participant.toLowerCase().includes(term))
      );
      if (participantMatch) {
        matchFound = true;
      }
    }

    if (!matchFound && conversation.lastMessage) {
      const lastMsgBody = conversation.lastMessage.body || '';
      const lastMsgSender = conversation.lastMessage.sender || '';

      if (searchTerms.some(term =>
        lastMsgBody.toLowerCase().includes(term) ||
        lastMsgSender.toLowerCase().includes(term))) {
        matchFound = true;
      }
    }

    if (matchFound) {
      filteredConversations.push(conversation);
    }
  }

  return filteredConversations;
}

function highlightSearchMatches(text, searchQuery) {
  if (!searchQuery || !searchQuery.trim() || !text) {
    return text;
  }

  const query = searchQuery.trim();
  const searchTerms = query.split(' ').filter(term => term.length > 0);
  let highlightedText = text;

  searchTerms.forEach(term => {
    const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    highlightedText = highlightedText.replace(regex, '<mark class="search-highlight">$1</mark>');
  });

  return highlightedText;
}

// Conversation selection
export async function selectConversation(conversation) {
  setChatSelectedConversation({
    slug: conversation.slug,
    type: conversation.type
  });
  saveChatState();

  document.querySelectorAll('.conversation-item').forEach(item => {
    item.classList.remove('selected', 'selecting');
  });

  const selectedItem = document.querySelector(`[data-conversation-slug="${conversation.slug}"]`);
  if (selectedItem) {
    selectedItem.classList.add('selecting');
    setTimeout(() => {
      selectedItem.classList.add('selected');
      selectedItem.classList.remove('selecting');
    }, 200);

    selectedItem.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'nearest'
    });
  }

  await loadConversationMessages(conversation);
}

async function loadConversationMessages(conversation, options = {}) {
  const messageThread = document.getElementById('message-thread');
  const conversationTitle = document.querySelector('.conversation-name');
  const conversationMeta = document.querySelector('.conversation-meta .participant-list');
  const messageCount = document.querySelector('.conversation-meta .message-count');

  if (!messageThread) return;

  try {
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

    if (!options.silent) {
      messageThread.innerHTML = `
        <div class="message-thread-placeholder">
          <div class="placeholder-icon" aria-hidden="true">⏳</div>
          <div class="placeholder-text">
            <h4>Loading messages...</h4>
            <p>Please wait while we fetch the conversation history</p>
          </div>
        </div>
      `;
    }

    let messages = [];
    if (conversation.type === 'room') {
      const response = await fetch(`${API_PREFIX}/monitor/chat/room/${encodeURIComponent(conversation.slug)}/messages`);
      if (response.ok) {
        messages = await response.json();
      }
    } else {
      messages = conversation.messages || [];
    }

    messages.sort((a, b) => new Date(a.sent_at) - new Date(b.sent_at));
    setChatCurrentMessages(messages);
    renderMessages(messages);

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

// Render messages
export function renderMessages(messages) {
  const startTime = startPerformanceTimer();
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

  // Store scroll state before rendering
  const wasAtBottom = isScrolledToBottom(messageThread);
  const previousScrollTop = messageThread.scrollTop;
  const previousScrollHeight = messageThread.scrollHeight;
  const previousMessageCount = messageThread.querySelectorAll('.message-group').length;

  // Group messages by sender and time proximity
  const messageGroups = groupMessagesBySender(messages);

  // Determine rendering strategy based on message count and performance
  const messageCount = messages.length;
  const shouldUseVirtualScrolling = messageCount > 100;
  const shouldUsePagination = messageCount > 500;

  if (shouldUsePagination) {
    renderMessageThreadWithPagination(messageThread, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount);
  } else if (shouldUseVirtualScrolling) {
    renderMessageThreadWithVirtualScrolling(messageThread, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount);
  } else {
    renderMessageThreadStandard(messageThread, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount);
  }

  const duration = endPerformanceTimer(startTime, 'renderMessages');
  if (messageCount > 50) {
    showPerformanceIndicator(duration, 'Render');
  }
}

function groupMessagesBySender(messages) {
  const groups = [];
  let currentGroup = null;

  const validMessages = messages.filter(message => {
    if (!message || !message.sender || !message.sent_at) {
      console.warn('Skipping invalid message:', message);
      return false;
    }
    return true;
  });

  validMessages.forEach(message => {
    const messageTime = new Date(message.sent_at);
    const shouldStartNewGroup = !currentGroup ||
      currentGroup.sender !== message.sender ||
      (messageTime - new Date(currentGroup.lastMessageTime)) > 5 * 60 * 1000;

    if (shouldStartNewGroup) {
      currentGroup = {
        sender: message.sender,
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

function renderMessageThreadStandard(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount) {
  threadEl.innerHTML = '';

  const fragment = document.createDocumentFragment();
  messageGroups.forEach(group => {
    const groupEl = createMessageGroup(group);
    fragment.appendChild(groupEl);
  });
  threadEl.appendChild(fragment);

  handleScrollBehaviorAfterRender(threadEl, messageGroups.length, previousMessageCount, wasAtBottom, previousScrollTop, previousScrollHeight);
}

function createMessageGroup(group) {
  const groupDiv = document.createElement('div');
  groupDiv.className = 'message-group';
  groupDiv.setAttribute('data-sender', group.sender);

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

  group.messages.forEach(message => {
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = message.body || '';
    bubble.appendChild(content);

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

// Virtual scrolling implementation
function renderMessageThreadWithVirtualScrolling(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount) {
  const virtualScrolling = getChatVirtualScrolling();
  updateChatVirtualScrolling({ enabled: true, totalItems: messageGroups.length });

  threadEl.innerHTML = '';
  threadEl.classList.add('virtual-scroll-container');

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

  if (!virtualScrolling.itemHeight) {
    updateChatVirtualScrolling({ itemHeight: 80 });
  }

  updateVirtualScrollRange(threadEl);
  renderVisibleMessageGroups(visibleContainer, messageGroups, topSpacer, bottomSpacer);
  setupVirtualScrollListener(threadEl, messageGroups);
  handleScrollBehaviorAfterRender(threadEl, messageGroups.length, previousMessageCount, wasAtBottom, previousScrollTop, previousScrollHeight);

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

  setTimeout(() => {
    if (indicator.parentNode) {
      indicator.parentNode.removeChild(indicator);
    }
  }, 3000);
}

function updateVirtualScrollRange(container) {
  const containerRect = container.getBoundingClientRect();
  const virtualScrolling = getChatVirtualScrolling();
  const itemHeight = virtualScrolling.itemHeight || 80;
  const buffer = virtualScrolling.renderBuffer || 5;
  const scrollTop = container.scrollTop;

  const visibleStart = Math.max(0, Math.floor(scrollTop / itemHeight) - buffer);
  const visibleEnd = Math.min(virtualScrolling.totalItems - 1,
    Math.floor((scrollTop + containerRect.height) / itemHeight) + buffer);

  updateChatVirtualScrolling({
    containerHeight: containerRect.height,
    scrollTop: scrollTop,
    visibleStart: visibleStart,
    visibleEnd: visibleEnd
  });
}

function renderVisibleMessageGroups(container, messageGroups, topSpacer, bottomSpacer) {
  const virtualScrolling = getChatVirtualScrolling();
  const { visibleStart, visibleEnd, itemHeight } = virtualScrolling;
  const renderCache = getChatRenderCache();

  topSpacer.style.height = `${visibleStart * itemHeight}px`;
  bottomSpacer.style.height = `${(messageGroups.length - visibleEnd - 1) * itemHeight}px`;

  container.innerHTML = '';
  const fragment = document.createDocumentFragment();

  for (let i = visibleStart; i <= visibleEnd; i++) {
    if (messageGroups[i]) {
      const cacheKey = `group-${i}-${JSON.stringify(messageGroups[i]).slice(0, 100)}`;
      let groupEl = renderCache.get(cacheKey);

      if (!groupEl) {
        groupEl = createMessageGroup(messageGroups[i]);
        groupEl.style.minHeight = `${itemHeight}px`;
        renderCache.set(cacheKey, groupEl.cloneNode(true));
      } else {
        groupEl = groupEl.cloneNode(true);
      }

      fragment.appendChild(groupEl);
    }
  }

  container.appendChild(fragment);

  if (renderCache.size > 200) {
    const entries = Array.from(renderCache.entries());
    entries.slice(0, 100).forEach(([key]) => renderCache.delete(key));
  }
}

function setupVirtualScrollListener(container, messageGroups) {
  container.removeEventListener('scroll', handleVirtualScroll);

  let scrollTimeout;
  function handleVirtualScroll() {
    const metrics = getChatPerformanceMetrics();
    updateChatPerformanceMetrics({ ...metrics, scrollEvents: (metrics.scrollEvents || 0) + 1 });

    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(() => {
      updateVirtualScrollRange(container);
      const visibleContainer = container.querySelector('.virtual-scroll-visible');
      const topSpacer = container.querySelector('.virtual-scroll-spacer-top');
      const bottomSpacer = container.querySelector('.virtual-scroll-spacer-bottom');

      if (visibleContainer && topSpacer && bottomSpacer) {
        renderVisibleMessageGroups(visibleContainer, messageGroups, topSpacer, bottomSpacer);
      }
    }, 16);
  }

  container.addEventListener('scroll', handleVirtualScroll, { passive: true });
}

// Pagination implementation
function renderMessageThreadWithPagination(threadEl, messageGroups, wasAtBottom, previousScrollTop, previousScrollHeight, previousMessageCount) {
  const pagination = getChatPagination();
  const pageSize = pagination.pageSize || 50;
  const totalPages = Math.ceil(messageGroups.length / pageSize);
  
  updateChatPagination({
    enabled: true,
    totalPages: totalPages
  });

  const currentState = getChatState();
  if (currentState.isNewConversationSelection || wasAtBottom) {
    updateChatPagination({ currentPage: totalPages - 1 });
  }

  threadEl.innerHTML = '';
  threadEl.classList.add('paginated-container');

  const paginationTop = createPaginationControls('top');
  const messageContainer = document.createElement('div');
  messageContainer.className = 'paginated-messages';
  const paginationBottom = createPaginationControls('bottom');

  threadEl.appendChild(paginationTop);
  threadEl.appendChild(messageContainer);
  threadEl.appendChild(paginationBottom);

  renderMessagePage(messageContainer, messageGroups);
  handleScrollBehaviorAfterRender(messageContainer, messageGroups.length, previousMessageCount, wasAtBottom, previousScrollTop, previousScrollHeight);
}

function createPaginationControls(position) {
  const controls = document.createElement('div');
  controls.className = `pagination-controls pagination-${position}`;

  const info = document.createElement('span');
  info.className = 'pagination-info';

  const prevBtn = document.createElement('button');
  prevBtn.className = 'pagination-btn secondary';
  prevBtn.innerHTML = '← Previous';
  const pagination = getChatPagination();
  prevBtn.disabled = pagination.currentPage === 0;
  prevBtn.onclick = () => navigateToPage(pagination.currentPage - 1);

  const nextBtn = document.createElement('button');
  nextBtn.className = 'pagination-btn secondary';
  nextBtn.innerHTML = 'Next →';
  nextBtn.disabled = pagination.currentPage >= pagination.totalPages - 1;
  nextBtn.onclick = () => navigateToPage(pagination.currentPage + 1);

  const jumpToEnd = document.createElement('button');
  jumpToEnd.className = 'pagination-btn secondary';
  jumpToEnd.innerHTML = 'Latest';
  jumpToEnd.onclick = () => navigateToPage(pagination.totalPages - 1);

  updatePaginationInfo(info);

  controls.appendChild(prevBtn);
  controls.appendChild(info);
  controls.appendChild(nextBtn);
  controls.appendChild(jumpToEnd);

  return controls;
}

function updatePaginationInfo(infoEl) {
  const pagination = getChatPagination();
  const { currentPage, totalPages, pageSize } = pagination;
  const currentMessages = getChatCurrentMessages();
  const totalMessages = currentMessages.length;
  const startMessage = currentPage * pageSize + 1;
  const endMessage = Math.min((currentPage + 1) * pageSize, totalMessages);

  infoEl.textContent = `Page ${currentPage + 1} of ${totalPages} (Messages ${startMessage}-${endMessage} of ${totalMessages})`;
}

function navigateToPage(pageNumber) {
  const pagination = getChatPagination();
  if (pageNumber < 0 || pageNumber >= pagination.totalPages) return;

  updateChatPagination({ currentPage: pageNumber });

  const messageContainer = document.querySelector('.paginated-messages');
  if (messageContainer) {
    const currentMessages = getChatCurrentMessages();
    const messageGroups = groupMessagesBySender(currentMessages);
    renderMessagePage(messageContainer, messageGroups);
  }

  document.querySelectorAll('.pagination-controls').forEach(controls => {
    const prevBtn = controls.querySelector('.pagination-btn:first-child');
    const nextBtn = controls.querySelector('.pagination-btn:nth-child(3)');
    const info = controls.querySelector('.pagination-info');

    if (prevBtn) prevBtn.disabled = pagination.currentPage === 0;
    if (nextBtn) nextBtn.disabled = pagination.currentPage >= pagination.totalPages - 1;
    if (info) updatePaginationInfo(info);
  });
}

function renderMessagePage(container, messageGroups) {
  const pagination = getChatPagination();
  const { currentPage, pageSize } = pagination;
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
  setTimeout(() => {
    const hasNewMessages = currentMessageCount > previousMessageCount;
    const currentState = getChatState();
    const isNewSelection = currentState.isNewConversationSelection;

    updateChatState({ isNewConversationSelection: false });

    if (isNewSelection || wasAtBottom || !hasNewMessages) {
      scrollToBottom(container, true);
      hideNewMessageIndicator();
    } else {
      const scrollDelta = container.scrollHeight - previousScrollHeight;
      container.scrollTop = previousScrollTop + scrollDelta;

      if (hasNewMessages) {
        showNewMessageIndicator(currentMessageCount - previousMessageCount);
      }
    }

    setupScrollListener(container);
  }, 50);
}

// Scroll helpers
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
  hideNewMessageIndicator();

  const threadEl = document.getElementById('message-thread');
  if (!threadEl) return;

  const indicator = document.createElement('div');
  indicator.id = 'new-message-indicator';
  indicator.className = 'new-message-indicator';
  indicator.innerHTML = `
    <span>↓ ${messageCount} new message${messageCount > 1 ? 's' : ''}</span>
  `;

  indicator.style.position = 'absolute';
  indicator.style.bottom = '20px';
  indicator.style.left = '50%';
  indicator.style.transform = 'translateX(-50%)';
  indicator.style.zIndex = '100';
  indicator.style.cursor = 'pointer';

  indicator.addEventListener('click', () => {
    scrollToBottom(threadEl, true);
    hideNewMessageIndicator();
  });

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

  threadEl.hasScrollListener = true;

  let scrollTimeout;
  threadEl.addEventListener('scroll', () => {
    clearTimeout(scrollTimeout);
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
  setChatSelectedConversation({ slug: null, type: null });
  saveChatState();

  document.querySelectorAll('.conversation-item').forEach(item => {
    item.classList.remove('selected');
  });

  renderMessageViewPlaceholder();
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

// Placeholder and error rendering
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

// Main refresh function
export async function refreshChatTab() {
  const chatMonitorPersonId = getChatMonitorPersonId();
  
  if (!chatMonitorPersonId) {
    renderChatPlaceholder();
    return;
  }

  const statusEl = document.getElementById('chat-last-refresh');
  if (statusEl) {
    statusEl.textContent = 'Refreshing...';
  }

  try {
    updateChatState({ isLoading: true });
    updateChatLoadingState(true);

    const peopleCache = getPeopleCache();
    const persona = peopleCache.find(p => p.id === chatMonitorPersonId);
    if (!persona || !persona.chat_handle) {
      throw new Error('Selected persona does not have a chat handle');
    }

    const fetchPromises = [
      fetchUserRooms(persona.chat_handle),
      fetchJson(`${API_PREFIX}/monitor/chat/messages/${chatMonitorPersonId}?scope=all&limit=100`)
    ];

    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Request timeout - please check your connection')), 10000);
    });

    const [roomsData, messagesData] = await Promise.race([
      Promise.all(fetchPromises),
      timeoutPromise
    ]);

    const rooms = await processRoomConversations(roomsData, messagesData.rooms || []);
    const dms = processDMConversations(messagesData.dms || []);
    
    setChatConversations({ rooms, dms });
    updateChatState({ lastRefresh: new Date() });

    const hasRestoredState = loadChatState();
    await renderConversationSidebar();

    if (hasRestoredState) {
      const selectedConv = getChatSelectedConversation();
      if (selectedConv.slug) {
        const conversation = [...rooms, ...dms].find(c => c.slug === selectedConv.slug);

        if (conversation) {
          document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('selected');
          });

          const selectedItem = document.querySelector(`[data-conversation-slug="${conversation.slug}"]`);
          if (selectedItem) {
            selectedItem.classList.add('selected');
          }

          await loadConversationMessages(conversation);
        } else {
          setChatSelectedConversation({ slug: null, type: null });
          saveChatState();
          renderMessageViewPlaceholder();
        }
      } else {
        renderMessageViewPlaceholder();
      }
    } else {
      renderMessageViewPlaceholder();
    }

    if (statusEl) {
      const lastRefresh = getChatState().lastRefresh;
      statusEl.textContent = `Last updated: ${lastRefresh.toLocaleTimeString()}`;
    }

    setupChatAutoRefresh();

  } catch (err) {
    console.error('Failed to refresh chat tab:', err);
    if (statusEl) {
      statusEl.textContent = 'Refresh failed';
    }
    renderChatError('Failed to load conversations. Please try again.');
  } finally {
    updateChatState({ isLoading: false });
    updateChatLoadingState(false);
  }
}

// Auto-refresh setup
export function setupChatAutoRefresh() {
  const autoRefreshInterval = getChatAutoRefreshInterval();
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
    setChatAutoRefreshInterval(null);
  }

  const isSimulationRunning = getIsSimulationRunning();
  const autoRefreshEnabled = getAutoRefreshEnabled();
  const chatMonitorPersonId = getChatMonitorPersonId();

  if (isSimulationRunning && autoRefreshEnabled && chatMonitorPersonId) {
    const newInterval = setInterval(async () => {
      const chatState = getChatState();
      if (chatMonitorPersonId &&
        document.getElementById('tab-chat').style.display !== 'none' &&
        !chatState.isLoading) {

        try {
          const statusEl = document.getElementById('chat-last-refresh');
          if (statusEl) {
            statusEl.textContent = 'Auto-refreshing...';
          }

          const currentMessages = getChatCurrentMessages();
          const previousMessageCount = currentMessages.length;

          await refreshChatTab();

          const newMessages = getChatCurrentMessages();
          if (newMessages.length > previousMessageCount) {
            showNewMessageIndicator(newMessages.length - previousMessageCount);
          }

          if (statusEl) {
            const lastRefresh = getChatState().lastRefresh;
            statusEl.textContent = `Last updated: ${lastRefresh.toLocaleTimeString()}`;
          }

        } catch (err) {
          console.error('Auto-refresh failed:', err);
        }
      }
    }, 10000);

    setChatAutoRefreshInterval(newInterval);
  }
}

// Search conversations with debouncing
export function searchConversations(query) {
  // Clear existing timeout
  if (conversationSearchTimeout) {
    clearTimeout(conversationSearchTimeout);
  }
  
  // Debounce search for 300ms
  conversationSearchTimeout = setTimeout(() => {
    setChatSearchQuery(query);
    renderConversationSidebar();
    announceToScreenReader(`Search completed. Conversations filtered.`);
  }, 300);
}

// Keyboard navigation
export function handleChatKeyboard(event) {
  const activeElement = document.activeElement;
  const chatSearchInput = document.getElementById('chat-search');
  const messageSearch = document.getElementById('message-search');

  if (activeElement === chatSearchInput || activeElement === messageSearch) {
    return;
  }

  switch (event.key.toLowerCase()) {
    case 'r':
      event.preventDefault();
      refreshChatTab();
      announceToScreenReader('Refreshing chat conversations');
      break;

    case '/':
      event.preventDefault();
      if (chatSearchInput) {
        chatSearchInput.focus();
        announceToScreenReader('Conversation search focused');
      }
      break;

    case 'escape':
      event.preventDefault();
      clearConversationSelection();
      announceToScreenReader('Conversation selection cleared');
      break;
  }
}

// Performance optimization
export function optimizeRenderingPerformance() {
  const renderCache = getChatRenderCache();
  const messageCount = getChatCurrentMessages().length;
  const metrics = getChatPerformanceMetrics();
  const averageRenderTime = metrics.averageRenderTime || 0;

  if (renderCache.size > 1000) {
    const entries = Array.from(renderCache.entries());
    const recentEntries = entries.slice(-500);
    renderCache.clear();
    recentEntries.forEach(([key, value]) => {
      renderCache.set(key, value);
    });
    console.log('Render cache optimized: cleared old entries');
  }

  const virtualScrolling = getChatVirtualScrolling();
  if (averageRenderTime > 100) {
    updateChatVirtualScrolling({
      renderBuffer: Math.max(5, virtualScrolling.renderBuffer - 2),
      itemHeight: Math.max(60, virtualScrolling.itemHeight - 10)
    });
  } else if (averageRenderTime < 30) {
    updateChatVirtualScrolling({
      renderBuffer: Math.min(15, virtualScrolling.renderBuffer + 1),
      itemHeight: Math.min(120, virtualScrolling.itemHeight + 5)
    });
  }

  if (messageCount > 50) {
    console.log(`Chat Performance: ${messageCount} messages, ${averageRenderTime.toFixed(2)}ms avg render time`);
  }
}

// Render conversation list (for backward compatibility)
export function renderConversationList(conversations) {
  renderConversationSidebar();
}

// Export all functions
export {
  chatState as default
};
