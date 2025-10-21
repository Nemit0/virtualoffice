from __future__ import annotations

import json
import os
import hashlib
import logging
import random
import time
import threading
import math
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Sequence, Tuple

from virtualoffice.common.db import execute_script, get_connection
from virtualoffice.virtualWorkers.worker import (
    ScheduleBlock,
    WorkerPersona,
    build_worker_markdown,
    render_minute_schedule,
)

from .gateways import ChatGateway, EmailGateway
from .planner import GPTPlanner, PlanResult, Planner, PlanningError, StubPlanner
from .schemas import (
    EventCreate,
    PersonCreate,
    PersonRead,
    ScheduleBlockIn,
    SimulationAdvanceResult,
    SimulationStartRequest,
    SimulationState,
)

logger = logging.getLogger(__name__)

@dataclass
class _InboundMessage:
    sender_id: int
    sender_name: str
    subject: str
    summary: str
    action_item: str | None
    message_type: str
    channel: str
    tick: int
    message_id: int | None = None


@dataclass
class _WorkerRuntime:
    person: PersonRead
    inbox: list[_InboundMessage] = field(default_factory=list)

    def queue(self, message: _InboundMessage) -> None:
        self.inbox.append(message)

    def drain(self) -> list[_InboundMessage]:
        items = self.inbox
        self.inbox = []
        return items

SIM_SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    timezone TEXT NOT NULL,
    work_hours TEXT NOT NULL,
    break_frequency TEXT NOT NULL,
    communication_style TEXT NOT NULL,
    email_address TEXT NOT NULL,
    chat_handle TEXT NOT NULL,
    is_department_head INTEGER NOT NULL DEFAULT 0,
    team_name TEXT,
    skills TEXT NOT NULL,
    personality TEXT NOT NULL,
    objectives TEXT NOT NULL,
    metrics TEXT NOT NULL,
    persona_markdown TEXT NOT NULL,
    planning_guidelines TEXT NOT NULL,
    event_playbook TEXT NOT NULL,
    statuses TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schedule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    activity TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS simulation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_tick INTEGER NOT NULL,
    is_running INTEGER NOT NULL,
    auto_tick INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tick_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    target_ids TEXT NOT NULL,
    project_id TEXT,
    at_tick INTEGER,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS project_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    project_summary TEXT NOT NULL,
    plan TEXT NOT NULL,
    generated_by INTEGER,
    duration_weeks INTEGER NOT NULL,
    start_week INTEGER NOT NULL DEFAULT 1,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(generated_by) REFERENCES people(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS project_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES project_plans(id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
    UNIQUE(project_id, person_id)
);

CREATE TABLE IF NOT EXISTS worker_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    plan_type TEXT NOT NULL,
    content TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    context TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS hourly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    hour_index INTEGER NOT NULL,
    summary TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
    UNIQUE(person_id, hour_index)
);

CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    day_index INTEGER NOT NULL,
    report TEXT NOT NULL,
    schedule_outline TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS simulation_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER,
    total_ticks INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS worker_runtime_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(recipient_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worker_exchange_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    sender_id INTEGER,
    recipient_id INTEGER,
    channel TEXT NOT NULL,
    subject TEXT,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(sender_id) REFERENCES people(id) ON DELETE SET NULL,
    FOREIGN KEY(recipient_id) REFERENCES people(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS worker_status_overrides (
    worker_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    until_tick INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(worker_id) REFERENCES people(id) ON DELETE CASCADE
);

"""


@dataclass
class SimulationStatus:
    current_tick: int
    is_running: bool
    auto_tick: bool


class SimulationEngine:
    def __init__(
        self,
        email_gateway: EmailGateway,
        chat_gateway: ChatGateway,
        sim_manager_email: str = "simulator@vdos.local",
        sim_manager_handle: str = "sim-manager",
        planner: Planner | None = None,
        hours_per_day: int = 8,
        tick_interval_seconds: float = 1.0,
        planner_strict: bool | None = None,
    ) -> None:
        self.email_gateway = email_gateway
        self.chat_gateway = chat_gateway
        self.sim_manager_email = sim_manager_email
        self.sim_manager_handle = sim_manager_handle
        self.planner = planner or GPTPlanner()
        self._stub_planner = StubPlanner()
        self.hours_per_day = hours_per_day
        self.project_duration_weeks = 4
        self._project_plan_cache: dict[str, Any] | None = None
        self._planner_model_hint: str | None = None
        self._tick_interval_seconds = tick_interval_seconds
        self._auto_tick_thread: threading.Thread | None = None
        self._auto_tick_stop: threading.Event | None = None
        self._advance_lock = threading.Lock()
        self._worker_runtime: dict[int, _WorkerRuntime] = {}
        self._status_overrides: dict[int, Tuple[str, int]] = {}
        self._active_person_ids: list[int] | None = None
        self._work_hours_ticks: dict[int, tuple[int, int]] = {}
        self._random = random.Random()
        self._planner_metrics: deque[dict[str, Any]] = deque(maxlen=200)
        # Locale (simple toggle for certain strings)
        self._locale = (os.getenv("VDOS_LOCALE", "en").strip().lower() or "en")
        self._planner_metrics_lock = threading.Lock()
        # Email threading support
        self._recent_emails: dict[int, deque] = {}  # {person_id: deque of recent emails}
        self._email_threads: dict[str, str] = {}  # {thread_key: thread_id}
        # Planner strict mode: if True, do not fall back to stub on GPT failures
        if planner_strict is None:
            env = os.getenv("VDOS_PLANNER_STRICT", "0").strip().lower()
            self._planner_strict = env in {"1", "true", "yes", "on"}
        else:
            self._planner_strict = bool(planner_strict)
        # Message throttling / deduplication
        self._sent_dedup: set[tuple] = set()
        try:
            # Default cooldown prevents spammy repeats; override via env
            self._contact_cooldown_ticks = int(os.getenv("VDOS_CONTACT_COOLDOWN_TICKS", "10"))
        except ValueError:
            self._contact_cooldown_ticks = 0
        # Hourly planning limiter to prevent endless replanning within the same minute
        try:
            self._max_hourly_plans_per_minute = int(os.getenv("VDOS_MAX_HOURLY_PLANS_PER_MINUTE", "10"))
        except ValueError:
            self._max_hourly_plans_per_minute = 10
        # (person_id, day_index, tick_of_day) -> attempts
        self._hourly_plan_attempts: dict[tuple[int, int, int], int] = {}
        # Scheduled comms: person_id -> { tick -> [action dicts] }
        self._scheduled_comms: dict[int, dict[int, list[dict[str, Any]]]] = {}
        self._last_contact: dict[tuple, int] = {}
        self._sim_base_dt: datetime | None = None
        # Parallel planning configuration
        try:
            self._max_planning_workers = int(os.getenv("VDOS_MAX_PLANNING_WORKERS", "4"))
        except ValueError:
            self._max_planning_workers = 4
        self._planning_executor: ThreadPoolExecutor | None = None
        if self._max_planning_workers > 1:
            self._planning_executor = ThreadPoolExecutor(max_workers=self._max_planning_workers, thread_name_prefix="planner")
        # Initialise DB and runtime state
        execute_script(SIM_SCHEMA)
        self._apply_migrations()
        self._ensure_state_row()
        self._bootstrap_channels()
        self._load_status_overrides()
        self._sync_worker_runtimes(self.list_people())

    def _reset_tick_sends(self) -> None:
        self._sent_dedup.clear()

    def _can_send(self, *, tick: int, channel: str, sender: str, recipient_key: tuple, subject: str | None, body: str) -> bool:
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
    
    # --- Scheduled comms parsing/dispatch ---
    def _schedule_from_hourly_plan(self, person: PersonRead, plan_text: str, current_tick: int) -> None:
        import re
        ticks_per_day = max(1, self.hours_per_day)
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
                channel = 'email'
                when = m.group(1)
                target = (m.group(2) or '').strip()
                cc_raw = (m.group(3) or '').strip()
                bcc_raw = (m.group(4) or '').strip()
                payload = (m.group(5) or '').strip()
            else:
                # Try reply syntax
                m = reply_re.match(ln)
                if m:
                    channel = 'email'
                    when = m.group(1)
                    reply_to_email_id = (m.group(2) or '').strip()
                    cc_raw = (m.group(3) or '').strip()
                    bcc_raw = (m.group(4) or '').strip()
                    payload = (m.group(5) or '').strip()
                    # target will be determined from the parent email
                else:
                    m = chat_re.match(ln)
                    if m:
                        channel = 'chat'
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
            entry = {'channel': channel, 'target': target, 'payload': payload}
            if reply_to_email_id:
                entry['reply_to_email_id'] = reply_to_email_id
            if cc_raw:
                entry['cc'] = [x.strip() for x in cc_raw.split(',') if x.strip()]
            if bcc_raw:
                entry['bcc'] = [x.strip() for x in bcc_raw.split(',') if x.strip()]

            # Deduplicate: check if identical entry already scheduled for this tick
            existing = sched.setdefault(t, [])
            if entry not in existing:
                existing.append(entry)

    def _get_thread_id_for_reply(self, person_id: int, email_id: str) -> tuple[str | None, str | None]:
        """Look up thread_id and original sender from email-id in recent emails.
        Returns (thread_id, original_sender_email) or (None, None) if not found.
        """
        recent = self._recent_emails.get(person_id, [])
        for email in recent:
            if email.get('email_id') == email_id:
                return email.get('thread_id'), email.get('from')
        return None, None

    def _dispatch_scheduled(self, person: PersonRead, current_tick: int, people_by_id: dict[int, PersonRead]) -> tuple[int, int]:
        emails = chats = 0
        by_tick = self._scheduled_comms.get(person.id) or {}
        actions = by_tick.pop(current_tick, [])
        if not actions:
            return 0, 0
        # Helper to avoid simultaneous mirrored DMs: if both sides scheduled the same message
        # at the same minute, only the lower-id sender will fire.
        handle_index = {p.chat_handle.lower(): p for p in people_by_id.values()}
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
        dt = self._sim_datetime_for_tick(current_tick)
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
            channel = act.get('channel')
            target = act.get('target') or ""
            payload = act.get('payload') or ""
            reply_to_email_id = act.get('reply_to_email_id')
            thread_id = None

            # Handle reply syntax - lookup parent email and thread_id
            if reply_to_email_id:
                thread_id, original_sender = self._get_thread_id_for_reply(person.id, reply_to_email_id)
                if original_sender:
                    # If we found the parent email, reply to its sender
                    target = original_sender
                else:
                    # If email-id not found, log warning and skip
                    logger.warning(f"Reply email-id [{reply_to_email_id}] not found in recent emails for {person.name}")
                    continue

            email_to, chat_to = _match_target(target)
            if channel == 'email' and email_to:
                subject = f"{'업데이트' if self._locale == 'ko' else 'Update'}: {person.name}"
                cc_raw = act.get('cc') or []
                bcc_raw = act.get('bcc') or []
                def _resolve_emails(raw_list: list[str]) -> list[str]:
                    out: list[str] = []
                    for tok in raw_list:
                        # Clean parsing artifacts like "bcc", "cc" from address
                        cleaned_tok = tok.strip()
                        # Remove "bcc" or "cc" suffix/prefix and other parsing artifacts
                        for keyword in [' bcc', ' cc', 'bcc ', 'cc ', 'bcc', 'cc']:
                            cleaned_tok = cleaned_tok.replace(keyword, '').strip()
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

                if self._can_send(tick=current_tick, channel='email', sender=person.email_address, recipient_key=recipients_key, subject=subject, body=payload):
                    result = self.email_gateway.send_email(
                        sender=person.email_address,
                        to=[email_to],
                        subject=subject,
                        body=payload,
                        cc=cc_emails,
                        bcc=bcc_emails,
                        thread_id=thread_id,
                        sent_at_iso=dt_iso
                    )
                    emails += 1

                    # Track sent email for threading context (store email_id if available)
                    if result and isinstance(result, dict):
                        email_id = result.get('id', f'email-{current_tick}-{emails}')
                        email_record = {
                            'email_id': email_id,
                            'from': person.email_address,
                            'to': email_to,
                            'subject': subject,
                            'thread_id': thread_id,
                            'sent_at_tick': current_tick,
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
            elif channel == 'chat' and chat_to:
                # Deterministic guard: only the lexicographically smaller handle sends to avoid mirrored DMs.
                s_handle = person.chat_handle.lower()
                r_handle = chat_to.lower()
                if s_handle > r_handle:
                    continue
                if self._can_send(tick=current_tick, channel='chat', sender=person.chat_handle, recipient_key=(chat_to,), subject=None, body=payload):
                    self.chat_gateway.send_dm(sender=person.chat_handle, recipient=chat_to, body=payload, sent_at_iso=dt_iso)
                    chats += 1
        return emails, chats
    def _schedule_direct_comm(self, person_id: int, tick: int, channel: str, target: str, payload: str) -> None:
        by_tick = self._scheduled_comms.setdefault(person_id, {})
        by_tick.setdefault(tick, []).append({'channel': channel, 'target': target, 'payload': payload})

    def _apply_migrations(self) -> None:
        with get_connection() as conn:
            people_columns = {row["name"] for row in conn.execute("PRAGMA table_info(people)")}
            if "is_department_head" not in people_columns:
                conn.execute("ALTER TABLE people ADD COLUMN is_department_head INTEGER NOT NULL DEFAULT 0")
            if "team_name" not in people_columns:
                conn.execute("ALTER TABLE people ADD COLUMN team_name TEXT")
            state_columns = {row["name"] for row in conn.execute("PRAGMA table_info(simulation_state)")}
            if "auto_tick" not in state_columns:
                conn.execute("ALTER TABLE simulation_state ADD COLUMN auto_tick INTEGER NOT NULL DEFAULT 0")
            # Multi-project support migrations
            project_columns = {row["name"] for row in conn.execute("PRAGMA table_info(project_plans)")}
            if "start_week" not in project_columns:
                conn.execute("ALTER TABLE project_plans ADD COLUMN start_week INTEGER NOT NULL DEFAULT 1")

    def _parse_time_to_tick(self, time_str: str, *, round_up: bool = False) -> int:
        try:
            hours, minutes = time_str.split(':')
            total_minutes = int(hours) * 60 + int(minutes)
        except Exception:
            return 0
        ticks_per_day = max(1, self.hours_per_day)
        ticks_float = (total_minutes / 1440) * ticks_per_day
        if round_up:
            tick = math.ceil(ticks_float)
        else:
            tick = math.floor(ticks_float)
        return max(0, min(ticks_per_day, tick))

    def _parse_work_hours_to_ticks(self, work_hours: str) -> tuple[int, int]:
        ticks_per_day = max(1, self.hours_per_day)
        if ticks_per_day < 6:
            return (0, ticks_per_day)
        if not work_hours or '-' not in work_hours:
            return (0, ticks_per_day)
        start_str, end_str = [segment.strip() for segment in work_hours.split('-', 1)]
        start_tick = self._parse_time_to_tick(start_str, round_up=False)
        end_tick = self._parse_time_to_tick(end_str, round_up=True)
        start_tick = max(0, min(ticks_per_day - 1, start_tick))
        end_tick = max(0, min(ticks_per_day, end_tick))
        if start_tick == end_tick:
            return (0, ticks_per_day)
        return (start_tick, end_tick)

    def _update_work_windows(self, people: Sequence[PersonRead]) -> None:
        cache: dict[int, tuple[int, int]] = {}
        for person in people:
            start_tick, end_tick = self._parse_work_hours_to_ticks(getattr(person, 'work_hours', '') or '')
            cache[person.id] = (start_tick, end_tick)
        self._work_hours_ticks = cache

    def _is_within_work_hours(self, person: PersonRead, tick: int) -> bool:
        if not self.hours_per_day:
            return True
        window = self._work_hours_ticks.get(person.id)
        if not window:
            return True
        start_tick, end_tick = window
        tick_of_day = (tick - 1) % self.hours_per_day
        if start_tick <= end_tick:
            return start_tick <= tick_of_day < end_tick
        return tick_of_day >= start_tick or tick_of_day < end_tick

    def _format_sim_time(self, tick: int) -> str:
        if tick <= 0:
            return "Day 0 00:00"
        ticks_per_day = max(1, self.hours_per_day)
        day_index = (tick - 1) // ticks_per_day + 1
        tick_of_day = (tick - 1) % ticks_per_day
        minutes = int((tick_of_day / ticks_per_day) * 1440)
        hour = minutes // 60
        minute = minutes % 60
        return f"Day {day_index} {hour:02d}:{minute:02d}"

    def _sim_datetime_for_tick(self, tick: int) -> datetime | None:
        base = self._sim_base_dt
        if not base:
            return None
        ticks_per_day = max(1, self.hours_per_day)
        day_index = (tick - 1) // ticks_per_day
        tick_of_day = (tick - 1) % ticks_per_day
        minutes = int((tick_of_day / ticks_per_day) * 1440)
        return base + timedelta(days=day_index, minutes=minutes)


    def _planner_context_summary(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        worker = kwargs.get('worker')
        if worker is not None:
            summary['worker'] = getattr(worker, 'name', worker)
        department_head = kwargs.get('department_head')
        if department_head is not None:
            summary['department_head'] = getattr(department_head, 'name', department_head)
        project_name = kwargs.get('project_name')
        if project_name:
            summary['project_name'] = project_name
        day_index = kwargs.get('day_index')
        if day_index is not None:
            summary['day_index'] = day_index
        tick = kwargs.get('tick')
        if tick is not None:
            summary['tick'] = tick
        model_hint = kwargs.get('model_hint')
        if model_hint:
            summary['model_hint'] = model_hint
        return summary

    def get_planner_metrics(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._planner_metrics_lock:
            data = list(self._planner_metrics)
        if limit <= 0:
            return data
        return data[-limit:]

    # ------------------------------------------------------------------
    # People management
    # ------------------------------------------------------------------
    def create_person(self, payload: PersonCreate) -> PersonRead:
        # Validate name uniqueness
        existing_people = self.list_people()
        for person in existing_people:
            if person.name.strip().lower() == payload.name.strip().lower():
                raise ValueError(
                    f"Duplicate name '{payload.name}'. "
                    f"A person with this name already exists (ID: {person.id}, Role: {person.role}). "
                    "Please use a unique name to avoid confusion in team communications."
                )

        # Validate Korean names for Korean locale
        locale = os.getenv("VDOS_LOCALE", "en").strip().lower()
        if locale == "ko":
            import re
            # Check if name contains Korean characters (Hangul)
            if not re.search(r'[\uac00-\ud7af]', payload.name):
                raise ValueError(
                    f"Korean locale requires Korean name, but got: '{payload.name}'. "
                    "Please use a Korean name (e.g., '김지훈' instead of 'Kim Jihoon')."
                )

        persona = self._to_persona(payload)
        schedule = [
            ScheduleBlock(block.start, block.end, block.activity)
            for block in payload.schedule or []
        ]
        persona_markdown = build_worker_markdown(
            persona,
            schedule=schedule,
            planning_guidelines=payload.planning_guidelines,
            event_playbook=payload.event_playbook,
            statuses=payload.statuses,
        )

        skills_json = json.dumps(list(payload.skills))
        personality_json = json.dumps(list(payload.personality))
        objectives_json = json.dumps(list(payload.objectives or []))
        metrics_json = json.dumps(list(payload.metrics or []))
        planning_json = json.dumps(list(payload.planning_guidelines or []))
        playbook_json = json.dumps(payload.event_playbook or {})
        statuses_json = json.dumps(list(payload.statuses or []))

        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO people (
                    name, role, timezone, work_hours, break_frequency,
                    communication_style, email_address, chat_handle, is_department_head, team_name, skills,
                    personality, objectives, metrics, persona_markdown,
                    planning_guidelines, event_playbook, statuses
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name,
                    payload.role,
                    payload.timezone,
                    payload.work_hours,
                    payload.break_frequency,
                    payload.communication_style,
                    payload.email_address,
                    payload.chat_handle,
                    1 if payload.is_department_head else 0,
                    payload.team_name,
                    skills_json,
                    personality_json,
                    objectives_json,
                    metrics_json,
                    persona_markdown,
                    planning_json,
                    playbook_json,
                    statuses_json,
                ),
            )
            person_id = cursor.lastrowid
            if schedule:
                conn.executemany(
                    "INSERT INTO schedule_blocks(person_id, start, end, activity) VALUES (?, ?, ?, ?)",
                    [(person_id, block.start, block.end, block.activity) for block in schedule],
                )

        self.email_gateway.ensure_mailbox(payload.email_address, payload.name)
        self.chat_gateway.ensure_user(payload.chat_handle, payload.name)

        person = self.get_person(person_id)
        self._get_worker_runtime(person)
        return person

    def list_people(self) -> List[PersonRead]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM people ORDER BY id"
            ).fetchall()
        return [self._row_to_person(row) for row in rows]

    def get_person(self, person_id: int) -> PersonRead:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
        if not row:
            raise ValueError("Person not found")
        return self._row_to_person(row)

    def delete_person_by_name(self, name: str) -> bool:
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM people WHERE name = ?", (name,)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM people WHERE id = ?", (row["id"],))
        self._worker_runtime.pop(row["id"], None)
        return True

    # ------------------------------------------------------------------
    # Planning lifecycle
    def _call_planner(self, method_name: str, **kwargs) -> PlanResult:
        planner = self.planner
        method = getattr(planner, method_name)
        planner_name = planner.__class__.__name__
        fallback_name = self._stub_planner.__class__.__name__
        context = self._planner_context_summary(kwargs)
        start = time.perf_counter()
        logger.info("Planner %s using %s starting with context=%s", method_name, planner_name, context)
        try:
            result = method(**kwargs)
        except PlanningError as exc:
            duration = time.perf_counter() - start
            if isinstance(planner, StubPlanner):
                logger.error("Stub planner %s failed after %.2fs: %s", method_name, duration, exc)
                raise
            if self._planner_strict:
                logger.error("Planner %s using %s failed after %.2fs and strict mode is enabled: %s", method_name, planner_name, duration, exc)
                raise RuntimeError(f"Planning failed ({method_name}): {exc}") from exc
            logger.warning("Planner %s using %s failed after %.2fs: %s. Falling back to stub planner.", method_name, planner_name, duration, exc)
            fallback_method = getattr(self._stub_planner, method_name)
            fallback_start = time.perf_counter()
            fallback_result = fallback_method(**kwargs)
            fallback_duration = time.perf_counter() - fallback_start
            logger.info("Stub planner %s succeeded in %.2fs (model=%s)", fallback_name, fallback_duration, getattr(fallback_result, 'model_used', 'vdos-stub'))
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'method': method_name,
                'planner': planner_name,
                'result_planner': fallback_name,
                'model': getattr(fallback_result, 'model_used', 'vdos-stub'),
                'duration_ms': round(duration * 1000, 2),
                'fallback_duration_ms': round(fallback_duration * 1000, 2),
                'fallback': True,
                'error': str(exc),
                'context': context,
            }
            with self._planner_metrics_lock:
                self._planner_metrics.append(entry)
            return fallback_result
        else:
            duration = time.perf_counter() - start
            logger.info("Planner %s using %s succeeded in %.2fs (model=%s)", method_name, planner_name, duration, getattr(result, 'model_used', 'unknown'))
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'method': method_name,
                'planner': planner_name,
                'result_planner': planner_name,
                'model': getattr(result, 'model_used', 'unknown'),
                'duration_ms': round(duration * 1000, 2),
                'fallback_duration_ms': None,
                'fallback': False,
                'context': context,
            }
            with self._planner_metrics_lock:
                self._planner_metrics.append(entry)
            return result

    # ------------------------------------------------------------------
    def get_project_plan(self) -> dict[str, Any] | None:
        if self._project_plan_cache is not None:
            return self._project_plan_cache.copy()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_plans ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        plan = self._row_to_project_plan(row)
        self._project_plan_cache = plan
        self.project_duration_weeks = plan["duration_weeks"]
        return plan

    def list_worker_plans(
        self,
        person_id: int,
        plan_type: str | None = None,
        limit: int | None = None,
    ) -> List[dict[str, Any]]:
        self.get_person(person_id)
        query = "SELECT * FROM worker_plans WHERE person_id = ?"
        params: list[Any] = [person_id]
        if plan_type:
            query += " AND plan_type = ?"
            params.append(plan_type)
        query += " ORDER BY id DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_worker_plan(row) for row in rows]

    def list_daily_reports(
        self,
        person_id: int,
        day_index: int | None = None,
        limit: int | None = None,
    ) -> List[dict[str, Any]]:
        self.get_person(person_id)
        query = "SELECT * FROM daily_reports WHERE person_id = ?"
        params: list[Any] = [person_id]
        if day_index is not None:
            query += " AND day_index = ?"
            params.append(day_index)
        query += " ORDER BY id DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_daily_report(row) for row in rows]

    def list_simulation_reports(self, limit: int | None = None) -> List[dict[str, Any]]:
        query = "SELECT * FROM simulation_reports ORDER BY id DESC"
        params: list[Any] = []
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_simulation_report(row) for row in rows]

    def _initialise_project_plan(self, request: SimulationStartRequest, team: Sequence[PersonRead]) -> None:
        if not team:
            raise RuntimeError("Cannot initialise project plan without any personas")
        self._sync_worker_runtimes(team)
        department_head = self._resolve_department_head(team, request.department_head_name)

        # Multi-project mode
        if request.projects:
            team_by_id = {p.id: p for p in team}
            for proj_timeline in request.projects:
                # Determine team for this project
                if proj_timeline.assigned_person_ids:
                    proj_team = [team_by_id[pid] for pid in proj_timeline.assigned_person_ids if pid in team_by_id]
                else:
                    proj_team = list(team)  # All team members by default

                if not proj_team:
                    continue

                try:
                    plan_result = self._call_planner(
                        'generate_project_plan',
                        department_head=department_head,
                        project_name=proj_timeline.project_name,
                        project_summary=proj_timeline.project_summary,
                        duration_weeks=proj_timeline.duration_weeks,
                        team=proj_team,
                        model_hint=request.model_hint,
                    )
                except PlanningError as exc:
                    raise RuntimeError(f"Unable to generate project plan for '{proj_timeline.project_name}': {exc}") from exc

                self._store_project_plan(
                    project_name=proj_timeline.project_name,
                    project_summary=proj_timeline.project_summary,
                    plan_result=plan_result,
                    generated_by=department_head.id if department_head else None,
                    duration_weeks=proj_timeline.duration_weeks,
                    start_week=proj_timeline.start_week,
                    assigned_person_ids=proj_timeline.assigned_person_ids,
                )

            # For multi-project mode, skip ALL initial person planning to avoid timeout
            # All daily/hourly plans will be generated lazily on first advance()
            # This makes initialization instant by only generating project plans (2-3 GPT calls)
            pass
        else:
            # Single-project mode (backward compatible)
            try:
                plan_result = self._call_planner(
                    'generate_project_plan',
                    department_head=department_head,
                    project_name=request.project_name,
                    project_summary=request.project_summary,
                    duration_weeks=request.duration_weeks,
                    team=team,
                    model_hint=request.model_hint,
                )
            except PlanningError as exc:
                raise RuntimeError(f"Unable to generate project plan: {exc}") from exc
            plan_record = self._store_project_plan(
                project_name=request.project_name,
                project_summary=request.project_summary,
                plan_result=plan_result,
                generated_by=department_head.id if department_head else None,
                duration_weeks=request.duration_weeks,
            )
            for person in team:
                daily_result = self._generate_daily_plan(person, plan_record, day_index=0)
                self._generate_hourly_plan(
                    person,
                    plan_record,
                    daily_result.content,
                    tick=0,
                    reason="initialisation",
                )

    def _get_active_project_for_person(self, person_id: int, week: int) -> dict[str, Any] | None:
        """Get the active project for a person at a given week, considering project timelines."""
        with get_connection() as conn:
            # First check if person is assigned to specific projects
            rows = conn.execute(
                """
                SELECT pp.* FROM project_plans pp
                INNER JOIN project_assignments pa ON pp.id = pa.project_id
                WHERE pa.person_id = ? AND pp.start_week <= ? AND (pp.start_week + pp.duration_weeks - 1) >= ?
                ORDER BY pp.start_week ASC
                LIMIT 1
                """,
                (person_id, week, week),
            ).fetchall()

            if not rows:
                # No specific assignment, check for projects without assignments (default: everyone)
                rows = conn.execute(
                    """
                    SELECT pp.* FROM project_plans pp
                    WHERE pp.id NOT IN (SELECT DISTINCT project_id FROM project_assignments)
                    AND pp.start_week <= ? AND (pp.start_week + pp.duration_weeks - 1) >= ?
                    ORDER BY pp.start_week ASC
                    LIMIT 1
                    """,
                    (week, week),
                ).fetchall()

            if rows:
                return self._row_to_project_plan(rows[0])
            return None

    def _get_all_active_projects_for_person(self, person_id: int, week: int) -> list[dict[str, Any]]:
        """Get ALL active projects for a person at a given week."""
        with get_connection() as conn:
            # Get assigned projects
            rows = conn.execute(
                """
                SELECT pp.* FROM project_plans pp
                INNER JOIN project_assignments pa ON pp.id = pa.project_id
                WHERE pa.person_id = ? AND pp.start_week <= ? AND (pp.start_week + pp.duration_weeks - 1) >= ?
                ORDER BY pp.start_week ASC
                """,
                (person_id, week, week),
            ).fetchall()

            assigned_ids = {row["id"] for row in rows}

            # Get projects without assignments (everyone works on them)
            unassigned_rows = conn.execute(
                """
                SELECT pp.* FROM project_plans pp
                WHERE pp.id NOT IN (SELECT DISTINCT project_id FROM project_assignments)
                AND pp.start_week <= ? AND (pp.start_week + pp.duration_weeks - 1) >= ?
                ORDER BY pp.start_week ASC
                """,
                (week, week),
            ).fetchall()

            all_rows = list(rows) + [r for r in unassigned_rows if r["id"] not in assigned_ids]
            return [self._row_to_project_plan(row) for row in all_rows]

    def _resolve_department_head(
        self, people: Sequence[PersonRead], requested_name: str | None
    ) -> PersonRead:
        if requested_name:
            for person in people:
                if person.name == requested_name:
                    return person
            raise RuntimeError(
                f"Department head '{requested_name}' not found among registered personas."
            )
        for person in people:
            if getattr(person, "is_department_head", False):
                return person
        # Default to the first registered persona so small teams can start without explicit leads.
        return people[0]

    def _store_project_plan(
        self,
        project_name: str,
        project_summary: str,
        plan_result: PlanResult,
        generated_by: int | None,
        duration_weeks: int,
        start_week: int = 1,
        assigned_person_ids: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO project_plans(project_name, project_summary, plan, generated_by, duration_weeks, start_week, model_used, tokens_used) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_name,
                    project_summary,
                    plan_result.content,
                    generated_by,
                    duration_weeks,
                    start_week,
                    plan_result.model_used,
                    plan_result.tokens_used,
                ),
            )
            project_id = cursor.lastrowid
            # Store project assignments if provided
            if assigned_person_ids:
                for person_id in assigned_person_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO project_assignments(project_id, person_id) VALUES (?, ?)",
                        (project_id, person_id),
                    )
            row = conn.execute(
                "SELECT * FROM project_plans WHERE id = ?", (project_id,)
            ).fetchone()
        plan = self._row_to_project_plan(row)
        self._project_plan_cache = plan
        self.project_duration_weeks = duration_weeks
        return plan

    def _row_to_project_plan(self, row) -> dict[str, Any]:
        # Get start_week with fallback to 1 for older records
        start_week = 1
        try:
            start_week = row["start_week"]
        except (KeyError, IndexError):
            pass

        return {
            "id": row["id"],
            "project_name": row["project_name"],
            "project_summary": row["project_summary"],
            "plan": row["plan"],
            "generated_by": row["generated_by"],
            "duration_weeks": row["duration_weeks"],
            "start_week": start_week,
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "created_at": row["created_at"],
        }

    def _generate_daily_plan(
        self, person: PersonRead, project_plan: dict[str, Any], day_index: int
    ) -> PlanResult:
        # Get all active people for team roster
        team = self._get_active_people()

        try:
            result = self._call_planner(
                'generate_daily_plan',
                worker=person,
                project_plan=project_plan['plan'],
                day_index=day_index,
                duration_weeks=self.project_duration_weeks,
                team=team,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate daily plan for {person.name}: {exc}") from exc
        self._store_worker_plan(
            person_id=person.id,
            tick=day_index,
            plan_type="daily",
            result=result,
            context=f"day_index={day_index}",
        )
        return result

    def _generate_hourly_plans_parallel(
        self,
        planning_tasks: list[tuple[PersonRead, dict[str, Any], str, int, str, list[str] | None, list[dict[str, Any]] | None]],
    ) -> list[tuple[PersonRead, PlanResult]]:
        """
        Generate hourly plans for multiple workers in parallel.

        Args:
            planning_tasks: List of (person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects)

        Returns:
            List of (person, PlanResult) tuples in same order as input
        """
        if not self._planning_executor or len(planning_tasks) <= 1:
            # Fall back to sequential planning
            results = []
            for task in planning_tasks:
                person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects = task
                try:
                    result = self._generate_hourly_plan(
                        person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects
                    )
                    results.append((person, result))
                except Exception as exc:
                    logger.error(f"Sequential planning failed for {person.name}: {exc}")
                    results.append((person, PlanResult(content="", model_used="error", tokens_used=0)))
            return results

        # Submit all planning tasks in parallel
        futures = []
        for task in planning_tasks:
            person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects = task
            future = self._planning_executor.submit(
                self._generate_hourly_plan,
                person, project_plan, daily_plan_text, tick, reason, adjustments, all_active_projects
            )
            futures.append((person, future))

        # Collect results in order
        results = []
        for person, future in futures:
            try:
                result = future.result(timeout=240)  # 4 minute timeout per plan
                results.append((person, result))
            except Exception as exc:
                logger.error(f"Parallel planning failed for {person.name}: {exc}")
                # Return empty plan to maintain order
                results.append((person, PlanResult(content="", model_used="error", tokens_used=0)))

        return results

    def _generate_hourly_plan(
        self,
        person: PersonRead,
        project_plan: dict[str, Any],
        daily_plan_text: str,
        tick: int,
        reason: str,
        adjustments: list[str] | None = None,
        all_active_projects: list[dict[str, Any]] | None = None,
    ) -> PlanResult:
        # Get all active people for team roster
        team = self._get_active_people()

        # Get recent emails for this person (for threading context)
        recent_emails = list(self._recent_emails.get(person.id, []))

        try:
            result = self._call_planner(
                'generate_hourly_plan',
                worker=person,
                project_plan=project_plan['plan'],
                daily_plan=daily_plan_text,
                tick=tick,
                context_reason=reason,
                team=team,
                model_hint=self._planner_model_hint,
                all_active_projects=all_active_projects,
                recent_emails=recent_emails,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate hourly plan for {person.name}: {exc}") from exc

        context = f"reason={reason}"
        content_result = result
        if adjustments:
            bullets = "\n".join(f"- {item}" for item in adjustments)
            content = f"{result.content}\n\nAdjustments from live collaboration:\n{bullets}"
            content_result = PlanResult(content=content, model_used=result.model_used, tokens_used=result.tokens_used)
            context += f";adjustments={len(adjustments)}"

        self._store_worker_plan(
            person_id=person.id,
            tick=tick,
            plan_type="hourly",
            result=content_result,
            context=context,
        )
        return content_result

    def _store_worker_plan(
        self,
        person_id: int,
        tick: int,
        plan_type: str,
        result: PlanResult,
        context: str | None,
    ) -> dict[str, Any]:
        with get_connection() as conn:
            # Verify person exists before attempting insert
            person_exists = conn.execute(
                "SELECT id FROM people WHERE id = ?", (person_id,)
            ).fetchone()
            if not person_exists:
                logger.error(f"Cannot store worker plan: person_id {person_id} does not exist in database")
                raise ValueError(f"Person ID {person_id} not found in database")

            cursor = conn.execute(
                "INSERT INTO worker_plans(person_id, tick, plan_type, content, model_used, tokens_used, context) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    person_id,
                    tick,
                    plan_type,
                    result.content,
                    result.model_used,
                    result.tokens_used,
                    context,
                ),
            )
            row = conn.execute(
                "SELECT * FROM worker_plans WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return self._row_to_worker_plan(row)

    def _row_to_worker_plan(self, row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "person_id": row["person_id"],
            "tick": row["tick"],
            "plan_type": row["plan_type"],
            "content": row["content"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "context": row["context"],
            "created_at": row["created_at"],
        }

    def _fetch_worker_plan(
        self,
        person_id: int,
        plan_type: str,
        tick: int | None = None,
        exact_tick: bool = False,
    ) -> dict[str, Any] | None:
        query = "SELECT * FROM worker_plans WHERE person_id = ? AND plan_type = ?"
        params: list[Any] = [person_id, plan_type]
        if tick is not None:
            comparator = "=" if exact_tick else "<="
            query += f" AND tick {comparator} ?"
            params.append(tick)
        query += " ORDER BY id DESC LIMIT 1"
        with get_connection() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return self._row_to_worker_plan(row) if row else None

    def _ensure_daily_plan(
        self, person: PersonRead, day_index: int, project_plan: dict[str, Any]
    ) -> str:
        existing = self._fetch_worker_plan(
            person.id, "daily", tick=day_index, exact_tick=True
        )
        if existing:
            return existing["content"]
        result = self._generate_daily_plan(person, project_plan, day_index)
        return result.content

    def _summarise_plan(self, plan_text: str, max_lines: int = 4) -> str:
        lines = [line.strip() for line in plan_text.splitlines() if line.strip()]
        if not lines:
            return "No plan provided yet."
        # Drop placeholder headers and meta lines
        filtered: list[str] = []
        for line in lines:
            if (line.startswith("[") and line.endswith("]")) or line.startswith("#") or line.startswith("```"):
                continue
            if line.startswith(("Tick:", "Worker:", "Reason:", "Outline:")):
                continue
            filtered.append(line)
        if not filtered:
            filtered = lines
        return "\n".join(filtered[:max_lines])

    def _fetch_hourly_summary(self, person_id: int, hour_index: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM hourly_summaries WHERE person_id = ? AND hour_index = ?",
                (person_id, hour_index),
            ).fetchone()
        if not row:
            return None
        return {
            'id': row['id'],
            'person_id': row['person_id'],
            'hour_index': row['hour_index'],
            'summary': row['summary'],
            'model_used': row['model_used'],
            'tokens_used': row['tokens_used'],
        }

    def _store_hourly_summary(
        self,
        person_id: int,
        hour_index: int,
        result: PlanResult,
    ) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT OR REPLACE INTO hourly_summaries(person_id, hour_index, summary, model_used, tokens_used) VALUES (?, ?, ?, ?, ?)",
                (person_id, hour_index, result.content, result.model_used, result.tokens_used or 0),
            )
            row_id = cursor.lastrowid
        return {
            'id': row_id,
            'person_id': person_id,
            'hour_index': hour_index,
            'summary': result.content,
            'model_used': result.model_used,
            'tokens_used': result.tokens_used or 0,
        }

    def _generate_hourly_summary(
        self,
        person: PersonRead,
        hour_index: int,
    ) -> dict[str, Any]:
        """Generate a summary for a completed hour."""
        existing = self._fetch_hourly_summary(person.id, hour_index)
        if existing:
            return existing

        # Get all hourly plans for this hour
        start_tick = hour_index * 60 + 1
        end_tick = (hour_index + 1) * 60
        with get_connection() as conn:
            hourly_rows = conn.execute(
                "SELECT tick, content FROM worker_plans WHERE person_id = ? AND plan_type = 'hourly' AND tick BETWEEN ? AND ? ORDER BY tick",
                (person.id, start_tick, end_tick),
            ).fetchall()

        if not hourly_rows:
            # No plans for this hour, skip summary
            return {'person_id': person.id, 'hour_index': hour_index, 'summary': '', 'model_used': 'none', 'tokens_used': 0}

        hourly_plans = "\n".join(f"Tick {row['tick']}: {row['content'][:200]}..." for row in hourly_rows)

        try:
            result = self._call_planner(
                'generate_hourly_summary',
                worker=person,
                hour_index=hour_index,
                hourly_plans=hourly_plans,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            logger.warning(f"Unable to generate hourly summary for {person.name} hour {hour_index}: {exc}")
            # Store a stub summary instead of failing
            result = PlanResult(content=f"Hour {hour_index + 1} activities", model_used="stub", tokens_used=0)

        return self._store_hourly_summary(person_id=person.id, hour_index=hour_index, result=result)

    def _fetch_daily_report(self, person_id: int, day_index: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE person_id = ? AND day_index = ? ORDER BY id DESC LIMIT 1",
                (person_id, day_index),
            ).fetchone()
        return self._row_to_daily_report(row) if row else None

    def _generate_daily_report(
        self,
        person: PersonRead,
        day_index: int,
        project_plan: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self._fetch_daily_report(person.id, day_index)
        if existing:
            return existing
        daily_plan_text = self._ensure_daily_plan(person, day_index, project_plan)

        # Use hourly summaries instead of all tick logs
        start_hour = day_index * (self.hours_per_day // 60)
        end_hour = (day_index + 1) * (self.hours_per_day // 60)
        with get_connection() as conn:
            summary_rows = conn.execute(
                "SELECT hour_index, summary FROM hourly_summaries WHERE person_id = ? AND hour_index BETWEEN ? AND ? ORDER BY hour_index",
                (person.id, start_hour, end_hour - 1),
            ).fetchall()

        if summary_rows:
            hourly_summary = "\n".join(f"Hour {row['hour_index'] + 1}: {row['summary']}" for row in summary_rows)
        else:
            # Fallback: generate hourly summaries now if they don't exist
            hourly_summary_lines = []
            for h in range(start_hour, end_hour):
                summary = self._generate_hourly_summary(person, h)
                if summary.get('summary'):
                    hourly_summary_lines.append(f"Hour {h + 1}: {summary['summary']}")
            hourly_summary = "\n".join(hourly_summary_lines) if hourly_summary_lines else "No hourly activities recorded."
        schedule_blocks = [
            ScheduleBlock(block.start, block.end, block.activity)
            for block in person.schedule or []
        ]
        minute_schedule = render_minute_schedule(schedule_blocks)
        try:
            result = self._call_planner(
                'generate_daily_report',
                worker=person,
                project_plan=project_plan['plan'],
                day_index=day_index,
                daily_plan=daily_plan_text,
                hourly_log=hourly_summary,
                minute_schedule=minute_schedule,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate daily report for {person.name}: {exc}") from exc
        return self._store_daily_report(
            person_id=person.id,
            day_index=day_index,
            schedule_outline=minute_schedule,
            result=result,
        )

    def _store_daily_report(
        self,
        person_id: int,
        day_index: int,
        schedule_outline: str,
        result: PlanResult,
    ) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO daily_reports(person_id, day_index, report, schedule_outline, model_used, tokens_used) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    person_id,
                    day_index,
                    result.content,
                    schedule_outline,
                    result.model_used,
                    result.tokens_used,
                ),
            )
            row = conn.execute("SELECT * FROM daily_reports WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_daily_report(row)

    def _row_to_daily_report(self, row) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "person_id": row["person_id"],
            "day_index": row["day_index"],
            "report": row["report"],
            "schedule_outline": row["schedule_outline"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "created_at": row["created_at"],
        }

    def _generate_simulation_report(self, project_plan: dict[str, Any], total_ticks: int) -> dict[str, Any]:
        if not project_plan:
            raise RuntimeError("Cannot generate simulation report without a project plan")
        people = self.list_people()
        with get_connection() as conn:
            # Limit tick log to major milestones only (every 480 ticks = 1 day for 8-hour days)
            tick_rows = conn.execute(
                "SELECT tick, reason FROM tick_log WHERE tick % 480 = 1 OR reason IN ('kickoff', 'manual') ORDER BY id LIMIT 100",
                ()
            ).fetchall()
            event_rows = conn.execute("SELECT type, target_ids, project_id, at_tick, payload FROM events ORDER BY id").fetchall()

        # Summarize tick log
        if len(tick_rows) > 50:
            tick_summary = f"Major milestones ({len(tick_rows)} key ticks):\n"
            tick_summary += "\n".join(f"Tick {row['tick']}: {row['reason']}" for row in tick_rows[:25])
            tick_summary += f"\n... ({len(tick_rows) - 25} more ticks) ..."
        else:
            tick_summary = "\n".join(f"Tick {row['tick']}: {row['reason']}" for row in tick_rows)

        # Summarize events concisely
        event_summary = f"Total events: {len(event_rows)}\n"
        event_summary += "\n".join(
            f"- {row['type']} (project={row['project_id']}, tick={row['at_tick']})"
            for row in event_rows[:20]  # Limit to first 20
        ) if event_rows else "No events logged."

        # Use daily report summaries (just the first 100 chars of each)
        daily_reports_full = self.list_daily_reports_for_summary()
        if len(daily_reports_full) > 1000:  # If very long, summarize further
            daily_reports = f"Daily reports summary ({len(daily_reports_full.splitlines())} days):\n"
            daily_reports += "\n".join(line[:150] for line in daily_reports_full.splitlines()[:50])
            daily_reports += f"\n... ({len(daily_reports_full.splitlines()) - 50} more days) ..."
        else:
            daily_reports = daily_reports_full

        try:
            result = self._call_planner(
                'generate_simulation_report',
                project_plan=project_plan['plan'],
                team=people,
                total_ticks=total_ticks,
                tick_log=tick_summary,
                daily_reports=daily_reports,
                event_summary=event_summary,
                model_hint=self._planner_model_hint,
            )
        except PlanningError as exc:
            raise RuntimeError(f"Unable to generate simulation report: {exc}") from exc
        return self._store_simulation_report(
            total_ticks=total_ticks,
            result=result,
        )

    def list_daily_reports_for_summary(self) -> str:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT person_id, day_index, report FROM daily_reports ORDER BY person_id, day_index"
            ).fetchall()
        if not rows:
            return "No daily reports were generated."
        parts = []
        for row in rows:
            parts.append(f"Person {row['person_id']} Day {row['day_index']}: {row['report']}")
        return "\n".join(parts)

    def _store_simulation_report(self, total_ticks: int, result: PlanResult) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO simulation_reports(report, model_used, tokens_used, total_ticks) VALUES (?, ?, ?, ?)",
                (
                    result.content,
                    result.model_used,
                    result.tokens_used,
                    total_ticks,
                ),
            )
            row = conn.execute("SELECT * FROM simulation_reports WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_simulation_report(row)

    def _row_to_simulation_report(self, row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "report": row["report"],
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "total_ticks": row["total_ticks"],
            "created_at": row["created_at"],
        }

    def get_token_usage(self) -> dict[str, int]:
        usage: dict[str, int] = {}
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens
                FROM project_plans
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens
                FROM worker_plans
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens
                FROM daily_reports
                UNION ALL
                SELECT model_used, COALESCE(tokens_used, 0) AS tokens
                FROM simulation_reports
                """
            ).fetchall()
        for row in rows:
            model = row["model_used"]
            tokens = row["tokens"] or 0
            usage[model] = usage.get(model, 0) + int(tokens)
        return usage

    # ------------------------------------------------------------------
    # Simulation control
    # ------------------------------------------------------------------
    def get_state(self) -> SimulationState:
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def start(self, request: SimulationStartRequest | None = None) -> SimulationState:
        seed = self._derive_seed(request)
        self._random.seed(seed)
        self._reset_runtime_state()
        all_people = self.list_people()
        if not all_people:
            raise RuntimeError("Cannot start simulation without any personas")
        active_people = self._resolve_active_people(request, all_people)
        self._active_person_ids = [person.id for person in active_people]
        if request is not None:
            # Multi-project mode uses total_duration_weeks if provided
            if request.total_duration_weeks:
                self.project_duration_weeks = request.total_duration_weeks
            else:
                self.project_duration_weeks = request.duration_weeks
            self._planner_model_hint = request.model_hint
            self._initialise_project_plan(request, active_people)
        self._set_running(True)
        try:
            self._sim_base_dt = datetime.now(timezone.utc)
        except Exception:
            self._sim_base_dt = None
        self._sync_worker_runtimes(active_people)
        # Schedule a kickoff chat/email at the first working minute for each worker
        try:
            ticks_per_day = max(1, self.hours_per_day)
            for person in active_people:
                start_end = self._work_hours_ticks.get(person.id, (0, ticks_per_day))
                start_tick_of_day = start_end[0]
                base_tick = 1  # day 1 start
                kickoff_tick = base_tick + max(0, start_tick_of_day) + 5  # +5 minutes
                # pick a collaborator to target
                recipients = self._select_collaborators(person, active_people)
                target = recipients[0] if recipients else None
                if target:
                    if self._locale == 'ko':
                        self._schedule_direct_comm(person.id, kickoff_tick, "chat", target.chat_handle, "좋은 아침입니다! 오늘 우선순위 빠르게 맞춰볼까요?")
                        self._schedule_direct_comm(person.id, kickoff_tick + 30, "email", target.email_address, "제목: 킥오프\n본문: 오늘 진행할 작업 정리했습니다 — 문의사항 있으면 알려주세요.")
                    else:
                        self._schedule_direct_comm(person.id, kickoff_tick, "chat", target.chat_handle, f"Morning! Quick sync on priorities?")
                        self._schedule_direct_comm(person.id, kickoff_tick + 30, "email", target.email_address, f"Subject: Quick kickoff\nBody: Lining up tasks for today — ping me with blockers.")
        except Exception:
            pass
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def stop(self) -> SimulationState:
        self.stop_auto_ticks()
        status = self._fetch_state()
        if status.is_running:
            project_plan = self.get_project_plan()
            if project_plan is not None:
                self._generate_simulation_report(project_plan, total_ticks=status.current_tick)
        self._set_running(False)
        self._active_person_ids = None
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def start_auto_ticks(self) -> SimulationState:
        status = self._fetch_state()
        if not status.is_running:
            raise RuntimeError("Simulation must be running before enabling automatic ticks")
        self._set_auto_tick(True)
        thread = self._auto_tick_thread
        if thread is None or not thread.is_alive():
            stop_event = threading.Event()
            self._auto_tick_stop = stop_event
            thread = threading.Thread(
                target=self._run_auto_tick_loop,
                args=(stop_event,),
                name="vdos-auto-tick",
                daemon=True,
            )
            self._auto_tick_thread = thread
            thread.start()
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def stop_auto_ticks(self) -> SimulationState:
        self._set_auto_tick(False)
        stop_event = self._auto_tick_stop
        if stop_event is not None:
            stop_event.set()
        thread = self._auto_tick_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
            if thread.is_alive():
                logger.warning("Automatic tick thread did not exit cleanly within timeout")
        self._auto_tick_thread = None
        self._auto_tick_stop = None
        status = self._fetch_state()
        return SimulationState(
            current_tick=status.current_tick,
            is_running=status.is_running,
            auto_tick=status.auto_tick,
            sim_time=self._format_sim_time(status.current_tick),
        )

    def _run_auto_tick_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(self._tick_interval_seconds):
            state = self._fetch_state()
            if not state.is_running or not state.auto_tick:
                break
            try:
                self.advance(1, "auto")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Automatic tick failed; disabling auto ticks.")
                self._set_auto_tick(False)
                break

    def advance(self, ticks: int, reason: str) -> SimulationAdvanceResult:
        with self._advance_lock:
            status = self._fetch_state()
            if not status.is_running:
                raise RuntimeError("Simulation is not running; call start first")
            if ticks <= 0:
                raise ValueError("Ticks must be positive")

            project_plan = self.get_project_plan()
            if project_plan is None:
                raise RuntimeError("Project plan is not initialised; start the simulation with project details before advancing.")

            people = self._get_active_people()
            if not people:
                raise RuntimeError("Cannot advance simulation without any active personas")
            self._sync_worker_runtimes(people)
            people_by_id = {person.id: person for person in people}

            # Calculate current week for multi-project support
            current_day = (status.current_tick - 1) // self.hours_per_day if status.current_tick > 0 else 0
            current_week = (current_day // 5) + 1  # 1-indexed weeks, assuming 5-day work weeks

            emails_sent = 0
            chats_sent = 0

            for _ in range(ticks):
                status.current_tick += 1
                self._reset_tick_sends()
                self._update_tick(status.current_tick, reason)
                self._refresh_status_overrides(status.current_tick)
                event_adjustments, _ = self._maybe_generate_events(people, status.current_tick, project_plan)
                day_index = (status.current_tick - 1) // self.hours_per_day
                tick_of_day = (status.current_tick - 1) % self.hours_per_day if self.hours_per_day > 0 else 0
                # Prune stale plan-attempt counters (keep only this minute)
                if self._hourly_plan_attempts:
                    keys = list(self._hourly_plan_attempts.keys())
                    for key in keys:
                        if key[1] != day_index or key[2] != tick_of_day:
                            self._hourly_plan_attempts.pop(key, None)

                # PHASE 1: Collect planning tasks and prepare context
                planning_tasks = []
                person_contexts = {}

                for person in people:
                    runtime = self._get_worker_runtime(person)
                    incoming = runtime.drain()
                    working = self._is_within_work_hours(person, status.current_tick)
                    adjustments: list[str] = list(event_adjustments.get(person.id, []))
                    override = self._status_overrides.get(person.id)
                    if override and override[0] == 'SickLeave':
                        incoming = []
                        adjustments.append('Observe sick leave and hold tasks until recovered.')
                    if not working:
                        if incoming:
                            for message in incoming:
                                runtime.queue(message)
                        for note in adjustments:
                            reminder = _InboundMessage(
                                sender_id=0,
                                sender_name='Simulation Manager',
                                subject='Pending adjustment',
                                summary=note,
                                action_item=note,
                                message_type='event',
                                channel='system',
                                tick=status.current_tick,
                            )
                            runtime.queue(reminder)
                        logger.info("Skipping planning for %s at tick %s (off hours)", person.name, status.current_tick)
                        continue
                    # Dispatch any scheduled comms for this tick before planning/fallback
                    se_pre, sc_pre = self._dispatch_scheduled(person, status.current_tick, people_by_id)
                    emails_sent += se_pre
                    chats_sent += sc_pre
                    if se_pre or sc_pre:
                        # If we sent scheduled comms at this minute, skip fallback sending to avoid duplication
                        continue
                    should_plan = bool(incoming) or bool(adjustments) or reason != 'auto' or (tick_of_day == 0)
                    if not should_plan:
                        continue
                    # Hourly planning limiter per minute
                    key = (person.id, day_index, tick_of_day)
                    attempts = self._hourly_plan_attempts.get(key, 0)
                    if attempts >= self._max_hourly_plans_per_minute:
                        logger.warning(
                            "Skipping hourly planning for %s at tick %s (minute cap %s reached)",
                            person.name,
                            status.current_tick,
                            self._max_hourly_plans_per_minute,
                        )
                        continue
                    # record attempt before planning to avoid re-entry storms
                    self._hourly_plan_attempts[key] = attempts + 1
                    self._remove_runtime_messages([msg.message_id for msg in incoming if msg.message_id is not None])
                    for message in incoming:
                        sender_person = people_by_id.get(message.sender_id)
                        if message.message_type == "ack":
                            adjustments.append(f"Acknowledged by {message.sender_name}: {message.summary}")
                            continue
                        if message.action_item:
                            adjustments.append(f"Handle request from {message.sender_name}: {message.action_item}")
                        if sender_person is None:
                            continue
                        ack_phrase = (message.action_item or message.summary or ("요청하신 내용" if self._locale == 'ko' else "your latest update")).rstrip('.')
                        if self._locale == 'ko':
                            ack_body = f"{sender_person.name.split()[0]}님, {ack_phrase} 진행 중입니다."
                        else:
                            ack_body = f"{sender_person.name.split()[0]}, I'm on {ack_phrase}."
                        if self._can_send(
                            tick=status.current_tick,
                            channel='chat',
                            sender=person.chat_handle,
                            recipient_key=(sender_person.chat_handle,),
                            subject=None,
                            body=ack_body,
                        ):
                            dt = self._sim_datetime_for_tick(status.current_tick)
                            self.chat_gateway.send_dm(
                                sender=person.chat_handle,
                                recipient=sender_person.chat_handle,
                                body=ack_body,
                                sent_at_iso=(dt.isoformat() if dt else None),
                            )
                            chats_sent += 1
                        self._log_exchange(status.current_tick, person.id, sender_person.id, 'chat', None, ack_body)
                        ack_message = _InboundMessage(
                            sender_id=person.id,
                            sender_name=person.name,
                            subject=f"Acknowledgement from {person.name}",
                            summary=ack_body,
                            action_item=None,
                            message_type='ack',
                            channel='chat',
                            tick=status.current_tick,
                        )
                        self._queue_runtime_message(sender_person, ack_message)

                    # Get ALL active projects for this person at current week (concurrent multi-project support)
                    active_projects = self._get_all_active_projects_for_person(person.id, current_week)
                    if not active_projects:
                        active_projects = [project_plan] if project_plan else []

                    # Use first project for daily plan, but pass all projects to hourly planner
                    primary_project = active_projects[0] if active_projects else project_plan

                    daily_plan_text = self._ensure_daily_plan(person, day_index, primary_project)

                    # Collect planning task for parallel execution
                    planning_task = (
                        person,
                        primary_project,
                        daily_plan_text,
                        status.current_tick,
                        reason,
                        adjustments or None,
                        active_projects if len(active_projects) > 1 else None,
                    )
                    planning_tasks.append(planning_task)

                    # Store context needed for post-processing
                    person_contexts[person.id] = {
                        'incoming': incoming,
                        'adjustments': adjustments,
                        'override': override,
                        'primary_project': primary_project,
                        'daily_plan_text': daily_plan_text,
                        'active_projects': active_projects,
                    }

                # PHASE 2: Execute planning in parallel (or sequential if disabled)
                if planning_tasks:
                    plan_results = self._generate_hourly_plans_parallel(planning_tasks)
                else:
                    plan_results = []

                # PHASE 3: Process results and send communications
                for person, hourly_result in plan_results:
                    context = person_contexts[person.id]
                    override = context['override']
                    daily_plan_text = context['daily_plan_text']
                    primary_project = context['primary_project']
                    # person_project is the dict with project details
                    person_project = primary_project if isinstance(primary_project, dict) else {'project_name': 'Unknown Project'}

                    daily_summary = self._summarise_plan(daily_plan_text, max_lines=3)
                    hourly_summary = self._summarise_plan(hourly_result.content)

                    # Store the hourly plan
                    self._store_worker_plan(
                        person_id=person.id,
                        tick=status.current_tick,
                        plan_type="hourly",
                        result=hourly_result,
                        context=None,
                    )

                    # Schedule any explicitly timed comms from the hourly plan
                    try:
                        self._schedule_from_hourly_plan(person, hourly_result.content, status.current_tick)
                    except Exception:
                        pass
                    if override and override[0] == 'SickLeave':
                        continue

                    recipients = self._select_collaborators(person, people)
                    # Dispatch scheduled comms for this tick before any fallback sends
                    se, sc = self._dispatch_scheduled(person, status.current_tick, people_by_id)
                    emails_sent += se
                    chats_sent += sc
                    if se or sc:
                        continue
                    if not recipients:
                        subject = f"Update for {person.name}"
                        body_lines = [
                            f"Project: {person_project['project_name']}",
                            f"Daily focus:\n{daily_summary}",
                            "",
                            f"Hourly plan:\n{hourly_summary}",
                            "",
                            "Keep the runway clear for surprises.",
                        ]
                        body_text = "\n".join(body_lines)
                        if self._can_send(
                            tick=status.current_tick,
                            channel='email',
                            sender=self.sim_manager_email,
                            recipient_key=(person.email_address,),
                            subject=subject,
                            body=body_text,
                        ):
                            dt = self._sim_datetime_for_tick(status.current_tick)
                            self.email_gateway.send_email(
                                sender=self.sim_manager_email,
                                to=[person.email_address],
                                subject=subject,
                                body=body_text,
                                sent_at_iso=(dt.isoformat() if dt else None),
                            )
                            emails_sent += 1
                        self._log_exchange(status.current_tick, None, person.id, "email", subject, body_text)
                        chat_body = f"Quick update: {hourly_summary.replace('\n', ' / ')}\nLet me know if you need support."
                        if self._can_send(
                            tick=status.current_tick,
                            channel='chat',
                            sender=self.sim_manager_handle,
                            recipient_key=(person.chat_handle,),
                            subject=None,
                            body=chat_body,
                        ):
                            dt = self._sim_datetime_for_tick(status.current_tick)
                            self.chat_gateway.send_dm(
                                sender=self.sim_manager_handle,
                                recipient=person.chat_handle,
                                body=chat_body,
                                sent_at_iso=(dt.isoformat() if dt else None),
                            )
                            chats_sent += 1
                        self._log_exchange(status.current_tick, None, person.id, "chat", None, chat_body)
                        continue
                    action_item = self._derive_action_item(hourly_summary, daily_summary)
                    for i, recipient in enumerate(recipients):
                        subject = f"{'업데이트' if self._locale == 'ko' else 'Update'}: {person.name} → {recipient.name}"
                        if self._locale == 'ko':
                            body_lines = [
                                f"{recipient.name.split()[0]}님 안녕하세요,",
                                "",
                                "현재 집중 작업:",
                                hourly_summary or daily_summary or "주요 작업에 집중하고 있습니다.",
                                "",
                                f"요청: {action_item}",
                                "필요하시면 언제든 말씀해 주세요.",
                            ]
                        else:
                            body_lines = [
                                f"Hey {recipient.name.split()[0]},",
                                "",
                                "Current focus:",
                                hourly_summary or daily_summary or "Heads down on deliverables.",
                                "",
                                f"Request: {action_item}",
                                "Ping me if you need anything shifted.",
                            ]
                        body = "\n".join(body_lines)
                        # Suggest CCs for fallback emails (dept head + one relevant peer)
                        cc_suggest: list[str] = []
                        try:
                            head = next((p for p in people if getattr(p, 'is_department_head', False)), None)
                        except Exception:
                            head = None
                        if head and head.id not in {person.id, recipient.id}:
                            cc_email = getattr(head, 'email_address', None)
                            if cc_email:
                                cc_suggest.append(cc_email)
                        def _role(s: str | None) -> str:
                            return (s or '').strip().lower()
                        s_role = _role(getattr(person, 'role', None))
                        want_peer = None
                        if any(k in s_role for k in ("devops", "site reliability")):
                            want_peer = "dev"
                        elif any(k in s_role for k in ("developer", "engineer", "dev")):
                            want_peer = "designer"
                        elif any(k in s_role for k in ("design", "designer")):
                            want_peer = "dev"
                        elif any(k in s_role for k in ("product", "pm", "manager")):
                            want_peer = "dev"
                        if want_peer:
                            for p in people:
                                if p.id in {person.id, recipient.id}:
                                    continue
                                if want_peer in _role(getattr(p, 'role', None)):
                                    peer_email = getattr(p, 'email_address', None)
                                    if peer_email:
                                        cc_suggest.append(peer_email)
                                        break
                        if self._can_send(
                            tick=status.current_tick,
                            channel='email',
                            sender=person.email_address,
                            recipient_key=(recipient.email_address,),
                            subject=subject,
                            body=body,
                        ):
                            dt = self._sim_datetime_for_tick(status.current_tick)
                            self.email_gateway.send_email(
                                sender=person.email_address,
                                to=[recipient.email_address],
                                subject=subject,
                                body=body,
                                cc=cc_suggest,
                                sent_at_iso=(dt.isoformat() if dt else None),
                            )
                            emails_sent += 1
                        self._log_exchange(status.current_tick, person.id, recipient.id, "email", subject, body)

                        if i == 0:
                            chat_body = (f"간단 업데이트: {action_item}" if self._locale == 'ko' else f"Quick update: {action_item}")
                            if self._can_send(
                                tick=status.current_tick,
                                channel='chat',
                                sender=person.chat_handle,
                                recipient_key=(recipient.chat_handle,),
                                subject=None,
                                body=chat_body,
                            ):
                                dt = self._sim_datetime_for_tick(status.current_tick)
                                self.chat_gateway.send_dm(
                                    sender=person.chat_handle,
                                    recipient=recipient.chat_handle,
                                    body=chat_body,
                                    sent_at_iso=(dt.isoformat() if dt else None),
                                )
                                chats_sent += 1
                        self._log_exchange(status.current_tick, person.id, recipient.id, "chat", None, chat_body)

                        inbound = _InboundMessage(
                            sender_id=person.id,
                            sender_name=person.name,
                            subject=subject,
                            summary=action_item,
                            action_item=action_item,
                            message_type="update",
                            channel="email+chat",
                            tick=status.current_tick,
                        )
                        self._queue_runtime_message(recipient, inbound)

                # Generate hourly summaries at the end of each hour (every 60 ticks)
                if status.current_tick % 60 == 0:
                    completed_hour = (status.current_tick // 60) - 1
                    for person in people:
                        try:
                            self._generate_hourly_summary(person, completed_hour)
                        except Exception as e:
                            logger.warning(f"Failed to generate hourly summary for {person.name} hour {completed_hour}: {e}")

                # Generate daily reports at the end of each day
                if status.current_tick % self.hours_per_day == 0:
                    completed_day = (status.current_tick // self.hours_per_day) - 1
                    for person in people:
                        self._generate_daily_report(person, completed_day, project_plan)

            return SimulationAdvanceResult(
                ticks_advanced=ticks,
                current_tick=status.current_tick,
                emails_sent=emails_sent,
                chat_messages_sent=chats_sent,
                sim_time=self._format_sim_time(status.current_tick),
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def inject_event(self, payload: EventCreate) -> dict:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events(type, target_ids, project_id, at_tick, payload)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    payload.type,
                    json.dumps(list(payload.target_ids)),
                    payload.project_id,
                    payload.at_tick,
                    json.dumps(payload.payload or {}),
                ),
            )
            event_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._row_to_event(row)

    def list_events(self) -> List[dict]:
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
        return [self._row_to_event(row) for row in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_worker_runtime(self, person: PersonRead) -> _WorkerRuntime:
        runtime = self._worker_runtime.get(person.id)
        if runtime is None:
            runtime = _WorkerRuntime(person=person)
            self._worker_runtime[person.id] = runtime
            self._load_runtime_messages(runtime)
        else:
            runtime.person = person
        return runtime

    def _sync_worker_runtimes(self, people: Sequence[PersonRead]) -> None:
        active_ids = {person.id for person in people}
        self._update_work_windows(people)
        for person in people:
            self._get_worker_runtime(person)
        for person_id in list(self._worker_runtime.keys()):
            if person_id not in active_ids:
                self._worker_runtime.pop(person_id, None)

    def _load_status_overrides(self) -> None:
        with get_connection() as conn:
            rows = conn.execute("SELECT worker_id, status, until_tick FROM worker_status_overrides").fetchall()
        self._status_overrides = {row["worker_id"]: (row["status"], row["until_tick"]) for row in rows}

    def _queue_runtime_message(self, recipient: PersonRead, message: _InboundMessage) -> None:
        runtime = self._get_worker_runtime(recipient)
        runtime.queue(message)
        self._persist_runtime_message(recipient.id, message)

    def _persist_runtime_message(self, recipient_id: int, message: _InboundMessage) -> None:
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

    def _remove_runtime_messages(self, message_ids: Sequence[int]) -> None:
        if not message_ids:
            return
        with get_connection() as conn:
            conn.executemany("DELETE FROM worker_runtime_messages WHERE id = ?", [(message_id,) for message_id in message_ids])

    def _load_runtime_messages(self, runtime: _WorkerRuntime) -> None:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, payload FROM worker_runtime_messages WHERE recipient_id = ? ORDER BY id",
                (runtime.person.id,),
            ).fetchall()
        runtime.inbox = []
        for row in rows:
            payload = json.loads(row["payload"])
            runtime.inbox.append(
                _InboundMessage(
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

    def _log_exchange(self, tick: int, sender_id: int | None, recipient_id: int | None, channel: str, subject: str | None, summary: str | None) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO worker_exchange_log(tick, sender_id, recipient_id, channel, subject, summary) VALUES (?, ?, ?, ?, ?, ?)",
                (tick, sender_id, recipient_id, channel, subject, summary),
            )

    def _set_status_override(self, worker_id: int, status: str, until_tick: int, reason: str) -> None:
        self._status_overrides[worker_id] = (status, until_tick)
        with get_connection() as conn:
            conn.execute(
                ("INSERT INTO worker_status_overrides(worker_id, status, until_tick, reason) VALUES (?, ?, ?, ?)"
                 " ON CONFLICT(worker_id) DO UPDATE SET status = excluded.status, until_tick = excluded.until_tick, reason = excluded.reason"),
                (worker_id, status, until_tick, reason),
            )

    def _refresh_status_overrides(self, current_tick: int) -> None:
        expired = [worker_id for worker_id, (_, until_tick) in self._status_overrides.items() if until_tick <= current_tick]
        if not expired:
            return
        with get_connection() as conn:
            conn.executemany(
                "DELETE FROM worker_status_overrides WHERE worker_id = ?",
                [(worker_id,) for worker_id in expired],
            )
        for worker_id in expired:
            self._status_overrides.pop(worker_id, None)

    def _reset_runtime_state(self) -> None:
        self._worker_runtime.clear()
        self._status_overrides.clear()
        self._active_person_ids = None
        with get_connection() as conn:
            conn.execute("DELETE FROM worker_runtime_messages")
            conn.execute("DELETE FROM worker_status_overrides")
        self._load_status_overrides()

    def _resolve_active_people(
        self,
        request: SimulationStartRequest | None,
        available: Sequence[PersonRead],
    ) -> list[PersonRead]:
        if not available:
            return []
        if request is None:
            return list(available)

        include_ids = {int(person_id) for person_id in (request.include_person_ids or [])}
        include_names = {name.strip().lower() for name in (request.include_person_names or []) if name.strip()}

        if include_ids or include_names:
            matched = [
                person
                for person in available
                if person.id in include_ids or person.name.lower() in include_names
            ]
            matched_ids = {person.id for person in matched}
            matched_names = {person.name.lower() for person in matched}
            missing_parts: list[str] = []
            missing_ids = sorted(include_ids - matched_ids)
            missing_names = sorted(include_names - matched_names)
            if missing_ids:
                missing_parts.append("ids " + ", ".join(str(identifier) for identifier in missing_ids))
            if missing_names:
                missing_parts.append("names " + ", ".join(missing_names))
            if missing_parts:
                raise RuntimeError("Requested personas not found: " + "; ".join(missing_parts))
        else:
            matched = list(available)

        exclude_ids = {int(person_id) for person_id in (request.exclude_person_ids or [])}
        exclude_names = {name.strip().lower() for name in (request.exclude_person_names or []) if name.strip()}
        filtered = [
            person
            for person in matched
            if person.id not in exclude_ids and person.name.lower() not in exclude_names
        ]
        if not filtered:
            raise RuntimeError("No personas remain after applying include/exclude filters")
        return filtered

    def _get_active_people(self) -> list[PersonRead]:
        available = self.list_people()
        if not available:
            return []
        if self._active_person_ids is None:
            return list(available)
        lookup = {person.id: person for person in available}
        active: list[PersonRead] = []
        for person_id in self._active_person_ids:
            person = lookup.get(person_id)
            if person is not None:
                active.append(person)
        if not active:
            return []
        if len(active) != len(self._active_person_ids):
            self._active_person_ids = [person.id for person in active]
        return active

    def _select_collaborators(self, person: PersonRead, people: Sequence[PersonRead]) -> list[PersonRead]:
        if len(people) <= 1:
            return []
        head = next((p for p in people if getattr(p, "is_department_head", False)), people[0])
        if person.id == head.id:
            return [member for member in people if member.id != person.id][:2]
        recipients: list[PersonRead] = []
        if head.id != person.id:
            recipients.append(head)
        for candidate in people:
            if candidate.id not in {person.id, head.id}:
                recipients.append(candidate)
                break
        return recipients

    def _derive_action_item(self, hourly_summary: str, daily_summary: str) -> str:
        for source in (hourly_summary, daily_summary):
            if not source:
                continue
            for line in source.splitlines():
                cleaned = line.strip().lstrip('-•').strip()
                if cleaned.startswith(("Tick:", "Worker:", "Reason:", "Outline:")):
                    continue
                if cleaned:
                    return cleaned
        return "Keep momentum on the current deliverables"

    def reset(self) -> SimulationState:
        with self._advance_lock:
            self.stop_auto_ticks()
            with get_connection() as conn:
                for table in ("project_plans", "worker_plans", "worker_exchange_log", "worker_runtime_messages", "daily_reports", "simulation_reports", "events", "tick_log"):
                    conn.execute(f"DELETE FROM {table}")
                conn.execute("DELETE FROM worker_status_overrides")
                conn.execute("UPDATE simulation_state SET current_tick = 0, is_running = 0, auto_tick = 0 WHERE id = 1")
            self._project_plan_cache = None
            self._planner_model_hint = None
            self._planner_metrics.clear()
            self.project_duration_weeks = 4
            self._reset_runtime_state()
            people = self.list_people()
            self._update_work_windows(people)
            status = self._fetch_state()
            return SimulationState(
                current_tick=status.current_tick,
                is_running=status.is_running,
                auto_tick=status.auto_tick,
                sim_time=self._format_sim_time(status.current_tick),
            )

    def reset_full(self) -> SimulationState:
        """Resets simulation state and deletes all personas.

        Intended for a destructive "start fresh" action in the dashboard.
        """
        with self._advance_lock:
            # First clear runtime and planning artifacts
            self.reset()
            # Then purge personas (cascades schedule blocks via FK)
            with get_connection() as conn:
                conn.execute("DELETE FROM people")
                conn.execute("DELETE FROM worker_status_overrides")
            # Reset runtime caches after purge
            self._reset_runtime_state()
            self._update_work_windows([])
            status = self._fetch_state()
            return SimulationState(
                current_tick=status.current_tick,
                is_running=status.is_running,
                auto_tick=status.auto_tick,
                sim_time=self._format_sim_time(status.current_tick),
            )

    def _record_event(self, event_type: str, target_ids: Sequence[int], tick: int, payload: dict | None = None) -> None:
        event = EventCreate(type=event_type, target_ids=list(target_ids), at_tick=tick, payload=payload)
        self.inject_event(event)

    def _derive_seed(self, request: SimulationStartRequest | None) -> int:
        if request and request.random_seed is not None:
            return request.random_seed
        base = (request.project_name if request else 'vdos-default').encode('utf-8')
        digest = hashlib.sha256(base).digest()
        return int.from_bytes(digest[:8], 'big')

    def _maybe_generate_events(self, people: Sequence[PersonRead], tick: int, project_plan: dict[str, Any]) -> tuple[dict[int, list[str]], dict[int, list[_InboundMessage]]]:
        adjustments: dict[int, list[str]] = {}
        immediate: dict[int, list[_InboundMessage]] = {}
        if not people:
            return adjustments, immediate
        rng = self._random
        # Gate event generation to humane frequencies to avoid per-minute GPT replanning.
        tick_of_day = (tick - 1) % max(1, self.hours_per_day)

        # Sick leave event: consider once per day around mid-morning.
        if tick_of_day == int(60 * max(1, self.hours_per_day) / 480):  # ~10:00
            # Roughly 5% daily chance across the team
            if rng.random() < 0.05:
                active_people = [p for p in people if self._status_overrides.get(p.id, (None, 0))[0] != 'SickLeave']
                if active_people:
                    target = rng.choice(active_people)
                    until_tick = tick + self.hours_per_day
                self._set_status_override(target.id, 'SickLeave', until_tick, f'Sick leave triggered at tick {tick}')
                rest_message = _InboundMessage(
                    sender_id=0,
                    sender_name='Simulation Manager',
                    subject='Rest and recover',
                    summary='Take the remainder of the day off to recover.',
                    action_item='Pause all work and update once you are back online.',
                    message_type='event',
                    channel='system',
                    tick=tick,
                )
                self._queue_runtime_message(target, rest_message)
                immediate.setdefault(target.id, []).append(rest_message)
                adjustments.setdefault(target.id, []).append('Rest and reschedule tasks due to sudden illness.')

                head = next((p for p in people if getattr(p, 'is_department_head', False)), None)
                if head and head.id != target.id:
                    subject = f'Coverage needed: {target.name} is out sick'
                    body = f"{target.name} reported sick leave at tick {tick}. Please redistribute their urgent work."
                    self.email_gateway.send_email(
                        sender=self.sim_manager_email,
                        to=[head.email_address],
                        subject=subject,
                        body=body,
                    )
                    self._log_exchange(tick, None, head.id, 'email', subject, body)
                    head_message = _InboundMessage(
                        sender_id=0,
                        sender_name='Simulation Manager',
                        subject=subject,
                        summary=body,
                        action_item=f'Coordinate cover for {target.name}.',
                        message_type='event',
                        channel='email',
                        tick=tick,
                    )
                    self._queue_runtime_message(head, head_message)
                    immediate.setdefault(head.id, []).append(head_message)
                    adjustments.setdefault(head.id, []).append(f'Coordinate cover while {target.name} recovers.')

                self._record_event('sick_leave', [target.id], tick, {'until_tick': until_tick})

        # Client feature request: at most a few times per day (every ~2 hours), low probability.
        if (tick_of_day % int(120 * max(1, self.hours_per_day) / 480) == 0) and (rng.random() < 0.10):
            head = next((p for p in people if getattr(p, 'is_department_head', False)), people[0])
            feature = rng.choice([
                'refresh hero messaging',
                'prepare launch analytics dashboard',
                'add testimonial carousel',
                'deliver onboarding walkthrough',
            ])
            subject = f'Client request: {feature}'
            body = f"Client requested {feature}. Align on next steps within this cycle."
            head_message = _InboundMessage(
                sender_id=0,
                sender_name='Simulation Manager',
                subject=subject,
                summary=body,
                action_item=f'Plan response to client request: {feature}.',
                message_type='event',
                channel='email',
                tick=tick,
            )
            self._queue_runtime_message(head, head_message)
            immediate.setdefault(head.id, []).append(head_message)
            adjustments.setdefault(head.id, []).append(f'Plan response to client request: {feature}.')

            collaborators = [p for p in people if p.id != head.id]
            if collaborators:
                partner = rng.choice(collaborators)
                partner_message = _InboundMessage(
                    sender_id=head.id,
                    sender_name=head.name,
                    subject=subject,
                    summary=f'Partner with {head.name} on {feature}.',
                    action_item=f'Support {head.name} on {feature}.',
                    message_type='event',
                    channel='chat',
                    tick=tick,
                )
                self._queue_runtime_message(partner, partner_message)
                immediate.setdefault(partner.id, []).append(partner_message)
                adjustments.setdefault(partner.id, []).append(f'Partner with {head.name} on client request: {feature}.')
                chat_body = f"Client request: {feature}. Let's sync on next steps."
                targets = [head.id, partner.id]
            else:
                targets = [head.id]
            self._record_event('client_feature_request', targets, tick, {'feature': feature})

        return adjustments, immediate

    def _bootstrap_channels(self) -> None:
        self.email_gateway.ensure_mailbox(self.sim_manager_email, "Simulation Manager")
        self.chat_gateway.ensure_user(self.sim_manager_handle, "Simulation Manager")

    def _ensure_state_row(self) -> None:
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM simulation_state WHERE id = 1").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO simulation_state(id, current_tick, is_running, auto_tick) VALUES (1, 0, 0, 0)"
                )

    def _fetch_state(self) -> SimulationStatus:
        with get_connection() as conn:
            row = conn.execute("SELECT current_tick, is_running, auto_tick FROM simulation_state WHERE id = 1").fetchone()
        return SimulationStatus(current_tick=row["current_tick"], is_running=bool(row["is_running"]), auto_tick=bool(row["auto_tick"]))

    def _set_running(self, running: bool) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET is_running = ? WHERE id = 1",
                (1 if running else 0,),
            )

    def _set_auto_tick(self, enabled: bool) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET auto_tick = ? WHERE id = 1",
                (1 if enabled else 0,),
            )

    def _update_tick(self, tick: int, reason: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET current_tick = ? WHERE id = 1",
                (tick,),
            )
            conn.execute(
                "INSERT INTO tick_log(tick, reason) VALUES (?, ?)",
                (tick, reason),
            )

    def _row_to_person(self, row) -> PersonRead:
        person_id = row["id"]
        schedule = self._fetch_schedule(person_id)
        # Check if team_name column exists (for backward compatibility)
        try:
            team_name = row["team_name"]
        except (KeyError, IndexError):
            team_name = None
        return PersonRead(
            id=person_id,
            name=row["name"],
            role=row["role"],
            timezone=row["timezone"],
            work_hours=row["work_hours"],
            break_frequency=row["break_frequency"],
            communication_style=row["communication_style"],
            email_address=row["email_address"],
            chat_handle=row["chat_handle"],
            is_department_head=bool(row["is_department_head"]),
            team_name=team_name,
            skills=json.loads(row["skills"]),
            personality=json.loads(row["personality"]),
            objectives=json.loads(row["objectives"]),
            metrics=json.loads(row["metrics"]),
            schedule=[ScheduleBlockIn(**block) for block in schedule],
            planning_guidelines=json.loads(row["planning_guidelines"]),
            event_playbook=json.loads(row["event_playbook"]),
            statuses=json.loads(row["statuses"]),
            persona_markdown=row["persona_markdown"],
        )

    def _fetch_schedule(self, person_id: int) -> List[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT start, end, activity FROM schedule_blocks WHERE person_id = ? ORDER BY id",
                (person_id,),
            ).fetchall()
        return [
            {"start": row["start"], "end": row["end"], "activity": row["activity"]}
            for row in rows
        ]

    def _row_to_event(self, row) -> dict:
        return {
            "id": row["id"],
            "type": row["type"],
            "target_ids": json.loads(row["target_ids"] or "[]"),
            "project_id": row["project_id"],
            "at_tick": row["at_tick"],
            "payload": json.loads(row["payload"] or "{}"),
        }

    def _to_persona(self, payload: PersonCreate) -> WorkerPersona:
        return WorkerPersona(
            name=payload.name,
            role=payload.role,
            skills=tuple(payload.skills),
            personality=tuple(payload.personality),
            timezone=payload.timezone,
            work_hours=payload.work_hours,
            break_frequency=payload.break_frequency,
            communication_style=payload.communication_style,
            email_address=payload.email_address,
            chat_handle=payload.chat_handle,
            objectives=tuple(payload.objectives or ()),
            metrics=tuple(payload.metrics or ()),
        )

    def close(self) -> None:
        self.stop_auto_ticks()
        close_email = getattr(self.email_gateway, "close", None)
        if callable(close_email):
            close_email()
        close_chat = getattr(self.chat_gateway, "close", None)
        if callable(close_chat):
            close_chat()






