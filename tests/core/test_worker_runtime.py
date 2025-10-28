"""
Tests for WorkerRuntime module.

Tests message queuing, draining, persistence, loading,
and runtime lifecycle management.
"""

import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager

import pytest

from virtualoffice.sim_manager.core.worker_runtime import WorkerRuntime, WorkerRuntimeManager
from virtualoffice.sim_manager.core.event_system import InboundMessage
from virtualoffice.sim_manager.schemas import PersonRead


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

    # Create worker_runtime_messages table
    with get_test_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE worker_runtime_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        conn.commit()

    # Patch get_connection
    import virtualoffice.common.db as db_module
    import virtualoffice.sim_manager.core.worker_runtime as worker_runtime_module

    def test_get_connection():
        return get_test_connection(db_path)

    monkeypatch.setattr(db_module, "get_connection", test_get_connection)
    monkeypatch.setattr(worker_runtime_module, "get_connection", test_get_connection)

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
    handle: str = "test"
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
        is_department_head=False,
        skills=["Python"],
        personality=["collaborative"],
        team_name="Engineering",
        objectives=[],
        metrics=[],
        persona_markdown="Test persona",
        planning_guidelines=[],
        event_playbook={},
        statuses=[]
    )


def create_test_message(
    sender_id: int = 1,
    sender_name: str = "Alice",
    subject: str = "Test",
    summary: str = "Test message",
    tick: int = 1
) -> InboundMessage:
    """Create a test InboundMessage."""
    return InboundMessage(
        sender_id=sender_id,
        sender_name=sender_name,
        subject=subject,
        summary=summary,
        action_item="Please review",
        message_type="request",
        channel="email",
        tick=tick
    )


class TestWorkerRuntime:
    """Test WorkerRuntime class."""
    
    def test_initialization(self):
        """Test WorkerRuntime initializes correctly."""
        person = create_mock_person(1, "Alice")
        runtime = WorkerRuntime(person=person)
        
        assert runtime.person == person
        assert len(runtime.inbox) == 0
        assert not runtime.has_messages()
        assert runtime.message_count() == 0
    
    def test_queue_message(self):
        """Test queuing a message."""
        person = create_mock_person(1, "Alice")
        runtime = WorkerRuntime(person=person)
        message = create_test_message()
        
        runtime.queue(message)
        
        assert runtime.has_messages()
        assert runtime.message_count() == 1
        assert message in runtime.inbox
    
    def test_queue_multiple_messages(self):
        """Test queuing multiple messages."""
        person = create_mock_person(1, "Alice")
        runtime = WorkerRuntime(person=person)
        
        msg1 = create_test_message(sender_id=1, subject="Message 1")
        msg2 = create_test_message(sender_id=2, subject="Message 2")
        msg3 = create_test_message(sender_id=3, subject="Message 3")
        
        runtime.queue(msg1)
        runtime.queue(msg2)
        runtime.queue(msg3)
        
        assert runtime.message_count() == 3
        assert msg1 in runtime.inbox
        assert msg2 in runtime.inbox
        assert msg3 in runtime.inbox
    
    def test_drain_messages(self):
        """Test draining messages from inbox."""
        person = create_mock_person(1, "Alice")
        runtime = WorkerRuntime(person=person)
        
        msg1 = create_test_message(sender_id=1, subject="Message 1")
        msg2 = create_test_message(sender_id=2, subject="Message 2")
        
        runtime.queue(msg1)
        runtime.queue(msg2)
        
        # Drain messages
        messages = runtime.drain()
        
        assert len(messages) == 2
        assert msg1 in messages
        assert msg2 in messages
        
        # Inbox should be empty after drain
        assert not runtime.has_messages()
        assert runtime.message_count() == 0
    
    def test_drain_empty_inbox(self):
        """Test draining an empty inbox."""
        person = create_mock_person(1, "Alice")
        runtime = WorkerRuntime(person=person)
        
        messages = runtime.drain()
        
        assert len(messages) == 0
        assert not runtime.has_messages()


