from __future__ import annotations

import json
import os
import hashlib
import logging
import random
import time
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Sequence

from virtualoffice.common.db import get_connection
from virtualoffice.common.localization import get_current_locale_manager
from virtualoffice.virtualWorkers.worker import (
    ScheduleBlock,
    WorkerPersona,
    build_worker_markdown,
    render_minute_schedule,
)
# Lazy imports moved to method level to avoid circular dependency at module load time
# VirtualWorker, PlanningContext, DailyPlanningContext, ReportContext imported where needed

from .core.simulation_state import (
    SimulationState as StateManager,
)
from .core.tick_manager import TickManager
from .core.event_system import EventSystem, InboundMessage
from .core.communication_hub import CommunicationHub
from .core.worker_runtime import WorkerRuntimeManager
from .core.project_manager import ProjectManager
from .core.people_repository import PeopleRepository
from .core.plan_store import PlanStore
from .core.report_store import ReportStore
from .gateways import ChatGateway, EmailGateway
from .planner import GPTPlanner, PlanResult, Planner, PlanningError, StubPlanner
from .prompts import PromptManager, ContextBuilder
from .schemas import (
    EventCreate,
    PersonCreate,
    PersonRead,
    ScheduleBlockIn,
    SimulationAdvanceResult,
    SimulationStartRequest,
    SimulationState,  # API response model
)

logger = logging.getLogger(__name__)

