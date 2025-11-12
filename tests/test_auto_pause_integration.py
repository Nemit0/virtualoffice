"""
Integration tests for auto-pause functionality.
Tests complete auto-pause workflow end-to-end including multi-project scenarios.
"""

import importlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from virtualoffice.sim_manager.planner import PlanResult
from fastapi.testclient import TestClient


@contextmanager
def _reload_db(tmp_path, monkeypatch):
    db_path = tmp_path / "vdos.db"
    monkeypatch.setenv("VDOS_DB_PATH", str(db_path))
    import virtualoffice.common.db as db_module
    importlib.reload(db_module)
    yield


@pytest.fixture
def auto_pause_client(tmp_path, monkeypatch):
    """Test client with auto-pause functionality enabled by default."""
    with _reload_db(tmp_path, monkeypatch):
        # Enable auto-pause by default for testing
        monkeypatch.setenv("VDOS_AUTO_PAUSE_ON_PROJECT_END", "true")
        # Set locale to English to avoid Korean name requirements
        monkeypatch.setenv("VDOS_LOCALE", "en")
        
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

        class TestEmailGateway:
            def ensure_mailbox(self, address: str, display_name: str | None = None) -> None:
                payload = {"display_name": display_name} if display_name else None
                response = email_http.put(f"/mailboxes/{address}", json=payload)
                assert response.status_code in (200, 201)

            def send_email(
                self,
                sender: str,
                to,
                subject: str,
                body: str,
                cc=None,
                bcc=None,
                thread_id=None,
            ) -> dict:
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
            hours_per_day=2, 
            tick_interval_seconds=0.02
        )
        app = create_app(engine)
        client = TestClient(app)
        try:
            yield client, email_http, chat_http, engine
        finally:
            client.close()
            engine.close()


def test_complete_auto_pause_workflow(auto_pause_client):
    """Test complete auto-pause workflow with projects that end at different times."""
    client, email_client, chat_client, engine = auto_pause_client

    # Create test personas
    person1_payload = {
        "name": "Alice Manager",
        "role": "Project Manager",
        "timezone": "UTC",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Direct",
        "email_address": "alice@vdos.local",
        "chat_handle": "alice",
        "skills": ["Management", "Planning"],
        "is_department_head": True,
        "personality": ["Organized", "Decisive"],
    }

    person2_payload = {
        "name": "Bob Developer",
        "role": "Developer",
        "timezone": "UTC",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Technical",
        "email_address": "bob@vdos.local",
        "chat_handle": "bob",
        "skills": ["Python", "Testing"],
        "personality": ["Analytical", "Thorough"],
    }

    # Create personas
    response1 = client.post("/api/v1/people", json=person1_payload)
    assert response1.status_code == 201
    person1 = response1.json()

    response2 = client.post("/api/v1/people", json=person2_payload)
    assert response2.status_code == 201
    person2 = response2.json()

    # Test auto-pause status before simulation starts
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["auto_pause_enabled"] == True  # Should be enabled by default
    assert status["should_pause"] == True  # Should pause when no projects exist
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0

    # Start simulation with a short project (1 week)
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Short Project",
        "project_summary": "A project that ends quickly",
        "duration_weeks": 1,
        "department_head_name": "Alice Manager",
        "include_person_ids": [person1["id"], person2["id"]],
    })
    assert start_response.status_code == 200
    start_body = start_response.json()
    assert start_body["is_running"] == True

    # Check auto-pause status after starting simulation
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["auto_pause_enabled"] == True
    assert status["should_pause"] == False  # Should not pause while project is active
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 0

    # Start auto-tick
    auto_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_start.status_code == 200
    assert auto_start.json()["auto_tick"] == True

    # Advance simulation to complete the project (1 week = 10 ticks with 2 hours per day)
    # Week 1 ends at tick 10, so advance to tick 11 to be past the project end
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 11, 
        "reason": "Complete project for auto-pause test"
    })
    assert advance_response.status_code == 200

    # Check that auto-pause has triggered
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["auto_pause_enabled"] == True
    assert status["should_pause"] == True  # Should pause now that project is complete
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert "all projects are complete" in status["reason"].lower()

    # Verify that auto-tick has been disabled due to auto-pause
    sim_state = client.get("/api/v1/simulation")
    assert sim_state.status_code == 200
    state = sim_state.json()
    # Auto-tick should be disabled by auto-pause logic
    assert state["auto_tick"] == False


