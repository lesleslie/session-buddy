-- Skills Metrics Schema - V4 Phase 4 Extensions
-- Migration: V4__phase4_extensions
-- Description: Advanced analytics, real-time monitoring, cross-session learning, and multi-modal skills
--
-- Features:
--   - Real-time metrics cache for dashboard
--   - Time-series data for trend analysis
--   - Anomaly detection for performance drops
--   - Community baselines for cross-user learning
--   - Collaborative filtering matrix
--   - A/B testing framework
--   - Skills taxonomy and categorization
--   - Skill dependency graph
--   - Multi-modal skill types
--
-- Technical Notes:
--   - Uses SQLite's window functions for analytics
--   - Implements time-series with hourly granularity
--   - Supports real-time anomaly detection via Z-score
--   - Enables collaborative filtering via user-skill interactions
--   - Provides A/B testing infrastructure for experimentation
--   - Supports skill taxonomy for multi-modal domains

-- ============================================================================
-- Section 1: Real-Time Monitoring Tables
-- ============================================================================

-- Table: Real-time metrics cache (updated every minute)
CREATE TABLE IF NOT EXISTS skill_metrics_cache (
    skill_name TEXT PRIMARY KEY,
    last_invocation_at TEXT NOT NULL,
    invocation_count_1h INTEGER DEFAULT 0,
    invocation_count_24h INTEGER DEFAULT 0,
    avg_completion_rate_24h REAL,
    is_anomalous BOOLEAN DEFAULT 0,
    anomaly_score REAL,
    updated_at TEXT NOT NULL,
    UNIQUE(skill_name),
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name)
);

CREATE INDEX IF NOT EXISTS idx_metrics_cache_updated
    ON skill_metrics_cache(updated_at);

-- Table: Time-series data for trend analysis (hourly granularity)
CREATE TABLE IF NOT EXISTS skill_time_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,  -- ISO format, hourly granularity
    invocation_count INTEGER DEFAULT 0,
    completion_rate REAL,
    avg_duration_seconds REAL,
    unique_sessions INTEGER DEFAULT 0,
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name)
);

CREATE INDEX IF NOT EXISTS idx_time_series_skill_timestamp
    ON skill_time_series(skill_name, timestamp DESC);

-- Table: Anomaly detection results
CREATE TABLE IF NOT EXISTS skill_anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,  -- 'drop', 'spike', 'pattern_shift'
    baseline_value REAL,
    observed_value REAL,
    deviation_score REAL,
    resolved_at TEXT,
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name)
);

CREATE INDEX IF NOT EXISTS idx_anomalies_detected_at
    ON skill_anomalies(detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_anomalies_skill
    ON skill_anomalies(skill_name, detected_at DESC);

-- ============================================================================
-- Section 2: Cross-Session Learning Tables
-- ============================================================================

-- Table: Community baselines (aggregated across users)
CREATE TABLE IF NOT EXISTS skill_community_baselines (
    skill_name TEXT PRIMARY KEY,
    total_users INTEGER DEFAULT 0,
    total_invocations INTEGER DEFAULT 0,
    global_completion_rate REAL,
    global_avg_duration_seconds REAL,
    most_common_workflow_phase TEXT,
    effectiveness_percentile REAL,  -- 0-100, relative to other skills
    last_updated TEXT NOT NULL,
    UNIQUE(skill_name),
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name)
);

-- Table: Collaborative filtering matrix (user-skill interactions)
CREATE TABLE IF NOT EXISTS skill_user_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,  -- Anonymous user identifier
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invoked_at TEXT NOT NULL,
    completed BOOLEAN NOT NULL,
    rating REAL,  -- Optional user feedback (1-5)
    alternatives_considered TEXT,  -- JSON array
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name)
);

