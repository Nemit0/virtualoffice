// Core API helpers for VDOS dashboard (ESM)
export const API_PREFIX = '/api/v1';

// Note: setStatus has been moved to utils/ui.js for better organization
// This file now focuses solely on API communication

export async function fetchJson(url, options = {}) {
  const opts = { ...options };
  if (opts.body && !opts.headers) {
    opts.headers = { 'Content-Type': 'application/json' };
  }
  const response = await fetch(url, opts);
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    console.error('[API ERROR]', {
      url,
      status: response.status,
      statusText: response.statusText,
      body: text
    });
    // Try to parse as JSON for better error messages
    try {
      const errorData = JSON.parse(text);
      console.error('[API ERROR DETAILS]', errorData);
      throw new Error(JSON.stringify(errorData, null, 2));
    } catch (e) {
      throw new Error(text || response.statusText);
    }
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

