from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence

from virtualoffice.common.localization import get_current_locale_manager

from ..planner import PlanResult, PlanningError
from ..schemas import PersonRead
from .planner_service import PlannerService
from .worker_registry import WorkerRegistry
from .communication_hub import CommunicationHub  # type: ignore[import-not-found]
from .plan_store import PlanStore
from .report_store import ReportStore


logger = logging.getLogger(__name__)


class PlanningOrchestrator:
    """Coordinates planning and reporting for workers.

    Responsibilities:
    - Generate daily plans (VirtualWorker when available, else PlannerService)
    - Generate hourly plans (serial/parallel)
    - Generate hourly summaries at hour boundaries
    - Generate daily reports at day boundaries
    - Persist plans/reports via stores
    """

    def __init__(
        self,
        *,
        planner_service: PlannerService,
        worker_registry: WorkerRegistry,
        communication_hub: CommunicationHub,
        plan_store: PlanStore,
        report_store: ReportStore,
        locale: str,
        hours_per_day: int,
    ) -> None:
        self.planner_service = planner_service
        self.worker_registry = worker_registry
        self.communication_hub = communication_hub
        self.plan_store = plan_store
        self.report_store = report_store
        self.locale = locale
        self.hours_per_day = hours_per_day

    # Daily planning ----------------------------------------------------
    def ensure_daily_plan(
        self,
        *,
        person: PersonRead,
        day_index: int,
        project_plan: dict[str, Any],
        duration_weeks: int,
        team: Sequence[PersonRead],
        model_hint: str | None,
    ) -> str:
        existing = self.plan_store.get_worker_plan(person.id, "daily", tick=day_index, exact_tick=True)
        if existing:
            return existing["content"]
        result = self.generate_daily_plan(
            person=person,
            project_plan=project_plan,
            day_index=day_index,
            duration_weeks=duration_weeks,
            team=team,
            model_hint=model_hint,
        )
        return result.content

    def generate_daily_plan(
        self,
        *,
        person: PersonRead,
        project_plan: dict[str, Any],
        day_index: int,
        duration_weeks: int,
        team: Sequence[PersonRead],
        model_hint: str | None,
    ) -> PlanResult:
        worker = self.worker_registry.workers.get(person.id)
        if worker:
            # Lazy import for contexts
            from virtualoffice.virtualWorkers.context_classes import DailyPlanningContext  # type: ignore

            ctx = DailyPlanningContext(
                project_plan=project_plan["plan"],
                day_index=day_index,
                duration_weeks=duration_weeks,
                team=team,
                locale=self.locale,
                model_hint=model_hint,
            )
            try:
                result = worker.plan_daily(ctx)
            except Exception as exc:  # pragma: no cover - delegate failure
                raise RuntimeError(f"Unable to generate daily plan for {person.name}: {exc}") from exc
        else:
            try:
                result = self.planner_service.call(
                    "generate_daily_plan",
                    worker=person,
                    project_plan=project_plan["plan"],
                    day_index=day_index,
                    duration_weeks=duration_weeks,
                    team=team,
                    model_hint=model_hint,
                )
            except Exception as exc:
                raise RuntimeError(f"Unable to generate daily plan for {person.name}: {exc}") from exc

        # Persist
        self.plan_store.put_worker_plan(
            person_id=person.id,
            tick=day_index,
            plan_type="daily",
            result=result,
            context=f"day_index={day_index}",
        )
        return result

    # Hourly planning ---------------------------------------------------
    def generate_hourly_plan(
        self,
        *,
        person: PersonRead,
        project_plan: dict[str, Any],
        daily_plan_text: str,
        tick: int,
        reason: str,
        team: Sequence[PersonRead],
        model_hint: str | None,
        adjustments: list[str] | None = None,
        all_active_projects: list[dict[str, Any]] | None = None,
    ) -> PlanResult:
        # Recent emails for threading context
        recent_emails = self.communication_hub.get_recent_emails_for_person(person.id, limit=10)

        worker = self.worker_registry.workers.get(person.id)
        if worker:
            # Lazy import for contexts
            from virtualoffice.virtualWorkers.context_classes import PlanningContext  # type: ignore

            ctx = PlanningContext(
                project_plan=project_plan["plan"],
                daily_plan=daily_plan_text,
                tick=tick,
                reason=reason,
                team=team,
                recent_emails=recent_emails,
                all_active_projects=all_active_projects,
                locale=self.locale,
                model_hint=model_hint,
            )
            try:
                result = worker.plan_next_hour(ctx)
            except Exception as exc:  # pragma: no cover - delegate failure
                raise RuntimeError(f"Unable to generate hourly plan for {person.name}: {exc}") from exc
        else:
            try:
                result = self.planner_service.call(
                    "generate_hourly_plan",
                    worker=person,
                    project_plan=project_plan["plan"],
                    daily_plan=daily_plan_text,
                    tick=tick,
                    context_reason=reason,
                    team=team,
                    model_hint=model_hint,
                    all_active_projects=all_active_projects,
                    recent_emails=recent_emails,
                )
            except Exception as exc:
                raise RuntimeError(f"Unable to generate hourly plan for {person.name}: {exc}") from exc

        # Apply adjustments into content
        content_result = result
        if adjustments:
            bullets = "\n".join(f"- {item}" for item in adjustments)
            loc = get_current_locale_manager()
            header = loc.get_text("live_collaboration_adjustments")
            content = f"{result.content}\n\n{header}:\n{bullets}"
            content_result = PlanResult(content=content, model_used=result.model_used, tokens_used=result.tokens_used)

        # Persist
        context = f"reason={reason}" + (f";adjustments={len(adjustments)}" if adjustments else "")
        self.plan_store.put_worker_plan(
            person_id=person.id,
            tick=tick,
            plan_type="hourly",
            result=content_result,
            context=context,
        )
        return content_result

    def generate_hourly_plans_parallel(
        self,
        planning_tasks: list[tuple[PersonRead, dict[str, Any], str, int, str, list[str] | None, list[dict[str, Any]] | None]],
        *,
        executor: ThreadPoolExecutor | None,
        team_provider: callable | None = None,  # deprecated; team is per-task in this pass
        model_hint: str | None = None,
    ) -> list[tuple[PersonRead, PlanResult]]:
        # Fallback to sequential if no executor or only one task
        if not executor or len(planning_tasks) <= 1:
            results: list[tuple[PersonRead, PlanResult]] = []
            for task in planning_tasks:
                person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects = task
                try:
                    # Team must be supplied by caller per-context; for now recompute outside
                    # (Engine supplies team separately when building contexts)
                    # Here we assume caller passes the correct team in daily_plan_text context
                    # and we recompute via callback if provided (not used in current code path)
                    result = self.generate_hourly_plan(
                        person=person,
                        project_plan=project_plan,
                        daily_plan_text=daily_plan_text,
                        tick=tick,
                        reason=reason,
                        team=team_provider() if team_provider else [],
                        model_hint=model_hint,
                        adjustments=adjustments,
                        all_active_projects=all_active_projects,
                    )
                except Exception as exc:
                    logger.error(f"Sequential planning failed for {person.name}: {exc}")
                    result = PlanResult(content="", model_used="error", tokens_used=0)
                results.append((person, result))
            return results

        futures = []
        for task in planning_tasks:
            person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects = task
            futures.append(
                (
                    person,
                    executor.submit(
                        self.generate_hourly_plan,
                        person=person,
                        project_plan=project_plan,
                        daily_plan_text=daily_plan_text,
                        tick=tick,
                        reason=reason,
                        team=team_provider() if team_provider else [],
                        model_hint=model_hint,
                        adjustments=adjustments,
                        all_active_projects=all_active_projects,
                    ),
                )
            )

        results: list[tuple[PersonRead, PlanResult]] = []
        for person, future in futures:
            try:
                result = future.result(timeout=240)
            except Exception as exc:
                logger.error(f"Parallel planning failed for {person.name}: {exc}")
                result = PlanResult(content="", model_used="error", tokens_used=0)
            results.append((person, result))
        return results

    # Hourly summaries --------------------------------------------------
    def generate_hourly_summary(self, *, person: PersonRead, hour_index: int, model_hint: str | None) -> dict[str, Any]:
        existing = self.report_store.get_hourly_summary(person.id, hour_index)
        if existing:
            return existing

        start_tick = hour_index * 60 + 1
        end_tick = (hour_index + 1) * 60
        hourly_rows = self.plan_store.list_hourly_plans_in_range(person.id, start_tick, end_tick)
        if not hourly_rows:
            return {
                "person_id": person.id,
                "hour_index": hour_index,
                "summary": "",
                "model_used": "none",
                "tokens_used": 0,
            }

        hourly_plans = "\n".join(f"Tick {row['tick']}: {row['content'][:200]}..." for row in hourly_rows)
        try:
            result = self.planner_service.call(
                "generate_hourly_summary",
                worker=person,
                hour_index=hour_index,
                hourly_plans=hourly_plans,
                model_hint=model_hint,
            )
        except Exception as exc:
            logger.warning(f"Unable to generate hourly summary for {person.name} hour {hour_index}: {exc}")
            result = PlanResult(content=f"Hour {hour_index + 1} activities", model_used="stub", tokens_used=0)

        return self.report_store.put_hourly_summary(person_id=person.id, hour_index=hour_index, result=result)

    # Daily report ------------------------------------------------------
    def generate_daily_report(
        self,
        *,
        person: PersonRead,
        day_index: int,
        project_plan: dict[str, Any],
        daily_plan_text: str | None,
        model_hint: str | None,
    ) -> dict[str, Any]:
        existing = self.report_store.get_daily_report(person.id, day_index)
        if existing:
            return existing

        if daily_plan_text is None:
            # Fetch last stored daily plan content
            daily = self.plan_store.get_worker_plan(person.id, "daily", tick=day_index, exact_tick=True)
            daily_plan_text = daily["content"] if daily else ""

        # Build hourly summary window based on hours_per_day
        start_hour = day_index * (self.hours_per_day // 60)
        end_hour = (day_index + 1) * (self.hours_per_day // 60)

        # Try precomputed hourly summaries for the day
        hourly_summary_lines: list[str] = []
        for h in range(start_hour, end_hour):
            summary = self.report_store.get_hourly_summary(person.id, h)
            if summary and summary.get("summary"):
                hourly_summary_lines.append(f"Hour {h + 1}: {summary['summary']}")

        if not hourly_summary_lines:
            # Fallback: generate on demand now
            for h in range(start_hour, end_hour):
                summary = self.generate_hourly_summary(person=person, hour_index=h, model_hint=model_hint)
                if summary.get("summary"):
                    hourly_summary_lines.append(f"Hour {h + 1}: {summary['summary']}")

        hourly_summary = (
            "\n".join(hourly_summary_lines)
            if hourly_summary_lines
            else get_current_locale_manager().get_text("no_hourly_activities")
        )

        # Minute schedule outline
        from virtualoffice.virtualWorkers.worker import ScheduleBlock, render_minute_schedule  # type: ignore

        schedule_blocks = [ScheduleBlock(block.start, block.end, block.activity) for block in (person.schedule or [])]
        minute_schedule = render_minute_schedule(schedule_blocks)

        worker = self.worker_registry.workers.get(person.id)
        if worker:
            from virtualoffice.virtualWorkers.context_classes import ReportContext  # type: ignore

            ctx = ReportContext(
                project_plan=project_plan["plan"],
                day_index=day_index,
                daily_plan=daily_plan_text,
                hourly_log=hourly_summary,
                minute_schedule=minute_schedule,
                locale=self.locale,
                model_hint=model_hint,
            )
            try:
                result = worker.generate_daily_report(ctx)
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"Unable to generate daily report for {person.name}: {exc}") from exc
        else:
            try:
                result = self.planner_service.call(
                    "generate_daily_report",
                    worker=person,
                    project_plan=project_plan["plan"],
                    day_index=day_index,
                    daily_plan=daily_plan_text,
                    hourly_log=hourly_summary,
                    minute_schedule=minute_schedule,
                    model_hint=model_hint,
                )
            except Exception as exc:
                raise RuntimeError(f"Unable to generate daily report for {person.name}: {exc}") from exc

        return self.report_store.put_daily_report(
            person_id=person.id,
            day_index=day_index,
            schedule_outline=minute_schedule,
            result=result,
        )

