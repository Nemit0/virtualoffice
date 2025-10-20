# VDOS Module Dependencies

Visual dependency graphs showing import relationships and runtime API calls.

---

## 1. Import Dependency Graph

**Compile-time module imports (Python `import` statements)**

```
Root Level (Simulation Scripts)
├─ quick_simulation.py
│  ├─ import virtualoffice.servers.email.app (email_app)
│  ├─ import virtualoffice.servers.chat.app (chat_app)
│  ├─ import virtualoffice.sim_manager (create_sim_app)
│  ├─ import requests
│  ├─ import uvicorn
│  └─ import threading
│
├─ mobile_chat_simulation.py
│  ├─ import virtualoffice.servers.email.app
│  ├─ import virtualoffice.servers.chat.app
│  ├─ import virtualoffice.sim_manager
│  ├─ import virtualoffice.sim_manager.gateways (HttpEmailGateway, HttpChatGateway)
│  └─ import virtualoffice.sim_manager.engine (SimulationEngine)
│
└─ short_blog_simulation.py
   ├─ import virtualoffice.servers.email.app
   ├─ import virtualoffice.servers.chat.app
   ├─ import virtualoffice.sim_manager
   ├─ import virtualoffice.sim_manager.gateways
   ├─ import virtualoffice.sim_manager.engine
   └─ import virtualoffice.sim_manager.planner (GPTPlanner)

Simulation Manager (src/virtualoffice/sim_manager/)
├─ app.py
│  ├─ import fastapi (FastAPI, Depends, HTTPException, Query, Body, etc.)
│  ├─ import .engine (SimulationEngine)
│  ├─ import .gateways (HttpEmailGateway, HttpChatGateway)
│  ├─ import .schemas (all Pydantic models)
│  └─ [dynamic] from virtualoffice.utils.completion_util import generate_text
│
├─ engine.py
│  ├─ import virtualoffice.common.db (get_connection, execute_script)
│  ├─ import virtualoffice.virtualWorkers.worker (build_worker_markdown, WorkerPersona, etc.)
│  ├─ import .gateways (ChatGateway, EmailGateway)
│  ├─ import .planner (GPTPlanner, StubPlanner, PlanResult, Planner)
│  ├─ import .schemas (EventCreate, PersonCreate, PersonRead, etc.)
│  ├─ import threading
│  ├─ import random
│  └─ import json
│
├─ gateways.py
│  ├─ import abc (ABC, abstractmethod)
│  ├─ import requests
│  └─ import json
│
├─ planner.py
│  ├─ import abc (ABC, abstractmethod)
│  ├─ import json
│  ├─ import dataclasses (dataclass)
│  └─ [dynamic] from virtualoffice.utils.completion_util import generate_text
│
└─ schemas.py
   └─ import pydantic (BaseModel, Field, validator)

Email Server (src/virtualoffice/servers/email/)
├─ app.py
│  ├─ import fastapi (FastAPI, HTTPException, status)
│  ├─ import .models (EmailSend, EmailRead, Mailbox, DraftCreate, etc.)
│  └─ import virtualoffice.common.db (get_connection, execute_script)
│
└─ models.py
   └─ import pydantic (BaseModel, Field)

Chat Server (src/virtualoffice/servers/chat/)
├─ app.py
│  ├─ import fastapi (FastAPI, HTTPException, status)
│  ├─ import .models (MessageSend, MessageRead, RoomCreate, User, etc.)
│  └─ import virtualoffice.common.db (get_connection, execute_script)
│
└─ models.py
   └─ import pydantic (BaseModel, Field)

Virtual Workers (src/virtualoffice/virtualWorkers/)
└─ worker.py
   ├─ import dataclasses (dataclass, field)
   └─ import typing (List)

Common Utilities (src/virtualoffice/common/)
└─ db.py
   ├─ import sqlite3
   ├─ import os
   └─ import pathlib (Path)

Utilities (src/virtualoffice/utils/)
└─ completion_util.py
   ├─ import openai (OpenAI)
   └─ import os
```

---

## 2. Runtime API Call Dependencies

**Which modules make HTTP calls to which services**

