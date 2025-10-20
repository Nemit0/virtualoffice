# VDOS Call Graphs and Execution Flows

Visual tree diagrams showing how code flows through the VDOS system.

---

## 1. Simulation Startup Flow

**From simulation script → all services running**

```
Script Main (e.g., quick_simulation.py::main)
├─ _maybe_start_services(force=True)
│  ├─ _free_port() × 3 → allocate ports for email, chat, sim
│  ├─ _start_server("email", email_app, "127.0.0.1", eport)
│  │  ├─ uvicorn.Config(email_app, host, port, log_level="warning")
│  │  ├─ uvicorn.Server(config)
│  │  ├─ threading.Thread(target=server.run, daemon=True).start()
│  │  └─ [wait for server.started flag, max 8s]
│  ├─ _start_server("chat", chat_app, "127.0.0.1", cport)
│  │  └─ [same uvicorn startup pattern]
│  └─ _start_server("sim", create_sim_app(engine), "127.0.0.1", sport)
│     ├─ HttpEmailGateway(base_url=EMAIL_BASE_URL)
│     ├─ HttpChatGateway(base_url=CHAT_BASE_URL)
│     ├─ SimulationEngine(
│     │     email_gateway=email_gw,
│     │     chat_gateway=chat_gw,
│     │     tick_interval_seconds=0.0002,
│     │     hours_per_day=480
│     │  )
│     │  ├─ execute_script(SIM_SCHEMA)  → create tables
│     │  ├─ _apply_migrations()
│     │  ├─ _ensure_state_row()  → INSERT INTO simulation_state
│     │  ├─ _bootstrap_channels()
│     │  │  ├─ email_gateway.ensure_mailbox(sim_manager_email)
│     │  │  │  └─ POST http://127.0.0.1:{eport}/mailboxes
│     │  │  └─ chat_gateway.ensure_user(sim_manager_handle)
│     │  │     └─ POST http://127.0.0.1:{cport}/users
│     │  ├─ _load_status_overrides()  → SELECT FROM worker_status_overrides
│     │  └─ _sync_worker_runtimes([])  → initialize runtime cache
│     └─ create_sim_app(engine)  → FastAPI app
│        ├─ app.state.engine = engine
│        └─ [mount routes at /api/v1/*]
├─ _full_reset()
│  ├─ POST http://127.0.0.1:{sport}/api/v1/simulation/stop
│  │  └─ engine.stop()  → UPDATE simulation_state SET is_running=0
│  └─ POST http://127.0.0.1:{sport}/api/v1/admin/hard-reset
│     ├─ engine.stop_auto_ticks()
│     ├─ DB_PATH.unlink()  → delete vdos.db
│     ├─ execute_script(EMAIL_SCHEMA)
│     ├─ execute_script(CHAT_SCHEMA)
│     ├─ execute_script(SIM_SCHEMA)
│     ├─ engine._ensure_state_row()
│     ├─ engine.reset()
│     └─ engine._bootstrap_channels()
└─ create_team()  [see "Persona Generation Flow"]
```

**Key Files**:
- `quick_simulation.py:320-344` - Main function
- `quick_simulation.py:159-196` - Service startup
- `src/virtualoffice/sim_manager/engine.py:221-286` - Engine init
- `src/virtualoffice/sim_manager/app.py:436-488` - Hard reset endpoint

---

## 2. Persona Generation Flow

**GPT-based persona creation → database storage**

```
create_team()  (e.g., quick_simulation.py:132-198)
├─ [for each team member spec]
│  ├─ POST http://127.0.0.1:{sport}/api/v1/personas/generate
│  │  ├─ app.py:202-208 → generate_persona(payload)
│  │  └─ _generate_persona_from_prompt(prompt, model_hint)
│  │     ├─ _generate_persona_text(messages, model="gpt-4.1-nano")
│  │     │  ├─ from virtualoffice.utils.completion_util import generate_text
│  │     │  └─ completion_util.py:generate_text(messages, model)
│  │     │     ├─ client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
│  │     │     ├─ response = client.chat.completions.create(
│  │     │     │     model=model,
│  │     │     │     messages=messages,
│  │     │     │     temperature=0.7
│  │     │     │  )
│  │     │     └─ return (response.choices[0].message.content, usage.total_tokens)
│  │     ├─ json.loads(text)  → parse GPT JSON
│  │     ├─ [normalize fields: timezone, work_hours, skills, etc.]
│  │     └─ return persona_dict
│  ├─ persona.update({
│  │     "is_department_head": spec["is_head"],
│  │     "email_address": f"{name}@quickchat.dev",
│  │     "chat_handle": f"@{name}",
│  │     "timezone": "America/New_York",
│  │     "work_hours": "09:00-18:00"
│  │  })
│  └─ POST http://127.0.0.1:{sport}/api/v1/people
│     ├─ app.py:198-200 → create_person(payload)
│     └─ engine.create_person(PersonCreate)
│        ├─ _validate_schedule_blocks(persona.schedule)
│        ├─ build_worker_markdown(WorkerPersona(...))
│        │  └─ virtualWorkers/worker.py:build_worker_markdown()
│        │     ├─ [format skills, objectives, schedule as markdown]
│        │     └─ return multiline string
│        ├─ INSERT INTO people (name, role, timezone, ..., persona_markdown)
│        ├─ [for each schedule_block]
│        │  └─ INSERT INTO schedule_blocks (person_id, start, end, activity)
│        ├─ email_gateway.ensure_mailbox(persona.email_address)
│        │  └─ POST http://127.0.0.1:{eport}/mailboxes
│        ├─ chat_gateway.ensure_user(persona.chat_handle)
│        │  └─ POST http://127.0.0.1:{cport}/users
│        └─ _sync_worker_runtimes()  → update runtime cache
└─ save_json(created_personas, "team_personas.json")
```

