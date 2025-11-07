# Planner Module Documentation

## Overview

The Planner module (`src/virtualoffice/sim_manager/planner.py`) provides AI-powered planning capabilities for the VDOS simulation engine. It generates project plans, daily plans, hourly plans, and reports using GPT models, with fallback to deterministic stub planners when AI is unavailable.

**Status**: Production-ready (November 2025)

## Architecture

### Design Philosophy

The Planner implements a **protocol-based architecture** with multiple implementations:

1. **GPTPlanner**: AI-powered planning using OpenAI GPT models
2. **StubPlanner**: Deterministic fallback for testing and offline operation
3. **Planner Protocol**: Interface defining all planning methods

```
┌─────────────────────────────────────────┐
│         Planner Protocol                │
│  (Interface for all planning methods)   │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌──────▼──────┐
│ GPTPlanner  │  │ StubPlanner │
│ (AI-powered)│  │ (Fallback)  │
└─────────────┘  └─────────────┘
```

### Planning Hierarchy

The planner supports multiple levels of planning granularity:

1. **Project Planning**: Week-by-week roadmap with milestones
2. **Daily Planning**: Day-level objectives and focus areas
3. **Hourly Planning**: Minute-by-minute task scheduling with communications
4. **Hourly Summary**: Concise activity summaries for aggregation
5. **Daily Reports**: End-of-day summaries with achievements and blockers
6. **Simulation Reports**: Executive summaries of entire simulation runs

## Core Classes

### `Planner` Protocol

Defines the interface that all planner implementations must follow.

```python
class Planner(Protocol):
    """Protocol defining all planning methods."""
    
    def generate_project_plan(...) -> PlanResult: ...
    def generate_daily_plan(...) -> PlanResult: ...
    def generate_hourly_plan(...) -> PlanResult: ...
    def generate_hourly_summary(...) -> PlanResult: ...
    def generate_daily_report(...) -> PlanResult: ...
    def generate_simulation_report(...) -> PlanResult: ...
    def generate_with_messages(...) -> PlanResult: ...
```

### `PlanResult`

Data class containing the result of a planning operation.

```python
@dataclass
class PlanResult:
    content: str                    # Generated plan text
    model_used: str                 # Model identifier
    tokens_used: int | None = None  # Token count (None for stub)
```

### `PlanningError`

Exception raised when AI-powered planning fails.

```python
class PlanningError(RuntimeError):
    """Raised when an LLM-backed planning attempt fails."""
```

## GPTPlanner

AI-powered planner using OpenAI GPT models.

### Initialization

```python
class GPTPlanner:
    def __init__(
        self,
        generator: PlanGenerator | None = None,
        project_model: str = DEFAULT_PROJECT_MODEL,
        daily_model: str = DEFAULT_DAILY_MODEL,
        hourly_model: str = DEFAULT_HOURLY_MODEL,
        daily_report_model: str | None = DEFAULT_DAILY_REPORT_MODEL,
        simulation_report_model: str | None = DEFAULT_SIMULATION_REPORT_MODEL,
        use_template_prompts: bool = False,
        hours_per_day: int = 8,
    ) -> None:
        """
        Initialize GPT-powered planner.
        
        Args:
            generator: Custom text generation function (optional)
            project_model: Model for project planning
            daily_model: Model for daily planning
            hourly_model: Model for hourly planning
            daily_report_model: Model for daily reports
            simulation_report_model: Model for simulation reports
            use_template_prompts: Use template-based prompts (experimental)
            hours_per_day: Working hours per day
        """
```

**Configuration via Environment Variables**:
- `VDOS_PLANNER_PROJECT_MODEL` (default: `gpt-4o-mini`)
- `VDOS_PLANNER_DAILY_MODEL` (default: same as project)
- `VDOS_PLANNER_HOURLY_MODEL` (default: same as daily)
- `VDOS_PLANNER_DAILY_REPORT_MODEL` (default: same as daily)
- `VDOS_PLANNER_SIM_REPORT_MODEL` (default: same as project)
- `VDOS_LOCALE` (default: `en`, supports `ko` for Korean)
- `VDOS_USE_TEMPLATE_PROMPTS` (default: `false`, experimental feature)

