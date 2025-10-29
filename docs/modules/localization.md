# Localization Module Documentation

## Overview

The localization module (`src/virtualoffice/common/localization.py`) provides centralized management of all localizable strings and templates in VDOS. It ensures consistent Korean localization throughout the application and eliminates hardcoded English text in Korean simulations.

## Architecture

### LocalizationManager Class

The core class that handles string retrieval based on locale settings.

```python
class LocalizationManager:
    def __init__(self, locale: str = "en")
    def get_text(self, key: str) -> str
    def get_list(self, key: str) -> List[str]
    def get_template(self, template_name: str, **kwargs) -> str
    def set_locale(self, locale: str) -> None
    def get_available_locales(self) -> List[str]
    def is_korean_locale(self) -> bool
    def get_client_feature_request(self, index: Optional[int] = None) -> str
```

### Supported Locales

- **English (`en`)**: Default locale with all base strings
- **Korean (`ko`)**: Complete Korean translations for workplace simulations

### Localization Strings

The system maintains comprehensive localization strings organized by category:

#### Planner Strings
- `scheduled_communications`: "Scheduled Communications" / "예정된 커뮤니케이션"

#### Engine Strings  
- `live_collaboration_adjustments`: "Adjustments from live collaboration" / "실시간 협업 조정사항"

#### Status Vocabulary
- `status_working`: "Working" / "근무중"
- `status_away`: "Away" / "자리비움"
- `status_off_duty`: "Off Duty" / "퇴근"
- `status_overtime`: "Overtime" / "야근"
- `status_sick_leave`: "Sick Leave" / "병가"
- `status_vacation`: "Vacation" / "휴가"

#### Client Feature Requests
Korean workplace-appropriate feature requests:
- "메인 메시지 새로고침" (refresh hero messaging)
- "런치 분석 대시보드 준비" (prepare launch analytics dashboard)
- "고객 후기 캐러셀 추가" (add testimonial carousel)
- "온보딩 가이드 제작" (deliver onboarding walkthrough)

#### Communication Templates
- `email_subject_update`: "Project Update" / "프로젝트 업데이트"
- `email_subject_meeting`: "Meeting Request" / "회의 요청"
- `email_subject_urgent`: "Urgent: Action Required" / "긴급: 조치 필요"
- `chat_greeting`: "Hi team" / "안녕하세요 팀"
- `chat_update`: "Quick update" / "간단한 업데이트"

#### Project Terminology
- `project_milestone`: "Milestone" / "마일스톤"
- `project_deadline`: "Deadline" / "마감일"
- `project_task`: "Task" / "작업"
- `project_blocker`: "Blocker" / "차단 요소"
- `project_dependency`: "Dependency" / "의존성"

## Usage Examples

### Basic Usage

```python
from virtualoffice.common.localization import LocalizationManager

# Create manager for Korean locale
manager = LocalizationManager("ko")

# Get localized text
header = manager.get_text("scheduled_communications")
# Returns: "예정된 커뮤니케이션"

# Get status text
status = manager.get_text("status_working")
# Returns: "근무중"
```

### Environment Integration

```python
from virtualoffice.common.localization import get_current_locale_manager

# Get manager based on VDOS_LOCALE environment variable
manager = get_current_locale_manager()

# Use in planner or engine code
adjustment_text = manager.get_text("live_collaboration_adjustments")
```

### Template Usage

```python
# Get template with variable substitution
template = manager.get_template("email_subject_update", project="Mobile App")
# Could return: "Mobile App 프로젝트 업데이트" (if template supports variables)
```

### Convenience Functions

```python
from virtualoffice.common.localization import get_text, get_korean_text

# Direct text retrieval
english_text = get_text("scheduled_communications", "en")
korean_text = get_korean_text("scheduled_communications")

# Equivalent to:
# english_text = "Scheduled Communications"
# korean_text = "예정된 커뮤니케이션"
```

