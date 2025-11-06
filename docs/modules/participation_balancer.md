# Participation Balancer Module

**Module:** `src/virtualoffice/sim_manager/participation_balancer.py`  
**Purpose:** Ensure realistic distribution of communication volume across personas  
**Status:** Implemented (2025-11-05)

## Overview

The Participation Balancer prevents message dominance by tracking communication volume per persona and applying throttling or boosting to maintain balanced participation. This ensures that no single persona dominates conversations while preventing personas from being completely silent.

## Key Features

- **Message Counting**: Tracks email and chat messages per persona per day
- **Throttling**: Reduces probability for high-volume senders (>2x team average)
- **Boosting**: Increases probability for low-volume senders (<0.5x team average)
- **Deterministic**: Uses provided random generator for reproducible behavior
- **Configurable**: Can be enabled/disabled via configuration flag
- **Observable**: Logs throttling/boosting decisions and provides statistics

## Requirements Addressed

- **R-5.1**: Track message counts per persona per simulation day
- **R-5.2**: Throttle personas exceeding 2x team average (probability 0.3)
- **R-5.3**: Boost personas below 0.5x team average (probability 0.9)
- **R-5.4**: Ensure top 2 chatters account for ≤40% of total messages
- **R-9.1**: Deterministic behavior with random seed
- **R-11.4**: Configuration support via enabled flag
- **O-3**: Log throttling/boosting decisions at INFO level

## Architecture

### Data Structures

```python
@dataclass
class ParticipationStats:
    """Statistics for a persona's participation on a specific day."""
    person_id: int
    day_index: int
    email_count: int = 0
    chat_count: int = 0
    total_count: int = 0
    probability_modifier: float = 1.0
```

### Class: ParticipationBalancer

```python
class ParticipationBalancer:
    """Manages participation balancing to ensure realistic message distribution."""
    
    def __init__(self, enabled: bool = True):
        """Initialize with optional enable/disable flag."""
        
    def record_message(self, person_id: int, day_index: int, channel: str) -> None:
        """Record that a persona sent a message."""
        
    def get_send_probability(self, person_id: int, day_index: int, team_size: int) -> float:
        """Get probability modifier for sending fallback message."""
        
    def should_generate_fallback(
        self, 
        person_id: int, 
        day_index: int, 
        team_size: int,
        random_gen: random.Random
    ) -> bool:
        """Determine if fallback message should be generated."""
        
    def get_stats_summary(self, day_index: int) -> Dict[str, any]:
        """Get summary statistics for all personas on a specific day."""
        
    def log_daily_summary(self, day_index: int) -> None:
        """Log summary of participation balance for a day."""
```

## Usage Examples

### Basic Usage

```python
from src.virtualoffice.sim_manager.participation_balancer import ParticipationBalancer
import random

# Initialize balancer
balancer = ParticipationBalancer(enabled=True)
rng = random.Random(42)  # For deterministic behavior

# Record messages as they are sent
balancer.record_message(person_id=1, day_index=0, channel='email')
balancer.record_message(person_id=1, day_index=0, channel='chat')

# Check if persona should send fallback message
should_send = balancer.should_generate_fallback(
    person_id=1,
    day_index=0,
    team_size=10,
    random_gen=rng
)

if should_send:
    # Generate and send fallback communication
    pass
```

### Monitoring Participation

```python
# Get statistics for a day
summary = balancer.get_stats_summary(day_index=0)

print(f"Total messages: {summary['total_messages']}")
print(f"Top 2 percentage: {summary['top_2_percentage']:.1f}%")
print(f"Gini coefficient: {summary['gini_coefficient']:.3f}")

# Log daily summary
balancer.log_daily_summary(day_index=0)
```

### Disabling Balancing

```python
# Disable balancing (all personas always generate)
balancer = ParticipationBalancer(enabled=False)

# This will always return True
should_send = balancer.should_generate_fallback(1, 0, 10, rng)
assert should_send == True
```

## Throttling and Boosting Logic

### Probability Calculation

The balancer calculates a probability modifier based on the persona's message count relative to the team average:

1. **Calculate team average**: Sum all messages for the day / team size
2. **Calculate ratio**: Persona's count / team average
3. **Apply modifier**:
   - If ratio > 2.0: probability = 0.3 (throttle)
   - If ratio < 0.5: probability = 0.9 (boost)
   - Otherwise: probability = 0.6 (normal)

### Example Scenarios

**High Volume Sender (Throttled)**:
```
Person 1: 20 messages
Team average: 6.5 messages
Ratio: 20 / 6.5 = 3.08 > 2.0
Probability: 0.3 (70% reduction)
```

**Low Volume Sender (Boosted)**:
```
Person 2: 1 message
Team average: 9.1 messages
Ratio: 1 / 9.1 = 0.11 < 0.5
Probability: 0.9 (50% increase from base 0.6)
```

