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
├── test_communication_generator.py      # Communication generator unit tests
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

### Diagnostic and Long-Running Test Scripts
```
.tmp/
├── diagnose_stuck_simulation.py         # Diagnostic tool for stuck simulations
├── full_simulation_test.py              # Comprehensive 5-tick workflow test
├── test_1week_simulation.py             # 1-week long-running stability test
├── test_persona_generation_ui.py        # Playwright UI automation test for persona generation
├── test_quality_validation_gpt.py       # GPT-4o quality validation for communication diversity (NEW)
├── test_auto_tick_long_wait.py          # Auto-tick monitoring test
├── test_auto_tick_with_logging.py       # Auto-tick database state monitoring
├── test_auto_tick_detailed.py           # Auto-tick with detailed error capture
├── debug_advance_step_by_step.py        # Step-by-step advance() debugging
├── test_planning_directly.py            # Isolated planning system test
├── check_thread_status.py               # Auto-tick thread status check
├── check_project_status.py              # Project status and auto-pause check
├── check_tick_log.py                    # Tick log inspection
├── check_tables.py                      # Database table inspection
└── check_sim_state.py                   # Detailed simulation state inspection
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
- **1-Week Simulation Test** (`.tmp/test_1week_simulation.py`): Long-running stability test with continuous monitoring (NEW)

### 4. Performance Tests
Load testing and performance validation:

- **Environment and API Tests** (`test_env_and_api.py`): Configuration validation, API performance
- **Dashboard Tests** (`test_dashboard_web.py`): Web interface performance
- **1-Week Simulation Test** (`.tmp/test_1week_simulation.py`): Extended performance and stability testing

### 5. UI Automation Tests
Browser-based UI testing with Playwright:

- **Persona Generation UI Test** (`.tmp/test_persona_generation_ui.py`): Automated testing of persona generation workflow in web dashboard (NEW)

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

## New Test: 1-Week Simulation Stability Test

### File: `.tmp/test_1week_simulation.py`

**Purpose**: Validates long-running simulation stability, auto-tick reliability, and performance consistency over an extended period (full work week).

**Key Features**:
- **Extended Duration**: Simulates 5 full work days (2400 ticks total)
- **Continuous Monitoring**: Progress checks every 60 seconds with detailed metrics
- **Performance Tracking**: Tick rates, ETA calculations, rate variation analysis
- **Safety Limits**: 1-hour maximum test duration to prevent runaway tests
- **Optimized Configuration**: Parallel planning (4 workers), Korean validation disabled, auto-pause disabled
- **Comprehensive Reporting**: Final statistics, success criteria validation, issue identification

**Test Configuration**:
```python
HOURS_PER_DAY = 480  # 8 hours * 60 minutes
WORK_DAYS = 5
TOTAL_TICKS = 2400  # Full work week
SAMPLE_INTERVAL = 60  # Check progress every 60 seconds
MAX_TEST_DURATION = 3600  # 1 hour safety limit
```

**Optimized Settings**:
```python
os.environ["VDOS_MAX_PLANNING_WORKERS"] = "4"  # Parallel planning
os.environ["VDOS_KOREAN_VALIDATION_RETRIES"] = "0"  # Disable retries
os.environ["VDOS_AUTO_PAUSE_ON_PROJECT_END"] = "false"  # Prevent early stop
```

**Test Phases**:

#### 1. Initialization
- Creates simulation engine with optimized settings
- Verifies at least 2 personas exist
- Starts fresh 1-week simulation

#### 2. Auto-Tick Monitoring
- Enables auto-tick for continuous advancement
- Monitors progress every 60 seconds
- Tracks tick rates and performance metrics
- Calculates ETA and progress percentage

#### 3. Progress Tracking
**Metrics Collected**:
- Overall tick advancement rate (ticks/second)
- Time per tick (seconds)
- Progress percentage and ETA
- Rate variation (min/max/average)
- Day and tick-of-day tracking

**Sample Output**:
```
[5.0m] Day 2, Tick 120/480 (Total: 600/2400) | Progress: 25.0% | Rate: 2.00 ticks/s | ETA: 15m
```

#### 4. Safety Checks
- Monitors auto-tick status (detects if disabled)
- Enforces 1-hour maximum test duration
- Handles keyboard interrupts gracefully
- Stops auto-tick on completion or interruption

#### 5. Final Statistics
**Time Metrics**:
- Total elapsed time (minutes and hours)
- Start and end timestamps
- Average time per tick
- Ticks per minute

**Progress Metrics**:
- Initial and final tick numbers
- Total ticks advanced
- Completion percentage
- Target vs actual ticks

**Performance Analysis**:
- Average tick rate (ticks/second)
- Rate variation (min/max/average)
- Performance consistency assessment

#### 6. Success Criteria Validation
**Pass Conditions**:
- ✓ Completes full 2400 ticks (or reaches time limit)
- ✓ Average time per tick <20 seconds
- ✓ Auto-tick remains enabled throughout
- ✓ No errors or exceptions in logs

**Issue Detection**:
- ⚠ Did not complete full week (time limit reached)
- ✗ Did not complete full week (auto-tick stopped)
- ⚠ Average time per tick is slow (>20s)
- ✗ Auto-tick was disabled before completion

**Running the Test**:
```bash
# Ensure services are running first
briefcase dev

