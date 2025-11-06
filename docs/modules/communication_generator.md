# Communication Generator Module

**Module:** `src/virtualoffice/sim_manager/communication_generator.py`  
**Status:** Active (Implemented Nov 5, 2025)  
**Purpose:** GPT-powered fallback communication generation for improved content diversity

---

## Overview

The Communication Generator provides GPT-based generation of diverse, context-aware communications when JSON communications are not present in hourly plans. It builds on the JSON parser foundation (Nov 4, 2024) to improve content quality by replacing hardcoded templates with AI-generated messages that reflect persona roles, personalities, and current work context.

### Key Features

- **Context-Aware Generation**: Extracts context from hourly plans, daily plans, projects, inbox messages, and collaborators
- **Role-Specific Language**: Automatically adapts terminology based on persona role (developer, designer, QA, marketer, PM)
- **Multi-Locale Support**: Korean and English prompt generation with culturally appropriate communication styles
- **Flexible Output**: Generates 1-3 communications per call (emails and/or chat messages)
- **Robust Parsing**: Handles various JSON response formats including markdown code blocks
- **Deterministic Behavior**: Supports random seed for reproducible simulations

---

## Architecture

### Integration with Simulation Engine

```
Hourly Plan Generated
        ↓
JSON Parser (Nov 4)
        ↓
   JSON Found? ──No──→ Collect Fallback Request
        │                      ↓
       Yes              Add to Batch Queue
        │                      ↓
        │              [Continue Planning Loop]
        │                      ↓
        │              All Personas Planned?
        │                      ↓
        │              Process Batch (Async)
        │                      ↓
        │              Parallel GPT-4o-mini Calls
        │                      ↓
        └──────→ Schedule & Send Communications
```

**Batch Processing Workflow:**

**Phase 1: Collection** (during planning loop)
- Hourly plan does not contain JSON communications
- Participation balancer allows generation (prevents message dominance)
- Persona is within work hours and has collaborators
- **Request collected** instead of immediate processing

**Phase 2: Batch Processing** (after planning loop)
- All collected requests processed in parallel using `generate_batch_async()`
- Reduces total latency from N × 500ms to ~500ms
- Automatic fallback to synchronous if async fails

**Benefits:**
- **4-5x speedup** for teams with multiple personas
- **Non-blocking**: Tick advancement continues
- **Graceful degradation**: Falls back to synchronous on error

### Component Relationships

- **Planner**: Uses existing `Planner` instance for GPT API calls
- **PersonRead**: Receives persona information including role, personality, communication style
- **Engine**: Called by simulation engine during tick processing
- **Style Filter**: Generated communications pass through style filter when enabled

---

## Class: CommunicationGenerator

### Initialization

```python
def __init__(
    self,
    planner: Planner,
    locale: str = "ko",
    random_seed: int | None = None,
    enable_caching: bool = True
)
```

**Parameters:**
- `planner`: Planner instance for GPT API calls (reuses existing planner infrastructure)
- `locale`: Language locale - `"ko"` (Korean) or `"en"` (English)
- `random_seed`: Optional seed for deterministic random behavior
- `enable_caching`: Enable context caching for performance optimization (default: True)

**Example:**
```python
from virtualoffice.sim_manager.planner import Planner
from virtualoffice.sim_manager.communication_generator import CommunicationGenerator

planner = Planner(locale="ko")
generator = CommunicationGenerator(
    planner=planner,
    locale="ko",
    random_seed=42,
    enable_caching=True  # Enable performance optimization
)
```

---

## Core Methods

### generate_fallback_communications()

Main entry point for generating communications.

```python
def generate_fallback_communications(
    self,
    person: PersonRead,
    current_tick: int | None = None,
    hourly_plan: str | None = None,
    daily_plan: str | None = None,
    project: dict[str, Any] | None = None,
    inbox_messages: list[dict[str, Any]] | None = None,
    collaborators: Sequence[PersonRead] | None = None,
    model_hint: str | None = None
) -> list[dict[str, Any]]
```

