# ReportStore

Location: `src/virtualoffice/sim_manager/core/report_store.py`

Database access layer for reports and summaries.

Responsibilities
- Persist and fetch daily reports
- Persist and fetch hourly summaries
- Persist and list simulation reports
- Aggregate token usage across tables

Key Methods
- `put_daily_report(person_id, day_index, schedule_outline, result) -> dict`
- `get_daily_report(person_id, day_index) -> dict | None`
- `list_daily_reports(person_id, day_index=None, limit=None) -> list[dict]`
- `put_hourly_summary(person_id, hour_index, result) -> dict`
- `get_hourly_summary(person_id, hour_index) -> dict | None`
- `put_simulation_report(total_ticks, result) -> dict`
- `list_simulation_reports(limit=None) -> list[dict]`
- `get_token_usage() -> dict[str, int]`

