"""
Simulation State Management Module.

This module handles all simulation state persistence, database schema management,
and state-related operations that were previously in the monolithic engine.

Extracted from: src/virtualoffice/sim_manager/engine.py
Date: 2025-10-27
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple

from virtualoffice.common.db import execute_script, get_connection


@dataclass
class SimulationStatus:
    """Current simulation status."""

    current_tick: int
    is_running: bool
    auto_tick: bool


# Database Schema
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

CREATE TABLE IF NOT EXISTS project_chat_rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    room_slug TEXT NOT NULL UNIQUE,
    room_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_at TEXT,
    FOREIGN KEY(project_id) REFERENCES project_plans(id) ON DELETE CASCADE
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


class SimulationState:
    """
    Manages simulation state persistence and database operations.

    This class encapsulates all state-related operations including:
    - Database schema initialization and migrations
    - Current simulation state (tick, running status, auto-tick)
    - Worker status overrides
    - State persistence and retrieval

    Example:
        >>> state = SimulationState()
        >>> state.initialize_database()
        >>> status = state.get_current_state()
        >>> print(f"Tick: {status.current_tick}")
    """

    def __init__(self, db_path: str | None = None):
        """
        Initialize simulation state manager.

        Args:
            db_path: Optional custom database path. If None, uses default from env.
        """
        self.db_path = db_path or os.getenv("VDOS_DB_PATH", "src/virtualoffice/vdos.db")
        self._status_overrides: dict[int, Tuple[str, int]] = {}

    def initialize_database(self) -> None:
        """Initialize database schema and ensure state row exists."""
        execute_script(SIM_SCHEMA)
        self.apply_migrations()
        self._ensure_state_row()
        self.load_status_overrides()

    def apply_migrations(self) -> None:
        """Apply database schema migrations."""
        with get_connection() as conn:
            # Check for missing columns and add them
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

    def _ensure_state_row(self) -> None:
        """Ensure simulation_state table has the singleton row."""
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM simulation_state WHERE id = 1").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO simulation_state(id, current_tick, is_running, auto_tick) VALUES (1, 0, 0, 0)"
                )

    def get_current_state(self) -> SimulationStatus:
        """
        Get current simulation state.

        Returns:
            SimulationStatus containing current_tick, is_running, and auto_tick
        """
        with get_connection() as conn:
            row = conn.execute(
                "SELECT current_tick, is_running, auto_tick FROM simulation_state WHERE id = 1"
            ).fetchone()
        return SimulationStatus(
            current_tick=row["current_tick"], is_running=bool(row["is_running"]), auto_tick=bool(row["auto_tick"])
        )

    def update_tick(self, tick: int, reason: str) -> None:
        """
        Update current tick and log the reason.

        Args:
            tick: New tick value
            reason: Reason for advancement (e.g., "manual", "auto-tick", "initialization")
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET current_tick = ? WHERE id = 1",
                (tick,),
            )
            conn.execute(
                "INSERT INTO tick_log(tick, reason) VALUES (?, ?)",
                (tick, reason),
            )

    def set_running(self, running: bool) -> None:
        """
        Set simulation running state.

        Args:
            running: True to mark as running, False otherwise
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET is_running = ? WHERE id = 1",
                (1 if running else 0,),
            )

    def set_auto_tick(self, enabled: bool) -> None:
        """
        Enable or disable auto-tick mode.

        Args:
            enabled: True to enable auto-tick, False to disable
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE simulation_state SET auto_tick = ? WHERE id = 1",
                (1 if enabled else 0,),
            )

    def load_status_overrides(self) -> None:
        """Load worker status overrides from database into memory."""
        with get_connection() as conn:
            rows = conn.execute("SELECT worker_id, status, until_tick FROM worker_status_overrides").fetchall()
        self._status_overrides = {row["worker_id"]: (row["status"], row["until_tick"]) for row in rows}

    def get_status_overrides(self) -> dict[int, Tuple[str, int]]:
        """
        Get all worker status overrides.

        Returns:
            Dictionary mapping worker_id to (status, until_tick) tuples
        """
        return self._status_overrides.copy()

    def set_status_override(self, worker_id: int, status: str, until_tick: int, reason: str) -> None:
        """
        Set a status override for a worker.

        Args:
            worker_id: ID of the worker
            status: Status to override (e.g., "out_sick", "on_vacation")
            until_tick: Tick when override expires
            reason: Reason for the override
        """
        with get_connection() as conn:
            conn.execute(
                (
                    "INSERT INTO worker_status_overrides(worker_id, status, until_tick, reason) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(worker_id) DO UPDATE SET status = excluded.status, until_tick = excluded.until_tick, reason = excluded.reason"
                ),
                (worker_id, status, until_tick, reason),
            )
        self._status_overrides[worker_id] = (status, until_tick)

    def clear_status_override(self, worker_id: int) -> None:
        """
        Clear status override for a worker.

        Args:
            worker_id: ID of the worker
        """
        with get_connection() as conn:
            conn.execute("DELETE FROM worker_status_overrides WHERE worker_id = ?", (worker_id,))
        self._status_overrides.pop(worker_id, None)

    def clear_expired_status_overrides(self, current_tick: int) -> list[int]:
        """
        Clear status overrides that have expired.

        Args:
            current_tick: Current simulation tick

        Returns:
            List of worker IDs whose overrides were cleared
        """
        expired = [
            worker_id for worker_id, (_, until_tick) in self._status_overrides.items() if current_tick >= until_tick
        ]
        if expired:
            with get_connection() as conn:
                conn.executemany(
                    "DELETE FROM worker_status_overrides WHERE worker_id = ?",
                    [(worker_id,) for worker_id in expired],
                )
            for worker_id in expired:
                self._status_overrides.pop(worker_id, None)
        return expired

    def clear_all_status_overrides(self) -> None:
        """Clear all worker status overrides."""
        with get_connection() as conn:
            conn.execute("DELETE FROM worker_status_overrides")
        self._status_overrides.clear()
        self.load_status_overrides()

    def reset_simulation(self) -> None:
        """
        Reset simulation state to tick 0.

        WARNING: This clears all simulation data but preserves personas.
        """
        with get_connection() as conn:
            # Clear all simulation data
            for table in (
                "project_plans",
                "worker_plans",
                "worker_exchange_log",
                "worker_runtime_messages",
                "daily_reports",
                "simulation_reports",
                "events",
                "tick_log",
                "hourly_summaries",
            ):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM worker_status_overrides")
            conn.execute("UPDATE simulation_state SET current_tick = 0, is_running = 0, auto_tick = 0 WHERE id = 1")
        self._status_overrides.clear()