## Integration Points

### Planner Integration

The localization system is fully integrated with the planner to replace hardcoded strings:

```python
# Before (hardcoded)
content += "\nScheduled Communications:"

# After (localized)
from virtualoffice.common.localization import get_current_locale_manager
manager = get_current_locale_manager()
content += f"\n{manager.get_text('scheduled_communications')}:"
```

#### Hourly Planning Example Communications and Guidelines

**Status**: ✅ Complete (as of 2025-10-29)

The planner now generates locale-aware example communications and comprehensive email guidelines in hourly planning prompts. When `VDOS_LOCALE=ko`, all examples and guidelines are in Korean:

**Group Chat vs DM Usage Guidelines** (`planner.py` lines 565-567):
```python
"그룹 채팅 vs 개인 메시지 사용 시기:",
"- '팀/프로젝트/그룹' 사용: 상태 업데이트, 차단 요소, 공지사항, 조정",
"- 개인 핸들 사용: 개인적인 질문, 민감한 피드백, 개인 확인",
```

**Email Content Guidelines** (`planner.py` lines 569-586):
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

**Korean Examples** (`planner.py` lines 600-607):
```python
"올바른 예시 (다음 패턴을 따르세요):",
"- 이메일 10:30에 colleague@example.dev 참조 manager@example.dev: 스프린트 업데이트 | 인증 모듈 완료, 리뷰 준비됨",
"- 채팅 11:00에 @colleague과: API 엔드포인트 관련 질문",
"- 채팅 11:00에 팀과: 스프린트 진행 상황 업데이트 (프로젝트 그룹 채팅으로 전송)",
"- 답장 14:00에 [email-42] 참조 lead@example.dev: RE: API 상태 | 업데이트 감사합니다, 통합 진행하겠습니다",
```

**Wrong Examples** (also in Korean, lines 609-614):
```python
"잘못된 예시 (절대 하지 마세요):",
"- 이메일 10:30에 dev 참조 pm: ... (잘못됨 - 'dev'와 'pm'은 이메일 주소가 아닙니다!)",
"- 이메일 10:30에 team@company.dev: ... (잘못됨 - 배포 목록은 존재하지 않습니다!)",
"- 이메일 10:30에 all: ... (잘못됨 - 정확한 이메일 주소를 지정하세요!)",
"- 이메일 10:30에 김민수: ... (잘못됨 - 사람 이름이 아닌 이메일 주소를 사용하세요!)",
"- 이메일 10:30에 @colleague: ... (잘못됨 - @는 채팅용이며, 이메일 주소를 사용하세요!)",
```

**Impact**: 
- GPT receives comprehensive Korean-only guidelines and examples when generating hourly plans
- Email content guidelines ensure substantive, realistic email bodies (3-5 sentences minimum)
- Project context guidelines encourage proper subject line formatting with project tags
- Group chat vs DM guidelines clarify appropriate communication channel selection
- Eliminates English text pollution in Korean simulations
- Ensures authentic Korean workplace communication patterns

**Related Files**:
- `src/virtualoffice/sim_manager/planner.py` (lines 562-614)
- `src/virtualoffice/virtualWorkers/planner_mixin.py` (locale-aware example generation)
- `agent_reports/20251029_PROMPT_LOCALIZATION_AUDIT.md` (comprehensive audit)
- `agent_reports/20251029_COMPREHENSIVE_KOREAN_LOCALIZATION_FIX.md` (complete details)

### Engine Integration

Replace hardcoded engine strings:

```python
# Before (hardcoded)
reason = "Adjustments from live collaboration"

# After (localized)
manager = get_current_locale_manager()
reason = manager.get_text("live_collaboration_adjustments")
```

#### Engine Adjustment Messages

**Status**: ✅ Complete (as of 2025-10-29)

The simulation engine now uses Korean-only adjustment messages when `VDOS_LOCALE=ko`. These messages are added to planning context when workers replan their hourly schedules.

