-- Migration: Add inbox_messages table for email threading and reply tracking
-- Date: 2025-11-05
-- Requirements: R-2.3, R-12.1

CREATE TABLE IF NOT EXISTS inbox_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    message_id TEXT NOT NULL,
    message_type TEXT NOT NULL CHECK(message_type IN ('email', 'chat')),
    sender_id INTEGER NOT NULL,
    sender_name TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    thread_id TEXT,
    received_tick INTEGER NOT NULL,
    needs_reply INTEGER NOT NULL DEFAULT 1,
    replied_tick INTEGER,
    message_category TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
    FOREIGN KEY(sender_id) REFERENCES people(id) ON DELETE CASCADE
);

-- Index for efficient inbox queries
CREATE INDEX IF NOT EXISTS idx_inbox_person_needs_reply 
ON inbox_messages(person_id, needs_reply);

-- Index for efficient message lookup
CREATE INDEX IF NOT EXISTS idx_inbox_message_id 
ON inbox_messages(message_id);

-- Index for efficient tick-based queries
CREATE INDEX IF NOT EXISTS idx_inbox_received_tick 
ON inbox_messages(received_tick);