**Parameters:**
- `person`: Persona generating communications (includes role, personality, communication_style)
- `current_tick`: Current simulation tick (for logging and metrics tracking)
- `hourly_plan`: Current hourly plan text (truncated to 500 chars)
- `daily_plan`: Daily plan summary (truncated to 300 chars)
- `project`: Project information dict with `project_name` and `project_summary`
- `inbox_messages`: Recent inbox messages (up to 5 most recent)
- `collaborators`: Team members for recipient selection
- `model_hint`: Optional model override (default: `"gpt-4o-mini"`)

**Returns:**
- List of communication dictionaries with structure:
  - Email: `{"type": "email", "to": [...], "subject": "...", "body": "...", "thread_id": "..."}`
  - Chat: `{"type": "chat", "target": "...", "message": "..."}`
- Empty list on error (with warning logs)

**Example:**
```python
communications = generator.generate_fallback_communications(
    person=developer_persona,
    current_tick=150,
    hourly_plan="API 엔드포인트 /auth/login 구현 중...",
    daily_plan="로그인 기능 개발",
    project={"project_name": "MobileApp", "project_summary": "모바일 앱 개발"},
    inbox_messages=[
        {"sender_name": "Designer", "subject": "목업 피드백", "message": "..."}
    ],
    collaborators=[designer_persona, qa_persona]
)

# Result: [
#   {
#     "type": "email",
#     "to": ["designer@example.com"],
#     "subject": "[MobileApp] 로그인 API 연동 완료",
#     "body": "안녕하세요! /auth/login 엔드포인트 연동 완료했습니다..."
#   }
# ]
```

---

## Internal Methods

### _build_context()

Extracts and formats context from available information.

**Key Features:**
- Truncates long text fields (hourly plan: 500 chars, daily plan: 300 chars, project summary: 200 chars)
- Formats inbox messages (up to 5 most recent, 50 char preview)
- Builds collaborator name list (excludes self)
- Handles None values gracefully

**Returns:** Dictionary with keys:
- `person`, `person_name`, `person_role`
- `current_work`, `daily_summary`
- `project_name`, `project_summary`
- `inbox`, `collaborators`, `locale`

---

### _build_korean_prompt() / _build_english_prompt()

Constructs locale-specific prompts for GPT.

**Role-Specific Guidance:**

| Role | Korean Terminology | English Terminology |
|------|-------------------|---------------------|
| Developer | API, 데이터베이스, 코드 리뷰, PR | API, database, code review, PR |
| Designer | 목업, UI/UX, 프로토타입, 레이아웃 | mockup, UI/UX, prototype, layout |
| QA | 테스트 케이스, 버그, 회귀 테스트 | test case, bug, regression test |
| Marketer | 캠페인, CTR, 전환율, 성과 | campaign, CTR, conversion rate |
| PM | 마일스톤, 타임라인, 이해관계자 | milestone, timeline, stakeholder |

**Prompt Structure:**
1. **System Message**: Persona identity, role, personality, communication style, role-specific guidance
2. **User Message**: Current work, project context, inbox messages, team members, output format instructions

**Output Format:** JSON with `communications` array containing email/chat objects

---

### _parse_gpt_response()

Robust JSON parsing with multiple fallback strategies.

**Handles:**
- Raw JSON objects
- JSON in markdown code blocks (` ```json ... ``` `)
- JSON with surrounding text
- Both dict with `communications` key and direct list format

**Validation:**
- Ensures emails have `to`, `subject`, `body` fields
- Ensures chats have `target`, `message` fields
- Converts string `to` field to list format
- Skips invalid communications with warning logs

**Error Handling:**
- Returns empty list on JSON parse errors
- Logs warnings with response preview (first 200 chars)
- Graceful degradation on unexpected structures

---

## Prompt Engineering

### Korean Prompt Guidelines

```
지침:
1. 역할에 맞는 자연스러운 언어 사용
2. 구체적인 작업이나 산출물 언급
3. 받은 메시지가 있으면 답장 고려 (thread_id 사용)
4. 프로젝트 이름을 제목에 포함 (예: [프로젝트명] 제목)
5. 다양한 메시지 유형 사용 (질문, 요청, 업데이트, 확인 등)
```

### English Prompt Guidelines

```
Guidelines:
1. Use natural language appropriate for your role
2. Mention specific tasks or deliverables
3. Consider replying to received messages (use thread_id)
4. Include project name in subject (e.g., [ProjectName] Subject)
5. Use varied message types (question, request, update, acknowledgment, etc.)
```

---

## Performance Characteristics

