import textwrap

from virtualoffice.virtualWorkers.worker import (
    DEFAULT_STATUSES,
    ScheduleBlock,
    VirtualWorker,
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
        statuses=("Working", "Away"),
    )

    assert "# Minseo Lee ? Engineering Manager" in markdown
    assert "| 09:00 | 10:00 | Team stand-up |" in markdown
    assert "Limit context switches" in markdown
    assert "**client_change**" in markdown
    assert "Working" in markdown and "Vacation" not in markdown


def test_virtual_worker_uses_defaults_when_optional_data_missing():
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
    worker = VirtualWorker(persona, schedule=())

    assert all(status in worker.persona_markdown for status in DEFAULT_STATUSES)
    assert "| 09:00 | 18:00 | Core project work |" in worker.persona_markdown

    prompt = worker.as_prompt()
    assert prompt[0]["role"] == "system"
    assert persona.name in prompt[0]["content"]
    assert prompt[1]["content"].startswith("Provide the next hourly plan")