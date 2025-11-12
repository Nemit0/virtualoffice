import textwrap

from virtualoffice.virtualWorkers.worker import (
    DEFAULT_STATUSES,
    ScheduleBlock,
    WorkerPersona,
    build_worker_markdown,
)


def test_build_worker_markdown_includes_core_sections():
    persona = WorkerPersona(
        name="Minseo Lee",
        role="Engineering Manager",
        skills=("Python", "Systems design"),
        personality=("Decisive", "Calm"),
        timezone="Asia/Seoul",
        work_hours="09:00-18:00",
        break_frequency="45/15 cadence",
        communication_style="Concise, async-first",
        email_address="minseo.lee@vdos.local",
        chat_handle="minseo",
    )
    schedule = [ScheduleBlock("09:00", "10:00", "Team stand-up"), ScheduleBlock("10:00", "12:00", "Coaching sessions")]
    markdown = build_worker_markdown(
        persona=persona,
        schedule=schedule,
        planning_guidelines=("Limit context switches","Close the hour with inbox zero"),
        event_playbook={"client_change": ("Acknowledge scope shift", "Replan backlog")},
        statuses=("근무중", "자리비움"),
    )

    assert "# Minseo Lee ? Engineering Manager" in markdown
    assert "| 09:00 | 10:00 | Team stand-up |" in markdown
    assert "Limit context switches" in markdown
    assert "**client_change**" in markdown
    assert "근무중" in markdown and "휴가" not in markdown


def test_build_worker_markdown_uses_defaults_when_optional_data_missing():
    """Test that build_worker_markdown uses sensible defaults for missing optional data."""
    persona = WorkerPersona(
        name="Hana",
        role="Designer",
        skills=("Figma",),
        personality=("Curious",),
        timezone="UTC+9",
        work_hours="09:00-18:00",
        break_frequency="Pomodoro",
        communication_style="Warm",
        email_address="hana@vdos.local",
        chat_handle="hana",
    )
    # Build markdown with empty schedule to test defaults
    markdown = build_worker_markdown(persona, schedule=())

    # Should include all default statuses
    assert all(status in markdown for status in DEFAULT_STATUSES)
    # Should show default schedule when empty
    assert "| 09:00 | 18:00 | Core project work |" in markdown