# Use InboundMessage from EventSystem module
_InboundMessage = InboundMessage


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
        planner_strict: bool | None = None,
    ) -> None:
        self.email_gateway = email_gateway
        self.chat_gateway = chat_gateway
        self.sim_manager_email = sim_manager_email
        self.sim_manager_handle = sim_manager_handle
        self.planner = planner or GPTPlanner()
        self._stub_planner = StubPlanner()
        self.hours_per_day = hours_per_day
        self.project_duration_weeks = 4
        self._planner_model_hint: str | None = None
        self._active_person_ids: list[int] | None = None

        # Initialize state and tick managers
        self.state = StateManager()
        self.tick_manager = TickManager(hours_per_day=hours_per_day, tick_interval_seconds=tick_interval_seconds)
        self._random = random.Random()

        # Initialize event system
        self.event_system = EventSystem(random_seed=None)

        # Initialize communication hub
        try:
            cooldown_ticks = int(os.getenv("VDOS_CONTACT_COOLDOWN_TICKS", "10"))
        except ValueError:
            cooldown_ticks = 10
        self.communication_hub = CommunicationHub(
            email_gateway=email_gateway,
            chat_gateway=chat_gateway,
            tick_manager=self.tick_manager,
            cooldown_ticks=cooldown_ticks,
        )

        # Initialize worker runtime manager
        self.worker_runtime_manager = WorkerRuntimeManager()

        # Initialize project manager
        self.project_manager = ProjectManager()

        # Persistence repositories/stores
        self.people_repo = PeopleRepository()
        self.plan_store = PlanStore()
        self.report_store = ReportStore()

        # Initialize prompt system
        template_dir = Path(__file__).parent / "prompts" / "templates"
        self._locale = os.getenv("VDOS_LOCALE", "en").strip().lower() or "en"
        self.prompt_manager = PromptManager(str(template_dir), locale=self._locale)
        self.context_builder = ContextBuilder(locale=self._locale)

        # Virtual workers dictionary (type hint uses string to avoid circular import)
        self.workers: dict[int, "VirtualWorker"] = {}

        self._planner_metrics: deque[dict[str, Any]] = deque(maxlen=200)
        # Locale (simple toggle for certain strings)
        self._planner_metrics_lock = threading.Lock()
        # Planner strict mode: if True, do not fall back to stub on GPT failures
        if planner_strict is None:
            env = os.getenv("VDOS_PLANNER_STRICT", "0").strip().lower()
            self._planner_strict = env in {"1", "true", "yes", "on"}
        else:
            self._planner_strict = bool(planner_strict)
        # Hourly planning limiter to prevent endless replanning within the same minute
        try:
            self._max_hourly_plans_per_minute = int(os.getenv("VDOS_MAX_HOURLY_PLANS_PER_MINUTE", "10"))
        except ValueError:
            self._max_hourly_plans_per_minute = 10
        # (person_id, day_index, tick_of_day) -> attempts
        self._hourly_plan_attempts: dict[tuple[int, int, int], int] = {}
        # Parallel planning configuration
        try:
            self._max_planning_workers = int(os.getenv("VDOS_MAX_PLANNING_WORKERS", "4"))
        except ValueError:
            self._max_planning_workers = 4
        self._planning_executor: ThreadPoolExecutor | None = None
        if self._max_planning_workers > 1:
            self._planning_executor = ThreadPoolExecutor(
                max_workers=self._max_planning_workers, thread_name_prefix="planner"
            )

        # Auto-pause configuration - default to enabled with validation
        try:
            env_auto_pause = os.getenv("VDOS_AUTO_PAUSE_ON_PROJECT_END", "true").strip().lower()
            if env_auto_pause in {"1", "true", "yes", "on"}:
                self._auto_pause_enabled = True
            elif env_auto_pause in {"0", "false", "no", "off"}:
                self._auto_pause_enabled = False
            else:
                logger.warning(
                    f"Invalid VDOS_AUTO_PAUSE_ON_PROJECT_END value '{env_auto_pause}', defaulting to enabled"
                )
                self._auto_pause_enabled = True
            logger.info(
                f"Auto-pause on project end initialized: {'enabled' if self._auto_pause_enabled else 'disabled'}"
            )
        except Exception as exc:
            logger.error(f"Failed to parse auto-pause configuration, defaulting to enabled: {exc}")
            self._auto_pause_enabled = True

        # Initialise DB and runtime state
        self.state.initialize_database()
        self._bootstrap_channels()
        self.worker_runtime_manager.sync_runtimes(self.list_people())
        self._sync_virtual_workers()

    def _sync_virtual_workers(self) -> None:
        """
        Synchronize VirtualWorker instances with database personas.
        
        Creates VirtualWorker instances for any personas that don't have one yet.
        This is called during initialization and when personas are loaded.
        
        Only creates VirtualWorkers if the planner supports the new interface
        (has generate_with_messages method).
        """
        # Check if planner supports new interface
        if not hasattr(self.planner, 'generate_with_messages'):
            logger.info("Planner does not support generate_with_messages, skipping VirtualWorker creation")
            return
        
        # Lazy import to avoid circular dependency
        from virtualoffice.virtualWorkers.virtual_worker import VirtualWorker
            
        people = self.list_people()
        for person in people:
            if person.id not in self.workers:
                # Reconstruct persona from PersonRead
                persona = self._to_persona_from_person_read(person)
                schedule = person.schedule or []
                
                # Create VirtualWorker instance
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
                self.workers[person.id] = worker

    def _to_persona_from_person_read(self, person: PersonRead) -> WorkerPersona:
        """Convert PersonRead back to WorkerPersona."""
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

    def _reset_tick_sends(self) -> None:
        """Delegate to CommunicationHub."""
        self.communication_hub.reset_tick_sends()

    def _can_send(
        self, *, tick: int, channel: str, sender: str, recipient_key: tuple, subject: str | None, body: str
    ) -> bool:
        """Delegate to CommunicationHub."""
        return self.communication_hub.can_send(
            tick=tick, channel=channel, sender=sender, recipient_key=recipient_key, subject=subject, body=body
        )

    # --- Scheduled comms parsing/dispatch ---
    def _schedule_from_hourly_plan(self, person: PersonRead, plan_text: str, current_tick: int) -> None:
        """Delegate to CommunicationHub."""
        self.communication_hub.schedule_from_hourly_plan(
            person=person, plan_text=plan_text, current_tick=current_tick, hours_per_day=self.hours_per_day
        )

    def _get_thread_id_for_reply(self, person_id: int, email_id: str) -> tuple[str | None, str | None]:
        """Delegate to CommunicationHub."""
        return self.communication_hub.get_thread_id_for_reply(person_id, email_id)

    def _dispatch_scheduled(
        self, person: PersonRead, current_tick: int, people_by_id: dict[int, PersonRead]
    ) -> tuple[int, int]:
        """Delegate to CommunicationHub."""
        return self.communication_hub.dispatch_scheduled(
            person=person,
            current_tick=current_tick,
            people_by_id=people_by_id,
            get_current_week_fn=self._get_current_week,
            get_active_projects_fn=self._get_all_active_projects_for_person,
            get_project_chat_room_fn=self.get_active_project_chat_room,
        )

    def _schedule_direct_comm(self, person_id: int, tick: int, channel: str, target: str, payload: str) -> None:
        """Delegate to CommunicationHub."""
        self.communication_hub.schedule_direct_comm(person_id, tick, channel, target, payload)

    def _get_current_week(self) -> int:
        """Calculate the current week from simulation state."""
        status = self.state.get_current_state()
        if status.current_tick <= 0:
            return 1
        current_day = (status.current_tick - 1) // max(1, self.hours_per_day)
        return max(1, (current_day // 5) + 1)

    def _planner_context_summary(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        worker = kwargs.get("worker")
        if worker is not None:
            summary["worker"] = getattr(worker, "name", worker)
        department_head = kwargs.get("department_head")
        if department_head is not None:
            summary["department_head"] = getattr(department_head, "name", department_head)
        project_name = kwargs.get("project_name")
        if project_name:
            summary["project_name"] = project_name
        day_index = kwargs.get("day_index")
        if day_index is not None:
            summary["day_index"] = day_index
        tick = kwargs.get("tick")
        if tick is not None:
            summary["tick"] = tick
        model_hint = kwargs.get("model_hint")
        if model_hint:
            summary["model_hint"] = model_hint
        return summary

    def get_planner_metrics(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._planner_metrics_lock:
            data = list(self._planner_metrics)
        if limit <= 0:
            return data
        return data[-limit:]

    # ------------------------------------------------------------------
    # People management
    # ------------------------------------------------------------------
    def create_person(self, payload: PersonCreate) -> PersonRead:
        # Validate name uniqueness
        existing_people = self.list_people()
        for person in existing_people:
            if person.name.strip().lower() == payload.name.strip().lower():
                raise ValueError(
                    f"Duplicate name '{payload.name}'. "
                    f"A person with this name already exists (ID: {person.id}, Role: {person.role}). "
                    "Please use a unique name to avoid confusion in team communications."
                )

        # Validate Korean names for Korean locale
        locale = os.getenv("VDOS_LOCALE", "en").strip().lower()
        if locale == "ko":
            import re

            # Check if name contains Korean characters (Hangul)
            if not re.search(r"[\uac00-\ud7af]", payload.name):
                raise ValueError(
                    f"Korean locale requires Korean name, but got: '{payload.name}'. "
                    "Please use a Korean name (e.g., '김지훈' instead of 'Kim Jihoon')."
                )

        persona = self._to_persona(payload)
        schedule = [ScheduleBlock(block.start, block.end, block.activity) for block in payload.schedule or []]
        persona_markdown = build_worker_markdown(
            persona,
            schedule=schedule,
            planning_guidelines=payload.planning_guidelines,
            event_playbook=payload.event_playbook,
            statuses=payload.statuses,
        )
        # Persist person and schedule via repository
        person_id = self.people_repo.insert(payload, persona_markdown, schedule)

        self.email_gateway.ensure_mailbox(payload.email_address, payload.name)
        self.chat_gateway.ensure_user(payload.chat_handle, payload.name)

        person = self.get_person(person_id)
        self.worker_runtime_manager.get_runtime(person)

        # Create VirtualWorker instance if planner supports new interface
        if hasattr(self.planner, 'generate_with_messages'):
            # Lazy import to avoid circular dependency
            from virtualoffice.virtualWorkers.virtual_worker import VirtualWorker
            
            worker = VirtualWorker(
                persona=persona,
                prompt_manager=self.prompt_manager,
                context_builder=self.context_builder,
                planner=self.planner,
                schedule=schedule,
                planning_guidelines=payload.planning_guidelines,
                event_playbook=payload.event_playbook,
                statuses=payload.statuses,
            )
            self.workers[person.id] = worker

        return person

    def list_people(self) -> List[PersonRead]:
        return self.people_repo.list_people()

    def get_person(self, person_id: int) -> PersonRead:
        return self.people_repo.get_person(person_id)

    def delete_person_by_name(self, name: str) -> bool:
        # Runtime will be removed on next sync_runtimes call
        return self.people_repo.delete_by_name(name)

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
            if self._planner_strict:
                logger.error(
                    "Planner %s using %s failed after %.2fs and strict mode is enabled: %s",
                    method_name,
                    planner_name,
                    duration,
                    exc,
                )
                raise RuntimeError(f"Planning failed ({method_name}): {exc}") from exc
            logger.warning(
                "Planner %s using %s failed after %.2fs: %s. Falling back to stub planner.",
                method_name,
                planner_name,
                duration,
                exc,
            )
            fallback_method = getattr(self._stub_planner, method_name)
            fallback_start = time.perf_counter()
            fallback_result = fallback_method(**kwargs)
            fallback_duration = time.perf_counter() - fallback_start
            logger.info(
                "Stub planner %s succeeded in %.2fs (model=%s)",
                fallback_name,
                fallback_duration,
                getattr(fallback_result, "model_used", "vdos-stub"),
            )
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": method_name,
                "planner": planner_name,
                "result_planner": fallback_name,
                "model": getattr(fallback_result, "model_used", "vdos-stub"),
                "duration_ms": round(duration * 1000, 2),
                "fallback_duration_ms": round(fallback_duration * 1000, 2),
                "fallback": True,
                "error": str(exc),
                "context": context,
            }
            with self._planner_metrics_lock:
                self._planner_metrics.append(entry)
            return fallback_result
        else:
            duration = time.perf_counter() - start
            logger.info(
                "Planner %s using %s succeeded in %.2fs (model=%s)",
                method_name,
                planner_name,
                duration,
                getattr(result, "model_used", "unknown"),
            )
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": method_name,
                "planner": planner_name,
                "result_planner": planner_name,
                "model": getattr(result, "model_used", "unknown"),
                "duration_ms": round(duration * 1000, 2),
                "fallback_duration_ms": None,
                "fallback": False,
                "context": context,
            }
            with self._planner_metrics_lock:
                self._planner_metrics.append(entry)
            return result

    # ------------------------------------------------------------------
    def get_project_plan(self) -> dict[str, Any] | None:
        """Delegate to ProjectManager."""
        plan = self.project_manager.get_project_plan()
        if plan:
            self.project_duration_weeks = plan["duration_weeks"]
        return plan

    def get_active_projects_with_assignments(self, current_week: int | None = None) -> list[dict[str, Any]]:
        """Delegate to ProjectManager."""
        if current_week is None:
            # Calculate current week from simulation state
            status = self.state.get_current_state()
            current_day = (status.current_tick - 1) // self.hours_per_day if status.current_tick > 0 else 0
            current_week = (current_day // 5) + 1  # 1-indexed weeks, assuming 5-day work weeks

        return self.project_manager.get_active_projects_with_assignments(current_week)

    def create_project_chat_room(self, project_id: int, project_name: str, team_members: list[PersonRead]) -> str:
        """Delegate to ProjectManager."""
        return self.project_manager.create_project_chat_room(project_id, project_name, team_members, self.chat_gateway)

    def get_active_project_chat_room(self, project_id: int) -> str | None:
        """Delegate to ProjectManager."""
        return self.project_manager.get_active_project_chat_room(project_id)

    def archive_project_chat_room(self, project_id: int) -> bool:
        """Delegate to ProjectManager."""
        return self.project_manager.archive_project_chat_room(project_id)

    def list_worker_plans(
        self,
        person_id: int,
        plan_type: str | None = None,
        limit: int | None = None,
    ) -> List[dict[str, Any]]:
        self.get_person(person_id)
        return self.plan_store.list_worker_plans(person_id, plan_type, limit)

    def list_daily_reports(
        self,
        person_id: int,
        day_index: int | None = None,
        limit: int | None = None,
    ) -> List[dict[str, Any]]:
        self.get_person(person_id)
        return self.report_store.list_daily_reports(person_id, day_index, limit)

    def list_simulation_reports(self, limit: int | None = None) -> List[dict[str, Any]]:
        return self.report_store.list_simulation_reports(limit)

    def _initialise_project_plan(self, request: SimulationStartRequest, team: Sequence[PersonRead]) -> None:
        if not team:
            raise RuntimeError("Cannot initialise project plan without any personas")
        self.worker_runtime_manager.sync_runtimes(team)
        department_head = self._resolve_department_head(team, request.department_head_name)

        # Multi-project mode
        if request.projects:
            team_by_id = {p.id: p for p in team}
            for proj_timeline in request.projects:
                # Determine team for this project
                if proj_timeline.assigned_person_ids:
                    proj_team = [team_by_id[pid] for pid in proj_timeline.assigned_person_ids if pid in team_by_id]
                else:
                    proj_team = list(team)  # All team members by default

                if not proj_team:
                    continue

                try:
                    plan_result = self._call_planner(
                        "generate_project_plan",
                        department_head=department_head,
                        project_name=proj_timeline.project_name,
                        project_summary=proj_timeline.project_summary,
                        duration_weeks=proj_timeline.duration_weeks,
                        team=proj_team,
                        model_hint=request.model_hint,
                    )
                except PlanningError as exc:
                    raise RuntimeError(
                        f"Unable to generate project plan for '{proj_timeline.project_name}': {exc}"
                    ) from exc

                project_plan = self._store_project_plan(
                    project_name=proj_timeline.project_name,
                    project_summary=proj_timeline.project_summary,
                    plan_result=plan_result,
                    generated_by=department_head.id if department_head else None,
                    duration_weeks=proj_timeline.duration_weeks,
                    start_week=proj_timeline.start_week,
                    assigned_person_ids=proj_timeline.assigned_person_ids,
                )

                # Create project chat room
                try:
                    room_slug = self.create_project_chat_room(
                        project_id=project_plan["id"], project_name=proj_timeline.project_name, team_members=proj_team
                    )
                    logger.info(f"Created project chat room '{room_slug}' for project '{proj_timeline.project_name}'")
                except Exception as exc:
                    logger.warning(f"Failed to create chat room for project '{proj_timeline.project_name}': {exc}")

            # For multi-project mode, skip ALL initial person planning to avoid timeout
            # All daily/hourly plans will be generated lazily on first advance()
            # This makes initialization instant by only generating project plans (2-3 GPT calls)
            pass
        else:
            # Single-project mode (backward compatible)
            try:
                plan_result = self._call_planner(
                    "generate_project_plan",
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

            # Create project chat room
            try:
                room_slug = self.create_project_chat_room(
                    project_id=plan_record["id"], project_name=request.project_name, team_members=list(team)
                )
                logger.info(f"Created project chat room '{room_slug}' for project '{request.project_name}'")
            except Exception as exc:
                logger.warning(f"Failed to create chat room for project '{request.project_name}': {exc}")
            for person in team:
                daily_result = self._generate_daily_plan(person, plan_record, day_index=0)
                self._generate_hourly_plan(
                    person,
                    plan_record,
                    daily_result.content,
                    tick=0,
                    reason="initialisation",
                )

    def _get_active_project_for_person(self, person_id: int, week: int) -> dict[str, Any] | None:
        """Delegate to ProjectManager."""
        return self.project_manager.get_active_project_for_person(person_id, week)

    def _get_all_active_projects_for_person(self, person_id: int, week: int) -> list[dict[str, Any]]:
        """Delegate to ProjectManager."""
        return self.project_manager.get_active_projects_for_person(person_id, week)

    def _resolve_department_head(self, people: Sequence[PersonRead], requested_name: str | None) -> PersonRead:
        if requested_name:
            for person in people:
                if person.name == requested_name:
                    return person
            raise RuntimeError(f"Department head '{requested_name}' not found among registered personas.")
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
        start_week: int = 1,
        assigned_person_ids: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        """Delegate to ProjectManager."""
        plan = self.project_manager.store_project_plan(
            project_name=project_name,
            project_summary=project_summary,
            plan_result=plan_result,
            generated_by=generated_by,
            duration_weeks=duration_weeks,
            start_week=start_week,
            assigned_person_ids=assigned_person_ids,
        )
        self.project_duration_weeks = duration_weeks
        return plan

    def _generate_daily_plan(self, person: PersonRead, project_plan: dict[str, Any], day_index: int) -> PlanResult:
        # Get all active people for team roster
        team = self._get_active_people()

        # Use VirtualWorker if available, otherwise fall back to direct planner call
        worker = self.workers.get(person.id)
        if worker:
            # Lazy import to avoid circular dependency
            from virtualoffice.virtualWorkers.context_classes import DailyPlanningContext
            
            # Build DailyPlanningContext for VirtualWorker
            daily_context = DailyPlanningContext(
                project_plan=project_plan["plan"],
                day_index=day_index,
                duration_weeks=self.project_duration_weeks,
                team=team,
                locale=self._locale,
                model_hint=self._planner_model_hint,
            )
            try:
                result = worker.plan_daily(daily_context)
            except Exception as exc:
                raise RuntimeError(f"Unable to generate daily plan for {person.name}: {exc}") from exc
        else:
            # Fallback to direct planner call for backward compatibility
            try:
                result = self._call_planner(
                    "generate_daily_plan",
                    worker=person,
                    project_plan=project_plan["plan"],
                    day_index=day_index,
                    duration_weeks=self.project_duration_weeks,
                    team=team,
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

    def _generate_hourly_plans_parallel(
        self,
        planning_tasks: list[
            tuple[PersonRead, dict[str, Any], str, int, str, list[str] | None, list[dict[str, Any]] | None]
        ],
    ) -> list[tuple[PersonRead, PlanResult]]:
        """
        Generate hourly plans for multiple workers in parallel.

        Args:
            planning_tasks: List of (person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects)

        Returns:
            List of (person, PlanResult) tuples in same order as input
        """
        if not self._planning_executor or len(planning_tasks) <= 1:
            # Fall back to sequential planning
            results = []
            for task in planning_tasks:
                person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects = task
                try:
                    result = self._generate_hourly_plan(
                        person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects
                    )
                    results.append((person, result))
                except Exception as exc:
                    logger.error(f"Sequential planning failed for {person.name}: {exc}")
                    results.append((person, PlanResult(content="", model_used="error", tokens_used=0)))
            return results

        # Submit all planning tasks in parallel
        futures = []
        for task in planning_tasks:
            person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects = task
            future = self._planning_executor.submit(
                self._generate_hourly_plan,
                person,
                project_plan,
                daily_plan_text,
                tick,
                reason,
                adjustments,
                all_active_projects,
            )
            futures.append((person, future))

        # Collect results in order
        results = []
        for person, future in futures:
            try:
                result = future.result(timeout=240)  # 4 minute timeout per plan
                results.append((person, result))
            except Exception as exc:
                logger.error(f"Parallel planning failed for {person.name}: {exc}")
                # Return empty plan to maintain order
                results.append((person, PlanResult(content="", model_used="error", tokens_used=0)))

        return results

    def _generate_hourly_plan(
        self,
        person: PersonRead,
        project_plan: dict[str, Any],
        daily_plan_text: str,
        tick: int,
        reason: str,
        adjustments: list[str] | None = None,
        all_active_projects: list[dict[str, Any]] | None = None,
    ) -> PlanResult:
        # Get all active people for team roster
        team = self._get_active_people()

        # Get recent emails for this person (for threading context)
        recent_emails = self.communication_hub.get_recent_emails_for_person(person.id, limit=10)

        # Use VirtualWorker if available, otherwise fall back to direct planner call
        worker = self.workers.get(person.id)
        if worker:
            # Lazy import to avoid circular dependency
            from virtualoffice.virtualWorkers.context_classes import PlanningContext
            
            # Build PlanningContext for VirtualWorker
            planning_context = PlanningContext(
                project_plan=project_plan["plan"],
                daily_plan=daily_plan_text,
                tick=tick,
                reason=reason,
                team=team,
                recent_emails=recent_emails,
                all_active_projects=all_active_projects,
                locale=self._locale,
                model_hint=self._planner_model_hint,
            )
            try:
                result = worker.plan_next_hour(planning_context)
            except Exception as exc:
                raise RuntimeError(f"Unable to generate hourly plan for {person.name}: {exc}") from exc
        else:
            # Fallback to direct planner call for backward compatibility
            try:
                result = self._call_planner(
                    "generate_hourly_plan",
                    worker=person,
                    project_plan=project_plan["plan"],
                    daily_plan=daily_plan_text,
                    tick=tick,
                    context_reason=reason,
                    team=team,
                    model_hint=self._planner_model_hint,
                    all_active_projects=all_active_projects,
                    recent_emails=recent_emails,
                )
            except PlanningError as exc:
                raise RuntimeError(f"Unable to generate hourly plan for {person.name}: {exc}") from exc

        context = f"reason={reason}"
        content_result = result
        if adjustments:
            bullets = "\n".join(f"- {item}" for item in adjustments)
            loc_manager = get_current_locale_manager()
            adjustments_header = loc_manager.get_text("live_collaboration_adjustments")
            content = f"{result.content}\n\n{adjustments_header}:\n{bullets}"
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
        # Ensure person exists
        self.get_person(person_id)
        return self.plan_store.put_worker_plan(person_id, tick, plan_type, result, context)

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
        return self.plan_store.get_worker_plan(person_id, plan_type, tick, exact_tick)

    def _ensure_daily_plan(self, person: PersonRead, day_index: int, project_plan: dict[str, Any]) -> str:
        existing = self._fetch_worker_plan(person.id, "daily", tick=day_index, exact_tick=True)
        if existing:
            return existing["content"]
        result = self._generate_daily_plan(person, project_plan, day_index)
        return result.content

    def _summarise_plan(self, plan_text: str, max_lines: int = 4) -> str:
        lines = [line.strip() for line in plan_text.splitlines() if line.strip()]
        if not lines:
            return "No plan provided yet."
        # Drop placeholder headers and meta lines
        filtered: list[str] = []
        for line in lines:
            if (line.startswith("[") and line.endswith("]")) or line.startswith("#") or line.startswith("```"):
                continue
            if line.startswith(("Tick:", "Worker:", "Reason:", "Outline:")):
                continue
            filtered.append(line)
        if not filtered:
            filtered = lines
        return "\n".join(filtered[:max_lines])

    def _fetch_hourly_summary(self, person_id: int, hour_index: int) -> dict[str, Any] | None:
        return self.report_store.get_hourly_summary(person_id, hour_index)

    def _store_hourly_summary(
        self,
        person_id: int,
        hour_index: int,
        result: PlanResult,
    ) -> dict[str, Any]:
        return self.report_store.put_hourly_summary(person_id, hour_index, result)

    def _generate_hourly_summary(
        self,
        person: PersonRead,
        hour_index: int,
    ) -> dict[str, Any]:
        """Generate a summary for a completed hour."""
        existing = self._fetch_hourly_summary(person.id, hour_index)
        if existing:
            return existing

        # Get all hourly plans for this hour
        start_tick = hour_index * 60 + 1
        end_tick = (hour_index + 1) * 60
        hourly_rows = self.plan_store.list_hourly_plans_in_range(person.id, start_tick, end_tick)

        if not hourly_rows:
            # No plans for this hour, skip summary
            return {
                "person_id": person.id,
                "hour_index": hour_index,
                "summary": "",
                "model_used": "none",
                "tokens_used": 0,
            }

        hourly_plans = "\n".join(f"Tick {row['tick']}: {row['content'][:200]}..." for row in hourly_rows)

        try:
            result = self._call_planner(
                "generate_hourly_summary",
                worker=person,
                hour_index=hour_index,
                hourly_plans=hourly_plans,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            logger.warning(f"Unable to generate hourly summary for {person.name} hour {hour_index}: {exc}")
            # Store a stub summary instead of failing
            result = PlanResult(content=f"Hour {hour_index + 1} activities", model_used="stub", tokens_used=0)

        return self._store_hourly_summary(person_id=person.id, hour_index=hour_index, result=result)

    def _fetch_daily_report(self, person_id: int, day_index: int) -> dict[str, Any] | None:
        return self.report_store.get_daily_report(person_id, day_index)

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

        # Use hourly summaries instead of all tick logs
        start_hour = day_index * (self.hours_per_day // 60)
        end_hour = (day_index + 1) * (self.hours_per_day // 60)
        # Collect any pre-existing hourly summaries for the day
        # (leave generation fallback below unchanged)
        with get_connection() as conn:
            summary_rows = conn.execute(
                "SELECT hour_index, summary FROM hourly_summaries WHERE person_id = ? AND hour_index BETWEEN ? AND ? ORDER BY hour_index",
                (person.id, start_hour, end_hour - 1),
            ).fetchall()

        if summary_rows:
            hourly_summary = "\n".join(f"Hour {row['hour_index'] + 1}: {row['summary']}" for row in summary_rows)
        else:
            # Fallback: generate hourly summaries now if they don't exist
            hourly_summary_lines = []
            for h in range(start_hour, end_hour):
                summary = self._generate_hourly_summary(person, h)
                if summary.get("summary"):
                    hourly_summary_lines.append(f"Hour {h + 1}: {summary['summary']}")
            hourly_summary = (
                "\n".join(hourly_summary_lines)
                if hourly_summary_lines
                else get_current_locale_manager().get_text("no_hourly_activities")
            )
        schedule_blocks = [ScheduleBlock(block.start, block.end, block.activity) for block in person.schedule or []]
        minute_schedule = render_minute_schedule(schedule_blocks)

        # Use VirtualWorker if available, otherwise fall back to direct planner call
        worker = self.workers.get(person.id)
        if worker:
            # Lazy import to avoid circular dependency
            from virtualoffice.virtualWorkers.context_classes import ReportContext
            
            # Build ReportContext for VirtualWorker
            report_context = ReportContext(
                project_plan=project_plan["plan"],
                day_index=day_index,
                daily_plan=daily_plan_text,
                hourly_log=hourly_summary,
                minute_schedule=minute_schedule,
                locale=self._locale,
                model_hint=self._planner_model_hint,
            )
            try:
                result = worker.generate_daily_report(report_context)
            except Exception as exc:
                raise RuntimeError(f"Unable to generate daily report for {person.name}: {exc}") from exc
        else:
            # Fallback to direct planner call for backward compatibility
            try:
                result = self._call_planner(
                    "generate_daily_report",
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
        return self.report_store.put_daily_report(person_id, day_index, schedule_outline, result)

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
            # Limit tick log to major milestones only (every 480 ticks = 1 day for 8-hour days)
            tick_rows = conn.execute(
                "SELECT tick, reason FROM tick_log WHERE tick % 480 = 1 OR reason IN ('kickof', 'manual') ORDER BY id LIMIT 100",
                (),
            ).fetchall()

        # Get events from EventSystem instead of direct database query
        event_dicts = self.event_system.list_events()

        # Summarize tick log
        if len(tick_rows) > 50:
            tick_summary = f"Major milestones ({len(tick_rows)} key ticks):\n"
            tick_summary += "\n".join(f"Tick {row['tick']}: {row['reason']}" for row in tick_rows[:25])
            tick_summary += f"\n... ({len(tick_rows) - 25} more ticks) ..."
        else:
            tick_summary = "\n".join(f"Tick {row['tick']}: {row['reason']}" for row in tick_rows)

        # Summarize events concisely
        event_summary = f"Total events: {len(event_dicts)}\n"
        event_summary += (
            "\n".join(
                f"- {evt['type']} (project={evt['project_id']}, tick={evt['at_tick']})"
                for evt in event_dicts[:20]  # Limit to first 20
            )
            if event_dicts
            else "No events logged."
        )

        # Use daily report summaries (just the first 100 chars of each)
        daily_reports_full = self.list_daily_reports_for_summary()
        if len(daily_reports_full) > 1000:  # If very long, summarize further
            daily_reports = f"Daily reports summary ({len(daily_reports_full.splitlines())} days):\n"
            daily_reports += "\n".join(line[:150] for line in daily_reports_full.splitlines()[:50])
            daily_reports += f"\n... ({len(daily_reports_full.splitlines()) - 50} more days) ..."
        else:
            daily_reports = daily_reports_full

        try:
            result = self._call_planner(
                "generate_simulation_report",
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
        return self.report_store.list_daily_reports_for_summary()

    def _store_simulation_report(self, total_ticks: int, result: PlanResult) -> dict[str, Any]:
        return self.report_store.put_simulation_report(total_ticks, result)

    def _row_to_simulation_report(self, row) -> dict[str, Any]:
        # Kept for backward compatibility; unused after extraction.
        return None if row is None else {
            "id": row["id"],
            "report": row["report"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "total_ticks": row["total_ticks"],
            "created_at": row["created_at"],
        }

    def get_token_usage(self) -> dict[str, int]:
        return self.report_store.get_token_usage()

    # ------------------------------------------------------------------
    # Simulation control
    # ------------------------------------------------------------------
    def get_state(self) -> SimulationState:
        status = self.state.get_current_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self.tick_manager.format_sim_time(status.current_tick),
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
            # Validate that either single-project or multi-project fields are provided
            if request.projects:
                # Multi-project mode
                if request.total_duration_weeks:
                    self.project_duration_weeks = request.total_duration_weeks
                else:
                    # Calculate total duration from projects
                    max_end_week = max(p.start_week + p.duration_weeks - 1 for p in request.projects)
                    self.project_duration_weeks = max_end_week
            else:
                # Single-project mode - require project_name and project_summary
                if not request.project_name or not request.project_summary:
                    raise RuntimeError(
                        "Either 'projects' or both 'project_name' and 'project_summary' must be provided"
                    )
                self.project_duration_weeks = request.duration_weeks
            self._planner_model_hint = request.model_hint
            self._initialise_project_plan(request, active_people)
        self.state.set_running(True)
        self.tick_manager.set_base_datetime()
        self.worker_runtime_manager.sync_runtimes(active_people)
        # Schedule a kickoff chat/email at the first working minute for each worker
        try:
            for person in active_people:
                start_tick_of_day, _ = self.tick_manager.get_work_hours_ticks(person.id)

                base_tick = 1  # day 1 start
                kickoff_tick = base_tick + max(0, start_tick_of_day) + 5  # +5 minutes
                # pick a collaborator to target
                recipients = self._select_collaborators(person, active_people)
                target = recipients[0] if recipients else None
                if target:
                    if self._locale == "ko":
                        self._schedule_direct_comm(
                            person.id,
                            kickoff_tick,
                            "chat",
                            target.chat_handle,
                            "좋은 아침입니다! 오늘 우선순위 빠르게 맞춰볼까요?",
                        )
                        self._schedule_direct_comm(
                            person.id,
                            kickoff_tick + 30,
                            "email",
                            target.email_address,
                            "제목: 킥오프\n본문: 오늘 진행할 작업 정리했습니다 — 문의사항 있으면 알려주세요.",
                        )
                    else:
                        self._schedule_direct_comm(
                            person.id, kickoff_tick, "chat", target.chat_handle, "Morning! Quick sync on priorities?"
                        )
                        self._schedule_direct_comm(
                            person.id,
                            kickoff_tick + 30,
                            "email",
                            target.email_address,
                            "Subject: Quick kickoff\nBody: Lining up tasks for today — ping me with blockers.",
                        )
        except Exception:
            pass
        status = self.state.get_current_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self.tick_manager.format_sim_time(status.current_tick),
        )

    def stop(self) -> SimulationState:
        self.stop_auto_ticks()
        status = self.state.get_current_state()
        if status.is_running:
            project_plan = self.get_project_plan()
            if project_plan is not None:
                self._generate_simulation_report(project_plan, total_ticks=status.current_tick)
        self.state.set_running(False)
        self._active_person_ids = None
        status = self.state.get_current_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self.tick_manager.format_sim_time(status.current_tick),
        )

    def start_auto_ticks(self) -> SimulationState:
        status = self.state.get_current_state()
        # Start auto-tick via tick manager
        self.tick_manager.start_auto_tick(
            is_running=status.is_running,
            advance_callback=lambda: self.advance(1, "auto"),
            state_manager=self.state,
            get_active_projects_callback=self.get_active_projects_with_assignments,
            archive_chat_room_callback=self.archive_project_chat_room,
            auto_pause_enabled=getattr(self, "_auto_pause_enabled", True),
        )
        status = self.state.get_current_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self.tick_manager.format_sim_time(status.current_tick),
        )

    def stop_auto_ticks(self) -> SimulationState:
        self.tick_manager.stop_auto_tick(self.state)
        status = self.state.get_current_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self.tick_manager.format_sim_time(status.current_tick),
        )

    def set_auto_pause(self, enabled: bool) -> dict[str, Any]:
        """Toggle auto-pause setting at runtime and return comprehensive status information.

        Args:
            enabled: Whether to enable auto-pause functionality

        Returns:
            Dictionary containing updated auto-pause status and configuration
        """
        try:
            # Update session-level configuration
            self._auto_pause_enabled = enabled

            # Log the configuration change
            logger.info(f"Auto-pause setting updated to: {'enabled' if enabled else 'disabled'}")

            # Return comprehensive status information
            return self.get_auto_pause_status()

        except Exception as exc:
            logger.error(f"Failed to update auto-pause setting: {exc}")
            return {
                "auto_pause_enabled": getattr(self, "_auto_pause_enabled", None),
                "error": str(exc),
                "reason": f"Failed to update auto-pause setting: {exc}",
            }

    def get_auto_pause_status(self) -> dict[str, Any]:
        """Get information about auto-pause status and reasons with enhanced project lifecycle calculations."""
        # Check session-level setting first, then fall back to environment variable
        if hasattr(self, "_auto_pause_enabled"):
            auto_pause_enabled = self._auto_pause_enabled
        else:
            auto_pause_enabled = os.getenv("VDOS_AUTO_PAUSE_ON_PROJECT_END", "true").lower() == "true"

        if not auto_pause_enabled:
            return {
                "auto_pause_enabled": False,
                "should_pause": False,
                "active_projects_count": 0,
                "future_projects_count": 0,
                "current_week": 0,
                "reason": "Auto-pause on project end is disabled",
            }

        try:
            # Enhanced current week calculation with validation
            status = self.state.get_current_state()
            if status.current_tick <= 0:
                current_day = 0
                current_week = 1
            else:
                # Ensure hours_per_day is at least 1 to prevent division by zero
                hours_per_day = max(1, self.hours_per_day)
                current_day = (status.current_tick - 1) // hours_per_day
                current_week = max(1, (current_day // 5) + 1)

            # Get active projects using verified calculation (start_week <= current_week <= end_week)
            active_projects = self.get_active_projects_with_assignments(current_week)

            # Check for future projects with enhanced validation
            with get_connection() as conn:
                future_projects = conn.execute(
                    "SELECT COUNT(*) as count FROM project_plans WHERE start_week > ?", (current_week,)
                ).fetchone()

            future_count = future_projects["count"] if future_projects else 0
            should_pause = len(active_projects) == 0 and future_count == 0

            # Enhanced reason with comprehensive project information
            if should_pause:
                # Get completed projects for detailed logging
                with get_connection() as conn:
                    completed_projects = conn.execute(
                        """SELECT project_name, start_week, duration_weeks,
                           (start_week + duration_weeks - 1) as end_week
                           FROM project_plans
                           WHERE (start_week + duration_weeks - 1) < ?
                           ORDER BY end_week DESC""",
                        (current_week,),
                    ).fetchall()

                completed_count = len(completed_projects)
                reason = f"All {completed_count} project(s) completed, no future projects (week {current_week}, tick {status.current_tick})"

                # Log the auto-pause condition for debugging
                logger.debug(f"Auto-pause condition met: {reason}")

            elif len(active_projects) > 0:
                active_names = [p.get("project_name", "Unknown") for p in active_projects[:3]]
                reason = f"{len(active_projects)} active project(s) in week {current_week}: {', '.join(active_names)}{'...' if len(active_projects) > 3 else ''}"

            else:
                # Get next future project details
                with get_connection() as conn:
                    next_future = conn.execute(
                        """SELECT project_name, start_week FROM project_plans
                           WHERE start_week > ? ORDER BY start_week ASC LIMIT 1""",
                        (current_week,),
                    ).fetchone()

                next_project_info = (
                    f" (next: '{next_future['project_name']}' in week {next_future['start_week']})"
                    if next_future
                    else ""
                )
                reason = f"No active projects in week {current_week}, but {future_count} future project(s) exist{next_project_info}"

            return {
                "auto_pause_enabled": True,
                "should_pause": should_pause,
                "active_projects_count": len(active_projects),
                "future_projects_count": future_count,
                "current_week": current_week,
                "current_tick": status.current_tick,
                "current_day": current_day,
                "reason": reason,
            }

        except Exception as exc:
            logger.error(f"Failed to check project status for auto-pause: {exc}")
            return {
                "auto_pause_enabled": True,
                "should_pause": False,
                "active_projects_count": 0,
                "future_projects_count": 0,
                "current_week": 0,
                "current_tick": 0,
                "current_day": 0,
                "error": str(exc),
                "reason": f"Failed to check project status: {exc}",
            }

    def set_tick_interval(self, interval_seconds: float) -> dict[str, Any]:
        """Update the auto-tick interval (in seconds). Use 0 for maximum speed."""
        self.tick_manager.set_tick_interval(interval_seconds)
        if interval_seconds == 0:
            logger.info("Tick interval set to 0s (maximum speed - no delay between ticks)")
        else:
            logger.info(f"Tick interval updated to {interval_seconds}s")
        return {
            "tick_interval_seconds": self.tick_manager.get_tick_interval(),
            "message": f"Tick interval set to {interval_seconds}s" + (" (max speed)" if interval_seconds == 0 else ""),
        }

    def get_tick_interval(self) -> float:
        """Get the current auto-tick interval (in seconds)."""
        return self.tick_manager.get_tick_interval()

    def advance(self, ticks: int, reason: str) -> SimulationAdvanceResult:
        with self.tick_manager.get_advance_lock():
            status = self.state.get_current_state()
            if not status.is_running:
                raise RuntimeError("Simulation is not running; call start first")
            if ticks <= 0:
                raise ValueError("Ticks must be positive")

            project_plan = self.get_project_plan()
            if project_plan is None:
                raise RuntimeError(
                    "Project plan is not initialised; start the simulation with project details before advancing."
                )

            people = self._get_active_people()
            if not people:
                raise RuntimeError("Cannot advance simulation without any active personas")
            self.worker_runtime_manager.sync_runtimes(people)
            people_by_id = {person.id: person for person in people}

            # Calculate current week for multi-project support
            current_day = (status.current_tick - 1) // self.hours_per_day if status.current_tick > 0 else 0
            current_week = (current_day // 5) + 1  # 1-indexed weeks, assuming 5-day work weeks

            emails_sent = 0
            chats_sent = 0

            for _ in range(ticks):
                status.current_tick += 1
                self._reset_tick_sends()
                self.state.update_tick(status.current_tick, reason)
                self._refresh_status_overrides(status.current_tick)
                event_adjustments, _ = self._maybe_generate_events(people, status.current_tick, project_plan)
                day_index = (status.current_tick - 1) // self.hours_per_day
                tick_of_day = (status.current_tick - 1) % self.hours_per_day if self.hours_per_day > 0 else 0
                # Prune stale plan-attempt counters (keep only this minute)
                if self._hourly_plan_attempts:
                    keys = list(self._hourly_plan_attempts.keys())
                    for key in keys:
                        if key[1] != day_index or key[2] != tick_of_day:
                            self._hourly_plan_attempts.pop(key, None)

                # PHASE 1: Collect planning tasks and prepare context
                planning_tasks = []
                person_contexts = {}

                for person in people:
                    runtime = self.worker_runtime_manager.get_runtime(person)
                    incoming = runtime.drain()
                    working = self.tick_manager.is_within_work_hours(person, status.current_tick)
                    adjustments: list[str] = list(event_adjustments.get(person.id, []))
                    override = self.state.get_status_overrides().get(person.id)
                    if override and override[0] == "SickLeave":
                        incoming = []
                        adjustments.append("Observe sick leave and hold tasks until recovered.")
                    if not working:
                        if incoming:
                            for message in incoming:
                                runtime.queue(message)
                        for note in adjustments:
                            reminder = _InboundMessage(
                                sender_id=0,
                                sender_name="Simulation Manager",
                                subject=get_current_locale_manager().get_text("pending_adjustment"),
                                summary=note,
                                action_item=note,
                                message_type="event",
                                channel="system",
                                tick=status.current_tick,
                            )
                            runtime.queue(reminder)
                        logger.info("Skipping planning for %s at tick %s (off hours)", person.name, status.current_tick)
                        continue
                    # Dispatch any scheduled comms for this tick before planning/fallback
                    se_pre, sc_pre = self._dispatch_scheduled(person, status.current_tick, people_by_id)
                    emails_sent += se_pre
                    chats_sent += sc_pre
                    if se_pre or sc_pre:
                        # If we sent scheduled comms at this minute, skip fallback sending to avoid duplication
                        continue
                    should_plan = bool(incoming) or bool(adjustments) or reason != "auto" or (tick_of_day == 0)
                    if not should_plan:
                        continue
                    # Hourly planning limiter per minute
                    key = (person.id, day_index, tick_of_day)
                    attempts = self._hourly_plan_attempts.get(key, 0)
                    if attempts >= self._max_hourly_plans_per_minute:
                        logger.warning(
                            "Skipping hourly planning for %s at tick %s (minute cap %s reached)",
                            person.name,
                            status.current_tick,
                            self._max_hourly_plans_per_minute,
                        )
                        continue
                    # record attempt before planning to avoid re-entry storms
                    self._hourly_plan_attempts[key] = attempts + 1
                    self.worker_runtime_manager.remove_messages(
                        [msg.message_id for msg in incoming if msg.message_id is not None]
                    )
                    for message in incoming:
                        sender_person = people_by_id.get(message.sender_id)
                        if message.message_type == "ack":
                            adjustments.append(f"Acknowledged by {message.sender_name}: {message.summary}")
                            continue
                        if message.action_item:
                            adjustments.append(f"Handle request from {message.sender_name}: {message.action_item}")
                        if sender_person is None:
                            continue
                        ack_phrase = (
                            message.action_item
                            or message.summary
                            or get_current_locale_manager().get_text("your_latest_update")
                        ).rstrip(".")
                        if self._locale == "ko":
                            # More varied and natural Korean acknowledgments
                            import random

                            ack_patterns = [
                                f"{sender_person.name.split()[0]}님, {ack_phrase} 확인했습니다.",
                                f"{sender_person.name.split()[0]}님, {ack_phrase} 진행하겠습니다.",
                                f"{sender_person.name.split()[0]}님, {ack_phrase} 작업 중입니다.",
                                f"{sender_person.name.split()[0]}님, 알겠습니다. {ack_phrase} 처리하겠습니다.",
                            ]
                            ack_body = random.choice(ack_patterns)
                        else:
                            ack_body = f"{sender_person.name.split()[0]}, I'm on {ack_phrase}."
                        if self._can_send(
                            tick=status.current_tick,
                            channel="chat",
                            sender=person.chat_handle,
                            recipient_key=(sender_person.chat_handle,),
                            subject=None,
                            body=ack_body,
                        ):
                            dt = self.tick_manager.sim_datetime_for_tick(status.current_tick)
                            self.chat_gateway.send_dm(
                                sender=person.chat_handle,
                                recipient=sender_person.chat_handle,
                                body=ack_body,
                                sent_at_iso=(dt.isoformat() if dt else None),
                            )
                            chats_sent += 1
                        self._log_exchange(status.current_tick, person.id, sender_person.id, "chat", None, ack_body)
                        ack_message = _InboundMessage(
                            sender_id=person.id,
                            sender_name=person.name,
                            subject=get_current_locale_manager().get_template("acknowledgement_from", name=person.name),
                            summary=ack_body,
                            action_item=None,
                            message_type="ack",
                            channel="chat",
                            tick=status.current_tick,
                        )
                        self.worker_runtime_manager.queue_message(sender_person, ack_message)

                    # Get ALL active projects for this person at current week (concurrent multi-project support)
                    active_projects = self._get_all_active_projects_for_person(person.id, current_week)
                    if not active_projects:
                        active_projects = [project_plan] if project_plan else []

                    # Skip planning if person has no active projects (idle until assigned)
                    if not active_projects:
                        logger.info(
                            "Skipping planning for %s at tick %s (no active project assignments for week %s)",
                            person.name,
                            status.current_tick,
                            current_week,
                        )
                        continue

                    # Use first project for daily plan, but pass all projects to hourly planner
                    primary_project = active_projects[0]

                    daily_plan_text = self._ensure_daily_plan(person, day_index, primary_project)

                    # Collect planning task for parallel execution
                    planning_task = (
                        person,
                        primary_project,
                        daily_plan_text,
                        status.current_tick,
                        reason,
                        adjustments or None,
                        active_projects if len(active_projects) > 1 else None,
                    )
                    planning_tasks.append(planning_task)

                    # Store context needed for post-processing
                    person_contexts[person.id] = {
                        "incoming": incoming,
                        "adjustments": adjustments,
                        "override": override,
                        "primary_project": primary_project,
                        "daily_plan_text": daily_plan_text,
                        "active_projects": active_projects,
                    }

                # PHASE 2: Execute planning in parallel (or sequential if disabled)
                if planning_tasks:
                    plan_results = self._generate_hourly_plans_parallel(planning_tasks)
                else:
                    plan_results = []

                # PHASE 3: Process results and send communications
                for person, hourly_result in plan_results:
                    context = person_contexts[person.id]
                    override = context["override"]
                    daily_plan_text = context["daily_plan_text"]
                    primary_project = context["primary_project"]
                    # person_project is the dict with project details
                    person_project = (
                        primary_project if isinstance(primary_project, dict) else {"project_name": "Unknown Project"}
                    )

                    daily_summary = self._summarise_plan(daily_plan_text, max_lines=3)
                    hourly_summary = self._summarise_plan(hourly_result.content)

                    # Store the hourly plan
                    self._store_worker_plan(
                        person_id=person.id,
                        tick=status.current_tick,
                        plan_type="hourly",
                        result=hourly_result,
                        context=None,
                    )

                    # Schedule any explicitly timed comms from the hourly plan
                    try:
                        self._schedule_from_hourly_plan(person, hourly_result.content, status.current_tick)
                    except Exception:
                        pass
                    if override and override[0] == "SickLeave":
                        continue

                    recipients = self._select_collaborators(person, people)
                    # Dispatch scheduled comms for this tick before any fallback sends
                    se, sc = self._dispatch_scheduled(person, status.current_tick, people_by_id)
                    emails_sent += se
                    chats_sent += sc
                    if se or sc:
                        continue
                    if not recipients:
                        subject = get_current_locale_manager().get_template("update_for", name=person.name)
                        body_lines = [
                            f"Project: {person_project['project_name']}",
                            f"Daily focus:\n{daily_summary}",
                            "",
                            f"Hourly plan:\n{hourly_summary}",
                            "",
                            "Keep the runway clear for surprises.",
                        ]
                        body_text = "\n".join(body_lines)
                        if self._can_send(
                            tick=status.current_tick,
                            channel="email",
                            sender=self.sim_manager_email,
                            recipient_key=(person.email_address,),
                            subject=subject,
                            body=body_text,
                        ):
                            dt = self.tick_manager.sim_datetime_for_tick(status.current_tick)
                            self.email_gateway.send_email(
                                sender=self.sim_manager_email,
                                to=[person.email_address],
                                subject=subject,
                                body=body_text,
                                sent_at_iso=(dt.isoformat() if dt else None),
                            )
                            emails_sent += 1
                        self._log_exchange(status.current_tick, None, person.id, "email", subject, body_text)
                        chat_body = (
                            f"Quick update: {hourly_summary.replace('\n', ' / ')}\nLet me know if you need support."
                        )
                        if self._can_send(
                            tick=status.current_tick,
                            channel="chat",
                            sender=self.sim_manager_handle,
                            recipient_key=(person.chat_handle,),
                            subject=None,
                            body=chat_body,
                        ):
                            dt = self.tick_manager.sim_datetime_for_tick(status.current_tick)
                            self.chat_gateway.send_dm(
                                sender=self.sim_manager_handle,
                                recipient=person.chat_handle,
                                body=chat_body,
                                sent_at_iso=(dt.isoformat() if dt else None),
                            )
                            chats_sent += 1
                        self._log_exchange(status.current_tick, None, person.id, "chat", None, chat_body)
                        continue
                    action_item = self._derive_action_item(hourly_summary, daily_summary)
                    for i, recipient in enumerate(recipients):
                        subject = get_current_locale_manager().get_template(
                            "update_from_to", from_name=person.name, to_name=recipient.name
                        )
                        if self._locale == "ko":
                            body_lines = [
                                f"{recipient.name.split()[0]}님 안녕하세요,",
                                "",
                                "현재 집중 작업:",
                                hourly_summary or daily_summary or "주요 작업에 집중하고 있습니다.",
                                "",
                                f"요청: {action_item}",
                                "필요하시면 언제든 말씀해 주세요.",
                            ]
                        else:
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
                        # Suggest CCs for fallback emails (dept head + one relevant peer)
                        cc_suggest: list[str] = []
                        try:
                            head = next((p for p in people if getattr(p, "is_department_head", False)), None)
                        except Exception:
                            head = None
                        if head and head.id not in {person.id, recipient.id}:
                            cc_email = getattr(head, "email_address", None)
                            if cc_email:
                                cc_suggest.append(cc_email)

                        def _role(s: str | None) -> str:
                            return (s or "").strip().lower()

                        s_role = _role(getattr(person, "role", None))
                        want_peer = None
                        if any(k in s_role for k in ("devops", "site reliability")):
                            want_peer = "dev"
                        elif any(k in s_role for k in ("developer", "engineer", "dev")):
                            want_peer = "designer"
                        elif any(k in s_role for k in ("design", "designer")):
                            want_peer = "dev"
                        elif any(k in s_role for k in ("product", "pm", "manager")):
                            want_peer = "dev"
                        if want_peer:
                            for p in people:
                                if p.id in {person.id, recipient.id}:
                                    continue
                                if want_peer in _role(getattr(p, "role", None)):
                                    peer_email = getattr(p, "email_address", None)
                                    if peer_email:
                                        cc_suggest.append(peer_email)
                                        break
                        if self._can_send(
                            tick=status.current_tick,
                            channel="email",
                            sender=person.email_address,
                            recipient_key=(recipient.email_address,),
                            subject=subject,
                            body=body,
                        ):
                            dt = self.tick_manager.sim_datetime_for_tick(status.current_tick)
                            self.email_gateway.send_email(
                                sender=person.email_address,
                                to=[recipient.email_address],
                                subject=subject,
                                body=body,
                                cc=cc_suggest,
                                sent_at_iso=(dt.isoformat() if dt else None),
                            )
                            emails_sent += 1
                        self._log_exchange(status.current_tick, person.id, recipient.id, "email", subject, body)

                        # Reduce frequency of auto-generated updates for more natural communication
                        if i == 0 and os.getenv("VDOS_REDUCE_AUTO_UPDATES", "false").lower() != "true":
                            chat_body = (
                                f"간단 업데이트: {action_item}"
                                if self._locale == "ko"
                                else f"Quick update: {action_item}"
                            )
                            if self._can_send(
                                tick=status.current_tick,
                                channel="chat",
                                sender=person.chat_handle,
                                recipient_key=(recipient.chat_handle,),
                                subject=None,
                                body=chat_body,
                            ):
                                dt = self.tick_manager.sim_datetime_for_tick(status.current_tick)
                                self.chat_gateway.send_dm(
                                    sender=person.chat_handle,
                                    recipient=recipient.chat_handle,
                                    body=chat_body,
                                    sent_at_iso=(dt.isoformat() if dt else None),
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
                        self.worker_runtime_manager.queue_message(recipient, inbound)

                # Generate hourly summaries at the end of each hour (every 60 ticks)
                if status.current_tick % 60 == 0:
                    completed_hour = (status.current_tick // 60) - 1
                    for person in people:
                        try:
                            self._generate_hourly_summary(person, completed_hour)
                        except Exception as e:
                            logger.warning(
                                f"Failed to generate hourly summary for {person.name} hour {completed_hour}: {e}"
                            )

                # Generate daily reports at the end of each day
                if status.current_tick % self.hours_per_day == 0:
                    completed_day = (status.current_tick // self.hours_per_day) - 1
                    for person in people:
                        self._generate_daily_report(person, completed_day, project_plan)

            return SimulationAdvanceResult(
                ticks_advanced=ticks,
                current_tick=status.current_tick,
                emails_sent=emails_sent,
                chat_messages_sent=chats_sent,
                sim_time=self.tick_manager.format_sim_time(status.current_tick),
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def inject_event(self, payload: EventCreate) -> dict:
        """Inject a custom event into the simulation (delegates to EventSystem)."""
        return self.event_system.inject_event(payload)

    def list_events(self) -> List[dict]:
        """List all events (delegates to EventSystem)."""
        return self.event_system.list_events()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _queue_runtime_message(self, recipient: PersonRead, message: _InboundMessage) -> None:
        """Delegate to WorkerRuntimeManager for backward compatibility."""
        self.worker_runtime_manager.queue_message(recipient, message)

    def _load_status_overrides(self) -> None:
        # Delegated to StateManager - no longer needed here
        pass

    def _log_exchange(
        self,
        tick: int,
        sender_id: int | None,
        recipient_id: int | None,
        channel: str,
        subject: str | None,
        summary: str | None,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO worker_exchange_log(tick, sender_id, recipient_id, channel, subject, summary) VALUES (?, ?, ?, ?, ?, ?)",
                (tick, sender_id, recipient_id, channel, subject, summary),
            )

    def _set_status_override(self, worker_id: int, status: str, until_tick: int, reason: str) -> None:
        self.state.set_status_override(worker_id, status, until_tick, reason)

    def _refresh_status_overrides(self, current_tick: int) -> None:
        self.state.clear_expired_status_overrides(current_tick)

    def _reset_runtime_state(self) -> None:
        """Reset runtime state including worker runtimes and status overrides."""
        self.worker_runtime_manager.clear_all()
        self._active_person_ids = None
        # Delegate status override clearing to StateManager
        self.state.clear_all_status_overrides()

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
                person for person in available if person.id in include_ids or person.name.lower() in include_names
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
            person for person in matched if person.id not in exclude_ids and person.name.lower() not in exclude_names
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
                cleaned = line.strip().lstrip("-•").strip()
                if cleaned.startswith(("Tick:", "Worker:", "Reason:", "Outline:")):
                    continue
                if cleaned:
                    return cleaned
        return "Keep momentum on the current deliverables"

    def reset(self) -> SimulationState:
        """Reset simulation state while preserving personas."""
        # Stop auto-ticks BEFORE acquiring lock to avoid deadlock
        self.stop_auto_ticks()
        with self.tick_manager.get_advance_lock():
            # Delegate simulation state reset to StateManager
            self.state.reset_simulation()
            # Clear ProjectManager cache
            self.project_manager.clear_cache()
            self._planner_model_hint = None
            self._planner_metrics.clear()
            self.project_duration_weeks = 4
            self._reset_runtime_state()
            people = self.list_people()
            self.tick_manager.update_work_windows(people)
            status = self.state.get_current_state()
            return SimulationState(
                current_tick=status.current_tick,
                is_running=status.is_running,
                auto_tick=status.auto_tick,
                sim_time=self.tick_manager.format_sim_time(status.current_tick),
            )

    def reset_full(self) -> SimulationState:
        """Resets simulation state and deletes all personas.

        Intended for a destructive "start fresh" action in the dashboard.
        Flushes ALL data including emails, chats, and all simulation artifacts.
        """
        # First clear runtime and planning artifacts
        # (reset() acquires its own lock)
        self.reset()

        # Then purge ALL data including email and chat servers
        with self.tick_manager.get_advance_lock():
            with get_connection() as conn:
                # Delete personas (cascades to schedule_blocks, project_assignments, etc.)
                conn.execute("DELETE FROM people")

                # Delete email server data
                conn.execute("DELETE FROM emails")
                conn.execute("DELETE FROM email_recipients")
                conn.execute("DELETE FROM mailboxes")
                conn.execute("DELETE FROM drafts")

                # Delete chat server data
                conn.execute("DELETE FROM chat_messages")
                conn.execute("DELETE FROM chat_members")
                conn.execute("DELETE FROM chat_rooms")
                conn.execute("DELETE FROM chat_users")

                # Delete any remaining simulation artifacts
                conn.execute("DELETE FROM hourly_summaries")

            # Clear all status overrides via StateManager
            self.state.clear_all_status_overrides()

            # Reset runtime caches after purge
            self._reset_runtime_state()
            self.tick_manager.update_work_windows([])
            status = self.state.get_current_state()
            return SimulationState(
                current_tick=status.current_tick,
                is_running=status.is_running,
                auto_tick=status.auto_tick,
                sim_time=self.tick_manager.format_sim_time(status.current_tick),
            )

    def _derive_seed(self, request: SimulationStartRequest | None) -> int:
        if request and request.random_seed is not None:
            return request.random_seed
        # For multi-project mode, use first project name; otherwise use single project name
        if request and request.projects:
            project_name = request.projects[0].project_name
        elif request and request.project_name:
            project_name = request.project_name
        else:
            project_name = "vdos-default"
        base = project_name.encode("utf-8")
        digest = hashlib.sha256(base).digest()
        return int.from_bytes(digest[:8], "big")

    def _maybe_generate_events(
        self, people: Sequence[PersonRead], tick: int, project_plan: dict[str, Any]
    ) -> tuple[dict[int, list[str]], dict[int, list[_InboundMessage]]]:
        """Generate random events for the current tick (delegates to EventSystem)."""
        return self.event_system.process_events_for_tick(
            tick=tick,
            people=people,
            hours_per_day=self.hours_per_day,
            status_overrides=self.state.get_status_overrides(),
            email_gateway=self.email_gateway,
            chat_gateway=self.chat_gateway,
            sim_manager_email=self.sim_manager_email,
            queue_message_callback=self._queue_runtime_message,
            log_exchange_callback=self._log_exchange,
            set_status_override_callback=self._set_status_override,
        )

    def _bootstrap_channels(self) -> None:
        self.email_gateway.ensure_mailbox(self.sim_manager_email, "Simulation Manager")
        self.chat_gateway.ensure_user(self.sim_manager_handle, "Simulation Manager")

    def _row_to_person(self, row) -> PersonRead:
        person_id = row["id"]
        schedule = self._fetch_schedule(person_id)
        # Check if team_name column exists (for backward compatibility)
        try:
            team_name = row["team_name"]
        except (KeyError, IndexError):
            team_name = None
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
        return [{"start": row["start"], "end": row["end"], "activity": row["activity"]} for row in rows]

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
