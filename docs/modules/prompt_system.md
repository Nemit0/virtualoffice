# Prompt Management System Documentation

## Overview

The Prompt Management System (`src/virtualoffice/sim_manager/prompts/`) provides centralized template management, context building, and metrics collection for LLM-powered planning and reporting in VDOS. This system was extracted from the SimulationEngine as part of the Phase 1 engine refactoring project.

## Architecture

### Module Location
```
src/virtualoffice/sim_manager/prompts/
├── __init__.py              # Module exports
├── prompt_manager.py        # Template loading and caching
├── context_builder.py       # Context aggregation
└── metrics_collector.py     # Performance tracking
```

### Dependencies
- `virtualoffice.sim_manager.schemas` - PersonRead and other data models
- `virtualoffice.virtualWorkers.context_classes` - Context dataclasses for structured data
- `yaml` - YAML template parsing
- `pathlib` - File system operations
- `dataclasses` - Data structure definitions

## Core Components

### PromptManager

Main class responsible for template lifecycle management.

```python
class PromptManager:
    """
    Manages prompt templates with caching and validation.
    
    Loads YAML templates from a directory structure, caches them for performance,
    and provides methods to build prompts with context substitution.
    """
    
    def __init__(self, template_dir: str, locale: str = "en"):
        """
        Initialize the prompt manager.
        
        Args:
            template_dir: Path to directory containing template files
            locale: Default locale for template loading (e.g., "en", "ko")
        """
```

#### Key Methods

##### load_template()
Load a template from disk or cache.

```python
def load_template(self, name: str, version: str = "latest") -> PromptTemplate:
    """
    Load a template from disk or cache.
    
    Args:
        name: Template name (without locale suffix or extension)
        version: Template version (currently only "latest" supported)
        
    Returns:
        Loaded and validated PromptTemplate
        
    Raises:
        PromptTemplateError: If template not found or invalid
    """
```

**Example Usage**:
```python
manager = PromptManager("templates/", locale="en")
template = manager.load_template("hourly_planning")
```

##### build_prompt()
Build a prompt from a template with context substitution.

```python
def build_prompt(
    self, 
    template_name: str, 
    context: dict[str, Any], 
    variant: str | None = None
) -> list[dict[str, str]]:
    """
    Build a prompt from a template with context substitution.
    
    Args:
        template_name: Name of template to use
        context: Dictionary of variables for substitution
        variant: Optional variant name for A/B testing
        
    Returns:
        List of message dicts with 'role' and 'content' keys
        
    Raises:
        PromptTemplateError: If template not found or context invalid
    """
```

**Example Usage**:
```python
context = {
    "worker_name": "Alice",
    "tick": 10,
    "project_plan": "Build dashboard MVP",
    "daily_plan": "Focus on authentication module",
}

messages = manager.build_prompt("hourly_planning", context)
# Returns: [
#   {"role": "system", "content": "You are a helpful assistant..."},
#   {"role": "user", "content": "Generate hourly plan for Alice..."}
# ]
```

##### validate_context()
Validate that context contains all required variables.

```python
def validate_context(self, template: PromptTemplate, context: dict[str, Any]) -> bool:
    """
    Validate that context contains all required variables.
    
    Args:
        template: Template to validate against
        context: Context dictionary to validate
        
    Returns:
        True if valid
        
    Raises:
        PromptTemplateError: If validation fails
    """
```

##### list_templates()
List available templates.

```python
def list_templates(self, category: str | None = None) -> list[str]:
    """
    List available templates.
    
    Args:
        category: Optional category filter (e.g., "planning", "reporting")
        
    Returns:
        List of template names (without locale suffix or extension)
    """
```

##### reload_templates()
Clear the template cache, forcing reload on next access.

```python
def reload_templates(self) -> None:
    """
    Clear the template cache, forcing reload on next access.
    
    Useful for development or when templates are updated at runtime.
    """
```

### PromptTemplate

Dataclass representing a loaded template.

