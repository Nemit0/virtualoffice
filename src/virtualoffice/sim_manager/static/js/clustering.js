/**
 * Email Clustering Visualization Module
 *
 * Handles all functionality for the Email Clusters tab including:
 * - Loading personas and their indexing status
 * - Triggering index building
 * - Polling for progress updates
 * - Rendering 3D visualizations with Plotly.js
 * - Interactive features (click, zoom, toggle clusters)
 */

// Configuration
const CLUSTERING_API_BASE = 'http://127.0.0.1:8016';
const POLL_INTERVAL_MS = 2000; // Poll every 2 seconds during indexing

// State
let currentPersonaId = null;
let pollingIntervalId = null;
let currentVisualizationData = null;
let isInitialized = false;

// Initialize when tab is activated
export function initClustering() {
    if (isInitialized) {
        console.log('[Clustering] Already initialized, skipping...');
        // Just refresh personas on subsequent calls
        loadPersonas();
        return;
    }

    console.log('[Clustering] Initializing clustering tab');
    isInitialized = true;

    // Set up event listeners
    setupEventListeners();

    // Load personas immediately
    loadPersonas();
}

function setupEventListeners() {
    const personaSelect = document.getElementById('cluster-persona-select');
    const indexBtn = document.getElementById('cluster-index-btn');
    const autoOptimizeBtn = document.getElementById('cluster-auto-optimize-btn');

    if (personaSelect) {
        personaSelect.addEventListener('change', onPersonaChange);
    }

    if (indexBtn) {
        indexBtn.addEventListener('click', onIndexButtonClick);
    }

    if (autoOptimizeBtn) {
        autoOptimizeBtn.addEventListener('click', onAutoOptimizeClick);
    }

    // Set up parameter slider listeners
    const epsSlider = document.getElementById('dbscan-eps');
    const minSamplesSlider = document.getElementById('dbscan-min-samples');
    const perplexitySlider = document.getElementById('tsne-perplexity');

    if (epsSlider) {
        epsSlider.addEventListener('input', (e) => {
            document.getElementById('dbscan-eps-value').textContent = e.target.value;
        });
    }

    if (minSamplesSlider) {
        minSamplesSlider.addEventListener('input', (e) => {
            document.getElementById('dbscan-min-samples-value').textContent = e.target.value;
        });
    }

    if (perplexitySlider) {
        perplexitySlider.addEventListener('input', (e) => {
            document.getElementById('tsne-perplexity-value').textContent = e.target.value;
        });
    }

    console.log('[Clustering] Event listeners set up');
}

// ============================================================================
// Persona Management
// ============================================================================

async function loadPersonas() {
    console.log('[Clustering] Loading personas...');

    try {
        const response = await fetch(`${CLUSTERING_API_BASE}/clustering/personas`);

        if (!response.ok) {
            throw new Error(`Failed to load personas: ${response.statusText}`);
        }

        const personas = await response.json();
        populatePersonaDropdown(personas);

        console.log(`[Clustering] Loaded ${personas.length} personas`);

    } catch (error) {
        console.error('[Clustering] Error loading personas:', error);
        showError('Failed to load personas. Make sure the clustering server is running.');
    }
}

function populatePersonaDropdown(personas) {
    const select = document.getElementById('cluster-persona-select');
    if (!select) return;

    // Clear existing options
    select.innerHTML = '<option value="">Select a persona...</option>';

    // Add personas with status indicators
    personas.forEach(persona => {
        const option = document.createElement('option');
        option.value = persona.persona_id;

        let statusIcon = '';
        if (persona.status === 'completed') {
            statusIcon = '✅ ';
        } else if (persona.status === 'indexing') {
            statusIcon = '⏳ ';
        } else if (persona.status === 'failed') {
            statusIcon = '❌ ';
        }

        option.textContent = `${statusIcon}${persona.persona_name} (${persona.total_emails} emails)`;
        option.dataset.status = persona.status;
        option.dataset.totalEmails = persona.total_emails;

        select.appendChild(option);
    });
}

