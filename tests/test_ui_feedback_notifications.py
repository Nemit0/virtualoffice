"""
Tests for UI feedback and notification system for auto-pause functionality.
Validates status display updates, notification appearance, and warning indicators.
"""

import importlib
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
def ui_test_client(tmp_path, monkeypatch):
    """Test client configured for UI feedback testing."""
    with _reload_db(tmp_path, monkeypatch):
        # Enable auto-pause by default
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
            yield client, email_http, chat_http, engine
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


def test_dashboard_html_contains_auto_pause_elements(ui_test_client):
    """Test that the dashboard HTML contains auto-pause UI elements."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Get the dashboard HTML
    response = client.get("/")
    assert response.status_code == 200
    html_content = response.text
    
    # Verify auto-pause toggle control is present
    assert "auto-pause-toggle" in html_content, "Auto-pause toggle control should be in dashboard HTML"
    
    # Verify auto-pause status display elements are present
    assert "auto-pause-status" in html_content, "Auto-pause status display should be in dashboard HTML"
    
    # Verify JavaScript functions for auto-pause are included
    assert "toggleAutoPause" in html_content, "toggleAutoPause function should be in dashboard HTML"
    assert "updateAutoPauseStatus" in html_content, "updateAutoPauseStatus function should be in dashboard HTML"
    
    # Verify CSS classes for auto-pause styling are present
    assert "auto-pause" in html_content, "Auto-pause CSS classes should be in dashboard HTML"


def test_status_display_updates_correctly(ui_test_client):
    """Test that status display updates correctly through API calls."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Create test person
    person = create_test_person(client, "Status Manager", "status@vdos.local", "status", True)
    
    # Test initial status (no projects)
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    # Verify initial status structure for UI consumption
    assert "auto_pause_enabled" in status
    assert "should_pause" in status
    assert "active_projects_count" in status
    assert "future_projects_count" in status
    assert "current_week" in status
    assert "reason" in status
    
    # Initial state should show auto-pause enabled and should pause (no projects)
    assert status["auto_pause_enabled"] == True
    assert status["should_pause"] == True
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert status["current_week"] == 1
    
    # Start a project and verify status updates
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Status Test Project",
        "project_summary": "Project for testing status updates",
        "duration_weeks": 2,
        "department_head_name": "Status Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Check status after starting project
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    # Status should now show active project and no auto-pause
    assert status["auto_pause_enabled"] == True
    assert status["should_pause"] == False
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 0
    assert "active projects" in status["reason"].lower()
    
    # Advance simulation past project completion
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 25, 
        "reason": "Complete project for status test"
    })
    assert advance_response.status_code == 200
    
    # Check status after project completion
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    # Status should now show auto-pause should trigger
    assert status["auto_pause_enabled"] == True
    assert status["should_pause"] == True
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert "all projects are complete" in status["reason"].lower()


def test_auto_pause_toggle_functionality(ui_test_client):
    """Test auto-pause toggle functionality and status feedback."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Test initial toggle state
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    initial_status = status_response.json()
    assert initial_status["auto_pause_enabled"] == True
    
    # Test disabling auto-pause
    toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": False})
    assert toggle_response.status_code == 200
    toggle_result = toggle_response.json()
    
    # Verify toggle response contains all necessary UI feedback data
    assert "auto_pause_enabled" in toggle_result
    assert "should_pause" in toggle_result
    assert "active_projects_count" in toggle_result
    assert "future_projects_count" in toggle_result
    assert "current_week" in toggle_result
    assert "reason" in toggle_result
    
    assert toggle_result["auto_pause_enabled"] == False
    
    # Test enabling auto-pause
    toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": True})
    assert toggle_response.status_code == 200
    toggle_result = toggle_response.json()
    assert toggle_result["auto_pause_enabled"] == True
    
    # Test invalid toggle request
    invalid_toggle = client.post("/api/v1/simulation/auto-pause/toggle", json={"invalid": "data"})
    assert invalid_toggle.status_code == 422  # Validation error for UI to handle


def test_warning_indicators_for_approaching_auto_pause(ui_test_client):
    """Test warning indicators when auto-pause conditions are approaching."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Create test person
    person = create_test_person(client, "Warning Manager", "warning@vdos.local", "warning", True)
    
    # Start a short project that will end soon
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Short Warning Project",
        "project_summary": "Project ending soon for warning test",
        "duration_weeks": 1,
        "department_head_name": "Warning Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Advance to near the end of the project (but not complete)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 8, 
        "reason": "Near end of project"
    })
    assert advance_response.status_code == 200
    
    # Check status - project should still be active but nearing completion
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    assert status["should_pause"] == False  # Not yet
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 0
    assert status["current_week"] == 1
    
    # The reason should indicate active projects (no warning yet)
    assert "active projects" in status["reason"].lower()
    
    # Advance to complete the project
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 12, 
        "reason": "Complete project"
    })
    assert advance_response.status_code == 200
    
    # Check status - should now show warning condition
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    assert status["should_pause"] == True
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert "all projects are complete" in status["reason"].lower()


