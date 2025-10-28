# VDOS Testing Documentation

## Overview

VDOS includes a comprehensive testing suite that validates all major components including simulation engine, planner system, localization, email/chat servers, and GUI functionality. The test suite is designed to ensure reliability, performance, and correctness across different scenarios and configurations.

## Test Suite Organization

### Test Structure
```
tests/
├── conftest.py                           # Test configuration and shared fixtures
├── test_app.py                          # GUI application tests
├── test_auto_pause_integration.py       # Auto-pause feature integration tests
├── test_auto_pause_unit.py             # Auto-pause unit tests
├── test_auto_pause_workflow_integration.py # Auto-pause workflow tests
├── test_chat_server.py                  # Chat server REST API tests
├── test_dashboard_web.py                # Web dashboard tests
├── test_email_client_integration.py     # Email client integration tests
├── test_email_client_interface.py       # Email client interface tests
├── test_email_client_unit.py           # Email client unit tests
├── test_email_server.py                # Email server REST API tests
├── test_env_and_api.py                 # Environment and API configuration tests
├── test_korean_simulation_integration.py # Korean localization integration tests
├── test_localization.py                # Localization system tests
├── test_mobile_chat_simulation.py      # Mobile chat simulation tests
├── test_multi_project_scenarios.py     # Multi-project simulation tests
├── test_sim_manager.py                 # Simulation engine core tests
├── test_ui_feedback_notifications.py   # UI feedback system tests
├── test_virtual_worker.py              # Virtual worker and persona tests
└── virtualoffice.py                    # Test utilities and helper functions
```

### Root-Level Test Files
```
test_korean_persona.py                   # Korean persona integration test (NEW)
```

## Test Categories

### 1. Unit Tests
Individual component testing with isolated functionality:

- **Virtual Worker Tests** (`test_virtual_worker.py`): Persona creation, markdown generation, schedule rendering
- **Localization Tests** (`test_localization.py`): Language switching, template rendering, Korean validation
- **Email Client Unit Tests** (`test_email_client_unit.py`): Email client core functionality
- **Auto-pause Unit Tests** (`test_auto_pause_unit.py`): Auto-pause logic validation

### 2. Integration Tests
Service interaction and workflow testing:

- **Email Server Tests** (`test_email_server.py`): REST API endpoints, mailbox management, message threading
- **Chat Server Tests** (`test_chat_server.py`): Chat API, room management, direct messaging
- **Simulation Manager Tests** (`test_sim_manager.py`): Complete simulation workflows, tick advancement, planning cycles
- **Korean Simulation Integration** (`test_korean_simulation_integration.py`): End-to-end Korean localization
- **Auto-pause Integration** (`test_auto_pause_integration.py`): Auto-pause with project lifecycle

### 3. End-to-End Tests
Complete simulation workflow testing:

- **Mobile Chat Simulation** (`test_mobile_chat_simulation.py`): Full 4-week simulation scenarios
- **Multi-project Scenarios** (`test_multi_project_scenarios.py`): Concurrent project management
- **Korean Persona Integration** (`test_korean_persona.py`): Korean locale with persona system

### 4. Performance Tests
Load testing and performance validation:

- **Environment and API Tests** (`test_env_and_api.py`): Configuration validation, API performance
- **Dashboard Tests** (`test_dashboard_web.py`): Web interface performance

## Locale-Aware Testing

### Persona Generation Endpoint Test

**File**: `tests/test_sim_manager.py::test_generate_persona_endpoint`

**Purpose**: Validates that the persona generation API endpoint respects the `VDOS_LOCALE` environment variable and generates appropriate personas for the configured locale.

**Key Features**:
- Detects active locale from `VDOS_LOCALE` environment variable
- Generates English personas when locale is `en` (default)
- Generates Korean personas when locale is `ko`
- Validates persona attributes match expected locale conventions
- Tests API endpoint behavior with mocked AI responses

**Test Scenarios**:

#### English Locale (Default)
```python
# With VDOS_LOCALE=en or unset
resp = client.post(
    "/api/v1/personas/generate",
    json={"prompt": "Full stack developer"},
)
assert resp.status_code == 200
payload = resp.json()["persona"]
assert payload["name"] == "Auto Dev"  # English name
assert payload["skills"] == ["Python"]
```