async function onPersonaChange(event) {
    const personaId = parseInt(event.target.value);

    if (!personaId) {
        hideAllSections();
        return;
    }

    console.log(`[Clustering] Persona changed to ${personaId}`);
    currentPersonaId = personaId;

    // Stop any ongoing polling
    stopPolling();

    // Load status for this persona
    await loadPersonaStatus(personaId);
}

async function loadPersonaStatus(personaId) {
    try {
        const response = await fetch(`${CLUSTERING_API_BASE}/clustering/${personaId}/status`);

        if (!response.ok) {
            throw new Error(`Failed to load status: ${response.statusText}`);
        }

        const status = await response.json();
        updateUI(status);

        // If indexing, start polling
        if (status.status === 'indexing') {
            startPolling(personaId);
        }

    } catch (error) {
        console.error('[Clustering] Error loading status:', error);
        showError('Failed to load persona status');
    }
}

// ============================================================================
// UI Updates
// ============================================================================

function updateUI(status) {
    const statusInfo = document.getElementById('cluster-status-info');
    const statusText = document.getElementById('cluster-status-text');
    const statusDetails = document.getElementById('cluster-status-details');
    const indexBtn = document.getElementById('cluster-index-btn');
    const progressDiv = document.getElementById('cluster-progress');
    const statsDiv = document.getElementById('cluster-stats');
    const vizDiv = document.getElementById('cluster-visualization');
    const placeholderDiv = document.getElementById('cluster-viz-placeholder');

    if (!statusInfo) return;

    // Show status info
    statusInfo.style.display = 'block';

    // Update status text and button
    if (status.status === 'not_indexed') {
        statusText.textContent = 'Not indexed';
        statusDetails.textContent = 'Click "Index Data" to build the cluster visualization';
        indexBtn.textContent = '🔄 Index Data';
        indexBtn.disabled = false;
        progressDiv.style.display = 'none';
        statsDiv.style.display = 'none';
        vizDiv.style.display = 'none';
        placeholderDiv.style.display = 'flex';

    } else if (status.status === 'indexing') {
        statusText.textContent = 'Indexing...';
        statusDetails.textContent = status.current_step;
        indexBtn.disabled = true;
        progressDiv.style.display = 'block';
        updateProgress(status.progress_percent, status.current_step);
        statsDiv.style.display = 'none';
        vizDiv.style.display = 'none';
        placeholderDiv.style.display = 'flex';

    } else if (status.status === 'completed') {
        statusText.textContent = 'Indexed';
        statusDetails.textContent = `${status.total_emails} emails indexed`;
        indexBtn.textContent = '🔄 Re-index';
        indexBtn.disabled = false;
        progressDiv.style.display = 'none';

        // Re-enable auto-optimize button
        const optimizeBtn = document.getElementById('cluster-auto-optimize-btn');
        const guidelineInput = document.getElementById('cluster-optimize-guideline');
        if (optimizeBtn) {
            optimizeBtn.disabled = false;
            optimizeBtn.textContent = '✨ Auto-Optimize with GPT';
            optimizeBtn.style.opacity = '1';
            optimizeBtn.style.cursor = 'pointer';
        }
        if (guidelineInput) {
            guidelineInput.disabled = false;
        }

        // Load visualization
        loadVisualization(currentPersonaId);

    } else if (status.status === 'failed') {
        statusText.textContent = 'Failed';
        statusDetails.textContent = status.error_message || 'Indexing failed';
        indexBtn.textContent = '🔄 Retry';
        indexBtn.disabled = false;
        progressDiv.style.display = 'none';
        statsDiv.style.display = 'none';
        vizDiv.style.display = 'none';
        placeholderDiv.style.display = 'flex';

        // Re-enable auto-optimize button on failure too
        const optimizeBtn = document.getElementById('cluster-auto-optimize-btn');
        const guidelineInput = document.getElementById('cluster-optimize-guideline');
        if (optimizeBtn) {
            optimizeBtn.disabled = false;
            optimizeBtn.textContent = '✨ Auto-Optimize with GPT';
            optimizeBtn.style.opacity = '1';
            optimizeBtn.style.cursor = 'pointer';
        }
        if (guidelineInput) {
            guidelineInput.disabled = false;
        }
    }
}