# In another terminal, run the test
python .tmp/test_1week_simulation.py
```

**Expected Results**:
- **Duration**: ~10 hours at 15s/tick (2400 ticks)
- **Performance**: Stable tick rates throughout
- **Reliability**: No auto-tick failures or crashes
- **Memory**: Stable memory usage
- **Communications**: All emails/chats generated correctly

**Use Cases**:
- Validating simulation stability for production use
- Testing performance under realistic workloads
- Verifying auto-tick doesn't degrade over time
- Benchmarking full-week simulation duration
- Stress-testing the simulation engine
- Detecting memory leaks or resource issues
- Validating database performance under load

**Troubleshooting**:
If the test fails or shows issues:
1. Check `virtualoffice.log` for errors
2. Run diagnostic tool: `python .tmp/diagnose_stuck_simulation.py`
3. Verify database state: `python .tmp/check_sim_state.py`
4. Check auto-tick thread: `python .tmp/check_thread_status.py`
5. Review performance metrics in test output

## New Test: Persona Generation UI Automation

### File: `.tmp/test_persona_generation_ui.py`

**Purpose**: Automated browser-based testing of the persona generation workflow in the VDOS web dashboard using Playwright.

**Key Features**:
- **Browser Automation**: Uses Playwright to interact with the web dashboard
- **Console Monitoring**: Captures and validates JavaScript console output
- **Error Detection**: Tracks page errors and JavaScript exceptions
- **Visual Validation**: Takes screenshots for manual inspection
- **Step-by-Step Verification**: Validates each step of the persona generation workflow
- **Korean Locale Testing**: Tests persona generation with Korean input ("풀스택 개발자 김최솔")

**Test Workflow**:

#### 1. Browser Setup
```python
browser = await p.chromium.launch(headless=False)
context = await browser.new_context()
page = await context.new_page()
```
- Launches Chromium browser in visible mode for inspection
- Sets up console message and error handlers
- Navigates to dashboard at `http://127.0.0.1:8025/`

#### 2. JavaScript Initialization Checks
**Validates**:
- ✓ Inline test message appears in console
- ✓ Dashboard.js module loads successfully
- ✓ Dashboard initialization starts

**Console Messages Checked**:
- `[INLINE TEST] JavaScript is working!`
- `DASHBOARD.JS LOADED`
- `Initializing dashboard`

#### 3. UI Element Discovery
**Locates and validates**:
- Persona prompt input field (`#persona-prompt`)
- Generate with GPT button (`#persona-generate-btn`)
- Button visibility and enabled state

#### 4. Persona Generation Trigger
**Actions**:
- Fills prompt input with Korean text: "풀스택 개발자 김최솔"
- Clicks "Generate with GPT" button
- Monitors console for event handlers

**Console Events Tracked**:
- `BUTTON CLICKED` - Button click event detected
- `generatePersona START` - Generation function called
- `Calling API` - API request initiated

