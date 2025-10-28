# PlannerService

Location: `src/virtualoffice/sim_manager/core/planner_service.py`

PlannerService centralizes planner invocations, strict/fallback behavior, and metrics collection.

Responsibilities
- Invoke concrete planner methods (e.g., `generate_project_plan`, `generate_daily_plan`)
- Apply strict mode (raise on failure) or fallback to `StubPlanner`
- Record per-call metrics (method, planner, durations, model, fallback/error)

Key Types
- `PlannerService(planner, stub_planner, strict, metrics)`
- `call(method_name: str, **kwargs) -> PlanResult`
- `get_metrics(limit: int = 50) -> list[dict]`

Usage
- Wired by `SimulationEngine` during initialization
- Used by `PlanningOrchestrator` for all non-VirtualWorker planning paths

