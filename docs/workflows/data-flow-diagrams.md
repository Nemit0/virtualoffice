# VDOS Data Flow Diagrams

Visual diagrams showing how data transforms as it moves through the system.

---

## 1. Persona Creation Data Flow

**JSON → Database → Markdown → Runtime Cache**

```
Input: GPT Prompt
│  "Experienced agile project manager for mobile app development..."
│
v
┌──────────────────────────────────────────────────────┐
│ OpenAI API Call                                      │
│ POST https://api.openai.com/v1/chat/completions      │
└──────────────────────────────────────────────────────┘
│
│ Returns JSON:
│ {
│   "name": "Alice Johnson",
│   "role": "Project Manager",
│   "skills": ["Agile", "Scrum", "Stakeholder Management"],
│   "personality": ["Organized", "Communicative", "Strategic"],
│   "timezone": "America/New_York",
│   "work_hours": "09:00-18:00",
│   "break_frequency": "50/10 cadence",
│   "communication_style": "Direct and organized",
│   "schedule": [
│     {"start": "09:00", "end": "10:00", "activity": "Daily standup"},
│     {"start": "10:00", "end": "12:00", "activity": "Sprint planning"}
│   ]
│ }
│
v
┌──────────────────────────────────────────────────────┐
│ Script Enhancement (quick_simulation.py:176-189)     │
│ persona.update({                                     │
│   "is_department_head": True,                        │
│   "email_address": "alice.johnson@quickchat.dev",    │
│   "chat_handle": "@alice_johnson"                    │
│ })                                                   │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ POST /api/v1/people                                  │
│ sim_manager/engine.py:create_person()                │
└──────────────────────────────────────────────────────┘
│
├─ Transform to WorkerPersona
│  │  virtualWorkers/worker.py:WorkerPersona
│  │  dataclass(name, role, skills, personality, ...)
│  │
│  v
│  ┌────────────────────────────────────────────────┐
│  │ build_worker_markdown(WorkerPersona)           │
│  │                                                │
│  │ Generates:                                     │
│  │ # Alice Johnson - Project Manager              │
│  │                                                │
│  │ ## Core Skills                                 │
│  │ - Agile                                        │
│  │ - Scrum                                        │
│  │ - Stakeholder Management                       │
│  │                                                │
│  │ ## Personality                                 │
│  │ - Organized                                    │
│  │ - Communicative                                │
│  │ - Strategic                                    │
│  │                                                │
│  │ ## Schedule                                    │
│  │ - 09:00-10:00: Daily standup                   │
│  │ - 10:00-12:00: Sprint planning                 │
│  │ ...                                            │
│  └────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Database Storage (SQLite)                            │
│                                                      │
│ INSERT INTO people (                                 │
│   name, role, timezone, work_hours,                  │
│   skills, personality, objectives, metrics,          │
│   persona_markdown, ...                              │
│ ) VALUES (                                           │
│   'Alice Johnson',                                   │
│   'Project Manager',                                 │
│   'America/New_York',                                │
│   '09:00-18:00',                                     │
│   '["Agile","Scrum","Stakeholder Management"]',      │
│   '["Organized","Communicative","Strategic"]',       │
│   '...',                                             │
│   '# Alice Johnson - Project Manager\n\n...'         │
│ )                                                    │
│                                                      │
│ INSERT INTO schedule_blocks (person_id, ...) x N     │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Runtime Cache Update                                 │
│ sim_manager/engine.py:_sync_worker_runtimes()        │
│                                                      │
│ _worker_runtime[person_id] = _WorkerRuntime(         │
│   person=PersonRead(...),                            │
│   inbox=[]                                           │
│ )                                                    │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Channel Provisioning                                 │
│                                                      │
│ POST /mailboxes                                      │
│   → INSERT INTO mailboxes (address)                  │
│   VALUES ('alice.johnson@quickchat.dev')             │
│                                                      │
│ POST /users                                          │
│   → INSERT INTO users (handle, username)             │
│   VALUES ('@alice_johnson', 'Alice Johnson')         │
└──────────────────────────────────────────────────────┘
│
v
Output: PersonRead
{
  "id": 1,
  "name": "Alice Johnson",
  "role": "Project Manager",
  "email_address": "alice.johnson@quickchat.dev",
  "chat_handle": "@alice_johnson",
  "is_department_head": true,
  "persona_markdown": "# Alice Johnson...",
  ...
}
```

