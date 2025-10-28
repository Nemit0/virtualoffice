# CommunicationHub Module Documentation

## Overview

The CommunicationHub module (`src/virtualoffice/sim_manager/core/communication_hub.py`) manages all communication scheduling, parsing, and dispatch for the simulation engine. It was extracted from the SimulationEngine as part of the Phase 2 engine refactoring project (Task 2.1 completed).

## Architecture

### Module Location
```
src/virtualoffice/sim_manager/core/
├── communication_hub.py     # CommunicationHub class
├── event_system.py          # Event management
├── simulation_state.py      # State management
└── tick_manager.py          # Time progression
```

### Dependencies
- `virtualoffice.sim_manager.gateways` - EmailGateway and ChatGateway for message delivery
- `virtualoffice.sim_manager.schemas` - PersonRead model
- `virtualoffice.sim_manager.core.tick_manager` - TickManager for time calculations
- `virtualoffice.common.localization` - Localized message templates

## Core Class

### CommunicationHub

Main class responsible for communication lifecycle management.

```python
class CommunicationHub:
    """
    Centralized communication management for the simulation.
    
    Handles:
    - Parsing communication schedules from hourly plans
    - Scheduling emails and chats for future ticks
    - Dispatching scheduled communications at the right time
    - Message deduplication and cooldown enforcement
    - Email threading support
    - Group chat vs DM routing
    """
    
    def __init__(
        self,
        email_gateway: EmailGateway,
        chat_gateway: ChatGateway,
        tick_manager: TickManager,
        cooldown_ticks: int = 10,
    ) -> None:
        """
        Initialize the CommunicationHub.
        
        Args:
            email_gateway: Gateway for sending emails
            chat_gateway: Gateway for sending chat messages
            tick_manager: Manager for time-related operations
            cooldown_ticks: Minimum ticks between messages to same recipient
        """
```

## Key Methods

### Message Deduplication and Cooldown

#### reset_tick_sends()
Clear deduplication tracking for a new tick.

```python
def reset_tick_sends(self) -> None:
    """Clear deduplication tracking for a new tick."""
```

**Usage**:
```python
# Called at the start of each tick
communication_hub.reset_tick_sends()
```

#### can_send()
Check if a message can be sent based on deduplication and cooldown rules.

```python
def can_send(
    self,
    *,
    tick: int,
    channel: str,
    sender: str,
    recipient_key: tuple,
    subject: str | None,
    body: str
) -> bool:
    """
    Check if a message can be sent based on deduplication and cooldown rules.
    
    Args:
        tick: Current simulation tick
        channel: Communication channel ('email' or 'chat')
        sender: Sender identifier (email or chat handle)
        recipient_key: Tuple of recipient identifiers
        subject: Email subject (None for chat)
        body: Message body
        
    Returns:
        True if message can be sent, False if blocked by dedup/cooldown
    """
```

**Deduplication Rules**:
- Same tick, channel, sender, recipients, subject, and body → blocked
- Prevents duplicate messages within the same tick

**Cooldown Rules**:
- Default: 10 ticks between messages to same recipient
- Configurable via `VDOS_CONTACT_COOLDOWN_TICKS` environment variable
- Prevents message spam and maintains realistic communication patterns

**Example Usage**:
```python
if communication_hub.can_send(
    tick=current_tick,
    channel='email',
    sender='alice@example.com',
    recipient_key=('bob@example.com',),
    subject='Project Update',
    body='Making progress on the dashboard'
):
    # Send the email
    email_gateway.send_email(...)
```

### Hourly Plan Parsing

#### schedule_from_hourly_plan()
Parse hourly plan text and schedule communications for future ticks.

```python
def schedule_from_hourly_plan(
    self,
    person: PersonRead,
    plan_text: str,
    current_tick: int,
    hours_per_day: int
) -> None:
    """
    Parse hourly plan text and schedule communications for future ticks.
    
    Supports formats:
    - Email at HH:MM to PERSON: Subject | Body
    - Email at HH:MM to PERSON cc PERSON2: Subject | Body
    - Reply at HH:MM to [email-id]: Subject | Body
    - Chat at HH:MM to/with PERSON: Message
    
    Args:
        person: Person whose plan is being parsed
        plan_text: The hourly plan text to parse
        current_tick: Current simulation tick
        hours_per_day: Ticks per day for time calculations
    """
```

**Supported Formats**:

1. **Simple Email**:
   ```
   Email at 10:30 to bob@example.com: Project Update | Making good progress on the API
   ```

2. **Email with CC**:
   ```
   Email at 14:00 to alice@example.com cc manager@example.com: Status Report | Weekly update
   ```

