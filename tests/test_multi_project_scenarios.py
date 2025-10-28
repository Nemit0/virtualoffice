"""
Tests for multi-project timeline scenarios and auto-pause behavior.
Validates overlapping timelines, future projects, and complex project schedules.
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
def multi_project_client(tmp_path, monkeypatch):
    """Test client configured for multi-project scenarios."""
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


def add_project_to_db(db_path, name, description, start_week, duration_weeks):
    """Helper function to add a project directly to the database."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, (name, description, start_week, duration_weeks))
        conn.commit()


def test_overlapping_project_timelines(multi_project_client):
    """Test projects with overlapping timelines."""
    client, email_client, chat_client, engine = multi_project_client
    
    # Create test person
    person = create_test_person(client, "Overlap Manager", "overlap@vdos.local", "overlap", True)
    
    # Start initial project (weeks 1-2)
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Project Alpha",
        "project_summary": "First project running weeks 1-2",
        "duration_weeks": 2,
        "department_head_name": "Overlap Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Add overlapping projects directly to database
    db_path = os.environ["VDOS_DB_PATH"]
    add_project_to_db(db_path, "Project Beta", "Second project weeks 2-4", 2, 3)
    add_project_to_db(db_path, "Project Gamma", "Third project weeks 3-4", 3, 2)
    
    # Test week 1: Only Project Alpha should be active
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 1
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 2
    assert status["should_pause"] == False
    
    # Advance to week 2 (tick 10-19)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 15, 
        "reason": "Advance to week 2"
    })
    assert advance_response.status_code == 200
    
    # Test week 2: Projects Alpha and Beta should be active
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 2
    assert status["active_projects_count"] == 2  # Alpha and Beta
    assert status["future_projects_count"] == 1  # Gamma
    assert status["should_pause"] == False
    
    # Advance to week 3 (tick 20-29)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 25, 
        "reason": "Advance to week 3"
    })
    assert advance_response.status_code == 200
    
    # Test week 3: Projects Beta and Gamma should be active (Alpha completed)
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 3
    assert status["active_projects_count"] == 2  # Beta and Gamma
    assert status["future_projects_count"] == 0
    assert status["should_pause"] == False
    
    # Advance to week 5 (past all projects)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 45, 
        "reason": "Advance past all projects"
    })
    assert advance_response.status_code == 200
    
    # Test week 5: All projects should be complete, auto-pause should trigger
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 5
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert status["should_pause"] == True


def test_projects_starting_in_future_weeks(multi_project_client):
    """Test projects that start in future weeks."""
    client, email_client, chat_client, engine = multi_project_client
    
    # Create test person
    person = create_test_person(client, "Future Manager", "future@vdos.local", "future", True)
    
    # Start initial project (week 1 only)
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Immediate Project",
        "project_summary": "Project that ends quickly",
        "duration_weeks": 1,
        "department_head_name": "Future Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Add future projects
    db_path = os.environ["VDOS_DB_PATH"]
    add_project_to_db(db_path, "Future Project A", "Starts in week 3", 3, 2)
    add_project_to_db(db_path, "Future Project B", "Starts in week 5", 5, 1)
    
    # Test week 1: Immediate project active, two future projects
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 1
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 2
    assert status["should_pause"] == False
    
    # Advance to week 2 (immediate project completed)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 15, 
        "reason": "Complete immediate project"
    })
    assert advance_response.status_code == 200
    
    # Test week 2: No active projects, but future projects prevent auto-pause
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 2
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 2
    assert status["should_pause"] == False
    assert "future projects" in status["reason"].lower()
    
    # Advance to week 3 (Future Project A starts)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 25, 
        "reason": "Start Future Project A"
    })
    assert advance_response.status_code == 200
    
    # Test week 3: Future Project A active, Future Project B still future
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 3
    assert status["active_projects_count"] == 1  # Future Project A
    assert status["future_projects_count"] == 1  # Future Project B
    assert status["should_pause"] == False
    
    # Advance to week 6 (all projects completed)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 55, 
        "reason": "Complete all projects"
    })
    assert advance_response.status_code == 200
    
    # Test week 6: All projects complete, auto-pause should trigger
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 6
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert status["should_pause"] == True