#### Korean Locale
```python
# With VDOS_LOCALE=ko
resp = client.post(
    "/api/v1/personas/generate",
    json={"prompt": "풀스택 개발자"},
)
assert resp.status_code == 200
payload = resp.json()["persona"]
assert payload["name"] == "김개발"  # Korean name
assert payload["skills"] == ["Python", "FastAPI"]
```

**Implementation Details**:
- Test checks `os.getenv("VDOS_LOCALE", "en")` to determine expected behavior
- Mocks `_generate_persona_text` function with locale-appropriate responses
- Validates both name and skills match expected locale conventions
- Ensures consistent behavior across different locale configurations

## New Test: Korean Persona Integration

### File: `test_korean_persona.py`

**Purpose**: Validates that Korean localization works seamlessly with the persona system, ensuring authentic Korean workplace simulation.

**Key Features**:
- Tests Korean locale configuration (`VDOS_LOCALE=ko`)
- Validates Korean persona creation with Korean names and content
- Tests daily planning in Korean with persona context
- Tests hourly planning in Korean with persona integration
- Validates Korean character ratio in generated content
- Checks for proper Korean scheduled communications section

**Test Scenarios**:

#### 1. Korean Daily Planning with Persona
```python
daily_result = planner.generate_daily_plan(
    worker=korean_worker,
    project_plan="사용자 인증과 기본 CRUD 작업이 포함된 모바일 앱 MVP를 구축합니다.",
    day_index=0,
    duration_weeks=2,
    team=[korean_worker],
    model_hint="gpt-4o-mini"
)
```

**Validation**:
- Checks model used and token consumption
- Validates Korean character ratio (>30% Korean characters)
- Ensures content is primarily in Korean

#### 2. Korean Hourly Planning with Persona
```python
hourly_result = planner.generate_hourly_plan(
    worker=korean_worker,
    project_plan="사용자 인증과 기본 CRUD 작업이 포함된 모바일 앱 MVP를 구축합니다.",
    daily_plan="API 개발과 데이터베이스 스키마 설계에 집중합니다.",
    tick=1,
    context_reason="start_of_day",
    team=[korean_worker],
    model_hint="gpt-4o-mini"
)
```

**Validation**:
- Verifies Korean content generation
- Checks for Korean scheduled communications section ("예정된 커뮤니케이션" or "일정된 소통")
- Validates persona integration with Korean context

#### 3. Korean Persona Definition
The test uses a comprehensive Korean persona:

```python
worker = PersonRead(
    name="김지훈",  # Korean name
    role="풀스택 개발자",
    skills=["Python", "React", "PostgreSQL"],
    personality=["분석적", "세심함", "협력적"],
    objectives=["MVP 기능 출시", "코드 품질 개선"],
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

## Testing Guidelines

### FastAPI Service Testing
- **Use ASGI TestClient**: No network overhead, fast execution
- **Test All Endpoints**: REST endpoints with various payloads and edge cases
- **Database Testing**: Use in-memory SQLite for test isolation
- **Error Scenarios**: Validation errors, missing resources, server errors

### Simulation Engine Testing
- **Tick Advancement**: Verify correct time progression and state updates
- **Event Processing**: Test event injection and worker response patterns
- **Planning Cycles**: Verify project → daily → hourly → report flow
- **Worker Filtering**: Test include/exclude persona functionality
- **State Persistence**: Verify simulation state survives restarts
- **Locale-Aware Persona Generation**: Test persona generation adapts to configured locale (English/Korean)

### Virtual Worker Testing
- **Persona Creation**: Test markdown generation and validation
- **Schedule Rendering**: Verify time block formatting and parsing
- **Planning Integration**: Test GPT and stub planner functionality
- **Communication**: Test message generation and response patterns

### Localization Testing
- **Language Switching**: Test locale configuration and switching
- **Content Validation**: Verify Korean content generation and validation
- **Template Rendering**: Test localized templates and messages
- **Persona Integration**: Test localization with persona system
- **Locale-Aware API Endpoints**: Test API endpoints respect `VDOS_LOCALE` environment variable
  - Persona generation endpoint (`/api/v1/personas/generate`) adapts to locale
  - English locale generates English personas with English names
  - Korean locale generates Korean personas with Korean names (e.g., "김개발")
  - Test validates expected names and attributes based on active locale

## Test Data Management

### Fixtures and Factories
- **Persona Fixtures**: Predefined personas for consistent testing (English and Korean)
- **Project Fixtures**: Sample projects with various complexities and languages
- **Message Fixtures**: Email and chat message templates in multiple languages
- **Event Fixtures**: Common simulation events (client changes, absences)

### Test Database
- **Isolation**: Each test gets fresh database state
- **Cleanup**: Automatic cleanup after test completion
- **Seeding**: Consistent test data seeding for reproducible results
- **Migration Testing**: Verify database schema changes

### Artifact Generation
- **Test Outputs**: Write test artifacts to `output/` directory
- **Simulation Runs**: Generate complete simulation traces for analysis
- **Report Validation**: Verify generated reports match expected format
- **Token Tracking**: Test AI usage tracking and metrics

## Performance Testing

### Load Testing Scenarios
- **High Persona Count**: Test with 10+ personas simultaneously
- **Rapid Tick Advancement**: Test high-frequency tick processing
- **Message Volume**: Test high-volume email/chat generation
- **Long Simulations**: Test multi-week simulation stability
- **Korean Content Generation**: Test Korean AI generation performance

### Performance Metrics
- **Tick Processing Time**: Target <100ms per tick for 5 personas
- **Memory Usage**: Monitor worker runtime cache growth
- **Database Performance**: Query execution time monitoring
- **AI Response Time**: GPT planning request latency tracking
- **Korean Generation Time**: Korean content generation performance

### Stress Testing
- **Concurrent Simulations**: Multiple simulation instances
- **API Rate Limiting**: Test rate limit enforcement
- **Resource Exhaustion**: Test behavior under resource constraints
- **Error Recovery**: Test graceful degradation and recovery

## Test Execution

### Running Tests

#### Full Test Suite
```bash
# Run all tests
python -m pytest

