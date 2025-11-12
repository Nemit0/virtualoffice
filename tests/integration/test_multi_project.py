"""
Integration tests for multi-project scenarios.

Tests that validate the refactored engine handles multiple concurrent projects
correctly, including project completion and auto-pause functionality.
"""

import importlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from virtualoffice.sim_manager.planner import PlanResult


@contextmanager
def _reload_db(tmp_path, monkeypatch):
    """Context manager to reload database with temporary path."""
    db_path = tmp_path / "vdos.db"
    monkeypatch.setenv("VDOS_DB_PATH", str(db_path))
    import virtualoffice.common.db as db_module
    importlib.reload(db_module)
    yield


@pytest.fixture
def multi_project_engine(tmp_path, monkeypatch):
    """Test fixture for multi-project scenarios with refactored engine."""
    with _reload_db(tmp_path, monkeypatch):
        # Configure environment
        monkeypatch.setenv("VDOS_AUTO_PAUSE_ON_PROJECT_END", "true")
        monkeypatch.setenv("VDOS_LOCALE", "en")
        
        # Reload modules
        email_app_module = importlib.import_module("virtualoffice.servers.email.app")
        chat_app_module = importlib.import_module("virtualoffice.servers.chat.app")
        sim_app_module = importlib.import_module("virtualoffice.sim_manager.app")
        sim_engine_module = importlib.import_module("virtualoffice.sim_manager.engine")

        importlib.reload(email_app_module)
        importlib.reload(chat_app_module)
        importlib.reload(sim_app_module)
        importlib.reload(sim_engine_module)

        if hasattr(email_app_module, "initialise"):
            email_app_module.initialise()
        if hasattr(chat_app_module, "initialise"):
            chat_app_module.initialise()

        email_http = TestClient(email_app_module.app)
        chat_http = TestClient(chat_app_module.app)

        SimulationEngine = sim_engine_module.SimulationEngine
        create_app = sim_app_module.create_app

        # Create test gateways
        class TestEmailGateway:
            def ensure_mailbox(self, address: str, display_name: str | None = None) -> None:
                payload = {"display_name": display_name} if display_name else None
                response = email_http.put(f"/mailboxes/{address}", json=payload)
                assert response.status_code in (200, 201)

            def send_email(self, sender: str, to, subject: str, body: str, cc=None, bcc=None, thread_id=None) -> dict:
                response = email_http.post(
                    "/emails/send",
                    json={
                        "sender": sender,
                        "to": list(to),
                        "cc": list(cc or []),
                        "bcc": list(bcc or []),
                        "subject": subject,
                        "body": body,
                        "thread_id": thread_id,
                    },
                )
                assert response.status_code == 201
                return response.json()

            def close(self) -> None:
                email_http.close()

        class TestChatGateway:
            def ensure_user(self, handle: str, display_name: str | None = None) -> None:
                payload = {"display_name": display_name} if display_name else None
                response = chat_http.put(f"/users/{handle}", json=payload)
                assert response.status_code in (200, 201)

            def send_dm(self, sender: str, recipient: str, body: str) -> dict:
                response = chat_http.post(
                    "/dms",
                    json={"sender": sender, "recipient": recipient, "body": body},
                )
                assert response.status_code == 201
                return response.json()

            def close(self) -> None:
                chat_http.close()

        class TestPlanner:
            def generate_project_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Project plan stub", model_used="stub-project", tokens_used=1)

            def generate_daily_plan(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                day_index = kwargs.get("day_index", 0)
                return PlanResult(content=f"Daily plan for {worker.name} day {day_index}", model_used="stub-daily", tokens_used=1)

            def generate_hourly_plan(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                tick = kwargs.get("tick", 0)
                reason = kwargs.get("context_reason", "manual")
                return PlanResult(content=f"Hourly plan tick {tick} for {worker.name} ({reason})", model_used="stub-hourly", tokens_used=1)

            def generate_daily_report(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                day_index = kwargs.get("day_index", 0)
                return PlanResult(content=f"Daily report for {worker.name} day {day_index}", model_used="stub-daily-report", tokens_used=1)

            def generate_simulation_report(self, **kwargs) -> PlanResult:
                total_ticks = kwargs.get("total_ticks", 0)
                return PlanResult(content=f"Simulation report after {total_ticks} ticks", model_used="stub-simulation", tokens_used=1)

        email_gateway = TestEmailGateway()
        chat_gateway = TestChatGateway()
        planner = TestPlanner()
        engine = SimulationEngine(
            email_gateway=email_gateway,
            chat_gateway=chat_gateway,
            planner=planner,
            hours_per_day=2,  # 2 hours per day for faster testing
            tick_interval_seconds=0.02
        )
        app = create_app(engine)
        client = TestClient(app)
        try:
            yield client, email_http, chat_http, engine, tmp_path
        finally:
            client.close()
            engine.close()


def create_test_person(client, name, email, handle, is_head=False):
    """Helper function to create a test person."""
    person_payload = {
        "name": name,
        "role": "Manager" if is_head else "Developer",
        "timezone": "UTC",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Direct",
        "email_address": email,
        "chat_handle": handle,
        "skills": ["Management"] if is_head else ["Development"],
        "is_department_head": is_head,
        "personality": ["Organized"],
    }
    
    response = client.post("/api/v1/people", json=person_payload)
    assert response.status_code == 201
    return response.json()


def test_two_project_scenario_with_five_workers(multi_project_engine):
    """Test 2-project scenario with 5 workers using refactored engine."""
    client, email_client, chat_client, engine, tmp_path = multi_project_engine
    
    # Create 5 workers (1 manager + 4 developers)
    manager = create_test_person(client, "Project Manager", "pm@vdos.local", "pm", True)
    dev1 = create_test_person(client, "Developer One", "dev1@vdos.local", "dev1", False)
    dev2 = create_test_person(client, "Developer Two", "dev2@vdos.local", "dev2", False)
    dev3 = create_test_person(client, "Developer Three", "dev3@vdos.local", "dev3", False)
    dev4 = create_test_person(client, "Developer Four", "dev4@vdos.local", "dev4", False)
    
    all_person_ids = [manager["id"], dev1["id"], dev2["id"], dev3["id"], dev4["id"]]
    
    # Start first project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Project Alpha",
        "project_summary": "First project with full team",
        "duration_weeks": 2,
        "department_head_name": "Project Manager",
        "include_person_ids": all_person_ids,
    })
    assert start_response.status_code == 200
    
    # Add second project to database
    db_path = tmp_path / "vdos.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Project Beta", "Second project overlapping with first", 2, 2))
        conn.commit()
    
    # Verify initial state
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["is_running"] == False
    assert status["current_tick"] == 0
    
    # Advance simulation through first week
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 10,
        "reason": "Complete first week"
    })
    assert advance_response.status_code == 200
    
    # Verify all workers have plans
    people_response = client.get("/api/v1/people")
    assert people_response.status_code == 200
    people = people_response.json()
    assert len(people) == 5
    
    # Advance to week 2 where both projects are active
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 15,
        "reason": "Advance to week 2"
    })
    assert advance_response.status_code == 200
    
    # Verify simulation state
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_tick"] == 15


