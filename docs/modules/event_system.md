# EventSystem Module Documentation

## Overview

The EventSystem module (`src/virtualoffice/sim_manager/core/event_system.py`) manages all simulation events including injection, processing, random generation, and conversion to worker planning adjustments. It was extracted from the SimulationEngine as part of the Phase 1 engine refactoring project.

## Architecture

### Module Location
```
src/virtualoffice/sim_manager/core/
├── event_system.py          # EventSystem class and InboundMessage dataclass
├── simulation_state.py      # State management
└── tick_manager.py          # Time progression
```

### Dependencies
- `virtualoffice.common.db` - Database connection management
- `virtualoffice.common.localization` - Localized event messages
- `virtualoffice.sim_manager.schemas` - EventCreate and PersonRead models

## Core Classes

### EventSystem

Main class responsible for event lifecycle management.

```python
class EventSystem:
    """
    Manages simulation events including injection, processing, and random generation.
    
    Responsibilities:
    - Event storage and retrieval from database
    - Random event generation (sick leave, client requests, blockers)
    - Event-to-adjustment conversion for worker planning
    - Project-specific event filtering
    """
    
    def __init__(self, random_seed: int | None = None):
        """
        Initialize the EventSystem.
        
        Args:
            random_seed: Optional seed for deterministic random event generation
        """
```

#### Key Methods

##### inject_event()
Store a custom event in the database.

```python
def inject_event(self, event: EventCreate) -> dict:
    """
    Inject a custom event into the simulation.
    
    Args:
        event: Event details including type, targets, timing, and payload
        
    Returns:
        Dictionary representation of the stored event
    """
```

**Example Usage**:
```python
from virtualoffice.sim_manager.schemas import EventCreate

event = EventCreate(
    type="client_change",
    target_ids=[1, 2],
    at_tick=720,
    payload={"change": "Add authentication", "priority": "high"}
)

event_system = EventSystem()
stored_event = event_system.inject_event(event)
```

##### list_events()
Query events with optional filtering.

```python
def list_events(
    self, 
    project_id: str | None = None, 
    target_id: int | None = None
) -> list[dict]:
    """
    List all events, optionally filtered by project or target.
    
    Args:
        project_id: Optional project ID to filter events
        target_id: Optional person ID to filter events
        
    Returns:
        List of event dictionaries
    """
```

**Example Usage**:
```python
# Get all events
all_events = event_system.list_events()

# Get events for specific project
project_events = event_system.list_events(project_id="dashboard-mvp")

# Get events targeting specific person
person_events = event_system.list_events(target_id=1)
```

##### process_events_for_tick()
Generate and process events for the current simulation tick.

```python
def process_events_for_tick(
    self,
    tick: int,
    people: Sequence[PersonRead],
    hours_per_day: int,
    status_overrides: dict[int, tuple[str, int]],
    email_gateway: Any,
    chat_gateway: Any,
    sim_manager_email: str,
    queue_message_callback: Any,
    log_exchange_callback: Any,
    set_status_override_callback: Any,
) -> tuple[dict[int, list[str]], dict[int, list[InboundMessage]]]:
    """
    Process and generate events for the current tick.
    
    Returns:
        Tuple of (adjustments dict, immediate messages dict)
        - adjustments: Dict mapping person_id to list of adjustment strings
        - immediate: Dict mapping person_id to list of InboundMessage objects
    """
```

**Return Values**:
- **adjustments**: Planning guidance strings for affected workers
- **immediate**: Messages queued for worker inboxes

##### convert_event_to_adjustments()
Convert an event into planning adjustment strings.

```python
def convert_event_to_adjustments(
    self, 
    event: dict, 
    person: PersonRead
) -> list[str]:
    """
    Convert an event into adjustment strings for a specific person.
    
    Args:
        event: Event dictionary with type, payload, etc.
        person: Person affected by the event
        
    Returns:
        List of adjustment strings to guide planning
    """
```

