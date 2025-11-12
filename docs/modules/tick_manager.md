# TickManager Module

## Overview

The `TickManager` module handles all time-related operations in the simulation, including tick advancement, work hours calculation, auto-tick threading, and time formatting. It provides a clean abstraction for simulation time management.

**Location**: `src/virtualoffice/sim_manager/core/tick_manager.py`

## Responsibilities

- Time progression and tick advancement
- Auto-tick loop management with threading
- Work hours calculation and caching
- Simulation datetime calculations
- Time formatting utilities
- Day/week/tick conversions

## Class: TickManager

### Constructor

```python
def __init__(self, state: SimulationState, hours_per_day: int = 8)
```

**Parameters**:
- `state` (SimulationState): State manager for tick persistence
- `hours_per_day` (int): Number of work hours per simulated day (default: 8)

**Example**:
```python
from virtualoffice.sim_manager.core.simulation_state import SimulationState
from virtualoffice.sim_manager.core.tick_manager import TickManager

state = SimulationState()
tick_manager = TickManager(state, hours_per_day=8)
```

### Methods

#### advance_ticks

```python
def advance_ticks(self, count: int, reason: str) -> None
```

Advance the simulation by the specified number of ticks.

**Parameters**:
- `count` (int): Number of ticks to advance
- `reason` (str): Reason for advancement (logged)

**Example**:
```python
tick_manager.advance_ticks(10, "Manual advancement")
tick_manager.advance_ticks(1, "Auto-tick")
```

#### is_within_work_hours

```python
def is_within_work_hours(self, person: PersonRead, tick: int) -> bool
```

Check if a given tick falls within a person's work hours.

**Parameters**:
- `person` (PersonRead): Person with work_hours attribute
- `tick` (int): Tick to check

**Returns**: True if tick is during work hours, False otherwise

**Example**:
```python
from virtualoffice.sim_manager.schemas import PersonRead

person = PersonRead(
    id=1,
    name="Test Worker",
    work_hours="09:00-18:00",
    ...
)

is_working = tick_manager.is_within_work_hours(person, tick=5)
print(f"Working at tick 5: {is_working}")
```

#### parse_work_hours_to_ticks

```python
def parse_work_hours_to_ticks(self, work_hours: str) -> tuple[int, int]
```

Convert work hours string to tick range.

**Parameters**:
- `work_hours` (str): Work hours in format "HH:MM-HH:MM" (e.g., "09:00-18:00")

**Returns**: Tuple of (start_tick, end_tick) where ticks are 0-indexed within the day

**Example**:
```python
start_tick, end_tick = tick_manager.parse_work_hours_to_ticks("09:00-18:00")
print(f"Work hours: tick {start_tick} to {end_tick}")  # 0 to 7 (8 hours)
```

#### format_sim_time

```python
def format_sim_time(self, tick: int) -> str
```

Format a tick as human-readable time string.

**Parameters**:
- `tick` (int): Tick to format

**Returns**: Formatted string like "Day 1, 10:00 AM" or "Week 2, Day 3, 2:00 PM"

**Example**:
```python
time_str = tick_manager.format_sim_time(15)
print(time_str)  # "Day 2, 4:00 PM" (assuming 8-hour days)
```

#### sim_datetime_for_tick

```python
def sim_datetime_for_tick(self, tick: int, base_dt: datetime) -> datetime
```

Convert a tick to an actual datetime object.

**Parameters**:
- `tick` (int): Tick to convert
- `base_dt` (datetime): Base datetime for simulation start

**Returns**: datetime object representing the tick

**Example**:
```python
from datetime import datetime

base_time = datetime(2024, 1, 1, 9, 0)  # Start at 9 AM
tick_time = tick_manager.sim_datetime_for_tick(5, base_time)
print(tick_time)  # 2024-01-01 14:00:00 (5 hours after start)
```

#### start_auto_tick

```python
def start_auto_tick(self, callback: Callable, interval_seconds: float) -> None
```

Start the auto-tick background thread.

**Parameters**:
- `callback` (Callable): Function to call on each tick (typically engine.advance)
- `interval_seconds` (float): Seconds between ticks

**Example**:
```python
def on_tick():
    print("Tick!")
    engine.advance(1, "auto-tick")

tick_manager.start_auto_tick(on_tick, interval_seconds=1.0)
```

#### stop_auto_tick

```python
def stop_auto_tick(self) -> None
```

Stop the auto-tick background thread.

**Example**:
```python
tick_manager.stop_auto_tick()
```

#### is_auto_tick_running

```python
def is_auto_tick_running(self) -> bool
```

Check if auto-tick is currently running.

**Returns**: True if auto-tick thread is active, False otherwise

**Example**:
```python
if tick_manager.is_auto_tick_running():
    print("Auto-tick is running")
else:
    print("Auto-tick is stopped")
```

## Time Calculations

### Tick to Day/Week Conversion

```python
# Assuming 8 hours per day, 5 days per week
day_index = tick // hours_per_day  # 0-indexed day
week_index = day_index // 5  # 0-indexed week
day_of_week = day_index % 5  # 0-4 (Mon-Fri)
hour_of_day = tick % hours_per_day  # 0-7
```

### Work Hours Caching

The `TickManager` caches parsed work hours to avoid repeated string parsing:

```python
# First call parses and caches
start, end = tick_manager.parse_work_hours_to_ticks("09:00-18:00")

# Subsequent calls use cache
start, end = tick_manager.parse_work_hours_to_ticks("09:00-18:00")  # Fast!
```

## Auto-Tick Threading

The auto-tick feature runs in a background thread:

