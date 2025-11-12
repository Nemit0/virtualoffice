// Persona Management Module
// Handles persona CRUD operations, AI generation, and style examples

import { API_PREFIX, fetchJson } from '../core/api.js';
import {
  parseCommaSeparated,
  parseLines,
  parseSchedule
} from '../utils/formatting.js';
import {
  setStatus,
  showModal,
  hideModal,
  buildPersonCard,
  buildPlanCard
} from '../utils/ui.js';
import {
  getSelectedPeople,
  setSelectedPeople,
  addSelectedPerson,
  removeSelectedPerson,
  getPeopleCache,
  setPeopleCache
} from '../core/state.js';
import { ensurePersonaSelectsWrapper } from '../dashboard.js';

/**
 * Refresh the people and plans display
 */
export async function refreshPeopleAndPlans() {
  const people = await fetchJson(`${API_PREFIX}/people`);
  setPeopleCache(people); // Cache for project team selection
  ensurePersonaSelectsWrapper(); // Populate email/chat persona dropdowns
  const container = document.getElementById('people-container');
  const plansContainer = document.getElementById('plans-container');
  const currentSelection = new Set(Array.from(container.querySelectorAll('input[type=checkbox]')).filter(cb => cb.checked).map(cb => Number(cb.value)));
  const selectedPeople = getSelectedPeople();
  if (selectedPeople.size === 0 && currentSelection.size > 0) {
    setSelectedPeople(currentSelection);
  }
  container.innerHTML = '';
  plansContainer.innerHTML = '';
  if (!people.length) {
    container.textContent = 'No personas registered.';
    return;
  }
  if (selectedPeople.size === 0) {
    const allIds = people.map(person => Number(person.id));
    setSelectedPeople(allIds);
  }
  people.forEach(person => {
    const checked = getSelectedPeople().has(Number(person.id));
    const card = buildPersonCard(person, checked);
    
    // Add checkbox change event listener
    const checkbox = card.querySelector('input[type=checkbox]');
    if (checkbox) {
      checkbox.addEventListener('change', () => {
        const id = Number(checkbox.value);
        if (checkbox.checked) {
          addSelectedPerson(id);
        } else {
          removeSelectedPerson(id);
        }
      });
    }
    
    container.appendChild(card);
  });
  const entries = await Promise.all(people.map(async person => {
    try {
      const [hourly, daily] = await Promise.all([
        fetchJson(`${API_PREFIX}/people/${person.id}/plans?plan_type=hourly&limit=1`),
        fetchJson(`${API_PREFIX}/people/${person.id}/daily-reports?limit=1`),
      ]);
      return {
        person,
        hourly: hourly && hourly.length ? hourly[0].content : '',
        daily: daily && daily.length ? daily[0].report : '',
      };
    } catch (err) {
      return { person, error: err.message || String(err) };
    }
  }));
  entries.forEach(entry => { plansContainer.appendChild(buildPlanCard(entry)); });
}

/**
 * Load style examples into the form
 */
export function loadStyleExamples(styleExamples) {
  // Parse style_examples if it's a string (JSON)
  let examples = [];
  if (typeof styleExamples === 'string') {
    try {
      examples = JSON.parse(styleExamples);
    } catch (err) {
      console.error('Failed to parse style_examples:', err);
      examples = [];
    }
  } else if (Array.isArray(styleExamples)) {
    examples = styleExamples;
  }

  // Populate the 10 textarea inputs (5 email + 5 chat)
  for (let i = 0; i < 10; i++) {
    const textarea = document.getElementById(`style-example-${i}`);
    if (textarea) {
      if (examples[i] && examples[i].content) {
        textarea.value = examples[i].content;
      } else {
        textarea.value = '';
      }
    }
  }
}

/**
 * Populate the persona form with data
 */
