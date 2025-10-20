# VDOS Simulation Scripts Reference

Complete guide to all simulation scripts in the VDOS project root directory.

---

## Overview

VDOS provides 8 simulation scripts that demonstrate different use cases:
- **English versions**: Quick tests and comprehensive simulations
- **Korean versions (`_ko.py`)**: Localized simulations with Korean language output
- **Variations**: Single/multi-project, different durations (5 days to 8 weeks)

---

## Script Catalog

### 1. `quick_simulation.py`
**Purpose**: Fast 4-week mobile chat app simulation with minimal setup
**Team Size**: 4 people (PM, Designer, Developer, DevOps)
**Duration**: 4 weeks (9,600 ticks = 4 weeks × 5 days × 8 hours × 60 minutes)
**Language**: English
**Key Features**:
- In-process server startup (email :8000, chat :8001, sim :8015)
- GPT-4o-nano persona generation
- Manual tick advancement (fast, no auto-tick polling)
- Comprehensive artifact collection

**Command**:
```bash
python quick_simulation.py
```

**Expected Outputs** (`simulation_output/`):
```
simulation_output/
├── mobile_team.json              # Generated personas
├── week_1_state.json             # State snapshots
├── week_2_state.json
├── week_3_state.json
├── week_4_state.json
├── all_emails.json               # Email communications
├── all_chats.json                # Chat/DM logs
└── final_simulation_report.json  # Comprehensive summary
```

**Execution Flow**:
```
quick_simulation.py::main()
├─ _start_uvicorn_server("email") → :8000
├─ _start_uvicorn_server("chat") → :8001
├─ _start_uvicorn_server("sim") → :8015
├─ create_mobile_team()
│  ├─ POST /api/v1/personas/generate (× 4)
│  └─ POST /api/v1/people (× 4)
├─ run_simulation()
│  ├─ POST /api/v1/simulation/start
│  └─ [for each week]
│     ├─ POST /api/v1/simulation/advance (chunks of 480 ticks)
│     └─ save_json(state, f"week_{week}_state.json")
├─ collect_all_emails()
│  └─ GET /mailboxes/{address}/emails (× 5 addresses)
├─ collect_all_chats()
│  └─ GET /rooms/{slug}/messages (× 10 DM pairs)
├─ generate_reports()
│  ├─ GET /api/v1/simulation
│  ├─ GET /api/v1/events
│  ├─ GET /api/v1/simulation/token-usage
│  └─ GET /api/v1/people/{id}/daily-reports (× 4)
└─ _stop_uvicorn_server() (× 3 servers)
```

---

### 2. `mobile_chat_simulation.py`
**Purpose**: Comprehensive 4-week simulation with rich reporting
**Team Size**: 4 people
**Duration**: 4 weeks (configurable via `MOBILE_SIM_WEEKS` env var)
**Language**: English
**Key Features**:
- Auto-tick mode with polling loop
- Daily and weekly snapshots
- Human-readable PROJECT_SUMMARY.md
- Detailed planner metrics
- Team lead hierarchy support

**Command**:
```bash
# Default 4 weeks
python mobile_chat_simulation.py

# Override duration
MOBILE_SIM_WEEKS=2 python mobile_chat_simulation.py
```

**Expected Outputs** (`simulation_output/mobile_4week/`):
```
mobile_4week/
├── team_personas.json
├── daily_snapshot_week{W}_day{D}_{dayname}.json  # 20 daily files
├── weekly_summary_week{W}.json                    # 4 weekly files
├── email_communications.json
├── chat_communications.json
├── final_project_report.json
└── PROJECT_SUMMARY.md                             # Human-readable summary
```

