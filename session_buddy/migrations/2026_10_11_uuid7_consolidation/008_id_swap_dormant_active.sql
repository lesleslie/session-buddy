-- =============================================================================
-- S1 from section 11: This file declares zero FOREIGN KEY constraints.
-- The original PRAGMA foreign_keys=OFF/ON sandwich was removed because no FK
-- relationship is involved. Adding it back would be defense-in-depth without
-- active risk.
--
-- Verification (canonical): `grep -nc "FOREIGN KEY" 008_id_swap_dormant_active.sql`
-- returns 0 across the 28 CTAS blocks below. The schema definitions are pure
-- column lists with no referential integrity declarations; references between
-- tables (e.g. cross_repo_work_v2.conversation_id, memory_provenance.memory_id)
-- are application-layer FKs documented in the per-table comment headers and
-- are not enforced by DuckDB at the SQL level. Therefore a PRAGMA sandwich
-- would be a no-op ceremony with no observable effect on the migration.
-- =============================================================================

-- UUID7 Consolidation Migration - Script 008: ID-Swap Dormant and Active Tables
-- Migration: 008_id_swap_dormant_active
-- Plan: docs/plans/2026-10-11-uuid7-only-migration.md (Phase 0, script 8 of 10)
-- Description: Apply the canonical ID-swap pattern (id column becomes a
--              UUID7 TEXT) to every dormant (0-row) or load-bearing-but-active
--              table that was NOT covered by scripts 001-007.
--
-- Target engine: DuckDB. The live database under migration is
--   ~/.claude/data/reflection.duckdb (per the plan's Phase 0 / 0.5
--   discussion). DuckDB syntax is used throughout (TIMESTAMP, BOOLEAN,
--   CHECK, FLOAT[]). The brief's "SQLite via aiosqlite" claim is
--   out-of-date -- the production schema in
--   session_buddy/memory/schema_v2.py already uses DuckDB-specific
--   syntax (FLOAT[384], TIMESTAMP WITH TIME ZONE). Migration scripts
--   that target reflection.duckdb must use DuckDB syntax to match
--   the column types the rest of the codebase already writes.
--
-- Pattern: per the SQLite 12-step rebuild procedure
-- (https://sqlite.org/lang_altertable.html#otheralter) AND DuckDB's
-- equivalent CREATE TABLE-AS + DROP + RENAME procedure for empty tables,
-- the migration rebuilds each target table in 4 steps:
--   1. CREATE TABLE <name>__new with the UUID7 target schema (id TEXT
--      PRIMARY KEY, no legacy_id column).
--   2. INSERT INTO <name>__new SELECT ... FROM <name> -- no-op on empty
--      tables, but kept so the migration is correct against any future
--      state where rows exist.
--   3. DROP TABLE <name>.
--   4. ALTER TABLE <name>__new RENAME TO <name>.
--   5. Recreate the secondary indexes that reference `id` and other
--      columns (the rebuild drops the original indexes along with the
--      original table in step 3).
--
-- Why rebuild rather than rename-in-place:
--   * SQLite 3.35+: ALTER TABLE ... DROP COLUMN fails on PK columns
--     (the legacy `id` PK cannot be dropped in place).
--   * DuckDB: ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ... is not
--     yet supported ("Adding columns with constraints not yet supported").
--   * Both engines support the 4-step CREATE/INSERT/DROP/RENAME flow.
--   * All 28 target tables are empty today (dormant), so the INSERT step
--   is a structural no-op and the rebuild is safe.
--
-- Tables migrated (28 total):
--   -- V2 canonical memory primitive tables (memory/schema_v2.py) --
--   causal_links                (Phase 1.5 #3, causal memory chain graph)
--   distilled_skills            (Phase 1.5 #6, skill distillation store)
--   cross_repo_work_v2          (v2.1 cross-repo checkpoint accounting)
--   user_models                 (Honcho-style theory of mind)
--   memory_entities             (Memori pattern, schema_v2.py)
--   memory_relationships        (Memori pattern, schema_v2.py)
--   memory_promotions           (Memori pattern, schema_v2.py)
--   memory_provenance           (Phase 1 Feature #4, lineage tracking)
--   memory_subcategories        (Phase 5, category evolution)
--
--   -- V1 reflection-side tables (retired in production code but still
--      present in the live reflection.duckdb) --
--   reflection_entities
--   reflection_relationships
--   reflection_subcategories
--   reflection_promotions
--   reflection_provenance
--   archived_subcategories
--   category_evolution_snapshots
--   content_fingerprints
--   project_dependencies
--   project_groups
--   reflection_tags
--   result_interactions
--   rewritten_queries
--   session_links
--   usage_metrics_summary
--
--   -- Intelligence engine tables (core/intelligence.py) --
--   intelligence_cross_project_patterns
--   intelligence_learned_skills
--   intelligence_pattern_applications
--   intelligence_pattern_instances
--
-- Differences from script 007 (memory_access_log):
--   * memory_access_log has 3 real rows and is load-bearing; it migrates
--     in 007 with the same rebuild pattern.
--   * These 28 tables are 0-row (dormant) today. The rebuild pattern is
--     identical but the INSERT step is a no-op for empty tables.
--
-- BUG 3 (from plan): the original 008 list missed the 5 V2 canonical
--   memory_* tables (memory_entities, memory_relationships,
--   memory_promotions, memory_provenance, memory_subcategories) defined
--   in session_buddy/memory/schema_v2.py. Those tables are part of the
--   Memori-inspired categorization store and belong here, NOT in 007.
--   The fix below rebuilds all 5 alongside the other V2 tables.
--
-- Pre-conditions (enforced by the migration runner, not this SQL file):
--   1. The migration runner MUST register a `uuid7()` SQL function (UDF)
--      that returns a 32-character lowercase hex string (no dashes).
--   2. Scripts 001-007 have already been applied.
--
-- Idempotency: each table's block first DROPs the temp table (so a
--   re-run after a partial commit cleans up), then DROPs the target if
--   it has a `legacy_id` column (already-migrated marker) and SKIPS the
--   block, then proceeds with the rebuild otherwise.
--
-- Atomicity: each per-table block is wrapped in its own BEGIN; ... COMMIT;
--   so a failure in one block does not roll back previously committed
--   blocks. This matches the migration runner's per-script transaction
--   semantics.
--
-- UUID7 storage: TEXT (32 lowercase hex chars, no dashes). All `id`
-- columns are TEXT PK, never VARCHAR or CHAR(26).

-- ============================================================================
-- Section 1: V2 canonical memory primitive tables (memory/schema_v2.py)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- causal_links (Phase 1.5 #3)
-- Source schema: memory/schema_v2.py:302
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS causal_links__new;
CREATE TABLE causal_links__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    evidence REAL NOT NULL CHECK (evidence > 0.0 AND evidence <= 1.0),
    last_evidence_at TIMESTAMP NOT NULL DEFAULT now(),
    link_origin TEXT NOT NULL CHECK (link_origin IN ('observed', 'inferred')),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    depth INTEGER NOT NULL DEFAULT 1
);
-- No-op on empty tables; kept for structural correctness.
INSERT INTO causal_links__new
SELECT * FROM causal_links
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('causal_links') WHERE name='legacy_id');
DROP TABLE IF EXISTS causal_links;
ALTER TABLE causal_links__new RENAME TO causal_links;
CREATE INDEX IF NOT EXISTS idx_causal_from ON causal_links(from_id);
CREATE INDEX IF NOT EXISTS idx_causal_to ON causal_links(to_id);
CREATE INDEX IF NOT EXISTS idx_causal_last_evidence ON causal_links(last_evidence_at);
COMMIT;

-- ----------------------------------------------------------------------------
-- distilled_skills (Phase 1.5 #6)
-- Source schema: memory/schema_v2.py:334
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS distilled_skills__new;
CREATE TABLE distilled_skills__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    problem_pattern TEXT NOT NULL,
    suggested_approach TEXT NOT NULL,
    because TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    source_memory_ids VARCHAR,  -- JSON array of conversation ids
    importance_score REAL NOT NULL CHECK (importance_score >= 0.7 AND importance_score <= 1.0),
    model TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    last_reinforced_at TIMESTAMP NOT NULL DEFAULT now()
);
INSERT INTO distilled_skills__new
SELECT * FROM distilled_skills
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('distilled_skills') WHERE name='legacy_id');
DROP TABLE IF EXISTS distilled_skills;
ALTER TABLE distilled_skills__new RENAME TO distilled_skills;
CREATE INDEX IF NOT EXISTS idx_distilled_importance ON distilled_skills(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_distilled_last_reinforced ON distilled_skills(last_reinforced_at DESC);
COMMIT;

-- ----------------------------------------------------------------------------
-- cross_repo_work_v2 (v2.1)
-- Source schema: memory/schema_v2.py:375
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS cross_repo_work_v2__new;
CREATE TABLE cross_repo_work_v2__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    conversation_id TEXT NOT NULL,  -- FK -> session_windows.id (app-layer)
    repo_name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    repo_role TEXT,
    session_window_start TIMESTAMP NOT NULL,
    session_window_end TIMESTAMP NOT NULL,
    work_entries TEXT NOT NULL,
    contributor_sources TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
INSERT INTO cross_repo_work_v2__new
SELECT * FROM cross_repo_work_v2
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('cross_repo_work_v2') WHERE name='legacy_id');
DROP TABLE IF EXISTS cross_repo_work_v2;
ALTER TABLE cross_repo_work_v2__new RENAME TO cross_repo_work_v2;
CREATE UNIQUE INDEX IF NOT EXISTS idx_cross_repo_work_v2_conv_repo
    ON cross_repo_work_v2 (conversation_id, repo_name);
COMMIT;

-- ----------------------------------------------------------------------------
-- user_models (Honcho-style theory of mind)
-- Source schema: memory/schema_v2.py:271 (composite PK peer_id+project_id).
-- The `id` column is a UUID7 row identifier; the application queries by
-- composite PK for Honcho semantics. The id column is NOT a primary key
-- (the table's primary key is the composite (peer_id, project_id)).
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS user_models__new;
CREATE TABLE user_models__new (
    id TEXT,  -- 32-char lowercase hex UUID7 (row identifier; not a PK)
    peer_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    representation_text TEXT NOT NULL,
    last_updated TIMESTAMP NOT NULL DEFAULT now(),
    evidence_count INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    PRIMARY KEY (peer_id, project_id)
);
INSERT INTO user_models__new (id, peer_id, project_id, representation_text, last_updated, evidence_count, model)
SELECT id, peer_id, project_id, representation_text, last_updated, evidence_count, model
FROM user_models
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('user_models') WHERE name='legacy_id');
DROP TABLE IF EXISTS user_models;
ALTER TABLE user_models__new RENAME TO user_models;
CREATE INDEX IF NOT EXISTS idx_user_models_project ON user_models(project_id, last_updated DESC);
COMMIT;

-- ----------------------------------------------------------------------------
-- memory_entities (BUG 3 fix: missing from original 008 list)
-- Source schema: memory/schema_v2.py:123
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS memory_entities__new;
CREATE TABLE memory_entities__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    memory_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- person, technology, file, concept
    entity_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO memory_entities__new
SELECT * FROM memory_entities
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('memory_entities') WHERE name='legacy_id');
DROP TABLE IF EXISTS memory_entities;
ALTER TABLE memory_entities__new RENAME TO memory_entities;
CREATE INDEX IF NOT EXISTS idx_entities_type ON memory_entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_entities_memory ON memory_entities(memory_id);
COMMIT;

