# Inbox Manager Module

**Module:** `src/virtualoffice/sim_manager/inbox_manager.py`  
**Status:** Implemented  
**Requirements:** R-2.1, R-2.2, R-2.3, R-7.1-R-7.5

---

## Overview

The Inbox Manager module provides inbox tracking for received messages in the VDOS simulation. It enables:

- **Message tracking**: Maintains a 20-message inbox per persona
- **Message classification**: Identifies message types (question, request, blocker, update, report)
- **Reply prioritization**: Prioritizes messages needing responses
- **Reply tracking**: Records when messages are replied to
- **Multilingual support**: Handles both Korean and English keywords

This module is a core component of the Communication Diversity feature, enabling threading and conversational flow by tracking which messages need replies.

---

## Architecture

### Data Model

```python
@dataclass
class InboxMessage:
    """Represents a received message in a persona's inbox"""
    message_id: int              # Unique message identifier
    sender_id: int               # Sender persona ID
    sender_name: str             # Sender display name
    subject: str                 # Email subject or empty for chat
    body: str                    # Message content
    thread_id: Optional[str]     # Thread identifier for threading
    received_tick: int           # When message was received
    needs_reply: bool            # Whether reply is expected
    message_type: str            # Classification type
    channel: str                 # 'email' or 'chat'
    replied_tick: Optional[int]  # When reply was sent (if any)
```

### Class Structure

```python
class InboxManager:
    """Manages inbox tracking for all personas"""
    
    def __init__(self):
        self.inboxes: dict[int, list[InboxMessage]] = {}
    
    def add_message(person_id: int, message: InboxMessage) -> None
    def get_inbox(person_id: int, max_messages: int = 5) -> list[InboxMessage]
    def classify_message_type(subject: str, body: str) -> tuple[str, bool]
    def mark_replied(person_id: int, message_id: int, replied_tick: int) -> None
```

---

## API Reference

### InboxManager.add_message()

Add a received message to a persona's inbox.

**Signature:**
```python
def add_message(
    self,
    person_id: int,
    message: InboxMessage
) -> None
```

**Parameters:**
- `person_id`: ID of the persona receiving the message
- `message`: InboxMessage object to add

**Behavior:**
- Creates inbox for persona if it doesn't exist
- Appends message to inbox
- Maintains 20-message limit (keeps most recent)

**Example:**
```python
manager = InboxManager()
msg = InboxMessage(
    message_id=1,
    sender_id=2,
    sender_name="Alice",
    subject="Question about API",
    body="Can you help with the authentication endpoint?",
    thread_id=None,
    received_tick=100,
    needs_reply=True,
    message_type="question",
    channel="email"
)
manager.add_message(person_id=1, message=msg)
```

---

### InboxManager.get_inbox()

Retrieve recent inbox messages for a persona, prioritized by reply needs.

**Signature:**
```python
def get_inbox(
    self,
    person_id: int,
    max_messages: int = 5
) -> list[InboxMessage]
```

**Parameters:**
- `person_id`: ID of the persona
- `max_messages`: Maximum number of messages to return (default: 5)

**Returns:**
- List of InboxMessage objects, with messages needing replies first

**Behavior:**
- Returns empty list if persona has no inbox
- Prioritizes messages with `needs_reply=True`
- Limits results to `max_messages`

**Example:**
```python
# Get up to 5 recent messages, prioritizing those needing replies
inbox = manager.get_inbox(person_id=1, max_messages=5)

for msg in inbox:
    if msg.needs_reply:
        print(f"Reply needed: {msg.subject}")
```

---

### InboxManager.classify_message_type()

Classify a message type and determine if a reply is needed.

**Signature:**
```python
def classify_message_type(
    self,
    subject: str,
    body: str
) -> tuple[str, bool]
```

**Parameters:**
- `subject`: Message subject (email) or empty string (chat)
- `body`: Message content

**Returns:**
- Tuple of `(message_type, needs_reply)` where:
  - `message_type`: One of 'question', 'request', 'blocker', 'update', 'report'
  - `needs_reply`: Boolean indicating if response is expected

**Classification Rules:**

1. **Question** (needs_reply=True):
   - Contains `?` character
   - English: "can you", "could you", "what", "when", "where", "why", "how"
   - Korean: "가능", "질문", "어떻게", "언제", "어디", "왜"

2. **Request** (needs_reply=True):
   - English: "please", "need", "request", "help", "review", "feedback"
   - Korean: "요청", "부탁", "필요", "도움", "검토", "피드백"

3. **Blocker** (needs_reply=True):
   - English: "blocker", "blocked", "issue", "problem", "error", "urgent"
   - Korean: "문제", "막힘", "블로커", "버그", "에러", "긴급"

4. **Update** (needs_reply=False):
   - English: "update", "status", "progress", "completed", "fyi"
   - Korean: "업데이트", "진행", "상황", "완료", "참고"

5. **Report** (needs_reply=False):
   - Default for informational messages

**Priority Order:** question > request > blocker > update > report

**Example:**
```python
# Question
msg_type, needs_reply = manager.classify_message_type(
    "Help needed",
    "Can you review this PR?"
)
# Returns: ('question', True)

# Update
msg_type, needs_reply = manager.classify_message_type(
    "Status Update",
    "Working on the login feature"
)
# Returns: ('update', False)
```

---

### InboxManager.mark_replied()

Mark a message as replied to track response completion.

**Signature:**
```python
def mark_replied(
    self,
    person_id: int,
    message_id: int,
    replied_tick: int
) -> None
```

