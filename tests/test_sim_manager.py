import importlib
from contextlib import contextmanager

import pytest
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

        email_gateway = TestEmailGateway()
        chat_gateway = TestChatGateway()
        engine = SimulationEngine(email_gateway=email_gateway, chat_gateway=chat_gateway)
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

    start = client.post("/api/v1/simulation/start")
    assert start.status_code == 200
    assert start.json()["is_running"] is True

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
        "personality": ["Calm"],
    })

    client.post("/api/v1/simulation/start")
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
