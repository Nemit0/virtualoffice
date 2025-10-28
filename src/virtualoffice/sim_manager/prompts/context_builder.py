"""
Context builder for prompt construction.

Aggregates data from various sources to build comprehensive context
dictionaries for LLM prompt generation.
"""

from __future__ import annotations

from typing import Any, Sequence
from ..schemas import PersonRead


class ContextBuilder:
    """
    Builds context dictionaries for prompt templates.

    Aggregates worker information, team rosters, project plans,
    and other contextual data needed for realistic LLM-generated plans.
    """

    def __init__(self, locale: str = "en"):
        """
        Initialize the context builder.

        Args:
            locale: Language/locale code (e.g., "en", "ko")
        """
        self.locale = locale.strip().lower() or "en"

    def build_planning_context(
        self,
        worker: PersonRead,
        tick: int,
        reason: str,
        project_plan: str,
        daily_plan: str,
        team: Sequence[PersonRead],
        recent_emails: list[dict[str, Any]] | None = None,
        all_active_projects: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Build context for hourly planning prompts.

        Args:
            worker: Worker persona generating the plan
            tick: Current simulation tick
            reason: Trigger reason for planning (e.g., "start_of_hour", "new_message")
            project_plan: Current project plan text
            daily_plan: Today's daily plan text
            team: List of team members
            recent_emails: Optional list of recent emails for threading context
            all_active_projects: Optional list of all active projects for multi-project scenarios

        Returns:
            Dictionary of context variables for template substitution
        """
        context = {
            "worker_name": worker.name,
            "worker_role": worker.role or "Team Member",
            "worker_email": worker.email_address,
            "worker_chat_handle": worker.chat_handle,
            "worker_timezone": getattr(worker, "timezone", "UTC"),
            "tick": tick,
            "context_reason": reason,
            "project_plan": project_plan,
            "daily_plan": daily_plan,
            "locale": self.locale,
        }

        # Add persona markdown if available
        if hasattr(worker, "persona_markdown") and worker.persona_markdown:
            context["persona_markdown"] = worker.persona_markdown
        else:
            context["persona_markdown"] = f"Role: {worker.role}\nSkills: General"

        # Add work hours
        work_hours = getattr(worker, "work_hours", "09:00-17:00") or "09:00-17:00"
        context["work_hours"] = work_hours

        # Build team roster
        context["team_roster"] = self._format_team_roster(worker, team)
        context["team_roster_list"] = self._build_team_roster_list(worker, team)

        # Add recent emails for threading
        if recent_emails:
            context["recent_emails"] = self._format_recent_emails(recent_emails)
            context["recent_emails_list"] = recent_emails
        else:
            context["recent_emails"] = "No recent emails"
            context["recent_emails_list"] = []

        # Add multi-project context
        if all_active_projects and len(all_active_projects) > 1:
            context["multi_project_mode"] = True
            context["active_projects"] = self._format_active_projects(all_active_projects)
            context["active_projects_list"] = all_active_projects
        else:
            context["multi_project_mode"] = False
            context["active_projects"] = ""
            context["active_projects_list"] = []

        return context

    def build_event_context(
        self,
        worker: PersonRead,
        event: dict[str, Any],
        tick: int,
        team: Sequence[PersonRead],
        project_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build context for event reaction prompts.

        Args:
            worker: Worker reacting to the event
            event: Event data dictionary
            tick: Current simulation tick
            team: List of team members
            project_plan: Current project plan data

        Returns:
            Dictionary of context variables for template substitution
        """
        context = {
            "worker_name": worker.name,
            "worker_role": worker.role or "Team Member",
            "worker_email": worker.email_address,
            "tick": tick,
            "event_type": event.get("event_type", "unknown"),
            "event_description": event.get("description", ""),
            "event_payload": event.get("payload", {}),
            "project_name": project_plan.get("project_name", "Current Project"),
            "project_plan": project_plan.get("plan", ""),
            "locale": self.locale,
        }

        # Add persona markdown if available
        if hasattr(worker, "persona_markdown") and worker.persona_markdown:
            context["persona_markdown"] = worker.persona_markdown
        else:
            context["persona_markdown"] = f"Role: {worker.role}\nSkills: General"

        # Build team roster
        context["team_roster"] = self._format_team_roster(worker, team)

        return context

    def build_reporting_context(
        self,
        worker: PersonRead,
        day_index: int,
        daily_plan: str,
        hourly_log: str,
        minute_schedule: str,
    ) -> dict[str, Any]:
        """
        Build context for daily report generation.

        Args:
            worker: Worker generating the report
            day_index: Day number (0-indexed)
            daily_plan: Today's daily plan text
            hourly_log: Log of hourly activities
            minute_schedule: Detailed minute-by-minute schedule

        Returns:
            Dictionary of context variables for template substitution
        """
        context = {
            "worker_name": worker.name,
            "worker_role": worker.role or "Team Member",
            "day_index": day_index,
            "day_number": day_index + 1,
            "daily_plan": daily_plan,
            "hourly_log": hourly_log or "No hourly updates recorded.",
            "minute_schedule": minute_schedule or "No detailed schedule available.",
            "locale": self.locale,
        }

        # Add persona markdown if available
        if hasattr(worker, "persona_markdown") and worker.persona_markdown:
            context["persona_markdown"] = worker.persona_markdown
        else:
            context["persona_markdown"] = f"Role: {worker.role}\nSkills: General"

        return context

    def _format_team_roster(self, worker: PersonRead, team: Sequence[PersonRead]) -> str:
        """
        Format team roster as a string for prompt inclusion.

        Args:
            worker: Current worker (to exclude from roster)
            team: List of all team members

        Returns:
            Formatted team roster string
        """
        if not team:
            return f"Known handles: {worker.chat_handle}"

        lines = []
        if self.locale == "ko":
            lines.append("=== 팀 명단 ===")
            lines.append("(정확한 이메일 주소만 사용하세요 - 새로운 주소를 만들지 마세요!)")
            lines.append("")
            lines.append(f"본인: {worker.name} ({worker.role})")
            lines.append(f"  이메일: {worker.email_address}")
            lines.append(f"  채팅: {worker.chat_handle}")
            lines.append("")
            lines.append("팀원:")
        else:
            lines.append("=== YOUR TEAM ROSTER ===")
            lines.append("(Use ONLY these exact email addresses - never create new ones!)")
            lines.append("")
            lines.append(f"YOU: {worker.name} ({worker.role})")
            lines.append(f"  Your Email: {worker.email_address}")
            lines.append(f"  Your Chat: {worker.chat_handle}")
            lines.append("")
            lines.append("YOUR TEAMMATES:")

        for member in team:
            if member.id == worker.id:
                continue
            lines.append(f"- {member.name} ({member.role})")
            if self.locale == "ko":
                lines.append(f"  이메일: {member.email_address}")
                lines.append(f"  채팅: {member.chat_handle}")
            else:
                lines.append(f"  Email: {member.email_address}")
                lines.append(f"  Chat: {member.chat_handle}")

        return "\n".join(lines)

    def _build_team_roster_list(self, worker: PersonRead, team: Sequence[PersonRead]) -> list[dict[str, Any]]:
        """
        Build team roster as a list of dictionaries.

        Args:
            worker: Current worker
            team: List of all team members

        Returns:
            List of team member dictionaries
        """
        roster = []
        for member in team:
            if member.id == worker.id:
                continue
            roster.append(
                {
                    "name": member.name,
                    "role": member.role,
                    "email": member.email_address,
                    "chat_handle": member.chat_handle,
                }
            )
        return roster

    def _format_recent_emails(self, emails: list[dict[str, Any]]) -> str:
        """
        Format recent emails for prompt inclusion.

        Args:
            emails: List of email dictionaries

        Returns:
            Formatted email list string
        """
        if not emails:
            if self.locale == "ko":
                return "최근 이메일 없음"
            return "No recent emails"

        lines = []
        if self.locale == "ko":
            lines.append("최근 이메일 (스레드 컨텍스트용):")
        else:
            lines.append("Recent Emails (for threading context):")

        for i, email in enumerate(emails[-5:], 1):
            email_id = email.get("email_id", f"email-{i}")
            from_addr = email.get("from", "unknown")
            subject = email.get("subject", "No subject")
            lines.append(f"  [{email_id}] From: {from_addr} - Subject: {subject}")

        return "\n".join(lines)

    def _format_active_projects(self, projects: list[dict[str, Any]]) -> str:
        """
        Format active projects for multi-project scenarios.

        Args:
            projects: List of project dictionaries

        Returns:
            Formatted project list string
        """
        if not projects:
            return ""

        lines = []
        if self.locale == "ko":
            lines.append("중요: 현재 여러 프로젝트를 동시에 진행 중입니다:")
        else:
            lines.append("IMPORTANT: You are currently working on MULTIPLE projects concurrently:")

        for i, proj in enumerate(projects, 1):
            project_name = proj.get("project_name", f"Project {i}")
            plan = proj.get("plan", "")
            lines.append(f"\nProject {i}: {project_name}")
            # Truncate plan for brevity
            if len(plan) > 500:
                lines.append(plan[:500] + "...")
            else:
                lines.append(plan)

        if self.locale == "ko":
            lines.append("\n하루 동안 이 프로젝트들 사이를 자연스럽게 전환해야 합니다.")
        else:
            lines.append("\nYou should naturally switch between these projects throughout your day.")

        return "\n".join(lines)
