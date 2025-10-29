"""
Virtual Workers package.

Provides worker persona management and autonomous planning capabilities.
"""

from .worker import (
    WorkerPersona,
    ScheduleBlock,
    build_worker_markdown,
    render_minute_schedule,
)
from .context_classes import (
    PlanningContext,
    DailyPlanningContext,
    EventContext,
    ReportContext,
    EventResponse,
)
from .planner_mixin import PlannerMixin
from .virtual_worker import VirtualWorker, create_virtual_worker

__all__ = [
    # Core persona classes
    "WorkerPersona",
    "ScheduleBlock",
    # Enhanced autonomous worker
    "VirtualWorker",
    "create_virtual_worker",
    # Context classes
    "PlanningContext",
    "DailyPlanningContext",
    "EventContext",
    "ReportContext",
    "EventResponse",
    # Mixins
    "PlannerMixin",
    # Utility functions
    "build_worker_markdown",
    "render_minute_schedule",
]
