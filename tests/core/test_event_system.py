"""
Tests for EventSystem module.

Tests event injection, processing, random event generation,
event-to-adjustment conversion, and project-specific filtering.
"""

import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from unittest.mock import Mock, MagicMock, call

import pytest

from virtualoffice.sim_manager.core.event_system import EventSystem, InboundMessage
from virtualoffice.sim_manager.schemas import EventCreate, PersonRead


@contextmanager
def get_test_connection(db_path):
    """Get a connection to the test database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@pytest.fixture
def isolated_db(monkeypatch):
    """Create an isolated test database for each test."""
    # Create temp database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Create events table
    with get_test_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                target_ids TEXT NOT NULL,
                project_id TEXT,
                at_tick INTEGER,
                payload TEXT
            )
        """)
        conn.commit()

    # Patch get_connection
    import virtualoffice.common.db as db_module
    import virtualoffice.sim_manager.core.event_system as event_system_module

    def test_get_connection():
        return get_test_connection(db_path)

    monkeypatch.setattr(db_module, "get_connection", test_get_connection)
    monkeypatch.setattr(event_system_module, "get_connection", test_get_connection)
    monkeypatch.setenv("VDOS_DB_PATH", db_path)
    monkeypatch.setenv("VDOS_LOCALE", "en")  # Set English locale for tests

    yield db_path

    # Cleanup
    try:
        time.sleep(0.05)
        if os.path.exists(db_path):
            os.remove(db_path)
    except (PermissionError, OSError):
        pass


def create_mock_person(
    person_id: int,
    name: str = "Test Worker",
    email: str = "test@example.com",
    handle: str = "test",
    is_department_head: bool = False
) -> PersonRead:
    """Create a mock PersonRead object."""
    return PersonRead(
        id=person_id,
        name=name,
        role="Developer",
        timezone="UTC",
        work_hours="09:00-17:00",
        break_frequency="50/10 cadence",
        communication_style="professional",
        email_address=email,
        chat_handle=handle,
        is_department_head=is_department_head,
        skills=["Python"],
        personality=["Focused"],
        persona_markdown=f"# {name}\nTest persona"
    )


class TestEventInjection:
    """Test event injection functionality."""

    def test_inject_simple_event(self, isolated_db):
        """Test injecting a simple event."""
        event_system = EventSystem()
        
        event = EventCreate(
            type="test_event",
            target_ids=[1, 2],
            at_tick=10,
            payload={"message": "test"}
        )
        
        result = event_system.inject_event(event)
        
        assert result["id"] == 1
        assert result["type"] == "test_event"
        assert result["target_ids"] == [1, 2]
        assert result["at_tick"] == 10
        assert result["payload"] == {"message": "test"}
        assert result["project_id"] is None

    def test_inject_event_with_project(self, isolated_db):
        """Test injecting an event with project ID."""
        event_system = EventSystem()
        
        event = EventCreate(
            type="client_request",
            target_ids=[1],
            project_id="alpha",
            at_tick=20,
            payload={"feature": "new dashboard"}
        )
        
        result = event_system.inject_event(event)
        
        assert result["project_id"] == "alpha"
        assert result["payload"]["feature"] == "new dashboard"

    def test_inject_event_without_payload(self, isolated_db):
        """Test injecting an event without payload."""
        event_system = EventSystem()
        
        event = EventCreate(
            type="meeting",
            target_ids=[1, 2, 3],
            at_tick=30
        )
        
        result = event_system.inject_event(event)
        
        assert result["payload"] == {}

    def test_inject_multiple_events(self, isolated_db):
        """Test injecting multiple events."""
        event_system = EventSystem()
        
        event1 = EventCreate(type="event1", target_ids=[1], at_tick=10)
        event2 = EventCreate(type="event2", target_ids=[2], at_tick=20)
        event3 = EventCreate(type="event3", target_ids=[3], at_tick=30)
        
        result1 = event_system.inject_event(event1)
        result2 = event_system.inject_event(event2)
        result3 = event_system.inject_event(event3)
        
        assert result1["id"] == 1
        assert result2["id"] == 2
        assert result3["id"] == 3

    def test_inject_event_persists_to_database(self, isolated_db):
        """Test that injected events are persisted to database."""
        event_system = EventSystem()
        
        event = EventCreate(
            type="blocker",
            target_ids=[1],
            at_tick=15,
            payload={"description": "API down"}
        )
        
        event_system.inject_event(event)
        
        # Verify in database
        with get_test_connection(isolated_db) as conn:
            row = conn.execute("SELECT * FROM events WHERE id = 1").fetchone()
        
        assert row is not None
        assert row["type"] == "blocker"
        assert json.loads(row["target_ids"]) == [1]
        assert row["at_tick"] == 15
        assert json.loads(row["payload"])["description"] == "API down"


