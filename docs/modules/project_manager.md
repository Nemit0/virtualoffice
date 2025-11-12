# ProjectManager Module Documentation

## Overview

The ProjectManager module (`src/virtualoffice/sim_manager/core/project_manager.py`) manages project plans, team assignments, multi-project coordination, and project chat room lifecycle. It was extracted from the SimulationEngine as part of the Phase 1 engine refactoring project.

## Architecture

### Module Location
```
src/virtualoffice/sim_manager/core/
├── project_manager.py       # ProjectManager class
├── simulation_state.py       # State management
├── tick_manager.py          # Time progression
├── event_system.py          # Event management
├── communication_hub.py     # Communication scheduling
└── worker_runtime.py        # Worker runtime state
```

### Dependencies
- `virtualoffice.common.db` - Database connection management
- `virtualoffice.sim_manager.schemas` - PersonRead model
- `virtualoffice.sim_manager.gateways` - ChatGateway for room creation
- `virtualoffice.sim_manager.planner` - PlanResult model

## Core Class

### ProjectManager

Main class responsible for project lifecycle management.

```python
class ProjectManager:
    """
    Manages project plans, assignments, and multi-project coordination.
    
    Responsibilities:
    - Project plan storage and retrieval
    - Active project queries with timeline awareness
    - Project-person assignment management
    - Multi-project scenario support
    - Project chat room lifecycle management
    - Project completion detection
    """
    
    def __init__(self):
        """Initialize the ProjectManager."""
```

## Key Methods

### Project Plan Storage

#### store_project_plan()
Store a new project plan in the database.

```python
def store_project_plan(
    self,
    project_name: str,
    project_summary: str,
    plan_result: PlanResult,
    generated_by: int | None,
    duration_weeks: int,
    start_week: int = 1,
    assigned_person_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    """
    Store a new project plan in the database.
    
    Args:
        project_name: Name of the project
        project_summary: Brief summary of the project
        plan_result: PlanResult containing the plan content and metadata
        generated_by: ID of the person who generated the plan (or None)
        duration_weeks: Duration of the project in weeks
        start_week: Week when the project starts (default: 1)
        assigned_person_ids: Optional list of person IDs assigned to this project
        
    Returns:
        Stored project plan dictionary
    """
```

**Example Usage**:
```python
from virtualoffice.sim_manager.planner import PlanResult

project_manager = ProjectManager()

plan_result = PlanResult(
    content="Detailed project plan...",
    model_used="gpt-4o",
    tokens_used=450
)

project = project_manager.store_project_plan(
    project_name="Dashboard MVP",
    project_summary="Build a metrics dashboard for team productivity",
    plan_result=plan_result,
    generated_by=1,  # Department head's ID
    duration_weeks=4,
    start_week=1,
    assigned_person_ids=[1, 2, 3]  # Team members
)

print(f"Created project {project['id']}: {project['project_name']}")
```

### Project Plan Retrieval

#### get_project_plan()
Get a project plan by ID, or the most recent plan if no ID provided.

```python
def get_project_plan(self, project_id: int | None = None) -> dict[str, Any] | None:
    """
    Get a project plan by ID, or the most recent plan if no ID provided.
    
    Args:
        project_id: Optional project ID. If None, returns most recent plan.
        
    Returns:
        Project plan dictionary or None if not found.
    """
```

**Example Usage**:
```python
# Get most recent project plan
current_project = project_manager.get_project_plan()

# Get specific project by ID
project = project_manager.get_project_plan(project_id=5)

if project:
    print(f"Project: {project['project_name']}")
    print(f"Duration: {project['duration_weeks']} weeks")
    print(f"Starts: Week {project['start_week']}")
```

**Caching Behavior**:
- Most recent project plan is cached for performance
- Cache is automatically updated when storing new projects
- Use `clear_cache()` to manually invalidate cache

### Active Project Queries

