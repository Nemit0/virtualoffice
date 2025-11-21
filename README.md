# Virtual Department Operations Simulator (VDOS)

Headless-first sandbox that simulates a small department's communication loop (email + chat), personas, and projects so you can test downstream dashboards, analytics, and agents without production data.

---

## Highlights
- FastAPI services for chat (`:8001`), email (`:8000`), simulation control (`:8015`), and email clustering (`:8016`), orchestrated by the server launcher in `src/virtualoffice/app.py`.
- Browser dashboard (`src/virtualoffice/sim_manager/index.html`) for persona management, multi-project setup, auto-tick controls, auto-pause, replay, style filtering, token usage, and clustering visualizations.
- Simulation start supports single or multi-project timelines, team assignments (`team_name`), include/exclude persona filters, reproducible seeds, and model hints.
- Communication pipeline with inbox-driven replies, participation balancing, daily message caps, and an optional GPT style filter to keep messages on-brand.
- OpenAI-powered persona generation (English + Korean), style example regeneration, import/export of personas/projects, and debug endpoints for monitoring chat/email traffic.
- SQLite-backed state (`virtualoffice/common/db.py`) with optional migrations for inbox logging, participation stats, and communication generation logs.

---

## Architecture
```
                   Web Dashboard (port 8015)
                           |
                           v
[Email Server :8000]   [Chat Server :8001]   [Simulation API :8015]   [Clustering API :8016]
         \                    |                     |                        /
                            SQLite (vdos.db)
```
- **Launcher:** `src/virtualoffice/app.py` starts chat -> email -> simulation -> clustering, then opens the dashboard.
- **Simulation engine:** `src/virtualoffice/sim_manager/engine.py` coordinates planning, tick progression, events, communications, inbox replies, participation balancing, and reporting.
- **Dashboard assets:** `src/virtualoffice/sim_manager/static/js` (orchestrator, personas/projects modules, email/chat clients, replay, clustering) + `static/css/styles.css`.
- **Style filter:** `src/virtualoffice/sim_manager/style_filter/` for persona-consistent messaging; metrics and tuning exposed via API and dashboard tab.
- **Clustering:** `src/virtualoffice/servers/clustering/app.py` + `src/virtualoffice/clustering/*` for FAISS-backed email clustering and labeling.

---

## Web Dashboard (http://127.0.0.1:8015)
- **Simulation controls:** start/stop/reset, manual advance, auto-tick interval, auto-pause toggle, replay mode, and status surface.
- **Personas:** create/edit manually, GPT-4o/4.1 persona generation (English/Korean), style example regeneration, preview/transform messages, import/export JSON.
- **Projects:** multi-project timelines with start/duration weeks, team assignments via `team_name` or explicit person IDs, export/import helpers.
- **Monitoring:** email and chat tabs read from the services via CORS-friendly proxy endpoints; includes folder switching for emails and room/DM filters for chat.
- **Style filter:** enable/disable, adjust sampling (`gpt-4o`/`gpt-4o-mini`), inspect metrics, and manage style examples.
- **Replay:** jump to tick, toggle replay mode, and view current replay window.
- **Clustering:** build per-persona FAISS indexes, view cluster summaries, drill into clusters/emails, and clear/rebuild indexes.

---

## Services & Key APIs

### Simulation Manager (`src/virtualoffice/sim_manager/app.py`, port 8015)
- **Personas:** `GET/POST /api/v1/people`, GPT persona generation (`POST /api/v1/personas/generate`), style example regeneration (`POST /api/v1/people/{id}/regenerate-style-examples`), preview filter (`POST /api/v1/personas/preview-filter`), delete by name.
- **Projects:** `GET /api/v1/projects`, project plan fetch, active projects, delete; export/import via `/api/v1/export/projects` and `/api/v1/import/projects`.
- **Simulation control:** `POST /api/v1/simulation/start`, `/stop`, `/reset`, `/full-reset`, `/advance`, auto-tick start/stop, tick interval setters, auto-pause status/toggle, init-status.
- **Reporting & metrics:** plans (`/people/{id}/plans`), daily reports, simulation reports, token usage, quality metrics, volume metrics, planner metrics, runtime debug info.
- **Events:** `POST/GET /api/v1/events` for injecting scenario changes.
- **Monitoring:** proxied inbox/room readers (`/monitor/emails/{person_id}`, `/monitor/chat/messages/{person_id}`, `/monitor/chat/rooms/{person_id}`, `/monitor/chat/room/{slug}/messages`).
- **Style filter:** `/style-filter/config` and `/style-filter/metrics`.
- **Replay:** `/replay/metadata`, `/replay/jump/{tick}`, `/replay/current`, `/replay/mode`, `/replay/reset`.
- **Import/Export:** personas/projects backup + restore; admin hard/soft reset and rewind endpoints for support.

