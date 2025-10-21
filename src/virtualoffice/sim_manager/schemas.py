from __future__ import annotations

from typing import Literal, Sequence

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
    is_department_head: bool = False
    team_name: str | None = Field(default=None, description="Team identifier for multi-team simulations")
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
    auto_tick: bool = False
    sim_time: str = "Day 0 00:00"


class SimulationAdvanceRequest(BaseModel):
    ticks: int = Field(..., gt=0, le=480)
    reason: str = Field(default="manual", max_length=128)


class SimulationAdvanceResult(BaseModel):
    ticks_advanced: int
    current_tick: int
    emails_sent: int
    chat_messages_sent: int
    sim_time: str


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

class ProjectTimelineIn(BaseModel):
    """Defines when a project is active within the simulation"""
    project_name: str
    project_summary: str
    start_week: int = Field(default=1, ge=1, description="Week when project starts (1-indexed)")
    duration_weeks: int = Field(default=4, ge=1, le=52, description="How many weeks the project lasts")
    assigned_person_ids: Sequence[int] | None = Field(default=None, description="Optional: specific people assigned to this project")

    @property
    def end_week(self) -> int:
        """Calculate the end week (inclusive)"""
        return self.start_week + self.duration_weeks - 1


class SimulationStartRequest(BaseModel):
    project_name: str
    project_summary: str
    duration_weeks: int = Field(default=4, ge=1, le=52)
    department_head_name: str | None = None
    model_hint: str | None = Field(default=None, description="Optional override for planning model")
    random_seed: int | None = Field(default=None, ge=0, description="Optional seed for reproducible events")
    include_person_ids: Sequence[int] | None = Field(default=None, description="Limit the run to these persona IDs")
    include_person_names: Sequence[str] | None = Field(default=None, description="Limit the run to personas matching these names")
    exclude_person_ids: Sequence[int] | None = Field(default=None, description="Remove these persona IDs from the run")
    exclude_person_names: Sequence[str] | None = Field(default=None, description="Remove personas whose names match these values")
    # Multi-project support
    projects: Sequence[ProjectTimelineIn] | None = Field(default=None, description="Optional: define multiple overlapping projects")
    total_duration_weeks: int | None = Field(default=None, ge=1, le=52, description="Total simulation duration when using multiple projects")


class ProjectPlanRead(BaseModel):
    id: int
    project_name: str
    project_summary: str
    plan: str
    generated_by: int | None = None
    duration_weeks: int
    model_used: str
    tokens_used: int | None = None
    created_at: str


PlanTypeLiteral = Literal['daily', 'hourly']


class WorkerPlanRead(BaseModel):
    id: int
    person_id: int
    tick: int
    plan_type: PlanTypeLiteral
    content: str
    model_used: str
    tokens_used: int | None = None
    context: str | None = None
    created_at: str



class DailyReportRead(BaseModel):
    id: int
    person_id: int
    day_index: int
    report: str
    schedule_outline: str
    model_used: str
    tokens_used: int | None = None
    created_at: str


class SimulationReportRead(BaseModel):
    id: int
    report: str
    model_used: str
    tokens_used: int | None = None
    total_ticks: int
    created_at: str



class TokenUsageSummary(BaseModel):
    per_model: dict[str, int] = Field(default_factory=dict)
    total_tokens: int = 0


# --- Persona generation (dashboard autofill) ---
class PersonaGenerateRequest(BaseModel):
    prompt: str
    model_hint: str | None = Field(default=None, description="Optional model name, e.g. gpt-4o-mini")
    explicit_name: str | None = Field(default=None, description="Optional: force this exact name instead of GPT-generated name")


# --- Status override (external integration) ---
class StatusOverrideRequest(BaseModel):
    person_id: int | None = Field(default=None, description="Person ID to override")
    person_name: str | None = Field(default=None, description="Person name to override (alternative to person_id)")
    status: Literal["Absent", "Offline", "SickLeave", "OnLeave"] = Field(..., description="Status to set")
    duration_ticks: int | None = Field(default=None, ge=1, description="How many ticks the status lasts (optional, defaults to current day)")
    reason: str = Field(default="External trigger", max_length=256)

    @field_validator("person_id", "person_name")
    @classmethod
    def _at_least_one_identifier(cls, value, info):
        if info.field_name == "person_name":
            # Check if both are None
            person_id = info.data.get("person_id")
            if person_id is None and value is None:
                raise ValueError("Either person_id or person_name must be provided")
        return value


class StatusOverrideResponse(BaseModel):
    person_id: int
    person_name: str
    status: str
    until_tick: int
    reason: str
    message: str


