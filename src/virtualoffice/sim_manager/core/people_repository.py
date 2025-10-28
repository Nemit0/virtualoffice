from __future__ import annotations

import json
from typing import List

from virtualoffice.common.db import get_connection
from ..schemas import PersonCreate, PersonRead, ScheduleBlockIn


class PeopleRepository:
    """Persistence layer for people and their schedules.

    Responsible only for DB I/O and row↔model mapping. No side-effects
    like gateway provisioning or VirtualWorker creation.
    """

    def list_people(self) -> List[PersonRead]:
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM people ORDER BY id").fetchall()
        return [self._row_to_person(row) for row in rows]

    def get_person(self, person_id: int) -> PersonRead:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
        if not row:
            raise ValueError("Person not found")
        return self._row_to_person(row)

    def find_by_name(self, name: str) -> PersonRead | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM people WHERE name = ?", (name,)).fetchone()
        return self._row_to_person(row) if row else None

    def delete_by_name(self, name: str) -> bool:
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM people WHERE name = ?", (name,)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM people WHERE id = ?", (row["id"],))
        return True

    def insert(self, payload: PersonCreate, persona_markdown: str, schedule_blocks: list[ScheduleBlockIn] | list) -> int:
        """Insert a new person and associated schedule blocks.

        `schedule_blocks` may be a list of ScheduleBlockIn or objects with
        attributes (start, end, activity). Only values are used.
        """
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
                    communication_style, email_address, chat_handle, is_department_head, team_name, skills,
                    personality, objectives, metrics, persona_markdown,
                    planning_guidelines, event_playbook, statuses
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    payload.team_name,
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
            if schedule_blocks:
                # Normalize to tuples
                values = []
                for block in schedule_blocks:
                    start = getattr(block, "start", None)
                    end = getattr(block, "end", None)
                    activity = getattr(block, "activity", None)
                    values.append((person_id, start, end, activity))
                conn.executemany(
                    "INSERT INTO schedule_blocks(person_id, start, end, activity) VALUES (?, ?, ?, ?)",
                    values,
                )
        return int(person_id)

    # --- Internal helpers ---
    def _row_to_person(self, row) -> PersonRead:
        person_id = row["id"]
        schedule = self._fetch_schedule(person_id)
        # Guard for optional team_name column (backward compatibility)
        try:
            team_name = row["team_name"]
        except (KeyError, IndexError):
            team_name = None
        # Coerce empty arrays to safe defaults to satisfy schema validators
        skills = json.loads(row["skills"]) if row["skills"] else []
        if not skills:
            skills = ["Generalist"]
        personality = json.loads(row["personality"]) if row["personality"] else []
        if not personality:
            personality = ["Helpful"]

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
            team_name=team_name,
            skills=skills,
            personality=personality,
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
        return [{"start": row["start"], "end": row["end"], "activity": row["activity"]} for row in rows]
