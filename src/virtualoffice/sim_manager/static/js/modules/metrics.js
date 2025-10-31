// Metrics Module
// Handles planner metrics, token usage, events, and style filter metrics display

import { API_PREFIX, fetchJson } from '../core/api.js';

/**
 * Refresh planner metrics table
 * Fetches and displays the latest planner execution metrics
 */
export async function refreshPlannerMetrics() {
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

/**
 * Refresh token usage table
 * Fetches and displays token usage per model
 */
export async function refreshTokenUsage() {
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

/**
 * Refresh events list
 * Fetches and displays the latest simulation events
 */
export async function refreshEvents() {
  const events = await fetchJson(`${API_PREFIX}/events`);
  const list = document.getElementById('events-list');
  list.innerHTML = '';
  events.slice(-10).reverse().forEach(evt => {
    const li = document.createElement('li');
    li.textContent = `#${evt.id} [${evt.type}] targets=${evt.target_ids.join(', ')} at tick ${evt.at_tick}`;
    list.appendChild(li);
  });
}

/**
 * Refresh style filter metrics
 * Fetches and displays communication style filter metrics
 */
export async function refreshFilterMetrics() {
  try {
    const metrics = await fetchJson(`${API_PREFIX}/style-filter/metrics`);

    // Update transformation count
    const transformCountEl = document.getElementById('filter-transform-count');
    if (transformCountEl) {
      transformCountEl.textContent = metrics.total_transformations || 0;
    }

    // Update tokens used
    const tokensEl = document.getElementById('filter-tokens');
    if (tokensEl) {
      tokensEl.textContent = (metrics.total_tokens || 0).toLocaleString();
    }

    // Update average latency
    const latencyEl = document.getElementById('filter-latency');
    if (latencyEl) {
      const latency = metrics.average_latency_ms || 0;
      latencyEl.textContent = `${latency.toFixed(0)}ms`;
    }

    // Update estimated cost
    const costEl = document.getElementById('filter-cost');
    if (costEl) {
      const cost = metrics.estimated_cost_usd || 0;
      costEl.textContent = `${cost.toFixed(4)}`;
    }

  } catch (err) {
    console.error('[STYLE-FILTER] Failed to fetch filter metrics:', err);
    // Set default values on error
    const transformCountEl = document.getElementById('filter-transform-count');
    const tokensEl = document.getElementById('filter-tokens');
    const latencyEl = document.getElementById('filter-latency');
    const costEl = document.getElementById('filter-cost');

    if (transformCountEl) transformCountEl.textContent = '0';
    if (tokensEl) tokensEl.textContent = '0';
    if (latencyEl) latencyEl.textContent = '0ms';
    if (costEl) costEl.textContent = '$0.00';
  }
}

/**
 * Generic function to render a metric table
 * @param {Array} data - Array of data objects to render
 * @param {string} tableId - ID of the table element
 * @param {Array} columns - Array of column definitions {key, label, formatter}
 */
export function renderMetricTable(data, tableId, columns) {
  const table = document.getElementById(tableId);
  if (!table) {
    console.error(`Table with ID ${tableId} not found`);
    return;
  }

  const tbody = table.querySelector('tbody');
  if (!tbody) {
    console.error(`Table ${tableId} has no tbody element`);
    return;
  }

  tbody.innerHTML = '';

  data.forEach(row => {
    const tr = document.createElement('tr');
    columns.forEach(col => {
      const td = document.createElement('td');
      const value = row[col.key];
      td.textContent = col.formatter ? col.formatter(value) : (value == null ? '' : String(value));
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}