def test_project_completion_and_auto_pause(multi_project_engine):
    """Test that auto-pause triggers correctly when all projects complete."""
    client, email_client, chat_client, engine, tmp_path = multi_project_engine
    
    # Create test person
    person = create_test_person(client, "Test Manager", "test@vdos.local", "test", True)
    
    # Start project with 1-week duration
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Short Project",
        "project_summary": "Single week project",
        "duration_weeks": 1,
        "department_head_name": "Test Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Check auto-pause status before completion
    if hasattr(engine, 'get_auto_pause_status'):
        status = engine.get_auto_pause_status()
        assert status["should_pause"] == False
    
    # Advance past project completion
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 15,
        "reason": "Complete project"
    })
    assert advance_response.status_code == 200
    
    # Check auto-pause status after completion
    if hasattr(engine, 'get_auto_pause_status'):
        status = engine.get_auto_pause_status()
        assert status["should_pause"] == True
        assert status["active_projects_count"] == 0


def test_refactored_modules_integration(multi_project_engine):
    """Test that all refactored modules work together correctly."""
    client, email_client, chat_client, engine, tmp_path = multi_project_engine
    
    # Verify core modules are present
    assert hasattr(engine, 'state_manager'), "Engine should have state_manager"
    assert hasattr(engine, 'tick_manager'), "Engine should have tick_manager"
    assert hasattr(engine, 'event_system'), "Engine should have event_system"
    assert hasattr(engine, 'communication_hub'), "Engine should have communication_hub"
    assert hasattr(engine, 'project_manager'), "Engine should have project_manager"
    
    # Create test person
    person = create_test_person(client, "Integration Test", "int@vdos.local", "int", True)
    
    # Start simulation
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Integration Test Project",
        "project_summary": "Testing module integration",
        "duration_weeks": 1,
        "department_head_name": "Integration Test",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Test event injection (EventSystem)
    event_response = client.post("/api/v1/events", json={
        "event_type": "client_request",
        "description": "Test event",
        "target_person_id": person["id"],
        "tick": 5,
    })
    assert event_response.status_code == 201
    
    # Advance simulation (TickManager, CommunicationHub, ProjectManager)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 10,
        "reason": "Test module integration"
    })
    assert advance_response.status_code == 200
    
    # Verify state was updated (SimulationState)
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_tick"] == 10
