-- Skills Metrics Storage Schema - V1 Rollback
-- Migration: V1__initial_schema (DOWN)
-- Description: Rollback initial skills metrics schema
--
-- This script removes all tables, views, indexes, triggers, and functions
-- created by the V1__initial_schema migration.
--
-- Drop order (respecting dependencies):
-- 1. Functions (depend on nothing)
-- 2. Views (depend on tables)
-- 3. Triggers (depend on tables)
-- 4. Tables (depend on indexes)
-- 5. Indexes (dropped with tables)

-- ============================================================================
-- Drop Views
-- ============================================================================

DROP VIEW IF EXISTS v_daily_skill_source;
DROP VIEW IF EXISTS v_top_skills;
DROP VIEW IF EXISTS v_skill_effectiveness;
DROP VIEW IF EXISTS v_session_skill_summary;

-- ============================================================================
-- Drop Materialized View Table
-- ============================================================================

DROP TABLE IF EXISTS mv_daily_skills;

-- ============================================================================
-- Drop Full-Text Search Table
-- ============================================================================

DROP TABLE IF EXISTS skill_invocation_fts;

-- ============================================================================
-- Drop Triggers
-- ============================================================================

DROP TRIGGER IF EXISTS trg_session_skills_after_insert;
DROP TRIGGER IF EXISTS trg_skill_metrics_after_insert;

-- ============================================================================
-- Drop Tables (in dependency order)
-- ============================================================================

-- Drop junction table first (has foreign keys)
DROP TABLE IF EXISTS session_skills;

-- Drop metrics table (referenced by session_skills)
DROP TABLE IF EXISTS skill_metrics;

-- Drop invocations table (core table)
DROP TABLE IF EXISTS skill_invocation;

-- Drop migrations table last (tracks schema changes)
DROP TABLE IF EXISTS skill_migrations;
