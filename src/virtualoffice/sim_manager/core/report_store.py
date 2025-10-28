from __future__ import annotations

from typing import Any, List

from virtualoffice.common.db import get_connection
from ..planner import PlanResult


class ReportStore:
    """Persistence for daily/hourly summaries and simulation reports.

    Also provides aggregate utility queries (e.g., token usage).
    """

    # Daily reports -----------------------------------------------------
    def put_daily_report(
        self, person_id: int, day_index: int, schedule_outline: str, result: PlanResult
    ) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO daily_reports(person_id, day_index, report, schedule_outline, model_used, tokens_used) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    person_id,
                    day_index,
                    result.content,
                    schedule_outline,
                    result.model_used,
                    result.tokens_used,
                ),
            )
            row = conn.execute("SELECT * FROM daily_reports WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_daily_report(row)

    def get_daily_report(self, person_id: int, day_index: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE person_id = ? AND day_index = ? ORDER BY id DESC LIMIT 1",
                (person_id, day_index),
            ).fetchone()
        return self._row_to_daily_report(row) if row else None

    def list_daily_reports(
        self, person_id: int, day_index: int | None = None, limit: int | None = None
    ) -> List[dict[str, Any]]:
        query = "SELECT * FROM daily_reports WHERE person_id = ?"
        params: list[Any] = [person_id]
        if day_index is not None:
            query += " AND day_index = ?"
            params.append(day_index)
        query += " ORDER BY id DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_daily_report(row) for row in rows]

    # Hourly summaries --------------------------------------------------
    def put_hourly_summary(self, person_id: int, hour_index: int, result: PlanResult) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT OR REPLACE INTO hourly_summaries(person_id, hour_index, summary, model_used, tokens_used) "
                "VALUES (?, ?, ?, ?, ?)",
                (person_id, hour_index, result.content, result.model_used, result.tokens_used or 0),
            )
            row_id = cursor.lastrowid
        return {
            "id": row_id,
            "person_id": person_id,
            "hour_index": hour_index,
            "summary": result.content,
            "model_used": result.model_used,
            "tokens_used": result.tokens_used or 0,
        }

    def get_hourly_summary(self, person_id: int, hour_index: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM hourly_summaries WHERE person_id = ? AND hour_index = ?",
                (person_id, hour_index),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "person_id": row["person_id"],
            "hour_index": row["hour_index"],
            "summary": row["summary"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
        }

    # Simulation reports -----------------------------------------------
    def put_simulation_report(self, total_ticks: int, result: PlanResult) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO simulation_reports(report, model_used, tokens_used, total_ticks) VALUES (?, ?, ?, ?)",
                (
                    result.content,
                    result.model_used,
                    result.tokens_used,
                    total_ticks,
                ),
            )
            row = conn.execute("SELECT * FROM simulation_reports WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_simulation_report(row)

    def list_simulation_reports(self, limit: int | None = None) -> List[dict[str, Any]]:
        query = "SELECT * FROM simulation_reports ORDER BY id DESC"
        params: list[Any] = []
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_simulation_report(row) for row in rows]

    # Aggregates --------------------------------------------------------
    def list_daily_reports_for_summary(self) -> str:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT person_id, day_index, report FROM daily_reports ORDER BY person_id, day_index"
            ).fetchall()
        if not rows:
            return "No daily reports were generated."
        parts = []
        for row in rows:
            parts.append(f"Person {row['person_id']} Day {row['day_index']}: {row['report']}")
        return "\n".join(parts)

    def get_token_usage(self) -> dict[str, int]:
        usage: dict[str, int] = {}
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens FROM project_plans
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens FROM worker_plans
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens FROM daily_reports
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens FROM simulation_reports
                """
            ).fetchall()
        for row in rows:
            model = row["model_used"]
            tokens = row["tokens"] or 0
            usage[model] = usage.get(model, 0) + int(tokens)
        return usage

    # --- Internal helpers ---
    def _row_to_daily_report(self, row) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "person_id": row["person_id"],
            "day_index": row["day_index"],
            "report": row["report"],
            "schedule_outline": row["schedule_outline"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "created_at": row["created_at"],
        }

    def _row_to_simulation_report(self, row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "report": row["report"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "total_ticks": row["total_ticks"],
            "created_at": row["created_at"],
        }