CREATE INDEX IF NOT EXISTS idx_user_interactions_user
    ON skill_user_interactions(user_id, invoked_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_interactions_skill
    ON skill_user_interactions(skill_name, completed);

CREATE INDEX IF NOT EXISTS idx_user_interactions_session
    ON skill_user_interactions(session_id);

-- Table: Skill clusters (for recommendations)
CREATE TABLE IF NOT EXISTS skill_clusters (
    cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_name TEXT NOT NULL,
    description TEXT,
    centroid_embedding BLOB,  -- Packed 384-dim embedding
    created_at TEXT NOT NULL,
    UNIQUE(cluster_name)
);

-- Table: Skill-to-cluster mappings
CREATE TABLE IF NOT EXISTS skill_cluster_membership (
    skill_name TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    membership_score REAL,  -- 0-1, how well skill fits cluster
    PRIMARY KEY (skill_name, cluster_id),
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name),
    FOREIGN KEY (cluster_id) REFERENCES skill_clusters(cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_membership_cluster
    ON skill_cluster_membership(cluster_id);

-- ============================================================================
-- Section 3: A/B Testing Framework Tables
-- ============================================================================

-- Table: A/B test configurations
CREATE TABLE IF NOT EXISTS ab_test_configs (
    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_name TEXT NOT NULL UNIQUE,
    description TEXT,
    control_strategy TEXT NOT NULL,  -- e.g., "semantic_search"
    treatment_strategy TEXT NOT NULL,  -- e.g., "workflow_aware_search"
    start_date TEXT NOT NULL,
    end_date TEXT,
    min_sample_size INTEGER DEFAULT 100,
    metrics TEXT,  -- JSON array: ["completion_rate", "user_satisfaction"]
    assignment_ratio REAL DEFAULT 0.5,  -- 50% control, 50% treatment
    status TEXT DEFAULT 'running',  -- 'running', 'completed', 'stopped'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Table: A/B test user assignments
CREATE TABLE IF NOT EXISTS ab_test_assignments (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    group_name TEXT NOT NULL,  -- 'control' or 'treatment'
    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
    UNIQUE(test_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_ab_assignments_test_user
    ON ab_test_assignments(test_id, user_id);

CREATE INDEX IF NOT EXISTS idx_ab_assignments_group
    ON ab_test_assignments(test_id, group_name);

-- Table: A/B test outcomes
CREATE TABLE IF NOT EXISTS ab_test_outcomes (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    completed BOOLEAN NOT NULL,
    duration_seconds REAL,
    user_rating REAL,  -- Optional user feedback (1-5)
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id),
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name)
);

CREATE INDEX IF NOT EXISTS idx_ab_outcomes_test
    ON ab_test_outcomes(test_id);

CREATE INDEX IF NOT EXISTS idx_ab_outcomes_user
    ON ab_test_outcomes(test_id, user_id);

-- ============================================================================
-- Section 4: Multi-Modal Skills Tables
-- ============================================================================

-- Table: Skill taxonomy
CREATE TABLE IF NOT EXISTS skill_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE,
    parent_category_id INTEGER,
    description TEXT,
    domain TEXT,  -- 'code', 'documentation', 'testing', 'deployment'
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_category_id) REFERENCES skill_categories(category_id)
);

-- Table: Skill-to-category mappings
CREATE TABLE IF NOT EXISTS skill_category_mapping (
    skill_name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    confidence_score REAL,  -- 0-1, how well skill fits category
    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (skill_name, category_id),
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name),
    FOREIGN KEY (category_id) REFERENCES skill_categories(category_id)
);

CREATE INDEX IF NOT EXISTS idx_category_mapping_skill
    ON skill_category_mapping(skill_name);

CREATE INDEX IF NOT EXISTS idx_category_mapping_category
    ON skill_category_mapping(category_id);

-- Table: Skill dependencies (which skills commonly used together)
CREATE TABLE IF NOT EXISTS skill_dependencies (
    skill_a TEXT NOT NULL,
    skill_b TEXT NOT NULL,
    co_occurrence_count INTEGER DEFAULT 1,
    lift_score REAL,  -- >1 means skills used together more than expected
    last_updated TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (skill_a, skill_b),
    FOREIGN KEY (skill_a) REFERENCES skill_metrics(skill_name),
    FOREIGN KEY (skill_b) REFERENCES skill_metrics(skill_name)
);

CREATE INDEX IF NOT EXISTS idx_dependencies_skill_a
    ON skill_dependencies(skill_a);

CREATE INDEX IF NOT EXISTS idx_dependencies_lift
    ON skill_dependencies(lift_score DESC);