3. **Email with BCC**:
   ```
   Email at 09:00 to team@example.com bcc manager@example.com: Announcement | New policy
   ```

4. **Reply to Email**:
   ```
   Reply at 11:00 to [email-123]: Re: Question | Here's the answer you requested
   ```

5. **Chat Message (DM)**:
   ```
   Chat at 15:30 to bob: Quick question about the API endpoint
   ```

6. **Chat Message (Group)**:
   ```
   Chat at 16:00 to team: Daily standup summary
   ```

**Parsing Rules**:
- Only schedules communications for future times in the current day
- Past times are ignored
- Duplicate entries are automatically deduplicated
- Invalid formats are silently skipped

**Example Usage**:
```python
plan_text = """
09:00-10:00 Review pull requests
Email at 10:30 to bob@example.com: Code Review | Approved your PR
10:00-12:00 Implement authentication
Chat at 11:30 to alice: Need your input on auth flow
"""

communication_hub.schedule_from_hourly_plan(
    person=worker,
    plan_text=plan_text,
    current_tick=1,
    hours_per_day=8
)
```

### Email Threading

#### get_thread_id_for_reply()
Look up thread_id and original sender from email-id in recent emails.

```python
def get_thread_id_for_reply(
    self, 
    person_id: int, 
    email_id: str
) -> tuple[str | None, str | None]:
    """
    Look up thread_id and original sender from email-id in recent emails.
    
    Args:
        person_id: ID of person looking up the email
        email_id: Email ID to look up
        
    Returns:
        Tuple of (thread_id, original_sender_email) or (None, None) if not found
    """
```

**Email Threading Support**:
- Maintains recent email history (last 10 emails per person)
- Tracks thread_id for conversation continuity
- Enables reply-to functionality in hourly plans
- Automatically links replies to original threads

**Example Usage**:
```python
# Worker wants to reply to email-123
thread_id, sender = communication_hub.get_thread_id_for_reply(
    person_id=1,
    email_id='email-123'
)

if thread_id:
    # Send reply in same thread
    email_gateway.send_email(
        sender='alice@example.com',
        to=[sender],
        subject='Re: Original Subject',
        body='Reply content',
        thread_id=thread_id
    )
```

#### get_recent_emails_for_person()
Get recent emails for a person for context building.

```python
def get_recent_emails_for_person(
    self, 
    person_id: int, 
    limit: int = 10
) -> list[dict]:
    """
    Get recent emails for a person for context building.
    
    Args:
        person_id: ID of person
        limit: Maximum number of emails to return
        
    Returns:
        List of recent email records
    """
```

**Email Record Structure**:
```python
{
    'email_id': 'email-123',
    'from': 'bob@example.com',
    'to': 'alice@example.com',
    'subject': 'Project Update',
    'thread_id': 'thread-abc',
    'sent_at_tick': 42
}
```

### Communication Dispatch

#### dispatch_scheduled()
Dispatch all scheduled communications for a person at the current tick.

```python
def dispatch_scheduled(
    self,
    person: PersonRead,
    current_tick: int,
    people_by_id: dict[int, PersonRead],
    get_current_week_fn: callable,
    get_active_projects_fn: callable,
    get_project_chat_room_fn: callable,
) -> tuple[int, int]:
    """
    Dispatch all scheduled communications for a person at the current tick.
    
    Args:
        person: Person sending the messages
        current_tick: Current simulation tick
        people_by_id: Dictionary of all people by ID
        get_current_week_fn: Function to get current simulation week
        get_active_projects_fn: Function to get active projects for person
        get_project_chat_room_fn: Function to get project chat room slug
        
    Returns:
        Tuple of (emails_sent, chats_sent)
    """
```

**Dispatch Features**:

1. **Target Resolution**:
   - Resolves names to email addresses or chat handles
   - Validates against team roster
   - Supports external stakeholders via `VDOS_EXTERNAL_STAKEHOLDERS` env var
   - Rejects hallucinated email addresses

2. **Automatic CC Suggestion**:
   - Suggests department head as CC when not explicitly provided
   - Suggests relevant peer based on role matching
   - Maintains realistic communication patterns

3. **Group Chat Routing**:
   - Keywords: 'team', 'project', 'group', 'everyone'
   - Routes to project chat room automatically
   - Falls back to DM if no active project

4. **DM Deduplication**:
   - Prevents mirrored DMs (both sides sending same message)
   - Only lexicographically smaller handle sends
   - Maintains deterministic behavior

5. **Email Threading**:
   - Generates unique thread_id for new conversations
   - Preserves thread_id for replies
   - Tracks email history for all recipients