# Run with verbose output
python -m pytest -v

# Run with coverage
python -m pytest --cov=src/virtualoffice
```

#### Specific Test Categories
```bash
# Unit tests only
python -m pytest tests/test_virtual_worker.py tests/test_localization.py -v

# Integration tests
python -m pytest tests/test_sim_manager.py tests/test_email_server.py -v

# Korean localization tests
python -m pytest tests/test_localization.py tests/test_korean_simulation_integration.py -v
python test_korean_persona.py

# Performance tests
python -m pytest tests/test_env_and_api.py --benchmark-only
```

#### Specific Test Files
```bash
# Simulation engine tests (includes locale-aware persona generation)
python -m pytest tests/test_sim_manager.py -v

# Test persona generation with English locale (default)
python -m pytest tests/test_sim_manager.py::test_generate_persona_endpoint -v

# Test persona generation with Korean locale
VDOS_LOCALE=ko python -m pytest tests/test_sim_manager.py::test_generate_korean_persona_endpoint -v

# Korean persona integration test
python test_korean_persona.py

# Email server API tests
python -m pytest tests/test_email_server.py -v

# Chat server API tests
python -m pytest tests/test_chat_server.py -v

# Auto-pause functionality tests
python -m pytest tests/test_auto_pause_integration.py -v
```

### Test Configuration

#### Environment Variables for Testing
```bash
# Use test-specific configuration
VDOS_DB_PATH=:memory:           # In-memory database for tests
VDOS_LOCALE=ko                  # Korean locale for localization tests
OPENAI_API_KEY=sk-test-key      # Test API key (if needed)
VDOS_PLANNER_STRICT=1          # Strict planner mode for testing
```

#### Logging Configuration
- **Capture Logs**: Use `-s` flag to see detailed logs during test execution
- **Log Levels**: Configure appropriate log levels for debugging
- **Structured Logs**: JSON logs for automated analysis

#### Timeouts and Parallel Execution
- **AI Test Timeouts**: Appropriate timeouts for AI-dependent tests
- **Parallel Execution**: Safe parallel test execution where possible
- **Resource Management**: Proper cleanup to prevent test interference

### Continuous Integration

#### Pre-commit Hooks
```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run tests before commits
pre-commit run --all-files
```

#### CI Pipeline Configuration
- **Automated Testing**: Run tests on pull requests
- **Coverage Reports**: Maintain high test coverage (>80%)
- **Performance Regression**: Monitor performance metrics over time
- **Multi-platform Testing**: Test on Windows, macOS, Linux

## Debugging Test Failures

### Common Issues

#### Timing Issues
- **Race Conditions**: Async operations completing out of order
- **Tick Timing**: Simulation timing inconsistencies
- **AI Response Delays**: Variable GPT response times

#### Database State Issues
- **Inconsistent State**: Database state leaking between tests
- **Migration Issues**: Schema changes affecting tests
- **Connection Leaks**: Database connections not properly closed

#### AI Dependencies
- **API Failures**: OpenAI API rate limits or failures
- **Content Validation**: Korean content validation failures
- **Token Limits**: Exceeding model context windows

#### Resource Cleanup
- **Memory Leaks**: Incomplete cleanup causing test interference
- **File Handles**: Unclosed files or database connections
- **Thread Cleanup**: Background threads not properly terminated

### Debugging Tools

#### Verbose Output
```bash
# Detailed test output
python -m pytest -v -s

