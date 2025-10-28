from __future__ import annotations

from typing import Any, List

from virtualoffice.common.db import get_connection
from ..planner import PlanResult


class PlanStore:
    """Persistence for worker plans (daily/hourly)."""

    def put_worker_plan(
        self, person_id: int, tick: int, plan_type: str, result: PlanResult, context: str | None
    ) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO worker_plans(person_id, tick, plan_type, content, model_used, tokens_used, context) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    person_id,
                    tick,
                    plan_type,
                    result.content,
                    result.model_used,
                    result.tokens_used,
                    context,
                ),
            )
            row = conn.execute("SELECT * FROM worker_plans WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_worker_plan(row)

    def get_worker_plan(
        self, person_id: int, plan_type: str, tick: int | None = None, exact_tick: bool = False
    ) -> dict[str, Any] | None:
        query = "SELECT * FROM worker_plans WHERE person_id = ? AND plan_type = ?"
        params: list[Any] = [person_id, plan_type]
        if tick is not None:
            comparator = "=" if exact_tick else "<="
            query += f" AND tick {comparator} ?"
            params.append(tick)
        query += " ORDER BY id DESC LIMIT 1"
        with get_connection() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return self._row_to_worker_plan(row) if row else None

    def list_worker_plans(
        self, person_id: int, plan_type: str | None = None, limit: int | None = None
    ) -> List[dict[str, Any]]:
        query = "SELECT * FROM worker_plans WHERE person_id = ?"
        params: list[Any] = [person_id]
        if plan_type:
            query += " AND plan_type = ?"
            params.append(plan_type)
        query += " ORDER BY id DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_worker_plan(row) for row in rows]

    def list_hourly_plans_in_range(self, person_id: int, start_tick: int, end_tick: int) -> List[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT tick, content FROM worker_plans WHERE person_id = ? AND plan_type = 'hourly' AND tick BETWEEN ? AND ? ORDER BY tick",
                (person_id, start_tick, end_tick),
            ).fetchall()
        return [{"tick": row["tick"], "content": row["content"]} for row in rows]

    # --- Internal helpers ---
    def _row_to_worker_plan(self, row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "person_id": row["person_id"],
            "tick": row["tick"],
            "plan_type": row["plan_type"],
            "content": row["content"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "context": row["context"],
            "created_at": row["created_at"],
        }

