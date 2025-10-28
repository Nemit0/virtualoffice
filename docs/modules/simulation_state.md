# SimulationState Module

## Overview

The `SimulationState` module provides centralized management of simulation state persistence, database operations, and configuration. It encapsulates all SQLite operations and provides a clean interface for state management.

**Location**: `src/virtualoffice/sim_manager/core/simulation_state.py`

## Responsibilities

- Database initialization and schema management
- Simulation state persistence (tick, running status, auto-tick)
- Configuration loading from environment variables
- Status override management for workers
- Database schema migrations
- Thread-safe state updates

## Class: SimulationState

### Constructor

```python
def __init__(self, db_path: str | None = None)
```

**Parameters**:
- `db_path` (str | None): Path to SQLite database file. If None, uses `VDOS_DB_PATH` environment variable or default path.

**Example**:
```python
# Use default database path
state = SimulationState()

# Use custom database path
state = SimulationState(db_path="/path/to/custom.db")
```

### Methods

#### get_current_state

```python
def get_current_state(self) -> SimulationStatus
```

Get the current simulation status including tick, running state, and auto-tick setting.

**Returns**: `SimulationStatus` dataclass with:
- `current_tick` (int): Current simulation tick
- `is_running` (bool): Whether simulation is running
- `auto_tick` (bool): Whether auto-tick is enabled

**Example**:
```python
status = state.get_current_state()
print(f"Tick: {status.current_tick}, Running: {status.is_running}")
```

#### update_tick

```python
def update_tick(self, tick: int, reason: str) -> None
```

Update the current simulation tick and log the advancement reason.

**Parameters**:
- `tick` (int): New tick value
- `reason` (str): Reason for tick advancement (logged to tick_log table)

**Example**:
```python
state.update_tick(100, "Manual advancement")
```

#### set_running

```python
def set_running(self, running: bool) -> None
```

Set the simulation running state.

**Parameters**:
- `running` (bool): True to mark simulation as running, False otherwise

**Example**:
```python
state.set_running(True)  # Start simulation
state.set_running(False)  # Stop simulation
```

#### set_auto_tick

```python
def set_auto_tick(self, enabled: bool) -> None
```

Enable or disable auto-tick functionality.

**Parameters**:
- `enabled` (bool): True to enable auto-tick, False to disable

**Example**:
```python
state.set_auto_tick(True)  # Enable auto-tick
state.set_auto_tick(False)  # Disable auto-tick
```

#### get_status_overrides

```python
def get_status_overrides(self) -> dict[int, tuple[str, int]]
```

Get all active worker status overrides.

**Returns**: Dictionary mapping person_id to (status, until_tick) tuples

**Example**:
```python
overrides = state.get_status_overrides()
for person_id, (status, until_tick) in overrides.items():
    print(f"Worker {person_id}: {status} until tick {until_tick}")
```

#### set_status_override

```python
def set_status_override(self, worker_id: int, status: str, until_tick: int) -> None
```

Set a temporary status override for a worker (e.g., sick leave).

**Parameters**:
- `worker_id` (int): ID of the worker
- `status` (str): Override status (e.g., "SickLeave", "Vacation")
- `until_tick` (int): Tick when override expires

**Example**:
```python
# Worker 1 is sick until tick 100
state.set_status_override(1, "SickLeave", 100)
```

#### clear_status_override

```python
def clear_status_override(self, worker_id: int) -> None
```

Clear a worker's status override.

**Parameters**:
- `worker_id` (int): ID of the worker

**Example**:
```python
state.clear_status_override(1)  # Worker 1 returns to normal status
```

#### apply_migrations

```python
def apply_migrations(self) -> None
```

Apply any pending database schema migrations.

**Example**:
```python
state.apply_migrations()
```

#### reset

```python
def reset(self) -> None
```

Reset the simulation state to initial values (tick=0, not running, auto-tick off).

**Example**:
```python
state.reset()  # Reset simulation
```

#### close

```python
def close(self) -> None
```

Close the database connection.

**Example**:
```python
state.close()
```

## Database Tables

### simulation_state

Single-row table tracking simulation state.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Always 1 |
| current_tick | INTEGER | Current simulation tick |
| is_running | INTEGER | 0 or 1 |
| auto_tick | INTEGER | 0 or 1 |

### tick_log

Log of tick advancements.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Unique identifier |
| tick | INTEGER | Tick value |
| reason | TEXT | Advancement reason |
| timestamp | TEXT | ISO timestamp |

### worker_status_overrides

Temporary status overrides for workers.

| Column | Type | Description |
|--------|------|-------------|
| person_id | INTEGER PK | Worker ID |
| status | TEXT | Override status |
| until_tick | INTEGER | Expiration tick |

## Integration

### With SimulationEngine

```python
class SimulationEngine:
    def __init__(self, ...):
        self.state_manager = SimulationState()
    
    def advance(self, ticks: int, reason: str):
        current_state = self.state_manager.get_current_state()
        new_tick = current_state.current_tick + ticks
        self.state_manager.update_tick(new_tick, reason)
```

### With TickManager

```python
class TickManager:
    def __init__(self, state: SimulationState, ...):
        self.state = state
    
    def advance_ticks(self, count: int, reason: str):
        current_state = self.state.get_current_state()
        new_tick = current_state.current_tick + count
        self.state.update_tick(new_tick, reason)
```

## Thread Safety

The `SimulationState` class is thread-safe for concurrent read operations. Write operations should be serialized by the caller (typically through the engine's `_advance_lock`).

## Configuration

### Environment Variables

- `VDOS_DB_PATH`: Path to SQLite database file (default: `src/virtualoffice/vdos.db`)
- `VDOS_DB_URL`: Alternative database connection URL format

## Best Practices

1. **Single Instance**: Create one `SimulationState` instance per simulation engine
2. **Close Connections**: Always call `close()` when done with the state manager
3. **Error Handling**: Wrap database operations in try-except blocks
4. **Migrations**: Call `apply_migrations()` after initialization
5. **Status Overrides**: Always set `until_tick` to prevent permanent overrides

## Example Usage

```python
from virtualoffice.sim_manager.core.simulation_state import SimulationState

# Initialize
state = SimulationState()
state.apply_migrations()

# Start simulation
state.set_running(True)
state.set_auto_tick(True)

# Advance simulation
for i in range(10):
    current = state.get_current_state()
    state.update_tick(current.current_tick + 1, f"Iteration {i}")

# Set worker on sick leave
state.set_status_override(worker_id=1, status="SickLeave", until_tick=50)

# Check status
overrides = state.get_status_overrides()
print(f"Active overrides: {overrides}")

# Reset and cleanup
state.reset()
state.close()
```

## Testing

The module has comprehensive unit tests in `tests/core/test_simulation_state.py` covering:
- State persistence and retrieval
- Tick advancement and logging
- Status override management
- Database migrations
- Thread safety
- Error handling

Run tests with:
```bash
pytest tests/core/test_simulation_state.py -v
```