```python
@dataclass
class PromptTemplate:
    """
    Represents a prompt template loaded from YAML.
    
    Attributes:
        name: Template identifier (e.g., "hourly_planning_en")
        version: Template version (e.g., "1.0", "latest")
        locale: Language/locale code (e.g., "en", "ko")
        category: Template category (e.g., "planning", "reporting")
        system_prompt: LLM system message content
        user_prompt_template: User message template with variable placeholders
        sections: Reusable template sections with their own templates
        validation_rules: List of validation requirements
        variants: Alternative template versions for A/B testing
        metadata: Additional template metadata
    """
```

### ContextBuilder

Aggregates data from various sources to build comprehensive context dictionaries.

```python
class ContextBuilder:
    """
    Builds context dictionaries for prompt templates.
    
    Aggregates worker information, team rosters, project plans,
    and other contextual data needed for realistic LLM-generated plans.
    """
    
    def __init__(self, locale: str = "en"):
        """
        Initialize the context builder.
        
        Args:
            locale: Language/locale code (e.g., "en", "ko")
        """
```

#### Key Methods

##### build_planning_context()
Build context for hourly planning prompts.

```python
def build_planning_context(
    self,
    worker: PersonRead,
    tick: int,
    reason: str,
    project_plan: str,
    daily_plan: str,
    team: Sequence[PersonRead],
    recent_emails: list[dict[str, Any]] | None = None,
    all_active_projects: list[dict[str, Any]] | None = None,
) -> PlanningContext:
    """
    Build context for hourly planning prompts.
    
    Returns:
        PlanningContext dataclass with all necessary information
    """
```

**Note**: This method now returns a `PlanningContext` dataclass (from `virtualWorkers.context_classes`) instead of a raw dictionary, providing type safety and better IDE support.

**Example Usage**:
```python
from virtualoffice.sim_manager.prompts.context_builder import ContextBuilder
from virtualoffice.virtualWorkers.context_classes import PlanningContext

builder = ContextBuilder(locale="en")

context = builder.build_planning_context(
    worker=alice,
    tick=10,
    reason="start_of_hour",
    project_plan="Build dashboard MVP",
    daily_plan="Focus on authentication",
    team=[alice, bob, charlie],
    recent_emails=[...],
    all_active_projects=[...]
)

# Context is a PlanningContext dataclass with attributes:
# - project_plan: str
# - daily_plan: str
# - tick: int
# - reason: str
# - team: Sequence[PersonRead]
# - recent_emails: list[dict] | None
# - all_active_projects: list[dict] | None
# - locale: str
# - model_hint: str | None

# Access context fields with type safety
print(f"Planning for tick {context.tick}")
print(f"Reason: {context.reason}")
print(f"Team size: {len(context.team)}")
```

##### build_event_context()
Build context for event reaction prompts.

```python
def build_event_context(
    self,
    worker: PersonRead,
    event: dict[str, Any],
    tick: int,
    team: Sequence[PersonRead],
    project_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    Build context for event reaction prompts.
    """
```

##### build_reporting_context()
Build context for daily report generation.

```python
def build_reporting_context(
    self,
    worker: PersonRead,
    day_index: int,
    daily_plan: str,
    hourly_log: str,
    minute_schedule: str,
) -> dict[str, Any]:
    """
    Build context for daily report generation.
    """
```

### PromptMetricsCollector

Tracks prompt usage, token consumption, and performance metrics.

```python
class PromptMetricsCollector:
    """
    Collects and aggregates prompt usage metrics.
    
    Tracks prompt performance for analysis and A/B testing,
    with support for exporting metrics to JSON.
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize the metrics collector.
        
        Args:
            max_history: Maximum number of metrics to keep in memory
        """
```

#### Key Methods

##### record_usage()
Record a prompt usage event.

```python
def record_usage(
    self,
    template_name: str,
    variant: str,
    model_used: str,
    tokens_used: int,
    duration_ms: float,
    success: bool,
    error: str | None = None,
) -> None:
    """
    Record a prompt usage event.
    """
```

