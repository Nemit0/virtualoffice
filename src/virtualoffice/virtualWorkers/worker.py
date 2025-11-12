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
    "근무중",
    "자리비움",
    "퇴근",
    "야근",
    "병가",
    "휴가",
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
    is_department_head: bool = False
    team_name: str | None = None


def _format_bullets(items: Iterable[str], prefix: str = "- ") -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return "\n".join(f"{prefix}{entry}" for entry in cleaned) if cleaned else "- TBD"


def _schedule_table(blocks: Sequence[ScheduleBlock]) -> str:
    if not blocks:
        return "| 09:00 | 18:00 | 핵심 프로젝트 작업 |"
    rows = []
    for block in blocks:
        rows.append(f"| {block.start} | {block.end} | {block.activity} |")
    return "\n".join(rows)


def _render_event_playbook(playbook: Mapping[str, Sequence[str]] | None) -> str:
    if not playbook:
        return "- 시나리오가 발생할 때 새로운 대응 매뉴얼 항목을 문서화합니다."
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
            "향후 의존성에 대한 시간별 계획을 검토합니다.",
            "상태 변경 전에 발송된 이메일과 채팅 업데이트를 기록합니다.",
            "일일 보고서 작성 전에 차단된 작업에 대한 후속 조치를 대기열에 추가합니다.",
        )
    )

    template = f"""# {persona.name} ? {persona.role}\n\n"""
    template += "## 신원 및 채널\n"
    template += _format_bullets(
        (
            f"이름: {persona.name}",
            f"역할: {persona.role}",
            f"시간대: {persona.timezone}",
            f"근무 시간: {persona.work_hours}",
            f"휴식 주기: {persona.break_frequency}",
            f"이메일: {persona.email_address}",
            f"채팅 핸들: {persona.chat_handle}",
        )
    )
    template += "\n\n## 기술 및 성격\n"
    template += _format_bullets(
        (
            "핵심 기술: " + ", ".join(persona.skills),
            "성격 특성: " + ", ".join(persona.personality),
            f"커뮤니케이션 스타일: {persona.communication_style}",
        )
    )
    template += "\n\n## 운영 목표\n"
    template += _format_bullets(persona.objectives)
    template += "\n\n## 성공 지표\n"
    template += _format_bullets(persona.metrics)
    template += "\n\n## 일일 일정 청사진\n"
    template += "| 시작 | 종료 | 집중 사항 |\n| ----- | --- | ----- |\n"
    template += f"{schedule_rows}\n"
    template += "\n## 상태 어휘\n"
    template += _format_bullets(active_statuses)
    template += "\n\n## 시간별 계획 수립 절차\n"
    template += planning_section
    template += "\n\n## 이벤트 대응 매뉴얼\n"
    template += _render_event_playbook(event_playbook)
    template += "\n\n## 일일 보고서 체크리스트\n"
    template += _format_bullets(
        (
            "일일 목표 대비 진행 상황을 요약합니다.",
            "담당자와 다음 조치가 포함된 차단 요소를 명시합니다.",
            "내일 후속 조치가 필요한 팀 간 요청 사항을 기록합니다.",
        )
    )
    template += "\n"
    return template
