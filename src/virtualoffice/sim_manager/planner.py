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
from virtualoffice.common.localization import get_current_locale_manager
from virtualoffice.common.korean_templates import get_korean_prompt
from virtualoffice.common.korean_validation import validate_korean_content

PlanGenerator = Callable[[list[dict[str, str]], str], tuple[str, int]]



DEFAULT_PROJECT_MODEL = os.getenv("VDOS_PLANNER_PROJECT_MODEL", "gpt-4o-mini")
DEFAULT_DAILY_MODEL = os.getenv("VDOS_PLANNER_DAILY_MODEL", DEFAULT_PROJECT_MODEL)
DEFAULT_HOURLY_MODEL = os.getenv("VDOS_PLANNER_HOURLY_MODEL", DEFAULT_DAILY_MODEL)
DEFAULT_DAILY_REPORT_MODEL = os.getenv("VDOS_PLANNER_DAILY_REPORT_MODEL")
DEFAULT_SIM_REPORT_MODEL = os.getenv("VDOS_PLANNER_SIM_REPORT_MODEL")

# Korean validation retry configuration
# Set to 0 to disable retries and speed up planning (accepts mixed Korean/English)
MAX_KOREAN_VALIDATION_RETRIES = int(os.getenv("VDOS_KOREAN_VALIDATION_RETRIES", "0"))

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
    
    def generate_with_messages(
        self,
        *,
        messages: list[dict[str, str]],
        model_hint: str | None = None,
    ) -> PlanResult:
        """
        Generate a plan using pre-built message list.
        
        This method allows using externally constructed prompts
        (e.g., from PromptManager) instead of the built-in prompt logic.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model_hint: Optional model override
            
        Returns:
            PlanResult with generated content
        """
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
        use_template_prompts: bool = False,
        hours_per_day: int = 8,
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
        self.use_template_prompts = use_template_prompts or os.getenv("VDOS_USE_TEMPLATE_PROMPTS", "").lower() in ("true", "1", "yes")
        self.hours_per_day = hours_per_day
        
        # Initialize prompt manager if using templates
        self._prompt_manager = None
        self._context_builder = None
        self._metrics_collector = None
        if self.use_template_prompts:
            try:
                from .prompts import PromptManager, ContextBuilder, PromptMetricsCollector
                import pathlib
                template_dir = pathlib.Path(__file__).parent / "prompts" / "templates"
                self._prompt_manager = PromptManager(str(template_dir), locale=self._locale)
                self._context_builder = ContextBuilder(locale=self._locale, hours_per_day=self.hours_per_day)
                self._metrics_collector = PromptMetricsCollector()
            except Exception as e:
                print(f"Warning: Failed to initialize prompt management system: {e}")
                self.use_template_prompts = False

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
                {"role": "system", "content": get_korean_prompt("business")},
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
        # Use template-based prompts if enabled
        if self.use_template_prompts and self._prompt_manager and self._context_builder:
            import time
            start_time = time.time()
            try:
                # Build context with Korean defaults
                persona_markdown = getattr(worker, 'persona_markdown', '') or f"역할: {worker.role}\n기술: 일반"
                team_roster = "\n".join(f"- {m.name} ({m.role}) - 이메일: {m.email_address}, 채팅: @{m.chat_handle}" for m in (team or []) if m.id != worker.id)
                
                context = {
                    "worker_name": worker.name,
                    "worker_role": worker.role or "팀원",
                    "worker_timezone": getattr(worker, "timezone", "Asia/Seoul"),
                    "persona_markdown": persona_markdown,
                    "team_roster": team_roster or "팀원 없음",
                    "duration_weeks": duration_weeks,
                    "day_number": day_index + 1,
                    "project_plan": project_plan,
                }
                
                # Build prompt from template
                messages = self._prompt_manager.build_prompt("daily", context)
                
                # Generate with metrics collection
                model = model_hint or self.daily_model
                result = self._invoke(messages, model)
                
                # Record metrics
                if self._metrics_collector:
                    duration_ms = (time.time() - start_time) * 1000
                    self._metrics_collector.record_usage(
                        template_name="daily_planning",
                        variant="default",
                        model_used=result.model_used,
                        tokens_used=result.tokens_used or 0,
                        duration_ms=duration_ms,
                        success=True,
                    )
                
                return result
            except Exception as e:
                print(f"Warning: Template-based prompt failed, falling back to hard-coded: {e}")
                if self._metrics_collector:
                    duration_ms = (time.time() - start_time) * 1000
                    self._metrics_collector.record_usage(
                        template_name="daily_planning",
                        variant="default",
                        model_used=model_hint or self.daily_model,
                        tokens_used=0,
                        duration_ms=duration_ms,
                        success=False,
                        error=str(e),
                    )
        
        # Original hard-coded prompt logic
        # Extract persona information for authentic planning
        persona_context = []
        if hasattr(worker, 'persona_markdown') and worker.persona_markdown:
            persona_context.append("=== YOUR PERSONA & WORKING STYLE ===")
            persona_context.append(worker.persona_markdown)
            persona_context.append("")
        
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
                "",
                *persona_context,
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
                    "IMPORTANT: Use the worker's persona information to create authentic plans that align with their skills, personality, and working style. "
                    "Write as a real person. Avoid any meta-commentary about prompts, models, or simulation."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.daily_model
        if self._locale == "ko":
            messages = [
                {"role": "system", "content": get_korean_prompt("business")},
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
        # Use template-based prompts if enabled
        if self.use_template_prompts and self._prompt_manager and self._context_builder:
            import time
            start_time = time.time()
            try:
                # Build context using ContextBuilder
                context = self._context_builder.build_planning_context(
                    worker=worker,
                    tick=tick,
                    reason=context_reason,
                    project_plan=project_plan,
                    daily_plan=daily_plan,
                    team=team or [],
                    recent_emails=recent_emails,
                    all_active_projects=all_active_projects,
                )
                
                # Add additional context fields needed by template
                context["project_reference"] = project_plan
                context["valid_email_list"] = "\n".join(f"  - {m.email_address}" for m in (team or []) if m.id != worker.id)
                
                # Build example communications in Korean
                valid_emails = [m.email_address for m in (team or []) if m.id != worker.id]
                examples = []
                if valid_emails:
                    examples.append(f"- 이메일 10:30에 {valid_emails[0]} 참조 {valid_emails[1] if len(valid_emails) > 1 else valid_emails[0]}: 스프린트 업데이트 | 인증 모듈 완료, 리뷰 준비됨")
                if team:
                    examples.append(f"- 채팅 11:00에 {team[0].chat_handle if team[0].id != worker.id else (team[1].chat_handle if len(team) > 1 else 'colleague')}과: API 엔드포인트 관련 질문")
                examples.append("- 채팅 11:00에 팀과: 스프린트 진행 상황 업데이트 (프로젝트 그룹 채팅으로 전송)")
                if valid_emails:
                    examples.append(f"- 답장 14:00에 [email-42] 참조 {valid_emails[0]}: RE: API 상태 | 업데이트 감사합니다, 통합 진행하겠습니다")
                context["correct_examples"] = "\n".join(examples)
                
                # Build prompt from template
                messages = self._prompt_manager.build_prompt("hourly", context)
                
                # Generate with metrics collection
                model = model_hint or self.hourly_model
                result = self._invoke(messages, model)
                
                # Record metrics
                if self._metrics_collector:
                    duration_ms = (time.time() - start_time) * 1000
                    self._metrics_collector.record_usage(
                        template_name="hourly_planning",
                        variant="default",
                        model_used=result.model_used,
                        tokens_used=result.tokens_used or 0,
                        duration_ms=duration_ms,
                        success=True,
                    )
                
                return result
            except Exception as e:
                # Fall back to hard-coded prompts on error
                print(f"Warning: Template-based prompt failed, falling back to hard-coded: {e}")
                if self._metrics_collector:
                    duration_ms = (time.time() - start_time) * 1000
                    self._metrics_collector.record_usage(
                        template_name="hourly_planning",
                        variant="default",
                        model_used=model_hint or self.hourly_model,
                        tokens_used=0,
                        duration_ms=duration_ms,
                        success=False,
                        error=str(e),
                    )
        
        # Original hard-coded prompt logic
        # Encourage explicit, machine-parseable scheduled comm lines for the engine.
        wh = getattr(worker, "work_hours", "09:00-17:00") or "09:00-17:00"
        
        # Extract persona information for authentic planning
        persona_context = []
        if hasattr(worker, 'persona_markdown') and worker.persona_markdown:
            persona_context.append("=== YOUR PERSONA & WORKING STYLE ===")
            persona_context.append(worker.persona_markdown)
            persona_context.append("")

        # Build team roster with explicit email addresses
        team_roster_lines = []
        valid_emails = []
        name_to_email_map = []  # Clear mapping for Korean names
        if team:
            team_roster_lines.append("=== YOUR TEAM ROSTER ===")
            team_roster_lines.append("(Use ONLY these exact email addresses - never create new ones!)")
            team_roster_lines.append("")

            # First, show YOURSELF for reference
            team_roster_lines.append(f"YOU: {worker.name} ({worker.role})")
            team_roster_lines.append(f"  Your Email: {worker.email_address}")
            team_roster_lines.append(f"  Your Chat: {worker.chat_handle}")
            team_roster_lines.append("")

            team_roster_lines.append("YOUR TEAMMATES:")
            for member in team:
                if member.id == worker.id:
                    continue  # Already showed above
                team_roster_lines.append(f"- {member.name} ({member.role})")
                team_roster_lines.append(f"  Email: {member.email_address}")
                team_roster_lines.append(f"  Chat: {member.chat_handle}")
                valid_emails.append(member.email_address)
                name_to_email_map.append(f"  '{member.name}' = {member.email_address}")

            team_roster_lines.append("")
            team_roster_lines.append("CRITICAL NAME-TO-EMAIL MAPPING:")
            team_roster_lines.append("When writing emails, use these EXACT email addresses:")
            team_roster_lines.extend(name_to_email_map)
            team_roster_lines.append("")
        else:
            team_roster_lines.append(f"Known handles: {worker.chat_handle}.")

        # Build recent emails context for threading
        recent_emails_lines = []
        if recent_emails:
            recent_emails_lines.append("Recent Emails (for threading context):")
            for i, email in enumerate(recent_emails[-5:], 1):  # Show last 5 emails
                email_id = email.get('email_id', f'email-{i}')
                from_addr = email.get('from', '알 수 없음')
                subject = email.get('subject', '제목 없음')
                recent_emails_lines.append(f"  [{email_id}] 발신: {from_addr} - 제목: {subject}")
            recent_emails_lines.append("")

        # Handle multiple concurrent projects
        project_context_lines = []
        if all_active_projects and len(all_active_projects) > 1:
            project_context_lines.append("중요: 현재 여러 프로젝트를 동시에 진행 중입니다:")
            for i, proj in enumerate(all_active_projects, 1):
                project_context_lines.append(f"\n프로젝트 {i}: {proj['project_name']}")
                project_context_lines.append(proj['plan'][:500] + "...")  # Truncate for brevity
            project_context_lines.append("\n하루 동안 이 프로젝트들 사이를 자연스럽게 전환해야 합니다.")
            project_context_lines.append("이메일/채팅 작성 시 제목/메시지에 각 커뮤니케이션이 관련된 프로젝트를 명시하세요.")
            project_context_lines.append("예시: '이메일 10:00에 dev 참조 pm: [모바일 앱 MVP] API 통합 상태 | ...'")
            project_reference = "\n".join(project_context_lines)
        else:
            project_reference = f"프로젝트 참조:\n{project_plan}"

        # Build format templates based on locale
        format_templates = []
        if self._locale == "ko":
            format_templates.extend([
                "다음 형식을 정확히 사용하세요:",
                "",
                "이메일 형식 (투명성을 위해 대부분의 이메일에 참조 또는 숨은참조 포함 필수):",
                "- 이메일 HH:MM에 TARGET 참조 PERSON1, PERSON2 숨은참조 PERSON3: 제목 | 본문 내용",
                "",
                "이메일 답장 형식 (최근 이메일에 답장할 때 사용):",
                "- 답장 HH:MM에 [email-id] 참조 PERSON: 제목 | 본문 내용",
                "  예시: 답장 14:00에 [email-42] 참조 dev@domain: RE: API 상태 | 업데이트 감사합니다...",
                "",
                "채팅 형식:",
                "- 채팅 HH:MM에 TARGET과: 메시지 내용",
                "",
                "채팅 대상 옵션:",
                "- 개인: 채팅 11:00에 colleague_handle과: 개인 메시지",
                "- 프로젝트 팀: 채팅 11:00에 팀과: 프로젝트 그룹 채팅 메시지",
                "- 프로젝트 팀: 채팅 11:00에 프로젝트와: 프로젝트 그룹 채팅 메시지",
                "- 프로젝트 팀: 채팅 11:00에 그룹과: 프로젝트 그룹 채팅 메시지",
                "",
                "그룹 채팅 vs 개인 메시지 사용 시기:",
                "- '팀/프로젝트/그룹' 사용: 상태 업데이트, 차단 요소, 공지사항, 조정",
                "- 개인 핸들 사용: 개인적인 질문, 민감한 피드백, 개인 확인",
            ])
        else:
            format_templates.extend([
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
                "Chat target options:",
                "- Individual: Chat at 11:00 with colleague_handle: Private message",
                "- Project team: Chat at 11:00 with team: Message to project group chat",
                "- Project team: Chat at 11:00 with project: Message to project group chat",
                "- Project team: Chat at 11:00 with group: Message to project group chat",
                "",
                "그룹 채팅 vs 개인 메시지 사용 시기:",
                "- '팀/프로젝트/그룹' 사용: 상태 업데이트, 차단 요소, 공지사항, 조정",
                "- 개인 핸들 사용: 개인적인 질문, 민감한 피드백, 개인 확인",
            ])

        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) at tick {tick}.",
                f"Trigger: {context_reason}.",
                f"Work hours today: {wh} (only schedule inside these).",
                "",
                *persona_context,
                *team_roster_lines,
                *recent_emails_lines,
                project_reference,
                "",
                "Daily focus:",
                daily_plan,
                "",
                "Plan the next few hours with realistic tasking and 10–15m buffers.",
                "",
                f"CRITICAL: At the end, add a block titled '{get_current_locale_manager().get_text('scheduled_communications')}' with 3–5 communication lines.",
                *format_templates,
                "",
                "그룹 채팅 vs 개인 메시지 사용 시기:",
                "- '팀/프로젝트/그룹' 사용: 상태 업데이트, 차단 요소, 공지사항, 조정",
                "- 개인 핸들 사용: 개인적인 질문, 민감한 피드백, 개인 확인",
                "",
                "이메일 내용 가이드라인 (중요):",
                "1. 이메일 길이: 최소 3-5문장으로 실질적인 이메일 본문 작성",
                "   - 구체적인 세부사항, 맥락, 명확한 조치 사항 포함",
                "   - 좋은 예시: '로그인 API 통합 작업 중입니다. OAuth 플로우와 사용자 세션 관리를 완료했습니다. 팀과 오류 처리 전략을 논의해야 합니다. 내일 오후 2시에 동기화할 수 있을까요? 또한 속도 제한을 지금 구현할지 v2에서 할지 결정해야 합니다.'",
                "   - 나쁜 예시: 'API 작업 업데이트. 진행 중입니다.'",
                "",
                "2. 제목에 프로젝트 맥락: 여러 프로젝트 작업 시 제목에 프로젝트 태그 포함",
                "   - 형식: '[프로젝트명] 실제 제목'",
                "   - 예시: '[모바일 앱 MVP] API 통합 상태 업데이트'",
                "   - 예시: '[웹 대시보드] 디자인 리뷰 요청'",
                "   - 업무 관련 이메일의 약 60-70%에 사용",
                "",
                "3. 이메일 현실성: 이메일을 자연스럽고 전문적으로 작성",
                "   - 적절한 경우 맥락이나 인사말로 시작",
                "   - 구체적인 기술 세부사항 또는 비즈니스 맥락 포함",
                "   - 명확한 다음 단계 또는 질문으로 마무리",
                "   - 커뮤니케이션 스타일을 다양화 (모든 이메일이 공식적일 필요는 없음)",
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
                "올바른 예시 (다음 패턴을 따르세요):",
                f"- 이메일 10:30에 {valid_emails[0] if valid_emails else 'colleague.1@example.dev'} 참조 {valid_emails[1] if len(valid_emails) > 1 else 'manager.1@example.dev'}: 스프린트 업데이트 | 인증 모듈 완료, 리뷰 준비됨",
                f"- 채팅 11:00에 {team[0].chat_handle if team else 'colleague'}과: API 엔드포인트 관련 질문",
                "- 채팅 11:00에 팀과: 스프린트 진행 상황 업데이트 (프로젝트 그룹 채팅으로 전송)",
                f"- 답장 14:00에 [email-42] 참조 {valid_emails[0] if valid_emails else 'lead@example.dev'}: RE: API 상태 | 업데이트 감사합니다, 통합 진행하겠습니다",
                "",
                "잘못된 예시 (절대 하지 마세요):",
                "- 이메일 10:30에 dev 참조 pm: ... (잘못됨 - 'dev'와 'pm'은 이메일 주소가 아닙니다!)",
                "- 이메일 10:30에 team@company.dev: ... (잘못됨 - 배포 목록은 존재하지 않습니다!)",
                "- 이메일 10:30에 all: ... (잘못됨 - 정확한 이메일 주소를 지정하세요!)",
                "- 이메일 10:30에 김민수: ... (잘못됨 - 사람 이름이 아닌 이메일 주소를 사용하세요!)",
                "- 이메일 10:30에 @colleague: ... (잘못됨 - @는 채팅용이며, 이메일 주소를 사용하세요!)",
                "",
                f"Do not add bracketed headers or meta text besides '{get_current_locale_manager().get_text('scheduled_communications')}'.",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You act as an operations coach who reshapes hourly schedules. Keep outputs concise, actionable, and include buffers. "
                    "Use natural phrasing; for chat moments be conversational, for email be slightly more formal. "
                    "IMPORTANT: You have detailed persona information about the worker - use their specific skills, personality traits, and communication style to make authentic plans. "
                    "Adopt the worker's tone/personality for phrasing and word choice based on their persona details. "
                    "Plan tasks that align with their skills and working preferences. "
                    "Never mention being an AI, a simulation, or the generation process. "
                    f"At the end, you MUST output a '{get_current_locale_manager().get_text('scheduled_communications')}' block with lines starting EXACTLY with 'Email at' or 'Chat at' as specified. "
                    "\n"
                    "CRITICAL EMAIL ADDRESS RULES (FOLLOW EXACTLY):\n"
                    "1. You MUST use ONLY the exact email addresses shown in 'YOUR TEAM ROSTER' and 'VALID EMAIL ADDRESSES' sections\n"
                    "2. NEVER create, invent, or hallucinate email addresses - even if they seem logical\n"
                    "3. NEVER use distribution lists (team@, all@, manager@, dept@) - they don't exist\n"
                    "4. NEVER use chat handles in email fields - use the full email address\n"
                    "5. When names are in Korean/non-English, use the romanized email address shown in the mapping\n"
                    "6. Check the 'CRITICAL NAME-TO-EMAIL MAPPING' section to match names to correct emails\n"
                    "7. Example: If roster shows '김민수' = minsu.kim@company.kr, write 'Email to minsu.kim@company.kr' NOT 'Email to 김민수@company.kr'\n"
                    "\n"
                    "EMAIL FORMAT: 'Email at HH:MM to user.1@domain.dev cc user.2@domain.dev: Subject | Body'\n"
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
                {"role": "system", "content": f"{get_korean_prompt('comprehensive')} '{get_current_locale_manager().get_text('scheduled_communications')}' 섹션의 형식은 그대로 유지하되 내용은 한국어로 작성하세요."},
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
        # Use template-based prompts if enabled
        if self.use_template_prompts and self._prompt_manager and self._context_builder:
            import time
            start_time = time.time()
            try:
                # Build context using ContextBuilder
                context = self._context_builder.build_reporting_context(
                    worker=worker,
                    day_index=day_index,
                    daily_plan=daily_plan,
                    hourly_log=hourly_log,
                    minute_schedule=minute_schedule,
                )
                
                # Build prompt from template
                messages = self._prompt_manager.build_prompt("daily_report", context)
                
                # Generate with metrics collection
                model = model_hint or self.daily_report_model
                result = self._invoke(messages, model)
                
                # Record metrics
                if self._metrics_collector:
                    duration_ms = (time.time() - start_time) * 1000
                    self._metrics_collector.record_usage(
                        template_name="daily_report",
                        variant="default",
                        model_used=result.model_used,
                        tokens_used=result.tokens_used or 0,
                        duration_ms=duration_ms,
                        success=True,
                    )
                
                return result
            except Exception as e:
                print(f"Warning: Template-based prompt failed, falling back to hard-coded: {e}")
                if self._metrics_collector:
                    duration_ms = (time.time() - start_time) * 1000
                    self._metrics_collector.record_usage(
                        template_name="daily_report",
                        variant="default",
                        model_used=model_hint or self.daily_report_model,
                        tokens_used=0,
                        duration_ms=duration_ms,
                        success=False,
                        error=str(e),
                    )
        
        # Original hard-coded prompt logic
        # Extract persona information for authentic reporting
        persona_context = []
        if hasattr(worker, 'persona_markdown') and worker.persona_markdown:
            persona_context.append("=== YOUR PERSONA & WORKING STYLE ===")
            persona_context.append(worker.persona_markdown)
            persona_context.append("")
        
        user_content = "\n".join(
            [
                f"Worker: {worker.name} ({worker.role}) day {day_index + 1}.",
                "",
                *persona_context,
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
                    "IMPORTANT: Use the worker's persona information to write reports in their authentic voice and perspective. "
                    "Summarize key achievements, decisions, communications, and any blockers. "
                    "Write as a human; avoid references to AI, simulation, prompts, or models."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        model = model_hint or self.daily_report_model
        if self._locale == "ko":
            messages = [
                {"role": "system", "content": get_korean_prompt("business")},
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
                {"role": "system", "content": get_korean_prompt("business")},
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
                {"role": "system", "content": get_korean_prompt("business")},
                *messages,
            ]
        return self._invoke(messages, model)

    def generate_with_messages(
        self,
        *,
        messages: list[dict[str, str]],
        model_hint: str | None = None,
    ) -> PlanResult:
        """
        Generate a plan using pre-built message list.
        
        This method allows using externally constructed prompts
        (e.g., from PromptManager) instead of the built-in prompt logic.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model_hint: Optional model override
            
        Returns:
            PlanResult with generated content
        """
        model = model_hint or self.hourly_model
        return self._invoke(messages, model)
    
    def _invoke(self, messages: list[dict[str, str]], model: str) -> PlanResult:
        try:
            content, tokens = self._generator(messages, model)
            
            # Validate Korean content if locale is Korean
            if self._locale == "ko":
                content, tokens = self._validate_and_retry_korean_content(
                    messages, model, content, tokens
                )
            
        except Exception as exc:  # pragma: no cover - surface as planning failure
            raise PlanningError(str(exc)) from exc
        return PlanResult(content=content, model_used=model, tokens_used=tokens)
    
    def _validate_and_retry_korean_content(
        self, 
        messages: list[dict[str, str]], 
        model: str, 
        content: str, 
        tokens: int
    ) -> tuple[str, int]:
        """
        Validate Korean content and retry with enhanced prompts if English text is detected.
        
        Args:
            messages: Original messages for generation
            model: Model used for generation
            content: Generated content to validate
            tokens: Token count from original generation
            
        Returns:
            Tuple of (validated_content, total_tokens)
        """
        max_retries = MAX_KOREAN_VALIDATION_RETRIES
        total_tokens = tokens
        
        for attempt in range(max_retries + 1):
            is_valid, issues = validate_korean_content(content, strict_mode=True)
            
            if is_valid:
                # Content is valid Korean, return as-is
                return content, total_tokens
            
            if attempt < max_retries:
                # Content has English text, retry with enhanced Korean prompt
                print(f"Korean validation failed (attempt {attempt + 1}): {'; '.join(issues)}")
                
                # Create enhanced retry messages with stricter Korean enforcement
                retry_messages = [
                    {
                        "role": "system", 
                        "content": f"""CRITICAL: 이전 응답에서 영어 텍스트가 감지되었습니다. 
                        
다음 문제들이 발견되었습니다:
{chr(10).join(f'- {issue}' for issue in issues)}

이번에는 반드시 다음 규칙을 따르세요:
{get_korean_prompt('comprehensive')}

절대로 영어 단어나 표현을 사용하지 마세요. 모든 기술 용어와 비즈니스 용어를 한국어로 번역하여 사용하세요.
예시: 'API 통합' (O), 'API integration' (X)
예시: '데이터베이스 설정' (O), 'database setup' (X)
예시: '프로젝트 관리' (O), 'project management' (X)"""
                    }
                ] + messages[1:]  # Skip original system message, use enhanced one
                
                try:
                    retry_content, retry_tokens = self._generator(retry_messages, model)
                    content = retry_content
                    total_tokens += retry_tokens
                except Exception as exc:
                    print(f"Retry attempt {attempt + 1} failed: {exc}")
                    # Continue with original content if retry fails
                    break
            else:
                # Max retries reached, log warning and return best attempt
                print(f"Korean validation failed after {max_retries} retries. Using best attempt.")
                print(f"Remaining issues: {'; '.join(issues)}")
                break
        
        return content, total_tokens


class StubPlanner:
    """Fallback planner that produces deterministic text without external calls."""

    def _result(self, label: str, body: str, model: str) -> PlanResult:
        # Return plain natural text to avoid placeholder headers like [Hourly Plan].
        content = body
        return PlanResult(content=content, model_used=model, tokens_used=0)
    
    def generate_with_messages(
        self,
        *,
        messages: list[dict[str, str]],
        model_hint: str | None = None,
    ) -> PlanResult:
        """
        Generate a plan using pre-built message list.
        
        For StubPlanner, this just returns a simple deterministic response.
        
        Args:
            messages: List of message dicts (ignored in stub)
            model_hint: Optional model override
            
        Returns:
            PlanResult with stub content
        """
        model = model_hint or "vdos-stub-generic"
        body = "Stub plan generated from messages"
        return self._result("Generic Plan", body, model)

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
            f"작업자: {worker.name} ({worker.role})",
            f"일차: {day_index + 1} / {total_days}",
            "목표:",
            "- 프로젝트 마일스톤 진행",
            "- 차단 요소 커뮤니케이션",
            "- 일일 보고서를 위한 진행 상황 기록",
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
        # A couple of realistic touchpoints in Korean
        sched = [
            f"채팅 09:10에 {other}과: 안녕하세요! 우선순위 간단히 조율할까요?",
            f"이메일 09:35에 {other}: 제목: 킥오프 | 본문: 오전 계획 및 차단 요소",
            f"채팅 14:20에 {other}과: 진행 상황 확인, 제가 도울 부분 있나요?",
        ]
        hour = tick % 60 or 60
        lines = [
            f"작업자: {worker.name}",
            f"틱: {tick} (분 {hour})",
            f"이유: {context_reason}",
            "다음 시간 집중 사항:",
            "- 우선순위 검토",
            "- 집중 실행",
            "- 팀원과 업데이트 공유",
            "",
            f"{get_current_locale_manager().get_text('scheduled_communications')}:",
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