```
Simulation Scripts
│
├─ POST /api/v1/admin/hard-reset          → Simulation Manager
├─ POST /api/v1/personas/generate         → Simulation Manager
├─ POST /api/v1/people                    → Simulation Manager
├─ POST /api/v1/simulation/start          → Simulation Manager
├─ POST /api/v1/simulation/advance        → Simulation Manager
├─ POST /api/v1/simulation/ticks/start    → Simulation Manager
├─ POST /api/v1/simulation/ticks/stop     → Simulation Manager
├─ GET  /api/v1/simulation                → Simulation Manager
├─ GET  /api/v1/events                    → Simulation Manager
├─ GET  /api/v1/simulation/token-usage    → Simulation Manager
├─ GET  /api/v1/people/{id}/daily-reports → Simulation Manager
├─ GET  /api/v1/people/{id}/plans         → Simulation Manager
│
├─ GET  /mailboxes/{address}/emails       → Email Server (direct)
└─ GET  /rooms/{slug}/messages            → Chat Server (direct)

Simulation Manager (engine.py)
│
├─ email_gateway.ensure_mailbox()
│  └─ POST /mailboxes                     → Email Server
│
├─ email_gateway.send_email()
│  └─ POST /emails/send                   → Email Server
│
├─ email_gateway.get_emails()
│  └─ GET  /mailboxes/{address}/emails    → Email Server
│
├─ chat_gateway.ensure_user()
│  └─ POST /users                         → Chat Server
│
├─ chat_gateway.ensure_room()
│  └─ POST /rooms                         → Chat Server
│
├─ chat_gateway.send_message()
│  └─ POST /messages                      → Chat Server
│
├─ chat_gateway.get_messages()
│  └─ GET  /rooms/{slug}/messages         → Chat Server
│
└─ planner.plan_project() / plan_hourly() / plan_daily()
   └─ completion_util.generate_text()
      └─ POST https://api.openai.com/v1/chat/completions

Simulation Manager (app.py)
│
└─ _generate_persona_from_prompt()
   └─ completion_util.generate_text()
      └─ POST https://api.openai.com/v1/chat/completions

Email Server (app.py)
│
└─ [no outbound API calls - only database operations]

Chat Server (app.py)
│
└─ [no outbound API calls - only database operations]

Virtual Workers (worker.py)
│
└─ [no API calls - pure data transformation]

Common DB (db.py)
│
└─ [SQLite file operations only]

Completion Util (completion_util.py)
│
└─ client.chat.completions.create()
   └─ POST https://api.openai.com/v1/chat/completions
```

---

## 3. Service Communication Graph

**HTTP-based communication between services**

```
┌─────────────────────────────────┐
│   Simulation Scripts            │
│   (quick_simulation.py, etc.)   │
└───────────┬─────────────────────┘
            │
            │ REST API calls
            │
            v
┌───────────────────────────────────────────────┐
│   Simulation Manager (:8015)                  │
│   - /api/v1/people                            │
│   - /api/v1/simulation/*                      │
│   - /api/v1/personas/generate                 │
│   - /api/v1/events                            │
└───┬─────────────────────┬─────────────────────┘
    │                     │
    │ HTTP                │ HTTP
    │ (via gateways)      │ (via gateways)
    │                     │
    v                     v
┌───────────────┐     ┌───────────────┐
│ Email Server  │     │  Chat Server  │
│ (:8000)       │     │  (:8001)      │
│               │     │               │
│ /mailboxes    │     │ /users        │
│ /emails/send  │     │ /rooms        │
│ /emails       │     │ /messages     │
└───────────────┘     └───────────────┘
    │                     │
    v                     v
┌────────────────────────────────┐
│   SQLite Database              │
│   (vdos.db)                    │
│                                │
│   Tables:                      │
│   - mailboxes, emails          │
│   - users, rooms, messages     │
│   - people, schedule_blocks    │
│   - simulation_state           │
│   - project_plans              │
│   - worker_plans               │
│   - daily_reports              │
│   - events                     │
│   - worker_exchange_log        │
└────────────────────────────────┘

External Services:
┌─────────────────────────────────┐
│   OpenAI API                    │
│   (https://api.openai.com)      │
│                                 │
│   - /v1/chat/completions        │
└───────────^─────────────────────┘
            │
            │ HTTPS
            │
    ┌───────┴────────┐
    │                │
┌───────────────┐ ┌──────────────┐
│ sim_manager/  │ │ sim_manager/ │
│ planner.py    │ │ app.py       │
└───────────────┘ └──────────────┘
```

