# Plan Parser Module Documentation

## Overview

The Plan Parser module (`src/virtualoffice/sim_manager/plan_parser.py`) provides AI-powered conversion of natural language hourly plans into structured JSON for scheduling. This creates a clean separation between planning (creative, natural language) and parsing (structured, validated).

**Status**: Implemented (November 2025)

## Architecture

### Design Philosophy

The Plan Parser implements a **two-stage planning architecture**:

1. **Stage 1 - Planning (Creative)**: LLM generates natural language hourly plans with enforced time formatting
2. **Stage 2 - Parsing (Structured)**: Dedicated parser agent extracts structured data from natural language

**Format Enforcement** (November 2025):
The planner now enforces strict time formatting rules to ensure reliable parsing:
- All tasks must start with `HH:MM - Task description` format
- This eliminates ambiguous time references like "morning" or "after lunch"
- Ensures Plan Parser can accurately extract task timing
- Improves scheduling reliability and reduces parsing failures

```
┌─────────────────┐
│  LLM generates  │
│  natural plan   │
│  (Korean text)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Plan Parser    │
│  Agent (GPT)    │
│  Extracts JSON  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Validated JSON │
│  with schema    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Scheduler      │
│  (_schedule_    │
│   from_json)    │
└─────────────────┘
```

### Benefits

**Better Plan Quality**:
- LLM writes naturally without JSON syntax constraints
- More realistic, human-like planning
- No JSON syntax errors in plans

**Separation of Concerns**:
- **Planning**: Focus on what to do and when
- **Parsing**: Extract structured data
- **Scheduling**: Execute the plan

**Error Recovery**:
- If parsing fails, can retry just the parser
- Original plan is preserved
- Can fall back to regex parser

**Easier Validation**:
- JSON schema validation in one place
- Can fix common parsing errors automatically
- Better error messages

## Integration with Simulation Engine

The Plan Parser integrates with the Simulation Engine through the `_schedule_from_json()` method, which processes parsed JSON plans and schedules communications for execution at specific simulation ticks.

### Workflow

1. **Planning**: LLM generates natural language hourly plan
2. **Parsing**: `PlanParser.parse_plan()` extracts structured JSON
3. **Scheduling**: `SimulationEngine._schedule_from_json()` schedules communications
4. **Execution**: Communications sent at scheduled ticks during simulation

### Engine Integration Point

**File**: `src/virtualoffice/sim_manager/engine.py`

```python
def _schedule_from_json(
    self,
    person: PersonRead,
    parsed_json: dict[str, Any],
    current_tick: int
) -> None:
    """
    Schedule communications from parsed JSON plan.
    
    Processes the 'communications' array from parsed JSON and schedules
    each communication for execution at the specified time.
    
    Args:
        person: Worker persona who created the plan
        parsed_json: Structured plan with tasks and communications
        current_tick: Current simulation tick
        
    Features:
        - Converts HH:MM time format to simulation ticks
        - Supports email, email_reply, and chat communication types
        - Handles CC/BCC for emails
        - Tracks email threading via reply_to field
        - Logs scheduling success/failure for observability
        - Tracks source as 'json_plan' for metrics
    """
```

**Communication Types Supported**:
- `email`: New email with to/cc/bcc/subject/body
- `email_reply`: Reply to existing email with thread_id from reply_to field
- `chat`: Direct message or room message

**Scheduling Logic**:
- Time strings (HH:MM) converted to tick numbers: `tick = (hour * 60) + minute`
- Communications stored in `self._scheduled_comms[person_id][tick]`
- Each action includes `_source: 'json_plan'` for tracking
- Invalid times or unknown types logged as warnings

## Core Classes

### `PlanParser`

Main class for converting natural language plans into structured JSON.

```python
class PlanParser:
    """
    Converts natural language hourly plans into structured JSON.
    
    Uses GPT to extract:
    - Tasks with start times and durations
    - Scheduled communications (emails and chats)
    - Breaks and meetings
    """
    
    def __init__(self, model: str | None = None):
        """
        Initialize the plan parser.
        
        Args:
            model: GPT model to use (default: gpt-4o-mini)
        """
```

**Key Methods**:

#### `parse_plan()`

```python
def parse_plan(
    self,
    plan_text: str,
    worker_name: str,
    work_hours: str,
    team_emails: list[str],
    team_handles: list[str],
    project_name: str | None = None
) -> dict[str, Any]:
    """
    Parse natural language plan into structured JSON.
    
    Args:
        plan_text: Natural language hourly plan
        worker_name: Name of the worker
        work_hours: Work hours (e.g., "09:00-18:00")
        team_emails: Valid email addresses
        team_handles: Valid chat handles
        project_name: Current project name
        
    Returns:
        Structured plan with tasks and communications
        
    Raises:
        ParsingError: If parsing fails
    """
```

**Process**:
1. Build system and user prompts with context
2. Call GPT-4o-mini with low temperature (0.1) for consistency
3. Extract JSON from response (handles markdown code blocks)
4. Validate against JSON schema
5. Fix common errors (invalid emails, handles)
6. Return validated JSON

#### `parse_plans_batch()` / `parse_plans_batch_async()`

**Added**: November 6, 2025