**Key Files**:
- `src/virtualoffice/sim_manager/app.py:49-130` - Persona generation
- `src/virtualoffice/sim_manager/engine.py:396-470` - create_person()
- `src/virtualoffice/utils/completion_util.py` - OpenAI client
- `src/virtualoffice/virtualWorkers/worker.py:59-119` - Markdown builder

---

## 3. Simulation Initialization Flow

**Project setup → daily/hourly planning**

```
start_project_simulation()  (e.g., mobile_chat_simulation.py:345-366)
├─ POST http://127.0.0.1:{sport}/api/v1/simulation/start
│  ├─ app.py:299-343 → start_simulation(payload, async_init=False)
│  └─ _retry_init(engine, payload, attempt=1)
│     ├─ [with _init_lock]
│     │  └─ _init_status["running"] = True
│     └─ engine.start(SimulationStartRequest)
│        ├─ [acquire _advance_lock]
│        ├─ state = _get_state()  → SELECT FROM simulation_state
│        ├─ [validate not already running]
│        ├─ _project_plan_cache = None  → clear cache
│        ├─ _active_person_ids = payload.include_person_ids
│        ├─ _random.seed(payload.random_seed or 42)
│        ├─ _planner_model_hint = payload.model_hint
│        ├─ _project_duration_weeks = payload.duration_weeks
│        │
│        ├─ [Generate project plan with GPT]
│        ├─ _generate_project_plan(payload)
│        │  ├─ all_people = list_people()
│        │  ├─ head = [p for p in all_people if p.is_department_head][0]
│        │  ├─ [build planning context from personas]
│        │  ├─ planner.plan_project(
│        │  │     project_name=payload.project_name,
│        │  │     project_summary=payload.project_summary,
│        │  │     duration_weeks=payload.duration_weeks,
│        │  │     team_context=context,
│        │  │     model_hint=model_hint
│        │  │  )
│        │  │  ├─ planner.py:GPTPlanner.plan_project()
│        │  │  ├─ messages = [system_msg, user_msg]
│        │  │  ├─ _invoke(messages, model)
│        │  │  │  ├─ from virtualoffice.utils.completion_util import generate_text
│        │  │  │  └─ generate_text(messages, model)  → OpenAI API call
│        │  │  ├─ json.loads(response_text)
│        │  │  └─ return PlanResult(plan=plan_dict, model=model, tokens=tokens)
│        │  ├─ INSERT INTO project_plans (
│        │  │     project_name, project_summary, plan,
│        │  │     generated_by=head.id, duration_weeks, model_used, tokens_used
│        │  │  )
│        │  ├─ [for each person in include_person_ids]
│        │  │  └─ INSERT INTO project_assignments (project_id, person_id)
│        │  └─ _project_plan_cache = plan_data
│        │
│        ├─ UPDATE simulation_state SET is_running=1
│        └─ return SimulationState(current_tick=0, is_running=True)
│
└─ return SimulationControlResponse(message="Simulation started for 'ProjectName'")
```

**Multi-Project Variant**:
```
engine.start(payload with payload.projects)
├─ [validate payload.projects structure]
├─ _generate_multi_project_plan(payload)
│  ├─ [for each subproject in payload.projects]
│  │  ├─ INSERT INTO project_plans (
│  │  │     project_name=sub.project_name,
│  │  │     start_week=sub.start_week,
│  │  │     duration_weeks=sub.duration_weeks
│  │  │  )
│  │  └─ [assign people via project_assignments]
│  └─ _project_plan_cache = {"projects": [...]}
└─ UPDATE simulation_state SET is_running=1
```

**Key Files**:
- `src/virtualoffice/sim_manager/app.py:299-343` - Start endpoint
- `src/virtualoffice/sim_manager/engine.py:874-1027` - start() method
- `src/virtualoffice/sim_manager/planner.py:60-120` - plan_project()

---

## 4. Tick Processing Flow

**What happens each tick during simulation**

