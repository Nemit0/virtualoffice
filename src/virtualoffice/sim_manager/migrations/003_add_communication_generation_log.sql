-- Migration: Add communication_generation_log table for observability
-- Date: 2025-11-05
-- Requirements: O-2, O-6

CREATE TABLE IF NOT EXISTS communication_generation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    generation_type TEXT NOT NULL CHECK(generation_type IN ('json', 'gpt_fallback', 'template')),
    channel TEXT NOT NULL CHECK(channel IN ('email', 'chat')),
    success INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    token_count INTEGER,
    latency_ms INTEGER,
    context_size INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);

-- Index for efficient person-tick queries
CREATE INDEX IF NOT EXISTS idx_comm_gen_person_tick 
ON communication_generation_log(person_id, tick);

-- Index for efficient type-based analysis
CREATE INDEX IF NOT EXISTS idx_comm_gen_type 
ON communication_generation_log(generation_type);

-- Index for efficient tick-based queries
CREATE INDEX IF NOT EXISTS idx_comm_gen_tick 
ON communication_generation_log(tick);