```python
def parse_plans_batch(
    self,
    parse_requests: list[dict[str, Any]]
) -> list[tuple[str, dict[str, Any] | None]]:
    """
    Parse multiple plans in parallel using async.
    
    Args:
        parse_requests: List of dicts with keys:
            - plan_text: str
            - worker_name: str
            - work_hours: str
            - team_emails: list[str]
            - team_handles: list[str]
            - project_name: str | None
    
    Returns:
        List of (worker_name, parsed_json or None) tuples
    """

async def parse_plans_batch_async(
    self,
    parse_requests: list[dict[str, Any]]
) -> list[tuple[str, dict[str, Any] | None]]:
    """
    Async version for use in async contexts.
    """
```

**Batch Parsing Features**:
- **Parallel Processing**: Parses multiple plans concurrently using `asyncio.gather()`
- **Performance**: Significantly faster than sequential parsing for multiple workers
- **Error Handling**: Failed parses return `(worker_name, None)` without stopping batch
- **Async Support**: Both sync wrapper and native async methods available
- **Use Case**: Multi-worker simulations where all personas plan simultaneously

**Example Usage**:
```python
# Prepare batch requests
requests = [
    {
        'plan_text': plan1,
        'worker_name': 'Alice',
        'work_hours': '09:00-18:00',
        'team_emails': team_emails,
        'team_handles': team_handles,
        'project_name': 'Project Alpha'
    },
    {
        'plan_text': plan2,
        'worker_name': 'Bob',
        'work_hours': '09:00-18:00',
        'team_emails': team_emails,
        'team_handles': team_handles,
        'project_name': 'Project Alpha'
    }
]

# Parse in parallel
results = parser.parse_plans_batch(requests)

# Process results
for worker_name, parsed_json in results:
    if parsed_json:
        # Schedule communications
        engine._schedule_from_json(person, parsed_json, tick)
    else:
        # Fall back to regex parser
        logger.warning(f"Batch parsing failed for {worker_name}")
```

**Performance Benefits**:
- **Sequential**: 4 workers × 1.5s = 6 seconds
- **Batch**: ~1.5-2 seconds total (75% faster)
- **Scalability**: Benefits increase with more workers

## Performance Optimization

### Batch Parsing Strategy

**When to Use Batch Parsing**:
- ✅ Multi-worker simulations (3+ personas)
- ✅ Hourly planning cycles where all workers plan simultaneously
- ✅ Performance-critical scenarios
- ❌ Single worker simulations (no benefit)
- ❌ Sequential planning workflows

**Implementation Pattern**:

```python
# Sequential (legacy approach)
for person in people:
    plan = generate_hourly_plan(person, ...)
    parsed = parser.parse_plan(plan.content, ...)
    schedule_from_json(person, parsed, tick)
# Total: N × 1.5s

# Batch (optimized approach)
plans = [generate_hourly_plan(p, ...) for p in people]
requests = [build_parse_request(p, plan) for p, plan in zip(people, plans)]
results = parser.parse_plans_batch(requests)
for (name, parsed), person in zip(results, people):
    if parsed:
        schedule_from_json(person, parsed, tick)
# Total: ~1.5-2s regardless of N
```

**Performance Metrics**:

| Workers | Sequential | Batch | Improvement |
|---------|-----------|-------|-------------|
| 4       | 6.0s      | 1.5s  | 75%         |
| 8       | 12.0s     | 2.0s  | 83%         |
| 12      | 18.0s     | 2.5s  | 86%         |
| 20      | 30.0s     | 3.0s  | 90%         |

**Cost Considerations**:
- Token usage identical (same prompts)
- API costs identical (same number of calls)
- Only wall-clock time improves
- No additional OpenAI charges

### `ParsingError`

Exception raised when plan parsing fails.

```python
class ParsingError(Exception):
    """Raised when plan parsing fails."""
    pass
```

## JSON Schema

The parser validates against a comprehensive JSON schema:

```json
{
  "type": "object",
  "properties": {
    "tasks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "time": {"type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$"},
          "duration_minutes": {"type": "integer", "minimum": 1},
          "description": {"type": "string"},
          "type": {"type": "string", "enum": ["work", "break", "meeting"]}
        },
        "required": ["time", "description"]
      }
    },
    "communications": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "time": {"type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$"},
          "type": {"type": "string", "enum": ["email", "chat", "email_reply"]},
          "to": {"type": "string"},
          "cc": {"type": "array", "items": {"type": "string"}},
          "bcc": {"type": "array", "items": {"type": "string"}},
          "subject": {"type": "string"},
          "body": {"type": "string"},
          "message": {"type": "string"},
          "reply_to": {"type": "string"}
        },
        "required": ["time", "type"]
      }
    }
  },
  "required": ["communications"]
}
```

### Schema Features

**Tasks**:
- Time in HH:MM format (validated with regex)
- Optional duration in minutes
- Description (required)
- Type: work, break, or meeting

**Communications**:
- Time in HH:MM format (validated with regex)
- Type: email, chat, or email_reply
- Email-specific: to, cc, bcc, subject, body
- Chat-specific: to, message
- Reply-specific: reply_to (original email ID)

## Prompt System

### System Prompt (Korean)

```python
"""당신은 자연어로 작성된 업무 계획을 구조화된 JSON으로 변환하는 전문가입니다.

주어진 계획에서 다음을 추출하세요:
1. 작업 목록 (시작 시간, 소요 시간, 설명)
2. 예정된 커뮤니케이