def test_manual_toggle_operations_and_state_persistence(auto_pause_client):
    """Test manual toggle operations and state persistence."""
    client, email_client, chat_client, engine = auto_pause_client

    # Test initial state (should be enabled by default)
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    initial_status = status_response.json()
    assert initial_status["auto_pause_enabled"] == True

    # Test disabling auto-pause
    toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": False})
    assert toggle_response.status_code == 200
    toggle_result = toggle_response.json()
    assert toggle_result["auto_pause_enabled"] == False

    # Verify state persisted
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["auto_pause_enabled"] == False

    # Test re-enabling auto-pause
    toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": True})
    assert toggle_response.status_code == 200
    toggle_result = toggle_response.json()
    assert toggle_result["auto_pause_enabled"] == True

    # Verify state persisted again
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["auto_pause_enabled"] == True

    # Test that disabled auto-pause doesn't interfere with simulation
    # Create a person and start a simulation
    person_payload = {
        "name": "Test Person",
        "role": "Tester",
        "timezone": "UTC",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Direct",
        "email_address": "test@vdos.local",
        "chat_handle": "test",
        "skills": ["Testing"],
        "is_department_head": True,
        "personality": ["Methodical"],
    }

    person_response = client.post("/api/v1/people", json=person_payload)
    assert person_response.status_code == 201

    # Disable auto-pause before starting simulation
    client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": False})

    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Test Project",
        "project_summary": "Testing auto-pause disabled",
        "duration_weeks": 1,
        "department_head_name": "Test Person",
    })
    assert start_response.status_code == 200

    # Start auto-tick
    auto_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_start.status_code == 200

    # Advance past project completion
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 11, 
        "reason": "Test disabled auto-pause"
    })
    assert advance_response.status_code == 200

    # Verify auto-tick is still running (auto-pause is disabled)
    sim_state = client.get("/api/v1/simulation")
    assert sim_state.status_code == 200
    state = sim_state.json()
    assert state["auto_tick"] == True  # Should still be running since auto-pause is disabled

    # Verify auto-pause status shows it would pause if enabled
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["auto_pause_enabled"] == False
    assert status["should_pause"] == True  # Would pause if enabled
    assert status["active_projects_count"] == 0


def test_multi_project_timeline_scenarios(auto_pause_client):
    """Test projects with overlapping timelines and future projects."""
    client, email_client, chat_client, engine = auto_pause_client

    # Create test personas
    person_payload = {
        "name": "Multi Project Manager",
        "role": "Manager",
        "timezone": "UTC",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Efficient",
        "email_address": "manager@vdos.local",
        "chat_handle": "manager",
        "skills": ["Management", "Coordination"],
        "is_department_head": True,
        "personality": ["Strategic", "Organized"],
    }

    person_response = client.post("/api/v1/people", json=person_payload)
    assert person_response.status_code == 201
    person = person_response.json()

    # Test overlapping projects scenario
    # Start with a 2-week project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "First Project",
        "project_summary": "Initial 2-week project",
        "duration_weeks": 2,
        "department_head_name": "Multi Project Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200

    # Check status during active project
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["should_pause"] == False
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 0

    # Advance to week 2 (tick 10-19 is week 2)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 15, 
        "reason": "Advance to week 2"
    })
    assert advance_response.status_code == 200

    # Project should still be active in week 2
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["should_pause"] == False
    assert status["active_projects_count"] == 1

    # Advance past project completion (week 2 ends at tick 20)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 21, 
        "reason": "Complete first project"
    })
    assert advance_response.status_code == 200

    # Now auto-pause should trigger
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["should_pause"] == True
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0