class TestEventListing:
    """Test event listing and filtering."""

    def test_list_all_events(self, isolated_db):
        """Test listing all events."""
        event_system = EventSystem()
        
        # Inject multiple events
        event_system.inject_event(EventCreate(type="event1", target_ids=[1], at_tick=10))
        event_system.inject_event(EventCreate(type="event2", target_ids=[2], at_tick=20))
        event_system.inject_event(EventCreate(type="event3", target_ids=[3], at_tick=30))
        
        events = event_system.list_events()
        
        assert len(events) == 3
        assert events[0]["type"] == "event1"
        assert events[1]["type"] == "event2"
        assert events[2]["type"] == "event3"

    def test_list_events_by_project(self, isolated_db):
        """Test filtering events by project ID."""
        event_system = EventSystem()
        
        event_system.inject_event(EventCreate(
            type="event1", target_ids=[1], project_id="alpha", at_tick=10
        ))
        event_system.inject_event(EventCreate(
            type="event2", target_ids=[2], project_id="beta", at_tick=20
        ))
        event_system.inject_event(EventCreate(
            type="event3", target_ids=[3], project_id="alpha", at_tick=30
        ))
        
        alpha_events = event_system.list_events(project_id="alpha")
        
        assert len(alpha_events) == 2
        assert all(e["project_id"] == "alpha" for e in alpha_events)
        assert alpha_events[0]["type"] == "event1"
        assert alpha_events[1]["type"] == "event3"

    def test_list_events_by_target(self, isolated_db):
        """Test filtering events by target person ID."""
        event_system = EventSystem()
        
        event_system.inject_event(EventCreate(type="event1", target_ids=[1, 2], at_tick=10))
        event_system.inject_event(EventCreate(type="event2", target_ids=[2, 3], at_tick=20))
        event_system.inject_event(EventCreate(type="event3", target_ids=[3, 4], at_tick=30))
        
        person2_events = event_system.list_events(target_id=2)
        
        assert len(person2_events) == 2
        assert all(2 in e["target_ids"] for e in person2_events)

    def test_list_events_by_project_and_target(self, isolated_db):
        """Test filtering events by both project and target."""
        event_system = EventSystem()
        
        event_system.inject_event(EventCreate(
            type="event1", target_ids=[1], project_id="alpha", at_tick=10
        ))
        event_system.inject_event(EventCreate(
            type="event2", target_ids=[1, 2], project_id="beta", at_tick=20
        ))
        event_system.inject_event(EventCreate(
            type="event3", target_ids=[1], project_id="alpha", at_tick=30
        ))
        
        filtered_events = event_system.list_events(project_id="alpha", target_id=1)
        
        assert len(filtered_events) == 2
        assert all(e["project_id"] == "alpha" and 1 in e["target_ids"] for e in filtered_events)

    def test_list_events_empty_database(self, isolated_db):
        """Test listing events from empty database."""
        event_system = EventSystem()
        
        events = event_system.list_events()
        
        assert events == []

    def test_list_events_no_matches(self, isolated_db):
        """Test listing events with no matches."""
        event_system = EventSystem()
        
        event_system.inject_event(EventCreate(type="event1", target_ids=[1], at_tick=10))
        
        events = event_system.list_events(project_id="nonexistent")
        
        assert events == []