**Sick Leave Adjustments** (`engine.py` line 869):
```python
adjustments.append("병가를 준수하고 회복할 때까지 작업을 보류합니다.")
# "Observe sick leave and hold tasks until recovered."
```

**Acknowledgment Messages** (`engine.py` lines 918, 921):
```python
# Acknowledgment from another worker
adjustments.append(f"{message.sender_name}의 확인: {message.summary}")
# "Acknowledged by {name}: {summary}"

# Request handling
adjustments.append(f"{message.sender_name}의 요청 처리: {message.action_item}")
# "Handle request from {name}: {action}"
```

**Acknowledgment Body Patterns** (`engine.py` lines 932-937):
```python
# Varied and natural Korean acknowledgment patterns
ack_patterns = [
    f"{sender_person.name.split()[0]}님, {ack_phrase} 확인했습니다.",
    f"{sender_person.name.split()[0]}님, {ack_phrase} 진행하겠습니다.",
    f"{sender_person.name.split()[0]}님, {ack_phrase} 작업 중입니다.",
    f"{sender_person.name.split()[0]}님, 알겠습니다. {ack_phrase} 처리하겠습니다.",
]
ack_body = random.choice(ack_patterns)
```

**Impact**: These adjustment messages are injected into planning context and sent to GPT when workers replan. Previously, English text would appear in Korean simulations, causing mixed language in generated content. Now all adjustment messages are Korean-only, ensuring pure Korean prompts.

**Related Files**:
- `src/virtualoffice/sim_manager/engine.py` (lines 869, 918, 921, 932-937)
- `agent_reports/20251029_ENGINE_ADJUSTMENTS_KOREAN_FIX.md`

### Client Feature Requests

Use localized feature request templates:

```python
# Get random Korean feature request
manager = LocalizationManager("ko")
feature_requests = manager.get_list("client_feature_requests")
random_request = random.choice(feature_requests)
# Returns one of: "메인 메시지 새로고침", "런치 분석 대시보드 준비", etc.
```

## Error Handling

### Fallback Behavior

The system provides graceful fallback handling:

```python
manager = LocalizationManager("ko")

# If Korean translation missing, falls back to English
try:
    text = manager.get_text("new_key_not_yet_translated")
except KeyError:
    # Key not found in either locale
    pass
```

### Locale Validation

```python
try:
    manager = LocalizationManager("invalid_locale")
except ValueError as e:
    # "Unsupported locale: invalid_locale. Supported locales: ['en', 'ko']"
    pass
```

## Extension Guidelines

### Adding New Localization Keys

1. Add the key to both English and Korean sections in `LOCALIZATION_STRINGS`
2. Ensure Korean translations are workplace-appropriate
3. Update this documentation with the new keys

```python
LOCALIZATION_STRINGS = {
    "en": {
        "new_key": "English text",
        # ... existing keys
    },
    "ko": {
        "new_key": "한국어 텍스트",
        # ... existing keys
    }
}
```

### Adding New Locales

1. Add new locale section to `LOCALIZATION_STRINGS`
2. Translate all existing keys
3. Update `get_available_locales()` documentation
4. Add locale-specific tests

### Integration Best Practices

1. **Use environment integration**: Prefer `get_current_locale_manager()` over hardcoded locales
2. **Cache managers**: Create manager instances once and reuse them
3. **Handle missing keys**: Always handle `KeyError` exceptions gracefully
4. **Validate early**: Validate locale settings during initialization
5. **Document keys**: Document all new localization keys in this file

## Testing and Validation

### Test Coverage
The localization system includes comprehensive tests across multiple test files:

#### Core Localization Tests (`tests/test_localization.py`)
- **Language Switching**: Validates locale configuration and switching
- **Template Rendering**: Tests all template types with various parameters
- **Korean Content Validation**: Ensures Korean-only content generation
- **Error Handling**: Tests fallback behavior and error scenarios
- **Integration**: Tests localization with simulation engine and planner