### Token Usage

**Per Generation Call:**
- System message: ~200 tokens
- User message (context): ~300-500 tokens
- GPT response: ~150-300 tokens
- **Total: ~650-1000 tokens per call**

**Cost (GPT-4o-mini):**
- Input: $0.15 per 1M tokens
- Output: $0.60 per 1M tokens
- **Per call: ~$0.00024**
- **1000 calls: ~$0.24**

### Latency

**Synchronous Generation:**
- GPT-4o-mini response time: 500-1000ms
- Blocks tick advancement until complete
- Acceptable for small teams (3-5 personas)

**Async Generation (Optimized):**
- GPT-4o-mini response time: 500-1000ms (same)
- Non-blocking: tick continues while GPT processes
- Recommended for medium-large teams (6+ personas)
- Latency impact: 2-5% vs. 5-8% for synchronous

**Batch Processing:**
- Parallel processing for multiple personas
- Total latency: ~500ms for N personas (vs. N × 500ms sequential)
- Speedup: ~N× for large teams
- Recommended for 10+ personas

### Context Caching

**Performance Impact:**
- Context building: <1ms (cached) vs. 5-10ms (uncached)
- Cache hit rate: 80-90% for stable simulations
- Memory overhead: <1KB per project, <100 bytes per team
- Recommended: Always enabled (default)

### Frequency

**Typical Usage:**
- Only called when JSON communications absent (~30-40% of hourly plans)
- Subject to participation balancing (prevents message dominance)
- Estimated: 2-3 calls per tick for 13-person team

### Performance Targets

- ✅ Tick latency increase: <10% (R-10.3)
- ✅ Context extraction: <10ms per message (R-10.2)
- ✅ Memory footprint: <5MB for template pools
- ✅ Verified via benchmark: `.tmp/benchmark_communication_diversity.py`

---

## Error Handling

### PlanningError

Caught from `planner.generate_with_messages()` call:
- Logs warning with persona name and error details
- Returns empty list (simulation continues)
- Includes stack trace in logs

### JSON Parse Errors

Multiple fallback strategies before giving up:
1. Try raw JSON parsing
2. Extract from markdown code blocks
3. Find first `{` and last `}`
4. Validate structure and required fields

### Unexpected Errors

Catch-all exception handler:
- Logs error with full stack trace
- Returns empty list
- Prevents simulation crash

---

## Integration Points

### With Simulation Engine

The engine uses **batch processing** for optimal performance:

**Phase 1: Collection** (during planning loop)
```python
# In engine.py - Collect fallback requests
fallback_requests = []
for person in people:
    if not json_comms and participation_balancer.should_generate_fallback(...):
        fallback_requests.append({
            "person": person,
            "hourly_plan": hourly_summary,
            "daily_plan": daily_summary,
            "project": person_project,
            "inbox_messages": inbox_messages,
            "collaborators": recipients,
            "current_tick": status.current_tick,
            "day_index": day_index
        })
```

**Phase 2: Batch Processing** (after planning loop)
```python
# Process all requests in parallel using async batch
if fallback_requests:
    logger.info(f"[GPT_FALLBACK_BATCH] Processing {len(fallback_requests)} fallback requests")
    
    try:
        # Async batch processing (parallel GPT calls)
        batch_results = await communication_generator.generate_batch_async(fallback_requests)
        
        # Process results
        for person, generated_comms in batch_results:
            if generated_comms:
                self._process_json_communications(generated_comms, current_tick, person, source="fallback")
                self._dispatch_scheduled(person, current_tick, people_by_id)
                # Record for participation balancing
                participation_balancer.record_message(person.id, day_index, channel)
    
    except Exception as e:
        # Fallback to synchronous processing if async fails
        logger.warning(f"Batch processing failed: {e}, falling back to synchronous")
        for req in fallback_requests:
            communications = communication_generator.generate_fallback_communications(...)
            # Process synchronously
```

**Benefits:**
- **4-5x speedup** for teams with multiple personas needing fallback
- **Non-blocking**: Tick advancement continues while GPT processes
- **Graceful degradation**: Falls back to synchronous if async fails
- **Automatic**: No configuration needed, works out of the box

### With Style Filter

