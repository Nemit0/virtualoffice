// Project Management Module
// Handles project CRUD operations, team selection, and import/export

import { API_PREFIX, fetchJson } from '../core/api.js';
import { setStatus } from '../utils/ui.js';
import {
  getProjects,
  setProjects,
  addProject as addProjectToState,
  removeProject as removeProjectFromState,
  clearProjects,
  getPeopleCache
} from '../core/state.js';

/**
 * Add a new project with user prompts for project details
 */
export function addProject() {
  const projectName = prompt("Enter project name:");
  if (!projectName) return;

  const projectSummary = prompt("Enter project summary:");
  if (!projectSummary) return;

  const startWeek = parseInt(prompt("Start week (1-52):", "1"));
  if (!startWeek || startWeek < 1) {
    setStatus("Invalid start week", true);
    return;
  }

  const durationWeeks = parseInt(prompt("Duration in weeks (1-52):", "1"));
  if (!durationWeeks || durationWeeks < 1) {
    setStatus("Invalid duration", true);
    return;
  }

  // Show team selection dialog
  showTeamSelectionDialog(projectName, projectSummary, startWeek, durationWeeks);
}

/**
 * Show team selection dialog and create project with selected teams
 */
export function showTeamSelectionDialog(projectName, projectSummary, startWeek, durationWeeks) {
  // Create a dialog for team selection
  const teamIds = [];
  const teams = getUniqueTeams();

  if (teams.length === 0) {
    setStatus("No teams available. Please create personas with team assignments first.", true);
    return;
  }

  let message = `Select teams for "${projectName}":\n\n`;
  teams.forEach((team, idx) => {
    message += `${idx + 1}. ${team.name} (${team.members.length} members)\n`;
  });
  message += `\nEnter team numbers separated by commas (e.g., "1,2"):`;

  const selection = prompt(message);
  if (!selection) return;

  const indices = selection.split(',').map(s => parseInt(s.trim()) - 1);
  indices.forEach(idx => {
    if (idx >= 0 && idx < teams.length) {
      teamIds.push(...teams[idx].memberIds);
    }
  });

  if (teamIds.length === 0) {
    setStatus("No valid teams selected", true);
    return;
  }

  const project = {
    name: projectName,
    summary: projectSummary,
    team_ids: teamIds,
    start_week: startWeek,
    duration_weeks: durationWeeks
  };

  addProjectToState(project);
  renderProjects();
  setStatus(`Added project: ${projectName}`);
}

/**
 * Get unique teams from people cache
 */
export function getUniqueTeams() {
  const teamsMap = new Map();

  const peopleCache = getPeopleCache();
  peopleCache.forEach(person => {
    const teamName = person.team_name || "No Team";
    if (!teamsMap.has(teamName)) {
      teamsMap.set(teamName, {
        name: teamName,
        members: [],
        memberIds: []
      });
    }
    teamsMap.get(teamName).members.push(person.name);
    teamsMap.get(teamName).memberIds.push(person.id);
  });

  return Array.from(teamsMap.values());
}

/**
 * Remove project at specified index
 */
export function removeProject(index) {
  const projects = getProjects();
  if (confirm(`Remove project "${projects[index].name}"?`)) {
    removeProjectFromState(index);
    renderProjects();
    setStatus("Project removed");
  }
}

/**
 * Render all projects in the UI
 */
export function renderProjects() {
  const container = document.getElementById('projects-list');
  container.innerHTML = '';

  const projects = getProjects();
  const peopleCache = getPeopleCache();
  
  projects.forEach((project, index) => {
    const card = document.createElement('div');
    card.className = 'project-card';

    const title = document.createElement('h4');
    title.textContent = project.name;
    card.appendChild(title);

    const summary = document.createElement('div');
    summary.className = 'project-info';
    summary.textContent = project.summary;
    card.appendChild(summary);

    const timeline = document.createElement('div');
    timeline.className = 'project-info';
    timeline.textContent = `📅 Week ${project.start_week} - ${project.start_week + project.duration_weeks - 1} (${project.duration_weeks} weeks)`;
    card.appendChild(timeline);

    const teamInfo = document.createElement('div');
    teamInfo.className = 'project-teams';
    const teamMembers = peopleCache.filter(p => project.team_ids.includes(p.id)).map(p => p.name);
    teamInfo.textContent = `👥 Team: ${teamMembers.join(', ')}`;
    card.appendChild(teamInfo);

    const removeBtn = document.createElement('button');
    removeBtn.textContent = 'Remove';
    removeBtn.className = 'remove-project-btn';
    removeBtn.onclick = () => removeProject(index);
    card.appendChild(removeBtn);

    container.appendChild(card);
  });
}

/**
 * Hydrate frontend projects from backend DB if empty.
 * Uses /projects endpoint that returns all project_plans with assigned person IDs.
 */
export async function hydrateProjectsFromDBIfNeeded() {
  try {
    const existing = getProjects();
    if (existing && existing.length > 0) {
      return; // Already have projects in memory/localStorage
    }

    // Fetch from backend
    const items = await fetchJson(`${API_PREFIX}/projects`);
    if (!Array.isArray(items) || items.length === 0) {
      return; // Nothing to hydrate
    }

    // Transform to frontend state shape
    const projects = items.map(item => {
      const p = item.project || {};
      const assigned = Array.isArray(item.assigned_person_ids) ? item.assigned_person_ids : [];
      return {
        name: p.project_name,
        summary: p.project_summary,
        start_week: p.start_week,
        duration_weeks: p.duration_weeks,
        // If no specific assignments in DB, leave empty (meaning all team members)
        team_ids: assigned
      };
    });

    // Store and render
    setProjects(projects);
    renderProjects();
    setStatus(`Loaded ${projects.length} project(s) from database`);
  } catch (err) {
    // Non-fatal: log and continue
    console.warn('[PROJECTS] Failed to hydrate projects from DB:', err);
  }
}

/**
 * Export projects to JSON file
 */
export async function exportProjects() {
  const exportBtn = document.getElementById('export-projects-btn');

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
    setStatus('Exporting projects...');

    // Export current frontend projects array
    const projects = getProjects();
    const exportData = {
      export_type: 'projects',
      export_timestamp: new Date().toISOString(),
      version: '1.0',
      projects: projects.map(p => ({
        project_name: p.name,
        project_summary: p.summary,
        start_week: p.start_week,
        duration_weeks: p.duration_weeks,
        assigned_person_ids: p.team_ids || []
      }))
    };

    // Create and download JSON file
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vdos-projects-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    setStatus(`Exported ${exportData.projects.length} projects successfully`);
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
 * Import projects from JSON file
 */
export async function importProjects() {
  const importBtn = document.getElementById('import-projects-btn');

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

      setStatus('Validating projects...');
      const result = await fetchJson(`${API_PREFIX}/import/projects`, {
        method: 'POST',
        body: JSON.stringify(data),
      });

      if (result.error_count > 0) {
        setStatus(`Validation errors found: ${result.errors.join(', ')}`, true);
        return;
      }

      // Clear existing projects and load imported ones
      clearProjects();
      result.validated_projects.forEach(p => {
        addProjectToState({
          name: p.project_name,
          summary: p.project_summary,
          start_week: p.start_week,
          duration_weeks: p.duration_weeks,
          team_ids: p.assigned_person_ids || []
        });
      });

      // Re-render projects
      renderProjects();

      setStatus(result.message);
      if (result.errors && result.errors.length > 0) {
        console.warn('Import warnings:', result.errors);
      }

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