#### 5. Form Population Validation
**Checks**:
- Name field (`#persona-name`) populated
- Role field (`#persona-role`) populated
- Waits up to 5 seconds for API response

#### 6. Screenshot Capture
**Artifacts Generated**:
- `persona_generation_test.png` - Success screenshot
- `persona_generation_error.png` - Error screenshot (if failure)

#### 7. Comprehensive Reporting
**Output Includes**:
- Step-by-step progress with checkmarks (✓/✗)
- All console messages captured
- All JavaScript errors detected
- Form field values
- Screenshot locations

**Prerequisites**:
```bash
# Install Playwright (auto-installed by script if missing)
pip install playwright
python -m playwright install chromium

# Ensure dashboard is running
briefcase dev
# or manually start simulation manager on port 8025
```

**Running the Test**:
```bash
# Run with visible browser (default)
python .tmp/test_persona_generation_ui.py

# Browser stays open for 10 seconds after completion for inspection
```

**Expected Output**:
```
================================================================================
VDOS Persona Generation UI Test
================================================================================

[1] Launching Chromium browser...
[2] Navigating to http://127.0.0.1:8025/...
  ✓ Page loaded
[3] Checking console for inline test message...
  ✓ Inline test message found - JavaScript is working
  ✓ Dashboard.js loaded successfully
  ✓ Dashboard initialization started
[4] Scrolling to persona section...
[5] Finding prompt input field...
  ✓ Prompt input found
[6] Entering prompt: '풀스택 개발자 김최솔'...
[7] Finding 'Generate with GPT' button...
  ✓ Generate button found
  - Visible: True
  - Enabled: True
[8] Clicking 'Generate with GPT' button...
  ✓ Button clicked
[9] Waiting for API response (max 30 seconds)...
[10] Checking console output after button click...
  ✓ Button click event detected
  ✓ generatePersona function called
  ✓ API call initiated
[11] Waiting for form to be populated...
[12] Checking form fields:
  - Name: '김최솔'
  - Role: '풀스택 개발자'
  ✓ Name field populated
  ✓ Role field populated
[13] Screenshot saved to: .tmp\persona_generation_test.png

================================================================================
ALL CONSOLE MESSAGES:
================================================================================
[log] [INLINE TEST] JavaScript is working!
[log] DASHBOARD.JS LOADED
[log] Initializing dashboard
[log] BUTTON CLICKED: persona-generate-btn
[log] generatePersona START
[log] Calling API: /api/v1/personas/generate
[log] API response received
[log] Form populated successfully

================================================================================
Test complete. Browser will stay open for 10 seconds for inspection...
================================================================================
```

**Use Cases**:
- **Regression Testing**: Verify persona generation UI works after changes
- **Integration Testing**: Validate frontend-backend communication
- **Debugging**: Visual inspection of UI behavior and console output
- **Korean Locale Testing**: Ensure Korean input/output works correctly
- **CI/CD Integration**: Automated UI testing in deployment pipeline

**Troubleshooting**:
If the test fails:
1. **Check Dashboard Running**: Ensure simulation manager is running on port 8025
2. **Review Console Output**: Look for JavaScript errors in test output
3. **Inspect Screenshots**: Check generated PNG files for visual issues
4. **Verify API Endpoint**: Test `/api/v1/personas/generate` endpoint directly
5. **Check Browser Logs**: Review Playwright browser logs for network issues
6. **Validate JavaScript**: Ensure `app.js` and `dashboard.js` are loading correctly

**Configuration**:
```python
# Adjust browser visibility
browser = await p.chromium.launch(headless=True)  # Run in background

# Adjust wait times
await page.wait_for_timeout(10000)  # Wait 10 seconds

# Change dashboard URL
await page.goto("http://localhost:8015/")  # Different port
```

**Dependencies**:
- `playwright` - Browser automation library
- Chromium browser (auto-installed by Playwright)
- Running VDOS dashboard on port 8025
- Active OpenAI API key for persona generation

## New Test: GPT-4o Quality Validation

### File: `.tmp/test_quality_validation_gpt.py`