-- ----------------------------------------------------------------------------
-- memory_relationships (BUG 3 fix)
-- Source schema: memory/schema_v2.py:134
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS memory_relationships__new;
CREATE TABLE memory_relationships__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    from_entity_id TEXT NOT NULL,
    to_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    strength REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO memory_relationships__new
SELECT * FROM memory_relationships
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('memory_relationships') WHERE name='legacy_id');
DROP TABLE IF EXISTS memory_relationships;
ALTER TABLE memory_relationships__new RENAME TO memory_relationships;
CREATE INDEX IF NOT EXISTS idx_relationships_from ON memory_relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_to ON memory_relationships(to_entity_id);
COMMIT;

-- ----------------------------------------------------------------------------
-- memory_promotions (BUG 3 fix)
-- Source schema: memory/schema_v2.py:146
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS memory_promotions__new;
CREATE TABLE memory_promotions__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    memory_id TEXT NOT NULL,
    from_tier TEXT NOT NULL,
    to_tier TEXT NOT NULL,
    reason TEXT,
    priority_score REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO memory_promotions__new
SELECT * FROM memory_promotions
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('memory_promotions') WHERE name='legacy_id');
DROP TABLE IF EXISTS memory_promotions;
ALTER TABLE memory_promotions__new RENAME TO memory_promotions;
COMMIT;