---

## 4. Database Access Patterns

**Which modules access which database tables**

```
SQLite Database (vdos.db)
│
├─ Email Server Tables
│  ├─ mailboxes
│  │  ├─ WRITE: servers/email/app.py:create_mailbox()
│  │  ├─ READ:  servers/email/app.py:get_mailbox()
│  │  └─ READ:  servers/email/app.py:send_email() [ensure exists]
│  │
│  ├─ emails
│  │  ├─ WRITE: servers/email/app.py:send_email()
│  │  ├─ READ:  servers/email/app.py:get_emails()
│  │  └─ DELETE: servers/email/app.py:delete_email()
│  │
│  └─ drafts
│     ├─ WRITE: servers/email/app.py:create_draft()
│     ├─ READ:  servers/email/app.py:get_drafts()
│     └─ DELETE: servers/email/app.py:delete_draft()
│
├─ Chat Server Tables
│  ├─ users
│  │  ├─ WRITE: servers/chat/app.py:create_user()
│  │  ├─ READ:  servers/chat/app.py:get_user()
│  │  └─ READ:  servers/chat/app.py:send_message() [ensure exists]
│  │
│  ├─ rooms
│  │  ├─ WRITE: servers/chat/app.py:create_room()
│  │  ├─ READ:  servers/chat/app.py:get_room()
│  │  └─ READ:  servers/chat/app.py:send_message() [ensure exists]
│  │
│  ├─ memberships
│  │  ├─ WRITE: servers/chat/app.py:add_member()
│  │  └─ READ:  servers/chat/app.py:get_room_members()
│  │
│  └─ messages
│     ├─ WRITE: servers/chat/app.py:send_message()
│     ├─ READ:  servers/chat/app.py:get_messages()
│     └─ READ:  servers/chat/app.py:get_room_history()
│
└─ Simulation Manager Tables
   ├─ people
   │  ├─ WRITE: sim_manager/engine.py:create_person()
   │  ├─ READ:  sim_manager/engine.py:list_people()
   │  ├─ READ:  sim_manager/engine.py:_get_active_workers()
   │  └─ DELETE: sim_manager/engine.py:delete_person_by_name()
   │
   ├─ schedule_blocks
   │  ├─ WRITE: sim_manager/engine.py:create_person()
   │  └─ READ:  sim_manager/engine.py:list_people() [JOIN]
   │
   ├─ simulation_state
   │  ├─ WRITE: sim_manager/engine.py:_ensure_state_row()
   │  ├─ WRITE: sim_manager/engine.py:start()
   │  ├─ WRITE: sim_manager/engine.py:advance()
   │  ├─ WRITE: sim_manager/engine.py:stop()
   │  ├─ WRITE: sim_manager/engine.py:reset()
   │  └─ READ:  sim_manager/engine.py:_get_state()
   │
   ├─ tick_log
   │  └─ WRITE: sim_manager/engine.py:advance()
   │
   ├─ events
   │  ├─ WRITE: sim_manager/engine.py:inject_event()
   │  ├─ READ:  sim_manager/engine.py:list_events()
   │  ├─ READ:  sim_manager/engine.py:_process_scheduled_events()
   │  └─ DELETE: sim_manager/engine.py:_process_scheduled_events()
   │
   ├─ project_plans
   │  ├─ WRITE: sim_manager/engine.py:_generate_project_plan()
   │  └─ READ:  sim_manager/engine.py:get_project_plan()
   │
   ├─ project_assignments
   │  ├─ WRITE: sim_manager/engine.py:_generate_project_plan()
   │  └─ READ:  sim_manager/engine.py:get_project_plan()
   │
   ├─ worker_plans
   │  ├─ WRITE: sim_manager/engine.py:_generate_hourly_plan()
   │  └─ READ:  sim_manager/engine.py:list_worker_plans()
   │
   ├─ daily_reports
   │  ├─ WRITE: sim_manager/engine.py:_generate_daily_report()
   │  └─ READ:  sim_manager/engine.py:list_daily_reports()
   │
   ├─ simulation_reports
   │  ├─ WRITE: sim_manager/engine.py:_generate_simulation_report()
   │  └─ READ:  sim_manager/engine.py:list_simulation_reports()
   │
   ├─ worker_runtime_messages
   │  ├─ WRITE: sim_manager/engine.py:_process_worker_inbox()
   │  ├─ READ:  sim_manager/engine.py:_restore_worker_inbox()
   │  └─ DELETE: sim_manager/engine.py:_clear_processed_messages()
   │
   ├─ worker_exchange_log
   │  ├─ WRITE: sim_manager/engine.py:_send_email()
   │  ├─ WRITE: sim_manager/engine.py:_send_chat()
   │  └─ READ:  sim_manager/engine.py:_get_exchange_history()
   │
   └─ worker_status_overrides
      ├─ WRITE: sim_manager/engine.py:_set_worker_status()
      ├─ READ:  sim_manager/engine.py:_load_status_overrides()
      └─ DELETE: sim_manager/engine.py:_process_scheduled_events()
```