---

## 2. Project Planning Data Flow

**Team Context → GPT → Structured Plan → Database**

```
Input: SimulationStartRequest
{
  "project_name": "QuickChat Mobile App",
  "project_summary": "Develop mobile chat MVP in 4 weeks...",
  "duration_weeks": 4,
  "include_person_ids": [1, 2, 3, 4]
}
│
v
┌──────────────────────────────────────────────────────┐
│ Build Team Context                                   │
│ sim_manager/engine.py:_generate_project_plan()       │
│                                                      │
│ team_personas = [list_people() for id in ids]       │
│ dept_head = [p for p if p.is_department_head][0]    │
│                                                      │
│ context = """                                        │
│   Team Members:                                      │
│   - Alice Johnson (PM): Agile, Scrum expert          │
│   - Bob Smith (Designer): UI/UX, mobile interfaces   │
│   - Carol Lee (Developer): React Native, Node.js     │
│   - Dave Chen (DevOps): CI/CD, cloud infrastructure  │
│ """                                                  │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ GPT Call: Project Planning                           │
│ sim_manager/planner.py:plan_project()                │
│                                                      │
│ Prompt:                                              │
│ "Create a 4-week project plan for:                   │
│  QuickChat Mobile App - Develop mobile chat MVP...   │
│                                                      │
│  Team: [team context above]                          │
│                                                      │
│  Return JSON with phases, milestones, risks"         │
└──────────────────────────────────────────────────────┘
│
│ OpenAI API Response:
│
v
{
  "phases": [
    {
      "week": 1,
      "focus": "Requirements & Design",
      "deliverables": [
        "User stories and acceptance criteria",
        "UI/UX mockups and design system",
        "Technical architecture document"
      ],
      "team_activities": {
        "PM": "Gather requirements, create user stories",
        "Designer": "Create mockups and design system",
        "Developer": "Review architecture, set up dev environment",
        "DevOps": "Set up CI/CD pipeline and staging environment"
      }
    },
    {
      "week": 2,
      "focus": "Core Development",
      "deliverables": [
        "Authentication system",
        "Real-time messaging backend",
        "Basic UI components"
      ],
      "team_activities": {...}
    },
    ...
  ],
  "milestones": [
    {"week": 1, "name": "Design Review Complete"},
    {"week": 2, "name": "Backend MVP Ready"},
    ...
  ],
  "risks": [
    "Real-time messaging complexity",
    "Cross-platform compatibility issues"
  ]
}
│
v
┌──────────────────────────────────────────────────────┐
│ Database Storage                                     │
│                                                      │
│ INSERT INTO project_plans (                          │
│   project_name,                                      │
│   project_summary,                                   │
│   plan,           -- JSON.stringify(phases)          │
│   generated_by,   -- dept_head.id                    │
│   duration_weeks,                                    │
│   model_used,     -- "gpt-4.1-nano"                  │
│   tokens_used     -- 1234                            │
│ )                                                    │
│                                                      │
│ INSERT INTO project_assignments (project_id, person_id)
│   VALUES (1, 1), (1, 2), (1, 3), (1, 4)             │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Cache for Fast Access                                │
│ _project_plan_cache = {                              │
│   "project_name": "QuickChat Mobile App",            │
│   "phases": [...],                                   │
│   "milestones": [...],                               │
│   "risks": [...]                                     │
│ }                                                    │
└──────────────────────────────────────────────────────┘
│
v
Output: ProjectPlanRead
{
  "id": 1,
  "project_name": "QuickChat Mobile App",
  "plan": {...},
  "duration_weeks": 4,
  "model_used": "gpt-4.1-nano"
}
```

---

## 3. Hourly Planning Data Flow

**Context Gathering → GPT → Action Schedule → Execution**

