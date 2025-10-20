from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def normalise_address(value: str) -> str:
    cleaned = value.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise ValueError("Invalid email address")
    return cleaned


class Mailbox(BaseModel):
    address: str
    display_name: Optional[str] = None

    @field_validator("address")
    @classmethod
    def _validate_address(cls, value: str) -> str:
        return normalise_address(value)


class MailboxUpdate(BaseModel):
    display_name: Optional[str] = None


class EmailSend(BaseModel):
    sender: str
    to: List[str] = Field(default_factory=list)
    cc: List[str] = Field(default_factory=list)
    bcc: List[str] = Field(default_factory=list)
    subject: str = Field(..., max_length=512)
    body: str
    thread_id: Optional[str] = Field(default=None, max_length=128)
    # Optional simulated timestamp (ISO 8601). When provided, server uses it for sent_at.
    sent_at_iso: Optional[str] = None

    @field_validator("sender")
    @classmethod
    def _validate_sender(cls, value: str) -> str:
        return normalise_address(value)

    @field_validator("to", "cc", "bcc", mode="before")
    @classmethod
    def _validate_recipients(cls, value: List[str]) -> List[str]:
        return [normalise_address(item) for item in value]

    def recipients_flat(self) -> List[str]:
        # Returns all distinct recipient addresses preserving order of to -> cc -> bcc.
        seen = set()
        ordered = []
        for bucket in (self.to, self.cc, self.bcc):
            for value in bucket:
                if value not in seen:
                    seen.add(value)
                    ordered.append(value)
        return ordered


class EmailMessage(BaseModel):
    id: int
    sender: str
    to: List[str]
    cc: List[str]
    bcc: List[str]
    subject: str
    body: str
    thread_id: Optional[str]
    sent_at: datetime


class DraftCreate(BaseModel):
    subject: str = Field(..., max_length=512)
    body: str
    thread_id: Optional[str] = Field(default=None, max_length=128)


class DraftRecord(BaseModel):
    id: int
    mailbox: str
    subject: str
    body: str
    thread_id: Optional[str]
    updated_at: datetime

    @field_validator("mailbox")
    @classmethod
    def _validate_mailbox(cls, value: str) -> str:
        return normalise_address(value)
