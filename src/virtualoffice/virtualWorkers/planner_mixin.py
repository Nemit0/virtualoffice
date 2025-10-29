"""
Planning mixin for VirtualWorker classes.

Provides planning methods that can be mixed into worker classes
to enable autonomous planning capabilities.
"""

from __future__ import annotations

# Import context classes and result types for type hints
from .context_classes import (
    PlanningContext,
    DailyPlanningContext,
    EventContext,
    ReportContext,
    EventResponse,
)
from ..sim_manager.planner import PlanResult


class PlannerMixin:
    """
    Mixin providing planning methods for VirtualWorker.

    This mixin assumes the class has:
    - self.persona: WorkerPersona instance
    - self.prompt_manager: PromptManager instance
    - self.context_builder: ContextBuilder instance
    - self.planner: Planner instance
    """

    def plan_next_hour(self, context: PlanningContext) -> PlanResult:
        """
        Generate an hourly plan based on current context.

        Uses the PromptManager and ContextBuilder to construct
        a context-aware prompt, then delegates to the planner
        for LLM-based plan generation.

        Args:
            context: PlanningContext with all necessary information

        Returns:
            PlanResult with generated plan content
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

        # Add additional context fields needed by hourly template
        prompt_context["project_reference"] = context.project_plan

        # Build valid email list (exclude self)
        worker_email = self.persona.email_address
        valid_emails = [m.email_address for m in context.team if m.email_address != worker_email]
        prompt_context["valid_email_list"] = "\n".join(f"  - {email}" for email in valid_emails)

        # Build example communications in Korean
        examples = []
        if valid_emails:
            examples.append(
                f"- 이메일 10:30에 {valid_emails[0]} 참조 {valid_emails[1] if len(valid_emails) > 1 else valid_emails[0]}: 스프린트 업데이트 | 인증 모듈 완료, 리뷰 준비됨"
            )
        if context.team:
            # Find a teammate's chat handle (not self)
            chat_handle = None
            for member in context.team:
                if member.email_address != worker_email:
                    chat_handle = member.chat_handle
                    break
            if chat_handle:
                examples.append(f"- 채팅 11:00에 {chat_handle}과: API 엔드포인트 관련 질문")
        examples.append("- 채팅 11:00에 팀과: 스프린트 진행 상황 업데이트 (프로젝트 그룹 채팅으로 전송)")
        if valid_emails:
            examples.append(
                f"- 답장 14:00에 [email-42] 참조 {valid_emails[0]}: RE: API 상태 | 업데이트 감사합니다, 통합 진행하겠습니다"
            )
        prompt_context["correct_examples"] = "\n".join(examples)

        # Build messages using PromptManager
        messages = self.prompt_manager.build_prompt("hourly", prompt_context)

        # Generate plan using planner
        return self.planner.generate_with_messages(
            messages=messages,
            model_hint=context.model_hint,
        )

    def plan_daily(self, context: DailyPlanningContext) -> PlanResult:
        """
        Generate a daily plan based on project timeline.

        Uses the PromptManager and ContextBuilder to construct
        a daily planning prompt with project context.

        Args:
            context: DailyPlanningContext with project and timeline info

        Returns:
            PlanResult with generated daily plan
        """
        # Build prompt context
        persona_markdown = (
            getattr(self.persona, "persona_markdown", "") or f"역할: {self.persona.role}\n기술: 일반"
        )
        worker_email = self.persona.email_address
        team_roster = "\n".join(
            f"- {m.name} ({m.role}) - 이메일: {m.email_address}, 채팅: @{m.chat_handle}"
            for m in context.team
            if m.email_address != worker_email
        )

        prompt_context = {
            "worker_name": self.persona.name,
            "worker_role": self.persona.role or "팀원",
            "worker_timezone": getattr(self.persona, "timezone", "Asia/Seoul"),
            "persona_markdown": persona_markdown,
            "team_roster": team_roster or "팀원 없음",
            "duration_weeks": context.duration_weeks,
            "day_number": context.day_index + 1,
            "project_plan": context.project_plan,
        }

        # Build messages using PromptManager
        messages = self.prompt_manager.build_prompt("daily", prompt_context)

        # Generate plan using planner
        return self.planner.generate_with_messages(
            messages=messages,
            model_hint=context.model_hint,
        )

    def generate_daily_report(self, context: ReportContext) -> PlanResult:
        """
        Generate an end-of-day report summarizing activities.

        Uses the PromptManager and ContextBuilder to construct
        a reporting prompt with the day's activities.

        Args:
            context: ReportContext with daily activities and logs

        Returns:
            PlanResult with generated report
        """
        # Build prompt context using ContextBuilder
        prompt_context = self.context_builder.build_reporting_context(
            worker=self.to_person_read(),
            day_index=context.day_index,
            daily_plan=context.daily_plan,
            hourly_log=context.hourly_log,
            minute_schedule=context.minute_schedule,
        )

        # Build messages using PromptManager
        messages = self.prompt_manager.build_prompt("daily_report", prompt_context)

        # Generate report using planner
        return self.planner.generate_with_messages(
            messages=messages,
            model_hint=context.model_hint,
        )

    def react_to_event(self, context: EventContext) -> EventResponse:
        """
        React to a simulation event.

        Generates an appropriate response to an event, including
        plan adjustments, status changes, and communications.

        Args:
            context: EventContext with event details

        Returns:
            EventResponse with structured reaction
        """
        # Build prompt context using ContextBuilder
        prompt_context = self.context_builder.build_event_context(
            worker=self.to_person_read(),
            event=context.event,
            tick=context.tick,
            team=context.team,
            project_plan=context.project_plan,
        )

        # Try to use event reaction template if available
        try:
            messages = self.prompt_manager.build_prompt("event_reaction", prompt_context)
        except Exception:
            # Fall back to simple prompt if template not available (Korean)
            event_type = context.event.get("event_type", "알 수 없음")
            description = context.event.get("description", "")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "작업자가 시뮬레이션 이벤트에 대응하도록 돕고 있습니다. "
                        "계획에 적용해야 할 조정 사항을 간단히 나열해 주세요."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"작업자: {self.persona.name} ({self.persona.role})\n"
                        f"이벤트: {event_type}\n"
                        f"설명: {description}\n\n"
                        "이 작업자가 계획에 적용해야 할 조정 사항은 무엇인가요?"
                    ),
                },
            ]

        # Generate response
        result = self.planner.generate_with_messages(
            messages=messages,
            model_hint=context.model_hint,
        )

        # Parse response into EventResponse
        # For now, just return adjustments as a list of lines
        adjustments = [
            line.strip() for line in result.content.split("\n") if line.strip() and not line.strip().startswith("#")
        ]

        return EventResponse(adjustments=adjustments)

    def to_person_read(self):
        """
        Convert persona to PersonRead for API compatibility.

        This method should be implemented by the concrete class
        to provide a PersonRead representation of the worker.

        Returns:
            PersonRead instance
        """
        raise NotImplementedError("Subclass must implement to_person_read()")