def test_complex_project_schedules(multi_project_client):
    """Test complex project schedules with gaps and overlaps."""
    client, email_client, chat_client, engine = multi_project_client
    
    # Create test person
    person = create_test_person(client, "Complex Manager", "complex@vdos.local", "complex", True)
    
    # Start initial project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Foundation",
        "project_summary": "Foundation project weeks 1-2",
        "duration_weeks": 2,
        "department_head_name": "Complex Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Add complex project schedule
    db_path = os.environ["VDOS_DB_PATH"]
    add_project_to_db(db_path, "Development A", "Weeks 2-4", 2, 3)
    add_project_to_db(db_path, "Development B", "Weeks 3-4", 3, 2)
    add_project_to_db(db_path, "Testing", "Weeks 4-5", 4, 2)
    add_project_to_db(db_path, "Deployment", "Week 7", 7, 1)  # Gap between testing and deployment
    
    # Test various weeks to ensure auto-pause behavior is correct
    test_scenarios = [
        # (target_tick, expected_week, expected_active, expected_future, should_pause)
        (5, 1, 1, 4, False),    # Week 1: Foundation active
        (15, 2, 2, 3, False),   # Week 2: Foundation + Development A
        (25, 3, 3, 2, False),   # Week 3: Foundation + Dev A + Dev B
        (35, 4, 3, 1, False),   # Week 4: Dev A + Dev B + Testing
        (45, 5, 1, 1, False),   # Week 5: Testing only
        (55, 6, 0, 1, False),   # Week 6: Gap, but Deployment is future
        (65, 7, 1, 0, False),   # Week 7: Deployment active
        (75, 8, 0, 0, True),    # Week 8: All complete, should pause
    ]
    
    for target_tick, expected_week, expected_active, expected_future, should_pause in test_scenarios:
        # Advance to target tick
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": target_tick, 
            "reason": f"Test week {expected_week}"
        })
        assert advance_response.status_code == 200
        
        # Check auto-pause status
        status_response = client.get("/api/v1/simulation/auto-pause/status")
        assert status_response.status_code == 200
        status = status_response.json()
        
        assert status["current_week"] == expected_week, \
            f"Week mismatch at tick {target_tick}: expected {expected_week}, got {status['current_week']}"
        assert status["active_projects_count"] == expected_active, \
            f"Active projects mismatch at week {expected_week}: expected {expected_active}, got {status['active_projects_count']}"
        assert status["future_projects_count"] == expected_future, \
            f"Future projects mismatch at week {expected_week}: expected {expected_future}, got {status['future_projects_count']}"
        assert status["should_pause"] == should_pause, \
            f"Auto-pause mismatch at week {expected_week}: expected {should_pause}, got {status['should_pause']}"


def test_single_week_projects(multi_project_client):
    """Test handling of single-week projects."""
    client, email_client, chat_client, engine = multi_project_client
    
    # Create test person
    person = create_test_person(client, "Sprint Manager", "sprint@vdos.local", "sprint", True)
    
    # Start with single-week project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Sprint 1",
        "project_summary": "Single week sprint",
        "duration_weeks": 1,
        "department_head_name": "Sprint Manager",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Add more single-week projects
    db_path = os.environ["VDOS_DB_PATH"]
    add_project_to_db(db_path, "Sprint 2", "Week 2", 2, 1)
    add_project_to_db(db_path, "Sprint 3", "Week 4", 4, 1)  # Gap in week 3
    
    # Test week 1: Sprint 1 active
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 1
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 2
    assert status["should_pause"] == False
    
    # Advance to week 2
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 15, 
        "reason": "Week 2"
    })
    assert advance_response.status_code == 200
    
    # Test week 2: Sprint 2 active
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 2
    assert status["active_projects_count"] == 1
    assert status["future_projects_count"] == 1
    assert status["should_pause"] == False
    
    # Advance to week 3 (gap week)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 25, 
        "reason": "Week 3 gap"
    })
    assert advance_response.status_code == 200
    
    # Test week 3: No active projects, but Sprint 3 is future
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 3
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 1
    assert status["should_pause"] == False
    
    # Advance to week 5 (past all projects)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 45, 
        "reason": "Past all sprints"
    })
    assert advance_response.status_code == 200
    
    # Test week 5: All sprints complete, should pause
    status_response = client.get("/api/v1/simulation/auto-pause/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_week"] == 5
    assert status["active_projects_count"] == 0
    assert status["future_projects_count"] == 0
    assert status["should_pause"] == True


