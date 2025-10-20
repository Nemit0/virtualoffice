from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class UserRecord(BaseModel):
    handle: str
    display_name: Optional[str] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = None


class RoomCreate(BaseModel):
    name: str = Field(..., max_length=128)
    participants: List[str] = Field(..., min_items=1)
    slug: Optional[str] = Field(default=None, max_length=128)


class RoomRecord(BaseModel):
    slug: str
    name: str
    participants: List[str]
    is_dm: bool


class MessagePost(BaseModel):
    sender: str
    body: str = Field(..., max_length=4096)
    sent_at_iso: Optional[str] = None


class MessageRecord(BaseModel):
    id: int
    room_slug: str
    sender: str
    body: str
    sent_at: datetime


class DMPost(BaseModel):
    sender: str
    recipient: str
    body: str = Field(..., max_length=4096)
    sent_at_iso: Optional[str] = None