#### get_active_projects_for_person()
Get ALL active projects for a person at a given week.

```python
def get_active_projects_for_person(self, person_id: int, week: int) -> list[dict[str, Any]]:
    """
    Get ALL active projects for a person at a given week.
    
    Args:
        person_id: ID of the person
        week: Week number (1-indexed)
        
    Returns:
        List of project plan dictionaries
    """
```

**Example Usage**:
```python
# Get all active projects for person 1 at week 3
active_projects = project_manager.get_active_projects_for_person(
    person_id=1,
    week=3
)

for project in active_projects:
    print(f"Working on: {project['project_name']}")
    end_week = project['start_week'] + project['duration_weeks'] - 1
    print(f"  Timeline: Week {project['start_week']}-{end_week}")
```

**Timeline Logic**:
- Returns projects where: `start_week <= week <= (start_week + duration_weeks - 1)`
- Includes both assigned projects and unassigned projects (everyone works on them)
- Returns empty list if no projects active at specified week

#### get_active_project_for_person()
Get the first active project for a person (backward compatibility).

```python
def get_active_project_for_person(self, person_id: int, week: int) -> dict[str, Any] | None:
    """
    Get the first active project for a person at a given week.
    
    This is a convenience method that returns the first project from
    get_active_projects_for_person(), maintaining backward compatibility.
    
    Args:
        person_id: ID of the person
        week: Week number (1-indexed)
        
    Returns:
        First active project plan dictionary or None if no active projects
    """
```

#### get_active_projects_with_assignments()
Get all projects active at the given week with their team assignments.

```python
def get_active_projects_with_assignments(self, week: int) -> list[dict[str, Any]]:
    """
    Get all projects active at the given week with their team assignments.
    
    Args:
        week: Week number (1-indexed)
        
    Returns:
        List of dictionaries with 'project' and 'team_members' keys
    """
```

**Example Usage**:
```python
# Get all active projects with their teams at week 2
projects_with_teams = project_manager.get_active_projects_with_assignments(week=2)

for item in projects_with_teams:
    project = item['project']
    team = item['team_members']
    
    print(f"\nProject: {project['project_name']}")
    print(f"Team ({len(team)} members):")
    for member in team:
        print(f"  - {member['name']} ({member['role']})")
```

**Team Assignment Logic**:
- If project has specific assignments, returns those team members
- If project has no assignments, returns ALL people (everyone works on it)
- Team members include: id, name, role, team_name

### Project Chat Room Lifecycle

#### create_project_chat_room()
Create a group chat room for a project.

```python
def create_project_chat_room(
    self, 
    project_id: int, 
    project_name: str, 
    team_members: list[PersonRead],
    chat_gateway: ChatGateway
) -> str:
    """
    Create a group chat room for a project and return the room slug.
    
    Args:
        project_id: ID of the project
        project_name: Name of the project
        team_members: List of PersonRead objects for team members
        chat_gateway: ChatGateway instance for creating the room
        
    Returns:
        Room slug for the created chat room
    """
```

**Example Usage**:
```python
from virtualoffice.sim_manager.gateways import ChatGateway

chat_gateway = ChatGateway(base_url="http://127.0.0.1:8001")
project_manager = ProjectManager()

# Get team members
team_members = [
    get_person(1),  # Alice
    get_person(2),  # Bob
    get_person(3),  # Charlie
]

# Create project chat room
room_slug = project_manager.create_project_chat_room(
    project_id=1,
    project_name="Dashboard MVP",
    team_members=team_members,
    chat_gateway=chat_gateway
)

print(f"Created chat room: {room_slug}")
# Output: "Created chat room: project-1-dashboard-mvp"
```

**Room Naming Convention**:
- Room slug: `project-{id}-{name-lowercase-with-dashes}`
- Room name: `{project_name} Team`
- Example: `project-1-dashboard-mvp` → "Dashboard MVP Team"

#### get_active_project_chat_room()
Get the active chat room slug for a project.

