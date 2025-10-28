from __future__ import annotations

import hashlib
import logging
import random
from typing import Any, Callable, List, Sequence

from virtualoffice.common.db import get_connection

from ..schemas import PersonRead, SimulationStartRequest, SimulationState


logger = logging.getLogger(__name__)


class SimulationLifecycle:
    """Manages lifecycle operations for the simulation.

    Extracted responsibilities:
    - Start/stop simulation (including kickoff scheduling)
    - Auto-tick start/stop wiring with TickManager
    - Reset/reset_full with DB cleanup

    This orchestrator depends on externally provided collaborators for
    project initialization, planning advancement, and state access.
    """

    def __init__(
        self,
        *,
        state_manager,
        tick_manager,
        communication_hub,
        worker_runtime_manager,
        project_manager,
        event_system,
        email_gateway,
        chat_gateway,
        sim_manager_email: str,
        sim_manager_handle: str,
        hours_per_day: int,
        locale: str,
        rnd: random.Random,
        # Callbacks and providers
        list_people_fn: Callable[[], List[PersonRead]],
        set_active_ids_fn: Callable[[list[int] | None], None],
        get_active_ids_fn: Callable[[], list[int] | None],
        initialise_project_plan_fn: Callable[[SimulationStartRequest, Sequence[PersonRead]], None],
        collaborator_selector_fn: Callable[[PersonRead, Sequence[PersonRead]], list[PersonRead]],
    ) -> None:
        self.state = state_manager
        self.tick_manager = tick_manager
        self.communication_hub = communication_hub
        self.worker_runtime_manager = worker_runtime_manager
        self.project_manager = project_manager
        self.event_system = event_system
        self.email_gateway = email_gateway
        self.chat_gateway = chat_gateway
        self.sim_manager_email = sim_manager_email
        self.sim_manager_handle = sim_manager_handle
        self.hours_per_day = hours_per_day
        self.locale = locale
        self._rnd = rnd

        # Callbacks
        self._list_people = list_people_fn
        self._set_active_ids = set_active_ids_fn
        self._get_active_ids = get_active_ids_fn
        self._initialise_project_plan = initialise_project_plan_fn
        self._select_collaborators = collaborator_selector_fn

    # --- Public API ----------------------------------------------------
    def get_state(self) -> SimulationState:
        status = self.state.get_current_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self.tick_manager.format_sim_time(status.current_tick),
        )

    def start(self, request: SimulationStartRequest | None) -> SimulationState:
        # Seed random for reproducibility
        self._rnd.seed(self._derive_seed(request))

        # Reset runtime and clear overrides
        self._reset_runtime_state()

        all_people = self._list_people()
        if not all_people:
            raise RuntimeError("Cannot start simulation without any personas")

        active_people = self._resolve_active_people(request, all_people)
        self._set_active_ids([p.id for p in active_people])

        if request is not None:
            # Initialize project plans (single or multi) via provided function
            self._initialise_project_plan(request, active_people)

        # Mark running and set base datetime
        self.state.set_running(True)
        self.tick_manager.set_base_datetime()
        self.worker_runtime_manager.sync_runtimes(active_people)

        # Schedule kickoff chat/email for each worker shortly after work start
        try:
            for person in active_people:
                start_tick_of_day, _ = self.tick_manager.get_work_hours_ticks(person.id)
                base_tick = 1
                kickoff_tick = base_tick + max(0, start_tick_of_day) + 5
                recipients = self._select_collaborators(person, active_people)
                target = recipients[0] if recipients else None
                if not target:
                    continue
                if self.locale == "ko":
                    self.communication_hub.schedule_direct_comm(
                        person.id, kickoff_tick, "chat", target.chat_handle, "좋은 아침입니다! 오늘 우선순위 빠르게 맞춰볼까요?"
                    )
                    self.communication_hub.schedule_direct_comm(
                        person.id,
                        kickoff_tick + 30,
                        "email",
                        target.email_address,
                        "제목: 킥오프\n본문: 오늘 진행할 작업 정리했습니다 — 문의사항 있으면 알려주세요.",
                    )
                else:
                    self.communication_hub.schedule_direct_comm(
                        person.id, kickoff_tick, "chat", target.chat_handle, "Morning! Quick sync on priorities?"
                    )
                    self.communication_hub.schedule_direct_comm(
                        person.id,
                        kickoff_tick + 30,
                        "email",
                        target.email_address,
                        "Subject: Quick kickoff\nBody: Lining up tasks for today — ping me with blockers.",
                    )
        except Exception:
            pass

        return self.get_state()

    def stop(self, *, generate_report_fn: Callable[[dict[str, Any], int], Any], get_project_plan_fn: Callable[[], dict | None]) -> SimulationState:
        self.tick_manager.stop_auto_tick(self.state)
        status = self.state.get_current_state()
        if status.is_running:
            plan = get_project_plan_fn()
            if plan is not None:
                generate_report_fn(plan, status.current_tick)
        self.state.set_running(False)
        self._set_active_ids(None)
        return self.get_state()

    def start_auto_ticks(
        self,
        *,
        advance_callback: Callable[[], None],
        get_active_projects_callback: Callable[[int | None], list[dict]],
        archive_chat_room_callback: Callable[[int], bool],
        auto_pause_enabled: bool,
    ) -> SimulationState:
        status = self.state.get_current_state()
        self.tick_manager.start_auto_tick(
            is_running=status.is_running,
            advance_callback=advance_callback,
            state_manager=self.state,
            get_active_projects_callback=get_active_projects_callback,
            archive_chat_room_callback=archive_chat_room_callback,
            auto_pause_enabled=auto_pause_enabled,
        )
        return self.get_state()

    def stop_auto_ticks(self) -> SimulationState:
        self.tick_manager.stop_auto_tick(self.state)
        return self.get_state()

    def set_tick_interval(self, seconds: float) -> dict[str, Any]:
        self.tick_manager.set_tick_interval(seconds)
        return {"tick_interval_seconds": self.tick_manager.get_tick_interval(), "message": f"Tick interval set to {seconds}s" + (" (max speed)" if seconds == 0 else "")}

    def get_tick_interval(self) -> float:
        return self.tick_manager.get_tick_interval()

    def reset_runtime_only(self) -> None:
        self._reset_runtime_state()

    def reset(self) -> SimulationState:
        # Stop auto-ticks BEFORE acquiring lock to avoid deadlock
        self.tick_manager.stop_auto_tick(self.state)
        with self.tick_manager.get_advance_lock():
            self.state.reset_simulation()
            # Clear all runtime state
            self._reset_runtime_state()
            people = self._list_people()
            self.tick_manager.update_work_windows(people)
            return self.get_state()

    def reset_full(self) -> SimulationState:
        # First clear runtime and planning artifacts
        self.reset()
        with self.tick_manager.get_advance_lock():
            with get_connection() as conn:
                # Delete personas (cascades)
                conn.execute("DELETE FROM people")
                # Email server data
                conn.execute("DELETE FROM emails")
                conn.execute("DELETE FROM email_recipients")
                conn.execute("DELETE FROM mailboxes")
                conn.execute("DELETE FROM drafts")
                # Chat server data
                conn.execute("DELETE FROM chat_messages")
                conn.execute("DELETE FROM chat_members")
                conn.execute("DELETE FROM chat_rooms")
                conn.execute("DELETE FROM chat_users")
                # Sim artifacts
                conn.execute("DELETE FROM hourly_summaries")
                conn.execute("DELETE FROM daily_reports")
                conn.execute("DELETE FROM simulation_reports")
                conn.execute("DELETE FROM worker_plans")
                conn.execute("DELETE FROM worker_runtime_messages")
                conn.execute("DELETE FROM worker_exchange_log")
                conn.execute("DELETE FROM worker_status_overrides")
                conn.execute("DELETE FROM events")
                conn.execute("DELETE FROM project_assignments")
                conn.execute("DELETE FROM project_chat_rooms")
                conn.execute("DELETE FROM project_plans")
                conn.execute("DELETE FROM tick_log")
            # Clear overrides and caches
            self.state.clear_all_status_overrides()
            self._reset_runtime_state()
            self.tick_manager.update_work_windows([])
            return self.get_state()

    # --- Internal helpers ---------------------------------------------
    def _derive_seed(self, request: SimulationStartRequest | None) -> int:
        if request and request.random_seed is not None:
            return request.random_seed
        if request and request.projects:
            project_name = request.projects[0].project_name
        elif request and request.project_name:
            project_name = request.project_name
        else:
            project_name = "vdos-default"
        base = project_name.encode("utf-8")
        digest = hashlib.sha256(base).digest()
        return int.from_bytes(digest[:8], "big")

    def _reset_runtime_state(self) -> None:
        self.worker_runtime_manager.clear_all()
        self._set_active_ids(None)
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