### Planning Methods

#### `generate_project_plan()`

Generates a week-by-week project roadmap with milestones and risk mitigations.

```python
def generate_project_plan(
    self,
    *,
    department_head: PersonRead,
    project_name: str,
    project_summary: str,
    duration_weeks: int,
    team: Sequence[PersonRead],
    model_hint: str | None = None,
) -> PlanResult:
    """
    Generate project plan with milestones and team assignments.
    
    Args:
        department_head: Project lead persona
        project_name: Name of the project
        project_summary: Brief project description
        duration_weeks: Project duration in weeks
        team: List of team member personas
        model_hint: Optional model override
        
    Returns:
        PlanResult with project plan content
    """
```

**Output Format**:
- Week-by-week breakdown
- Milestones with owners
- Risk mitigations
- Buffer time allocations
- Team coordination points

#### `generate_daily_plan()`

Generates day-level objectives and focus areas.

```python
def generate_daily_plan(
    self,
    *,
    worker: PersonRead,
    project_plan: str | dict[str, Any],
    day_index: int,
    duration_weeks: int,
    team: Sequence[PersonRead] | None = None,
    model_hint: str | None = None,
) -> PlanResult:
    """
    Generate daily plan with objectives and communication strategy.
    
    Args:
        worker: Worker persona
        project_plan: Project plan text or dict with 'plan' and 'project_name'
        day_index: Day number (0-indexed)
        duration_weeks: Total project duration
        team: Team member personas
        model_hint: Optional model override
        
    Returns:
        PlanResult with daily plan content
        
    Features:
        - Supports dict project_plan with project_name extraction
        - Uses persona markdown for authentic planning
        - Template-based prompts (if enabled)
        - Korean localization support
    """
```

**Key Features**:
- Extracts project name from dict or uses default
- Incorporates persona markdown for authentic voice
- Includes team roster with contact information
- Template-based prompts (experimental)
- Fallback to hard-coded prompts on error

#### `generate_hourly_plan()`

Generates minute-by-minute task scheduling with scheduled communications.

```python
def generate_hourly_plan(
    self,
    *,
    worker: PersonRead,
    project_plan: str | dict[str, Any],
    daily_plan: str,
    tick: int,
    context_reason: str,
    team: Sequence[PersonRead] | None = None,
    model_hint: str | None = None,
    all_active_projects: list[dict[str, Any]] | None = None,
    recent_emails: list[dict[str, Any]] | None = None,
) -> PlanResult:
    """
    Generate hourly plan with tasks and scheduled communications.
    
    Args:
        worker: Worker persona
        project_plan: Project plan text or dict
        daily_plan: Daily plan text
        tick: Current simulation tick
        context_reason: Reason for planning (e.g., "start of hour")
        team: Team member personas
        model_hint: Optional model override
        all_active_projects: List of concurrent projects (multi-project support)
        recent_emails: Recent emails for threading context (NEW)
        
    Returns:
        PlanResult with hourly plan content
        
    Features:
        - Enforces HH:MM time format for all tasks
        - Includes "Scheduled Communications" section
        - Supports email threading via recent_emails
        - Multi-project context awareness
        - Strict email address validation
        - Template-based prompts (if enabled)
        - Korean localization with comprehensive guidelines
    """
```

**Recent Enhancements** (November 2025):

1. **Email Threading Context** (`recent_emails` parameter):
   - Provides last 5 received emails for context
   - Enables realistic email reply generation
   - Format: `[{email_id, from, subject}, ...]`
   - Used in prompt to show recent conversations

2. **Multi-Project Support** (`all_active_projects` parameter):
   - Handles concurrent project work
   - Prompts for project tags in communications
   - Example: `[Mobile App] API status update`

