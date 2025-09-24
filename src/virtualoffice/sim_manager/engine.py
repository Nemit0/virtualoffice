from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence

from virtualoffice.common.db import execute_script, get_connection
from virtualoffice.virtualWorkers.worker import (
    ScheduleBlock,
    WorkerPersona,
    build_worker_markdown,
    render_minute_schedule,
)

from .gateways import ChatGateway, EmailGateway
from .planner import GPTPlanner, PlanResult, Planner, PlanningError
from .schemas import (
    EventCreate,
    PersonCreate,
    PersonRead,
    ScheduleBlockIn,
    SimulationAdvanceResult,
    SimulationStartRequest,
    SimulationState,
)

SIM_SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    timezone TEXT NOT NULL,
    work_hours TEXT NOT NULL,
    break_frequency TEXT NOT NULL,
    communication_style TEXT NOT NULL,
    email_address TEXT NOT NULL,
    chat_handle TEXT NOT NULL,
    is_department_head INTEGER NOT NULL DEFAULT 0,
    skills TEXT NOT NULL,
    personality TEXT NOT NULL,
    objectives TEXT NOT NULL,
    metrics TEXT NOT NULL,
    persona_markdown TEXT NOT NULL,
    planning_guidelines TEXT NOT NULL,
    event_playbook TEXT NOT NULL,
    statuses TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schedule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    activity TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS simulation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_tick INTEGER NOT NULL,
    is_running INTEGER NOT NULL,
    auto_tick INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tick_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    target_ids TEXT NOT NULL,
    project_id TEXT,
    at_tick INTEGER,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS project_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    project_summary TEXT NOT NULL,
    plan TEXT NOT NULL,
    generated_by INTEGER,
    duration_weeks INTEGER NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(generated_by) REFERENCES people(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS worker_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    plan_type TEXT NOT NULL,
    content TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    context TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    day_index INTEGER NOT NULL,
    report TEXT NOT NULL,
    schedule_outline TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS simulation_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    total_ticks INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

"""


@dataclass
class SimulationStatus:
    current_tick: int
    is_running: bool
    auto_tick: bool


class SimulationEngine:
    def __init__(
        self,
        email_gateway: EmailGateway,
        chat_gateway: ChatGateway,
        sim_manager_email: str = "simulator@vdos.local",
        sim_manager_handle: str = "sim-manager",
        planner: Planner | None = None,
        hours_per_day: int = 8,
    ) -> None:
        self.email_gateway = email_gateway
        self.chat_gateway = chat_gateway
        self.sim_manager_email = sim_manager_email
        self.sim_manager_handle = sim_manager_handle
        self.planner = planner or GPTPlanner()
        self.hours_per_day = hours_per_day
        self.project_duration_weeks = 4
        self._project_plan_cache: dict[str, Any] | None = None
        self._planner_model_hint: str | None = None
        execute_script(SIM_SCHEMA)
        self._apply_migrations()
        self._ensure_state_row()
        self._bootstrap_channels()

    def _apply_migrations(self) -> None:
        with get_connection() as conn:
            people_columns = {row["name"] for row in conn.execute("PRAGMA table_info(people)")}
            if "is_department_head" not in people_columns:
                conn.execute("ALTER TABLE people ADD COLUMN is_department_head INTEGER NOT NULL DEFAULT 0")
            state_columns = {row["name"] for row in conn.execute("PRAGMA table_info(simulation_state)")}
            if "auto_tick" not in state_columns:
                conn.execute("ALTER TABLE simulation_state ADD COLUMN auto_tick INTEGER NOT NULL DEFAULT 0")

    # ------------------------------------------------------------------
    # People management
    # ------------------------------------------------------------------
    def create_person(self, payload: PersonCreate) -> PersonRead:
        persona = self._to_persona(payload)
        schedule = [
            ScheduleBlock(block.start, block.end, block.activity)
            for block in payload.schedule or []
        ]
        persona_markdown = build_worker_markdown(
            persona,
            schedule=schedule,
            planning_guidelines=payload.planning_guidelines,
            event_playbook=payload.event_playbook,
            statuses=payload.statuses,
        )

        skills_json = json.dumps(list(payload.skills))
        personality_json = json.dumps(list(payload.personality))
        objectives_json = json.dumps(list(payload.objectives or []))
        metrics_json = json.dumps(list(payload.metrics or []))
        planning_json = json.dumps(list(payload.planning_guidelines or []))
        playbook_json = json.dumps(payload.event_playbook or {})
        statuses_json = json.dumps(list(payload.statuses or []))

        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO people (
                    name, role, timezone, work_hours, break_frequency,
                    communication_style, email_address, chat_handle, is_department_head, skills,
                    personality, objectives, metrics, persona_markdown,
                    planning_guidelines, event_playbook, statuses
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name,
                    payload.role,
                    payload.timezone,
                    payload.work_hours,
                    payload.break_frequency,
                    payload.communication_style,
                    payload.email_address,
                    payload.chat_handle,
                    1 if payload.is_department_head else 0,
                    skills_json,
                    personality_json,
                    objectives_json,
                    metrics_json,
                    persona_markdown,
                    planning_json,
                    playbook_json,
                    statuses_json,
                ),
            )
            person_id = cursor.lastrowid
            if schedule:
                conn.executemany(
                    "INSERT INTO schedule_blocks(person_id, start, end, activity) VALUES (?, ?, ?, ?)",
                    [(person_id, block.start, block.end, block.activity) for block in schedule],
                )

        self.email_gateway.ensure_mailbox(payload.email_address, payload.name)
        self.chat_gateway.ensure_user(payload.chat_handle, payload.name)

        return self.get_person(person_id)

    def list_people(self) -> List[PersonRead]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM people ORDER BY id"
            ).fetchall()
        return [self._row_to_person(row) for row in rows]

    def get_person(self, person_id: int) -> PersonRead:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
        if not row:
            raise ValueError("Person not found")
        return self._row_to_person(row)

    def delete_person_by_name(self, name: str) -> bool:
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM people WHERE name = ?", (name,)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM people WHERE id = ?", (row["id"],))
        return True

    # ------------------------------------------------------------------
    # Planning lifecycle
    # ------------------------------------------------------------------
    def get_project_plan(self) -> dict[str, Any] | None:
        if self._project_plan_cache is not None:
            return self._project_plan_cache.copy()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_plans ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        plan = self._row_to_project_plan(row)
        self._project_plan_cache = plan
        self.project_duration_weeks = plan["duration_weeks"]
        return plan

    def list_worker_plans(
        self,
        person_id: int,
        plan_type: str | None = None,
        limit: int | None = None,
    ) -> List[dict[str, Any]]:
        self.get_person(person_id)
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

    def list_daily_reports(
        self,
        person_id: int,
        day_index: int | None = None,
        limit: int | None = None,
    ) -> List[dict[str, Any]]:
        self.get_person(person_id)
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

    def list_simulation_reports(self, limit: int | None = None) -> List[dict[str, Any]]:
        query = "SELECT * FROM simulation_reports ORDER BY id DESC"
        params: list[Any] = []
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_simulation_report(row) for row in rows]

    def _initialise_project_plan(self, request: SimulationStartRequest) -> None:
        people = self.list_people()
        if not people:
            raise RuntimeError("Cannot initialise project plan without any personas")
        department_head = self._resolve_department_head(people, request.department_head_name)
        try:
            plan_result = self.planner.generate_project_plan(
                department_head=department_head,
                project_name=request.project_name,
                project_summary=request.project_summary,
                duration_weeks=request.duration_weeks,
                team=people,
                model_hint=request.model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate project plan: {exc}") from exc
        plan_record = self._store_project_plan(
            project_name=request.project_name,
            project_summary=request.project_summary,
            plan_result=plan_result,
            generated_by=department_head.id if department_head else None,
            duration_weeks=request.duration_weeks,
        )
        for person in people:
            daily_result = self._generate_daily_plan(person, plan_record, day_index=0)
            self._generate_hourly_plan(
                person,
                plan_record,
                daily_result.content,
                tick=0,
                reason="initialisation",
            )

    def _resolve_department_head(
        self, people: Sequence[PersonRead], requested_name: str | None
    ) -> PersonRead:
        if requested_name:
            for person in people:
                if person.name == requested_name:
                    return person
        for person in people:
            if getattr(person, "is_department_head", False):
                return person
        raise RuntimeError(
            "No department head defined. Mark a persona with is_department_head=True or pass department_head_name."
        )

    def _store_project_plan(
        self,
        project_name: str,
        project_summary: str,
        plan_result: PlanResult,
        generated_by: int | None,
        duration_weeks: int,
    ) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO project_plans(project_name, project_summary, plan, generated_by, duration_weeks, model_used, tokens_used) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_name,
                    project_summary,
                    plan_result.content,
                    generated_by,
                    duration_weeks,
                    plan_result.model_used,
                    plan_result.tokens_used,
                ),
            )
            row = conn.execute(
                "SELECT * FROM project_plans WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        plan = self._row_to_project_plan(row)
        self._project_plan_cache = plan
        self.project_duration_weeks = duration_weeks
        return plan

    def _row_to_project_plan(self, row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_name": row["project_name"],
            "project_summary": row["project_summary"],
            "plan": row["plan"],
            "generated_by": row["generated_by"],
            "duration_weeks": row["duration_weeks"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "created_at": row["created_at"],
        }

    def _generate_daily_plan(
        self, person: PersonRead, project_plan: dict[str, Any], day_index: int
    ) -> PlanResult:
        try:
            result = self.planner.generate_daily_plan(
                worker=person,
                project_plan=project_plan["plan"],
                day_index=day_index,
                duration_weeks=self.project_duration_weeks,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate daily plan for {person.name}: {exc}") from exc
        self._store_worker_plan(
            person_id=person.id,
            tick=day_index,
            plan_type="daily",
            result=result,
            context=f"day_index={day_index}",
        )
        return result

    def _generate_hourly_plan(
        self,
        person: PersonRead,
        project_plan: dict[str, Any],
        daily_plan_text: str,
        tick: int,
        reason: str,
    ) -> PlanResult:
        try:
            result = self.planner.generate_hourly_plan(
                worker=person,
                project_plan=project_plan["plan"],
                daily_plan=daily_plan_text,
                tick=tick,
                context_reason=reason,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate hourly plan for {person.name}: {exc}") from exc
        self._store_worker_plan(
            person_id=person.id,
            tick=tick,
            plan_type="hourly",
            result=result,
            context=f"reason={reason}",
        )
        return result

    def _store_worker_plan(
        self,
        person_id: int,
        tick: int,
        plan_type: str,
        result: PlanResult,
        context: str | None,
    ) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO worker_plans(person_id, tick, plan_type, content, model_used, tokens_used, context) VALUES (?, ?, ?, ?, ?, ?, ?)",
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
            row = conn.execute(
                "SELECT * FROM worker_plans WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return self._row_to_worker_plan(row)

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

    def _fetch_worker_plan(
        self,
        person_id: int,
        plan_type: str,
        tick: int | None = None,
        exact_tick: bool = False,
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

    def _ensure_daily_plan(
        self, person: PersonRead, day_index: int, project_plan: dict[str, Any]
    ) -> str:
        existing = self._fetch_worker_plan(
            person.id, "daily", tick=day_index, exact_tick=True
        )
        if existing:
            return existing["content"]
        result = self._generate_daily_plan(person, project_plan, day_index)
        return result.content

    def _summarise_plan(self, plan_text: str, max_lines: int = 4) -> str:
        lines = [line.strip() for line in plan_text.splitlines() if line.strip()]
        if not lines:
            return "No plan provided yet."
        return "\n".join(lines[:max_lines])

    def _fetch_daily_report(self, person_id: int, day_index: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE person_id = ? AND day_index = ? ORDER BY id DESC LIMIT 1",
                (person_id, day_index),
            ).fetchone()
        return self._row_to_daily_report(row) if row else None

    def _generate_daily_report(
        self,
        person: PersonRead,
        day_index: int,
        project_plan: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self._fetch_daily_report(person.id, day_index)
        if existing:
            return existing
        daily_plan_text = self._ensure_daily_plan(person, day_index, project_plan)
        start_tick = day_index * self.hours_per_day + 1
        end_tick = (day_index + 1) * self.hours_per_day
        with get_connection() as conn:
            hourly_rows = conn.execute(
                "SELECT tick, content FROM worker_plans WHERE person_id = ? AND plan_type = 'hourly' AND tick BETWEEN ? AND ? ORDER BY tick",
                (person.id, start_tick, end_tick),
            ).fetchall()
        hourly_summary = "\n".join(f"Tick {row['tick']}: {row['content']}" for row in hourly_rows)
        schedule_blocks = [
            ScheduleBlock(block.start, block.end, block.activity)
            for block in person.schedule or []
        ]
        minute_schedule = render_minute_schedule(schedule_blocks)
        try:
            result = self.planner.generate_daily_report(
                worker=person,
                project_plan=project_plan["plan"],
                day_index=day_index,
                daily_plan=daily_plan_text,
                hourly_log=hourly_summary,
                minute_schedule=minute_schedule,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate daily report for {person.name}: {exc}") from exc
        return self._store_daily_report(
            person_id=person.id,
            day_index=day_index,
            schedule_outline=minute_schedule,
            result=result,
        )

    def _store_daily_report(
        self,
        person_id: int,
        day_index: int,
        schedule_outline: str,
        result: PlanResult,
    ) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO daily_reports(person_id, day_index, report, schedule_outline, model_used, tokens_used) VALUES (?, ?, ?, ?, ?, ?)",
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

    def _generate_simulation_report(self, project_plan: dict[str, Any], total_ticks: int) -> dict[str, Any]:
        if not project_plan:
            raise RuntimeError("Cannot generate simulation report without a project plan")
        people = self.list_people()
        with get_connection() as conn:
            tick_rows = conn.execute("SELECT tick, reason FROM tick_log ORDER BY id").fetchall()
            event_rows = conn.execute("SELECT type, target_ids, project_id, at_tick, payload FROM events ORDER BY id").fetchall()
        tick_summary = "\n".join(f"Tick {row['tick']}: {row['reason']}" for row in tick_rows)
        event_summary = "\n".join(
            f"Event {row['type']} (project={row['project_id']}, targets={row['target_ids']}, tick={row['at_tick']}) payload={row['payload']}"
            for row in event_rows
        ) or "No events logged."
        daily_reports = self.list_daily_reports_for_summary()
        try:
            result = self.planner.generate_simulation_report(
                project_plan=project_plan["plan"],
                team=people,
                total_ticks=total_ticks,
                tick_log=tick_summary,
                daily_reports=daily_reports,
                event_summary=event_summary,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate simulation report: {exc}") from exc
        return self._store_simulation_report(
            total_ticks=total_ticks,
            result=result,
        )

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

    def _store_simulation_report(self, total_ticks: int, result: PlanResult) -> dict[str, Any]:
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

    def _row_to_simulation_report(self, row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "report": row["report"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "total_ticks": row["total_ticks"],
            "created_at": row["created_at"],
        }

    def get_token_usage(self) -> dict[str, int]:
        usage: dict[str, int] = {}
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens
                FROM project_plans
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens
                FROM worker_plans
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens
                FROM daily_reports
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens
                FROM simulation_reports
                """
            ).fetchall()
        for row in rows:
            model = row["model_used"]
            tokens = row["tokens"] or 0
            usage[model] = usage.get(model, 0) + int(tokens)
        return usage

    # ------------------------------------------------------------------
    # Simulation control
    # ------------------------------------------------------------------
    def get_state(self) -> SimulationState:
        status = self._fetch_state()
        return SimulationState(current_tick=status.current_tick, is_running=status.is_running, auto_tick=status.auto_tick)

    def start(self, request: SimulationStartRequest | None = None) -> SimulationState:
        if request is not None:
            self.project_duration_weeks = request.duration_weeks
            self._planner_model_hint = request.model_hint
            self._initialise_project_plan(request)
        self._set_running(True)
        status = self._fetch_state()
        return SimulationState(current_tick=status.current_tick, is_running=status.is_running, auto_tick=status.auto_tick)

    def stop(self) -> SimulationState:
        status = self._fetch_state()
        if status.is_running:
            project_plan = self.get_project_plan()
            if project_plan is not None:
                self._generate_simulation_report(project_plan, total_ticks=status.current_tick)
        self._set_running(False)
        status = self._fetch_state()
        return SimulationState(current_tick=status.current_tick, is_running=status.is_running, auto_tick=status.auto_tick)

    def start_auto_ticks(self) -> SimulationState:
        self._set_auto_tick(True)
        status = self._fetch_state()
        return SimulationState(current_tick=status.current_tick, is_running=status.is_running, auto_tick=status.auto_tick)

    def stop_auto_ticks(self) -> SimulationState:
        self._set_auto_tick(False)
        status = self._fetch_state()
        return SimulationState(current_tick=status.current_tick, is_running=status.is_running, auto_tick=status.auto_tick)

    def advance(self, ticks: int, reason: str) -> SimulationAdvanceResult:
        status = self._fetch_state()
        if not status.is_running:
            raise RuntimeError("Simulation is not running; call start first")
        if ticks <= 0:
            raise ValueError("Ticks must be positive")

        project_plan = self.get_project_plan()
        if project_plan is None:
            raise RuntimeError("Project plan is not initialised; start the simulation with project details before advancing.")

        people = self.list_people()
        if not people:
            raise RuntimeError("Cannot advance simulation without registered people")

        emails_sent = 0
        chats_sent = 0

        for _ in range(ticks):
            status.current_tick += 1
            self._update_tick(status.current_tick, reason)
            day_index = (status.current_tick - 1) // self.hours_per_day
            for person in people:
                daily_plan_text = self._ensure_daily_plan(person, day_index, project_plan)
                hourly_result = self._generate_hourly_plan(
                    person,
                    project_plan,
                    daily_plan_text,
                    tick=status.current_tick,
                    reason=reason,
                )
                daily_summary = self._summarise_plan(daily_plan_text, max_lines=3)
                hourly_summary = self._summarise_plan(hourly_result.content)
                subject = f"[Tick {status.current_tick}] {reason.title()} update for {person.name}"
                body = (
                    f"Project: {project_plan['project_name']}\n"
                    f"Daily focus:\n{daily_summary}\n\n"
                    f"Hourly plan:\n{hourly_summary}\n\n"
                    "Finish slightly ahead to absorb surprises."
                )
                self.email_gateway.send_email(
                    sender=self.sim_manager_email,
                    to=[person.email_address],
                    subject=subject,
                    body=body,
                )
                emails_sent += 1

                chat_body = (
                    f"Tick {status.current_tick}: {hourly_summary.replace('\n', ' / ')}\n"
                    "Ping me if you need to reallocate the buffer."
                )
                self.chat_gateway.send_dm(
                    sender=self.sim_manager_handle,
                    recipient=person.chat_handle,
                    body=chat_body,
                )
                chats_sent += 1

            if status.current_tick % self.hours_per_day == 0:
                completed_day = (status.current_tick // self.hours_per_day) - 1
                for person in people:
                    self._generate_daily_report(person, completed_day, project_plan)

        return SimulationAdvanceResult(
            ticks_advanced=ticks,
            current_tick=status.current_tick,
            emails_sent=emails_sent,
            chat_messages_sent=chats_sent,
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def inject_event(self, payload: EventCreate) -> dict:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events(type, target_ids, project_id, at_tick, payload)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    payload.type,
                    json.dumps(list(payload.target_ids)),
                    payload.project_id,
                    payload.at_tick,
                    json.dumps(payload.payload or {}),
                ),
            )
            event_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._row_to_event(row)

    def list_events(self) -> List[dict]:
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
        return [self._row_to_event(row) for row in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _bootstrap_channels(self) -> None:
        self.email_gateway.ensure_mailbox(self.sim_manager_email, "Simulation Manager")
        self.chat_gateway.ensure_user(self.sim_manager_handle, "Simulation Manager")

    def _ensure_state_row(self) -> None:
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM simulation_state WHERE id = 1").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO simulation_state(id, current_tick, is_running, auto_tick) VALUES (1, 0, 0, 0)"
                )

    def _fetch_state(self) -> SimulationStatus:
        with get_connection() as conn:
            row = conn.execute("SELECT current_tick, is_running, auto_tick FROM simulation_state WHERE id = 1").fetchone()
        return SimulationStatus(current_tick=row["current_tick"], is_running=bool(row["is_running"]), auto_tick=bool(row["auto_tick"]))

    def _set_running(self, running: bool) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET is_running = ? WHERE id = 1",
                (1 if running else 0,),
            )

    def _set_auto_tick(self, enabled: bool) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET auto_tick = ? WHERE id = 1",
                (1 if enabled else 0,),
            )

    def _update_tick(self, tick: int, reason: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET current_tick = ? WHERE id = 1",
                (tick,),
            )
            conn.execute(
                "INSERT INTO tick_log(tick, reason) VALUES (?, ?)",
                (tick, reason),
            )

    def _row_to_person(self, row) -> PersonRead:
        person_id = row["id"]
        schedule = self._fetch_schedule(person_id)
        return PersonRead(
            id=person_id,
            name=row["name"],
            role=row["role"],
            timezone=row["timezone"],
            work_hours=row["work_hours"],
            break_frequency=row["break_frequency"],
            communication_style=row["communication_style"],
            email_address=row["email_address"],
            chat_handle=row["chat_handle"],
            is_department_head=bool(row["is_department_head"]),
            skills=json.loads(row["skills"]),
            personality=json.loads(row["personality"]),
            objectives=json.loads(row["objectives"]),
            metrics=json.loads(row["metrics"]),
            schedule=[ScheduleBlockIn(**block) for block in schedule],
            planning_guidelines=json.loads(row["planning_guidelines"]),
            event_playbook=json.loads(row["event_playbook"]),
            statuses=json.loads(row["statuses"]),
            persona_markdown=row["persona_markdown"],
        )

    def _fetch_schedule(self, person_id: int) -> List[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT start, end, activity FROM schedule_blocks WHERE person_id = ? ORDER BY id",
                (person_id,),
            ).fetchall()
        return [
            {"start": row["start"], "end": row["end"], "activity": row["activity"]}
            for row in rows
        ]

    def _row_to_event(self, row) -> dict:
        return {
            "id": row["id"],
            "type": row["type"],
            "target_ids": json.loads(row["target_ids"] or "[]"),
            "project_id": row["project_id"],
            "at_tick": row["at_tick"],
            "payload": json.loads(row["payload"] or "{}"),
        }

    def _to_persona(self, payload: PersonCreate) -> WorkerPersona:
        return WorkerPersona(
            name=payload.name,
            role=payload.role,
            skills=tuple(payload.skills),
            personality=tuple(payload.personality),
            timezone=payload.timezone,
            work_hours=payload.work_hours,
            break_frequency=payload.break_frequency,
            communication_style=payload.communication_style,
            email_address=payload.email_address,
            chat_handle=payload.chat_handle,
            objectives=tuple(payload.objectives or ()),
            metrics=tuple(payload.metrics or ()),
        )

    def close(self) -> None:
        close_email = getattr(self.email_gateway, "close", None)
        if callable(close_email):
            close_email()
        close_chat = getattr(self.chat_gateway, "close", None)
        if callable(close_chat):
            close_chat()