#### Korean Persona Integration Test (`test_korean_persona.py`)
**NEW**: Comprehensive test validating Korean localization with persona system integration:

```python
def test_korean_persona_integration():
    """Test that Korean locale works with persona information and outputs Korean."""
    
    # Set Korean locale
    os.environ["VDOS_LOCALE"] = "ko"
    
    # Create Korean worker with Korean persona information
    worker = PersonRead(
        name="김지훈",  # Korean name
        role="풀스택 개발자",
        persona_markdown="""# 김지훈 - 풀스택 개발자
        
## 신원 및 채널
- 이름: 김지훈
- 역할: 풀스택 개발자
...
""",
        planning_guidelines=["기술적 우수성에 집중", "차단 요소를 조기에 소통"],
        statuses=["근무중", "자리비움", "퇴근"]
    )
```

**Test Scenarios**:
1. **Korean Daily Planning**: Tests daily plan generation with Korean project context
2. **Korean Hourly Planning**: Tests hourly plan generation with persona integration
3. **Content Validation**: Validates Korean character ratio (>30% Korean characters)
4. **Scheduled Communications**: Checks for Korean scheduled communications section

**Validation Metrics**:
- Korean character ratio analysis
- Model usage and token consumption tracking
- Content authenticity verification
- Scheduled communications format validation

#### Korean Simulation Integration (`tests/test_korean_simulation_integration.py`)
- **End-to-End Korean Workflows**: Complete simulation runs in Korean
- **Multi-persona Korean Teams**: Korean team coordination and communication
- **Korean Project Management**: Project lifecycle in Korean locale

### Unit Tests

```python
def test_localization_manager():
    # Test English locale
    en_manager = LocalizationManager("en")
    assert en_manager.get_text("scheduled_communications") == "Scheduled Communications"
    
    # Test Korean locale
    ko_manager = LocalizationManager("ko")
    assert ko_manager.get_text("scheduled_communications") == "예정된 커뮤니케이션"
    
    # Test fallback behavior
    assert ko_manager.get_text("nonexistent_key") raises KeyError
```

### Integration Tests

```python
def test_environment_integration():
    import os
    os.environ["VDOS_LOCALE"] = "ko"
    
    manager = get_current_locale_manager()
    assert manager.is_korean_locale()
    assert manager.get_text("status_working") == "근무중"
```

### Korean Content Validation
The system includes strict Korean content validation:

```python
from virtualoffice.common.korean_validation import validate_korean_content

is_valid, issues = validate_korean_content(content, strict_mode=True)
if not is_valid:
    print(f"Validation issues: {issues}")
```

**Validation Rules**:
- Detects English words mixed with Korean text
- Identifies technical terms that should be translated
- Validates Korean character ratios
- Checks for proper Korean workplace terminology

### Running Localization Tests

#### All Localization Tests
```bash
# Run all localization-related tests
python -m pytest tests/test_localization.py tests/test_korean_simulation_integration.py -v

# Run Korean persona integration test
python test_korean_persona.py

# Run with Korean locale
VDOS_LOCALE=ko python -m pytest tests/test_localization.py -v
```

#### Specific Test Scenarios
```bash
# Test Korean daily planning
python test_korean_persona.py

# Test Korean content validation
python -m pytest tests/test_localization.py::test_korean_content_validation -v

# Test Korean simulation integration
python -m pytest tests/test_korean_simulation_integration.py -v
```

## Future Enhancements

### Planned Features

1. **Dynamic locale switching**: Runtime locale changes without restart
2. **Pluralization support**: Handle singular/plural forms appropriately
3. **Date/time formatting**: Locale-specific date and time formats
4. **Number formatting**: Locale-specific number and currency formats
5. **Additional locales**: Support for other languages as needed