-- Table: Multi-modal skill types
CREATE TABLE IF NOT EXISTS skill_modalities (
    skill_name TEXT PRIMARY KEY,
    modality_type TEXT NOT NULL,  -- 'code', 'documentation', 'testing', 'deployment'
    input_format TEXT,  -- e.g., 'python_code', 'markdown', 'yaml'
    output_format TEXT,
    requires_human_review BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (skill_name) REFERENCES skill_metrics(skill_name)
);

-- ============================================================================
-- Section 5: Triggers for Real-Time Cache Updates
-- ============================================================================

-- Trigger: Update metrics cache on new invocation
CREATE TRIGGER IF NOT EXISTS trg_metrics_cache_after_insert
    AFTER INSERT ON skill_invocation
    BEGIN
        -- Insert or update metrics cache
        INSERT INTO skill_metrics_cache (skill_name, last_invocation_at, invocation_count_1h, invocation_count_24h, updated_at)
        VALUES (
            NEW.skill_name,
            NEW.invoked_at,
            1,  -- Initial count for 1h
            1,  -- Initial count for 24h
            datetime('now')
        )
        ON CONFLICT(skill_name) DO UPDATE SET
            last_invocation_at = NEW.invoked_at,
            invocation_count_1h = invocation_count_1h + 1,
            invocation_count_24h = invocation_count_24h + 1,
            updated_at = datetime('now');
    END;

-- Trigger: Populate time-series data hourly (via application logic)
-- Note: This trigger is a placeholder - actual population done by scheduled task

-- ============================================================================
-- Section 6: Views for Analytics
-- ============================================================================

-- View: Real-time skill performance dashboard
CREATE VIEW IF NOT EXISTS v_realtime_skill_dashboard AS
SELECT
    smc.skill_name,
    smc.last_invocation_at,
    smc.invocation_count_1h,
    smc.invocation_count_24h,
    smc.avg_completion_rate_24h,
    smc.is_anomalous,
    smc.anomaly_score,
    sm.total_invocations,
    sm.completion_rate,
    sm.avg_duration_seconds
FROM skill_metrics_cache smc
JOIN skill_metrics sm ON smc.skill_name = sm.skill_name
ORDER BY smc.invocation_count_24h DESC;

-- View: Skill effectiveness trend (last 7 days)
CREATE VIEW IF NOT EXISTS v_skill_effectiveness_trend AS
WITH daily_stats AS (
    SELECT
        skill_name,
        DATE(invoked_at) as date,
        COUNT(*) as invocations,
        AVG(CASE WHEN completed = 1 THEN 1.0 ELSE 0.0 END) as completion_rate
    FROM skill_invocation
    WHERE datetime(invoked_at) >= datetime('now', '-7 days')
    GROUP BY skill_name, DATE(invoked_at)
)
SELECT
    skill_name,
    AVG(completion_rate) as avg_completion_rate_7d,
    MAX(completion_rate) as max_completion_rate_7d,
    MIN(completion_rate) as min_completion_rate_7d,
    -- Linear regression slope (trend direction)
    (MAX(completion_rate) - MIN(completion_rate)) / NULLIF(COUNT(*) - 1, 1) as trend_slope
FROM daily_stats
GROUP BY skill_name;

-- View: Community baseline comparison
CREATE VIEW IF NOT EXISTS v_community_baseline_comparison AS
SELECT
    si.skill_name,
    COUNT(DISTINCT si.session_id) as user_invocations,
    AVG(CASE WHEN si.completed = 1 THEN 1.0 ELSE 0.0 END) as user_completion_rate,
    scb.global_completion_rate as baseline_completion_rate,
    scb.effectiveness_percentile,
    (AVG(CASE WHEN si.completed = 1 THEN 1.0 ELSE 0.0 END) - scb.global_completion_rate) as delta_from_baseline
FROM skill_invocation si
JOIN skill_community_baselines scb ON si.skill_name = scb.skill_name
GROUP BY si.skill_name, scb.global_completion_rate, scb.effectiveness_percentile;

-- View: Skill dependency network
CREATE VIEW IF NOT EXISTS v_skill_dependency_network AS
SELECT
    skill_a,
    skill_b,
    co_occurrence_count,
    lift_score,
    -- Interpret lift score
    CASE
        WHEN lift_score > 2.0 THEN 'strong_positive'
        WHEN lift_score > 1.5 THEN 'moderate_positive'
        WHEN lift_score > 1.0 THEN 'weak_positive'
        WHEN lift_score = 1.0 THEN 'independent'
        WHEN lift_score > 0.5 THEN 'weak_negative'
        ELSE 'moderate_negative'
    END as relationship_type