**Example Usage**:
```python
event = {
    "type": "client_feature_request",
    "payload": {"feature": "Add dark mode"}
}

adjustments = event_system.convert_event_to_adjustments(event, person)
# Returns: ["Plan response to client request: Add dark mode."]
```

### InboundMessage

Dataclass representing messages queued for worker inboxes.

```python
@dataclass
class InboundMessage:
    """Message queued for a worker's inbox."""
    sender_id: int
    sender_name: str
    subject: str
    summary: str
    action_item: str | None
    message_type: str
    channel: str
    tick: int
    message_id: int | None = None
```

**Fields**:
- `sender_id`: ID of message sender (0 for system messages)
- `sender_name`: Display name of sender
- `subject`: Message subject line
- `summary`: Brief message summary
- `action_item`: Suggested action for recipient
- `message_type`: Type of message ('event', 'communication', etc.)
- `channel`: Communication channel ('email', 'chat', 'system')
- `tick`: Tick when message was generated
- `message_id`: Optional message ID for threading

## Random Event Generation

### Event Types

#### Sick Leave
**Trigger**: Once per day around mid-morning (tick ~60 of day)
**Probability**: 5% daily chance across team
**Duration**: Until end of current day

**Behavior**:
1. Selects random active worker (not already on sick leave)
2. Sets status override to 'SickLeave'
3. Sends system message to affected worker
4. Notifies department head for coverage coordination
5. Records event in database

**Localization**:
- Uses `rest_and_recover`, `rest_and_recover_body`, `rest_and_recover_action` keys
- Department head notification uses `coverage_needed` template

#### Client Feature Request
**Trigger**: Every ~2 hours (120 minutes)
**Probability**: 10% per trigger interval
**Target**: Department head (or first person if no head)

**Behavior**:
1. Selects random feature from localized feature list
2. Sends request to department head
3. Assigns random collaborator for partnership
4. Generates coordination messages
5. Records event with feature details

**Feature Examples** (English/Korean):
- `update main page banner` / `메인 페이지 배너 업데이트`
- `prepare analytics dashboard` / `분석 대시보드 준비`
- `add customer review section` / `고객 리뷰 섹션 추가`
- `improve user onboarding flow` / `사용자 온보딩 플로우 개선`
- `optimize mobile performance` / `모바일 성능 최적화`
- `add search functionality` / `검색 기능 추가`

**Localization**:
- Feature list defined inline with universally understandable requests
- Templates: `client_request_subject`, `client_request_body`, `client_request_action`
- Collaboration messages: `partner_with`, `support_on`
- Locale-aware feature selection (Korean for `ko` locale, English otherwise)

#### Extensible Event Types
The system supports additional event types through the `convert_event_to_adjustments()` method:

- **Blocker**: Dependency issues requiring coordination
- **Meeting**: Scheduled gatherings affecting availability
- **Custom**: Any event type with appropriate payload

### Deterministic Randomness

The EventSystem uses a seeded random number generator for reproducible simulations:

```python
# Create EventSystem with seed for reproducibility
event_system = EventSystem(random_seed=42)

# Same seed produces same event sequence
event_system1 = EventSystem(random_seed=42)
event_system2 = EventSystem(random_seed=42)
# Both will generate identical events
```

## Integration with SimulationEngine

### Initialization

```python
class SimulationEngine:
    def __init__(self, ...):
        # Initialize event system with optional seed
        self.event_system = EventSystem(random_seed=None)
```

### Tick Processing

During each tick advancement, the engine calls `process_events_for_tick()`:

```python
def advance(self, ticks: int, reason: str):
    for _ in range(ticks):
        # Process events for current tick
        adjustments, immediate = self.event_system.process_events_for_tick(
            tick=self.state.current_tick,
            people=active_people,
            hours_per_day=self.hours_per_day,
            status_overrides=self._status_overrides,
            email_gateway=self.email_gateway,
            chat_gateway=self.chat_gateway,
            sim_manager_email=self.sim_manager_email,
            queue_message_callback=self._queue_message,
            log_exchange_callback=self._log_exchange,
            set_status_override_callback=self._set_status_override,
        )
        
        # Apply adjustments to worker planning
        for person_id, adjustment_list in adjustments.items():
            # Use adjustments in planning context
            pass
```

