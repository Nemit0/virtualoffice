# WorkerRuntime Module Documentation

## Overview

The WorkerRuntime module (`src/virtualoffice/sim_manager/core/worker_runtime.py`) manages runtime state for virtual workers including message queuing, inbox management, and persistence. It was extracted from the SimulationEngine as part of the Phase 1 engine refactoring project.

## Architecture

### Module Location
```
src/virtualoffice/sim_manager/core/
├── worker_runtime.py        # WorkerRuntime and WorkerRuntimeManager classes
├── event_system.py          # InboundMessage dataclass (dependency)
└── simulation_state.py      # State management
```

### Dependencies
- `virtualoffice.common.db` - Database connection management
- `virtualoffice.sim_manager.schemas` - PersonRead model
- `virtualoffice.sim_manager.core.event_system` - InboundMessage dataclass

## Core Classes

### WorkerRuntime

Dataclass representing runtime state for a single virtual worker.

```python
@dataclass
class WorkerRuntime:
    """
    Runtime state for a single virtual worker.
    
    Maintains an inbox of pending messages that need to be processed
    by the worker during their next planning cycle.
    """
    person: PersonRead
    inbox: list[InboundMessage] = field(default_factory=list)
```

#### Key Methods

##### queue()
Add a message to the worker's inbox.

```python
def queue(self, message: InboundMessage) -> None:
    """Add a message to the worker's inbox."""
```

**Example Usage**:
```python
runtime = WorkerRuntime(person=worker)
message = InboundMessage(
    sender_id=1,
    sender_name="Manager",
    subject="Task Update",
    summary="Please review the PR",
    action_item="Review PR #123",
    message_type="email",
    channel="email",
    tick=50
)
runtime.queue(message)
```

##### drain()
Remove and return all messages from the inbox.

```python
def drain(self) -> list[InboundMessage]:
    """
    Remove and return all messages from the inbox.
    
    Returns:
        List of messages that were in the inbox
    """
```

**Example Usage**:
```python
# Worker processes all pending messages
messages = runtime.drain()
for msg in messages:
    # Process message in planning cycle
    process_message(msg)
```

##### has_messages()
Check if the worker has any pending messages.

```python
def has_messages(self) -> bool:
    """Check if the worker has any pending messages."""
```

##### message_count()
Get the number of pending messages.

```python
def message_count(self) -> int:
    """Get the number of pending messages."""
```

### WorkerRuntimeManager

Main class responsible for managing runtime state for all workers.

```python
class WorkerRuntimeManager:
    """
    Manages runtime state for all virtual workers in the simulation.
    
    Handles:
    - Creating and retrieving worker runtimes
    - Synchronizing runtimes with active people
    - Persisting messages to database
    - Loading messages from database
    - Clearing runtime state
    """
```

#### Key Methods

##### get_runtime()
Get or create a runtime for a person.

```python
def get_runtime(self, person: PersonRead) -> WorkerRuntime:
    """
    Get or create a runtime for a person.
    
    Args:
        person: Person to get runtime for
        
    Returns:
        WorkerRuntime for the person
    """
```

**Example Usage**:
```python
manager = WorkerRuntimeManager()
runtime = manager.get_runtime(worker)

# Runtime is cached - subsequent calls return same instance
runtime2 = manager.get_runtime(worker)
assert runtime is runtime2
```

**Behavior**:
- Creates new runtime if one doesn't exist
- Loads persisted messages from database on creation
- Updates person reference if runtime already exists
- Caches runtimes by person ID

##### sync_runtimes()
Synchronize worker runtimes with the active people list.

```python
def sync_runtimes(self, people: Sequence[PersonRead]) -> None:
    """
    Synchronize worker runtimes with the active people list.
    
    Creates runtimes for new people and removes runtimes for
    people who are no longer active.
    
    Args:
        people: List of currently active people
    """
```

**Example Usage**:
```python
# After simulation start or people changes
active_people = engine.list_people()
manager.sync_runtimes(active_people)
```

