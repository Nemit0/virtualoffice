# Template Authoring Guide

## Overview

This guide explains how to create and maintain YAML prompt templates for the VDOS prompt management system. Templates allow you to iterate on prompts without code deployment and track prompt performance.

## Template Structure

### Basic Template Format

```yaml
name: "template_name"
version: "1.0"
locale: "en"
category: "planning"  # planning, reporting, communication, events
description: "Brief description of template purpose"

system_prompt: |
  System-level instructions for the LLM.
  These set the overall behavior and constraints.

user_prompt_template: |
  User-level prompt with {variable_placeholders}.
  Variables are substituted at runtime with context data.

sections:
  section_name:
    template: |
      Reusable section content with {section_variables}.
    required_variables: ["section_variables"]

validation_rules:
  - "Expected output characteristic 1"
  - "Expected output characteristic 2"

variants:
  - name: "variant_name"
    description: "What makes this variant different"
    system_prompt: "Optional override for system prompt"
    user_prompt_template: "Optional override for user prompt"

metadata:
  author: "Your Name"
  created_at: "2024-01-01"
  last_modified: "2024-01-15"
  notes: "Additional context about this template"
```

## Template Categories

### Planning Templates

Used for generating work plans (hourly, daily, project).

**Location**: `templates/planning/`

**Common Variables**:
- `worker_name`: Name of the worker
- `worker_role`: Job title/role
- `tick`: Current simulation tick
- `context_reason`: Why planning is triggered
- `persona_markdown`: Full persona specification
- `team_roster`: List of team members
- `project_plan`: Current project plan
- `daily_plan`: Current daily plan
- `recent_emails`: Recent email history
- `all_active_projects`: List of active projects

**Example**: `hourly_planning_en.yaml`

```yaml
name: "hourly_planning_en"
version: "1.0"
locale: "en"
category: "planning"

system_prompt: |
  You are an operations coach helping workers plan their next few hours.
  Use the worker's persona to create authentic, realistic plans.

user_prompt_template: |
  Worker: {worker_name} ({worker_role}) at tick {tick}.
  Trigger: {context_reason}.
  
  {persona_section}
  {team_roster_section}
  {project_section}
  
  Generate a realistic hourly plan with:
  - Specific tasks with time estimates
  - Scheduled communications (emails/chats)
  - Buffer time for interruptions

sections:
  persona_section:
    template: |
      === YOUR PERSONA ===
      {persona_markdown}
    required_variables: ["persona_markdown"]
  
  team_roster_section:
    template: |
      === TEAM ROSTER ===
      {team_roster}
    required_variables: ["team_roster"]
  
  project_section:
    template: |
      === PROJECT PLAN ===
      {project_plan}
      
      === DAILY PLAN ===
      {daily_plan}
    required_variables: ["project_plan", "daily_plan"]

validation_rules:
  - "Must include scheduled communications section"
  - "Must use exact email addresses from team roster"
  - "Must include realistic time estimates"
```

### Reporting Templates

Used for generating daily reports and summaries.

**Location**: `templates/reporting/`

**Common Variables**:
- `worker_name`: Name of the worker
- `day_index`: Day number (0-indexed)
- `daily_plan`: Plan for the day
- `hourly_log`: Log of hourly activities
- `minute_schedule`: Detailed minute-by-minute schedule

**Example**: `daily_report_en.yaml`

```yaml
name: "daily_report_en"
version: "1.0"
locale: "en"
category: "reporting"

system_prompt: |
  You are generating an end-of-day report for a virtual worker.
  Be concise, factual, and highlight key accomplishments and blockers.

user_prompt_template: |
  Generate a daily report for {worker_name} (Day {day_index}).
  
  === PLANNED ACTIVITIES ===
  {daily_plan}
  
  === ACTUAL ACTIVITIES ===
  {hourly_log}
  
  Report should include:
  - Key accomplishments
  - Blockers encountered
  - Tomorrow's priorities

validation_rules:
  - "Must include accomplishments section"
  - "Must include blockers section"
  - "Must include tomorrow's priorities"
```