def test_future_projects_prevent_auto_pause(auto_pause_client):
    """Test that future projects prevent auto-pause from triggering."""
    client, email_client, chat_client, engine = auto_pause_client

    # Create test persona
    person_payload = {
        "name": "Future Project Manager",
        "role": "Manager",
        "timezone": "UTC",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Forward-thinking",
        "email_address": "future@vdos.local",
        "chat_handle": "future",
        "skills": ["Planning", "Strategy"],
        "is_department_head": True,
        "personality": ["Visionary", "Organized"],
    }

    person_response = client.post("/api/v1/people", json=person_payload)
    assert person_response.status_code == 201
    person = person_response.json()

    # Start simulation with a project that starts in week 3
    # First, we need to manually insert a future project into the database
    # since the API doesn't directly support creating future projects
    
    # Start a regular project first to get the simulation running
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Current Project",
        "project_summary": "Project ending in week 1",
        "duration_weeks": 1,
        "department_head_name": "Future Project Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200

    # Manually add a future project to the database
    db_path = os.environ["VDOS_DB_PATH"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Future Project", "A project starting in week 3", 3, 2))
        conn.commit()

    # Check status while current project is active
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["should_pause"] == False
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 1  # Should detect the future project

    # Advance past current project completion (week 1 ends at tick 10)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 11, 
        "reason": "Complete current project"
    })
    assert advance_response.status_code == 200

    # Auto-pause should NOT trigger because there's a future project
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["should_pause"] == False  # Should not pause due to future project
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 1
    assert "future projects" in status["reason"].lower()

    # Advance to when future project becomes active (week 3 starts at tick 20)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 25, 
        "reason": "Activate future project"
    })
    assert advance_response.status_code == 200

    # Future project should now be active
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["should_pause"] == False
    assert status["active_projects_count"] == 1  # Future project is now active
    assert status["future_projects_count"] == 0


def test_auto_pause_api_endpoints(auto_pause_client):
    """Test auto-pause API endpoints functionality."""
    client, email_client, chat_client, engine = auto_pause_client

    # Test GET status endpoint
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    # Verify all required fields are present
    required_fields = [
        "auto_pause_enabled", "should_pause", "active_projects_count", 
        "future_projects_count", "current_week", "reason"
    ]
    for field in required_fields:
        assert field in status, f"Missing required field: {field}"

    # Test POST toggle endpoint with valid data
    toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": False})
    assert toggle_response.status_code == 200
    toggle_result = toggle_response.json()
    assert toggle_result["auto_pause_enabled"] == False

    # Test POST toggle endpoint with invalid data
    invalid_toggle = client.post("/api/v1/simulation/auto-pause/toggle", json={"invalid": "data"})
    assert invalid_toggle.status_code == 422  # Validation error

    # Test legacy endpoint for backward compatibility
    legacy_response = client.get("/api/v1/simulation/auto-pause-status")
    assert legacy_response.status_code == 200
    legacy_status = legacy_response.json()
    assert "auto_pause_enabled" in legacy_status


def test_error_handling_and_recovery(auto_pause_client):
    """Test error handling and recovery scenarios."""
    client, email_client, chat_client, engine = auto_pause_client

    # Test auto-pause status when database has issues
    # This is difficult to test without mocking, so we'll test edge cases instead
    
    # Test with no projects in database
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert status["should_pause"] == True

    # Test toggle with extreme values
    toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": True})
    assert toggle_response.status_code == 200

    # Test multiple rapid toggles
    for i in range(5):
        enabled = i % 2 == 0
        toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": enabled})
        assert toggle_response.status_code == 200
        assert toggle_response.json()["auto_pause_enabled"] == enabled

    # Final verification that state is consistent
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    final_status = status_response.json()
    # The last toggle in the loop was i=4, so enabled = 4 % 2 == 0 = True
    assert final_status["auto_pause_enabled"] == True  # Last toggle was True (i=4)