**Behavior**:
- Creates runtimes for all active people
- Removes runtimes for people no longer in the list
- Maintains consistency between simulation state and runtimes

##### queue_message()
Queue a message for a recipient and persist it to the database.

```python
def queue_message(self, recipient: PersonRead, message: InboundMessage) -> None:
    """
    Queue a message for a recipient and persist it to the database.
    
    Args:
        recipient: Person to receive the message
        message: Message to queue
    """
```

**Example Usage**:
```python
# Queue a message from event system
message = InboundMessage(
    sender_id=0,
    sender_name="System",
    subject="Client Request",
    summary="New feature request received",
    action_item="Review and estimate",
    message_type="event",
    channel="system",
    tick=100
)
manager.queue_message(worker, message)
```

**Behavior**:
- Adds message to worker's inbox
- Persists message to `worker_runtime_messages` table
- Sets `message_id` on the InboundMessage object

##### remove_messages()
Remove messages from the database by their IDs.

```python
def remove_messages(self, message_ids: Sequence[int]) -> None:
    """
    Remove messages from the database by their IDs.
    
    Args:
        message_ids: List of message IDs to remove
    """
```

**Example Usage**:
```python
# After worker processes messages
messages = runtime.drain()
message_ids = [msg.message_id for msg in messages if msg.message_id]
manager.remove_messages(message_ids)
```

##### clear_all()
Clear all worker runtimes and delete all runtime messages from database.

```python
def clear_all(self) -> None:
    """Clear all worker runtimes and delete all runtime messages from database."""
```

**Example Usage**:
```python
# Reset simulation state
manager.clear_all()
```

##### get_all_runtimes()
Get all worker runtimes.

```python
def get_all_runtimes(self) -> dict[int, WorkerRuntime]:
    """
    Get all worker runtimes.
    
    Returns:
        Dictionary mapping person IDs to their runtimes
    """
```

## Integration with SimulationEngine

### Initialization

```python
class SimulationEngine:
    def __init__(self, ...):
        # Initialize worker runtime manager
        self.worker_runtime_manager = WorkerRuntimeManager()
        
        # Sync with active people
        self.worker_runtime_manager.sync_runtimes(self.list_people())
```

### Message Queuing

During event processing or communication, messages are queued for workers:

```python
def _queue_message(self, recipient: PersonRead, message: InboundMessage):
    """Queue a message for a worker."""
    self.worker_runtime_manager.queue_message(recipient, message)
```

### Message Processing

During tick advancement, workers drain their inboxes:

```python
def advance(self, ticks: int, reason: str):
    for person in active_people:
        runtime = self.worker_runtime_manager.get_runtime(person)
        
        if runtime.has_messages():
            # Drain inbox
            messages = runtime.drain()
            
            # Process messages in planning
            context = self._build_planning_context(person, messages)
            plan = self._call_planner('generate_hourly_plan', **context)
            
            # Remove processed messages from database
            message_ids = [msg.message_id for msg in messages if msg.message_id]
            self.worker_runtime_manager.remove_messages(message_ids)
```

### Simulation Reset

When resetting simulation state:

```python
def reset(self):
    """Reset simulation to initial state."""
    self.worker_runtime_manager.clear_all()
    # ... other reset operations
```

## Database Schema

### worker_runtime_messages Table

```sql
CREATE TABLE worker_runtime_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id INTEGER NOT NULL,
    payload TEXT NOT NULL,  -- JSON object
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recipient_id) REFERENCES people(id) ON DELETE CASCADE
);
```

**Columns**:
- `id`: Unique message identifier
- `recipient_id`: ID of the person who should receive the message
- `payload`: JSON object containing InboundMessage fields
- `created_at`: Timestamp of message creation

**Payload Structure**:
```json
{
    "sender_id": 1,
    "sender_name": "Manager",
    "subject": "Task Update",
    "summary": "Please review the PR",
    "action_item": "Review PR #123",
    "message_type": "email",
    "channel": "email",
    "tick": 50
}
```

## Message Lifecycle

