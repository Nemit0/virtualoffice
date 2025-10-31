// Data Formatting Utilities Module
// Provides parsing and formatting functions for consistent data transformations

/**
 * Parse comma-separated values into an array
 * @param {string} value - Comma-separated string
 * @returns {string[]} Array of trimmed, non-empty values
 */
export function parseCommaSeparated(value) {
  if (!value) return [];
  return value.split(',').map(entry => entry.trim()).filter(Boolean);
}

/**
 * Parse line-separated text into an array
 * @param {string} value - Newline-separated string
 * @returns {string[]} Array of trimmed, non-empty lines
 */
export function parseLines(value) {
  if (!value) return [];
  return value.split('\\n').map(line => line.trim()).filter(Boolean);
}

/**
 * Parse schedule text into structured time blocks
 * Format: "HH:MM-HH:MM Activity description"
 * @param {string} text - Schedule text with time ranges
 * @returns {Array<{start: string, end: string, activity: string}>} Array of schedule blocks
 */
export function parseSchedule(text) {
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

/**
 * Format schedule blocks back into text format
 * @param {Array<{start: string, end: string, activity: string}>} blocks - Schedule blocks
 * @returns {string} Formatted schedule text
 */
export function formatSchedule(blocks) {
  if (!blocks || !Array.isArray(blocks)) return '';
  return blocks
    .map(block => `${block.start}-${block.end} ${block.activity}`)
    .join('\\n');
}

/**
 * Validate and parse JSON string
 * @param {string} text - JSON string to validate
 * @returns {{valid: boolean, data: any, error: string|null}} Validation result
 */
export function validateJSON(text) {
  if (!text || typeof text !== 'string') {
    return { valid: false, data: null, error: 'Empty or invalid input' };
  }
  
  try {
    const data = JSON.parse(text);
    return { valid: true, data, error: null };
  } catch (err) {
    return { valid: false, data: null, error: err.message };
  }
}

/**
 * Format timestamp into human-readable format
 * @param {string|number|Date} timestamp - Timestamp to format
 * @param {boolean} includeTime - Whether to include time (default: true)
 * @returns {string} Formatted timestamp
 */
export function formatTimestamp(timestamp, includeTime = true) {
  if (!timestamp) return '—';
  
  try {
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return '—';
    
    const options = {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    };
    
    if (includeTime) {
      options.hour = '2-digit';
      options.minute = '2-digit';
    }
    
    return date.toLocaleString('en-US', options);
  } catch (err) {
    console.error('Error formatting timestamp:', err);
    return '—';
  }
}

/**
 * Format relative time (e.g., "2 hours ago", "Yesterday")
 * @param {string} timestamp - ISO timestamp
 * @returns {string} Relative time string
 */
export function formatRelativeTime(timestamp) {
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
    return emailTime.toLocaleDateString();
  }
}

/**
 * Format duration in milliseconds into human-readable format
 * @param {number} ms - Duration in milliseconds
 * @returns {string} Formatted duration (e.g., "2h 30m", "45s", "1.5s")
 */
export function formatDuration(ms) {
  if (typeof ms !== 'number' || ms < 0) return '—';

  if (ms < 1000) {
    return `${ms}ms`;
  }

  const seconds = ms / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  
  if (minutes < 60) {
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  }
  
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}
