from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, Field, field_validator


class ScheduleBlockIn(BaseModel):
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="24h start time e.g. 09:00")
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="24h end time e.g. 10:00")
    activity: str


class PersonCreate(BaseModel):
    name: str
    role: str
    timezone: str = Field(..., description="IANA or descriptive timezone string")
    work_hours: str = Field(..., description="Human readable window e.g. 09:00-18:00")
    break_frequency: str
    communication_style: str
    email_address: str
    chat_handle: str
    skills: Sequence[str]
    personality: Sequence[str]
    objectives: Sequence[str] | None = None
    metrics: Sequence[str] | None = None
    schedule: Sequence[ScheduleBlockIn] | None = None
    planning_guidelines: Sequence[str] | None = None
    event_playbook: dict[str, Sequence[str]] | None = None
    statuses: Sequence[str] | None = None

    @field_validator("skills", "personality")
    @classmethod
    def _ensure_non_empty(cls, value: Sequence[str]) -> Sequence[str]:
        if not value:
            raise ValueError("Must include at least one entry")
        return value


class PersonRead(PersonCreate):
    id: int
    persona_markdown: str


class SimulationState(BaseModel):
    current_tick: int = 0
    is_running: bool = False


class SimulationAdvanceRequest(BaseModel):
    ticks: int = Field(..., gt=0, le=480)
    reason: str = Field(default="manual", max_length=128)


class SimulationAdvanceResult(BaseModel):
    ticks_advanced: int
    current_tick: int
    emails_sent: int
    chat_messages_sent: int


class SimulationControlResponse(SimulationState):
    message: str


class EventCreate(BaseModel):
    type: str
    target_ids: Sequence[int] = Field(default_factory=list)
    project_id: str | None = None
    at_tick: int | None = None
    payload: dict | None = None


class EventRead(EventCreate):
    id: int