```
POST /api/v1/simulation/advance {"ticks": 60, "reason": "auto"}
├─ app.py:419-429 → advance_simulation(payload)
└─ engine.advance(ticks=60, reason="auto")
   ├─ [acquire _advance_lock]  → prevent concurrent ticks
   ├─ state = _get_state()
   ├─ [validate is_running]
   ├─ _reset_tick_sends()  → clear dedup cache
   │
   ├─ [for tick in range(current_tick, current_tick + ticks)]
   │  │
   │  ├─ _calculate_sim_time(tick)
   │  │  ├─ day_index = tick // (hours_per_day * 60)
   │  │  ├─ tick_of_day = tick % (hours_per_day * 60)
   │  │  ├─ hour = tick_of_day // 60
   │  │  ├─ minute = tick_of_day % 60
   │  │  └─ return {"day_index": day_index, "hour": hour, "minute": minute, ...}
   │  │
   │  ├─ _process_scheduled_events(tick)
   │  │  ├─ SELECT * FROM events WHERE at_tick = {tick}
   │  │  ├─ [for each event]
   │  │  │  └─ _inject_event_context(event)
   │  │  │     ├─ [parse event.type: "sick_day", "meeting", etc.]
   │  │  │     └─ _set_worker_status(worker_id, status, duration, reason)
   │  │  │        └─ INSERT/UPDATE worker_status_overrides
   │  │  └─ DELETE FROM events WHERE at_tick = {tick}
   │  │
   │  ├─ _process_inbox_for_all_workers(tick, sim_time)
   │  │  ├─ active_workers = _get_active_workers()
   │  │  └─ [for each worker]
   │  │     ├─ _process_worker_inbox(worker, tick, sim_time)
   │  │     │  ├─ GET http://127.0.0.1:{eport}/mailboxes/{worker.email}/emails
   │  │     │  │  └─ email_server returns [{id, from, subject, body, ...}, ...]
   │  │     │  ├─ [for each email]
   │  │     │  │  ├─ _summarize_with_gpt(email.body)  → action items
   │  │     │  │  └─ runtime.queue(_InboundMessage(
   │  │     │  │        sender_id=..., subject=email.subject,
   │  │     │  │        summary=summary, channel="email", tick=tick
   │  │     │  │     ))
   │  │     │  ├─ GET http://127.0.0.1:{cport}/rooms/dm:{handle}:{other}/messages
   │  │     │  │  └─ chat_server returns [{id, sender, body, timestamp}, ...]
   │  │     │  └─ [queue chat messages to inbox]
   │  │     └─ INSERT INTO worker_runtime_messages (recipient_id, payload)
   │  │
   │  ├─ _maybe_plan_for_workers(tick, sim_time)
   │  │  ├─ [determine if hourly planning needed]
   │  │  ├─ _needs_hourly_plan(worker, tick, sim_time)
   │  │  │  ├─ [check if start of new hour AND within work hours]
   │  │  │  ├─ [check not already planned this minute]
   │  │  │  └─ return True/False
   │  │  │
   │  │  └─ [for each worker needing plan]
   │  │     ├─ _generate_hourly_plan(worker, tick, sim_time)
   │  │     │  ├─ context = _build_planning_context(worker, tick, sim_time)
   │  │     │  │  ├─ project_plan = get_project_plan()
   │  │     │  │  ├─ inbox_items = worker_runtime.drain()
   │  │     │  │  ├─ status = _get_worker_status(worker.id, tick)
   │  │     │  │  └─ return {
   │  │     │  │        "project": project_plan,
   │  │     │  │        "inbox": inbox_items,
   │  │     │  │        "status": status,
   │  │     │  │        "current_time": sim_time
   │  │     │  │     }
   │  │     │  ├─ planner.plan_hourly(
   │  │     │  │     persona_markdown=worker.persona_markdown,
   │  │     │  │     context=context,
   │  │     │  │     model_hint=model_hint
   │  │     │  │  )
   │  │     │  │  ├─ planner.py:GPTPlanner.plan_hourly()
   │  │     │  │  ├─ messages = [system, user with persona + context]
   │  │     │  │  ├─ _invoke(messages, model)  → OpenAI API
   │  │     │  │  ├─ json.loads(response)
   │  │     │  │  └─ return PlanResult(plan={actions: [...]}, model, tokens)
   │  │     │  ├─ INSERT INTO worker_plans (
   │  │     │  │     person_id, tick, plan_type="hourly",
   │  │     │  │     content=json.dumps(plan), model_used, tokens_used, context
   │  │     │  │  )
   │  │     │  └─ _schedule_actions(worker.id, tick, plan.actions)
   │  │     │     └─ _scheduled_comms[worker.id][target_tick] = actions
   │  │     │
   │  │     └─ [daily planning at day start]
   │  │        └─ _generate_daily_report(worker, day_index)
   │  │           ├─ [similar GPT call for daily summary]
   │  │           └─ INSERT INTO daily_reports
   │  │
   │  ├─ _execute_scheduled_actions(tick)
   │  │  ├─ [for each worker with scheduled actions at this tick]
   │  │  └─ [for each action in worker's schedule]
   │  │     ├─ action.type == "send_email"
   │  │     │  ├─ _can_send(tick, "email", sender, recipient, subject, body)
   │  │     │  │  ├─ [check dedup cache]
   │  │     │  │  └─ [check cooldown period]
   │  │     │  ├─ email_gateway.send_email(
   │  │     │  │     from=worker.email, to=recipient,
   │  │     │  │     subject=action.subject, body=action.body
   │  │     │  │  )
   │  │     │  │  └─ POST http://127.0.0.1:{eport}/emails/send
   │  │     │  └─ INSERT INTO worker_exchange_log (
   │  │     │        tick, sender_id, recipient_id,
   │  │     │        channel="email", subject, summary
   │  │     │     )
   │  │     │
   │  │     └─ action.type == "send_chat"
   │  │        ├─ _can_send(tick, "chat", sender, recipient, None, body)
   │  │        ├─ chat_gateway.send_message(
   │  │        │     room_slug=dm_slug, sender=worker.handle, body=action.message
   │  │        │  )
   │  │        │  └─ POST http://127.0.0.1:{cport}/messages
   │  │        └─ INSERT INTO worker_exchange_log
   │  │
   │  ├─ UPDATE simulation_state SET current_tick = {tick}
   │  └─ [emit progress to planner metrics]
   │
   ├─ final_state = _get_state()
   └─ return SimulationAdvanceResult(
         tick=final_state.current_tick,
         sim_time=_calculate_sim_time(final_state.current_tick),
         message=f"Advanced {ticks} ticks"
      )
```