### Event Templates

Used for generating reactions to simulation events.

**Location**: `templates/events/`

**Common Variables**:
- `worker_name`: Name of the worker
- `event_type`: Type of event (sick_leave, client_request, blocker)
- `event_description`: Event details
- `tick`: Current tick
- `team_roster`: List of team members
- `project_plan`: Current project

**Example**: `event_reaction_en.yaml`

```yaml
name: "event_reaction_en"
version: "1.0"
locale: "en"
category: "events"

system_prompt: |
  You are helping a worker react to an unexpected event.
  Generate realistic adjustments and communications.

user_prompt_template: |
  Worker {worker_name} encountered an event at tick {tick}:
  
  Event Type: {event_type}
  Description: {event_description}
  
  {team_section}
  {project_section}
  
  Generate:
  1. Immediate adjustments to current plan
  2. Communications to send (who, what, when)
  3. Status change if needed (e.g., "Away", "SickLeave")

sections:
  team_section:
    template: |
      === TEAM ===
      {team_roster}
    required_variables: ["team_roster"]
  
  project_section:
    template: |
      === PROJECT ===
      {project_plan}
    required_variables: ["project_plan"]

validation_rules:
  - "Must include adjustments list"
  - "Must include communications if coordination needed"
  - "Must specify status change if applicable"
```

## Variable Substitution

### Basic Substitution

Variables in templates are enclosed in curly braces: `{variable_name}`

```yaml
user_prompt_template: |
  Hello {worker_name}, you are a {worker_role}.
```

Context:
```python
context = {
    "worker_name": "Alice",
    "worker_role": "Developer"
}
```

Result:
```
Hello Alice, you are a Developer.
```

### Section Substitution

Sections are reusable template fragments:

```yaml
sections:
  greeting_section:
    template: |
      Hello {name}, welcome to {project}!
    required_variables: ["name", "project"]

user_prompt_template: |
  {greeting_section}
  
  Your task is to...
```

Context:
```python
context = {
    "name": "Bob",
    "project": "Dashboard MVP",
    "greeting_section": "..."  # Automatically populated
}
```

### Conditional Sections

Use Python-style conditionals in context building:

```python
context = {
    "worker_name": "Alice",
    "has_messages": True,
    "message_section": "You have 3 new messages." if has_messages else ""
}
```

Template:
```yaml
user_prompt_template: |
  Worker: {worker_name}
  
  {message_section}
```

## Localization

### Creating Localized Templates

Create separate template files for each locale:

- `hourly_planning_en.yaml` - English version
- `hourly_planning_ko.yaml` - Korean version

**English Template**:
```yaml
name: "hourly_planning_en"
locale: "en"

system_prompt: |
  You are an operations coach. Generate plans in natural English.

user_prompt_template: |
  === SCHEDULED COMMUNICATIONS ===
  List any emails or chats to send.
```

**Korean Template**:
```yaml
name: "hourly_planning_ko"
locale: "ko"

system_prompt: |
  당신은 업무 코치입니다. 자연스러운 한국어로만 계획을 작성하세요.
  영어 단어나 표현을 절대 사용하지 마세요.

user_prompt_template: |
  === 예정된 커뮤니케이션 ===
  보낼 이메일이나 채팅을 나열하세요.
```

### Localization Best Practices

1. **Complete Translation**: Translate all text, including system prompts and validation rules
2. **Cultural Adaptation**: Adapt examples and terminology to local workplace culture
3. **Consistent Terminology**: Use consistent translations for technical terms
4. **Natural Language**: Avoid literal translations; use natural phrasing
5. **Format Preservation**: Keep the same structure and variable names

## Variants for A/B Testing

### Creating Variants

Variants allow testing different prompt strategies:

