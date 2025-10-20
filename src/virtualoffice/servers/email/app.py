from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable, List

from fastapi import Depends, FastAPI, HTTPException, status

from virtualoffice.common.db import execute_script, get_connection
from virtualoffice.servers.email.models import (
    DraftCreate,
    DraftRecord,
    EmailMessage,
    EmailSend,
    Mailbox,
    MailboxUpdate,
    normalise_address,
)

app = FastAPI(title="VDOS Email Server", version="0.1.0")

EMAIL_SCHEMA = """
CREATE TABLE IF NOT EXISTS mailboxes (
    address TEXT PRIMARY KEY,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    thread_id TEXT,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(sender) REFERENCES mailboxes(address)
);

CREATE TABLE IF NOT EXISTS email_recipients (
    email_id INTEGER NOT NULL,
    address TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('to', 'cc', 'bcc')),
    FOREIGN KEY(email_id) REFERENCES emails(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mailbox TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    thread_id TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(mailbox) REFERENCES mailboxes(address)
);

CREATE INDEX IF NOT EXISTS idx_email_recipient_address ON email_recipients(address);
CREATE INDEX IF NOT EXISTS idx_drafts_mailbox ON drafts(mailbox);
"""


@app.on_event("startup")
def initialise() -> None:
    execute_script(EMAIL_SCHEMA)


def db_dependency():
    with get_connection() as conn:
        yield conn


def _normalise_or_422(address: str) -> str:
    try:
        return normalise_address(address)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _ensure_mailboxes(conn, addresses: Iterable[str]) -> None:
    unique_addresses = {_normalise_or_422(addr) for addr in addresses if addr}
    for address in unique_addresses:
        conn.execute(
            "INSERT INTO mailboxes(address) VALUES (?) ON CONFLICT(address) DO NOTHING",
            (address,),
        )