**Key Files**:
- `src/virtualoffice/sim_manager/engine.py:1054-1280` - advance() method
- `src/virtualoffice/sim_manager/engine.py:1349-1458` - Planning methods
- `src/virtualoffice/sim_manager/engine.py:1473-1610` - Action execution
- `src/virtualoffice/sim_manager/planner.py:122-212` - plan_hourly()

---

## 5. Email Send Flow

**From worker decision → email delivered**

```
_execute_scheduled_actions(tick)
├─ action = {"type": "send_email", "to": "dev@quickchat.dev", "subject": "...", "body": "..."}
├─ _can_send(tick=1234, channel="email", sender="pm@quickchat.dev", recipient="dev@quickchat.dev", ...)
│  ├─ dedup_key = (tick, channel, sender, recipient, subject, body_hash)
│  ├─ [check if dedup_key in _sent_dedup]  → False (OK to send)
│  ├─ cooldown_key = (channel, sender, recipient)
│  ├─ [check if tick - _last_contact[cooldown_key] < 10]  → False (cooldown passed)
│  ├─ _sent_dedup.add(dedup_key)
│  ├─ _last_contact[cooldown_key] = tick
│  └─ return True
│
├─ email_gateway.send_email(
│     from_address="pm@quickchat.dev",
│     to_address="dev@quickchat.dev",
│     subject="Sprint planning update",
│     body="Let's discuss feature priorities..."
│  )
│  ├─ gateways.py:HttpEmailGateway.send_email()
│  └─ POST http://127.0.0.1:8000/emails/send
│     ├─ {
│     │    "from_address": "pm@quickchat.dev",
│     │    "to_address": "dev@quickchat.dev",
│     │    "subject": "Sprint planning update",
│     │    "body": "Let's discuss...",
│     │    "sent_at": "2025-01-17T14:30:00Z"
│     │  }
│     └─ email_server (virtualoffice/servers/email/app.py)
│        ├─ send_email(payload: EmailSend)
│        ├─ ensure_mailbox(payload.from_address)
│        │  └─ INSERT OR IGNORE INTO mailboxes (address)
│        ├─ ensure_mailbox(payload.to_address)
│        ├─ INSERT INTO emails (
│        │     from_address, to_address, subject, body,
│        │     sent_at, received_at=CURRENT_TIMESTAMP
│        │  )
│        └─ return EmailRead(id=123, from_address=..., ...)
│
└─ INSERT INTO worker_exchange_log (
      tick=1234, sender_id=1, recipient_id=3,
      channel="email", subject="Sprint planning update",
      summary="Discussion about feature priorities"
   )
```

**Reading Emails**:
```
_process_worker_inbox(worker, tick, sim_time)
├─ GET http://127.0.0.1:8000/mailboxes/dev@quickchat.dev/emails
│  └─ email_server: get_emails(address)
│     ├─ SELECT * FROM emails WHERE to_address = 'dev@quickchat.dev'
│     │     ORDER BY received_at DESC
│     └─ return [EmailRead(...), EmailRead(...), ...]
│
├─ [for each email]
│  ├─ _summarize_with_gpt(email.body)  → extract action items
│  └─ worker_runtime.queue(_InboundMessage(
│        sender_id=1, sender_name="PM Name",
│        subject=email.subject, summary="...",
│        action_item="Review priorities", channel="email", tick=tick
│     ))
└─ [messages queued for next hourly planning]
```

