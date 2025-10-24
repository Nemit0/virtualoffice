"""
Unit tests for auto-pause functionality.
Tests SimulationEngine.set_auto_pause method, API endpoint handling, and core logic.
"""

import importlib
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

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
def unit_test_client(tmp_path, monkeypatch):
    """Test client for unit testing auto-pause functionality."""
    with _reload_db(tmp_path, monkeypatch):
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

        class MockEmailGateway:
            def ensure_mailbox(self, address: str, display_name: str | None = None) -> None:
                pass

            def send_email(self, sender: str, to, subject: str, body: str, cc=None, bcc=None, thread_id=None) -> dict:
                return {"id": "mock-email-id", "status": "sent"}

            def close(self) -> None:
                pass

        class MockChatGateway:
            def ensure_user(self, handle: str, display_name: str | None = None) -> None:
                pass

            def send_dm(self, sender: str, recipient: str, body: str) -> dict:
                return {"id": "mock-dm-id", "status": "sent"}

            def close(self) -> None:
                pass

        class MockPlanner:
            def generate_project_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Mock project plan", model_used="mock-project", tokens_used=1)

            def generate_daily_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Mock daily plan", model_used="mock-daily", tokens_used=1)

            def generate_hourly_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Mock hourly plan", model_used="mock-hourly", tokens_used=1)

            def generate_daily_report(self, **kwargs) -> PlanResult:
                return PlanResult(content="Mock daily report", model_used="mock-daily-report", tokens_used=1)

            def generate_simulation_report(self, **kwargs) -> PlanResult:
                return PlanResult(content="Mock simulation report", model_used="mock-simulation", tokens_used=1)

        email_gateway = MockEmailGateway()
        chat_gateway = MockChatGateway()
        planner = MockPlanner()
        engine = SimulationEngine(
            email_gateway=email_gateway, 
            chat_gateway=chat_gateway, 
            planner=planner, 
            hours_per_day=9,  # Standard 9-hour workday
            tick_interval_seconds=0.01  # Fast for unit tests
        )
        app = create_app(engine)
        client = TestClient(app)
        try:
            yield client, engine
        finally:
            client.close()
            engine.close()


def test_simulation_engine_set_auto_pause_method(unit_test_client):
    """Test SimulationEngine.set_auto_pause method functionality."""
    client, engine = unit_test_client
    
    # Test enabling auto-pause
    result = engine.set_auto_pause(True)
    
    # Verify return structure
    assert isinstance(result, dict)
    required_fields = [
        "auto_pause_enabled", "should_pause", "active_projects_count",
        "future_projects_count", "current_week", "reason"
    ]
    for field in required_fields:
        assert field in result, f"set_auto_pause result missing field: {field}"
    
    assert result["auto_pause_enabled"] == True
    
    # Test disabling auto-pause
    result = engine.set_auto_pause(False)
    assert result["auto_pause_enabled"] == False
    
    # Test that setting persists
    status = engine.get_auto_pause_status()
    assert status["auto_pause_enabled"] == False
    
    # Test re-enabling
    result = engine.set_auto_pause(True)
    assert result["auto_pause_enabled"] == True
    
    status = engine.get_auto_pause_status()
    assert status["auto_pause_enabled"] == True


def test_simulation_engine_get_auto_pause_status_method(unit_test_client):
    """Test SimulationEngine.get_auto_pause_status method functionality."""
    client, engine = unit_test_client
    
    # Test basic status retrieval
    status = engine.get_auto_pause_status()
    
    # Verify return structure
    assert isinstance(status, dict)
    required_fields = [
        "auto_pause_enabled", "should_pause", "active_projects_count",
        "future_projects_count", "current_week", "reason"
    ]
    for field in required_fields:
        assert field in status, f"get_auto_pause_status result missing field: {field}"
    
    # Verify data types
    assert isinstance(status["auto_pause_enabled"], bool)
    assert isinstance(status["should_pause"], bool)
    assert isinstance(status["active_projects_count"], int)
    assert isinstance(status["future_projects_count"], int)
    assert isinstance(status["current_week"], int)
    assert isinstance(status["reason"], str)
    
    # Verify reasonable values
    assert status["active_projects_count"] >= 0
    assert status["future_projects_count"] >= 0
    assert status["current_week"] >= 1
    assert len(status["reason"]) > 0