3. **Strict Time Formatting**:
   - All tasks must start with `HH:MM - Description`
   - Eliminates ambiguous time references
   - Improves Plan Parser reliability

4. **Email Address Validation**:
   - Explicit team roster with email mappings
   - Prevents hallucinated email addresses
   - Korean name to email mapping support

**Output Format**:
```
09:00 - Review priorities and blockers
09:30 - API development work
10:30 - Code review session
...

Scheduled Communications:
- Email at 10:30 to dev@company.kr cc pm@company.kr: Sprint update | Auth module complete
- Chat at 11:00 with designer_handle: Quick question about API endpoints
- Reply at 14:00 to [email-42] cc lead@company.kr: RE: API status | Thanks for update
```

#### `generate_hourly_summary()`

Generates concise summaries of hourly activities for aggregation.

```python
def generate_hourly_summary(
    self,
    *,
    worker: PersonRead,
    hour_index: int,
    hourly_plans: str,
    model_hint: str | None = None,
) -> PlanResult:
    """
    Generate concise hourly activity summary.
    
    Args:
        worker: Worker persona
        hour_index: Hour number (0-indexed)
        hourly_plans: Hourly plan text
        model_hint: Optional model override
        
    Returns:
        PlanResult with 2-3 bullet point summary
        
    Purpose:
        - Aggregates into daily reports
        - Tracks key tasks and communications
        - Identifies blockers and decisions
    """
```

#### `generate_daily_report()`

Generates end-of-day summaries with achievements and blockers.

```python
def generate_daily_report(
    self,
    *,
    worker: PersonRead,
    project_plan: str,
    day_index: int,
    daily_plan: str,
    hourly_log: str,
    minute_schedule: str,
    model_hint: str | None = None,
) -> PlanResult:
    """
    Generate daily report with highlights and risks.
    
    Args:
        worker: Worker persona
        project_plan: Project plan text
        day_index: Day number (0-indexed)
        daily_plan: Daily plan text
        hourly_log: Aggregated hourly activities
        minute_schedule: Detailed minute-by-minute log
        model_hint: Optional model override
        
    Returns:
        PlanResult with daily report content
        
    Features:
        - Uses persona markdown for authentic voice
        - Template-based prompts (if enabled)
        - Korean localization support
    """
```

#### `generate_simulation_report()`

Generates executive summaries of entire simulation runs.

```python
def generate_simulation_report(
    self,
    *,
    project_plan: str,
    team: Sequence[PersonRead],
    total_ticks: int,
    tick_log: str,
    daily_reports: str,
    event_summary: str,
    model_hint: str | None = None,
) -> PlanResult:
    """
    Generate simulation retrospective report.
    
    Args:
        project_plan: Project plan text
        team: All team member personas
        total_ticks: Total simulation ticks
        tick_log: Tick-by-tick activity log
        daily_reports: Aggregated daily reports
        event_summary: Summary of injected events
        model_hint: Optional model override
        
    Returns:
        PlanResult with executive summary
        
    Purpose:
        - Cross-team coordination analysis
        - Risk and blocker identification
        - Readiness assessment for next cycle
    """
```

#### `generate_with_messages()` ✨ NEW

Generates plans using externally constructed prompts.

```python
def generate_with_messages(
    self,
    *,
    messages: list[dict[str, str]],
    model_hint: str | None = None,
) -> PlanResult:
    """
    Generate plan using pre-built message list.
    
    This method allows using externally constructed prompts
    (e.g., from PromptManager) instead of the built-in prompt logic.
    
    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_hint: Optional model override
        
    Returns:
        PlanResult with generated content
        
    Use Cases:
        - Template-based prompt systems
        - Custom prompt engineering
        - A/B testing different prompts
        - Integration with PromptManager
    """
```