**Key Files**:
- `src/virtualoffice/sim_manager/engine.py:1473-1537` - Email sending
- `src/virtualoffice/sim_manager/gateways.py:16-38` - HttpEmailGateway
- `src/virtualoffice/servers/email/app.py:50-82` - Email server send
- `src/virtualoffice/servers/email/app.py:84-95` - Email server read

---

## 6. Chat Message Flow

**From worker decision → chat posted**

```
_execute_scheduled_actions(tick)
├─ action = {"type": "send_chat", "to": "dev", "message": "Ready for standup?"}
├─ _can_send(tick=1250, channel="chat", sender="pm", recipient="dev", body="Ready...")
│  └─ [same dedup + cooldown logic as email]
│
├─ chat_gateway.send_message(
│     room_slug="dm:dev:pm",  # sorted handles
│     sender="pm",
│     body="Ready for standup?"
│  )
│  ├─ gateways.py:HttpChatGateway.send_message()
│  └─ POST http://127.0.0.1:8001/messages
│     ├─ {
│     │    "room_slug": "dm:dev:pm",
│     │    "sender": "pm",
│     │    "body": "Ready for standup?",
│     │    "timestamp": "2025-01-17T14:45:00Z"
│     │  }
│     └─ chat_server (virtualoffice/servers/chat/app.py)
│        ├─ send_message(payload: MessageSend)
│        ├─ ensure_user(payload.sender)
│        │  └─ INSERT OR IGNORE INTO users (handle, username)
│        ├─ [parse room_slug to determine if DM or group]
│        ├─ ensure_room(room_slug)
│        │  ├─ INSERT OR IGNORE INTO rooms (slug, name, room_type)
│        │  └─ [for each participant in DM]
│        │     └─ INSERT OR IGNORE INTO memberships (room_id, user_id)
│        ├─ INSERT INTO messages (
│        │     room_id, sender_id, body,
│        │     timestamp=payload.timestamp or CURRENT_TIMESTAMP
│        │  )
│        └─ return MessageRead(id=456, room_slug=..., sender=..., body=...)
│
└─ INSERT INTO worker_exchange_log (
      tick=1250, sender_id=1, recipient_id=3,
      channel="chat", summary="Standup coordination"
   )
```

**Reading Chat Messages**:
```
_process_worker_inbox(worker, tick, sim_time)
├─ handles = [worker.chat_handle, *other_team_handles]
├─ [for each other_handle]
│  ├─ room_slug = _dm_slug(worker.chat_handle, other_handle)
│  │  └─ f"dm:{min(a,b)}:{max(a,b)}"  # sorted
│  ├─ GET http://127.0.0.1:8001/rooms/{room_slug}/messages
│  │  └─ chat_server: get_messages(room_slug)
│  │     ├─ SELECT r.id FROM rooms r WHERE r.slug = '{room_slug}'
│  │     ├─ SELECT m.* FROM messages m
│  │     │     WHERE m.room_id = {room_id}
│  │     │     ORDER BY m.timestamp DESC
│  │     └─ return [MessageRead(...), MessageRead(...), ...]
│  │
│  └─ [for each message not yet processed]
│     └─ worker_runtime.queue(_InboundMessage(
│           sender_name=message.sender, summary=message.body,
│           channel="chat", tick=tick
│        ))
└─ [messages queued for next hourly planning]
```

**Key Files**:
- `src/virtualoffice/sim_manager/engine.py:1538-1610` - Chat sending
- `src/virtualoffice/sim_manager/gateways.py:60-102` - HttpChatGateway
- `src/virtualoffice/servers/chat/app.py:92-151` - Chat server send
- `src/virtualoffice/servers/chat/app.py:153-180` - Chat server read

---

## 7. Planning Flow

**Project plan → daily plan → hourly actions**