```python
def get_active_project_chat_room(self, project_id: int) -> str | None:
    """
    Get the active chat room slug for a project, if any.
    
    Args:
        project_id: ID of the project
        
    Returns:
        Room slug or None if no active room exists
    """
```

**Example Usage**:
```python
# Get active chat room for project
room_slug = project_manager.get_active_project_chat_room(project_id=1)

if room_slug:
    print(f"Project chat room: {room_slug}")
    # Send message to project room
    chat_gateway.send_room_message(
        room_slug=room_slug,
        sender="alice",
        body="Project update: Authentication module complete!"
    )
else:
    print("No active chat room for this project")
```

#### archive_project_chat_room()
Archive the chat room for a completed project.

```python
def archive_project_chat_room(self, project_id: int) -> bool:
    """
    Archive the chat room for a completed project.
    
    Args:
        project_id: ID of the project
        
    Returns:
        True if a room was archived, False otherwise
    """
```

**Example Usage**:
```python
# Archive chat room when project completes
if project_manager.is_project_complete(project_id=1, current_week=5):
    archived = project_manager.archive_project_chat_room(project_id=1)
    if archived:
        print("Project chat room archived")
```

### Project Completion Detection

#### is_project_complete()
Check if a project is complete based on its timeline.

```python
def is_project_complete(self, project_id: int, current_week: int) -> bool:
    """
    Check if a project is complete based on its timeline.
    
    Args:
        project_id: ID of the project
        current_week: Current week number (1-indexed)
        
    Returns:
        True if the project's end week is before the current week
    """
```

**Example Usage**:
```python
# Check if project is complete
current_week = 5
is_done = project_manager.is_project_complete(project_id=1, current_week=current_week)

if is_done:
    print("Project is complete!")
    # Archive chat room
    project_manager.archive_project_chat_room(project_id=1)
else:
    print("Project still in progress")
```

**Completion Logic**:
- Project ends at: `start_week + duration_weeks - 1`
- Complete when: `current_week > end_week`
- Example: Project weeks 1-3 is complete at week 4

### Cache Management

#### clear_cache()
Clear the project plan cache.

```python
def clear_cache(self) -> None:
    """Clear the project plan cache."""
```

**Example Usage**:
```python
# Clear cache after external database modifications
project_manager.clear_cache()

# Next get_project_plan() will fetch from database
project = project_manager.get_project_plan()
```

## Integration with SimulationEngine

### Initialization

```python
class SimulationEngine:
    def __init__(self, ...):
        # Initialize project manager
        self.project_manager = ProjectManager()
```

### Project Plan Creation

```python
def start(self, request: SimulationStartRequest):
    # Generate project plan
    plan_result = self._call_planner(
        'generate_project_plan',
        project_name=request.project_name,
        project_summary=request.project_summary,
        # ...
    )
    
    # Store project plan
    project = self.project_manager.store_project_plan(
        project_name=request.project_name,
        project_summary=request.project_summary,
        plan_result=plan_result,
        generated_by=dept_head.id if dept_head else None,
        duration_weeks=request.duration_weeks,
        start_week=1,
        assigned_person_ids=request.include_person_ids
    )
    
    # Create project chat room
    if active_people:
        room_slug = self.project_manager.create_project_chat_room(
            project_id=project['id'],
            project_name=project['project_name'],
            team_members=active_people,
            chat_gateway=self.chat_gateway
        )
```

### Active Project Queries

```python
def _get_all_active_projects_for_person(self, person_id: int, week: int) -> list[dict]:
    """Delegate to ProjectManager."""
    return self.project_manager.get_active_projects_for_person(person_id, week)

def get_active_project_chat_room(self, project_id: int) -> str | None:
    """Delegate to ProjectManager."""
    return self.project_manager.get_active_project_chat_room(project_id)
```

### Multi-Project Support

