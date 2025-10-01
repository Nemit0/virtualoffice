from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Protocol, Sequence

try:
    from virtualoffice.utils.completion_util import generate_text
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    def generate_text(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError(
            "OpenAI client is not installed; install optional dependencies to enable planning."
        )

from .schemas import PersonRead

PlanGenerator = Callable[[list[dict[str, str]], str], tuple[str, int]]



DEFAULT_PROJECT_MODEL = os.getenv("VDOS_PLANNER_PROJECT_MODEL", "gpt-4o-mini")
DEFAULT_DAILY_MODEL = os.getenv("VDOS_PLANNER_DAILY_MODEL", DEFAULT_PROJECT_MODEL)
DEFAULT_HOURLY_MODEL = os.getenv("VDOS_PLANNER_HOURLY_MODEL", DEFAULT_DAILY_MODEL)
DEFAULT_DAILY_REPORT_MODEL = os.getenv("VDOS_PLANNER_DAILY_REPORT_MODEL")
DEFAULT_SIM_REPORT_MODEL = os.getenv("VDOS_PLANNER_SIM_REPORT_MODEL")

@dataclass
class PlanResult:
    content: str
    model_used: str
    tokens_used: int | None = None


class PlanningError(RuntimeError):
    """Raised when an LLM-backed planning attempt fails."""


class Planner(Protocol):
    def generate_project_plan(
        self,
        *,
        department_head: PersonRead,
        project_name: str,
        project_summary: str,
        duration_weeks: int,
        team: Sequence[PersonRead],
        model_hint: str | None = None,
    ) -> PlanResult:
        ...

    def generate_daily_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        duration_weeks: int,
        model_hint: str | None = None,
    ) -> PlanResult:
        ...

    def generate_hourly_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        daily_plan: str,
        tick: int,
        context_reason: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        ...

    def generate_daily_report(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        daily_plan: str,
        hourly_log: str,
        minute_schedule: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        ...

    def generate_simulation_report(
        self,
        *,
        project_plan: str,
        team: Sequence[PersonRead],
        total_ticks: int,
        tick_log: str,
        daily_reports: str,
        event_summary: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        ...


class GPTPlanner:
    """Planner that delegates plan generation to OpenAI chat completions."""

    def __init__(
        self,
        generator: PlanGenerator | None = None,
        project_model: str = DEFAULT_PROJECT_MODEL,
        daily_model: str = DEFAULT_DAILY_MODEL,
        hourly_model: str = DEFAULT_HOURLY_MODEL,
        daily_report_model: str | None = DEFAULT_DAILY_REPORT_MODEL,
        simulation_report_model: str | None = DEFAULT_SIM_REPORT_MODEL,
    ) -> None:
        if generator is None:
            def _default(messages: list[dict[str, str]], model: str) -> tuple[str, int]:
                return generate_text(messages, model=model)

            self._generator = _default
        else:
            self._generator = generator
        self.project_model = project_model
        self.daily_model = daily_model
        self.hourly_model = hourly_model
        self.daily_report_model = daily_report_model or daily_model
        self.simulation_report_model = simulation_report_model or project_model

    def generate_project_plan(
        self,
        *,
        department_head: PersonRead,
        project_name: str,
        project_summary: str,
        duration_weeks: int,
        team: Sequence[PersonRead],
        model_hint: str | None = None,
    ) -> PlanResult:
        team_lines = "\n".join(f"- {member.name} ({member.role})" for member in team)
        user_content = "\n".join(
            [
                f"Project name: {project_name}",
                f"Summary: {project_summary}",
                f"Duration: {duration_weeks} weeks",
                "Team:",
                team_lines,
                "",
                "Create a week-by-week plan with milestones, owners, risk mitigations, and explicit buffer time for each phase.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a meticulous department head responsible for designing cross-disciplinary project roadmaps. "
                    "Ensure the plan keeps teams finishing ahead of schedule with documented buffers."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.project_model
        return self._invoke(messages, model)

    def generate_daily_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        duration_weeks: int,
        model_hint: str | None = None,
    ) -> PlanResult:
        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) in {worker.timezone}.",
                f"Project duration: {duration_weeks} weeks. Today is day {day_index + 1}.",
                "Project plan excerpt:",
                project_plan,
                "",
                "Outline today's key objectives, planned communications, and the time reserved as buffer.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You help knowledge workers turn project plans into focused daily objectives, finishing at least one hour early."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.daily_model
        return self._invoke(messages, model)

    def generate_hourly_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        daily_plan: str,
        tick: int,
        context_reason: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) at tick {tick}.",
                f"Trigger: {context_reason}.",
                "Project reference:",
                project_plan,
                "",
                "Daily focus:",
                daily_plan,
                "",
                "Replan the next few hours, mark email/chat touchpoints, and finish early with contingency time.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You act as an operations coach who reshapes hourly schedules. Keep outputs concise, actionable, and include buffers."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.hourly_model
        return self._invoke(messages, model)

    def generate_daily_report(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        daily_plan: str,
        hourly_log: str,
        minute_schedule: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) day {day_index + 1}.",
                "Daily plan:",
                daily_plan,
                "",
                "Hourly log:",
                hourly_log or "No hourly updates recorded.",
                "",
                "Minute schedule:",
                minute_schedule,
                "",
                "Summarise the day with minute-by-minute highlights, note communications, and flag risks for tomorrow.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an operations chief of staff producing detailed daily reports. "
                    "Capture minute-level timeline, decisions, escalations, and buffer usage."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.daily_report_model
        return self._invoke(messages, model)

    def generate_simulation_report(
        self,
        *,
        project_plan: str,
        team: Sequence[PersonRead],
        total_ticks: int,
        tick_log: str,
        daily_reports: str,
        event_summary: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        team_lines = "\n".join(f"- {member.name} ({member.role})" for member in team)
        user_content = "\n".join(
            [
                f"Total ticks: {total_ticks}",
                "Team:",
                team_lines,
                "",
                "Project plan:",
                project_plan,
                "",
                "Tick log:",
                tick_log or "No ticks processed.",
                "",
                "Daily reports:",
                daily_reports or "No daily reports logged.",
                "",
                "Events:",
                event_summary,
                "",
                "Produce an executive summary covering achievements, issues, communications, and next steps.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the department head preparing an end-of-run retrospective. "
                    "Highlight cross-team coordination, risks, and readiness for the next cycle."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.simulation_report_model
        return self._invoke(messages, model)

    def _invoke(self, messages: list[dict[str, str]], model: str) -> PlanResult:
        try:
            content, tokens = self._generator(messages, model)
        except Exception as exc:  # pragma: no cover - surface as planning failure
            raise PlanningError(str(exc)) from exc
        return PlanResult(content=content, model_used=model, tokens_used=tokens)


class StubPlanner:
    """Fallback planner that produces deterministic text without external calls."""

    def _result(self, label: str, body: str, model: str) -> PlanResult:
        content = f"[{label}]\n{body}"
        return PlanResult(content=content, model_used=model, tokens_used=0)

    def generate_project_plan(
        self,
        *,
        department_head: PersonRead,
        project_name: str,
        project_summary: str,
        duration_weeks: int,
        team: Sequence[PersonRead],
        model_hint: str | None = None,
    ) -> PlanResult:
        teammates = "\n".join(f"- {member.name} ({member.role})" for member in team)
        body = "\n".join([
            f"Project: {project_name}",
            f"Summary: {project_summary}",
            f"Duration: {duration_weeks} week(s)",
            f"Department head: {department_head.name}",
            "Team:",
            teammates or "- (none)",
            "Initial focus: break work into design, build, review, and communication checkpoints.",
        ])
        model = model_hint or "vdos-stub-project"
        return self._result("Project Plan", body, model)

    def generate_daily_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        duration_weeks: int,
        model_hint: str | None = None,
    ) -> PlanResult:
        total_days = max(duration_weeks, 1) * 5
        body = "\n".join([
            f"Worker: {worker.name} ({worker.role})",
            f"Day: {day_index + 1} / {total_days}",
            "Goals:",
            "- Advance project milestones",
            "- Communicate blockers",
            "- Capture progress for end-of-day report",
        ])
        model = model_hint or "vdos-stub-daily"
        return self._result("Daily Plan", body, model)

    def generate_hourly_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        daily_plan: str,
        tick: int,
        context_reason: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        hour = tick % 60 or 60
        body = "\n".join([
            f"Worker: {worker.name}",
            f"Tick: {tick} (minute {hour})",
            f"Reason: {context_reason}",
            "Outline:",
            "- Review priorities",
            "- Heads-down execution",
            "- Share update with team",
        ])
        model = model_hint or "vdos-stub-hourly"
        return self._result("Hourly Plan", body, model)

    def generate_daily_report(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        daily_plan: str,
        hourly_log: str,
        minute_schedule: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        body = "\n".join([
            f"Worker: {worker.name}",
            f"Day {day_index + 1} summary",
            "Highlights:",
            "- Delivered planned work",
            "- Communicated status",
            "Risks:",
            "- Pending follow-ups",
        ])
        model = model_hint or "vdos-stub-daily-report"
        return self._result("Daily Report", body, model)

    def generate_simulation_report(
        self,
        *,
        project_plan: str,
        team: Sequence[PersonRead],
        total_ticks: int,
        tick_log: str,
        daily_reports: str,
        event_summary: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        teammates = ", ".join(person.name for person in team) or "(none)"
        body = "\n".join([
            f"Total ticks: {total_ticks}",
            f"Team: {teammates}",
            "Recap:",
            "- Work advanced",
            "- Communications logged",
            "- Review outstanding risks",
        ])
        model = model_hint or "vdos-stub-simulation"
        return self._result("Simulation Report", body, model)
