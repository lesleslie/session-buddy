-- Skills Metrics Schema - V3 Workflow Correlation
-- Migration: V3__add_workflow_correlation
-- Description: Add Oneiric workflow phase tracking for skills
--
-- Features:
--   - Add workflow_phase column to track Oneiric workflow phases
--   - Add workflow_step_id for correlation with Oneiric DAG steps
--   - Add indexes for workflow-based queries
--   - Enable cross-phase skill effectiveness analytics
--
-- Technical Notes:
--   - workflow_phase: TEXT field (e.g., "setup", "execution", "verification")
--   - workflow_step_id: TEXT field (Oneiric step identifier)
--   - Enables workflow-aware skill recommendations
--   - Supports bottleneck identification by phase

-- ============================================================================
-- Add Workflow Tracking Columns
-- ============================================================================

-- Add workflow phase column
ALTER TABLE skill_invocation ADD COLUMN workflow_phase TEXT;

-- Add Oneiric step ID column
ALTER TABLE skill_invocation ADD COLUMN workflow_step_id TEXT;

-- ============================================================================
-- Create Indexes for Workflow Queries
-- ============================================================================

-- Index on workflow_phase for phase-based analytics
CREATE INDEX IF NOT EXISTS idx_invocation_workflow_phase
    ON skill_invocation(workflow_phase)
    WHERE workflow_phase IS NOT NULL;

-- Index on workflow_step_id for step correlation
CREATE INDEX IF NOT EXISTS idx_invocation_workflow_step
    ON skill_invocation(workflow_step_id)
    WHERE workflow_step_id IS NOT NULL;

-- Composite index for phase + completion (useful for bottleneck detection)
CREATE INDEX IF NOT EXISTS idx_invocation_phase_completion
    ON skill_invocation(workflow_phase, completed)
    WHERE workflow_phase IS NOT NULL;

-- ============================================================================
-- Create Views for Workflow Analytics
-- ============================================================================

-- View: Skill effectiveness by workflow phase
CREATE VIEW IF NOT EXISTS v_skill_effectiveness_by_phase AS
SELECT
    skill_name,
    workflow_phase,
    COUNT(*) as total_invocations,
    SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_count,
    SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) as abandoned_count,
    AVG(CASE WHEN completed = 1 THEN duration_seconds END) as avg_duration_seconds,
    AVG(CASE WHEN completed = 1 THEN duration_seconds END) as avg_completion_time,
    CAST(SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100.0 as completion_rate
FROM skill_invocation
WHERE workflow_phase IS NOT NULL
GROUP BY skill_name, workflow_phase;

-- View: Workflow phase transition patterns
CREATE VIEW IF NOT EXISTS v_workflow_phase_patterns AS
SELECT
    workflow_phase,
    COUNT(*) as invocations_in_phase,
    COUNT(DISTINCT skill_name) as unique_skills_in_phase,
    SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as successful_completions,
    AVG(CASE WHEN duration_seconds IS NOT NULL THEN duration_seconds END) as avg_phase_duration
FROM skill_invocation
WHERE workflow_phase IS NOT NULL
GROUP BY workflow_phase
ORDER BY workflow_phase;

-- View: Skills by workflow phase usage
CREATE VIEW IF NOT EXISTS v_skills_by_phase_usage AS
SELECT
    skill_name,
    workflow_phase,
    COUNT(*) as usage_count,
    AVG(CASE WHEN completed = 1 THEN 1.0 ELSE 0.0 END) as success_rate
FROM skill_invocation
WHERE workflow_phase IS NOT NULL
GROUP BY skill_name, workflow_phase
ORDER BY skill_name, workflow_phase;

-- ============================================================================
-- Migration Tracking
-- ============================================================================

-- Record migration
INSERT INTO skill_migrations (version, applied_at, description, applied_by)
VALUES ('V3__add_workflow_correlation', datetime('now'), 'Add Oneiric workflow phase tracking for skills', 'session-buddy');

-- ============================================================================
-- Usage Notes
-- ============================================================================

-- Workflow Phase Values (recommended):
--   - "setup": Initial configuration and preparation
--   - "execution": Main task execution
--   - "verification": Testing and validation
--   - "cleanup": Post-task cleanup
--   - "rollback": Error recovery and rollback
--
-- Oneiric Step ID Format:
--   - Uses Oneiric's step identifier format
--   - Enables correlation with Oneiric DAG execution
--   - Useful for tracing which workflow steps used which skills
--
-- Query Examples:
--   -- Get skill effectiveness by phase
--   SELECT * FROM v_skill_effectiveness_by_phase WHERE skill_name = 'pytest-run';
--
--   -- Find bottlenecks (high abandonment in a phase)
--   SELECT workflow_phase, abandoned_count, total_invocations,
--          CAST(abandoned_count AS FLOAT) / total_invocations AS bottleneck_score
--   FROM v_skill_effectiveness_by_phase
--   GROUP BY workflow_phase
--   ORDER BY bottleneck_score DESC;
--
--   -- Track skill usage patterns across phases
--   SELECT * FROM v_skills_by_phase_usage WHERE skill_name = 'ruff-check';
