"""
Unit tests for InboxManager

Tests inbox tracking, message classification, and reply management.
"""

import pytest
from src.virtualoffice.sim_manager.inbox_manager import InboxManager, InboxMessage


class TestInboxMessage:
    """Test InboxMessage dataclass"""
    
    def test_inbox_message_creation(self):
        """Test creating an InboxMessage"""
        msg = InboxMessage(
            message_id=1,
            sender_id=2,
            sender_name="Alice",
            subject="Test Subject",
            body="Test body",
            thread_id="thread-1",
            received_tick=100,
            needs_reply=True,
            message_type="question",
            channel="email"
        )
        
        assert msg.message_id == 1
        assert msg.sender_id == 2
        assert msg.sender_name == "Alice"
        assert msg.needs_reply is True
        assert msg.replied_tick is None


class TestInboxManager:
    """Test InboxManager functionality"""
    
    def test_initialization(self):
        """Test InboxManager initializes with empty inboxes"""
        manager = InboxManager()
        assert manager.inboxes == {}
    
    def test_add_message(self):
        """Test adding a message to inbox"""
        manager = InboxManager()
        msg = InboxMessage(
            message_id=1,
            sender_id=2,
            sender_name="Alice",
            subject="Test",
            body="Test body",
            thread_id=None,
            received_tick=100,
            needs_reply=False,
            message_type="update",
            channel="email"
        )
        
        manager.add_message(1, msg)
        
        assert 1 in manager.inboxes
        assert len(manager.inboxes[1]) == 1
        assert manager.inboxes[1][0].message_id == 1
    
    def test_inbox_20_message_limit(self):
        """Test that inbox maintains 20-message limit"""
        manager = InboxManager()
        
        # Add 25 messages
        for i in range(25):
            msg = InboxMessage(
                message_id=i,
                sender_id=2,
                sender_name="Alice",
                subject=f"Message {i}",
                body="Test",
                thread_id=None,
                received_tick=100 + i,
                needs_reply=False,
                message_type="update",
                channel="email"
            )
            manager.add_message(1, msg)
        
        # Should only keep last 20
        assert len(manager.inboxes[1]) == 20
        # Should have messages 5-24 (most recent)
        assert manager.inboxes[1][0].message_id == 5
        assert manager.inboxes[1][-1].message_id == 24
    
    def test_get_inbox_empty(self):
        """Test getting inbox for persona with no messages"""
        manager = InboxManager()
        inbox = manager.get_inbox(1)
        assert inbox == []
    
    def test_get_inbox_prioritizes_replies(self):
        """Test that get_inbox prioritizes messages needing replies"""
        manager = InboxManager()
        
        # Add messages in mixed order
        msg1 = InboxMessage(
            message_id=1, sender_id=2, sender_name="Alice",
            subject="Update", body="Status update",
            thread_id=None, received_tick=100,
            needs_reply=False, message_type="update", channel="email"
        )
        msg2 = InboxMessage(
            message_id=2, sender_id=3, sender_name="Bob",
            subject="Question", body="Can you help?",
            thread_id=None, received_tick=101,
            needs_reply=True, message_type="question", channel="email"
        )
        msg3 = InboxMessage(
            message_id=3, sender_id=4, sender_name="Carol",
            subject="Report", body="Weekly report",
            thread_id=None, received_tick=102,
            needs_reply=False, message_type="report", channel="email"
        )
        msg4 = InboxMessage(
            message_id=4, sender_id=5, sender_name="Dave",
            subject="Request", body="Please review",
            thread_id=None, received_tick=103,
            needs_reply=True, message_type="request", channel="email"
        )
        
        manager.add_message(1, msg1)
        manager.add_message(1, msg2)
        manager.add_message(1, msg3)
        manager.add_message(1, msg4)
        
        inbox = manager.get_inbox(1, max_messages=3)
        
        # Should get 2 messages needing replies first, then 1 other
        assert len(inbox) == 3
        assert inbox[0].needs_reply is True
        assert inbox[1].needs_reply is True
        assert inbox[2].needs_reply is False
    
    def test_get_inbox_respects_max_messages(self):
        """Test that get_inbox respects max_messages parameter"""
        manager = InboxManager()
        
        # Add 10 messages
        for i in range(10):
            msg = InboxMessage(
                message_id=i, sender_id=2, sender_name="Alice",
                subject=f"Message {i}", body="Test",
                thread_id=None, received_tick=100 + i,
                needs_reply=False, message_type="update", channel="email"
            )
            manager.add_message(1, msg)
        
        inbox = manager.get_inbox(1, max_messages=3)
        assert len(inbox) == 3
    
    def test_mark_replied(self):
        """Test marking a message as replied"""
        manager = InboxManager()
        
        msg = InboxMessage(
            message_id=1, sender_id=2, sender_name="Alice",
            subject="Question", body="Can you help?",
            thread_id=None, received_tick=100,
            needs_reply=True, message_type="question", channel="email"
        )
        manager.add_message(1, msg)
        
        # Mark as replied
        manager.mark_replied(1, 1, 150)
        
        # Check that needs_reply is now False
        inbox = manager.get_inbox(1)
        assert inbox[0].needs_reply is False
        assert inbox[0].replied_tick == 150
    
    def test_mark_replied_nonexistent_message(self):
        """Test marking nonexistent message as replied (should not error)"""
        manager = InboxManager()
        
        msg = InboxMessage(
            message_id=1, sender_id=2, sender_name="Alice",
            subject="Test", body="Test",
            thread_id=None, received_tick=100,
            needs_reply=True, message_type="question", channel="email"
        )
        manager.add_message(1, msg)
        
        # Try to mark nonexistent message
        manager.mark_replied(1, 999, 150)
        
        # Original message should be unchanged
        inbox = manager.get_inbox(1)
        assert inbox[0].needs_reply is True
        assert inbox[0].replied_tick is None