**Normal Volume Sender**:
```
Person 3: 5 messages
Team average: 5.0 messages
Ratio: 5 / 5 = 1.0 (within 0.5 to 2.0)
Probability: 0.6 (baseline)
```

## Statistics and Metrics

### Gini Coefficient

The balancer calculates the Gini coefficient to measure inequality in message distribution:

- **0.0**: Perfect equality (everyone sends same amount)
- **1.0**: Perfect inequality (one person sends everything)
- **Target**: < 0.4 for realistic team collaboration

### Top 2 Percentage

Tracks the percentage of messages sent by the top 2 most active personas:

- **Current baseline**: 65% (problematic)
- **Target**: ≤ 40% (realistic)
- **Calculation**: (top_2_count / total_messages) * 100

## Integration with Engine

The ParticipationBalancer integrates with the simulation engine's fallback communication generation:

```python
# In engine.py
class SimulationEngine:
    def __init__(self, ...):
        self.participation_balancer = ParticipationBalancer(
            enabled=config.get('VDOS_PARTICIPATION_BALANCE_ENABLED', True)
        )
    
    def _generate_fallback_communication(self, person, tick, day_index):
        # Check if persona should send fallback
        if not self.participation_balancer.should_generate_fallback(
            person_id=person.id,
            day_index=day_index,
            team_size=len(self.team),
            random_gen=self._random
        ):
            return  # Skip fallback generation
        
        # Generate fallback communication
        communication = self._create_fallback_message(person)
        
        # Record the message
        channel = 'email' if communication['type'] == 'email' else 'chat'
        self.participation_balancer.record_message(
            person_id=person.id,
            day_index=day_index,
            channel=channel
        )
```

## Configuration

### Environment Variables

```bash
# Enable/disable participation balancing
VDOS_PARTICIPATION_BALANCE_ENABLED=true  # default: true

# Fallback generation probability (when balancing disabled)
VDOS_FALLBACK_PROBABILITY=0.6  # default: 0.6
```

### Runtime Configuration

```python
# Enable balancing
balancer = ParticipationBalancer(enabled=True)

# Disable balancing (all personas always generate)
balancer = ParticipationBalancer(enabled=False)
```

## Logging

The balancer provides comprehensive logging for monitoring and debugging:

### DEBUG Level
```
Recorded email message for person_id=1, day_index=0: email=2, chat=1, total=3
Throttling person_id=1 on day_index=0: count=20, team_avg=6.5, ratio=3.08, probability=0.3
Boosting person_id=2 on day_index=0: count=1, team_avg=9.1, ratio=0.11, probability=0.9
```

### INFO Level
```
ParticipationBalancer initialized (enabled=True)
Participation balancing prevented fallback generation for person_id=1, day_index=0 (probability=0.30)
Participation summary for day 0: total=150, top_2=38.7%, gini=0.285, enabled=True
Top senders on day 0: person_1=25, person_2=23, person_3=18, person_4=15, person_5=14
```

### WARNING Level
```
Unknown channel 'unknown' for person_id=1, day_index=0
```

## Testing

Comprehensive unit tests cover all functionality:

- **Initialization**: Enabled/disabled states
- **Message Counting**: Email, chat, multiple messages, different personas/days
- **Team Average**: Various scenarios including edge cases
- **Throttling/Boosting**: High/low/normal volume senders
- **Determinism**: Same seed produces same results
- **Statistics**: Summary, Gini coefficient, top 2 percentage
- **Integration**: Full day and multi-day simulations

Run tests:
```bash
python -m pytest tests/test_participation_balancer.py -v
```

## Performance Characteristics

- **Memory**: O(P × D) where P = personas, D = days (~6.5 KB for 13 personas × 5 days)
- **Time Complexity**:
  - `record_message()`: O(1)
  - `get_send_probability()`: O(P) for team average calculation
  - `should_generate_fallback()`: O(P)
  - `get_stats_summary()`: O(P)
- **Overhead**: <1ms per message for typical team sizes (10-20 personas)

## Future Enhancements

1. **Database Persistence**: Store participation stats in database for analysis
2. **Adaptive Thresholds**: Adjust throttling/boosting based on team dynamics
3. **Channel-Specific Balancing**: Separate balancing for email vs chat
4. **Time-Based Balancing**: Consider time of day patterns
5. **Role-Based Balancing**: Different expectations for different roles

## Related Modules

- **CommunicationGenerator**: Generates fallback communications (uses ParticipationBalancer)
- **InboxManager**: Tracks received messages (complements ParticipationBalancer)
- **SimulationEngine**: Orchestrates simulation (integrates ParticipationBalancer)

## References

- Requirements: `.kiro/specs/communication-diversity/requirements.md`
- Design: `.kiro/specs/communication-diversity/design.md`
- Tasks: `.kiro/specs/communication-diversity/tasks.md`
- Tests: `tests/test_participation_balancer.py`
