"""
EventSystem module for Virtual Department Operations Simulator.

This module handles event injection, processing, random event generation,
and event-to-adjustment conversion for the simulation engine.

Extracted from SimulationEngine as part of the engine refactoring project.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from typing import Any, Sequence

from virtualoffice.common.db import get_connection
from virtualoffice.common.localization import get_current_locale_manager
from virtualoffice.sim_manager.schemas import EventCreate, PersonRead

logger = logging.getLogger(__name__)


@dataclass
class InboundMessage:
    """Message queued for a worker's inbox."""

    sender_id: int
    sender_name: str
    subject: str
    summary: str
    action_item: str | None
    message_type: str
    channel: str
    tick: int
    message_id: int | None = None


class EventSystem:
    """
    Manages simulation events including injection, processing, and random generation.

    Responsibilities:
    - Event storage and retrieval from database
    - Random event generation (sick leave, client requests, blockers)
    - Event-to-adjustment conversion for worker planning
    - Project-specific event filtering
    """

    def __init__(self, random_seed: int | None = None):
        """
        Initialize the EventSystem.

        Args:
            random_seed: Optional seed for deterministic random event generation
        """
        self._random = random.Random(random_seed)

    def inject_event(self, event: EventCreate) -> dict:
        """
        Inject a custom event into the simulation.

        Args:
            event: Event details including type, targets, timing, and payload

        Returns:
            Dictionary representation of the stored event
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events(type, target_ids, project_id, at_tick, payload)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    event.type,
                    json.dumps(list(event.target_ids)),
                    event.project_id,
                    event.at_tick,
                    json.dumps(event.payload or {}),
                ),
            )
            event_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._row_to_event(row)

    def list_events(self, project_id: str | None = None, target_id: int | None = None) -> list[dict]:
        """
        List all events, optionally filtered by project or target.

        Args:
            project_id: Optional project ID to filter events
            target_id: Optional person ID to filter events

        Returns:
            List of event dictionaries
        """
        query = "SELECT * FROM events"
        params: list[Any] = []
        conditions: list[str] = []

        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)

        if target_id is not None:
            conditions.append("json_extract(target_ids, '$') LIKE ?")
            params.append(f"%{target_id}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id"

        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_event(row) for row in rows]

    def process_events_for_tick(
        self,
        tick: int,
        people: Sequence[PersonRead],
        hours_per_day: int,
        status_overrides: dict[int, tuple[str, int]],
        email_gateway: Any,
        chat_gateway: Any,
        sim_manager_email: str,
        queue_message_callback: Any,
        log_exchange_callback: Any,
        set_status_override_callback: Any,
    ) -> tuple[dict[int, list[str]], dict[int, list[InboundMessage]]]:
        """
        Process and generate events for the current tick.

        This includes both random event generation and processing of scheduled events.

        Args:
            tick: Current simulation tick
            people: Active people in the simulation
            hours_per_day: Hours per simulation day
            status_overrides: Current status overrides for workers
            email_gateway: Gateway for sending emails
            chat_gateway: Gateway for sending chats
            sim_manager_email: Email address of simulation manager
            queue_message_callback: Callback to queue messages for workers
            log_exchange_callback: Callback to log communication exchanges
            set_status_override_callback: Callback to set status overrides

        Returns:
            Tuple of (adjustments dict, immediate messages dict)
            - adjustments: Dict mapping person_id to list of adjustment strings
            - immediate: Dict mapping person_id to list of InboundMessage objects
        """
        adjustments: dict[int, list[str]] = {}
        immediate: dict[int, list[InboundMessage]] = {}

        if not people:
            return adjustments, immediate

        rng = self._random
        tick_of_day = (tick - 1) % max(1, hours_per_day)

        # Sick leave event: consider once per day around mid-morning (~10:00)
        if tick_of_day == int(60 * max(1, hours_per_day) / 480):
            # Roughly 5% daily chance across the team
            if rng.random() < 0.05:
                active_people = [p for p in people if status_overrides.get(p.id, (None, 0))[0] != "SickLeave"]
                if active_people:
                    target = rng.choice(active_people)
                    until_tick = tick + hours_per_day
                    set_status_override_callback(
                        target.id, "SickLeave", until_tick, f"Sick leave triggered at tick {tick}"
                    )

                    loc_manager = get_current_locale_manager()
                    rest_message = InboundMessage(
                        sender_id=0,
                        sender_name="Simulation Manager",
                        subject=loc_manager.get_text("rest_and_recover"),
                        summary=loc_manager.get_text("rest_and_recover_body"),
                        action_item=loc_manager.get_text("rest_and_recover_action"),
                        message_type="event",
                        channel="system",
                        tick=tick,
                    )
                    queue_message_callback(target, rest_message)
                    immediate.setdefault(target.id, []).append(rest_message)
                    adjustments.setdefault(target.id, []).append("Rest and reschedule tasks due to sudden illness.")

                    # Notify department head
                    head = next((p for p in people if getattr(p, "is_department_head", False)), None)
                    if head and head.id != target.id:
                        subject = loc_manager.get_template("coverage_needed", name=target.name)
                        body = loc_manager.get_template("coverage_needed_body", name=target.name, tick=tick)
                        email_gateway.send_email(
                            sender=sim_manager_email,
                            to=[head.email_address],
                            subject=subject,
                            body=body,
                        )
                        log_exchange_callback(tick, None, head.id, "email", subject, body)

                        head_message = InboundMessage(
                            sender_id=0,
                            sender_name="Simulation Manager",
                            subject=subject,
                            summary=body,
                            action_item=f"Coordinate cover for {target.name}.",
                            message_type="event",
                            channel="email",
                            tick=tick,
                        )
                        queue_message_callback(head, head_message)
                        immediate.setdefault(head.id, []).append(head_message)
                        adjustments.setdefault(head.id, []).append(f"Coordinate cover while {target.name} recovers.")

                    # Record the event
                    self._record_event("sick_leave", [target.id], tick, {"until_tick": until_tick})

        # Client feature request: at most a few times per day (every ~2 hours), low probability
        interval_ticks = max(1, int(120 * max(1, hours_per_day) / 480))
        if (tick_of_day % interval_ticks == 0) and (rng.random() < 0.10):
            head = next((p for p in people if getattr(p, "is_department_head", False)), people[0])
            loc_manager = get_current_locale_manager()
            feature_requests = loc_manager.get_list("client_feature_requests")
            feature = rng.choice(feature_requests)
            subject = loc_manager.get_template("client_request_subject", feature=feature)
            body = loc_manager.get_template("client_request_body", feature=feature)
            action_item = loc_manager.get_template("client_request_action", feature=feature)

            head_message = InboundMessage(
                sender_id=0,
                sender_name="Simulation Manager",
                subject=subject,
                summary=body,
                action_item=action_item,
                message_type="event",
                channel="email",
                tick=tick,
            )
            queue_message_callback(head, head_message)
            immediate.setdefault(head.id, []).append(head_message)
            adjustments.setdefault(head.id, []).append(f"Plan response to client request: {feature}.")

            # Assign a collaborator
            collaborators = [p for p in people if p.id != head.id]
            if collaborators:
                partner = rng.choice(collaborators)
                partner_message = InboundMessage(
                    sender_id=head.id,
                    sender_name=head.name,
                    subject=subject,
                    summary=loc_manager.get_template("partner_with", name=head.name, feature=feature),
                    action_item=loc_manager.get_template("support_on", name=head.name, feature=feature),
                    message_type="event",
                    channel="chat",
                    tick=tick,
                )
                queue_message_callback(partner, partner_message)
                immediate.setdefault(partner.id, []).append(partner_message)
                adjustments.setdefault(partner.id, []).append(f"Partner with {head.name} on client request: {feature}.")
                targets = [head.id, partner.id]
            else:
                targets = [head.id]

            self._record_event("client_feature_request", targets, tick, {"feature": feature})

        return adjustments, immediate

    def convert_event_to_adjustments(self, event: dict, person: PersonRead) -> list[str]:
        """
        Convert an event into adjustment strings for a specific person.

        Args:
            event: Event dictionary with type, payload, etc.
            person: Person affected by the event

        Returns:
            List of adjustment strings to guide planning
        """
        adjustments: list[str] = []
        event_type = event.get("type", "")
        payload = event.get("payload", {})

        if event_type == "sick_leave":
            adjustments.append("Rest and reschedule tasks due to sudden illness.")
        elif event_type == "client_feature_request":
            feature = payload.get("feature", "new feature")
            adjustments.append(f"Plan response to client request: {feature}.")
        elif event_type == "blocker":
            blocker_desc = payload.get("description", "dependency issue")
            adjustments.append(f"Address blocker: {blocker_desc}.")
        elif event_type == "meeting":
            meeting_topic = payload.get("topic", "team sync")
            adjustments.append(f"Attend meeting: {meeting_topic}.")

        return adjustments

    def _record_event(self, event_type: str, target_ids: Sequence[int], tick: int, payload: dict | None = None) -> None:
        """
        Record an event to the database.

        Args:
            event_type: Type of event (sick_leave, client_feature_request, etc.)
            target_ids: List of person IDs affected by the event
            tick: Tick when the event occurred
            payload: Optional additional event data
        """
        event = EventCreate(type=event_type, target_ids=list(target_ids), at_tick=tick, payload=payload)
        self.inject_event(event)

    def _row_to_event(self, row) -> dict:
        """
        Convert a database row to an event dictionary.

        Args:
            row: Database row from events table

        Returns:
            Event dictionary
        """
        return {
            "id": row["id"],
            "type": row["type"],
            "target_ids": json.loads(row["target_ids"] or "[]"),
            "project_id": row["project_id"],
            "at_tick": row["at_tick"],
            "payload": json.loads(row["payload"] or "{}"),
        }