export function populatePersonaForm(persona) {
  console.log('[DEBUG] populatePersonaForm called with:', persona);
  console.log('[DEBUG] Persona type:', typeof persona);
  console.log('[DEBUG] Persona is null?', persona === null);
  console.log('[DEBUG] Persona is undefined?', persona === undefined);

  try {
    console.log('[DEBUG] Setting name field to:', persona.name || '');
    document.getElementById('persona-name').value = persona.name || '';

    console.log('[DEBUG] Setting role field to:', persona.role || '');
    document.getElementById('persona-role').value = persona.role || '';

    console.log('[DEBUG] Setting timezone field');
    document.getElementById('persona-timezone').value = persona.timezone || 'UTC';

    console.log('[DEBUG] Setting work hours field');
    document.getElementById('persona-hours').value = persona.work_hours || '09:00-17:00';

    console.log('[DEBUG] Setting break frequency field');
    document.getElementById('persona-break').value = persona.break_frequency || '50/10 cadence';

    console.log('[DEBUG] Setting communication style field');
    document.getElementById('persona-style').value = persona.communication_style || 'Warm async';

    console.log('[DEBUG] Setting email field');
    document.getElementById('persona-email').value = persona.email_address || '';

    console.log('[DEBUG] Setting chat handle field');
    document.getElementById('persona-chat').value = persona.chat_handle || '';

    console.log('[DEBUG] Setting team name field');
    document.getElementById('persona-team').value = persona.team_name || '';

    console.log('[DEBUG] Setting department head checkbox');
    document.getElementById('persona-is-head').checked = Boolean(persona.is_department_head);

    console.log('[DEBUG] Setting skills field');
    document.getElementById('persona-skills').value = (persona.skills || []).join(', ');

    console.log('[DEBUG] Setting personality field');
    document.getElementById('persona-personality').value = (persona.personality || []).join(', ');

    console.log('[DEBUG] Setting objectives field');
    document.getElementById('persona-objectives').value = (persona.objectives || []).join('\n');

    console.log('[DEBUG] Setting metrics field');
    document.getElementById('persona-metrics').value = (persona.metrics || []).join('\n');

    console.log('[DEBUG] Setting planning guidelines field');
    document.getElementById('persona-guidelines').value = (persona.planning_guidelines || []).join('\n');

    console.log('[DEBUG] Building schedule');
    const schedule = (persona.schedule || []).map(block => `${block.start}-${block.end} ${block.activity || ''}`.trim()).join('\n');
    document.getElementById('persona-schedule').value = schedule;

    console.log('[DEBUG] Setting event playbook');
    document.getElementById('persona-playbook').value = JSON.stringify(persona.event_playbook || {}, null, 2);

    console.log('[DEBUG] Setting statuses field');
    document.getElementById('persona-statuses').value = (persona.statuses || []).join('\n');

    // Load style examples
    console.log('[DEBUG] Loading style examples');
    loadStyleExamples(persona.style_examples);

    console.log('[DEBUG] populatePersonaForm completed successfully');
  } catch (err) {
    console.error('[DEBUG] Error in populatePersonaForm:', err);
    console.error('[DEBUG] Error stack:', err.stack);
    throw err;
  }
}

/**
 * Clear the persona form
 */
export function clearPersonaForm() {
  populatePersonaForm({});
  document.getElementById('persona-is-head').checked = false;
}

/**
 * Collect style examples from the form
 */
export function collectStyleExamples() {
  const examples = [];
  const exampleTypes = ['email', 'email', 'email', 'email', 'email', 'chat', 'chat', 'chat', 'chat', 'chat'];

  for (let i = 0; i < 10; i++) {
    const textarea = document.getElementById(`style-example-${i}`);
    if (textarea) {
      const content = textarea.value.trim();
      if (content) {
        examples.push({
          type: exampleTypes[i],
          content: content
        });
      }
    }
  }

  return examples;
}

/**
 * Collect persona payload from the form
 */
