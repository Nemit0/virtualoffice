import importlib
from contextlib import contextmanager

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
def sim_client(tmp_path, monkeypatch):
    with _reload_db(tmp_path, monkeypatch):
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

            def close(self) -> None:  # pragma: no cover
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

            def close(self) -> None:  # pragma: no cover
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
        engine = SimulationEngine(email_gateway=email_gateway, chat_gateway=chat_gateway, planner=planner, hours_per_day=2)
        app = create_app(engine)
        client = TestClient(app)
        try:
            yield client, email_http, chat_http
        finally:
            client.close()
            engine.close()
def test_full_simulation_flow(sim_client):
    client, email_client, chat_client = sim_client

    person_payload = {
        "name": "Hana Kim",
        "role": "Designer",
        "timezone": "Asia/Seoul",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Warm async",
        "email_address": "hana.kim@vdos.local",
        "chat_handle": "hana",
        "skills": ["Figma", "UX"],
        "is_department_head": True,
        "personality": ["Collaborative", "Calm"],
        "schedule": [
            {"start": "09:00", "end": "10:00", "activity": "Stand-up & triage"},
            {"start": "10:00", "end": "12:00", "activity": "Design sprint"},
        ],
    }

    response = client.post("/api/v1/people", json=person_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == person_payload["name"]
    assert "persona_markdown" in body and "Hana Kim" in body["persona_markdown"]

    start = client.post("/api/v1/simulation/start", json={
        "project_name": "Website Refresh",
        "project_summary": "Deliver a refreshed marketing site",
        "duration_weeks": 4,
        "department_head_name": "Hana Kim",
    })
    assert start.status_code == 200
    start_body = start.json()
    assert start_body["is_running"] is True
    assert start_body["auto_tick"] is False

    project_plan = client.get("/api/v1/simulation/project-plan")
    assert project_plan.status_code == 200
    plan_body = project_plan.json()
    assert plan_body is not None
    assert plan_body["project_name"] == "Website Refresh"

    auto_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_start.status_code == 200
    assert auto_start.json()["auto_tick"] is True

    auto_stop = client.post("/api/v1/simulation/ticks/stop")
    assert auto_stop.status_code == 200
    assert auto_stop.json()["auto_tick"] is False

    advance = client.post("/api/v1/simulation/advance", json={"ticks": 2, "reason": "smoke"})
    assert advance.status_code == 200
    advance_body = advance.json()
    assert advance_body["current_tick"] == 2
    assert advance_body["emails_sent"] == 2
    assert advance_body["chat_messages_sent"] == 2

    mails = email_client.get("/mailboxes/hana.kim@vdos.local/emails")
    assert mails.status_code == 200
    assert len(mails.json()) == 2

    dm_slug = "dm:hana:sim-manager"
    chat_history = chat_client.get(f"/rooms/{dm_slug}/messages")
    assert chat_history.status_code == 200
    assert len(chat_history.json()) == 2

    worker_plans = client.get("/api/v1/people/1/plans", params={"plan_type": "hourly"})
    assert worker_plans.status_code == 200
    assert worker_plans.json()

    daily_reports = client.get("/api/v1/people/1/daily-reports")
    assert daily_reports.status_code == 200
    daily_body = daily_reports.json()
    assert len(daily_body) == 1
    assert "schedule_outline" in daily_body[0] and daily_body[0]["schedule_outline"]

    stop_response = client.post("/api/v1/simulation/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["is_running"] is False

    sim_reports = client.get("/api/v1/simulation/reports")
    assert sim_reports.status_code == 200
    sim_body = sim_reports.json()
    assert len(sim_body) == 1

    token_usage = client.get("/api/v1/simulation/token-usage")
    assert token_usage.status_code == 200
    usage_body = token_usage.json()
    assert usage_body["total_tokens"] == 7
    assert usage_body["per_model"]["stub-project"] == 1
    assert usage_body["per_model"]["stub-daily"] == 1
    assert usage_body["per_model"]["stub-hourly"] == 3
    assert usage_body["per_model"]["stub-daily-report"] == 1
    assert usage_body["per_model"]["stub-simulation"] == 1

def test_delete_person_by_name(sim_client):
    client, *_ = sim_client

    payload = {
        "name": "Hana Kim",
        "role": "Designer",
        "timezone": "Asia/Seoul",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Warm async",
        "email_address": "hana.kim@vdos.local",
        "chat_handle": "hana",
        "skills": ["Figma", "UX"],
        "is_department_head": True,
        "personality": ["Collaborative", "Calm"],
    }

    create = client.post("/api/v1/people", json=payload)
    assert create.status_code == 201

    deleted = client.delete("/api/v1/people/by-name/Hana%20Kim")
    assert deleted.status_code == 204

    people = client.get("/api/v1/people")
    assert people.status_code == 200
    assert people.json() == []

    missing = client.delete("/api/v1/people/by-name/Hana%20Kim")
    assert missing.status_code == 404


def test_event_injection(sim_client):
    client, *_ = sim_client
    client.post("/api/v1/people", json={
        "name": "Manager",
        "role": "Engineering Manager",
        "timezone": "UTC",
        "work_hours": "09:00-17:00",
        "break_frequency": "60/15",
        "communication_style": "Concise",
        "email_address": "manager@vdos.local",
        "chat_handle": "manager",
        "skills": ["Leadership"],
        "is_department_head": True,
        "personality": ["Calm"],
    })

    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Alpha rollout",
        "project_summary": "Coordinate cross-team release for alpha",
        "duration_weeks": 2,
    })
    assert start_response.status_code == 200
    client.post("/api/v1/simulation/advance", json={"ticks": 1, "reason": "prep"})

    event_payload = {
        "type": "client_change",
        "target_ids": [1],
        "project_id": "alpha",
        "at_tick": 2,
        "payload": {"change": "Update hero copy"},
    }
    created = client.post("/api/v1/events", json=event_payload)
    assert created.status_code == 201
    event = created.json()
    assert event["type"] == "client_change"
    assert event["payload"]["change"] == "Update hero copy"

    events = client.get("/api/v1/events")
    assert events.status_code == 200
    assert len(events.json()) == 1
