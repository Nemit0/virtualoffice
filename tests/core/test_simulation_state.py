"""
Tests for SimulationState module.

Tests state management, database operations, status overrides, and migrations.
"""

import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from virtualoffice.sim_manager.core import SimulationState, SimulationStatus, SIM_SCHEMA


@contextmanager
def get_test_connection(db_path):
    """Get a connection to the test database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()  # Commit changes on success
    except Exception:
        conn.rollback()  # Rollback on error
        raise
    finally:
        conn.close()


@pytest.fixture
def isolated_db(monkeypatch):
    """Create an isolated test database for each test."""
    # Create temp database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)  # Close file descriptor immediately

    # Patch get_connection and execute_script in both locations
    import virtualoffice.common.db as db_module
    import virtualoffice.sim_manager.core.simulation_state as sim_state_module

    def test_get_connection():
        """Return context manager for test database connection."""
        # Return the context manager itself, not call it
        return get_test_connection(db_path)

    def test_execute_script(script: str):
        """Execute SQL script on test database."""
        with get_test_connection(db_path) as conn:
            conn.executescript(script)
            conn.commit()

    # Apply monkeypatch to both modules
    monkeypatch.setattr(db_module, "get_connection", test_get_connection)
    monkeypatch.setattr(db_module, "execute_script", test_execute_script)
    monkeypatch.setattr(sim_state_module, "get_connection", test_get_connection)
    monkeypatch.setattr(sim_state_module, "execute_script", test_execute_script)
    monkeypatch.setenv("VDOS_DB_PATH", db_path)

    yield db_path

    # Cleanup
    try:
        # Give Windows time to release file locks
        time.sleep(0.05)
        if os.path.exists(db_path):
            os.remove(db_path)
    except (PermissionError, OSError):
        # File is still locked on Windows, will be cleaned up eventually
        pass


class TestSimulationStateInitialization:
    """Test database initialization and setup."""

    def test_initialize_database(self, isolated_db):
        """Test that database schema is created correctly."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Verify tables exist
        with get_test_connection(isolated_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            'people', 'schedule_blocks', 'simulation_state', 'tick_log',
            'events', 'project_plans', 'project_assignments', 'project_chat_rooms',
            'worker_plans', 'hourly_summaries', 'daily_reports', 'simulation_reports',
            'worker_runtime_messages', 'worker_exchange_log', 'worker_status_overrides'
        }

        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

    def test_ensure_state_row(self, isolated_db):
        """Test that simulation_state row is created."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        with get_test_connection(isolated_db) as conn:
            row = conn.execute("SELECT * FROM simulation_state WHERE id = 1").fetchone()

        assert row is not None
        assert row["current_tick"] == 0
        assert row["is_running"] == 0
        assert row["auto_tick"] == 0

    def test_multiple_initializations_safe(self, isolated_db):
        """Test that multiple initializations don't break the database."""
        state = SimulationState(isolated_db)
        state.initialize_database()
        state.initialize_database()  # Should not raise error

        status = state.get_current_state()
        assert status.current_tick == 0


class TestSimulationStateManagement:
    """Test simulation state operations."""

    def test_get_current_state(self, isolated_db):
        """Test getting current simulation state."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        status = state.get_current_state()

        assert isinstance(status, SimulationStatus)
        assert status.current_tick == 0
        assert status.is_running is False
        assert status.auto_tick is False

    def test_update_tick(self, isolated_db):
        """Test updating simulation tick."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        state.update_tick(10, "test advancement")
        status = state.get_current_state()

        assert status.current_tick == 10

        # Verify tick log
        with get_test_connection(isolated_db) as conn:
            log = conn.execute(
                "SELECT * FROM tick_log WHERE tick = ? AND reason = ?",
                (10, "test advancement")
            ).fetchone()

        assert log is not None
        assert log["tick"] == 10
        assert log["reason"] == "test advancement"

    def test_set_running(self, isolated_db):
        """Test setting running state."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Set to running
        state.set_running(True)
        status = state.get_current_state()
        assert status.is_running is True

        # Set to stopped
        state.set_running(False)
        status = state.get_current_state()
        assert status.is_running is False

    def test_set_auto_tick(self, isolated_db):
        """Test setting auto-tick mode."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Enable auto-tick
        state.set_auto_tick(True)
        status = state.get_current_state()
        assert status.auto_tick is True

        # Disable auto-tick
        state.set_auto_tick(False)
        status = state.get_current_state()
        assert status.auto_tick is False


