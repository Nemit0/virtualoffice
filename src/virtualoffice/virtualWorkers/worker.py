from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

try:
    from ..utils.completion_util import generate_text
except ModuleNotFoundError:  # pragma: no cover - fallback when optional deps missing
    def generate_text(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError("OpenAI client is not installed; install optional dependencies to enable text generation.")

def _to_minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def _format_minutes(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def render_minute_schedule(blocks: Sequence[ScheduleBlock], granularity: int = 15) -> str:
    if not blocks:
        return "00:00-23:59 Hold for assignments"
    slices: list[str] = []
    for block in blocks:
        start = _to_minutes(block.start)
        end = _to_minutes(block.end)
        if end <= start:
            end = start + granularity
        current = start
        while current < end:
            next_mark = min(current + granularity, end)
            slices.append(f"{_format_minutes(current)}-{_format_minutes(next_mark)} {block.activity}")
            current = next_mark
    return "\n".join(slices)


DEFAULT_STATUSES: Sequence[str] = (
    "Working",
    "Away",
    "OffDuty",
    "Overtime",
    "SickLeave",
    "Vacation",
)


@dataclass
class ScheduleBlock:
    start: str
    end: str
    activity: str


@dataclass
class WorkerPersona:
    name: str
    role: str
    skills: Sequence[str]
    personality: Sequence[str]
    timezone: str
    work_hours: str
    break_frequency: str
    communication_style: str
    email_address: str
    chat_handle: str
    objectives: Sequence[str] = field(default_factory=tuple)
    metrics: Sequence[str] = field(default_factory=tuple)


def _format_bullets(items: Iterable[str], prefix: str = "- ") -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return "\n".join(f"{prefix}{entry}" for entry in cleaned) if cleaned else "- TBD"


def _schedule_table(blocks: Sequence[ScheduleBlock]) -> str:
    if not blocks:
        return "| 09:00 | 18:00 | Core project work |"
    rows = []
    for block in blocks:
        rows.append(f"| {block.start} | {block.end} | {block.activity} |")
    return "\n".join(rows)


def _render_event_playbook(playbook: Mapping[str, Sequence[str]] | None) -> str:
    if not playbook:
        return "- Document new playbook entries as scenarios emerge."
    sections = []
    for event_name, steps in playbook.items():
        header = f"- **{event_name}**"
        detail = _format_bullets(steps, prefix="  - ")
        sections.append(f"{header}\n{detail}")
    return "\n".join(sections)


def build_worker_markdown(
    persona: WorkerPersona,
    schedule: Sequence[ScheduleBlock] | None = None,
    planning_guidelines: Sequence[str] | None = None,
    event_playbook: Mapping[str, Sequence[str]] | None = None,
    statuses: Sequence[str] | None = None,
) -> str:
    active_statuses = statuses or DEFAULT_STATUSES
    schedule_rows = _schedule_table(schedule or [])
    planning_section = _format_bullets(
        planning_guidelines
        or (
            "Review hourly plan for upcoming dependencies.",
            "Log sent emails and chat updates before status changes.",
            "Queue follow-ups for any blocked tasks before daily report.",
        )
    )

    template = f"""# {persona.name} ? {persona.role}\n\n"""
    template += "## Identity & Channels\n"
    template += _format_bullets(
        (
            f"Name: {persona.name}",
            f"Role: {persona.role}",
            f"Timezone: {persona.timezone}",
            f"Work hours: {persona.work_hours}",
            f"Break cadence: {persona.break_frequency}",
            f"Email: {persona.email_address}",
            f"Chat handle: {persona.chat_handle}",
        )
    )
    template += "\n\n## Skills & Personality\n"
    template += _format_bullets(
        (
            "Core skills: " + ", ".join(persona.skills),
            "Personality anchors: " + ", ".join(persona.personality),
            f"Communication style: {persona.communication_style}",
        )
    )
    template += "\n\n## Operating Objectives\n"
    template += _format_bullets(persona.objectives)
    template += "\n\n## Success Metrics\n"
    template += _format_bullets(persona.metrics)
    template += "\n\n## Daily Schedule Blueprint\n"
    template += "| Start | End | Focus |\n| ----- | --- | ----- |\n"
    template += f"{schedule_rows}\n"
    template += "\n## Status Vocabulary\n"
    template += _format_bullets(active_statuses)
    template += "\n\n## Hourly Planning Ritual\n"
    template += planning_section
    template += "\n\n## Event Playbook\n"
    template += _render_event_playbook(event_playbook)
    template += "\n\n## Daily Report Checklist\n"
    template += _format_bullets(
        (
            "Summarise progress versus daily goals.",
            "Call out blockers with owner and next action.",
            "Note cross-team asks that need follow-up tomorrow.",
        )
    )
    template += "\n"
    return template


class Worker(ABC):
    @abstractmethod
    def plan_next_hour(self):
        raise NotImplementedError

    @abstractmethod
    def react_to_event(self, event):
        raise NotImplementedError


class VirtualWorker(Worker):
    def __init__(
        self,
        persona: WorkerPersona,
        schedule: Sequence[ScheduleBlock] | None = None,
        planning_guidelines: Sequence[str] | None = None,
        event_playbook: Mapping[str, Sequence[str]] | None = None,
        statuses: Sequence[str] | None = None,
    ):
        self.persona = persona
        self.schedule = schedule or []
        self.planning_guidelines = planning_guidelines or []
        self.event_playbook = event_playbook or {}
        self.statuses = statuses or DEFAULT_STATUSES
        self.state = "Idle"
        self.memory: list[str] = []
        self.persona_markdown = build_worker_markdown(
            persona=persona,
            schedule=self.schedule,
            planning_guidelines=self.planning_guidelines,
            event_playbook=self.event_playbook,
            statuses=self.statuses,
        )

    def minute_schedule(self, granularity: int = 15) -> str:
        schedule_blocks = [ScheduleBlock(block.start, block.end, block.activity) for block in self.schedule]
        return render_minute_schedule(schedule_blocks, granularity=granularity)

    def plan_next_hour(self):
        raise NotImplementedError("VirtualWorker planning is orchestrated by the simulation manager.")

    def react_to_event(self, event):
        raise NotImplementedError("Event handling will be implemented when the simulation manager is ready.")

    def as_prompt(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.persona_markdown},
            {"role": "user", "content": "Provide the next hourly plan."},
        ]

    def request_plan(self, model: str = "gpt-4o-mini") -> tuple[str, int]:
        prompt = self.as_prompt()
        response_text, tokens = generate_text(prompt, model=model)
        self.memory.append(response_text)
        return response_text, tokens


if __name__ == "__main__":
    persona = WorkerPersona(
        name="Hana Kim",
        role="UI/UX Designer",
        skills=("Figma", "Design systems", "User research"),
        personality=("Collaborative", "Detail-oriented", "Empathetic"),
        timezone="Asia/Seoul",
        work_hours="09:00-18:00",
        break_frequency="Pomodoro 50/10, lunch at 12:30",
        communication_style="Warm tone, prefers async updates",
        email_address="hana.kim@vdos.local",
        chat_handle="hana",
        objectives=("Ship Alpha hero section", "Reduce design QA turnaround"),
        metrics=("Review response time < 2h", "Weekly stakeholder satisfaction"),
    )
    schedule = (
        ScheduleBlock("09:00", "10:00", "Inbox triage & stand-up prep"),
        ScheduleBlock("10:00", "12:00", "Design iteration"),
        ScheduleBlock("13:00", "15:00", "Design/dev sync & QA"),
        ScheduleBlock("15:00", "17:30", "Asset handoff & async updates"),
    )
    worker = VirtualWorker(persona, schedule)
    print(worker.persona_markdown)

    # test the planning request
    plan, token_count = worker.request_plan()
    print(f"--- Plan (tokens: {token_count}) ---\n{plan}")
    print("Done")

    # minute schedule test
    print("--- Minute Schedule (15 min) ---")
    print(worker.minute_schedule(granularity=15))
    print("--- Minute Schedule (30 min) ---")
    print(worker.minute_schedule(granularity=30))
    print("Done")