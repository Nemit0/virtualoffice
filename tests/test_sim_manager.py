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
        engine = SimulationEngine(email_gateway=email_gateway, chat_gateway=chat_gateway, planner=planner, hours_per_day=2, tick_interval_seconds=0.02)
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
            "include_person_ids": [body['id']],
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

def test_start_simulation_without_department_head(sim_client):
    client, *_ = sim_client

    payload = {
        "name": "Solo Analyst",
        "role": "Analyst",
        "timezone": "UTC",
        "work_hours": "09:00-17:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Direct",
        "email_address": "solo.analyst@vdos.local",
        "chat_handle": "solo",
        "skills": ["Analysis"],
        "personality": ["Focused"],
    }

    create = client.post("/api/v1/people", json=payload)
    assert create.status_code == 201

    start = client.post(
        "/api/v1/simulation/start",
        json={
            "project_name": "Solo project",
            "project_summary": "Single worker scenario",
            "duration_weeks": 1,
            "random_seed": 11,
        },
    )
    assert start.status_code == 200
    body = start.json()
    assert body["is_running"] is True
    assert body["current_tick"] == 0

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



def test_portfolio_webwite_project_outputs(sim_client):
    client, email_client, chat_client = sim_client

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "portfolio_webwite_run.json"

    def ensure_person(payload):
        listing = client.get("/api/v1/people")
        assert listing.status_code == 200
        for entry in listing.json():
            if entry["name"] == payload["name"]:
                return entry
        created = client.post("/api/v1/people", json=payload)
        assert created.status_code == 201
        return created.json()

    hana_payload = {
        "name": "Hana Kim",
        "role": "Designer",
        "timezone": "Asia/Seoul",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Warm async",
        "email_address": "hana.kim@vdos.local",
        "chat_handle": "hana",
        "skills": ["Figma", "UX"],
        "personality": ["Collaborative", "Calm"],
        "is_department_head": True,
        "schedule": [
            {"start": "09:00", "end": "10:00", "activity": "Stand-up & triage"},
            {"start": "10:00", "end": "12:00", "activity": "Design sprint"},
        ],
    }

    dev_payload = {
        "name": "Elliot Park",
        "role": "Full-Stack Developer",
        "timezone": "America/Los_Angeles",
        "work_hours": "08:00-16:00",
        "break_frequency": "45/15 cadence",
        "communication_style": "Concise async",
        "email_address": "elliot.park@vdos.local",
        "chat_handle": "elliot",
        "skills": ["React", "Python", "CI/CD"],
        "personality": ["Pragmatic", "Supportive"],
        "schedule": [
            {"start": "08:00", "end": "09:00", "activity": "Code review"},
            {"start": "09:00", "end": "11:00", "activity": "Feature implementation"},
        ],
    }

    hana = ensure_person(hana_payload)
    developer = ensure_person(dev_payload)

    start = client.post(
        "/api/v1/simulation/start",
        json={
            "project_name": "Portofolio Webwite",
            "project_summary": "Deliver a polished portfolio experience for the client in one week.",
            "duration_weeks": 1,
            "department_head_name": "Hana Kim",
            "include_person_ids": [hana['id'], developer['id']],
            "random_seed": 23,
        },
    )
    assert start.status_code == 200
    start_body = start.json()
    assert start_body["is_running"] is True

    auto_start = client.post("/api/v1/simulation/ticks/start")
    assert auto_start.status_code == 200
    auto_start_body = auto_start.json()

    def wait_for_ticks(target_ticks: int) -> dict:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            state_resp = client.get("/api/v1/simulation")
            assert state_resp.status_code == 200
            state = state_resp.json()
            if state["current_tick"] >= target_ticks:
                return state
            time.sleep(0.01)
        pytest.fail(f"Automatic ticking did not reach {target_ticks} ticks")

    state_after_auto = wait_for_ticks(2)
    assert state_after_auto["current_tick"] >= 2

    auto_stop = client.post("/api/v1/simulation/ticks/stop")
    assert auto_stop.status_code == 200
    auto_stop_body = auto_stop.json()

    state_resp = client.get("/api/v1/simulation")
    assert state_resp.status_code == 200
    state_body = state_resp.json()

    plan_resp = client.get("/api/v1/simulation/project-plan")
    assert plan_resp.status_code == 200
    plan_body = plan_resp.json()
    assert plan_body is not None
    assert plan_body["project_name"] == "Portofolio Webwite"

    def fetch_hourly_plans(person_id):
        response = client.get(
            f"/api/v1/people/{person_id}/plans", params={"plan_type": "hourly"}
        )
        assert response.status_code == 200
        return response.json()

    def fetch_daily_reports(person_id):
        response = client.get(f"/api/v1/people/{person_id}/daily-reports")
        assert response.status_code == 200
        return response.json()

    hana_plans = fetch_hourly_plans(hana["id"])
    dev_plans = fetch_hourly_plans(developer["id"])
    hana_reports = fetch_daily_reports(hana["id"])
    dev_reports = fetch_daily_reports(developer["id"])

    def fetch_mailbox(address):
        response = email_client.get(f"/mailboxes/{address}/emails")
        assert response.status_code == 200
        return response.json()

    def fetch_chat(handle, peers):
        for peer in peers:
            if peer == handle:
                continue
            room_handles = sorted([handle, peer])
            slug = f"dm:{room_handles[0]}:{room_handles[1]}"
            response = chat_client.get(f"/rooms/{slug}/messages")
            if response.status_code == 200:
                return response.json()
        pytest.fail(f"No DM thread found for {handle} against peers {peers}")

    hana_emails = fetch_mailbox(hana["email_address"])
    dev_emails = fetch_mailbox(developer["email_address"])
    hana_chat = fetch_chat(hana["chat_handle"], ["sim-manager", developer["chat_handle"]])
    dev_chat = fetch_chat(developer["chat_handle"], ["sim-manager", hana["chat_handle"]])

    assert len(hana_emails) >= 2
    assert len(dev_emails) >= 2
    assert len(hana_chat) >= 2
    assert len(dev_chat) >= 2

    events = client.get("/api/v1/events")
    assert events.status_code == 200
    event_body = events.json()
    assert event_body

    db_path = Path(os.environ["VDOS_DB_PATH"])
    with sqlite3.connect(db_path) as conn:
        exchange_count = conn.execute("SELECT COUNT(*) FROM worker_exchange_log").fetchone()[0]
        inbox_count = conn.execute("SELECT COUNT(*) FROM worker_runtime_messages").fetchone()[0]
    assert exchange_count >= 4
    assert inbox_count <= 4

    results = {
        "start": start_body,
        "auto_tick": {
            "start": auto_start_body,
            "state_before_stop": state_after_auto,
            "stop": auto_stop_body,
        },
        "state": state_body,
        "project_plan": plan_body,
        "people": {"hana": hana, "developer": developer},
        "hourly_plans": {"hana": hana_plans, "developer": dev_plans},
        "daily_reports": {"hana": hana_reports, "developer": dev_reports},
        "emails": {"hana": hana_emails, "developer": dev_emails},
        "chat_messages": {"hana": hana_chat, "developer": dev_chat},
        "events": event_body,
    }

    output_file.write_text(json.dumps(results, indent=2, sort_keys=True))
    assert output_file.exists()

    stop = client.post("/api/v1/simulation/stop")
    assert stop.status_code == 200




