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

```

+-----------------------+           +----------------------+
\|   Simulation Manager  |<--------->|  State Store (SQLite |
\|  (orchestrates ticks) |           |   or PostgreSQL)     |
+-----------+-----------+           +----------+-----------+
\|                                   |
v                                   v
+----------------------+               +---------------------+
\|     Email Server     |<------------->|      Chat Server    |
\|  (FastAPI service)   |               |   (FastAPI service) |
+----------+-----------+               +----------+----------+
^                                      ^
\|                                      |
\|                                      |
+------+-------+                        +-----+------+
\|   Agents     |                        | Monitoring |
\| (Employees)  |                        |   GUI/API  |
+--------------+                        +------------+

````

**Implementation stance**
- Each server is a standalone FastAPI app exposing REST endpoints.
- Agents are headless workers (async tasks) that call those endpoints.
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
- Can run **headless** (CLI) or expose control endpoints.

### 4) Employee/Manager Agents
- Materialized from **markdown templates**:
  - `Name`, `Role`, `Skills`, `Personality`, `Daily schedule`, `Break frequency`.
- Maintain a personal **hourly plan** and **task queue**; adapt when events arrive.
- Generate **messages** (email/chat) as part of plan execution.
- Produce **daily report** before `OffDuty`.

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

### People
- `POST /people` → create person from a markdown spec (fields parsed server-side)
- `GET /people` → list
- `PATCH /people/{id}/status` → set status (e.g., `Working`, `Away:Lunch`)

### Email
- `POST /email/messages` → send (`from`, `to`, `subject`, `body`, `thread_id?`)
- `GET /email/messages?owner_id=&label=&since_tick=&limit=`
- `GET /email/messages/{id}`
- `POST /email/drafts` → save draft

### Chat
- `POST /chat/rooms` → create (`type`, `name`, `members`)
- `POST /chat/messages` → post (`room_id|dm_with`, `from`, `body`, `mentions?`)
- `GET /chat/messages?room_id=&since_tick=&limit=`

### Simulation
- `POST /sim/start` → `{ "tick_ms": 50, "business_days": 5 }`
- `POST /sim/stop`
- `POST /sim/advance` → `{ "ticks": 60 }` (manual stepping)
- `POST /sim/events` → inject event(s)
- `GET /sim/state` → clock, day, summary metrics

### Reports
- `GET /reports/daily?person_id=&date=`
- `GET /reports/department?date=`

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

Environment variables (common):
- `VDOS_DB_URL` (default `sqlite:///./vdos.db`)
- `VDOS_TICK_MS` (default `50`) – wall-clock milliseconds per simulation tick
- `VDOS_BUSINESS_DAYS` (default `5`)
- `VDOS_WORKDAY_START` (default `09:00`)
- `VDOS_WORKDAY_END` (default `18:00`)
- `VDOS_DEFAULT_BREAK_PATTERN` (e.g., `25/5, 90/lunch/60`)
- `VDOS_LOCALE_TZ` (default `Asia/Seoul`)

Service ports (defaults):
- Email API: `8025`
- Chat API: `8035`
- Simulation Manager API: `8015`

---

## Run locally

> Assumes Python 3.11+ and `uvicorn`/`fastapi` installed via `requirements.txt`.

### 1) Install dependencies
```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
````

### 2) Start services (three terminals)

```bash
# Terminal A – Email server
export VDOS_DB_URL=sqlite:///./vdos.db
uvicorn email_server.app:app --host 127.0.0.1 --port 8025 --reload

# Terminal B – Chat server
uvicorn chat_server.app:app --host 127.0.0.1 --port 8035 --reload

# Terminal C – Simulation manager
uvicorn sim_manager.app:app --host 127.0.0.1 --port 8015 --reload
```

### 3) Smoke test

```bash
# Create people
curl -X POST http://127.0.0.1:8015/api/v1/people -H "Content-Type: application/json" \
  -d @seeds/people/manager_pm.json

curl -X POST http://127.0.0.1:8015/api/v1/people -H "Content-Type: application/json" \
  -d @seeds/people/fullstack_ic.json

# Start sim for 5 business days with 1min ticks at 50ms real time
curl -X POST http://127.0.0.1:8015/api/v1/sim/start -H "Content-Type: application/json" \
  -d '{ "tick_ms": 50, "business_days": 5 }'
```

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

* **Plan synthesis**: use an LLM prompt to transform role+skills+project context into hourly plans.
* **Drafting messages**: generate polite, role-consistent emails/chats; keep a “tone” profile per person.
* **Report generation**: summarize completed/blocked/next; enforce consistent rubric.
* **Event realism**: sample distributions for delays, misunderstanding probability, and rework rates.

> Keep a deterministic seed for reproducibility.

---

## Milestones & acceptance criteria

### M1 — Skeleton (✅ when)

* [ ] CRUD for **people**, **projects**, **tasks**
* [ ] Email & Chat servers running; can **send/list** messages
* [ ] Simulation Manager can **start/stop**, **advance ticks**, and **inject events**
* **Acceptance**: Run a 1-day sim that produces ≥ 20 messages and ≥ 3 events; daily reports exist.

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

### M4 — GUI / Visualization (optional)

* [ ] PyQt or web dashboard with status lanes, message counters, and per-agent timelines.

---

## Repository layout

```
.
├── email_server/
│   ├── app.py
│   └── models.py
├── chat_server/
│   ├── app.py
│   └── models.py
├── sim_manager/
│   ├── app.py
│   ├── engine.py
│   └── policies.py
├── common/
│   ├── db.py
│   ├── schemas.py
│   └── utils.py
├── seeds/
│   ├── people/
│   └── projects/
├── scripts/
│   └── run_local.sh
├── tests/
│   └── e2e_smoketest.py
├── requirements.txt
└── README.md
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
