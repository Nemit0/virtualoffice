// Style Filter Module
// Handles communication style filtering configuration and status

import { API_PREFIX, fetchJson } from '../core/api.js';
import { setStatus } from '../utils/ui.js';

/**
 * Toggle the style filter on/off
 */
export async function toggleStyleFilter() {
  const toggleEl = document.getElementById('style-filter-toggle');
  if (!toggleEl) return;

  const enabled = toggleEl.checked;

  console.log('[STYLE-FILTER] User toggled style filter:', {
    requested_state: enabled,
    timestamp: new Date().toISOString()
  });

  try {
    setStatus('Updating style filter setting...');
    const result = await fetchJson(`${API_PREFIX}/style-filter/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    });

    console.log('[STYLE-FILTER] Server response to toggle:', {
      requested: enabled,
      actual: result.enabled,
      success: result.enabled === enabled,
      full_response: result,
      timestamp: new Date().toISOString()
    });

    // Update the toggle to reflect the actual server state
    toggleEl.checked = result.enabled;

    // Update the status badge
    updateStyleFilterStatus(result.enabled);

    const statusMsg = result.enabled ? 'Style filter enabled' : 'Style filter disabled';
    setStatus(statusMsg);

  } catch (err) {
    console.error('[STYLE-FILTER] Failed to toggle style filter:', {
      requested_state: enabled,
      error: err.message || String(err),
      timestamp: new Date().toISOString()
    });

    // Revert the toggle on error
    toggleEl.checked = !enabled;
    setStatus(err.message || String(err), true);
  }
}

/**
 * Refresh the style filter status from the server
 */
export async function refreshFilterStatus() {
  try {
    const config = await fetchJson(`${API_PREFIX}/style-filter/config`);

    // Update toggle to match server state
    const toggleEl = document.getElementById('style-filter-toggle');
    if (toggleEl) {
      toggleEl.checked = config.enabled;
    }

    // Update status badge
    updateStyleFilterStatus(config.enabled);

  } catch (err) {
    console.error('[STYLE-FILTER] Failed to fetch filter status:', err);
    // Set default state on error
    updateStyleFilterStatus(true);
  }
}

/**
 * Update the style filter status badge in the UI
 */
export function updateStyleFilterStatus(enabled) {
  const statusEl = document.getElementById('style-filter-status');
  if (statusEl) {
    statusEl.textContent = enabled ? 'Enabled' : 'Disabled';
    statusEl.className = enabled ? 'badge enabled' : 'badge disabled';
  }
}