**Example Usage**:
```python
collector = PromptMetricsCollector()

collector.record_usage(
    template_name="hourly_planning",
    variant="default",
    model_used="gpt-4o",
    tokens_used=450,
    duration_ms=1250.5,
    success=True
)
```

##### get_performance_stats()
Get performance statistics for a template.

```python
def get_performance_stats(self, template_name: str) -> dict[str, Any]:
    """
    Get performance statistics for a template.
    
    Returns:
        Dictionary with performance statistics including:
        - total_uses: Total number of uses
        - success_rate: Percentage of successful generations
        - avg_tokens: Average token consumption
        - avg_duration_ms: Average generation duration
        - total_tokens: Total tokens consumed
        - by_variant: Per-variant statistics
    """
```

**Example Usage**:
```python
stats = collector.get_performance_stats("hourly_planning")
print(f"Success rate: {stats['success_rate']}%")
print(f"Average tokens: {stats['avg_tokens']}")
print(f"By variant: {stats['by_variant']}")
```

##### get_best_variant()
Identify the best performing variant for a template.

```python
def get_best_variant(self, template_name: str) -> str:
    """
    Identify the best performing variant for a template.
    
    Uses a composite score based on success rate, token efficiency,
    and generation speed. Success rate is heavily weighted (70%).
    
    Returns:
        Name of best performing variant, or "default" if no data
    """
```

##### export_metrics()
Export metrics to a JSON file.

```python
def export_metrics(self, filepath: str) -> None:
    """
    Export metrics to a JSON file.
    """
```

##### get_metrics_summary()
Get a summary of all metrics across all templates.

```python
def get_metrics_summary(self) -> dict[str, Any]:
    """
    Get a summary of all metrics across all templates.
    
    Returns:
        Dictionary with overall statistics
    """
```

### PromptMetric

Dataclass representing a single prompt usage metric.

```python
@dataclass
class PromptMetric:
    """
    Represents a single prompt usage metric.
    
    Attributes:
        timestamp: When the prompt was used
        template_name: Name of the template used
        variant: Variant name (e.g., "default", "verbose", "concise")
        model_used: LLM model identifier (e.g., "gpt-4o", "gpt-4o-mini")
        tokens_used: Number of tokens consumed
        duration_ms: Generation duration in milliseconds
        success: Whether generation succeeded
        error: Error message if generation failed
    """
```

## Context Classes Integration

The Prompt Management System integrates with VirtualWorker Context Classes (`src/virtualoffice/virtualWorkers/context_classes.py`) to provide type-safe, structured data for prompt generation.

### Context Dataclasses

The `ContextBuilder` returns structured context objects instead of raw dictionaries:

#### PlanningContext

Returned by `build_planning_context()`:

```python
@dataclass
class PlanningContext:
    project_plan: str
    daily_plan: str
    tick: int
    reason: str
    team: Sequence[PersonRead]
    recent_emails: list[dict[str, Any]] | None = None
    all_active_projects: list[dict[str, Any]] | None = None
    locale: str = "en"
    model_hint: str | None = None
```

#### DailyPlanningContext

Returned by `build_daily_planning_context()`:

```python
@dataclass
class DailyPlanningContext:
    project_plan: str
    day_index: int
    duration_weeks: int
    team: Sequence[PersonRead]
    locale: str = "en"
    model_hint: str | None = None
```

#### EventContext

Returned by `build_event_context()`:

```python
@dataclass
class EventContext:
    event: dict[str, Any]
    tick: int
    team: Sequence[PersonRead]
    project_plan: dict[str, Any]
    locale: str = "en"
    model_hint: str | None = None
```

#### ReportContext

Returned by `build_reporting_context()`:

```python
@dataclass
class ReportContext:
    day_index: int
    daily_plan: str
    hourly_log: str
    minute_schedule: str
    project_plan: str | None = None  # Optional project plan context
    locale: str = "en"
    model_hint: str | None = None
```

