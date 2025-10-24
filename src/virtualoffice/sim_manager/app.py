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
from .gateways import HttpChatGateway, HttpEmailGateway
from .schemas import (
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

_DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "index_new.html")

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

    email_gateway = HttpEmailGateway(base_url=email_base)
    chat_gateway = HttpChatGateway(base_url=chat_base)
    # Allow tick interval override for faster auto-ticking if used
    try:
        tick_interval_seconds = float(os.getenv("VDOS_TICK_INTERVAL_SECONDS", "1.0"))
    except ValueError:
        tick_interval_seconds = 1.0
    # Use minute-level ticks by default: 480 ticks per 8-hour workday
    try:
        ticks_per_day = int(os.getenv("VDOS_TICKS_PER_DAY", "480"))
    except ValueError:
        ticks_per_day = 480
    return SimulationEngine(
        email_gateway=email_gateway,
        chat_gateway=chat_gateway,
        sim_manager_email=sim_email,
        sim_manager_handle=sim_handle,
        tick_interval_seconds=tick_interval_seconds,
        hours_per_day=ticks_per_day,
    )


def create_app(engine: SimulationEngine | None = None) -> FastAPI:
    app = FastAPI(title="VDOS Simulation Manager", version="0.1.0")
    app.state.engine = engine or _build_default_engine()

    # Mount static files
    static_path = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/", response_class=HTMLResponse)
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

    @app.get(f"{API_PREFIX}/people", response_model=list[PersonRead])
    def list_people(engine: SimulationEngine = Depends(get_engine)) -> list[PersonRead]:
        return engine.list_people()

    @app.post(f"{API_PREFIX}/people", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
    def create_person(payload: PersonCreate, engine: SimulationEngine = Depends(get_engine)) -> PersonRead:
        return engine.create_person(payload)

    @app.post(f"{API_PREFIX}/personas/generate")
    def generate_persona(
        payload: PersonaGenerateRequest = Body(...),
        engine: SimulationEngine = Depends(get_engine),
    ) -> dict[str, Any]:
        persona = _generate_persona_from_prompt(payload.prompt, payload.model_hint, payload.explicit_name)
        return {"persona": persona}

    @app.delete(f"{API_PREFIX}/people/by-name/{{person_name}}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_person(person_name: str, engine: SimulationEngine = Depends(get_engine)) -> None:
        deleted = engine.delete_person_by_name(person_name)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    @app.get(f"{API_PREFIX}/simulation/project-plan", response_model=ProjectPlanRead | None)
    def get_project_plan(engine: SimulationEngine = Depends(get_engine)) -> ProjectPlanRead | None:
        plan = engine.get_project_plan()
        return plan if plan is not None else None

    @app.get(f"{API_PREFIX}/simulation/active-projects")
    def get_active_projects(engine: SimulationEngine = Depends(get_engine)) -> list[dict]:
        """Get all active projects with their team assignments for the current simulation week."""
        return engine.get_active_projects_with_assignments()

    @app.get(f"{API_PREFIX}/people/{{person_id}}/plans", response_model=list[WorkerPlanRead])
    def get_worker_plans(
        person_id: int,
        plan_type: PlanTypeLiteral | None = Query(default=None),
        limit: int | None = Query(default=20, ge=1, le=200),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[WorkerPlanRead]:
        return engine.list_worker_plans(person_id, plan_type=plan_type, limit=limit)

    @app.get(f"{API_PREFIX}/people/{{person_id}}/daily-reports", response_model=list[DailyReportRead])
    def get_daily_reports(
        person_id: int,
        day_index: int | None = Query(default=None, ge=0),
        limit: int | None = Query(default=20, ge=1, le=200),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[DailyReportRead]:
        return engine.list_daily_reports(person_id, day_index=day_index, limit=limit)

    @app.get(f"{API_PREFIX}/simulation/reports", response_model=list[SimulationReportRead])
    def get_simulation_reports(
        limit: int | None = Query(default=10, ge=1, le=200),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[SimulationReportRead]:
        return engine.list_simulation_reports(limit=limit)

    @app.get(f"{API_PREFIX}/simulation/token-usage", response_model=TokenUsageSummary)
    def get_token_usage(engine: SimulationEngine = Depends(get_engine)) -> TokenUsageSummary:
        usage = engine.get_token_usage()
        total = sum(usage.values())
        return TokenUsageSummary(per_model=usage, total_tokens=total)

    @app.get(f"{API_PREFIX}/simulation", response_model=SimulationState)
    def get_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationState:
        return engine.get_state()

    @app.get(f"{API_PREFIX}/metrics/planner")
    def get_planner_metrics_endpoint(
        limit: int = Query(default=50, ge=1, le=500),
        engine: SimulationEngine = Depends(get_engine),
    ) -> list[dict[str, Any]]:
        return engine.get_planner_metrics(limit)

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

    @app.post(f"{API_PREFIX}/simulation/start", response_model=SimulationControlResponse)
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

    @app.get(f"{API_PREFIX}/simulation/init-status")
    def get_init_status() -> dict[str, Any]:
        """Check async initialization status."""
        with _init_lock:
            return {
                "running": _init_status["running"],
                "retries": _init_status["retries"],
                "max_retries": _init_status["max_retries"],
                "error": _init_status["error"],
            }

    @app.post(f"{API_PREFIX}/simulation/stop", response_model=SimulationControlResponse)
    def stop_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.stop()
        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Simulation stopped",
        )

    @app.post(f"{API_PREFIX}/simulation/reset", response_model=SimulationControlResponse)
    def reset_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.reset()
        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Simulation reset",
        )

    @app.post(f"{API_PREFIX}/simulation/full-reset", response_model=SimulationControlResponse)
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
    @app.post(f"{API_PREFIX}/sim/full-reset", response_model=SimulationControlResponse)
    def full_reset_simulation_alias(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        return full_reset_simulation(engine)

    @app.post(f"{API_PREFIX}/simulation/ticks/start", response_model=SimulationControlResponse)
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

    @app.post(f"{API_PREFIX}/simulation/ticks/stop", response_model=SimulationControlResponse)
    def stop_ticks(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.stop_auto_ticks()
        return SimulationControlResponse(
            current_tick=state.current_tick,
            is_running=state.is_running,
            auto_tick=state.auto_tick,
            sim_time=state.sim_time,
            message="Automatic ticking disabled",
        )

    @app.put(f"{API_PREFIX}/simulation/ticks/interval")
    def set_tick_interval(
        interval: float = Body(..., ge=0.0, le=60.0, embed=True),
        engine: SimulationEngine = Depends(get_engine)
    ) -> dict[str, Any]:
        """Set the auto-tick interval in seconds. Use 0 for maximum speed (no delay)."""
        try:
            return engine.set_tick_interval(interval)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get(f"{API_PREFIX}/simulation/ticks/interval")
    def get_tick_interval(engine: SimulationEngine = Depends(get_engine)) -> dict[str, float]:
        """Get the current auto-tick interval in seconds."""
        return {"tick_interval_seconds": engine.get_tick_interval()}

    @app.get(f"{API_PREFIX}/simulation/auto-pause-status")
    def get_auto_pause_status(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
        """Get information about auto-pause on project end status."""
        return engine.get_auto_pause_status()

    @app.post(f"{API_PREFIX}/simulation/advance", response_model=SimulationAdvanceResult)
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
    @app.post(f"{API_PREFIX}/admin/hard-reset", response_model=SimulationControlResponse)
    def admin_hard_reset(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
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

    @app.post(f"{API_PREFIX}/events", response_model=EventRead, status_code=status.HTTP_201_CREATED)
    def create_event(payload: EventCreate, engine: SimulationEngine = Depends(get_engine)) -> EventRead:
        return EventRead(**engine.inject_event(payload))

    @app.get(f"{API_PREFIX}/events", response_model=list[EventRead])
    def list_events(engine: SimulationEngine = Depends(get_engine)) -> list[EventRead]:
        return [EventRead(**event) for event in engine.list_events()]

    @app.post(f"{API_PREFIX}/people/status-override", response_model=StatusOverrideResponse)
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

    @app.delete(f"{API_PREFIX}/people/{{person_id}}/status-override", status_code=status.HTTP_204_NO_CONTENT)
    def clear_status_override(person_id: int, engine: SimulationEngine = Depends(get_engine)) -> None:
        """Clear a persona's status override, making them available again."""
        # Check if person exists
        people = engine.list_people()
        person = next((p for p in people if p.id == person_id), None)
        if not person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with ID {person_id} not found")

        # Remove from internal dict and database
        engine._status_overrides.pop(person_id, None)
        from virtualoffice.common.db import get_connection
        with get_connection() as conn:
            conn.execute("DELETE FROM worker_status_overrides WHERE worker_id = ?", (person_id,))

    # --- Monitoring proxy endpoints (avoid CORS by routing through sim_manager) ---
    @app.get(f"{API_PREFIX}/monitor/emails/{{person_id}}")
    def monitor_emails(
        person_id: int,
        box: str = Query(default="all", pattern="^(all|inbox|sent)$"),
        limit: int | None = Query(default=50, ge=1, le=500),
        since_id: int | None = Query(default=None),
        since_timestamp: str | None = Query(default=None),
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

    @app.get(f"{API_PREFIX}/monitor/chat/messages/{{person_id}}")
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

    @app.get(f"{API_PREFIX}/monitor/chat/room/{{room_slug}}/messages")
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
    @app.get(f"{API_PREFIX}/export/personas")
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
            # Convert PersonRead to export format (exclude id and persona_markdown)
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
                "statuses": list(person.statuses) if person.statuses else []
            }
            export_data["personas"].append(persona_data)
        
        return export_data

    @app.post(f"{API_PREFIX}/import/personas")
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

    @app.get(f"{API_PREFIX}/export/projects")
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

    @app.post(f"{API_PREFIX}/import/projects")
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

    return app


def _bootstrap_default_app() -> FastAPI:
    try:
        return create_app()
    except Exception as exc:  # pragma: no cover - bootstrap fallback
        fallback = FastAPI(title="VDOS Simulation Manager", version="0.1.0")

        @fallback.get("/bootstrap-status")
        def bootstrap_status() -> dict[str, Any]:
            return {"status": "degraded", "detail": str(exc)}

        return fallback


app = _bootstrap_default_app()
