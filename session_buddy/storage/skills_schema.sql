-- Skills Metrics Storage Schema for Session-Buddy
--
-- This schema defines the persistent storage for skills tracking using
-- Dhruva (ACID-compliant storage).
--
-- Tables:
--   skill_invocation - Immutable event log (append-only)
--   skill_metrics - Aggregated metrics (mutable, updated via triggers)
--   session_skills - Junction table for session-skill relationships
--   skill_migrations - Schema version tracking
--
-- Key Design Decisions:
--   - Immutable invocations: never update, only append
--   - Denormalized metrics: pre-aggregated for fast reads
--   - Triggers: automatically update metrics on new invocations
--   - Foreign keys: enforce referential integrity
--   - WAL mode: enable concurrent readers/writers
--   - Indexes: optimize common query patterns

-- ============================================================================
-- Table: skill_invocation
-- Immutable event log of all skill invocations
-- ============================================================================
CREATE TABLE IF NOT EXISTS skill_invocation (
    -- Primary key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core fields
    skill_name TEXT NOT NULL,                -- Name of skill used
    invoked_at TEXT NOT NULL,                 -- ISO format timestamp
    session_id TEXT NOT NULL,                -- Session this belongs to

    -- Workflow context
    workflow_path TEXT,                       -- "quick", "comprehensive", etc.

    -- Completion tracking
    completed BOOLEAN NOT NULL DEFAULT 0,     -- 0 = False, 1 = True
    duration_seconds REAL,                    -- How long skill took (NULL if not completed)

    -- Semantic search context (enhanced features)
    user_query TEXT,                          -- User's problem description
    alternatives_considered TEXT,             -- JSON array of other skills shown
    selection_rank INTEGER,                   -- Position in recommendations (1=best)

    -- Outcomes
    follow_up_actions TEXT,                   -- JSON array of actions taken
    error_type TEXT,                          -- If skill failed

    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- Foreign keys
    CONSTRAINT fk_invocation_session
        FOREIGN KEY (session_id)
        REFERENCES session(id)
        ON DELETE CASCADE
);

-- Indexes for skill_invocation
-- Primary lookups by session and skill
CREATE INDEX IF NOT EXISTS idx_invocation_session
    ON skill_invocation(session_id);

CREATE INDEX IF NOT EXISTS idx_invocation_skill
    ON skill_invocation(skill_name);

CREATE INDEX IF NOT EXISTS idx_invocation_invoked_at
    ON skill_invocation(invoked_at DESC);

-- Composite index for session summaries
CREATE INDEX IF NOT EXISTS idx_invocation_session_completed
    ON skill_invocation(session_id, completed);

-- Full-text search on user queries (for semantic search analytics)
CREATE VIRTUAL TABLE IF NOT EXISTS skill_invocation_fts
    USING fts5(user_query, content=skill_invocation, content_rowid=id);