export function collectPersonaPayload() {
  const eventPlaybookText = document.getElementById('persona-playbook').value.trim();
  let eventPlaybook = {};
  if (eventPlaybookText) {
    try {
      eventPlaybook = JSON.parse(eventPlaybookText);
    } catch (err) {
      throw new Error('Invalid event playbook JSON');
    }
  }
  const schedule = parseSchedule(document.getElementById('persona-schedule').value);
  const teamName = document.getElementById('persona-team').value.trim();

  // Collect style examples
  const styleExamples = collectStyleExamples();

  return {
    name: document.getElementById('persona-name').value.trim(),
    role: document.getElementById('persona-role').value.trim(),
    timezone: document.getElementById('persona-timezone').value.trim() || 'UTC',
    work_hours: document.getElementById('persona-hours').value.trim() || '09:00-17:00',
    break_frequency: document.getElementById('persona-break').value.trim() || '50/10 cadence',
    communication_style: document.getElementById('persona-style').value.trim() || 'Async',
    email_address: document.getElementById('persona-email').value.trim(),
    chat_handle: document.getElementById('persona-chat').value.trim(),
    team_name: teamName || null,
    is_department_head: document.getElementById('persona-is-head').checked,
    skills: parseCommaSeparated(document.getElementById('persona-skills').value),
    personality: parseCommaSeparated(document.getElementById('persona-personality').value),
    objectives: parseLines(document.getElementById('persona-objectives').value),
    metrics: parseLines(document.getElementById('persona-metrics').value),
    planning_guidelines: parseLines(document.getElementById('persona-guidelines').value),
    schedule,
    event_playbook: eventPlaybook,
    statuses: parseLines(document.getElementById('persona-statuses').value),
    style_examples: JSON.stringify(styleExamples),
  };
}

/**
 * Create a new persona
 */
export async function createPersona() {
  console.log('[DEBUG] ========== createPersona START ==========');

  let payload;
  try {
    payload = collectPersonaPayload();
    console.log('[DEBUG] Collected payload:', payload);
  } catch (err) {
    console.error('[DEBUG] Error collecting payload:', err);
    setStatus(err.message || String(err), true);
    return;
  }

  // Validate required fields
  console.log('[DEBUG] Validating required fields...');
  console.log('[DEBUG] Name:', payload.name);
  console.log('[DEBUG] Role:', payload.role);
  console.log('[DEBUG] Email:', payload.email_address);
  console.log('[DEBUG] Chat handle:', payload.chat_handle);
  console.log('[DEBUG] Skills:', payload.skills);
  console.log('[DEBUG] Personality:', payload.personality);

  if (!payload.name || !payload.role || !payload.email_address || !payload.chat_handle) {
    const missing = [];
    if (!payload.name) missing.push('name');
    if (!payload.role) missing.push('role');
    if (!payload.email_address) missing.push('email');
    if (!payload.chat_handle) missing.push('chat handle');

    const errorMsg = `Missing required fields: ${missing.join(', ')}`;
    console.error('[DEBUG] Validation failed:', errorMsg);
    setStatus(errorMsg, true);
    return;
  }
  if (!payload.skills.length) {
    console.error('[DEBUG] Validation failed: No skills specified');
    setStatus('Specify at least one skill.', true);
    return;
  }
  if (!payload.personality.length) {
    console.error('[DEBUG] Validation failed: No personality traits specified');
    setStatus('Specify at least one personality trait.', true);
    return;
  }

  console.log('[DEBUG] Validation passed, creating persona...');

  try {
    const created = await fetchJson(`${API_PREFIX}/people`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    console.log('[DEBUG] API response:', created);
    console.log('[DEBUG] Created persona with ID:', created?.id);

    setStatus(`Created persona ${payload.name}`);
    if (created && created.id) {
      addSelectedPerson(Number(created.id));
    }
    clearPersonaForm();
    await refreshPeopleAndPlans();

    console.log('[DEBUG] ========== createPersona SUCCESS ==========');
  } catch (err) {
    console.error('[DEBUG] ========== createPersona ERROR ==========');
    console.error('[DEBUG] Error:', err);
    console.error('[DEBUG] Error message:', err.message);
    setStatus(err.message || String(err), true);
  }
}

/**
 * Generate a persona using AI
 */
export async function generatePersona() {
  console.log('[DEBUG] ========== generatePersona START ==========');
  console.log('[DEBUG] Timestamp:', new Date().toISOString());

  const generateBtn = document.getElementById('persona-generate-btn');
  console.log('[DEBUG] Generate button element:', generateBtn);

  // Prevent multiple clicks
  if (generateBtn.disabled) {
    console.log('[DEBUG] Button already disabled, ignoring click');
    return;
  }

  const prompt = document.getElementById('persona-prompt').value.trim();
  console.log('[DEBUG] Prompt value:', prompt);
  console.log('[DEBUG] Prompt length:', prompt.length);

  if (!prompt) {
    console.log('[DEBUG] No prompt entered');
    setStatus('Enter a prompt before generating.', true);
    return;
  }

  try {
    // Disable button and update text
    generateBtn.disabled = true;
    const originalText = generateBtn.textContent;
    generateBtn.textContent = 'Generating...';
    generateBtn.style.opacity = '0.6';
    console.log('[DEBUG] Button disabled, text changed to "Generating..."');

    setStatus('Generating persona...');
    console.log('[DEBUG] Calling API endpoint:', `${API_PREFIX}/personas/generate`);
    console.log('[DEBUG] Request payload:', { prompt });

    const startTime = performance.now();
    const response = await fetchJson(`${API_PREFIX}/personas/generate`, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    });
    const endTime = performance.now();

    console.log('[DEBUG] API call completed in', (endTime - startTime).toFixed(2), 'ms');
    console.log('[DEBUG] API response:', response);
    console.log('[DEBUG] Response type:', typeof response);
    console.log('[DEBUG] Response has persona?', !!response?.persona);

    if (response && response.persona) {
      console.log('[DEBUG] Persona data:', response.persona);
      console.log('[DEBUG] Persona fields:', Object.keys(response.persona));
      console.log('[DEBUG] Calling populatePersonaForm...');

      populatePersonaForm(response.persona);

      console.log('[DEBUG] Form populated successfully');
      setStatus('Persona drafted. Review the fields and click Create Persona.');

      // Verify form was populated
      const nameValue = document.getElementById('persona-name').value;
      const roleValue = document.getElementById('persona-role').value;
      console.log('[DEBUG] Verification - Name field:', nameValue);
      console.log('[DEBUG] Verification - Role field:', roleValue);
    } else {
      console.error('[DEBUG] No persona in response or response is null');
      console.error('[DEBUG] Full response:', JSON.stringify(response, null, 2));
      setStatus('No persona returned from API', true);
    }
  } catch (err) {
    console.error('[DEBUG] ========== ERROR ==========');
    console.error('[DEBUG] Error type:', err.constructor.name);
    console.error('[DEBUG] Error message:', err.message);
    console.error('[DEBUG] Error stack:', err.stack);
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button
    generateBtn.disabled = false;
    generateBtn.textContent = 'Generate with GPT';
    generateBtn.style.opacity = '1';
    console.log('[DEBUG] Button re-enabled');
    console.log('[DEBUG] ========== generatePersona END ==========');
  }
}

