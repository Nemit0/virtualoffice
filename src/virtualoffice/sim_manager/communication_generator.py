"""
Communication Generator for GPT-powered fallback communications.

This module provides GPT-based generation of diverse, context-aware communications
when JSON communications are not present in hourly plans. It builds on the JSON
parser foundation (Nov 4) to improve content quality.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Sequence

from .planner import Planner, PlanResult, PlanningError
from .schemas import PersonRead

logger = logging.getLogger(__name__)


class CommunicationGenerator:
    """
    Generates diverse, context-aware fallback communications using GPT.
    
    This class is used when hourly plans don't include JSON communications,
    providing realistic alternatives to hardcoded templates.
    
    Supports both synchronous and asynchronous generation for performance optimization.
    """
    
    def __init__(
        self,
        planner: Planner,
        locale: str = "ko",
        random_seed: int | None = None,
        enable_caching: bool = True
    ):
        """
        Initialize the communication generator.
        
        Args:
            planner: Planner instance for GPT calls
            locale: Language locale ('ko' or 'en')
            random_seed: Random seed for deterministic behavior
            enable_caching: Enable context caching for performance (default: True)
        """
        self.planner = planner
        self.locale = locale
        self.random = random.Random(random_seed)
        self.enable_caching = enable_caching
        
        # Context cache for performance optimization
        # Cache project info and collaborator lists to avoid repeated processing
        self._project_cache: dict[str, dict[str, Any]] = {}
        self._collaborator_cache: dict[int, list[str]] = {}  # team_id -> names
        
        logger.info(
            f"CommunicationGenerator initialized with locale={locale}, "
            f"seed={random_seed}, caching={enable_caching}"
        )
    
    def _build_context(
        self,
        person: PersonRead,
        hourly_plan: str | None,
        daily_plan: str | None,
        project: dict[str, Any] | None,
        inbox_messages: list[dict[str, Any]] | None,
        collaborators: Sequence[PersonRead] | None
    ) -> dict[str, Any]:
        """
        Build context dictionary from available information.
        
        Extracts relevant context from hourly plan, daily plan, project info,
        inbox messages, and collaborators for use in prompt generation.
        Uses caching for project info and collaborator lists to improve performance.
        
        Args:
            person: The persona generating communications
            hourly_plan: Current hourly plan text (may be None)
            daily_plan: Daily plan summary (may be None)
            project: Project information dict (may be None)
            inbox_messages: Recent inbox messages (may be None)
            collaborators: Team members (may be None)
            
        Returns:
            Dictionary with context keys for prompt building
        """
        # Truncate long text fields to reasonable lengths
        def truncate(text: str | None, max_length: int = 500) -> str:
            if not text:
                return ""
            return text[:max_length] + "..." if len(text) > max_length else text
        
        # Build collaborator list with caching
        collaborator_names = []
        if collaborators:
            # Create cache key from collaborator IDs
            collab_ids = tuple(sorted(c.id for c in collaborators))
            
            if self.enable_caching and collab_ids in self._collaborator_cache:
                # Use cached collaborator names
                all_names = self._collaborator_cache[collab_ids]
                collaborator_names = [n for n in all_names if n != person.name]
            else:
                # Build and cache collaborator names
                all_names = [c.name for c in collaborators]
                if self.enable_caching:
                    self._collaborator_cache[collab_ids] = all_names
                collaborator_names = [n for n in all_names if n != person.name]
        
        # Extract project info with caching
        project_name = ""
        project_summary = ""
        if project:
            project_id = project.get("id", "")
            
            if self.enable_caching and project_id and project_id in self._project_cache:
                # Use cached project info
                cached = self._project_cache[project_id]
                project_name = cached["name"]
                project_summary = cached["summary"]
            else:
                # Extract and cache project info
                project_name = project.get("project_name", "")
                project_summary = truncate(project.get("project_summary", ""), 200)
                
                if self.enable_caching and project_id:
                    self._project_cache[project_id] = {
                        "name": project_name,
                        "summary": project_summary
                    }
        
        # Format inbox messages (not cached as they change frequently)
        inbox_summary = ""
        if inbox_messages:
            recent = inbox_messages[:5]  # Only most recent 5
            inbox_items = []
            for msg in recent:
                sender = msg.get("sender_name", "Unknown")
                subject = msg.get("subject", msg.get("message", ""))[:50]

                # Include CC information for email messages
                cc_info = ""
                if msg.get("cc_addresses"):
                    cc_names = ", ".join(msg["cc_addresses"])
                    cc_info = f" (CC: {cc_names})"

                # Include recipient role if available
                role_info = ""
                if msg.get("my_role") == "cc":
                    role_info = " [You were CC'd]"

                inbox_items.append(f"- From {sender}: {subject}{cc_info}{role_info}")
            inbox_summary = "\n".join(inbox_items)
        
        return {
            "person": person,
            "person_name": person.name,
            "person_role": person.role,
            "current_work": truncate(hourly_plan, 500),
            "daily_summary": truncate(daily_plan, 300),
            "project_name": project_name,
            "project_summary": project_summary,
            "inbox": inbox_summary,
            "collaborators": collaborator_names,
            "locale": self.locale,
        }
    
    def _build_korean_prompt(
        self,
        context: dict[str, Any]
    ) -> list[dict[str, str]]:
        """
        Build Korean language prompt for GPT communication generation.
        
        Creates system and user messages with role context, work context,
        project context, inbox context, and output format instructions.
        
        Args:
            context: Context dictionary from _build_context()
            
        Returns:
            List of message dicts for GPT API
        """
        person = context["person"]
        
        # Build role-specific guidance
        role_guidance = ""
        if "개발" in person.role or "developer" in person.role.lower():
            role_guidance = "기술적인 용어를 사용하세요 (예: API, 데이터베이스, 코드 리뷰, PR)."
        elif "디자인" in person.role or "design" in person.role.lower():
            role_guidance = "디자인 용어를 사용하세요 (예: 목업, UI/UX, 프로토타입, 레이아웃)."
        elif "QA" in person.role or "테스트" in person.role:
            role_guidance = "테스트 용어를 사용하세요 (예: 테스트 케이스, 버그, 회귀 테스트)."
        elif "마케팅" in person.role or "marketing" in person.role.lower():
            role_guidance = "마케팅 용어를 사용하세요 (예: 캠페인, CTR, 전환율, 성과)."
        elif "매니저" in person.role or "manager" in person.role.lower() or "PM" in person.role:
            role_guidance = "조율 용어를 사용하세요 (예: 마일스톤, 타임라인, 이해관계자)."
        
        # Build work context
        work_context = ""
        if context["current_work"]:
            work_context = f"\n\n현재 작업:\n{context['current_work']}"
        elif context["daily_summary"]:
            work_context = f"\n\n오늘의 계획:\n{context['daily_summary']}"
        
        # Build project context
        project_context = ""
        if context["project_name"]:
            project_context = f"\n\n프로젝트: {context['project_name']}"
            if context["project_summary"]:
                project_context += f"\n{context['project_summary']}"
        
        # Build inbox context
        inbox_context = ""
        if context["inbox"]:
            inbox_context = f"\n\n최근 받은 메시지:\n{context['inbox']}"
        
        # Build collaborator context
        collaborator_context = ""
        if context["collaborators"]:
            collaborator_context = f"\n\n팀원: {', '.join(context['collaborators'])}"
        
        system_message = f"""당신은 {person.name} ({person.role})입니다.

