# Virtual Department Operations Simulator

**Short name:** VDOS  
**Goal:** A fully scriptable, headless-first simulator that models how a small department communicates and coordinates work using only **email** and **chat**, with **statuses**, **work plans**, **unexpected events**, and **daily reports**—so you can test downstream tools (agents, analytics, dashboards) without real company data.

---

## Table of Contents
1. [Why this project exists](#why-this-project-exists)
2. [Core concepts](#core-concepts)
3. [System architecture](#system-architecture)
4. [Components](#components)
5. [Data model](#data-model)
6. [APIs](#apis)
7. [Simulation loop](#simulation-loop)
8. [Workflows](#workflows)
9. [Configuration](#configuration)
10. [Run locally](#run-locally)
11. [Seeding dummy personas & a project](#seeding-dummy-personas--a-project)
12. [Observability](#observability)
13. [Extending with AI](#extending-with-ai)
14. [Milestones & acceptance criteria](#milestones--acceptance-criteria)
15. [Repository layout](#repository-layout)
16. [License](#license)
17. [Appendix: Example payloads](#appendix-example-payloads)

---

## Why this project exists
In many orgs, the **data you want to analyze doesn’t exist yet** or can’t be shared. VDOS generates realistic, reproducible **email + chat traces**, tied to **people**, **roles**, **skills**, **personalities**, **schedules**, and **events**. You can:
- Stress-test inbox triage, absence summaries, prioritization, and report generation.
- Evaluate routing/escalation logic under noisy communication.
- Prototype monitoring GUIs (e.g., PyQt) or FastAPI backends without sensitive data.

---

## Core concepts

- **Tick**: the base simulation time unit. Default: `1 minute`.  
- **Workday**: a sequence of ticks; default scenario runs **5 business days**.
- **Channels**: all communication is via **Email** and **Chat** servers.
- **Roles**: `Manager (1)`, `ICs (3–5)`, plus a **Simulation Manager** (orchestrator).
- **Statuses**: `Working`, `Away` (meeting, break, lunch, external visit), `OffDuty`, `Overtime`, `SickLeave`, `Vacation`.
- **Plan granularity**: each person prepares an **hourly plan**, subdivided into minute-level tasks with communication steps embedded.
- **Events**: planned (routine) and unplanned (client change, blocker, sudden absence).
- **Daily report**: end-of-day summary produced by each person; feeds next day’s plan.

---

## System architecture

### Modular Architecture (Refactored Engine)

VDOS has been refactored from a monolithic 2360+ line engine into a modular, maintainable architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                     SimulationEngine                         │
│                    (Orchestrator <500 lines)                 │
│  - Coordinates modules                                       │
│  - Manages lifecycle                                         │
└────────┬────────────────────────────────────────────────────┘
         │
         ├──────────┬──────────┬──────────┬──────────┬─────────
         │          │          │          │          │
    ┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌──▼─────┐ ┌──▼────────┐
    │ State  │ │  Tick  │ │ Event  │ │ Comms  │ │  Project  │
    │Manager │ │Manager │ │ System │ │  Hub   │ │  Manager  │
    └────┬───┘ └────────┘ └────────┘ └────────┘ └───────────┘
         │
    ┌────▼──────────────────────────────────────────┐
    │        WorkerRuntime (per worker)             │
    │  - Individual worker state                     │
    │  - Message queue                               │
    └────┬──────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────────┐
    │           VirtualWorker                        │
    │  - Owns persona                                │
    │  - Plans autonomously                          │
    │  - Uses PromptManager                          │
    └────┬──────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────────┐
    │         PromptManager + Templates             │
    │  - YAML-based templates                        │
    │  - Context builders                            │
    │  - A/B testing support                         │
    └───────────────────────────────────────────────┘
```

**Core Modules:**
- **SimulationState**: Database operations and state persistence
- **TickManager**: Time advancement and work hours calculation
- **EventSystem**: Event injection and processing
- **CommunicationHub**: Email/chat coordination and scheduling
- **WorkerRuntime**: Per-worker state and message queuing
- **ProjectManager**: Project plans and team assignments
- **PromptManager**: Centralized YAML-based prompt templates with versioning

**Implementation stance**
- Each server is a standalone FastAPI app exposing REST endpoints.
- Core simulation logic is modularized into focused, testable components.
- Virtual workers are autonomous agents that plan and communicate using AI.
- A single process can host all services for simplicity in dev; split later if needed.

---

## Components

### 1) Email Server (FastAPI)
- Auto-provisions inbox when a person is created.
- REST for **send**, **list**, **get**, **save draft**.
- Stores messages with delivery metadata and threading keys.
- Optional SMTP/IMAP emulation is out-of-scope for v1; keep it REST.

### 2) Chat Server (FastAPI)
- Auto-provisions user identity.
- REST for **create room**, **post message**, **list history**, **DMs**.
- Rooms can be project-scoped or ad-hoc. DMs use a user-pair room key.

### 3) Simulation Manager
- Owns **clock**, **event schedule**, **project backlog**, and **policy knobs**.
- At each tick: advances time, dispatches planned sends, injects events, triggers replanning, records metrics, and writes audit logs.
- Supports per-run persona filters (include/exclude), reproducible random seeds, and automatic ticking loops.
- Persists runtime state (worker inbox queues, exchange logs, status overrides, events) so long-running sims survive restarts.
- Can run **headless** (CLI) or expose control endpoints.

### 4) Employee/Manager Agents
- Materialized from **markdown templates**:
  - `Name`, `Role`, `Skills`, `Personality`, `Daily schedule`, `Break frequency`.
- Maintain a personal **hourly plan** and **task queue**; adapt when events arrive.
- Generate **messages** (email/chat) as part of plan execution.
- Produce **daily report** before `OffDuty`.

### 5) Web Dashboard (Browser-Based Control Panel)
- Accessed via browser at `http://127.0.0.1:8015` when servers are running.
- Provides comprehensive simulation management:
  - **Persona Management**: Create/edit personas manually or with GPT-4o assistance (supports Korean localization)
  - **Multi-Project Configuration**: Add multiple projects, assign teams, set different timelines
  - **Team Organization**: Group personas into teams with `team_name` field
  - **Simulation Controls**: Start/stop, advance ticks, reset, auto-tick toggle
  - **Real-time Monitoring**: Adaptive refresh (60s when stopped, 5s when running)
  - **Observability**: View hourly plans, daily reports, events, and token usage
- Fully replaces previous PySide6 GUI - all operations now web-based.

---

## Data model

> Use SQLite for local dev; switchable to PostgreSQL via env.

### Tables / Collections (logical)

- **people**
  - `id`, `name`, `role`, `skills[]`, `personality`, `timezone`, `work_hours`, `break_pattern`, `email_address`, `chat_handle`, `status`
- **projects**
  - `id`, `name`, `description`, `start_date`, `end_date`, `status`
- **tasks**
  - `id`, `project_id`, `assignee_id`, `title`, `estimated_minutes`, `status`, `dependencies[]`, `priority`
- **plans**
  - `id`, `person_id`, `date`, `hour_block` (e.g., `09:00`), `entries[]` (minute-level steps, including comms)
- **events**
  - `id`, `type` (client_change, sick_leave, vacation, blocker, meeting), `target_ids[]`, `project_id?`, `at_tick`, `payload`
- **emails**
  - `id`, `thread_id`, `from`, `to[]`, `cc[]`, `subject`, `body`, `created_at_tick`, `delivered_at_tick`, `labels[]`, `draft:boolean`
- **chats**
  - `id`, `room_id`, `from`, `mentions[]`, `body`, `created_at_tick`, `delivered_at_tick`
- **rooms**
  - `id`, `name`, `type` (project, ad-hoc, dm), `members[]`
- **reports**
  - `id`, `person_id`, `date`, `summary`, `completed[]`, `blocked[]`, `planned_next[]`
- **metrics**
  - `tick`, `emails_sent`, `chats_sent`, `avg_response_minutes`, `utilization_pct`, `events_injected`

---

## APIs

All endpoints are versioned under `/api/v1`.

### Simulation Manager (Port 8015)
- `POST /api/v1/simulation/start` → Start simulation with project config
- `POST /api/v1/simulation/stop` → Stop running simulation  
- `POST /api/v1/simulation/advance` → Manual tick advancement
- `GET /api/v1/simulation` → Get current simulation state
- `GET /api/v1/simulation/reports` → Get simulation reports
- `GET /api/v1/simulation/token-usage` → Get token usage summary

### People Management
- `POST /api/v1/people` → Create person with full persona spec
- `GET /api/v1/people` → List all people
- `GET /api/v1/people/{id}` → Get specific person
- `GET /api/v1/people/{id}/daily-reports` → Get daily reports for person
- `GET /api/v1/people/{id}/plans` → Get plans (daily/hourly) for person

### Events
- `POST /api/v1/events` → Inject simulation events
- `GET /api/v1/events` → List events

### Email Server (Port 8000)
- `POST /emails/send` → Send email message
- `GET /mailboxes/{address}/emails` → Get emails for mailbox
- `POST /mailboxes/{address}/drafts` → Save draft
- `GET /mailboxes/{address}/drafts` → List drafts

### Chat Server (Port 8001)  
- `POST /rooms` → Create chat room
- `POST /rooms/{room_id}/messages` → Post message to room
- `POST /dm` → Send direct message
- `GET /rooms/{room_id}/messages` → Get room messages
- `GET /dm/{handle1}/{handle2}` → Get DM history

> See [Appendix](#appendix-example-payloads) for concrete JSON examples.

---

## Simulation loop

At each tick:
1. **Advance clock** and compute current hour block for each person.
2. **Apply scheduled plan entries** (work steps or comms):
   - If comms: enqueue **email/chat** via servers; record “send at tick”.
3. **Deliver messages** (zero or small delay).
4. **Handle incoming**: for each agent, read new messages → **replan if needed**.
5. **Process events** due at this tick:  
   - Examples: client change (adds/updates tasks), sudden absence (status flip), blocker (dependency unmet), meeting invite.
6. **Spillover planning**: unfinished steps roll into next hour block; adjust priorities.
7. **Metrics**: update counters, latencies, utilization.
8. **End-of-day**: generate **daily report**; set status to `OffDuty` unless `Overtime`.

---

## Workflows

### Onboarding (auto-provision)
- Create person → allocate `email_address` and `chat_handle` → add to default rooms.

### Daily planning (per person)
- Before first working hour: compile an **hourly plan** with minute-level steps (work segments, breaks, comm sends).
- Plans are private until executed (others only see effects via messages).

### Mid-hour replanning
- When an event/message arrives that requires time, agent **estimates minutes** and updates its queue. Overflows push into next hour; cascading spillover allowed.

### Absence handling
- While `Away`, messages accumulate; on return, agent triages backlog and replans.

### Daily report
- Contains: **completed**, **blocked (with reasons)**, **ETA for in-flight**, **plan for tomorrow**.

---

## Configuration

Environment variables (see `.env.template` for full list):

**Server Configuration:**
- `VDOS_CHAT_HOST=127.0.0.1`, `VDOS_CHAT_PORT=8001` – Chat server endpoint
- `VDOS_EMAIL_HOST=127.0.0.1`, `VDOS_EMAIL_PORT=8000` – Email server endpoint
- `VDOS_SIM_HOST=127.0.0.1`, `VDOS_SIM_PORT=8015` – Simulation Manager API endpoint
- `VDOS_DB_PATH` – SQLite database location (default: `src/virtualoffice/vdos.db`)

**API Configuration:**
- `OPENAI_API_KEY` – Primary OpenAI API key for LLM calls
- `OPENAI_API_KEY2` – Secondary OpenAI key (fallback)
- `OPENROUTER_API_KEY` – OpenRouter API key
- `VDOS_USE_OPENROUTER` – Set to `true` to use OpenRouter instead of OpenAI
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_AREA` – Azure OpenAI configuration

**Simulation Settings:**
- `VDOS_TICK_MS` (default `50`) – wall-clock milliseconds per simulation tick
- `VDOS_BUSINESS_DAYS` (default `5`)
- `VDOS_WORKDAY_START` (default `09:00`)
- `VDOS_WORKDAY_END` (default `18:00`)
- `VDOS_DEFAULT_BREAK_PATTERN` (e.g., `25/5, 90/lunch/60`)
- `VDOS_LOCALE_TZ` (default `Asia/Seoul`)
- `VDOS_LOCALE` (default `en`) – Language locale (`en` for English, `ko` for Korean with comprehensive localization)

---

## Run locally

> Requires Python 3.11+ and dependencies from `requirements.txt`.

### 1) Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Option A: Use the Web Dashboard (Recommended)

```bash
# Start all servers and open the web dashboard
briefcase dev
```

This will automatically:
- Start all three servers (Email :8000, Chat :8001, Simulation :8015)
- Open the web dashboard in your browser at `http://127.0.0.1:8015`

The web dashboard lets you:
- Create and manage personas (manually or with GPT-4o assistance)
- Configure multi-project simulations with different teams and timelines
- Control simulation (start/stop, advance ticks, auto-tick toggle)
- Monitor real-time state, plans, reports, and token usage

### 2) Option B: Start services manually (three terminals)

```bash
# Terminal A – Email server
uvicorn virtualoffice.servers.email:app --host 127.0.0.1 --port 8000 --reload

# Terminal B – Chat server  
uvicorn virtualoffice.servers.chat:app --host 127.0.0.1 --port 8001 --reload

# Terminal C – Simulation manager
uvicorn virtualoffice.sim_manager:create_app --host 127.0.0.1 --port 8015 --reload
```

### 3) Option C: Run a complete simulation script

```bash
# Run multi-team Korean locale simulations (2 or 5 weeks)
python scripts/test_multiteam_2week.py
python scripts/test_multiteam_5week.py

# Other simulation examples available in scripts/ directory
```

### 4) Smoke test via API

```bash
# Create a sample persona
curl -X POST http://127.0.0.1:8015/api/v1/people -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Johnson",
    "role": "Senior Developer", 
    "timezone": "Asia/Seoul",
    "work_hours": "09:00-18:00",
    "break_frequency": "50/10 cadence",
    "communication_style": "Direct, async",
    "email_address": "alice@vdos.local",
    "chat_handle": "alice",
    "skills": ["Python", "FastAPI"],
    "personality": ["Analytical", "Collaborative"]
  }'

# Start a simulation
curl -X POST http://127.0.0.1:8015/api/v1/simulation/start -H "Content-Type: application/json" \
  -d '{
    "project_name": "Dashboard MVP",
    "project_summary": "Build a metrics dashboard for team productivity",
    "duration_weeks": 2
  }'

# Advance the simulation by one day (480 ticks)
curl -X POST http://127.0.0.1:8015/api/v1/simulation/advance -H "Content-Type: application/json" \
  -d '{ "ticks": 480, "reason": "manual test" }'
```

### 5) Developer Notes: Refactored Architecture

VDOS has been refactored into a modular architecture for better maintainability:

**Core Modules** (in `src/virtualoffice/sim_manager/core/`):
- `simulation_state.py` - Database operations and state persistence
- `tick_manager.py` - Time advancement and work hours
- `event_system.py` - Event injection and processing
- `communication_hub.py` - Email/chat coordination
- `worker_runtime.py` - Per-worker state management
- `project_manager.py` - Project plans and assignments

**Prompt Management** (in `src/virtualoffice/sim_manager/prompts/`):
- `prompt_manager.py` - YAML template loading and caching
- `context_builder.py` - Context aggregation for prompts
- `metrics_collector.py` - Performance tracking
- `templates/` - YAML prompt templates (planning, reporting, events)

**Enhanced Workers** (in `src/virtualoffice/virtualWorkers/`):
- `virtual_worker.py` - Autonomous worker with planning capabilities
- `planner_mixin.py` - Planning methods
- `context_classes.py` - Context dataclasses for planning

For detailed documentation, see:
- `docs/architecture.md` - Complete architecture overview
- `docs/guides/migration_guide.md` - Migration guide for refactored engine
- `docs/guides/template_authoring.md` - Creating custom prompt templates
- `docs/guides/troubleshooting.md` - Troubleshooting common issues
- `docs/modules/` - Individual module documentation

---

## Seeding dummy personas & a project

Place files under `seeds/people/*.json` (or `.md` if you prefer to author then parse server-side).

**Example: `seeds/people/fullstack_ic.json`**

```json
{
  "name": "Lee Minseo",
  "role": "FullStack",
  "skills": ["React", "FastAPI", "SQL", "CI/CD"],
  "personality": "Conscientious, low-friction, prefers async over meetings.",
  "timezone": "Asia/Seoul",
  "work_hours": {"start": "09:00", "end": "18:00"},
  "break_pattern": "25/5,90/lunch/60",
  "planned_daily_meetings": [{"at": "10:00", "minutes": 15, "title": "Stand-up"}]
}
```

**Project seed: `seeds/projects/alpha_website.json`**

```json
{
  "name": "Alpha Website",
  "description": "Build a simple marketing site with contact form.",
  "tasks": [
    {"title": "Landing copy v1", "estimated_minutes": 120, "assignee": "PM"},
    {"title": "Hero section UI", "estimated_minutes": 180, "assignee": "UIUX"},
    {"title": "Form backend", "estimated_minutes": 240, "assignee": "FullStack"},
    {"title": "DB schema", "estimated_minutes": 90, "assignee": "DBDevOps"}
  ]
}
```

Load seeds:

```bash
curl -X POST http://127.0.0.1:8015/api/v1/projects/seed \
  -H "Content-Type: application/json" -d @seeds/projects/alpha_website.json
```

---

## Observability

* **Logs**: structured JSON per service (`/logs/*.jsonl`).
  Useful fields: `tick`, `actor`, `action`, `latency_ms`, `message_ids`, `event_id`.
* **Metrics**: `/api/v1/sim/state` returns a rolling summary; export Prometheus later.
* **Traces (optional)**: add OpenTelemetry for spans around “plan → send → deliver → replan”.

---

## Extending with AI

### Prompt Management System

VDOS includes a centralized prompt management system for AI-powered features:

* **YAML-based templates**: All LLM prompts are defined in versioned YAML templates
* **Template categories**: Planning (hourly, daily), reporting, events, communication
* **Localization support**: Separate templates for English (`_en.yaml`) and Korean (`_ko.yaml`)
* **A/B testing**: Support for prompt variants with performance metrics
* **Context-aware prompts**: Automatic context building with persona, team, project info
* **Metrics collection**: Track token usage, duration, and success rates per template

### AI Features

* **Plan synthesis**: LLM transforms role+skills+project context into hourly plans using template-based prompts
* **Persona generation**: GPT-4o assisted creation of realistic worker profiles with Korean localization support
* **Worker-driven planning**: Virtual workers autonomously plan and adapt using PromptManager
* **Drafting messages**: Generate polite, role-consistent emails/chats with personality preservation
* **Report generation**: Summarize completed/blocked/next tasks with consistent rubrics
* **Event reactions**: Workers respond to simulation events with context-aware adjustments
* **Korean localization**: Set `VDOS_LOCALE=ko` for natural Korean workplace communication across all AI features

### Template Authoring

Create custom prompt templates in `src/virtualoffice/sim_manager/prompts/templates/`:

```yaml
name: "hourly_planning_en"
version: "1.0"
locale: "en"
category: "planning"

system_prompt: |
  You act as an operations coach who reshapes hourly schedules.

user_prompt_template: |
  Worker: {worker_name} ({worker_role}) at tick {tick}.
  {persona_section}
  {team_roster_section}
  
  Plan the next few hours with realistic tasks.

sections:
  persona_section:
    template: "=== YOUR PERSONA ===\n{persona_markdown}"
    required_variables: ["persona_markdown"]

validation_rules:
  - "Must include scheduled communications section"
```

See `docs/guides/template_authoring.md` for complete guide.

> Keep a deterministic seed for reproducibility.

---

## Milestones & acceptance criteria

### ✅ M1 — Skeleton (COMPLETED)

* ✅ CRUD for **people**, **projects**, **tasks**
* ✅ Email & Chat servers running; can **send/list** messages
* ✅ Simulation Manager can **start/stop**, **advance ticks**, and **inject events**
* **Acceptance**: ✅ Run a 1-day sim that produces ≥ 20 messages and ≥ 3 events; daily reports exist.

### M2 — Planning & Replanning

* [ ] Agents create **hourly plans**; execute minute-steps
* [ ] **Replanning** on message/event with spillover
* [ ] Status transitions (`Working`, `Away`, `OffDuty`) affect delivery/triage
* **Acceptance**: A lunch-hour “Away” causes backlog+triage on return; visible in metrics.

### M3 — Department-level Scenarios

* [ ] Client change requests produce new tasks & message bursts
* [ ] Sudden absence (Sick/Vacation) redistributes workload
* [ ] End-of-day departmental report aggregates member reports
* **Acceptance**: 5-day run yields coherent project progress and roll-over tasks.

### ✅ M4 — Web Dashboard & Visualization (COMPLETED)

* ✅ Browser-based dashboard with real-time monitoring and controls
* ✅ Multi-project configuration UI with team assignment
* ✅ Persona creation and management interface
* ✅ Adaptive refresh rates based on simulation state
* ✅ Token usage and planner metrics visualization
* **Acceptance**: ✅ Complete web-based interface replaces desktop GUI; all operations performed via browser.

---

## Repository layout

```
virtualoffice/
├── src/virtualoffice/           # Main application package
│   ├── __main__.py             # CLI entry point
│   ├── app.py                  # Server launcher (auto-starts all services)
│   ├── servers/                # FastAPI service modules
│   │   ├── email/              # Email server (app.py, models.py)
│   │   └── chat/               # Chat server (app.py, models.py)
│   ├── sim_manager/            # Simulation engine and web dashboard
│   │   ├── app.py              # Simulation API endpoints
│   │   ├── engine.py           # Refactored orchestrator (<500 lines)
│   │   ├── planner.py          # GPT and Stub planners
│   │   ├── gateways.py         # HTTP client adapters
│   │   ├── schemas.py          # Request/response models
│   │   ├── core/               # NEW: Core simulation modules
│   │   │   ├── simulation_state.py  # State persistence & DB
│   │   │   ├── tick_manager.py      # Tick advancement & timing
│   │   │   ├── event_system.py      # Event injection & processing
│   │   │   ├── communication_hub.py # Email/chat coordination
│   │   │   ├── worker_runtime.py    # Worker runtime state
│   │   │   └── project_manager.py   # Project & planning coordination
│   │   ├── prompts/            # NEW: Centralized prompt system
│   │   │   ├── prompt_manager.py    # Template loading & caching
│   │   │   ├── context_builder.py   # Context aggregation
│   │   │   ├── metrics_collector.py # Performance tracking
│   │   │   └── templates/           # YAML prompt templates
│   │   │       ├── planning/        # Hourly/daily planning templates
│   │   │       ├── reporting/       # Daily report templates
│   │   │       └── events/          # Event reaction templates
│   │   ├── index_new.html      # Web dashboard interface
│   │   └── static/             # Dashboard assets (JS, CSS)
│   │       ├── js/dashboard.js # Dashboard client-side logic
│   │       └── css/styles.css  # Dashboard styling
│   ├── virtualWorkers/         # AI persona system
│   │   ├── worker.py           # Worker persona and markdown builder
│   │   ├── virtual_worker.py   # NEW: Enhanced autonomous worker
│   │   ├── planner_mixin.py    # NEW: Planning methods
│   │   └── context_classes.py  # NEW: Context dataclasses
│   ├── common/                 # Shared utilities
│   │   └── db.py               # SQLite connection helpers
│   ├── utils/                  # Helper functions
│   │   ├── completion_util.py  # OpenAI API wrapper
│   │   └── pdf_to_md.py        # PDF processing
│   ├── resources/              # Static resources
│   └── vdos.db                 # SQLite database file
├── tests/                      # Comprehensive test suite
│   ├── conftest.py             # Test configuration
│   ├── core/                   # NEW: Core module tests
│   │   ├── test_simulation_state.py
│   │   ├── test_tick_manager.py
│   │   ├── test_event_system.py
│   │   ├── test_communication_hub.py
│   │   ├── test_worker_runtime.py
│   │   └── test_project_manager.py
│   ├── prompts/                # NEW: Prompt system tests
│   │   ├── test_prompt_manager.py
│   │   └── test_context_builder.py
│   ├── integration/            # NEW: Integration tests
│   │   ├── test_long_simulation.py
│   │   └── test_multi_project.py
│   ├── performance/            # NEW: Performance benchmarks
│   │   ├── test_tick_advancement.py
│   │   ├── test_parallel_planning.py
│   │   ├── test_memory_usage.py
│   │   └── test_template_loading.py
│   ├── test_*.py               # Individual test modules
│   ├── test_auto_pause_integration.py # Auto-pause integration tests
│   ├── test_auto_pause_unit.py # Auto-pause unit tests
│   ├── test_auto_pause_workflow_integration.py # Workflow tests
│   ├── test_virtual_worker_enhanced.py # Enhanced VirtualWorker tests
│   ├── integration/            # Integration tests (Phase 5)
│   │   ├── __init__.py         # Integration test package
│   │   ├── test_long_simulation.py # 1-week and 4-week simulation tests
│   │   └── test_multi_project.py # Multi-project scenario tests
│   ├── performance/            # Performance benchmarks (Phase 5)
│   │   ├── test_tick_advancement.py # Tick advancement performance
│   │   ├── test_parallel_planning.py # Parallel planning benchmarks
│   │   ├── test_memory_usage.py # Memory profiling
│   │   └── test_template_loading.py # Template caching performance
│   └── virtualoffice.py        # Test utilities
├── docs/                       # Documentation
│   ├── README.md               # Documentation index
│   ├── GETTING_STARTED.md      # Setup and first simulation
│   ├── architecture.md         # System architecture
│   └── api/                    # API documentation
├── simulation_output/          # Generated simulation artifacts
├── agent_reports/              # AI-generated analysis reports
├── scripts/                    # Utility and simulation scripts
│   ├── test_multiteam_2week.py # Multi-team 2-week simulation
│   ├── test_multiteam_5week.py # Multi-team 5-week simulation
│   └── *.py                    # Other utility scripts
├── .env.template               # Environment configuration template
├── pyproject.toml              # Briefcase configuration
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## License

MIT (placeholder—adjust as needed).

---

## Appendix: Example payloads

**Create person (markdown spec allowed; server parses):**

```json
{
  "markdown": "## Name: Kim Hana\nRole: UI/UX\nSkills: Figma, Design Systems\nPersonality: Collaborative, detail-oriented\nDaily Schedule: 09:00-18:00\nBreak Frequency: 25/5, Lunch 60 min at 12:30"
}
```

**Send email:**

```json
{
  "from": "minseo.lee@vdos.local",
  "to": ["hana.kim@vdos.local"],
  "subject": "Hero section handoff",
  "body": "Uploading Figma link at 15:00. Can you review the spacing tokens?",
  "thread_id": "alpha-hero-1"
}
```

**Post chat message (DM by user pair):**

```json
{
  "from": "minseo",
  "dm_with": "hana",
  "body": "Heads up: API shape changed. Will push docs after stand-up."
}
```

**Inject event (client change):**

```json
{
  "type": "client_change",
  "target_ids": ["manager-1"],
  "project_id": "alpha",
  "at_tick": 540, 
  "payload": {
    "change": "Add multi-step form validation",
    "expected_extra_minutes": 180,
    "affects_roles": ["FullStack", "UIUX"]
  }
}
```

**Daily report (read):**

```json
{
  "person_id": "fullstack-1",
  "date": "2025-09-22",
  "summary": "Form backend progressed; validation pending new client request.",
  "completed": ["Form POST handler", "DB schema for leads"],
  "blocked": ["Validation rules from PM"],
  "planned_next": ["Implement client-side checks", "Update API docs"]
}
```

---

## 🎯 Project Status Summary

**VDOS is feature-complete and production-ready!** All major milestones have been achieved:

✅ **Full System Implementation**: Complete CRUD operations, REST APIs, and simulation engine
✅ **Modular Architecture**: Refactored from 2360+ line monolith to focused, testable modules (<500 line orchestrator)
✅ **Prompt Management System**: Centralized YAML-based templates with versioning and A/B testing
✅ **Worker-Driven Planning**: Autonomous virtual workers with context-aware AI planning
✅ **Advanced Planning**: Multi-level planning hierarchy with AI-powered generation
✅ **Web Dashboard**: Browser-based interface with real-time monitoring and comprehensive controls
✅ **Multi-Project Support**: Configure multiple projects with different teams and timelines via web UI
✅ **Team Organization**: Group personas into teams with flexible assignment and filtering
✅ **Production Features**: Token tracking, event system, adaptive refresh rates, comprehensive testing
✅ **Auto-Pause System**: Intelligent simulation lifecycle management with comprehensive integration testing
✅ **Configurable Architecture**: Server ports and API keys configurable via `.env` file

The system successfully generates realistic workplace communication patterns and is ready for use in testing downstream tools, research, and development scenarios.

**Quick Start**: Run `briefcase dev` to automatically start all servers and open the web dashboard - start your first simulation in minutes!

## Testing and Validation

VDOS includes a comprehensive test suite ensuring reliability and correctness across all components:

### Auto-Pause Integration Testing
- **Complete workflow validation**: End-to-end testing of auto-pause triggering when all projects complete
- **Multi-project scenarios**: Testing overlapping, sequential, and gap project timelines
- **API endpoint testing**: Full validation of request/response handling and error cases
- **State persistence**: Testing session-level configuration changes and persistence
- **Future project detection**: Validation that future projects prevent premature auto-pause

### Test Suite Organization
```bash
# Run the complete test suite
pytest tests/

# Run specific auto-pause tests
pytest tests/test_auto_pause_integration.py -v
pytest tests/test_auto_pause_unit.py -v
pytest tests/test_auto_pause_workflow_integration.py -v

# Run with coverage reporting
pytest tests/ --cov=src/virtualoffice
```

### Key Test Files
- `tests/test_auto_pause_integration.py` - Comprehensive integration tests for auto-pause functionality
- `tests/test_auto_pause_unit.py` - Unit tests for individual auto-pause components
- `tests/test_auto_pause_workflow_integration.py` - Workflow-specific integration tests
- `tests/test_sim_manager.py` - Simulation engine and manager tests
- `tests/test_email_server.py` - Email service endpoint tests
- `tests/test_chat_server.py` - Chat service endpoint tests