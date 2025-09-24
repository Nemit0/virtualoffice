# Repository Guidelines

## Project Overview
Virtual Department Operations Simulator (VDOS) is a headless-first sandbox that generates realistic departmental comms (email + chat) and agent behaviour so downstream systems (dashboards, analytics, AI assistants) can iterate without exposing production data.

## Current High-Level Architecture
- **PySide6 App** (`src/virtualoffice/app.py`): developer GUI for spinning up services, driving the sim, and tailing logs.
- **FastAPI services** (`src/virtualoffice/servers`): REST backends for email and chat communication.
- **Simulation manager** (`src/virtualoffice/sim_manager`): orchestrates ticks, persists people/events, and calls the comms services.
- **Virtual workers** (`src/virtualoffice/virtualWorkers`): persona templates + helpers for hourly planning prompts.
- **Common utilities** (`src/virtualoffice/common` & `src/virtualoffice/utils`): database access, OpenAI helper.
- **Tests** (`tests/`): pytest suite covering email/chat servers, simulation control loop, and worker markdown.

## Modules & Responsibilities

### PySide6 Application (`src/virtualoffice/app.py`)
- Starts/stops each FastAPI service individually from the GUI.
- Provides simulation controls (seed worker, start/stop sim, advance ticks) and a live log viewer.
- Uses background threads (`RequestWorker`) so HTTP calls and server startup do not block the UI.
- Exposes `start_server(name)`, `stop_server(name)`, and `is_server_running(name)` used by the dashboard.

### Email Server (`src/virtualoffice/servers/email`)
- `app.py`: FastAPI app exposing `/emails/send`, `/mailboxes/{address}/emails`, `/mailboxes/{address}/drafts`, etc.
- `models.py`: Pydantic models for payloads (`EmailSend`, `DraftCreate`, `Mailbox`).
- Persists to SQLite via `virtualoffice.common.db`. Automatically provisions mailboxes when needed.

### Chat Server (`src/virtualoffice/servers/chat`)
- `app.py`: FastAPI service for rooms, messages, and DMs (auto-creates users/rooms as needed).
- `models.py`: Pydantic models for chat entities.
- Stores memberships and messages in SQLite, paralleling the email server’s structure.

### Simulation Manager (`src/virtualoffice/sim_manager`)
- `app.py`: FastAPI API (start/stop/advance, CRUD people, event injection).
- `engine.py`: SQLite-backed orchestration of ticks, email/chat dispatch, persona markdown storage.
- `gateways.py`: HTTP client adapters for talking to email/chat services.
- `schemas.py`: request/response models for the Simulation API.

### Virtual Workers (`src/virtualoffice/virtualWorkers`)
- `worker.py`: markdown persona builder (`WorkerPersona`, `ScheduleBlock`, `build_worker_markdown`) and `VirtualWorker` helper that can form chat prompts.

### Common Utilities
- `src/virtualoffice/common/db.py`: SQLite connection helpers used by all services.
- `src/virtualoffice/utils/completion_util.py`: OpenAI client wrapper (optional dependency).

### Tests (`tests/`)
- `test_email_server.py`, `test_chat_server.py`: exercise REST endpoints with ASGI testclients.
- `test_sim_manager.py`: spins up in-memory email/chat services and validates simulation API flows.
- `test_virtual_worker.py`: ensures persona markdown builder formatting.

## Typical Dev Loop
1. Activate `.venv` and install deps (`pip install -r requirements.txt`).
2. `python -m pytest` for regression suite.
3. Launch GUI via `briefcase dev`, start services individually, and drive sim from the dashboard.

## Notable Configuration / Env Vars
- `VDOS_EMAIL_HOST`, `VDOS_EMAIL_PORT`, `VDOS_CHAT_HOST`, `VDOS_CHAT_PORT`: service endpoints used by GUI and simulation manager.
- `VDOS_SIM_HOST`, `VDOS_SIM_PORT`, `VDOS_SIM_BASE_URL`: simulation API endpoint.
- `VDOS_DB_PATH`: overrides SQLite location (defaults to `src/virtualoffice/vdos.db`).
- `.env` (LOCAL ONLY): stores `OPENAI_API_KEY` for `completion_util`.

## Next Steps / Ideas
- Replace FastAPI `@app.on_event` hooks with lifespan handlers to remove deprecation warnings.
- Extend PySide dashboard with persona CRUD and live metrics.
- Add more detailed simulation logic (tick policies, event reactions) inside `SimulationEngine`.
- Package services separately for production (disable GUI auto start, provide CLI scripts).
#