**Example Usage**:
```python
emails_sent, chats_sent = communication_hub.dispatch_scheduled(
    person=worker,
    current_tick=42,
    people_by_id=people_dict,
    get_current_week_fn=lambda: 2,
    get_active_projects_fn=lambda pid, week: [...],
    get_project_chat_room_fn=lambda proj_id: 'project-alpha-chat'
)

logger.info(f"Dispatched {emails_sent} emails and {chats_sent} chats")
```

#### schedule_direct_comm()
Directly schedule a communication for a specific tick.

```python
def schedule_direct_comm(
    self,
    person_id: int,
    tick: int,
    channel: str,
    target: str,
    payload: str
) -> None:
    """
    Directly schedule a communication for a specific tick.
    
    Args:
        person_id: ID of person sending the message
        tick: Tick at which to send the message
        channel: Communication channel ('email' or 'chat')
        target: Target recipient
        payload: Message content
    """
```

**Use Cases**:
- Programmatic message scheduling
- Event-driven communications
- System-generated messages

**Example Usage**:
```python
# Schedule a system notification
communication_hub.schedule_direct_comm(
    person_id=1,
    tick=100,
    channel='email',
    target='alice@example.com',
    payload='System Notification | Server maintenance scheduled'
)
```

## Integration with SimulationEngine

### Initialization

```python
class SimulationEngine:
    def __init__(self, ...):
        # Initialize communication hub with gateways and tick manager
        try:
            cooldown_ticks = int(os.getenv("VDOS_CONTACT_COOLDOWN_TICKS", "10"))
        except ValueError:
            cooldown_ticks = 10
            
        self.communication_hub = CommunicationHub(
            email_gateway=email_gateway,
            chat_gateway=chat_gateway,
            tick_manager=self.tick_manager,
            cooldown_ticks=cooldown_ticks
        )
```

### Tick Processing

During each tick advancement, the engine delegates to CommunicationHub:

```python
def advance(self, ticks: int, reason: str):
    for _ in range(ticks):
        # Reset deduplication at start of tick
        self.communication_hub.reset_tick_sends()
        
        # Parse hourly plans for scheduled communications
        for person in active_people:
            plan = self._get_hourly_plan(person, current_tick)
            self.communication_hub.schedule_from_hourly_plan(
                person=person,
                plan_text=plan.content,
                current_tick=current_tick,
                hours_per_day=self.hours_per_day
            )
        
        # Dispatch scheduled communications
        for person in active_people:
            emails, chats = self.communication_hub.dispatch_scheduled(
                person=person,
                current_tick=current_tick,
                people_by_id=people_dict,
                get_current_week_fn=self._get_current_week,
                get_active_projects_fn=self._get_all_active_projects_for_person,
                get_project_chat_room_fn=self.get_active_project_chat_room
            )
```

### Engine Delegation Methods

The engine provides thin delegation methods for backward compatibility:

```python
def _reset_tick_sends(self) -> None:
    """Delegate to CommunicationHub."""
    self.communication_hub.reset_tick_sends()

def _can_send(self, *, tick: int, channel: str, sender: str, 
              recipient_key: tuple, subject: str | None, body: str) -> bool:
    """Delegate to CommunicationHub."""
    return self.communication_hub.can_send(...)

def _schedule_from_hourly_plan(self, person: PersonRead, 
                                plan_text: str, current_tick: int) -> None:
    """Delegate to CommunicationHub."""
    self.communication_hub.schedule_from_hourly_plan(...)

def _dispatch_scheduled(self, person: PersonRead, current_tick: int, 
                        people_by_id: dict[int, PersonRead]) -> tuple[int, int]:
    """Delegate to CommunicationHub."""
    return self.communication_hub.dispatch_scheduled(...)
```

## Configuration

### Environment Variables

- `VDOS_CONTACT_COOLDOWN_TICKS` - Minimum ticks between messages to same recipient (default: 10)
- `VDOS_EXTERNAL_STAKEHOLDERS` - Comma-separated list of external email addresses allowed in simulations

**Example**:
```bash
VDOS_CONTACT_COOLDOWN_TICKS=15
VDOS_EXTERNAL_STAKEHOLDERS=client@external.com,vendor@partner.com
```

## Testing

### Unit Tests

Location: `tests/core/test_communication_hub.py`

**Test Coverage**:
- Message deduplication and cooldown logic
- Hourly plan parsing (all formats)
- Email threading and reply-to functionality
- Communication dispatch (email, chat, group chat)
- Target resolution and validation
- Automatic CC suggestion
- Hallucinated email rejection