### Benefits of Context Classes

1. **Type Safety**: IDE autocomplete and type checking
2. **Clear Contracts**: Explicit interfaces between components
3. **Immutability**: Dataclasses are immutable by default
4. **Documentation**: Self-documenting with type hints
5. **Validation**: Required fields enforced at creation time

### Usage Pattern

```python
# Build context using ContextBuilder
builder = ContextBuilder(locale="en")
context = builder.build_planning_context(
    worker=alice,
    tick=10,
    reason="start_of_hour",
    project_plan="Build dashboard MVP",
    daily_plan="Focus on authentication",
    team=[alice, bob, charlie]
)

# Context is a PlanningContext dataclass
assert isinstance(context, PlanningContext)

# Access fields with type safety
print(f"Planning for {context.reason} at tick {context.tick}")

# Pass to VirtualWorker
result = worker.plan_next_hour(context)
```

For complete documentation of context classes, see `docs/modules/virtual_worker_context.md`.

## Template Format

### YAML Template Structure

Templates are stored as YAML files with the following structure:

```yaml
name: hourly_planning
version: "1.0"
locale: en
category: planning

system_prompt: |
  You are an AI assistant helping a worker plan their hour.
  Generate realistic, detailed hourly plans.

user_prompt_template: |
  Worker: {worker_name} ({worker_role})
  Current Tick: {tick}
  Reason: {context_reason}
  
  Project Plan:
  {project_plan}
  
  Daily Plan:
  {daily_plan}
  
  {team_roster}
  
  Generate an hourly plan for the next hour.

sections:
  team_roster:
    template: |
      === TEAM ROSTER ===
      {team_roster_list}
    required_variables:
      - team_roster_list

validation_rules:
  - "Must include scheduled communications"
  - "Must reference team members by exact email/handle"

variants:
  - name: verbose
    system_prompt: |
      You are an AI assistant. Be very detailed in your planning.
    user_prompt_template: |
      [Verbose version of template]
  
  - name: concise
    system_prompt: |
      You are an AI assistant. Be brief and focused.
    user_prompt_template: |
      [Concise version of template]

metadata:
  author: "VDOS Team"
  created: "2025-10-27"
  description: "Hourly planning template for workers"
```

### Template Directory Structure

```
templates/
├── planning/
│   ├── hourly_planning_en.yaml
│   ├── hourly_planning_ko.yaml
│   ├── daily_planning_en.yaml
│   └── daily_planning_ko.yaml
├── reporting/
│   ├── daily_report_en.yaml
│   ├── daily_report_ko.yaml
│   └── simulation_report_en.yaml
└── communication/
    ├── email_draft_en.yaml
    └── chat_message_en.yaml
```

## Integration with SimulationEngine

### Initialization

```python
class SimulationEngine:
    def __init__(self, ...):
        # Initialize prompt system
        template_dir = Path(__file__).parent / "templates"
        locale = os.getenv("VDOS_LOCALE", "en")
        
        self.prompt_manager = PromptManager(str(template_dir), locale=locale)
        self.context_builder = ContextBuilder(locale=locale)
        self.metrics_collector = PromptMetricsCollector(max_history=1000)
```

### Direct Prompt Generation with Planner

The `Planner` protocol now supports direct prompt generation using pre-built message lists via the `generate_with_messages()` method:

```python
def generate_with_messages(
    self,
    *,
    messages: list[dict[str, str]],
    model_hint: str | None = None,
) -> PlanResult:
    """
    Generate a plan using pre-built message list.
    
    This method allows using externally constructed prompts
    (e.g., from PromptManager) instead of the built-in prompt logic.
    
    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_hint: Optional model override
        
    Returns:
        PlanResult with generated content
    """
```