def test_auto_pause_logic_with_no_projects(unit_test_client):
    """Test auto-pause logic when no projects exist."""
    client, engine = unit_test_client
    
    # With no projects, auto-pause should trigger
    status = engine.get_auto_pause_status()
    
    assert status["should_pause"] == True
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert "no active projects" in status["reason"].lower()


def test_auto_pause_logic_with_active_projects(unit_test_client):
    """Test auto-pause logic when active projects exist."""
    client, engine = unit_test_client
    
    # Add an active project to the database
    db_path = os.environ["VDOS_DB_PATH"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Test Project", "Active project", 1, 2))
        conn.commit()
    
    # With active project, auto-pause should not trigger
    status = engine.get_auto_pause_status()
    
    assert status["should_pause"] == False
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 0
    assert "active projects" in status["reason"].lower()


def test_auto_pause_logic_with_future_projects(unit_test_client):
    """Test auto-pause logic when future projects exist."""
    client, engine = unit_test_client
    
    # Add a future project to the database
    db_path = os.environ["VDOS_DB_PATH"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Future Project", "Future project", 5, 1))
        conn.commit()
    
    # With future project, auto-pause should not trigger
    status = engine.get_auto_pause_status()
    
    assert status["should_pause"] == False
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 1
    assert "future projects" in status["reason"].lower()


def test_current_week_calculation(unit_test_client):
    """Test current week calculation from simulation ticks."""
    client, engine = unit_test_client
    
    # Test various tick values and expected weeks
    test_cases = [
        (0, 1),    # Tick 0 should be week 1
        (1, 1),    # Tick 1 should be week 1
        (9, 1),    # Tick 9 (end of day 1) should be week 1
        (45, 1),   # Tick 45 (end of week 1) should be week 1
        (46, 2),   # Tick 46 (start of week 2) should be week 2
        (90, 2),   # Tick 90 (end of week 2) should be week 2
        (450, 10), # Tick 450 should be week 10
    ]
    
    for tick, expected_week in test_cases:
        # Set the engine's current tick
        engine.current_tick = tick
        
        status = engine.get_auto_pause_status()
        assert status["current_week"] == expected_week, \
            f"Tick {tick} should be week {expected_week}, got {status['current_week']}"


def test_project_end_date_calculation_logic(unit_test_client):
    """Test project end date calculation logic (start_week + duration_weeks - 1)."""
    client, engine = unit_test_client
    
    # Test various project configurations
    test_projects = [
        # (start_week, duration_weeks, expected_end_week)
        (1, 1, 1),   # Single week project
        (1, 4, 4),   # Multi-week project from start
        (3, 2, 4),   # Project starting later
        (5, 3, 7),   # Long project starting later
    ]
    
    db_path = os.environ["VDOS_DB_PATH"]
    
    for i, (start_week, duration_weeks, expected_end_week) in enumerate(test_projects):
        # Clear previous projects
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM projects")
            conn.execute("""
                INSERT INTO projects (name, description, start_week, duration_weeks)
                VALUES (?, ?, ?, ?)
            """, (f"Test Project {i+1}", f"Project {i+1}", start_week, duration_weeks))
            conn.commit()
        
        # Test that project is active during its expected timeline
        for test_week in range(start_week, expected_end_week + 1):
            # Set engine to the test week
            engine.current_tick = (test_week - 1) * 45 + 1  # Middle of the week
            
            status = engine.get_auto_pause_status()
            assert status["current_week"] == test_week
            assert status["active_projects_count"] == 1, \
                f"Project {i+1} should be active in week {test_week}"
        
        # Test that project is not active after its end week
        test_week = expected_end_week + 1
        engine.current_tick = (test_week - 1) * 45 + 1
        
        status = engine.get_auto_pause_status()
        assert status["current_week"] == test_week
        assert status["active_projects_count"] == 0, \
            f"Project {i+1} should not be active in week {test_week}"


def test_auto_pause_environment_variable_handling(unit_test_client):
    """Test auto-pause environment variable handling."""
    client, engine = unit_test_client
    
    # Test default behavior (should be enabled)
    status = engine.get_auto_pause_status()
    # Note: Default behavior depends on environment setup in fixture
    
    # Test setting via set_auto_pause method
    engine.set_auto_pause(True)
    status = engine.get_auto_pause_status()
    assert status["auto_pause_enabled"] == True
    
    engine.set_auto_pause(False)
    status = engine.get_auto_pause_status()
    assert status["auto_pause_enabled"] == False


def test_auto_pause_api_endpoint_request_validation(unit_test_client):
    """Test API endpoint request validation."""
    client, engine = unit_test_client
    
    # Test valid requests
    valid_requests = [
        {"enabled": True},
        {"enabled": False},
    ]
    
    for request_data in valid_requests:
        response = client.post("/api/v1/simulation/auto-pause/toggle", json=request_data)
        assert response.status_code == 200
        result = response.json()
        assert result["auto_pause_enabled"] == request_data["enabled"]
    
    # Test invalid requests
    invalid_requests = [
        {},  # Missing enabled field
        {"enabled": "true"},  # String instead of boolean
        {"enabled": 1},  # Integer instead of boolean
        {"wrong_field": True},  # Wrong field name
        {"enabled": None},  # Null value
    ]
    
    for request_data in invalid_requests:
        response = client.post("/api/v1/simulation/auto-pause/toggle", json=request_data)
        assert response.status_code == 422, f"Should reject invalid request: {request_data}"


def test_auto_pause_api_endpoint_response_structure(unit_test_client):
    """Test API endpoint response structure."""
    client, engine = unit_test_client
    
    # Test GET status endpoint
    response = client.get("/api/v1/simulation/auto-pause/status")
    assert response.status_code == 200
    
    data = response.json()
    required_fields = [
        "auto_pause_enabled", "should_pause", "active_projects_count",
        "future_projects_count", "current_week", "reason"
    ]
    
    for field in required_fields:
        assert field in data, f"Response missing required field: {field}"
    
    # Verify data types
    assert isinstance(data["auto_pause_enabled"], bool)
    assert isinstance(data["should_pause"], bool)
    assert isinstance(data["active_projects_count"], int)
    assert isinstance(data["future_projects_count"], int)
    assert isinstance(data["current_week"], int)
    assert isinstance(data["reason"], str)
    
    # Test POST toggle endpoint
    response = client.post("/api/v1/simulation/auto-pause/toggle", json={"enabled": True})
    assert response.status_code == 200
    
    data = response.json()
    for field in required_fields:
        assert field in data, f"Toggle response missing required field: {field}"


def test_auto_pause_status_reason_messages(unit_test_client):
    """Test auto-pause status reason messages for different scenarios."""
    client, engine = unit_test_client
    
    db_path = os.environ["VDOS_DB_PATH"]
    
    # Test scenario 1: No projects
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM projects")
        conn.commit()
    
    status = engine.get_auto_pause_status()
    assert status["should_pause"] == True
    reason = status["reason"].lower()
    assert "no active projects" in reason
    assert "no future projects" in reason
    
    # Test scenario 2: Active projects
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM projects")
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Active Project", "Currently active", 1, 2))
        conn.commit()
    
    status = engine.get_auto_pause_status()
    assert status["should_pause"] == False
    reason = status["reason"].lower()
    assert "active projects" in reason
    
    # Test scenario 3: Future projects only
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM projects")
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Future Project", "Starting later", 5, 1))
        conn.commit()
    
    status = engine.get_auto_pause_status()
    assert status["should_pause"] == False
    reason = status["reason"].lower()
    assert "future projects" in reason
    
    # Test scenario 4: Mixed active and future projects
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM projects")
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
        """, ("Active Project", "Currently active", 1, 2,
              "Future Project", "Starting later", 5, 1))
        conn.commit()
    
    status = engine.get_auto_pause_status()
    assert status["should_pause"] == False
    reason = status["reason"].lower()
    assert "active projects" in reason


def test_auto_pause_disabled_behavior(unit_test_client):
    """Test behavior when auto-pause is disabled."""
    client, engine = unit_test_client
    
    # Disable auto-pause
    engine.set_auto_pause(False)
    
    # Even with no projects, should_pause should reflect what would happen if enabled
    status = engine.get_auto_pause_status()
    assert status["auto_pause_enabled"] == False
    assert status["should_pause"] == True  # Would pause if enabled
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    
    # Add a project and verify behavior
    db_path = os.environ["VDOS_DB_PATH"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Test Project", "Test project", 1, 1))
        conn.commit()
    
    status = engine.get_auto_pause_status()
    assert status["auto_pause_enabled"] == False
    assert status["should_pause"] == False  # Would not pause due to active project
    assert status["active_projects_count"] == 1


def test_auto_pause_edge_cases(unit_test_client):
    """Test auto-pause edge cases and boundary conditions."""
    client, engine = unit_test_client
    
    # Test with tick 0
    engine.current_tick = 0
    status = engine.get_auto_pause_status()
    assert status["current_week"] == 1
    
    # Test with very high tick values
    engine.current_tick = 10000
    status = engine.get_auto_pause_status()
    assert status["current_week"] > 1
    assert isinstance(status["current_week"], int)
    
    # Test rapid toggle operations
    for i in range(10):
        enabled = i % 2 == 0
        result = engine.set_auto_pause(enabled)
        assert result["auto_pause_enabled"] == enabled
    
    # Test with projects that have edge case timelines
    db_path = os.environ["VDOS_DB_PATH"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM projects")
        # Project that starts and ends in week 1
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Edge Project", "Single week project", 1, 1))
        conn.commit()
    
    # Test at exact boundaries
    engine.current_tick = 1  # Start of week 1
    status = engine.get_auto_pause_status()
    assert status["active_projects_count"] == 1
    
    engine.current_tick = 45  # End of week 1
    status = engine.get_auto_pause_status()
    assert status["active_projects_count"] == 1
    
    engine.current_tick = 46  # Start of week 2
    status = engine.get_auto_pause_status()
    assert status["active_projects_count"] == 0


def test_auto_pause_error_handling(unit_test_client):
    """Test auto-pause error handling scenarios."""
    client, engine = unit_test_client
    
    # Test with corrupted database state (this is hard to simulate, so we test robustness)
    status = engine.get_auto_pause_status()
    
    # Should always return valid structure even in error conditions
    assert isinstance(status, dict)
    assert "auto_pause_enabled" in status
    assert "should_pause" in status
    assert "reason" in status
    
    # Test set_auto_pause with various inputs
    valid_inputs = [True, False]
    for input_val in valid_inputs:
        result = engine.set_auto_pause(input_val)
        assert isinstance(result, dict)
        assert result["auto_pause_enabled"] == input_val
    
    # Test that methods are idempotent
    engine.set_auto_pause(True)
    status1 = engine.get_auto_pause_status()
    engine.set_auto_pause(True)  # Set again
    status2 = engine.get_auto_pause_status()
    
    assert status1["auto_pause_enabled"] == status2["auto_pause_enabled"]


def test_legacy_endpoint_compatibility(unit_test_client):
    """Test legacy endpoint compatibility."""
    client, engine = unit_test_client
    
    # Test legacy endpoint exists and works
    response = client.get("/api/v1/simulation/auto-pause-status")
    assert response.status_code == 200
    
    legacy_data = response.json()
    assert "auto_pause_enabled" in legacy_data
    
    # Compare with new endpoint
    new_response = client.get("/api/v1/simulation/auto-pause/status")
    assert new_response.status_code == 200
    new_data = new_response.json()
    
    # Key compatibility fields should match
    assert legacy_data["auto_pause_enabled"] == new_data["auto_pause_enabled"]