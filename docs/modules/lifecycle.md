# SimulationLifecycle

Location: `src/virtualoffice/sim_manager/core/lifecycle.py`

Orchestrates simulation lifecycle operations.

Responsibilities
- Start: seed RNG, reset runtime/overrides, resolve active people, initialize projects, mark running, set base datetime, schedule kickoff comms
- Stop: stop auto-tick, optional end-of-run report, clear running and active IDs
- Auto-ticks: start/stop with `TickManager` and callbacks
- Reset: clear simulation artifacts while preserving personas
- Reset full: destructive cleanup across email/chat/sim tables
- Auto‑pause: track enabled flag and compute status/reason

Collaborators
- `SimulationState`, `TickManager`, `CommunicationHub`, `WorkerRuntimeManager`, `ProjectManager`, `EventSystem`, gateways
- Engine provides callbacks to list people, set/get active IDs, initialize project plans, and select collaborators

Key Methods
- `start(request) -> SimulationState`
- `stop(generate_report_fn, get_project_plan_fn) -> SimulationState`
- `start_auto_ticks(advance_callback, get_active_projects_callback, archive_chat_room_callback, auto_pause_enabled) -> SimulationState`
- `stop_auto_ticks() -> SimulationState`
- `set_tick_interval(seconds) -> dict`
- `get_tick_interval() -> float`
- `reset() -> SimulationState`
- `reset_full() -> SimulationState`
- `set_auto_pause(enabled) -> dict`
- `get_auto_pause_status() -> dict`