```python
# Get all active projects for a person
current_week = self._get_current_week()
active_projects = self.project_manager.get_active_projects_for_person(
    person_id=worker.id,
    week=current_week
)

# Worker can be assigned to multiple projects simultaneously
for project in active_projects:
    print(f"Working on: {project['project_name']}")
```

## Database Schema

### project_plans Table

```sql
CREATE TABLE project_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    project_summary TEXT NOT NULL,
    plan TEXT NOT NULL,
    generated_by INTEGER,
    duration_weeks INTEGER NOT NULL,
    start_week INTEGER DEFAULT 1,
    model_used TEXT,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Columns**:
- `id`: Unique project identifier
- `project_name`: Name of the project
- `project_summary`: Brief project description
- `plan`: Generated project plan content
- `generated_by`: ID of person who generated the plan (FK to people.id)
- `duration_weeks`: Project duration in weeks
- `start_week`: Week when project starts (1-indexed)
- `model_used`: AI model used for plan generation
- `tokens_used`: Token count for plan generation
- `created_at`: Timestamp of project creation

### project_assignments Table

```sql
CREATE TABLE project_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    UNIQUE(project_id, person_id)
);
```

**Columns**:
- `id`: Unique assignment identifier
- `project_id`: FK to project_plans.id
- `person_id`: FK to people.id
- `UNIQUE(project_id, person_id)`: Prevents duplicate assignments

**Assignment Logic**:
- If project has assignments: only assigned people work on it
- If project has NO assignments: everyone works on it

### project_chat_rooms Table

```sql
CREATE TABLE project_chat_rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    room_slug TEXT NOT NULL,
    room_name TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP
);
```

**Columns**:
- `id`: Unique room identifier
- `project_id`: FK to project_plans.id
- `room_slug`: Chat room slug (e.g., "project-1-dashboard-mvp")
- `room_name`: Display name (e.g., "Dashboard MVP Team")
- `is_active`: 1 if active, 0 if archived
- `created_at`: Room creation timestamp
- `archived_at`: Room archival timestamp (NULL if active)

## Multi-Project Scenarios

### Overlapping Projects

```python
# Person assigned to multiple projects with overlapping timelines
project_manager.store_project_plan(
    project_name="Project Alpha",
    project_summary="First project",
    plan_result=plan_result,
    generated_by=1,
    duration_weeks=4,
    start_week=1,
    assigned_person_ids=[1, 2]  # Alice and Bob
)

project_manager.store_project_plan(
    project_name="Project Beta",
    project_summary="Second project",
    plan_result=plan_result,
    generated_by=1,
    duration_weeks=3,
    start_week=2,  # Starts during Alpha
    assigned_person_ids=[1, 3]  # Alice and Charlie
)

# At week 3, Alice works on both projects
alice_projects = project_manager.get_active_projects_for_person(1, week=3)
# Returns: [Project Alpha, Project Beta]
```

### Sequential Projects

```python
# Projects that run one after another
project_manager.store_project_plan(
    project_name="Phase 1",
    project_summary="Initial development",
    plan_result=plan_result,
    generated_by=1,
    duration_weeks=2,
    start_week=1,  # Weeks 1-2
    assigned_person_ids=[1]
)

project_manager.store_project_plan(
    project_name="Phase 2",
    project_summary="Enhancement phase",
    plan_result=plan_result,
    generated_by=1,
    duration_weeks=2,
    start_week=3,  # Weeks 3-4 (after Phase 1)
    assigned_person_ids=[1]
)

# Week 1: Only Phase 1
# Week 3: Only Phase 2
```

### Mixed Assigned and Unassigned Projects

```python
# Specific project for Alice
project_manager.store_project_plan(
    project_name="Alice's Project",
    project_summary="Specific assignment",
    plan_result=plan_result,
    generated_by=1,
    duration_weeks=3,
    start_week=1,
    assigned_person_ids=[1]  # Only Alice
)

