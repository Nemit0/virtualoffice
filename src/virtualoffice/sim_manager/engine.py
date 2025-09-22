from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from virtualoffice.common.db import execute_script, get_connection
from virtualoffice.virtualWorkers.worker import (
    ScheduleBlock,
    VirtualWorker,
    WorkerPersona,
    build_worker_markdown,
)

from .gateways import ChatGateway, EmailGateway
from .schemas import EventCreate, PersonCreate, PersonRead, ScheduleBlockIn, SimulationAdvanceResult, SimulationState

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
    is_running INTEGER NOT NULL
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
"""


@dataclass
class SimulationStatus:
    current_tick: int
    is_running: bool


class SimulationEngine:
    def __init__(
        self,
        email_gateway: EmailGateway,
        chat_gateway: ChatGateway,
        sim_manager_email: str = "simulator@vdos.local",
        sim_manager_handle: str = "sim-manager",
    ) -> None:
        self.email_gateway = email_gateway
        self.chat_gateway = chat_gateway
        self.sim_manager_email = sim_manager_email
        self.sim_manager_handle = sim_manager_handle
        execute_script(SIM_SCHEMA)
        self._ensure_state_row()
        self._bootstrap_channels()

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
                    communication_style, email_address, chat_handle, skills,
                    personality, objectives, metrics, persona_markdown,
                    planning_guidelines, event_playbook, statuses
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    # ------------------------------------------------------------------
    # Simulation control
    # ------------------------------------------------------------------
    def get_state(self) -> SimulationState:
        status = self._fetch_state()
        return SimulationState(current_tick=status.current_tick, is_running=status.is_running)

    def start(self) -> SimulationState:
        self._set_running(True)
        status = self._fetch_state()
        return SimulationState(current_tick=status.current_tick, is_running=status.is_running)

    def stop(self) -> SimulationState:
        self._set_running(False)
        status = self._fetch_state()
        return SimulationState(current_tick=status.current_tick, is_running=status.is_running)

    def advance(self, ticks: int, reason: str) -> SimulationAdvanceResult:
        status = self._fetch_state()
        if not status.is_running:
            raise RuntimeError("Simulation is not running; call start first")
        if ticks <= 0:
            raise ValueError("Ticks must be positive")

        people = self.list_people()
        emails_sent = 0
        chats_sent = 0

        for _ in range(ticks):
            status.current_tick += 1
            self._update_tick(status.current_tick, reason)
            for person in people:
                subject = f"[Tick {status.current_tick}] {reason.title()}"
                body = (
                    f"Tick {status.current_tick} processed for {person.name}.\n"
                    f"Role: {person.role}\n"
                    "Stay aligned with your hourly plan."
                )
                self.email_gateway.send_email(
                    sender=self.sim_manager_email,
                    to=[person.email_address],
                    subject=subject,
                    body=body,
                )
                emails_sent += 1

                chat_body = (
                    f"Tick {status.current_tick} update ? please review your inbox and objectives."
                )
                self.chat_gateway.send_dm(
                    sender=self.sim_manager_handle,
                    recipient=person.chat_handle,
                    body=chat_body,
                )
                chats_sent += 1

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
                    "INSERT INTO simulation_state(id, current_tick, is_running) VALUES (1, 0, 0)"
                )

    def _fetch_state(self) -> SimulationStatus:
        with get_connection() as conn:
            row = conn.execute("SELECT current_tick, is_running FROM simulation_state WHERE id = 1").fetchone()
        return SimulationStatus(current_tick=row["current_tick"], is_running=bool(row["is_running"]))

    def _set_running(self, running: bool) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET is_running = ? WHERE id = 1",
                (1 if running else 0,),
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