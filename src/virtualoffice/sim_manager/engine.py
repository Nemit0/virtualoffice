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
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore
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
from .communication_generator import CommunicationGenerator
from .inbox_manager import InboxManager
from .participation_balancer import ParticipationBalancer
from .quality_metrics import QualityMetricsTracker
from .plan_parser import PlanParser, ParsingError

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
        self.hours_per_day = hours_per_day
        self.planner = planner or GPTPlanner(hours_per_day=hours_per_day)
        self._stub_planner = StubPlanner()
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
        # Communication staggering to avoid synchronized blasts
        try:
            self._comm_stagger_max_minutes = int(os.getenv("VDOS_COMM_STAGGER_MAX_MINUTES", "7"))
        except ValueError:
            self._comm_stagger_max_minutes = 7
        self._avoid_round_minutes = os.getenv("VDOS_AVOID_ROUND_MINUTES", "true").strip().lower() in {"1", "true", "yes", "on"}
        self._current_seed: int | None = None
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
        # Initialize plan_parser placeholder (will be properly set in start() method)
        self.plan_parser = None
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
        
        # Auto-pause configuration - default to enabled with validation
        try:
            env_auto_pause = os.getenv("VDOS_AUTO_PAUSE_ON_PROJECT_END", "true").strip().lower()
            if env_auto_pause in {"1", "true", "yes", "on"}:
                self._auto_pause_enabled = True
            elif env_auto_pause in {"0", "false", "no", "off"}:
                self._auto_pause_enabled = False
            else:
                logger.warning(f"Invalid VDOS_AUTO_PAUSE_ON_PROJECT_END value '{env_auto_pause}', defaulting to enabled")
                self._auto_pause_enabled = True
            logger.info(f"Auto-pause on project end initialized: {'enabled' if self._auto_pause_enabled else 'disabled'}")
        except Exception as exc:
            logger.error(f"Failed to parse auto-pause configuration, defaulting to enabled: {exc}")
            self._auto_pause_enabled = True
        
        # Initialize communication diversity components
        # Note: These will be properly initialized in start() when seed is available
        self.communication_generator: CommunicationGenerator | None = None
        self.inbox_manager = InboxManager()
        self.participation_balancer = ParticipationBalancer(
            enabled=os.getenv("VDOS_PARTICIPATION_BALANCE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        )
        self.quality_metrics = QualityMetricsTracker()
        
        # Daily message limits tracking (safety net)
        # Key: (person_id, day_index), Value: {"email": count, "chat": count}
        self._daily_message_counts: dict[tuple[int, int], dict[str, int]] = {}
        
        # Volume metrics tracking for monitoring and debugging
        # Key: day_index, Value: dict with metrics
        self._volume_metrics: dict[int, dict[str, Any]] = {}
        
        # Email Volume Reduction Configuration (v2.0)
        # New configuration variables for purposeful communication
        try:
            env_auto_fallback = os.getenv("VDOS_ENABLE_AUTO_FALLBACK", "false").strip().lower()
            self._enable_auto_fallback = env_auto_fallback in {"1", "true", "yes", "on"}
            logger.info(f"Auto-fallback communication: {'enabled' if self._enable_auto_fallback else 'disabled'}")
        except Exception as exc:
            logger.error(f"Failed to parse VDOS_ENABLE_AUTO_FALLBACK, defaulting to disabled: {exc}")
            self._enable_auto_fallback = False
        
        try:
            env_inbox_replies = os.getenv("VDOS_ENABLE_INBOX_REPLIES", "true").strip().lower()
            self._enable_inbox_replies = env_inbox_replies in {"1", "true", "yes", "on"}
            logger.info(f"Inbox-driven replies: {'enabled' if self._enable_inbox_replies else 'disabled'}")
        except Exception as exc:
            logger.error(f"Failed to parse VDOS_ENABLE_INBOX_REPLIES, defaulting to enabled: {exc}")
            self._enable_inbox_replies = True
        
        try:
            self._inbox_reply_probability = float(os.getenv("VDOS_INBOX_REPLY_PROBABILITY", "0.80"))
            if not 0.0 <= self._inbox_reply_probability <= 1.0:
                logger.warning(f"VDOS_INBOX_REPLY_PROBABILITY must be between 0.0 and 1.0, got {self._inbox_reply_probability}, defaulting to 0.80")
                self._inbox_reply_probability = 0.80
        except ValueError:
            logger.warning("Invalid VDOS_INBOX_REPLY_PROBABILITY value, defaulting to 0.80")
            self._inbox_reply_probability = 0.80
        
        # Communication diversity configuration (legacy, used when auto-fallback enabled)
        try:
            self._threading_rate = float(os.getenv("VDOS_THREADING_RATE", "0.3"))
            if not 0.0 <= self._threading_rate <= 1.0:
                logger.warning(f"VDOS_THREADING_RATE must be between 0.0 and 1.0, got {self._threading_rate}, defaulting to 0.3")
                self._threading_rate = 0.3
        except ValueError:
            logger.warning("Invalid VDOS_THREADING_RATE value, defaulting to 0.3")
            self._threading_rate = 0.3
        
        try:
            self._fallback_probability = float(os.getenv("VDOS_FALLBACK_PROBABILITY", "0.6"))
            if not 0.0 <= self._fallback_probability <= 1.0:
                logger.warning(f"VDOS_FALLBACK_PROBABILITY must be between 0.0 and 1.0, got {self._fallback_probability}, defaulting to 0.6")
                self._fallback_probability = 0.6
        except ValueError:
            logger.warning("Invalid VDOS_FALLBACK_PROBABILITY value, defaulting to 0.6")
            self._fallback_probability = 0.6
        
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
    
    def _check_daily_limits(
        self,
        person_id: int,
        day_index: int,
        channel: str
    ) -> bool:
        """
        Check if persona has reached daily message limits.
        
        Returns True if message can be sent, False if limit reached.
        """
        try:
            max_emails = int(os.getenv("VDOS_MAX_EMAILS_PER_DAY", "50"))
        except ValueError:
            logger.warning("Invalid VDOS_MAX_EMAILS_PER_DAY value, defaulting to 50")
            max_emails = 50
        
        try:
            max_chats = int(os.getenv("VDOS_MAX_CHATS_PER_DAY", "100"))
        except ValueError:
            logger.warning("Invalid VDOS_MAX_CHATS_PER_DAY value, defaulting to 100")
            max_chats = 100
        
        key = (person_id, day_index)
        counts = self._daily_message_counts.get(key, {"email": 0, "chat": 0})
        
        if channel == "email" and counts["email"] >= max_emails:
            logger.warning(
                f"[DAILY_LIMIT] Person {person_id} reached email limit "
                f"({max_emails}/day) on day {day_index}"
            )
            # Track that limit was hit
            if day_index not in self._volume_metrics:
                self._volume_metrics[day_index] = {
                    "total_emails": 0,
                    "total_chats": 0,
                    "emails_by_person": {},
                    "chats_by_person": {},
                    "json_communications": 0,
                    "inbox_replies": 0,
                    "daily_limits_hit": [],
                }
            limit_event = {"person_id": person_id, "channel": "email", "limit": max_emails}
            if limit_event not in self._volume_metrics[day_index]["daily_limits_hit"]:
                self._volume_metrics[day_index]["daily_limits_hit"].append(limit_event)
            return False
        
        if channel == "chat" and counts["chat"] >= max_chats:
            logger.warning(
                f"[DAILY_LIMIT] Person {person_id} reached chat limit "
                f"({max_chats}/day) on day {day_index}"
            )
            # Track that limit was hit
            if day_index not in self._volume_metrics:
                self._volume_metrics[day_index] = {
                    "total_emails": 0,
                    "total_chats": 0,
                    "emails_by_person": {},
                    "chats_by_person": {},
                    "json_communications": 0,
                    "inbox_replies": 0,
                    "daily_limits_hit": [],
                }
            limit_event = {"person_id": person_id, "channel": "chat", "limit": max_chats}
            if limit_event not in self._volume_metrics[day_index]["daily_limits_hit"]:
                self._volume_metrics[day_index]["daily_limits_hit"].append(limit_event)
            return False
        
        return True
    
    def _record_daily_message(
        self,
        person_id: int,
        day_index: int,
        channel: str
    ) -> None:
        """Record a sent message for daily limit tracking."""
        key = (person_id, day_index)
        if key not in self._daily_message_counts:
            self._daily_message_counts[key] = {"email": 0, "chat": 0}
        
        self._daily_message_counts[key][channel] += 1
        
        # Also update volume metrics
        self._update_volume_metrics(person_id, day_index, channel)
    
    def _update_volume_metrics(
        self,
        person_id: int,
        day_index: int,
        channel: str,
        source: str = "unknown"
    ) -> None:
        """Update volume metrics for monitoring and debugging."""
        if day_index not in self._volume_metrics:
            self._volume_metrics[day_index] = {
                "total_emails": 0,
                "total_chats": 0,
                "emails_by_person": {},
                "chats_by_person": {},
                "json_communications": 0,
                "inbox_replies": 0,
                "daily_limits_hit": [],
            }
        
        metrics = self._volume_metrics[day_index]
        
        if channel == "email":
            metrics["total_emails"] += 1
            metrics["emails_by_person"][person_id] = metrics["emails_by_person"].get(person_id, 0) + 1
        elif channel == "chat":
            metrics["total_chats"] += 1
            metrics["chats_by_person"][person_id] = metrics["chats_by_person"].get(person_id, 0) + 1
        
        # Track source if provided
        if source == "json":
            metrics["json_communications"] += 1
        elif source == "inbox_reply":
            metrics["inbox_replies"] += 1
    
    def get_volume_metrics(self) -> dict[str, Any]:
        """Get volume metrics for the current simulation day."""
        state = self.get_state()
        current_tick = state.current_tick
        day_ticks = max(1, self.hours_per_day * 60)
        day_index = (current_tick - 1) // day_ticks if current_tick > 0 else 0
        
        # Get metrics for current day
        metrics = self._volume_metrics.get(day_index, {
            "total_emails": 0,
            "total_chats": 0,
            "emails_by_person": {},
            "chats_by_person": {},
            "json_communications": 0,
            "inbox_replies": 0,
            "daily_limits_hit": [],
        })
        
        # Calculate averages
        people = self.list_people()
        active_people_count = len(people) if people else 1
        
        avg_emails_per_person = metrics["total_emails"] / active_people_count if active_people_count > 0 else 0
        avg_chats_per_person = metrics["total_chats"] / active_people_count if active_people_count > 0 else 0
        
        # Calculate rates
        total_communications = metrics["json_communications"] + metrics["inbox_replies"]
        json_communication_rate = (
            metrics["json_communications"] / total_communications 
            if total_communications > 0 else 0
        )
        inbox_reply_rate = (
            metrics["inbox_replies"] / total_communications 
            if total_communications > 0 else 0
        )
        
        # Get threading rate from quality metrics
        quality_metrics = self.quality_metrics.get_all_metrics()
        threading_rate = quality_metrics.get("threading_rate", {}).get("current", 0)
        
        return {
            "day_index": day_index,
            "current_tick": current_tick,
            "total_emails_today": metrics["total_emails"],
            "total_chats_today": metrics["total_chats"],
            "avg_emails_per_person": round(avg_emails_per_person, 2),
            "avg_chats_per_person": round(avg_chats_per_person, 2),
            "json_communication_rate": round(json_communication_rate, 3),
            "inbox_reply_rate": round(inbox_reply_rate, 3),
            "threading_rate": round(threading_rate, 3),
            "daily_limits_hit": metrics.get("daily_limits_hit", []),
            "emails_by_person": metrics["emails_by_person"],
            "chats_by_person": metrics["chats_by_person"],
        }
    
    # --- Scheduled comms parsing/dispatch ---

    def _try_parse_json_communications(self, plan_text: str) -> list[dict[str, Any]] | None:
        """
        Attempt to extract and parse JSON communications block from plan text.
        Returns list of communication dicts if successful, None if JSON not found or invalid.
        """
        import json
        import re

        # Try to find JSON block in the plan (between ```json and ``` or just {...})
        json_patterns = [
            r'```json\s*\n(.*?)\n```',  # Markdown JSON code block
            r'```\s*\n(\{.*?\})\n```',   # Generic code block with JSON
            r'(\{[\s\S]*"communications"[\s\S]*\})',  # Raw JSON object
        ]

        json_text = None
        for pattern in json_patterns:
            match = re.search(pattern, plan_text, re.DOTALL | re.IGNORECASE)
            if match:
                json_text = match.group(1).strip()
                break

        if not json_text:
            return None

        # Try to parse JSON
        try:
            data = json.loads(json_text)
            if isinstance(data, dict) and 'communications' in data:
                return data['communications']
            return None
        except json.JSONDecodeError:
            # Attempt to repair common JSON errors
            repaired = self._repair_json(json_text)
            if repaired:
                try:
                    data = json.loads(repaired)
                    if isinstance(data, dict) and 'communications' in data:
                        logger.info(f"Successfully repaired malformed JSON in plan")
                        return data['communications']
                except json.JSONDecodeError:
                    pass

            logger.debug(f"Failed to parse JSON communications block")
            return None

    def _repair_json(self, json_text: str) -> str | None:
        """
        Attempt to fix common JSON formatting errors made by LLMs.
        Returns repaired JSON string or None if repair fails.
        """
        try:
            # Fix common issues
            repaired = json_text

            # Remove trailing commas before } or ]
            repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)

            # Replace single quotes with double quotes (be careful with apostrophes)
            # Only replace if they're likely JSON quotes (after : or [ or ,)
            repaired = re.sub(r"(?<=:)\s*'([^']*)'", r' "\1"', repaired)
            repaired = re.sub(r"(?<=\[)\s*'([^']*)'", r' "\1"', repaired)
            repaired = re.sub(r"(?<=,)\s*'([^']*)'", r' "\1"', repaired)

            # Remove JSON comments (// ... or /* ... */)
            repaired = re.sub(r'//.*?$', '', repaired, flags=re.MULTILINE)
            repaired = re.sub(r'/\*.*?\*/', '', repaired, flags=re.DOTALL)

            # Fix unescaped newlines in strings (rough heuristic)
            # This is tricky, so we'll skip it for now

            return repaired
        except Exception:
            return None

    def _process_json_communications(
        self,
        communications: list[dict[str, Any]],
        current_tick: int,
        person: PersonRead,
        source: str = "json"
    ) -> None:
        """
        Process parsed JSON communications and schedule them.
        
        Args:
            communications: List of communication dicts
            current_tick: Current simulation tick
            person: Persona sending the communications
            source: Source of communications ('json' or 'fallback')
        """
        ticks_per_day = max(1, self.hours_per_day * 60)
        day_index = (current_tick - 1) // ticks_per_day
        tick_of_day = (current_tick - 1) % ticks_per_day
        base_tick = day_index * ticks_per_day + 1
        sched = self._scheduled_comms.setdefault(person.id, {})

        for comm in communications:
            try:
                comm_type = comm.get('type', '').lower()
                time_str = comm.get('time', '')

                if not time_str or not comm_type:
                    continue

                # Parse time
                try:
                    hh, mm = [int(x) for x in time_str.split(':', 1)]
                    minutes = hh * 60 + mm
                    scheduled_tick_of_day = int(round(minutes * ticks_per_day / 1440))
                except Exception:
                    logger.warning(f"Invalid time format in JSON communication: {time_str}")
                    continue

                # Skip if time already passed
                if scheduled_tick_of_day <= tick_of_day:
                    continue

                t = base_tick + scheduled_tick_of_day

                # Build entry based on type
                if comm_type == 'email':
                    target = comm.get('to', '').strip()
                    if not target:
                        continue

                    # Combine subject and body with | separator
                    subject = comm.get('subject', '').strip()
                    body = comm.get('body', '').strip()
                    payload = f"{subject} | {body}" if subject and body else subject or body

                    entry = {
                        'channel': 'email',
                        'target': target,
                        'payload': payload,
                        '_source': source  # Track source for metrics
                    }

                    # Add cc/bcc if present
                    cc = comm.get('cc', [])
                    bcc = comm.get('bcc', [])
                    if cc:
                        entry['cc'] = cc if isinstance(cc, list) else [x.strip() for x in cc.split(',')]
                    if bcc:
                        entry['bcc'] = bcc if isinstance(bcc, list) else [x.strip() for x in bcc.split(',')]

                    # Check for reply_to
                    reply_to = comm.get('reply_to')
                    if reply_to:
                        entry['reply_to_email_id'] = reply_to

                elif comm_type == 'chat':
                    target = comm.get('target', '').strip()
                    message = comm.get('message', '').strip()

                    if not target or not message:
                        continue

                    entry = {
                        'channel': 'chat',
                        'target': target,
                        'payload': message,
                        '_source': source  # Track source for metrics
                    }

                else:
                    logger.warning(f"Unknown communication type in JSON: {comm_type}")
                    continue

                # Add to schedule (deduplicate)
                existing = sched.setdefault(t, [])
                if entry not in existing:
                    existing.append(entry)

            except Exception as e:
                logger.warning(f"Error processing JSON communication: {e}")
                continue

    def _get_recent_hourly_plan(self, person_id: int) -> str | None:
        """
        Get the most recent hourly plan for a persona.
        
        Used to provide context when generating inbox-driven replies.
        
        Args:
            person_id: ID of the persona
            
        Returns:
            Most recent hourly plan content, or None if not found
        """
        try:
            with get_connection() as conn:
                cursor = conn.execute("""
                    SELECT content FROM worker_plans
                    WHERE person_id = ? AND plan_type = 'hourly'
                    ORDER BY tick DESC LIMIT 1
                """, (person_id,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.warning(f"Failed to get recent hourly plan for person_id={person_id}: {e}")
            return None

    def _get_recent_daily_plan(self, person_id: int) -> str | None:
        """
        Get the most recent daily plan for a persona.
        
        Used to provide context when generating inbox-driven replies.
        
        Args:
            person_id: ID of the persona
            
        Returns:
            Most recent daily plan content, or None if not found
        """
        try:
            with get_connection() as conn:
                cursor = conn.execute("""
                    SELECT content FROM worker_plans
                    WHERE person_id = ? AND plan_type = 'daily'
                    ORDER BY tick DESC LIMIT 1
                """, (person_id,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.warning(f"Failed to get recent daily plan for person_id={person_id}: {e}")
            return None

    def _try_generate_inbox_reply(
        self,
        person: PersonRead,
        current_tick: int,
        people_by_id: dict[int, PersonRead]
    ) -> bool:
        """
        Generate a reply to an unreplied inbox message if appropriate.
        
        This method implements inbox-driven reply generation as part of the
        email volume reduction strategy. Instead of automatic fallback communications,
        personas now reply to received messages that need responses.
        
        Requirements: R-2.1, R-2.2, R-2.3, R-2.4, R-2.5
        
        Args:
            person: The persona who might reply
            current_tick: Current simulation tick
            people_by_id: Dictionary of all personas by ID
            
        Returns:
            True if a reply was generated and sent, False otherwise
        """
        # Check if inbox replies are enabled
        inbox_replies_enabled = os.getenv("VDOS_ENABLE_INBOX_REPLIES", "true").strip().lower() in {"1", "true", "yes", "on"}
        if not inbox_replies_enabled:
            return False
        
        # Task 6: Block ALL communication generation for away/offline personas
        # Check status before attempting any communication generation
        override = self._status_overrides.get(person.id)
        offline_statuses = {"SickLeave", "Offline", "Absent", "Vacation", "Leave", "Away", "휴가", "병가", "자리비움"}
        if override and (override[0] in offline_statuses):
            logger.debug(
                f"[STATUS_BLOCK] Blocking inbox reply for {person.name} due to status: {override[0]} "
                f"(tick={current_tick})"
            )
            return False
        
        # Get reply probability from environment (use instance variable for consistency)
        reply_probability = self._inbox_reply_probability
        if reply_probability <= 0:
            return False
        
        # Get unreplied messages from inbox
        inbox_messages = self.inbox_manager.get_inbox(person.id, max_messages=5)
        unreplied = [msg for msg in inbox_messages if msg.needs_reply and msg.replied_tick is None]
        
        if not unreplied:
            logger.debug(f"[INBOX_REPLY] No unreplied messages for {person.name}")
            return False
        
        # Limit to 1 reply per hour to avoid reply storms
        # Check if already replied this hour
        hour_start = (current_tick // 60) * 60
        recent_replies = [
            msg for msg in inbox_messages 
            if msg.replied_tick and msg.replied_tick >= hour_start
        ]
        if recent_replies:
            logger.debug(
                f"[INBOX_REPLY] Already replied this hour for {person.name}, skipping "
                f"(replied_tick={recent_replies[0].replied_tick}, hour_start={hour_start})"
            )
            return False
        
        # Probabilistic reply decision (deterministic with seed)
        if self._random.random() > reply_probability:
            logger.debug(
                f"[INBOX_REPLY] Probability check failed for {person.name} "
                f"(probability={reply_probability})"
            )
            return False
        
        # Select message to reply to (prioritize questions and requests)
        # InboxManager already prioritizes messages needing replies
        message_to_reply = unreplied[0]
        
        logger.info(
            f"[INBOX_REPLY] Attempting to generate reply for {person.name} "
            f"to message from {message_to_reply.sender_name} "
            f"(type={message_to_reply.message_type}, tick={current_tick})"
        )
        
        # Generate reply using CommunicationGenerator
        if self.communication_generator is None:
            logger.warning(
                f"[INBOX_REPLY] CommunicationGenerator not available for {person.name}, "
                f"skipping inbox reply"
            )
            return False
        
        try:
            # Get project context and collaborators
            # Fix: Use calendar weeks (10080 ticks = 7*24*60) to match project configuration (REQ-2.1.2)
            # Projects are configured in calendar weeks, not work weeks
            TICKS_PER_CALENDAR_WEEK = 7 * 24 * 60  # 10,080 ticks
            current_week = ((current_tick - 1) // TICKS_PER_CALENDAR_WEEK) + 1 if current_tick > 0 else 1
            active_projects = self._get_all_active_projects_for_person(person.id, current_week)
            project = active_projects[0] if active_projects else None
            
            # Get project-specific collaborators (only people on same projects)
            collaborators = self._get_project_collaborators(
                person_id=person.id,
                current_week=current_week,
                all_people=people_by_id,
                project_id=project.id if project else None
            )
            
            # Get recent hourly and daily plans for context
            hourly_plan = self._get_recent_hourly_plan(person.id)
            daily_plan = self._get_recent_daily_plan(person.id)
            
            # Format inbox message for CommunicationGenerator
            inbox_context = [{
                "sender_name": message_to_reply.sender_name,
                "subject": message_to_reply.subject,
                "body": message_to_reply.body,
                "message_type": message_to_reply.message_type,
                "thread_id": message_to_reply.thread_id
            }]
            
            # Generate reply
            logger.debug(
                f"[INBOX_REPLY] Calling CommunicationGenerator for {person.name} "
                f"with inbox_context={len(inbox_context)} messages"
            )
            
            generated_comms = self.communication_generator.generate_fallback_communications(
                person=person,
                current_tick=current_tick,
                hourly_plan=hourly_plan,
                daily_plan=daily_plan,
                project=project,
                inbox_messages=inbox_context,
                collaborators=collaborators
            )
            
            if not generated_comms:
                logger.debug(
                    f"[INBOX_REPLY] No communications generated for {person.name}"
                )
                return False
            
            logger.info(
                f"[INBOX_REPLY] Generated {len(generated_comms)} communications "
                f"for {person.name} in response to {message_to_reply.sender_name}"
            )
            
            # Process the generated reply through the standard communication pipeline
            # Add time field to communications (schedule for immediate dispatch)
            current_hour = (current_tick % (ticks_per_day)) // 60
            current_minute = (current_tick % (ticks_per_day)) % 60
            time_str = f"{current_hour:02d}:{current_minute:02d}"
            
            for comm in generated_comms:
                if 'time' not in comm:
                    comm['time'] = time_str
                # If replying to an email, add thread_id for threading
                if comm.get('type') == 'email' and message_to_reply.thread_id:
                    comm['thread_id'] = message_to_reply.thread_id
            
            self._process_json_communications(
                generated_comms, 
                current_tick, 
                person, 
                source="inbox_reply"
            )
            
            # Dispatch the reply immediately
            se, sc = self._dispatch_scheduled(person, current_tick, people_by_id)
            
            if se > 0 or sc > 0:
                # Mark message as replied
                self.inbox_manager.mark_replied(
                    person_id=person.id,
                    message_id=message_to_reply.message_id,
                    replied_tick=current_tick
                )
                logger.info(
                    f"[INBOX_REPLY] {person.name} replied to message from "
                    f"{message_to_reply.sender_name} (emails={se}, chats={sc}, tick={current_tick})"
                )
                return True
            else:
                logger.debug(
                    f"[INBOX_REPLY] No messages dispatched for {person.name} "
                    f"after generating reply"
                )
                return False
        
        except Exception as e:
            logger.warning(
                f"[INBOX_REPLY] Failed to generate inbox reply for {person.name}: {e}",
                exc_info=True
            )
            return False

    def _prepare_inbox_reply_request(
        self,
        person: PersonRead,
        current_tick: int,
        people_by_id: dict[int, PersonRead],
        day_index: int,
        person_project: dict[str, Any],
        hourly_summary: str,
        daily_summary: str,
        current_week: int
    ) -> dict[str, Any] | None:
        """
        Check if a persona should generate an inbox reply and prepare the request data.

        This method performs all the checks (enabled, status, probability, limits)
        and returns a request dict if the persona should reply, or None otherwise.

        Used by batch processing to collect all inbox reply requests before processing.

        Args:
            person: The persona who might reply
            current_tick: Current simulation tick
            people_by_id: Dictionary of all personas by ID
            day_index: Current day index
            person_project: Project context for the persona
            hourly_summary: Summary of hourly plan
            daily_summary: Summary of daily plan
            current_week: Current week number

        Returns:
            Request dict if persona should reply, None otherwise
        """
        # Check if inbox replies are enabled
        inbox_replies_enabled = os.getenv("VDOS_ENABLE_INBOX_REPLIES", "true").strip().lower() in {"1", "true", "yes", "on"}
        if not inbox_replies_enabled:
            return None

        # Task 6: Block ALL communication generation for away/offline personas
        override = self._status_overrides.get(person.id)
        offline_statuses = {"SickLeave", "Offline", "Absent", "Vacation", "Leave", "Away", "휴가", "병가", "자리비움"}
        if override and (override[0] in offline_statuses):
            logger.debug(
                f"[INBOX_REPLY_BATCH] Blocking inbox reply for {person.name} due to status: {override[0]} "
                f"(tick={current_tick})"
            )
            return None

        # Get reply probability from environment (use instance variable for consistency)
        reply_probability = self._inbox_reply_probability
        if reply_probability <= 0:
            return None

        # Get unreplied messages from inbox
        inbox_messages = self.inbox_manager.get_inbox(person.id, max_messages=5)
        unreplied = [msg for msg in inbox_messages if msg.needs_reply and msg.replied_tick is None]

        if not unreplied:
            return None

        # Limit to 1 reply per hour to avoid reply storms
        hour_start = (current_tick // 60) * 60
        recent_replies = [
            msg for msg in inbox_messages
            if msg.replied_tick and msg.replied_tick >= hour_start
        ]
        if recent_replies:
            logger.debug(
                f"[INBOX_REPLY_BATCH] Already replied this hour for {person.name}, skipping "
                f"(replied_tick={recent_replies[0].replied_tick}, hour_start={hour_start})"
            )
            return None

        # Probabilistic reply decision (deterministic with seed)
        if self._random.random() > reply_probability:
            return None

        # Check if CommunicationGenerator is available
        if self.communication_generator is None:
            logger.warning(
                f"[INBOX_REPLY_BATCH] CommunicationGenerator not available for {person.name}, "
                f"skipping inbox reply"
            )
            return None

        # Select message to reply to (prioritize questions and requests)
        message_to_reply = unreplied[0]

        # Get project context and collaborators
        active_projects = self._get_all_active_projects_for_person(person.id, current_week)
        project = active_projects[0] if active_projects else None

        # Get project-specific collaborators (only people on same projects)
        collaborators = self._get_project_collaborators(
            person_id=person.id,
            current_week=current_week,
            all_people=people_by_id,
            project_id=project["id"] if isinstance(project, dict) else getattr(project, "id", None) if project else None
        )
        
        hourly_plan = self._get_recent_hourly_plan(person.id)
        daily_plan = self._get_recent_daily_plan(person.id)

        # Format inbox message for CommunicationGenerator
        inbox_context = [{
            "sender_name": message_to_reply.sender_name,
            "subject": message_to_reply.subject,
            "body": message_to_reply.body,
            "message_type": message_to_reply.message_type,
            "thread_id": message_to_reply.thread_id
        }]

        logger.info(
            f"[INBOX_REPLY_BATCH] Collecting reply request for {person.name} "
            f"to message from {message_to_reply.sender_name} "
            f"(type={message_to_reply.message_type}, tick={current_tick})"
        )

        # Return request dict for batch processing
        return {
            "person": person,
            "current_tick": current_tick,
            "hourly_plan": hourly_plan,
            "daily_plan": daily_plan,
            "project": project,
            "inbox_messages": inbox_context,
            "collaborators": collaborators,
            "message_to_reply": message_to_reply,
            "day_index": day_index
        }

    def _process_inbox_reply_batch(
        self,
        inbox_reply_requests: list[dict[str, Any]],
        current_tick: int,
        people_by_id: dict[int, PersonRead]
    ) -> tuple[int, int]:
        """
        Process multiple inbox reply requests in batch using async parallelization.

        This method implements batch processing for inbox replies, providing 4-5x
        performance improvement over sequential processing when multiple personas
        need to reply at the same time.

        Performance: O(max(n)) instead of O(sum(n)) for n GPT API calls

        Args:
            inbox_reply_requests: List of request dicts from _prepare_inbox_reply_request
            current_tick: Current simulation tick
            people_by_id: Dictionary of all personas by ID

        Returns:
            Tuple of (emails_sent, chats_sent)
        """
        if not inbox_reply_requests:
            return (0, 0)

        logger.info(
            f"[INBOX_REPLY_BATCH] Processing {len(inbox_reply_requests)} inbox reply requests "
            f"(tick={current_tick})"
        )

        emails_sent = 0
        chats_sent = 0

        try:
            # Use async batch processing for performance
            import asyncio

            batch_results = asyncio.run(
                self.communication_generator.generate_batch_async(inbox_reply_requests)
            )

            # Process each result
            for person, generated_comms in batch_results:
                if not generated_comms:
                    logger.debug(
                        f"[INBOX_REPLY_BATCH] No communications generated for {person.name}"
                    )
                    continue

                # Find the original request to get message context
                req = next((r for r in inbox_reply_requests if r["person"].id == person.id), None)
                if not req:
                    logger.warning(
                        f"[INBOX_REPLY_BATCH] Could not find request for {person.name}, skipping"
                    )
                    continue

                message_to_reply = req["message_to_reply"]
                day_index = req["day_index"]

                logger.info(
                    f"[INBOX_REPLY_BATCH] Generated {len(generated_comms)} communications "
                    f"for {person.name} in response to {message_to_reply.sender_name}"
                )

                # Add time and thread_id to communications
                ticks_per_day = max(1, self.hours_per_day * 60)
                current_hour = (current_tick % ticks_per_day) // 60
                current_minute = (current_tick % ticks_per_day) % 60
                time_str = f"{current_hour:02d}:{current_minute:02d}"

                for comm in generated_comms:
                    if 'time' not in comm:
                        comm['time'] = time_str
                    # Add thread_id for email replies
                    if comm.get('type') == 'email' and message_to_reply.thread_id:
                        comm['thread_id'] = message_to_reply.thread_id

                # Process through standard pipeline
                self._process_json_communications(
                    generated_comms,
                    current_tick,
                    person,
                    source="inbox_reply_batch"
                )

                # Dispatch immediately
                se, sc = self._dispatch_scheduled(person, current_tick, people_by_id)
                emails_sent += se
                chats_sent += sc

                # Mark as replied and record stats
                if se > 0 or sc > 0:
                    self.inbox_manager.mark_replied(
                        person_id=person.id,
                        message_id=message_to_reply.message_id,
                        replied_tick=current_tick
                    )

                    # Record for daily limits tracking
                    if se > 0:
                        self._record_daily_message(person.id, day_index, 'email')
                    if sc > 0:
                        self._record_daily_message(person.id, day_index, 'chat')

                    logger.info(
                        f"[INBOX_REPLY_BATCH] {person.name} replied to {message_to_reply.sender_name} "
                        f"(emails={se}, chats={sc}, tick={current_tick})"
                    )
                else:
                    logger.debug(
                        f"[INBOX_REPLY_BATCH] No messages dispatched for {person.name} "
                        f"after generating reply"
                    )

            logger.info(
                f"[INBOX_REPLY_BATCH] Batch processing complete: "
                f"{emails_sent} emails, {chats_sent} chats sent (tick={current_tick})"
            )

        except Exception as e:
            logger.warning(
                f"[INBOX_REPLY_BATCH] Batch processing failed: {e}, "
                f"falling back to synchronous processing",
                exc_info=True
            )

            # Fallback to synchronous processing if batch fails
            for req in inbox_reply_requests:
                try:
                    person = req["person"]
                    message_to_reply = req["message_to_reply"]
                    day_index = req["day_index"]

                    logger.debug(
                        f"[INBOX_REPLY_FALLBACK] Processing request for {person.name} "
                        f"synchronously"
                    )

                    # Generate reply synchronously
                    generated_comms = self.communication_generator.generate_fallback_communications(
                        person=person,
                        current_tick=req["current_tick"],
                        hourly_plan=req["hourly_plan"],
                        daily_plan=req["daily_plan"],
                        project=req["project"],
                        inbox_messages=req["inbox_messages"],
                        collaborators=req["collaborators"]
                    )

                    if not generated_comms:
                        continue

                    # Same processing as batch path
                    ticks_per_day = max(1, self.hours_per_day * 60)
                    current_hour = (current_tick % ticks_per_day) // 60
                    current_minute = (current_tick % ticks_per_day) % 60
                    time_str = f"{current_hour:02d}:{current_minute:02d}"

                    for comm in generated_comms:
                        if 'time' not in comm:
                            comm['time'] = time_str
                        if comm.get('type') == 'email' and message_to_reply.thread_id:
                            comm['thread_id'] = message_to_reply.thread_id

                    self._process_json_communications(
                        generated_comms,
                        current_tick,
                        person,
                        source="inbox_reply_fallback"
                    )

                    se, sc = self._dispatch_scheduled(person, current_tick, people_by_id)
                    emails_sent += se
                    chats_sent += sc

                    if se > 0 or sc > 0:
                        self.inbox_manager.mark_replied(
                            person_id=person.id,
                            message_id=message_to_reply.message_id,
                            replied_tick=current_tick
                        )

                        if se > 0:
                            self._record_daily_message(person.id, day_index, 'email')
                        if sc > 0:
                            self._record_daily_message(person.id, day_index, 'chat')

                        logger.info(
                            f"[INBOX_REPLY_FALLBACK] {person.name} replied to {message_to_reply.sender_name} "
                            f"(emails={se}, chats={sc}, tick={current_tick})"
                        )

                except Exception as e2:
                    logger.warning(
                        f"[INBOX_REPLY_FALLBACK] Failed for {person.name}: {e2}",
                        exc_info=True
                    )

        return (emails_sent, chats_sent)

    def _schedule_from_json(
        self,
        person: PersonRead,
        parsed_json: dict[str, Any],
        current_tick: int
    ) -> None:
        """
        Schedule communications from parsed JSON plan.
        
        Args:
            person: Worker persona
            parsed_json: Structured plan with tasks and communications
            current_tick: Current simulation tick
        """
        if person.id not in self._scheduled_comms:
            self._scheduled_comms[person.id] = {}
        
        communications = parsed_json.get('communications', [])
        if not communications:
            logger.debug(f"[SCHEDULE_JSON] No communications in parsed plan for {person.name}")
            return
        
        scheduled_count = 0
        for comm in communications:
            try:
                # Parse time
                time_str = comm.get('time', '')
                if not time_str or ':' not in time_str:
                    logger.warning(f"[SCHEDULE_JSON] Invalid time format: {time_str}")
                    continue
                
                hour, minute = map(int, time_str.split(':'))
                tick = (hour * 60) + minute
                
                # Build action dict based on communication type
                if comm.get('type') == 'email':
                    action = {
                        'type': 'email',
                        'time': time_str,
                        'to': comm.get('to', ''),
                        'cc': comm.get('cc', []),
                        'bcc': comm.get('bcc', []),
                        'subject': comm.get('subject', ''),
                        'body': comm.get('body', ''),
                        '_source': 'json_plan'
                    }
                elif comm.get('type') == 'email_reply':
                    action = {
                        'type': 'email',
                        'time': time_str,
                        'to': comm.get('to', ''),
                        'cc': comm.get('cc', []),
                        'subject': comm.get('subject', ''),
                        'body': comm.get('body', ''),
                        'thread_id': comm.get('reply_to'),  # Use reply_to as thread_id
                        '_source': 'json_plan'
                    }
                elif comm.get('type') == 'chat':
                    action = {
                        'type': 'chat',
                        'time': time_str,
                        'to': comm.get('to', ''),
                        'message': comm.get('message', ''),
                        '_source': 'json_plan'
                    }
                else:
                    logger.warning(f"[SCHEDULE_JSON] Unknown communication type: {comm.get('type')}")
                    continue
                
                # Schedule the action
                if tick not in self._scheduled_comms[person.id]:
                    self._scheduled_comms[person.id][tick] = []
                self._scheduled_comms[person.id][tick].append(action)
                scheduled_count += 1
                
                logger.debug(
                    f"[SCHEDULE_JSON] {person.name} scheduled {comm.get('type')} at {time_str}"
                )
                
            except Exception as e:
                logger.error(f"[SCHEDULE_JSON] Failed to schedule communication: {comm}, error: {e}")
        
        logger.info(
            f"[SCHEDULE_JSON] Scheduled {scheduled_count}/{len(communications)} communications "
            f"for {person.name} from parsed JSON"
        )

    def _schedule_from_hourly_plan(self, person: PersonRead, plan_text: str, current_tick: int) -> None:
        import re

        # Try JSON parsing first
        json_comms = self._try_parse_json_communications(plan_text)
        if json_comms is not None:
            logger.info(
                f"[JSON_COMMS] Parsed {len(json_comms)} communications from JSON "
                f"for {person.name} (tick={current_tick})"
            )
            self._process_json_communications(json_comms, current_tick, person)
            return

        # Fall back to regex parsing (supports both English and Korean)
        logger.debug(
            f"[REGEX_FALLBACK] No JSON found, using regex parsing "
            f"for {person.name} (tick={current_tick})"
        )

        ticks_per_day = max(1, self.hours_per_day * 60)
        day_index = (current_tick - 1) // ticks_per_day
        tick_of_day = (current_tick - 1) % ticks_per_day
        base_tick = day_index * ticks_per_day + 1
        lines = [ln.strip() for ln in plan_text.splitlines() if ln.strip()]
        if not lines:
            return
        sched = self._scheduled_comms.setdefault(person.id, {})

        # English patterns - allow optional leading whitespace and bullets (-, *, •)
        email_re = re.compile(
            r"^\s*[-*•]?\s*Email\s+at\s+(\d{2}:\d{2})\s+to\s+([^:]+?)"
            r"(?:\s+cc\s+([^:]+?))?"
            r"(?:\s+bcc\s+([^:]+?))?\s*:\s*(.*)$",
            re.I,
        )
        reply_re = re.compile(
            r"^\s*[-*•]?\s*Reply\s+at\s+(\d{2}:\d{2})\s+to\s+\[([^\]]+)\]"
            r"(?:\s+cc\s+([^:]+?))?"
            r"(?:\s+bcc\s+([^:]+?))?\s*:\s*(.*)$",
            re.I,
        )
        chat_re = re.compile(r"^\s*[-*•]?\s*Chat\s+at\s+(\d{2}:\d{2})\s+(?:with|to)\s+([^:]+):\s*(.*)$", re.I)

        # Korean patterns (이메일, 채팅, 답장) - allow optional leading whitespace and bullets (-, *, •)
        email_ko_re = re.compile(
            r"^\s*[-*•]?\s*이메일\s+(\d{2}:\d{2})에\s+([^:]+?)"
            r"(?:\s+참조\s+([^:]+?))?"
            r"(?:\s+숨은참조\s+([^:]+?))?\s*:\s*(.*)$",
            re.I,
        )
        reply_ko_re = re.compile(
            r"^\s*[-*•]?\s*답장\s+(\d{2}:\d{2})에\s+\[([^\]]+)\]"
            r"(?:\s+참조\s+([^:]+?))?"
            r"(?:\s+숨은참조\s+([^:]+?))?\s*:\s*(.*)$",
            re.I,
        )
        chat_ko_re = re.compile(r"^\s*[-*•]?\s*채팅\s+(\d{2}:\d{2})에\s+([^:]+)(?:과|와):\s*(.*)$", re.I)

        # Track parsed communications to detect duplicates
        parsed_comms = []
        
        for ln in lines:
            channel = None
            when = None
            target = None
            payload = ""
            cc_raw = None
            bcc_raw = None
            reply_to_email_id = None

            # Try English email pattern
            m = email_re.match(ln)
            if m:
                channel = 'email'
                when = m.group(1)
                target = (m.group(2) or '').strip()
                cc_raw = (m.group(3) or '').strip()
                bcc_raw = (m.group(4) or '').strip()
                payload = (m.group(5) or '').strip()
            else:
                # Try Korean email pattern
                m = email_ko_re.match(ln)
                if m:
                    channel = 'email'
                    when = m.group(1)
                    target = (m.group(2) or '').strip()
                    cc_raw = (m.group(3) or '').strip()
                    bcc_raw = (m.group(4) or '').strip()
                    payload = (m.group(5) or '').strip()
                else:
                    # Try English reply syntax
                    m = reply_re.match(ln)
                    if m:
                        channel = 'email'
                        when = m.group(1)
                        reply_to_email_id = (m.group(2) or '').strip()
                        cc_raw = (m.group(3) or '').strip()
                        bcc_raw = (m.group(4) or '').strip()
                        payload = (m.group(5) or '').strip()
                    else:
                        # Try Korean reply syntax
                        m = reply_ko_re.match(ln)
                        if m:
                            channel = 'email'
                            when = m.group(1)
                            reply_to_email_id = (m.group(2) or '').strip()
                            cc_raw = (m.group(3) or '').strip()
                            bcc_raw = (m.group(4) or '').strip()
                            payload = (m.group(5) or '').strip()
                        else:
                            # Try English chat pattern
                            m = chat_re.match(ln)
                            if m:
                                channel = 'chat'
                                when, target, payload = m.group(1), m.group(2).strip(), m.group(3).strip()
                            else:
                                # Try Korean chat pattern
                                m = chat_ko_re.match(ln)
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

            # Create a signature for duplicate detection (channel + target + first 50 chars of payload)
            signature = (channel, target.lower() if target else '', payload[:50] if payload else '')
            
            # Check if we've already parsed this communication (handles mixed English/Korean duplicates)
            if signature in parsed_comms:
                logger.debug(f"Skipping duplicate communication: {channel} to {target}")
                continue
            
            parsed_comms.append(signature)

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
        
        # Calculate day index for daily limit tracking
        day_ticks = max(1, self.hours_per_day * 60)
        day_index = (current_tick - 1) // day_ticks

        # Calculate current week for project validation (REQ-2.3.1)
        TICKS_PER_CALENDAR_WEEK = 7 * 24 * 60  # 10,080 ticks
        current_week = ((current_tick - 1) // TICKS_PER_CALENDAR_WEEK) + 1 if current_tick > 0 else 1

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
                    logger.info(
                        f"[INBOX] Generating reply for {person.name} to email-id [{reply_to_email_id}] "
                        f"(thread_id={thread_id}, tick={current_tick})"
                    )
                else:
                    # If email-id not found, log warning and skip
                    logger.warning(f"Reply email-id [{reply_to_email_id}] not found in recent emails for {person.name}")
                    continue

            email_to, chat_to = _match_target(target)
            if channel == 'email' and email_to:
                # Parse "Subject | Body" format from payload
                if ' | ' in payload:
                    parts = payload.split(' | ', 1)  # Split only on first occurrence
                    subject = parts[0].strip()
                    body = parts[1].strip()
                else:
                    # Fallback to generic subject if no pipe separator
                    subject = f"{'업데이트' if self._locale == 'ko' else 'Update'}: {person.name}"
                    body = payload

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

                # Check daily limits before sending
                if not self._check_daily_limits(person.id, day_index, 'email'):
                    continue

                # Validate project assignment for all recipients (REQ-2.3.1)
                # Filter out invalid recipients instead of dropping entire email
                all_recipients = [email_to] + cc_emails + bcc_emails
                valid_recipients = []
                invalid_recipients = []

                for recipient_email in all_recipients:
                    if self._validate_project_communication(
                        sender_email=person.email_address,
                        recipient_email=recipient_email,
                        subject=subject,
                        current_week=current_week
                    ):
                        valid_recipients.append(recipient_email)
                    else:
                        invalid_recipients.append(recipient_email)

                # Skip email only if NO valid recipients remain
                if not valid_recipients:
                    logger.info(
                        f"[PROJECT_VALIDATION] Skipping email from {person.email_address}: "
                        f"No valid recipients (all {len(invalid_recipients)} filtered). "
                        f"Subject: {subject[:80]}"
                    )
                    continue

                # Log filtered recipients for debugging
                if invalid_recipients:
                    logger.debug(
                        f"[PROJECT_VALIDATION] Filtered {len(invalid_recipients)} invalid recipient(s) "
                        f"from {person.email_address}: {', '.join(invalid_recipients)}. "
                        f"Sending to {len(valid_recipients)} valid recipient(s)."
                    )

                # Update recipient lists to only include valid recipients
                # Primary recipient must be valid (it's first in all_recipients)
                if email_to not in valid_recipients:
                    # Primary recipient is invalid - skip this email
                    logger.info(
                        f"[PROJECT_VALIDATION] Skipping email from {person.email_address}: "
                        f"Primary recipient {email_to} not on shared project. "
                        f"Subject: {subject[:80]}"
                    )
                    continue

                # Filter CC/BCC lists to only valid recipients
                cc_emails = [email for email in cc_emails if email in valid_recipients]
                bcc_emails = [email for email in bcc_emails if email in valid_recipients]

                if self._can_send(tick=current_tick, channel='email', sender=person.email_address, recipient_key=recipients_key, subject=subject, body=body):
                    result = self.email_gateway.send_email(
                        sender=person.email_address,
                        to=[email_to],
                        subject=subject,
                        body=body,
                        cc=cc_emails,
                        bcc=bcc_emails,
                        thread_id=thread_id,
                        sent_at_iso=dt_iso,
                        persona_id=person.id
                    )
                    emails += 1
                    
                    # Log the exchange
                    recipient_id = None
                    recipient_person = email_index.get(email_to.lower())
                    if recipient_person:
                        recipient_id = recipient_person.id
                    
                    self._log_exchange(
                        tick=current_tick,
                        sender_id=person.id,
                        recipient_id=recipient_id,
                        channel='email',
                        subject=subject,
                        summary=body[:100] if body else None
                    )
                    
                    # Get source for tracking
                    source = act.get('_source', 'unknown')
                    
                    # Record the sent email for daily limit tracking and volume metrics
                    self._record_daily_message(person.id, day_index, 'email')
                    self._update_volume_metrics(person.id, day_index, 'email', source)
                    
                    # Track quality metrics
                    # Check if message has project context (mentions project name or common project terms)
                    has_project_context = False
                    text_to_check = (subject + " " + body).lower()
                    if any(term in text_to_check for term in ['project', '프로젝트', '[', 'milestone', '마일스톤']):
                        has_project_context = True
                    
                    self.quality_metrics.record_email(
                        subject=subject,
                        thread_id=thread_id,
                        has_project_context=has_project_context,
                        source=source,
                        person_id=person.id
                    )

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
                                
                                # Add to InboxManager for tracking and reply generation
                                from .inbox_manager import InboxMessage
                                message_type, needs_reply = self.inbox_manager.classify_message_type(subject, body, self._locale)
                                inbox_msg = InboxMessage(
                                    message_id=email_id,
                                    sender_id=person.id,
                                    sender_name=person.name,
                                    subject=subject,
                                    body=body,
                                    thread_id=thread_id,
                                    received_tick=current_tick,
                                    message_type=message_type,
                                    needs_reply=needs_reply,
                                    channel='email'
                                )
                                self.inbox_manager.add_message(recipient_person.id, inbox_msg)
                        
                        # Queue an inbound message to the primary recipient to enable a natural reply/ack during their next planning
                        primary_recipient = email_index.get((email_to or '').lower())
                        if primary_recipient is not None:
                            # Derive a short action item from the subject when possible
                            action_item = None
                            if subject:
                                action_item = subject.strip()
                            inbound = _InboundMessage(
                                sender_id=person.id,
                                sender_name=person.name,
                                subject=subject,
                                summary=(body[:140] + '...') if isinstance(body, str) and len(body) > 160 else (body or subject or ''),
                                action_item=action_item,
                                message_type='email',
                                channel='email',
                                tick=current_tick,
                            )
                            self._queue_runtime_message(primary_recipient, inbound)
            elif channel == 'chat' and chat_to:
                # Deterministic guard: only the lexicographically smaller handle sends to avoid mirrored DMs.
                s_handle = person.chat_handle.lower()
                r_handle = chat_to.lower()
                if s_handle > r_handle:
                    continue
                # Check daily limits before sending
                if not self._check_daily_limits(person.id, day_index, 'chat'):
                    continue
                # Project validation: only allow chat if sender and recipient share an ACTIVE project
                TICKS_PER_CALENDAR_WEEK = 7 * 24 * 60  # 10,080 ticks
                current_week = ((current_tick - 1) // TICKS_PER_CALENDAR_WEEK) + 1 if current_tick > 0 else 1
                recipient_person = handle_index.get(chat_to)
                if recipient_person is not None:
                    if not self._validate_project_pair(person.id, recipient_person.id, current_week):
                        logger.info(
                            f"[PROJECT_VALIDATION] Skipping chat from {person.chat_handle} to {chat_to}: "
                            f"no shared active project in week {current_week}"
                        )
                        continue

                if self._can_send(tick=current_tick, channel='chat', sender=person.chat_handle, recipient_key=(chat_to,), subject=None, body=payload):
                    result = self.chat_gateway.send_dm(sender=person.chat_handle, recipient=chat_to, body=payload, sent_at_iso=dt_iso, persona_id=person.id)
                    chats += 1
                    
                    # Log the exchange
                    recipient_id = None
                    recipient_person = handle_index.get(chat_to)
                    if recipient_person:
                        recipient_id = recipient_person.id
                    
                    self._log_exchange(
                        tick=current_tick,
                        sender_id=person.id,
                        recipient_id=recipient_id,
                        channel='chat',
                        subject=None,
                        summary=payload
                    )
                    
                    # Get source for tracking
                    source = act.get('_source', 'unknown')
                    
                    # Record the sent chat for daily limit tracking and volume metrics
                    self._record_daily_message(person.id, day_index, 'chat')
                    self._update_volume_metrics(person.id, day_index, 'chat', source)
                    
                    # Track quality metrics
                    has_project_context = False
                    text_to_check = payload.lower()
                    if any(term in text_to_check for term in ['project', '프로젝트', '[', 'milestone', '마일스톤']):
                        has_project_context = True
                    
                    source = act.get('_source', 'unknown')
                    
                    self.quality_metrics.record_chat(
                        has_project_context=has_project_context,
                        source=source,
                        person_id=person.id
                    )
                    
                    # Queue inbound for recipient to enable conversational acks during their next planning cycle
                    recipient = handle_index.get(r_handle)
                    if recipient is not None:
                        # Add to InboxManager for tracking
                        from .inbox_manager import InboxMessage
                        message_id = result.get('id', f'chat-{current_tick}-{chats}') if isinstance(result, dict) else f'chat-{current_tick}-{chats}'
                        message_type, needs_reply = self.inbox_manager.classify_message_type(None, payload, self._locale)
                        inbox_msg = InboxMessage(
                            message_id=message_id,
                            sender_id=person.id,
                            sender_name=person.name,
                            subject="",
                            body=payload,
                            thread_id=None,
                            received_tick=current_tick,
                            message_type=message_type,
                            needs_reply=needs_reply,
                            channel='chat'
                        )
                        self.inbox_manager.add_message(recipient.id, inbox_msg)
                        
                        inbound = _InboundMessage(
                            sender_id=person.id,
                            sender_name=person.name,
                            subject=f"DM from {person.name}",
                            summary=payload,
                            action_item=None,
                            message_type='dm',
                            channel='chat',
                            tick=current_tick,
                        )
                        self._queue_runtime_message(recipient, inbound)
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
        ticks_per_day = max(1, self.hours_per_day * 60)
        ticks_float = (total_minutes / 1440) * ticks_per_day
        if round_up:
            tick = math.ceil(ticks_float)
        else:
            tick = math.floor(ticks_float)
        return max(0, min(ticks_per_day, tick))

    def _parse_work_hours_to_ticks(self, work_hours: str) -> tuple[int, int]:
        ticks_per_day = max(1, self.hours_per_day * 60)
        if ticks_per_day < 60:
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

    def _is_work_hours_tick(self, tick: int) -> bool:
        """
        Check if a tick falls within work hours (09:00-17:00 on weekdays).

        Uses 480-tick workday system (8-hour days) consistent with all other simulation logic.
        - Work hours: 09:00-17:00 mapped to 480-tick scale (ticks 180-340 of each day)
        - Weekends: Days 5-6 of each week (Saturday-Sunday) are skipped

        Returns False for:
        - Before 09:00 (ticks 0-179 of day)
        - After 17:00 (ticks 341-479 of day)
        - Weekends (days 5-6 of each week)

        This allows the simulation to skip non-work ticks for efficiency while ensuring
        daily planning triggers correctly at tick 180 (09:00) every workday.
        """
        # Use 480-tick workday system (consistent with rest of simulation)
        day_ticks = max(1, self.hours_per_day * 60)  # 480 ticks per 8-hour workday

        # Check if it's a weekend (5-day work week: days 5-6 are Saturday-Sunday)
        day_index = (tick - 1) // day_ticks if tick > 0 else 0
        day_of_week = day_index % 7
        if day_of_week >= 5:
            return False

        # Map 09:00-17:00 to 480-tick scale
        # 09:00 = 540 minutes = (540/1440) * 480 = 180 ticks
        # 17:00 = 1020 minutes = (1020/1440) * 480 = 340 ticks
        WORK_START_TICK = 180  # 09:00 in 480-tick scale
        WORK_END_TICK = 340    # 17:00 in 480-tick scale

        # Check if it's during work hours
        tick_of_day = (tick - 1) % day_ticks if tick > 0 else 0
        return WORK_START_TICK <= tick_of_day <= WORK_END_TICK

    def _is_within_work_hours(self, person: PersonRead, tick: int) -> bool:
        if not self.hours_per_day:
            return True

        # Check if it's a weekend (5-day work week: days 5-6 are Saturday-Sunday)
        day_ticks = max(1, self.hours_per_day * 60)
        day_index = (tick - 1) // day_ticks
        day_of_week = day_index % 7
        # Days 5 and 6 of each week are Saturday and Sunday
        if day_of_week >= 5:
            return False

        window = self._work_hours_ticks.get(person.id)
        if not window:
            return True
        start_tick, end_tick = window
        tick_of_day = (tick - 1) % day_ticks
        if start_tick <= end_tick:
            return start_tick <= tick_of_day < end_tick
        return tick_of_day >= start_tick or tick_of_day < end_tick

    def _format_sim_time(self, tick: int) -> str:
        if tick <= 0:
            return "Day 0 09:00"

        # Use workday model (hours_per_day * 60 ticks per day, starting at 09:00)
        ticks_per_day = max(1, self.hours_per_day * 60)
        day_index = ((tick - 1) // ticks_per_day) + 1
        tick_of_day = (tick - 1) % ticks_per_day

        # Map tick-of-day to work time (09:00-17:00 for 8-hour days)
        # Each tick = 1 minute of work time, starting at 09:00
        base_hour = 9  # Work starts at 09:00
        total_minutes = tick_of_day
        hour = base_hour + (total_minutes // 60)
        minute = total_minutes % 60
        return f"Day {day_index} {hour:02d}:{minute:02d}"

    def _sim_datetime_for_tick(self, tick: int) -> datetime | None:
        base = self._sim_base_dt
        if not base:
            return None

        # Use workday model (hours_per_day * 60 ticks per day)
        ticks_per_day = max(1, self.hours_per_day * 60)
        day_index = (tick - 1) // ticks_per_day
        tick_of_day = (tick - 1) % ticks_per_day

        # Each tick = 1 minute of work time, starting at 09:00
        # Add 9 hours offset to start at 09:00 instead of 00:00
        total_minutes = tick_of_day + (9 * 60)  # 9-hour offset

        return base + timedelta(days=day_index, minutes=total_minutes)

    def _compute_comm_stagger(self, person_id: int, day_index: int) -> int:
        """Compute a deterministic minute-level stagger for scheduled communications.

        The offset is derived from the simulation seed, person ID, and day index
        to ensure reproducibility while avoiding synchronized sends. Returns a
        small offset in [-max, +max] minutes, where max is configured by
        VDOS_COMM_STAGGER_MAX_MINUTES (default 7).
        """
        max_min = max(0, int(self._comm_stagger_max_minutes))
        if max_min == 0:
            return 0
        base_seed = self._current_seed if self._current_seed is not None else 0
        local_seed = (base_seed * 1315423911) ^ (person_id * 2654435761) ^ (day_index * 97531)
        rng = random.Random(local_seed & 0xFFFFFFFF)
        offset = rng.randint(-max_min, max_min)
        if offset == 0 and max_min > 0:
            # Nudge away from 0 to ensure actual staggering
            offset = 1 if (person_id + day_index) % 2 == 0 else -1
        return offset


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

    def get_active_projects_with_assignments(self, current_week: int | None = None) -> list[dict[str, Any]]:
        """Get all projects active at the given week with their team assignments."""
        if current_week is None:
            # Calculate current week from simulation state
            status = self._fetch_state()
            day_ticks = max(1, self.hours_per_day * 60)
            current_day = (status.current_tick - 1) // day_ticks if status.current_tick > 0 else 0
            current_week = (current_day // 5) + 1  # 1-indexed weeks, assuming 5-day work weeks

        with get_connection() as conn:
            # Get all projects active in the current week
            project_rows = conn.execute(
                """
                SELECT * FROM project_plans
                WHERE start_week <= ? AND (start_week + duration_weeks - 1) >= ?
                ORDER BY start_week ASC
                """,
                (current_week, current_week),
            ).fetchall()

            result = []
            for proj_row in project_rows:
                project = self._row_to_project_plan(proj_row)

                # Get assigned people for this project
                assignment_rows = conn.execute(
                    """
                    SELECT p.id, p.name, p.role, p.team_name
                    FROM people p
                    INNER JOIN project_assignments pa ON p.id = pa.person_id
                    WHERE pa.project_id = ?
                    ORDER BY p.team_name, p.name
                    """,
                    (project['id'],),
                ).fetchall()

                team_members = [
                    {
                        'id': row['id'],
                        'name': row['name'],
                        'role': row['role'],
                        'team_name': row['team_name'],
                    }
                    for row in assignment_rows
                ]

                # If no specific assignments, project is for everyone
                if not team_members:
                    all_people_rows = conn.execute(
                        "SELECT id, name, role, team_name FROM people ORDER BY team_name, name"
                    ).fetchall()
                    team_members = [
                        {
                            'id': row['id'],
                            'name': row['name'],
                            'role': row['role'],
                            'team_name': row['team_name'],
                        }
                        for row in all_people_rows
                    ]

                result.append({
                    'project': project,
                    'team_members': team_members,
                })

            return result

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

    # ------------------------------------------------------------------
    # Projects listing (for UI hydration)
    # ------------------------------------------------------------------
    def list_all_projects_with_assignees(self) -> list[dict[str, Any]]:
        """Return all projects with their assigned person ids.

        Shape:
            [
              {
                'project': { ...project_plan_fields },
                'assigned_person_ids': [int, ...]
              },
              ...
            ]
        """
        with get_connection() as conn:
            proj_rows = conn.execute(
                "SELECT * FROM project_plans ORDER BY start_week ASC, id ASC"
            ).fetchall()
            results: list[dict[str, Any]] = []
            for row in proj_rows:
                proj = self._row_to_project_plan(row)
                assigned = [
                    r["person_id"]
                    for r in conn.execute(
                        "SELECT person_id FROM project_assignments WHERE project_id = ? ORDER BY person_id",
                        (proj["id"],),
                    ).fetchall()
                ]
                results.append({
                    "project": proj,
                    "assigned_person_ids": assigned,
                })
            return results

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
            # PERFORMANCE: Parallelize initial planning to avoid 50-75s startup time
            # Generate daily and hourly plans in parallel for all team members
            def generate_initial_plans_for_person(person):
                daily_result = self._generate_daily_plan(person, plan_record, day_index=0)
                self._generate_hourly_plan(
                    person,
                    plan_record,
                    daily_result.content,
                    tick=0,
                    reason="initialisation",
                )
                return person

            # Optional: disable tick-0 initial planning for strict off-hours starts
            disable_initial = (os.getenv("VDOS_DISABLE_INITIAL_PLANNING", "0").strip().lower() in {"1", "true", "yes", "on"})
            if not disable_initial:
                with ThreadPoolExecutor(max_workers=min(4, len(team))) as executor:
                    futures = [executor.submit(generate_initial_plans_for_person, person) for person in team]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f"Failed to generate initial plans: {e}", exc_info=True)

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

    def _validate_project_pair(self, sender_id: int, recipient_id: int, current_week: int) -> bool:
        """Return True if sender and recipient share at least one active project in the given week.

        Considers both explicitly assigned projects and unassigned active projects (everyone).
        """
        try:
            s_projects = self._get_all_active_projects_for_person(sender_id, current_week)
            r_projects = self._get_all_active_projects_for_person(recipient_id, current_week)
            if not s_projects or not r_projects:
                return False
            def _pid(p):
                return p.get("id") if isinstance(p, dict) else getattr(p, "id", None)
            s_ids = { _pid(p) for p in s_projects if _pid(p) is not None }
            r_ids = { _pid(p) for p in r_projects if _pid(p) is not None }
            return bool(s_ids & r_ids)
        except Exception:
            return False

    def _get_project_collaborators(
        self,
        person_id: int,
        current_week: int,
        all_people: dict[int, PersonRead],
        project_id: int | None = None
    ) -> list[PersonRead]:
        """
        Get collaborators for a person based on shared project assignments.

        Returns personas who are assigned to at least one of the same projects
        as the given person. If a person has no project assignments (works on
        unassigned projects), returns all other personas.

        Args:
            person_id: ID of the person to get collaborators for
            current_week: Current simulation week
            all_people: Dictionary of all personas by ID
            project_id: Optional specific project ID to filter by (REQ-2.2.1)
                       If provided, only returns collaborators on THIS specific project.
                       If None, returns collaborators on ANY shared project (old behavior).

        Returns:
            List of PersonRead objects representing project collaborators
        """
        with get_connection() as conn:
            # If project_id is specified, only get collaborators for that specific project (REQ-2.2.1)
            if project_id is not None:
                # Verify the person is assigned to this project
                person_on_project = conn.execute(
                    """
                    SELECT 1 FROM project_assignments pa
                    INNER JOIN project_plans pp ON pa.project_id = pp.id
                    WHERE pa.person_id = ? AND pa.project_id = ?
                    AND pp.start_week <= ? AND (pp.start_week + pp.duration_weeks - 1) >= ?
                    """,
                    (person_id, project_id, current_week, current_week)
                ).fetchone()

                if not person_on_project:
                    # Person not on this project, return empty list
                    return []

                # Get all people assigned to THIS specific project
                collaborator_rows = conn.execute(
                    """
                    SELECT DISTINCT pa.person_id
                    FROM project_assignments pa
                    INNER JOIN project_plans pp ON pa.project_id = pp.id
                    WHERE pa.project_id = ?
                    AND pa.person_id != ?
                    AND pp.start_week <= ?
                    AND (pp.start_week + pp.duration_weeks - 1) >= ?
                    """,
                    (project_id, person_id, current_week, current_week)
                ).fetchall()

                collaborator_ids = {row['person_id'] for row in collaborator_rows}
                return [all_people[pid] for pid in collaborator_ids if pid in all_people]

            # Original behavior: Get projects assigned to this person
            person_projects = conn.execute(
                """
                SELECT DISTINCT pa.project_id
                FROM project_assignments pa
                INNER JOIN project_plans pp ON pa.project_id = pp.id
                WHERE pa.person_id = ?
                AND pp.start_week <= ?
                AND (pp.start_week + pp.duration_weeks - 1) >= ?
                """,
                (person_id, current_week, current_week)
            ).fetchall()

            person_project_ids = {row['project_id'] for row in person_projects}

            # If person has no specific project assignments, they work on unassigned projects
            # In this case, return all other personas (existing behavior)
            if not person_project_ids:
                return [p for p in all_people.values() if p.id != person_id]

            # Get all people assigned to the same projects
            collaborator_rows = conn.execute(
                """
                SELECT DISTINCT pa.person_id
                FROM project_assignments pa
                INNER JOIN project_plans pp ON pa.project_id = pp.id
                WHERE pa.project_id IN ({})
                AND pa.person_id != ?
                AND pp.start_week <= ?
                AND (pp.start_week + pp.duration_weeks - 1) >= ?
                """.format(','.join('?' * len(person_project_ids))),
                (*person_project_ids, person_id, current_week, current_week)
            ).fetchall()

            collaborator_ids = {row['person_id'] for row in collaborator_rows}

            # Also include people with no assignments (they work on unassigned projects)
            people_with_no_assignments = conn.execute(
                """
                SELECT DISTINCT p.id
                FROM people p
                WHERE p.id NOT IN (SELECT DISTINCT person_id FROM project_assignments)
                AND p.id != ?
                """,
                (person_id,)
            ).fetchall()

            for row in people_with_no_assignments:
                collaborator_ids.add(row['id'])

            # Return PersonRead objects for collaborators
            return [all_people[pid] for pid in collaborator_ids if pid in all_people]

    def _validate_project_communication(
        self,
        sender_email: str,
        recipient_email: str,
        subject: str | None,
        current_week: int
    ) -> bool:
        """
        Validate that sender and recipient are both assigned to the project being discussed (REQ-2.3.1).

        Args:
            sender_email: Email address of sender
            recipient_email: Email address of recipient
            subject: Email subject line (may contain project identifier like "[Project OMEGA]")
            current_week: Current simulation week

        Returns:
            True if validation passes (both on same project or no project identifier found),
            False if validation fails (project identified but recipient not assigned)
        """
        if not subject:
            # No subject, allow (backward compatibility for chats without project context)
            return True

        # Extract project name from subject
        import re
        # Try English format: [Project NAME]
        match = re.search(r'\[Project ([A-Z]+)\]', subject)
        if not match:
            # Try Korean format: [프로젝트 NAME]
            match = re.search(r'\[프로젝트 ([A-Z]+)\]', subject)
        if not match:
            # Try without brackets
            match = re.search(r'(?:Project|프로젝트)\s+([A-Z]+)', subject)

        if not match:
            # No project identifier found, allow (REQ-2.4.1 - backward compatibility)
            return True

        project_name = match.group(1)

        # Look up project ID by name
        with get_connection() as conn:
            project_row = conn.execute(
                """
                SELECT id FROM project_plans
                WHERE project_name LIKE ?
                AND start_week <= ?
                AND (start_week + duration_weeks - 1) >= ?
                """,
                (f"%{project_name}%", current_week, current_week)
            ).fetchone()

            if not project_row:
                # Project not found or not active, allow (might be future/past project reference)
                logger.debug(f"Project '{project_name}' not found or not active in week {current_week}")
                return True

            project_id = project_row['id']

            # Get sender's persona
            sender_row = conn.execute(
                "SELECT id FROM people WHERE email_address = ?",
                (sender_email,)
            ).fetchone()

            # Get recipient's persona
            recipient_row = conn.execute(
                "SELECT id FROM people WHERE email_address = ?",
                (recipient_email,)
            ).fetchone()

            if not sender_row or not recipient_row:
                # Sender or recipient not in persona database, allow (might be external)
                return True

            sender_id = sender_row['id']
            recipient_id = recipient_row['id']

            # Check if both are assigned to this project
            sender_on_project = conn.execute(
                "SELECT 1 FROM project_assignments WHERE person_id = ? AND project_id = ?",
                (sender_id, project_id)
            ).fetchone()

            recipient_on_project = conn.execute(
                "SELECT 1 FROM project_assignments WHERE person_id = ? AND project_id = ?",
                (recipient_id, project_id)
            ).fetchone()

            # Validation fails if recipient is NOT on the project (REQ-2.3.1)
            if not recipient_on_project:
                logger.warning(
                    f"[PROJECT_VALIDATION] Rejecting communication about '{project_name}': "
                    f"recipient {recipient_email} (ID {recipient_id}) not assigned to project {project_id}. "
                    f"Subject: {subject[:80]}"
                )
                return False

            # Validation passes
            return True

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
        self, person: PersonRead, project_plan: dict[str, Any], day_index: int, all_active_projects: list[dict[str, Any]] | None = None
    ) -> PlanResult:
        # Get all active people for team roster
        team = self._get_active_people()

        try:
            result = self._call_planner(
                'generate_daily_plan',
                worker=person,
                project_plan=project_plan,  # Pass full dict to include project_name
                day_index=day_index,
                duration_weeks=self.project_duration_weeks,
                team=team,
                model_hint=self._planner_model_hint,
                all_active_projects=all_active_projects,  # Pass all active projects for multi-project support
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
        # Calculate current week for project-specific team filtering (REQ-2.2.1)
        # Use calendar weeks to match project configuration (REQ-2.1.2)
        TICKS_PER_CALENDAR_WEEK = 7 * 24 * 60  # 10,080 ticks
        current_week = ((tick - 1) // TICKS_PER_CALENDAR_WEEK) + 1 if tick > 0 else 1

        # Get project-specific team roster (REQ-2.2.1)
        # Only include teammates who are on the PRIMARY project being planned
        project_id = project_plan.get('id') if isinstance(project_plan, dict) else None
        all_people = {p.id: p for p in self._get_active_people()}

        if project_id is not None:
            # Filter to only collaborators on this specific project
            team = self._get_project_collaborators(
                person_id=person.id,
                current_week=current_week,
                all_people=all_people,
                project_id=project_id
            )
        else:
            # Fall back to all active people if no project ID (backward compatibility)
            team = list(all_people.values())
            if person.id in all_people:
                team = [p for p in team if p.id != person.id]

        # Get recent emails for this person (for threading context)
        recent_emails = list(self._recent_emails.get(person.id, []))

        try:
            result = self._call_planner(
                'generate_hourly_plan',
                worker=person,
                project_plan=project_plan,  # Pass full dict to include project_name
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

        # NEW: Parse natural language plan into structured JSON and schedule communications
        if self.plan_parser is not None:
            try:
                # Extract project name for parser context
                project_name = None
                if isinstance(project_plan, dict):
                    project_name = project_plan.get('project_name')
                
                # Build name-to-handle mapping for Korean name resolution
                name_to_handle = {p.name: p.chat_handle for p in team if p.id != person.id}
                
                # Parse the plan
                parsed_json = self.plan_parser.parse_plan(
                    plan_text=content_result.content,
                    worker_name=person.name,
                    work_hours=getattr(person, 'work_hours', '09:00-18:00'),
                    team_emails=[p.email_address for p in team if p.id != person.id],
                    team_handles=[p.chat_handle for p in team if p.id != person.id],
                    project_name=project_name,
                    name_to_handle=name_to_handle
                )
                
                # Schedule communications from parsed JSON
                self._schedule_from_json(person, parsed_json, tick)
                
                logger.info(
                    f"[PLAN_PARSER] Successfully parsed and scheduled plan for {person.name} "
                    f"({len(parsed_json.get('communications', []))} communications)"
                )
                
            except ParsingError as e:
                logger.warning(
                    f"[PLAN_PARSER] Failed to parse plan for {person.name}: {e}, "
                    f"falling back to regex parser"
                )
                # Fall back to regex parsing
                self._schedule_from_hourly_plan(person, content_result.content, tick)
            except Exception as e:
                logger.error(
                    f"[PLAN_PARSER] Unexpected error parsing plan for {person.name}: {e}, "
                    f"falling back to regex parser"
                )
                # Fall back to regex parsing
                self._schedule_from_hourly_plan(person, content_result.content, tick)
        else:
            # Plan parser disabled, use regex parsing
            self._schedule_from_hourly_plan(person, content_result.content, tick)

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
        self, person: PersonRead, day_index: int, project_plan: dict[str, Any], all_active_projects: list[dict[str, Any]] | None = None
    ) -> str:
        existing = self._fetch_worker_plan(
            person.id, "daily", tick=day_index, exact_tick=True
        )
        if existing:
            return existing["content"]
        result = self._generate_daily_plan(person, project_plan, day_index, all_active_projects)
        return result.content

    def _summarise_plan(self, plan_text: str, max_lines: int = 4) -> str:
        lines = [line.strip() for line in plan_text.splitlines() if line.strip()]
        if not lines:
            # Return empty summary so callers can choose a sensible fallback
            return ""
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

        # Use hourly summaries (hour indices are 0..hours_per_day-1 per day)
        start_hour = day_index * self.hours_per_day
        end_hour = (day_index + 1) * self.hours_per_day
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

    # ------------------------------------------------------------------
    # Project management (delete)
    # ------------------------------------------------------------------
    def delete_project(self, project_id: int) -> dict[str, Any]:
        """Delete a project and its associations (assignments),
        and remove any events that reference the project by id or name.

        Returns a small summary of what was deleted.
        """
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_plans WHERE id = ?",
                (project_id,),
            ).fetchone()
            if not row:
                raise RuntimeError(f"Project id {project_id} not found")

            project = self._row_to_project_plan(row)

            # Delete the project (assignments are removed via ON DELETE CASCADE)
            conn.execute("DELETE FROM project_plans WHERE id = ?", (project_id,))

            # Best-effort: cleanup events that referenced the project
            try:
                conn.execute(
                    "DELETE FROM events WHERE project_id = ? OR project_id = ?",
                    (str(project_id), project["project_name"]),
                )
            except Exception:
                pass

        # Invalidate cache since the latest project might have been removed
        self._project_plan_cache = None

        return {
            "deleted_id": project_id,
            "project_name": project["project_name"],
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
        self._current_seed = seed
        self._random.seed(seed)
        self._reset_runtime_state()
        
        # Initialize CommunicationGenerator with seed, planner, and locale
        self.communication_generator = CommunicationGenerator(
            planner=self.planner,
            locale=self._locale,
            random_seed=seed
        )
        logger.info(f"Initialized CommunicationGenerator with seed={seed}, locale={self._locale}")
        
        # Initialize PlanParser for converting natural language plans to JSON
        enable_plan_parser = os.getenv("VDOS_ENABLE_PLAN_PARSER", "true").strip().lower() in {"1", "true", "yes", "on"}
        if enable_plan_parser:
            try:
                self.plan_parser = PlanParser()
                logger.info("Initialized PlanParser for structured plan extraction")
            except Exception as e:
                logger.warning(f"Failed to initialize PlanParser: {e}, will use regex fallback")
                self.plan_parser = None
        else:
            self.plan_parser = None
            logger.info("PlanParser disabled via VDOS_ENABLE_PLAN_PARSER")
        
        all_people = self.list_people()
        if not all_people:
            raise RuntimeError("Cannot start simulation without any personas")
        active_people = self._resolve_active_people(request, all_people)
        self._active_person_ids = [person.id for person in active_people]
        if request is not None:
            # Validate that either single-project or multi-project fields are provided
            if request.projects:
                # Multi-project mode
                if request.total_duration_weeks:
                    self.project_duration_weeks = request.total_duration_weeks
                else:
                    # Calculate total duration from projects
                    max_end_week = max(p.start_week + p.duration_weeks - 1 for p in request.projects)
                    self.project_duration_weeks = max_end_week
            else:
                # Single-project mode - require project_name and project_summary
                if not request.project_name or not request.project_summary:
                    raise RuntimeError("Either 'projects' or both 'project_name' and 'project_summary' must be provided")
                self.project_duration_weeks = request.duration_weeks
            self._planner_model_hint = request.model_hint
            self._initialise_project_plan(request, active_people)
        self._set_running(True)
        # Anchor the simulation base datetime to local midnight of the dominant timezone
        # among active people, then convert to UTC. This ensures that a tick's wall-clock
        # minute-of-day corresponds to the workers' local day boundaries.
        try:
            now_utc = datetime.now(timezone.utc)
            # Choose the most common timezone among active people; default to 'UTC'.
            tz_counts: dict[str, int] = {}
            for p in active_people:
                tz = getattr(p, 'timezone', None) or 'UTC'
                tz_counts[tz] = tz_counts.get(tz, 0) + 1
            dominant_tz = max(tz_counts, key=tz_counts.get) if tz_counts else 'UTC'

            if ZoneInfo is not None:
                local = now_utc.astimezone(ZoneInfo(dominant_tz))
                local_midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
                self._sim_base_dt = local_midnight.astimezone(timezone.utc)
            else:
                # Fallback: use UTC midnight
                self._sim_base_dt = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            # Last resort: leave unset (engine will omit sent_at and servers will default)
            self._sim_base_dt = None
        self._sync_worker_runtimes(active_people)
        # Schedule a kickoff chat/email at the first working minute for each worker
        try:
            ticks_per_day = max(1, self.hours_per_day * 60)
            # Calendar week size for project timelines
            TICKS_PER_CALENDAR_WEEK = 7 * 24 * 60  # 10,080 ticks
            # Active people map for collaborator lookup
            people_by_id = {p.id: p for p in active_people}
            for person in active_people:
                start_end = self._work_hours_ticks.get(person.id, (0, ticks_per_day))
                start_tick_of_day = start_end[0]
                base_tick = 1  # day 1 start
                kickoff_tick = base_tick + max(0, start_tick_of_day) + 5  # +5 minutes (minute ticks)

                # Only schedule kickoff if the person has at least one ACTIVE project in week 1
                current_week = 1
                active_projects = self._get_all_active_projects_for_person(person.id, current_week)
                if not active_projects:
                    continue

                # Choose collaborators strictly from the same active project
                project_for_collab = active_projects[0]
                collaborators = self._get_project_collaborators(
                    person_id=person.id,
                    current_week=current_week,
                    all_people=people_by_id,
                    project_id=project_for_collab["id"] if isinstance(project_for_collab, dict) else getattr(project_for_collab, "id", None),
                )
                target = collaborators[0] if collaborators else None
                if not target:
                    continue

                if self._locale == 'ko':
                    self._schedule_direct_comm(person.id, kickoff_tick, "chat", target.chat_handle, "좋은 아침입니다! 오늘 우선순위 빠르게 맞춰볼까요?")
                    self._schedule_direct_comm(person.id, kickoff_tick + 30, "email", target.email_address, "킥오프 | 오늘 진행할 작업 정리했습니다 — 문의사항 있으면 알려주세요.")
                else:
                    self._schedule_direct_comm(person.id, kickoff_tick, "chat", target.chat_handle, f"Morning! Quick sync on priorities?")
                    self._schedule_direct_comm(person.id, kickoff_tick + 30, "email", target.email_address, f"Quick kickoff | Lining up tasks for today — ping me with blockers.")
        except Exception:
            # Kickoff scheduling is best-effort; if collaborator or project lookup fails, skip.
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

    def set_auto_pause(self, enabled: bool) -> dict[str, Any]:
        """Toggle auto-pause setting at runtime and return comprehensive status information.
        
        Args:
            enabled: Whether to enable auto-pause functionality
            
        Returns:
            Dictionary containing updated auto-pause status and configuration
        """
        try:
            # Update session-level configuration
            self._auto_pause_enabled = enabled
            
            # Log the configuration change
            logger.info(f"Auto-pause setting updated to: {'enabled' if enabled else 'disabled'}")
            
            # Return comprehensive status information
            return self.get_auto_pause_status()
            
        except Exception as exc:
            logger.error(f"Failed to update auto-pause setting: {exc}")
            return {
                "auto_pause_enabled": getattr(self, '_auto_pause_enabled', None),
                "error": str(exc),
                "reason": f"Failed to update auto-pause setting: {exc}"
            }

    def get_auto_pause_status(self) -> dict[str, Any]:
        """Get information about auto-pause status and reasons with enhanced project lifecycle calculations."""
        # Check session-level setting first, then fall back to environment variable
        if hasattr(self, '_auto_pause_enabled'):
            auto_pause_enabled = self._auto_pause_enabled
        else:
            auto_pause_enabled = os.getenv("VDOS_AUTO_PAUSE_ON_PROJECT_END", "true").lower() == "true"
        
        if not auto_pause_enabled:
            return {
                "auto_pause_enabled": False,
                "should_pause": False,
                "active_projects_count": 0,
                "future_projects_count": 0,
                "current_week": 0,
                "reason": "Auto-pause on project end is disabled"
            }
        
        try:
            # Enhanced current week calculation with validation
            status = self._fetch_state()
            if status.current_tick <= 0:
                current_day = 0
                current_week = 1
            else:
                # Use minute ticks per day for calculations
                day_ticks = max(1, self.hours_per_day * 60)
                current_day = (status.current_tick - 1) // day_ticks
                current_week = max(1, (current_day // 5) + 1)
            
            # Get active projects using verified calculation (start_week <= current_week <= end_week)
            active_projects = self.get_active_projects_with_assignments(current_week)
            
            # Check for future projects with enhanced validation
            with get_connection() as conn:
                future_projects = conn.execute(
                    "SELECT COUNT(*) as count FROM project_plans WHERE start_week > ?",
                    (current_week,)
                ).fetchone()
            
            future_count = future_projects["count"] if future_projects else 0
            should_pause = len(active_projects) == 0 and future_count == 0
            
            # Enhanced reason with comprehensive project information
            if should_pause:
                # Get completed projects for detailed logging
                with get_connection() as conn:
                    completed_projects = conn.execute(
                        """SELECT project_name, start_week, duration_weeks,
                           (start_week + duration_weeks - 1) as end_week
                           FROM project_plans 
                           WHERE (start_week + duration_weeks - 1) < ?
                           ORDER BY end_week DESC""",
                        (current_week,)
                    ).fetchall()
                
                completed_count = len(completed_projects)
                reason = f"All {completed_count} project(s) completed, no future projects (week {current_week}, tick {status.current_tick})"
                
                # Log the auto-pause condition for debugging
                logger.debug(f"Auto-pause condition met: {reason}")
                
            elif len(active_projects) > 0:
                active_names = [p.get("project_name", "Unknown") for p in active_projects[:3]]
                reason = f"{len(active_projects)} active project(s) in week {current_week}: {', '.join(active_names)}{'...' if len(active_projects) > 3 else ''}"
                
            else:
                # Get next future project details
                with get_connection() as conn:
                    next_future = conn.execute(
                        """SELECT project_name, start_week FROM project_plans 
                           WHERE start_week > ? ORDER BY start_week ASC LIMIT 1""",
                        (current_week,)
                    ).fetchone()
                
                next_project_info = f" (next: '{next_future['project_name']}' in week {next_future['start_week']})" if next_future else ""
                reason = f"No active projects in week {current_week}, but {future_count} future project(s) exist{next_project_info}"
            
            return {
                "auto_pause_enabled": True,
                "should_pause": should_pause,
                "active_projects_count": len(active_projects),
                "future_projects_count": future_count,
                "current_week": current_week,
                "current_tick": status.current_tick,
                "current_day": current_day,
                "reason": reason
            }
            
        except Exception as exc:
            logger.error(f"Failed to check project status for auto-pause: {exc}")
            return {
                "auto_pause_enabled": True,
                "should_pause": False,
                "active_projects_count": 0,
                "future_projects_count": 0,
                "current_week": 0,
                "current_tick": 0,
                "current_day": 0,
                "error": str(exc),
                "reason": f"Failed to check project status: {exc}"
            }

    def set_tick_interval(self, interval_seconds: float) -> dict[str, Any]:
        """Update the auto-tick interval (in seconds). Use 0 for maximum speed."""
        if interval_seconds < 0:
            raise ValueError("Tick interval cannot be negative")
        if interval_seconds > 60:
            raise ValueError("Tick interval cannot exceed 60 seconds")
        self._tick_interval_seconds = interval_seconds
        if interval_seconds == 0:
            logger.info("Tick interval set to 0s (maximum speed - no delay between ticks)")
        else:
            logger.info(f"Tick interval updated to {interval_seconds}s")
        return {
            "tick_interval_seconds": self._tick_interval_seconds,
            "message": f"Tick interval set to {interval_seconds}s" + (" (max speed)" if interval_seconds == 0 else "")
        }

    def get_tick_interval(self) -> float:
        """Get the current auto-tick interval (in seconds)."""
        return self._tick_interval_seconds

    def _run_auto_tick_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(self._tick_interval_seconds):
            state = self._fetch_state()
            if not state.is_running or not state.auto_tick:
                break
            
            # Check if auto-pause on project completion is enabled
            auto_pause_on_completion = getattr(self, '_auto_pause_enabled', True)
            if auto_pause_on_completion:
                try:
                    # Enhanced project lifecycle calculations with edge case handling
                    if state.current_tick <= 0:
                        current_day = 0
                        current_week = 1
                    else:
                        # Use minute ticks per day for calculations
                        day_ticks = max(1, self.hours_per_day * 60)
                        current_day = (state.current_tick - 1) // day_ticks
                        current_week = max(1, (current_day // 5) + 1)
                    
                    # Get active projects for current week using enhanced calculation
                    active_projects = self.get_active_projects_with_assignments(current_week)
                    
                    if not active_projects:
                        # Enhanced multi-project scenario handling
                        with get_connection() as conn:
                            # Check for future projects that haven't started yet
                            future_projects = conn.execute(
                                "SELECT COUNT(*) as count FROM project_plans WHERE start_week > ?",
                                (current_week,)
                            ).fetchone()
                            
                            # Also get details of future projects for better logging
                            future_project_details = conn.execute(
                                """SELECT project_name, start_week, duration_weeks, 
                                   (start_week + duration_weeks - 1) as end_week 
                                   FROM project_plans WHERE start_week > ? 
                                   ORDER BY start_week ASC""",
                                (current_week,)
                            ).fetchall()
                        
                        future_count = future_projects["count"] if future_projects else 0
                        
                        if future_count == 0:
                            # Comprehensive logging for auto-pause trigger
                            with get_connection() as conn:
                                # Get all completed projects for logging
                                completed_projects = conn.execute(
                                    """SELECT project_name, start_week, duration_weeks,
                                       (start_week + duration_weeks - 1) as end_week
                                       FROM project_plans 
                                       WHERE (start_week + duration_weeks - 1) < ?
                                       ORDER BY end_week DESC""",
                                    (current_week,)
                                ).fetchall()
                                
                                total_projects = conn.execute(
                                    "SELECT COUNT(*) as count FROM project_plans"
                                ).fetchone()["count"]
                            
                            completed_count = len(completed_projects)
                            completed_names = [p["project_name"] for p in completed_projects[:5]]  # Show first 5
                            
                            logger.info(
                                f"🛑 AUTO-PAUSE TRIGGERED: All projects completed! "
                                f"Week {current_week}, Tick {state.current_tick}, Day {current_day}. "
                                f"Completed {completed_count}/{total_projects} projects: "
                                f"{', '.join(completed_names)}{'...' if completed_count > 5 else ''}. "
                                f"No active or future projects remaining. Pausing auto-tick."
                            )
                            
                            # Also log to console for frontend debugging
                            print(f"[AUTO-PAUSE] Week {current_week}: All {completed_count} projects completed, pausing simulation")
                            
                            self._set_auto_tick(False)
                            break
                        else:
                            # Enhanced logging for multi-project scenarios
                            future_project_names = [p["project_name"] for p in future_project_details[:3]]  # Show first 3
                            next_start_week = min(p["start_week"] for p in future_project_details)
                            logger.debug(
                                f"Auto-pause check: No active projects in week {current_week}, "
                                f"but {future_count} future project(s) exist (next starts week {next_start_week}): "
                                f"{', '.join(future_project_names)}{'...' if len(future_project_details) > 3 else ''}. "
                                f"Continuing auto-tick."
                            )
                    else:
                        # Enhanced logging for active projects
                        active_project_names = [p.get("project_name", "Unknown") for p in active_projects[:3]]  # Show first 3
                        logger.debug(
                            f"Auto-pause check: {len(active_projects)} active project(s) in week {current_week}: "
                            f"{', '.join(active_project_names)}{'...' if len(active_projects) > 3 else ''}. "
                            f"Continuing auto-tick."
                        )
                        
                except Exception as exc:
                    logger.error(
                        f"Auto-pause check failed at tick {state.current_tick}: {exc}. "
                        f"Continuing auto-tick to prevent simulation halt."
                    )
            
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
            day_ticks = max(1, self.hours_per_day * 60)
            current_day = (status.current_tick - 1) // day_ticks if status.current_tick > 0 else 0
            current_week = (current_day // 5) + 1  # 1-indexed weeks, assuming 5-day work weeks

            emails_sent = 0
            chats_sent = 0

            for _ in range(ticks):
                status.current_tick += 1

                # WORK HOURS FILTER: Skip all processing for non-work hours ticks
                # This dramatically improves performance by skipping 16 hours/day + weekends
                # Work hours: Mon-Fri 09:00-17:00 (ticks 540-1020 of each calendar day)
                if not self._is_work_hours_tick(status.current_tick):
                    self._update_tick(status.current_tick, "off_hours_skip")
                    continue

                self._reset_tick_sends()
                self._update_tick(status.current_tick, reason)
                self._refresh_status_overrides(status.current_tick)
                event_adjustments, _ = self._maybe_generate_events(people, status.current_tick, project_plan)
                day_index = (status.current_tick - 1) // day_ticks
                tick_of_day = (status.current_tick - 1) % day_ticks if self.hours_per_day > 0 else 0
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
                    # Respect offline-style overrides: do not plan while unavailable
                    offline_statuses = {"SickLeave", "Offline", "Absent", "Vacation", "Leave", "Away", "휴가", "병가", "자리비움"}
                    if override and (override[0] in offline_statuses):
                        # Drain incoming into queue as reminders and skip planning
                        if incoming:
                            for message in incoming:
                                self._get_worker_runtime(person).queue(message)
                        logger.info("Skipping planning for %s at tick %s due to status override: %s", person.name, status.current_tick, override[0])
                        continue
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
                    # Plan at the start of each worker's day (their work window), not only at absolute day start
                    start_end = self._work_hours_ticks.get(person.id, (0, day_ticks))
                    work_start_tick = start_end[0] if self.hours_per_day > 0 else 0
                    should_plan = (
                        bool(incoming)
                        or bool(adjustments)
                        or reason != 'auto'
                        or (tick_of_day == work_start_tick)
                    )
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
                            # Casual and natural Korean acknowledgments for chat
                            import random
                            ack_patterns = [
                                f"{sender_person.name.split()[0]}님, {ack_phrase} 확인했어요!",
                                f"{sender_person.name.split()[0]}님, {ack_phrase} 진행할게요~",
                                f"{sender_person.name.split()[0]}님, {ack_phrase} 작업 중이에요",
                                f"{sender_person.name.split()[0]}님, 알겠습니다. {ack_phrase} 처리할게요",
                                f"{sender_person.name.split()[0]}님, 네~ {ack_phrase} 바로 시작할게요",
                                f"{sender_person.name.split()[0]}님, {ack_phrase} 확인했습니다. 진행하겠습니다",
                            ]
                            ack_body = random.choice(ack_patterns)
                        else:
                            ack_body = f"{sender_person.name.split()[0]}, I'm on {ack_phrase}."
                        # Only acknowledge if on a shared active project
                        TICKS_PER_CALENDAR_WEEK = 7 * 24 * 60  # 10,080 ticks
                        current_week_for_validation = ((status.current_tick - 1) // TICKS_PER_CALENDAR_WEEK) + 1 if status.current_tick > 0 else 1
                        if sender_person is not None and not self._validate_project_pair(person.id, sender_person.id, current_week_for_validation):
                            continue
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
                                persona_id=person.id
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
                    # Prefer assigned projects when multiple are active
                    if active_projects:
                        try:
                            with get_connection() as conn:
                                rows = conn.execute(
                                    """
                                    SELECT pp.id FROM project_plans pp
                                    INNER JOIN project_assignments pa ON pp.id = pa.project_id
                                    WHERE pa.person_id = ? AND pp.start_week <= ? AND (pp.start_week + pp.duration_weeks - 1) >= ?
                                    ORDER BY pp.start_week ASC
                                    """,
                                    (person.id, current_week, current_week),
                                ).fetchall()
                            assigned_ids = [r["id"] for r in rows]
                            if assigned_ids:
                                assigned_first = [p for p in active_projects if p.get("id") in assigned_ids]
                                unassigned_rest = [p for p in active_projects if p.get("id") not in assigned_ids]
                                active_projects = assigned_first + unassigned_rest
                        except Exception:
                            pass

                    # Skip planning if person has no active projects (idle until assigned)
                    if not active_projects:
                        logger.info(
                            "Skipping planning for %s at tick %s (no active project assignments for week %s)",
                            person.name,
                            status.current_tick,
                            current_week,
                        )
                        continue

                    # Use first (assigned-first) project for daily plan primary reference, but pass all projects for multi-project support
                    primary_project = active_projects[0]

                    daily_plan_text = self._ensure_daily_plan(person, day_index, primary_project, active_projects if len(active_projects) > 1 else None)

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
                inbox_reply_requests = []  # Collect inbox reply requests for batch processing

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

                    # Task 6: Block ALL communication generation for away/offline personas
                    # Check status early before scheduling or dispatching any communications
                    offline_statuses = {"SickLeave", "Offline", "Absent", "Vacation", "Leave", "Away", "휴가", "병가", "자리비움"}
                    if override and (override[0] in offline_statuses):
                        logger.debug(
                            f"[STATUS_BLOCK] Blocking all communications for {person.name} due to status: {override[0]} "
                            f"(tick={status.current_tick})"
                        )
                        continue

                    # Schedule any explicitly timed comms from the hourly plan
                    try:
                        self._schedule_from_hourly_plan(person, hourly_result.content, status.current_tick)
                    except Exception:
                        pass

                    # Dispatch scheduled communications from hourly plans
                    se, sc = self._dispatch_scheduled(person, status.current_tick, people_by_id)
                    emails_sent += se
                    chats_sent += sc

                    # BATCH OPTIMIZATION: Collect inbox reply requests instead of processing one-by-one
                    # Check if this persona should generate an inbox reply
                    # Note: We collect requests here and process them in batch in PHASE 4
                    inbox_reply_request = self._prepare_inbox_reply_request(
                        person=person,
                        current_tick=status.current_tick,
                        people_by_id=people_by_id,
                        day_index=day_index,
                        person_project=person_project,
                        hourly_summary=hourly_summary,
                        daily_summary=daily_summary,
                        current_week=current_week
                    )
                    if inbox_reply_request:
                        inbox_reply_requests.append(inbox_reply_request)

                    # Automatic fallback generation removed as part of email volume reduction (Task 1)
                    # Personas now only communicate when:
                    # 1. They have explicit JSON communications in their hourly plans
                    # 2. They are responding to inbox messages (inbox-driven replies - Task 4 IMPLEMENTED with BATCH PROCESSING)
                    # 3. Event-driven notifications (sick leave, etc.) are triggered by the event injection system

                # PHASE 4: Process inbox reply requests in batch for performance optimization
                # This phase processes all collected inbox reply requests concurrently using async batch processing
                # Performance: 4-5x faster than sequential processing for multiple personas
                if inbox_reply_requests:
                    batch_emails, batch_chats = self._process_inbox_reply_batch(
                        inbox_reply_requests=inbox_reply_requests,
                        current_tick=status.current_tick,
                        people_by_id=people_by_id
                    )
                    emails_sent += batch_emails
                    chats_sent += batch_chats

                # Generate hourly summaries at the end of each hour (every 60 ticks)
                # PERFORMANCE: Parallelized to avoid blocking - runs 5x faster with ThreadPoolExecutor
                if status.current_tick % 60 == 0:
                    completed_hour = (status.current_tick // 60) - 1
                    # Use ThreadPoolExecutor to generate summaries in parallel instead of sequentially
                    with ThreadPoolExecutor(max_workers=min(4, len(people))) as executor:
                        futures = {
                            executor.submit(self._generate_hourly_summary, person, completed_hour): person
                            for person in people
                        }
                        for future in as_completed(futures):
                            person = futures[future]
                            try:
                                future.result()
                            except Exception as e:
                                logger.warning(f"Failed to generate hourly summary for {person.name} hour {completed_hour}: {e}")

                # Generate daily reports at the end of each day (hours_per_day * 60 minutes)
                if status.current_tick % day_ticks == 0:
                    completed_day = (status.current_tick // day_ticks) - 1
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
        # Stop auto-ticks BEFORE acquiring lock to avoid deadlock
        self.stop_auto_ticks()
        with self._advance_lock:
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
        Flushes ALL data including emails, chats, and all simulation artifacts.
        """
        # First clear runtime and planning artifacts
        # (reset() acquires its own lock)
        self.reset()

        # Then purge ALL data including email and chat servers
        with self._advance_lock:
            with get_connection() as conn:
                # Delete personas (cascades to schedule_blocks, project_assignments, etc.)
                conn.execute("DELETE FROM people")
                conn.execute("DELETE FROM worker_status_overrides")

                # Delete email server data
                conn.execute("DELETE FROM emails")
                conn.execute("DELETE FROM email_recipients")
                conn.execute("DELETE FROM mailboxes")
                conn.execute("DELETE FROM drafts")

                # Delete chat server data
                conn.execute("DELETE FROM chat_messages")
                conn.execute("DELETE FROM chat_members")
                conn.execute("DELETE FROM chat_rooms")
                conn.execute("DELETE FROM chat_users")

                # Delete project-related tables
                self._ensure_project_chat_rooms_table(conn)
                conn.execute("DELETE FROM project_chat_rooms")
                conn.execute("DELETE FROM project_assignments")

                # Delete any remaining simulation artifacts
                conn.execute("DELETE FROM hourly_summaries")

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

    @staticmethod
    def _ensure_project_chat_rooms_table(conn) -> None:
        """Ensure project_chat_rooms table exists for older databases."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_chat_rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                room_slug TEXT NOT NULL UNIQUE,
                room_name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                archived_at TEXT,
                FOREIGN KEY(project_id) REFERENCES project_plans(id) ON DELETE CASCADE
            )
        """)

    def _record_event(self, event_type: str, target_ids: Sequence[int], tick: int, payload: dict | None = None) -> None:
        event = EventCreate(type=event_type, target_ids=list(target_ids), at_tick=tick, payload=payload)
        self.inject_event(event)

    def _derive_seed(self, request: SimulationStartRequest | None) -> int:
        if request and request.random_seed is not None:
            return request.random_seed
        # For multi-project mode, use first project name; otherwise use single project name
        if request and request.projects:
            project_name = request.projects[0].project_name
        elif request and request.project_name:
            project_name = request.project_name
        else:
            project_name = 'vdos-default'
        base = project_name.encode('utf-8')
        digest = hashlib.sha256(base).digest()
        return int.from_bytes(digest[:8], 'big')

    def _maybe_generate_events(self, people: Sequence[PersonRead], tick: int, project_plan: dict[str, Any]) -> tuple[dict[int, list[str]], dict[int, list[_InboundMessage]]]:
        adjustments: dict[int, list[str]] = {}
        immediate: dict[int, list[_InboundMessage]] = {}
        if not people:
            return adjustments, immediate

        # Skip event generation on weekends (5-day work week)
        day_ticks = max(1, self.hours_per_day * 60)
        day_index = (tick - 1) // day_ticks
        day_of_week = day_index % 7
        if day_of_week >= 5:
            return adjustments, immediate

        rng = self._random
        # Gate event generation to humane frequencies to avoid per-minute GPT replanning.
        tick_of_day = (tick - 1) % day_ticks

        # Sick leave event: consider once per day around mid-morning.
        # Consider once per day around ~1 hour into the workday
        if tick_of_day == 60:
            # Roughly 5% daily chance across the team
            if rng.random() < 0.05:
                active_people = [p for p in people if self._status_overrides.get(p.id, (None, 0))[0] != 'SickLeave']
                if active_people:
                    target = rng.choice(active_people)
                    # Set status override until end of workday (in minute ticks)
                    until_tick = tick + (day_ticks - tick_of_day)
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
                    # Use simulated timestamp for consistency with other communications
                    dt = self._sim_datetime_for_tick(tick)
                    self.email_gateway.send_email(
                        sender=self.sim_manager_email,
                        to=[head.email_address],
                        subject=subject,
                        body=body,
                        sent_at_iso=(dt.isoformat() if dt else None),
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
        if (tick_of_day % 120 == 0) and (rng.random() < 0.10):
            head = next((p for p in people if getattr(p, 'is_department_head', False)), people[0])
            
            # Feature names in English and Korean
            # Using more universally understandable feature requests
            features = {
                'update main page banner': '메인 페이지 배너 업데이트',
                'prepare analytics dashboard': '분석 대시보드 준비',
                'add customer review section': '고객 리뷰 섹션 추가',
                'improve user onboarding flow': '사용자 온보딩 플로우 개선',
                'optimize mobile performance': '모바일 성능 최적화',
                'add search functionality': '검색 기능 추가',
            }
            feature_en = rng.choice(list(features.keys()))
            feature_ko = features[feature_en]
            
            # Use Korean for Korean locale, English otherwise
            feature = feature_ko if self._locale == 'ko' else feature_en
            
            if self._locale == 'ko':
                subject = f'클라이언트 요청: {feature}'
                body = f"클라이언트가 {feature} 작업을 요청했습니다. 이번 주기 내에 다음 단계를 조율해주세요."
            else:
                subject = f'Client request: {feature}'
                body = f"Client requested {feature}. Align on next steps within this cycle."
            
            head_message = _InboundMessage(
                sender_id=0,
                sender_name='Simulation Manager',
                subject=subject,
                summary=body,
                action_item=f'Plan response to client request: {feature}.' if self._locale != 'ko' else f'클라이언트 요청에 대한 응답 계획: {feature}',
                message_type='event',
                channel='email',
                tick=tick,
            )
            self._queue_runtime_message(head, head_message)
            immediate.setdefault(head.id, []).append(head_message)
            
            if self._locale == 'ko':
                adjustments.setdefault(head.id, []).append(f'클라이언트 요청에 대한 응답 계획: {feature}')
            else:
                adjustments.setdefault(head.id, []).append(f'Plan response to client request: {feature}.')

            # Get project-specific collaborators for the department head
            # This ensures the partner is from the same project(s)
            # Fix: Use calendar weeks (10080 ticks = 7*24*60) to match project configuration
            TICKS_PER_CALENDAR_WEEK = 7 * 24 * 60  # 10,080 ticks
            current_week = ((tick - 1) // TICKS_PER_CALENDAR_WEEK) + 1 if tick > 0 else 1
            people_by_id = {p.id: p for p in people}

            # Get head's active projects and pick first one
            active_projects = self._get_all_active_projects_for_person(head.id, current_week)
            project_for_collab = active_projects[0] if active_projects else None

            collaborators = self._get_project_collaborators(
                person_id=head.id,
                current_week=current_week,
                all_people=people_by_id,
                project_id=project_for_collab["id"] if isinstance(project_for_collab, dict) else getattr(project_for_collab, "id", None) if project_for_collab else None
            )
            if collaborators:
                partner = rng.choice(collaborators)
                
                # Use casual Korean for chat messages
                if self._locale == 'ko':
                    # Casual Korean chat message
                    summary_text = f'{head.name}님과 {feature} 작업 협력'
                    action_text = f'{head.name}님과 {feature} 작업 협력'
                    chat_body = f"{head.name}님, {feature} 건으로 클라이언트 요청 들어왔어요. 같이 진행해요~"
                else:
                    summary_text = f'Partner with {head.name} on {feature}.'
                    action_text = f'Support {head.name} on {feature}.'
                    chat_body = f"Client request: {feature}. Let's sync on next steps."
                
                partner_message = _InboundMessage(
                    sender_id=head.id,
                    sender_name=head.name,
                    subject=subject,
                    summary=summary_text,
                    action_item=action_text,
                    message_type='event',
                    channel='chat',
                    tick=tick,
                )
                self._queue_runtime_message(partner, partner_message)
                immediate.setdefault(partner.id, []).append(partner_message)
                
                if self._locale == 'ko':
                    adjustments.setdefault(partner.id, []).append(f'{head.name}님과 클라이언트 요청 작업 협력: {feature}')
                else:
                    adjustments.setdefault(partner.id, []).append(f'Partner with {head.name} on client request: {feature}.')
                
                targets = [head.id, partner.id]
            else:
                targets = [head.id]
            self._record_event('client_feature_request', targets, tick, {'feature': feature})

        return adjustments, immediate

    def _bootstrap_channels(self) -> None:
        # Ensure Simulation Manager identities exist
        self.email_gateway.ensure_mailbox(self.sim_manager_email, "Simulation Manager")
        self.chat_gateway.ensure_user(self.sim_manager_handle, "Simulation Manager")
        # Ensure all existing personas have provisioned mailboxes and chat users
        try:
            people = self.list_people()
            for p in people:
                if getattr(p, 'email_address', None):
                    self.email_gateway.ensure_mailbox(p.email_address, p.name)
                if getattr(p, 'chat_handle', None):
                    self.chat_gateway.ensure_user(p.chat_handle, p.name)
        except Exception:
            # Non-fatal: servers may not be up at engine init; they will be
            # provisioned lazily on first use
            pass

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

    def get_current_tick(self) -> int:
        """
        Get the current simulation tick.

        Returns:
            int: Current tick number
        """
        status = self._fetch_state()
        return status.current_tick

    def set_current_tick(self, tick: int) -> None:
        """
        Set the current simulation tick (for replay/time-travel).

        This is used by the replay manager to jump to specific ticks.
        Updates the tick in the database without logging to tick_log.

        Args:
            tick: Tick number to jump to

        Raises:
            ValueError: If tick < 0
        """
        if tick < 0:
            raise ValueError(f"Tick must be >= 0, got {tick}")

        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET current_tick = ? WHERE id = 1",
                (tick,),
            )

        logger.info(f"[REPLAY] Current tick set to {tick}")

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