def test_start_with_invalid_include(sim_client):
    client, _, _ = sim_client

    payload = {
        "name": "Solo Lead",
        "role": "Manager",
        "timezone": "UTC",
        "work_hours": "09:00-17:00",
        "break_frequency": "60/15 cadence",
        "communication_style": "Direct",
        "email_address": "solo.lead@vdos.local",
        "chat_handle": "solo",
        "skills": ["Leadership"],
        "personality": ["Focused"],
    }
    created = client.post("/api/v1/people", json=payload)
    assert created.status_code == 201
    person = created.json()

    invalid_id = person['id'] + 42
    start = client.post("/api/v1/simulation/start", json={
        "project_name": "Invalid Include Check",
        "project_summary": "Ensure unknown participants are rejected",
        "duration_weeks": 1,
        "include_person_ids": [invalid_id],
    })
    assert start.status_code == 400
    detail = start.json().get('detail', '')
    assert 'not found' in detail.lower()



def test_dashboard_root(sim_client):
    client, _, _ = sim_client
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "<title>VDOS Dashboard" in body
    assert "const API_PREFIX = '/api/v1'" in body


def test_simulation_reset_endpoint(sim_client):
    client, email_client, chat_client = sim_client
    payload = {
        "name": "Reset Tester",
        "role": "QA",
        "timezone": "UTC",
        "work_hours": "09:00-17:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Async",
        "email_address": "reset.tester@vdos.local",
        "chat_handle": "reset",
        "skills": ["Testing"],
        "personality": ["Meticulous"],
        "schedule": [
            {"start": "09:00", "end": "10:00", "activity": "Plan"}
        ],
    }
    resp = client.post("/api/v1/people", json=payload)
    assert resp.status_code == 201

    start = client.post(
        "/api/v1/simulation/start",
        json={
            "project_name": "Reset Project",
            "project_summary": "Ensure reset clears state",
            "duration_weeks": 1,
        },
    )
    assert start.status_code == 200

    advance = client.post(
        "/api/v1/simulation/advance",
        json={"ticks": 2, "reason": "reset-test"},
    )
    assert advance.status_code == 200

    reset = client.post("/api/v1/simulation/reset")
    assert reset.status_code == 200
    state = reset.json()
    assert state["current_tick"] == 0
    assert state["sim_time"].startswith("Day 0")

    events = client.get("/api/v1/events").json()
    assert events == []
    plan = client.get("/api/v1/simulation/project-plan").json()
    assert plan is None


def test_generate_persona_endpoint(sim_client, monkeypatch):
    client, _, _ = sim_client
    from virtualoffice.sim_manager import app as sim_app

    def fake_generate(messages, model):
        return (
            '{"name":"Auto Dev","role":"Engineer","timezone":"UTC","work_hours":"09:00-17:00","break_frequency":"50/10 cadence","communication_style":"Async","email_address":"auto.dev@vdos.local","chat_handle":"autodev","is_department_head":false,"skills":["Python"],"personality":["Helpful"],"schedule":[{"start":"09:00","end":"10:00","activity":"Plan"}]}'
            ,
            0,
        )

    monkeypatch.setattr(sim_app, "_generate_persona_text", fake_generate, raising=False)

    resp = client.post(
        "/api/v1/personas/generate",
        json={"prompt": "Full stack developer"},
    )
    assert resp.status_code == 200
    payload = resp.json()["persona"]
    assert payload["name"] == "Auto Dev"
    assert payload["skills"] == ["Python"]