**Purpose**: Uses GPT-4o to evaluate the quality of generated communications from the communication diversity system, validating realism and role differentiation.

**Key Features**:
- **Automated Quality Assessment**: Uses GPT-4o as an expert evaluator
- **Realism Scoring**: Rates messages on 1-10 scale for workplace realism
- **Role Identification**: Tests if roles can be identified from message content alone
- **Batch Processing**: Evaluates 50 messages in efficient batches
- **Statistical Analysis**: Provides score distributions and accuracy metrics
- **Target Validation**: Verifies system meets quality targets (≥7.5/10 realism, ≥75% role accuracy)

**Test Workflow**:

#### 1. Message Sampling
```python
messages = sample_messages(db_path, sample_size=50)
```
- Samples 50 random messages from simulation database
- Includes both emails (with subject/body) and chat messages
- Joins with `people` table to get sender role information
- Filters for meaningful content (>20 chars for emails, >10 for chats)
- Shuffles and balances email/chat ratio

**SQL Queries**:
```sql
-- Email sampling
SELECT e.subject, e.body, p.name, p.role
FROM emails e
JOIN people p ON e.sender = p.email
WHERE e.subject IS NOT NULL AND LENGTH(e.body) > 20
ORDER BY RANDOM() LIMIT 50

-- Chat sampling  
SELECT cm.message, p.name, p.role
FROM chat_messages cm
JOIN people p ON cm.sender_handle = p.chat_handle
WHERE cm.message IS NOT NULL AND LENGTH(cm.message) > 10
ORDER BY RANDOM() LIMIT 25
```

#### 2. Realism Evaluation
```python
avg_score, evaluations = evaluate_realism_batch(messages)
```

**GPT-4o Evaluation Criteria**:
- **10**: Indistinguishable from real workplace communication
- **8-9**: Very realistic with minor artificial patterns
- **6-7**: Mostly realistic but with some template-like qualities
- **4-5**: Somewhat realistic but clearly generated
- **1-3**: Unrealistic, repetitive, or obviously templated

**Factors Considered**:
- Natural language flow and variety
- Appropriate formality and tone
- Specific details vs. generic statements
- Conversational patterns
- Role-appropriate vocabulary

**Response Format**:
```json
{
  "evaluations": [
    {"message_id": 1, "score": 8, "reasoning": "Natural language with specific details"},
    {"message_id": 2, "score": 7, "reasoning": "Good but slightly formal"}
  ],
  "average_score": 7.5,
  "overall_assessment": "Messages show good realism with natural variation"
}
```

#### 3. Role Identification
```python
accuracy, predictions = identify_roles_batch(messages)
```

**GPT-4o Role Detection**:
Analyzes message content to identify sender's role based on:
- Technical terminology and jargon
- Communication style and formality
- Topics discussed
- Vocabulary choices

**Possible Roles**:
- **Developer/Engineer (개발자)**: Technical terms, code references, API discussions
- **Designer (디자이너)**: Visual design, UI/UX, mockups, prototypes
- **QA/Tester (QA)**: Testing, bugs, test cases, quality assurance
- **Marketer (마케터)**: Campaigns, metrics, CTR, conversion rates
- **Manager/PM (매니저)**: Coordination, timelines, stakeholders, planning

**Accuracy Calculation**:
```python
# Normalize role names for comparison
role_matches = {
    'developer': ['developer', 'engineer', '개발자', 'dev'],
    'designer': ['designer', '디자이너', 'design'],
    'qa': ['qa', 'tester', 'test', 'quality'],
    'marketer': ['marketer', 'marketing', '마케터'],
    'manager': ['manager', 'pm', '매니저', 'lead'],
}

# Check if predicted role matches actual role category
accuracy = correct_predictions / total_predictions
```

#### 4. Comprehensive Reporting

**Score Distribution**:
```
Score Distribution:
  10/10: ████ (4)
   9/10: ████████ (8)
   8/10: ████████████ (12)
   7/10: ██████████ (10)
   6/10: ████████ (8)
   5/10: ████ (4)
   4/10: ██ (2)
   3/10: ██ (2)
```

