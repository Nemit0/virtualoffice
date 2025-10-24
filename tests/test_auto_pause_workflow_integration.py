"""
Integration tests for complete auto-pause workflow.
Tests end-to-end auto-pause triggering, API integration with frontend controls,
and error handling and recovery scenarios.
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
def workflow_client(tmp_path, monkeypatch):
    """Test client configured for workflow integration testing."""
    with _reload_db(tmp_path, monkeypatch):
        # Enable auto-pause by default for workflow testing
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

        class WorkflowEmailGateway:
            def __init__(self):
                self.emails_sent = []

            def ensure_mailbox(self, address: str, display_name: str | None = None) -> None:
                payload = {"display_name": display_name} if display_name else None
                response = email_http.put(f"/mailboxes/{address}", json=payload)
                assert response.status_code in (200, 201)

            def send_email(self, sender: str, to, subject: str, body: str, cc=None, bcc=None, thread_id=None) -> dict:
                email_data = {
                    "sender": sender,
                    "to": list(to),
                    "cc": list(cc or []),
                    "bcc": list(bcc or []),
                    "subject": subject,
                    "body": body,
                    "thread_id": thread_id,
                }
                self.emails_sent.append(email_data)
                
                response = email_http.post("/emails/send", json=email_data)
                assert response.status_code == 201
                return response.json()

            def close(self) -> None:
                email_http.close()

        class WorkflowChatGateway:
            def __init__(self):
                self.messages_sent = []

            def ensure_user(self, handle: str, display_name: str | None = None) -> None:
                payload = {"display_name": display_name} if display_name else None
                response = chat_http.put(f"/users/{handle}", json=payload)
                assert response.status_code in (200, 201)

            def send_dm(self, sender: str, recipient: str, body: str) -> dict:
                message_data = {"sender": sender, "recipient": recipient, "body": body}
                self.messages_sent.append(message_data)
                
                response = chat_http.post("/dms", json=message_data)
                assert response.status_code == 201
                return response.json()

            def close(self) -> None:
                chat_http.close()

        class WorkflowPlanner:
            def __init__(self):
                self.plans_generated = []

            def generate_project_plan(self, **kwargs) -> PlanResult:
                plan = PlanResult(content="Workflow project plan", model_used="workflow-project", tokens_used=1)
                self.plans_generated.append(("project", kwargs))
                return plan

            def generate_daily_plan(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                day_index = kwargs.get("day_index", 0)
                plan = PlanResult(content=f"Workflow daily plan for {worker.name} day {day_index}", model_used="workflow-daily", tokens_used=1)
                self.plans_generated.append(("daily", kwargs))
                return plan

            def generate_hourly_plan(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                tick = kwargs.get("tick", 0)
                reason = kwargs.get("context_reason", "manual")
                plan = PlanResult(content=f"Workflow hourly plan tick {tick} for {worker.name} ({reason})", model_used="workflow-hourly", tokens_used=1)
                self.plans_generated.append(("hourly", kwargs))
                return plan

            def generate_daily_report(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                day_index = kwargs.get("day_index", 0)
                plan = PlanResult(content=f"Workflow daily report for {worker.name} day {day_index}", model_used="workflow-daily-report", tokens_used=1)
                self.plans_generated.append(("daily_report", kwargs))
                return plan

            def generate_simulation_report(self, **kwargs) -> PlanResult:
                total_ticks = kwargs.get("total_ticks", 0)
                plan = PlanResult(content=f"Workflow simulation report after {total_ticks} ticks", model_used="workflow-simulation", tokens_used=1)
                self.plans_generated.append(("simulation_report", kwargs))
                return plan

        email_gateway = WorkflowEmailGateway()
        chat_gateway = WorkflowChatGateway()
        planner = WorkflowPlanner()
        engine = SimulationEngine(
            email_gateway=email_gateway, 
            chat_gateway=chat_gateway, 
            planner=planner, 
            hours_per_day=2,  # 2 hours per day for faster testing
            tick_interval_seconds=0.01  # Very fast for integration tests
        )
        app = create_app(engine)
        client = TestClient(app)
        try:
            yield client, email_http, chat_http, engine, email_gateway, chat_gateway, planner
        finally:
            client.close()
            engine.close()


def create_workflow_person(client, name, email, handle, is_head=False):
    """Helper function to create a person for workflow testing."""
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


def test_end_to_end_auto_pause_triggering(workflow_client):
    """Test complete end-to-end auto-pause triggering workflow."""
    client, email_client, chat_client, engine, email_gateway, chat_gateway, planner = workflow_client
    
    # Create test personas
    manager = create_workflow_person(client, "Workflow Manager", "manager@vdos.local", "manager", True)
    developer = create_workflow_person(client, "Workflow Developer", "dev@vdos.local", "dev", False)
    
    # Verify initial auto-pause status
    initial_status = client.get("/api/v1/simulation/auto-pause/status")
    assert initial_status.status_code == 200
    status_data = initial_status.json()
    assert status_data["auto_pause_enabled"] == True
    assert status_data["should_pause"] == True  # No projects initially
    assert status_data["active_projects_count"] == 0
    assert status_data["future_projects_count"] == 0
    
    # Start simulation with a short project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "End-to-End Test Project",
        "project_summary": "Project for testing complete auto-pause workflow",
        "duration_weeks": 1,
        "department_head_name": "Workflow Manager",
        "include_person_ids": [manager["id"], developer["id"]],
    })
    assert start_response.status_code == 200
    start_data = start_response.json()
    assert start_data["is_running"] == True
    
    # Verify auto-pause status during active project
    active_status = client.get("/api/v1/simulation/auto-pause/status")
    assert active_status.status_code == 200
    status_data = active_status.json()
    assert status_data["should_pause"] == False  # Project is active
    assert status_data["active_projects_count"] == 1
    assert status_data["future_projects_count"] == 0
    
    # Start auto-tick to simulate real workflow
    auto_tick_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_tick_start.status_code == 200
    auto_tick_data = auto_tick_start.json()
    assert auto_tick_data["auto_tick"] == True
    
    # Advance simulation to complete the project
    # Week 1 with 2 hours per day = 10 ticks, so advance to tick 12 to be past completion
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 12, 
        "reason": "Complete project for end-to-end auto-pause test"
    })
    assert advance_response.status_code == 200
    advance_data = advance_response.json()
    
    # Verify that emails and chat messages were sent during simulation
    assert len(email_gateway.emails_sent) > 0, "Emails should have been sent during simulation"
    assert len(chat_gateway.messages_sent) > 0, "Chat messages should have been sent during simulation"
    assert len(planner.plans_generated) > 0, "Plans should have been generated during simulation"
    
    # Verify auto-pause has triggered
    final_status = client.get("/api/v1/simulation/auto-pause/status")
    assert final_status.status_code == 200
    status_data = final_status.json()
    assert status_data["should_pause"] == True  # Should pause now
    assert status_data["active_projects_count"] == 0
    assert status_data["future_projects_count"] == 0
    assert "all projects are complete" in status_data["reason"].lower()
    
    # Verify that auto-tick has been disabled by auto-pause
    sim_state = client.get("/api/v1/simulation")
    assert sim_state.status_code == 200
    state_data = sim_state.json()
    assert state_data["auto_tick"] == False  # Should be disabled by auto-pause
    
    # Verify simulation is still running but auto-tick is paused
    assert state_data["is_running"] == True
    assert state_data["current_tick"] >= 12


def test_api_integration_with_frontend_controls(workflow_client):
    """Test API integration with frontend controls workflow."""
    client, email_client, chat_client, engine, email_gateway, chat_gateway, planner = workflow_client
    
    # Test dashboard HTML contains auto-pause controls
    dashboard_response = client.get("/")
    assert dashboard_response.status_code == 200
    dashboard_html = dashboard_response.text
    
    # Verify auto-pause UI elements are present
    assert "auto-pause" in dashboard_html.lower(), "Dashboard should contain auto-pause UI elements"
    
    # Test complete frontend workflow simulation
    # 1. Check initial status
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    initial_status = status_response.json()
    
    # 2. Toggle auto-pause off (simulating frontend toggle)
    toggle_off_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": False})
    assert toggle_off_response.status_code == 200
    toggle_off_data = toggle_off_response.json()
    assert toggle_off_data["auto_pause_enabled"] == False
    
    # 3. Verify status reflects the change
    status_after_toggle = client.get("/api/v1/simulation/auto-pause/status")
    assert status_after_toggle.status_code == 200
    status_data = status_after_toggle.json()
    assert status_data["auto_pause_enabled"] == False
    
    # 4. Create and run a simulation with auto-pause disabled
    person = create_workflow_person(client, "Frontend Test Manager", "frontend@vdos.local", "frontend", True)
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Frontend Integration Project",
        "project_summary": "Testing frontend integration",
        "duration_weeks": 1,
        "department_head_name": "Frontend Test Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # 5. Start auto-tick
    auto_tick_response = client.post("/api/v1/simulation/ticks/start")
    assert auto_tick_response.status_code == 200
    
    # 6. Advance past project completion
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 12, 
        "reason": "Test frontend integration with auto-pause disabled"
    })
    assert advance_response.status_code == 200
    
    # 7. Verify auto-tick continues running (auto-pause is disabled)
    sim_state = client.get("/api/v1/simulation")
    assert sim_state.status_code == 200
    state_data = sim_state.json()
    assert state_data["auto_tick"] == True  # Should still be running
    
    # 8. Toggle auto-pause back on (simulating frontend re-enable)
    toggle_on_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": True})
    assert toggle_on_response.status_code == 200
    toggle_on_data = toggle_on_response.json()
    assert toggle_on_data["auto_pause_enabled"] == True
    assert toggle_on_data["should_pause"] == True  # Should indicate pause needed
    
    # 9. Verify status shows auto-pause would trigger
    final_status = client.get("/api/v1/simulation/auto-pause/status")
    assert final_status.status_code == 200
    final_data = final_status.json()
    assert final_data["auto_pause_enabled"] == True
    assert final_data["should_pause"] == True


def test_error_handling_and_recovery_scenarios(workflow_client):
    """Test error handling and recovery scenarios in auto-pause workflow."""
    client, email_client, chat_client, engine, email_gateway, chat_gateway, planner = workflow_client
    
    # Test 1: Invalid API requests and recovery
    invalid_requests = [
        {},  # Empty request
        {"enabled": "invalid"},  # Wrong type
        {"wrong_field": True},  # Wrong field
    ]
    
    for invalid_request in invalid_requests:
        error_response = client.post("/api/v1/simulation/auto-pause/toggle", json=invalid_request)
        assert error_response.status_code == 422, f"Should reject invalid request: {invalid_request}"
        
        # Verify system state remains consistent after error
        status_response = client.get("/api/v1/simulation/auto-pause/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert isinstance(status_data["auto_pause_enabled"], bool)
    
    # Test 2: Rapid toggle operations and state consistency
    for i in range(10):
        enabled = i % 2 == 0
        toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": enabled})
        assert toggle_response.status_code == 200
        
        # Verify state is immediately consistent
        status_response = client.get("/api/v1/simulation/auto-pause/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["auto_pause_enabled"] == enabled
    
    # Test 3: Auto-pause behavior during simulation errors
    person = create_workflow_person(client, "Error Test Manager", "error@vdos.local", "error", True)
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Error Recovery Project",
        "project_summary": "Testing error recovery",
        "duration_weeks": 1,
        "department_head_name": "Error Test Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Test auto-pause status during various simulation states
    status_during_sim = client.get("/api/v1/simulation/auto-pause/status")
    assert status_during_sim.status_code == 200
    
    # Test stopping simulation and auto-pause behavior
    stop_response = client.post("/api/v1/simulation/stop")
    assert stop_response.status_code == 200
    
    status_after_stop = client.get("/api/v1/simulation/auto-pause/status")
    assert status_after_stop.status_code == 200
    status_data = status_after_stop.json()
    # Auto-pause status should still be available even when simulation is stopped
    assert "auto_pause_enabled" in status_data
    
    # Test 4: Database consistency during errors
    # Simulate database issues by checking robustness
    db_path = os.environ["VDOS_DB_PATH"]
    
    # Add some test data and verify auto-pause handles it correctly
    with sqlite3.connect(db_path) as conn:
        # Add a project with unusual data to test robustness
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Edge Case Project", "Testing edge cases", 1, 1))
        conn.commit()
    
    status_with_edge_data = client.get("/api/v1/simulation/auto-pause/status")
    assert status_with_edge_data.status_code == 200
    edge_status = status_with_edge_data.json()
    assert edge_status["active_projects_count"] >= 0
    assert edge_status["future_projects_count"] >= 0
    
    # Test 5: Recovery after reset
    reset_response = client.post("/api/v1/simulation/reset")
    if reset_response.status_code == 200:  # Reset endpoint exists
        status_after_reset = client.get("/api/v1/simulation/auto-pause/status")
        assert status_after_reset.status_code == 200
        reset_status = status_after_reset.json()
        assert reset_status["current_week"] == 1
        assert reset_status["active_projects_count"] == 0


def test_complex_workflow_with_multiple_project_phases(workflow_client):
    """Test complex workflow with multiple project phases and auto-pause interactions."""
    client, email_client, chat_client, engine, email_gateway, chat_gateway, planner = workflow_client
    
    # Create multiple personas for complex workflow
    manager = create_workflow_person(client, "Complex Manager", "complex@vdos.local", "complex", True)
    dev1 = create_workflow_person(client, "Developer One", "dev1@vdos.local", "dev1", False)
    dev2 = create_workflow_person(client, "Developer Two", "dev2@vdos.local", "dev2", False)
    
    # Phase 1: Start initial project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Complex Workflow Phase 1",
        "project_summary": "First phase of complex workflow testing",
        "duration_weeks": 2,
        "department_head_name": "Complex Manager",
        "include_person_ids": [manager["id"], dev1["id"], dev2["id"]],
    })
    assert start_response.status_code == 200
    
    # Verify initial state
    status_phase1 = client.get("/api/v1/simulation/auto-pause/status")
    assert status_phase1.status_code == 200
    phase1_data = status_phase1.json()
    assert phase1_data["should_pause"] == False
    assert phase1_data["active_projects_count"] == 1
    
    # Phase 2: Add future projects to create complex timeline
    db_path = os.environ["VDOS_DB_PATH"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
        """, ("Complex Phase 2", "Second phase", 3, 2,
              "Complex Phase 3", "Final phase", 6, 1))
        conn.commit()
    
    # Verify complex timeline is detected
    status_with_future = client.get("/api/v1/simulation/auto-pause/status")
    assert status_with_future.status_code == 200
    future_data = status_with_future.json()
    assert future_data["should_pause"] == False
    assert future_data["active_projects_count"] == 1
    assert future_data["future_projects_count"] == 2
    
    # Phase 3: Run simulation through multiple project phases
    auto_tick_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_tick_start.status_code == 200
    
    # Advance through Phase 1 completion (2 weeks = 20 ticks)
    advance_phase1 = client.post("/api/v1/simulation/advance", json={
        "ticks": 22, 
        "reason": "Complete Phase 1"
    })
    assert advance_phase1.status_code == 200
    
    # Verify gap between Phase 1 and Phase 2
    status_gap = client.get("/api/v1/simulation/auto-pause/status")
    assert status_gap.status_code == 200
    gap_data = status_gap.json()
    assert gap_data["should_pause"] == False  # Future projects prevent pause
    assert gap_data["active_projects_count"] == 0
    assert gap_data["future_projects_count"] == 2
    
    # Advance to Phase 2 start (week 3 = tick 20+)
    advance_phase2 = client.post("/api/v1/simulation/advance", json={
        "ticks": 32, 
        "reason": "Start Phase 2"
    })
    assert advance_phase2.status_code == 200
    
    # Verify Phase 2 is active
    status_phase2 = client.get("/api/v1/simulation/auto-pause/status")
    assert status_phase2.status_code == 200
    phase2_data = status_phase2.json()
    assert phase2_data["should_pause"] == False
    assert phase2_data["active_projects_count"] == 1  # Phase 2
    assert phase2_data["future_projects_count"] == 1  # Phase 3
    
    # Phase 4: Test auto-pause toggle during active complex workflow
    toggle_during_active = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": False})
    assert toggle_during_active.status_code == 200
    
    # Advance to complete all phases
    advance_complete = client.post("/api/v1/simulation/advance", json={
        "ticks": 70, 
        "reason": "Complete all phases"
    })
    assert advance_complete.status_code == 200
    
    # Verify auto-pause is disabled so auto-tick continues
    sim_state_disabled = client.get("/api/v1/simulation")
    assert sim_state_disabled.status_code == 200
    disabled_state = sim_state_disabled.json()
    assert disabled_state["auto_tick"] == True  # Should continue running
    
    # Re-enable auto-pause
    toggle_enable = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": True})
    assert toggle_enable.status_code == 200
    
    # Verify final state shows all projects complete
    final_status = client.get("/api/v1/simulation/auto-pause/status")
    assert final_status.status_code == 200
    final_data = final_status.json()
    assert final_data["should_pause"] == True
    assert final_data["active_projects_count"] == 0
    assert final_data["future_projects_count"] == 0
    
    # Verify communication occurred throughout the workflow
    assert len(email_gateway.emails_sent) > 5, "Multiple emails should have been sent during complex workflow"
    assert len(chat_gateway.messages_sent) > 5, "Multiple chat messages should have been sent"
    assert len(planner.plans_generated) > 10, "Multiple plans should have been generated"


