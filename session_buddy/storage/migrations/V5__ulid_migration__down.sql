-- ULID Migration Rollback
-- Migration: V5__ulid_migration
-- Description: Rollback ULID migration if needed

-- ============================================================================
-- Rollback: Remove ULID columns
-- ============================================================================

-- Conversations table rollback
ALTER TABLE conversations DROP COLUMN conversation_ulid;
ALTER TABLE conversations DROP COLUMN conversation_ulid_generated_at;

-- Reflections table rollback
ALTER TABLE reflections DROP COLUMN reflection_ulid;
ALTER TABLE reflections DROP COLUMN reflection_ulid_generated_at;

-- Code graphs table rollback
ALTER TABLE code_graphs DROP COLUMN code_graph_ulid;
ALTER TABLE code_graphs DROP COLUMN code_graph_ulid_generated_at;

-- ============================================================================
-- Rollback: Drop ULID indexes
-- ============================================================================

DROP INDEX IF EXISTS idx_conversations_ulid;
DROP INDEX IF EXISTS idx_reflections_ulid;
DROP INDEX IF EXISTS idx_code_graphs_ulid;

-- ============================================================================
-- Notes:
-- ============================================================================
-- 1. Restores database to pre-migration state
-- 2. MD5 hash IDs become active identifiers again
-- 3. Application code changes must be reverted to remove ULID generation
-- 4. Data backfilled during migration remains in ULID columns
-- 5. Safe to run during maintenance window with no active sessions
-- ============================================================================