function updateProgress(percent, step) {
    const progressBar = document.getElementById('cluster-progress-bar');
    const progressPercent = document.getElementById('cluster-progress-percent');
    const progressStep = document.getElementById('cluster-progress-step');

    if (progressBar) {
        progressBar.style.width = `${percent}%`;
    }

    if (progressPercent) {
        progressPercent.textContent = `${Math.round(percent)}%`;
    }

    if (progressStep) {
        progressStep.textContent = step;
    }
}

function hideAllSections() {
    document.getElementById('cluster-status-info').style.display = 'none';
    document.getElementById('cluster-progress').style.display = 'none';
    document.getElementById('cluster-stats').style.display = 'none';
    document.getElementById('cluster-list').style.display = 'none';
    document.getElementById('cluster-visualization').style.display = 'none';
    document.getElementById('cluster-viz-placeholder').style.display = 'flex';
}

// ============================================================================
// Indexing
// ============================================================================

async function onIndexButtonClick() {
    if (!currentPersonaId) return;

    // Gather parameter values from sliders
    const dbscanEps = parseFloat(document.getElementById('dbscan-eps').value);
    const dbscanMinSamples = parseInt(document.getElementById('dbscan-min-samples').value);
    const tsnePerplexity = parseFloat(document.getElementById('tsne-perplexity').value);

    console.log(`[Clustering] Starting index build for persona ${currentPersonaId}`, {
        dbscan_eps: dbscanEps,
        dbscan_min_samples: dbscanMinSamples,
        tsne_perplexity: tsnePerplexity
    });

    try {
        const response = await fetch(`${CLUSTERING_API_BASE}/clustering/index/${currentPersonaId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                dbscan_eps: dbscanEps,
                dbscan_min_samples: dbscanMinSamples,
                tsne_perplexity: tsnePerplexity
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start indexing');
        }

        const result = await response.json();
        console.log('[Clustering] Indexing started:', result);

        // Start polling for progress
        startPolling(currentPersonaId);

    } catch (error) {
        console.error('[Clustering] Error starting indexing:', error);
        showError(error.message);
    }
}

async function onAutoOptimizeClick() {
    console.log('[Clustering] Auto-optimize button clicked!', 'currentPersonaId:', currentPersonaId);

    if (!currentPersonaId) {
        alert('⚠️ Please select a persona first!\n\nTo use auto-optimization:\n1. Select a persona from the dropdown above\n2. Click "Index Data" to build the initial clusters\n3. Then click "Auto-Optimize with GPT"');
        return;
    }

    // Get button and guideline input
    const button = document.getElementById('cluster-auto-optimize-btn');
    const guidelineInput = document.getElementById('cluster-optimize-guideline');
    const guideline = guidelineInput ? guidelineInput.value.trim() : '';

    console.log(`[Clustering] Starting auto-optimization for persona ${currentPersonaId}`);
    if (guideline) {
        console.log(`[Clustering] Using guideline: "${guideline}"`);
    }

    // Confirm with user
    const message = guideline
        ? `Auto-optimize clustering parameters using GPT?\n\nGoal: ${guideline}\n\nThis will:\n- Test multiple parameter configurations\n- Use GPT to evaluate cluster quality\n- Take several minutes and make ~6-12 API calls\n\nContinue?`
        : `Auto-optimize clustering parameters using GPT?\n\nThis will:\n- Test multiple parameter configurations\n- Use GPT to evaluate cluster quality\n- Take several minutes and make ~6-12 API calls\n\nContinue?`;

    if (!confirm(message)) {
        return;
    }

    // Disable button and show loading state
    if (button) {
        button.disabled = true;
        button.textContent = '⏳ Optimizing... (this may take several minutes)';
        button.style.opacity = '0.6';
        button.style.cursor = 'not-allowed';
    }

    // Disable guideline input during optimization
    if (guidelineInput) {
        guidelineInput.disabled = true;
    }

    try {
        const requestBody = guideline ? { guideline } : {};

        const response = await fetch(`${CLUSTERING_API_BASE}/clustering/optimize/${currentPersonaId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start optimization');
        }

        const result = await response.json();
        console.log('[Clustering] Optimization started:', result);

        // Show status message in the UI
        const statusDiv = document.getElementById('cluster-status');
        if (statusDiv) {
            statusDiv.textContent = '🤖 Auto-optimization in progress... Testing multiple configurations with GPT evaluation.';
            statusDiv.className = 'status-msg indexing';
        }

        // Start polling for progress
        startPolling(currentPersonaId);

    } catch (error) {
        console.error('[Clustering] Error starting optimization:', error);
        showError(error.message);

        // Re-enable button on error
        if (button) {
            button.disabled = false;
            button.textContent = '✨ Auto-Optimize with GPT';
            button.style.opacity = '1';
            button.style.cursor = 'pointer';
        }
        if (guidelineInput) {
            guidelineInput.disabled = false;
        }
    }
}

function startPolling(personaId) {
    console.log('[Clustering] Starting progress polling');

    // Stop any existing polling
    stopPolling();

    // Poll immediately
    loadPersonaStatus(personaId);

    // Then poll regularly
    pollingIntervalId = setInterval(() => {
        loadPersonaStatus(personaId);
    }, POLL_INTERVAL_MS);
}

function stopPolling() {
    if (pollingIntervalId) {
        console.log('[Clustering] Stopping progress polling');
        clearInterval(pollingIntervalId);
        pollingIntervalId = null;
    }
}

// ============================================================================
// Visualization
// ============================================================================

async function loadVisualization(personaId) {
    console.log(`[Clustering] Loading visualization for persona ${personaId}`);

    try {
        const response = await fetch(`${CLUSTERING_API_BASE}/clustering/${personaId}/data`);

        if (!response.ok) {
            throw new Error(`Failed to load visualization data: ${response.statusText}`);
        }

        const data = await response.json();
        currentVisualizationData = data;

        console.log('[Clustering] Received visualization data:', {
            clusters: data.clusters?.length,
            points: data.points?.length,
            statistics: data.statistics
        });

        // Update statistics
        updateStatistics(data.statistics);

        // Update cluster list
        updateClusterList(data.clusters);

        // Render 3D plot
        if (data.points && data.points.length > 0) {
            console.log('[Clustering] Rendering 3D plot with', data.points.length, 'points');
            render3DPlot(data);
        } else {
            console.warn('[Clustering] No point data to render in 3D plot');
        }

        console.log('[Clustering] Visualization loaded successfully');

    } catch (error) {
        console.error('[Clustering] Error loading visualization:', error);
        showError('Failed to load visualization data');
    }
}

function updateStatistics(stats) {
    const statsDiv = document.getElementById('cluster-stats');

    document.getElementById('stat-total-emails').textContent = stats.total_emails;
    document.getElementById('stat-num-clusters').textContent = stats.num_clusters;
    document.getElementById('stat-noise-points').textContent = stats.noise_points;
    document.getElementById('stat-avg-size').textContent = stats.avg_cluster_size;

    statsDiv.style.display = 'block';
}

function updateClusterList(clusters) {
    const listDiv = document.getElementById('cluster-list');
    const itemsDiv = document.getElementById('cluster-list-items');

    itemsDiv.innerHTML = '';

    // Sort clusters by label (excluding noise)
    const sortedClusters = clusters
        .filter(c => c.cluster_label >= 0)
        .sort((a, b) => a.cluster_label - b.cluster_label);

    sortedClusters.forEach(cluster => {
        const item = document.createElement('div');
        item.style.cssText = 'padding: 8px; margin-bottom: 4px; background: white; border-radius: 4px; cursor: pointer; border-left: 4px solid ' + cluster.color;
        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>${cluster.short_label || `Cluster ${cluster.cluster_label}`}</strong>
                    <div style="font-size: 12px; color: #64748b; margin-top: 2px;">${cluster.description || ''}</div>
                </div>
                <div style="background: ${cluster.color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600;">
                    ${cluster.num_emails}
                </div>
            </div>
        `;

        // Click to highlight cluster in visualization
        item.addEventListener('click', () => {
            highlightCluster(cluster.cluster_label);
        });

        itemsDiv.appendChild(item);
    });

    // Add noise cluster if present
    const noiseCluster = clusters.find(c => c.cluster_label === -1);
    if (noiseCluster && noiseCluster.num_emails > 0) {
        const item = document.createElement('div');
        item.style.cssText = 'padding: 8px; background: #f1f5f9; border-radius: 4px; border-left: 4px solid #94a3b8';
        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>Noise / Unclustered</strong>
                    <div style="font-size: 12px; color: #64748b; margin-top: 2px;">Emails that don't fit into any cluster</div>
                </div>
                <div style="background: #94a3b8; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600;">
                    ${noiseCluster.num_emails}
                </div>
            </div>
        `;
        itemsDiv.appendChild(item);
    }

    listDiv.style.display = 'block';
}

function render3DPlot(data) {
    const vizDiv = document.getElementById('cluster-visualization');
    const placeholderDiv = document.getElementById('cluster-viz-placeholder');

    // Group points by cluster
    const clusterMap = {};
    data.clusters.forEach(cluster => {
        clusterMap[cluster.cluster_label] = cluster;
    });

    // Create traces for each cluster
    const traces = [];

    data.clusters.forEach(cluster => {
        const clusterPoints = data.points.filter(p => p.cluster_label === cluster.cluster_label);

        if (clusterPoints.length === 0) return;

        const trace = {
            x: clusterPoints.map(p => p.x),
            y: clusterPoints.map(p => p.y),
            z: clusterPoints.map(p => p.z),
            mode: 'markers',
            type: 'scatter3d',
            name: cluster.short_label || `Cluster ${cluster.cluster_label}`,
            text: clusterPoints.map(p => p.subject),
            customdata: clusterPoints.map(p => ({
                email_id: p.email_id,
                subject: p.subject,
                sender: p.sender
            })),
            hovertemplate: '<b>%{text}</b><br>From: %{customdata.sender}<extra></extra>',
            marker: {
                size: 5,
                color: cluster.color || '#3b82f6',
                opacity: 0.8,
                line: {
                    color: '#ffffff',
                    width: 0.5
                }
            }
        };

        traces.push(trace);
    });

    // Layout configuration
    const layout = {
        title: {
            text: `Email Clusters - ${data.persona_name}`,
            font: { size: 18 }
        },
        scene: {
            xaxis: { title: 't-SNE Dimension 1', showgrid: true },
            yaxis: { title: 't-SNE Dimension 2', showgrid: true },
            zaxis: { title: 't-SNE Dimension 3', showgrid: true },
            camera: {
                eye: { x: 1.5, y: 1.5, z: 1.5 }
            }
        },
        showlegend: true,
        legend: {
            x: 1.02,
            y: 1,
            xanchor: 'left',
            yanchor: 'top'
        },
        margin: { l: 0, r: 0, b: 0, t: 40 },
        hovermode: 'closest',
        paper_bgcolor: '#ffffff',
        plot_bgcolor: '#ffffff'
    };

    // Configuration
    const config = {
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['toImage'],
        modeBarButtonsToAdd: [{
            name: 'Reset Camera',
            icon: Plotly.Icons.home,
            click: function(gd) {
                Plotly.relayout(gd, {
                    'scene.camera': {
                        eye: { x: 1.5, y: 1.5, z: 1.5 }
                    }
                });
            }
        }]
    };

    // Render plot
    Plotly.newPlot(vizDiv, traces, layout, config);

    // Add click handler for points
    vizDiv.on('plotly_click', async function(eventData) {
        if (eventData.points && eventData.points.length > 0) {
            const point = eventData.points[0];
            const emailId = point.customdata.email_id;

            console.log(`[Clustering] Clicked email ${emailId}`);
            await showEmailDetails(emailId);
        }
    });

    // Show visualization, hide placeholder
    vizDiv.style.display = 'block';
    placeholderDiv.style.display = 'none';

    console.log('[Clustering] 3D plot rendered with', traces.length, 'clusters');
}

function highlightCluster(clusterLabel) {
    console.log(`[Clustering] Highlighting cluster ${clusterLabel}`);

    // TODO: Implement cluster highlighting
    // Could temporarily increase opacity/size of selected cluster points
    // and reduce opacity of other clusters
}

async function showEmailDetails(emailId) {
    if (!currentPersonaId) return;

    try {
        const response = await fetch(`${CLUSTERING_API_BASE}/clustering/${currentPersonaId}/email/${emailId}`);

        if (!response.ok) {
            throw new Error(`Failed to load email: ${response.statusText}`);
        }

        const email = await response.json();

        // Show email in modal (reuse existing email modal if available)
        displayEmailModal(email);

    } catch (error) {
        console.error('[Clustering] Error loading email details:', error);
        showError('Failed to load email details');
    }
}

function displayEmailModal(email) {
    // Try to use existing email modal
    const modal = document.getElementById('email-modal');
    const subjectEl = document.getElementById('email-modal-subject');
    const bodyEl = document.getElementById('email-modal-body');
    const closeBtn = document.getElementById('email-modal-close');

    if (modal && subjectEl && bodyEl) {
        subjectEl.textContent = email.subject;

        bodyEl.innerHTML = `
            <div style="margin-bottom: 12px;">
                <strong>From:</strong> ${email.sender}<br>
                <strong>To:</strong> ${email.recipients_to.join(', ')}<br>
                ${email.recipients_cc.length > 0 ? `<strong>CC:</strong> ${email.recipients_cc.join(', ')}<br>` : ''}
                <strong>Sent:</strong> ${new Date(email.sent_at).toLocaleString()}<br>
                ${email.cluster_name ? `<strong>Cluster:</strong> ${email.cluster_name}<br>` : ''}
            </div>
            <div style="white-space: pre-wrap; background: #f8fafc; padding: 12px; border-radius: 4px;">
                ${email.body}
            </div>
        `;

        modal.style.display = 'block';

        // Set up close handler
        if (closeBtn) {
            closeBtn.onclick = () => {
                modal.style.display = 'none';
            };
        }

        // Close on backdrop click
        modal.onclick = (e) => {
            if (e.target === modal || e.target.classList.contains('modal-backdrop')) {
                modal.style.display = 'none';
            }
        };
    } else {
        // Fallback: simple alert
        alert(`Subject: ${email.subject}\n\nFrom: ${email.sender}\n\n${email.body}`);
    }
}

// ============================================================================
// Error Handling
// ============================================================================

function showError(message) {
    console.error('[Clustering] Error:', message);

    // Show error in status details
    const statusDetails = document.getElementById('cluster-status-details');
    if (statusDetails) {
        statusDetails.innerHTML = `<span style="color: #b91c1c;">Error: ${message}</span>`;
    }
}

// ============================================================================
// Export and Initialize
// ============================================================================

// Make initClustering globally available for dashboard.js
window.initClustering = initClustering;

// Initialize on DOM ready (handles both initial load and tab switching)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('[Clustering] DOM ready, will initialize when tab is activated');
    });
} else {
    console.log('[Clustering] Module loaded, ready for initialization');
}

export default { initClustering };
