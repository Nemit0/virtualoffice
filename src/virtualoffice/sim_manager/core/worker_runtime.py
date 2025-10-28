"""
WorkerRuntime Module

Manages runtime state for virtual workers including message queuing and persistence.
Responsibilities:
- Maintain per-worker message inboxes
- Queue and drain messages for workers
- Persist runtime messages to database
- Load runtime state from database
- Synchronize worker runtimes with active people
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Sequence

from virtualoffice.common.db import get_connection

from ..schemas import PersonRead
from .event_system import InboundMessage

logger = logging.getLogger(__name__)


@dataclass
class WorkerRuntime:
    """
    Runtime state for a single virtual worker.

    Maintains an inbox of pending messages that need to be processed
    by the worker during their next planning cycle.
    """

    person: PersonRead
    inbox: list[InboundMessage] = field(default_factory=list)

    def queue(self, message: InboundMessage) -> None:
        """Add a message to the worker's inbox."""
        self.inbox.append(message)

    def drain(self) -> list[InboundMessage]:
        """
        Remove and return all messages from the inbox.

        Returns:
            List of messages that were in the inbox
        """
        items = self.inbox
        self.inbox = []
        return items

    def has_messages(self) -> bool:
        """Check if the worker has any pending messages."""
        return len(self.inbox) > 0

    def message_count(self) -> int:
        """Get the number of pending messages."""
        return len(self.inbox)


class WorkerRuntimeManager:
    """
    Manages runtime state for all virtual workers in the simulation.

    Handles:
    - Creating and retrieving worker runtimes
    - Synchronizing runtimes with active people
    - Persisting messages to database
    - Loading messages from database
    - Clearing runtime state
    """

    def __init__(self) -> None:
        """Initialize the WorkerRuntimeManager."""
        self._worker_runtime: dict[int, WorkerRuntime] = {}

    def get_runtime(self, person: PersonRead) -> WorkerRuntime:
        """
        Get or create a runtime for a person.

        Args:
            person: Person to get runtime for

        Returns:
            WorkerRuntime for the person
        """
        runtime = self._worker_runtime.get(person.id)
        if runtime is None:
            runtime = WorkerRuntime(person=person)
            self._worker_runtime[person.id] = runtime
            self._load_runtime_messages(runtime)
        else:
            # Update person reference in case it changed
            runtime.person = person
        return runtime

    def sync_runtimes(self, people: Sequence[PersonRead]) -> None:
        """
        Synchronize worker runtimes with the active people list.

        Creates runtimes for new people and removes runtimes for
        people who are no longer active.

        Args:
            people: List of currently active people
        """
        active_ids = {person.id for person in people}

        # Create runtimes for all active people
        for person in people:
            self.get_runtime(person)

        # Remove runtimes for inactive people
        for person_id in list(self._worker_runtime.keys()):
            if person_id not in active_ids:
                self._worker_runtime.pop(person_id, None)

    def queue_message(self, recipient: PersonRead, message: InboundMessage) -> None:
        """
        Queue a message for a recipient and persist it to the database.

        Args:
            recipient: Person to receive the message
            message: Message to queue
        """
        runtime = self.get_runtime(recipient)
        runtime.queue(message)
        self._persist_runtime_message(recipient.id, message)

    def remove_messages(self, message_ids: Sequence[int]) -> None:
        """
        Remove messages from the database by their IDs.

        Args:
            message_ids: List of message IDs to remove
        """
        if not message_ids:
            return
        with get_connection() as conn:
            conn.executemany(
                "DELETE FROM worker_runtime_messages WHERE id = ?", [(message_id,) for message_id in message_ids]
            )

    def clear_all(self) -> None:
        """Clear all worker runtimes and delete all runtime messages from database."""
        self._worker_runtime.clear()
        with get_connection() as conn:
            conn.execute("DELETE FROM worker_runtime_messages")

    def get_all_runtimes(self) -> dict[int, WorkerRuntime]:
        """
        Get all worker runtimes.

        Returns:
            Dictionary mapping person IDs to their runtimes
        """
        return self._worker_runtime.copy()

    # Private methods

    def _persist_runtime_message(self, recipient_id: int, message: InboundMessage) -> None:
        """
        Persist a runtime message to the database.

        Args:
            recipient_id: ID of the recipient
            message: Message to persist
        """
        payload = {
            "sender_id": message.sender_id,
            "sender_name": message.sender_name,
            "subject": message.subject,
            "summary": message.summary,
            "action_item": message.action_item,
            "message_type": message.message_type,
            "channel": message.channel,
            "tick": message.tick,
        }
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO worker_runtime_messages(recipient_id, payload) VALUES (?, ?)",
                (recipient_id, json.dumps(payload)),
            )
            message.message_id = cursor.lastrowid

    def _load_runtime_messages(self, runtime: WorkerRuntime) -> None:
        """
        Load persisted messages from database into a runtime.

        Args:
            runtime: Runtime to load messages into
        """
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, payload FROM worker_runtime_messages WHERE recipient_id = ? ORDER BY id",
                (runtime.person.id,),
            ).fetchall()

        runtime.inbox = []
        for row in rows:
            payload = json.loads(row["payload"])
            runtime.inbox.append(
                InboundMessage(
                    sender_id=payload["sender_id"],
                    sender_name=payload["sender_name"],
                    subject=payload["subject"],
                    summary=payload["summary"],
                    action_item=payload.get("action_item"),
                    message_type=payload["message_type"],
                    channel=payload["channel"],
                    tick=payload["tick"],
                    message_id=row["id"],
                )
            )