```
Tick: 480 (Day 0, 08:00)
Worker: Alice Johnson (PM)
│
v
┌──────────────────────────────────────────────────────┐
│ Check if Planning Needed                             │
│ sim_manager/engine.py:_needs_hourly_plan()           │
│                                                      │
│ - Is it start of hour? (minute == 0)     ✓          │
│ - Within work hours? (9 <= hour < 17)    ✓          │
│ - Not already planned?                   ✓          │
│ → Yes, plan needed                                   │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Build Planning Context                               │
│ sim_manager/engine.py:_build_planning_context()      │
└──────────────────────────────────────────────────────┘
│
├─ Get Project Plan
│  │  SELECT plan FROM project_plans WHERE id=1
│  │
│  v
│  current_phase = {
│    "week": 1,
│    "focus": "Requirements & Design",
│    "deliverables": [...],
│    "team_activities": {
│      "PM": "Gather requirements, create user stories"
│    }
│  }
│
├─ Drain Inbox
│  │  worker_runtime[1].drain()
│  │
│  v
│  inbox_messages = [
│    {
│      "from": "simulator@vdos.local",
│      "subject": "Project Kickoff",
│      "summary": "4-week mobile app project starting",
│      "action_item": "Begin requirements gathering"
│    }
│  ]
│
├─ Get Worker Status
│  │  SELECT status FROM worker_status_overrides WHERE worker_id=1
│  │
│  v
│  status = "available"  # or "sick", "meeting", etc.
│
└─ Calculate Sim Time
   │
   v
   sim_time = {
     "day_index": 0,
     "hour": 8,
     "minute": 0,
     "formatted": "Day 0, Monday 08:00"
   }

Context (combined):
{
  "project": {
    "name": "QuickChat Mobile App",
    "current_phase": "Requirements & Design",
    "my_responsibilities": "Gather requirements, create user stories"
  },
  "inbox": [
    {"from": "simulator", "summary": "Project kickoff", "action": "Begin gathering"}
  ],
  "status": "available",
  "current_time": "Day 0, 08:00"
}
│
v
┌──────────────────────────────────────────────────────┐
│ GPT Call: Hourly Planning                            │
│ sim_manager/planner.py:plan_hourly()                 │
│                                                      │
│ System: "You are Alice Johnson, Project Manager..."  │
│                                                      │
│ User Prompt:                                         │
│ """                                                  │
│ # Persona                                            │
│ # Alice Johnson - Project Manager                    │
│ Skills: Agile, Scrum, Stakeholder Management         │
│ ...                                                  │
│                                                      │
│ # Context                                            │
│ Project Phase: Requirements & Design                 │
│ Your Role: Gather requirements, create user stories  │
│                                                      │
│ Inbox (1 message):                                   │
│ - Simulator: Project kickoff notification            │
│                                                      │
│ Current Time: Day 0, 08:00                           │
│ Status: Available                                    │
│                                                      │
│ # Task                                               │
│ Plan your next hour (08:00-09:00).                   │
│ Return JSON:                                         │
│ {                                                    │
│   "reasoning": "...",                                │
│   "actions": [                                       │
│     {                                                │
│       "type": "send_email",                          │
│       "to": "...",                                   │
│       "subject": "...",                              │
│       "body": "..."                                  │
│     }                                                │
│   ]                                                  │
│ }                                                    │
│ """                                                  │
└──────────────────────────────────────────────────────┘
│
│ OpenAI API Response:
│
v
{
  "reasoning": "Starting new project. Need to coordinate with team on requirements gathering and schedule initial meetings.",
  "actions": [
    {
      "type": "send_email",
      "to": "bob.smith@quickchat.dev",
      "subject": "QuickChat Requirements - Design Input Needed",
      "body": "Hi Bob,\n\nAs we kick off the QuickChat mobile app, I'd like to gather your input on design requirements..."
    },
    {
      "type": "send_email",
      "to": "carol.lee@quickchat.dev",
      "subject": "Technical Architecture Discussion",
      "body": "Hi Carol,\n\nLet's schedule time this week to discuss the technical architecture..."
    },
    {
      "type": "send_chat",
      "to": "@dave_chen",
      "message": "Hey Dave, can we sync on the CI/CD setup later today?"
    }
  ]
}
│
v
┌──────────────────────────────────────────────────────┐
│ Database Storage                                     │
│                                                      │
│ INSERT INTO worker_plans (                           │
│   person_id,      -- 1                               │
│   tick,           -- 480                             │
│   plan_type,      -- "hourly"                        │
│   content,        -- JSON of reasoning + actions     │
│   model_used,     -- "gpt-4.1-nano"                  │
│   tokens_used,    -- 567                             │
│   context         -- JSON of planning context        │
│ )                                                    │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Schedule Actions for Execution                       │
│ sim_manager/engine.py:_schedule_actions()            │
│                                                      │
│ For each action:                                     │
│   target_tick = 480 + random(5, 55)                  │
│   _scheduled_comms[worker_id][target_tick] = action  │
│                                                      │
│ Example:                                             │
│   _scheduled_comms[1][492] = email to Bob            │
│   _scheduled_comms[1][513] = email to Carol          │
│   _scheduled_comms[1][528] = chat to Dave            │
└──────────────────────────────────────────────────────┘
│
v
[Later, at tick 492]
┌──────────────────────────────────────────────────────┐
│ Execute Scheduled Action                             │
│ sim_manager/engine.py:_execute_scheduled_actions()   │
│                                                      │
│ action = _scheduled_comms[1][492]                    │
│ → send_email(                                        │
│     from="alice.johnson@quickchat.dev",              │
│     to="bob.smith@quickchat.dev",                    │
│     subject="QuickChat Requirements...",             │
│     body="Hi Bob,\n\n..."                            │
│   )                                                  │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Email Delivery                                       │
│ POST http://127.0.0.1:8000/emails/send               │
│                                                      │
│ servers/email/app.py:send_email()                    │
│   INSERT INTO emails (                               │
│     from_address, to_address, subject, body,         │
│     sent_at, received_at                             │
│   )                                                  │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Exchange Logging                                     │
│ INSERT INTO worker_exchange_log (                    │
│   tick,           -- 492                             │
│   sender_id,      -- 1 (Alice)                       │
│   recipient_id,   -- 2 (Bob)                         │
│   channel,        -- "email"                         │
│   subject,        -- "QuickChat Requirements..."     │
│   summary         -- "Requirements gathering"        │
│ )                                                    │
└──────────────────────────────────────────────────────┘
│
v
Output: Email delivered, logged, waiting in Bob's inbox
```

