"""
Replay Manager - Time Machine for Simulation Playback

This module provides time-travel functionality for the VirtualOffice simulation,
allowing users to jump to any previously generated tick and view historical data.

Primary use case: Live feed simulation data to external projects via API.
"""

import logging
from typing import Optional, TYPE_CHECKING

from virtualoffice.common.db import get_connection

if TYPE_CHECKING:
    from virtualoffice.sim_manager.engine import SimulationEngine

logger = logging.getLogger(__name__)


class ReplayManager:
    """
    Manages replay/time-travel functionality for the simulation.

    Features:
    - Jump to any previously generated tick
    - Safety checks to prevent jumping beyond max generated data
    - Query emails and chats at specific ticks
    - Switch between live and replay mode
    """

    def __init__(self, engine: 'SimulationEngine'):
        """
        Initialize the replay manager.

        Args:
            engine: Reference to the simulation engine
        """
        self.engine = engine
        self.mode: str = 'live'  # 'live' or 'replay'

        # Calendar day constants (1440 ticks per 24-hour day)
        self.TICKS_PER_CALENDAR_DAY = 24 * 60  # 1440 ticks
        self.TICKS_PER_HOUR = 60

    def get_max_generated_tick(self) -> int:
        """
        Get the highest tick number that has generated data in the database.

        This is used as the safety boundary - users cannot jump beyond this tick.

        Returns:
            int: Maximum tick with data, or 0 if no data exists
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT MAX(tick) FROM worker_exchange_log"
            )
            result = cursor.fetchone()
            max_tick = result[0] if result and result[0] is not None else 0

        logger.info(f"[REPLAY] Max generated tick: {max_tick}")
        return max_tick

    def get_metadata(self) -> dict:
        """
        Get replay metadata including boundaries and current state.

        Returns:
            dict: Metadata with max_tick, current_tick, mode, stats
        """
        max_tick = self.get_max_generated_tick()
        current_tick = self.engine.get_current_tick()

        # Calculate days simulated
        total_days = (max_tick // self.TICKS_PER_CALENDAR_DAY) + 1 if max_tick > 0 else 0

        # Get communication counts
        with get_connection() as conn:
            email_count = conn.execute(
                "SELECT COUNT(*) FROM emails"
            ).fetchone()[0]

            chat_count = conn.execute(
                "SELECT COUNT(*) FROM chat_messages"
            ).fetchone()[0]

        # Determine if in replay mode
        is_replay = current_tick < max_tick

        return {
            "max_generated_tick": max_tick,
            "current_tick": current_tick,
            "total_days": total_days,
            "mode": "replay" if is_replay else "live",
            "is_replay": is_replay,
            "total_emails": email_count,
            "total_chats": chat_count
        }

    def tick_to_time(self, tick: int) -> dict:
        """
        Convert a tick number to day/hour/minute representation.

        Args:
            tick: Tick number to convert

        Returns:
            dict: { "day": int, "hour": int, "minute": int, "sim_time": str }
        """
        day = ((tick - 1) // self.TICKS_PER_CALENDAR_DAY) + 1
        tick_of_day = (tick - 1) % self.TICKS_PER_CALENDAR_DAY
        hour = tick_of_day // 60
        minute = tick_of_day % 60

        return {
            "day": day,
            "hour": hour,
            "minute": minute,
            "sim_time": f"{hour:02d}:{minute:02d}"
        }

    def time_to_tick(self, day: int, hour: int, minute: int) -> int:
        """
        Convert day/hour/minute to tick number.

        Args:
            day: Day number (1-indexed)
            hour: Hour (0-23)
            minute: Minute (0-59)

        Returns:
            int: Corresponding tick number
        """
        # Validate inputs
        if day < 1:
            raise ValueError(f"Day must be >= 1, got {day}")
        if not (0 <= hour <= 23):
            raise ValueError(f"Hour must be 0-23, got {hour}")
        if not (0 <= minute <= 59):
            raise ValueError(f"Minute must be 0-59, got {minute}")

        # Calculate tick
        # Day 1 starts at tick 1, so: (day - 1) * ticks_per_day + 1
        tick = ((day - 1) * self.TICKS_PER_CALENDAR_DAY) + (hour * 60) + minute + 1

        return tick

    def jump_to_tick(self, tick: int) -> dict:
        """
        Jump to a specific tick (with safety validation).

        This is the main time-travel function. It validates the requested tick
        against the max generated tick, then updates the engine's current tick.

        Args:
            tick: Tick number to jump to

        Returns:
            dict: Response with tick data (emails, chats, metadata)

        Raises:
            ValueError: If tick is out of valid range
        """
        # Safety validation
        max_tick = self.get_max_generated_tick()

        if tick < 1:
            raise ValueError(f"Tick must be >= 1, got {tick}")

        if tick > max_tick:
            raise ValueError(
                f"Cannot jump to tick {tick}: only {max_tick} ticks have been generated. "
                f"Run the simulation longer to generate more data."
            )

        # Update engine's current tick
        logger.info(f"[REPLAY] Jumping from tick {self.engine.get_current_tick()} to {tick}")
        self.engine.set_current_tick(tick)
        self.mode = 'replay'

        # Get data at this tick
        return self.get_current_tick_data()

    def jump_to_time(self, day: int, hour: int, minute: int) -> dict:
        """
        Jump to a specific time (day/hour/minute).

        Convenience method that converts time to tick and jumps.

        Args:
            day: Day number (1-indexed)
            hour: Hour (0-23)
            minute: Minute (0-59)

        Returns:
            dict: Response with tick data

        Raises:
            ValueError: If time is invalid or beyond max generated data
        """
        tick = self.time_to_tick(day, hour, minute)
        return self.jump_to_tick(tick)

    def get_tick_data(self, tick: int) -> dict:
        """
        Get emails and chats that were sent at a specific tick.

        Queries the database for communications that occurred at the specified tick
        by matching timestamps from worker_exchange_log.

        Args:
            tick: Tick number to query

        Returns:
            dict: { "emails": [...], "chats": [...] }
        """
        emails = []
        chats = []

        with get_connection() as conn:
            # Get time range for this tick from worker_exchange_log
            time_range = conn.execute(
                """
                SELECT MIN(created_at), MAX(created_at)
                FROM worker_exchange_log
                WHERE tick = ?
                """,
                (tick,)
            ).fetchone()

            if time_range and time_range[0]:
                min_time, max_time = time_range

                # Query emails within this time range
                email_rows = conn.execute(
                    """
                    SELECT id, sender, subject, body, thread_id, sent_at
                    FROM emails
                    WHERE sent_at >= ? AND sent_at <= ?
                    ORDER BY sent_at
                    """,
                    (min_time, max_time)
                ).fetchall()

                for row in email_rows:
                    # Get recipients
                    # Align with schema: email_recipients(email_id, address, kind)
                    recipients_rows = conn.execute(
                        "SELECT address FROM email_recipients WHERE email_id = ? ORDER BY rowid",
                        (row[0],)
                    ).fetchall()
                    recipients = [r[0] for r in recipients_rows]

                    emails.append({
                        "id": row[0],
                        "sender": row[1],
                        "recipients": recipients,
                        "subject": row[2],
                        "body": row[3],
                        "thread_id": row[4],
                        "sent_at": row[5]
                    })

                # Query chats within this time range
                chat_rows = conn.execute(
                    """
                    SELECT id, room_id, sender, body, sent_at
                    FROM chat_messages
                    WHERE sent_at >= ? AND sent_at <= ?
                    ORDER BY sent_at
                    """,
                    (min_time, max_time)
                ).fetchall()

                for row in chat_rows:
                    chats.append({
                        "id": row[0],
                        "room_id": row[1],
                        "sender": row[2],
                        "body": row[3],
                        "sent_at": row[4]
                    })

        logger.debug(f"[REPLAY] Tick {tick}: {len(emails)} emails, {len(chats)} chats")

        return {
            "emails": emails,
            "chats": chats
        }

    def get_current_tick_data(self) -> dict:
        """
        Get data at the engine's current tick.

        Returns:
            dict: Complete response with tick, time, data, and metadata
        """
        current_tick = self.engine.get_current_tick()
        time_info = self.tick_to_time(current_tick)
        tick_data = self.get_tick_data(current_tick)
        max_tick = self.get_max_generated_tick()

        return {
            "tick": current_tick,
            "day": time_info["day"],
            "hour": time_info["hour"],
            "minute": time_info["minute"],
            "sim_time": time_info["sim_time"],
            "is_replay": current_tick < max_tick,
            "max_generated_tick": max_tick,
            "data": tick_data
        }

    def reset_to_live(self) -> dict:
        """
        Reset to live mode (jump to max generated tick).

        Returns:
            dict: Metadata after reset
        """
        max_tick = self.get_max_generated_tick()

        logger.info(f"[REPLAY] Resetting to live mode (tick {max_tick})")

        self.engine.set_current_tick(max_tick)
        self.mode = 'live'

        return self.get_metadata()

    def set_mode(self, mode: str) -> dict:
        """
        Set the replay mode (live or replay).

        Args:
            mode: 'live' or 'replay'

        Returns:
            dict: Updated metadata

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in ('live', 'replay'):
            raise ValueError(f"Mode must be 'live' or 'replay', got '{mode}'")

        if mode == 'live':
            return self.reset_to_live()
        else:
            self.mode = mode
            return self.get_metadata()