---

## 5. Dependency Hierarchy (Top-Down)

**Layered view of module dependencies**

```
Layer 1: User Scripts
├─ quick_simulation.py
├─ mobile_chat_simulation.py
├─ short_blog_simulation.py
└─ [Korean variants: *_ko.py]

Layer 2: Simulation Manager (Orchestrator)
├─ sim_manager/app.py        [FastAPI endpoints]
├─ sim_manager/engine.py     [Core simulation logic]
├─ sim_manager/schemas.py    [Pydantic models]
└─ sim_manager/planner.py    [GPT planning interface]

Layer 3: Gateways (HTTP Clients)
└─ sim_manager/gateways.py
   ├─ HttpEmailGateway  → calls Email Server
   └─ HttpChatGateway   → calls Chat Server

Layer 4: Communication Servers
├─ servers/email/app.py      [Email FastAPI server]
├─ servers/email/models.py   [Email Pydantic models]
├─ servers/chat/app.py       [Chat FastAPI server]
└─ servers/chat/models.py    [Chat Pydantic models]

Layer 5: Domain Logic
└─ virtualWorkers/worker.py  [Persona markdown builder]

Layer 6: Infrastructure
├─ common/db.py              [SQLite connection management]
└─ utils/completion_util.py  [OpenAI API client]

Layer 7: External Services
└─ OpenAI API (https://api.openai.com)
```

---

## 6. Cross-Module Function Call Chains

**Example trace of a typical operation**

### Creating a Persona

```
Script: quick_simulation.py:165
└─ api_call("POST", "/personas/generate", {...})
   │
   └─ HTTP → sim_manager/app.py:202
      └─ _generate_persona_from_prompt(prompt, model_hint)
         │
         ├─ sim_manager/app.py:72
         │  └─ _generate_persona_text(messages, model)
         │     │
         │     └─ sim_manager/app.py:43
         │        └─ utils/completion_util.py:generate_text()
         │           │
         │           └─ HTTPS → OpenAI API
         │
         └─ return persona_dict

Script: quick_simulation.py:192
└─ api_call("POST", "/people", persona)
   │
   └─ HTTP → sim_manager/app.py:198
      └─ engine.create_person(PersonCreate)
         │
         ├─ sim_manager/engine.py:406
         │  └─ build_worker_markdown(WorkerPersona(...))
         │     │
         │     └─ virtualWorkers/worker.py:59
         │
         ├─ sim_manager/engine.py:430
         │  └─ db.get_connection().execute("INSERT INTO people ...")
         │     │
         │     └─ common/db.py:get_connection()
         │
         ├─ sim_manager/engine.py:449
         │  └─ email_gateway.ensure_mailbox(email_address)
         │     │
         │     └─ sim_manager/gateways.py:26
         │        └─ POST → servers/email/app.py:40
         │           │
         │           └─ db.execute("INSERT OR IGNORE INTO mailboxes ...")
         │
         └─ sim_manager/engine.py:454
            └─ chat_gateway.ensure_user(chat_handle)
               │
               └─ sim_manager/gateways.py:71
                  └─ POST → servers/chat/app.py:54
                     │
                     └─ db.execute("INSERT OR IGNORE INTO users ...")
```