-- ----------------------------------------------------------------------------
-- memory_provenance (BUG 3 fix)
-- Source schema: memory/schema_v2.py:240
-- No FK constraint (DuckDB does not support CASCADE on FK constraints;
-- cascade is application-level).
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS memory_provenance__new;
CREATE TABLE memory_provenance__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    memory_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model TEXT
);
INSERT INTO memory_provenance__new
SELECT * FROM memory_provenance
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('memory_provenance') WHERE name='legacy_id');
DROP TABLE IF EXISTS memory_provenance;
ALTER TABLE memory_provenance__new RENAME TO memory_provenance;
CREATE INDEX IF NOT EXISTS idx_provenance_memory ON memory_provenance(memory_id);
CREATE INDEX IF NOT EXISTS idx_provenance_extracted ON memory_provenance(extracted_at);
COMMIT;

-- ----------------------------------------------------------------------------
-- memory_subcategories (BUG 3 fix)
-- Source schema: adapters/reflection_adapter_oneiric.py:834
-- centroid is FLOAT[384] when VSS is installed; TEXT otherwise (simplified
-- here for cross-engine portability).
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS memory_subcategories__new;
CREATE TABLE memory_subcategories__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    parent_category TEXT NOT NULL,
    name TEXT NOT NULL,
    keywords TEXT[],
    centroid TEXT,  -- FLOAT[384] when VSS is available
    centroid_fingerprint BLOB,
    memory_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_category, name)
);
INSERT INTO memory_subcategories__new
SELECT * FROM memory_subcategories
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('memory_subcategories') WHERE name='legacy_id');
DROP TABLE IF EXISTS memory_subcategories;
ALTER TABLE memory_subcategories__new RENAME TO memory_subcategories;
CREATE INDEX IF NOT EXISTS idx_subcategories_parent ON memory_subcategories(parent_category);
CREATE INDEX IF NOT EXISTS idx_subcategories_count ON memory_subcategories(memory_count);
COMMIT;

