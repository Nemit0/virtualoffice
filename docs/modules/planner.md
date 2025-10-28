# Planner Module Documentation

## Overview

The planner module (`src/virtualoffice/sim_manager/planner.py`) provides AI-powered and stub planning capabilities for the VDOS simulation engine. It generates project plans, daily plans, hourly plans, and reports using GPT-4o integration with fallback to deterministic stub implementations.

## Architecture

### Core Classes

#### `PlanResult`
```python
@dataclass
class PlanResult:
    content: str
    model_used: str
    tokens_used: int | None = None
```

Data class representing the result of any planning operation, including the generated content, model used, and token consumption metrics.

#### `Planner` Protocol
```python
class Planner(Protocol):
    def generate_project_plan(...) -> PlanResult
    def generate_daily_plan(...) -> PlanResult
    def generate_hourly_plan(...) -> PlanResult
    def generate_daily_report(...) -> PlanResult
    def generate_simulation_report(...) -> PlanResult
```

Protocol defining the interface for all planner implementations, ensuring consistent API across GPT and stub planners.

### Implementations

#### `GPTPlanner`
AI-powered planner using OpenAI's GPT-4o models for realistic workplace simulation.

**Features**:
- **Persona Integration**: Uses complete `persona_markdown` context for authentic planning
- **Localization Support**: Enhanced Korean language enforcement when `VDOS_LOCALE=ko`
- **Team Awareness**: Includes team roster and project context in planning
- **Communication Scheduling**: Generates parseable scheduled communication instructions
- **Token Tracking**: Comprehensive usage metrics for cost monitoring

**Model Configuration**:
```python
DEFAULT_PROJECT_MODEL = os.getenv("VDOS_PLANNER_PROJECT_MODEL", "gpt-4o-mini")
DEFAULT_DAILY_MODEL = os.getenv("VDOS_PLANNER_DAILY_MODEL", DEFAULT_PROJECT_MODEL)
DEFAULT_HOURLY_MODEL = os.getenv("VDOS_PLANNER_HOURLY_MODEL", DEFAULT_DAILY_MODEL)
DEFAULT_DAILY_REPORT_MODEL = os.getenv("VDOS_PLANNER_DAILY_REPORT_MODEL")
DEFAULT_SIM_REPORT_MODEL = os.getenv("VDOS_PLANNER_SIM_REPORT_MODEL")
```

#### `StubPlanner`
Deterministic fallback planner for testing and scenarios without AI dependencies.

**Features**:
- **Deterministic Output**: Consistent, predictable plans for testing
- **Localization Aware**: Korean-localized stub content when appropriate
- **Zero Dependencies**: No external API requirements
- **Fast Execution**: Immediate response for rapid testing scenarios

## Planning Functions

### Project Planning
```python
def generate_project_plan(
    department_head: PersonRead,
    project_name: str,
    project_summary: str,
    duration_weeks: int,
    team: Sequence[PersonRead],
    model_hint: str | None = None,
) -> PlanResult
```

Generates comprehensive project roadmaps with weekly phases, deliverables, and team coordination strategies.

**Context Provided**:
- Department head persona and leadership style
- Complete team roster with roles and skills
- Project scope and duration requirements
- Localized templates and terminology

### Daily Planning
```python
def generate_daily_plan(
    worker: PersonRead,
    project_plan: str,
    day_index: int,
    model_hint: str | None = None,
    all_active_projects: list[dict[str, Any]] | None = None,
) -> PlanResult
```

Creates detailed daily schedules aligned with project phases and individual worker capabilities.

**Context Provided**:
- **Enhanced Persona Context**: Complete `persona_markdown` for authentic planning
- Current project phase and objectives
- Multi-project coordination when applicable
- Work hours and break patterns
- Localized planning templates

### Hourly Planning (Enhanced)
```python
def generate_hourly_plan(
    worker: PersonRead,
    project_plan: str,
    daily_plan: str,
    tick: int,
    context_reason: str,
    team: Sequence[PersonRead] | None = None,
    model_hint: str | None = None,
    all_active_projects: list[dict[str, Any]] | None = None,
    recent_emails: list[dict[str, Any]] | None = None,
) -> PlanResult
```