---

## 4. Email Processing Data Flow

**Inbox Fetch → Summarization → Queue → Planning Input**

```
Tick: 550 (Day 0, 09:10)
Worker: Bob Smith (Designer)
│
v
┌──────────────────────────────────────────────────────┐
│ Fetch Inbox                                          │
│ sim_manager/engine.py:_process_worker_inbox()        │
│                                                      │
│ GET http://127.0.0.1:8000/mailboxes/                 │
│     bob.smith@quickchat.dev/emails                   │
└──────────────────────────────────────────────────────┘
│
│ Email Server Response:
│
v
[
  {
    "id": 123,
    "from_address": "alice.johnson@quickchat.dev",
    "to_address": "bob.smith@quickchat.dev",
    "subject": "QuickChat Requirements - Design Input Needed",
    "body": "Hi Bob,\n\nAs we kick off the QuickChat mobile app, I'd like to gather your input on design requirements...",
    "sent_at": "2025-01-17T08:12:00Z",
    "received_at": "2025-01-17T08:12:00Z"
  }
]
│
v
┌──────────────────────────────────────────────────────┐
│ For Each New Email                                   │
│ (not yet processed - track by message_id)            │
└──────────────────────────────────────────────────────┘
│
├─ Extract Metadata
│  │
│  v
│  sender = "Alice Johnson"
│  sender_id = 1
│  subject = "QuickChat Requirements - Design Input Needed"
│
├─ Summarize with GPT (optional, based on config)
│  │
│  │ Prompt: "Summarize this email and extract action items:
│  │          [email body]"
│  │
│  v
│  summary = "PM requesting design input for requirements"
│  action_item = "Provide design requirements and mockup ideas"
│
└─ Create Inbound Message
   │
   v
   _InboundMessage(
     sender_id=1,
     sender_name="Alice Johnson",
     subject="QuickChat Requirements - Design Input Needed",
     summary="PM requesting design input",
     action_item="Provide requirements and mockups",
     message_type="request",
     channel="email",
     tick=550,
     message_id=123
   )

│
v
┌──────────────────────────────────────────────────────┐
│ Queue to Worker Runtime                              │
│ _worker_runtime[2].queue(inbound_message)            │
│                                                      │
│ _worker_runtime[2].inbox = [                         │
│   {sender: "Alice", subject: "...", action: "..."}   │
│ ]                                                    │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Persist to Database (for recovery)                   │
│ INSERT INTO worker_runtime_messages (                │
│   recipient_id,   -- 2 (Bob)                         │
│   payload         -- JSON of inbound_message         │
│ )                                                    │
└──────────────────────────────────────────────────────┘
│
v
[Later, at tick 600 (10:00) - next hour]
┌──────────────────────────────────────────────────────┐
│ Hourly Planning for Bob                              │
│ _build_planning_context() → drains inbox             │
│                                                      │
│ inbox = _worker_runtime[2].drain()                   │
│   → [inbound_message from Alice]                     │
│                                                      │
│ Context passed to GPT includes:                      │
│ {                                                    │
│   "inbox": [                                         │
│     {                                                │
│       "from": "Alice Johnson",                       │
│       "subject": "Requirements - Design Input",      │
│       "action": "Provide requirements and mockups"   │
│     }                                                │
│   ]                                                  │
│ }                                                    │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ GPT Planning Response (Bob)                          │
│ {                                                    │
│   "reasoning": "Alice needs design input. Will draft │
│                 initial requirements and schedule    │
│                 sync meeting.",                      │
│   "actions": [                                       │
│     {                                                │
│       "type": "send_email",                          │
│       "to": "alice.johnson@quickchat.dev",           │
│       "subject": "Re: QuickChat Requirements",       │
│       "body": "Hi Alice,\n\nI've reviewed our       │
│                discussion. Here are my initial       │
│                design requirements..."               │
│     },                                               │
│     {                                                │
│       "type": "send_chat",                           │
│       "to": "@alice_johnson",                        │
│       "message": "Sent you my initial thoughts.      │
│                   Can we sync at 2pm today?"         │
│     }                                                │
│   ]                                                  │
│ }                                                    │
└──────────────────────────────────────────────────────┘
│
v
Output: Bob responds to Alice via email + chat
        (cycle continues with Alice receiving in her inbox)
```

