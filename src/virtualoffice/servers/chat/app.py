from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable, List

from fastapi import Depends, FastAPI, HTTPException, status

from virtualoffice.common.db import execute_script, get_connection
from virtualoffice.servers.chat.models import (
    DMPost,
    MessagePost,
    MessageRecord,
    RoomCreate,
    RoomRecord,
    UserRecord,
    UserUpdate,
)

app = FastAPI(title="VDOS Chat Server", version="0.1.0")

CHAT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_users (
    handle TEXT PRIMARY KEY,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_dm INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_members (
    room_id INTEGER NOT NULL,
    handle TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (room_id, handle),
    FOREIGN KEY(room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE,
    FOREIGN KEY(handle) REFERENCES chat_users(handle) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    sender TEXT NOT NULL,
    body TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE,
    FOREIGN KEY(sender) REFERENCES chat_users(handle)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room_id, sent_at);
"""


@app.on_event("startup")
def initialise() -> None:
    execute_script(CHAT_SCHEMA)


def db_dependency():
    with get_connection() as conn:
        yield conn


def _normalise_handle(handle: str) -> str:
    return handle.strip().lower()


def _ensure_users(conn, handles: Iterable[str]) -> None:
    for handle in {_normalise_handle(h) for h in handles if h}:
        conn.execute(
            "INSERT INTO chat_users(handle) VALUES (?) ON CONFLICT(handle) DO NOTHING",
            (handle,),
        )


def _room_by_slug(conn, slug: str):
    row = conn.execute(
        "SELECT id, slug, name, is_dm FROM chat_rooms WHERE slug = ?",
        (slug,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return row


def _room_to_record(conn, room_row) -> RoomRecord:
    participants = [
        member["handle"]
        for member in conn.execute(
            "SELECT handle FROM chat_members WHERE room_id = ? ORDER BY handle",
            (room_row["id"],),
        )
    ]
    return RoomRecord(
        slug=room_row["slug"],
        name=room_row["name"],
        participants=participants,
        is_dm=bool(room_row["is_dm"]),
    )


def _message_to_record(conn, message_id: int) -> MessageRecord:
    row = conn.execute(
        "SELECT m.id, r.slug, m.sender, m.body, m.sent_at\n"
        "FROM chat_messages m JOIN chat_rooms r ON m.room_id = r.id WHERE m.id = ?",
        (message_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return MessageRecord(
        id=row["id"],
        room_slug=row["slug"],
        sender=row["sender"],
        body=row["body"],
        sent_at=datetime.fromisoformat(row["sent_at"]),
    )


@app.put("/users/{handle}", response_model=UserRecord, status_code=status.HTTP_201_CREATED)
def ensure_user(handle: str, update: UserUpdate | None = None, conn=Depends(db_dependency)):
    normalised = _normalise_handle(handle)
    display_name = update.display_name if update else None
    conn.execute(
        "INSERT INTO chat_users(handle, display_name) VALUES(?, ?)\n"
        "ON CONFLICT(handle) DO UPDATE SET display_name = COALESCE(?, display_name)",
        (normalised, display_name, display_name),
    )
    row = conn.execute(
        "SELECT handle, display_name FROM chat_users WHERE handle = ?",
        (normalised,),
    ).fetchone()
    return UserRecord(handle=row["handle"], display_name=row["display_name"])


@app.post("/rooms", response_model=RoomRecord, status_code=status.HTTP_201_CREATED)
def create_room(payload: RoomCreate, conn=Depends(db_dependency)):
    handles = [_normalise_handle(h) for h in payload.participants]
    if not handles:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one participant required")

    _ensure_users(conn, handles)

    slug = payload.slug.lower() if payload.slug else f"room-{uuid.uuid4().hex[:8]}"
    existing = conn.execute(
        "SELECT 1 FROM chat_rooms WHERE slug = ?",
        (slug,),
    ).fetchone()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room slug already exists")

    cursor = conn.execute(
        "INSERT INTO chat_rooms(slug, name, is_dm) VALUES (?, ?, 0)",
        (slug, payload.name),
    )
    room_id = cursor.lastrowid

    for handle in handles:
        conn.execute(
            "INSERT OR IGNORE INTO chat_members(room_id, handle) VALUES(?, ?)",
            (room_id, handle),
        )

    return _room_to_record(conn, _room_by_slug(conn, slug))


@app.get("/rooms/{slug}", response_model=RoomRecord)
def get_room(slug: str, conn=Depends(db_dependency)):
    row = _room_by_slug(conn, slug)
    return _room_to_record(conn, row)


@app.post(
    "/rooms/{slug}/messages",
    response_model=MessageRecord,
    status_code=status.HTTP_201_CREATED,
)
def post_message(slug: str, payload: MessagePost, conn=Depends(db_dependency)):
    room = _room_by_slug(conn, slug)
    sender = _normalise_handle(payload.sender)
    _ensure_users(conn, [sender])
    membership = conn.execute(
        "SELECT 1 FROM chat_members WHERE room_id = ? AND handle = ?",
        (room["id"], sender),
    ).fetchone()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sender not in room")

    if getattr(payload, "sent_at_iso", None):
        cursor = conn.execute(
            "INSERT INTO chat_messages(room_id, sender, body, sent_at) VALUES (?, ?, ?, ?)",
            (room["id"], sender, payload.body, payload.sent_at_iso),
        )
    else:
        cursor = conn.execute(
            "INSERT INTO chat_messages(room_id, sender, body) VALUES (?, ?, ?)",
            (room["id"], sender, payload.body),
        )
    return _message_to_record(conn, cursor.lastrowid)


@app.get("/rooms/{slug}/messages", response_model=List[MessageRecord])
def list_messages(
    slug: str,
    since_id: int | None = None,
    since_timestamp: str | None = None,
    limit: int | None = None,
    conn=Depends(db_dependency)
):
    """Get messages in a room, optionally filtered by ID or timestamp.

    Args:
        slug: Room slug
        since_id: Only return messages with ID greater than this (for polling new messages)
        since_timestamp: Only return messages sent after this ISO timestamp
        limit: Maximum number of messages to return (chronological order)
    """
    room = _room_by_slug(conn, slug)

    query = "SELECT id FROM chat_messages WHERE room_id = ?"
    params = [room["id"]]

    if since_id is not None:
        query += " AND id > ?"
        params.append(since_id)

    if since_timestamp is not None:
        query += " AND sent_at > ?"
        params.append(since_timestamp)

    query += " ORDER BY sent_at"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    messages = conn.execute(query, params)
    return [_message_to_record(conn, row["id"]) for row in messages]


def _dm_slug(sender: str, recipient: str) -> str:
    handles = sorted([_normalise_handle(sender), _normalise_handle(recipient)])
    return f"dm:{handles[0]}:{handles[1]}"


@app.post("/dms", response_model=MessageRecord, status_code=status.HTTP_201_CREATED)
def send_dm(payload: DMPost, conn=Depends(db_dependency)):
    slug = _dm_slug(payload.sender, payload.recipient)
    handles = {_normalise_handle(payload.sender), _normalise_handle(payload.recipient)}
    _ensure_users(conn, handles)

    room_row = conn.execute(
        "SELECT id FROM chat_rooms WHERE slug = ?",
        (slug,),
    ).fetchone()

    if not room_row:
        sorted_handles = sorted(handles)
        display_name = (
            f"DM {sorted_handles[0]}<->{sorted_handles[1]}" if len(sorted_handles) > 1 else f"DM {sorted_handles[0]}"
        )
        cursor = conn.execute(
            "INSERT INTO chat_rooms(slug, name, is_dm) VALUES (?, ?, 1)",
            (slug, display_name),
        )
        room_id = cursor.lastrowid
        for handle in handles:
            conn.execute(
                "INSERT INTO chat_members(room_id, handle) VALUES(?, ?)",
                (room_id, handle),
            )
    else:
        room_id = room_row["id"]

    # Preserve provided sent_at if present
    post_payload = MessagePost(sender=payload.sender, body=payload.body, sent_at_iso=getattr(payload, "sent_at_iso", None))
    return post_message(slug, post_payload, conn)


@app.get("/users/{handle}/dms", response_model=List[MessageRecord])
def list_user_dms(
    handle: str,
    since_id: int | None = None,
    since_timestamp: str | None = None,
    limit: int | None = None,
    conn=Depends(db_dependency)
):
    """Get all DM messages for a user across all DM conversations.

    Args:
        handle: User's chat handle
        since_id: Only return messages with ID greater than this
        since_timestamp: Only return messages sent after this ISO timestamp
        limit: Maximum number of messages to return
    """
    normalised = _normalise_handle(handle)

    # Find all DM rooms the user is a member of
    room_ids = [
        row["room_id"]
        for row in conn.execute(
            """
            SELECT DISTINCT cm.room_id
            FROM chat_members cm
            JOIN chat_rooms cr ON cm.room_id = cr.id
            WHERE cm.handle = ? AND cr.is_dm = 1
            """,
            (normalised,),
        )
    ]

    if not room_ids:
        return []

    # Build query for messages in those rooms
    placeholders = ",".join("?" * len(room_ids))
    query = f"SELECT id FROM chat_messages WHERE room_id IN ({placeholders})"
    params = list(room_ids)

    if since_id is not None:
        query += " AND id > ?"
        params.append(since_id)

    if since_timestamp is not None:
        query += " AND sent_at > ?"
        params.append(since_timestamp)

    query += " ORDER BY sent_at"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    messages = conn.execute(query, params)
    return [_message_to_record(conn, row["id"]) for row in messages]