```yaml
name: "hourly_planning_en"
version: "1.0"

system_prompt: |
  Default system prompt.

user_prompt_template: |
  Default user prompt.

variants:
  - name: "verbose"
    description: "More detailed instructions"
    system_prompt: |
      You are an operations coach. Provide detailed, step-by-step plans.
    user_prompt_template: |
      Generate a comprehensive hourly plan with:
      1. Detailed task breakdown
      2. Time estimates for each subtask
      3. Dependencies and prerequisites
      4. Risk mitigation strategies
  
  - name: "concise"
    description: "Minimal instructions"
    system_prompt: |
      Generate brief, actionable plans.
    user_prompt_template: |
      Create a concise hourly plan. Be brief.
  
  - name: "structured"
    description: "Strict format requirements"
    user_prompt_template: |
      Generate plan in this exact format:
      
      ## Tasks
      - Task 1 (30 min)
      - Task 2 (45 min)
      
      ## Communications
      - Email to X at 10:00
```

### Variant Selection

The PromptManager automatically selects the best-performing variant based on:
- Success rate (70% weight)
- Token efficiency (20% weight)
- Generation speed (10% weight)

Manual selection:
```python
messages = prompt_manager.build_prompt(
    "hourly_planning_en",
    context,
    variant="verbose"
)
```

## Validation Rules

### Purpose

Validation rules document expected output characteristics for:
- Template documentation
- Output validation (future feature)
- Quality assurance

### Examples

```yaml
validation_rules:
  - "Must include scheduled communications section"
  - "Must use exact email addresses from team roster"
  - "Must include realistic time estimates (15-60 min per task)"
  - "Must not reference non-existent team members"
  - "Must follow format: 'Email at HH:MM to PERSON: Subject | Body'"
  - "Must include buffer time for interruptions"
  - "Must align with persona's working style"
```

## Best Practices

### 1. Clear Instructions

**Bad**:
```yaml
system_prompt: |
  Generate a plan.
```

**Good**:
```yaml
system_prompt: |
  You are an operations coach helping workers plan their next few hours.
  Generate realistic plans that:
  - Align with the worker's persona and skills
  - Include specific, actionable tasks
  - Account for communication overhead
  - Include buffer time for interruptions
```

### 2. Specific Examples

**Bad**:
```yaml
user_prompt_template: |
  Generate communications.
```

**Good**:
```yaml
user_prompt_template: |
  === SCHEDULED COMMUNICATIONS ===
  Format: "Email at HH:MM to PERSON: Subject | Body"
  Example: "Email at 10:30 to alice@company.com: Project Update | Quick status update on dashboard progress."
```

### 3. Context Awareness

**Bad**:
```yaml
user_prompt_template: |
  Generate a plan for the worker.
```

**Good**:
```yaml
user_prompt_template: |
  Worker: {worker_name} ({worker_role})
  Current Time: Tick {tick} ({formatted_time})
  Trigger: {context_reason}
  
  {persona_section}
  {team_roster_section}
  {project_section}
  
  Generate a plan considering:
  - Worker's current context and recent activities
  - Team availability and ongoing collaborations
  - Project deadlines and priorities
```

### 4. Consistent Formatting

Use consistent section headers and formatting across templates:

```yaml
# Standard section headers
=== YOUR PERSONA ===
=== TEAM ROSTER ===
=== PROJECT PLAN ===
=== SCHEDULED COMMUNICATIONS ===
=== RECENT EMAILS ===
```

### 5. Version Control

Update version numbers when making significant changes:

```yaml
# Initial version
version: "1.0"

# Minor improvements
version: "1.1"

# Major restructuring
version: "2.0"
```

## Testing Templates

### Manual Testing

```python
from virtualoffice.sim_manager.prompts.prompt_manager import PromptManager

# Load template
manager = PromptManager("templates/", locale="en")
template = manager.load_template("hourly_planning_en")

# Build prompt with test context
context = {
    "worker_name": "Test Worker",
    "worker_role": "Developer",
    "tick": 10,
    "context_reason": "test",
    "persona_markdown": "Test persona",
    "team_roster": "Team roster",
    "project_plan": "Project plan",
    "daily_plan": "Daily plan",
}

messages = manager.build_prompt("hourly_planning_en", context)
print(messages)
```