def test_auto_pause_workflow_with_simulation_events(workflow_client):
    """Test auto-pause workflow interaction with simulation events."""
    client, email_client, chat_client, engine, email_gateway, chat_gateway, planner = workflow_client
    
    # Create personas
    manager = create_workflow_person(client, "Event Manager", "event@vdos.local", "event", True)
    developer = create_workflow_person(client, "Event Developer", "eventdev@vdos.local", "eventdev", False)
    
    # Start simulation
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Event Workflow Project",
        "project_summary": "Testing auto-pause with events",
        "duration_weeks": 2,
        "department_head_name": "Event Manager",
        "include_person_ids": [manager["id"], developer["id"]],
    })
    assert start_response.status_code == 200
    
    # Inject an event during the simulation
    event_response = client.post("/api/v1/events", json={
        "type": "client_change",
        "target_ids": [manager["id"]],
        "project_id": "event-workflow",
        "at_tick": 5,
        "payload": {"change": "Update requirements for auto-pause testing"}
    })
    assert event_response.status_code == 201
    
    # Start auto-tick
    auto_tick_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_tick_start.status_code == 200
    
    # Advance through the event
    advance_through_event = client.post("/api/v1/simulation/advance", json={
        "ticks": 10, 
        "reason": "Process event during auto-pause workflow"
    })
    assert advance_through_event.status_code == 200
    
    # Verify auto-pause status is still correct during event processing
    status_during_event = client.get("/api/v1/simulation/auto-pause/status")
    assert status_during_event.status_code == 200
    event_status = status_during_event.json()
    assert event_status["should_pause"] == False  # Project still active
    assert event_status["active_projects_count"] == 1
    
    # Complete the project
    advance_complete = client.post("/api/v1/simulation/advance", json={
        "ticks": 25, 
        "reason": "Complete project after event"
    })
    assert advance_complete.status_code == 200
    
    # Verify auto-pause triggers correctly even after events
    final_status = client.get("/api/v1/simulation/auto-pause/status")
    assert final_status.status_code == 200
    final_data = final_status.json()
    assert final_data["should_pause"] == True
    assert final_data["active_projects_count"] == 0
    
    # Verify events were processed
    events_response = client.get("/api/v1/events")
    assert events_response.status_code == 200
    events_data = events_response.json()
    assert len(events_data) > 0
    
    # Verify auto-tick was disabled by auto-pause
    sim_state = client.get("/api/v1/simulation")
    assert sim_state.status_code == 200
    state_data = sim_state.json()
    assert state_data["auto_tick"] == False