**Parameters:**
- `person_id`: ID of the persona who received the original message
- `message_id`: ID of the message being replied to
- `replied_tick`: Simulation tick when the reply was sent

**Behavior:**
- Sets `needs_reply=False` for the message
- Records `replied_tick` for metrics
- No-op if message not found (graceful handling)

**Example:**
```python
# When sending a reply
manager.mark_replied(
    person_id=1,
    message_id=42,
    replied_tick=150
)
```

---

## Integration with Engine

The InboxManager integrates with the simulation engine to track message flow:

### Message Delivery Integration

When the engine delivers an email or chat message:

```python
# In engine.py, after delivering a message
inbox_message = InboxMessage(
    message_id=email_id,
    sender_id=sender.id,
    sender_name=sender.name,
    subject=email_subject,
    body=email_body,
    thread_id=thread_id,
    received_tick=current_tick,
    needs_reply=False,  # Will be set by classification
    message_type="",    # Will be set by classification
    channel="email"
)

# Classify the message
msg_type, needs_reply = inbox_manager.classify_message_type(
    email_subject,
    email_body
)
inbox_message.message_type = msg_type
inbox_message.needs_reply = needs_reply

# Add to recipient's inbox
inbox_manager.add_message(recipient.id, inbox_message)
```

### Communication Generation Integration

When generating fallback communications:

```python
# Get inbox messages for context
inbox_messages = inbox_manager.get_inbox(person.id, max_messages=5)

# Generate communications with inbox context
communications = communication_generator.generate_fallback_communications(
    person=person,
    hourly_plan=plan,
    inbox_messages=inbox_messages,  # Provides reply context
    ...
)

# If communication is a reply, mark original as replied
for comm in communications:
    if 'reply_to' in comm:
        inbox_manager.mark_replied(
            person.id,
            comm['reply_to'],
            current_tick
        )
```

---

## Testing

### Unit Tests

Location: `tests/test_inbox_manager.py`

**Test Coverage:**
- ✅ InboxMessage dataclass creation
- ✅ InboxManager initialization
- ✅ Adding messages to inbox
- ✅ 20-message limit enforcement
- ✅ Empty inbox handling
- ✅ Reply prioritization in get_inbox()
- ✅ max_messages parameter
- ✅ Marking messages as replied
- ✅ Message classification (all types)
- ✅ Multilingual classification (English/Korean)
- ✅ Classification priority order

**Running Tests:**
```bash
python -m pytest tests/test_inbox_manager.py -v
```

**Test Results:**
- 19 tests, all passing
- 100% code coverage for core functionality

---

## Performance Considerations

### Memory Usage

- **Per Inbox:** Maximum 20 messages × ~500 bytes = ~10 KB
- **13 Personas:** 13 × 10 KB = ~130 KB total
- **Negligible impact** on simulation memory footprint

### Classification Performance

- **Keyword matching:** O(n) where n = number of keywords
- **Per message:** <1ms typical
- **Acceptable** for simulation use case

### Scalability

- **Current design:** In-memory only
- **Phase 2 option:** Database persistence for larger simulations
- **Recommendation:** Keep in-memory for <100 personas

---

## Configuration

### Environment Variables

No environment variables required for basic functionality.

**Optional (Phase 2):**
- `VDOS_INBOX_PERSISTENCE_ENABLED`: Enable database persistence (default: false)
- `VDOS_INBOX_MAX_MESSAGES`: Maximum messages per inbox (default: 20)

---

## Future Enhancements

### Phase 2: Database Persistence

**Table Schema:**
```sql
CREATE TABLE IF NOT EXISTS inbox_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_name TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    thread_id TEXT,
    received_tick INTEGER NOT NULL,
    needs_reply INTEGER NOT NULL DEFAULT 0,
    replied_tick INTEGER,
    channel TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
    FOREIGN KEY(sender_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE INDEX idx_inbox_person_needs_reply 
ON inbox_messages(person_id, needs_reply);
```

**Benefits:**
- Persistence across simulation restarts
- Historical analysis of message flow
- Metrics on response times

### Advanced Classification

**Machine Learning:**
- Train classifier on actual workplace messages
- Improve accuracy beyond keyword matching
- Support more nuanced message types

**Sentiment Analysis:**
- Detect urgency levels
- Identify emotional tone
- Prioritize based on sentiment

---

## Troubleshooting

### Issue: Messages not being classified correctly

**Symptoms:** Messages classified as 'report' when they should be 'question'

**Solution:**
- Check if keywords are present in subject or body
- Verify language (Korean vs English)
- Add custom keywords if needed

### Issue: Inbox not prioritizing replies

**Symptoms:** get_inbox() returns messages in wrong order

**Solution:**
- Verify `needs_reply` flag is set correctly
- Check classification logic
- Ensure messages are added with correct classification

### Issue: Memory usage growing

**Symptoms:** Simulation slows down over time

**Solution:**
- Verify 20-message limit is enforced
- Check for memory leaks in message objects
- Consider enabling database persistence (Phase 2)

---

## Related Modules

- **CommunicationGenerator**: Uses inbox messages for reply context
- **ParticipationBalancer**: May use inbox stats for balancing
- **Engine**: Integrates inbox tracking with message delivery
- **Style Filter**: Applies to both original and reply messages

---

## References

- **Requirements:** `.kiro/specs/communication-diversity/requirements.md`
- **Design:** `.kiro/specs/communication-diversity/design_v2.md`
- **Tasks:** `.kiro/specs/communication-diversity/tasks.md`
- **Tests:** `tests/test_inbox_manager.py`

---

**Last Updated:** 2025-11-05  
**Status:** ✅ Implemented and Tested