# Show local variables on failure
python -m pytest --tb=long

# Stop on first failure
python -m pytest -x
```

#### Log Analysis
```bash
# Check test logs for error patterns
tail -f virtualoffice.log

# Examine database state during failures
sqlite3 src/virtualoffice/vdos.db ".tables"
```

#### Database Inspection
```bash
# Examine test database state
sqlite3 :memory: ".schema"

# Check for data consistency
python -c "from virtualoffice.common.db import get_connection; print(list(get_connection().execute('SELECT * FROM people')))"
```

#### Profiling
```bash
# Profile test performance
python -m pytest --profile

# Memory profiling
python -m pytest --memray
```

### Test Maintenance

#### Regular Updates
- **Keep Tests Current**: Update tests with code changes
- **Dependency Updates**: Update test dependencies regularly
- **Documentation Sync**: Keep test documentation current

#### Flaky Test Management
- **Identify Patterns**: Track flaky test occurrences
- **Root Cause Analysis**: Investigate timing and resource issues
- **Stabilization**: Fix unreliable tests promptly

#### Test Documentation
- **Document Complex Scenarios**: Explain intricate test setups
- **Update Examples**: Keep code examples current
- **Cross-references**: Link tests to relevant documentation

#### Refactoring
- **Regular Cleanup**: Refactor tests for maintainability
- **Shared Utilities**: Extract common test patterns
- **Performance Optimization**: Optimize slow tests

## Test Coverage Goals

### Current Coverage Areas
- ✅ **Simulation Engine**: Core tick advancement, planning cycles, event processing
- ✅ **Email Server**: REST API, mailbox management, message threading
- ✅ **Chat Server**: Chat API, room management, direct messaging
- ✅ **Virtual Workers**: Persona creation, schedule rendering, planning integration
- ✅ **Localization**: Language switching, Korean content validation
- ✅ **Auto-pause**: Project lifecycle management, auto-pause logic
- ✅ **Korean Integration**: Korean persona with localization system (NEW)

### Coverage Targets
- **Unit Tests**: >90% line coverage for core modules
- **Integration Tests**: >80% workflow coverage
- **End-to-End Tests**: All major user scenarios covered
- **Performance Tests**: Key performance metrics monitored
- **Localization Tests**: All supported locales tested

### Metrics Tracking
- **Line Coverage**: Track code coverage percentages
- **Branch Coverage**: Ensure all code paths tested
- **Function Coverage**: All public functions tested
- **Integration Coverage**: All service interactions tested

## Best Practices

### Test Design
- **Single Responsibility**: Each test should test one specific behavior
- **Clear Naming**: Test names should describe what they validate
- **Arrange-Act-Assert**: Structure tests with clear setup, execution, and validation
- **Independent Tests**: Tests should not depend on each other

### Data Management
- **Fresh State**: Each test starts with clean state
- **Realistic Data**: Use realistic test data that matches production patterns
- **Edge Cases**: Test boundary conditions and error scenarios
- **Localization**: Include multi-language test data

### Performance
- **Fast Execution**: Keep tests fast to encourage frequent running
- **Parallel Safe**: Design tests to run safely in parallel
- **Resource Efficient**: Minimize resource usage in tests
- **Cleanup**: Always clean up resources after tests

### Maintenance
- **Regular Review**: Review and update tests regularly
- **Documentation**: Document complex test scenarios
- **Refactoring**: Keep test code clean and maintainable
- **Monitoring**: Monitor test performance and reliability

The VDOS testing suite provides comprehensive coverage of all system components with special attention to localization, persona integration, and multi-language support. The new Korean persona integration test ensures that the localization system works seamlessly with the persona system for authentic Korean workplace simulation.