"""
Enhanced VirtualWorker with autonomous planning capabilities.

Provides a fully autonomous worker that can plan, react to events,
and generate reports using the prompt management system.
"""

from __future__ import annotations

from typing import Sequence

from .worker import WorkerPersona, ScheduleBlock, build_worker_markdown
from .planner_mixin import PlannerMixin
from .context_classes import PlanningContext
from ..sim_manager.schemas import PersonRead
from ..sim_manager.planner import Planner
from ..sim_manager.prompts import PromptManager, ContextBuilder


class VirtualWorker(PlannerMixin):
    """
    Autonomous virtual worker with planning capabilities.

    This class represents a fully autonomous worker that can:
    - Generate hourly plans based on context
    - Generate daily plans based on project timeline
    - React to simulation events
    - Generate end-of-day reports

    The worker uses the PromptManager and ContextBuilder to construct
    context-aware prompts, and delegates to a Planner for LLM-based
    content generation.

    Attributes:
        persona: WorkerPersona with identity and attributes
        prompt_manager: PromptManager for template-based prompts
        context_builder: ContextBuilder for context aggregation
        planner: Planner for LLM-based generation
        schedule: Optional schedule blocks for the worker
        planning_guidelines: Optional planning guidelines
        event_playbook: Optional event response playbook
        statuses: Optional status vocabulary
        persona_markdown: Generated markdown representation of persona
    """

    def __init__(
        self,
        persona: WorkerPersona,
        prompt_manager: PromptManager,
        context_builder: ContextBuilder,
        planner: Planner,
        schedule: Sequence[ScheduleBlock] | None = None,
        planning_guidelines: Sequence[str] | None = None,
        event_playbook: dict[str, Sequence[str]] | None = None,
        statuses: Sequence[str] | None = None,
    ):
        """
        Initialize the virtual worker.

        Args:
            persona: WorkerPersona with identity and attributes
            prompt_manager: PromptManager for template-based prompts
            context_builder: ContextBuilder for context aggregation
            planner: Planner for LLM-based generation
            schedule: Optional schedule blocks
            planning_guidelines: Optional planning guidelines
            event_playbook: Optional event response playbook
            statuses: Optional status vocabulary
        """
        self.persona = persona
        self.prompt_manager = prompt_manager
        self.context_builder = context_builder
        self.planner = planner
        self.schedule = schedule or []
        self.planning_guidelines = planning_guidelines or []
        self.event_playbook = event_playbook or {}
        self.statuses = statuses or []

        # Generate persona markdown for prompt inclusion
        self.persona_markdown = build_worker_markdown(
            persona=persona,
            schedule=self.schedule,
            planning_guidelines=self.planning_guidelines,
            event_playbook=self.event_playbook,
            statuses=self.statuses,
        )

        # Attach persona_markdown to persona for easy access
        self.persona.persona_markdown = self.persona_markdown

    def to_person_read(self) -> PersonRead:
        """
        Convert to PersonRead for API compatibility.

        Creates a PersonRead instance that can be used with
        existing simulation engine APIs.

        Returns:
            PersonRead instance with worker attributes
        """
        return PersonRead(
            id=getattr(self.persona, "id", 0),
            name=self.persona.name,
            role=self.persona.role,
            email_address=self.persona.email_address,
            chat_handle=self.persona.chat_handle,
            timezone=self.persona.timezone,
            work_hours=self.persona.work_hours,
            break_frequency=self.persona.break_frequency,
            communication_style=self.persona.communication_style,
            skills=self.persona.skills,
            personality=self.persona.personality,
            objectives=self.persona.objectives,
            metrics=self.persona.metrics,
            schedule=(
                [{"start": block.start, "end": block.end, "activity": block.activity} for block in self.schedule]
                if self.schedule
                else None
            ),
            planning_guidelines=list(self.planning_guidelines) if self.planning_guidelines else None,
            event_playbook=dict(self.event_playbook) if self.event_playbook else None,
            statuses=list(self.statuses) if self.statuses else None,
            persona_markdown=self.persona_markdown,
        )

    def as_prompt(self, context: PlanningContext) -> list[dict[str, str]]:
        """
        Generate prompt messages for this worker.

        Uses the PromptManager and ContextBuilder to construct
        context-aware prompt messages.

        Args:
            context: PlanningContext with all necessary information

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        # Build prompt context using ContextBuilder
        prompt_context = self.context_builder.build_planning_context(
            worker=self.to_person_read(),
            tick=context.tick,
            reason=context.reason,
            project_plan=context.project_plan,
            daily_plan=context.daily_plan,
            team=context.team,
            recent_emails=context.recent_emails,
            all_active_projects=context.all_active_projects,
        )

        # Build messages using PromptManager
        return self.prompt_manager.build_prompt("hourly", prompt_context)


# Convenience function for creating VirtualWorker instances
def create_virtual_worker(
    persona: WorkerPersona,
    prompt_manager: PromptManager,
    context_builder: ContextBuilder,
    planner: Planner,
    **kwargs,
) -> VirtualWorker:
    """
    Create a VirtualWorker instance with dependencies.

    Convenience function for creating workers with all required
    dependencies injected.

    Args:
        persona: WorkerPersona with identity and attributes
        prompt_manager: PromptManager for template-based prompts
        context_builder: ContextBuilder for context aggregation
        planner: Planner for LLM-based generation
        **kwargs: Additional arguments passed to VirtualWorker constructor

    Returns:
        Configured VirtualWorker instance
    """
    return VirtualWorker(
        persona=persona,
        prompt_manager=prompt_manager,
        context_builder=context_builder,
        planner=planner,
        **kwargs,
    )
