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

**English Format**:
```
Email at 10:30 to dev@example.com cc pm@example.com: Subject | Body text
Chat at 14:00 with @designer: Message text
Reply at 11:00 to [email-123] cc team@example.com: Response subject | Response body
```

**Korean Format** (when `VDOS_LOCALE=ko`):
```
이메일 10:30에 dev@example.com 참조 pm@example.com: 제목 | 본문
채팅 14:00에 @designer과: 메시지 내용
답장 11:00에 [email-123] 참조 team@example.com: 답장 제목 | 답장 본문
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

### Korean Example Communications (Updated October 2025)

The planner now generates **Korean-only example communications** in hourly planning prompts when `VDOS_LOCALE=ko`. This eliminates English text pollution in Korean simulations.

**Implementation** (`planner.py` lines 562-614):

#### Group Chat vs DM Usage Guidelines (Korean)
```python
"그룹 채팅 vs 개인 메시지 사용 시기:",
"- '팀/프로젝트/그룹' 사용: 상태 업데이트, 차단 요소, 공지사항, 조정",
"- 개인 핸들 사용: 개인적인 질문, 민감한 피드백, 개인 확인",
```

#### Email Content Guidelines (Korean)
```python
"이메일 내용 가이드라인 (중요):",
"1. 이메일 길이: 최소 3-5문장으로 실질적인 이메일 본문 작성",
"   - 구체적인 세부사항, 맥락, 명확한 조치 사항 포함",
"   - 좋은 예시: '로그인 API 통합 작업 중입니다. OAuth 플로우와 사용자 세션 관리를 완료했습니다...'",
"   - 나쁜 예시: 'API 작업 업데이트. 진행 중입니다.'",
"",
"2. 제목에 프로젝트 맥락: 여러 프로젝트 작업 시 제목에 프로젝트 태그 포함",
"   - 형식: '[프로젝트명] 실제 제목'",
"   - 예시: '[모바일 앱 MVP] API 통합 상태 업데이트'",
"   - 예시: '[웹 대시보드] 디자인 리뷰 요청'",
"   - 업무 관련 이메일의 약 60-70%에 사용",
"",
"3. 이메일 현실성: 이메일을 자연스럽고 전문적으로 작성",
"   - 적절한 경우 맥락이나 인사말로 시작",
"   - 구체적인 기술 세부사항 또는 비즈니스 맥락 포함",
"   - 명확한 다음 단계 또는 질문으로 마무리",
"   - 커뮤니케이션 스타일을 다양화 (모든 이메일이 공식적일 필요는 없음)",
```

#### Correct Examples (Korean)
```python
"올바른 예시 (다음 패턴을 따르세요):",
"- 이메일 10:30에 colleague@example.dev 참조 manager@example.dev: 스프린트 업데이트 | 인증 모듈 완료, 리뷰 준비됨",
"- 채팅 11:00에 @colleague과: API 엔드포인트 관련 질문",
"- 채팅 11:00에 팀과: 스프린트 진행 상황 업데이트 (프로젝트 그룹 채팅으로 전송)",
"- 답장 14:00에 [email-42] 참조 lead@example.dev: RE: API 상태 | 업데이트 감사합니다, 통합 진행하겠습니다",
```

#### Wrong Examples (Korean)
```python
"잘못된 예시 (절대 하지 마세요):",
"- 이메일 10:30에 dev 참조 pm: ... (잘못됨 - 'dev'와 'pm'은 이메일 주소가 아닙니다!)",
"- 이메일 10:30에 team@company.dev: ... (잘못됨 - 배포 목록은 존재하지 않습니다!)",
"- 이메일 10:30에 all: ... (잘못됨 - 정확한 이메일 주소를 지정하세요!)",
"- 이메일 10:30에 김민수: ... (잘못됨 - 사람 이름이 아닌 이메일 주소를 사용하세요!)",
"- 이메일 10:30에 @colleague: ... (잘못됨 - @는 채팅용이며, 이메일 주소를 사용하세요!)",
```

**Impact**:
- GPT receives Korean-only examples and guidelines when generating hourly plans
- Eliminates mixed Korean/English content in simulations
- Ensures authentic Korean workplace communication patterns
- Provides detailed email content guidelines in Korean
- Clarifies group chat vs DM usage in Korean context
- Maintains consistency with Korean persona markdown and templates

**Related Changes**:
- `planner_mixin.py`: Also updated with locale-aware example generation
- See `agent_reports/20251029_PROMPT_LOCALIZATION_AUDIT.md` for comprehensive audit
- See `agent_reports/20251029_COMPREHENSIVE_KOREAN_LOCALIZATION_FIX.md` for complete details

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