**Example Usage**:
```python
# Build messages using PromptManager
prompt_manager = PromptManager(template_dir, locale="en")
context = {
    "worker_name": "Alice",
    "tick": 10,
    "project_plan": "Build dashboard MVP",
    "daily_plan": "Focus on authentication module",
    ...
}
messages = prompt_manager.build_prompt("hourly_planning", context)

# Generate using pre-built messages
planner = GPTPlanner()
result = planner.generate_with_messages(
    messages=messages,
    model_hint="gpt-4o"
)

print(f"Generated plan: {result.content}")
print(f"Model used: {result.model_used}")
print(f"Tokens: {result.tokens_used}")
```

This allows external systems to construct prompts using PromptManager and pass them directly to the planner, bypassing the built-in prompt logic. This is particularly useful for:
- Custom prompt engineering workflows
- A/B testing different prompt structures
- Integration with external prompt management systems
- Advanced prompt optimization scenarios

### Usage in Planning

```python
def _generate_hourly_plan(self, worker: PersonRead, tick: int, ...):
    # Build context
    context = self.context_builder.build_planning_context(
        worker=worker,
        tick=tick,
        reason="start_of_hour",
        project_plan=project_plan,
        daily_plan=daily_plan,
        team=team,
        recent_emails=recent_emails,
        all_active_projects=active_projects
    )
    
    # Get best variant (A/B testing)
    variant = self.metrics_collector.get_best_variant("hourly_planning")
    
    # Build prompt
    messages = self.prompt_manager.build_prompt(
        "hourly_planning",
        context,
        variant=variant
    )
    
    # Call LLM
    start_time = time.perf_counter()
    try:
        response = self.llm_client.generate(messages, model="gpt-4o")
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Record metrics
        self.metrics_collector.record_usage(
            template_name="hourly_planning",
            variant=variant,
            model_used="gpt-4o",
            tokens_used=response.tokens,
            duration_ms=duration_ms,
            success=True
        )
        
        return response.content
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        self.metrics_collector.record_usage(
            template_name="hourly_planning",
            variant=variant,
            model_used="gpt-4o",
            tokens_used=0,
            duration_ms=duration_ms,
            success=False,
            error=str(e)
        )
        raise
```

## Localization Support

The prompt system integrates with the localization system for multi-language support:

### Locale-Specific Templates

- **English (en)**: `hourly_planning_en.yaml`
- **Korean (ko)**: `hourly_planning_ko.yaml`

### Context Builder Localization

The `ContextBuilder` automatically formats team rosters and other context elements based on the configured locale:

```python
# English locale
builder = ContextBuilder(locale="en")
context = builder.build_planning_context(...)
# team_roster: "=== YOUR TEAM ROSTER ==="

# Korean locale
builder = ContextBuilder(locale="ko")
context = builder.build_planning_context(...)
# team_roster: "=== 팀 명단 ==="
```

## A/B Testing and Optimization

### Variant System

Templates can define multiple variants for A/B testing:

```yaml
variants:
  - name: verbose
    system_prompt: "Be very detailed..."
  - name: concise
    system_prompt: "Be brief..."
```

### Automatic Variant Selection

The metrics collector tracks performance and automatically selects the best variant:

```python
# Get best performing variant based on success rate, token efficiency, and speed
variant = metrics_collector.get_best_variant("hourly_planning")

# Use variant in prompt generation
messages = prompt_manager.build_prompt("hourly_planning", context, variant=variant)
```

### Performance Scoring

Variants are scored using a composite metric:
- **Success Rate**: 70% weight (most important)
- **Token Efficiency**: 20% weight (cost optimization)
- **Generation Speed**: 10% weight (user experience)

## Testing

### Unit Tests

Location: `tests/prompts/`

**Test Coverage**:
- Template loading and caching
- Context building for all scenarios
- Metrics collection and aggregation
- Variant selection logic
- Error handling and validation

**Example Test**:
```python
def test_load_template():
    manager = PromptManager("test_templates/", locale="en")
    template = manager.load_template("hourly_planning")
    
    assert template.name == "hourly_planning"
    assert template.locale == "en"
    assert template.category == "planning"
```

### Integration Tests

Location: `tests/test_sim_manager.py`