### Report Generation

When generating simulation reports, the engine uses `list_events()` to retrieve event summaries:

```python
def _generate_simulation_report(self, project_plan: dict, total_ticks: int):
    # Get events from EventSystem instead of direct database query
    event_dicts = self.event_system.list_events()
    
    # Summarize events concisely
    event_summary = f"Total events: {len(event_dicts)}\n"
    event_summary += "\n".join(
        f"- {evt['type']} (project={evt['project_id']}, tick={evt['at_tick']})"
        for evt in event_dicts[:20]  # Limit to first 20
    ) if event_dicts else "No events logged."
    
    # Pass event summary to planner for report generation
    result = self._call_planner(
        'generate_simulation_report',
        event_summary=event_summary,
        # ... other parameters
    )
```

### Event Injection API

The engine exposes event injection through its API:

```python
def inject_event(self, event: EventCreate) -> dict:
    """Delegate to EventSystem."""
    return self.event_system.inject_event(event)

def list_events(self, project_id: str | None = None, target_id: int | None = None) -> list[dict]:
    """Delegate to EventSystem."""
    return self.event_system.list_events(project_id=project_id, target_id=target_id)
```

**Usage in Engine Methods:**
- `inject_event()`: API endpoint for custom event injection
- `list_events()`: API endpoint for event retrieval with filtering
- `_generate_simulation_report()`: Retrieves all events for report generation
- `advance()`: Processes events during tick advancement via `process_events_for_tick()`

## Database Schema

### events Table

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    target_ids TEXT NOT NULL,  -- JSON array of person IDs
    project_id TEXT,
    at_tick INTEGER NOT NULL,
    payload TEXT,              -- JSON object
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Columns**:
- `id`: Unique event identifier
- `type`: Event type (sick_leave, client_feature_request, blocker, meeting, etc.)
- `target_ids`: JSON array of affected person IDs
- `project_id`: Optional project scope
- `at_tick`: Tick when event should trigger
- `payload`: JSON object with event-specific data
- `created_at`: Timestamp of event creation

## Localization Support

The EventSystem integrates with the localization system for multi-language support:

```python
from virtualoffice.common.localization import get_current_locale_manager

loc_manager = get_current_locale_manager()

# Get localized text
subject = loc_manager.get_text("rest_and_recover")

# Get localized template with variables
message = loc_manager.get_template("coverage_needed", name=worker.name)

# Get localized list
features = loc_manager.get_list("client_feature_requests")
```

### Supported Locales
- **English (en)**: Default locale
- **Korean (ko)**: Full Korean workplace simulation support

### Localization Keys Used

**Sick Leave Events**:
- `rest_and_recover` - Subject for sick worker
- `rest_and_recover_body` - Message body for sick worker
- `rest_and_recover_action` - Action item for sick worker
- `coverage_needed` - Subject for department head
- `coverage_needed_body` - Message body for department head

**Client Feature Requests**:
- `client_feature_requests` - List of feature descriptions
- `client_request_subject` - Request subject template
- `client_request_body` - Request body template
- `client_request_action` - Action item template
- `partner_with` - Collaboration message template
- `support_on` - Support request template

## Testing

### Unit Tests

Location: `tests/core/test_event_system.py`

**Test Coverage**:
- Event injection and storage
- Event retrieval with filtering
- Random event generation (sick leave, client requests)
- Event-to-adjustment conversion
- Deterministic randomness with seeds
- Localization integration

**Example Test**:
```python
def test_inject_event():
    event_system = EventSystem()
    
    event = EventCreate(
        type="client_change",
        target_ids=[1, 2],
        at_tick=100,
        payload={"change": "New feature"}
    )
    
    result = event_system.inject_event(event)
    
    assert result["type"] == "client_change"
    assert result["target_ids"] == [1, 2]
    assert result["at_tick"] == 100
```

