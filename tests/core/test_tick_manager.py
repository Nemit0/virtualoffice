"""
Tests for TickManager module.

Tests time conversions, work hours parsing, and auto-tick threading.
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock, MagicMock

import pytest

from virtualoffice.sim_manager.core import TickManager


class TestTimeConversions:
    """Test time format conversions."""

    def test_parse_time_to_tick_morning(self):
        """Test parsing morning time to tick."""
        tm = TickManager(hours_per_day=8)
        # 9:00 AM = 540 minutes = 540/1440 * 8 = 3.0 ticks
        tick = tm.parse_time_to_tick("09:00")
        assert tick == 3

    def test_parse_time_to_tick_noon(self):
        """Test parsing noon time to tick."""
        tm = TickManager(hours_per_day=8)
        # 12:00 PM = 720 minutes = 720/1440 * 8 = 4.0 ticks
        tick = tm.parse_time_to_tick("12:00")
        assert tick == 4

    def test_parse_time_to_tick_evening(self):
        """Test parsing evening time to tick."""
        tm = TickManager(hours_per_day=8)
        # 17:00 (5 PM) = 1020 minutes = 1020/1440 * 8 = 5.666... ticks
        tick = tm.parse_time_to_tick("17:00")
        assert tick == 5  # Floor by default

    def test_parse_time_to_tick_round_up(self):
        """Test parsing time with round up."""
        tm = TickManager(hours_per_day=8)
        # 17:00 = 1020/1440 * 8 = 5.666... ticks
        tick = tm.parse_time_to_tick("17:00", round_up=True)
        assert tick == 6  # Ceiling

    def test_parse_time_to_tick_invalid_format(self):
        """Test parsing invalid time format."""
        tm = TickManager(hours_per_day=8)
        tick = tm.parse_time_to_tick("invalid")
        assert tick == 0

    def test_parse_time_to_tick_midnight(self):
        """Test parsing midnight."""
        tm = TickManager(hours_per_day=8)
        tick = tm.parse_time_to_tick("00:00")
        assert tick == 0

    def test_parse_work_hours_to_ticks_standard(self):
        """Test parsing standard work hours."""
        tm = TickManager(hours_per_day=8)
        # 09:00-17:00 (9 AM to 5 PM)
        start_tick, end_tick = tm.parse_work_hours_to_ticks("09:00-17:00")
        assert start_tick == 3
        assert end_tick == 6

    def test_parse_work_hours_to_ticks_early_bird(self):
        """Test parsing early work hours."""
        tm = TickManager(hours_per_day=8)
        # 06:00-14:00 (6 AM to 2 PM)
        # 06:00 = 360/1440 * 8 = 2.0 ticks
        # 14:00 = 840/1440 * 8 = 4.666... = ceil = 5 ticks
        start_tick, end_tick = tm.parse_work_hours_to_ticks("06:00-14:00")
        assert start_tick == 2
        assert end_tick == 5

    def test_parse_work_hours_to_ticks_invalid_format(self):
        """Test parsing invalid work hours format."""
        tm = TickManager(hours_per_day=8)
        start_tick, end_tick = tm.parse_work_hours_to_ticks("invalid")
        assert start_tick == 0
        assert end_tick == 8

    def test_parse_work_hours_to_ticks_empty(self):
        """Test parsing empty work hours."""
        tm = TickManager(hours_per_day=8)
        start_tick, end_tick = tm.parse_work_hours_to_ticks("")
        assert start_tick == 0
        assert end_tick == 8

    def test_parse_work_hours_to_ticks_small_day(self):
        """Test parsing work hours with small hours_per_day."""
        tm = TickManager(hours_per_day=4)
        # When ticks_per_day < 6, return full day
        start_tick, end_tick = tm.parse_work_hours_to_ticks("09:00-17:00")
        assert start_tick == 0
        assert end_tick == 4

    def test_format_sim_time_day_1(self):
        """Test formatting day 1 times."""
        tm = TickManager(hours_per_day=8)
        # tick_of_day = (tick - 1) % 8
        # minutes = (tick_of_day / 8) * 1440
        # Tick 1: tick_of_day=0, minutes=0 -> 00:00
        # Tick 3: tick_of_day=2, minutes=360 -> 06:00
        # Tick 5: tick_of_day=4, minutes=720 -> 12:00
        assert tm.format_sim_time(1) == "Day 1 00:00"
        assert tm.format_sim_time(3) == "Day 1 06:00"
        assert tm.format_sim_time(5) == "Day 1 12:00"

    def test_format_sim_time_day_2(self):
        """Test formatting day 2 times."""
        tm = TickManager(hours_per_day=8)
        # Tick 9: day=2, tick_of_day=0, minutes=0 -> 00:00
        # Tick 11: day=2, tick_of_day=2, minutes=360 -> 06:00
        assert tm.format_sim_time(9) == "Day 2 00:00"
        assert tm.format_sim_time(11) == "Day 2 06:00"

    def test_format_sim_time_day_3(self):
        """Test formatting day 3 times."""
        tm = TickManager(hours_per_day=8)
        assert tm.format_sim_time(17) == "Day 3 00:00"

    def test_format_sim_time_tick_zero(self):
        """Test formatting tick 0."""
        tm = TickManager(hours_per_day=8)
        assert tm.format_sim_time(0) == "Day 0 00:00"

    def test_format_sim_time_negative_tick(self):
        """Test formatting negative tick."""
        tm = TickManager(hours_per_day=8)
        assert tm.format_sim_time(-5) == "Day 0 00:00"

    def test_sim_datetime_for_tick_no_base(self):
        """Test datetime conversion with no base datetime."""
        tm = TickManager(hours_per_day=8)
        dt = tm.sim_datetime_for_tick(10)
        assert dt is None

    def test_sim_datetime_for_tick_with_base(self):
        """Test datetime conversion with base datetime."""
        tm = TickManager(hours_per_day=8)
        base_dt = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        tm.set_base_datetime(base_dt)

        # Tick 1 = Day 1, 00:00 (tick_of_day=0, minutes=0)
        dt1 = tm.sim_datetime_for_tick(1)
        assert dt1 == base_dt

        # Tick 9 = Day 2, 00:00
        dt9 = tm.sim_datetime_for_tick(9)
        assert dt9 == base_dt + timedelta(days=1)

        # Tick 5 = Day 1, 12:00 (tick_of_day=4, minutes=720)
        dt5 = tm.sim_datetime_for_tick(5)
        expected = base_dt + timedelta(hours=12)
        assert dt5 == expected

    def test_set_base_datetime_none(self):
        """Test setting base datetime to None."""
        tm = TickManager(hours_per_day=8)
        tm.set_base_datetime(None)
        # Should set to current time
        assert tm._sim_base_dt is not None

    def test_calculate_current_week_tick_zero(self):
        """Test calculating week from tick 0."""
        tm = TickManager(hours_per_day=8)
        week = tm.calculate_current_week(0)
        assert week == 1

    def test_calculate_current_week_day_1(self):
        """Test calculating week from day 1."""
        tm = TickManager(hours_per_day=8)
        week = tm.calculate_current_week(8)  # End of day 1
        assert week == 1

    def test_calculate_current_week_day_5(self):
        """Test calculating week from day 5."""
        tm = TickManager(hours_per_day=8)
        week = tm.calculate_current_week(40)  # End of day 5
        assert week == 1

    def test_calculate_current_week_day_6(self):
        """Test calculating week from day 6 (week 2)."""
        tm = TickManager(hours_per_day=8)
        week = tm.calculate_current_week(48)  # Day 6 start
        assert week == 2


class TestWorkHours:
    """Test work hours functionality."""

    def _create_mock_person(self, person_id: int, work_hours: str) -> Any:
        """Create a mock person object."""
        person = Mock()
        person.id = person_id
        person.work_hours = work_hours
        return person

    def test_update_work_windows(self):
        """Test updating work windows cache."""
        tm = TickManager(hours_per_day=8)
        people = [
            self._create_mock_person(1, "09:00-17:00"),
            self._create_mock_person(2, "06:00-14:00"),
            self._create_mock_person(3, "12:00-20:00"),
        ]
        tm.update_work_windows(people)

        assert len(tm._work_hours_ticks) == 3
        # 09:00-17:00 = (3, 6)
        assert tm._work_hours_ticks[1] == (3, 6)
        # 06:00-14:00 = (2, 5)
        assert tm._work_hours_ticks[2] == (2, 5)
        # 12:00-20:00 = (4, 7)
        assert tm._work_hours_ticks[3] == (4, 7)

    def test_update_work_windows_empty_hours(self):
        """Test updating work windows with empty hours."""
        tm = TickManager(hours_per_day=8)
        people = [self._create_mock_person(1, "")]
        tm.update_work_windows(people)

        # Empty hours should default to full day
        assert tm._work_hours_ticks[1] == (0, 8)

    def test_is_within_work_hours_standard_day(self):
        """Test checking work hours for standard day."""
        tm = TickManager(hours_per_day=8)
        person = self._create_mock_person(1, "09:00-17:00")
        tm.update_work_windows([person])

        # 09:00-17:00 = ticks 3-6
        # Tick 1 = 00:00 (before work)
        assert not tm.is_within_work_hours(person, 1)
        # Tick 4 = 12:00 (during work)
        assert tm.is_within_work_hours(person, 4)
        # Tick 7 = 18:00 (after work)
        assert not tm.is_within_work_hours(person, 7)

    def test_is_within_work_hours_no_hours_per_day(self):
        """Test checking work hours with no hours_per_day."""
        tm = TickManager(hours_per_day=0)
        person = self._create_mock_person(1, "09:00-17:00")
        tm.update_work_windows([person])

        # Should always return True when hours_per_day is 0
        assert tm.is_within_work_hours(person, 1)

    def test_is_within_work_hours_no_window_cached(self):
        """Test checking work hours with no cached window."""
        tm = TickManager(hours_per_day=8)
        person = self._create_mock_person(1, "09:00-17:00")
        # Don't update work windows

        # Should return True when no window cached
        assert tm.is_within_work_hours(person, 1)

    def test_is_within_work_hours_multiple_days(self):
        """Test checking work hours across multiple days."""
        tm = TickManager(hours_per_day=8)
        person = self._create_mock_person(1, "09:00-17:00")
        tm.update_work_windows([person])

        # Day 2, tick 12 = (12-1) % 8 = 3 = 09:00 (during work)
        assert tm.is_within_work_hours(person, 12)
        # Day 3, tick 17 = (17-1) % 8 = 0 = 00:00 (before work)
        assert not tm.is_within_work_hours(person, 17)


class MockStateManager:
    """Mock StateManager for testing."""

    def __init__(self):
        self.current_tick = 0
        self.is_running = True
        self.auto_tick = True

    def get_current_state(self):
        """Get mock state."""
        state = Mock()
        state.current_tick = self.current_tick
        state.is_running = self.is_running
        state.auto_tick = self.auto_tick
        return state

    def set_auto_tick(self, enabled: bool):
        """Set auto-tick flag."""
        self.auto_tick = enabled


class TestAutoTick:
    """Test auto-tick threading functionality."""

    def test_start_auto_tick_not_running(self):
        """Test starting auto-tick when not running."""
        tm = TickManager(hours_per_day=8, tick_interval_seconds=0.1)
        state_manager = MockStateManager()
        state_manager.is_running = False

        with pytest.raises(RuntimeError, match="Simulation must be running"):
            tm.start_auto_tick(
                is_running=False,
                advance_callback=Mock(),
                state_manager=state_manager,
                get_active_projects_callback=Mock(return_value=[]),
                archive_chat_room_callback=Mock(),
            )

    def test_start_auto_tick_creates_thread(self):
        """Test that start_auto_tick creates a thread."""
        tm = TickManager(hours_per_day=8, tick_interval_seconds=0.1)
        state_manager = MockStateManager()
        advance_callback = Mock()

        tm.start_auto_tick(
            is_running=True,
            advance_callback=advance_callback,
            state_manager=state_manager,
            get_active_projects_callback=Mock(return_value=[{"project_name": "Test"}]),
            archive_chat_room_callback=Mock(),
        )

        # Thread should be created and alive
        assert tm._auto_tick_thread is not None
        assert tm._auto_tick_thread.is_alive()

        # Cleanup
        tm.stop_auto_tick(state_manager)

    def test_stop_auto_tick_stops_thread(self):
        """Test that stop_auto_tick stops the thread."""
        tm = TickManager(hours_per_day=8, tick_interval_seconds=0.1)
        state_manager = MockStateManager()

        tm.start_auto_tick(
            is_running=True,
            advance_callback=Mock(),
            state_manager=state_manager,
            get_active_projects_callback=Mock(return_value=[{"project_name": "Test"}]),
            archive_chat_room_callback=Mock(),
        )

        # Stop the thread
        tm.stop_auto_tick(state_manager)

        # Thread should be stopped
        assert state_manager.auto_tick is False
        assert tm._auto_tick_thread is None
        assert tm._auto_tick_stop is None

    def test_auto_tick_loop_advances_simulation(self):
        """Test that auto-tick loop advances simulation."""
        tm = TickManager(hours_per_day=8, tick_interval_seconds=0.05)
        state_manager = MockStateManager()
        advance_callback = Mock()

        # Start auto-tick
        tm.start_auto_tick(
            is_running=True,
            advance_callback=advance_callback,
            state_manager=state_manager,
            get_active_projects_callback=Mock(return_value=[{"project_name": "Test"}]),
            archive_chat_room_callback=Mock(),
        )

        # Wait for a few ticks
        time.sleep(0.3)

        # Stop auto-tick
        tm.stop_auto_tick(state_manager)

        # Advance callback should have been called multiple times
        assert advance_callback.call_count >= 2

    def test_auto_tick_loop_stops_when_not_running(self):
        """Test that auto-tick loop stops when simulation is not running."""
        tm = TickManager(hours_per_day=8, tick_interval_seconds=0.05)
        state_manager = MockStateManager()
        advance_callback = Mock()

        tm.start_auto_tick(
            is_running=True,
            advance_callback=advance_callback,
            state_manager=state_manager,
            get_active_projects_callback=Mock(return_value=[{"project_name": "Test"}]),
            archive_chat_room_callback=Mock(),
        )

        # Wait a bit
        time.sleep(0.1)

        # Stop simulation
        state_manager.is_running = False

        # Wait for thread to exit
        time.sleep(0.2)

        # Thread should have exited
        assert not tm._auto_tick_thread.is_alive()

    def test_auto_tick_loop_stops_when_auto_tick_disabled(self):
        """Test that auto-tick loop stops when auto_tick is disabled."""
        tm = TickManager(hours_per_day=8, tick_interval_seconds=0.05)
        state_manager = MockStateManager()
        advance_callback = Mock()

        tm.start_auto_tick(
            is_running=True,
            advance_callback=advance_callback,
            state_manager=state_manager,
            get_active_projects_callback=Mock(return_value=[{"project_name": "Test"}]),
            archive_chat_room_callback=Mock(),
        )

        # Wait a bit
        time.sleep(0.1)

        # Disable auto-tick
        state_manager.auto_tick = False

        # Wait for thread to exit
        time.sleep(0.2)

        # Thread should have exited
        assert not tm._auto_tick_thread.is_alive()

    def test_auto_tick_handles_advance_failure(self):
        """Test that auto-tick handles advance callback failures."""
        tm = TickManager(hours_per_day=8, tick_interval_seconds=0.05)
        state_manager = MockStateManager()

        # Create advance callback that fails
        advance_callback = Mock(side_effect=RuntimeError("Advance failed"))

        tm.start_auto_tick(
            is_running=True,
            advance_callback=advance_callback,
            state_manager=state_manager,
            get_active_projects_callback=Mock(return_value=[{"project_name": "Test"}]),
            archive_chat_room_callback=Mock(),
        )

        # Wait for thread to handle error and exit
        time.sleep(0.2)

        # Thread should have stopped and auto_tick disabled
        assert not tm._auto_tick_thread.is_alive()
        assert state_manager.auto_tick is False

    def test_get_advance_lock(self):
        """Test getting advance lock."""
        tm = TickManager(hours_per_day=8)
        lock = tm.get_advance_lock()
        assert lock is tm._advance_lock
        # Verify it's actually a lock by trying to acquire/release
        acquired = lock.acquire(blocking=False)
        assert acquired is True
        lock.release()


class TestTickManagerEdgeCases:
    """Test edge cases and error conditions."""

    def test_hours_per_day_zero(self):
        """Test with hours_per_day = 0."""
        tm = TickManager(hours_per_day=0)
        # Should handle gracefully with max(1, hours_per_day)
        formatted = tm.format_sim_time(5)
        assert "Day" in formatted

    def test_negative_tick_interval(self):
        """Test with negative tick interval."""
        # Should accept but may cause issues in threading
        tm = TickManager(hours_per_day=8, tick_interval_seconds=-1.0)
        assert tm._tick_interval_seconds == -1.0

    def test_large_tick_number(self):
        """Test with very large tick number."""
        tm = TickManager(hours_per_day=8)
        formatted = tm.format_sim_time(10000)
        assert "Day" in formatted
        # Day 1250 (10000/8 = 1250)
        assert "Day 1250" in formatted

    def test_parse_work_hours_same_start_end(self):
        """Test parsing work hours with same start and end."""
        tm = TickManager(hours_per_day=8)
        # If start_tick == end_tick, should return full day
        start_tick, end_tick = tm.parse_work_hours_to_ticks("09:00-09:00")
        assert start_tick == 0
        assert end_tick == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