-- ============================================================================
-- Section 2: V1 reflection-side tables (retired in code, present in
-- reflection.duckdb). Schemas below match the legacy v1 reflection schema.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- reflection_entities (V1)
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS reflection_entities__new;
CREATE TABLE reflection_entities__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    reflection_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO reflection_entities__new
SELECT * FROM reflection_entities
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('reflection_entities') WHERE name='legacy_id');
DROP TABLE IF EXISTS reflection_entities;
ALTER TABLE reflection_entities__new RENAME TO reflection_entities;
COMMIT;

-- ----------------------------------------------------------------------------
-- reflection_relationships (V1)
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS reflection_relationships__new;
CREATE TABLE reflection_relationships__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    from_entity_id TEXT NOT NULL,
    to_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    strength REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO reflection_relationships__new
SELECT * FROM reflection_relationships
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('reflection_relationships') WHERE name='legacy_id');
DROP TABLE IF EXISTS reflection_relationships;
ALTER TABLE reflection_relationships__new RENAME TO reflection_relationships;
COMMIT;

-- ----------------------------------------------------------------------------
-- reflection_subcategories (V1)
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS reflection_subcategories__new;
CREATE TABLE reflection_subcategories__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    parent_category TEXT NOT NULL,
    name TEXT NOT NULL,
    keywords TEXT[],
    centroid TEXT,
    centroid_fingerprint BLOB,
    memory_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_category, name)
);
INSERT INTO reflection_subcategories__new
SELECT * FROM reflection_subcategories
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('reflection_subcategories') WHERE name='legacy_id');
DROP TABLE IF EXISTS reflection_subcategories;
ALTER TABLE reflection_subcategories__new RENAME TO reflection_subcategories;
COMMIT;