### Advancing a Tick

```
Script: quick_simulation.py:235
└─ api_call("POST", "/simulation/advance", {"ticks": 60})
   │
   └─ HTTP → sim_manager/app.py:419
      └─ engine.advance(ticks=60, reason="...")
         │
         ├─ sim_manager/engine.py:1077
         │  └─ _calculate_sim_time(tick)
         │
         ├─ sim_manager/engine.py:1090
         │  └─ _process_scheduled_events(tick)
         │     └─ db.execute("SELECT * FROM events WHERE at_tick=?")
         │
         ├─ sim_manager/engine.py:1095
         │  └─ _process_inbox_for_all_workers(tick, sim_time)
         │     │
         │     └─ email_gateway.get_emails(worker.email_address)
         │        │
         │        └─ sim_manager/gateways.py:32
         │           └─ GET → servers/email/app.py:84
         │              └─ db.execute("SELECT * FROM emails WHERE to_address=?")
         │
         ├─ sim_manager/engine.py:1120
         │  └─ _maybe_plan_for_workers(tick, sim_time)
         │     │
         │     └─ _generate_hourly_plan(worker, tick, sim_time)
         │        │
         │        ├─ _build_planning_context(...)
         │        │  └─ get_project_plan()
         │        │     └─ db.execute("SELECT * FROM project_plans")
         │        │
         │        └─ planner.plan_hourly(persona_markdown, context, model_hint)
         │           │
         │           └─ sim_manager/planner.py:122
         │              └─ _invoke(messages, model)
         │                 │
         │                 └─ sim_manager/planner.py:52
         │                    └─ utils/completion_util.py:generate_text()
         │                       │
         │                       └─ HTTPS → OpenAI API
         │
         ├─ sim_manager/engine.py:1180
         │  └─ _execute_scheduled_actions(tick)
         │     │
         │     ├─ _send_email(worker, action)
         │     │  │
         │     │  └─ email_gateway.send_email(from, to, subject, body)
         │     │     │
         │     │     └─ sim_manager/gateways.py:16
         │     │        └─ POST → servers/email/app.py:50
         │     │           │
         │     │           └─ db.execute("INSERT INTO emails ...")
         │     │
         │     └─ _send_chat(worker, action)
         │        │
         │        └─ chat_gateway.send_message(room_slug, sender, body)
         │           │
         │           └─ sim_manager/gateways.py:92
         │              └─ POST → servers/chat/app.py:92
         │                 │
         │                 └─ db.execute("INSERT INTO messages ...")
         │
         └─ sim_manager/engine.py:1240
            └─ db.execute("UPDATE simulation_state SET current_tick=?")
```

---

## 7. Key Module Interactions

### Simulation Manager ↔ Email Server

```
sim_manager/engine.py
│
├─ _bootstrap_channels()
│  └─ email_gateway.ensure_mailbox(sim_manager_email)
│     └─ POST /mailboxes → servers/email/app.py:create_mailbox()
│
├─ create_person()
│  └─ email_gateway.ensure_mailbox(persona.email_address)
│     └─ POST /mailboxes → servers/email/app.py:create_mailbox()
│
├─ _process_worker_inbox()
│  └─ email_gateway.get_emails(worker.email_address)
│     └─ GET /mailboxes/{addr}/emails → servers/email/app.py:get_emails()
│
└─ _send_email()
   └─ email_gateway.send_email(from, to, subject, body)
      └─ POST /emails/send → servers/email/app.py:send_email()
```

### Simulation Manager ↔ Chat Server