Generated communications pass through existing style filter:
- Respects `VDOS_STYLE_FILTER_ENABLED` setting
- Applies per-persona `style_filter_enabled` flag
- Transforms subject/body for emails, message for chats
- Records metrics (token usage, latency, success rate)

### With Planner

Reuses existing planner infrastructure:
- Calls `planner.generate_with_messages()` method
- Uses same API key configuration (OpenAI API Key 1)
- Respects model hints and temperature settings
- Tracks token usage via `PlanResult.tokens_used`

---

## Configuration

### Environment Variables

**New Variables (Proposed):**
- `VDOS_GPT_FALLBACK_ENABLED` (boolean, default: true) - Enable/disable GPT fallback generation
- `VDOS_FALLBACK_PROBABILITY` (float 0.0-1.0, default: 0.6) - Base probability for generating fallback
- `VDOS_FALLBACK_MODEL` (string, default: "gpt-4o-mini") - Model for fallback generation

**Existing Variables (Used):**
- `OPENAI_API_KEY` - Required for GPT calls
- `VDOS_STYLE_FILTER_ENABLED` - Applied to generated communications
- `VDOS_LOCALE_TZ` - Determines locale for prompt selection

---

## Logging

### Log Levels

**INFO:**
- Initialization with locale and seed
- Generation start with persona name, tick, locale, and model
- Generation completion with count, tick, token usage, latency, and model

**WARNING:**
- GPT planning errors (with tick, latency, and exception info)
- JSON parse failures (with response preview)
- Invalid communication structures (missing fields)
- Unknown communication types

**ERROR:**
- Unexpected errors during generation (with tick, latency, and full stack trace)

**DEBUG:**
- Context building details (if enabled)
- Prompt construction steps (if enabled)

### Example Log Output

**Batch Processing (Typical):**
```
INFO: CommunicationGenerator initialized with locale=ko, seed=42
INFO: [GPT_FALLBACK_BATCH] Processing 3 fallback requests
INFO: [GPT_FALLBACK_BATCH] Processing 2 generated communications for 김개발 (tick=150)
INFO: [GPT_FALLBACK_BATCH] Processing 1 generated communications for 이디자인 (tick=150)
DEBUG: GPT fallback batch generated no communications for 박QA
```

**Synchronous Fallback (Error Case):**
```
WARNING: [GPT_FALLBACK_BATCH] Batch processing failed: Connection timeout, falling back to synchronous
INFO: [GPT_FALLBACK] Generating communications for 김개발 (tick=150, locale=ko, model=gpt-4o-mini)
INFO: [GPT_FALLBACK] Generated 2 communications for 김개발 (tick=150, tokens=847, latency=652.3ms, model=gpt-4o-mini)
WARNING: [GPT_FALLBACK] Planning error for 이디자인 (tick=150, latency=234.5ms): API rate limit exceeded
```

**Individual Processing (Legacy/Manual):**
```
INFO: [GPT_FALLBACK] Generating communications for 김개발 (tick=150, locale=ko, model=gpt-4o-mini)
INFO: [GPT_FALLBACK] Generated 2 communications for 김개발 (tick=150, tokens=847, latency=652.3ms, model=gpt-4o-mini)
WARNING: Email missing required fields: dict_keys(['type', 'subject', 'body'])
```

### Enhanced Logging Features

**Structured Logging:**
- Batch operations prefixed with `[GPT_FALLBACK_BATCH]` for easy filtering
- Individual operations prefixed with `[GPT_FALLBACK]`
- Tick tracking enables correlation with simulation state
- Latency metrics (in milliseconds) for performance monitoring
- Model tracking for cost analysis and optimization

**Performance Monitoring:**
- Latency measured from start to completion (including GPT call and parsing)
- Token usage tracked for cost estimation
- Error latency tracked even on failures for timeout detection
- Enables identification of slow generations and bottlenecks

**Observability:**
- Logs can be parsed for metrics dashboards
- Tick correlation enables timeline reconstruction
- Model tracking supports A/B testing different GPT models
- Latency tracking helps identify performance regressions

---

## Testing

### Unit Tests

Located in `tests/test_communication_generator.py`:

- `test_init()` - Initialization with various parameters
- `test_build_context()` - Context extraction from various inputs
- `test_build_korean_prompt()` - Korean prompt structure
- `test_build_english_prompt()` - English prompt structure
- `test_parse_gpt_response()` - JSON parsing with various formats
- `test_generate_fallback_communications()` - End-to-end generation (mocked)