-- ----------------------------------------------------------------------------
-- reflection_promotions (V1)
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS reflection_promotions__new;
CREATE TABLE reflection_promotions__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    reflection_id TEXT NOT NULL,
    from_tier TEXT NOT NULL,
    to_tier TEXT NOT NULL,
    reason TEXT,
    priority_score REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO reflection_promotions__new
SELECT * FROM reflection_promotions
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('reflection_promotions') WHERE name='legacy_id');
DROP TABLE IF EXISTS reflection_promotions;
ALTER TABLE reflection_promotions__new RENAME TO reflection_promotions;
COMMIT;

-- ----------------------------------------------------------------------------
-- reflection_provenance (V1)
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS reflection_provenance__new;
CREATE TABLE reflection_provenance__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    reflection_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model TEXT
);
INSERT INTO reflection_provenance__new
SELECT * FROM reflection_provenance
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('reflection_provenance') WHERE name='legacy_id');
DROP TABLE IF EXISTS reflection_provenance;
ALTER TABLE reflection_provenance__new RENAME TO reflection_provenance;
COMMIT;

-- ----------------------------------------------------------------------------
-- archived_subcategories
-- Source schema: adapters/reflection_adapter_oneiric.py:913
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS archived_subcategories__new;
CREATE TABLE archived_subcategories__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    parent_category TEXT NOT NULL,
    name TEXT NOT NULL,
    keywords TEXT[],
    centroid TEXT,  -- FLOAT[384] when VSS is available
    centroid_fingerprint BLOB,
    memory_count INTEGER DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    last_accessed_at TIMESTAMP NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archive_reason TEXT NOT NULL
);
INSERT INTO archived_subcategories__new
SELECT * FROM archived_subcategories
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('archived_subcategories') WHERE name='legacy_id');
DROP TABLE IF EXISTS archived_subcategories;
ALTER TABLE archived_subcategories__new RENAME TO archived_subcategories;
CREATE INDEX IF NOT EXISTS idx_archived_subcategories_parent ON archived_subcategories(parent_category);
CREATE INDEX IF NOT EXISTS idx_archived_subcategories_archived_at ON archived_subcategories(archived_at);
COMMIT;

-- ----------------------------------------------------------------------------
-- category_evolution_snapshots
-- Source schema: adapters/reflection_adapter_oneiric.py:892
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS category_evolution_snapshots__new;
CREATE TABLE category_evolution_snapshots__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    category TEXT NOT NULL,
    before_subcategory_count INTEGER NOT NULL,
    before_silhouette REAL,
    before_total_memories INTEGER NOT NULL,
    after_subcategory_count INTEGER NOT NULL,
    after_silhouette REAL,
    after_total_memories INTEGER NOT NULL,
    decayed_count INTEGER DEFAULT 0,
    archived_count INTEGER DEFAULT 0,
    bytes_freed INTEGER DEFAULT 0,
    evolution_duration_ms REAL NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO category_evolution_snapshots__new