### 1. Message Creation
Messages are created by:
- EventSystem during event processing
- CommunicationHub during scheduled communication
- SimulationEngine during direct messaging

### 2. Message Queuing
```python
# Create message
message = InboundMessage(...)

# Queue for recipient
manager.queue_message(recipient, message)
```

### 3. Message Persistence
- Automatically persisted to database when queued
- `message_id` set on InboundMessage object
- Survives simulation restarts

### 4. Message Loading
- Automatically loaded when runtime is created
- Loaded from database in ID order
- Reconstructed as InboundMessage objects

### 5. Message Processing
```python
# Worker drains inbox
messages = runtime.drain()

# Process in planning cycle
for msg in messages:
    # Include in planning context
    # Generate responses
    pass

# Remove from database
message_ids = [msg.message_id for msg in messages if msg.message_id]
manager.remove_messages(message_ids)
```

### 6. Message Cleanup
- Removed after processing
- Cleared on simulation reset
- Cascade deleted when person is deleted

## Testing

### Unit Tests

Location: `tests/core/test_worker_runtime.py`

**Test Coverage**:
- Runtime creation and caching
- Message queuing and draining
- Database persistence and loading
- Runtime synchronization
- Message removal
- Clear all functionality

**Example Test**:
```python
def test_queue_and_drain_messages():
    manager = WorkerRuntimeManager()
    runtime = manager.get_runtime(worker)
    
    # Queue messages
    msg1 = InboundMessage(...)
    msg2 = InboundMessage(...)
    runtime.queue(msg1)
    runtime.queue(msg2)
    
    assert runtime.message_count() == 2
    assert runtime.has_messages()
    
    # Drain messages
    messages = runtime.drain()
    assert len(messages) == 2
    assert runtime.message_count() == 0
    assert not runtime.has_messages()
```

### Integration Tests

Location: `tests/test_sim_manager.py`

**Test Scenarios**:
- Message queuing during simulation
- Message persistence across restarts
- Worker inbox processing
- Runtime synchronization with people changes

## Performance Considerations

### Memory Usage
- Runtimes cached in memory by person ID
- Inbox messages stored in memory until drained
- Database persistence prevents memory growth

### Database Operations
- Batch message removal for efficiency
- Indexed queries on recipient_id
- Cascade deletes for cleanup

### Optimization Strategies
- Lazy runtime creation (only when needed)
- Batch database operations where possible
- Clear processed messages promptly
- Limit inbox size through regular draining

## Best Practices

### Runtime Management
- Always sync runtimes after people changes
- Clear runtimes on simulation reset
- Use get_runtime() for consistent access

### Message Handling
- Queue messages immediately when created
- Drain inbox before planning cycles
- Remove processed messages from database
- Include message context in planning

### Database Consistency
- Let WorkerRuntimeManager handle persistence
- Don't manipulate worker_runtime_messages table directly
- Use cascade deletes for cleanup
- Rely on automatic loading on runtime creation

### Error Handling
- Handle missing runtimes gracefully
- Validate message payloads before queuing
- Log database errors for debugging
- Ensure cleanup on exceptions

## Future Enhancements

### Planned Features
1. **Message Prioritization**: Priority queue for urgent messages
2. **Message Expiration**: Automatic cleanup of old messages
3. **Message Threading**: Link related messages together
4. **Batch Operations**: Bulk message queuing and removal
5. **Message Filtering**: Filter messages by type or sender

### Integration Roadmap
1. **Phase 1**: WorkerRuntime extraction ✅ Complete
2. **Phase 2**: Enhanced message management
3. **Phase 3**: Message analytics and reporting
4. **Phase 4**: Advanced inbox management features

## Conclusion

The WorkerRuntime module provides a clean, testable, and efficient foundation for managing worker message inboxes and runtime state. By extracting this functionality from the SimulationEngine, we've improved code organization, testability, and maintainability while preserving all existing functionality.

The module's design supports both in-memory performance and database persistence, ensuring that worker state survives simulation restarts while maintaining fast access during active simulation.