역할: {person.role}
성격: {', '.join(person.personality)}
커뮤니케이션 스타일: {person.communication_style}

{role_guidance}

자연스럽고 현실적인 업무 커뮤니케이션을 생성하세요."""

        user_message = f"""다음 상황에서 보낼 수 있는 이메일이나 채팅 메시지를 1-3개 생성하세요.
{work_context}
{project_context}
{inbox_context}
{collaborator_context}

지침:
1. 역할에 맞는 자연스러운 언어 사용
2. 구체적인 작업이나 산출물 언급
3. 받은 메시지가 있으면 답장 고려 (thread_id 사용)
4. 프로젝트 이름을 제목에 포함 (예: [프로젝트명] 제목)
5. 다양한 메시지 유형 사용 (질문, 요청, 업데이트, 확인 등)

채팅 메시지 스타일 (매우 중요):
- 이메일보다 훨씬 캐주얼하게 작성 (~요, ~네요, ~어요 사용)
- 짧고 간결하게 (1-2문장)
- 자연스럽게 말하듯이 작성
- 절대 영어 단어를 섞지 마세요
- 대괄호 [...] 형식을 사용하지 마세요
- 격식체(~습니다, ~합니다) 대신 반말체 사용

좋은 채팅 예: "민준님, API 작업 거의 다 됐어요. 내일 리뷰 가능하세요?"
나쁜 채팅 예: "[프로젝트 진행 상황] 작업 진행하겠습니다" ❌

