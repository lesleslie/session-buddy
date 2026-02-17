-- Skills Metrics Schema - V3 Rollback
-- Migration: V3__add_workflow_correlation (rollback)
-- Description: Remove Oneiric workflow phase tracking
--
-- WARNING: This will permanently delete workflow phase tracking data!
-- Make sure to backup database before rolling back.

-- ============================================================================
-- Remove Migration Record
-- ============================================================================

DELETE FROM skill_migrations WHERE version = 'V3__add_workflow_correlation';

-- ============================================================================
-- Drop Views
-- ============================================================================

DROP VIEW IF EXISTS v_skills_by_phase_usage;
DROP VIEW IF EXISTS v_workflow_phase_patterns;
DROP VIEW IF EXISTS v_skill_effectiveness_by_phase;

-- ============================================================================
-- Drop Indexes
-- ============================================================================

DROP INDEX IF EXISTS idx_invocation_phase_completion;
DROP INDEX IF EXISTS idx_invocation_workflow_step;
DROP INDEX IF EXISTS idx_invocation_workflow_phase;

-- ============================================================================
-- Drop Columns
-- ============================================================================

-- SQLite doesn't support DROP COLUMN directly
-- Need to recreate table without workflow columns

BEGIN TRANSACTION;

-- Create new table without workflow columns
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

    -- Embeddings (V2)
    embedding BLOB,

    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Copy data (excluding workflow columns)
INSERT INTO skill_invocation_new
SELECT
    id, skill_name, invoked_at, session_id, workflow_path,
    completed, duration_seconds, user_query, alternatives_considered,
    selection_rank, follow_up_actions, error_type, embedding, created_at
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

CREATE INDEX IF NOT EXISTS idx_invocation_embedding
    ON skill_invocation(embedding)
    WHERE embedding IS NOT NULL;

COMMIT;

-- ============================================================================
-- Notes
-- ============================================================================

-- Rollback complete. All workflow phase tracking data has been permanently deleted.
-- Future re-application of V3 migration will require re-tagging invocations
-- with their workflow phases.