**Test Scenarios**:
- End-to-end prompt generation in simulations
- Multi-locale template usage
- Metrics collection during simulation runs
- A/B testing variant selection

## Performance Considerations

### Template Caching

- Templates are cached in memory after first load
- Cache key: `{name}_{locale}_{version}`
- Use `reload_templates()` to clear cache during development

### Metrics Memory Management

- Metrics collector maintains a rolling window (default: 1000 entries)
- Oldest metrics are automatically discarded
- Export metrics to JSON for long-term storage

### Context Building Efficiency

- Team rosters are formatted once per planning cycle
- Recent emails are limited to last 5 for context
- Project plans are truncated to 500 characters in multi-project scenarios

## Extension Guidelines

### Adding New Templates

1. **Create YAML file** in appropriate category directory:
```yaml
name: new_template
version: "1.0"
locale: en
category: planning
system_prompt: "..."
user_prompt_template: "..."
```

2. **Add locale variants** (e.g., `new_template_ko.yaml`)

3. **Update context builder** if new context variables needed:
```python
def build_new_context(self, ...):
    context = {
        "new_variable": value,
        ...
    }
    return context
```

4. **Add tests** for new template:
```python
def test_new_template():
    manager = PromptManager("templates/", locale="en")
    template = manager.load_template("new_template")
    assert template.name == "new_template"
```

### Adding New Context Variables

1. **Update ContextBuilder** method:
```python
def build_planning_context(self, ...):
    context = {
        ...
        "new_variable": self._format_new_data(data),
    }
    return context
```

2. **Add formatting helper**:
```python
def _format_new_data(self, data: Any) -> str:
    # Format data for prompt inclusion
    return formatted_string
```

3. **Update template** to use new variable:
```yaml
user_prompt_template: |
  ...
  {new_variable}
  ...
```

### Adding New Metrics

1. **Extend PromptMetric** dataclass:
```python
@dataclass
class PromptMetric:
    ...
    new_metric: float = 0.0
```

2. **Update record_usage()**:
```python
def record_usage(self, ..., new_metric: float = 0.0):
    metric = PromptMetric(
        ...
        new_metric=new_metric
    )
```

3. **Update performance stats**:
```python
def get_performance_stats(self, template_name: str):
    ...
    avg_new_metric = sum(m.new_metric for m in metrics) / len(metrics)
    ...
```

## Best Practices

### Template Design
- Keep system prompts focused and clear
- Use descriptive variable names in templates
- Include validation rules for expected output format
- Document template purpose in metadata

### Context Building
- Validate all required variables are present
- Format data consistently across locales
- Truncate large context elements appropriately
- Include only relevant information

### Metrics Collection
- Record metrics for all prompt generations
- Export metrics regularly for analysis
- Monitor success rates and token usage
- Use A/B testing for optimization

### Error Handling
- Validate templates on load
- Check context completeness before generation
- Handle missing variables gracefully
- Log errors with sufficient context

## Future Enhancements

### Planned Features
1. **Dynamic Template Loading**: Hot-reload templates without restart
2. **Advanced A/B Testing**: Multi-armed bandit algorithms for variant selection
3. **Template Versioning**: Support for multiple template versions simultaneously
4. **Prompt Optimization**: Automatic prompt refinement based on metrics
5. **Template Inheritance**: Base templates with category-specific overrides

### Integration Roadmap
1. **Phase 1**: Prompt system extraction ✅ Complete
2. **Phase 2**: Template library expansion
3. **Phase 3**: Advanced metrics and A/B testing
4. **Phase 4**: Automatic prompt optimization

## Conclusion

The Prompt Management System provides a robust, scalable foundation for LLM integration in VDOS. By centralizing template management, context building, and metrics collection, it enables consistent, high-quality prompt generation while supporting localization, A/B testing, and continuous optimization.

The system's modular design allows for easy extension and integration with the SimulationEngine while maintaining clean separation of concerns and comprehensive testing coverage.
