# PlanningOrchestrator

Location: `src/virtualoffice/sim_manager/core/planning_orchestrator.py`

Coordinates daily/hourly planning and reporting across workers.

Responsibilities
- Generate daily plans and persist them
- Generate hourly plans (sequential/parallel) and persist them
- Append live-collaboration adjustments to hourly plans
- Generate hourly summaries at hour boundaries
- Generate daily reports at day boundaries

Dependencies
- `PlannerService` for planner calls and metrics
- `WorkerRegistry` for VirtualWorker delegation when available
- `CommunicationHub` to fetch recent emails for threading context
- `PlanStore` and `ReportStore` for persistence

Key Methods
- `ensure_daily_plan(person, day_index, project_plan, duration_weeks, team, model_hint) -> str`
- `generate_daily_plan(...) -> PlanResult`
- `generate_hourly_plan(...) -> PlanResult`
- `generate_hourly_plans_parallel(planning_tasks, executor, ...) -> list[(PersonRead, PlanResult)]`
- `generate_hourly_summary(person, hour_index, model_hint) -> dict`
- `generate_daily_report(person, day_index, project_plan, daily_plan_text, model_hint) -> dict`

