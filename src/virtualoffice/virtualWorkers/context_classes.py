"""
Context dataclasses for VirtualWorker planning and reporting.

Provides structured context objects that encapsulate all information
needed for different types of worker operations (planning, reporting, events).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from ..sim_manager.schemas import PersonRead


@dataclass
class PlanningContext:
    """
    Context for hourly planning operations.

    Encapsulates all information a worker needs to generate
    an hourly plan, including project details, team roster,
    and recent communications.

    Attributes:
        project_plan: Current project plan text
        daily_plan: Today's daily plan text
        tick: Current simulation tick
        reason: Trigger reason for planning (e.g., "start_of_hour", "new_message")
        team: List of team members for communication context
        recent_emails: Optional list of recent emails for threading
        all_active_projects: Optional list of all active projects for multi-project scenarios
        locale: Language/locale code (e.g., "en", "ko")
        model_hint: Optional model override for this planning operation
    """

    project_plan: str
    daily_plan: str
    tick: int
    reason: str
    team: Sequence[PersonRead]
    recent_emails: list[dict[str, Any]] | None = None
    all_active_projects: list[dict[str, Any]] | None = None
    locale: str = "en"
    model_hint: str | None = None


@dataclass
class DailyPlanningContext:
    """
    Context for daily planning operations.

    Encapsulates information needed to generate a daily plan,
    including project timeline and team composition.

    Attributes:
        project_plan: Current project plan text
        day_index: Day number (0-indexed)
        duration_weeks: Total project duration in weeks
        team: List of team members
        locale: Language/locale code (e.g., "en", "ko")
        model_hint: Optional model override for this planning operation
    """

    project_plan: str
    day_index: int
    duration_weeks: int
    team: Sequence[PersonRead]
    locale: str = "en"
    model_hint: str | None = None


@dataclass
class EventContext:
    """
    Context for event reaction operations.

    Encapsulates information about a simulation event that
    a worker needs to react to appropriately.

    Attributes:
        event: Event data dictionary with type, description, and payload
        tick: Current simulation tick when event occurred
        team: List of team members for coordination
        project_plan: Current project plan data
        locale: Language/locale code (e.g., "en", "ko")
        model_hint: Optional model override for this reaction
    """

    event: dict[str, Any]
    tick: int
    team: Sequence[PersonRead]
    project_plan: dict[str, Any]
    locale: str = "en"
    model_hint: str | None = None


@dataclass
class ReportContext:
    """
    Context for daily report generation.

    Encapsulates information needed to generate an end-of-day
    report summarizing the worker's activities and progress.

    Attributes:
        day_index: Day number (0-indexed)
        daily_plan: Today's daily plan text
        hourly_log: Log of hourly activities throughout the day
        minute_schedule: Detailed minute-by-minute schedule
        locale: Language/locale code (e.g., "en", "ko")
        model_hint: Optional model override for this report
    """

    day_index: int
    daily_plan: str
    hourly_log: str
    minute_schedule: str
    project_plan: str | None = None  # Optional project plan context
    locale: str = "en"
    model_hint: str | None = None


@dataclass
class EventResponse:
    """
    Structured response to a simulation event.

    Represents how a worker reacts to an event, including
    plan adjustments, immediate actions, and communications.

    Attributes:
        adjustments: List of textual adjustments to current plans
        immediate_actions: List of immediate action dictionaries
        status_change: Optional status change (e.g., "sick_leave", "away")
        communications: Optional list of communication dictionaries to send
    """

    adjustments: list[str] = field(default_factory=list)
    immediate_actions: list[dict[str, Any]] = field(default_factory=list)
    status_change: str | None = None
    communications: list[dict[str, Any]] | None = None
