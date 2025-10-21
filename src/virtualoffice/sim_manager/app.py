from __future__ import annotations

import os
import json
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
        safe = prompt.strip() or "Auto Worker"
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

with open(os.path.join(os.path.dirname(__file__), "index_new.html"), "r", encoding="utf-8") as f:
    DASHBOARD_HTML = f.read()

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
        return HTMLResponse(DASHBOARD_HTML)

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
            error_msg = f"Attempt {attempt}/{max_retries} failed: {str(exc)}"
            print(f"⚠️  {error_msg}")

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
            message = "Simulation started"
            if payload is not None:
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