**Execution Flow**:
```
MobileChatSimulation::run_complete_simulation()
├─ create_personas()
│  └─ [GPT generates 4 detailed personas with objectives/metrics]
├─ start_project_simulation()
│  └─ POST /api/v1/simulation/start
├─ run_simulation_ticks(weeks=4)
│  ├─ POST /api/v1/simulation/advance (ticks=1, kickoff)
│  ├─ POST /api/v1/simulation/ticks/start (enable auto-tick)
│  └─ [for each week & day]
│     ├─ [poll until target_tick reached]
│     ├─ capture_daily_snapshot()
│     └─ capture_weekly_snapshot()
├─ generate_final_reports()
│  ├─ GET /api/v1/simulation/project-plan
│  ├─ GET /api/v1/simulation/reports
│  ├─ GET /api/v1/people/{id}/daily-reports (limit=100)
│  └─ GET /api/v1/people/{id}/plans?plan_type=hourly (limit=200)
├─ export_communication_logs()
└─ generate_readable_summary() → PROJECT_SUMMARY.md
```

---

### 3. `short_blog_simulation.py`
**Purpose**: Quick 5-day blog project (smoke test)
**Team Size**: 2 people (Designer, Full-Stack Dev)
**Duration**: 5 business days (2,400 ticks)
**Language**: English
**Key Features**:
- Minimal team for fast execution
- Auto-tick with completion polling
- Graceful interrupt handling (Ctrl+C saves artifacts)

**Command**:
```bash
python short_blog_simulation.py
```

**Expected Outputs** (`simulation_output/blog_5day/`):
```
blog_5day/
├── mobile_team.json              # 2-person team
├── week_1_state.json
├── all_emails.json
├── all_chats.json
└── final_simulation_report.json
```

**Execution Flow**:
```
main()
├─ _maybe_start_services(force=True)
├─ _full_reset() → POST /api/v1/admin/hard-reset
├─ create_team()
│  ├─ POST /api/v1/personas/generate (× 2)
│  └─ POST /api/v1/people (× 2)
├─ run_sim()
│  ├─ POST /api/v1/simulation/start
│  ├─ POST /api/v1/simulation/advance (ticks=1, kickoff)
│  ├─ POST /api/v1/simulation/ticks/start
│  └─ [poll every 5s until 2400 ticks or KeyboardInterrupt]
├─ collect_emails()
├─ collect_chats()
└─ generate_reports()
```

---

### 4. `mobile_chat_simulation_ko.py`
**Purpose**: 4-week Korean localized simulation
**Team Size**: 4 people
**Duration**: 4 weeks
**Language**: Korean (all prompts, reports, communications)
**Key Features**:
- `VDOS_LOCALE=ko` environment setting
- Korean persona prompts
- Timestamped output directory
- Duration tracking with formatted time

**Command**:
```bash
python mobile_chat_simulation_ko.py
```

**Expected Outputs** (`simulation_output/mobile_4week_ko_{TIMESTAMP}/`):
```
mobile_4week_ko_20250117_143022/
├── team_personas.json
├── email_communications.json
├── chat_communications.json
├── final_state.json              # Includes simulation_duration
└── api_errors.json               # (if any errors occurred)
```

**Execution Flow**:
```
main()
├─ _maybe_start_services(force=True)
│  └─ os.environ["VDOS_LOCALE"] = "ko"
├─ _full_reset()
├─ create_team()
│  └─ [prompts in Korean: "Agile/Scrum 기반 모바일 앱 PM..."]
├─ run_sim(weeks=4)
│  ├─ POST /api/v1/simulation/start
│  ├─ POST /api/v1/simulation/advance (ticks=1, kickoff)
│  └─ [manual advancement with retry logic]
│     ├─ [chunk=60 ticks per call]
│     └─ [retry up to 3 times on failure, with backoff]
└─ collect_logs()
```

---

### 5. `multi_project_simulation_ko.py`
**Purpose**: 8-week multi-project simulation with 3 overlapping projects
**Team Size**: 4 people
**Duration**: 8 weeks (19,200 ticks)
**Language**: Korean
**Key Features**:
- **Project A**: Weeks 1-4 (Mobile App MVP)
- **Project B**: Weeks 3-6 (Web Dashboard)
- **Project C**: Weeks 4-8 (API Integration)
- All team members work on all projects

