# Repository Guidelines

## Project Overview
Virtual Department Operations Simulator (VDOS) is a headless-first sandbox that generates realistic departmental comms (email + chat) and agent behaviour so downstream systems (dashboards, analytics, AI assistants) can iterate without exposing production data.

## Current High-Level Architecture
- **Server Launcher** (`src/virtualoffice/app.py`): lightweight launcher that automatically starts Chat, Email, and Simulation servers sequentially when running `briefcase dev`.
- **Web Dashboard** (`src/virtualoffice/sim_manager/index_new.html` + `static/`): browser-based UI for managing personas, configuring multi-project simulations, and monitoring simulation state.
- **FastAPI services** (`src/virtualoffice/servers`): REST backends for email and chat communication.
- **Simulation manager** (`src/virtualoffice/sim_manager`): orchestrates ticks, persists people/events, and calls the comms services.
- **Virtual workers** (`src/virtualoffice/virtualWorkers`): persona templates + helpers for hourly planning prompts.
- **Common utilities** (`src/virtualoffice/common` & `src/virtualoffice/utils`): database access, OpenAI helper.
- **Tests** (`tests/`): pytest suite covering email/chat servers, simulation control loop, and worker markdown.

## Modules & Responsibilities

### Server Launcher (`src/virtualoffice/app.py`)
- Automatically starts all three FastAPI servers (Chat, Email, Simulation) in background threads when running `briefcase dev`.
- Servers start sequentially to ensure proper initialization order.
- Opens the web dashboard in the default browser automatically.
- Configurable via environment variables in `.env`:
  - `VDOS_CHAT_HOST`, `VDOS_CHAT_PORT` (default: 127.0.0.1:8001)
  - `VDOS_EMAIL_HOST`, `VDOS_EMAIL_PORT` (default: 127.0.0.1:8000)
  - `VDOS_SIM_HOST`, `VDOS_SIM_PORT` (default: 127.0.0.1:8015)
- Monitors server health and keeps the application running.

### Web Dashboard (`src/virtualoffice/sim_manager/`)
- **index_new.html**: Main dashboard interface with persona management, multi-project configuration, and simulation controls.
- **static/js/dashboard.js**: Client-side logic for:
  - Real-time simulation state monitoring with adaptive refresh (60s when stopped, 5s when running)
  - Persona creation with optional GPT-4o auto-generation
  - Multi-project configuration: add/remove projects, assign teams, set timelines
  - Team management: personas can be organized into teams with `team_name` field
  - Simulation controls: start/stop, advance ticks, reset, auto-tick toggle
  - Token usage and planner metrics visualization
- **static/css/styles.css**: Dashboard styling including project card layouts.
- Fully replaces the previous PySide6 GUI - all simulation operations now performed via web interface.

### Email Server (`src/virtualoffice/servers/email`)
- `app.py`: FastAPI app exposing `/emails/send`, `/mailboxes/{address}/emails`, `/mailboxes/{address}/drafts`, etc.
- `models.py`: Pydantic models for payloads (`EmailSend`, `DraftCreate`, `Mailbox`).
- Persists to SQLite via `virtualoffice.common.db`. Automatically provisions mailboxes when needed.

### Chat Server (`src/virtualoffice/servers/chat`)
- `app.py`: FastAPI service for rooms, messages, and DMs (auto-creates users/rooms as needed).
- `models.py`: Pydantic models for chat entities.
- Stores memberships and messages in SQLite, paralleling the email server’s structure.

### Simulation Manager (`src/virtualoffice/sim_manager`)
- `app.py`: FastAPI API (start/stop/advance, CRUD people, event injection) with support for:
  - Multi-project simulations with different teams and timelines
  - Include/exclude persona filters
  - Reproducible random seeds
  - Model hints for LLM selection
- `engine.py`: SQLite-backed orchestration of ticks, email/chat dispatch, persona markdown storage, auto-tick loop management, and runtime persistence (exchange logs, inbox queue, status overrides, events).
- `gateways.py`: HTTP client adapters for talking to email/chat services.
- `schemas.py`: request/response models for the Simulation API, including worker filtering fields and multi-project configuration.

### Virtual Workers (`src/virtualoffice/virtualWorkers`)
- `worker.py`: markdown persona builder (`WorkerPersona`, `ScheduleBlock`, `build_worker_markdown`) and `VirtualWorker` helper that can form chat prompts.

### Common Utilities
- `src/virtualoffice/common/db.py`: SQLite connection helpers used by all services.
- `src/virtualoffice/utils/completion_util.py`: OpenAI client wrapper (optional dependency).