def test_performance_and_consistency_under_load(workflow_client):
    """Test auto-pause performance and consistency under simulated load."""
    client, email_client, chat_client, engine, email_gateway, chat_gateway, planner = workflow_client
    
    # Create multiple personas for load testing
    personas = []
    for i in range(5):
        person = create_workflow_person(
            client, 
            f"Load Test Person {i+1}", 
            f"load{i+1}@vdos.local", 
            f"load{i+1}", 
            i == 0  # First person is department head
        )
        personas.append(person)
    
    # Start simulation with all personas
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Load Test Project",
        "project_summary": "Testing auto-pause under load",
        "duration_weeks": 1,
        "department_head_name": "Load Test Person 1",
        "include_person_ids": [p["id"] for p in personas],
    })
    assert start_response.status_code == 200
    
    # Perform rapid status checks to test consistency
    status_results = []
    for i in range(20):
        status_response = client.get("/api/v1/simulation/auto-pause/status")
        assert status_response.status_code == 200
        status_results.append(status_response.json())
    
    # Verify all status responses are consistent
    first_status = status_results[0]
    for status in status_results[1:]:
        assert status["auto_pause_enabled"] == first_status["auto_pause_enabled"]
        assert status["should_pause"] == first_status["should_pause"]
        assert status["active_projects_count"] == first_status["active_projects_count"]
    
    # Perform rapid toggle operations
    for i in range(10):
        enabled = i % 2 == 0
        toggle_response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": enabled})
        assert toggle_response.status_code == 200
        
        # Immediately check status for consistency
        status_response = client.get("/api/v1/simulation/auto-pause/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["auto_pause_enabled"] == enabled
    
    # Run simulation with auto-tick and verify performance
    auto_tick_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_tick_start.status_code == 200
    
    # Advance simulation while checking status periodically
    for tick_batch in range(1, 6):
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": tick_batch * 3, 
            "reason": f"Load test batch {tick_batch}"
        })
        assert advance_response.status_code == 200
        
        # Check status after each batch
        status_response = client.get("/api/v1/simulation/auto-pause/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        
        # Verify status is reasonable
        assert isinstance(status_data["current_week"], int)
        assert status_data["current_week"] >= 1
        assert status_data["active_projects_count"] >= 0
    
    # Complete project and verify final auto-pause
    advance_final = client.post("/api/v1/simulation/advance", json={
        "ticks": 15, 
        "reason": "Complete load test project"
    })
    assert advance_final.status_code == 200
    
    final_status = client.get("/api/v1/simulation/auto-pause/status")
    assert final_status.status_code == 200
    final_data = final_status.json()
    assert final_data["should_pause"] == True
    assert final_data["active_projects_count"] == 0
    
    # Verify significant activity occurred during load test
    assert len(email_gateway.emails_sent) > 10, "Load test should generate significant email activity"
    assert len(chat_gateway.messages_sent) > 10, "Load test should generate significant chat activity"
    assert len(planner.plans_generated) > 20, "Load test should generate significant planning activity"