### Integration Tests

- Test with real GPT API (requires API key)
- Verify role-specific language in generated messages
- Check message diversity across multiple calls
- Validate threading and project context inclusion

### Quality Validation

**Script:** `.tmp/test_quality_validation_gpt.py`

Uses GPT-4o as an expert evaluator to assess the quality of generated communications:

#### Realism Evaluation
- Samples 50 random messages from simulation database
- GPT-4o rates each message on 1-10 scale for workplace realism
- Provides score distribution and sample evaluations
- **Target:** Average score ≥7.5/10

**Scoring Criteria:**
- 10: Indistinguishable from real workplace communication
- 8-9: Very realistic with minor artificial patterns
- 6-7: Mostly realistic but with some template-like qualities
- 4-5: Somewhat realistic but clearly generated
- 1-3: Unrealistic, repetitive, or obviously templated

#### Role Identification
- GPT-4o attempts to identify sender's role from message content alone
- Tests if role-specific vocabulary is being used effectively
- Calculates accuracy by comparing predicted vs. actual roles
- **Target:** Accuracy ≥75%

**Evaluated Roles:**
- Developer/Engineer (개발자): Technical terms, code references, API discussions
- Designer (디자이너): Visual design, UI/UX, mockups, prototypes
- QA/Tester (QA): Testing, bugs, test cases, quality assurance
- Marketer (마케터): Campaigns, metrics, CTR, conversion rates
- Manager/PM (매니저): Coordination, timelines, stakeholders, planning

#### Running Quality Validation
```bash
# Ensure simulation has generated messages
briefcase dev
# Run simulation to generate at least 50 messages

# Run quality validation
python .tmp/test_quality_validation_gpt.py

# Expected duration: 2-3 minutes
# Expected cost: ~$0.02 (GPT-4o token usage)
```

#### Example Output
```
================================================================================
Task 8.8: Quality Validation with GPT Evaluation
================================================================================

Sampling 50 random messages from simulation...
Sampled 50 messages:
  - 35 emails
  - 15 chat messages

--------------------------------------------------------------------------------
1. REALISM EVALUATION
--------------------------------------------------------------------------------
Average Realism Score: 7.82/10
Target: ≥7.5/10
Status: ✅ PASS

Score Distribution:
   9/10: ████████ (8)
   8/10: ████████████ (12)
   7/10: ██████████ (10)

--------------------------------------------------------------------------------
2. ROLE IDENTIFICATION
--------------------------------------------------------------------------------
Role Identification Accuracy: 78.0%
Target: ≥75%
Status: ✅ PASS

================================================================================
OVERALL RESULTS
================================================================================
Realism Score: 7.82/10 (target: ≥7.5) ✅
Role Accuracy: 78.0% (target: ≥75%) ✅

✅ ALL QUALITY TARGETS MET
```

#### Use Cases
- **Quality Assurance**: Validate communication diversity improvements
- **Regression Testing**: Ensure quality doesn't degrade with changes
- **Benchmarking**: Compare different generation approaches
- **A/B Testing**: Evaluate template-based vs. GPT-generated messages
- **Continuous Monitoring**: Track quality metrics over time

#### Token Usage
- Realism Evaluation: ~3000 tokens (50 messages)
- Role Identification: ~3000 tokens (50 messages)
- Total: ~6000 tokens per run (~$0.02 per run)

---

## Performance Optimization (Implemented)

### Async Generation

**Method:** `generate_fallback_communications_async()`

```python
async def generate_fallback_communications_async(
    self,
    person: PersonRead,
    current_tick: int | None = None,
    hourly_plan: str | None = None,
    daily_plan: str | None = None,
    project: dict[str, Any] | None = None,
    inbox_messages: list[dict[str, Any]] | None = None,
    collaborators: Sequence[PersonRead] | None = None,
    model_hint: str | None = None
) -> list[dict[str, Any]]
```

**Features:**
- Non-blocking GPT calls using `asyncio.run_in_executor()`
- Tick advancement continues while GPT processes
- Same interface as synchronous version
- Maintains determinism and logging

**Usage:**
```python
# Async generation
communications = await generator.generate_fallback_communications_async(
    person=persona,
    current_tick=150,
    hourly_plan=plan,
    project=project,
    collaborators=team
)
```