**Sample Evaluations**:
```
Message 1: 8/10 - Natural language with specific technical details
Message 2: 7/10 - Good context but slightly formal tone
Message 3: 9/10 - Excellent conversational flow and role-appropriate terms
```

**Role Predictions**:
```
Message 1: Developer (actual: 개발자) ✓
  Reasoning: Uses technical terms like API, database, code review
Message 2: Designer (actual: 디자이너) ✓
  Reasoning: Discusses UI/UX, mockups, visual design
Message 3: Manager (actual: 매니저) ✓
  Reasoning: Coordination language, timeline references
```

#### 5. Success Criteria Validation

**Pass Conditions**:
- ✅ Average realism score ≥7.5/10
- ✅ Role identification accuracy ≥75%

**Output**:
```
================================================================================
OVERALL RESULTS
================================================================================
Realism Score: 7.82/10 (target: ≥7.5) ✅
Role Accuracy: 78.0% (target: ≥75%) ✅

✅ ALL QUALITY TARGETS MET

The communication diversity system successfully generates:
  - Realistic, natural workplace communications
  - Role-differentiated messages with appropriate vocabulary
  - Diverse content that avoids template repetition
```

**Prerequisites**:
```bash
# Ensure simulation has run and generated messages
briefcase dev
# Run simulation to generate at least 50 messages

# Ensure OpenAI API key is configured
export OPENAI_API_KEY=sk-...
```

**Running the Test**:
```bash
# Run quality validation
python .tmp/test_quality_validation_gpt.py

# Expected duration: 2-3 minutes (2 GPT-4o API calls)
# Expected cost: ~$0.02 (GPT-4o token usage)
```

**Expected Output**:
```
================================================================================
Task 8.8: Quality Validation with GPT Evaluation
================================================================================

Using database: src/virtualoffice/vdos.db

Sampling 50 random messages from simulation...
Sampled 50 messages:
  - 35 emails
  - 15 chat messages

--------------------------------------------------------------------------------
1. REALISM EVALUATION
--------------------------------------------------------------------------------
Evaluating message realism with GPT-4o...
Used 2847 tokens

Average Realism Score: 7.82/10
Target: ≥7.5/10
Status: ✅ PASS

Score Distribution:
   9/10: ████████ (8)
   8/10: ████████████ (12)
   7/10: ██████████ (10)
   6/10: ████████ (8)

Sample Evaluations:
  Message 1: 8/10 - Natural language with specific details
  Message 2: 9/10 - Excellent role-appropriate vocabulary
  Message 3: 7/10 - Good but slightly formal

--------------------------------------------------------------------------------
2. ROLE IDENTIFICATION
--------------------------------------------------------------------------------
Identifying roles with GPT-4o...
Used 3124 tokens

Role Identification Accuracy: 78.0%
Target: ≥75%
Status: ✅ PASS

Sample Predictions:
  Message 1: Developer (actual: 개발자) ✓
    Reasoning: Uses technical terms like API
  Message 2: Designer (actual: 디자이너) ✓
    Reasoning: Discusses UI/UX and mockups
  Message 3: Manager (actual: 매니저) ✓
    Reasoning: Coordination and timeline focus

================================================================================
OVERALL RESULTS
================================================================================
Realism Score: 7.82/10 (target: ≥7.5) ✅
Role Accuracy: 78.0% (target: ≥75%) ✅

✅ ALL QUALITY TARGETS MET
```

**Use Cases**:
- **Quality Assurance**: Validate communication diversity improvements
- **Regression Testing**: Ensure quality doesn't degrade with changes
- **Benchmarking**: Compare different generation approaches
- **A/B Testing**: Evaluate template-based vs. GPT-generated messages
- **Continuous Monitoring**: Track quality metrics over time

**Troubleshooting**:
If the test fails:
1. **Insufficient Messages**: Run longer simulation to generate more messages
2. **Database Not Found**: Ensure `src/virtualoffice/vdos.db` exists
3. **API Key Issues**: Verify `OPENAI_API_KEY` is set correctly
4. **Low Realism Score**: Review generated messages for template patterns
5. **Low Role Accuracy**: Check if role-specific vocabulary is being used
6. **JSON Parse Errors**: GPT-4o response format may have changed

