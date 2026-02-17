-- ULID Migration: Add ULID columns for cross-system correlation
-- Migration: V5__ulid_migration
-- Date: 2026-02-12
-- Description: Add ULID columns alongside existing IDs for zero-downtime migration

-- ============================================================================
-- Phase 1: EXPAND - Add new ULID columns
-- ============================================================================

-- Conversations table expansion
ALTER TABLE conversations ADD COLUMN conversation_ulid TEXT;
ALTER TABLE conversations ADD COLUMN conversation_ulid_generated_at TIMESTAMP;

-- Reflections table expansion
ALTER TABLE reflections ADD COLUMN reflection_ulid TEXT;
ALTER TABLE reflections ADD COLUMN reflection_ulid_generated_at TIMESTAMP;

-- Code graphs table expansion
ALTER TABLE code_graphs ADD COLUMN code_graph_ulid TEXT;
ALTER TABLE code_graphs ADD COLUMN code_graph_ulid_generated_at TIMESTAMP;

-- ============================================================================
-- Phase 2: INDEXES - Create indexes for ULID lookups
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_conversations_ulid
ON conversations(conversation_ulid);

CREATE INDEX IF NOT EXISTS idx_reflections_ulid
ON reflections(reflection_ulid);

CREATE INDEX IF NOT EXISTS idx_code_graphs_ulid
ON code_graphs(code_graph_ulid);

-- ============================================================================
-- Phase 3: MIGRATION - Backfill ULIDs (will be done in application code)
-- ============================================================================

-- Backfill happens in Python code to use generate_ulid() function
-- See: session_buddy/reflection/storage.py updates

-- ============================================================================
-- Notes:
-- ============================================================================
-- 1. MD5 hash IDs remain as PRIMARY KEY (no schema change needed)
-- 2. ULID columns are added alongside for dual-write period
-- 3. After verification period (7 days), can switch to ULID as primary
-- 4. Application code updates required to use ULID for new records
-- 5. These indexes enable efficient cross-system correlation queries
-- ============================================================================