```
Simulation Start
├─ _generate_project_plan(payload)
│  ├─ planner.plan_project(
│  │     project_name="QuickChat Mobile App",
│  │     project_summary="Develop mobile chat MVP in 4 weeks...",
│  │     duration_weeks=4,
│  │     team_context="""
│  │       Team:
│  │       - Alice (PM): Agile expert, stakeholder comm
│  │       - Bob (Designer): UI/UX, mobile interfaces
│  │       - Carol (Developer): React Native, Node.js
│  │       - Dave (DevOps): CI/CD, cloud infrastructure
│  │     """
│  │  )
│  │  ├─ system_msg = "You are a project planning assistant..."
│  │  ├─ user_msg = f"Create 4-week plan for: {project_summary}\nTeam: {team_context}"
│  │  ├─ _invoke(messages, model="gpt-4.1-nano")
│  │  │  └─ OpenAI API call
│  │  ├─ response = {
│  │  │    "phases": [
│  │  │      {"week": 1, "focus": "Requirements & Design", "deliverables": [...]},
│  │  │      {"week": 2, "focus": "Core Development", "deliverables": [...]},
│  │  │      {"week": 3, "focus": "Integration & Testing", "deliverables": [...]},
│  │  │      {"week": 4, "focus": "Polish & Launch", "deliverables": [...]}
│  │  │    ],
│  │  │    "milestones": [...],
│  │  │    "risks": [...]
│  │  │  }
│  │  └─ return PlanResult(plan=response, model="gpt-4.1-nano", tokens=1234)
│  │
│  └─ INSERT INTO project_plans (
│        project_name, project_summary, plan=json.dumps(plan_result.plan),
│        duration_weeks=4, model_used="gpt-4.1-nano", tokens_used=1234
│     )
│
└─ [stored in _project_plan_cache for reuse]

Daily Planning (at start of each day)
├─ _generate_daily_report(worker, day_index=0)
│  ├─ project_plan = get_project_plan()
│  ├─ week_num = (day_index // 5) + 1
│  ├─ current_phase = project_plan["phases"][week_num - 1]
│  ├─ planner.plan_daily(
│  │     persona_markdown=worker.persona_markdown,
│  │     project_context=current_phase,
│  │     day_index=day_index
│  │  )
│  │  ├─ messages = [
│  │  │    {"role": "system", "content": "Create daily plan..."},
│  │  │    {"role": "user", "content": f"Day {day_index}, Phase: {current_phase}"}
│  │  │  ]
│  │  ├─ _invoke(messages, model)  → OpenAI API
│  │  └─ return PlanResult(plan={"priorities": [...], "schedule": [...]}, ...)
│  │
│  └─ INSERT INTO daily_reports (
│        person_id, day_index, report=json.dumps(plan),
│        model_used, tokens_used
│     )

Hourly Planning (at start of each hour, within work hours)
├─ _needs_hourly_plan(worker, tick=480, sim_time={day:0, hour:8, minute:0})
│  ├─ [check: sim_time.minute == 0]  → True (start of hour)
│  ├─ [check: 9 <= sim_time.hour < 17]  → True (work hours)
│  ├─ [check: not already planned this minute]  → True
│  └─ return True
│
└─ _generate_hourly_plan(worker, tick=480, sim_time)
   ├─ context = _build_planning_context(...)
   │  ├─ project_plan = get_project_plan()
   │  ├─ inbox_items = worker_runtime.drain()  # emails/chats received
   │  ├─ status = _get_worker_status(worker.id, tick)  # "available" or "sick", etc.
   │  └─ return {
   │        "project": project_plan,
   │        "current_phase": "Week 1: Requirements & Design",
   │        "inbox": [
   │           {"from": "PM", "subject": "Kickoff meeting notes", "action": "Review requirements"},
   │           {"from": "Designer", "message": "Initial mockups ready", "action": "Provide feedback"}
   │        ],
   │        "status": "available",
   │        "current_time": "Day 0, 08:00"
   │     }
   │
   ├─ planner.plan_hourly(
   │     persona_markdown=worker.persona_markdown,
   │     context=context,
   │     model_hint="gpt-4.1-nano"
   │  )
   │  ├─ system = "You are simulating a worker. Respond with JSON actions..."
   │  ├─ user = f"""
   │  │    Persona:
   │  │    {persona_markdown}
   │  │
   │  │    Context:
   │  │    Project Phase: Week 1 - Requirements & Design
   │  │    Inbox: 2 messages
   │  │      - PM: Review requirements
   │  │      - Designer: Provide feedback on mockups
   │  │    Status: available
   │  │    Time: 08:00
   │  │
   │  │    Plan your next hour. Return JSON:
   │  │    {
   │  │      "reasoning": "...",
   │  │      "actions": [
   │  │        {"type": "send_email", "to": "pm@...", "subject": "...", "body": "..."},
   │  │        {"type": "send_chat", "to": "designer", "message": "..."}
   │  │      ]
   │  │    }
   │  │    """
   │  ├─ _invoke(messages, model="gpt-4.1-nano")  → OpenAI API
   │  ├─ response = {
   │  │    "reasoning": "Need to respond to PM about requirements and coordinate with designer",
   │  │    "actions": [
   │  │      {
   │  │        "type": "send_email",
   │  │        "to": "pm@quickchat.dev",
   │  │        "subject": "Re: Kickoff meeting notes",
   │  │        "body": "Thanks for the notes. I've reviewed the requirements and have a few questions..."
   │  │      },
   │  │      {
   │  │        "type": "send_chat",
   │  │        "to": "designer",
   │  │        "message": "Mockups look great! Let's sync on the user flow at 10am"
   │  │      }
   │  │    ]
   │  │  }
   │  └─ return PlanResult(plan=response, model="gpt-4.1-nano", tokens=567)
   │
   ├─ INSERT INTO worker_plans (
   │     person_id=worker.id, tick=480, plan_type="hourly",
   │     content=json.dumps(plan_result.plan),
   │     model_used="gpt-4.1-nano", tokens_used=567,
   │     context=json.dumps(context)
   │  )
   │
   └─ _schedule_actions(worker.id, tick, plan_result.plan["actions"])
      ├─ [for each action]
      │  ├─ target_tick = tick + random.randint(5, 55)  # within the hour
      │  └─ _scheduled_comms[worker.id][target_tick].append(action)
      └─ [actions will execute when tick reaches target_tick]
```