**Configuration**:
```python
# Adjust sample size
messages = sample_messages(db_path, sample_size=100)  # More messages

# Change evaluation model
response, tokens = generate_text(prompt, model="gpt-4o", temperature=0.3)

# Adjust scoring criteria
# Edit system prompt in evaluate_realism_batch() function
```

**Token Usage**:
- **Realism Evaluation**: ~3000 tokens (50 messages)
- **Role Identification**: ~3000 tokens (50 messages)
- **Total**: ~6000 tokens per run
- **Cost**: ~$0.02 per run (GPT-4o pricing)

**Dependencies**:
- `sqlite3` - Database access (built-in)
- `json` - JSON parsing (built-in)
- `random` - Message sampling (built-in)
- `virtualoffice.utils.completion_util` - GPT API wrapper
- Active OpenAI API key
- Simulation database with generated messages

**Related Tests**:
- `tests/test_communication_generator.py` - Unit tests for generator
- `tests/integration/test_communication_diversity.py` - Integration tests
- `.tmp/benchmark_communication_diversity.py` - Performance benchmarks

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
- **1-Week Stability Test**: Extended 2400-tick simulation with continuous monitoring (NEW)

### Performance Metrics
- **Tick Processing Time**: Target <100ms per tick for 5 personas
- **Memory Usage**: Monitor worker runtime cache growth
- **Database Performance**: Query execution time monitoring
- **AI Response Time**: GPT planning request latency tracking
- **Korean Generation Time**: Korean content generation performance
- **Long-Running Stability**: Tick rate consistency over extended periods (NEW)
- **Auto-Tick Reliability**: Thread stability and advancement consistency (NEW)

### 1-Week Simulation Performance Benchmarks
**Test**: `.tmp/test_1week_simulation.py`

**Expected Performance**:
- **Total Duration**: ~10 hours for 2400 ticks
- **Average Tick Rate**: ~0.067 ticks/second (15 seconds per tick)
- **Ticks Per Minute**: ~4 ticks/minute
- **Memory Growth**: <100MB over full simulation
- **Database Size**: <50MB for full week with 2 personas

**Performance Targets**:
- ✓ Average time per tick: <20 seconds
- ✓ Tick rate variation: <50% deviation from average
- ✓ Memory usage: Stable (no continuous growth)
- ✓ Auto-tick uptime: 100% (no crashes or stops)
- ✓ Database operations: No lock errors or timeouts

**Monitoring Metrics**:
- Overall tick advancement rate (ticks/second)
- Recent tick rate (last 60 seconds)
- Progress percentage and ETA
- Rate variation (min/max/average)
- Day and tick-of-day tracking

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

#### Long-Running and Diagnostic Tests
```bash
# 1-week simulation stability test (requires services running)
python .tmp/test_1week_simulation.py

# Full simulation workflow test (5 ticks)
python .tmp/full_simulation_test.py

# Diagnostic tool for stuck simulations
python .tmp/diagnose_stuck_simulation.py

# Auto-tick monitoring tests
python .tmp/test_auto_tick_long_wait.py
python .tmp/test_auto_tick_with_logging.py
python .tmp/test_auto_tick_detailed.py

# Step-by-step advance debugging
python .tmp/debug_advance_step_by_step.py

# Database and state inspection
python .tmp/check_sim_state.py
python .tmp/check_tables.py
python .tmp/check_tick_log.py
python .tmp/check_thread_status.py
python .tmp/check_project_status.py
```

#### UI Automation Tests
```bash
# Persona generation UI test (requires dashboard running on port 8025)
python .tmp/test_persona_generation_ui.py

# Install Playwright if needed
pip install playwright
python -m playwright install chromium
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
- ✅ **Korean Integration**: Korean persona with localization system
- ✅ **Long-Running Stability**: 1-week simulation with continuous monitoring
- ✅ **UI Automation**: Playwright-based persona generation workflow testing (NEW)

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