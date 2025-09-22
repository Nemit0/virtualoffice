import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    db_path = tmp_path / "chat.db"
    monkeypatch.setenv("VDOS_DB_PATH", str(db_path))

    db_module = importlib.import_module("virtualoffice.common.db")
    importlib.reload(db_module)

    chat_module = importlib.import_module("virtualoffice.servers.chat.app")
    chat_module = importlib.reload(chat_module)

    client = TestClient(chat_module.app)
    with client:
        yield client


def test_create_room_and_post_message(chat_client):
    room_payload = {
        "name": "Alpha Standup",
        "participants": ["Manager", "Analyst"],
    }
    response = chat_client.post("/rooms", json=room_payload)
    assert response.status_code == 201
    room = response.json()
    assert room["name"] == room_payload["name"]
    slug = room["slug"]

    post_response = chat_client.post(
        f"/rooms/{slug}/messages",
        json={"sender": "manager", "body": "Standup in 10."},
    )
    assert post_response.status_code == 201
    message = post_response.json()
    assert message["room_slug"] == slug
    assert message["sender"] == "manager"

    history = chat_client.get(f"/rooms/{slug}/messages")
    assert history.status_code == 200
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["body"] == "Standup in 10."


def test_dm_flow(chat_client):
    dm_payload = {"sender": "Manager", "recipient": "Designer", "body": "Need mockups"}
    response = chat_client.post("/dms", json=dm_payload)
    assert response.status_code == 201
    message = response.json()
    assert message["room_slug"] == "dm:designer:manager"

    room_response = chat_client.get("/rooms/dm:designer:manager")
    assert room_response.status_code == 200
    room = room_response.json()
    assert sorted(room["participants"]) == ["designer", "manager"]

    second = chat_client.post(
        "/dms",
        json={"sender": "designer", "recipient": "manager", "body": "Mockups uploaded"},
    )
    assert second.status_code == 201
    history = chat_client.get("/rooms/dm:designer:manager/messages")
    assert len(history.json()) == 2


def test_non_member_cannot_post(chat_client):
    room_payload = {"name": "Ops", "participants": ["lead", "analyst"]}
    response = chat_client.post("/rooms", json=room_payload)
    slug = response.json()["slug"]

    forbidden = chat_client.post(
        f"/rooms/{slug}/messages",
        json={"sender": "outsider", "body": "Hi"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Sender not in room"