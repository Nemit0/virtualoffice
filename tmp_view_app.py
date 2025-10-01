from __future__ import annotations

import os
import json
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

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


def _generate_persona_from_prompt(prompt: str, model_hint: str | None = None) -> dict[str, Any]:
    """Best-effort persona generator.

    - Uses OpenAI if configured; otherwise returns a sensible stub.
    - Ensures output matches PersonCreate-compatible shape used by the dashboard.
    """
    model = model_hint or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    system = (
        "You generate JSON personas for internal simulations. "
        "Respond ONLY with a single JSON object containing fields: "
        "name, role, timezone, work_hours, break_frequency, communication_style, "
        "email_address, chat_handle, is_department_head (boolean), skills (array), personality (array), "
        "objectives (array, optional), metrics (array, optional), planning_guidelines (array, optional), "
        "schedule (array of {start, end, activity})."
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
        # Minimal normalization
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

with open(os.path.join(os.path.dirname(__file__), "index.html"), "r", encoding="utf-8") as f:
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
    return SimulationEngine(
        email_gateway=email_gateway,
        chat_gateway=chat_gateway,
        sim_manager_email=sim_email,
        sim_manager_handle=sim_handle,
    )


def create_app(engine: SimulationEngine | None = None) -> FastAPI:
    app = FastAPI(title="VDOS Simulation Manager", version="0.1.0")
    app.state.engine = engine or _build_default_engine()

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
        persona = _generate_persona_from_prompt(payload.prompt, payload.model_hint)
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

    @app.post(f"{API_PREFIX}/simulation/start", response_model=SimulationControlResponse)
    def start_simulation(
        payload: SimulationStartRequest | None = Body(default=None),
        engine: SimulationEngine = Depends(get_engine),
    ) -> SimulationControlResponse:
        try:
            state = engine.start(payload)
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

    @app.post(f"{API_PREFIX}/events", response_model=EventRead, status_code=status.HTTP_201_CREATED)
    def create_event(payload: EventCreate, engine: SimulationEngine = Depends(get_engine)) -> EventRead:
        return EventRead(**engine.inject_event(payload))

    @app.get(f"{API_PREFIX}/events", response_model=list[EventRead])
    def list_events(engine: SimulationEngine = Depends(get_engine)) -> list[EventRead]:
        return [EventRead(**event) for event in engine.list_events()]

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