**Command**:
```bash
python multi_project_simulation_ko.py
```

**Expected Outputs** (`simulation_output/multi_project_8week_ko/`):
```
multi_project_8week_ko/
├── team_personas.json
├── email_communications.json
├── chat_communications.json
├── final_state.json
└── api_errors.json               # (if any)
```

**Project Timeline**:
```
Weeks: 1  2  3  4  5  6  7  8
       ├──┴──┴──┴──┴──┴──┴──┤
Proj A:[████████]
Proj B:      [████████]
Proj C:         [█████████████]
```

**Execution Flow**:
```
main()
├─ create_team() → 4 people
└─ run_multi_project_sim()
   ├─ POST /api/v1/simulation/start
   │  └─ payload.projects = [
   │       {"name": "모바일 앱 MVP", start_week: 1, duration: 4},
   │       {"name": "웹 대시보드", start_week: 3, duration: 4},
   │       {"name": "API 통합", start_week: 4, duration: 5}
   │     ]
   ├─ POST /api/v1/simulation/advance (ticks=1, kickoff)
   └─ [manual advancement in 60-tick chunks with retry]
```

---

### 6. `test_multiproject_3week_ko.py`
**Purpose**: 3-week multi-project test (2 overlapping projects)
**Team Size**: 3 people (PM, Designer, Developer)
**Duration**: 3 weeks (7,200 ticks)
**Language**: Korean
**Key Features**:
- **Project A**: Weeks 1-2 (Mobile App Features)
- **Project B**: Weeks 2-3 (Web Dashboard)
- Faster test of multi-project functionality

**Command**:
```bash
python test_multiproject_3week_ko.py
```

**Expected Outputs** (`simulation_output/test_multiproject_3week_ko/`):
```
test_multiproject_3week_ko/
├── team_personas.json
├── email_communications.json
├── chat_communications.json
└── final_state.json
```

**Project Timeline**:
```
Weeks: 1  2  3
       ├──┴──┤
Proj A:[████]
Proj B:   [████]
```

---

### 7. `quick_multiproject_test_ko.py`
**Purpose**: Ultra-fast 1-week multi-project test
**Team Size**: 2 people (PM, Developer)
**Duration**: 1 week (2,400 ticks)
**Language**: Korean
**Key Features**:
- Minimal team for speed
- 2 projects running simultaneously for the full week
- Timestamped output
- Duration tracking

**Command**:
```bash
python quick_multiproject_test_ko.py
```

**Expected Outputs** (`simulation_output/quick_multiproject_1week_ko_{TIMESTAMP}/`):
```
quick_multiproject_1week_ko_20250117_150000/
├── team_personas.json
├── email_communications.json
├── chat_communications.json
└── final_state.json              # Includes simulation_duration
```

**Project Timeline**:
```
Week: 1
      ├┤
Proj A:[█] (모바일 채팅 앱)
Proj B:[█] (웹 관리 대시보드)
```

---

### 8. `short_blog_simulation_ko.py`
**Purpose**: 5-day Korean blog simulation
**Team Size**: 2 people
**Duration**: 5 business days
**Language**: Korean
**Key Features**:
- Korean-specific GPTPlanner subclass (`KoreanGPTPlanner`)
- All responses forced to Korean via system message
- Fast smoke test with localization

**Command**:
```bash
python short_blog_simulation_ko.py
```

**Expected Outputs** (`simulation_output/blog_5day_ko/`):
```
blog_5day_ko/
├── mobile_team.json
├── week_1_state.json
├── all_emails.json
├── all_chats.json
└── final_simulation_report.json
```

**Execution Flow**:
```
main()
├─ _maybe_start_services(force=True)
│  └─ engine = SimulationEngine(..., planner=KoreanGPTPlanner())
├─ create_team()
│  └─ [prompts: "마케팅/블로그 사이트에 능숙한 UI/UX 디자이너..."]
└─ run_sim()
   └─ [auto-tick with Korean communications]
```

