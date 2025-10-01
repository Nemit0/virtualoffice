from __future__ import annotations

import json
import hashlib
import logging
import random
import time
import threading
import math
from collections import deque
from datetime import datetime, timezone
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Sequence, Tuple

from virtualoffice.common.db import execute_script, get_connection
from virtualoffice.virtualWorkers.worker import (
    ScheduleBlock,
    WorkerPersona,
    build_worker_markdown,
    render_minute_schedule,
)

from .gateways import ChatGateway, EmailGateway
from .planner import GPTPlanner, PlanResult, Planner, PlanningError, StubPlanner
from .schemas import (
    EventCreate,
    PersonCreate,
    PersonRead,
    ScheduleBlockIn,
    SimulationAdvanceResult,
    SimulationStartRequest,
    SimulationState,
)

logger = logging.getLogger(__name__)

@dataclass
class _InboundMessage:
    sender_id: int
    sender_name: str
    subject: str
    summary: str
    action_item: str | None
    message_type: str
    channel: str
    tick: int
    message_id: int | None = None


@dataclass
class _WorkerRuntime:
    person: PersonRead
    inbox: list[_InboundMessage] = field(default_factory=list)

    def queue(self, message: _InboundMessage) -> None:
        self.inbox.append(message)

    def drain(self) -> list[_InboundMessage]:
        items = self.inbox
        self.inbox = []
        return items

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