---

## 5. Token Tracking Data Flow

**API Call → Usage Extraction → Aggregation → JSON Report**

```
GPT API Call (any planning operation)
│
│ POST https://api.openai.com/v1/chat/completions
│ {
│   "model": "gpt-4.1-nano",
│   "messages": [...]
│ }
│
v
OpenAI Response:
{
  "choices": [...],
  "usage": {
    "prompt_tokens": 234,
    "completion_tokens": 123,
    "total_tokens": 357
  }
}
│
v
┌──────────────────────────────────────────────────────┐
│ utils/completion_util.py:generate_text()             │
│                                                      │
│ response = client.chat.completions.create(...)       │
│ total_tokens = response.usage.total_tokens           │
│                                                      │
│ return (response.choices[0].message.content,         │
│         total_tokens)  # → 357                       │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Caller: sim_manager/planner.py:_invoke()             │
│                                                      │
│ text, tokens = completion_util.generate_text(...)    │
│                                                      │
│ return PlanResult(                                   │
│   plan=json.loads(text),                             │
│   model="gpt-4.1-nano",                              │
│   tokens=357                                         │
│ )                                                    │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Database Storage (context-specific)                  │
└──────────────────────────────────────────────────────┘
│
├─ Project Plan
│  │  INSERT INTO project_plans (..., tokens_used=357)
│  │
├─ Daily Report
│  │  INSERT INTO daily_reports (..., tokens_used=456)
│  │
├─ Hourly Plan
│  │  INSERT INTO worker_plans (..., tokens_used=234)
│  │
└─ Simulation Report
   │  INSERT INTO simulation_reports (..., tokens_used=890)

│
v
┌──────────────────────────────────────────────────────┐
│ Runtime Aggregation                                  │
│ sim_manager/engine.py:get_token_usage()              │
│                                                      │
│ SELECT SUM(tokens_used) as total,                    │
│        model_used as model                           │
│ FROM (                                               │
│   SELECT tokens_used, model_used FROM project_plans  │
│   UNION ALL                                          │
│   SELECT tokens_used, model_used FROM worker_plans   │
│   UNION ALL                                          │
│   SELECT tokens_used, model_used FROM daily_reports  │
│   UNION ALL                                          │
│   SELECT tokens_used, model_used FROM simulation_reports
│ )                                                    │
│ GROUP BY model_used                                  │
└──────────────────────────────────────────────────────┘
│
v
Aggregated Result:
{
  "gpt-4.1-nano": 45678,
  "gpt-4o": 12345
}
│
v
┌──────────────────────────────────────────────────────┐
│ API Response: GET /api/v1/simulation/token-usage     │
│ {                                                    │
│   "per_model": {                                     │
│     "gpt-4.1-nano": 45678,                           │
│     "gpt-4o": 12345                                  │
│   },                                                 │
│   "total_tokens": 58023                              │
│ }                                                    │
└──────────────────────────────────────────────────────┘
│
v
┌──────────────────────────────────────────────────────┐
│ Simulation Script Collection                         │
│ save_json(tokens, "final_simulation_report.json")    │
│                                                      │
│ {                                                    │
│   ...,                                               │
│   "token_usage": {                                   │
│     "per_model": {...},                              │
│     "total_tokens": 58023                            │
│   },                                                 │
│   "summary": {                                       │
│     "total_tokens": 58023                            │
│   }                                                  │
│ }                                                    │
└──────────────────────────────────────────────────────┘
│
v
Output: JSON file with complete token tracking
```

