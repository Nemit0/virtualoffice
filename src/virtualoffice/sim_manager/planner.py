from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable, Protocol, Sequence

try:
    from virtualoffice.utils.completion_util import generate_text
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    def generate_text(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError(
            "OpenAI client is not installed; install optional dependencies to enable planning."
        )

from .schemas import PersonRead

PlanGenerator = Callable[[list[dict[str, str]], str], tuple[str, int]]



DEFAULT_PROJECT_MODEL = os.getenv("VDOS_PLANNER_PROJECT_MODEL", "gpt-4o-mini")
DEFAULT_DAILY_MODEL = os.getenv("VDOS_PLANNER_DAILY_MODEL", DEFAULT_PROJECT_MODEL)
DEFAULT_HOURLY_MODEL = os.getenv("VDOS_PLANNER_HOURLY_MODEL", DEFAULT_DAILY_MODEL)
DEFAULT_DAILY_REPORT_MODEL = os.getenv("VDOS_PLANNER_DAILY_REPORT_MODEL")
DEFAULT_SIM_REPORT_MODEL = os.getenv("VDOS_PLANNER_SIM_REPORT_MODEL")

@dataclass
class PlanResult:
    content: str
    model_used: str
    tokens_used: int | None = None


class PlanningError(RuntimeError):
    """Raised when an LLM-backed planning attempt fails."""


class Planner(Protocol):
    def generate_project_plan(
        self,
        *,
        department_head: PersonRead,
        project_name: str,
        project_summary: str,
        duration_weeks: int,
        team: Sequence[PersonRead],
        model_hint: str | None = None,
    ) -> PlanResult:
        ...

    def generate_daily_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        duration_weeks: int,
        team: Sequence[PersonRead] | None = None,
        model_hint: str | None = None,
    ) -> PlanResult:
        ...

    def generate_hourly_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        daily_plan: str,
        tick: int,
        context_reason: str,
        team: Sequence[PersonRead] | None = None,
        model_hint: str | None = None,
        all_active_projects: list[dict[str, Any]] | None = None,
    ) -> PlanResult:
        ...

    def generate_hourly_summary(
        self,
        *,
        worker: PersonRead,
        hour_index: int,
        hourly_plans: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        ...

    def generate_daily_report(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        daily_plan: str,
        hourly_log: str,
        minute_schedule: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        ...

    def generate_simulation_report(
        self,
        *,
        project_plan: str,
        team: Sequence[PersonRead],
        total_ticks: int,
        tick_log: str,
        daily_reports: str,
        event_summary: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        ...


class GPTPlanner:
    """Planner that delegates plan generation to OpenAI chat completions."""

    def __init__(
        self,
        generator: PlanGenerator | None = None,
        project_model: str = DEFAULT_PROJECT_MODEL,
        daily_model: str = DEFAULT_DAILY_MODEL,
        hourly_model: str = DEFAULT_HOURLY_MODEL,
        daily_report_model: str | None = DEFAULT_DAILY_REPORT_MODEL,
        simulation_report_model: str | None = DEFAULT_SIM_REPORT_MODEL,
    ) -> None:
        if generator is None:
            def _default(messages: list[dict[str, str]], model: str) -> tuple[str, int]:
                return generate_text(messages, model=model)

            self._generator = _default
        else:
            self._generator = generator
        self.project_model = project_model
        self.daily_model = daily_model
        self.hourly_model = hourly_model
        self.daily_report_model = daily_report_model or daily_model
        self.simulation_report_model = simulation_report_model or project_model
        self._locale = os.getenv("VDOS_LOCALE", "en").strip().lower() or "en"

    def generate_project_plan(
        self,
        *,
        department_head: PersonRead,
        project_name: str,
        project_summary: str,
        duration_weeks: int,
        team: Sequence[PersonRead],
        model_hint: str | None = None,
    ) -> PlanResult:
        team_lines = "\n".join(f"- {member.name} ({member.role})" for member in team)
        user_content = "\n".join(
            [
                f"Project name: {project_name}",
                f"Summary: {project_summary}",
                f"Duration: {duration_weeks} weeks",
                "Team:",
                team_lines,
                "",
                "Create a week-by-week plan with milestones, owners, risk mitigations, and explicit buffer time for each phase.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a meticulous department head responsible for designing cross-disciplinary project roadmaps. "
                    "Ensure the plan keeps teams finishing ahead of schedule with documented buffers. "
                    "Write as a human colleague; stay in character. Do not mention being an AI or a simulation. "
                    "Keep language natural and professional. Do not include model names, tokens, or implementation meta."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.project_model
        # Language enforcement
        if self._locale == "ko":
            messages = [
                {"role": "system", "content": "모든 응답은 자연스러운 한국어로만 작성하세요. 영어 표현을 사용하지 마세요."},
                *messages,
            ]
        return self._invoke(messages, model)

    def generate_daily_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        duration_weeks: int,
        team: Sequence[PersonRead] | None = None,
        model_hint: str | None = None,
    ) -> PlanResult:
        # Build team roster
        team_roster_lines = []
        if team:
            team_roster_lines.append("Team Roster:")
            for member in team:
                if member.id == worker.id:
                    continue  # Skip self
                team_roster_lines.append(
                    f"- {member.name} ({member.role}) - Email: {member.email_address}, Chat: @{member.chat_handle}"
                )
            team_roster_lines.append("")  # Add blank line

        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) in {worker.timezone}.",
                *team_roster_lines,
                f"Project duration: {duration_weeks} weeks. Today is day {day_index + 1}.",
                "Project plan excerpt:",
                project_plan,
                "",
                "Outline today's key objectives, planned communications, and the time reserved as buffer.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You help knowledge workers turn project plans into focused daily objectives, finishing at least one hour early. "
                    "Write as a real person. Avoid any meta-commentary about prompts, models, or simulation."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.daily_model
        if self._locale == "ko":
            messages = [
                {"role": "system", "content": "모든 응답은 자연스러운 한국어로만 작성하세요. 영어 표현을 사용하지 마세요."},
                *messages,
            ]
        return self._invoke(messages, model)

    def generate_hourly_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        daily_plan: str,
        tick: int,
        context_reason: str,
        team: Sequence[PersonRead] | None = None,
        model_hint: str | None = None,
        all_active_projects: list[dict[str, Any]] | None = None,
        recent_emails: list[dict[str, Any]] | None = None,
    ) -> PlanResult:
        # Encourage explicit, machine-parseable scheduled comm lines for the engine.
        wh = getattr(worker, "work_hours", "09:00-17:00") or "09:00-17:00"

        # Build team roster with explicit email addresses
        team_roster_lines = []
        valid_emails = []
        if team:
            team_roster_lines.append("Team Roster:")
            for member in team:
                if member.id == worker.id:
                    continue  # Skip self
                team_roster_lines.append(
                    f"- {member.name} ({member.role}) - Email: {member.email_address}, Chat: @{member.chat_handle}"
                )
                valid_emails.append(member.email_address)
            team_roster_lines.append("")  # Add blank line
        else:
            team_roster_lines.append(f"Known handles: {worker.chat_handle}.")

        # Build recent emails context for threading
        recent_emails_lines = []
        if recent_emails:
            recent_emails_lines.append("Recent Emails (for threading context):")
            for i, email in enumerate(recent_emails[-5:], 1):  # Show last 5 emails
                email_id = email.get('email_id', f'email-{i}')
                from_addr = email.get('from', 'unknown')
                subject = email.get('subject', 'No subject')
                recent_emails_lines.append(f"  [{email_id}] From: {from_addr} - Subject: {subject}")
            recent_emails_lines.append("")

        # Handle multiple concurrent projects
        project_context_lines = []
        if all_active_projects and len(all_active_projects) > 1:
            project_context_lines.append("IMPORTANT: You are currently working on MULTIPLE projects concurrently:")
            for i, proj in enumerate(all_active_projects, 1):
                project_context_lines.append(f"\nProject {i}: {proj['project_name']}")
                project_context_lines.append(proj['plan'][:500] + "...")  # Truncate for brevity
            project_context_lines.append("\nYou should naturally switch between these projects throughout your day.")
            project_context_lines.append("When writing emails/chats, specify which project each communication relates to in the subject/message.")
            project_context_lines.append("Example: 'Email at 10:00 to dev cc pm: [Mobile App MVP] API integration status | ...'")
            project_reference = "\n".join(project_context_lines)
        else:
            project_reference = f"Project reference:\n{project_plan}"

        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) at tick {tick}.",
                f"Trigger: {context_reason}.",
                f"Work hours today: {wh} (only schedule inside these).",
                "",
                *team_roster_lines,
                *recent_emails_lines,
                project_reference,
                "",
                "Daily focus:",
                daily_plan,
                "",
                "Plan the next few hours with realistic tasking and 10–15m buffers.",
                "",
                "CRITICAL: At the end, add a block titled 'Scheduled Communications' with 3–5 communication lines.",
                "You MUST use these EXACT formats:",
                "",
                "Email format (you MUST include cc or bcc in most emails for transparency):",
                "- Email at HH:MM to TARGET cc PERSON1, PERSON2 bcc PERSON3: Subject | Body text",
                "",
                "Reply to email format (use when responding to a recent email):",
                "- Reply at HH:MM to [email-id] cc PERSON: Subject | Body text",
                "  Example: Reply at 14:00 to [email-42] cc dev@domain: RE: API status | Thanks for the update...",
                "",
                "Chat format:",
                "- Chat at HH:MM with TARGET: message text",
                "",
                "EMAIL CONTENT GUIDELINES (IMPORTANT):",
                "1. EMAIL LENGTH: Write substantive email bodies with 3-5 sentences minimum",
                "   - Include specific details, context, and clear action items",
                "   - Good example: 'Working on the login API integration. Completed the OAuth flow and user session management. Need to discuss error handling strategies with the team. Can we sync tomorrow at 2pm? Also, should we implement rate limiting now or in v2?'",
                "   - Bad example: 'Update on API work. Making progress.'",
                "",
                "2. PROJECT CONTEXT IN SUBJECTS: When working on multiple projects, include project tag in subject",
                "   - Format: '[ProjectName] actual subject'",
                "   - Example: '[Mobile App MVP] API integration status update'",
                "   - Example: '[웹 대시보드] 디자인 리뷰 요청'",
                "   - Use this for about 60-70% of work-related emails",
                "",
                "3. EMAIL REALISM: Make emails sound natural and professional",
                "   - Start with context or greeting when appropriate",
                "   - Include specific technical details or business context",
                "   - End with clear next steps or questions",
                "   - Vary your communication style (not all emails need to be formal)",
                "",
                "EMAIL RULES (VERY IMPORTANT):",
                "1. ONLY use email addresses EXACTLY as shown in the Team Roster above",
                "2. NEVER create new email addresses, distribution lists, or group aliases",
                "3. NEVER use chat handles in email fields - use ONLY the full email addresses",
                "4. For project updates: cc the department head by their EXACT email address",
                "5. For technical decisions: cc relevant peers by their EXACT email addresses",
                "6. For status reports: cc team members by their EXACT email addresses",
                "7. Use 'cc' when recipients should know about each other",
                "8. Use 'bcc' when you want to privately loop someone in",
                "",
                "VALID EMAIL ADDRESSES (use ONLY these):",
                *(f"  - {email}" for email in valid_emails),
                "",
                "CORRECT EXAMPLES:",
                f"- Email at 10:30 to {valid_emails[0] if valid_emails else 'colleague.1@example.dev'} cc {valid_emails[1] if len(valid_emails) > 1 else 'manager.1@example.dev'}: Sprint update | Completed auth module",
                f"- Chat at 11:00 with {team[0].chat_handle if team else 'colleague'}: Quick question about the API endpoint",
                "",
                "WRONG EXAMPLES (DO NOT DO THIS):",
                "- Email at 10:30 to dev cc pm: ... (WRONG - use full email addresses!)",
                "- Email at 10:30 to team@company.dev: ... (WRONG - no distribution lists!)",
                "- Email at 10:30 to all: ... (WRONG - specify exact recipients!)",
                "",
                "Do not add bracketed headers or meta text besides 'Scheduled Communications'.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You act as an operations coach who reshapes hourly schedules. Keep outputs concise, actionable, and include buffers. "
                    "Use natural phrasing; for chat moments be conversational, for email be slightly more formal. "
                    "Adopt the worker's tone/personality for phrasing and word choice. "
                    "Never mention being an AI, a simulation, or the generation process. "
                    "At the end, you MUST output a 'Scheduled Communications' block with lines starting EXACTLY with 'Email at' or 'Chat at' as specified. "
                    "CRITICAL EMAIL ADDRESS RULE: You MUST use ONLY the exact email addresses provided in the 'VALID EMAIL ADDRESSES' list. "
                    "NEVER create email addresses, distribution lists (like team@, all@, manager@), or use chat handles in email fields. "
                    "When writing email lines with cc/bcc, use ONLY the full email addresses from the valid list. "
                    "Follow the format exactly: 'Email at HH:MM to user.1@domain.dev cc user.2@domain.dev: Subject | Body' "
                    "IMPORTANT: Write substantive email bodies with 3-5 sentences minimum, including specific details and context. "
                    "Include project tags in subjects when working on multiple projects (e.g., '[Mobile App] API status'). "
                    "Make emails realistic and professional with clear action items or questions."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.hourly_model
        if self._locale == "ko":
            messages = [
                {"role": "system", "content": "모든 응답은 자연스러운 한국어로만 작성하세요. 영어 표현을 사용하지 마세요."},
                *messages,
            ]
        return self._invoke(messages, model)

    def generate_daily_report(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        daily_plan: str,
        hourly_log: str,
        minute_schedule: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) day {day_index + 1}.",
                "Daily plan:",
                daily_plan,
                "",
                "Hourly log:",
                hourly_log or "No hourly updates recorded.",
                "",
                "Summarise the day with key highlights, note communications, and flag risks for tomorrow.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an operations chief of staff producing concise daily reports. "
                    "Summarize key achievements, decisions, communications, and any blockers. "
                    "Write as a human; avoid references to AI, simulation, prompts, or models."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.daily_report_model
        if self._locale == "ko":
            messages = [
                {"role": "system", "content": "모든 응답은 자연스러운 한국어로만 작성하세요. 영어 표현을 사용하지 마세요."},
                *messages,
            ]
        return self._invoke(messages, model)

    def generate_hourly_summary(
        self,
        *,
        worker: PersonRead,
        hour_index: int,
        hourly_plans: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        """Generate a concise summary of an hour's worth of activity."""
        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) - Hour {hour_index + 1}",
                "",
                "Hourly plans for this hour:",
                hourly_plans,
                "",
                "Summarize this hour's activities in 2-3 concise bullet points.",
                "Focus on: key tasks completed, communications sent, and any blockers/decisions.",
                "Keep it brief - this is for aggregating into daily reports."
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You create brief hourly activity summaries. "
                    "Output 2-3 bullet points maximum. Be concise and factual. "
                    "Never mention being an AI or simulation."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.hourly_model
        if self._locale == "ko":
            messages = [
                {"role": "system", "content": "모든 응답은 자연스러운 한국어로만 작성하세요. 영어 표현을 사용하지 마세요."},
                *messages,
            ]
        return self._invoke(messages, model)

    def generate_simulation_report(
        self,
        *,
        project_plan: str,
        team: Sequence[PersonRead],
        total_ticks: int,
        tick_log: str,
        daily_reports: str,
        event_summary: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        team_lines = "\n".join(f"- {member.name} ({member.role})" for member in team)
        user_content = "\n".join(
            [
                f"Total ticks: {total_ticks}",
                "Team:",
                team_lines,
                "",
                "Project plan:",
                project_plan,
                "",
                "Tick log:",
                tick_log or "No ticks processed.",
                "",
                "Daily reports:",
                daily_reports or "No daily reports logged.",
                "",
                "Events:",
                event_summary,
                "",
                "Produce an executive summary covering achievements, issues, communications, and next steps.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the department head preparing an end-of-run retrospective. "
                    "Highlight cross-team coordination, risks, and readiness for the next cycle. "
                    "Produce a natural, human summary with clear bullets and executive tone. No meta or AI references."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.simulation_report_model
        if self._locale == "ko":
            messages = [
                {"role": "system", "content": "모든 응답은 자연스러운 한국어로만 작성하세요. 영어 표현을 사용하지 마세요."},
                *messages,
            ]
        return self._invoke(messages, model)

    def _invoke(self, messages: list[dict[str, str]], model: str) -> PlanResult:
        try:
            content, tokens = self._generator(messages, model)
        except Exception as exc:  # pragma: no cover - surface as planning failure
            raise PlanningError(str(exc)) from exc
        return PlanResult(content=content, model_used=model, tokens_used=tokens)


class StubPlanner:
    """Fallback planner that produces deterministic text without external calls."""

    def _result(self, label: str, body: str, model: str) -> PlanResult:
        # Return plain natural text to avoid placeholder headers like [Hourly Plan].
        content = body
        return PlanResult(content=content, model_used=model, tokens_used=0)

    def generate_project_plan(
        self,
        *,
        department_head: PersonRead,
        project_name: str,
        project_summary: str,
        duration_weeks: int,
        team: Sequence[PersonRead],
        model_hint: str | None = None,
    ) -> PlanResult:
        teammates = "\n".join(f"- {member.name} ({member.role})" for member in team)
        body = "\n".join([
            f"Project: {project_name}",
            f"Summary: {project_summary}",
            f"Duration: {duration_weeks} week(s)",
            f"Department head: {department_head.name}",
            "Team:",
            teammates or "- (none)",
            "Initial focus: break work into design, build, review, and communication checkpoints.",
        ])
        model = model_hint or "vdos-stub-project"
        return self._result("Project Plan", body, model)

    def generate_daily_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        duration_weeks: int,
        team: Sequence[PersonRead] | None = None,
        model_hint: str | None = None,
    ) -> PlanResult:
        total_days = max(duration_weeks, 1) * 5
        body = "\n".join([
            f"Worker: {worker.name} ({worker.role})",
            f"Day: {day_index + 1} / {total_days}",
            "Goals:",
            "- Advance project milestones",
            "- Communicate blockers",
            "- Capture progress for end-of-day report",
        ])
        model = model_hint or "vdos-stub-daily"
        return self._result("Daily Plan", body, model)

    def generate_hourly_plan(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        daily_plan: str,
        tick: int,
        context_reason: str,
        team: Sequence[PersonRead] | None = None,
        model_hint: str | None = None,
        all_active_projects: list[dict[str, Any]] | None = None,
    ) -> PlanResult:
        # Deterministic, human-like plan with explicit scheduled comms later in the workday
        start, end = ("09:00", "17:00")
        if getattr(worker, "work_hours", None) and "-" in worker.work_hours:
            try:
                parts = [p.strip() for p in worker.work_hours.split("-", 1)]
                if len(parts) == 2:
                    start, end = parts
            except Exception:
                pass
        # Pick sensible default contacts for a 2-person run: designer <-> dev
        me = (worker.chat_handle or worker.name or "worker").lower()
        other = "designer" if "dev" in me or "full" in (worker.role or "").lower() else "dev"
        # A couple of realistic touchpoints
        sched = [
            f"Chat at 09:10 with {other}: Morning! Quick sync on priorities?",
            f"Email at 09:35 to {other}: Subject: Kickoff | Body: Plan for the morning and any blockers",
            f"Chat at 14:20 with {other}: Checking in on progress, anything I can unblock?",
        ]
        hour = tick % 60 or 60
        lines = [
            f"Worker: {worker.name}",
            f"Tick: {tick} (minute {hour})",
            f"Reason: {context_reason}",
            "Focus for the next hours:",
            "- Review priorities",
            "- Heads-down execution",
            "- Share update with teammate",
            "",
            "Scheduled Communications:",
            *sched,
        ]
        body = "\n".join(lines)
        model = model_hint or "vdos-stub-hourly"
        return self._result("Hourly Plan", body, model)

    def generate_hourly_summary(
        self,
        *,
        worker: PersonRead,
        hour_index: int,
        hourly_plans: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        body = f"- Continued project work\n- Coordinated with team\n- {hour_index + 1} hour(s) logged"
        model = model_hint or "vdos-stub-hourly-summary"
        return self._result("Hourly Summary", body, model)

    def generate_daily_report(
        self,
        *,
        worker: PersonRead,
        project_plan: str,
        day_index: int,
        daily_plan: str,
        hourly_log: str,
        minute_schedule: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        body = "\n".join([
            f"Worker: {worker.name}",
            f"Day {day_index + 1} summary",
            "Highlights:",
            "- Delivered planned work",
            "- Communicated status",
            "Risks:",
            "- Pending follow-ups",
        ])
        model = model_hint or "vdos-stub-daily-report"
        return self._result("Daily Report", body, model)

    def generate_simulation_report(
        self,
        *,
        project_plan: str,
        team: Sequence[PersonRead],
        total_ticks: int,
        tick_log: str,
        daily_reports: str,
        event_summary: str,
        model_hint: str | None = None,
    ) -> PlanResult:
        teammates = ", ".join(person.name for person in team) or "(none)"
        body = "\n".join([
            f"Total ticks: {total_ticks}",
            f"Team: {teammates}",
            "Recap:",
            "- Work advanced",
            "- Communications logged",
            "- Review outstanding risks",
        ])
        model = model_hint or "vdos-stub-simulation"
        return self._result("Simulation Report", body, model)
