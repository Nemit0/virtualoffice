# VDOS API Call Reference

Complete reference of all API endpoints and their callers.

---

## Table of Contents

1. [Simulation Manager API (:8015)](#simulation-manager-api-8015)
2. [Email Server API (:8000)](#email-server-api-8000)
3. [Chat Server API (:8001)](#chat-server-api-8001)
4. [OpenAI API (External)](#openai-api-external)
5. [Quick Reference Matrix](#quick-reference-matrix)

---

## Simulation Manager API (:8015)

Base URL: `http://127.0.0.1:8015/api/v1`

### People Management

#### `POST /api/v1/people`
**Create a new person (persona)**

**Request Body**:
```json
{
  "name": "Alice Johnson",
  "role": "Project Manager",
  "timezone": "America/New_York",
  "work_hours": "09:00-18:00",
  "break_frequency": "50/10 cadence",
  "communication_style": "Direct and organized",
  "email_address": "alice@quickchat.dev",
  "chat_handle": "@alice",
  "is_department_head": true,
  "skills": ["Agile", "Scrum"],
  "personality": ["Organized", "Communicative"],
  "objectives": ["Deliver MVP", "Manage stakeholders"],
  "metrics": ["Velocity", "Satisfaction score"],
  "planning_guidelines": ["Daily standup at 9am"],
  "schedule": [
    {"start": "09:00", "end": "10:00", "activity": "Daily standup"}
  ]
}
```

**Response**: `PersonRead` (201 Created)

**Called By**:
- `quick_simulation.py:192` - `create_mobile_team()`
- `mobile_chat_simulation.py:336` - `create_personas()`
- `short_blog_simulation.py:264` - `create_team()`

**Code Location**: `src/virtualoffice/sim_manager/app.py:198-200`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:396-470` - `create_person()`

---

#### `GET /api/v1/people`
**List all people**

**Response**: `list[PersonRead]`

**Called By**:
- Internal: `engine.py` during startup and planning

**Code Location**: `src/virtualoffice/sim_manager/app.py:194-196`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:472-513` - `list_people()`

---

#### `DELETE /api/v1/people/by-name/{person_name}`
**Delete a person by name**

**Response**: 204 No Content

**Called By**:
- Rarely used (cleanup operations)

**Code Location**: `src/virtualoffice/sim_manager/app.py:210-214`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:515-530` - `delete_person_by_name()`

---

### Persona Generation

#### `POST /api/v1/personas/generate`
**Generate persona using GPT**

**Request Body**:
```json
{
  "prompt": "Experienced agile project manager for mobile app development",
  "model_hint": "gpt-4.1-nano"
}
```

**Response**:
```json
{
  "persona": {
    "name": "Alice Johnson",
    "role": "Project Manager",
    "skills": ["Agile", "Scrum"],
    ...
  }
}
```

**Called By**:
- `quick_simulation.py:165` - `create_mobile_team()`
- `mobile_chat_simulation.py:254` - `create_personas()`
- `short_blog_simulation.py:250` - `create_team()`
- All Korean variants (`*_ko.py`)

**Code Location**: `src/virtualoffice/sim_manager/app.py:202-208`
**Implementation**: `src/virtualoffice/sim_manager/app.py:49-130` - `_generate_persona_from_prompt()`

**External Dependency**: Calls OpenAI API via `utils/completion_util.py`

---

### Simulation Control

#### `POST /api/v1/simulation/start`
**Start a new simulation**

**Request Body**:
```json
{
  "project_name": "QuickChat Mobile App",
  "project_summary": "Develop mobile chat MVP in 4 weeks...",
  "duration_weeks": 4,
  "include_person_ids": [1, 2, 3, 4],
  "random_seed": 42,
  "model_hint": "gpt-4.1-nano"
}
```

**Multi-Project Variant**:
```json
{
  "project_name": "Integrated Platform",
  "project_summary": "Multi-project development",
  "total_duration_weeks": 8,
  "projects": [
    {
      "project_name": "Mobile App MVP",
      "project_summary": "Core mobile features",
      "start_week": 1,
      "duration_weeks": 4,
      "assigned_person_ids": [1, 2, 3, 4]
    },
    {
      "project_name": "Web Dashboard",
      "project_summary": "Admin web interface",
      "start_week": 3,
      "duration_weeks": 4,
      "assigned_person_ids": null
    }
  ],
  "include_person_ids": [1, 2, 3, 4],
  "random_seed": 42,
  "model_hint": "gpt-4.1-nano"
}
```

**Query Parameters**:
- `async_init` (bool, default=false): Run initialization in background

**Response**: `SimulationControlResponse`

**Called By**:
- `quick_simulation.py:219` - `run_simulation()`
- `mobile_chat_simulation.py:362` - `start_project_simulation()`
- `short_blog_simulation.py:286` - `run_sim()`
- All multi-project scripts

**Code Location**: `src/virtualoffice/sim_manager/app.py:299-343`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:874-1027` - `start()`

**External Dependency**: Calls OpenAI API for project planning

---

#### `POST /api/v1/simulation/stop`
**Stop the running simulation**

**Response**: `SimulationControlResponse`

**Called By**:
- Scripts during cleanup
- `_full_reset()` in all scripts

**Code Location**: `src/virtualoffice/sim_manager/app.py:356-365`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:1029-1035` - `stop()`

---

#### `POST /api/v1/simulation/reset`
**Soft reset (clear state, keep people)**

**Response**: `SimulationControlResponse`

**Called By**:
- Rarely used (testing scenarios)

**Code Location**: `src/virtualoffice/sim_manager/app.py:367-376`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:646-668` - `reset()`

---

#### `POST /api/v1/simulation/full-reset`
**Full reset (clear state AND delete people)**

**Response**: `SimulationControlResponse`

**Called By**:
- `_full_reset()` in scripts as fallback to hard-reset

**Code Location**: `src/virtualoffice/sim_manager/app.py:378-387`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:670-695` - `reset_full()`

---

#### `POST /api/v1/admin/hard-reset`
**Administrative hard reset (delete DB, recreate schemas)**

**Response**: `SimulationControlResponse`

**Called By**:
- `_full_reset()` in all scripts (preferred method)

**Code Location**: `src/virtualoffice/sim_manager/app.py:436-488`
**Implementation**:
1. Stop auto-ticks
2. Delete `vdos.db` file
3. Recreate email, chat, and sim schemas
4. Re-initialize engine state
5. Bootstrap channels

---

#### `GET /api/v1/simulation`
**Get current simulation state**

**Response**:
```json
{
  "current_tick": 1234,
  "is_running": true,
  "auto_tick": false,
  "sim_time": "Day 2, Wednesday 13:34",
  "project_name": "QuickChat Mobile App",
  "duration_weeks": 4
}
```

**Called By**:
- `quick_simulation.py:241` - During tick loop
- `mobile_chat_simulation.py:393` - Polling during auto-tick
- `short_blog_simulation.py:307` - State monitoring
- Scripts for final state collection

**Code Location**: `src/virtualoffice/sim_manager/app.py:252-254`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:532-570` - `get_state()`

---

#### `GET /api/v1/simulation/init-status`
**Check async initialization status**

**Response**:
```json
{
  "running": true,
  "retries": 2,
  "max_retries": 3,
  "error": null
}
```

**Called By**:
- Scripts using `async_init=true` parameter

**Code Location**: `src/virtualoffice/sim_manager/app.py:345-354`

---

### Tick Control

#### `POST /api/v1/simulation/advance`
**Advance simulation by N ticks**

**Request Body**:
```json
{
  "ticks": 60,
  "reason": "Week 1 development cycle"
}
```

**Response**: `SimulationAdvanceResult`
```json
{
  "tick": 540,
  "sim_time": "Day 1, Tuesday 09:00",
  "actions_executed": 12,
  "plans_generated": 4,
  "message": "Advanced 60 ticks"
}
```

**Called By**:
- `quick_simulation.py:235` - Manual advancement loop
- `mobile_chat_simulation.py:379` - Kickoff tick
- Auto-tick background thread (internal)

**Code Location**: `src/virtualoffice/sim_manager/app.py:419-429`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:1054-1280` - `advance()`

**External Dependency**: May call OpenAI API for hourly/daily planning

**Performance**: Linear with `ticks` parameter; GPT calls are bottleneck

---

#### `POST /api/v1/simulation/ticks/start`
**Enable automatic ticking**

**Response**: `SimulationControlResponse`

**Called By**:
- `mobile_chat_simulation.py:382` - Auto-tick mode
- `short_blog_simulation.py:296` - Auto-tick mode

**Code Location**: `src/virtualoffice/sim_manager/app.py:394-406`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:1037-1052` - `start_auto_ticks()`

**Side Effect**: Spawns background thread running `_auto_tick_loop()`

---

#### `POST /api/v1/simulation/ticks/stop`
**Disable automatic ticking**

**Response**: `SimulationControlResponse`

**Called By**:
- Scripts before shutdown
- `mobile_chat_simulation.py:403` - After completion

**Code Location**: `src/virtualoffice/sim_manager/app.py:408-417`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:697-726` - `stop_auto_ticks()`

---

### Project & Planning

#### `GET /api/v1/simulation/project-plan`
**Get the current project plan**

**Response**: `ProjectPlanRead`
```json
{
  "id": 1,
  "project_name": "QuickChat Mobile App",
  "project_summary": "...",
  "plan": {
    "phases": [...],
    "milestones": [...],
    "risks": [...]
  },
  "duration_weeks": 4,
  "model_used": "gpt-4.1-nano",
  "tokens_used": 1234
}
```

**Called By**:
- `mobile_chat_simulation.py:457` - Final report generation
- Internal planning context building

**Code Location**: `src/virtualoffice/sim_manager/app.py:216-219`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:728-763` - `get_project_plan()`

---

#### `GET /api/v1/people/{person_id}/plans`
**Get worker plans (hourly/daily)**

**Query Parameters**:
- `plan_type` (optional): "hourly" | "daily"
- `limit` (default=20, max=200)

**Response**: `list[WorkerPlanRead]`

**Called By**:
- `mobile_chat_simulation.py:481` - Collect hourly plans
- `quick_simulation.py:297` - Final report generation

**Code Location**: `src/virtualoffice/sim_manager/app.py:221-228`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:765-812` - `list_worker_plans()`

---

#### `GET /api/v1/people/{person_id}/daily-reports`
**Get daily reports for a person**

**Query Parameters**:
- `day_index` (optional): Specific day
- `limit` (default=20, max=200)

**Response**: `list[DailyReportRead]`

**Called By**:
- `mobile_chat_simulation.py:477` - Collect daily reports
- `quick_simulation.py:295` - Final report generation

**Code Location**: `src/virtualoffice/sim_manager/app.py:230-237`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:814-856` - `list_daily_reports()`

---

#### `GET /api/v1/simulation/reports`
**Get simulation-level reports**

**Query Parameters**:
- `limit` (default=10, max=200)

**Response**: `list[SimulationReportRead]`

**Called By**:
- `mobile_chat_simulation.py:460` - Final report collection

**Code Location**: `src/virtualoffice/sim_manager/app.py:239-244`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:858-872` - `list_simulation_reports()`

---

### Events

#### `POST /api/v1/events`
**Inject a simulation event**

**Request Body**:
```json
{
  "type": "sick_day",
  "target_ids": [1],
  "project_id": null,
  "at_tick": 1500,
  "payload": {"reason": "flu"}
}
```

**Response**: `EventRead` (201 Created)

**Called By**:
- Manual event injection (testing, demos)
- Planner can suggest events

**Code Location**: `src/virtualoffice/sim_manager/app.py:490-492`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:572-608` - `inject_event()`

---

#### `GET /api/v1/events`
**List all events**

**Response**: `list[EventRead]`

**Called By**:
- `quick_simulation.py:289` - Final report generation
- `mobile_chat_simulation.py:466` - Event collection

**Code Location**: `src/virtualoffice/sim_manager/app.py:494-496`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:610-644` - `list_events()`

---

### Metrics & Monitoring

#### `GET /api/v1/simulation/token-usage`
**Get aggregated token usage**

**Response**:
```json
{
  "per_model": {
    "gpt-4.1-nano": 45678,
    "gpt-4o": 12345
  },
  "total_tokens": 58023
}
```

**Called By**:
- `quick_simulation.py:290` - Final report
- `mobile_chat_simulation.py:469` - Token tracking

**Code Location**: `src/virtualoffice/sim_manager/app.py:246-250`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:1645-1694` - `get_token_usage()`

---

#### `GET /api/v1/metrics/planner`
**Get planner performance metrics**

**Query Parameters**:
- `limit` (default=50, max=500)

**Response**: `list[dict]`
```json
[
  {
    "tick": 1234,
    "worker_id": 1,
    "plan_type": "hourly",
    "duration_ms": 2345,
    "tokens": 234,
    "model": "gpt-4.1-nano"
  }
]
```

**Called By**:
- `mobile_chat_simulation.py:439` - Performance analysis

**Code Location**: `src/virtualoffice/sim_manager/app.py:256-261`
**Implementation**: `src/virtualoffice/sim_manager/engine.py:1717-1724` - `get_planner_metrics()`

---

## Email Server API (:8000)

Base URL: `http://127.0.0.1:8000`

### Mailbox Management

#### `POST /mailboxes`
**Create a mailbox**

**Request Body**:
```json
{
  "address": "alice@quickchat.dev"
}
```

**Response**: `Mailbox` (201 Created)

**Called By**:
- `sim_manager/gateways.py:26` - `HttpEmailGateway.ensure_mailbox()`
  - From `engine.py:449` during `create_person()`
  - From `engine.py:1791` during `_bootstrap_channels()`

**Code Location**: `src/virtualoffice/servers/email/app.py:40-48`

---

#### `GET /mailboxes/{address}/emails`
**Get all emails for a mailbox**

**Response**: `list[EmailRead]`

**Called By**:
- `sim_manager/gateways.py:32` - `HttpEmailGateway.get_emails()`
  - From `engine.py:1537-1610` during `_process_worker_inbox()`
- `quick_simulation.py:257` - Direct collection
- `mobile_chat_simulation.py:582` - Direct collection

**Code Location**: `src/virtualoffice/servers/email/app.py:84-95`

---

### Email Operations

#### `POST /emails/send`
**Send an email**

**Request Body**:
```json
{
  "from_address": "alice@quickchat.dev",
  "to_address": "bob@quickchat.dev",
  "subject": "Sprint Planning Update",
  "body": "Let's discuss feature priorities...",
  "sent_at": "2025-01-17T14:30:00Z"
}
```

**Response**: `EmailRead` (201 Created)

**Called By**:
- `sim_manager/gateways.py:16` - `HttpEmailGateway.send_email()`
  - From `engine.py:1473-1537` during `_execute_scheduled_actions()`

**Code Location**: `src/virtualoffice/servers/email/app.py:50-82`

---

#### `GET /mailboxes/{address}/drafts`
**Get drafts for a mailbox**

**Response**: `list[DraftRead]`

**Called By**:
- Rarely used (future feature)

**Code Location**: `src/virtualoffice/servers/email/app.py:97-108`

---

#### `POST /mailboxes/{address}/drafts`
**Create a draft email**

**Request Body**:
```json
{
  "to_address": "bob@quickchat.dev",
  "subject": "Draft subject",
  "body": "Draft content..."
}
```

**Response**: `DraftRead` (201 Created)

**Called By**:
- Rarely used (future feature)

**Code Location**: `src/virtualoffice/servers/email/app.py:110-133`

---

## Chat Server API (:8001)

Base URL: `http://127.0.0.1:8001`

### User Management

#### `POST /users`
**Create a user**

**Request Body**:
```json
{
  "handle": "@alice",
  "username": "Alice Johnson"
}
```

**Response**: `User` (201 Created)

**Called By**:
- `sim_manager/gateways.py:71` - `HttpChatGateway.ensure_user()`
  - From `engine.py:454` during `create_person()`
  - From `engine.py:1796` during `_bootstrap_channels()`

**Code Location**: `src/virtualoffice/servers/chat/app.py:54-68`

---

#### `GET /users/{handle}`
**Get user by handle**

**Response**: `User`

**Called By**:
- Internal gateway checks

**Code Location**: `src/virtualoffice/servers/chat/app.py:70-80`

---

### Room Management

#### `POST /rooms`
**Create a room**

**Request Body**:
```json
{
  "slug": "dm:@alice:@bob",
  "name": "Alice & Bob",
  "room_type": "dm",
  "members": ["@alice", "@bob"]
}
```

**Response**: `RoomRead` (201 Created)

**Called By**:
- `sim_manager/gateways.py:82` - `HttpChatGateway.ensure_room()`
  - From `engine.py:1581` during `_send_chat()`

**Code Location**: `src/virtualoffice/servers/chat/app.py:82-118`

---

#### `GET /rooms/{slug}`
**Get room by slug**

**Response**: `RoomRead`

**Called By**:
- Internal gateway checks

**Code Location**: `src/virtualoffice/servers/chat/app.py:120-130`

---

### Messaging

#### `POST /messages`
**Send a message**

**Request Body**:
```json
{
  "room_slug": "dm:@alice:@bob",
  "sender": "@alice",
  "body": "Ready for standup?",
  "timestamp": "2025-01-17T14:45:00Z"
}
```

**Response**: `MessageRead` (201 Created)

**Called By**:
- `sim_manager/gateways.py:92` - `HttpChatGateway.send_message()`
  - From `engine.py:1538-1610` during `_execute_scheduled_actions()`

**Code Location**: `src/virtualoffice/servers/chat/app.py:92-151`

---

#### `GET /rooms/{slug}/messages`
**Get messages in a room**

**Response**: `list[MessageRead]`

**Called By**:
- `sim_manager/gateways.py:100` - `HttpChatGateway.get_messages()`
  - From `engine.py:1473-1537` during `_process_worker_inbox()`
- `quick_simulation.py:276` - Direct collection
- `mobile_chat_simulation.py:593` - Direct collection

**Code Location**: `src/virtualoffice/servers/chat/app.py:153-180`

---

## OpenAI API (External)

Base URL: `https://api.openai.com`

### Chat Completions

#### `POST /v1/chat/completions`
**Generate chat completion**

**Request Body**:
```json
{
  "model": "gpt-4.1-nano",
  "messages": [
    {"role": "system", "content": "You are a project planner..."},
    {"role": "user", "content": "Create a 4-week plan for..."}
  ],
  "temperature": 0.7
}
```

**Response**:
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "{\"phases\": [...], \"milestones\": [...]}"
      }
    }
  ],
  "usage": {
    "prompt_tokens": 234,
    "completion_tokens": 123,
    "total_tokens": 357
  }
}
```

**Called By**:
- `utils/completion_util.py:25` - `generate_text()`
  - From `sim_manager/app.py:72` - Persona generation
  - From `sim_manager/planner.py:52` - Project planning
  - From `sim_manager/planner.py:122` - Hourly planning
  - From `sim_manager/planner.py:177` - Daily planning

**Code Location**: `src/virtualoffice/utils/completion_util.py`

**Authentication**: Requires `OPENAI_API_KEY` environment variable

---

## Quick Reference Matrix

### By Caller

| Caller | API Endpoint | Purpose |
|--------|--------------|---------|
| **Simulation Scripts** |
| `quick_simulation.py` | POST /admin/hard-reset | Full reset |
| | POST /personas/generate | Generate personas |
| | POST /people | Create personas |
| | POST /simulation/start | Start simulation |
| | POST /simulation/advance | Manual tick advancement |
| | GET /simulation | State monitoring |
| | GET /events | Event collection |
| | GET /simulation/token-usage | Token tracking |
| | GET /people/{id}/daily-reports | Report collection |
| | GET /people/{id}/plans | Plan collection |
| | GET /mailboxes/{addr}/emails | Direct email collection |
| | GET /rooms/{slug}/messages | Direct chat collection |
| **Simulation Engine** |
| `engine.py:create_person()` | POST /mailboxes | Provision mailbox |
| | POST /users | Provision chat user |
| `engine.py:_process_worker_inbox()` | GET /mailboxes/{addr}/emails | Fetch inbox |
| | GET /rooms/{slug}/messages | Fetch DMs |
| `engine.py:_execute_scheduled_actions()` | POST /emails/send | Send email |
| | POST /rooms | Ensure room exists |
| | POST /messages | Send chat message |
| **Planner** |
| `planner.py:plan_project()` | POST /v1/chat/completions (OpenAI) | Project planning |
| `planner.py:plan_hourly()` | POST /v1/chat/completions (OpenAI) | Hourly planning |
| `planner.py:plan_daily()` | POST /v1/chat/completions (OpenAI) | Daily planning |
| **App** |
| `app.py:generate_persona()` | POST /v1/chat/completions (OpenAI) | Persona generation |

### By API Endpoint

| Endpoint | Method | Caller | Code Location |
|----------|--------|--------|---------------|
| **Simulation Manager** |
| `/people` | POST | Scripts | `app.py:198`, `engine.py:396` |
| `/people` | GET | Internal | `app.py:194`, `engine.py:472` |
| `/personas/generate` | POST | Scripts | `app.py:202`, `app.py:49` |
| `/simulation/start` | POST | Scripts | `app.py:299`, `engine.py:874` |
| `/simulation` | GET | Scripts | `app.py:252`, `engine.py:532` |
| `/simulation/advance` | POST | Scripts, Auto-tick | `app.py:419`, `engine.py:1054` |
| `/simulation/ticks/start` | POST | Scripts | `app.py:394`, `engine.py:1037` |
| `/simulation/ticks/stop` | POST | Scripts | `app.py:408`, `engine.py:697` |
| `/simulation/token-usage` | GET | Scripts | `app.py:246`, `engine.py:1645` |
| `/people/{id}/plans` | GET | Scripts | `app.py:221`, `engine.py:765` |
| `/people/{id}/daily-reports` | GET | Scripts | `app.py:230`, `engine.py:814` |
| `/events` | GET | Scripts | `app.py:494`, `engine.py:610` |
| `/admin/hard-reset` | POST | Scripts | `app.py:436` |
| **Email Server** |
| `/mailboxes` | POST | Engine (gateways) | `email/app.py:40` |
| `/emails/send` | POST | Engine (gateways) | `email/app.py:50` |
| `/mailboxes/{addr}/emails` | GET | Engine (gateways), Scripts | `email/app.py:84` |
| **Chat Server** |
| `/users` | POST | Engine (gateways) | `chat/app.py:54` |
| `/rooms` | POST | Engine (gateways) | `chat/app.py:82` |
| `/messages` | POST | Engine (gateways) | `chat/app.py:92` |
| `/rooms/{slug}/messages` | GET | Engine (gateways), Scripts | `chat/app.py:153` |
| **OpenAI** |
| `/v1/chat/completions` | POST | Planner, App | `completion_util.py:25` |

### By HTTP Method

**POST (Creation/Mutation)**:
- Simulation: start, stop, reset, advance, ticks/start, ticks/stop
- People: create person, generate persona
- Email: create mailbox, send email, create draft
- Chat: create user, create room, send message
- Events: inject event
- Admin: hard-reset
- OpenAI: chat completions

**GET (Read-only)**:
- Simulation: state, reports, token usage, init status, planner metrics
- People: list, plans, daily reports
- Email: mailbox emails, drafts
- Chat: room messages, user info, room info
- Events: list
- Project: project plan

**DELETE (Rare)**:
- People: delete by name
- Email: delete email, delete draft
- (Most cleanup done via reset operations)

---

## Performance Considerations

### High-Frequency Endpoints
1. `POST /simulation/advance` - Called every tick or in large chunks
2. `GET /mailboxes/{addr}/emails` - Called per worker per tick during inbox processing
3. `GET /rooms/{slug}/messages` - Called per DM pair per tick
4. `POST /v1/chat/completions` - Called for every planning operation

### Low-Frequency Endpoints
1. `POST /people` - Called once per persona
2. `POST /simulation/start` - Called once per simulation
3. `GET /simulation/token-usage` - Called at end of simulation
4. `POST /admin/hard-reset` - Called once at startup

### Optimization Tips
- **Batch advancement**: Use large `ticks` values (60-480) for faster execution
- **Cache project plans**: Engine caches to avoid repeated DB queries
- **Inbox throttling**: Cooldown prevents spammy communications
- **Token aggregation**: Calculated on-demand from database

---

## Summary

This reference documents:

1. **47 Total Endpoints**: 27 Sim Manager, 10 Email, 9 Chat, 1 OpenAI
2. **3 Core Services**: All communicate via HTTP REST APIs
3. **Gateway Pattern**: Engine uses gateways to abstract HTTP calls
4. **GPT Integration**: 4 endpoints call OpenAI for planning
5. **Token Tracking**: All GPT calls record usage in database

For flow details, see `docs/workflows/call-graphs.md`.
For module dependencies, see `docs/workflows/module-dependencies.md`.