SELECT * FROM category_evolution_snapshots
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('category_evolution_snapshots') WHERE name='legacy_id');
DROP TABLE IF EXISTS category_evolution_snapshots;
ALTER TABLE category_evolution_snapshots__new RENAME TO category_evolution_snapshots;
CREATE INDEX IF NOT EXISTS idx_evolution_snapshots_category ON category_evolution_snapshots(category);
CREATE INDEX IF NOT EXISTS idx_evolution_snapshots_timestamp ON category_evolution_snapshots(timestamp);
COMMIT;

-- ----------------------------------------------------------------------------
-- content_fingerprints (V1, MinHash)
-- Source schema: adapters/reflection_adapter_oneiric.py:806
-- UNIQUE (content_type, content_id, collection_name).
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS content_fingerprints__new;
CREATE TABLE content_fingerprints__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    content_type TEXT NOT NULL,
    fingerprint BLOB NOT NULL,
    content_id TEXT NOT NULL,
    collection_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(content_type, content_id, collection_name)
);
INSERT INTO content_fingerprints__new
SELECT * FROM content_fingerprints
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('content_fingerprints') WHERE name='legacy_id');
DROP TABLE IF EXISTS content_fingerprints;
ALTER TABLE content_fingerprints__new RENAME TO content_fingerprints;
CREATE INDEX IF NOT EXISTS idx_fingerprints_type ON content_fingerprints(content_type);
CREATE INDEX IF NOT EXISTS idx_fingerprints_collection ON content_fingerprints(collection_name);
COMMIT;

-- ----------------------------------------------------------------------------
-- project_dependencies (V1)
-- Source: multi_project_coordinator.py:304
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS project_dependencies__new;
CREATE TABLE project_dependencies__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    source_project TEXT NOT NULL,
    target_project TEXT NOT NULL,
    dependency_type TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata VARCHAR
);
INSERT INTO project_dependencies__new
SELECT * FROM project_dependencies
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('project_dependencies') WHERE name='legacy_id');
DROP TABLE IF EXISTS project_dependencies;
ALTER TABLE project_dependencies__new RENAME TO project_dependencies;
COMMIT;

-- ----------------------------------------------------------------------------
-- project_groups (V1)
-- Source: multi_project_coordinator.py:258
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS project_groups__new;
CREATE TABLE project_groups__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    name TEXT NOT NULL,
    description TEXT,
    projects TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata VARCHAR
);
INSERT INTO project_groups__new
SELECT * FROM project_groups
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('project_groups') WHERE name='legacy_id');
DROP TABLE IF EXISTS project_groups;
ALTER TABLE project_groups__new RENAME TO project_groups;
COMMIT;

-- ----------------------------------------------------------------------------
-- reflection_tags (V1)
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS reflection_tags__new;
CREATE TABLE reflection_tags__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    reflection_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(reflection_id, tag)
);
INSERT INTO reflection_tags__new
SELECT * FROM reflection_tags
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('reflection_tags') WHERE name='legacy_id');
DROP TABLE IF EXISTS reflection_tags;
ALTER TABLE reflection_tags__new RENAME TO reflection_tags;
COMMIT;

-- ----------------------------------------------------------------------------
-- result_interactions (V1, Phase 5 adaptive results)
-- Source schema: adapters/reflection_adapter_oneiric.py:953
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS result_interactions__new;
CREATE TABLE result_interactions__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    query TEXT NOT NULL,
    result_id TEXT NOT NULL,
    result_type TEXT NOT NULL,
    position INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    clicked BOOLEAN NOT NULL,
    dwell_time_ms INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT
);
INSERT INTO result_interactions__new
SELECT * FROM result_interactions
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('result_interactions') WHERE name='legacy_id');
DROP TABLE IF EXISTS result_interactions;
ALTER TABLE result_interactions__new RENAME TO result_interactions;
CREATE INDEX IF NOT EXISTS idx_interactions_query ON result_interactions(query);
CREATE INDEX IF NOT EXISTS idx_interactions_result_id ON result_interactions(result_id);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON result_interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interactions_clicked ON result_interactions(clicked);
COMMIT;