**Recent Enhancement (October 2025)**: Now includes complete persona context for authentic planning.

**Enhanced Context Building**:
```python
# Extract persona information for authentic planning
persona_context = []
if hasattr(worker, 'persona_markdown') and worker.persona_markdown:
    persona_context.append("=== YOUR PERSONA & WORKING STYLE ===")
    persona_context.append(worker.persona_markdown)
    persona_context.append("")
```

**Context Provided**:
- **Complete Persona Context**: Full personality, skills, and working style information
- Team roster with exact email addresses for communication
- Recent email context for threading and responses
- Current project status and daily objectives
- Scheduled communication parsing and validation
- Multi-project coordination and prioritization

**Scheduled Communication Format**:
```
Email at 10:30 to dev cc pm, designer: Subject | Body text
Chat at 14:00 with designer: Message text
Reply at 11:00 to [email-123] cc team: Response subject | Response body
```

### Report Generation

#### Daily Reports
```python
def generate_daily_report(
    worker: PersonRead,
    day_index: int,
    hourly_plans: list[str],
    model_hint: str | None = None,
) -> PlanResult
```

Summarizes daily accomplishments, blockers, and next-day planning.

#### Simulation Reports
```python
def generate_simulation_report(
    total_ticks: int,
    people: Sequence[PersonRead],
    model_hint: str | None = None,
) -> PlanResult
```

Comprehensive end-of-simulation analysis with team performance and project outcomes.

## Localization Integration

### Korean Language Support
When `VDOS_LOCALE=ko` is configured, the planner applies enhanced Korean language enforcement:

**System Message Enhancement**:
```python
korean_system_msg = get_korean_prompt("comprehensive")
# Applies strict Korean-only instructions across all planning functions
```

**Features**:
- **Natural Korean Communication**: Workplace-appropriate Korean language patterns
- **Mixed Language Prevention**: Strict enforcement against English/Korean mixing
- **Context-Aware Examples**: Specific examples of correct Korean terminology
- **Cultural Authenticity**: Korean workplace norms and communication styles

### Localization Manager Integration
```python
from virtualoffice.common.localization import get_current_locale_manager

locale_manager = get_current_locale_manager()
scheduled_header = locale_manager.get_text("scheduled_communications")
# Returns "Scheduled Communications" (en) or "예정된 커뮤니케이션" (ko)
```

## Error Handling and Fallback

### Planner Strict Mode
```python
VDOS_PLANNER_STRICT = os.getenv("VDOS_PLANNER_STRICT", "0")
```

**Behavior**:
- `VDOS_PLANNER_STRICT=0` (default): Falls back to `StubPlanner` on GPT failures
- `VDOS_PLANNER_STRICT=1`: Raises `PlanningError` on GPT failures, no fallback

### Error Recovery
1. **API Failures**: Network timeouts, rate limits, authentication errors
2. **Content Filtering**: OpenAI content policy violations
3. **Token Limits**: Request exceeds model context window
4. **Parsing Errors**: Malformed responses from AI models

**Fallback Strategy**:
```python
try:
    result = gpt_planner.generate_hourly_plan(...)
except Exception as e:
    logger.warning(f"GPT planning failed: {e}")
    if not self._planner_strict:
        result = stub_planner.generate_hourly_plan(...)
    else:
        raise PlanningError(f"Planning failed: {e}")
```

## Performance and Optimization

### Token Usage Tracking
All planning operations track token consumption for cost monitoring and optimization:

```python
@dataclass
class PlanResult:
    content: str
    model_used: str
    tokens_used: int | None = None
```

### Caching Strategy
- **Project Plans**: Cached in simulation engine for reuse across workers
- **Team Context**: Built once per planning cycle, reused for all workers
- **Localization**: Locale manager cached for session duration

### Rate Limiting
```python
VDOS_MAX_HOURLY_PLANS_PER_MINUTE = int(os.getenv("VDOS_MAX_HOURLY_PLANS_PER_MINUTE", "10"))
```

