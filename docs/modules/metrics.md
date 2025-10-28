# MetricsRecorder

Location: `src/virtualoffice/sim_manager/core/metrics.py`

Thread-safe bounded recorder for planner metrics.

Responsibilities
- Append metrics entries from planner invocations
- Expose recent N entries for UI/API consumption

API
- `MetricsRecorder(maxlen: int = 200)`
- `append(entry: dict) -> None`
- `list(limit: int | None = None) -> list[dict]`

Used By
- `PlannerService` to record success/fallback/error events with durations and model names
- `SimulationEngine.get_planner_metrics()` to expose recent entries

