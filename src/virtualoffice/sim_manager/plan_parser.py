"""
Plan Parser Agent

Converts natural language hourly plans into structured JSON for scheduling.
This provides a clean separation between planning (creative) and parsing (structured).
"""

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# JSON Schema for parsed plans
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$"},
                    "duration_minutes": {"type": "integer", "minimum": 0},
                    "description": {"type": "string"},
                    "type": {"type": "string", "enum": ["work", "break", "meeting"]}
                },
                "required": ["time", "description"]
            }
        },
        "communications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$"},
                    "type": {"type": "string", "enum": ["email", "chat", "email_reply"]},
                    "to": {"type": "string"},
                    "cc": {"type": "array", "items": {"type": "string"}},
                    "bcc": {"type": "array", "items": {"type": "string"}},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "message": {"type": "string"},
                    "reply_to": {"type": "string"}
                },
                "required": ["time", "type"]
            }
        }
    },
    "required": ["communications"]
}


class PlanParser:
    """
    Converts natural language hourly plans into structured JSON.
    
    Uses GPT to extract:
    - Tasks with start times and durations
    - Scheduled communications (emails and chats)
    - Breaks and meetings
    """
    
    def __init__(self, model: str | None = None):
        """
        Initialize the plan parser.
        
        Args:
            model: GPT model to use (default: gpt-4o-mini)
        """
        self.model = model or os.getenv("VDOS_PLAN_PARSER_MODEL", "gpt-4o-mini")
        self._client = None
    
    def _get_client(self):
        """Lazy load OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            except ImportError:
                raise RuntimeError("OpenAI package not installed. Install with: pip install openai")
        return self._client
    
    def parse_plan(
        self,
        plan_text: str,
        worker_name: str,
        work_hours: str,
        team_emails: list[str],
        team_handles: list[str],
        project_name: str | None = None,
        name_to_handle: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        Parse natural language plan into structured JSON.
        
        Args:
            plan_text: Natural language hourly plan
            worker_name: Name of the worker
            work_hours: Work hours (e.g., "09:00-18:00")
            team_emails: Valid email addresses
            team_handles: Valid chat handles
            project_name: Current project name
            name_to_handle: Mapping of Korean names to chat handles
            
        Returns:
            Structured plan with tasks and communications
            
        Raises:
            ParsingError: If parsing fails
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            plan_text=plan_text,
            worker_name=worker_name,
            work_hours=work_hours,
            team_emails=team_emails,
            team_handles=team_handles,
            project_name=project_name
        )
        
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent parsing
                max_tokens=1500
            )
            
            content = response.choices[0].message.content
            
            # Try to parse JSON
            parsed_json = self._extract_json(content)
            
            # Validate schema
            self._validate_schema(parsed_json)
            
            # Fix common issues
            parsed_json = self._fix_common_errors(
                parsed_json, 
                team_emails, 
                team_handles,
                name_to_handle or {}
            )
            
            logger.info(
                f"[PLAN_PARSER] Successfully parsed plan for {worker_name}: "
                f"{len(parsed_json.get('communications', []))} communications, "
                f"{len(parsed_json.get('tasks', []))} tasks"
            )
            
            return parsed_json
            
        except Exception as e:
            logger.error(f"[PLAN_PARSER] Failed to parse plan for {worker_name}: {e}")
            raise ParsingError(f"Plan parsing failed: {e}") from e
    
    async def parse_plans_batch_async(
        self,
        parse_requests: list[dict[str, Any]]
    ) -> list[tuple[str, dict[str, Any] | None]]:
        """
        Parse multiple plans in parallel using async.
        
        Args:
            parse_requests: List of dicts with keys:
                - plan_text: str
                - worker_name: str
                - work_hours: str
                - team_emails: list[str]
                - team_handles: list[str]
                - project_name: str | None
        
        Returns:
            List of (worker_name, parsed_json or None) tuples
        """
        import asyncio
        from openai import AsyncOpenAI
        
        async_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        async def parse_one(request: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
            worker_name = request['worker_name']
            try:
                system_prompt = self._build_system_prompt()
                user_prompt = self._build_user_prompt(
                    plan_text=request['plan_text'],
                    worker_name=worker_name,
                    work_hours=request['work_hours'],
                    team_emails=request['team_emails'],
                    team_handles=request['team_handles'],
                    project_name=request.get('project_name')
                )
                
                response = await async_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=1500
                )
                
                content = response.choices[0].message.content
                parsed_json = self._extract_json(content)
                self._validate_schema(parsed_json)
                parsed_json = self._fix_common_errors(
                    parsed_json,
                    request['team_emails'],
                    request['team_handles']
                )
                
                logger.info(
                    f"[PLAN_PARSER_BATCH] Successfully parsed plan for {worker_name}: "
                    f"{len(parsed_json.get('communications', []))} communications"
                )
                
                return (worker_name, parsed_json)
                
            except Exception as e:
                logger.error(f"[PLAN_PARSER_BATCH] Failed to parse plan for {worker_name}: {e}")
                return (worker_name, None)
        
        # Parse all plans concurrently
        results = await asyncio.gather(*[parse_one(req) for req in parse_requests])
        return results
    
    def parse_plans_batch(
        self,
        parse_requests: list[dict[str, Any]]
    ) -> list[tuple[str, dict[str, Any] | None]]:
        """
        Synchronous wrapper for batch parsing.
        
        Args:
            parse_requests: List of parse request dicts
        
        Returns:
            List of (worker_name, parsed_json or None) tuples
        """
        import asyncio
        return asyncio.run(self.parse_plans_batch_async(parse_requests))
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the parser."""
        return """당신은 자연어로 작성된 업무 계획을 구조화된 JSON으로 변환하는 전문가입니다.

주어진 계획에서 다음을 추출하세요:
1. 작업 목록 (시작 시간, 소요 시간, 설명)
2. 예정된 커뮤니케이션 (이메일, 채팅, 답장)

**중요 규칙:**
- 시간은 HH:MM 형식 (예: "09:00", "14:30")
- 이메일 주소는 제공된 목록에 있는 것만 사용
- 채팅 핸들은 @ 없이 영문 형식으로 작성 (예: minjun_kim, seoyeon_lee)
- 한국어 이름을 채팅 핸들로 사용하지 마세요 (예: "이서연" ❌, "seoyeon_lee" ✅)
- 프로젝트 이름이 제공되면 이메일 제목에 포함
- 답장은 email_reply 타입으로 표시하고 reply_to 필드에 원본 이메일 ID 포함
- "이메일", "채팅", "답장"으로 시작하는 줄만 커뮤니케이션으로 추출
- 형식: "이메일 HH:MM에 TO 참조 CC: 제목 | 본문"
- 형식: "채팅 HH:MM에 TO와: 메시지"
- 형식: "답장 HH:MM에 [email-id] 참조 TO: 제목 | 본문"

**출력 형식:**
반드시 유효한 JSON만 출력하세요. 추가 설명이나 마크다운 없이 JSON만 반환하세요.
"""
    
    def _build_user_prompt(
        self,
        plan_text: str,
        worker_name: str,
        work_hours: str,
        team_emails: list[str],
        team_handles: list[str],
        project_name: str | None
    ) -> str:
        """Build the user prompt with plan details."""
        schema_str = json.dumps(PLAN_SCHEMA, indent=2, ensure_ascii=False)
        
        return f"""다음 계획을 JSON으로 변환하세요:

작성자: {worker_name}
근무 시간: {work_hours}
프로젝트: {project_name or '현재 프로젝트'}

유효한 이메일 주소:
{chr(10).join(f'  - {email}' for email in team_emails)}

유효한 채팅 핸들 (영문 형식만 사용):
{chr(10).join(f'  - {handle}' for handle in team_handles)}

**중요:** 채팅 메시지를 보낼 때는 반드시 위의 영문 핸들을 사용하세요. 한국어 이름을 사용하지 마세요.

계획:
{plan_text}

JSON 스키마:
{schema_str}

위 스키마에 맞는 JSON을 생성하세요. "이메일", "채팅", "답장"으로 시작하는 줄만 communications 배열에 포함하세요.
채팅의 "to" 필드에는 반드시 위에 나열된 영문 핸들 중 하나를 사용하세요.
"""
    
    def _extract_json(self, content: str) -> dict[str, Any]:
        """
        Extract JSON from response content.
        
        Handles cases where JSON is wrapped in markdown code blocks.
        """
        # Try direct parsing first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try extracting any JSON object
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        raise ParsingError(f"Could not extract valid JSON from response: {content[:200]}...")
    
    def _validate_schema(self, parsed_json: dict[str, Any]) -> None:
        """
        Validate parsed JSON against schema.
        
        Raises:
            ParsingError: If validation fails
        """
        try:
            from jsonschema import validate, ValidationError
            validate(instance=parsed_json, schema=PLAN_SCHEMA)
        except ImportError:
            # jsonschema not installed, skip validation
            logger.warning("jsonschema not installed, skipping validation")
        except ValidationError as e:
            raise ParsingError(f"Schema validation failed: {e}") from e
    
    def _fix_common_errors(
        self,
        parsed_json: dict[str, Any],
        team_emails: list[str],
        team_handles: list[str],
        name_to_handle: dict[str, str]
    ) -> dict[str, Any]:
        """
        Fix common parsing errors.
        
        - Remove invalid email addresses
        - Remove invalid chat handles (or map Korean names to handles)
        - Ensure required fields exist
        """
        # Ensure communications array exists
        if 'communications' not in parsed_json:
            parsed_json['communications'] = []
        
        # Ensure tasks array exists
        if 'tasks' not in parsed_json:
            parsed_json['tasks'] = []
        
        # Filter communications
        valid_comms = []
        for comm in parsed_json.get('communications', []):
            # Check email addresses
            if comm.get('type') in ['email', 'email_reply']:
                to_addr = comm.get('to', '')
                
                # Fix common invalid email patterns
                if to_addr not in team_emails:
                    # Check if it's a distribution list pattern (team@, all@, etc.)
                    if '@' in to_addr and any(to_addr.startswith(prefix) for prefix in ['team@', 'all@', 'everyone@', 'dept@', 'manager@']):
                        # Replace with first team member (or could pick random)
                        if team_emails:
                            old_addr = to_addr
                            to_addr = team_emails[0]
                            comm['to'] = to_addr
                            logger.info(f"[PLAN_PARSER] Fixed invalid distribution list {old_addr} -> {to_addr}")
                        else:
                            logger.warning(f"[PLAN_PARSER] Invalid email address: {to_addr}, skipping (no team emails available)")
                            continue
                    else:
                        logger.warning(f"[PLAN_PARSER] Invalid email address: {to_addr}, skipping")
                        continue
                
                # Check CC addresses - filter out invalid ones
                if 'cc' in comm:
                    original_cc = comm['cc']
                    comm['cc'] = [addr for addr in comm['cc'] if addr in team_emails]
                    if len(comm['cc']) < len(original_cc):
                        logger.info(f"[PLAN_PARSER] Filtered CC addresses: {len(original_cc)} -> {len(comm['cc'])}")
                
                # Check BCC addresses - filter out invalid ones
                if 'bcc' in comm:
                    original_bcc = comm['bcc']
                    comm['bcc'] = [addr for addr in comm['bcc'] if addr in team_emails]
                    if len(comm['bcc']) < len(original_bcc):
                        logger.info(f"[PLAN_PARSER] Filtered BCC addresses: {len(original_bcc)} -> {len(comm['bcc'])}")
            
            # Check chat handles
            elif comm.get('type') == 'chat':
                to_handle = comm.get('to', '')
                
                # Try to map Korean name to handle
                if to_handle in name_to_handle:
                    old_handle = to_handle
                    to_handle = name_to_handle[to_handle]
                    comm['to'] = to_handle
                    logger.info(f"[PLAN_PARSER] Mapped Korean name {old_handle} -> {to_handle}")
                
                # Allow special handles like "팀", "프로젝트", "그룹"
                if to_handle not in team_handles and to_handle not in ['팀', '프로젝트', '그룹', 'team', 'project', 'group']:
                    logger.warning(f"[PLAN_PARSER] Invalid chat handle: {to_handle}, skipping")
                    continue
            
            valid_comms.append(comm)
        
        parsed_json['communications'] = valid_comms
        
        return parsed_json


class ParsingError(Exception):
    """Raised when plan parsing fails."""
    pass
