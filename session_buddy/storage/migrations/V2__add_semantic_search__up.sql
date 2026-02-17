-- Skills Metrics Schema - V2 Semantic Search
-- Migration: V2__add_semantic_search
-- Description: Add vector embedding support for semantic skill search
--
-- Features:
--   - Add embedding column to skill_invocation (384-dim float vectors)
--   - Add partial index on embeddings (only non-null values)
--   - Support cosine similarity search via application layer
--
-- Technical Notes:
--   - Embeddings stored as BLOB (packed float32 array)
--   - 384 dimensions × 4 bytes = 1536 bytes per embedding
--   - Partial index saves space (NULL embeddings have no index entry)
--   - Application handles cosine similarity calculation

-- ============================================================================
-- Add Embedding Column
-- ============================================================================

-- Add embedding column as nullable BLOB
-- Stores packed float32 array (384 dimensions × 4 bytes = 1536 bytes)
ALTER TABLE skill_invocation ADD COLUMN embedding BLOB;

-- Create partial index on embeddings (only index non-null values)
-- This saves space since NULL embeddings (old records) won't be indexed
CREATE INDEX IF NOT EXISTS idx_invocation_embedding
    ON skill_invocation(embedding)
    WHERE embedding IS NOT NULL;

-- ============================================================================
-- Migration Tracking
-- ============================================================================

-- Record migration
INSERT INTO skill_migrations (version, applied_at, description, applied_by)
VALUES ('V2__add_semantic_search', datetime('now'), 'Add vector embedding support for semantic search', 'session-buddy');

-- ============================================================================
-- Performance Notes
-- ============================================================================

-- Index Usage:
--   - Partial index on embedding enables faster similarity searches
--   - Query pattern: WHERE embedding IS NOT NULL ORDER BY ...
--   - Application layer handles cosine similarity calculation
--
-- Storage Impact:
--   - Each embedding: 1536 bytes (384 × 4-byte float32)
--   - 1000 invocations ≈ 1.5 MB additional storage
--   - Index overhead: ~20-30% of embedding size
--
-- Query Performance:
--   - Use "WHERE embedding IS NOT NULL" to leverage partial index
--   - Application-side cosine similarity (fast for 384-dim vectors)
--   - Consider materialized top-k view for frequent queries