**Key Files**:
- `src/virtualoffice/sim_manager/engine.py:1282-1347` - Project plan generation
- `src/virtualoffice/sim_manager/engine.py:1349-1458` - Hourly/daily planning
- `src/virtualoffice/sim_manager/planner.py:60-212` - GPT planner methods
- `src/virtualoffice/utils/completion_util.py` - OpenAI client wrapper

---

## 8. Auto-Tick Loop Flow

**Background thread continuously advancing simulation**

```
POST /api/v1/simulation/ticks/start
├─ app.py:394-406 → start_ticks()
└─ engine.start_auto_ticks()
   ├─ [validate is_running]
   ├─ UPDATE simulation_state SET auto_tick=1
   ├─ _auto_tick_stop = threading.Event()
   ├─ _auto_tick_thread = threading.Thread(target=_auto_tick_loop, daemon=True)
   ├─ _auto_tick_thread.start()
   └─ return SimulationState(auto_tick=True)

_auto_tick_loop() [background thread]
├─ while not _auto_tick_stop.is_set():
│  ├─ time.sleep(_tick_interval_seconds)  # 0.0002 or 1.0
│  ├─ [acquire _advance_lock]
│  ├─ state = _get_state()
│  ├─ [if not state.is_running]: break
│  ├─ advance(ticks=1, reason="auto-tick")
│  │  └─ [see "Tick Processing Flow" above]
│  └─ [release _advance_lock]
└─ [thread exits when _auto_tick_stop is set]

POST /api/v1/simulation/ticks/stop
├─ app.py:408-417 → stop_ticks()
└─ engine.stop_auto_ticks()
   ├─ UPDATE simulation_state SET auto_tick=0
   ├─ _auto_tick_stop.set()
   ├─ _auto_tick_thread.join(timeout=5)
   └─ return SimulationState(auto_tick=False)
```

**Key Files**:
- `src/virtualoffice/sim_manager/engine.py:1037-1052` - start_auto_ticks()
- `src/virtualoffice/sim_manager/engine.py:1696-1715` - _auto_tick_loop()
- `src/virtualoffice/sim_manager/app.py:394-417` - Start/stop endpoints

---

## 9. API Call Chain Summary

**High-level view of which modules call which APIs**

```
Simulation Scripts (quick_simulation.py, etc.)
├─ POST /api/v1/admin/hard-reset
│  └─ sim_manager/app.py:436 → admin_hard_reset()
│
├─ POST /api/v1/personas/generate
│  └─ sim_manager/app.py:202 → generate_persona()
│     └─ utils/completion_util.py → OpenAI API
│
├─ POST /api/v1/people
│  └─ sim_manager/app.py:198 → create_person()
│     ├─ POST http://127.0.0.1:8000/mailboxes
│     │  └─ servers/email/app.py:40 → create_mailbox()
│     └─ POST http://127.0.0.1:8001/users
│        └─ servers/chat/app.py:54 → create_user()
│
├─ POST /api/v1/simulation/start
│  └─ sim_manager/app.py:299 → start_simulation()
│     └─ sim_manager/planner.py → OpenAI API (project plan)
│
├─ POST /api/v1/simulation/advance
│  └─ sim_manager/app.py:419 → advance_simulation()
│     ├─ GET http://127.0.0.1:8000/mailboxes/{addr}/emails
│     │  └─ servers/email/app.py:84 → get_emails()
│     ├─ GET http://127.0.0.1:8001/rooms/{slug}/messages
│     │  └─ servers/chat/app.py:153 → get_messages()
│     ├─ sim_manager/planner.py → OpenAI API (hourly plans)
│     ├─ POST http://127.0.0.1:8000/emails/send
│     │  └─ servers/email/app.py:50 → send_email()
│     └─ POST http://127.0.0.1:8001/messages
│        └─ servers/chat/app.py:92 → send_message()
│
├─ POST /api/v1/simulation/ticks/start
│  └─ sim_manager/app.py:394 → start_ticks()
│     └─ [spawns background thread calling advance() repeatedly]
│
├─ GET /api/v1/simulation
│  └─ sim_manager/app.py:252 → get_simulation()
│
├─ GET /api/v1/people/{id}/daily-reports
│  └─ sim_manager/app.py:230 → get_daily_reports()
│
└─ GET /api/v1/simulation/token-usage
   └─ sim_manager/app.py:246 → get_token_usage()
```

---