class TestRandomEventGeneration:
    """Test random event generation."""

    def test_random_event_generation_with_seed(self, isolated_db):
        """Test that random events are deterministic with seed."""
        event_system1 = EventSystem(random_seed=42)
        event_system2 = EventSystem(random_seed=42)
        
        people = [create_mock_person(i, f"Worker {i}") for i in range(1, 4)]
        
        # Mock dependencies
        mock_email_gateway = Mock()
        mock_chat_gateway = Mock()
        mock_queue_message = Mock()
        mock_log_exchange = Mock()
        mock_set_status = Mock()
        
        # Process events at same tick with both systems
        # Use tick 10 which triggers sick leave check
        result1, _ = event_system1.process_events_for_tick(
            tick=10,
            people=people,
            hours_per_day=8,
            status_overrides={},
            email_gateway=mock_email_gateway,
            chat_gateway=mock_chat_gateway,
            sim_manager_email="sim@test.local",
            queue_message_callback=mock_queue_message,
            log_exchange_callback=mock_log_exchange,
            set_status_override_callback=mock_set_status,
        )
        
        result2, _ = event_system2.process_events_for_tick(
            tick=10,
            people=people,
            hours_per_day=8,
            status_overrides={},
            email_gateway=mock_email_gateway,
            chat_gateway=mock_chat_gateway,
            sim_manager_email="sim@test.local",
            queue_message_callback=mock_queue_message,
            log_exchange_callback=mock_log_exchange,
            set_status_override_callback=mock_set_status,
        )
        
        # Results should be identical
        assert result1 == result2

    def test_sick_leave_event_generation(self, isolated_db, monkeypatch):
        """Test sick leave event generation."""
        # Force sick leave to trigger
        event_system = EventSystem(random_seed=1)
        
        # Mock random to always trigger sick leave
        mock_random = Mock()
        mock_random.random = Mock(return_value=0.01)  # Below 0.05 threshold
        # Make Worker 2 get sick (not the department head)
        mock_random.choice = Mock(side_effect=lambda x: x[1] if len(x) > 1 else x[0])
        event_system._random = mock_random
        
        people = [
            create_mock_person(1, "Manager", "manager@test.local", "manager", is_department_head=True),
            create_mock_person(2, "Worker", "worker@test.local", "worker"),
        ]
        
        mock_email_gateway = Mock()
        mock_queue_message = Mock()
        mock_log_exchange = Mock()
        mock_set_status = Mock()
        
        # Tick 10 = mid-morning (sick leave check time)
        # tick_of_day = (10-1) % 8 = 9 % 8 = 1
        # Sick leave check happens when tick_of_day == int(60 * 8 / 480) = 1
        adjustments, immediate = event_system.process_events_for_tick(
            tick=10,
            people=people,
            hours_per_day=8,
            status_overrides={},
            email_gateway=mock_email_gateway,
            chat_gateway=Mock(),
            sim_manager_email="sim@test.local",
            queue_message_callback=mock_queue_message,
            log_exchange_callback=mock_log_exchange,
            set_status_override_callback=mock_set_status,
        )
        
        # Should set status override for sick worker (Worker 2)
        mock_set_status.assert_called()
        call_args = mock_set_status.call_args[0]
        assert call_args[0] == 2  # Worker 2's ID
        assert call_args[1] == 'SickLeave'
        assert call_args[2] == 18  # tick + hours_per_day
        
        # Should have adjustments for both workers (sick worker + department head)
        assert len(adjustments) == 2
        assert 2 in adjustments  # Worker 2 (sick)
        assert 1 in adjustments  # Manager (department head)
        
        # Should queue messages for both
        assert mock_queue_message.call_count >= 2
        
        # Should send email to department head
        mock_email_gateway.send_email.assert_called_once()

    def test_client_feature_request_generation(self, isolated_db):
        """Test client feature request generation."""
        event_system = EventSystem(random_seed=2)
        
        # Mock random to trigger feature request
        mock_random = Mock()
        mock_random.random = Mock(return_value=0.05)  # Below 0.10 threshold
        mock_random.choice = Mock(side_effect=lambda x: x[0])
        event_system._random = mock_random
        
        people = [
            create_mock_person(1, "Manager", is_department_head=True),
            create_mock_person(2, "Developer"),
        ]
        
        mock_queue_message = Mock()
        
        # Tick at interval boundary
        # interval_ticks = int(120 * 8 / 480) = 2
        # tick_of_day must be divisible by 2
        # tick=3: tick_of_day = (3-1) % 8 = 2 ✓
        adjustments, immediate = event_system.process_events_for_tick(
            tick=3,
            people=people,
            hours_per_day=8,
            status_overrides={},
            email_gateway=Mock(),
            chat_gateway=Mock(),
            sim_manager_email="sim@test.local",
            queue_message_callback=mock_queue_message,
            log_exchange_callback=Mock(),
            set_status_override_callback=Mock(),
        )
        
        # Should have adjustments for manager and collaborator
        assert len(adjustments) >= 1
        
        # Should queue messages
        assert mock_queue_message.call_count >= 1

    def test_no_events_generated_empty_people(self, isolated_db):
        """Test that no events are generated with empty people list."""
        event_system = EventSystem()
        
        # Use tick 10 which would normally trigger sick leave check
        adjustments, immediate = event_system.process_events_for_tick(
            tick=10,
            people=[],
            hours_per_day=8,
            status_overrides={},
            email_gateway=Mock(),
            chat_gateway=Mock(),
            sim_manager_email="sim@test.local",
            queue_message_callback=Mock(),
            log_exchange_callback=Mock(),
            set_status_override_callback=Mock(),
        )
        
        assert adjustments == {}
        assert immediate == {}

    def test_sick_leave_respects_existing_overrides(self, isolated_db):
        """Test that sick leave doesn't affect already sick workers."""
        event_system = EventSystem(random_seed=3)
        
        # Mock random to trigger sick leave
        mock_random = Mock()
        mock_random.random = Mock(return_value=0.01)
        mock_random.choice = Mock(side_effect=lambda x: x[0])
        event_system._random = mock_random
        
        people = [
            create_mock_person(1, "Worker 1"),
            create_mock_person(2, "Worker 2"),
        ]
        
        # Worker 1 already on sick leave
        status_overrides = {1: ('SickLeave', 100)}
        
        mock_set_status = Mock()
        
        # Use tick 10 which triggers sick leave check
        event_system.process_events_for_tick(
            tick=10,
            people=people,
            hours_per_day=8,
            status_overrides=status_overrides,
            email_gateway=Mock(),
            chat_gateway=Mock(),
            sim_manager_email="sim@test.local",
            queue_message_callback=Mock(),
            log_exchange_callback=Mock(),
            set_status_override_callback=mock_set_status,
        )
        
        # Should only affect Worker 2 (not already sick)
        if mock_set_status.called:
            call_args = mock_set_status.call_args[0]
            assert call_args[0] == 2  # Worker 2's ID


