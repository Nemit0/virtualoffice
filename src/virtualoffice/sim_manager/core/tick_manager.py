"""
Tick Management Module.

This module handles all tick-related operations including time conversions,
work hours calculations, and auto-tick threading.

Extracted from: src/virtualoffice/sim_manager/engine.py
Date: 2025-10-27
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Sequence

from virtualoffice.common.db import get_connection

logger = logging.getLogger(__name__)


class TickManager:
    """
    Manages tick-related operations and auto-tick threading.

    This class encapsulates all tick-related operations including:
    - Time format conversions (tick <-> datetime <-> human-readable)
    - Work hours parsing and validation
    - Auto-tick thread management

    Example:
        >>> tick_manager = TickManager(hours_per_day=8)
        >>> formatted = tick_manager.format_sim_time(24)
        >>> print(formatted)  # "Day 3 00:00"
    """

    def __init__(
        self,
        hours_per_day: int = 8,
        tick_interval_seconds: float = 1.0,
    ) -> None:
        """
        Initialize tick manager.

        Args:
            hours_per_day: Number of ticks per simulated day
            tick_interval_seconds: Seconds between auto-ticks
        """
        self.hours_per_day = hours_per_day
        self._tick_interval_seconds = tick_interval_seconds
        self._sim_base_dt: datetime | None = None
        self._work_hours_ticks: dict[int, tuple[int, int]] = {}

        # Auto-tick threading state
        self._auto_tick_thread: threading.Thread | None = None
        self._auto_tick_stop: threading.Event | None = None
        self._advance_lock = threading.Lock()

    def set_base_datetime(self, base_dt: datetime | None = None) -> None:
        """
        Set the base datetime for simulation time calculations.

        Args:
            base_dt: Base datetime. If None, uses current UTC time.
        """
        try:
            self._sim_base_dt = base_dt or datetime.now(timezone.utc)
        except Exception:
            self._sim_base_dt = None

            self._sim_base_dt = None

    def parse_time_to_tick(self, time_str: str, *, round_up: bool = False) -> int:
        """
        Parse time string "HH:MM" to tick number within a day.

        Args:
            time_str: Time string in "HH:MM" format
            round_up: If True, round up to nearest tick; otherwise round down

        Returns:
            Tick number (0-indexed within day)

        Example:
            >>> tm = TickManager(hours_per_day=8)
            >>> tm.parse_time_to_tick("09:00")
            3  # 9:00 AM is 3/8 through the day
        """
        try:
            hours, minutes = time_str.split(":")
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

    def parse_work_hours_to_ticks(self, work_hours: str) -> tuple[int, int]:
        """
        Parse work hours string "HH:MM-HH:MM" to tick range.

        Args:
            work_hours: Work hours string in "HH:MM-HH:MM" format

        Returns:
            Tuple of (start_tick, end_tick) within a day

        Example:
            >>> tm = TickManager(hours_per_day=8)
            >>> tm.parse_work_hours_to_ticks("09:00-17:00")
            (3, 6)  # 9 AM to 5 PM
        """
        ticks_per_day = max(1, self.hours_per_day)
        if ticks_per_day < 6:
            return (0, ticks_per_day)
        if not work_hours or "-" not in work_hours:
            return (0, ticks_per_day)
        start_str, end_str = [segment.strip() for segment in work_hours.split("-", 1)]
        start_tick = self.parse_time_to_tick(start_str, round_up=False)
        end_tick = self.parse_time_to_tick(end_str, round_up=True)
        start_tick = max(0, min(ticks_per_day - 1, start_tick))
        end_tick = max(0, min(ticks_per_day, end_tick))
        if start_tick == end_tick:
            return (0, ticks_per_day)
        return (start_tick, end_tick)

    def update_work_windows(self, people: Sequence[Any]) -> None:
        """
        Update work hours cache for all people.

        Args:
            people: Sequence of PersonRead objects with work_hours attribute
        """
        cache: dict[int, tuple[int, int]] = {}
        for person in people:
            start_tick, end_tick = self.parse_work_hours_to_ticks(getattr(person, "work_hours", "") or "")
            cache[person.id] = (start_tick, end_tick)
        self._work_hours_ticks = cache

    def get_work_hours_ticks(self, person_id: int) -> tuple[int, int]:
        """
        Get work hours tick range for a person.

        Args:
            person_id: ID of the person

        Returns:
            Tuple of (start_tick, end_tick) within a day, or (0, hours_per_day) if not found
        """
        ticks_per_day = max(1, self.hours_per_day)
        return self._work_hours_ticks.get(person_id, (0, ticks_per_day))

    def is_within_work_hours(self, person: Any, tick: int) -> bool:
        """
        Check if tick is within person's work hours.

        Args:
            person: PersonRead object with id attribute
            tick: Tick number to check

        Returns:
            True if tick is within work hours, False otherwise
        """
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

    def format_sim_time(self, tick: int) -> str:
        """
        Format tick number to human-readable simulation time.

        Args:
            tick: Tick number (1-indexed)

        Returns:
            Formatted time string "Day X HH:MM"

        Example:
            >>> tm = TickManager(hours_per_day=8)
            >>> tm.format_sim_time(1)
            "Day 1 00:00"
            >>> tm.format_sim_time(24)
            "Day 3 00:00"
        """
        if tick <= 0:
            return "Day 0 00:00"
        ticks_per_day = max(1, self.hours_per_day)
        day_index = (tick - 1) // ticks_per_day + 1
        tick_of_day = (tick - 1) % ticks_per_day
        minutes = int((tick_of_day / ticks_per_day) * 1440)
        hour = minutes // 60
        minute = minutes % 60
        return f"Day {day_index} {hour:02d}:{minute:02d}"

    def sim_datetime_for_tick(self, tick: int) -> datetime | None:
        """
        Convert tick to datetime.

        Args:
            tick: Tick number (1-indexed)

        Returns:
            Datetime for tick, or None if base datetime not set
        """
        base = self._sim_base_dt
        if not base:
            return None
        ticks_per_day = max(1, self.hours_per_day)
        day_index = (tick - 1) // ticks_per_day
        tick_of_day = (tick - 1) % ticks_per_day
        minutes = int((tick_of_day / ticks_per_day) * 1440)
        return base + timedelta(days=day_index, minutes=minutes)

    def calculate_current_week(self, current_tick: int) -> int:
        """
        Calculate current week from tick number.

        Args:
            current_tick: Current tick number

        Returns:
            Current week number (1-indexed)
        """
        if current_tick <= 0:
            return 1
        current_day = (current_tick - 1) // max(1, self.hours_per_day)
        return max(1, (current_day // 5) + 1)

    def start_auto_tick(
        self,
        is_running: bool,
        advance_callback: Callable[[], None],
        state_manager: Any,
        get_active_projects_callback: Callable[[int], list[dict]],
        archive_chat_room_callback: Callable[[int], bool],
        auto_pause_enabled: bool = True,
    ) -> None:
        """
        Start auto-tick thread.

        Args:
            is_running: Whether simulation is running
            advance_callback: Callback to advance simulation by 1 tick
            state_manager: StateManager instance for getting/setting state
            get_active_projects_callback: Callback to get active projects for a week
            archive_chat_room_callback: Callback to archive chat room for project
            auto_pause_enabled: Whether to enable auto-pause on project completion

        Raises:
            RuntimeError: If simulation is not running
        """
        if not is_running:
            raise RuntimeError("Simulation must be running before enabling automatic ticks")

        state_manager.set_auto_tick(True)
        thread = self._auto_tick_thread
        if thread is None or not thread.is_alive():
            stop_event = threading.Event()
            self._auto_tick_stop = stop_event
            thread = threading.Thread(
                target=self._run_auto_tick_loop,
                args=(
                    stop_event,
                    advance_callback,
                    state_manager,
                    get_active_projects_callback,
                    archive_chat_room_callback,
                    auto_pause_enabled,
                ),
                name="vdos-auto-tick",
                daemon=True,
            )
            self._auto_tick_thread = thread
            thread.start()

    def stop_auto_tick(self, state_manager: Any) -> None:
        """
        Stop auto-tick thread.

        Args:
            state_manager: StateManager instance for setting auto_tick flag
        """
        state_manager.set_auto_tick(False)
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

    def _run_auto_tick_loop(
        self,
        stop_event: threading.Event,
        advance_callback: Callable[[], None],
        state_manager: Any,
        get_active_projects_callback: Callable[[int], list[dict]],
        archive_chat_room_callback: Callable[[int], bool],
        auto_pause_enabled: bool,
    ) -> None:
        """
        Main auto-tick loop (runs in background thread).

        Args:
            stop_event: Event to signal loop should stop
            advance_callback: Callback to advance simulation by 1 tick
            state_manager: StateManager instance
            get_active_projects_callback: Callback to get active projects
            archive_chat_room_callback: Callback to archive chat room
            auto_pause_enabled: Whether to auto-pause on project completion
        """
        while not stop_event.wait(self._tick_interval_seconds):
            state = state_manager.get_current_state()
            if not state.is_running or not state.auto_tick:
                break

            # Check if auto-pause on project completion is enabled
            if auto_pause_enabled:
                try:
                    # Enhanced project lifecycle calculations with edge case handling
                    if state.current_tick <= 0:
                        current_day = 0
                        current_week = 1
                    else:
                        # Ensure hours_per_day is at least 1 to prevent division by zero
                        hours_per_day = max(1, self.hours_per_day)
                        current_day = (state.current_tick - 1) // hours_per_day
                        current_week = max(1, (current_day // 5) + 1)

                    # Get active projects for current week using enhanced calculation
                    active_projects = get_active_projects_callback(current_week)

                    if not active_projects:
                        # Enhanced multi-project scenario handling
                        with get_connection() as conn:
                            # Check for future projects that haven't started yet
                            future_projects = conn.execute(
                                "SELECT COUNT(*) as count FROM project_plans WHERE start_week > ?", (current_week,)
                            ).fetchone()

                            # Get details of future projects for logging (if needed in future)
                            _ = conn.execute(
                                """SELECT project_name, start_week, duration_weeks,
                                   (start_week + duration_weeks - 1) as end_week
                                   FROM project_plans WHERE start_week > ?
                                   ORDER BY start_week ASC""",
                                (current_week,),
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
                                    (current_week,),
                                ).fetchall()

                                _ = conn.execute("SELECT COUNT(*) as count FROM project_plans").fetchone()["count"]

                            # Track completed projects for archiving
                            _ = len(completed_projects)
                            _ = [p["project_name"] for p in completed_projects[:5]]  # Show first 5

                            # Archive chat rooms for completed projects
                            for completed_project in completed_projects:
                                try:
                                    # Find the project ID for this completed project
                                    with get_connection() as conn:
                                        project_row = conn.execute(
                                            "SELECT id FROM project_plans WHERE project_name = ?",
                                            (completed_project["project_name"],),
                                        ).fetchone()

                                    if project_row:
                                        archived = archive_chat_room_callback(project_row["id"])
                                        if archived:
                                            logger.info(
                                                f"Archived chat room for completed project '{completed_project['project_name']}'"
                                            )
                                except Exception:
                                    logger.warning(
                                        f"Failed to archive chat room for project '{completed_project['project_name']}': error occurred"
                                    )

                except Exception:
                    logger.error(
                        f"Auto-pause check failed at tick {state.current_tick}: error occurred. "
                        f"Continuing auto-tick to prevent simulation halt."
                    )

            try:
                with self._advance_lock:
                    advance_callback()
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Automatic tick failed; disabling auto ticks.")
                state_manager.set_auto_tick(False)
                break

    def get_advance_lock(self) -> threading.Lock:
        """
        Get the advance lock for thread-safe tick advancement.

        Returns:
            Threading lock
        """
        return self._advance_lock

    def set_tick_interval(self, interval_seconds: float) -> None:
        """
        Set the auto-tick interval.

        Args:
            interval_seconds: Seconds between auto-ticks (0 for maximum speed)

        Raises:
            ValueError: If interval is negative or exceeds 60 seconds
        """
        if interval_seconds < 0:
            raise ValueError("Tick interval cannot be negative")
        if interval_seconds > 60:
            raise ValueError("Tick interval cannot exceed 60 seconds")
        self._tick_interval_seconds = interval_seconds

    def get_tick_interval(self) -> float:
        """
        Get the current auto-tick interval.

        Returns:
            Seconds between auto-ticks
        """
        return self._tick_interval_seconds