## 10. Complete Script Execution Example

**Full trace of `quick_simulation.py` run**

```
$ python quick_simulation.py

quick_simulation.py::main() [line 320]
│
├─ _start_uvicorn_server("email", email_app, "127.0.0.1", 8000)
│  └─ [email server running on :8000]
│
├─ _start_uvicorn_server("chat", chat_app, "127.0.0.1", 8001)
│  └─ [chat server running on :8001]
│
├─ _start_uvicorn_server("sim", create_sim_app(), "127.0.0.1", 8015)
│  └─ [sim manager running on :8015]
│
├─ create_mobile_team() [line 132]
│  ├─ POST http://127.0.0.1:8015/api/v1/personas/generate
│  │  └─ OpenAI API (gpt-4.1-nano) → returns PM persona JSON
│  ├─ POST http://127.0.0.1:8015/api/v1/people
│  │  ├─ INSERT INTO people (name="Alice", role="Project Manager", ...)
│  │  ├─ POST http://127.0.0.1:8000/mailboxes {"address": "alice@quickchat.dev"}
│  │  └─ POST http://127.0.0.1:8001/users {"handle": "@alice"}
│  ├─ [repeat for Designer, Developer, DevOps]
│  └─ save_json(personas, "mobile_team.json")
│
├─ run_simulation(personas, weeks=4) [line 201]
│  ├─ POST http://127.0.0.1:8015/api/v1/simulation/start
│  │  ├─ OpenAI API (gpt-4.1-nano) → project plan for 4 weeks
│  │  ├─ INSERT INTO project_plans (...)
│  │  └─ UPDATE simulation_state SET is_running=1
│  │
│  ├─ [Week 1]
│  │  ├─ POST /api/v1/simulation/advance {"ticks": 480}
│  │  │  ├─ Ticks 0-479: Process inbox, plan hourly, execute actions
│  │  │  │  ├─ GET /mailboxes/alice@quickchat.dev/emails
│  │  │  │  ├─ OpenAI API → hourly plan for Alice
│  │  │  │  ├─ POST /emails/send (Alice → Bob re: requirements)
│  │  │  │  ├─ POST /messages (Bob → Carol re: design handoff)
│  │  │  │  └─ ... [480 ticks of activity]
│  │  │  └─ return {"tick": 480}
│  │  ├─ POST /api/v1/simulation/advance {"ticks": 480}  # Day 2
│  │  ├─ POST /api/v1/simulation/advance {"ticks": 480}  # Day 3
│  │  ├─ POST /api/v1/simulation/advance {"ticks": 480}  # Day 4
│  │  ├─ POST /api/v1/simulation/advance {"ticks": 480}  # Day 5
│  │  └─ save_json(state, "week_1_state.json")
│  │
│  ├─ [Weeks 2-4 similar...]
│  └─ return True
│
├─ collect_all_emails(personas) [line 247]
│  ├─ GET http://127.0.0.1:8000/mailboxes/alice@quickchat.dev/emails → [123 emails]
│  ├─ GET http://127.0.0.1:8000/mailboxes/bob@quickchat.dev/emails → [98 emails]
│  ├─ ... [for each mailbox]
│  └─ save_json(emails, "all_emails.json")
│
├─ collect_all_chats(personas) [line 263]
│  ├─ GET http://127.0.0.1:8001/rooms/dm:@alice:@bob/messages → [45 messages]
│  ├─ GET http://127.0.0.1:8001/rooms/dm:@alice:@carol/messages → [32 messages]
│  ├─ ... [for all DM pairs]
│  └─ save_json(chats, "all_chats.json")
│
├─ generate_reports(personas) [line 284]
│  ├─ GET http://127.0.0.1:8015/api/v1/simulation → final state
│  ├─ GET http://127.0.0.1:8015/api/v1/events → all events
│  ├─ GET http://127.0.0.1:8015/api/v1/simulation/token-usage → token summary
│  ├─ GET http://127.0.0.1:8015/api/v1/people/1/daily-reports?limit=200
│  ├─ ... [for each person]
│  └─ save_json(report, "final_simulation_report.json")
│
└─ [cleanup]
   ├─ _stop_uvicorn_server(email_handle)
   ├─ _stop_uvicorn_server(chat_handle)
   └─ _stop_uvicorn_server(sim_handle)

✅ Simulation complete. Output: simulation_output/
```

---

## Summary

These call graphs demonstrate:

1. **Layered Architecture**: Scripts → Sim Manager → Email/Chat Servers → Database
2. **GPT Integration Points**: Persona gen, project planning, daily/hourly planning
3. **HTTP-based Communication**: All services communicate via REST APIs
4. **Tick-based Simulation**: Everything scheduled/executed relative to tick counter
5. **Database Persistence**: All state stored in SQLite (people, plans, messages, logs)

For API endpoint details, see `docs/reference/api-call-reference.md`.
For data transformations, see `docs/workflows/data-flow-diagrams.md`.
