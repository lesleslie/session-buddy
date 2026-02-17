-- Skills Metrics Schema - V2 Rollback
-- Migration: V2__add_semantic_search (rollback)
-- Description: Remove vector embedding support
--
-- WARNING: This will permanently delete all stored embeddings!
-- Make sure to backup database before rolling back.

-- ============================================================================
-- Remove Migration Record
-- ============================================================================

DELETE FROM skill_migrations WHERE version = 'V2__add_semantic_search';

-- ============================================================================
-- Drop Index
-- ============================================================================

DROP INDEX IF EXISTS idx_invocation_embedding;

-- ============================================================================
-- Drop Embedding Column
-- ============================================================================

-- SQLite doesn't support DROP COLUMN directly
-- Need to recreate table without embedding column

BEGIN TRANSACTION;

-- Create new table without embedding column
CREATE TABLE skill_invocation_new (
    -- Primary key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core fields
    skill_name TEXT NOT NULL,
    invoked_at TEXT NOT NULL,
    session_id TEXT NOT NULL,

    -- Workflow context
    workflow_path TEXT,

    -- Completion tracking
    completed BOOLEAN NOT NULL DEFAULT 0,
    duration_seconds REAL,

    -- Semantic search context
    user_query TEXT,
    alternatives_considered TEXT,
    selection_rank INTEGER,

    -- Outcomes
    follow_up_actions TEXT,
    error_type TEXT,

    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Copy data (excluding embeddings)
INSERT INTO skill_invocation_new
SELECT
    id, skill_name, invoked_at, session_id, workflow_path,
    completed, duration_seconds, user_query, alternatives_considered,
    selection_rank, follow_up_actions, error_type, created_at
FROM skill_invocation;

-- Drop old table
DROP TABLE skill_invocation;

-- Rename new table
ALTER TABLE skill_invocation_new RENAME TO skill_invocation;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS idx_invocation_session
    ON skill_invocation(session_id);

CREATE INDEX IF NOT EXISTS idx_invocation_skill
    ON skill_invocation(skill_name);

CREATE INDEX IF NOT EXISTS idx_invocation_invoked_at
    ON skill_invocation(invoked_at DESC);

CREATE INDEX IF NOT EXISTS idx_invocation_session_completed
    ON skill_invocation(session_id, completed);

COMMIT;

-- ============================================================================
-- Notes
-- ============================================================================

-- Rollback complete. All embeddings have been permanently deleted.
-- Future re-application of V2 migration will require regenerating
-- embeddings for all existing invocations.