---

## 6. Simulation Duration Tracking Data Flow

**Start Time → End Time → Duration Calculation → Report**

```
Script Start
│
├─ start_time = time.time()  # 1705504800.0
├─ start_datetime = datetime.now().isoformat()  # "2025-01-17T14:00:00"
│
v
┌──────────────────────────────────────────────────────┐
│ Simulation Execution                                 │
│ (services startup, persona generation, ticks, ...)   │
│                                                      │
│ [2 hours 34 minutes 17 seconds of wall-clock time]   │
└──────────────────────────────────────────────────────┘
│
v
Script End
│
├─ end_time = time.time()  # 1705514057.0
├─ end_datetime = datetime.now().isoformat()  # "2025-01-17T16:34:17"
│
v
┌──────────────────────────────────────────────────────┐
│ Duration Calculation                                 │
│                                                      │
│ duration_seconds = end_time - start_time             │
│   → 1705514057.0 - 1705504800.0 = 9257.0            │
│                                                      │
│ duration_hours = duration_seconds / 3600             │
│   → 9257.0 / 3600 = 2.571...                        │
│                                                      │
│ formatted = f"{int(hours)}h {int(mins)}m {int(secs)}s"
│   → "2h 34m 17s"                                     │
└──────────────────────────────────────────────────────┘
│
v
duration_info = {
  "start_time": "2025-01-17T14:00:00",
  "end_time": "2025-01-17T16:34:17",
  "duration_seconds": 9257.0,
  "duration_hours": 2.571,
  "duration_formatted": "2h 34m 17s"
}
│
v
┌──────────────────────────────────────────────────────┐
│ Merge into Final State                               │
│                                                      │
│ final_state = api_call("GET", "/api/v1/simulation")  │
│ final_state["simulation_duration"] = duration_info   │
│                                                      │
│ save_json(final_state, "final_state.json")           │
└──────────────────────────────────────────────────────┘
│
v
Output: final_state.json
{
  "current_tick": 9600,
  "is_running": false,
  "sim_time": "Day 19, Friday 17:00",
  "simulation_duration": {
    "start_time": "2025-01-17T14:00:00",
    "end_time": "2025-01-17T16:34:17",
    "duration_seconds": 9257.0,
    "duration_hours": 2.571,
    "duration_formatted": "2h 34m 17s"
  },
  ...
}
```