```
sim_manager/engine.py
│
├─ _bootstrap_channels()
│  └─ chat_gateway.ensure_user(sim_manager_handle)
│     └─ POST /users → servers/chat/app.py:create_user()
│
├─ create_person()
│  └─ chat_gateway.ensure_user(persona.chat_handle)
│     └─ POST /users → servers/chat/app.py:create_user()
│
├─ _process_worker_inbox()
│  └─ chat_gateway.get_messages(room_slug)
│     └─ GET /rooms/{slug}/messages → servers/chat/app.py:get_messages()
│
└─ _send_chat()
   ├─ chat_gateway.ensure_room(room_slug)
   │  └─ POST /rooms → servers/chat/app.py:create_room()
   └─ chat_gateway.send_message(room_slug, sender, body)
      └─ POST /messages → servers/chat/app.py:send_message()
```

### Simulation Manager ↔ OpenAI

```
sim_manager/app.py:_generate_persona_from_prompt()
│
└─ _generate_persona_text(messages, model)
   └─ utils/completion_util.py:generate_text()
      └─ POST https://api.openai.com/v1/chat/completions

sim_manager/planner.py:GPTPlanner
│
├─ plan_project()
│  └─ _invoke(messages, model)
│     └─ utils/completion_util.py:generate_text()
│        └─ POST https://api.openai.com/v1/chat/completions
│
├─ plan_daily()
│  └─ _invoke(messages, model)
│     └─ utils/completion_util.py:generate_text()
│        └─ POST https://api.openai.com/v1/chat/completions
│
└─ plan_hourly()
   └─ _invoke(messages, model)
      └─ utils/completion_util.py:generate_text()
         └─ POST https://api.openai.com/v1/chat/completions
```

---

## 8. Circular Dependency Prevention

**Design patterns that prevent import cycles**

```
❌ AVOIDED: Direct imports between services
   Email Server ─X─> Chat Server
   Chat Server  ─X─> Email Server
   Email Server ─X─> Sim Manager
   Chat Server  ─X─> Sim Manager

✅ ACTUAL: Gateway pattern isolates dependencies
   Sim Manager → HttpEmailGateway → HTTP → Email Server
   Sim Manager → HttpChatGateway  → HTTP → Chat Server

❌ AVOIDED: Engine importing app
   sim_manager/engine.py ─X─> sim_manager/app.py

✅ ACTUAL: App imports engine
   sim_manager/app.py ──> sim_manager/engine.py

❌ AVOIDED: Virtual workers importing engine
   virtualWorkers/worker.py ─X─> sim_manager/engine.py

✅ ACTUAL: Engine imports workers (one-way)
   sim_manager/engine.py ──> virtualWorkers/worker.py

❌ AVOIDED: Planner importing engine
   sim_manager/planner.py ─X─> sim_manager/engine.py

✅ ACTUAL: Engine imports planner
   sim_manager/engine.py ──> sim_manager/planner.py
```

---

## 9. Optional Dependencies

**Modules with graceful degradation**

```
utils/completion_util.py
├─ Requires: openai package
└─ Fallback: sim_manager/app.py returns stub personas

sim_manager/planner.py:GPTPlanner
├─ Requires: utils/completion_util (which requires openai)
└─ Fallback: sim_manager/engine.py uses StubPlanner (no GPT calls)

Environment Variables (all optional with defaults):
├─ OPENAI_API_KEY → required for GPT features, else stubs used
├─ VDOS_EMAIL_BASE_URL → defaults to http://127.0.0.1:8000
├─ VDOS_CHAT_BASE_URL → defaults to http://127.0.0.1:8001
├─ VDOS_SIM_BASE_URL → defaults to http://127.0.0.1:8015/api/v1
└─ VDOS_DB_PATH → defaults to src/virtualoffice/vdos.db
```

---

## Summary

This dependency analysis shows:

1. **Clean Layering**: Scripts → Sim Manager → Gateways → Servers → DB
2. **HTTP Boundaries**: Services communicate via REST APIs, not direct imports
3. **No Cycles**: One-way dependencies from top to bottom
4. **Gateway Pattern**: Isolates simulation engine from server implementations
5. **Optional GPT**: System works (with stubs) even without OpenAI API access

For detailed call flows, see `docs/workflows/call-graphs.md`.
For API endpoints, see `docs/reference/api-call-reference.md`.