class TestEventToAdjustmentConversion:
    """Test event-to-adjustment conversion."""

    def test_convert_sick_leave_event(self, isolated_db):
        """Test converting sick leave event to adjustments."""
        event_system = EventSystem()
        
        event = {
            "type": "sick_leave",
            "payload": {}
        }
        
        person = create_mock_person(1)
        adjustments = event_system.convert_event_to_adjustments(event, person)
        
        assert len(adjustments) == 1
        assert "Rest and reschedule tasks" in adjustments[0]

    def test_convert_client_feature_request_event(self, isolated_db):
        """Test converting client feature request to adjustments."""
        event_system = EventSystem()
        
        event = {
            "type": "client_feature_request",
            "payload": {"feature": "dark mode"}
        }
        
        person = create_mock_person(1)
        adjustments = event_system.convert_event_to_adjustments(event, person)
        
        assert len(adjustments) == 1
        assert "dark mode" in adjustments[0]
        assert "client request" in adjustments[0]

    def test_convert_blocker_event(self, isolated_db):
        """Test converting blocker event to adjustments."""
        event_system = EventSystem()
        
        event = {
            "type": "blocker",
            "payload": {"description": "API rate limit"}
        }
        
        person = create_mock_person(1)
        adjustments = event_system.convert_event_to_adjustments(event, person)
        
        assert len(adjustments) == 1
        assert "blocker" in adjustments[0].lower()
        assert "API rate limit" in adjustments[0]

    def test_convert_meeting_event(self, isolated_db):
        """Test converting meeting event to adjustments."""
        event_system = EventSystem()
        
        event = {
            "type": "meeting",
            "payload": {"topic": "sprint planning"}
        }
        
        person = create_mock_person(1)
        adjustments = event_system.convert_event_to_adjustments(event, person)
        
        assert len(adjustments) == 1
        assert "meeting" in adjustments[0].lower()
        assert "sprint planning" in adjustments[0]

    def test_convert_unknown_event_type(self, isolated_db):
        """Test converting unknown event type returns empty list."""
        event_system = EventSystem()
        
        event = {
            "type": "unknown_event",
            "payload": {}
        }
        
        person = create_mock_person(1)
        adjustments = event_system.convert_event_to_adjustments(event, person)
        
        assert adjustments == []

    def test_convert_event_with_missing_payload_fields(self, isolated_db):
        """Test converting event with missing payload fields uses defaults."""
        event_system = EventSystem()
        
        event = {
            "type": "client_feature_request",
            "payload": {}  # Missing 'feature' field
        }
        
        person = create_mock_person(1)
        adjustments = event_system.convert_event_to_adjustments(event, person)
        
        assert len(adjustments) == 1
        assert "new feature" in adjustments[0]  # Default value