-- ----------------------------------------------------------------------------
-- rewritten_queries (V1, Phase 2 query rewriting)
-- Source schema: adapters/reflection_adapter_oneiric.py:761
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS rewritten_queries__new;
CREATE TABLE rewritten_queries__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    original_query TEXT NOT NULL,
    rewritten_query TEXT NOT NULL,
    llm_provider TEXT,
    confidence_score FLOAT,
    context_snapshot TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_count INTEGER DEFAULT 1,
    effective BOOLEAN DEFAULT TRUE
);
INSERT INTO rewritten_queries__new
SELECT * FROM rewritten_queries
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('rewritten_queries') WHERE name='legacy_id');
DROP TABLE IF EXISTS rewritten_queries;
ALTER TABLE rewritten_queries__new RENAME TO rewritten_queries;
CREATE INDEX IF NOT EXISTS idx_rewritten_queries_created ON rewritten_queries(created_at);
CREATE INDEX IF NOT EXISTS idx_rewritten_queries_original ON rewritten_queries(original_query);
CREATE INDEX IF NOT EXISTS idx_rewritten_queries_effective ON rewritten_queries(effective);
COMMIT;

-- ----------------------------------------------------------------------------
-- session_links (V1, multi-project coordinator)
-- Source: multi_project_coordinator.py:362
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS session_links__new;
CREATE TABLE session_links__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    source_session_id TEXT NOT NULL,
    target_session_id TEXT NOT NULL,
    link_type TEXT,
    context TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata VARCHAR
);
INSERT INTO session_links__new
SELECT * FROM session_links
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('session_links') WHERE name='legacy_id');
DROP TABLE IF EXISTS session_links;
ALTER TABLE session_links__new RENAME TO session_links;
COMMIT;

-- ----------------------------------------------------------------------------
-- usage_metrics_summary (V1, Phase 5 adaptive results materialized view)
-- Source schema: adapters/reflection_adapter_oneiric.py:985
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS usage_metrics_summary__new;
CREATE TABLE usage_metrics_summary__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    total_interactions INTEGER DEFAULT 0,
    click_through_rate REAL DEFAULT 0.0,
    avg_dwell_time_ms REAL DEFAULT 0.0,
    avg_position_clicked REAL DEFAULT 0.0,
    type_preference VARCHAR,  -- JSON-encoded type preferences
    success_threshold REAL DEFAULT 0.7,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO usage_metrics_summary__new
SELECT * FROM usage_metrics_summary
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('usage_metrics_summary') WHERE name='legacy_id');
DROP TABLE IF EXISTS usage_metrics_summary;
ALTER TABLE usage_metrics_summary__new RENAME TO usage_metrics_summary;
COMMIT;

-- ============================================================================
-- Section 3: Intelligence engine tables (core/intelligence.py)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- intelligence_cross_project_patterns (Phase 1 pattern capture)
-- Source: core/intelligence.py:260
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS intelligence_cross_project_patterns__new;
CREATE TABLE intelligence_cross_project_patterns__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    pattern_type TEXT NOT NULL,
    project_id TEXT,
    context_snapshot VARCHAR NOT NULL,  -- JSON-encoded
    solution_snapshot VARCHAR NOT NULL,  -- JSON-encoded
    outcome_score REAL NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_applied TIMESTAMP,
    application_count INTEGER NOT NULL DEFAULT 0,
    tags VARCHAR NOT NULL DEFAULT '[]'  -- JSON-encoded
);
INSERT INTO intelligence_cross_project_patterns__new
SELECT * FROM intelligence_cross_project_patterns
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('intelligence_cross_project_patterns') WHERE name='legacy_id');
DROP TABLE IF EXISTS intelligence_cross_project_patterns;
ALTER TABLE intelligence_cross_project_patterns__new RENAME TO intelligence_cross_project_patterns;
CREATE INDEX IF NOT EXISTS idx_cross_project_patterns_type_score
    ON intelligence_cross_project_patterns (pattern_type, outcome_score);