출력 형식 (JSON):
{{
  "communications": [
    {{
      "type": "email",
      "to": ["수신자 이메일"],
      "subject": "제목",
      "body": "본문",
      "thread_id": "답장인 경우 원본 thread_id"
    }},
    {{
      "type": "chat",
      "target": "채팅방 이름 또는 @사용자",
      "message": "메시지 내용"
    }}
  ]
}}

JSON만 출력하세요."""

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
    
    def _build_english_prompt(
        self,
        context: dict[str, Any]
    ) -> list[dict[str, str]]:
        """
        Build English language prompt for GPT communication generation.
        
        Creates system and user messages with role context, work context,
        project context, inbox context, and output format instructions.
        
        Args:
            context: Context dictionary from _build_context()
            
        Returns:
            List of message dicts for GPT API
        """
        person = context["person"]
        
        # Build role-specific guidance
        role_guidance = ""
        if "developer" in person.role.lower() or "engineer" in person.role.lower():
            role_guidance = "Use technical terminology (e.g., API, database, code review, PR)."
        elif "design" in person.role.lower():
            role_guidance = "Use design terminology (e.g., mockup, UI/UX, prototype, layout)."
        elif "qa" in person.role.lower() or "test" in person.role.lower():
            role_guidance = "Use testing terminology (e.g., test case, bug, regression test)."
        elif "marketing" in person.role.lower():
            role_guidance = "Use marketing terminology (e.g., campaign, CTR, conversion rate)."
        elif "manager" in person.role.lower() or "pm" in person.role.lower():
            role_guidance = "Use coordination terminology (e.g., milestone, timeline, stakeholder)."
        
        # Build work context
        work_context = ""
        if context["current_work"]:
            work_context = f"\n\nCurrent work:\n{context['current_work']}"
        elif context["daily_summary"]:
            work_context = f"\n\nToday's plan:\n{context['daily_summary']}"
        
        # Build project context
        project_context = ""
        if context["project_name"]:
            project_context = f"\n\nProject: {context['project_name']}"
            if context["project_summary"]:
                project_context += f"\n{context['project_summary']}"
        
        # Build inbox context
        inbox_context = ""
        if context["inbox"]:
            inbox_context = f"\n\nRecent messages:\n{context['inbox']}"
        
        # Build collaborator context
        collaborator_context = ""
        if context["collaborators"]:
            collaborator_context = f"\n\nTeam: {', '.join(context['collaborators'])}"
        
        system_message = f"""You are {person.name} ({person.role}).

Role: {person.role}
Personality: {', '.join(person.personality)}
Communication style: {person.communication_style}

{role_guidance}

Generate natural, realistic workplace communications."""

        user_message = f"""Generate 1-3 emails or chat messages you might send in this situation.
{work_context}
{project_context}
{inbox_context}
{collaborator_context}

Guidelines:
1. Use natural language appropriate for your role
2. Mention specific tasks or deliverables
3. Consider replying to received messages (use thread_id)
4. Include project name in subject (e.g., [ProjectName] Subject)
5. Use varied message types (question, request, update, acknowledgment, etc.)

Output format (JSON):
{{
  "communications": [
    {{
      "type": "email",
      "to": ["recipient@email"],
      "subject": "Subject",
      "body": "Body text",
      "thread_id": "original thread_id if replying"
    }},
    {{
      "type": "chat",
      "target": "room-name or @user",
      "message": "Message content"
    }}
  ]
}}

