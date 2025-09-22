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
    ) -> dict:
        payload = {
            "sender": sender,
            "to": list(to),
            "cc": list(cc or []),
            "bcc": list(bcc or []),
            "subject": subject,
            "body": body,
            "thread_id": thread_id,
        }
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

    def send_dm(self, sender: str, recipient: str, body: str) -> dict:
        payload = {
            "sender": sender,
            "recipient": recipient,
            "body": body,
        }
        response = self.client.post("/dms", json=payload)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        if self._external_client is None:
            self._client.close()