class TestInboundMessage:
    """Test InboundMessage dataclass."""

    def test_inbound_message_creation(self):
        """Test creating an InboundMessage."""
        msg = InboundMessage(
            sender_id=1,
            sender_name="Manager",
            subject="Task Update",
            summary="Please review the PR",
            action_item="Review PR #123",
            message_type="email",
            channel="email",
            tick=50,
            message_id=100
        )
        
        assert msg.sender_id == 1
        assert msg.sender_name == "Manager"
        assert msg.subject == "Task Update"
        assert msg.summary == "Please review the PR"
        assert msg.action_item == "Review PR #123"
        assert msg.message_type == "email"
        assert msg.channel == "email"
        assert msg.tick == 50
        assert msg.message_id == 100

    def test_inbound_message_optional_message_id(self):
        """Test InboundMessage with optional message_id."""
        msg = InboundMessage(
            sender_id=0,
            sender_name="System",
            subject="Event",
            summary="Event occurred",
            action_item=None,
            message_type="event",
            channel="system",
            tick=10
        )
        
        assert msg.message_id is None
        assert msg.action_item is None


class TestEventSystemIntegration:
    """Test EventSystem integration scenarios."""

    def test_full_event_lifecycle(self, isolated_db):
        """Test complete event lifecycle: inject, list, process."""
        event_system = EventSystem()
        
        # 1. Inject event
        event = EventCreate(
            type="blocker",
            target_ids=[1],
            project_id="alpha",
            at_tick=50,
            payload={"description": "Database migration"}
        )
        
        injected = event_system.inject_event(event)
        assert injected["id"] == 1
        
        # 2. List events
        events = event_system.list_events(project_id="alpha")
        assert len(events) == 1
        assert events[0]["type"] == "blocker"
        
        # 3. Convert to adjustments
        person = create_mock_person(1)
        adjustments = event_system.convert_event_to_adjustments(events[0], person)
        assert len(adjustments) == 1
        assert "Database migration" in adjustments[0]

    def test_multiple_projects_event_isolation(self, isolated_db):
        """Test that events are properly isolated by project."""
        event_system = EventSystem()
        
        # Inject events for different projects
        event_system.inject_event(EventCreate(
            type="event1", target_ids=[1], project_id="alpha", at_tick=10
        ))
        event_system.inject_event(EventCreate(
            type="event2", target_ids=[2], project_id="beta", at_tick=20
        ))
        event_system.inject_event(EventCreate(
            type="event3", target_ids=[1], project_id="alpha", at_tick=30
        ))
        
        # Verify isolation
        alpha_events = event_system.list_events(project_id="alpha")
        beta_events = event_system.list_events(project_id="beta")
        
        assert len(alpha_events) == 2
        assert len(beta_events) == 1
        assert all(e["project_id"] == "alpha" for e in alpha_events)
        assert all(e["project_id"] == "beta" for e in beta_events)

    def test_event_processing_with_department_head(self, isolated_db):
        """Test event processing correctly identifies department head."""
        event_system = EventSystem(random_seed=10)
        
        # Mock random to trigger sick leave
        mock_random = Mock()
        mock_random.random = Mock(return_value=0.01)
        # Return Worker (not Manager) to get sick
        worker_person = create_mock_person(2, "Worker", "worker@test.local", "worker")
        mock_random.choice = Mock(return_value=worker_person)
        event_system._random = mock_random
        
        people = [
            create_mock_person(1, "Manager", "manager@test.local", "manager", is_department_head=True),
            worker_person,
        ]
        
        mock_email_gateway = Mock()
        mock_queue_message = Mock()
        
        # Use tick 10 which triggers sick leave check
        event_system.process_events_for_tick(
            tick=10,
            people=people,
            hours_per_day=8,
            status_overrides={},
            email_gateway=mock_email_gateway,
            chat_gateway=Mock(),
            sim_manager_email="sim@test.local",
            queue_message_callback=mock_queue_message,
            log_exchange_callback=Mock(),
            set_status_override_callback=Mock(),
        )
        
        # Should send email to department head
        assert mock_email_gateway.send_email.called
        call_kwargs = mock_email_gateway.send_email.call_args[1]
        # Department head's email should be in recipients
        assert "manager@test.local" in call_kwargs["to"]