def _row_to_email(conn, email_id: int) -> EmailMessage:
    row = conn.execute(
        "SELECT id, sender, subject, body, thread_id, sent_at FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    recipients: dict[str, List[str]] = defaultdict(list)
    for rec in conn.execute(
        "SELECT address, kind FROM email_recipients WHERE email_id = ? ORDER BY rowid",
        (email_id,),
    ):
        recipients[rec["kind"]].append(rec["address"])

    return EmailMessage(
        id=row["id"],
        sender=row["sender"],
        to=recipients.get("to", []),
        cc=recipients.get("cc", []),
        bcc=recipients.get("bcc", []),
        subject=row["subject"],
        body=row["body"],
        thread_id=row["thread_id"],
        sent_at=datetime.fromisoformat(row["sent_at"]),
    )


@app.put(
    "/mailboxes/{address}",
    response_model=Mailbox,
    status_code=status.HTTP_201_CREATED,
)
def ensure_mailbox(address: str, update: MailboxUpdate | None = None, conn=Depends(db_dependency)):
    cleaned = _normalise_or_422(address)
    display_name = update.display_name if update else None
    conn.execute(
        "INSERT INTO mailboxes(address, display_name) VALUES(?, ?)\n"
        "ON CONFLICT(address) DO UPDATE SET display_name = COALESCE(?, display_name)",
        (cleaned, display_name, display_name),
    )
    stored = conn.execute(
        "SELECT address, display_name FROM mailboxes WHERE address = ?",
        (cleaned,),
    ).fetchone()
    return Mailbox(address=stored["address"], display_name=stored["display_name"])


@app.post("/emails/send", response_model=EmailMessage, status_code=status.HTTP_201_CREATED)
def send_email(payload: EmailSend, conn=Depends(db_dependency)):
    recipients = payload.recipients_flat()
    if not recipients:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one recipient required")

    all_addresses = [payload.sender, *recipients]
    _ensure_mailboxes(conn, all_addresses)

    # Allow overriding sent_at when sent_at_iso is provided
    if getattr(payload, "sent_at_iso", None):
        cursor = conn.execute(
            "INSERT INTO emails(sender, subject, body, thread_id, sent_at) VALUES (?, ?, ?, ?, ?)",
            (payload.sender, payload.subject, payload.body, payload.thread_id, payload.sent_at_iso),
        )
    else:
        cursor = conn.execute(
            "INSERT INTO emails(sender, subject, body, thread_id) VALUES (?, ?, ?, ?)",
            (payload.sender, payload.subject, payload.body, payload.thread_id),
        )
    email_id = cursor.lastrowid

    for address in payload.to:
        conn.execute(
            "INSERT INTO email_recipients(email_id, address, kind) VALUES (?, ?, 'to')",
            (email_id, address),
        )
    for address in payload.cc:
        conn.execute(
            "INSERT INTO email_recipients(email_id, address, kind) VALUES (?, ?, 'cc')",
            (email_id, address),
        )
    for address in payload.bcc:
        conn.execute(
            "INSERT INTO email_recipients(email_id, address, kind) VALUES (?, ?, 'bcc')",
            (email_id, address),
        )

    return _row_to_email(conn, email_id)


@app.get("/mailboxes/{address}/emails", response_model=List[EmailMessage])
def list_mailbox_emails(
    address: str,
    since_id: int | None = None,
    since_timestamp: str | None = None,
    limit: int | None = None,
    conn=Depends(db_dependency)
):
    """Get emails for a mailbox, optionally filtered by ID or timestamp.

    Args:
        address: Email address of the mailbox
        since_id: Only return emails with ID greater than this (for polling new messages)
        since_timestamp: Only return emails sent after this ISO timestamp (for time-based filtering)
        limit: Maximum number of emails to return (newest first)
    """
    cleaned = _normalise_or_422(address)
    mailbox_exists = conn.execute(
        "SELECT 1 FROM mailboxes WHERE address = ?",
        (cleaned,),
    ).fetchone()
    if not mailbox_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox not found")

    # Build query with optional filters
    query = """
        SELECT DISTINCT er.email_id
        FROM email_recipients er
        JOIN emails e ON er.email_id = e.id
        WHERE er.address = ?
    """
    params = [cleaned]

    if since_id is not None:
        query += " AND er.email_id > ?"
        params.append(since_id)

    if since_timestamp is not None:
        query += " AND e.sent_at > ?"
        params.append(since_timestamp)

    query += " ORDER BY er.email_id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    email_ids = [row["email_id"] for row in conn.execute(query, params)]
    return [_row_to_email(conn, email_id) for email_id in email_ids]


@app.get("/emails/{email_id}", response_model=EmailMessage)
def get_email(email_id: int, conn=Depends(db_dependency)):
    return _row_to_email(conn, email_id)


@app.post(
    "/mailboxes/{address}/drafts",
    response_model=DraftRecord,
    status_code=status.HTTP_201_CREATED,
)
def save_draft(address: str, payload: DraftCreate, conn=Depends(db_dependency)):
    cleaned = _normalise_or_422(address)
    _ensure_mailboxes(conn, [cleaned])
    cursor = conn.execute(
        """
        INSERT INTO drafts(mailbox, subject, body, thread_id)
        VALUES (?, ?, ?, ?)
        """,
        (cleaned, payload.subject, payload.body, payload.thread_id),
    )
    draft_id = cursor.lastrowid
    return _draft_to_record(conn, draft_id)


@app.get("/mailboxes/{address}/drafts", response_model=List[DraftRecord])
def list_drafts(address: str, conn=Depends(db_dependency)):
    cleaned = _normalise_or_422(address)
    mailbox_exists = conn.execute(
        "SELECT 1 FROM mailboxes WHERE address = ?",
        (cleaned,),
    ).fetchone()
    if not mailbox_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox not found")

    draft_ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM drafts WHERE mailbox = ? ORDER BY updated_at DESC",
            (cleaned,),
        )
    ]
    return [_draft_to_record(conn, draft_id) for draft_id in draft_ids]


def _draft_to_record(conn, draft_id: int) -> DraftRecord:
    row = conn.execute(
        "SELECT id, mailbox, subject, body, thread_id, updated_at FROM drafts WHERE id = ?",
        (draft_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return DraftRecord(
        id=row["id"],
        mailbox=row["mailbox"],
        subject=row["subject"],
        body=row["body"],
        thread_id=row["thread_id"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
