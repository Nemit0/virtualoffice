from __future__ import annotations

from typing import Iterable, Optional

import httpx


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
        # Filter out empty/invalid email addresses
        def _clean_addresses(addresses: Iterable[str]) -> list[str]:
            cleaned = []
            for addr in addresses:
                addr_str = str(addr).strip()
                # Must have @ and not be empty
                if addr_str and "@" in addr_str and not addr_str.startswith("@") and not addr_str.endswith("@"):
                    cleaned.append(addr_str)
            return cleaned

        cleaned_to = _clean_addresses(to)
        cleaned_cc = _clean_addresses(cc or [])
        cleaned_bcc = _clean_addresses(bcc or [])

        # Check if we have at least one valid recipient after cleaning
        if not cleaned_to and not cleaned_cc and not cleaned_bcc:
            # No valid recipients - return empty response instead of failing
            # This can happen when scheduled comms have malformed addresses
            return {"id": -1, "sender": sender, "to": [], "cc": [], "bcc": [],
                    "subject": subject, "body": "(skipped - no valid recipients)",
                    "thread_id": thread_id, "sent_at": sent_at_iso or ""}

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

    def close(self) -> None:
        if self._external_client is None:
            self._client.close()