### Email Server (`src/virtualoffice/servers/email/app.py`, port 8000)
- Ensures mailboxes exist (`PUT /mailboxes/{address}`), send email (`POST /emails/send`), list emails per mailbox, thread-aware draft save/list. Emails and recipients are persisted in SQLite; mailboxes auto-provision on send.

### Chat Server (`src/virtualoffice/servers/chat/app.py`, port 8001)
- Ensure users (`PUT /users/{handle}`), create rooms (`POST /rooms`), post room messages, list room history, send/list DMs (`/dms`), list rooms and messages for a user. Users and rooms auto-provision as needed.

### Clustering Server (`src/virtualoffice/servers/clustering/app.py`, port 8016)
- Index emails per persona (`POST /clustering/index/{persona_id}`), list personas + indexing status, fetch clusters/points, fetch raw email content for a cluster or message, optimize labels, and clear indexes.

---

## Simulation Model & Features
- **Tick model:** 1 tick = 1 minute of simulated time; defaults to 480 ticks/day. Tick formatting and work-hour helpers live in `src/virtualoffice/sim_manager/core/tick_manager.py`.
- **Start payload:** `SimulationStartRequest` supports single-project fields (`project_name`, `project_summary`, `duration_weeks`) or multi-project timelines (`projects[]` with `project_name`, `project_summary`, `start_week`, `duration_weeks`, `assigned_person_ids`). Include/exclude filters, `department_head_name`, `model_hint`, `random_seed`, and `total_duration_weeks` are available.
- **Planning:** `GPTPlanner` (OpenAI), `StubPlanner` fallback. Plans feed the execution loop, communication generator, and report creation.
- **Communications:** inbox-driven replies (`VDOS_ENABLE_INBOX_REPLIES`, probability via `VDOS_INBOX_REPLY_PROBABILITY`), participation balancing to avoid message dominance, daily message caps (`VDOS_MAX_EMAILS_PER_DAY`, `VDOS_MAX_CHATS_PER_DAY`), optional automatic fallback comms (`VDOS_ENABLE_AUTO_FALLBACK=false` by default).
- **Style filter:** optional GPT-4o pass to align persona voice (`VDOS_STYLE_FILTER_ENABLED=true`); metrics tracked and exposed to the UI.
- **Events & overrides:** inject events via `/api/v1/events`; temporary status overrides via `/api/v1/people/{id}/status-override` endpoints for integration tests or external control.
- **Auto-pause & replay:** auto-pause when projects conclude (toggle via API/UI); replay manager can jump to ticks and rehydrate state for review.
- **Localization:** `VDOS_LOCALE` controls locale; Korean personas and content are supported. Persona generation prompts adapt automatically.

---