**Example Test**:
```python
def test_can_send_cooldown_enforced():
    comm_hub = CommunicationHub(...)
    
    # Send first message at tick 1
    comm_hub.can_send(
        tick=1,
        channel='email',
        sender='alice@example.com',
        recipient_key=('bob@example.com',),
        subject='Test 1',
        body='Hello 1'
    )
    
    # Try to send different message at tick 5 (within cooldown of 10)
    result = comm_hub.can_send(
        tick=5,
        channel='email',
        sender='alice@example.com',
        recipient_key=('bob@example.com',),
        subject='Test 2',
        body='Hello 2'
    )
    
    assert result is False  # Blocked by cooldown
```

### Integration Tests

Location: `tests/test_sim_manager.py`

**Test Scenarios**:
- Full simulation with scheduled communications
- Multi-person communication patterns
- Email threading across multiple ticks
- Group chat coordination

## Performance Considerations

### Memory Management
- Recent emails limited to 10 per person (configurable via deque maxlen)
- Scheduled communications cleared after dispatch
- Deduplication set cleared each tick

### Optimization Strategies
- O(1) deduplication checks using set
- O(1) cooldown checks using dict
- Efficient regex compilation for plan parsing
- Minimal string operations during dispatch

## Extension Guidelines

### Adding New Communication Formats

1. **Define Regex Pattern**:
```python
new_format_re = re.compile(
    r"^NewFormat\s+at\s+(\d{2}:\d{2})\s+to\s+([^:]+):\s*(.*)$",
    re.I
)
```

2. **Add Parsing Logic**:
```python
# In schedule_from_hourly_plan()
m = new_format_re.match(ln)
if m:
    channel = 'new_channel'
    when, target, payload = m.group(1), m.group(2), m.group(3)
    # Schedule the communication
```

3. **Add Dispatch Logic**:
```python
# In dispatch_scheduled()
elif channel == 'new_channel':
    # Handle new channel dispatch
    new_gateway.send_message(...)
```

### Customizing CC Suggestion Logic

Modify the `_suggest_cc()` function in `dispatch_scheduled()`:

```python
def _suggest_cc(primary_to_email: str) -> list[str]:
    cc_list: list[str] = []
    
    # Custom logic for CC suggestions
    # Example: Always CC project manager
    for p in people_by_id.values():
        if 'project manager' in p.role.lower():
            cc_list.append(p.email_address)
    
    return cc_list
```

### Adding New Target Resolution Rules

Extend the `_match_target()` function in `dispatch_scheduled()`:

```python
def _match_target(raw: str) -> tuple[str | None, str | None]:
    val = raw.strip().lower()
    
    # Custom resolution logic
    if val.startswith('@'):
        # Handle special @mentions
        handle = val[1:]
        return None, handle
    
    # Existing logic...
```

## Best Practices

### Communication Scheduling
- Use clear, parseable formats in hourly plans
- Include subject and body for emails (separated by ` | `)
- Specify CC/BCC explicitly when needed
- Use reply-to syntax for threaded conversations

### Message Deduplication
- Rely on automatic deduplication for same-tick messages
- Configure cooldown appropriately for simulation realism
- Reset deduplication at tick boundaries

### Email Threading
- Use reply-to syntax to maintain conversation threads
- Track email IDs for context building
- Leverage recent email history for planning

### Group Communication
- Use keywords ('team', 'project', 'group') for group chats
- Ensure active projects exist for group routing
- Fall back to DM when group routing fails

## Future Enhancements

### Planned Features
1. **Priority-based dispatch**: High-priority messages bypass cooldown
2. **Scheduled reminders**: Automatic follow-up messages
3. **Communication templates**: Reusable message templates
4. **Advanced threading**: Multi-level conversation trees
5. **Communication analytics**: Track patterns and volumes

### Integration Roadmap
1. **Phase 2**: CommunicationHub extraction ✅ Complete (Task 2.1)
2. **Phase 2**: CommunicationHub tests ✅ Complete (Task 2.2)
3. **Phase 2**: CommunicationHub integration ✅ Complete (Task 2.3)
4. **Phase 3**: Template-based communication generation
5. **Phase 4**: Worker-driven communication planning

## Conclusion

The CommunicationHub module provides a clean, testable, and extensible foundation for managing all simulation communications. By extracting this functionality from the SimulationEngine, we've improved code organization, testability, and maintainability while preserving all existing functionality and adding new capabilities like email threading and group chat routing.

The module's design supports both scheduled communications from hourly plans and programmatic message generation, making it a versatile tool for realistic workplace communication simulation.
