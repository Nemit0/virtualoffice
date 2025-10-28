"""
Tests for CommunicationHub module.

Tests communication parsing, scheduling, dispatch, deduplication,
cooldown logic, email threading, and group chat vs DM routing.
"""

import os
import tempfile
from unittest.mock import Mock, MagicMock, call

import pytest

from virtualoffice.sim_manager.core.communication_hub import CommunicationHub
from virtualoffice.sim_manager.core.tick_manager import TickManager
from virtualoffice.sim_manager.core.simulation_state import SimulationState
from virtualoffice.sim_manager.schemas import PersonRead
from virtualoffice.sim_manager.gateways import EmailGateway, ChatGateway


def create_mock_person(
    person_id: int,
    name: str = "Test Worker",
    email: str = "test@example.com",
    handle: str = "test",
    role: str = "Developer",
    is_department_head: bool = False
) -> PersonRead:
    """Create a mock PersonRead object."""
    return PersonRead(
        id=person_id,
        name=name,
        role=role,
        timezone="UTC",
        work_hours="09:00-17:00",
        break_frequency="50/10 cadence",
        communication_style="professional",
        email_address=email,
        chat_handle=handle,
        is_department_head=is_department_head,
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


@pytest.fixture
def mock_gateways():
    """Create mock email and chat gateways."""
    email_gateway = Mock(spec=EmailGateway)
    chat_gateway = Mock(spec=ChatGateway)
    
    # Mock email gateway to return a result with ID
    email_gateway.send_email.return_value = {'id': 'email-123', 'status': 'sent'}
    
    return email_gateway, chat_gateway


@pytest.fixture
def tick_manager():
    """Create a TickManager for testing."""
    # Create temp database for state manager
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    state = SimulationState(db_path=db_path)
    state.initialize_database()
    
    manager = TickManager(hours_per_day=8, tick_interval_seconds=1.0)
    manager._state = state
    
    yield manager
    
    # Cleanup
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except (PermissionError, OSError):
        pass


@pytest.fixture
def comm_hub(mock_gateways, tick_manager):
    """Create a CommunicationHub for testing."""
    email_gateway, chat_gateway = mock_gateways
    return CommunicationHub(
        email_gateway=email_gateway,
        chat_gateway=chat_gateway,
        tick_manager=tick_manager,
        cooldown_ticks=10
    )


class TestCommunicationHubBasics:
    """Test basic CommunicationHub functionality."""
    
    def test_initialization(self, comm_hub, mock_gateways):
        """Test CommunicationHub initializes correctly."""
        email_gateway, chat_gateway = mock_gateways
        assert comm_hub.email_gateway == email_gateway
        assert comm_hub.chat_gateway == chat_gateway
        assert comm_hub._contact_cooldown_ticks == 10
        assert len(comm_hub._sent_dedup) == 0
        assert len(comm_hub._scheduled_comms) == 0
    
    def test_reset_tick_sends(self, comm_hub):
        """Test reset_tick_sends clears deduplication tracking."""
        # Add some dedup entries
        comm_hub._sent_dedup.add((1, 'email', 'sender', ('recipient',), 'subject', 'body'))
        assert len(comm_hub._sent_dedup) > 0
        
        # Reset
        comm_hub.reset_tick_sends()
        assert len(comm_hub._sent_dedup) == 0


class TestDeduplicationAndCooldown:
    """Test message deduplication and cooldown logic."""
    
    def test_can_send_first_message(self, comm_hub):
        """Test first message to recipient is allowed."""
        result = comm_hub.can_send(
            tick=1,
            channel='email',
            sender='alice@example.com',
            recipient_key=('bob@example.com',),
            subject='Test',
            body='Hello'
        )
        assert result is True
    
    def test_can_send_duplicate_blocked(self, comm_hub):
        """Test duplicate message is blocked."""
        # Send first message
        comm_hub.can_send(
            tick=1,
            channel='email',
            sender='alice@example.com',
            recipient_key=('bob@example.com',),
            subject='Test',
            body='Hello'
        )
        
        # Try to send duplicate
        result = comm_hub.can_send(
            tick=1,
            channel='email',
            sender='alice@example.com',
            recipient_key=('bob@example.com',),
            subject='Test',
            body='Hello'
        )
        assert result is False
    
    def test_can_send_cooldown_enforced(self, comm_hub):
        """Test cooldown period is enforced."""
        # Send first message at tick 1
        comm_hub.can_send(
            tick=1,
            channel='email',
            sender='alice@example.com',
            recipient_key=('bob@example.com',),
            subject='Test 1',
            body='Hello 1'
        )
        
        # Try to send different message at tick 5 (within cooldown of 10)
        result = comm_hub.can_send(
            tick=5,
            channel='email',
            sender='alice@example.com',
            recipient_key=('bob@example.com',),
            subject='Test 2',
            body='Hello 2'
        )
        assert result is False
    
    def test_can_send_after_cooldown(self, comm_hub):
        """Test message allowed after cooldown period."""
        # Send first message at tick 1
        comm_hub.can_send(
            tick=1,
            channel='email',
            sender='alice@example.com',
            recipient_key=('bob@example.com',),
            subject='Test 1',
            body='Hello 1'
        )
        
        # Send different message at tick 12 (after cooldown of 10)
        result = comm_hub.can_send(
            tick=12,
            channel='email',
            sender='alice@example.com',
            recipient_key=('bob@example.com',),
            subject='Test 2',
            body='Hello 2'
        )
        assert result is True
    
    def test_can_send_different_recipients(self, comm_hub):
        """Test messages to different recipients are independent."""
        # Send to Bob
        comm_hub.can_send(
            tick=1,
            channel='email',
            sender='alice@example.com',
            recipient_key=('bob@example.com',),
            subject='Test',
            body='Hello Bob'
        )
        
        # Send to Charlie (should be allowed)
        result = comm_hub.can_send(
            tick=1,
            channel='email',
            sender='alice@example.com',
            recipient_key=('charlie@example.com',),
            subject='Test',
            body='Hello Charlie'
        )
        assert result is True


class TestHourlyPlanParsing:
    """Test parsing of hourly plans for scheduled communications."""
    
    def test_parse_simple_email(self, comm_hub):
        """Test parsing simple email schedule."""
        person = create_mock_person(1, "Alice", "alice@example.com", "alice")
        plan_text = "Email at 10:30 to bob@example.com: Project Update | Making good progress"
        
        comm_hub.schedule_from_hourly_plan(person, plan_text, current_tick=1, hours_per_day=8)
        
        # Check scheduled communications
        assert 1 in comm_hub._scheduled_comms
        scheduled = comm_hub._scheduled_comms[1]
        assert len(scheduled) > 0
        
        # Find the scheduled email
        found = False
        for tick, actions in scheduled.items():
            for action in actions:
                if action['channel'] == 'email' and 'bob@example.com' in action['target']:
                    found = True
                    assert 'Project Update | Making good progress' in action['payload']
        assert found
    
    def test_parse_email_with_cc(self, comm_hub):
        """Test parsing email with CC."""
        person = create_mock_person(1, "Alice", "alice@example.com", "alice")
        plan_text = "Email at 14:00 to bob@example.com cc charlie@example.com: Status | All good"
        
        comm_hub.schedule_from_hourly_plan(person, plan_text, current_tick=1, hours_per_day=8)
        
        scheduled = comm_hub._scheduled_comms[1]
        found = False
        for tick, actions in scheduled.items():
            for action in actions:
                if action['channel'] == 'email':
                    found = True
                    assert 'cc' in action
                    assert 'charlie@example.com' in action['cc']
        assert found
    
    def test_parse_reply_to_email(self, comm_hub):
        """Test parsing reply to email syntax."""
        person = create_mock_person(1, "Alice", "alice@example.com", "alice")
        plan_text = "Reply at 11:00 to [email-456]: Re: Question | Here's the answer"
        
        comm_hub.schedule_from_hourly_plan(person, plan_text, current_tick=1, hours_per_day=8)
        
        scheduled = comm_hub._scheduled_comms[1]
        found = False
        for tick, actions in scheduled.items():
            for action in actions:
                if action['channel'] == 'email' and 'reply_to_email_id' in action:
                    found = True
                    assert action['reply_to_email_id'] == 'email-456'
        assert found
    
    def test_parse_chat_message(self, comm_hub):
        """Test parsing chat message schedule."""
        person = create_mock_person(1, "Alice", "alice@example.com", "alice")
        plan_text = "Chat at 15:30 to bob: Quick question about the API"
        
        comm_hub.schedule_from_hourly_plan(person, plan_text, current_tick=1, hours_per_day=8)
        
        scheduled = comm_hub._scheduled_comms[1]
        found = False
        for tick, actions in scheduled.items():
            for action in actions:
                if action['channel'] == 'chat':
                    found = True
                    assert action['target'] == 'bob'
                    assert 'Quick question' in action['payload']
        assert found
    
    def test_parse_multiple_communications(self, comm_hub):
        """Test parsing multiple scheduled communications."""
        person = create_mock_person(1, "Alice", "alice@example.com", "alice")
        plan_text = """
        Email at 10:00 to bob@example.com: Morning Update | Starting work
        Chat at 11:30 to charlie: Need your input
        Email at 14:00 to team@example.com: Afternoon Status | Progress report
        """
        
        comm_hub.schedule_from_hourly_plan(person, plan_text, current_tick=1, hours_per_day=8)
        
        scheduled = comm_hub._scheduled_comms[1]
        total_actions = sum(len(actions) for actions in scheduled.values())
        assert total_actions == 3
    
    def test_parse_ignores_past_times(self, comm_hub):
        """Test that past times in the same day are ignored."""
        person = create_mock_person(1, "Alice", "alice@example.com", "alice")
        # Current tick is 5 (around 11:15 AM if 8 hours/day)
        plan_text = "Email at 09:00 to bob@example.com: Too Late | This is in the past"
        
        comm_hub.schedule_from_hourly_plan(person, plan_text, current_tick=5, hours_per_day=8)
        
        # Should not schedule anything
        scheduled = comm_hub._scheduled_comms.get(1, {})
        assert len(scheduled) == 0


class TestEmailThreading:
    """Test email threading functionality."""
    
    def test_get_thread_id_for_reply_found(self, comm_hub):
        """Test looking up thread_id for a reply."""
        # Add a recent email
        comm_hub._recent_emails[1] = []
        comm_hub._recent_emails[1].append({
            'email_id': 'email-123',
            'from': 'bob@example.com',
            'thread_id': 'thread-abc',
            'subject': 'Question'
        })
        
        thread_id, sender = comm_hub.get_thread_id_for_reply(1, 'email-123')
        assert thread_id == 'thread-abc'
        assert sender == 'bob@example.com'
    
    def test_get_thread_id_for_reply_not_found(self, comm_hub):
        """Test looking up non-existent email."""
        thread_id, sender = comm_hub.get_thread_id_for_reply(1, 'email-999')
        assert thread_id is None
        assert sender is None
    
    def test_get_recent_emails(self, comm_hub):
        """Test retrieving recent emails for a person."""
        # Add some recent emails
        from collections import deque
        comm_hub._recent_emails[1] = deque(maxlen=10)
        comm_hub._recent_emails[1].append({'email_id': 'email-1', 'subject': 'Test 1'})
        comm_hub._recent_emails[1].append({'email_id': 'email-2', 'subject': 'Test 2'})
        
        recent = comm_hub.get_recent_emails_for_person(1, limit=10)
        assert len(recent) == 2
        assert recent[0]['email_id'] == 'email-1'
        assert recent[1]['email_id'] == 'email-2'


class TestDispatchScheduled:
    """Test dispatching scheduled communications."""
    
    def test_dispatch_simple_email(self, comm_hub, mock_gateways):
        """Test dispatching a simple email."""
        email_gateway, chat_gateway = mock_gateways
        
        alice = create_mock_person(1, "Alice", "alice@example.com", "alice")
        bob = create_mock_person(2, "Bob", "bob@example.com", "bob")
        people_by_id = {1: alice, 2: bob}
        
        # Schedule an email
        comm_hub._scheduled_comms[1] = {
            5: [{'channel': 'email', 'target': 'bob@example.com', 'payload': 'Update | Progress report'}]
        }
        
        # Mock helper functions
        get_current_week = Mock(return_value=1)
        get_active_projects = Mock(return_value=[])
        get_project_chat_room = Mock(return_value=None)
        
        # Dispatch
        emails, chats = comm_hub.dispatch_scheduled(
            alice, 5, people_by_id,
            get_current_week, get_active_projects, get_project_chat_room
        )
        
        assert emails == 1
        assert chats == 0
        email_gateway.send_email.assert_called_once()
    
    def test_dispatch_chat_dm(self, comm_hub, mock_gateways):
        """Test dispatching a chat DM."""
        email_gateway, chat_gateway = mock_gateways
        
        alice = create_mock_person(1, "Alice", "alice@example.com", "alice")
        bob = create_mock_person(2, "Bob", "bob@example.com", "bob")
        people_by_id = {1: alice, 2: bob}
        
        # Schedule a chat
        comm_hub._scheduled_comms[1] = {
            5: [{'channel': 'chat', 'target': 'bob', 'payload': 'Quick question'}]
        }
        
        # Mock helper functions
        get_current_week = Mock(return_value=1)
        get_active_projects = Mock(return_value=[])
        get_project_chat_room = Mock(return_value=None)
        
        # Dispatch
        emails, chats = comm_hub.dispatch_scheduled(
            alice, 5, people_by_id,
            get_current_week, get_active_projects, get_project_chat_room
        )
        
        assert emails == 0
        assert chats == 1
        chat_gateway.send_dm.assert_called_once()
    
    def test_dispatch_group_chat(self, comm_hub, mock_gateways):
        """Test dispatching to group chat."""
        email_gateway, chat_gateway = mock_gateways
        
        alice = create_mock_person(1, "Alice", "alice@example.com", "alice")
        people_by_id = {1: alice}
        
        # Schedule a group chat message
        comm_hub._scheduled_comms[1] = {
            5: [{'channel': 'chat', 'target': 'team', 'payload': 'Team update'}]
        }
        
        # Mock helper functions
        get_current_week = Mock(return_value=1)
        get_active_projects = Mock(return_value=[{'id': 1, 'name': 'Project Alpha'}])
        get_project_chat_room = Mock(return_value='project-alpha-chat')
        
        # Dispatch
        emails, chats = comm_hub.dispatch_scheduled(
            alice, 5, people_by_id,
            get_current_week, get_active_projects, get_project_chat_room
        )
        
        assert chats == 1
        chat_gateway.send_room_message.assert_called_once()
        call_args = chat_gateway.send_room_message.call_args
        assert call_args[1]['room_slug'] == 'project-alpha-chat'
    
    def test_dispatch_email_with_cc_suggestion(self, comm_hub, mock_gateways):
        """Test email dispatch with automatic CC suggestion."""
        email_gateway, chat_gateway = mock_gateways
        
        alice = create_mock_person(1, "Alice", "alice@example.com", "alice", role="Developer")
        bob = create_mock_person(2, "Bob", "bob@example.com", "bob", role="Developer")
        manager = create_mock_person(3, "Manager", "manager@example.com", "mgr", role="Manager", is_department_head=True)
        people_by_id = {1: alice, 2: bob, 3: manager}
        
        # Schedule an email without explicit CC
        comm_hub._scheduled_comms[1] = {
            5: [{'channel': 'email', 'target': 'bob@example.com', 'payload': 'Update | Status report'}]
        }
        
        # Mock helper functions
        get_current_week = Mock(return_value=1)
        get_active_projects = Mock(return_value=[])
        get_project_chat_room = Mock(return_value=None)
        
        # Dispatch
        emails, chats = comm_hub.dispatch_scheduled(
            alice, 5, people_by_id,
            get_current_week, get_active_projects, get_project_chat_room
        )
        
        assert emails == 1
        # Check that CC was suggested (should include manager)
        call_args = email_gateway.send_email.call_args
        cc_list = call_args[1].get('cc', [])
        assert 'manager@example.com' in cc_list
    
    def test_dispatch_reply_to_email(self, comm_hub, mock_gateways):
        """Test dispatching a reply to an email."""
        email_gateway, chat_gateway = mock_gateways
        
        alice = create_mock_person(1, "Alice", "alice@example.com", "alice")
        bob = create_mock_person(2, "Bob", "bob@example.com", "bob")
        people_by_id = {1: alice, 2: bob}
        
        # Add the original email to recent emails
        from collections import deque
        comm_hub._recent_emails[1] = deque(maxlen=10)
        comm_hub._recent_emails[1].append({
            'email_id': 'email-123',
            'from': 'bob@example.com',
            'thread_id': 'thread-abc',
            'subject': 'Question'
        })
        
        # Schedule a reply
        comm_hub._scheduled_comms[1] = {
            5: [{'channel': 'email', 'reply_to_email_id': 'email-123', 'payload': 'Re: Question | Here is the answer'}]
        }
        
        # Mock helper functions
        get_current_week = Mock(return_value=1)
        get_active_projects = Mock(return_value=[])
        get_project_chat_room = Mock(return_value=None)
        
        # Dispatch
        emails, chats = comm_hub.dispatch_scheduled(
            alice, 5, people_by_id,
            get_current_week, get_active_projects, get_project_chat_room
        )
        
        assert emails == 1
        # Check that thread_id was preserved
        call_args = email_gateway.send_email.call_args
        assert call_args[1]['thread_id'] == 'thread-abc'
        assert call_args[1]['to'] == ['bob@example.com']
    
    def test_dispatch_no_actions_at_tick(self, comm_hub, mock_gateways):
        """Test dispatch when no actions scheduled for tick."""
        alice = create_mock_person(1, "Alice", "alice@example.com", "alice")
        people_by_id = {1: alice}
        
        # Mock helper functions
        get_current_week = Mock(return_value=1)
        get_active_projects = Mock(return_value=[])
        get_project_chat_room = Mock(return_value=None)
        
        # Dispatch at tick with no scheduled actions
        emails, chats = comm_hub.dispatch_scheduled(
            alice, 5, people_by_id,
            get_current_week, get_active_projects, get_project_chat_room
        )
        
        assert emails == 0
        assert chats == 0
    
    def test_dispatch_rejects_hallucinated_emails(self, comm_hub, mock_gateways):
        """Test that hallucinated email addresses are rejected."""
        email_gateway, chat_gateway = mock_gateways
        
        alice = create_mock_person(1, "Alice", "alice@example.com", "alice")
        bob = create_mock_person(2, "Bob", "bob@example.com", "bob")
        people_by_id = {1: alice, 2: bob}
        
        # Schedule email to non-existent address
        comm_hub._scheduled_comms[1] = {
            5: [{'channel': 'email', 'target': 'fake@nowhere.com', 'payload': 'Test | Message'}]
        }
        
        # Mock helper functions
        get_current_week = Mock(return_value=1)
        get_active_projects = Mock(return_value=[])
        get_project_chat_room = Mock(return_value=None)
        
        # Dispatch
        emails, chats = comm_hub.dispatch_scheduled(
            alice, 5, people_by_id,
            get_current_week, get_active_projects, get_project_chat_room
        )
        
        # Should not send email to hallucinated address
        assert emails == 0
        email_gateway.send_email.assert_not_called()


class TestDirectScheduling:
    """Test direct communication scheduling."""
    
    def test_schedule_direct_comm(self, comm_hub):
        """Test directly scheduling a communication."""
        comm_hub.schedule_direct_comm(
            person_id=1,
            tick=10,
            channel='email',
            target='bob@example.com',
            payload='Direct message'
        )
        
        assert 1 in comm_hub._scheduled_comms
        assert 10 in comm_hub._scheduled_comms[1]
        actions = comm_hub._scheduled_comms[1][10]
        assert len(actions) == 1
        assert actions[0]['channel'] == 'email'
        assert actions[0]['target'] == 'bob@example.com'
        assert actions[0]['payload'] == 'Direct message'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