class TestWorkerRuntimeManager:
    """Test WorkerRuntimeManager class."""
    
    def test_initialization(self, isolated_db):
        """Test WorkerRuntimeManager initializes correctly."""
        manager = WorkerRuntimeManager()
        
        assert len(manager._worker_runtime) == 0
        assert len(manager.get_all_runtimes()) == 0
    
    def test_get_runtime_creates_new(self, isolated_db):
        """Test getting runtime creates new runtime if not exists."""
        manager = WorkerRuntimeManager()
        person = create_mock_person(1, "Alice")
        
        runtime = manager.get_runtime(person)
        
        assert runtime is not None
        assert runtime.person == person
        assert len(manager._worker_runtime) == 1
    
    def test_get_runtime_returns_existing(self, isolated_db):
        """Test getting runtime returns existing runtime."""
        manager = WorkerRuntimeManager()
        person = create_mock_person(1, "Alice")
        
        runtime1 = manager.get_runtime(person)
        runtime2 = manager.get_runtime(person)
        
        assert runtime1 is runtime2
        assert len(manager._worker_runtime) == 1
    
    def test_get_runtime_updates_person_reference(self, isolated_db):
        """Test getting runtime updates person reference."""
        manager = WorkerRuntimeManager()
        person1 = create_mock_person(1, "Alice", "alice@example.com")
        person2 = create_mock_person(1, "Alice Updated", "alice.new@example.com")
        
        runtime = manager.get_runtime(person1)
        assert runtime.person.email_address == "alice@example.com"
        
        # Get runtime again with updated person
        runtime = manager.get_runtime(person2)
        assert runtime.person.email_address == "alice.new@example.com"
    
    def test_sync_runtimes_creates_new(self, isolated_db):
        """Test sync_runtimes creates runtimes for new people."""
        manager = WorkerRuntimeManager()
        
        alice = create_mock_person(1, "Alice")
        bob = create_mock_person(2, "Bob")
        people = [alice, bob]
        
        manager.sync_runtimes(people)
        
        assert len(manager._worker_runtime) == 2
        assert 1 in manager._worker_runtime
        assert 2 in manager._worker_runtime
    
    def test_sync_runtimes_removes_inactive(self, isolated_db):
        """Test sync_runtimes removes runtimes for inactive people."""
        manager = WorkerRuntimeManager()
        
        alice = create_mock_person(1, "Alice")
        bob = create_mock_person(2, "Bob")
        charlie = create_mock_person(3, "Charlie")
        
        # Initial sync with all three
        manager.sync_runtimes([alice, bob, charlie])
        assert len(manager._worker_runtime) == 3
        
        # Sync with only Alice and Bob (Charlie removed)
        manager.sync_runtimes([alice, bob])
        assert len(manager._worker_runtime) == 2
        assert 1 in manager._worker_runtime
        assert 2 in manager._worker_runtime
        assert 3 not in manager._worker_runtime
    
    def test_queue_message(self, isolated_db):
        """Test queuing a message for a recipient."""
        manager = WorkerRuntimeManager()
        person = create_mock_person(1, "Alice")
        message = create_test_message()
        
        manager.queue_message(person, message)
        
        runtime = manager.get_runtime(person)
        assert runtime.has_messages()
        assert runtime.message_count() == 1
    
    def test_queue_message_persists_to_db(self, isolated_db):
        """Test queuing a message persists it to database."""
        manager = WorkerRuntimeManager()
        person = create_mock_person(1, "Alice")
        message = create_test_message(subject="Important", summary="Please review ASAP")
        
        manager.queue_message(person, message)
        
        # Check database
        with get_test_connection(isolated_db) as conn:
            rows = conn.execute(
                "SELECT * FROM worker_runtime_messages WHERE recipient_id = ?",
                (person.id,)
            ).fetchall()
        
        assert len(rows) == 1
        payload = json.loads(rows[0]["payload"])
        assert payload["subject"] == "Important"
        assert payload["summary"] == "Please review ASAP"
    
    def test_load_runtime_messages(self, isolated_db):
        """Test loading messages from database into runtime."""
        manager = WorkerRuntimeManager()
        person = create_mock_person(1, "Alice")
        
        # Insert messages directly into database
        with get_test_connection(isolated_db) as conn:
            for i in range(3):
                payload = {
                    "sender_id": i + 10,
                    "sender_name": f"Sender {i}",
                    "subject": f"Subject {i}",
                    "summary": f"Summary {i}",
                    "action_item": f"Action {i}",
                    "message_type": "request",
                    "channel": "email",
                    "tick": i + 1
                }
                conn.execute(
                    "INSERT INTO worker_runtime_messages(recipient_id, payload) VALUES (?, ?)",
                    (person.id, json.dumps(payload))
                )
        
        # Get runtime (should load messages)
        runtime = manager.get_runtime(person)
        
        assert runtime.message_count() == 3
        assert runtime.inbox[0].subject == "Subject 0"
        assert runtime.inbox[1].subject == "Subject 1"
        assert runtime.inbox[2].subject == "Subject 2"
    
    def test_remove_messages(self, isolated_db):
        """Test removing messages from database."""
        manager = WorkerRuntimeManager()
        person = create_mock_person(1, "Alice")
        
        # Queue some messages
        msg1 = create_test_message(subject="Message 1")
        msg2 = create_test_message(subject="Message 2")
        msg3 = create_test_message(subject="Message 3")
        
        manager.queue_message(person, msg1)
        manager.queue_message(person, msg2)
        manager.queue_message(person, msg3)
        
        # Get message IDs
        message_ids = [msg1.message_id, msg2.message_id]
        
        # Remove first two messages
        manager.remove_messages(message_ids)
        
        # Check database
        with get_test_connection(isolated_db) as conn:
            rows = conn.execute(
                "SELECT * FROM worker_runtime_messages WHERE recipient_id = ?",
                (person.id,)
            ).fetchall()
        
        # Only one message should remain
        assert len(rows) == 1
        payload = json.loads(rows[0]["payload"])
        assert payload["subject"] == "Message 3"
    
    def test_remove_messages_empty_list(self, isolated_db):
        """Test removing messages with empty list does nothing."""
        manager = WorkerRuntimeManager()
        
        # Should not raise an error
        manager.remove_messages([])
    
    def test_clear_all(self, isolated_db):
        """Test clearing all runtimes and messages."""
        manager = WorkerRuntimeManager()
        
        alice = create_mock_person(1, "Alice")
        bob = create_mock_person(2, "Bob")
        
        # Queue messages for both
        manager.queue_message(alice, create_test_message(subject="For Alice"))
        manager.queue_message(bob, create_test_message(subject="For Bob"))
        
        assert len(manager._worker_runtime) == 2
        
        # Clear all
        manager.clear_all()
        
        assert len(manager._worker_runtime) == 0
        
        # Check database is empty
        with get_test_connection(isolated_db) as conn:
            rows = conn.execute("SELECT * FROM worker_runtime_messages").fetchall()
        assert len(rows) == 0
    
    def test_get_all_runtimes(self, isolated_db):
        """Test getting all runtimes."""
        manager = WorkerRuntimeManager()
        
        alice = create_mock_person(1, "Alice")
        bob = create_mock_person(2, "Bob")
        
        manager.get_runtime(alice)
        manager.get_runtime(bob)
        
        all_runtimes = manager.get_all_runtimes()
        
        assert len(all_runtimes) == 2
        assert 1 in all_runtimes
        assert 2 in all_runtimes
        assert all_runtimes[1].person.name == "Alice"
        assert all_runtimes[2].person.name == "Bob"