Prevents excessive API usage during high-activity simulation periods.

## Integration Points

### Simulation Engine Integration
```python
# Engine calls planner with complete context
result = self.planner.generate_hourly_plan(
    worker=worker,
    project_plan=project_plan,
    daily_plan=daily_plan,
    tick=current_tick,
    context_reason=reason,
    team=team_members,
    model_hint=self._planner_model_hint,
    all_active_projects=active_projects,
    recent_emails=recent_emails
)
```

### Communication Gateway Integration
Planner-generated scheduled communications are parsed and executed by the simulation engine:

1. **Parsing**: Engine extracts scheduled communication instructions from plans
2. **Validation**: Email addresses validated against team roster
3. **Execution**: Communications sent at specified simulation ticks
4. **Threading**: Email replies properly threaded using recent email context

### Persona System Integration
The planner leverages the complete persona system for authentic behavior:

- **Personality Traits**: Plans reflect individual communication styles and preferences
- **Skills and Expertise**: Task assignments align with worker capabilities
- **Work Patterns**: Schedules respect individual work hours and break preferences
- **Role Responsibilities**: Actions appropriate for job titles and team positions

## Testing and Validation

### Test Coverage
- **Unit Tests**: Individual planner function validation
- **Integration Tests**: End-to-end planning pipeline testing
- **Localization Tests**: Korean language enforcement validation
- **Fallback Tests**: Stub planner functionality and error handling
- **Performance Tests**: Token usage and response time monitoring

### Quality Assurance
- **Content Validation**: Korean content validation for mixed language detection
- **Communication Parsing**: Scheduled communication format validation
- **Team Coordination**: Multi-worker planning consistency checks
- **Project Alignment**: Plan adherence to project phases and objectives

## Future Enhancements

### Planned Improvements
1. **Dynamic Persona Learning**: Adapt planning based on simulation history
2. **Advanced Team Coordination**: Cross-worker dependency modeling
3. **Stress Response Modeling**: Workload-based planning adjustments
4. **Communication Pattern Analysis**: Persona-specific messaging styles
5. **Multi-Language Support**: Additional locale support beyond Korean

### Extension Points
1. **Custom Planner Implementations**: Plugin architecture for specialized planners
2. **Industry-Specific Templates**: Domain-specific planning patterns
3. **Advanced AI Models**: Integration with newer language models
4. **Real-Time Adaptation**: Dynamic planning based on simulation feedback

## Configuration Reference

### Environment Variables
```bash
# Model Selection
VDOS_PLANNER_PROJECT_MODEL=gpt-4o-mini
VDOS_PLANNER_DAILY_MODEL=gpt-4o-mini
VDOS_PLANNER_HOURLY_MODEL=gpt-4o-mini
VDOS_PLANNER_DAILY_REPORT_MODEL=gpt-4o-mini
VDOS_PLANNER_SIM_REPORT_MODEL=gpt-4o-mini

# Behavior Configuration
VDOS_PLANNER_STRICT=0                    # Enable/disable fallback to stub planner
VDOS_MAX_HOURLY_PLANS_PER_MINUTE=10     # Rate limiting for API usage
VDOS_LOCALE=ko                          # Enable Korean localization

# API Configuration
OPENAI_API_KEY=sk-...                   # Required for GPT planner functionality
```

### Usage Examples
```python
# Initialize planner
planner = GPTPlanner()

# Generate project plan
project_result = planner.generate_project_plan(
    department_head=dept_head,
    project_name="Mobile App Redesign",
    project_summary="Modernize mobile application UI/UX",
    duration_weeks=4,
    team=team_members
)

# Generate hourly plan with persona context
hourly_result = planner.generate_hourly_plan(
    worker=worker,
    project_plan=project_result.content,
    daily_plan=daily_plan_content,
    tick=current_tick,
    context_reason="New messages received",
    team=team_members
)
```

The planner module serves as the intelligence core of VDOS, generating realistic workplace behavior through sophisticated AI integration while maintaining reliability through comprehensive fallback mechanisms and localization support.