import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def email_client(tmp_path, monkeypatch):
    db_path = tmp_path / "email.db"
    monkeypatch.setenv("VDOS_DB_PATH", str(db_path))

    db_module = importlib.import_module("virtualoffice.common.db")
    importlib.reload(db_module)

    models_module = importlib.import_module("virtualoffice.servers.email.models")
    importlib.reload(models_module)

    app_module = importlib.import_module("virtualoffice.servers.email.app")
    app_module = importlib.reload(app_module)

    client = TestClient(app_module.app)
    with client:
        yield client


def test_send_and_list_email(email_client):
    payload = {
        "sender": "manager@vdos.local",
        "to": ["analyst@vdos.local"],
        "cc": ["observer@vdos.local"],
        "subject": "Daily brief",
        "body": "Stand-up at 09:30.",
        "thread_id": "standup-1",
    }
    response = email_client.post("/emails/send", json=payload)
    assert response.status_code == 201
    email = response.json()
    assert email["sender"] == payload["sender"]
    assert email["to"] == payload["to"]
    assert email["cc"] == payload["cc"]
    assert email["thread_id"] == payload["thread_id"]

    listing = email_client.get("/mailboxes/analyst@vdos.local/emails")
    assert listing.status_code == 200
    emails = listing.json()
    assert len(emails) == 1
    assert emails[0]["subject"] == payload["subject"]

    fetched = email_client.get(f"/emails/{email['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["body"] == payload["body"]


def test_draft_lifecycle(email_client):
    address = "designer@vdos.local"
    draft_payload = {
        "subject": "Wireframe notes",
        "body": "Capture color palette feedback.",
    }
    response = email_client.post(f"/mailboxes/{address}/drafts", json=draft_payload)
    assert response.status_code == 201
    draft = response.json()
    assert draft["mailbox"] == address
    assert draft["subject"] == draft_payload["subject"]

    drafts = email_client.get(f"/mailboxes/{address}/drafts")
    assert drafts.status_code == 200
    records = drafts.json()
    assert len(records) == 1
    assert records[0]["body"] == draft_payload["body"]


def test_requires_recipient(email_client):
    response = email_client.post(
        "/emails/send",
        json={
            "sender": "solo@vdos.local",
            "to": [],
            "subject": "Lonely",
            "body": "Nobody hears this.",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "At least one recipient required"