class TestWorkerRuntimeIntegration:
    """Integration tests for WorkerRuntime."""
    
    def test_full_message_lifecycle(self, isolated_db):
        """Test complete message lifecycle: queue, persist, load, drain."""
        manager = WorkerRuntimeManager()
        person = create_mock_person(1, "Alice")
        
        # Queue a message
        message = create_test_message(subject="Test", summary="Test message")
        manager.queue_message(person, message)
        
        # Clear runtime (simulating restart)
        manager._worker_runtime.clear()
        
        # Get runtime again (should load from database)
        runtime = manager.get_runtime(person)
        
        assert runtime.has_messages()
        assert runtime.message_count() == 1
        
        # Drain messages
        messages = runtime.drain()
        assert len(messages) == 1
        assert messages[0].subject == "Test"
        
        # Remove from database
        manager.remove_messages([messages[0].message_id])
        
        # Verify database is clean
        with get_test_connection(isolated_db) as conn:
            rows = conn.execute(
                "SELECT * FROM worker_runtime_messages WHERE recipient_id = ?",
                (person.id,)
            ).fetchall()
        assert len(rows) == 0
    
    def test_multiple_workers_independent_inboxes(self, isolated_db):
        """Test that multiple workers have independent inboxes."""
        manager = WorkerRuntimeManager()
        
        alice = create_mock_person(1, "Alice")
        bob = create_mock_person(2, "Bob")
        
        # Queue different messages for each
        manager.queue_message(alice, create_test_message(subject="For Alice"))
        manager.queue_message(bob, create_test_message(subject="For Bob"))
        manager.queue_message(bob, create_test_message(subject="Another for Bob"))
        
        # Check Alice's inbox
        alice_runtime = manager.get_runtime(alice)
        assert alice_runtime.message_count() == 1
        assert alice_runtime.inbox[0].subject == "For Alice"
        
        # Check Bob's inbox
        bob_runtime = manager.get_runtime(bob)
        assert bob_runtime.message_count() == 2
        assert bob_runtime.inbox[0].subject == "For Bob"
        assert bob_runtime.inbox[1].subject == "Another for Bob"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