def test_notification_content_and_structure(ui_test_client):
    """Test that notification content contains proper information for UI display."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Create test person
    person = create_test_person(client, "Notification Manager", "notify@vdos.local", "notify", True)
    
    # Test various scenarios and verify notification content
    scenarios = [
        {
            "name": "No projects",
            "setup": lambda: None,  # No setup needed
            "expected_should_pause": True,
            "expected_reason_contains": ["no active projects", "no future projects"],
        },
        {
            "name": "Active project",
            "setup": lambda: client.post("/api/v1/simulation/start", json={
                "project_name": "Active Notification Project",
                "project_summary": "Project for notification testing",
                "duration_weeks": 1,
                "department_head_name": "Notification Manager",
                "include_person_ids": [person["id"]],
            }),
            "expected_should_pause": False,
            "expected_reason_contains": ["active projects"],
        },
    ]
    
    for scenario in scenarios:
        # Reset simulation state
        reset_response = client.post("/api/v1/simulation/reset")
        if reset_response.status_code == 200:  # Reset endpoint exists
            pass
        
        # Run scenario setup
        if scenario["setup"]:
            setup_result = scenario["setup"]()
            if setup_result:
                assert setup_result.status_code == 200
        
        # Check notification content
        status_response = client.get("/api/v1/simulation/auto-pause/status")
        assert status_response.status_code == 200
        status = status_response.json()
        
        assert status["should_pause"] == scenario["expected_should_pause"], \
            f"Scenario '{scenario['name']}' should_pause mismatch"
        
        # Verify reason contains expected content for UI notifications
        reason_lower = status["reason"].lower()
        for expected_content in scenario["expected_reason_contains"]:
            assert expected_content in reason_lower, \
                f"Scenario '{scenario['name']}' reason should contain '{expected_content}', got: {status['reason']}"
        
        # Verify notification structure includes all UI-needed fields
        required_fields = [
            "auto_pause_enabled", "should_pause", "active_projects_count",
            "future_projects_count", "current_week", "reason"
        ]
        for field in required_fields:
            assert field in status, f"Scenario '{scenario['name']}' missing field: {field}"


def test_user_guidance_in_notifications(ui_test_client):
    """Test that notifications provide clear user guidance."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Create test person
    person = create_test_person(client, "Guidance Manager", "guidance@vdos.local", "guidance", True)
    
    # Test guidance when auto-pause is disabled
    toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": False})
    assert toggle_response.status_code == 200
    
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    assert status["auto_pause_enabled"] == False
    # When disabled, the reason should still indicate what would happen if enabled
    assert status["should_pause"] == True  # Would pause if enabled
    
    # Test guidance when projects exist but auto-pause is approaching
    toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": True})
    assert toggle_response.status_code == 200
    
    # Add a future project to test guidance about future projects
    db_path = os.environ["VDOS_DB_PATH"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Future Guidance Project", "Future project for guidance test", 3, 1))
        conn.commit()
    
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    assert status["should_pause"] == False
    assert status["future_projects_count"] == 1
    assert "future projects" in status["reason"].lower()
    
    # The reason should provide clear guidance about why auto-pause isn't triggering
    reason = status["reason"].lower()
    assert any(word in reason for word in ["future", "scheduled", "upcoming"]), \
        f"Reason should mention future projects: {status['reason']}"


def test_simulation_state_integration_with_auto_pause_status(ui_test_client):
    """Test that simulation state properly integrates auto-pause status information."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Create test person
    person = create_test_person(client, "Integration Manager", "integration@vdos.local", "integration", True)
    
    # Start a simulation
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Integration Test Project",
        "project_summary": "Project for integration testing",
        "duration_weeks": 1,
        "department_head_name": "Integration Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Get simulation state
    sim_state_response = client.get("/api/v1/simulation")
    assert sim_state_response.status_code == 200
    sim_state = sim_state_response.json()
    
    # Verify simulation state contains basic fields
    assert "current_tick" in sim_state
    assert "is_running" in sim_state
    assert "auto_tick" in sim_state
    assert "sim_time" in sim_state
    
    # Get auto-pause status
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    auto_pause_status = status_response.json()
    
    # Verify auto-pause status is comprehensive for UI integration
    assert auto_pause_status["should_pause"] == False  # Project is active
    assert auto_pause_status["active_projects_count"] == 1
    
    # Start auto-tick to test integration
    auto_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_start.status_code == 200
    
    # Advance past project completion
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 15, 
        "reason": "Test auto-pause integration"
    })
    assert advance_response.status_code == 200
    
    # Check that auto-pause status now indicates pause should occur
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    auto_pause_status = status_response.json()
    
    assert auto_pause_status["should_pause"] == True
    assert auto_pause_status["active_projects_count"] == 0
    
    # Verify simulation state reflects auto-pause effect
    sim_state_response = client.get("/api/v1/simulation")
    assert sim_state_response.status_code == 200
    sim_state = sim_state_response.json()
    
    # Auto-tick should be disabled due to auto-pause
    assert sim_state["auto_tick"] == False


def test_error_scenarios_for_ui_feedback(ui_test_client):
    """Test error scenarios and ensure proper UI feedback."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Test invalid toggle requests
    invalid_requests = [
        {},  # Empty request
        {"enabled": "invalid"},  # Wrong type
        {"wrong_field": True},  # Wrong field name
        {"enabled": None},  # Null value
    ]
    
    for invalid_request in invalid_requests:
        toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json=invalid_request)
        assert toggle_response.status_code == 422, \
            f"Invalid request should return 422: {invalid_request}"
        
        # Verify error response structure for UI handling
        error_data = toggle_response.json()
        assert "detail" in error_data, "Error response should contain detail for UI"
    
    # Test that status endpoint is robust
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    
    # Even with no projects, status should be complete and valid
    assert isinstance(status["auto_pause_enabled"], bool)
    assert isinstance(status["should_pause"], bool)
    assert isinstance(status["active_projects_count"], int)
    assert isinstance(status["future_projects_count"], int)
    assert isinstance(status["current_week"], int)
    assert isinstance(status["reason"], str)
    
    # Verify status is consistent even after errors
    assert status["active_projects_count"] >= 0
    assert status["future_projects_count"] >= 0
    assert status["current_week"] >= 1
    assert len(status["reason"]) > 0


def test_legacy_endpoint_compatibility(ui_test_client):
    """Test that legacy endpoints still work for backward compatibility."""
    client, email_client, chat_client, engine = ui_test_client
    
    # Test legacy auto-pause status endpoint
    legacy_response = client.get("/api/v1/simulation/auto-pause-status")
    assert legacy_response.status_code == 200
    legacy_status = legacy_response.json()
    
    # Verify legacy endpoint returns compatible data
    assert "auto_pause_enabled" in legacy_status
    assert isinstance(legacy_status["auto_pause_enabled"], bool)
    
    # Compare with new endpoint to ensure consistency
    new_response = client.get("/api/v1/simulation/auto-pause/status")
    assert new_response.status_code == 200
    new_status = new_response.json()
    
    # Key fields should match between legacy and new endpoints
    assert legacy_status["auto_pause_enabled"] == new_status["auto_pause_enabled"]