from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status

from .engine import SimulationEngine
from .gateways import HttpChatGateway, HttpEmailGateway
from .schemas import (
    EventCreate,
    EventRead,
    PersonCreate,
    PersonRead,
    SimulationAdvanceRequest,
    SimulationAdvanceResult,
    SimulationControlResponse,
    SimulationState,
)

API_PREFIX = "/api/v1"


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

    @app.get(f"{API_PREFIX}/simulation", response_model=SimulationState)
    def get_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationState:
        return engine.get_state()

    @app.post(f"{API_PREFIX}/simulation/start", response_model=SimulationControlResponse)
    def start_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.start()
        return SimulationControlResponse(current_tick=state.current_tick, is_running=state.is_running, message="Simulation started")

    @app.post(f"{API_PREFIX}/simulation/stop", response_model=SimulationControlResponse)
    def stop_simulation(engine: SimulationEngine = Depends(get_engine)) -> SimulationControlResponse:
        state = engine.stop()
        return SimulationControlResponse(current_tick=state.current_tick, is_running=state.is_running, message="Simulation stopped")

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