---

## 7. Complete Data Lifecycle: Single Tick

**Comprehensive view of all data transformations in one tick**

```
Tick 1234 (Day 2, Wednesday 13:34)

[1] Tick Metadata Calculation
    tick=1234
    → day_index = 1234 // 480 = 2
    → tick_of_day = 1234 % 480 = 274
    → hour = 274 // 60 = 4 (13:00 in 8h day = 4h after 9am)
    → minute = 274 % 60 = 34
    → sim_time = "Day 2, Wednesday 13:34"

[2] Event Processing
    SELECT * FROM events WHERE at_tick = 1234
    → [{type: "meeting", target_ids: [1,2], duration: 60}]
    → _set_worker_status([1,2], "in_meeting", until_tick=1294)
    → DELETE FROM events WHERE at_tick = 1234

[3] Inbox Processing (Worker 1: Alice)
    GET /mailboxes/alice.johnson@quickchat.dev/emails
    → [
        {id: 456, from: "carol.lee@...", subject: "Architecture doc ready"},
        {id: 457, from: "dave.chen@...", subject: "CI/CD pipeline live"}
      ]

    For each email:
      - Summarize: "Carol completed architecture document"
      - Extract action: "Review and approve architecture"
      - Queue: _worker_runtime[1].inbox.append({...})

    GET /rooms/dm:@alice_johnson:@bob_smith/messages
    → [
        {id: 789, sender: "@bob_smith", body: "Mockups are done"}
      ]

    Queue chat: _worker_runtime[1].inbox.append({...})

[4] Planning Check (Worker 3: Carol)
    _needs_hourly_plan(worker=Carol, tick=1234, sim_time)
    → minute == 34 (not 0) → No planning needed

    (Planning only happens at :00)

[5] Scheduled Action Execution (Worker 2: Bob)
    _scheduled_comms[2][1234] = [
      {type: "send_email", to: "alice...", subject: "...", body: "..."}
    ]

    For action:
      [5a] Dedup Check
           dedup_key = (1234, "email", "bob...", "alice...", "subject", "body_hash")
           → Not in _sent_dedup → OK to send

      [5b] Cooldown Check
           cooldown_key = ("email", "bob...", "alice...")
           last_contact = _last_contact.get(cooldown_key) = 1180
           → 1234 - 1180 = 54 > 10 (cooldown) → OK to send

      [5c] Email Send
           POST /emails/send
           → INSERT INTO emails (from, to, subject, body, sent_at)

      [5d] Exchange Log
           INSERT INTO worker_exchange_log (
             tick=1234, sender_id=2, recipient_id=1,
             channel="email", subject="...", summary="..."
           )

      [5e] Update Tracking
           _sent_dedup.add(dedup_key)
           _last_contact[cooldown_key] = 1234

[6] State Update
    UPDATE simulation_state SET current_tick = 1234

[7] Metrics Recording
    _planner_metrics.append({
      "tick": 1234,
      "worker_id": 1,
      "operation": "inbox_processing",
      "emails_processed": 2,
      "chats_processed": 1,
      "timestamp": "2025-01-17T14:34:00"
    })

[8] Tick Log
    INSERT INTO tick_log (tick, reason, created_at)
    VALUES (1234, "auto-tick", CURRENT_TIMESTAMP)

End of Tick 1234
→ All data persisted
→ Ready for tick 1235
```

---

## Summary

These data flow diagrams show:

1. **JSON ↔ Database ↔ Markdown**: Personas transform through multiple representations
2. **GPT Integration**: All planning involves JSON prompt → GPT → JSON response → database
3. **Message Queuing**: Emails/chats queued to runtime inbox → drained during planning
4. **Token Aggregation**: Per-call tracking → database storage → runtime aggregation
5. **State Persistence**: All simulation state stored in SQLite for recovery
6. **Tick-Based Processing**: Everything coordinated by tick counter (minute-level)

For API details, see `docs/reference/api-call-reference.md`.
For execution flows, see `docs/workflows/call-graphs.md`.