**KoreanGPTPlanner**:
```python
class KoreanGPTPlanner(GPTPlanner):
    def _invoke(self, messages, model):
        prefixed = [
            {"role": "system", "content": "모든 응답은 자연스러운 한국어로 작성하세요."}
        ] + list(messages)
        return super()._invoke(prefixed, model)
```

---

## Common Patterns Across All Scripts

### 1. Server Startup Pattern
```python
def _maybe_start_services(force: bool = False) -> list[_Srv]:
    handles: list[_Srv] = []
    if force:
        # Allocate fresh ports
        eport, cport, sport = _free_port(), _free_port(), _free_port()
        EMAIL_BASE_URL = f"http://127.0.0.1:{eport}"
        CHAT_BASE_URL = f"http://127.0.0.1:{cport}"
        SIM_BASE_URL = f"http://127.0.0.1:{sport}/api/v1"

    # Start email server
    handles.append(_start_server("email", email_app, host, port))

    # Start chat server
    handles.append(_start_server("chat", chat_app, host, port))

    # Start simulation manager with custom engine
    engine = SimulationEngine(
        email_gateway=HttpEmailGateway(base_url=EMAIL_BASE_URL),
        chat_gateway=HttpChatGateway(base_url=CHAT_BASE_URL),
        tick_interval_seconds=TICK_INTERVAL_SECONDS,
        hours_per_day=480  # minute-level ticks
    )
    handles.append(_start_server("sim", create_sim_app(engine), host, port))

    return handles
```

### 2. Persona Generation Pattern
```python
# Request GPT-generated persona
gen = api_call("POST", f"{SIM_BASE_URL}/personas/generate", {
    "prompt": "Experienced agile project manager...",
    "model_hint": "gpt-4.1-nano"
})

persona = gen["persona"]

# Enhance with project-specific fields
persona.update({
    "is_department_head": True,
    "email_address": "pm.1@company.dev",
    "chat_handle": "pm",
    "timezone": "America/New_York",
    "work_hours": "09:00-18:00"
})

# Create in system
created = api_call("POST", f"{SIM_BASE_URL}/people", persona)
```

### 3. Simulation Advancement Pattern

**Manual Advancement** (fast):
```python
ticks_per_week = 5 * 8 * 60  # 2,400 ticks
for week in range(4):
    remaining = ticks_per_week
    while remaining > 0:
        chunk = min(480, remaining)  # Advance in chunks
        api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {
            "ticks": chunk,
            "reason": f"Week {week+1} development"
        })
        remaining -= chunk
```

**Auto-Tick Advancement** (hands-off):
```python
# Kickoff
api_call("POST", f"{SIM_BASE_URL}/simulation/advance", {"ticks": 1, "reason": "kickoff"})

# Enable auto-tick
api_call("POST", f"{SIM_BASE_URL}/simulation/ticks/start", {})

# Poll until complete
target_tick = 9600  # 4 weeks
while True:
    state = api_call("GET", f"{SIM_BASE_URL}/simulation")
    if state["current_tick"] >= target_tick:
        break
    time.sleep(5)

# Stop auto-tick
api_call("POST", f"{SIM_BASE_URL}/simulation/ticks/stop", {})
```

### 4. Communication Collection Pattern
```python
# Emails
mailboxes = [p["email_address"] for p in personas]
emails = {}
for addr in mailboxes:
    emails[addr] = api_call("GET", f"{EMAIL_BASE_URL}/mailboxes/{addr}/emails")

# Chats (DMs between all pairs)
handles = [p["chat_handle"] for p in personas]
rooms = {}
for a, b in itertools.combinations(handles, 2):
    slug = f"dm:{min(a,b)}:{max(a,b)}"
    messages = api_call("GET", f"{CHAT_BASE_URL}/rooms/{slug}/messages")
    if messages:
        rooms[slug] = messages
```

---

## Environment Variables

