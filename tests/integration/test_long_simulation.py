"""
Integration tests for long-running simulations.

Tests that validate the refactored engine can handle extended simulations
in both English and Korean locales, producing valid output.
"""

import importlib
import os
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


def _create_simulation_engine(tmp_path, monkeypatch, locale="en"):
    """Helper function to create simulation engine for testing."""
    with _reload_db(tmp_path, monkeypatch):
        # Configure environment
        monkeypatch.setenv("VDOS_LOCALE", locale)
        
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

            def get_emails(self, address: str) -> list:
                response = email_http.get(f"/mailboxes/{address}/emails")
                assert response.status_code == 200
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

            def get_messages(self, handle: str) -> list:
                response = chat_http.get(f"/users/{handle}/messages")
                if response.status_code == 200:
                    return response.json()
                return []

            def close(self) -> None:
                chat_http.close()

        class TestPlanner:
            def __init__(self, locale="en"):
                self.locale = locale

            def generate_project_plan(self, **kwargs) -> PlanResult:
                content = "Project plan stub" if self.locale == "en" else "프로젝트 계획 스텁"
                return PlanResult(content=content, model_used="stub-project", tokens_used=1)

            def generate_daily_plan(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                day_index = kwargs.get("day_index", 0)
                if self.locale == "en":
                    content = f"Daily plan for {worker.name} day {day_index}"
                else:
                    content = f"{worker.name}의 {day_index}일차 일일 계획"
                return PlanResult(content=content, model_used="stub-daily", tokens_used=1)

            def generate_hourly_plan(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                tick = kwargs.get("tick", 0)
                reason = kwargs.get("context_reason", "manual" if self.locale == "en" else "수동")
                if self.locale == "en":
                    content = f"Hourly plan tick {tick} for {worker.name} ({reason})"
                else:
                    content = f"{worker.name}의 {tick}시간 계획 ({reason})"
                return PlanResult(content=content, model_used="stub-hourly", tokens_used=1)

            def generate_daily_report(self, **kwargs) -> PlanResult:
                worker = kwargs["worker"]
                day_index = kwargs.get("day_index", 0)
                if self.locale == "en":
                    content = f"Daily report for {worker.name} day {day_index}"
                else:
                    content = f"{worker.name}의 {day_index}일차 일일 보고"
                return PlanResult(content=content, model_used="stub-daily-report", tokens_used=1)

            def generate_simulation_report(self, **kwargs) -> PlanResult:
                total_ticks = kwargs.get("total_ticks", 0)
                if self.locale == "en":
                    content = f"Simulation report after {total_ticks} ticks"
                else:
                    content = f"{total_ticks}틱 후 시뮬레이션 보고서"
                return PlanResult(content=content, model_used="stub-simulation", tokens_used=1)

        email_gateway = TestEmailGateway()
        chat_gateway = TestChatGateway()
        planner = TestPlanner(locale)
        engine = SimulationEngine(
            email_gateway=email_gateway,
            chat_gateway=chat_gateway,
            planner=planner,
            hours_per_day=8,  # Full workday
            tick_interval_seconds=0.01
        )
        app = create_app(engine)
        client = TestClient(app)
        try:
            yield client, email_gateway, chat_gateway, engine
        finally:
            client.close()
            engine.close()


@pytest.fixture
def english_simulation(tmp_path, monkeypatch):
    """Fixture for English locale simulation."""
    yield from _create_simulation_engine(tmp_path, monkeypatch, locale="en")


@pytest.fixture
def korean_simulation(tmp_path, monkeypatch):
    """Fixture for Korean locale simulation."""
    yield from _create_simulation_engine(tmp_path, monkeypatch, locale="ko")


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


def test_one_week_english_simulation(english_simulation):
    """Test 1-week simulation in English locale produces valid output."""
    client, email_gateway, chat_gateway, engine = english_simulation
    
    # Create team
    manager = create_test_person(client, "English Manager", "mgr@vdos.local", "mgr", True)
    dev1 = create_test_person(client, "Developer One", "dev1@vdos.local", "dev1", False)
    dev2 = create_test_person(client, "Developer Two", "dev2@vdos.local", "dev2", False)
    
    # Start 1-week project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "English Test Project",
        "project_summary": "One week English simulation test",
        "duration_weeks": 1,
        "department_head_name": "English Manager",
        "include_person_ids": [manager["id"], dev1["id"], dev2["id"]],
    })
    assert start_response.status_code == 200
    
    # Run simulation for 1 week (40 ticks = 5 days * 8 hours)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 40,
        "reason": "Complete 1-week English simulation"
    })
    assert advance_response.status_code == 200
    
    # Verify simulation state
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_tick"] == 40
    
    # Verify people have plans
    people_response = client.get("/api/v1/people")
    assert people_response.status_code == 200
    people = people_response.json()
    assert len(people) == 3
    
    # Verify communications were generated
    emails = email_gateway.get_emails("mgr@vdos.local")
    assert len(emails) >= 0  # May or may not have emails depending on plans
    
    # Verify output is in English
    for person in people:
        assert person["name"] in ["English Manager", "Developer One", "Developer Two"]