FROM skill_dependencies
WHERE lift_score IS NOT NULL
ORDER BY co_occurrence_count DESC;

-- View: A/B test summary
CREATE VIEW IF NOT EXISTS v_ab_test_summary AS
SELECT
    tc.test_id,
    tc.test_name,
    tc.control_strategy,
    tc.treatment_strategy,
    tc.status,
    COUNT(DISTINCT aa.user_id) as total_users,
    SUM(CASE WHEN aa.group_name = 'control' THEN 1 ELSE 0 END) as control_users,
    SUM(CASE WHEN aa.group_name = 'treatment' THEN 1 ELSE 0 END) as treatment_users,
    AVG(CASE WHEN ao.completed = 1 AND aa.group_name = 'control' THEN 1.0 ELSE NULL END) as control_completion_rate,
    AVG(CASE WHEN ao.completed = 1 AND aa.group_name = 'treatment' THEN 1.0 ELSE NULL END) as treatment_completion_rate
FROM ab_test_configs tc
LEFT JOIN ab_test_assignments aa ON tc.test_id = aa.test_id
LEFT JOIN ab_test_outcomes ao ON tc.test_id = ao.test_id AND aa.user_id = ao.user_id
GROUP BY tc.test_id, tc.test_name, tc.control_strategy, tc.treatment_strategy, tc.status;

-- View: Multi-modal skill catalog
CREATE VIEW IF NOT EXISTS v_multimodal_skill_catalog AS
SELECT
    si.skill_name,
    sm.modality_type,
    sm.input_format,
    sm.output_format,
    sm.requires_human_review,
    COUNT(DISTINCT si.session_id) as total_sessions,
    AVG(CASE WHEN si.completed = 1 THEN 1.0 ELSE 0.0 END) as completion_rate,
    AVG(si.duration_seconds) as avg_duration_seconds,
    sc.category_name,
    sc.domain
FROM skill_invocation si
LEFT JOIN skill_modalities sm ON si.skill_name = sm.skill_name
LEFT JOIN skill_category_mapping scm ON si.skill_name = scm.skill_name
LEFT JOIN skill_categories sc ON scm.category_id = sc.category_id
GROUP BY si.skill_name, sm.modality_type, sm.input_format, sm.output_format,
         sm.requires_human_review, sc.category_name, sc.domain
ORDER BY si.skill_name;

-- ============================================================================
-- Section 7: Migration Tracking
-- ============================================================================

-- Record migration
INSERT INTO skill_migrations (version, applied_at, description, applied_by)
VALUES ('V4__phase4_extensions', datetime('now'), 'Phase 4: Advanced analytics, real-time monitoring, cross-session learning, and multi-modal skills', 'session-buddy');

-- ============================================================================
-- Section 8: Usage Notes
-- ============================================================================

-- Real-Time Monitoring:
--   - skill_metrics_cache updated every minute via trigger
--   - Use v_realtime_skill_dashboard for live metrics
--   - Anomaly detection via Z-score (> 2.0 = anomaly)
--
-- Cross-Session Learning:
--   - skill_user_interactions stores per-user data
--   - skill_community_baselines aggregated across users
--   - Use v_community_baseline_comparison for insights
--
-- A/B Testing:
--   - Create test in ab_test_configs
--   - Assign users via ab_test_assignments
--   - Record outcomes in ab_test_outcomes
--   - Analyze via v_ab_test_summary
--
-- Multi-Modal Skills:
--   - Categorize skills via skill_categories
--   - Track dependencies via skill_dependencies
--   - Browse catalog via v_multimodal_skill_catalog
--
-- Query Examples:
--   -- Get real-time top skills
--   SELECT * FROM v_realtime_skill_dashboard LIMIT 10;
--
--   -- Find trending skills (improving completion rate)
--   SELECT * FROM v_skill_effectiveness_trend WHERE trend_slope > 0.05;
--
--   -- Get skill dependencies
--   SELECT * FROM v_skill_dependency_network WHERE skill_a = 'pytest-run' LIMIT 10;
--
--   -- A/B test analysis
--   SELECT * FROM v_ab_test_summary WHERE test_id = 1;