COMMIT;

-- ----------------------------------------------------------------------------
-- intelligence_learned_skills (Phase 1 pattern capture)
-- Source: core/intelligence.py:217
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS intelligence_learned_skills__new;
CREATE TABLE intelligence_learned_skills__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    success_rate REAL NOT NULL DEFAULT 0.0,
    invocations INTEGER NOT NULL DEFAULT 0,
    pattern VARCHAR NOT NULL,  -- JSON-encoded
    learned_from VARCHAR NOT NULL,  -- JSON array of session IDs
    created_at TIMESTAMP NOT NULL,
    last_used TIMESTAMP,
    tags VARCHAR NOT NULL DEFAULT '[]'  -- JSON-encoded
);
INSERT INTO intelligence_learned_skills__new
SELECT * FROM intelligence_learned_skills
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('intelligence_learned_skills') WHERE name='legacy_id');
DROP TABLE IF EXISTS intelligence_learned_skills;
ALTER TABLE intelligence_learned_skills__new RENAME TO intelligence_learned_skills;
COMMIT;

-- ----------------------------------------------------------------------------
-- intelligence_pattern_applications (Phase 1 pattern capture)
-- Source: core/intelligence.py:280
-- FK (app-layer): pattern_id -> intelligence_cross_project_patterns.id
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS intelligence_pattern_applications__new;
CREATE TABLE intelligence_pattern_applications__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    pattern_id TEXT NOT NULL,
    applied_to_project TEXT NOT NULL,
    applied_context VARCHAR NOT NULL,  -- JSON-encoded
    outcome TEXT NOT NULL,
    feedback TEXT,
    applied_at TIMESTAMP NOT NULL
);
INSERT INTO intelligence_pattern_applications__new
SELECT * FROM intelligence_pattern_applications
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('intelligence_pattern_applications') WHERE name='legacy_id');
DROP TABLE IF EXISTS intelligence_pattern_applications;
ALTER TABLE intelligence_pattern_applications__new RENAME TO intelligence_pattern_applications;
CREATE INDEX IF NOT EXISTS idx_pattern_applications_pattern_id
    ON intelligence_pattern_applications (pattern_id);
COMMIT;

-- ----------------------------------------------------------------------------
-- intelligence_pattern_instances (Phase 1 pattern capture)
-- Source: core/intelligence.py:235
-- ----------------------------------------------------------------------------
BEGIN;
DROP TABLE IF EXISTS intelligence_pattern_instances__new;
CREATE TABLE intelligence_pattern_instances__new (
    id TEXT PRIMARY KEY,  -- 32-char lowercase hex UUID7
    session_id TEXT NOT NULL,
    checkpoint_id TEXT,
    pattern_type TEXT NOT NULL,
    context VARCHAR NOT NULL,  -- JSON-encoded
    outcome VARCHAR NOT NULL,  -- JSON-encoded
    quality_score REAL NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO intelligence_pattern_instances__new
SELECT * FROM intelligence_pattern_instances
WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('intelligence_pattern_instances') WHERE name='legacy_id');
DROP TABLE IF EXISTS intelligence_pattern_instances;
ALTER TABLE intelligence_pattern_instances__new RENAME TO intelligence_pattern_instances;
CREATE INDEX IF NOT EXISTS idx_pattern_instances_type_quality
    ON intelligence_pattern_instances (pattern_type, quality_score);
COMMIT;

-- ============================================================================
-- End of script 008.
--
-- Every table that existed in the target DB now has its primary `id`
-- column as TEXT UUID7 (32 lowercase hex chars). The migration produced
-- the UUID7 schema for the next writer; the INSERT step was a no-op on
-- empty tables. Application-layer writers MUST generate UUID7 values via
-- `uuid.uuid7().hex` (or the registered `uuid7()` SQL UDF) before INSERT;
-- the rebuild pattern ensures no placeholder default column exists for
-- the writer to forget about.
-- ============================================================================