### Validation Testing

```python
# Validate context has all required variables
is_valid = manager.validate_context(template, context)
assert is_valid, "Context missing required variables"
```

### Output Testing

Generate actual output and verify it meets validation rules:

```python
from virtualoffice.sim_manager.planner import GPTPlanner

planner = GPTPlanner()
result = planner.generate_with_messages(messages)

# Check output meets validation rules
assert "Scheduled Communications" in result.content
assert "@" in result.content  # Has email addresses
```

## Common Patterns

### Multi-Project Context

```yaml
user_prompt_template: |
  You are working on multiple projects:
  
  {all_projects_section}
  
  Coordinate work across projects and communicate with relevant teams.

sections:
  all_projects_section:
    template: |
      {% for project in all_active_projects %}
      Project: {project.name}
      Team: {project.team_members}
      Status: {project.status}
      {% endfor %}
    required_variables: ["all_active_projects"]
```

### Event-Driven Planning

```yaml
user_prompt_template: |
  {% if has_new_messages %}
  === NEW MESSAGES ===
  {new_messages_summary}
  
  Respond to urgent messages and adjust your plan accordingly.
  {% endif %}
  
  {% if has_events %}
  === EVENTS ===
  {events_summary}
  
  React to these events and communicate with affected team members.
  {% endif %}
```

### Persona-Specific Instructions

```yaml
system_prompt: |
  You are generating a plan for {worker_name}, a {worker_role}.
  
  {% if persona.communication_style == "Direct" %}
  Keep communications brief and to the point.
  {% elif persona.communication_style == "Detailed" %}
  Provide comprehensive updates with context and reasoning.
  {% endif %}
  
  {% if persona.working_style == "Focused" %}
  Minimize context switching. Group similar tasks together.
  {% elif persona.working_style == "Flexible" %}
  Balance multiple priorities and be ready to adapt.
  {% endif %}
```

## Troubleshooting

### Missing Variables

**Error**: `KeyError: 'variable_name'`

**Solution**: Ensure all required variables are in context:

```python
# Check template requirements
template = manager.load_template("template_name")
print(template.sections["section_name"].required_variables)

# Provide all required variables
context = {
    "required_var_1": "value1",
    "required_var_2": "value2",
}
```

### Template Not Found

**Error**: `PromptTemplateError: Template 'name' not found`

**Solution**: Check template name and location:

```bash
# List available templates
ls templates/planning/
ls templates/reporting/
ls templates/events/

# Verify template name matches file name (without .yaml)
# File: hourly_planning_en.yaml
# Name in template: "hourly_planning_en"
```

### Poor Output Quality

**Solution**: Refine system prompt and add examples:

```yaml
system_prompt: |
  Generate realistic plans. DO NOT:
  - Use placeholder text like "TODO" or "TBD"
  - Reference non-existent team members
  - Include unrealistic time estimates
  
  DO:
  - Use specific, actionable language
  - Reference actual team members from roster
  - Include realistic time estimates (15-60 min per task)

user_prompt_template: |
  Example good plan:
  - Review pull request from alice@company.com (30 min)
  - Email at 10:30 to bob@company.com: Code Review | Reviewed your PR, looks good with minor comments.
  - Implement authentication feature (45 min)
  
  Now generate a plan for {worker_name}:
```

## Resources

- **Template Directory**: `src/virtualoffice/sim_manager/prompts/templates/`
- **PromptManager API**: `docs/modules/prompt_system.md`
- **Example Templates**: See existing templates in `templates/` directory
- **Testing Guide**: `tests/prompts/test_prompt_manager.py`

## Next Steps

1. Review existing templates in `templates/` directory
2. Create a new template following this guide
3. Test your template with sample context
4. Create variants for A/B testing
5. Monitor metrics to optimize performance