Output JSON only."""

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]

    
    def generate_fallback_communications(
        self,
        person: PersonRead,
        current_tick: int | None = None,
        hourly_plan: str | None = None,
        daily_plan: str | None = None,
        project: dict[str, Any] | None = None,
        inbox_messages: list[dict[str, Any]] | None = None,
        collaborators: Sequence[PersonRead] | None = None,
        model_hint: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Generate fallback communications using GPT when JSON not present.
        
        This is the main entry point for generating diverse, context-aware
        communications as an alternative to hardcoded templates.
        
        Args:
            person: The persona generating communications
            current_tick: Current simulation tick (for logging)
            hourly_plan: Current hourly plan text (optional)
            daily_plan: Daily plan summary (optional)
            project: Project information dict (optional)
            inbox_messages: Recent inbox messages (optional)
            collaborators: Team members (optional)
            model_hint: Optional model override (default: gpt-4o-mini)
            
        Returns:
            List of communication dictionaries with type, to/target, subject/message, body
            Returns empty list on error
        """
        import time
        start_time = time.time()
        
        try:
            # Build context from available information
            context = self._build_context(
                person=person,
                hourly_plan=hourly_plan,
                daily_plan=daily_plan,
                project=project,
                inbox_messages=inbox_messages,
                collaborators=collaborators
            )
            
            # Build prompt based on locale
            if self.locale == "ko":
                messages = self._build_korean_prompt(context)
            else:
                messages = self._build_english_prompt(context)
            
            # Call GPT via planner
            model = model_hint or "gpt-4o-mini"
            logger.info(
                f"[GPT_FALLBACK] Generating communications for {person.name} "
                f"(tick={current_tick}, locale={self.locale}, model={model})"
            )
            
            result = self.planner.generate_with_messages(
                messages=messages,
                model_hint=model
            )
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            
            # Parse JSON response
            communications = self._parse_gpt_response(result.content)
            
            # Log success with detailed metrics
            logger.info(
                f"[GPT_FALLBACK] Generated {len(communications)} communications "
                f"for {person.name} (tick={current_tick}, "
                f"tokens={result.tokens_used}, latency={latency_ms:.1f}ms, "
                f"model={model})"
            )
            
            return communications
            
        except PlanningError as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(
                f"[GPT_FALLBACK] Planning error for {person.name} "
                f"(tick={current_tick}, latency={latency_ms:.1f}ms): {e}",
                exc_info=True
            )
            return []
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[GPT_FALLBACK] Unexpected error for {person.name} "
                f"(tick={current_tick}, latency={latency_ms:.1f}ms): {e}",
                exc_info=True
            )
            return []

    
    def _parse_gpt_response(self, response: str) -> list[dict[str, Any]]:
        """
        Parse GPT response to extract communications.
        
        Handles various JSON formats:
        - Raw JSON
        - JSON in markdown code blocks
        - JSON with extra text
        
        Args:
            response: Raw GPT response text
            
        Returns:
            List of communication dictionaries
            Returns empty list if parsing fails
        """
        try:
            # Try to extract JSON from response
            json_str = response.strip()
            
            # Handle markdown code blocks
            if "```json" in json_str:
                start = json_str.find("```json") + 7
                end = json_str.find("```", start)
                if end > start:
                    json_str = json_str[start:end].strip()
            elif "```" in json_str:
                start = json_str.find("```") + 3
                end = json_str.find("```", start)
                if end > start:
                    json_str = json_str[start:end].strip()
            
            # Try to find JSON object
            if not json_str.startswith("{"):
                # Look for first { and last }
                start = json_str.find("{")
                end = json_str.rfind("}")
                if start >= 0 and end > start:
                    json_str = json_str[start:end+1]
            
            # Parse JSON
            data = json.loads(json_str)
            
            # Extract communications array
            if isinstance(data, dict) and "communications" in data:
                communications = data["communications"]
            elif isinstance(data, list):
                communications = data
            else:
                logger.warning(
                    f"Unexpected JSON structure: {type(data)}, "
                    f"expected dict with 'communications' key or list"
                )
                return []
            
            # Validate each communication
            validated = []
            for comm in communications:
                if not isinstance(comm, dict):
                    logger.warning(f"Skipping non-dict communication: {comm}")
                    continue
                
                # Check required fields based on type
                comm_type = comm.get("type", "").lower()
                
                if comm_type == "email":
                    if not all(k in comm for k in ["to", "subject", "body"]):
                        logger.warning(
                            f"Email missing required fields: {comm.keys()}"
                        )
                        continue
                    # Ensure 'to' is a list
                    if isinstance(comm["to"], str):
                        comm["to"] = [comm["to"]]
                        
                elif comm_type == "chat":
                    if not all(k in comm for k in ["target", "message"]):
                        logger.warning(
                            f"Chat missing required fields: {comm.keys()}"
                        )
                        continue
                else:
                    logger.warning(f"Unknown communication type: {comm_type}")
                    continue
                
                validated.append(comm)
            
            return validated
            
        except json.JSONDecodeError as e:
            logger.warning(
                f"[GPT_FALLBACK] JSON parsing failed: {e}\n"
                f"Response preview: {response[:200]}..."
            )
            return []
        except Exception as e:
            logger.warning(
                f"[GPT_FALLBACK] Unexpected parsing error: {e}",
                exc_info=True
            )
            return []
    
    async def generate_fallback_communications_async(
        self,
        person: PersonRead,
        current_tick: int | None = None,
        hourly_plan: str | None = None,
        daily_plan: str | None = None,
        project: dict[str, Any] | None = None,
        inbox_messages: list[dict[str, Any]] | None = None,
        collaborators: Sequence[PersonRead] | None = None,
        model_hint: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Async version of generate_fallback_communications.
        
        Generates fallback communications without blocking the event loop,
        allowing tick advancement to continue while GPT calls are in progress.
        
        Args:
            person: The persona generating communications
            current_tick: Current simulation tick (for logging)
            hourly_plan: Current hourly plan text (optional)
            daily_plan: Daily plan summary (optional)
            project: Project information dict (optional)
            inbox_messages: Recent inbox messages (optional)
            collaborators: Team members (optional)
            model_hint: Optional model override (default: gpt-4o-mini)
            
        Returns:
            List of communication dictionaries with type, to/target, subject/message, body
            Returns empty list on error
        """
        import time
        start_time = time.time()
        
        try:
            # Build context from available information (synchronous, fast)
            context = self._build_context(
                person=person,
                hourly_plan=hourly_plan,
                daily_plan=daily_plan,
                project=project,
                inbox_messages=inbox_messages,
                collaborators=collaborators
            )
            
            # Build prompt based on locale (synchronous, fast)
            if self.locale == "ko":
                messages = self._build_korean_prompt(context)
            else:
                messages = self._build_english_prompt(context)
            
            # Call GPT via planner in thread pool to avoid blocking
            model = model_hint or "gpt-4o-mini"
            logger.info(
                f"[GPT_FALLBACK_ASYNC] Generating communications for {person.name} "
                f"(tick={current_tick}, locale={self.locale}, model={model})"
            )
            
            # Run synchronous planner call in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.planner.generate_with_messages(
                    messages=messages,
                    model_hint=model
                )
            )
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            
            # Parse JSON response (synchronous, fast)
            communications = self._parse_gpt_response(result.content)
            
            # Log success with detailed metrics
            logger.info(
                f"[GPT_FALLBACK_ASYNC] Generated {len(communications)} communications "
                f"for {person.name} (tick={current_tick}, "
                f"tokens={result.tokens_used}, latency={latency_ms:.1f}ms, "
                f"model={model})"
            )
            
            return communications
            
        except PlanningError as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(
                f"[GPT_FALLBACK_ASYNC] Planning error for {person.name} "
                f"(tick={current_tick}, latency={latency_ms:.1f}ms): {e}",
                exc_info=True
            )
            return []
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[GPT_FALLBACK_ASYNC] Unexpected error for {person.name} "
                f"(tick={current_tick}, latency={latency_ms:.1f}ms): {e}",
                exc_info=True
            )
            return []
    
    async def generate_batch_async(
        self,
        requests: list[dict[str, Any]]
    ) -> list[tuple[PersonRead, list[dict[str, Any]]]]:
        """
        Generate communications for multiple personas in parallel.
        
        This method batches multiple generation requests and processes them
        concurrently to reduce overall latency when multiple personas need
        fallback communications at the same time.
        
        Args:
            requests: List of request dicts, each containing:
                - person: PersonRead
                - current_tick: int | None
                - hourly_plan: str | None
                - daily_plan: str | None
                - project: dict | None
                - inbox_messages: list | None
                - collaborators: Sequence[PersonRead] | None
                - model_hint: str | None
                
        Returns:
            List of tuples (person, communications) for each request
        """
        logger.info(
            f"[GPT_FALLBACK_BATCH] Starting batch generation for "
            f"{len(requests)} personas"
        )
        
        # Create async tasks for all requests
        tasks = []
        for req in requests:
            task = self.generate_fallback_communications_async(
                person=req["person"],
                current_tick=req.get("current_tick"),
                hourly_plan=req.get("hourly_plan"),
                daily_plan=req.get("daily_plan"),
                project=req.get("project"),
                inbox_messages=req.get("inbox_messages"),
                collaborators=req.get("collaborators"),
                model_hint=req.get("model_hint")
            )
            tasks.append((req["person"], task))
        
        # Execute all tasks concurrently
        results = []
        for person, task in tasks:
            try:
                communications = await task
                results.append((person, communications))
            except Exception as e:
                logger.error(
                    f"[GPT_FALLBACK_BATCH] Error in batch for {person.name}: {e}",
                    exc_info=True
                )
                results.append((person, []))
        
        logger.info(
            f"[GPT_FALLBACK_BATCH] Completed batch generation for "
            f"{len(results)} personas"
        )
        
        return results
    
    def clear_cache(self) -> None:
        """
        Clear the context cache.
        
        Call this when project information or team composition changes
        to ensure fresh data is used.
        """
        self._project_cache.clear()
        self._collaborator_cache.clear()
        logger.debug("CommunicationGenerator cache cleared")