-- ============================================================================
-- Table: skill_metrics
-- Aggregated metrics per skill (denormalized for fast reads)
-- ============================================================================
CREATE TABLE IF NOT EXISTS skill_metrics (
    -- Primary key
    skill_name TEXT PRIMARY KEY,

    -- Invocation counts
    total_invocations INTEGER NOT NULL DEFAULT 0,
    completed_invocations INTEGER NOT NULL DEFAULT 0,
    abandoned_invocations INTEGER NOT NULL DEFAULT 0,

    -- Duration tracking
    total_duration_seconds REAL NOT NULL DEFAULT 0.0,

    -- Workflow preferences (JSON: {"quick": 10, "comprehensive": 5})
    workflow_paths TEXT NOT NULL DEFAULT '{}',

    -- Error patterns (JSON: {"timeout": 2, "validation": 1})
    common_errors TEXT NOT NULL DEFAULT '{}',

    -- Follow-up actions (JSON: {"git commit": 15, "continue": 8})
    follow_up_actions TEXT NOT NULL DEFAULT '{}',

    -- Recommendation effectiveness (enhanced features)
    avg_selection_rank REAL,
    recommendation_success_rate REAL,

    -- Timestamps
    first_invoked TEXT,
    last_invoked TEXT,

    -- Computed fields (updated via triggers)
    completion_rate REAL NOT NULL DEFAULT 0.0,
    avg_duration_seconds REAL NOT NULL DEFAULT 0.0,

    -- Metadata
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Triggers: Auto-update computed fields on INSERT/UPDATE
CREATE TRIGGER IF NOT EXISTS trg_skill_metrics_after_insert
    AFTER INSERT ON skill_invocation
    BEGIN
        -- Insert new skill metrics row if not exists
        INSERT OR IGNORE INTO skill_metrics (skill_name, first_invoked, last_invoked)
        VALUES (NEW.skill_name, NEW.invoked_at, NEW.invoked_at);

        -- Update invocations count
        UPDATE skill_metrics SET
            total_invocations = total_invocations + 1,
            last_invoked = NEW.invoked_at
        WHERE skill_name = NEW.skill_name;

        -- Update completion tracking
        IF NEW.completed = 1 THEN
            UPDATE skill_metrics SET
                completed_invocations = completed_invocations + 1,
                total_duration_seconds = total_duration_seconds + COALESCE(NEW.duration_seconds, 0)
            WHERE skill_name = NEW.skill_name;
        ELSE
            UPDATE skill_metrics SET
                abandoned_invocations = abandoned_invocations + 1
            WHERE skill_name = NEW.skill_name;
        END IF;

        -- Update workflow paths
        IF NEW.workflow_path IS NOT NULL THEN
            UPDATE skill_metrics SET
                workflow_paths = json_set(
                    workflow_paths,
                    '$.' || NEW.workflow_path,
                    COALESCE(
                        json_extract(workflow_paths, '$.' || NEW.workflow_path),
                        0
                    ) + 1
                )
            WHERE skill_name = NEW.skill_name;
        END IF;

        -- Update common errors
        IF NEW.error_type IS NOT NULL THEN
            UPDATE skill_metrics SET
                common_errors = json_set(
                    common_errors,
                    '$.' || NEW.error_type,
                    COALESCE(
                        json_extract(common_errors, '$.' || NEW.error_type),
                        0
                    ) + 1
                )
            WHERE skill_name = NEW.skill_name;
        END IF;

        -- Update follow-up actions
        IF NEW.follow_up_actions IS NOT NULL THEN
            UPDATE skill_metrics SET
                follow_up_actions = json_increment_items(
                    follow_up_actions,
                    NEW.follow_up_actions
                )
            WHERE skill_name = NEW.skill_name;
        END IF;

        -- Update computed fields
        UPDATE skill_metrics SET
            completion_rate = CAST(completed_invocations AS REAL) / NULLIF(total_invocations, 0) * 100.0,
            avg_duration_seconds = total_duration_seconds / NULLIF(completed_invocations, 0),
            updated_at = datetime('now')
        WHERE skill_name = NEW.skill_name;
    END;

-- Custom function to increment JSON object values (for follow_up_actions)
CREATE FUNCTION IF NOT EXISTS json_increment_items(
    target_json TEXT,
    items_json TEXT
) RETURNS TEXT
BEGIN
    DECLARE item TEXT;
    DECLARE count INTEGER;

    -- Parse items JSON array
    SET count = 0;

    -- Loop through items and increment counts
    FOR item IN (
        SELECT value FROM json_each(items_json)
    ) LOOP
        UPDATE skill_metrics SET
            follow_up_actions = json_set(
                follow_up_actions,
                '$.' || item,
                COALESCE(
                    json_extract(follow_up_actions, '$.' || item),
                    0
                ) + 1
            )
        WHERE skill_name = (SELECT skill_name FROM skill_invocation WHERE id = NEW.id);

        SET count = count + 1;
    END LOOP;

    RETURN (SELECT follow_up_actions FROM skill_metrics WHERE skill_name = (SELECT skill_name FROM skill_invocation WHERE id = NEW.id));
END;

-- ============================================================================
-- Table: session_skills
-- Junction table: Many-to-many relationship between sessions and skills
-- ============================================================================
CREATE TABLE IF NOT EXISTS session_skills (
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invocation_count INTEGER NOT NULL DEFAULT 1,

    PRIMARY KEY (session_id, skill_name),

    -- Foreign keys
    CONSTRAINT fk_session_skills_session
        FOREIGN KEY (session_id)
        REFERENCES session(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_session_skills_skill
        FOREIGN KEY (skill_name)
        REFERENCES skill_metrics(skill_name)
        ON DELETE CASCADE
);

-- Index for session skill queries
CREATE INDEX IF NOT EXISTS idx_session_skills_skill
    ON session_skills(skill_name);

-- Trigger: Update session_skills on new invocation
CREATE TRIGGER IF NOT EXISTS trg_session_skills_after_insert
    AFTER INSERT ON skill_invocation
    BEGIN
        -- Insert or update junction table
        INSERT INTO session_skills (session_id, skill_name, invocation_count)
        VALUES (NEW.session_id, NEW.skill_name, 1)
        ON CONFLICT(session_id, skill_name)
        DO UPDATE SET
            invocation_count = invocation_count + 1;
    END;

-- ============================================================================
-- Table: skill_migrations
-- Track schema version and migration history
-- ============================================================================
CREATE TABLE IF NOT EXISTS skill_migrations (
    version TEXT PRIMARY KEY,               -- Migration version (e.g., "V1__initial_schema")
    applied_at TEXT NOT NULL,                -- When migration was applied
    description TEXT,                         -- Human-readable description
    rollback_sql TEXT,                       -- SQL to rollback this migration
    checksum TEXT,                            -- Optional SHA256 checksum of SQL

    applied_by TEXT DEFAULT 'session-buddy', -- What applied this migration
    success BOOLEAN NOT NULL DEFAULT 1        -- Whether migration succeeded
);

-- Index for migration queries
CREATE INDEX IF NOT EXISTS idx_migrations_applied_at
    ON skill_migrations(applied_at DESC);

-- ============================================================================
-- Views: Common queries for analytics
-- ============================================================================

-- View: Session skill summary (quick lookup for a session)
CREATE VIEW IF NOT EXISTS v_session_skill_summary AS
SELECT
    session_id,
    COUNT(DISTINCT skill_name) as unique_skills,
    COUNT(*) as total_invocations,
    SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_count,
    SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) as abandoned_count,
    SUM(COALESCE(duration_seconds, 0)) as total_duration_seconds,
    MIN(invoked_at) as first_skill_at,
    MAX(invoked_at) as last_skill_at
FROM skill_invocation
GROUP BY session_id;

-- View: Skill effectiveness (completion rate by skill)
CREATE VIEW IF NOT EXISTS v_skill_effectiveness AS
SELECT
    skill_name,
    total_invocations,
    completed_invocations,
    abandoned_invocations,
    completion_rate,
    avg_duration_seconds,
    first_invoked,
    last_invoked,
    -- Compute most recent activity
    CAST(julianday('now') - julianday(last_invoked) AS INTEGER) as days_since_last_use
FROM skill_metrics
WHERE total_invocations > 0
ORDER BY total_invocations DESC;

-- View: Top skills by usage (aggregated stats)
CREATE VIEW IF NOT EXISTS v_top_skills AS
SELECT
    skill_name,
    total_invocations,
    completion_rate,
    avg_duration_seconds,
    -- Extract most used workflow path
    json_extract(workflow_paths, '$.' ||
        (SELECT key FROM json_each(workflow_paths)
         ORDER BY value DESC
         LIMIT 1
    ) as preferred_workflow
FROM skill_metrics
WHERE total_invocations > 0
ORDER BY total_invocations DESC;

-- ============================================================================
-- Materialized View: Daily skill usage (for time-series analytics)
-- Refresh periodically: REFRESH MATERIALIZED VIEW mv_daily_skills
-- ============================================================================
CREATE TABLE IF NOT EXISTS mv_daily_skills (
    date TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invocations INTEGER NOT NULL,
    completions INTEGER NOT NULL,
    abandonments INTEGER NOT NULL,
    avg_duration_seconds REAL,
    PRIMARY KEY (date, skill_name)
);

CREATE INDEX IF NOT EXISTS idx_mv_daily_date
    ON mv_daily_skills(date DESC);

CREATE INDEX IF NOT EXISTS idx_mv_daily_skill
    ON mv_daily_skills(skill_name);

-- View to populate materialized view
CREATE VIEW IF NOT EXISTS v_daily_skill_source AS
SELECT
    DATE(invoked_at) as date,
    skill_name,
    COUNT(*) as invocations,
    SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completions,
    SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) as abandonments,
    AVG(CASE WHEN completed = 1 THEN duration_seconds END) as avg_duration_seconds
FROM skill_invocation
GROUP BY DATE(invoked_at), skill_name;

-- ============================================================================
-- Helper functions for common operations
-- ============================================================================

-- Function: Get skill metrics for a session
CREATE FUNCTION IF NOT EXISTS get_session_skill_metrics(p_session_id TEXT)
RETURNS TABLE (
    skill_name TEXT,
    invocation_count INTEGER,
    completion_count INTEGER,
    avg_duration REAL
)
AS $$
BEGIN
    RETURN QUERY
    SELECT
        si.skill_name,
        COUNT(*) as invocation_count,
        SUM(CASE WHEN si.completed = 1 THEN 1 ELSE 0 END) as completion_count,
        AVG(CASE WHEN si.completed = 1 THEN si.duration_seconds END) as avg_duration
    FROM skill_invocation si
    WHERE si.session_id = p_session_id
    GROUP BY si.skill_name
    ORDER BY invocation_count DESC;
END;
$$ LANGUAGE plpgsql;

-- Function: Get top N skills by usage
CREATE FUNCTION IF NOT EXISTS get_top_skills(p_limit INTEGER)
RETURNS TABLE (
    skill_name TEXT,
    total_invocations INTEGER,
    completion_rate REAL,
    avg_duration_seconds REAL
)
AS $$
BEGIN
    RETURN QUERY
    SELECT
        skill_name,
        total_invocations,
        completion_rate,
        avg_duration_seconds
    FROM skill_metrics
    ORDER BY total_invocations DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Initial data seeding (optional, for testing)
-- ============================================================================

-- No default data needed - schema is empty by default
-- Migrations will populate as skills are used

-- ============================================================================
-- Schema validation
-- ============================================================================

-- Enable WAL mode for concurrent access
PRAGMA journal_mode = WAL;

-- Optimize for performance
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;  -- 64MB cache
PRAGMA temp_store = MEMORY;

-- Foreign key constraints (enforce referential integrity)
PRAGMA foreign_keys = ON;

-- ============================================================================
-- Migration tracking
-- ============================================================================

-- Record this schema version
INSERT INTO skill_migrations (version, applied_at, description, applied_by)
VALUES (
    'V1__initial_schema',
    datetime('now'),
    'Initial skills metrics schema with invocations, metrics, and session tracking',
    'session-buddy'
);