**Example Usage**:
```python
# Build messages externally
messages = [
    {"role": "system", "content": "You are a project planner..."},
    {"role": "user", "content": "Create a plan for..."}
]

# Generate using pre-built messages
result = planner.generate_with_messages(
    messages=messages,
    model_hint="gpt-4o"
)
```

### Korean Localization

When `VDOS_LOCALE=ko`, the planner applies comprehensive Korean language instructions:

**Features**:
- Natural Korean business language
- Korean-specific communication patterns
- Localized terminology and examples
- Korean validation with retry logic

**Validation and Retry**:
```python
def _validate_and_retry_korean_content(
    self, 
    messages: list[dict[str, str]], 
    model: str, 
    content: str, 
    tokens: int
) -> tuple[str, int]:
    """
    Validate Korean content and retry if English detected.
    
    - Checks for English text in generated content
    - Retries with enhanced Korean prompts
    - Configurable retry count via VDOS_KOREAN_VALIDATION_RETRIES
    - Default: 0 retries (accepts mixed content for speed)
    """
```

**Configuration**:
- `VDOS_KOREAN_VALIDATION_RETRIES` (default: `0`)
  - Set to `0` to disable validation (faster, accepts mixed Korean/English)
  - Set to `1-3` for strict Korean-only output (slower, more API calls)

## StubPlanner

Deterministic fallback planner for testing and offline operation.

### Purpose

- **Testing**: Reproducible output for test assertions
- **Offline Operation**: Works without OpenAI API
- **Development**: Fast iteration without API costs
- **Fallback**: Graceful degradation when GPT fails

### Implementation

```python
class StubPlanner:
    """Fallback planner with deterministic output."""
    
    def generate_project_plan(...) -> PlanResult:
        # Returns simple, deterministic project plan
        
    def generate_daily_plan(...) -> PlanResult:
        # Returns Korean-language daily plan
        
    def generate_hourly_plan(...) -> PlanResult:
        # Returns realistic hourly plan with scheduled comms
        
    # ... other methods
```

**Key Features**:
- Zero token usage
- Deterministic output
- Korean language support
- Realistic communication examples
- Model identifier: `vdos-stub-{type}`

## Integration with Simulation Engine

### Engine Integration

The planner integrates with the simulation engine through the `_call_planner()` method:

```python
def _call_planner(
    self,
    method_name: str,
    **kwargs
) -> PlanResult:
    """
    Call planner method with fallback handling.
    
    Args:
        method_name: Name of planner method to call
        **kwargs: Arguments to pass to planner method
        
    Returns:
        PlanResult from planner
        
    Features:
        - Automatic fallback to StubPlanner on error
        - Metrics tracking (success/failure/duration)
        - Configurable strict mode (VDOS_PLANNER_STRICT=1)
    """
```

### Workflow

```
┌──────────────┐
│   Engine     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│_call_planner │
└──────┬───────┘
       │
       ├─────────────┐
       │             │
       ▼             ▼
┌──────────┐   ┌──────────┐
│GPTPlanner│   │StubPlanner│
│ (try)    │   │(fallback) │
└──────────┘   └──────────┘
```

### Parallel Planning

The engine supports parallel hourly planning for multiple workers:

```python
def _generate_hourly_plans_parallel(
    self,
    planning_tasks: list[tuple[PersonRead, str, str]],
    team: list[PersonRead]
) -> dict[int, PlanResult]:
    """
    Generate hourly plans in parallel using ThreadPoolExecutor.
    
    Args:
        planning_tasks: List of (person, project_plan, daily_plan) tuples
        team: All team members for context
        
    Returns:
        Dict mapping person_id to PlanResult
        
    Performance:
        - Concurrent API calls reduce wall-clock time
        - Configurable worker count via VDOS_MAX_PLANNING_WORKERS
        - Default: 4 concurrent workers
    """
```

