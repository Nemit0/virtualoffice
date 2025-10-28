from __future__ import annotations

from typing import Dict, Sequence

# Lazy imports only at function level to avoid cycles
from ..schemas import PersonRead, ScheduleBlockIn


class WorkerRegistry:
    """Manages VirtualWorker lifecycle and avoids circular imports.

    - Creates VirtualWorker instances only when the planner supports
      the `generate_with_messages` interface.
    - Keeps a cache of workers by person_id.
    """

    def __init__(self, *, prompt_manager, context_builder, planner) -> None:
        self.prompt_manager = prompt_manager
        self.context_builder = context_builder
        self.planner = planner
        self.workers: Dict[int, "VirtualWorker"] = {}

    # Public API --------------------------------------------------------
    def supports_virtual_workers(self) -> bool:
        return hasattr(self.planner, "generate_with_messages")

    def sync_workers(self, people: Sequence[PersonRead]) -> None:
        if not self.supports_virtual_workers():
            return
        for person in people:
            if person.id not in self.workers:
                self.workers[person.id] = self._create_worker_for_person(person)

    def ensure_worker(self, person: PersonRead) -> None:
        if not self.supports_virtual_workers():
            return
        if person.id not in self.workers:
            self.workers[person.id] = self._create_worker_for_person(person)

    # Internals ---------------------------------------------------------
    def _to_persona(self, person: PersonRead):
        from virtualoffice.virtualWorkers.worker import WorkerPersona

        return WorkerPersona(
            name=person.name,
            role=person.role,
            email_address=person.email_address,
            chat_handle=person.chat_handle,
            timezone=person.timezone,
            work_hours=person.work_hours,
            break_frequency=person.break_frequency,
            communication_style=person.communication_style,
            skills=person.skills,
            personality=person.personality,
            objectives=person.objectives,
            metrics=person.metrics,
            is_department_head=person.is_department_head,
            team_name=person.team_name,
        )

    def _create_worker_for_person(self, person: PersonRead):
        from virtualoffice.virtualWorkers.worker import ScheduleBlock
        from virtualoffice.virtualWorkers.virtual_worker import VirtualWorker

        schedule = []
        for block in (person.schedule or []):
            if isinstance(block, dict):
                start, end, activity = block.get("start"), block.get("end"), block.get("activity")
            else:  # ScheduleBlockIn
                block = block  # type: ignore[assignment]
                start, end, activity = block.start, block.end, block.activity
            schedule.append(ScheduleBlock(start, end, activity))

        persona = self._to_persona(person)

        worker = VirtualWorker(
            persona=persona,
            prompt_manager=self.prompt_manager,
            context_builder=self.context_builder,
            planner=self.planner,
            schedule=schedule,
            planning_guidelines=person.planning_guidelines,
            event_playbook=person.event_playbook,
            statuses=person.statuses,
        )
        return worker