### Integration Tests

Location: `tests/test_sim_manager.py`

**Test Scenarios**:
- Event injection through API endpoints
- Event processing during simulation
- Worker response to events
- Multi-project event filtering

## Performance Considerations

### Random Event Generation
- Events checked once per tick (O(1) per event type)
- Probability-based triggering minimizes overhead
- No event generation when no people active

### Database Operations
- Batch event retrieval with filtering
- JSON extraction for target_id filtering
- Indexed queries on common fields

### Memory Usage
- Events stored in database, not memory
- InboundMessage objects created only when needed
- Adjustments generated on-demand

## Extension Guidelines

### Adding New Event Types

1. **Define Event Type**:
```python
# In convert_event_to_adjustments()
elif event_type == 'new_event_type':
    description = payload.get('description', 'default')
    adjustments.append(f'Handle new event: {description}.')
```

2. **Add Random Generation** (optional):
```python
# In process_events_for_tick()
if some_condition:
    # Generate new event type
    self._record_event('new_event_type', [target.id], tick, payload)
```

3. **Add Localization Keys**:
```python
# In localization.py
LOCALIZATION_STRINGS = {
    "en": {
        "new_event_subject": "New Event",
        "new_event_body": "Event description",
    },
    "ko": {
        "new_event_subject": "새 이벤트",
        "new_event_body": "이벤트 설명",
    }
}
```

4. **Add Tests**:
```python
def test_new_event_type():
    event_system = EventSystem()
    event = {"type": "new_event_type", "payload": {"description": "test"}}
    adjustments = event_system.convert_event_to_adjustments(event, person)
    assert "Handle new event: test." in adjustments
```

### Customizing Event Probabilities

Modify probability values in `process_events_for_tick()`:

```python
# Sick leave: change from 5% to 10%
if rng.random() < 0.10:  # Was 0.05
    # Trigger sick leave
    
# Client requests: change from 10% to 20%
if rng.random() < 0.20:  # Was 0.10
    # Trigger client request
```

### Adding Event Callbacks

The EventSystem uses callbacks to interact with the engine:

```python
# Custom callback for new event type
def handle_custom_event(person_id: int, event_data: dict):
    # Custom event handling logic
    pass

# Pass callback to process_events_for_tick()
adjustments, immediate = event_system.process_events_for_tick(
    ...,
    custom_callback=handle_custom_event
)
```

## Best Practices

### Event Design
- Keep event payloads simple and JSON-serializable
- Use descriptive event type names
- Include all necessary context in payload
- Document expected payload structure

### Random Event Generation
- Use appropriate probabilities for realism
- Consider time-of-day for event timing
- Respect worker status (don't target sick workers)
- Coordinate with team structure (notify heads)

### Localization
- Always use localization keys for user-facing text
- Provide both English and Korean translations
- Use templates for variable substitution
- Test with both locales

### Testing
- Test with deterministic seeds for reproducibility
- Verify event storage and retrieval
- Test edge cases (no workers, all sick, etc.)
- Validate localization for all event types

## Future Enhancements

### Planned Features
1. **Event Scheduling**: Schedule events at specific simulation times
2. **Event Chains**: Events that trigger follow-up events
3. **Event Priorities**: High-priority events interrupt planning
4. **Event Analytics**: Track event frequency and impact
5. **Custom Event Handlers**: Plugin system for custom event types

### Integration Roadmap
1. **Phase 1**: EventSystem extraction ✅ Complete
2. **Phase 2**: Enhanced event types and probabilities
3. **Phase 3**: Event analytics and reporting
4. **Phase 4**: Custom event plugin system

## Conclusion

The EventSystem module provides a clean, testable, and extensible foundation for managing simulation events. By extracting this functionality from the SimulationEngine, we've improved code organization, testability, and maintainability while preserving all existing functionality.

The module's design supports both random event generation for realistic simulations and custom event injection for scenario testing, making it a versatile tool for various simulation needs.