## Setup
1) **Python environment**
```bash
python -m venv .venv
.\.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

2) **Environment variables** (see `.env.template`, copy to `.env`)
- `OPENAI_API_KEY` (primary), optional `OPENAI_API_KEY2`, `OPENROUTER_API_KEY`, Azure settings.
- Provider selection: `VDOS_API_PROVIDER` (`auto`|`openai_key1`|`openai_key2`|`azure`), `VDOS_USE_OPENROUTER`.
- Communication controls: `VDOS_STYLE_FILTER_ENABLED`, `VDOS_ENABLE_AUTO_FALLBACK`, `VDOS_ENABLE_INBOX_REPLIES`, `VDOS_INBOX_REPLY_PROBABILITY`, `VDOS_MAX_EMAILS_PER_DAY`, `VDOS_MAX_CHATS_PER_DAY`, `VDOS_PARTICIPATION_BALANCE_ENABLED`, `VDOS_THREADING_RATE`, `VDOS_FALLBACK_MODEL`.
- Locale: `VDOS_LOCALE` (`en`/`ko`), optional temperature/timeout overrides for OpenAI calls.
- Server ports/hosts: `VDOS_CHAT_HOST/PORT`, `VDOS_EMAIL_HOST/PORT`, `VDOS_SIM_HOST/PORT`, `VDOS_CLUSTER_HOST/PORT`, DB override `VDOS_DB_PATH`.
- Dev logging: `VDOS_DEV_LOGGING_ENABLED` (default on). When enabled, `briefcase dev` mirrors stdout/stderr to `logs/YYYYMMDD_HHMMSS_briefcase_dev.log` while preserving console output. Override log directory with `VDOS_LOG_DIR` if needed.

3) **Database migrations (optional analytics tables)**
```bash
python -m virtualoffice.sim_manager.migrations.run_migrations
```

---

## Running locally

### All services + dashboard
```bash
# From repo root
briefcase dev
```
`src/virtualoffice/app.py` starts chat -> email -> simulation -> clustering, then opens http://127.0.0.1:8015.
Stdout/stderr are mirrored to `logs/<timestamp>_briefcase_dev.log` by default; disable via `VDOS_DEV_LOGGING_ENABLED=false` or redirect logs using `VDOS_LOG_DIR`.

### Start services manually
```bash
uvicorn virtualoffice.servers.email.app:app --host 127.0.0.1 --port 8000
uvicorn virtualoffice.servers.chat.app:app --host 127.0.0.1 --port 8001
uvicorn virtualoffice.sim_manager.app:app --host 127.0.0.1 --port 8015
uvicorn virtualoffice.servers.clustering.app:app --host 127.0.0.1 --port 8016
```

---

## Testing
```bash
python -m pytest
```
Notable coverage: simulation control (`tests/test_sim_manager.py`), email/chat services, volume reduction and inbox reply logic, style filter (including UI), localization (Korean), auto-pause workflows, multi-project scenarios, metrics, and dashboard smoke tests.

---

## Repository Layout (high level)
```
src/virtualoffice/
  app.py                      # Server launcher
  servers/
    email/app.py, models.py   # Email REST service
    chat/app.py, models.py    # Chat REST service
    clustering/app.py         # Email clustering API
  sim_manager/
    app.py                    # FastAPI simulation API + dashboard host
    engine.py                 # Simulation engine (planning, events, comms, persistence)
    planner.py, gateways.py   # Planner implementations and HTTP gateways
    communication_generator.py, inbox_manager.py, participation_balancer.py, plan_parser.py, quality_metrics.py
    replay_manager.py         # Replay support
    style_filter/             # Persona style filter + metrics
    core/                     # Tick manager, lifecycle helpers, planning orchestrator, state stores
    static/                   # Dashboard JS/CSS/assets (includes clustering + replay)
    migrations/               # Optional DB migrations
  clustering/                 # FAISS store, clustering engine, label optimizer
  virtualWorkers/             # Persona builders and virtual worker helpers
  common/db.py                # SQLite helpers (vdos.db resolution + WAL)
  utils/completion_util.py    # OpenAI/OpenRouter/Azure client wrapper
tests/                        # Unit/integration/performance suites
docs/                         # Additional guides and architecture notes
scripts/                      # Helper scripts for simulations and specs
```

---

## Example API Calls

Create a persona:
```bash
curl -X POST http://127.0.0.1:8015/api/v1/people \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Johnson",
    "role": "Product Manager",
    "timezone": "Asia/Seoul",
    "work_hours": "09:00-18:00",
    "break_frequency": "50/10 cadence",
    "communication_style": "Direct, async-first",
    "email_address": "alice@vdos.local",
    "chat_handle": "alice",
    "team_name": "mvp",
    "skills": ["Product strategy", "Backlog grooming"],
    "personality": ["Analytical", "Collaborative"],
    "planning_guidelines": ["Keep updates concise", "Surface risks early"]
  }'
```

Start a simulation (multi-project example):
```bash
curl -X POST http://127.0.0.1:8015/api/v1/simulation/start \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Department Sandbox",
    "project_summary": "Baseline run for dashboard testing",
    "duration_weeks": 4,
    "random_seed": 42,
    "projects": [
      {"project_name": "Dashboard", "project_summary": "Ship analytics UI", "start_week": 1, "duration_weeks": 4},
      {"project_name": "Mobile App", "project_summary": "Onboarding revamp", "start_week": 2, "duration_weeks": 3}
    ],
    "include_person_names": ["Alice Johnson"]
  }'
```

Inject an event:
```bash
curl -X POST http://127.0.0.1:8015/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"type": "client_change", "target_ids": [1], "project_id": "Dashboard", "at_tick": 180, "payload": {"change": "Add SSO", "expected_extra_minutes": 120}}'
```

---

VDOS is under active development; the dashboard and APIs reflect the current engine behavior. Use the simulation API and dashboard together for the smoothest experience.
