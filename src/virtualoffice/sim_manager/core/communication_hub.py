"""
CommunicationHub Module

Handles all communication scheduling, parsing, and dispatch for the simulation engine.
Responsibilities:
- Parse hourly plans for scheduled communications
- Manage email and chat message scheduling
- Handle message deduplication and cooldown logic
- Support email threading (reply-to, thread_id)
- Route group chat vs DM messages
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections import deque
from typing import Any

from virtualoffice.common.localization import get_current_locale_manager

from ..gateways import ChatGateway, EmailGateway
from ..schemas import PersonRead
from .tick_manager import TickManager

logger = logging.getLogger(__name__)


class CommunicationHub:
    """
    Centralized communication management for the simulation.

    Handles:
    - Parsing communication schedules from hourly plans
    - Scheduling emails and chats for future ticks
    - Dispatching scheduled communications at the right time
    - Message deduplication and cooldown enforcement
    - Email threading support
    - Group chat vs DM routing
    """

    def __init__(
        self,
        email_gateway: EmailGateway,
        chat_gateway: ChatGateway,
        tick_manager: TickManager,
        cooldown_ticks: int = 10,
    ) -> None:
        """
        Initialize the CommunicationHub.

        Args:
            email_gateway: Gateway for sending emails
            chat_gateway: Gateway for sending chat messages
            tick_manager: Manager for time-related operations
            cooldown_ticks: Minimum ticks between messages to same recipient
        """
        self.email_gateway = email_gateway
        self.chat_gateway = chat_gateway
        self.tick_manager = tick_manager
        self._contact_cooldown_ticks = cooldown_ticks

        # Message throttling / deduplication
        self._sent_dedup: set[tuple] = set()
        self._last_contact: dict[tuple, int] = {}

        # Scheduled comms: person_id -> { tick -> [action dicts] }
        self._scheduled_comms: dict[int, dict[int, list[dict[str, Any]]]] = {}

        # Email threading support
        self._recent_emails: dict[int, deque] = {}  # {person_id: deque of recent emails}
        self._email_threads: dict[str, str] = {}  # {thread_key: thread_id}

    def reset_tick_sends(self) -> None:
        """Clear deduplication tracking for a new tick."""
        self._sent_dedup.clear()

    def can_send(
        self, *, tick: int, channel: str, sender: str, recipient_key: tuple, subject: str | None, body: str
    ) -> bool:
        """
        Check if a message can be sent based on deduplication and cooldown rules.

        Args:
            tick: Current simulation tick
            channel: Communication channel ('email' or 'chat')
            sender: Sender identifier (email or chat handle)
            recipient_key: Tuple of recipient identifiers
            subject: Email subject (None for chat)
            body: Message body

        Returns:
            True if message can be sent, False if blocked by dedup/cooldown
        """
        body_key = body.strip()
        dedup = (tick, channel, sender, recipient_key, subject or "", body_key)
        if dedup in self._sent_dedup:
            return False

        cooldown_key = (channel, sender, recipient_key)
        last = self._last_contact.get(cooldown_key)
        if last is not None and tick - last < self._contact_cooldown_ticks:
            return False

        self._sent_dedup.add(dedup)
        self._last_contact[cooldown_key] = tick
        return True

    def schedule_from_hourly_plan(
        self, person: PersonRead, plan_text: str, current_tick: int, hours_per_day: int
    ) -> None:
        """
        Parse hourly plan text and schedule communications for future ticks.

        Supports formats:
        - Email at HH:MM to PERSON: Subject | Body
        - Email at HH:MM to PERSON cc PERSON2: Subject | Body
        - Reply at HH:MM to [email-id]: Subject | Body
        - Chat at HH:MM to/with PERSON: Message

        Args:
            person: Person whose plan is being parsed
            plan_text: The hourly plan text to parse
            current_tick: Current simulation tick
            hours_per_day: Ticks per day for time calculations
        """
        ticks_per_day = max(1, hours_per_day)
        day_index = (current_tick - 1) // ticks_per_day
        tick_of_day = (current_tick - 1) % ticks_per_day
        base_tick = day_index * ticks_per_day + 1

        lines = [ln.strip() for ln in plan_text.splitlines() if ln.strip()]
        if not lines:
            return

        sched = self._scheduled_comms.setdefault(person.id, {})

        # Accept optional cc/bcc prior to ':'
        email_re = re.compile(
            r"^Email\s+at\s+(\d{2}:\d{2})\s+to\s+([^:]+?)"
            r"(?:\s+cc\s+([^:]+?))?"
            r"(?:\s+bcc\s+([^:]+?))?\s*:\s*(.*)$",
            re.I,
        )
        # Reply to email syntax: "Reply at HH:MM to [email-id] cc PERSON: Subject | Body"
        reply_re = re.compile(
            r"^Reply\s+at\s+(\d{2}:\d{2})\s+to\s+\[([^\]]+)\]"
            r"(?:\s+cc\s+([^:]+?))?"
            r"(?:\s+bcc\s+([^:]+?))?\s*:\s*(.*)$",
            re.I,
        )
        chat_re = re.compile(r"^Chat\s+at\s+(\d{2}:\d{2})\s+(?:with|to)\s+([^:]+):\s*(.*)$", re.I)

        for ln in lines:
            m = email_re.match(ln)
            channel = None
            when = None
            target = None
            payload = ""
            cc_raw = None
            bcc_raw = None
            reply_to_email_id = None

            if m:
                channel = "email"
                when = m.group(1)
                target = (m.group(2) or "").strip()
                cc_raw = (m.group(3) or "").strip()
                bcc_raw = (m.group(4) or "").strip()
                payload = (m.group(5) or "").strip()
            else:
                # Try reply syntax
                m = reply_re.match(ln)
                if m:
                    channel = "email"
                    when = m.group(1)
                    reply_to_email_id = (m.group(2) or "").strip()
                    cc_raw = (m.group(3) or "").strip()
                    bcc_raw = (m.group(4) or "").strip()
                    payload = (m.group(5) or "").strip()
                    # target will be determined from the parent email
                else:
                    m = chat_re.match(ln)
                    if m:
                        channel = "chat"
                        when, target, payload = m.group(1), m.group(2).strip(), m.group(3).strip()

            if not channel:
                continue

            try:
                hh, mm = [int(x) for x in when.split(":", 1)]
                minutes = hh * 60 + mm
                scheduled_tick_of_day = int(round(minutes * ticks_per_day / 1440))
            except Exception:
                continue

            if scheduled_tick_of_day <= tick_of_day:
                continue

            t = base_tick + scheduled_tick_of_day
            entry = {"channel": channel, "target": target, "payload": payload}
            if reply_to_email_id:
                entry["reply_to_email_id"] = reply_to_email_id
            if cc_raw:
                entry["cc"] = [x.strip() for x in cc_raw.split(",") if x.strip()]
            if bcc_raw:
                entry["bcc"] = [x.strip() for x in bcc_raw.split(",") if x.strip()]

            # Deduplicate: check if identical entry already scheduled for this tick
            existing = sched.setdefault(t, [])
            if entry not in existing:
                existing.append(entry)

    def get_thread_id_for_reply(self, person_id: int, email_id: str) -> tuple[str | None, str | None]:
        """
        Look up thread_id and original sender from email-id in recent emails.

        Args:
            person_id: ID of person looking up the email
            email_id: Email ID to look up

        Returns:
            Tuple of (thread_id, original_sender_email) or (None, None) if not found
        """
        recent = self._recent_emails.get(person_id, [])
        for email in recent:
            if email.get("email_id") == email_id:
                return email.get("thread_id"), email.get("from")
        return None, None

    def get_recent_emails_for_person(self, person_id: int, limit: int = 10) -> list[dict]:
        """
        Get recent emails for a person for context building.

        Args:
            person_id: ID of person
            limit: Maximum number of emails to return

        Returns:
            List of recent email records
        """
        recent = self._recent_emails.get(person_id, [])
        return list(recent)[-limit:]

    def dispatch_scheduled(
        self,
        person: PersonRead,
        current_tick: int,
        people_by_id: dict[int, PersonRead],
        get_current_week_fn: callable,
        get_active_projects_fn: callable,
        get_project_chat_room_fn: callable,
    ) -> tuple[int, int]:
        """
        Dispatch all scheduled communications for a person at the current tick.

        Args:
            person: Person sending the messages
            current_tick: Current simulation tick
            people_by_id: Dictionary of all people by ID
            get_current_week_fn: Function to get current simulation week
            get_active_projects_fn: Function to get active projects for person
            get_project_chat_room_fn: Function to get project chat room slug

        Returns:
            Tuple of (emails_sent, chats_sent)
        """
        emails = chats = 0
        by_tick = self._scheduled_comms.get(person.id) or {}
        actions = by_tick.pop(current_tick, [])
        if not actions:
            return 0, 0

        # Helper to avoid simultaneous mirrored DMs
        # handle_index = {p.chat_handle.lower(): p for p in people_by_id.values()}  # Reserved for future use
        # Email index for quick lookups when suggesting CCs
        email_index = {p.email_address.lower(): p for p in people_by_id.values()}

        # Build valid email set from team roster + external stakeholders
        valid_emails = {p.email_address.lower() for p in people_by_id.values()}
        # Get external stakeholders from environment (comma-separated list)
        external_stakeholders = set()
        external_env = os.getenv("VDOS_EXTERNAL_STAKEHOLDERS", "")
        if external_env.strip():
            external_stakeholders = {addr.strip().lower() for addr in external_env.split(",") if addr.strip()}
        all_valid_emails = valid_emails | external_stakeholders

        def _match_target(raw: str) -> tuple[str | None, str | None]:
            val = raw.strip().lower()

            # Check for group chat keywords
            if val in ["team", "project", "group", "everyone"]:
                return None, val  # Return as chat target for group routing

            # Check team roster email addresses
            for p in people_by_id.values():
                if p.email_address.lower() == val:
                    return p.email_address, None
            # Check chat handles
            for p in people_by_id.values():
                if p.chat_handle.lower() == val or f"@{p.chat_handle.lower()}" == val:
                    return None, p.chat_handle
            # Check names
            for p in people_by_id.values():
                if p.name.lower() == val:
                    return p.email_address, p.chat_handle
            # Check if looks like email - validate against allowed list
            if "@" in val:
                normalized = val.strip()
                if normalized in all_valid_emails:
                    # Return original casing from team roster or external list
                    for p in people_by_id.values():
                        if p.email_address.lower() == normalized:
                            return p.email_address, None
                    # External stakeholder - return normalized
                    return normalized, None
                else:
                    # REJECT hallucinated email addresses
                    logger.warning(f"Rejecting hallucinated email address: {raw}")
                    return None, None
            return None, raw.strip()

        dt = self.tick_manager.sim_datetime_for_tick(current_tick)
        dt_iso = dt.isoformat() if dt else None

        # Heuristic: when no CC explicitly provided, suggest dept head and one relevant peer
        def _suggest_cc(primary_to_email: str) -> list[str]:
            cc_list: list[str] = []
            primary = email_index.get((primary_to_email or "").lower())
            # Department head first
            dept_head = None
            for p in people_by_id.values():
                if getattr(p, "is_department_head", False):
                    dept_head = p
                    break
            if dept_head and dept_head.email_address.lower() not in {
                person.email_address.lower(),
                (primary_to_email or "").lower(),
            }:
                cc_list.append(dept_head.email_address)

            # Pick one relevant peer based on roles
            def _role(s: str | None) -> str:
                return (s or "").strip().lower()

            s_role = _role(getattr(person, "role", None))
            p_role = _role(getattr(primary, "role", None)) if primary else ""
            want_peer = None
            for r in (s_role, p_role):
                if not r:
                    continue
                if "devops" in r or "site reliability" in r:
                    want_peer = "dev"
                    break
                if "developer" in r or "engineer" in r or "dev" in r:
                    want_peer = "designer"
                    break
                if "design" in r or "designer" in r:
                    want_peer = "dev"
                    break
                if "product" in r or "pm" in r or "manager" in r:
                    want_peer = "dev"
                    break
            if want_peer:
                for p in people_by_id.values():
                    if p.id == person.id:
                        continue
                    if primary and p.id == primary.id:
                        continue
                    if want_peer in _role(getattr(p, "role", None)):
                        email = p.email_address
                        if email and email.lower() not in {
                            person.email_address.lower(),
                            (primary_to_email or "").lower(),
                        }:
                            cc_list.append(email)
                            break
            # Dedupe preserving order
            seen: set[str] = set()
            out: list[str] = []
            for em in cc_list:
                low = em.lower()
                if low not in seen:
                    seen.add(low)
                    out.append(em)
            return out

        for act in actions:
            channel = act.get("channel")
            target = act.get("target") or ""
            payload = act.get("payload") or ""
            reply_to_email_id = act.get("reply_to_email_id")
            thread_id = None

            # Handle reply syntax - lookup parent email and thread_id
            if reply_to_email_id:
                thread_id, original_sender = self.get_thread_id_for_reply(person.id, reply_to_email_id)
                if original_sender:
                    # If we found the parent email, reply to its sender
                    target = original_sender
                else:
                    # If email-id not found, log warning and skip
                    logger.warning(f"Reply email-id [{reply_to_email_id}] not found in recent emails for {person.name}")
                    continue

            email_to, chat_to = _match_target(target)
            if channel == "email" and email_to:
                # Parse "Subject | Body" format from payload
                if " | " in payload:
                    parts = payload.split(" | ", 1)  # Split only on first occurrence
                    subject = parts[0].strip()
                    body = parts[1].strip()
                else:
                    # Fallback to generic subject if no pipe separator
                    subject = get_current_locale_manager().get_template("update_generic", name=person.name)
                    body = payload

                cc_raw = act.get("cc") or []
                bcc_raw = act.get("bcc") or []

                def _resolve_emails(raw_list: list[str]) -> list[str]:
                    out: list[str] = []
                    for tok in raw_list:
                        # Clean parsing artifacts like "bcc", "cc" from address
                        cleaned_tok = tok.strip()
                        # Remove "bcc" or "cc" suffix/prefix and other parsing artifacts
                        for keyword in [" bcc", " cc", "bcc ", "cc ", "bcc", "cc"]:
                            cleaned_tok = cleaned_tok.replace(keyword, "").strip()
                        # Skip empty strings after cleaning
                        if not cleaned_tok:
                            continue
                        em, _ = _match_target(cleaned_tok)
                        if em:
                            out.append(em)
                    # dedupe preserving order
                    seen = set()
                    uniq = []
                    for em in out:
                        if em not in seen:
                            seen.add(em)
                            uniq.append(em)
                    return uniq

                cc_emails = _resolve_emails(list(cc_raw))
                if not cc_emails:
                    cc_emails = _suggest_cc(email_to)
                bcc_emails = _resolve_emails(list(bcc_raw))
                recipients_key = tuple(sorted({email_to, *cc_emails, *bcc_emails}))

                # Generate new thread_id if this is not a reply
                if thread_id is None:
                    thread_id = f"thread-{uuid.uuid4().hex[:16]}"

                if self.can_send(
                    tick=current_tick,
                    channel="email",
                    sender=person.email_address,
                    recipient_key=recipients_key,
                    subject=subject,
                    body=body,
                ):
                    result = self.email_gateway.send_email(
                        sender=person.email_address,
                        to=[email_to],
                        subject=subject,
                        body=body,
                        cc=cc_emails,
                        bcc=bcc_emails,
                        thread_id=thread_id,
                        sent_at_iso=dt_iso,
                    )
                    emails += 1

                    # Track sent email for threading context (store email_id if available)
                    if result and isinstance(result, dict):
                        email_id = result.get("id", f"email-{current_tick}-{emails}")
                        email_record = {
                            "email_id": email_id,
                            "from": person.email_address,
                            "to": email_to,
                            "subject": subject,
                            "thread_id": thread_id,
                            "sent_at_tick": current_tick,
                        }
                        # Add to sender's recent emails
                        if person.id not in self._recent_emails:
                            self._recent_emails[person.id] = deque(maxlen=10)
                        self._recent_emails[person.id].append(email_record)

                        # Also add to all recipients' recent emails for their context
                        for recipient_addr in [email_to, *cc_emails]:
                            recipient_person = email_index.get(recipient_addr.lower())
                            if recipient_person:
                                if recipient_person.id not in self._recent_emails:
                                    self._recent_emails[recipient_person.id] = deque(maxlen=10)
                                self._recent_emails[recipient_person.id].append(email_record)

            elif channel == "chat" and chat_to:
                # Check if this should go to project group chat or DM
                if chat_to.lower() in ["team", "project", "group", "everyone"]:
                    # Send to project group chat
                    current_week = get_current_week_fn()
                    active_projects = get_active_projects_fn(person.id, current_week)

                    if active_projects:
                        # Use the first active project's chat room
                        project = active_projects[0]
                        room_slug = get_project_chat_room_fn(project["id"])

                        if room_slug and self.can_send(
                            tick=current_tick,
                            channel="chat",
                            sender=person.chat_handle,
                            recipient_key=(room_slug,),
                            subject=None,
                            body=payload,
                        ):
                            try:
                                self.chat_gateway.send_room_message(
                                    room_slug=room_slug, sender=person.chat_handle, body=payload, sent_at_iso=dt_iso
                                )
                                chats += 1
                            except Exception as exc:
                                logger.warning(f"Failed to send group chat message: {exc}")
                else:
                    # Send as DM - keep existing logic
                    # Deterministic guard: only the lexicographically smaller handle sends to avoid mirrored DMs.
                    s_handle = person.chat_handle.lower()
                    r_handle = chat_to.lower()
                    if s_handle > r_handle:
                        continue
                    if self.can_send(
                        tick=current_tick,
                        channel="chat",
                        sender=person.chat_handle,
                        recipient_key=(chat_to,),
                        subject=None,
                        body=payload,
                    ):
                        self.chat_gateway.send_dm(
                            sender=person.chat_handle, recipient=chat_to, body=payload, sent_at_iso=dt_iso
                        )
                        chats += 1

        return emails, chats

    def schedule_direct_comm(self, person_id: int, tick: int, channel: str, target: str, payload: str) -> None:
        """
        Directly schedule a communication for a specific tick.

        Args:
            person_id: ID of person sending the message
            tick: Tick at which to send the message
            channel: Communication channel ('email' or 'chat')
            target: Target recipient
            payload: Message content
        """
        by_tick = self._scheduled_comms.setdefault(person_id, {})
        by_tick.setdefault(tick, []).append({"channel": channel, "target": target, "payload": payload})
