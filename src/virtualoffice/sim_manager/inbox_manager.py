"""
Inbox Management System for Communication Diversity

This module provides inbox tracking for received messages, enabling:
- Message classification (question, request, blocker, update, report)
- Reply tracking and prioritization
- Threading support for conversational flow

Requirements: R-2.1, R-2.2, R-2.3, R-7.1-R-7.5
"""

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class InboxMessage:
    """
    Represents a received message in a persona's inbox.
    
    Attributes:
        message_id: Unique identifier for the message
        sender_id: ID of the persona who sent the message
        sender_name: Name of the sender
        subject: Email subject or chat topic (empty string for chats)
        body: Message content
        thread_id: Thread identifier for email threading (None for new threads)
        received_tick: Simulation tick when message was received
        needs_reply: Whether this message requires a response
        message_type: Classification (question, request, blocker, update, report)
        channel: Communication channel ('email' or 'chat')
        replied_tick: Simulation tick when reply was sent (None if not replied)
    """
    message_id: int
    sender_id: int
    sender_name: str
    subject: str
    body: str
    thread_id: Optional[str]
    received_tick: int
    needs_reply: bool
    message_type: str
    channel: str
    replied_tick: Optional[int] = None


class InboxManager:
    """
    Manages inbox tracking for all personas in the simulation.
    
    Tracks received messages, classifies them, and identifies which need replies.
    Maintains a 20-message limit per inbox to keep context manageable.
    
    Requirements: R-2.3
    """
    
    def __init__(self, persist_to_db: bool = False):
        """
        Initialize the inbox manager with empty inboxes.
        
        Args:
            persist_to_db: If True, persist inbox messages to database (optional)
        """
        self.inboxes: dict[int, list[InboxMessage]] = {}
        self.persist_to_db = persist_to_db

    def add_message(
        self,
        person_id: int,
        message: InboxMessage
    ) -> None:
        """
        Add a received message to a persona's inbox.
        
        Maintains a 20-message limit per inbox, keeping only the most recent messages.
        This prevents memory bloat while maintaining sufficient context for replies.
        
        Args:
            person_id: ID of the persona receiving the message
            message: InboxMessage object to add
            
        Requirements: R-2.3
        """
        if person_id not in self.inboxes:
            self.inboxes[person_id] = []
        
        self.inboxes[person_id].append(message)
        
        # Log message addition
        logger.debug(
            f"[INBOX] Added message to inbox for person_id={person_id}: "
            f"type={message.message_type}, sender_id={message.sender_id}, "
            f"needs_reply={message.needs_reply}, tick={message.received_tick}"
        )
        
        # Keep only last 20 messages
        if len(self.inboxes[person_id]) > 20:
            self.inboxes[person_id] = self.inboxes[person_id][-20:]
        
        # Optionally persist to database
        if self.persist_to_db:
            self._persist_message(message)
    
    def get_inbox(
        self,
        person_id: int,
        max_messages: int = 5
    ) -> list[InboxMessage]:
        """
        Retrieve recent inbox messages for a persona.
        
        Messages are prioritized with those needing replies first, followed by
        other messages in chronological order. This ensures important messages
        are included in the context for communication generation.
        
        Args:
            person_id: ID of the persona
            max_messages: Maximum number of messages to return (default: 5)
            
        Returns:
            List of InboxMessage objects, prioritized by needs_reply
            
        Requirements: R-2.3
        """
        messages = self.inboxes.get(person_id, [])
        
        # Prioritize messages needing replies
        needs_reply = [m for m in messages if m.needs_reply]
        others = [m for m in messages if not m.needs_reply]
        
        # Return up to max_messages, prioritizing replies
        return (needs_reply + others)[:max_messages]

    def classify_message_type(
        self,
        subject: str,
        body: str,
        locale: str = "en"
    ) -> tuple[str, bool]:
        """
        Classify a message type and determine if a reply is needed.
        
        Uses keyword-based heuristics to identify message types:
        - question: Contains question marks or question keywords
        - request: Contains request/action keywords
        - blocker: Contains blocker/issue keywords
        - update: Contains status update keywords
        - report: Default for informational messages
        
        Supports both Korean and English keywords for multilingual simulations.
        
        Args:
            subject: Message subject (email) or empty string (chat)
            body: Message content
            locale: Language locale ('ko' for Korean, 'en' for English, default: 'en')
            
        Returns:
            Tuple of (message_type, needs_reply) where:
            - message_type: One of 'question', 'request', 'blocker', 'update', 'report'
            - needs_reply: Boolean indicating if response is expected
            
        Requirements: R-2.1, R-2.2, R-7.1, R-7.2, R-7.3, R-7.4, R-7.5
        """
        # Combine subject and body for analysis
        subject_text = subject if subject else ""
        body_text = body if body else ""
        text = (subject_text + " " + body_text).lower().strip()
        
        # Question detection (highest priority for replies)
        question_keywords_en = ['can you', 'could you', 'would you', 'will you', 
                                'should we', 'what', 'when', 'where', 'why', 'how',
                                'do you', 'does', 'is it', 'are you']
        question_keywords_ko = ['가능', '질문', '어떻게', '언제', '어디', '왜',
                                '할 수 있', '해주실', '해주시', '알려주', '확인']
        
        if '?' in text or any(kw in text for kw in question_keywords_en + question_keywords_ko):
            message_type = 'question'
            needs_reply = True
            logger.debug(
                f"[INBOX] Classified message as '{message_type}' "
                f"(needs_reply={needs_reply})"
            )
            return message_type, needs_reply
        
        # Request detection (high priority for replies)
        request_keywords_en = ['please', 'need', 'request', 'require', 'asking',
                               'help', 'assist', 'support', 'review', 'check',
                               'feedback', 'approve', 'confirm']
        request_keywords_ko = ['요청', '부탁', '필요', '도움', '검토', '확인',
                               '피드백', '승인', '리뷰', '체크']
        
        if any(kw in text for kw in request_keywords_en + request_keywords_ko):
            message_type = 'request'
            needs_reply = True
            logger.debug(
                f"[INBOX] Classified message as '{message_type}' "
                f"(needs_reply={needs_reply})"
            )
            return message_type, needs_reply
        
        # Blocker detection (high priority for replies)
        blocker_keywords_en = ['blocker', 'blocked', 'issue', 'problem', 'error',
                               'bug', 'stuck', 'cannot', 'unable', 'failing',
                               'broken', 'urgent']
        blocker_keywords_ko = ['문제', '막힘', '블로커', '버그', '에러', '오류',
                               '안됨', '불가', '긴급', '장애']
        
        if any(kw in text for kw in blocker_keywords_en + blocker_keywords_ko):
            message_type = 'blocker'
            needs_reply = True
            logger.debug(
                f"[INBOX] Classified message as '{message_type}' "
                f"(needs_reply={needs_reply})"
            )
            return message_type, needs_reply
        
        # Update detection (informational, no reply needed)
        update_keywords_en = ['update', 'status', 'progress', 'completed', 'finished',
                              'done', 'working on', 'fyi', 'heads up']
        update_keywords_ko = ['업데이트', '진행', '상황', '완료', '작업 중',
                              '참고', '알림', '공유']
        
        if any(kw in text for kw in update_keywords_en + update_keywords_ko):
            message_type = 'update'
            needs_reply = False
            logger.debug(
                f"[INBOX] Classified message as '{message_type}' "
                f"(needs_reply={needs_reply})"
            )
            return message_type, needs_reply
        
        # Default to report (informational, no reply needed)
        message_type = 'report'
        needs_reply = False
        logger.debug(
            f"[INBOX] Classified message as '{message_type}' "
            f"(needs_reply={needs_reply})"
        )
        return message_type, needs_reply

    def mark_replied(
        self,
        person_id: int,
        message_id: int,
        replied_tick: int
    ) -> None:
        """
        Mark a message as replied to track response completion.
        
        Updates the needs_reply flag to False and records when the reply was sent.
        This enables metrics tracking for response times and conversation flow.
        
        Args:
            person_id: ID of the persona who received the original message
            message_id: ID of the message being replied to
            replied_tick: Simulation tick when the reply was sent
            
        Requirements: R-2.1
        """
        messages = self.inboxes.get(person_id, [])
        for msg in messages:
            if msg.message_id == message_id:
                msg.needs_reply = False
                msg.replied_tick = replied_tick
                
                # Optionally update database
                if self.persist_to_db:
                    self._update_replied_status(message_id, replied_tick)
                break

    def _persist_message(self, message: InboxMessage) -> None:
        """
        Persist an inbox message to the database.
        
        Args:
            message: InboxMessage to persist
            
        Requirements: R-12.1
        """
        try:
            from virtualoffice.common.db import get_connection
            
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO inbox_messages (
                        person_id, message_id, message_type, sender_id, sender_name,
                        subject, body, thread_id, received_tick, needs_reply, message_category
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message.sender_id,  # person_id is the recipient
                    str(message.message_id),
                    message.channel,
                    message.sender_id,
                    message.sender_name,
                    message.subject,
                    message.body,
                    message.thread_id,
                    message.received_tick,
                    1 if message.needs_reply else 0,
                    message.message_type
                ))
        except Exception as e:
            logger.warning(f"Failed to persist inbox message: {e}")

    def _update_replied_status(self, message_id: int, replied_tick: int) -> None:
        """
        Update the replied status of a message in the database.
        
        Args:
            message_id: ID of the message
            replied_tick: Tick when reply was sent
            
        Requirements: R-12.1
        """
        try:
            from virtualoffice.common.db import get_connection
            
            with get_connection() as conn:
                conn.execute("""
                    UPDATE inbox_messages 
                    SET needs_reply = 0, replied_tick = ?
                    WHERE message_id = ?
                """, (replied_tick, str(message_id)))
        except Exception as e:
            logger.warning(f"Failed to update replied status: {e}")