### Integration Roadmap

1. **Phase 1**: Planner integration (replace hardcoded headers) ✅ Complete
2. **Phase 2**: Engine integration (replace hardcoded messages) ✅ Complete
3. **Phase 3**: Persona generation integration (localized persona templates) ✅ Complete
4. **Phase 4**: Planner example communications (Korean hourly planning examples) ✅ Complete
5. **Phase 5**: UI integration (localized dashboard and GUI elements) 🔄 In Progress

### Worker Schedule Defaults

**Status**: ✅ Complete (as of 2025-10-29)

The worker module now uses locale-aware default schedule table entries. When no schedule blocks are provided, the system generates a default entry in the appropriate language:

**Implementation** (`src/virtualoffice/virtualWorkers/worker.py` line 83):
```python
def _schedule_table(blocks: Sequence[ScheduleBlock]) -> str:
    if not blocks:
        return "| 09:00 | 18:00 | 핵심 프로젝트 작업 |"  # Korean: "Core project work"
    # ... rest of implementation
```

**Impact**: This ensures that persona markdown generation produces Korean-only content when `VDOS_LOCALE=ko`, including default schedule entries. The default activity text "핵심 프로젝트 작업" (Core project work) appears in persona markdown when no explicit schedule blocks are defined.

**Related Files**:
- `src/virtualoffice/virtualWorkers/worker.py` (line 83)
- `agent_reports/20251029_COMPREHENSIVE_KOREAN_LOCALIZATION_FIX.md`

### Persona Generation Integration

The localization system is fully integrated with the persona generation API endpoint (`POST /api/v1/personas/generate`), ensuring that AI-generated personas match the configured locale.

**Implementation Details:**

```python
# In sim_manager/app.py
locale = os.getenv("VDOS_LOCALE", "en").strip().lower()

# Persona generation respects locale
if locale == "ko":
    # Generate Korean persona with Korean name
    # Example: "김지훈" (Kim Ji-hoon)
    # Uses Korean role titles: "풀스택 개발자"
    # Korean communication style: "비동기"
else:
    # Generate English persona with English name
    # Example: "Alex Chen"
    # Uses English role titles: "Full Stack Developer"
    # English communication style: "Async"
```

**Testing:**

The persona generation endpoint includes comprehensive locale-aware testing:

```python
# tests/test_sim_manager.py::test_generate_persona_endpoint
def test_generate_persona_endpoint(sim_client, monkeypatch):
    locale = os.getenv("VDOS_LOCALE", "en").strip().lower()
    
    if locale == "ko":
        # Expect Korean persona
        assert payload["name"] == "김개발"
        assert payload["role"] == "소프트웨어 엔지니어"
    else:
        # Expect English persona
        assert payload["name"] == "Auto Dev"
        assert payload["role"] == "Engineer"
```

**Benefits:**

- **Consistent Experience**: Personas match the simulation locale automatically
- **Authentic Names**: Korean locale generates authentic Korean names
- **Proper Terminology**: Role titles and attributes use locale-appropriate terms
- **Seamless Integration**: No manual configuration needed beyond `VDOS_LOCALE`

## Performance Considerations

### Optimization Strategies

1. **Singleton pattern**: Global manager instance for common locale
2. **Lazy loading**: Load strings only when needed
3. **Caching**: Cache frequently accessed strings
4. **Memory efficiency**: Minimize string duplication across locales

### Benchmarks

The localization system is designed for minimal performance impact:
- String lookup: O(1) dictionary access
- Manager creation: Minimal overhead with validation
- Memory usage: ~1KB per locale for all strings

## Conclusion

The localization module provides a robust foundation for internationalization in VDOS, with particular focus on Korean workplace simulations. It eliminates hardcoded English text, provides consistent Korean translations, and offers a clean API for integration throughout the system.

The module is designed for extensibility and can easily accommodate additional locales and features as the system grows.