def test_project_lifecycle_calculations(multi_project_client):
    """Test that project lifecycle calculations are accurate."""
    client, email_client, chat_client, engine = multi_project_client
    
    # Create test person
    person = create_test_person(client, "Calc Manager", "calc@vdos.local", "calc", True)
    
    # Test various project configurations
    project_configs = [
        # (start_week, duration_weeks, expected_end_week)
        (1, 1, 1),   # Single week
        (1, 4, 4),   # Multi-week from start
        (3, 2, 4),   # Starting later
        (5, 3, 7),   # Long project starting later
    ]
    
    for i, (start_week, duration_weeks, expected_end_week) in enumerate(project_configs):
        # Clear previous projects and start fresh
        if i == 0:
            # Start initial project
            start_response = client.post("/api/v1/simulation/start", json={
                "project_name": f"Test Project {i+1}",
                "project_summary": f"Project {i+1} for lifecycle testing",
                "duration_weeks": duration_weeks,
                "department_head_name": "Calc Manager",
                "include_person_ids": [person["id"]],
            })
            assert start_response.status_code == 200
        else:
            # Add subsequent projects to database
            db_path = os.environ["VDOS_DB_PATH"]
            add_project_to_db(db_path, f"Test Project {i+1}", f"Project {i+1}", start_week, duration_weeks)
        
        # Test that the project is active during its expected weeks
        for test_week in range(start_week, expected_end_week + 1):
            # Calculate target tick for the test week
            target_tick = (test_week - 1) * 10 + 5  # Middle of the week
            
            advance_response = client.post("/api/v1/simulation/advance", json={
                "ticks": target_tick, 
                "reason": f"Test project {i+1} week {test_week}"
            })
            assert advance_response.status_code == 200
            
            status_response = client.get("/api/v1/simulation/auto-pause/status")
            assert status_response.status_code == 200
            status = status_response.json()
            
            # Verify the project is active during its expected timeline
            assert status["current_week"] == test_week
            # Note: We can't easily test individual project activity without more complex setup
            # but we can verify that SOME project is active during expected weeks
            if test_week <= max(config[0] + config[1] - 1 for config in project_configs[:i+1]):
                assert status["active_projects_count"] > 0, \
                    f"Expected active projects in week {test_week} for project {i+1}"


def test_auto_pause_behavior_with_complex_schedules(multi_project_client):
    """Test auto-pause behavior with very complex project schedules."""
    client, email_client, chat_client, engine = multi_project_client
    
    # Create test person
    person = create_test_person(client, "Complex Scheduler", "scheduler@vdos.local", "scheduler", True)
    
    # Start initial project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Initial Setup",
        "project_summary": "Initial project",
        "duration_weeks": 1,
        "department_head_name": "Complex Scheduler",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Create a very complex schedule with multiple overlaps and gaps
    db_path = os.environ["VDOS_DB_PATH"]
    complex_projects = [
        ("Phase 1A", 2, 2),    # Weeks 2-3
        ("Phase 1B", 2, 3),    # Weeks 2-4
        ("Phase 2A", 4, 2),    # Weeks 4-5
        ("Phase 2B", 5, 1),    # Week 5
        ("Integration", 6, 2), # Weeks 6-7
        ("Testing", 7, 2),     # Weeks 7-8
        ("Deployment", 10, 1), # Week 10 (gap in weeks 8-9)
    ]
    
    for name, start_week, duration_weeks in complex_projects:
        add_project_to_db(db_path, name, f"Complex project {name}", start_week, duration_weeks)
    
    # Test that auto-pause never triggers until all projects are truly complete
    for week in range(1, 12):
        target_tick = (week - 1) * 10 + 5
        
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": target_tick, 
            "reason": f"Test complex schedule week {week}"
        })
        assert advance_response.status_code == 200
        
        status_response = client.get("/api/v1/simulation/auto-pause/status")
        assert status_response.status_code == 200
        status = status_response.json()
        
        # Auto-pause should only trigger after week 10 (when Deployment is complete)
        if week <= 10:
            assert status["should_pause"] == False, \
                f"Auto-pause should not trigger in week {week} (projects still exist)"
        else:
            assert status["should_pause"] == True, \
                f"Auto-pause should trigger in week {week} (all projects complete)"
            assert status["active_projects_count"] == 0
            assert status["future_projects_count"] == 0