**Configuration**:
- `VDOS_MAX_PLANNING_WORKERS` (default: `4`)
- Higher values = more concurrent API calls
- Limited by OpenAI rate limits

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VDOS_PLANNER_PROJECT_MODEL` | `gpt-4o-mini` | Model for project planning |
| `VDOS_PLANNER_DAILY_MODEL` | (same as project) | Model for daily planning |
| `VDOS_PLANNER_HOURLY_MODEL` | (same as daily) | Model for hourly planning |
| `VDOS_PLANNER_DAILY_REPORT_MODEL` | (same as daily) | Model for daily reports |
| `VDOS_PLANNER_SIM_REPORT_MODEL` | (same as project) | Model for simulation reports |
| `VDOS_PLANNER_STRICT` | `0` | Disable stub fallback (1=strict) |
| `VDOS_LOCALE` | `en` | Locale (en or ko) |
| `VDOS_USE_TEMPLATE_PROMPTS` | `false` | Use template-based prompts |
| `VDOS_KOREAN_VALIDATION_RETRIES` | `0` | Korean validation retry count |
| `VDOS_MAX_PLANNING_WORKERS` | `4` | Parallel planning workers |
| `OPENAI_API_KEY` | (required) | OpenAI API key |

### Model Selection

**Recommended Models**:
- **gpt-4o-mini**: Cost-effective, fast, good quality (default)
- **gpt-4o**: Higher quality, more expensive
- **gpt-3.5-turbo**: Fastest, lowest cost, lower quality

**Cost Considerations**:
- Hourly planning is most frequent (every hour per worker)
- Daily planning once per day per worker
- Project planning once per project
- Reports at end of day/simulation

**Example Configuration**:
```bash
# Balanced: Fast hourly, quality reports
VDOS_PLANNER_HOURLY_MODEL=gpt-4o-mini
VDOS_PLANNER_DAILY_REPORT_MODEL=gpt-4o
VDOS_PLANNER_SIM_REPORT_MODEL=gpt-4o

# Cost-optimized: All mini
VDOS_PLANNER_PROJECT_MODEL=gpt-4o-mini
VDOS_PLANNER_DAILY_MODEL=gpt-4o-mini
VDOS_PLANNER_HOURLY_MODEL=gpt-4o-mini

# Quality-optimized: All gpt-4o
VDOS_PLANNER_PROJECT_MODEL=gpt-4o
VDOS_PLANNER_DAILY_MODEL=gpt-4o
VDOS_PLANNER_HOURLY_MODEL=gpt-4o
```

## Error Handling

### Fallback Strategy

When `GPTPlanner` fails:

1. **Log Error**: Record error message and duration
2. **Check Strict Mode**: If `VDOS_PLANNER_STRICT=1`, raise `RuntimeError`
3. **Fallback**: Use `StubPlanner` for deterministic output
4. **Record Metrics**: Track fallback in `_planner_metrics`

```python
try:
    result = self.gpt_planner.generate_hourly_plan(...)
except Exception as e:
    logger.error(f"GPT planning failed: {e}")
    if strict_mode:
        raise RuntimeError("Planning failed in strict mode")
    result = self.stub_planner.generate_hourly_plan(...)
    self._planner_metrics['fallbacks'] += 1
```

### Common Errors

**API Key Missing**:
```
RuntimeError: OpenAI client is not installed; install optional dependencies
```
**Solution**: Set `OPENAI_API_KEY` environment variable

**Rate Limit Exceeded**:
```
PlanningError: Rate limit exceeded
```
**Solution**: Reduce `VDOS_MAX_PLANNING_WORKERS` or add delays

**Invalid Model**:
```
PlanningError: Model 'gpt-5' not found
```
**Solution**: Use valid model name (gpt-4o, gpt-4o-mini, etc.)

## Performance Optimization

### Parallel Planning

**Sequential Planning** (legacy):
```python
for person in people:
    plan = planner.generate_hourly_plan(person, ...)
# Total: N × 1.5s
```

**Parallel Planning** (optimized):
```python
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [
        executor.submit(planner.generate_hourly_plan, person, ...)
        for person in people
    ]
    results = [f.result() for f in futures]