# Company-wide project (no assignments = everyone)
project_manager.store_project_plan(
    project_name="Team Project",
    project_summary="Everyone participates",
    plan_result=plan_result,
    generated_by=1,
    duration_weeks=3,
    start_week=1
    # No assigned_person_ids = everyone works on it
)

# Alice sees both projects
alice_projects = project_manager.get_active_projects_for_person(1, week=2)
# Returns: [Alice's Project, Team Project]

# Bob only sees the team project
bob_projects = project_manager.get_active_projects_for_person(2, week=2)
# Returns: [Team Project]
```

## Testing

### Unit Tests

Location: `tests/core/test_project_manager.py`

**Test Coverage**:
- Project plan storage and retrieval
- Active project queries with timeline awareness
- Project-person assignment management
- Multi-project scenarios (overlapping, sequential, mixed)
- Project chat room lifecycle
- Project completion detection
- Cache management
- Edge cases and error conditions

**Example Test**:
```python
def test_get_active_projects_for_person_with_assignment():
    manager = ProjectManager()
    
    # Store project assigned to Alice
    manager.store_project_plan(
        project_name="Alice's Project",
        project_summary="For Alice",
        plan_result=create_test_plan_result(),
        generated_by=1,
        duration_weeks=4,
        start_week=1,
        assigned_person_ids=[1]
    )
    
    # Get active projects for Alice at week 2
    projects = manager.get_active_projects_for_person(1, week=2)
    
    assert len(projects) == 1
    assert projects[0]["project_name"] == "Alice's Project"
```

### Integration Tests

Location: `tests/test_sim_manager.py`

**Test Scenarios**:
- Project creation through simulation start
- Multi-project simulation workflows
- Project chat room integration
- Project completion and archival

## Performance Considerations

### Caching Strategy
- Most recent project plan is cached for performance
- Cache invalidated on new project storage
- Manual cache clearing available via `clear_cache()`

### Database Queries
- Active project queries use indexed lookups
- Timeline filtering done at database level
- Assignment queries use JOIN for efficiency

### Memory Usage
- Minimal memory footprint (cache holds single project)
- Project lists generated on-demand
- No persistent in-memory state beyond cache

## Best Practices

### Project Plan Storage
- Always provide meaningful project names and summaries
- Use appropriate duration_weeks for realistic timelines
- Specify start_week for multi-project coordination
- Assign specific people when needed, omit for company-wide projects

### Active Project Queries
- Use `get_active_projects_for_person()` for multi-project support
- Use `get_active_project_for_person()` for backward compatibility
- Always check for empty results (no active projects)
- Consider timeline boundaries when querying

### Chat Room Management
- Create chat rooms when projects start
- Archive rooms when projects complete
- Use `get_active_project_chat_room()` before sending messages
- Handle None return values gracefully

### Multi-Project Scenarios
- Design timelines carefully to avoid overload
- Use assignments to distribute workload
- Monitor active project counts per person
- Consider project priorities and dependencies

## Future Enhancements

### Planned Features
1. **Project Dependencies**: Track dependencies between projects
2. **Project Priorities**: Priority levels for workload management
3. **Project Milestones**: Track intermediate milestones within projects
4. **Resource Allocation**: Track resource usage across projects
5. **Project Templates**: Reusable project plan templates

### Integration Roadmap
1. **Phase 1**: ProjectManager extraction ✅ Complete
2. **Phase 2**: Enhanced multi-project coordination
3. **Phase 3**: Project analytics and reporting
4. **Phase 4**: Advanced resource management

## Conclusion

The ProjectManager module provides comprehensive project lifecycle management with support for multi-project scenarios, team assignments, and chat room integration. By extracting this functionality from the SimulationEngine, we've improved code organization, testability, and maintainability while enabling advanced multi-project simulation capabilities.

The module's design supports both simple single-project simulations and complex multi-project scenarios with overlapping timelines, making it a versatile foundation for realistic workplace simulation.