### Tests (`tests/`)
- `test_email_server.py`, `test_chat_server.py`: exercise REST endpoints with ASGI testclients.
- `test_sim_manager.py`: spins up in-memory email/chat services, exercises auto-ticking, event persistence, worker filtering, and writes rich run artifacts to `output/`.
- `test_virtual_worker.py`: ensures persona markdown builder formatting.

## Typical Dev Loop
1. Activate `.venv` and install deps (`pip install -r requirements.txt`).
2. `python -m pytest` for regression suite.
3. Run `briefcase dev` to automatically start all servers and open the web dashboard.
4. Configure personas and multi-project simulations via the web interface.
5. Use Python scripts in `scripts/` directory for programmatic multi-team simulations (Korean locale examples available).

## Notable Configuration / Env Vars
Server ports and hosts are configurable via `.env` (defaults shown):
- `VDOS_CHAT_HOST=127.0.0.1`, `VDOS_CHAT_PORT=8001`: Chat server endpoint
- `VDOS_EMAIL_HOST=127.0.0.1`, `VDOS_EMAIL_PORT=8000`: Email server endpoint
- `VDOS_SIM_HOST=127.0.0.1`, `VDOS_SIM_PORT=8015`: Simulation API endpoint
- `VDOS_DB_PATH`: overrides SQLite location (defaults to `src/virtualoffice/vdos.db`)

API configuration:
- `OPENAI_API_KEY`: Primary OpenAI API key for LLM calls
- `OPENAI_API_KEY2`: Secondary OpenAI key (fallback)
- `OPENROUTER_API_KEY`: OpenRouter API key
- `VDOS_USE_OPENROUTER`: Set to `true` to use OpenRouter instead of OpenAI
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_AREA`: Azure OpenAI configuration

See `.env.template` for all available configuration options.

## API Key Configuration
**CURRENT ACTIVE API KEY: OpenAI API Key 1 ONLY**

### Rules:
- ALWAYS use **OpenAI API Key 1** for all simulations unless explicitly told otherwise
- Azure keys and OpenAI Key 2 are disabled per company policy
- DO NOT use fallback keys without explicit user permission
- If a different key is needed, user will update this section
- When running simulations, verify this section first to confirm which API key to use

### How to Change:
To use a different API key, update the "CURRENT ACTIVE API KEY" line above with:
- `OpenAI API Key 1` - Primary key (default)
- `OpenAI API Key 2` - Secondary key (requires user approval)
- `Azure OpenAI` - Azure endpoint (requires user approval)
- `Custom: <description>` - Other configuration


## Custom Instructions

### Error Output
For any error output that can only be read from the gui, read the output from logs/error_output.txt

### Agent Reports
When creating markdown reports or documentation files during development sessions:
- NEVER create these files in the project root directory
- ALWAYS save reports to the `agent_reports/` directory
- ALWAYS prefix filenames with a timestamp in the format: `YYYYMMDD_HHMMSS_`
- Example: `20251020_094530_EMAIL_VALIDATION_FIXES.md`
- This helps track when reports were created and maintains chronological order

### Project Task Tracking
- All project TODOs and tasks are tracked in `todo.md` at the project root
- When starting a new task, check `todo.md` for context and priorities
- When completing a task, update `todo.md` to mark it as complete with date
- Add new discovered tasks or future enhancements to `todo.md`
- Keep the file organized by priority (High/Medium/Low) and category
- During active work sessions, use the TodoWrite tool for real-time tracking, then consolidate to `todo.md` when done

### Temporary Files and Output Management
- NEVER create temporary files in the project root
- ALWAYS use the `.tmp/` directory for temporary outputs, test logs, and intermediate files
- Common temporary files to avoid in root:
  - Simulation output logs (use `.tmp/` or `simulation_output/`)
  - Terminal output captures (redirect to `.tmp/`)
  - Test artifacts (store in `.tmp/`)
  - Temporary scripts (use `.tmp/` if needed, or `scripts/` if permanent)
- Clean up `.tmp/` directory periodically or at end of session
- The `.tmp/` directory is gitignored - safe for temporary work

### Git Commit Guidelines
- ALWAYS commit changes after completing a significant feature or fix
- Use clear, descriptive commit messages following conventional commit format:
  - `feat: description` - New features
  - `fix: description` - Bug fixes
  - `refactor: description` - Code refactoring
  - `perf: description` - Performance improvements
  - `docs: description` - Documentation updates
  - `test: description` - Test additions/updates
  - `chore: description` - Maintenance tasks

- Use `git add` to stage only relevant files (avoid committing temp files, logs, etc.)
- Push to remote only when explicitly requested by user
- Example commit flow:
  1. Stage changes: `git add <specific files>`
  2. Commit with message: `git commit -m "$(cat <<'EOF' ...)"`
  3. Verify with `git status`
  4. Push only if user requests: `git push`