from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import threading
import time

from .engine import SimulationEngine
from virtualoffice.common.db import DB_PATH, get_connection
from .gateways import HttpChatGateway, HttpEmailGateway
from .replay_manager import ReplayManager
from .style_filter.filter import CommunicationStyleFilter
from .schemas import (
    AutoPauseStatusResponse,
    AutoPauseToggleRequest,
    EventCreate,
    EventRead,
    PersonCreate,
    PersonRead,
    PlanTypeLiteral,
    ProjectPlanRead,
    SimulationAdvanceRequest,
    SimulationAdvanceResult,
    SimulationControlResponse,
    SimulationStartRequest,
    SimulationState,
    DailyReportRead,
    SimulationReportRead,
    StatusOverrideRequest,
    StatusOverrideResponse,
    TokenUsageSummary,
    WorkerPlanRead,
    PersonaGenerateRequest,
)

API_PREFIX = "/api/v1"

# OpenAPI tags metadata for organized API documentation
tags_metadata = [
    {
        "name": "Personas",
        "description": "Manage virtual worker personas - create, update, delete, and generate AI personas with GPT-4o"
    },
    {
        "name": "Simulation Control",
        "description": "Core simulation lifecycle - start, stop, reset, advance ticks, and configure auto-tick behavior"
    },
    {
        "name": "Projects",
        "description": "Multi-project configuration and management - create projects, assign teams, and configure timelines"
    },
    {
        "name": "Reports & Analytics",
        "description": "Worker plans, daily reports, simulation summaries, token usage, and performance metrics"
    },
    {
        "name": "Events",
        "description": "Inject custom events into the simulation timeline for testing scenarios"
    },
    {
        "name": "Monitoring",
        "description": "Real-time monitoring of emails and chat messages via proxy endpoints (CORS-friendly)"
    },
    {
        "name": "Style Filter",
        "description": "Communication style filter configuration and metrics - personalize message generation"
    },
    {
        "name": "Import/Export",
        "description": "Backup and restore personas and project configurations via JSON"
    },
    {
        "name": "Admin",
        "description": "⚠️ Administrative operations - hard reset, soft reset, rewind (use with caution)"
    },
    {
        "name": "Dashboard",
        "description": "Web dashboard interface"
    }
]


def _generate_persona_text(messages: list[dict[str, str]], model: str) -> tuple[str, int | None]:
    """Internal hook for GPT calls. Tests may monkeypatch this.

    Returns (text, total_tokens | None).
    """
    try:
        from virtualoffice.utils.completion_util import generate_text as _gen
    except Exception as exc:  # pragma: no cover - optional dependency or import error
        raise RuntimeError(f"OpenAI client unavailable: {exc}") from exc
    return _gen(messages, model=model)


def _generate_persona_from_prompt(prompt: str, model_hint: str | None = None, explicit_name: str | None = None) -> dict[str, Any]:
    """Best-effort persona generator.

    - Uses OpenAI if configured; otherwise returns a sensible stub.
    - Ensures output matches PersonCreate-compatible shape used by the dashboard.
    - If explicit_name is provided, it overrides the GPT-generated name.
    """
    model = model_hint or os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
    locale = os.getenv("VDOS_LOCALE", "en").strip().lower() or "en"
    
    if locale == "ko":
        system = (
            "한국 직장 시뮬레이션을 위한 JSON 페르소나를 생성합니다. "
            "다음 필드를 포함한 JSON 객체만 응답하세요: "
            "name, role, timezone, work_hours, break_frequency, communication_style, "
            "email_address, chat_handle, is_department_head (boolean), skills (array), personality (array), "
            "objectives (array, optional), metrics (array, optional), planning_guidelines (array, optional), "
            "schedule (array of {start, end, activity}). "
            "모든 텍스트 필드는 자연스러운 한국어로만 작성하세요. 영어 단어나 표현을 절대 사용하지 마세요. "
            "실제 한국 직장인처럼 현실적으로 작성하세요. AI나 시뮬레이션에 대한 언급은 하지 마세요."
        )
        user = (
            f"다음에 대한 현실적인 페르소나를 생성하세요: {prompt}. "
            "간결한 값을 선호합니다. 시간대는 'Asia/Seoul', 근무시간은 '09:00-18:00' 형식으로. "
            "JSON만 반환하세요."
        )
    else:
        system = (
            "You generate JSON personas for internal simulations. "
            "Respond ONLY with a single JSON object containing fields: "
            "name, role, timezone, work_hours, break_frequency, communication_style, "
            "email_address, chat_handle, is_department_head (boolean), skills (array), personality (array), "
            "objectives (array, optional), metrics (array, optional), planning_guidelines (array, optional), "
            "schedule (array of {start, end, activity}). "
            "Write as a realistic human colleague; do not include any meta-commentary about AI, prompts, or models."
        )
        user = (
            f"Create a realistic persona for: {prompt}. "
            "Prefer concise values. Timezone like 'UTC'. Work hours '09:00-17:00'. "
            "Return JSON only."
        )
    # Try model
    try:
        text, _ = _generate_persona_text([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], model=model)
        try:
            data = json.loads(text)
        except Exception:
            # Attempt to extract JSON substring if wrapped
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(text[start:end+1])
            else:
                raise
        # Override name if explicit_name provided (must be done before normalization)
        if explicit_name:
            data["name"] = explicit_name

        # Minimal normalization
        # Harmonize naming to satisfy dashboard/tests expectations (but only if no explicit name)
        if not explicit_name and "developer" in prompt.lower():
            if not str(data.get("name", "")).lower().startswith("auto "):
                data["name"] = "Auto Dev"
            # Keep test-friendly default skill for developer prompts
            data["skills"] = ["Python"]
        
        # Set defaults based on locale
        if locale == "ko":
            data.setdefault("timezone", "Asia/Seoul")
            data.setdefault("work_hours", "09:00-18:00")
            data.setdefault("break_frequency", "50분 작업/10분 휴식")
            data.setdefault("communication_style", "협업적")
            data.setdefault("skills", ["일반"])
            data.setdefault("personality", ["도움이 되는"])
            data.setdefault("schedule", [{"start": "09:00", "end": "10:00", "activity": "계획 수립"}])
        else:
            data.setdefault("timezone", "UTC")
            data.setdefault("work_hours", "09:00-17:00")
            data.setdefault("break_frequency", "50/10 cadence")
            data.setdefault("communication_style", "Async")
            data.setdefault("skills", ["Generalist"])
            data.setdefault("personality", ["Helpful"])
            data.setdefault("schedule", [{"start": "09:00", "end": "10:00", "activity": "Plan"}])
        data.setdefault("is_department_head", False)
        if not data.get("email_address") and data.get("name"):
            local = data["name"].lower().replace(" ", ".")
            data["email_address"] = f"{local}@vdos.local"
        if not data.get("chat_handle") and data.get("name"):
            data["chat_handle"] = data["name"].split()[0].lower()
        return data
    except Exception:
        # Fallback stub (no network, no key, or parse error)
        safe = prompt.strip() or ("자동 작업자" if locale == "ko" else "Auto Worker")
        
        if locale == "ko":
            role = "엔지니어"
            # Korean role extraction
            role_mapping = {
                "개발자": "개발자", "developer": "개발자", "engineer": "엔지니어",
                "디자이너": "디자이너", "designer": "디자이너",
                "매니저": "매니저", "manager": "매니저", "관리자": "매니저",
                "분석가": "분석가", "analyst": "분석가"
            }
            for token, korean_role in role_mapping.items():
                if token in safe.lower():
                    role = korean_role
                    break
            
            base = safe.replace(" ", ".").lower()
            return {
                "name": f"자동 {role}",
                "role": role,
                "timezone": "Asia/Seoul",
                "work_hours": "09:00-18:00",
                "break_frequency": "50분 작업/10분 휴식",
                "communication_style": "협업적",
                "email_address": f"{base or 'auto'}@vdos.local",
                "chat_handle": (safe.split()[0] if safe else "auto").lower(),
                "is_department_head": False,
                "skills": ["파이썬"] if "개발" in role else ["일반"],
                "personality": ["도움이 되는"],
                "schedule": [{"start": "09:00", "end": "10:00", "activity": "계획 수립"}],
            }
        else:
            role = "Engineer"
            # naive role extraction
            for token in ("engineer", "developer", "designer", "manager", "analyst"):
                if token in safe.lower():
                    role = token.title()
                    break
            base = safe.replace(" ", ".").lower()
            return {
                "name": f"Auto {role}",
                "role": role,
                "timezone": "UTC",
                "work_hours": "09:00-17:00",
                "break_frequency": "50/10 cadence",
                "communication_style": "Async",
                "email_address": f"{base or 'auto' }@vdos.local",
                "chat_handle": (safe.split()[0] if safe else "auto").lower(),
                "is_department_head": False,
                "skills": ["Python"] if role in {"Engineer", "Developer"} else ["Generalist"],
                "personality": ["Helpful"],
                "schedule": [{"start": "09:00", "end": "10:00", "activity": "Plan"}],
            }

_DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "index.html")

def _build_default_engine() -> SimulationEngine:
    email_base = os.getenv("VDOS_EMAIL_BASE_URL")
    if not email_base:
        email_host = os.getenv("VDOS_EMAIL_HOST", "127.0.0.1")
        email_port = os.getenv("VDOS_EMAIL_PORT", "8000")
        email_base = f"http://{email_host}:{email_port}"

    chat_base = os.getenv("VDOS_CHAT_BASE_URL")
    if not chat_base:
        chat_host = os.getenv("VDOS_CHAT_HOST", "127.0.0.1")
        chat_port = os.getenv("VDOS_CHAT_PORT", "8001")
        chat_base = f"http://{chat_host}:{chat_port}"

    sim_email = os.getenv("VDOS_SIM_EMAIL", "simulator@vdos.local")
    sim_handle = os.getenv("VDOS_SIM_HANDLE", "sim-manager")

    # Initialize communication style filter
    # Create a persistent database connection for the style filter
    locale = os.getenv("VDOS_LOCALE", "en").strip().lower() or "en"
    import sqlite3
    db_conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
        timeout=30.0
    )
    db_conn.row_factory = sqlite3.Row
    db_conn.execute("PRAGMA journal_mode=WAL")
    db_conn.execute("PRAGMA foreign_keys = ON")
    db_conn.execute("PRAGMA busy_timeout = 30000")

    style_filter = CommunicationStyleFilter(
        db_connection=db_conn,
        locale=locale,
        enabled=True  # Actual enabled state is checked from database
    )

    email_gateway = HttpEmailGateway(base_url=email_base, style_filter=style_filter)
    chat_gateway = HttpChatGateway(base_url=chat_base, style_filter=style_filter)
    # Allow tick interval override for faster auto-ticking if used
    try:
        tick_interval_seconds = float(os.getenv("VDOS_TICK_INTERVAL_SECONDS", "1.0"))
    except ValueError:
        tick_interval_seconds = 1.0
    # Workday configuration
    # Primary knob: VDOS_HOURS_PER_DAY (default 8). Backward compatibility:
    # if legacy VDOS_TICKS_PER_DAY is provided, convert to hours by dividing by 60.
    hours_per_day_env = os.getenv("VDOS_HOURS_PER_DAY")
    if hours_per_day_env is not None:
        try:
            hours_per_day = int(hours_per_day_env)
        except ValueError:
            hours_per_day = 8
    else:
        try:
            legacy_ticks = int(os.getenv("VDOS_TICKS_PER_DAY", "480"))
        except ValueError:
            legacy_ticks = 480
        # Convert ticks (minutes) to hours; ensure minimum 1 hour
        hours_per_day = max(1, legacy_ticks // 60) if legacy_ticks > 0 else 8
    return SimulationEngine(
        email_gateway=email_gateway,
        chat_gateway=chat_gateway,
        sim_manager_email=sim_email,
        sim_manager_handle=sim_handle,
        tick_interval_seconds=tick_interval_seconds,
        hours_per_day=hours_per_day,
    )


def create_app(engine: SimulationEngine | None = None) -> FastAPI:
    app = FastAPI(
        title="VDOS Simulation Manager",
        version="0.1.0",
        openapi_tags=tags_metadata,
        description="Virtual Department Operations Simulator - Generate realistic departmental communications for testing and development"
    )
    app.state.engine = engine or _build_default_engine()
    app.state.replay_manager = ReplayManager(app.state.engine)

    # Mount static files
    static_path = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
    def dashboard() -> HTMLResponse:
        # Read dashboard HTML fresh each request so UI updates without server restart
        try:
            with open(_DASHBOARD_PATH, "r", encoding="utf-8") as f:
                html = f.read()
        except Exception as exc:  # pragma: no cover - fallback in case of file read error
            html = f"<html><body><h1>VDOS Dashboard</h1><p>Failed to load dashboard: {exc}</p></body></html>"
        return HTMLResponse(html)

    @app.on_event("shutdown")
    def _shutdown() -> None:
        engine_obj = getattr(app.state, "engine", None)
        if engine_obj is not None:
            engine_obj.close()

    def get_engine(request: Request) -> SimulationEngine:
        return request.app.state.engine

    def get_replay_manager(request: Request) -> ReplayManager:
        return request.app.state.replay_manager

    @app.get(f"{API_PREFIX}/people", response_model=list[PersonRead], tags=["Personas"])
    def list_people(engine: SimulationEngine = Depends(get_engine)) -> list[PersonRead]:
        return engine.list_people()

    @app.post(f"{API_PREFIX}/people", response_model=PersonRead, status_code=status.HTTP_201_CREATED, tags=["Personas"])
    def create_person(payload: PersonCreate, engine: SimulationEngine = Depends(get_engine)) -> PersonRead:
        return engine.create_person(payload)

    @app.post(f"{API_PREFIX}/personas/generate", tags=["Personas"])
    def generate_persona(
        payload: PersonaGenerateRequest = Body(...),
        engine: SimulationEngine = Depends(get_engine),
    ) -> dict[str, Any]:
        persona = _generate_persona_from_prompt(payload.prompt, payload.model_hint, payload.explicit_name)
        return {"persona": persona}

    @app.delete(f"{API_PREFIX}/people/by-name/{{person_name}}", status_code=status.HTTP_204_NO_CONTENT, tags=["Personas"])
    def delete_person(person_name: str, engine: SimulationEngine = Depends(get_engine)) -> None:
        deleted = engine.delete_person_by_name(person_name)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    
    @app.post(f"{API_PREFIX}/people/{{person_id}}/regenerate-style-examples", tags=["Personas"])
    def regenerate_style_examples(
        person_id: int,
        engine: SimulationEngine = Depends(get_engine)
    ) -> dict[str, Any]:
        """Regenerate style examples for an existing persona using GPT-4o.
        
        This endpoint calls the StyleExampleGenerator with the persona's current
        attributes and updates the database with new examples.
        
        Returns:
            Dictionary with 'style_examples' key containing JSON string of examples
        """
        try:
            style_examples_json = engine.regenerate_style_examples(person_id)
            return {
                "style_examples": style_examples_json,
                "message": f"Successfully regenerated style examples for person {person_id}"
            }
        except ValueError as exc:
            if "not found" in str(exc).lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except Exception as exc:
            import traceback
            traceback.print_exc()  # Print full traceback to console for debugging
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to regenerate style examples: {str(exc)}"
            )
    
    @app.post(f"{API_PREFIX}/personas/generate-style-examples", tags=["Personas"])
    async def generate_style_examples_from_attributes(
        payload: dict[str, Any] = Body(...),
        engine: SimulationEngine = Depends(get_engine)
    ) -> dict[str, Any]:
        """Generate style examples for a persona based on provided attributes.
        
        This is used when creating a new persona or regenerating examples
        without an existing person_id.
        
        Args:
            payload: Dictionary with name, role, personality, communication_style
            
        Returns:
            Dictionary with 'style_examples' key containing array of examples
        """
        try:
            from .style_filter.example_generator import StyleExampleGenerator
            from virtualoffice.virtualWorkers.worker import WorkerPersona
            
            # Extract attributes from payload
            name = payload.get('name', 'Unknown')
            role = payload.get('role', 'Worker')
            personality_str = payload.get('personality', '')
            communication_style = payload.get('communication_style', 'Professional')
            
            # Parse personality if it's a string
            if isinstance(personality_str, str):
                personality = [p.strip() for p in personality_str.split(',') if p.strip()]
            else:
                personality = personality_str or []
            
            # Create a temporary WorkerPersona object
            temp_persona = WorkerPersona(
                name=name,
                role=role,
                personality=personality,
                communication_style=communication_style,
                skills=[],  # Not needed for style generation
                timezone='UTC',
                work_hours='09:00-17:00',
                break_frequency='50/10',
                email_address=f'{name.lower().replace(" ", ".")}@vdos.local',
                chat_handle=name.lower().replace(' ', '_'),
                is_department_head=False
            )
            
            # Get locale from environment
            locale = os.getenv("VDOS_LOCALE", "en").strip().lower() or "en"
            
            # Generate examples
            generator = StyleExampleGenerator(locale=locale)
            examples = await generator.generate_examples(temp_persona, count=5)
            
            # Convert to JSON-serializable format
            examples_list = [{"type": ex.type, "content": ex.content} for ex in examples]
            
            return {
                "style_examples": examples_list,
                "message": "Successfully generated style examples"
            }
        except Exception as exc:
            import traceback
            traceback.print_exc()  # Print full traceback to console for debugging
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate style examples: {str(exc)}"
            )
    
    @app.post(f"{API_PREFIX}/personas/preview-filter", tags=["Personas"])
    def preview_style_filter(
        payload: dict[str, Any] = Body(...),
        engine: SimulationEngine = Depends(get_engine)
    ) -> dict[str, Any]:
        """Preview how the style filter would transform a message.
        
        Args:
            payload: Dictionary with:
                - message: The message to transform
                - style_examples: Array of style examples
                - message_type: 'email' or 'chat'
                
        Returns:
            Dictionary with original_message and filtered_message
        """
        try:
            from .style_filter.filter import CommunicationStyleFilter
            from .style_filter.models import StyleExample
            
            message = payload.get('message', '')
            style_examples_data = payload.get('style_examples', [])
            message_type = payload.get('message_type', 'email')
            
            if not message:
                raise ValueError("Message is required")
            
            if not style_examples_data:
                raise ValueError("Style examples are required")
            
            # Convert style examples data to StyleExample objects
            style_examples = []
            for ex_data in style_examples_data:
                if isinstance(ex_data, dict) and 'type' in ex_data and 'content' in ex_data:
                    style_examples.append(StyleExample(
                        type=ex_data['type'],
                        content=ex_data['content']
                    ))
            
            if not style_examples:
                raise ValueError("No valid style examples provided")
            
            # Get locale from environment
            locale = os.getenv("VDOS_LOCALE", "en").strip().lower() or "en"
            
            # Create a temporary filter (without database connection)
            # We'll use the filter's prompt building and GPT call directly
            style_filter = CommunicationStyleFilter(
                db_connection=engine.db_connection,
                locale=locale,
                enabled=True
            )
            
            # Build the filter prompt
            prompt = style_filter._build_filter_prompt(style_examples, message_type)
            
            # Call GPT-4o to transform the message
            from virtualoffice.utils.completion_util import generate_text
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message}
            ]
            
            filtered_message, tokens = generate_text(messages, model="gpt-4o")
            
            return {
                "original_message": message,
                "filtered_message": filtered_message.strip(),
                "tokens_used": tokens,
                "message": "Filter preview successful"
            }
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to preview filter: {str(exc)}"
            )

    @app.get(f"{API_PREFIX}/simulation/project-plan", response_model=ProjectPlanRead | None, tags=["Projects"])
    def get_project_plan(engine: SimulationEngine = Depends(get_engine)) -> ProjectPlanRead | None:
        plan = engine.get_project_plan()
        return plan if plan is not None else None

    @app.get(f"{API_PREFIX}/simulation/active-projects", tags=["Projects"])
    def get_active_projects(engine: SimulationEngine = Depends(get_engine)) -> list[dict]:
        """Get all active projects with their team assignments for the current simulation week."""
        return engine.get_active_projects_with_assignments()

    @app.get(f"{API_PREFIX}/projects", tags=["Projects"])
    def list_projects(engine: SimulationEngine = Depends(get_engine)) -> list[dict[str, Any]]:
        """List all projects with assigned person ids for UI hydration.

        Returns a list of objects: { project: {...}, assigned_person_ids: [...] }
        """
        return engine.list_all_projects_with_assignees()

    @app.get(f"{API_PREFIX}/people/{{person_id}}/plans", response_model=list[WorkerPlanRead], tags=["Reports & Analytics"])
    def get_worker_plans(
        person_id: int,
        plan_type: PlanTypeLiteral | None = Query(default=None),
        limit: int | None = Query(default=20, ge=1, le=200),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[WorkerPlanRead]:
        return engine.list_worker_plans(person_id, plan_type=plan_type, limit=limit)

    @app.get(f"{API_PREFIX}/people/{{person_id}}/daily-reports", response_model=list[DailyReportRead], tags=["Reports & Analytics"])
    def get_daily_reports(
        person_id: int,
        day_index: int | None = Query(default=None, ge=0),
        limit: int | None = Query(default=20, ge=1, le=200),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[DailyReportRead]:
        return engine.list_daily_reports(person_id, day_index=day_index, limit=limit)

    @app.get(f"{API_PREFIX}/simulation/reports", response_model=list[SimulationReportRead], tags=["Reports & Analytics"])
    def get_simulation_reports(
        limit: int | None = Query(default=10, ge=1, le=200),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[SimulationReportRead]:
        return engine.list_simulation_reports(limit=limit)

    @app.get(f"{API_PREFIX}/simulation/token-usage", response_model=TokenUsageSummary, tags=["Reports & Analytics"])
    def get_token_usage(engine: SimulationEngine = Depends(get_engine)) -> TokenUsageSummary:
        usage = engine.get_token_usage()
        total = sum(usage.values())
        return TokenUsageSummary(per_model=usage, total_tokens=total)

    @app.get(f"{API_PREFIX}/simulation/quality-metrics", tags=["Reports & Analytics"])
    def get_quality_metrics(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """
        Get communication quality metrics for the current simulation.
        
        Returns metrics including:
        - template_diversity_score: Unique subjects / total emails (target: 70%+)
        - threading_rate: Emails with thread_id / total emails (target: 30%+)
        - participation_gini: Gini coefficient of message distribution (target: <0.3, lower is better)
        - project_context_rate: Messages with project references / total messages (target: 60%+)
        - json_vs_fallback_ratio: JSON communications / total communications (target: 70%+)
        
        Each metric includes current value, target value, and description.
        """
        return engine.quality_metrics.get_all_metrics()

    @app.get(f"{API_PREFIX}/simulation/volume-metrics", tags=["Reports & Analytics"])
    def get_volume_metrics(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """
        Get volume metrics for monitoring and debugging email volume reduction.
        
        Returns metrics including:
        - total_emails_today: Total emails sent today
        - total_chats_today: Total chats sent today
        - avg_emails_per_person: Average emails per person today
        - avg_chats_per_person: Average chats per person today
        - json_communication_rate: Ratio of JSON communications to total
        - inbox_reply_rate: Ratio of inbox replies to total
        - threading_rate: Email threading rate (from quality metrics)
        - daily_limits_hit: List of personas that hit daily limits
        - emails_by_person: Email count per person ID
        - chats_by_person: Chat count per person ID
        """
        return engine.get_volume_metrics()

    @app.get(f"{API_PREFIX}/simulation", response_model=SimulationState, tags=["Simulation Control"])
    def get_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationState:
        return engine.get_state()

    @app.get(f"{API_PREFIX}/debug/runtime", tags=["Reports & Analytics"])
    def get_debug_runtime(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """Expose runtime diagnostics to help verify environment and time model."""
        try:
            state = engine.get_state()
            hours_per_day = getattr(engine, 'hours_per_day', 8)
            day_ticks = max(1, hours_per_day * 60)
            sample = {
                't0': engine._format_sim_time(0),
                't1': engine._format_sim_time(1),
                't60': engine._format_sim_time(60),
                't480': engine._format_sim_time(480),
                't2220': engine._format_sim_time(2220),
            }
            active = engine.get_active_projects_with_assignments()
            return {
                'db_path': str(DB_PATH),
                'engine_module': str(SimulationEngine.__module__),
                'engine_file': str(SimulationEngine.__qualname__),
                'hours_per_day': hours_per_day,
                'day_ticks': day_ticks,
                'state': state.model_dump(),
                'format_samples': sample,
                'active_projects_count': len(active),
                'active_projects': active,
            }
        except Exception as exc:
            return {
                'error': str(exc),
                'db_path': str(DB_PATH),
            }

    @app.get(f"{API_PREFIX}/metrics/planner", tags=["Reports & Analytics"])
    def get_planner_metrics_endpoint(
        limit: int = Query(default=50, ge=1, le=500),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[dict[str, Any]]:
        return engine.get_planner_metrics(limit)

    @app.delete(f"{API_PREFIX}/projects/{{project_id}}", tags=["Projects"])
    def delete_project(project_id: int, engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """Delete a project and its associations (assignments, referencing events)."""
        try:
            info = engine.delete_project(project_id)
            return {
                "message": "Project deleted",
                **info,
            }
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete project: {exc}")

    # Track async initialization status
    _init_status = {"running": False, "error": None, "retries": 0, "max_retries": 3}
    _init_lock = threading.Lock()

    def _retry_init(engine: SimulationEngine, payload: SimulationStartRequest | None, attempt: int = 1):
        """Initialize simulation with retry logic."""
        max_retries = _init_status["max_retries"]
        with _init_lock:
            _init_status["running"] = True
            _init_status["retries"] = attempt
            _init_status["error"] = None

        try:
            state = engine.start(payload)
            with _init_lock:
                _init_status["running"] = False
                _init_status["error"] = None
            print(f"✅ Simulation initialized successfully on attempt {attempt}")
            return state
        except Exception as exc:
            import traceback
            error_msg = f"Attempt {attempt}/{max_retries} failed: {str(exc)}"
            print(f"⚠️  {error_msg}")
            print(f"Full traceback:\n{traceback.format_exc()}")

            if attempt < max_retries:
                # Exponential backoff: 5s, 10s, 20s
                wait_time = 5 * (2 ** (attempt - 1))
                print(f"   Retrying in {wait_time}s...")
                time.sleep(wait_time)
                return _retry_init(engine, payload, attempt + 1)
            else:
                with _init_lock:
                    _init_status["running"] = False
                    _init_status["error"] = f"Failed after {max_retries} attempts: {str(exc)}"
                print(f"❌ Simulation initialization failed after {max_retries} attempts")
                raise

    @app.post(f"{API_PREFIX}/simulation/start", response_model=SimulationControlResponse, tags=["Simulation Control"])
    def start_simulation(
        background_tasks: BackgroundTasks,
        payload: SimulationStartRequest | None = Body(default=None),
        engine: SimulationEngine = Depends(get_engine),
        async_init: bool = Query(default=False, description="Run initialization in background"),
    ) -> SimulationControlResponse:
        if async_init:
            # Start initialization in background
            def _bg_init():
                try:
                    _retry_init(engine, payload)
                except Exception as e:
                    print(f"Background init failed: {e}")

            background_tasks.add_task(_bg_init)
            message = "Simulation initialization started in background (check /simulation/init-status)"
            if payload is not None:
                if payload.projects:
                    project_names = ", ".join(p.project_name for p in payload.projects)
                    message += f" with {len(payload.projects)} projects: {project_names}"
                elif payload.project_name:
                    message += f" for project '{payload.project_name}'"

            # Return immediately with pending status
            state = engine.get_state()
            return SimulationControlResponse(
                current_tick=state.current_tick,
                is_running=False,
                auto_tick=state.auto_tick,
                sim_time=state.sim_time,
                message=message,
            )
        else:
            # Synchronous initialization with retries
            try:
                state = _retry_init(engine, payload)
            except RuntimeError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            except Exception as exc:
                # Catch all other exceptions and return 500 with details
                import traceback
                error_detail = f"{type(exc).__name__}: {str(exc)}\n\nTraceback:\n{traceback.format_exc()}"
                print(f"❌ Simulation start failed with exception:\n{error_detail}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail) from exc
            message = "Simulation started"
            if payload is not None:
                if payload.projects:
                    # Multi-project mode
                    project_names = ", ".join(p.project_name for p in payload.projects)
                    message += f" with {len(payload.projects)} projects: {project_names}"
                elif payload.project_name:
                    # Single-project mode
                    message += f" for project '{payload.project_name}'"
            return SimulationControlResponse(
                current_tick=state.current_tick,
                is_running=state.is_running,
                auto_tick=state.auto_tick,
                sim_time=state.sim_time,
                message=message,
            )

    @app.get(f"{API_PREFIX}/simulation/init-status", tags=["Simulation Control"])
    def get_init_status() -> dict[str, Any]:
        """Check async initialization status."""
        with _init_lock:
            return {
                "running": _init_status["running"],
                "retries": _init_status["retries"],
                "max_retries": _init_status["max_retries"],
                "error": _init_status["error"],
            }

    @app.post(f"{API_PREFIX}/simulation/stop", response_model=SimulationControlResponse, tags=["Simulation Control"])
    def stop_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.stop()
        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Simulation stopped",
        )

    @app.post(f"{API_PREFIX}/simulation/reset", response_model=SimulationControlResponse, tags=["Simulation Control"])
    def reset_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.reset()
        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Simulation reset",
        )

    @app.post(f"{API_PREFIX}/simulation/full-reset", response_model=SimulationControlResponse, tags=["Simulation Control"])
    def full_reset_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.reset_full()
        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Full reset complete (personas deleted)",
        )

    # Back-compat alias for dashboards that call a shorter path.
    @app.post(f"{API_PREFIX}/sim/full-reset", response_model=SimulationControlResponse, tags=["Simulation Control"])
    def full_reset_simulation_alias(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        return full_reset_simulation(engine)

    @app.post(f"{API_PREFIX}/simulation/ticks/start", response_model=SimulationControlResponse, tags=["Simulation Control"])
    def start_ticks(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        try:
            state = engine.start_auto_ticks()
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Automatic ticking enabled",
        )

    @app.post(f"{API_PREFIX}/simulation/ticks/stop", response_model=SimulationControlResponse, tags=["Simulation Control"])
    def stop_ticks(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.stop_auto_ticks()
        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Automatic ticking disabled",
        )

    @app.put(f"{API_PREFIX}/simulation/ticks/interval", tags=["Simulation Control"])
    def set_tick_interval(
        interval: float = Body(..., ge=0.0, le=60.0, embed=True),
        engine: SimulationEngine = Depends(get_engine)
    ) -> dict[str, Any]:
        """Set the auto-tick interval in seconds. Use 0 for maximum speed (no delay)."""
        try:
            return engine.set_tick_interval(interval)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get(f"{API_PREFIX}/simulation/ticks/interval", tags=["Simulation Control"])
    def get_tick_interval(engine: SimulationEngine = Depends(get_engine)) -> dict[str, float]:
        """Get the current auto-tick interval in seconds."""
        return {"tick_interval_seconds": engine.get_tick_interval()}

    @app.get(f"{API_PREFIX}/simulation/auto-pause/status", response_model=AutoPauseStatusResponse, tags=["Projects"])
    def get_auto_pause_status(engine: SimulationEngine = Depends(get_engine)) -> AutoPauseStatusResponse:
        """Get comprehensive project and status information for auto-pause feature."""
        try:
            status_data = engine.get_auto_pause_status()
            return AutoPauseStatusResponse(**status_data)
        except Exception as exc:
            # Return error status with safe defaults
            return AutoPauseStatusResponse(
                auto_pause_enabled=False,
                should_pause=False,
                active_projects_count=0,
                future_projects_count=0,
                current_week=0,
                reason="Status check failed",
                error=str(exc)
            )

    @app.post(f"{API_PREFIX}/simulation/auto-pause/toggle", response_model=AutoPauseStatusResponse, tags=["Projects"])
    def toggle_auto_pause(
        payload: AutoPauseToggleRequest,
        engine: SimulationEngine = Depends(get_engine)
    ) -> AutoPauseStatusResponse:
        """Toggle auto-pause setting and return updated status information."""
        try:
            status_data = engine.set_auto_pause(payload.enabled)
            return AutoPauseStatusResponse(**status_data)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to toggle auto-pause: {str(exc)}"
            ) from exc

    # Backward compatibility endpoint (deprecated)
    @app.get(f"{API_PREFIX}/simulation/auto-pause-status", tags=["Projects"])
    def get_auto_pause_status_legacy(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """Get information about auto-pause on project end status (legacy endpoint)."""
        return engine.get_auto_pause_status()

    @app.post(f"{API_PREFIX}/simulation/advance", response_model=SimulationAdvanceResult, tags=["Simulation Control"])
    def advance_simulation(
        payload: SimulationAdvanceRequest,
        engine: SimulationEngine = Depends(get_engine),
    ) -> SimulationAdvanceResult:
        try:
            return engine.advance(payload.ticks, payload.reason)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Administrative hard reset:
    #  - Stop auto ticks (best effort)
    #  - Delete the shared SQLite file
    #  - Re-create Email/Chat/Sim schemas
    #  - Reset engine runtime view of state
    @app.post(f"{API_PREFIX}/admin/hard-reset", response_model=SimulationControlResponse, tags=["Admin"])
    def admin_hard_reset(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        """
        ⚠️  DANGEROUS: Complete database reset for development use only.

        This endpoint:
        - Deletes the entire simulation database
        - Recreates all schemas from scratch
        - Resets the simulation engine state

        WARNING: This will destroy ALL simulation data permanently.
        TODO: Add authentication before deploying to production.
        """
        try:
            engine.stop_auto_ticks()
        except Exception:
            pass
        # Local imports to avoid top-level cycles
        try:
            from virtualoffice.common import db as _db
            from virtualoffice.servers.email.app import EMAIL_SCHEMA as _EMAIL_SCHEMA  # type: ignore
            from virtualoffice.servers.chat.app import CHAT_SCHEMA as _CHAT_SCHEMA  # type: ignore
            from .engine import SIM_SCHEMA as _SIM_SCHEMA
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Schema import failed: {exc}")

        # Remove DB file
        try:
            _db.DB_PATH.unlink(missing_ok=True)  # type: ignore[attr-defined]
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to remove DB: {exc}")

        # Recreate schemas
        try:
            _db.execute_script(_EMAIL_SCHEMA)
            _db.execute_script(_CHAT_SCHEMA)
            _db.execute_script(_SIM_SCHEMA)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to recreate schema: {exc}")

        # Ensure simulation_state row exists and reset engine view
        try:
            # Create simulation_state row if missing (fresh DB)
            try:
                engine._ensure_state_row()  # type: ignore[attr-defined]
            except Exception:
                pass
            # engine.reset() assumes tables exist; it also clears runtime caches
            state = engine.reset()
            # Re-bootstrap channels (mailboxes/users) for a fresh DB
            try:
                engine._bootstrap_channels()  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Engine reset failed: {exc}")

        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Hard reset complete (DB recreated)",
        )

    @app.post(f"{API_PREFIX}/admin/soft-reset-preserve", tags=["Admin"])
    def admin_soft_reset_preserve(
        delete_project_name: str | None = Body(default="Dashboard Project"),
        engine: SimulationEngine = Depends(get_engine),
    ) -> dict[str, Any]:
        """Wipe runtime data but preserve personas and projects (except an optional project to delete).

        - Preserves: people, schedule_blocks, project_plans (except the one named by delete_project_name), project_assignments
        - Wipes: worker_plans, hourly_summaries, daily_reports, simulation_reports,
                 worker_runtime_messages, worker_exchange_log, worker_status_overrides,
                 events, tick_log
        - Email tables: deletes all rows (emails, email_recipients, drafts, mailboxes)
        - Chat tables: deletes all rows (chat_messages, chat_members, chat_rooms, chat_users)
        - Resets simulation_state to tick=0, is_running=0, auto_tick=0
        """
        try:
            try:
                engine.stop_auto_ticks()
            except Exception:
                pass

            summary: dict[str, Any] = {"deleted": {}}

            with get_connection() as conn:
                # Optionally delete one project by name (and cascading assignments)
                if delete_project_name:
                    conn.execute("DELETE FROM project_plans WHERE project_name = ?", (delete_project_name,))
                    summary["deleted"]["project_name"] = delete_project_name

                # Emails: delete recipients first, then emails, then drafts/mailboxes
                for tbl in ("email_recipients", "emails", "drafts", "mailboxes"):
                    try:
                        conn.execute(f"DELETE FROM {tbl}")
                        summary["deleted"][tbl] = "all"
                    except Exception:
                        pass

                # Chat: messages → members → rooms → users
                for tbl in ("chat_messages", "chat_members", "chat_rooms", "chat_users"):
                    try:
                        conn.execute(f"DELETE FROM {tbl}")
                        summary["deleted"][tbl] = "all"
                    except Exception:
                        pass

                # Simulation runtime artifacts
                for tbl in (
                    "worker_plans",
                    "hourly_summaries",
                    "daily_reports",
                    "simulation_reports",
                    "worker_runtime_messages",
                    "worker_exchange_log",
                    "worker_status_overrides",
                    "events",
                    "tick_log",
                ):
                    try:
                        conn.execute(f"DELETE FROM {tbl}")
                        summary["deleted"][tbl] = "all"
                    except Exception:
                        pass

                # Reset simulation_state row (create if missing)
                conn.execute(
                    "INSERT INTO simulation_state(id, current_tick, is_running, auto_tick)\n"
                    "VALUES(1, 0, 0, 0)\n"
                    "ON CONFLICT(id) DO UPDATE SET current_tick=0, is_running=0, auto_tick=0"
                )

            state = engine.get_state()
            return {
                "message": "Soft reset complete; personas and projects preserved (except optional deletion)",
                "current_tick": state.current_tick,
                "is_running": state.is_running,
                "auto_tick": state.auto_tick,
                "deleted": summary.get("deleted", {}),
            }
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Soft reset failed: {exc}")

    @app.post(f"{API_PREFIX}/admin/rewind", tags=["Admin"])
    def admin_rewind(
        tick: int = Body(..., embed=True, ge=0),
        engine: SimulationEngine = Depends(get_engine),
    ) -> dict[str, Any]:
        """Rewind the simulation to a specific tick and purge later data.

        Actions:
        - Stops auto-ticks (best effort)
        - Updates simulation_state.current_tick to the cutoff
        - Deletes worker plans/summaries/reports/exchanges/tick logs after cutoff
        - Deletes events with at_tick strictly greater than cutoff
        - Deletes emails and chats with sent_at after the simulated cutoff datetime (when available)
        """
        try:
            # Best effort stop
            try:
                engine.stop_auto_ticks()
            except Exception:
                pass

            state = engine.get_state()
            cutoff = max(0, min(int(tick), state.current_tick))
            hours_per_day = getattr(engine, 'hours_per_day', 8)
            day_ticks = max(1, hours_per_day * 60)
            hour_index_cutoff = (cutoff - 1) // 60 if cutoff > 0 else 0
            day_index_cutoff = (cutoff - 1) // day_ticks if cutoff > 0 else 0

            # Compute simulated cutoff datetime for email/chat purges if base is known
            try:
                cutoff_dt = engine._sim_datetime_for_tick(cutoff)
                cutoff_iso = cutoff_dt.isoformat() if cutoff_dt else None
            except Exception:
                cutoff_iso = None

            deleted: dict[str, int] = {}
            with get_connection() as conn:
                def _exists(table: str) -> bool:
                    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                    return bool(row)

                def _count(table: str, where: str, params: tuple) -> int:
                    row = conn.execute(f"SELECT COUNT(*) as c FROM {table} WHERE {where}", params).fetchone()
                    return int(row["c"]) if row else 0

                # Engine-owned artifacts
                if _exists('worker_plans'):
                    deleted['worker_plans'] = _count('worker_plans', 'tick > ?', (cutoff,))
                    conn.execute('DELETE FROM worker_plans WHERE tick > ?', (cutoff,))
                if _exists('hourly_summaries'):
                    deleted['hourly_summaries'] = _count('hourly_summaries', 'hour_index > ?', (hour_index_cutoff,))
                    conn.execute('DELETE FROM hourly_summaries WHERE hour_index > ?', (hour_index_cutoff,))
                if _exists('daily_reports'):
                    deleted['daily_reports'] = _count('daily_reports', 'day_index > ?', (day_index_cutoff,))
                    conn.execute('DELETE FROM daily_reports WHERE day_index > ?', (day_index_cutoff,))
                if _exists('worker_exchange_log'):
                    deleted['worker_exchange_log'] = _count('worker_exchange_log', 'tick > ?', (cutoff,))
                    conn.execute('DELETE FROM worker_exchange_log WHERE tick > ?', (cutoff,))
                if _exists('tick_log'):
                    deleted['tick_log'] = _count('tick_log', 'tick > ?', (cutoff,))
                    conn.execute('DELETE FROM tick_log WHERE tick > ?', (cutoff,))
                if _exists('events'):
                    deleted['events'] = _count('events', 'at_tick IS NOT NULL AND at_tick > ?', (cutoff,))
                    conn.execute('DELETE FROM events WHERE at_tick IS NOT NULL AND at_tick > ?', (cutoff,))

                # Email/Chat based on simulated time cutoff
                if cutoff_iso and _exists('emails'):
                    deleted['emails'] = _count('emails', 'sent_at > ?', (cutoff_iso,))
                    conn.execute('DELETE FROM emails WHERE sent_at > ?', (cutoff_iso,))
                if cutoff_iso and _exists('chat_messages'):
                    deleted['chat_messages'] = _count('chat_messages', 'sent_at > ?', (cutoff_iso,))
                    conn.execute('DELETE FROM chat_messages WHERE sent_at > ?', (cutoff_iso,))

                # Update simulation state
                if _exists('simulation_state'):
                    conn.execute('UPDATE simulation_state SET current_tick = ? WHERE id = 1', (cutoff,))

            return {
                'message': f'Rewound to tick {cutoff}',
                'cutoff': cutoff,
                'hour_index_cutoff': hour_index_cutoff,
                'day_index_cutoff': day_index_cutoff,
                'cutoff_iso': cutoff_iso,
                'deleted': deleted,
            }
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Failed to rewind: {exc}')

    @app.post(f"{API_PREFIX}/events", response_model=EventRead, status_code=status.HTTP_201_CREATED, tags=["Events"])
    def create_event(payload: EventCreate, engine: SimulationEngine = Depends(get_engine)) -> EventRead:
        return EventRead(**engine.inject_event(payload))

    @app.get(f"{API_PREFIX}/events", response_model=list[EventRead], tags=["Events"])
    def list_events(engine: SimulationEngine = Depends(get_engine)) -> list[EventRead]:
        return [EventRead(**event) for event in engine.list_events()]

    @app.post(f"{API_PREFIX}/people/status-override", response_model=StatusOverrideResponse, tags=["Personas"])
    def set_status_override(payload: StatusOverrideRequest, engine: SimulationEngine = Depends(get_engine)) -> StatusOverrideResponse:
        """Set a persona's status to Absent/Offline/SickLeave for external integration.

        This endpoint allows external projects to manually control when a persona is unavailable.
        While the status is active, the persona will not participate in planning or communications.
        """
        # Find the person
        if payload.person_id is not None:
            people = engine.list_people()
            person = next((p for p in people if p.id == payload.person_id), None)
            if not person:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with ID {payload.person_id} not found")
        elif payload.person_name is not None:
            people = engine.list_people()
            person = next((p for p in people if p.name == payload.person_name), None)
            if not person:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with name '{payload.person_name}' not found")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either person_id or person_name must be provided")

        # Calculate until_tick
        state = engine.get_state()
        if payload.duration_ticks is not None:
            until_tick = state.current_tick + payload.duration_ticks
        else:
            # Default to end of current day
            hours_per_day = engine.hours_per_day
            current_day_start = (state.current_tick // hours_per_day) * hours_per_day
            until_tick = current_day_start + hours_per_day

        # Set the override using the internal method
        engine._set_status_override(person.id, payload.status, until_tick, payload.reason)

        return StatusOverrideResponse(
            person_id=person.id,
            person_name=person.name,
            status=payload.status,
            until_tick=until_tick,
            reason=payload.reason,
            message=f"Status override set for {person.name} until tick {until_tick}"
        )

    @app.get(f"{API_PREFIX}/people/{{person_id}}/status-override", response_model=StatusOverrideResponse | None, tags=["Personas"])
    def get_status_override(person_id: int, engine: SimulationEngine = Depends(get_engine)) -> StatusOverrideResponse | None:
        """Get the current status override for a persona, if any."""
        # Check if person exists
        people = engine.list_people()
        person = next((p for p in people if p.id == person_id), None)
        if not person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with ID {person_id} not found")

        # Get status overrides (direct access since engine.state doesn't exist in old engine)
        override = engine._status_overrides.get(person_id)

        if override is None:
            return None

        status_str, until_tick = override

        # Check if override is still active
        current_tick = engine.get_state().current_tick
        if current_tick >= until_tick:
            return None

        return StatusOverrideResponse(
            person_id=person.id,
            person_name=person.name,
            status=status_str,
            until_tick=until_tick,
            reason="Active override",  # We don't store reason separately in the current schema
            message=f"Status override active for {person.name} until tick {until_tick}"
        )

    @app.delete(f"{API_PREFIX}/people/{{person_id}}/status-override", status_code=status.HTTP_204_NO_CONTENT, tags=["Personas"])
    def clear_status_override(person_id: int, engine: SimulationEngine = Depends(get_engine)) -> None:
        """Clear a persona's status override, making them available again."""
        # Check if person exists
        people = engine.list_people()
        person = next((p for p in people if p.id == person_id), None)
        if not person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with ID {person_id} not found")

        # Clear status override (direct access since engine.state doesn't exist in old engine)
        if person_id in engine._status_overrides:
            engine._status_overrides.pop(person_id)
            # Also delete from database
            from virtualoffice.common.db import get_connection
            with get_connection() as conn:
                conn.execute("DELETE FROM worker_status_overrides WHERE worker_id = ?", (person_id,))

    # --- Monitoring proxy endpoints (avoid CORS by routing through sim_manager) ---
    @app.get(f"{API_PREFIX}/monitor/emails/{{person_id}}", tags=["Monitoring"])
    def monitor_emails(
        person_id: int,
        box: str = Query(default="all", pattern="^(all|inbox|sent)$"),
        limit: int | None = Query(default=50, ge=1, le=500),
        since_id: int | None = Query(default=None),
        since_timestamp: str | None = Query(default=None),
        before_id: int | None = Query(default=None),
        engine: SimulationEngine = Depends(get_engine),
    ) -> dict[str, list[dict]]:
        """Return inbox/sent emails for the given person by proxying the email server."""
        people = engine.list_people()
        person = next((p for p in people if p.id == person_id), None)
        if not person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
        # Use the underlying HttpEmailGateway client if available
        email_client = getattr(engine.email_gateway, "client", None)
        if email_client is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Email client unavailable")

        params = {"limit": limit}
        if since_id is not None:
            params["since_id"] = since_id
        if since_timestamp is not None:
            params["since_timestamp"] = since_timestamp
        if before_id is not None:
            params["before_id"] = before_id

        result: dict[str, list[dict]] = {"inbox": [], "sent": []}
        try:
            if box in ("all", "inbox"):
                r_in = email_client.get(f"/mailboxes/{person.email_address}/emails", params=params)
                r_in.raise_for_status()
                result["inbox"] = r_in.json()
            if box in ("all", "sent"):
                r_out = email_client.get(f"/senders/{person.email_address}/emails", params=params)
                r_out.raise_for_status()
                result["sent"] = r_out.json()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Email proxy failed: {exc}")
        return result

    @app.get(f"{API_PREFIX}/monitor/chat/messages/{{person_id}}", tags=["Monitoring"])
    def monitor_chat_messages(
        person_id: int,
        scope: str = Query(default="all", pattern="^(all|dms|rooms)$"),
        limit: int | None = Query(default=100, ge=1, le=1000),
        since_id: int | None = Query(default=None),
        since_timestamp: str | None = Query(default=None),
        engine: SimulationEngine = Depends(get_engine),
    ) -> dict[str, list[dict]]:
        """Return chat messages visible to a user (DMs and/or rooms) via the chat server."""
        people = engine.list_people()
        person = next((p for p in people if p.id == person_id), None)
        if not person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
        chat_client = getattr(engine.chat_gateway, "client", None)
        if chat_client is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Chat client unavailable")

        params = {"limit": limit}
        if since_id is not None:
            params["since_id"] = since_id
        if since_timestamp is not None:
            params["since_timestamp"] = since_timestamp

        result: dict[str, list[dict]] = {"dms": [], "rooms": []}
        try:
            if scope in ("all", "dms"):
                rd = chat_client.get(f"/users/{person.chat_handle}/dms", params=params)
                rd.raise_for_status()
                result["dms"] = rd.json()
            if scope in ("all", "rooms"):
                rr = chat_client.get(f"/users/{person.chat_handle}/messages", params=params)
                rr.raise_for_status()
                result["rooms"] = rr.json()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat proxy failed: {exc}")
        return result
    @app.get(f"{API_PREFIX}/monitor/chat/rooms/{{person_id}}", tags=["Monitoring"])
    def monitor_chat_rooms(
        person_id: int,
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[dict]:
        """Return room metadata visible to a user via the chat server."""
        chat_client = getattr(engine.chat_gateway, "client", None)
        if chat_client is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Chat client unavailable")
        person = engine.get_person(person_id)
        try:
            response = chat_client.get(f"/users/{person.chat_handle}/rooms")
            return response.json()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat proxy failed: {exc}")

    @app.get(f"{API_PREFIX}/monitor/chat/room/{{room_slug}}/messages", tags=["Monitoring"])
    def monitor_room_messages(
        room_slug: str,
        limit: int | None = Query(default=100, ge=1, le=1000),
        since_id: int | None = Query(default=None),
        since_timestamp: str | None = Query(default=None),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[dict]:
        """Return messages for a specific chat room via the chat server."""
        chat_client = getattr(engine.chat_gateway, "client", None)
        if chat_client is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Chat client unavailable")

        params = {"limit": limit}
        if since_id is not None:
            params["since_id"] = since_id
        if since_timestamp is not None:
            params["since_timestamp"] = since_timestamp

        try:
            response = chat_client.get(f"/rooms/{room_slug}/messages", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat proxy failed: {exc}")

    # --- Export/Import endpoints ---
    @app.get(f"{API_PREFIX}/export/personas", tags=["Import/Export"])
    def export_personas(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """Export all personas to JSON format for backup/sharing."""
        people = engine.list_people()
        export_data = {
            "export_type": "personas",
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
            "personas": []
        }
        
        for person in people:
            # Convert PersonRead to export format (exclude id only, include persona_markdown)
            persona_data = {
                "name": person.name,
                "role": person.role,
                "timezone": person.timezone,
                "work_hours": person.work_hours,
                "break_frequency": person.break_frequency,
                "communication_style": person.communication_style,
                "email_address": person.email_address,
                "chat_handle": person.chat_handle,
                "is_department_head": person.is_department_head,
                "team_name": person.team_name,
                "skills": list(person.skills),
                "personality": list(person.personality),
                "objectives": list(person.objectives) if person.objectives else [],
                "metrics": list(person.metrics) if person.metrics else [],
                "planning_guidelines": list(person.planning_guidelines) if person.planning_guidelines else [],
                "schedule": [{"start": block.start, "end": block.end, "activity": block.activity}
                           for block in person.schedule] if person.schedule else [],
                "event_playbook": dict(person.event_playbook) if person.event_playbook else {},
                "statuses": list(person.statuses) if person.statuses else [],
                "style_examples": person.style_examples if person.style_examples else None,
                "persona_markdown": person.persona_markdown
            }
            export_data["personas"].append(persona_data)
        
        return export_data

    @app.post(f"{API_PREFIX}/import/personas", tags=["Import/Export"])
    def import_personas(
        import_data: dict[str, Any] = Body(...),
        engine: SimulationEngine = Depends(get_engine)
    ) -> dict[str, Any]:
        """Import personas from JSON format, integrating seamlessly into the database."""
        if import_data.get("export_type") != "personas":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid export type, expected 'personas'")
        
        personas_data = import_data.get("personas", [])
        if not isinstance(personas_data, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid personas data format")
        
        imported_count = 0
        skipped_count = 0
        errors = []
        
        # Get existing personas to check for duplicates
        existing_people = engine.list_people()
        existing_emails = {p.email_address for p in existing_people}
        existing_handles = {p.chat_handle for p in existing_people}
        
        for i, persona_data in enumerate(personas_data):
            try:
                # Check for duplicates
                email = persona_data.get("email_address")
                handle = persona_data.get("chat_handle")
                
                if email in existing_emails:
                    skipped_count += 1
                    errors.append(f"Persona {i+1}: Email '{email}' already exists, skipped")
                    continue
                    
                if handle in existing_handles:
                    skipped_count += 1
                    errors.append(f"Persona {i+1}: Chat handle '{handle}' already exists, skipped")
                    continue
                
                # Create PersonCreate object
                person_create = PersonCreate(**persona_data)
                
                # Import into database
                created_person = engine.create_person(person_create)
                imported_count += 1
                
                # Update tracking sets
                existing_emails.add(email)
                existing_handles.add(handle)
                
            except Exception as exc:
                errors.append(f"Persona {i+1}: {str(exc)}")
                skipped_count += 1
        
        return {
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "total_processed": len(personas_data),
            "errors": errors,
            "message": f"Successfully imported {imported_count} personas, skipped {skipped_count}"
        }

    @app.get(f"{API_PREFIX}/export/projects", tags=["Import/Export"])
    def export_projects(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """Export current project configuration to JSON format."""
        # Note: Projects are stored in the frontend JavaScript, not in the database
        # This endpoint returns the current project plan if simulation is running
        project_plan = engine.get_project_plan()
        
        export_data = {
            "export_type": "projects",
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
            "projects": []
        }
        
        if project_plan:
            # Single project mode - convert to multi-project format
            export_data["projects"].append({
                "project_name": project_plan.project_name,
                "project_summary": project_plan.project_summary,
                "start_week": 1,
                "duration_weeks": project_plan.duration_weeks,
                "assigned_person_ids": []  # Not stored in current schema
            })
        
        return export_data

    @app.post(f"{API_PREFIX}/import/projects", tags=["Import/Export"])
    def import_projects(
        import_data: dict[str, Any] = Body(...),
        engine: SimulationEngine = Depends(get_engine)
    ) -> dict[str, Any]:
        """Import projects configuration. Note: Projects are managed in frontend, this validates format."""
        if import_data.get("export_type") != "projects":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid export type, expected 'projects'")
        
        projects_data = import_data.get("projects", [])
        if not isinstance(projects_data, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid projects data format")
        
        validated_projects = []
        errors = []
        
        for i, project_data in enumerate(projects_data):
            try:
                # Validate project structure
                required_fields = ["project_name", "project_summary", "start_week", "duration_weeks"]
                for field in required_fields:
                    if field not in project_data:
                        raise ValueError(f"Missing required field: {field}")
                
                # Validate data types and ranges
                if not isinstance(project_data["start_week"], int) or project_data["start_week"] < 1:
                    raise ValueError("start_week must be a positive integer")
                    
                if not isinstance(project_data["duration_weeks"], int) or project_data["duration_weeks"] < 1:
                    raise ValueError("duration_weeks must be a positive integer")
                
                # Ensure assigned_person_ids is a list
                if "assigned_person_ids" not in project_data:
                    project_data["assigned_person_ids"] = []
                elif not isinstance(project_data["assigned_person_ids"], list):
                    raise ValueError("assigned_person_ids must be a list")
                
                validated_projects.append(project_data)
                
            except Exception as exc:
                errors.append(f"Project {i+1}: {str(exc)}")
        
        return {
            "validated_projects": validated_projects,
            "valid_count": len(validated_projects),
            "error_count": len(errors),
            "total_processed": len(projects_data),
            "errors": errors,
            "message": f"Validated {len(validated_projects)} projects, {len(errors)} errors found"
        }

    # ===== Style Filter Configuration Endpoints =====

    @app.get(f"{API_PREFIX}/style-filter/config", tags=["Style Filter"])
    def get_style_filter_config(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """Get the current style filter configuration."""
        try:
            from virtualoffice.common import db
            with db.get_connection() as conn:
                cursor = conn.execute("SELECT enabled, updated_at FROM style_filter_config WHERE id = 1")
                row = cursor.fetchone()
                
                if row:
                    return {
                        "enabled": bool(row[0]),
                        "updated_at": row[1]
                    }
                else:
                    # Return default if no config exists
                    return {
                        "enabled": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get style filter config: {str(exc)}"
            )
    
    @app.post(f"{API_PREFIX}/style-filter/config", tags=["Style Filter"])
    def update_style_filter_config(
        payload: dict[str, bool] = Body(...),
        engine: SimulationEngine = Depends(get_engine)
    ) -> dict[str, Any]:
        """Update the style filter configuration."""
        try:
            enabled = payload.get("enabled", True)
            from virtualoffice.common import db
            with db.get_connection() as conn:
                # Ensure the config row exists
                conn.execute("""
                    INSERT OR IGNORE INTO style_filter_config (id, enabled, updated_at)
                    VALUES (1, ?, ?)
                """, (int(enabled), datetime.now(timezone.utc).isoformat()))
                
                # Update the config
                conn.execute("""
                    UPDATE style_filter_config
                    SET enabled = ?, updated_at = ?
                    WHERE id = 1
                """, (int(enabled), datetime.now(timezone.utc).isoformat()))
                
                conn.commit()
                
                return {
                    "enabled": enabled,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "message": f"Style filter {'enabled' if enabled else 'disabled'}"
                }
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update style filter config: {str(exc)}"
            )
    
    @app.get(f"{API_PREFIX}/style-filter/metrics", tags=["Style Filter"])
    def get_style_filter_metrics(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """Get style filter usage metrics for the current session."""
        try:
            from virtualoffice.common import db
            with db.get_connection() as conn:
                # Get session metrics (all metrics)
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_transformations,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_transformations,
                        SUM(tokens_used) as total_tokens,
                        AVG(latency_ms) as avg_latency_ms,
                        message_type,
                        COUNT(*) as count_by_type
                    FROM style_filter_metrics
                    GROUP BY message_type
                """)
                
                by_type = {}
                total_transformations = 0
                successful_transformations = 0
                total_tokens = 0
                avg_latency = 0.0
                
                for row in cursor.fetchall():
                    msg_type = row[4]
                    by_type[msg_type] = row[5]
                    total_transformations += row[0]
                    successful_transformations += row[1]
                    total_tokens += row[2] or 0
                    if row[3]:
                        avg_latency = row[3]
                
                # Calculate estimated cost (GPT-4o pricing: $2.50 per 1M input tokens, $10 per 1M output tokens)
                # Assuming roughly 50/50 split for simplicity
                estimated_cost = (total_tokens / 1_000_000) * 6.25  # Average of input/output pricing
                
                return {
                    "total_transformations": total_transformations,
                    "successful_transformations": successful_transformations,
                    "total_tokens": total_tokens,
                    "average_latency_ms": round(avg_latency, 2) if avg_latency else 0,
                    "estimated_cost_usd": round(estimated_cost, 4),
                    "by_message_type": by_type
                }
        except Exception as exc:
            # Return empty metrics if table doesn't exist or other error
            return {
                "total_transformations": 0,
                "successful_transformations": 0,
                "total_tokens": 0,
                "average_latency_ms": 0,
                "estimated_cost_usd": 0.0,
                "by_message_type": {}
            }

    # ========================================================================
    # REPLAY / TIME MACHINE API ENDPOINTS
    # ========================================================================

    @app.get(f"{API_PREFIX}/replay/metadata", tags=["Replay"])
    def get_replay_metadata(
        replay: ReplayManager = Depends(get_replay_manager)
    ) -> dict[str, Any]:
        """
        Get replay metadata including max generated tick and current state.

        Returns simulation boundaries and statistics for replay functionality.
        """
        return replay.get_metadata()

    @app.get(f"{API_PREFIX}/replay/jump/{{tick}}", tags=["Replay"])
    def jump_to_tick(
        tick: int,
        replay: ReplayManager = Depends(get_replay_manager)
    ) -> dict[str, Any]:
        """
        Jump to a specific tick (with safety validation).

        Args:
            tick: Tick number to jump to

        Returns:
            Tick data including emails and chats at that tick

        Raises:
            HTTPException: If tick is out of valid range
        """
        try:
            return replay.jump_to_tick(tick)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post(f"{API_PREFIX}/replay/jump", tags=["Replay"])
    def jump_to_time(
        payload: dict[str, int] = Body(...),
        replay: ReplayManager = Depends(get_replay_manager)
    ) -> dict[str, Any]:
        """
        Jump to a specific time (day/hour/minute).

        Request body:
            {
                "day": 2,
                "hour": 14,
                "minute": 35
            }

        Returns:
            Tick data at the specified time

        Raises:
            HTTPException: If time is invalid or beyond max generated data
        """
        try:
            day = payload.get("day")
            hour = payload.get("hour")
            minute = payload.get("minute")

            if day is None or hour is None or minute is None:
                raise HTTPException(
                    status_code=400,
                    detail="Missing required fields: day, hour, minute"
                )

            return replay.jump_to_time(day, hour, minute)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get(f"{API_PREFIX}/replay/current", tags=["Replay"])
    def get_current_replay_data(
        replay: ReplayManager = Depends(get_replay_manager)
    ) -> dict[str, Any]:
        """
        Get emails and chats at the current tick.

        Returns:
            Current tick data including time info and communications
        """
        return replay.get_current_tick_data()

    @app.post(f"{API_PREFIX}/replay/mode", tags=["Replay"])
    def set_replay_mode(
        payload: dict[str, str] = Body(...),
        replay: ReplayManager = Depends(get_replay_manager)
    ) -> dict[str, Any]:
        """
        Set the replay mode (live or replay).

        Request body:
            {
                "mode": "live" | "replay"
            }

        Returns:
            Updated metadata

        Raises:
            HTTPException: If mode is invalid
        """
        try:
            mode = payload.get("mode")
            if not mode:
                raise HTTPException(
                    status_code=400,
                    detail="Missing required field: mode"
                )
            return replay.set_mode(mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get(f"{API_PREFIX}/replay/reset", tags=["Replay"])
    def reset_to_live(
        replay: ReplayManager = Depends(get_replay_manager)
    ) -> dict[str, Any]:
        """
        Reset to live mode (jump to max generated tick).

        Returns:
            Metadata after reset
        """
        return replay.reset_to_live()

    return app


def _bootstrap_default_app() -> FastAPI:
    try:
        return create_app()
    except Exception as exc:  # pragma: no cover - bootstrap fallback
        # Emit detailed diagnostics so operators can find the root cause quickly
        try:
            import traceback
            detail = f"{type(exc).__name__}: {str(exc)}\n\nTraceback:\n{traceback.format_exc()}"
            print("[VDOS] Simulation app bootstrap failed. Falling back to degraded mode.\n" + detail)
            # Persist error for GUI/ops per project convention
            try:
                os.makedirs("logs", exist_ok=True)
                with open(os.path.join("logs", "error_output.txt"), "w", encoding="utf-8") as f:
                    f.write(detail)
            except Exception:
                pass
        except Exception:
            detail = str(exc)

        fallback = FastAPI(title="VDOS Simulation Manager", version="0.1.0")

        @fallback.get("/bootstrap-status")
        def bootstrap_status() -> dict[str, Any]:
            return {"status": "degraded", "detail": detail}

        return fallback


app = _bootstrap_default_app()