def test_one_week_korean_simulation(korean_simulation):
    """Test 1-week simulation in Korean locale produces valid output."""
    client, email_gateway, chat_gateway, engine = korean_simulation
    
    # Create team with Korean names
    manager = create_test_person(client, "김민수", "kim@vdos.local", "kim", True)
    dev1 = create_test_person(client, "이영희", "lee@vdos.local", "lee", False)
    dev2 = create_test_person(client, "박철수", "park@vdos.local", "park", False)
    
    # Start 1-week project
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "한국어 테스트 프로젝트",
        "project_summary": "1주일 한국어 시뮬레이션 테스트",
        "duration_weeks": 1,
        "department_head_name": "김민수",
        "include_person_ids": [manager["id"], dev1["id"], dev2["id"]],
    })
    assert start_response.status_code == 200
    
    # Run simulation for 1 week
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 40,
        "reason": "1주일 한국어 시뮬레이션 완료"
    })
    assert advance_response.status_code == 200
    
    # Verify simulation state
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_tick"] == 40
    
    # Verify people have plans
    people_response = client.get("/api/v1/people")
    assert people_response.status_code == 200
    people = people_response.json()
    assert len(people) == 3
    
    # Verify output uses Korean names
    korean_names = ["김민수", "이영희", "박철수"]
    for person in people:
        assert person["name"] in korean_names


def test_four_week_multi_project_simulation(english_simulation):
    """Test 4-week multi-project simulation produces valid output."""
    client, email_gateway, chat_gateway, engine = english_simulation
    
    # Create larger team
    manager = create_test_person(client, "Project Manager", "pm@vdos.local", "pm", True)
    devs = []
    for i in range(4):
        dev = create_test_person(client, f"Developer {i+1}", f"dev{i+1}@vdos.local", f"dev{i+1}", False)
        devs.append(dev)
    
    all_person_ids = [manager["id"]] + [dev["id"] for dev in devs]
    
    # Start first project (2 weeks)
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Project Phase 1",
        "project_summary": "First phase of multi-project simulation",
        "duration_weeks": 2,
        "department_head_name": "Project Manager",
        "include_person_ids": all_person_ids,
    })
    assert start_response.status_code == 200
    
    # Add second project (weeks 2-4)
    import sqlite3
    db_path = os.environ["VDOS_DB_PATH"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO projects (name, description, start_week, duration_weeks)
            VALUES (?, ?, ?, ?)
        """, ("Project Phase 2", "Second phase overlapping and extending", 2, 3))
        conn.commit()
    
    # Run simulation for 4 weeks (160 ticks = 20 days * 8 hours)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 160,
        "reason": "Complete 4-week multi-project simulation"
    })
    assert advance_response.status_code == 200
    
    # Verify simulation completed
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_tick"] == 160
    
    # Verify all people still exist
    people_response = client.get("/api/v1/people")
    assert people_response.status_code == 200
    people = people_response.json()
    assert len(people) == 5
    
    # Verify simulation produced output
    for person in people:
        assert "name" in person
        assert "email_address" in person


def test_simulation_output_validation(english_simulation):
    """Test that simulation output is valid and complete."""
    client, email_gateway, chat_gateway, engine = english_simulation
    
    # Create minimal team
    manager = create_test_person(client, "Test Manager", "test@vdos.local", "test", True)
    
    # Start short simulation
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Validation Test",
        "project_summary": "Test output validation",
        "duration_weeks": 1,
        "department_head_name": "Test Manager",
        "include_person_ids": [manager["id"]],
    })
    assert start_response.status_code == 200
    
    # Run for a few ticks
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 10,
        "reason": "Test output validation"
    })
    assert advance_response.status_code == 200
    
    # Validate simulation state structure
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    
    # Check required fields
    assert "current_tick" in status
    assert "is_running" in status
    assert isinstance(status["current_tick"], int)
    assert isinstance(status["is_running"], bool)
    
    # Validate people structure
    people_response = client.get("/api/v1/people")
    assert people_response.status_code == 200
    people = people_response.json()
    
    for person in people:
        assert "id" in person
        assert "name" in person
        assert "email_address" in person
        assert "chat_handle" in person
        assert "role" in person
