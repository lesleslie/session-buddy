-- UUID7 Consolidation Migration - Script 006: Drop Vestigial Tables
-- Migration: 006_drop_vestigial
-- Plan: docs/plans/2026-10-11-uuid7-only-migration.md (Phase 0, script 6 of 10)
-- Description: Remove vestigial tables that were left behind by earlier storage
--              experiments and ULID-shape infrastructure. Their content was either
--              absorbed by Phase 0 scripts 001 (conversations -> conversations) and
--              003 (reflections_v2 -> reflections, default_reflections -> reflections)
--              or was never used in production.
--
-- Tables dropped (vestigial-only after B-step adversarial review 2026-10-11):
--   access_log_v2     -- superseded by memory_access_log (renamed/preserved
--                         with UUID7 PKs in script 007); the _v2 variant was
--                         dead-on-arrival scaffolding from a prior experiment
--   query_cache_l2    -- L2 query cache never wired into the read path; the
--                         hot store is the in-process reflection cache plus
--                         DuckDB FTS, not a SQLite L2
--
-- Tables REMOVED from the original drop list (adversarial review caught live data):
--   schema_meta       -- live DB has 1 row: key='schema_version', value='v2'.
--                         Active schema-version lookup; dropping it breaks
--                         readers that consult schema_meta. PRESERVED.
--   schema_migrations -- live DB has 1 row: id='mig_20260607_085742_861283',
--                         a historical v1->v2 audit record (migrated=930
--                         reflections on 2026-06-07). Dropping it destroys
--                         audit history. PRESERVED.
--
-- Idempotency: every DROP uses IF EXISTS so re-running this script against
-- a partially-migrated or already-migrated database is a safe no-op.
--
-- Atomicity: the two DROPs run inside a single transaction so the database
-- never observes a half-vestigial state.
--
-- This script is the canonical cleanup step from Option B (Strict-UUID7
-- offline migration with consolidation) per the plan. The DROP statements
-- cover the truly vestigial tables named in Phase 0 step 2.f minus the two
-- false-drops flagged by adversarial review. No new schemas are created
-- here; scripts 007 and 008 add the UUID7 PK columns to the load-bearing
-- tables, 009 and 010 drop the *.duckdb files entirely.

BEGIN;

-- ============================================================================
-- Drop: access_log_v2
-- Vestigial: superseded by memory_access_log (script 007 backfills UUID7).
-- ============================================================================
DROP TABLE IF EXISTS access_log_v2;

-- ============================================================================
-- Drop: query_cache_l2
-- Vestigial: dead-on-arrival L2 query cache; not referenced from the read
-- path. Hot store is in-process + DuckDB FTS.
-- ============================================================================
DROP TABLE IF EXISTS query_cache_l2;

-- ============================================================================
-- Marker: signal that the UUID7 consolidation migration has completed.
-- scripts/fix_database_issues.py checks for this marker at startup and
-- skips the recreate-vestigial-tables branch (specifically: the
-- access_log_v2 recreate) when it exists. Without this marker, the next
-- session-buddy startup would silently undo the access_log_v2 drop.
-- ============================================================================
CREATE TABLE IF NOT EXISTS __uuid7_migration_done (
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    migration_id VARCHAR DEFAULT '2026_10_11_uuid7_consolidation'
);

COMMIT;