# Total: ~1.5-2s regardless of N
```

**Performance Metrics**:

| Workers | Sequential | Parallel (4 threads) | Improvement |
|---------|-----------|---------------------|-------------|
| 4       | 6.0s      | 1.5s                | 75%         |
| 8       | 12.0s     | 3.0s                | 75%         |
| 12      | 18.0s     | 4.5s                | 75%         |

### Token Optimization

**Strategies**:
1. **Use gpt-4o-mini** for frequent operations (hourly planning)
2. **Limit context size**: Only include relevant team members
3. **Truncate logs**: Don't pass entire simulation history
4. **Cache project plans**: Reuse across daily/hourly planning

**Token Usage Estimates**:
- Project plan: ~1000-1500 tokens
- Daily plan: ~500-800 tokens
- Hourly plan: ~800-1200 tokens
- Daily report: ~600-1000 tokens

## Testing

### Unit Tests

```python
def test_gpt_planner_hourly_plan():
    """Test GPT planner generates valid hourly plan."""
    planner = GPTPlanner()
    
    result = planner.generate_hourly_plan(
        worker=test_worker,
        project_plan="Test project...",
        daily_plan="Test daily plan...",
        tick=540,  # 09:00
        context_reason="start of hour",
        team=[test_teammate],
    )
    
    assert result.content
    assert result.model_used == "gpt-4o-mini"
    assert result.tokens_used > 0
    assert "Scheduled Communications" in result.content or "예정된 커뮤니케이션" in result.content
```

### Integration Tests

```python
def test_planner_fallback():
    """Test fallback to stub planner on error."""
    # Mock GPT planner to fail
    mock_planner = Mock(side_effect=PlanningError("API error"))
    
    engine = SimulationEngine(planner=mock_planner)
    
    # Should fall back to stub planner
    result = engine._call_planner("generate_hourly_plan", ...)
    
    assert result.model_used.startswith("vdos-stub")
    assert engine._planner_metrics['fallbacks'] == 1
```

## Related Documentation

- [Plan Parser Module](./plan_parser.md) - Converts natural language plans to JSON
- [Architecture Documentation](../architecture.md) - Overall system architecture
- [Prompt System](./prompts.md) - Template-based prompt management (experimental)
- [Communication Generator](./communication_generator.md) - Fallback communication generation

## Changelog

### November 2025

**Enhancements**:
- ✅ Added `generate_with_messages()` for external prompt construction
- ✅ Added `recent_emails` parameter to `generate_hourly_plan()` for threading
- ✅ Added multi-project support via `all_active_projects` parameter
- ✅ Enforced strict HH:MM time formatting in hourly plans
- ✅ Enhanced email address validation with explicit team roster
- ✅ Korean name to email mapping support
- ✅ Template-based prompt system (experimental)
- ✅ Korean validation with configurable retry logic

**Performance**:
- ✅ Parallel planning support via ThreadPoolExecutor
- ✅ Configurable worker count (`VDOS_MAX_PLANNING_WORKERS`)
- ✅ Token usage optimization

**Localization**:
- ✅ Comprehensive Korean language support
- ✅ Korean validation and retry mechanism
- ✅ Localized communication examples

## Future Enhancements

**Planned Features**:
1. **Prompt Caching**: Cache frequently used prompts to reduce tokens
2. **Streaming Responses**: Stream plan generation for faster perceived performance
3. **Plan Templates**: Pre-defined plan templates for common scenarios
4. **Multi-Model Support**: Support for Anthropic Claude, Google Gemini
5. **Plan Validation**: Validate plans against project constraints
6. **Learning from Feedback**: Improve plans based on simulation outcomes

**Under Consideration**:
- Fine-tuned models for specific planning tasks
- Plan quality scoring and automatic improvement
- Integration with external project management tools
- Real-time plan adjustment based on simulation events