class TestEventSystemEdgeCases:
    """Test edge cases and error conditions."""

    def test_event_system_with_none_seed(self, isolated_db):
        """Test EventSystem with None seed (non-deterministic)."""
        event_system = EventSystem(random_seed=None)
        assert event_system._random is not None

    def test_inject_event_with_empty_target_ids(self, isolated_db):
        """Test injecting event with empty target IDs."""
        event_system = EventSystem()
        
        event = EventCreate(
            type="broadcast",
            target_ids=[],
            at_tick=10
        )
        
        result = event_system.inject_event(event)
        assert result["target_ids"] == []

    def test_process_events_with_zero_hours_per_day(self, isolated_db):
        """Test processing events with zero hours_per_day."""
        event_system = EventSystem()
        
        people = [create_mock_person(1)]
        
        # Use tick 10
        adjustments, immediate = event_system.process_events_for_tick(
            tick=10,
            people=people,
            hours_per_day=0,  # Edge case
            status_overrides={},
            email_gateway=Mock(),
            chat_gateway=Mock(),
            sim_manager_email="sim@test.local",
            queue_message_callback=Mock(),
            log_exchange_callback=Mock(),
            set_status_override_callback=Mock(),
        )
        
        # Should handle gracefully
        assert isinstance(adjustments, dict)
        assert isinstance(immediate, dict)

    def test_list_events_with_special_characters_in_project_id(self, isolated_db):
        """Test listing events with special characters in project ID."""
        event_system = EventSystem()
        
        event_system.inject_event(EventCreate(
            type="event1",
            target_ids=[1],
            project_id="project-with-dashes_and_underscores",
            at_tick=10
        ))
        
        events = event_system.list_events(project_id="project-with-dashes_and_underscores")
        
        assert len(events) == 1
        assert events[0]["project_id"] == "project-with-dashes_and_underscores"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
