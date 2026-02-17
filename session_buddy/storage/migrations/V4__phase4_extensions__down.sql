-- Skills Metrics Schema - V4 Phase 4 Extensions Rollback
-- Migration: V4__phase4_extensions (down)
-- Description: Rollback Phase 4 extensions (real-time monitoring, cross-session learning, A/B testing, multi-modal skills)
--
-- WARNING: This will DELETE all Phase 4 data!
-- - Time-series data
-- - Community baselines
-- - A/B test results
-- - Skill taxonomy
-- - Dependency graph
--
-- Ensure you have backups before running this migration!

-- ============================================================================
-- Section 1: Drop Views
-- ============================================================================

DROP VIEW IF EXISTS v_multimodal_skill_catalog;
DROP VIEW IF EXISTS v_ab_test_summary;
DROP VIEW IF EXISTS v_skill_dependency_network;
DROP VIEW IF EXISTS v_community_baseline_comparison;
DROP VIEW IF EXISTS v_skill_effectiveness_trend;
DROP VIEW IF EXISTS v_realtime_skill_dashboard;

-- ============================================================================
-- Section 2: Drop Triggers
-- ============================================================================

DROP TRIGGER IF EXISTS trg_metrics_cache_after_insert;

-- ============================================================================
-- Section 3: Drop Multi-Modal Skills Tables
-- ============================================================================

DROP TABLE IF EXISTS skill_modalities;
DROP TABLE IF EXISTS skill_dependencies;
DROP TABLE IF EXISTS skill_category_mapping;
DROP TABLE IF EXISTS skill_categories;

-- ============================================================================
-- Section 4: Drop A/B Testing Tables
-- ============================================================================

DROP TABLE IF EXISTS ab_test_outcomes;
DROP TABLE IF EXISTS ab_test_assignments;
DROP TABLE IF EXISTS ab_test_configs;

-- ============================================================================
-- Section 5: Drop Cross-Session Learning Tables
-- ============================================================================

DROP TABLE IF EXISTS skill_cluster_membership;
DROP TABLE IF EXISTS skill_clusters;
DROP TABLE IF EXISTS skill_user_interactions;
DROP TABLE IF EXISTS skill_community_baselines;

-- ============================================================================
-- Section 6: Drop Real-Time Monitoring Tables
-- ============================================================================

DROP TABLE IF EXISTS skill_anomalies;
DROP TABLE IF EXISTS skill_time_series;
DROP TABLE IF EXISTS skill_metrics_cache;

-- ============================================================================
-- Section 7: Remove Migration Record
-- ============================================================================

DELETE FROM skill_migrations WHERE version = 'V4__phase4_extensions';

-- ============================================================================
-- Rollback Complete
-- ============================================================================

-- Database is now back to V3 schema
-- All V4 data has been permanently deleted
