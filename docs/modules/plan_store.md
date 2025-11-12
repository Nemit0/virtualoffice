# PlanStore

Location: `src/virtualoffice/sim_manager/core/plan_store.py`

Database access layer for worker plan persistence.

Responsibilities
- Insert and fetch `worker_plans` (daily/hourly)
- List plans with optional type/limit filters
- List hourly plans in a tick range (for hourly summaries)

Key Methods
- `put_worker_plan(person_id, tick, plan_type, result, context) -> dict`
- `get_worker_plan(person_id, plan_type, tick=None, exact_tick=False) -> dict | None`
- `list_worker_plans(person_id, plan_type=None, limit=None) -> list[dict]`
- `list_hourly_plans_in_range(person_id, start_tick, end_tick) -> list[dict]`