### Batch Processing

**Method:** `generate_batch_async()`

```python
async def generate_batch_async(
    self,
    requests: list[dict[str, Any]]
) -> list[tuple[PersonRead, list[dict[str, Any]]]]
```

**Features:**
- Parallel processing for multiple personas
- Reduces total latency from N × 500ms to ~500ms
- Maintains per-persona error handling
- Recommended for teams of 10+ personas
- **Automatically used by engine** during planning phase

**Engine Integration:**
The simulation engine automatically collects fallback requests during the planning loop and processes them in batch:

```python
# In engine.py - PHASE 3: Collect fallback requests
fallback_requests = []
for person in people:
    if should_generate_fallback:
        fallback_requests.append({
            "person": person,
            "hourly_plan": hourly_summary,
            "daily_plan": daily_summary,
            "project": person_project,
            "inbox_messages": inbox_messages,
            "collaborators": recipients,
            "current_tick": status.current_tick,
            "day_index": day_index
        })

# PHASE 4: Process all requests in batch (async)
if fallback_requests:
    batch_results = await generator.generate_batch_async(fallback_requests)
    for person, communications in batch_results:
        # Process and dispatch communications
        pass
```

**Manual Usage:**
```python
# Prepare batch requests
requests = [
    {
        "person": persona1,
        "current_tick": 100,
        "hourly_plan": plan1,
        "project": project,
        "collaborators": team
    },
    {
        "person": persona2,
        "current_tick": 100,
        "hourly_plan": plan2,
        "project": project,
        "collaborators": team
    }
]

# Generate in parallel
results = await generator.generate_batch_async(requests)

# Process results
for person, communications in results:
    # Handle communications for each person
    pass
```

**Fallback Behavior:**
If async batch processing fails, the engine automatically falls back to synchronous processing:
```python
except Exception as e:
    logger.warning(f"Batch processing failed: {e}, falling back to synchronous")
    # Process each request synchronously
    for req in fallback_requests:
        communications = generator.generate_fallback_communications(...)
```

### Context Caching

**Features:**
- Caches project information by project ID
- Caches collaborator names by team composition
- Reduces context building from 5-10ms to <1ms
- Minimal memory overhead (<1KB per project)

**Cache Management:**
```python
# Clear cache when project/team changes
generator.clear_cache()

# Disable caching (not recommended)
generator = CommunicationGenerator(
    planner=planner,
    locale="ko",
    enable_caching=False
)
```

### Performance Benchmarking

**Script:** `.tmp/benchmark_communication_diversity.py`

**Measures:**
- Baseline tick latency (features disabled)
- Optimized tick latency (features enabled)
- Statistical analysis (mean, median, P95, P99)
- Verification of <10% increase threshold

**Run Benchmark:**
```bash
python .tmp/benchmark_communication_diversity.py
```

## Future Enhancements

### Phase 3 (Proposed)

- **Adaptive Batching**: Automatically batch based on team size
- **Smart Cache Eviction**: LRU cache with configurable size limits
- **Performance Profiling**: Built-in profiling tools for optimization
- **Quality Metrics**: Track realism scores, role differentiation accuracy
- **A/B Testing**: Compare GPT-generated vs template-based communications
- **Custom Prompts**: Per-project or per-persona prompt customization

---

## Related Documentation

- [Planner Module](planner.md) - GPT API integration and planning infrastructure
- [Communication Style Filter](communication_style_filter.md) - Post-generation style transformation
- [Communication Hub](communication_hub.md) - Message routing and delivery
- [Simulation Engine](../architecture.md#simulation-engine) - Tick processing and orchestration
- [Localization](localization.md) - Multi-language support

---

## References

- **Spec**: `.kiro/specs/communication-diversity/requirements.md`
- **Design**: `.kiro/specs/communication-diversity/design_v2.md`
- **Tasks**: `.kiro/specs/communication-diversity/tasks.md`
- **Implementation Report**: `agent_reports/20251105_task1_communication_generator_implementation.md`
- **JSON Parser**: Implemented Nov 4, 2024 (foundation for this module)

---

**Last Updated:** November 5, 2025  
**Status:** Task 1 Complete - Core infrastructure implemented and tested