class TestStatusOverrides:
    """Test worker status override functionality."""

    def _create_test_person(self, db_path, name="Test Worker", email="test@example.com", handle="test"):
        """Helper to create a test person in the database."""
        with get_test_connection(db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO people (name, role, timezone, work_hours, break_frequency,
                   communication_style, email_address, chat_handle, skills, personality,
                   objectives, metrics, persona_markdown, planning_guidelines, event_playbook,
                   statuses) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, "Developer", "UTC", "09:00-17:00", "2h", "professional",
                 email, handle, "[]", "[]", "[]", "[]", "Test persona",
                 "[]", "{}", "[]")
            )
            conn.commit()
            return cursor.lastrowid

    def test_set_status_override(self, isolated_db):
        """Test setting a status override."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Create a test person
        worker_id = self._create_test_person(isolated_db)

        # Set status override
        state.set_status_override(worker_id, "out_sick", 100, "Illness")

        # Verify in memory
        overrides = state.get_status_overrides()
        assert worker_id in overrides
        assert overrides[worker_id] == ("out_sick", 100)

        # Verify in database
        with get_test_connection(isolated_db) as conn:
            row = conn.execute(
                "SELECT * FROM worker_status_overrides WHERE worker_id = ?",
                (worker_id,)
            ).fetchone()

        assert row is not None
        assert row["status"] == "out_sick"
        assert row["until_tick"] == 100
        assert row["reason"] == "Illness"

    def test_clear_status_override(self, isolated_db):
        """Test clearing a status override."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Create test person and override
        worker_id = self._create_test_person(isolated_db)
        state.set_status_override(worker_id, "out_sick", 100, "Illness")

        # Clear it
        state.clear_status_override(worker_id)

        # Verify cleared from memory
        overrides = state.get_status_overrides()
        assert worker_id not in overrides

        # Verify cleared from database
        with get_test_connection(isolated_db) as conn:
            row = conn.execute(
                "SELECT * FROM worker_status_overrides WHERE worker_id = ?",
                (worker_id,)
            ).fetchone()

        assert row is None

    def test_clear_expired_status_overrides(self, isolated_db):
        """Test clearing expired status overrides."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Create test people
        worker1_id = self._create_test_person(isolated_db, "Worker 1", "worker1@example.com", "worker1")
        worker2_id = self._create_test_person(isolated_db, "Worker 2", "worker2@example.com", "worker2")

        # Set overrides with different expiration times
        state.set_status_override(worker1_id, "out_sick", 50, "Illness")  # Expires at 50
        state.set_status_override(worker2_id, "on_vacation", 150, "Vacation")  # Expires at 150

        # Clear expired at tick 100 (should clear worker1 but not worker2)
        expired = state.clear_expired_status_overrides(100)

        assert worker1_id in expired
        assert worker2_id not in expired

        overrides = state.get_status_overrides()
        assert worker1_id not in overrides
        assert worker2_id in overrides

    def test_clear_all_status_overrides(self, isolated_db):
        """Test clearing all status overrides."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Create test people and overrides
        worker1_id = self._create_test_person(isolated_db, "Worker 1", "worker1@example.com", "worker1")
        worker2_id = self._create_test_person(isolated_db, "Worker 2", "worker2@example.com", "worker2")

        state.set_status_override(worker1_id, "out_sick", 100, "Illness")
        state.set_status_override(worker2_id, "on_vacation", 150, "Vacation")

        # Clear all
        state.clear_all_status_overrides()

        overrides = state.get_status_overrides()
        assert len(overrides) == 0

        # Verify database is empty
        with get_test_connection(isolated_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM worker_status_overrides").fetchone()[0]
        assert count == 0


class TestDatabaseMigrations:
    """Test database migration functionality."""

    def test_apply_migrations(self, isolated_db):
        """Test that migrations are applied correctly."""
        # Create database with old schema (missing columns)
        with get_test_connection(isolated_db) as conn:
            conn.execute("""
                CREATE TABLE people (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    work_hours TEXT NOT NULL,
                    break_frequency TEXT NOT NULL,
                    communication_style TEXT NOT NULL,
                    email_address TEXT NOT NULL,
                    chat_handle TEXT NOT NULL,
                    skills TEXT NOT NULL,
                    personality TEXT NOT NULL,
                    objectives TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    persona_markdown TEXT NOT NULL,
                    planning_guidelines TEXT NOT NULL,
                    event_playbook TEXT NOT NULL,
                    statuses TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE simulation_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    current_tick INTEGER NOT NULL,
                    is_running INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE project_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT NOT NULL,
                    project_summary TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    generated_by INTEGER,
                    duration_weeks INTEGER NOT NULL,
                    model_used TEXT NOT NULL,
                    tokens_used INTEGER
                )
            """)
            conn.commit()

        # Apply migrations
        state = SimulationState(isolated_db)
        state.apply_migrations()

        # Verify new columns exist
        with get_test_connection(isolated_db) as conn:
            people_cols = {row["name"] for row in conn.execute("PRAGMA table_info(people)")}
            state_cols = {row["name"] for row in conn.execute("PRAGMA table_info(simulation_state)")}
            project_cols = {row["name"] for row in conn.execute("PRAGMA table_info(project_plans)")}

        assert "is_department_head" in people_cols
        assert "team_name" in people_cols
        assert "auto_tick" in state_cols
        assert "start_week" in project_cols


class TestResetSimulation:
    """Test simulation reset functionality."""

    def test_reset_simulation(self, isolated_db):
        """Test that reset clears simulation data but preserves personas."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Create test data
        with get_test_connection(isolated_db) as conn:
            # Add a person
            cursor = conn.execute(
                """INSERT INTO people (name, role, timezone, work_hours, break_frequency,
                   communication_style, email_address, chat_handle, skills, personality,
                   objectives, metrics, persona_markdown, planning_guidelines, event_playbook,
                   statuses) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("Test Worker", "Developer", "UTC", "09:00-17:00", "2h", "professional",
                 "test@example.com", "test", "[]", "[]", "[]", "[]", "Test persona",
                 "[]", "{}", "[]")
            )
            person_id = cursor.lastrowid

            # Add simulation data
            conn.execute("INSERT INTO tick_log(tick, reason) VALUES (?, ?)", (10, "test"))
            conn.execute("INSERT INTO events(type, target_ids) VALUES (?, ?)", ("test_event", f"[{person_id}]"))
            conn.commit()

        # Advance state
        state.update_tick(50, "test")
        state.set_running(True)
        state.set_auto_tick(True)

        # Reset
        state.reset_simulation()

        # Verify state is reset
        status = state.get_current_state()
        assert status.current_tick == 0
        assert status.is_running is False
        assert status.auto_tick is False

        # Verify simulation data cleared
        with get_test_connection(isolated_db) as conn:
            tick_count = conn.execute("SELECT COUNT(*) FROM tick_log").fetchone()[0]
            event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

        assert tick_count == 0
        assert event_count == 0

        # Verify person preserved
        with get_test_connection(isolated_db) as conn:
            person_count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]

        assert person_count == 1


class TestSimulationStateEdgeCases:
    """Test edge cases and error conditions."""

    def test_get_status_overrides_returns_copy(self, isolated_db):
        """Test that get_status_overrides returns a copy, not the internal dict."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Get overrides
        overrides1 = state.get_status_overrides()
        overrides1[999] = ("fake", 100)  # Modify the returned dict

        # Get again - should not be affected
        overrides2 = state.get_status_overrides()
        assert 999 not in overrides2

    def test_clear_nonexistent_override(self, isolated_db):
        """Test clearing a nonexistent override doesn't raise error."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        # Should not raise error
        state.clear_status_override(99999)

    def test_clear_expired_with_no_overrides(self, isolated_db):
        """Test clearing expired overrides when there are none."""
        state = SimulationState(isolated_db)
        state.initialize_database()

        expired = state.clear_expired_status_overrides(100)
        assert expired == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