/**
 * Regenerate style examples using AI
 */
export async function regenerateStyleExamples() {
  // Get the persona attributes from the form
  const name = document.getElementById('persona-name').value.trim();
  const role = document.getElementById('persona-role').value.trim();

  if (!name || !role) {
    setStatus('Name and role are required to regenerate style examples.', true);
    return;
  }

  try {
    setStatus('Regenerating style examples with AI...');
    const regenerateBtn = document.getElementById('regenerate-examples-btn');
    regenerateBtn.disabled = true;
    regenerateBtn.textContent = 'Generating...';

    // Build a temporary persona object for generation
    const tempPersona = {
      name: name,
      role: role,
      personality: parseCommaSeparated(document.getElementById('persona-personality').value),
      communication_style: document.getElementById('persona-style').value.trim() || 'Async',
    };

    // Call the style example generator
    const response = await fetchJson(`${API_PREFIX}/personas/generate-style-examples`, {
      method: 'POST',
      body: JSON.stringify(tempPersona),
    });

    if (response && response.style_examples) {
      loadStyleExamples(response.style_examples);
      setStatus('Style examples regenerated successfully');
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    const regenerateBtn = document.getElementById('regenerate-examples-btn');
    regenerateBtn.disabled = false;
    regenerateBtn.textContent = 'Regenerate with AI';
  }
}

/**
 * Open the preview modal for style filter transformation
 */
export function openPreviewModal() {
  showModal('preview-modal');

  // Clear previous results
  document.getElementById('preview-input').value = '';
  document.getElementById('preview-results').style.display = 'none';
  document.getElementById('preview-error').style.display = 'none';
}

/**
 * Close the preview modal
 */
export function closePreviewModal() {
  hideModal('preview-modal');
}

/**
 * Transform a preview message using style examples
 */
export async function transformPreviewMessage() {
  const message = document.getElementById('preview-input').value.trim();
  if (!message) {
    document.getElementById('preview-error').textContent = 'Please enter a sample message';
    document.getElementById('preview-error').style.display = 'block';
    return;
  }

  try {
    // Collect current style examples
    const styleExamples = collectStyleExamples();
    if (styleExamples.length === 0) {
      document.getElementById('preview-error').textContent = 'Please add at least one style example';
      document.getElementById('preview-error').style.display = 'block';
      return;
    }

    const transformBtn = document.getElementById('preview-transform-btn');
    transformBtn.disabled = true;
    transformBtn.textContent = 'Transforming...';

    const response = await fetchJson(`${API_PREFIX}/personas/preview-filter`, {
      method: 'POST',
      body: JSON.stringify({
        message: message,
        style_examples: styleExamples,
        message_type: 'email'
      }),
    });

    if (response) {
      document.getElementById('preview-original').textContent = response.original_message;
      document.getElementById('preview-filtered').textContent = response.filtered_message;
      document.getElementById('preview-results').style.display = 'block';
      document.getElementById('preview-error').style.display = 'none';
    }
  } catch (err) {
    document.getElementById('preview-error').textContent = err.message || String(err);
    document.getElementById('preview-error').style.display = 'block';
    document.getElementById('preview-results').style.display = 'none';
  } finally {
    const transformBtn = document.getElementById('preview-transform-btn');
    transformBtn.disabled = false;
    transformBtn.textContent = 'Transform';
  }
}

/**
 * Export personas to JSON file
 */
export async function exportPersonas() {
  const exportBtn = document.getElementById('export-personas-btn');

  // Prevent multiple clicks by disabling the button
  if (exportBtn.disabled) {
    return;
  }

  // Disable button and update text to show it's processing
  exportBtn.disabled = true;
  const originalText = exportBtn.textContent;
  exportBtn.textContent = 'Exporting...';
  exportBtn.style.opacity = '0.6';

  try {
    setStatus('Exporting personas...');
    const data = await fetchJson(`${API_PREFIX}/export/personas`);

    // Create and download JSON file
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vdos-personas-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    setStatus(`Exported ${data.personas.length} personas successfully`);
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    // Re-enable button and restore original text
    exportBtn.disabled = false;
    exportBtn.textContent = originalText;
    exportBtn.style.opacity = '1';
  }
}

/**
 * Import personas from JSON file
 */
export async function importPersonas() {
  const importBtn = document.getElementById('import-personas-btn');

  // Prevent multiple clicks by disabling the button
  if (importBtn.disabled) {
    return;
  }

  // Create file input
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.json';
  fileInput.style.display = 'none';

  fileInput.addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Disable button and update text to show it's processing
    importBtn.disabled = true;
    const originalText = importBtn.textContent;
    importBtn.textContent = 'Importing...';
    importBtn.style.opacity = '0.6';

    try {
      setStatus('Reading file...');
      const text = await file.text();
      const data = JSON.parse(text);

      setStatus('Importing personas...');
      const result = await fetchJson(`${API_PREFIX}/import/personas`, {
        method: 'POST',
        body: JSON.stringify(data),
      });

      setStatus(result.message);
      if (result.errors && result.errors.length > 0) {
        console.warn('Import warnings:', result.errors);
      }

      // Refresh the personas list
      await refreshPeopleAndPlans();

    } catch (err) {
      if (err instanceof SyntaxError) {
        setStatus('Invalid JSON file format', true);
      } else {
        setStatus(err.message || String(err), true);
      }
    } finally {
      // Re-enable button and restore original text
      importBtn.disabled = false;
      importBtn.textContent = originalText;
      importBtn.style.opacity = '1';

      // Clean up file input
      document.body.removeChild(fileInput);
    }
  });

  document.body.appendChild(fileInput);
  fileInput.click();
}