```
┌─────────────────────────────────────┐
│         Main Thread                 │
│  (FastAPI Event Loop)               │
│                                     │
│  tick_manager.start_auto_tick()     │
│         │                           │
│         └──────────┐                │
└────────────────────┼────────────────┘
                     │
         ┌───────────▼──────────────┐
         │   Auto-Tick Thread       │
         │                          │
         │  while running:          │
         │    sleep(interval)       │
         │    callback()            │
         │                          │
         └──────────────────────────┘
```

**Thread Safety**:
- Auto-tick thread calls the provided callback
- Callback should handle its own thread safety (e.g., using locks)
- `stop_auto_tick()` safely terminates the thread

## Integration

### With SimulationEngine

```python
class SimulationEngine:
    def __init__(self, ..., hours_per_day: int = 8, tick_interval_seconds: float = 1.0):
        self.state_manager = SimulationState()
        self.tick_manager = TickManager(self.state_manager, hours_per_day)
        self.tick_interval_seconds = tick_interval_seconds
    
    def start_auto_tick(self):
        def on_tick():
            self.advance(1, "auto-tick")
        
        self.tick_manager.start_auto_tick(on_tick, self.tick_interval_seconds)
    
    def stop_auto_tick(self):
        self.tick_manager.stop_auto_tick()
```

### With CommunicationHub

```python
class CommunicationHub:
    def __init__(self, ..., tick_manager: TickManager):
        self.tick_manager = tick_manager
    
    def format_email_timestamp(self, tick: int):
        return self.tick_manager.format_sim_time(tick)
```

## Configuration

### Environment Variables

- `VDOS_WORKDAY_START`: Work day start time (default: "09:00")
- `VDOS_WORKDAY_END`: Work day end time (default: "18:00")
- `VDOS_TICK_MS`: Wall-clock milliseconds per tick (default: 50)

### Hours Per Day

The `hours_per_day` parameter affects:
- Day boundaries (day_index = tick // hours_per_day)
- Week calculations (week_index = day_index // 5)
- Time formatting
- Work hours validation

**Common Values**:
- `8`: Standard 8-hour workday (default)
- `2`: Fast testing (2 hours per day)
- `24`: Full day simulation

## Best Practices

1. **Consistent Hours**: Use the same `hours_per_day` throughout the simulation
2. **Work Hours Format**: Always use "HH:MM-HH:MM" format for work_hours
3. **Auto-Tick Cleanup**: Always call `stop_auto_tick()` before engine shutdown
4. **Thread Safety**: Ensure auto-tick callback handles concurrent access
5. **Time Zones**: Use consistent time zones across all workers

## Example Usage

```python
from datetime import datetime
from virtualoffice.sim_manager.core.simulation_state import SimulationState
from virtualoffice.sim_manager.core.tick_manager import TickManager
from virtualoffice.sim_manager.schemas import PersonRead

# Initialize
state = SimulationState()
tick_manager = TickManager(state, hours_per_day=8)

# Parse work hours
start_tick, end_tick = tick_manager.parse_work_hours_to_ticks("09:00-18:00")
print(f"Work hours: {start_tick} to {end_tick}")  # 0 to 7

# Check if worker is working
person = PersonRead(id=1, name="Worker", work_hours="09:00-18:00", ...)
is_working = tick_manager.is_within_work_hours(person, tick=5)
print(f"Working at tick 5: {is_working}")  # True

# Format time
time_str = tick_manager.format_sim_time(15)
print(time_str)  # "Day 2, 4:00 PM"

# Convert to datetime
base_time = datetime(2024, 1, 1, 9, 0)
tick_time = tick_manager.sim_datetime_for_tick(5, base_time)
print(tick_time)  # 2024-01-01 14:00:00

# Start auto-tick
def on_tick():
    current_state = state.get_current_state()
    print(f"Auto-tick: {current_state.current_tick}")
    tick_manager.advance_ticks(1, "auto-tick")

tick_manager.start_auto_tick(on_tick, interval_seconds=0.1)

# Run for a while...
import time
time.sleep(1.0)

# Stop auto-tick
tick_manager.stop_auto_tick()
print(f"Auto-tick running: {tick_manager.is_auto_tick_running()}")  # False
```

## Testing

The module has comprehensive unit tests in `tests/core/test_tick_manager.py` covering:
- Tick advancement
- Work hours parsing and validation
- Time formatting
- Datetime conversion
- Auto-tick threading
- Edge cases (midnight, day boundaries)
- Thread safety

Run tests with:
```bash
pytest tests/core/test_tick_manager.py -v
```

## Performance Considerations

- **Work Hours Caching**: Parsed work hours are cached for performance
- **Auto-Tick Overhead**: Minimal overhead (~1ms per tick)
- **Thread Safety**: Uses threading.Event for clean shutdown
- **Memory Usage**: Negligible (only caches work hours strings)

## Common Patterns

### Manual Tick Advancement

```python
# Advance one tick at a time
for i in range(10):
    tick_manager.advance_ticks(1, f"Step {i}")
```

### Bulk Advancement

```python
# Advance multiple ticks at once
tick_manager.advance_ticks(40, "Complete one week")  # 5 days * 8 hours
```

### Conditional Advancement

```python
# Only advance if worker is working
if tick_manager.is_within_work_hours(person, current_tick):
    tick_manager.advance_ticks(1, "Work hour")
```

### Auto-Tick with Pause

```python
# Start auto-tick
tick_manager.start_auto_tick(callback, 1.0)

# Pause when needed
if should_pause:
    tick_manager.stop_auto_tick()

# Resume later
if should_resume:
    tick_manager.start_auto_tick(callback, 1.0)
```
