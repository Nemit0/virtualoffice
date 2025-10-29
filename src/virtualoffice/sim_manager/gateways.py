from __future__ import annotations

import logging
from typing import Iterable, Optional

import httpx

from virtualoffice.common.email_validation import filter_valid_emails

logger = logging.getLogger(__name__)


class EmailGateway:
    def ensure_mailbox(self, address: str, display_name: Optional[str] = None) -> None:
        raise NotImplementedError

    def send_email(
        self,
        sender: str,
        to: Iterable[str],
        subject: str,
        body: str,
        cc: Iterable[str] | None = None,
        bcc: Iterable[str] | None = None,
        thread_id: str | None = None,
        sent_at_iso: str | None = None,
    ) -> dict:
        raise NotImplementedError


class HttpEmailGateway(EmailGateway):
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._external_client = client
        self._client = client or httpx.Client(base_url=self.base_url, timeout=10.0)

    @property
    def client(self) -> httpx.Client:
        return self._client

    def ensure_mailbox(self, address: str, display_name: Optional[str] = None) -> None:
        payload = {"display_name": display_name} if display_name else None
        response = self.client.put(f"/mailboxes/{address}", json=payload)
        response.raise_for_status()

    def send_email(
        self,
        sender: str,
        to: Iterable[str],
        subject: str,
        body: str,
        cc: Iterable[str] | None = None,
        bcc: Iterable[str] | None = None,
        thread_id: str | None = None,
        sent_at_iso: str | None = None,
    ) -> dict:
        # Filter out empty/invalid email addresses using centralized validation
        cleaned_to = filter_valid_emails(to, normalize=False, strict=False)
        cleaned_cc = filter_valid_emails(cc or [], normalize=False, strict=False)
        cleaned_bcc = filter_valid_emails(bcc or [], normalize=False, strict=False)

        # Check if we have at least one valid recipient after cleaning
        if not cleaned_to and not cleaned_cc and not cleaned_bcc:
            # No valid recipients - log and raise error for visibility
            logger.warning(
                "Email send failed: no valid recipients. sender=%s, to=%s, cc=%s, bcc=%s, subject=%s",
                sender,
                to,
                cc,
                bcc,
                subject,
            )
            raise ValueError(f"No valid email recipients found. Original to={to}, cc={cc}, bcc={bcc}")

        payload = {
            "sender": sender,
            "to": cleaned_to,
            "cc": cleaned_cc,
            "bcc": cleaned_bcc,
            "subject": subject,
            "body": body,
            "thread_id": thread_id,
        }
        if sent_at_iso:
            payload["sent_at_iso"] = sent_at_iso
        response = self.client.post("/emails/send", json=payload)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        if self._external_client is None:
            self._client.close()


class ChatGateway:
    def ensure_user(self, handle: str, display_name: Optional[str] = None) -> None:
        raise NotImplementedError

    def send_dm(self, sender: str, recipient: str, body: str) -> dict:
        raise NotImplementedError

    def create_room(self, name: str, participants: list[str], slug: str | None = None) -> dict:
        raise NotImplementedError

    def send_room_message(self, room_slug: str, sender: str, body: str, *, sent_at_iso: str | None = None) -> dict:
        raise NotImplementedError

    def get_room_info(self, room_slug: str) -> dict:
        raise NotImplementedError


class HttpChatGateway(ChatGateway):
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._external_client = client
        self._client = client or httpx.Client(base_url=self.base_url, timeout=10.0)

    @property
    def client(self) -> httpx.Client:
        return self._client

    def ensure_user(self, handle: str, display_name: Optional[str] = None) -> None:
        payload = {"display_name": display_name} if display_name else None
        response = self.client.put(f"/users/{handle}", json=payload)
        response.raise_for_status()

    def send_dm(self, sender: str, recipient: str, body: str, *, sent_at_iso: str | None = None) -> dict:
        payload = {
            "sender": sender,
            "recipient": recipient,
            "body": body,
        }
        if sent_at_iso:
            payload["sent_at_iso"] = sent_at_iso
        response = self.client.post("/dms", json=payload)
        response.raise_for_status()
        return response.json()

    def create_room(self, name: str, participants: list[str], slug: str | None = None) -> dict:
        """Create a group chat room with specified participants."""
        payload = {
            "name": name,
            "participants": participants,
        }
        if slug:
            payload["slug"] = slug
        response = self.client.post("/rooms", json=payload)
        response.raise_for_status()
        return response.json()

    def send_room_message(self, room_slug: str, sender: str, body: str, *, sent_at_iso: str | None = None) -> dict:
        """Send a message to a group chat room."""
        payload = {
            "sender": sender,
            "body": body,
        }
        if sent_at_iso:
            payload["sent_at_iso"] = sent_at_iso
        response = self.client.post(f"/rooms/{room_slug}/messages", json=payload)
        response.raise_for_status()
        return response.json()

    def get_room_info(self, room_slug: str) -> dict:
        """Get room information including participants."""
        response = self.client.get(f"/rooms/{room_slug}")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        if self._external_client is None:
            self._client.close()