class TestMessageClassification:
    """Test message classification logic"""
    
    def test_classify_question_english(self):
        """Test question classification with English keywords"""
        manager = InboxManager()
        
        # Question mark
        msg_type, needs_reply = manager.classify_message_type(
            "Help needed", "Can you help me with this?"
        )
        assert msg_type == "question"
        assert needs_reply is True
        
        # Question keywords
        msg_type, needs_reply = manager.classify_message_type(
            "Question", "What should we do about this issue?"
        )
        assert msg_type == "question"
        assert needs_reply is True
    
    def test_classify_question_korean(self):
        """Test question classification with Korean keywords"""
        manager = InboxManager()
        
        msg_type, needs_reply = manager.classify_message_type(
            "질문", "이 작업 가능할까요?"
        )
        assert msg_type == "question"
        assert needs_reply is True
    
    def test_classify_request_english(self):
        """Test request classification with English keywords"""
        manager = InboxManager()
        
        msg_type, needs_reply = manager.classify_message_type(
            "Review needed", "Please review this PR"
        )
        assert msg_type == "request"
        assert needs_reply is True
    
    def test_classify_request_korean(self):
        """Test request classification with Korean keywords"""
        manager = InboxManager()
        
        msg_type, needs_reply = manager.classify_message_type(
            "검토 요청", "코드 리뷰 부탁드립니다"
        )
        assert msg_type == "request"
        assert needs_reply is True
    
    def test_classify_blocker_english(self):
        """Test blocker classification with English keywords"""
        manager = InboxManager()
        
        msg_type, needs_reply = manager.classify_message_type(
            "Blocker", "I'm blocked on this task due to API issue"
        )
        assert msg_type == "blocker"
        assert needs_reply is True
    
    def test_classify_blocker_korean(self):
        """Test blocker classification with Korean keywords"""
        manager = InboxManager()
        
        msg_type, needs_reply = manager.classify_message_type(
            "문제 발생", "API 에러로 작업이 막혔습니다"
        )
        assert msg_type == "blocker"
        assert needs_reply is True
    
    def test_classify_update_english(self):
        """Test update classification with English keywords"""
        manager = InboxManager()
        
        msg_type, needs_reply = manager.classify_message_type(
            "Status Update", "Working on the login feature"
        )
        assert msg_type == "update"
        assert needs_reply is False
    
    def test_classify_update_korean(self):
        """Test update classification with Korean keywords"""
        manager = InboxManager()
        
        msg_type, needs_reply = manager.classify_message_type(
            "진행 상황", "로그인 기능 작업 중입니다"
        )
        assert msg_type == "update"
        assert needs_reply is False
    
    def test_classify_report_default(self):
        """Test that generic messages default to report"""
        manager = InboxManager()
        
        msg_type, needs_reply = manager.classify_message_type(
            "Weekly Summary", "Here are the metrics for this week"
        )
        assert msg_type == "report"
        assert needs_reply is False
    
    def test_classify_priority_order(self):
        """Test that classification follows priority order (question > request > blocker > update)"""
        manager = InboxManager()
        
        # Question should take priority over request keywords
        msg_type, needs_reply = manager.classify_message_type(
            "Request", "Can you please help with this?"
        )
        assert msg_type == "question"
        assert needs_reply is True
        
        # Request should take priority over update keywords
        msg_type, needs_reply = manager.classify_message_type(
            "Update", "Please review the status update"
        )
        assert msg_type == "request"
        assert needs_reply is True