All scripts respect these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VDOS_EMAIL_BASE_URL` | `http://127.0.0.1:8000` | Email server URL |
| `VDOS_CHAT_BASE_URL` | `http://127.0.0.1:8001` | Chat server URL |
| `VDOS_SIM_BASE_URL` | `http://127.0.0.1:8015/api/v1` | Simulation manager URL |
| `VDOS_SIM_EMAIL` | `simulator@vdos.local` | Sim manager email |
| `VDOS_SIM_HANDLE` | `sim-manager` | Sim manager chat handle |
| `VDOS_SIM_MODEL_HINT` | `gpt-4.1-nano` | GPT model for planning |
| `VDOS_TICK_INTERVAL_SECONDS` | `0.0002` (or `1.0`) | Auto-tick interval |
| `VDOS_LOCALE` | `en` | Locale for Korean scripts (`ko`) |
| `MOBILE_SIM_WEEKS` | `4` | Override weeks for mobile_chat_simulation |
| `OPENAI_API_KEY` | (required) | OpenAI API key for GPT calls |

---

## Performance Characteristics

### Tick Calculation
- **1 minute** = 1 tick
- **1 hour** = 60 ticks
- **1 day** (8 hours) = 480 ticks
- **1 week** (5 days) = 2,400 ticks
- **4 weeks** = 9,600 ticks

### Bottlenecks
1. **GPT API Calls**: Persona generation, planning, and reports
2. **Tick Advancement**: Linear with total ticks (but fast in manual mode)
3. **Communication Collection**: Linear with team size (O(n²) for DM pairs)

### Speed Optimization
- Use manual advancement (chunks of 60-480 ticks) instead of auto-tick
- Reduce `VDOS_SIM_MODEL_HINT` to faster models (gpt-4.1-nano vs gpt-4o)
- Smaller teams reduce planning overhead
- Shorter durations (1-2 weeks for testing)

---

## Troubleshooting

### Common Issues

**1. "Failed to start simulation"**
- Check `OPENAI_API_KEY` is set
- Verify services started (check logs for port conflicts)
- Ensure database is accessible

**2. Timeout during advance**
- Reduce chunk size (480 → 60 ticks)
- Increase timeout in `api_call(..., timeout=600)`
- Check GPT API rate limits

**3. No emails/chats collected**
- Verify team has email_address/chat_handle fields
- Check services are running on expected ports
- Ensure simulation actually ran (check tick count)

**4. Korean scripts output English**
- Verify `VDOS_LOCALE=ko` is set before engine creation
- Check `KoreanGPTPlanner` is used (short_blog_simulation_ko)
- Ensure prompts are in Korean

---

## Quick Reference Table

| Script | Team | Duration | Locale | Projects | Output Dir |
|--------|------|----------|--------|----------|------------|
| `quick_simulation.py` | 4 | 4 weeks | EN | 1 | `simulation_output/` |
| `mobile_chat_simulation.py` | 4 | 4 weeks | EN | 1 | `simulation_output/mobile_4week/` |
| `short_blog_simulation.py` | 2 | 5 days | EN | 1 | `simulation_output/blog_5day/` |
| `mobile_chat_simulation_ko.py` | 4 | 4 weeks | KO | 1 | `simulation_output/mobile_4week_ko_{TS}/` |
| `multi_project_simulation_ko.py` | 4 | 8 weeks | KO | 3 | `simulation_output/multi_project_8week_ko/` |
| `test_multiproject_3week_ko.py` | 3 | 3 weeks | KO | 2 | `simulation_output/test_multiproject_3week_ko/` |
| `quick_multiproject_test_ko.py` | 2 | 1 week | KO | 2 | `simulation_output/quick_multiproject_1week_ko_{TS}/` |
| `short_blog_simulation_ko.py` | 2 | 5 days | KO | 1 | `simulation_output/blog_5day_ko/` |

---

## Next Steps

- See `docs/workflows/call-graphs.md` for detailed execution flow diagrams
- See `docs/reference/api-call-reference.md` for API endpoint mappings
- See `docs/workflows/data-flow-diagrams.md` for data transformation flows