CREATE TABLE IF NOT EXISTS worker_runtime_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(recipient_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worker_exchange_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    sender_id INTEGER,
    recipient_id INTEGER,
    channel TEXT NOT NULL,
    subject TEXT,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(sender_id) REFERENCES people(id) ON DELETE SET NULL,
    FOREIGN KEY(recipient_id) REFERENCES people(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS worker_status_overrides (
    worker_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    until_tick INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(worker_id) REFERENCES people(id) ON DELETE CASCADE
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
        tick_interval_seconds: float = 1.0,
    ) -> None:
        self.email_gateway = email_gateway
        self.chat_gateway = chat_gateway
        self.sim_manager_email = sim_manager_email
        self.sim_manager_handle = sim_manager_handle
        self.planner = planner or GPTPlanner()
        self._stub_planner = StubPlanner()
        self.hours_per_day = hours_per_day
        self.project_duration_weeks = 4
        self._project_plan_cache: dict[str, Any] | None = None
        self._planner_model_hint: str | None = None
        self._tick_interval_seconds = tick_interval_seconds
        self._auto_tick_thread: threading.Thread | None = None
        self._auto_tick_stop: threading.Event | None = None
        self._advance_lock = threading.Lock()
        self._worker_runtime: dict[int, _WorkerRuntime] = {}
        self._status_overrides: dict[int, Tuple[str, int]] = {}
        self._active_person_ids: list[int] | None = None
        self._work_hours_ticks: dict[int, tuple[int, int]] = {}
        self._random = random.Random()
        self._planner_metrics: deque[dict[str, Any]] = deque(maxlen=200)
        self._planner_metrics_lock = threading.Lock()
        execute_script(SIM_SCHEMA)
        self._apply_migrations()
        self._ensure_state_row()
        self._bootstrap_channels()
        self._load_status_overrides()
        self._sync_worker_runtimes(self.list_people())

    def _apply_migrations(self) -> None:
        with get_connection() as conn:
            people_columns = {row["name"] for row in conn.execute("PRAGMA table_info(people)")}
            if "is_department_head" not in people_columns:
                conn.execute("ALTER TABLE people ADD COLUMN is_department_head INTEGER NOT NULL DEFAULT 0")
            state_columns = {row["name"] for row in conn.execute("PRAGMA table_info(simulation_state)")}
            if "auto_tick" not in state_columns:
                conn.execute("ALTER TABLE simulation_state ADD COLUMN auto_tick INTEGER NOT NULL DEFAULT 0")

    def _parse_time_to_tick(self, time_str: str, *, round_up: bool = False) -> int:
        try:
            hours, minutes = time_str.split(':')
            total_minutes = int(hours) * 60 + int(minutes)
        except Exception:
            return 0
        ticks_per_day = max(1, self.hours_per_day)
        ticks_float = (total_minutes / 1440) * ticks_per_day
        if round_up:
            tick = math.ceil(ticks_float)
        else:
            tick = math.floor(ticks_float)
        return max(0, min(ticks_per_day, tick))

    def _parse_work_hours_to_ticks(self, work_hours: str) -> tuple[int, int]:
        ticks_per_day = max(1, self.hours_per_day)
        if ticks_per_day < 6:
            return (0, ticks_per_day)
        if not work_hours or '-' not in work_hours:
            return (0, ticks_per_day)
        start_str, end_str = [segment.strip() for segment in work_hours.split('-', 1)]
        start_tick = self._parse_time_to_tick(start_str, round_up=False)
        end_tick = self._parse_time_to_tick(end_str, round_up=True)
        start_tick = max(0, min(ticks_per_day - 1, start_tick))
        end_tick = max(0, min(ticks_per_day, end_tick))
        if start_tick == end_tick:
            return (0, ticks_per_day)
        return (start_tick, end_tick)

    def _update_work_windows(self, people: Sequence[PersonRead]) -> None:
        cache: dict[int, tuple[int, int]] = {}
        for person in people:
            start_tick, end_tick = self._parse_work_hours_to_ticks(getattr(person, 'work_hours', '') or '')
            cache[person.id] = (start_tick, end_tick)
        self._work_hours_ticks = cache

    def _is_within_work_hours(self, person: PersonRead, tick: int) -> bool:
        if not self.hours_per_day:
            return True
        window = self._work_hours_ticks.get(person.id)
        if not window:
            return True
        start_tick, end_tick = window
        tick_of_day = (tick - 1) % self.hours_per_day
        if start_tick <= end_tick:
            return start_tick <= tick_of_day < end_tick
        return tick_of_day >= start_tick or tick_of_day < end_tick

    def _format_sim_time(self, tick: int) -> str:
        if tick <= 0:
            return "Day 0 00:00"
        ticks_per_day = max(1, self.hours_per_day)
        day_index = (tick - 1) // ticks_per_day + 1
        tick_of_day = (tick - 1) % ticks_per_day
        minutes = int((tick_of_day / ticks_per_day) * 1440)
        hour = minutes // 60
        minute = minutes % 60
        return f"Day {day_index} {hour:02d}:{minute:02d}"


    def _planner_context_summary(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        worker = kwargs.get('worker')
        if worker is not None:
            summary['worker'] = getattr(worker, 'name', worker)
        department_head = kwargs.get('department_head')
        if department_head is not None:
            summary['department_head'] = getattr(department_head, 'name', department_head)
        project_name = kwargs.get('project_name')
        if project_name:
            summary['project_name'] = project_name
        day_index = kwargs.get('day_index')
        if day_index is not None:
            summary['day_index'] = day_index
        tick = kwargs.get('tick')
        if tick is not None:
            summary['tick'] = tick
        model_hint = kwargs.get('model_hint')
        if model_hint:
            summary['model_hint'] = model_hint
        return summary

    def get_planner_metrics(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._planner_metrics_lock:
            data = list(self._planner_metrics)
        if limit <= 0:
            return data
        return data[-limit:]

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

        person = self.get_person(person_id)
        self._get_worker_runtime(person)
        return person

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
        self._worker_runtime.pop(row["id"], None)
        return True

    # ------------------------------------------------------------------
    # Planning lifecycle
    def _call_planner(self, method_name: str, **kwargs) -> PlanResult:
        planner = self.planner
        method = getattr(planner, method_name)
        planner_name = planner.__class__.__name__
        fallback_name = self._stub_planner.__class__.__name__
        context = self._planner_context_summary(kwargs)
        start = time.perf_counter()
        logger.info("Planner %s using %s starting with context=%s", method_name, planner_name, context)
        try:
            result = method(**kwargs)
        except PlanningError as exc:
            duration = time.perf_counter() - start
            if isinstance(planner, StubPlanner):
                logger.error("Stub planner %s failed after %.2fs: %s", method_name, duration, exc)
                raise
            logger.warning("Planner %s using %s failed after %.2fs: %s. Falling back to stub planner.", method_name, planner_name, duration, exc)
            fallback_method = getattr(self._stub_planner, method_name)
            fallback_start = time.perf_counter()
            fallback_result = fallback_method(**kwargs)
            fallback_duration = time.perf_counter() - fallback_start
            logger.info("Stub planner %s succeeded in %.2fs (model=%s)", fallback_name, fallback_duration, getattr(fallback_result, 'model_used', 'vdos-stub'))
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'method': method_name,
                'planner': planner_name,
                'result_planner': fallback_name,
                'model': getattr(fallback_result, 'model_used', 'vdos-stub'),
                'duration_ms': round(duration * 1000, 2),
                'fallback_duration_ms': round(fallback_duration * 1000, 2),
                'fallback': True,
                'error': str(exc),
                'context': context,
            }
            with self._planner_metrics_lock:
                self._planner_metrics.append(entry)
            return fallback_result
        else:
            duration = time.perf_counter() - start
            logger.info("Planner %s using %s succeeded in %.2fs (model=%s)", method_name, planner_name, duration, getattr(result, 'model_used', 'unknown'))
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'method': method_name,
                'planner': planner_name,
                'result_planner': planner_name,
                'model': getattr(result, 'model_used', 'unknown'),
                'duration_ms': round(duration * 1000, 2),
                'fallback_duration_ms': None,
                'fallback': False,
                'context': context,
            }
            with self._planner_metrics_lock:
                self._planner_metrics.append(entry)
            return result

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

    def _initialise_project_plan(self, request: SimulationStartRequest, team: Sequence[PersonRead]) -> None:
        if not team:
            raise RuntimeError("Cannot initialise project plan without any personas")
        self._sync_worker_runtimes(team)
        department_head = self._resolve_department_head(team, request.department_head_name)
        try:
            plan_result = self._call_planner(
                'generate_project_plan',
                department_head=department_head,
                project_name=request.project_name,
                project_summary=request.project_summary,
                duration_weeks=request.duration_weeks,
                team=team,
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
        for person in team:
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
            raise RuntimeError(
                f"Department head '{requested_name}' not found among registered personas."
            )
        for person in people:
            if getattr(person, "is_department_head", False):
                return person
        # Default to the first registered persona so small teams can start without explicit leads.
        return people[0]

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
            result = self._call_planner(
                'generate_daily_plan',
                worker=person,
                project_plan=project_plan['plan'],
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
        adjustments: list[str] | None = None,
    ) -> PlanResult:
        try:
            result = self._call_planner(
                'generate_hourly_plan',
                worker=person,
                project_plan=project_plan['plan'],
                daily_plan=daily_plan_text,
                tick=tick,
                context_reason=reason,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate hourly plan for {person.name}: {exc}") from exc

        context = f"reason={reason}"
        content_result = result
        if adjustments:
            bullets = "\n".join(f"- {item}" for item in adjustments)
            content = f"{result.content}\n\nAdjustments from live collaboration:\n{bullets}"
            content_result = PlanResult(content=content, model_used=result.model_used, tokens_used=result.tokens_used)
            context += f";adjustments={len(adjustments)}"

        self._store_worker_plan(
            person_id=person.id,
            tick=tick,
            plan_type="hourly",
            result=content_result,
            context=context,
        )
        return content_result

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
            result = self._call_planner(
                'generate_daily_report',
                worker=person,
                project_plan=project_plan['plan'],
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
            result = self._call_planner(
                'generate_simulation_report',
                project_plan=project_plan['plan'],
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
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def start(self, request: SimulationStartRequest | None = None) -> SimulationState:
        seed = self._derive_seed(request)
        self._random.seed(seed)
        self._reset_runtime_state()
        all_people = self.list_people()
        if not all_people:
            raise RuntimeError("Cannot start simulation without any personas")
        active_people = self._resolve_active_people(request, all_people)
        self._active_person_ids = [person.id for person in active_people]
        if request is not None:
            self.project_duration_weeks = request.duration_weeks
            self._planner_model_hint = request.model_hint
            self._initialise_project_plan(request, active_people)
        self._set_running(True)
        self._sync_worker_runtimes(active_people)
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def stop(self) -> SimulationState:
        self.stop_auto_ticks()
        status = self._fetch_state()
        if status.is_running:
            project_plan = self.get_project_plan()
            if project_plan is not None:
                self._generate_simulation_report(project_plan, total_ticks=status.current_tick)
        self._set_running(False)
        self._active_person_ids = None
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def start_auto_ticks(self) -> SimulationState:
        status = self._fetch_state()
        if not status.is_running:
            raise RuntimeError("Simulation must be running before enabling automatic ticks")
        self._set_auto_tick(True)
        thread = self._auto_tick_thread
        if thread is None or not thread.is_alive():
            stop_event = threading.Event()
            self._auto_tick_stop = stop_event
            thread = threading.Thread(
                target=self._run_auto_tick_loop,
                args=(stop_event,),
                name="vdos-auto-tick",
                daemon=True,
            )
            self._auto_tick_thread = thread
            thread.start()
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def stop_auto_ticks(self) -> SimulationState:
        self._set_auto_tick(False)
        stop_event = self._auto_tick_stop
        if stop_event is not None:
            stop_event.set()
        thread = self._auto_tick_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
            if thread.is_alive():
                logger.warning("Automatic tick thread did not exit cleanly within timeout")
        self._auto_tick_thread = None
        self._auto_tick_stop = None
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def _run_auto_tick_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(self._tick_interval_seconds):
            state = self._fetch_state()
            if not state.is_running or not state.auto_tick:
                break
            try:
                self.advance(1, "auto")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Automatic tick failed; disabling auto ticks.")
                self._set_auto_tick(False)
                break

    def advance(self, ticks: int, reason: str) -> SimulationAdvanceResult:
        with self._advance_lock:
            status = self._fetch_state()
            if not status.is_running:
                raise RuntimeError("Simulation is not running; call start first")
            if ticks <= 0:
                raise ValueError("Ticks must be positive")

            project_plan = self.get_project_plan()
            if project_plan is None:
                raise RuntimeError("Project plan is not initialised; start the simulation with project details before advancing.")

            people = self._get_active_people()
            if not people:
                raise RuntimeError("Cannot advance simulation without any active personas")
            self._sync_worker_runtimes(people)
            people_by_id = {person.id: person for person in people}

            emails_sent = 0
            chats_sent = 0

            for _ in range(ticks):
                status.current_tick += 1
                self._update_tick(status.current_tick, reason)
                self._refresh_status_overrides(status.current_tick)
                event_adjustments, _ = self._maybe_generate_events(people, status.current_tick, project_plan)
                day_index = (status.current_tick - 1) // self.hours_per_day
                for person in people:
                    runtime = self._get_worker_runtime(person)
                    incoming = runtime.drain()
                    working = self._is_within_work_hours(person, status.current_tick)
                    adjustments: list[str] = list(event_adjustments.get(person.id, []))
                    override = self._status_overrides.get(person.id)
                    if override and override[0] == 'SickLeave':
                        incoming = []
                        adjustments.append('Observe sick leave and hold tasks until recovered.')
                    if not working:
                        if incoming:
                            for message in incoming:
                                runtime.queue(message)
                        for note in adjustments:
                            reminder = _InboundMessage(
                                sender_id=0,
                                sender_name='Simulation Manager',
                                subject='Pending adjustment',
                                summary=note,
                                action_item=note,
                                message_type='event',
                                channel='system',
                                tick=status.current_tick,
                            )
                            runtime.queue(reminder)
                        logger.info("Skipping planning for %s at tick %s (off hours)", person.name, status.current_tick)
                        continue
                    should_plan = bool(incoming) or bool(adjustments) or reason != 'auto' or (((status.current_tick - 1) % self.hours_per_day) == 0)
                    if not should_plan:
                        continue
                    self._remove_runtime_messages([msg.message_id for msg in incoming if msg.message_id is not None])
                    for message in incoming:
                        sender_person = people_by_id.get(message.sender_id)
                        if message.message_type == "ack":
                            adjustments.append(f"Acknowledged by {message.sender_name}: {message.summary}")
                            continue
                        if message.action_item:
                            adjustments.append(f"Handle request from {message.sender_name}: {message.action_item}")
                        if sender_person is None:
                            continue
                        ack_phrase = (message.action_item or message.summary or "your latest update").rstrip('.')
                        ack_body = f"{sender_person.name.split()[0]}, I'm on {ack_phrase}."
                        self.chat_gateway.send_dm(
                            sender=person.chat_handle,
                            recipient=sender_person.chat_handle,
                            body=ack_body,
                        )
                        chats_sent += 1
                        self._log_exchange(status.current_tick, person.id, sender_person.id, 'chat', None, ack_body)
                        ack_message = _InboundMessage(
                            sender_id=person.id,
                            sender_name=person.name,
                            subject=f"Acknowledgement from {person.name}",
                            summary=ack_body,
                            action_item=None,
                            message_type='ack',
                            channel='chat',
                            tick=status.current_tick,
                        )
                        self._queue_runtime_message(sender_person, ack_message)

                    daily_plan_text = self._ensure_daily_plan(person, day_index, project_plan)
                    hourly_result = self._generate_hourly_plan(
                        person,
                        project_plan,
                        daily_plan_text,
                        tick=status.current_tick,
                        reason=reason,
                        adjustments=adjustments or None,
                    )
                    daily_summary = self._summarise_plan(daily_plan_text, max_lines=3)
                    hourly_summary = self._summarise_plan(hourly_result.content)
                    if override and override[0] == 'SickLeave':
                        continue
                    recipients = self._select_collaborators(person, people)
                    if not recipients:
                        subject = f"[Tick {status.current_tick}] {reason.title()} update for {person.name}"
                        body_lines = [
                            f"Project: {project_plan['project_name']}",
                            f"Daily focus:\n{daily_summary}",
                            "",
                            f"Hourly plan:\n{hourly_summary}",
                            "",
                            "Keep the runway clear for surprises.",
                        ]
                        body_text = "\n".join(body_lines)
                        self.email_gateway.send_email(
                            sender=self.sim_manager_email,
                            to=[person.email_address],
                            subject=subject,
                            body=body_text,
                        )
                        emails_sent += 1
                        self._log_exchange(status.current_tick, None, person.id, "email", subject, body_text)
                        chat_body = f"Tick {status.current_tick}: {hourly_summary.replace('\n', ' / ')}\nLet me know if you need support."
                        self.chat_gateway.send_dm(
                            sender=self.sim_manager_handle,
                            recipient=person.chat_handle,
                            body=chat_body,
                        )
                        chats_sent += 1
                        self._log_exchange(status.current_tick, None, person.id, "chat", None, chat_body)
                        continue
                    action_item = self._derive_action_item(hourly_summary, daily_summary)
                    for recipient in recipients:
                        subject = f"[Tick {status.current_tick}] {person.name} -> {recipient.name}: {reason.title()} focus"
                        body_lines = [
                            f"Hey {recipient.name.split()[0]},",
                            "",
                            "Current focus:",
                            hourly_summary or daily_summary or "Heads down on deliverables.",
                            "",
                            f"Request: {action_item}",
                            "Ping me if you need anything shifted.",
                        ]
                        body = "\n".join(body_lines)
                        self.email_gateway.send_email(
                            sender=person.email_address,
                            to=[recipient.email_address],
                            subject=subject,
                            body=body,
                        )
                        emails_sent += 1
                        self._log_exchange(status.current_tick, person.id, recipient.id, "email", subject, body)

                        chat_body = f"Tick {status.current_tick}: {action_item}"
                        self.chat_gateway.send_dm(
                            sender=person.chat_handle,
                            recipient=recipient.chat_handle,
                            body=chat_body,
                        )
                        chats_sent += 1
                        self._log_exchange(status.current_tick, person.id, recipient.id, "chat", None, chat_body)

                        inbound = _InboundMessage(
                            sender_id=person.id,
                            sender_name=person.name,
                            subject=subject,
                            summary=action_item,
                            action_item=action_item,
                            message_type="update",
                            channel="email+chat",
                            tick=status.current_tick,
                        )
                        self._queue_runtime_message(recipient, inbound)

                if status.current_tick % self.hours_per_day == 0:
                    completed_day = (status.current_tick // self.hours_per_day) - 1
                    for person in people:
                        self._generate_daily_report(person, completed_day, project_plan)

            return SimulationAdvanceResult(
                ticks_advanced=ticks,
                current_tick=status.current_tick,
                emails_sent=emails_sent,
                chat_messages_sent=chats_sent,
                sim_time=self._format_sim_time(status.current_tick),
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
    def _get_worker_runtime(self, person: PersonRead) -> _WorkerRuntime:
        runtime = self._worker_runtime.get(person.id)
        if runtime is None:
            runtime = _WorkerRuntime(person=person)
            self._worker_runtime[person.id] = runtime
            self._load_runtime_messages(runtime)
        else:
            runtime.person = person
        return runtime

    def _sync_worker_runtimes(self, people: Sequence[PersonRead]) -> None:
        active_ids = {person.id for person in people}
        self._update_work_windows(people)
        for person in people:
            self._get_worker_runtime(person)
        for person_id in list(self._worker_runtime.keys()):
            if person_id not in active_ids:
                self._worker_runtime.pop(person_id, None)

    def _load_status_overrides(self) -> None:
        with get_connection() as conn:
            rows = conn.execute("SELECT worker_id, status, until_tick FROM worker_status_overrides").fetchall()
        self._status_overrides = {row["worker_id"]: (row["status"], row["until_tick"]) for row in rows}

    def _queue_runtime_message(self, recipient: PersonRead, message: _InboundMessage) -> None:
        runtime = self._get_worker_runtime(recipient)
        runtime.queue(message)
        self._persist_runtime_message(recipient.id, message)

    def _persist_runtime_message(self, recipient_id: int, message: _InboundMessage) -> None:
        payload = {
            "sender_id": message.sender_id,
            "sender_name": message.sender_name,
            "subject": message.subject,
            "summary": message.summary,
            "action_item": message.action_item,
            "message_type": message.message_type,
            "channel": message.channel,
            "tick": message.tick,
        }
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO worker_runtime_messages(recipient_id, payload) VALUES (?, ?)",
                (recipient_id, json.dumps(payload)),
            )
            message.message_id = cursor.lastrowid

    def _remove_runtime_messages(self, message_ids: Sequence[int]) -> None:
        if not message_ids:
            return
        with get_connection() as conn:
            conn.executemany("DELETE FROM worker_runtime_messages WHERE id = ?", [(message_id,) for message_id in message_ids])

    def _load_runtime_messages(self, runtime: _WorkerRuntime) -> None:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, payload FROM worker_runtime_messages WHERE recipient_id = ? ORDER BY id",
                (runtime.person.id,),
            ).fetchall()
        runtime.inbox = []
        for row in rows:
            payload = json.loads(row["payload"])
            runtime.inbox.append(
                _InboundMessage(
                    sender_id=payload["sender_id"],
                    sender_name=payload["sender_name"],
                    subject=payload["subject"],
                    summary=payload["summary"],
                    action_item=payload.get("action_item"),
                    message_type=payload["message_type"],
                    channel=payload["channel"],
                    tick=payload["tick"],
                    message_id=row["id"],
                )
            )

    def _log_exchange(self, tick: int, sender_id: int | None, recipient_id: int | None, channel: str, subject: str | None, summary: str | None) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO worker_exchange_log(tick, sender_id, recipient_id, channel, subject, summary) VALUES (?, ?, ?, ?, ?, ?)",
                (tick, sender_id, recipient_id, channel, subject, summary),
            )

    def _set_status_override(self, worker_id: int, status: str, until_tick: int, reason: str) -> None:
        self._status_overrides[worker_id] = (status, until_tick)
        with get_connection() as conn:
            conn.execute(
                ("INSERT INTO worker_status_overrides(worker_id, status, until_tick, reason) VALUES (?, ?, ?, ?)"
                 " ON CONFLICT(worker_id) DO UPDATE SET status = excluded.status, until_tick = excluded.until_tick, reason = excluded.reason"),
                (worker_id, status, until_tick, reason),
            )

    def _refresh_status_overrides(self, current_tick: int) -> None:
        expired = [worker_id for worker_id, (_, until_tick) in self._status_overrides.items() if until_tick <= current_tick]
        if not expired:
            return
        with get_connection() as conn:
            conn.executemany(
                "DELETE FROM worker_status_overrides WHERE worker_id = ?",
                [(worker_id,) for worker_id in expired],
            )
        for worker_id in expired:
            self._status_overrides.pop(worker_id, None)

    def _reset_runtime_state(self) -> None:
        self._worker_runtime.clear()
        self._status_overrides.clear()
        self._active_person_ids = None
        with get_connection() as conn:
            conn.execute("DELETE FROM worker_runtime_messages")
            conn.execute("DELETE FROM worker_status_overrides")
        self._load_status_overrides()

    def _resolve_active_people(
        self,
        request: SimulationStartRequest | None,
        available: Sequence[PersonRead],
    ) -> list[PersonRead]:
        if not available:
            return []
        if request is None:
            return list(available)

        include_ids = {int(person_id) for person_id in (request.include_person_ids or [])}
        include_names = {name.strip().lower() for name in (request.include_person_names or []) if name.strip()}

        if include_ids or include_names:
            matched = [
                person
                for person in available
                if person.id in include_ids or person.name.lower() in include_names
            ]
            matched_ids = {person.id for person in matched}
            matched_names = {person.name.lower() for person in matched}
            missing_parts: list[str] = []
            missing_ids = sorted(include_ids - matched_ids)
            missing_names = sorted(include_names - matched_names)
            if missing_ids:
                missing_parts.append("ids " + ", ".join(str(identifier) for identifier in missing_ids))
            if missing_names:
                missing_parts.append("names " + ", ".join(missing_names))
            if missing_parts:
                raise RuntimeError("Requested personas not found: " + "; ".join(missing_parts))
        else:
            matched = list(available)

        exclude_ids = {int(person_id) for person_id in (request.exclude_person_ids or [])}
        exclude_names = {name.strip().lower() for name in (request.exclude_person_names or []) if name.strip()}
        filtered = [
            person
            for person in matched
            if person.id not in exclude_ids and person.name.lower() not in exclude_names
        ]
        if not filtered:
            raise RuntimeError("No personas remain after applying include/exclude filters")
        return filtered

    def _get_active_people(self) -> list[PersonRead]:
        available = self.list_people()
        if not available:
            return []
        if self._active_person_ids is None:
            return list(available)
        lookup = {person.id: person for person in available}
        active: list[PersonRead] = []
        for person_id in self._active_person_ids:
            person = lookup.get(person_id)
            if person is not None:
                active.append(person)
        if not active:
            return []
        if len(active) != len(self._active_person_ids):
            self._active_person_ids = [person.id for person in active]
        return active

    def _select_collaborators(self, person: PersonRead, people: Sequence[PersonRead]) -> list[PersonRead]:
        if len(people) <= 1:
            return []
        head = next((p for p in people if getattr(p, "is_department_head", False)), people[0])
        if person.id == head.id:
            return [member for member in people if member.id != person.id][:2]
        recipients: list[PersonRead] = []
        if head.id != person.id:
            recipients.append(head)
        for candidate in people:
            if candidate.id not in {person.id, head.id}:
                recipients.append(candidate)
                break
        return recipients

    def _derive_action_item(self, hourly_summary: str, daily_summary: str) -> str:
        for source in (hourly_summary, daily_summary):
            if not source:
                continue
            for line in source.splitlines():
                cleaned = line.strip().lstrip('-•').strip()
                if cleaned:
                    return cleaned
        return "Keep momentum on the current deliverables"

    def reset(self) -> SimulationState:
        with self._advance_lock:
            self.stop_auto_ticks()
            with get_connection() as conn:
                for table in ("project_plans", "worker_plans", "worker_exchange_log", "worker_runtime_messages", "daily_reports", "simulation_reports", "events", "tick_log"):
                    conn.execute(f"DELETE FROM {table}")
                conn.execute("DELETE FROM worker_status_overrides")
                conn.execute("UPDATE simulation_state SET current_tick = 0, is_running = 0, auto_tick = 0 WHERE id = 1")
            self._project_plan_cache = None
            self._planner_model_hint = None
            self._planner_metrics.clear()
            self.project_duration_weeks = 4
            self._reset_runtime_state()
            people = self.list_people()
            self._update_work_windows(people)
            status = self._fetch_state()
            return SimulationState(
                current_tick=status.current_tick,
                is_running=status.is_running,
                auto_tick=status.auto_tick,
                sim_time=self._format_sim_time(status.current_tick),
            )

    def reset_full(self) -> SimulationState:
        """Resets simulation state and deletes all personas.

        Intended for a destructive "start fresh" action in the dashboard.
        """
        with self._advance_lock:
            # First clear runtime and planning artifacts
            self.reset()
            # Then purge personas (cascades schedule blocks via FK)
            with get_connection() as conn:
                conn.execute("DELETE FROM people")
                conn.execute("DELETE FROM worker_status_overrides")
            # Reset runtime caches after purge
            self._reset_runtime_state()
            self._update_work_windows([])
            status = self._fetch_state()
            return SimulationState(
                current_tick=status.current_tick,
                is_running=status.is_running,
                auto_tick=status.auto_tick,
                sim_time=self._format_sim_time(status.current_tick),
            )

    def _record_event(self, event_type: str, target_ids: Sequence[int], tick: int, payload: dict | None = None) -> None:
        event = EventCreate(type=event_type, target_ids=list(target_ids), at_tick=tick, payload=payload)
        self.inject_event(event)

    def _derive_seed(self, request: SimulationStartRequest | None) -> int:
        if request and request.random_seed is not None:
            return request.random_seed
        base = (request.project_name if request else 'vdos-default').encode('utf-8')
        digest = hashlib.sha256(base).digest()
        return int.from_bytes(digest[:8], 'big')

    def _maybe_generate_events(self, people: Sequence[PersonRead], tick: int, project_plan: dict[str, Any]) -> tuple[dict[int, list[str]], dict[int, list[_InboundMessage]]]:
        adjustments: dict[int, list[str]] = {}
        immediate: dict[int, list[_InboundMessage]] = {}
        if not people:
            return adjustments, immediate
        rng = self._random

        # Sick leave event
        if rng.random() < 0.25:
            active_people = [p for p in people if self._status_overrides.get(p.id, (None, 0))[0] != 'SickLeave']
            if active_people:
                target = rng.choice(active_people)
                until_tick = tick + self.hours_per_day
                self._set_status_override(target.id, 'SickLeave', until_tick, f'Sick leave triggered at tick {tick}')
                rest_message = _InboundMessage(
                    sender_id=0,
                    sender_name='Simulation Manager',
                    subject='Rest and recover',
                    summary='Take the remainder of the day off to recover.',
                    action_item='Pause all work and update once you are back online.',
                    message_type='event',
                    channel='system',
                    tick=tick,
                )
                self._queue_runtime_message(target, rest_message)
                immediate.setdefault(target.id, []).append(rest_message)
                adjustments.setdefault(target.id, []).append('Rest and reschedule tasks due to sudden illness.')

                head = next((p for p in people if getattr(p, 'is_department_head', False)), None)
                if head and head.id != target.id:
                    subject = f'Coverage needed: {target.name} is out sick'
                    body = f"{target.name} reported sick leave at tick {tick}. Please redistribute their urgent work."
                    self.email_gateway.send_email(
                        sender=self.sim_manager_email,
                        to=[head.email_address],
                        subject=subject,
                        body=body,
                    )
                    self._log_exchange(tick, None, head.id, 'email', subject, body)
                    head_message = _InboundMessage(
                        sender_id=0,
                        sender_name='Simulation Manager',
                        subject=subject,
                        summary=body,
                        action_item=f'Coordinate cover for {target.name}.',
                        message_type='event',
                        channel='email',
                        tick=tick,
                    )
                    self._queue_runtime_message(head, head_message)
                    immediate.setdefault(head.id, []).append(head_message)
                    adjustments.setdefault(head.id, []).append(f'Coordinate cover while {target.name} recovers.')

                self._record_event('sick_leave', [target.id], tick, {'until_tick': until_tick})

        # Client feature request
        if rng.random() < 0.3:
            head = next((p for p in people if getattr(p, 'is_department_head', False)), people[0])
            feature = rng.choice([
                'refresh hero messaging',
                'prepare launch analytics dashboard',
                'add testimonial carousel',
                'deliver onboarding walkthrough',
            ])
            subject = f'Client request: {feature}'
            body = f"Client requested {feature} at tick {tick}. Align on next steps within this cycle."
            self.email_gateway.send_email(
                sender=self.sim_manager_email,
                to=[head.email_address],
                subject=subject,
                body=body,
            )
            self._log_exchange(tick, None, head.id, 'email', subject, body)
            head_message = _InboundMessage(
                sender_id=0,
                sender_name='Simulation Manager',
                subject=subject,
                summary=body,
                action_item=f'Plan response to client request: {feature}.',
                message_type='event',
                channel='email',
                tick=tick,
            )
            self._queue_runtime_message(head, head_message)
            immediate.setdefault(head.id, []).append(head_message)
            adjustments.setdefault(head.id, []).append(f'Plan response to client request: {feature}.')

            collaborators = [p for p in people if p.id != head.id]
            if collaborators:
                partner = rng.choice(collaborators)
                partner_message = _InboundMessage(
                    sender_id=head.id,
                    sender_name=head.name,
                    subject=subject,
                    summary=f'Partner with {head.name} on {feature}.',
                    action_item=f'Support {head.name} on {feature}.',
                    message_type='event',
                    channel='chat',
                    tick=tick,
                )
                self._queue_runtime_message(partner, partner_message)
                immediate.setdefault(partner.id, []).append(partner_message)
                adjustments.setdefault(partner.id, []).append(f'Partner with {head.name} on client request: {feature}.')
                chat_body = f"Client request: {feature}. Let's sync on next steps."
                self.chat_gateway.send_dm(
                    sender=head.chat_handle,
                    recipient=partner.chat_handle,
                    body=chat_body,
                )
                self._log_exchange(tick, head.id, partner.id, 'chat', None, chat_body)
                targets = [head.id, partner.id]
            else:
                targets = [head.id]
            self._record_event('client_feature_request', targets, tick, {'feature': feature})

        return adjustments, immediate

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
        self.stop_auto_ticks()
        close_email = getattr(self.email_gateway, "close", None)
        if callable(close_email):
            close_email()
        close_chat = getattr(self.chat_gateway, "close", None)
        if callable(close_chat):
            close_chat()



