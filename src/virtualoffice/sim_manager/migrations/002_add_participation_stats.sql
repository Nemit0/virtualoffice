-- Migration: Add participation_stats table for message balancing
-- Date: 2025-11-05
-- Requirements: R-5.1, R-12.1

CREATE TABLE IF NOT EXISTS participation_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    day_index INTEGER NOT NULL,
    email_count INTEGER NOT NULL DEFAULT 0,
    chat_count INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL DEFAULT 0,
    probability_modifier REAL NOT NULL DEFAULT 1.0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
    UNIQUE(person_id, day_index)
);

-- Index for efficient day-based queries
CREATE INDEX IF NOT EXISTS idx_participation_day 
ON participation_stats(day_index);

-- Index for efficient person lookup
CREATE INDEX IF NOT EXISTS idx_participation_person 
ON participation_stats(person_id);
