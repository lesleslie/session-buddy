"""
Enhanced Memory Schema v2 - Memori-inspired categorization with DuckDB.

Combines Memori's superior categorization with session-mgmt's ONNX vector search.
"""

from enum import StrEnum


class MemoryCategory(StrEnum):
    """
    Memory categories inspired by Memori's structured categorization.

    These categories enable intelligent memory organization and retrieval.
    """

    FACTS = "facts"  # Factual information (project names, tech stack)
    PREFERENCES = "preferences"  # User preferences (coding style, tools)
    SKILLS = "skills"  # User knowledge/expertise (languages, frameworks)
    RULES = "rules"  # Learned patterns/rules (workflows, best practices)
    CONTEXT = "context"  # Contextual information (current tasks, environment)
    CLAUDE_TURN = (
        "claude_turn"  # A single Claude conversation turn (transcript ingester)
    )


class MemoryTier(StrEnum):
    """
    Memory storage tiers for optimized retrieval.

    Inspired by Memori's short-term/long-term memory architecture.
    """

    WORKING = "working"  # Active context for current session (highest priority)
    SHORT_TERM = "short_term"  # Recently accessed or promoted memories
    LONG_TERM = "long_term"  # All historical memories


# DuckDB schema migration SQL
SCHEMA_V2_SQL = """
-- Enhanced conversations table with Memori-inspired categorization
CREATE TABLE IF NOT EXISTS conversations_v2 (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[384],  -- ONNX vector (session-mgmt's superior approach)

    -- Memori-inspired categorization
    category TEXT NOT NULL,  -- facts, preferences, skills, rules, context
    subcategory TEXT,
    importance_score REAL DEFAULT 0.5,  -- 0.0-1.0

    -- Memory tier management
    memory_tier TEXT DEFAULT 'long_term',  -- working, short_term, long_term
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,

    -- Metadata
    project TEXT,
    namespace TEXT DEFAULT 'default',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    user_id TEXT DEFAULT 'default',

    -- Search optimization
    searchable_content TEXT,  -- For full-text fallback
    reasoning TEXT,  -- Why this memory is important

    -- Provenance + lineage (added Phase 0 v2 rewire)
    metadata VARCHAR,  -- JSON-encoded metadata (allowlist-filtered)
    source_type TEXT CHECK (
        source_type IS NULL OR source_type IN (
            'claude_code', 'crackerjack', 'mahavishnu_workflow', 'manual', 'migration'
        )
    ),  -- claude_code | crackerjack | mahavishnu_workflow | manual | migration
    turn_parent_id TEXT,  -- Parent turn in a transcript chain
    causal_parent_id TEXT  -- Parent that caused this memory to be written
);

-- Enhanced reflections table
CREATE TABLE IF NOT EXISTS reflections_v2 (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[384],

    -- Memori-inspired structure
    category TEXT NOT NULL,
    importance_score REAL DEFAULT 0.5,
    memory_tier TEXT DEFAULT 'long_term',

    -- Tags and relationships
    tags TEXT[],
    related_entities TEXT[],

    -- Metadata
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    project TEXT,
    namespace TEXT DEFAULT 'default',

    -- Access tracking
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,

    -- Legacy compatibility columns (used by store_reflection)
    -- These are written alongside the v2 columns so the v2 table can
    -- serve as a drop-in replacement for the legacy reflections table.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    insight_type TEXT,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    confidence_score REAL,
    fingerprint BLOB,
    subcategory TEXT
);

-- Entity extraction table (Memori pattern)
CREATE TABLE IF NOT EXISTS memory_entities (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- person, technology, file, concept
    entity_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations_v2(id)
);

-- Entity relationships (Memori pattern)
CREATE TABLE IF NOT EXISTS memory_relationships (
    id TEXT PRIMARY KEY,
    from_entity_id TEXT NOT NULL,
    to_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,  -- uses, extends, references, related_to
    strength REAL DEFAULT 1.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_entity_id) REFERENCES memory_entities(id),
    FOREIGN KEY (to_entity_id) REFERENCES memory_entities(id)
);

-- Short-term memory promotion tracking
CREATE TABLE IF NOT EXISTS memory_promotions (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    from_tier TEXT NOT NULL,
    to_tier TEXT NOT NULL,
    reason TEXT,
    priority_score REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations_v2(id)
);

-- Access patterns tracking (for Conscious Agent)
-- ``memory_id`` is nullable: a search that hits nothing has no row in
-- ``conversations_v2`` to point at. ``query_text`` captures the raw
-- search string so the analysis loop can group by query pattern.
CREATE TABLE IF NOT EXISTS memory_access_log (
    id TEXT PRIMARY KEY,
    memory_id TEXT,  -- nullable: search hits often have no memory_id
    access_type TEXT,  -- search, retrieve, promote, demote
    query_text TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations_v2(id)
);

-- Column patches: idempotent ALTER TABLE guards for columns added after initial deployment.
-- DuckDB's CREATE TABLE IF NOT EXISTS does not add new columns to existing tables, so
-- any column added to a CREATE TABLE block above also needs an ADD COLUMN IF NOT EXISTS here.
-- These run BEFORE indexes so that indexes referencing new columns (e.g. source_type) succeed
-- even on databases that predate those columns.

-- conversations_v2: provenance + lineage columns (added Phase 0 v2 rewire)
ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS metadata VARCHAR;
ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS source_type TEXT;
ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS turn_parent_id TEXT;
ALTER TABLE conversations_v2 ADD COLUMN IF NOT EXISTS causal_parent_id TEXT;

-- reflections_v2: legacy compatibility columns (used by store_reflection)
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS insight_type TEXT;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS usage_count INTEGER DEFAULT 0;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS confidence_score REAL;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS fingerprint BLOB;
ALTER TABLE reflections_v2 ADD COLUMN IF NOT EXISTS subcategory TEXT;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversations_category ON conversations_v2(category, namespace);
CREATE INDEX IF NOT EXISTS idx_conversations_tier ON conversations_v2(memory_tier, importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_namespace ON conversations_v2(namespace, project);
CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations_v2(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_access ON conversations_v2(last_accessed DESC);

CREATE INDEX IF NOT EXISTS idx_reflections_category ON reflections_v2(category, namespace);
CREATE INDEX IF NOT EXISTS idx_reflections_tier ON reflections_v2(memory_tier);

CREATE INDEX IF NOT EXISTS idx_entities_type ON memory_entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_entities_memory ON memory_entities(memory_id);

CREATE INDEX IF NOT EXISTS idx_relationships_from ON memory_relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_to ON memory_relationships(to_entity_id);

CREATE INDEX IF NOT EXISTS idx_access_log_memory ON memory_access_log(memory_id, timestamp DESC);

-- Full-text search (fallback when ONNX unavailable)
CREATE INDEX IF NOT EXISTS idx_conversations_fts ON conversations_v2(searchable_content);

-- Index for source_type lookups (most reads filter by project + recency).
-- Note: source_type CHECK constraint is defined inline in the CREATE TABLE
-- above (DuckDB does not support ALTER TABLE ... ADD CONSTRAINT).
CREATE INDEX IF NOT EXISTS idx_v2_source_type_project
    ON conversations_v2(source_type, project, timestamp DESC);

-- Memory provenance / lineage (Phase 1 Feature #4).
-- One row per memory write that declares a source_type. Records WHERE
-- each memory came from (source_ref, e.g. session id), WHEN it was
-- extracted, and WHICH model produced it.
--
-- Note: no FOREIGN KEY constraint here. DuckDB does NOT support
-- ``ON DELETE CASCADE`` on FOREIGN KEY constraints (Parser Error:
-- FOREIGN KEY constraints cannot use CASCADE, SET NULL or SET
-- DEFAULT). Cascading is application-level: callers that delete from
-- ``conversations_v2`` must also delete matching
-- ``memory_provenance`` rows in the same transaction (same pattern
-- as ``memory_entities`` and ``memory_promotions``).
CREATE TABLE IF NOT EXISTS memory_provenance (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model TEXT
);
CREATE INDEX IF NOT EXISTS idx_provenance_memory ON memory_provenance(memory_id);
CREATE INDEX IF NOT EXISTS idx_provenance_extracted ON memory_provenance(extracted_at);

-- Per-project peer model (Honcho-style theory of mind, Phase 1.5 #2).
-- ``peer_id`` is the user/agent identifier, ``project_id`` scopes the
-- representation so cross-project leakage is impossible at the schema
-- level (composite primary key). ``representation_text`` is the
-- short, evolving user summary — initially heuristic, optionally
-- LLM-derived when the Conscious Agent runs.
--
-- Concurrency: writes use ``INSERT ... ON CONFLICT (peer_id, project_id)
-- DO UPDATE`` so two workers updating the same peer race harmlessly
-- (last-writer-wins on the row). The Conscious Agent's evidence
-- count lets us decide when re-derivation is worth the LLM cost
-- (plan §LLM Cost Ceiling: 50 calls/day/peer).
--
-- ACL note: this table is NOT consumed by any read path by default.
-- Cross-component consumers (Mahavishnu routing, Akosha analytics)
-- must check the ``peer_models:read`` permission before reading
-- (plan §Honcho: ``peer_models:read``/``peer_models:write`` ACL).
-- Session-Buddy exposes peer_context() but the ACL gate lives in
-- the calling tool, not in the adapter — adapters are infrastructure,
-- not policy.
CREATE TABLE IF NOT EXISTS user_models (
    peer_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    representation_text TEXT NOT NULL,
    last_updated TIMESTAMP NOT NULL DEFAULT now(),
    evidence_count INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    PRIMARY KEY (peer_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_user_models_project ON user_models(project_id, last_updated DESC);

-- Causal Memory Chains (Phase 1.5 #3).
-- A directed graph over ``conversations_v2`` rows: ``from_id`` was
-- (probably) the cause of ``to_id``. The graph is walked in
-- :func:`walk_causal_chain` with a depth cap of 3 (per the plan's
-- cap-at-3 decision, cycle-safe via visited-set).
--
-- ``link_type`` is a free-form label (e.g. ``led_to``, ``elaborated``,
-- ``superseded``). The application decides the vocabulary. ``evidence``
-- is a weight in [0.0, 1.0] — links with evidence <= 0.5 are NOT
-- persisted by ``infer_causal_links`` (the plan's quality floor).
-- ``last_evidence_at`` is bumped on every observed reuse so the
-- Conscious Agent can prune links that haven't been touched in 90 days.
-- ``link_origin`` distinguishes ``observed`` (direct transcript pair,
-- parent_uuid_chain, or other ground-truth) from ``inferred``
-- (heuristic guess from co-occurrence).
--
-- Note: no FK to ``conversations_v2(id)`` because the source rows
-- are not necessarily conversations — the schema is open to links
-- from any future memory primitive (reflections, distilled skills,
-- etc.). Application-level cascade is in the adapter's delete path.
CREATE TABLE IF NOT EXISTS causal_links (
    id TEXT PRIMARY KEY,
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    evidence REAL NOT NULL CHECK (evidence > 0.0 AND evidence <= 1.0),
    last_evidence_at TIMESTAMP NOT NULL DEFAULT now(),
    link_origin TEXT NOT NULL CHECK (link_origin IN ('observed', 'inferred')),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    depth INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_causal_from ON causal_links(from_id);
CREATE INDEX IF NOT EXISTS idx_causal_to ON causal_links(to_id);
CREATE INDEX IF NOT EXISTS idx_causal_last_evidence ON causal_links(last_evidence_at);

-- Skill Distillation (Phase 1.5 #6).
-- A distilled skill is a learnable pattern extracted from observed
-- session activity. The shape is "for problems like X, try Y because
-- Z worked in N prior cases" — three short fields plus evidence.
--
-- The CHECK constraint on ``importance_score >= 0.7`` is the plan's
-- quality floor: skills below this threshold are not persisted
-- (the distiller filters them out at the application layer). The
-- Conscious Agent's LLM synthesis path can also rewrite
-- ``suggested_approach`` into better prose. The data layer doesn't
-- care which path produced the text — the ``model`` column records it.
--
-- ``source_memory_ids`` is a JSON array (stored as VARCHAR per the
-- v2 ``metadata`` pattern, no native JSON column in DuckDB). Each
-- entry is a conversation id that contributed to the distillation.
-- This is provenance for the skill: "N prior cases" comes from this
-- list's length.
CREATE TABLE IF NOT EXISTS distilled_skills (
    id TEXT PRIMARY KEY,
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
CREATE INDEX IF NOT EXISTS idx_distilled_importance ON distilled_skills(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_distilled_last_reinforced ON distilled_skills(last_reinforced_at DESC);
"""

# Migration from v1 to v2
MIGRATION_SQL = """
-- Migrate existing conversations to v2 schema
INSERT INTO conversations_v2 (
    id, content, embedding, category, memory_tier,
    project, timestamp, searchable_content
)
SELECT
    id,
    content,
    embedding,
    CASE
        WHEN content LIKE '%prefer%' THEN 'preferences'
        WHEN content LIKE '%error%' OR content LIKE '%bug%' THEN 'context'
        ELSE 'facts'
    END as category,
    'long_term' as memory_tier,
    project,
    timestamp,
    content as searchable_content
FROM conversations
WHERE id NOT IN (SELECT id FROM conversations_v2);

-- Migrate existing reflections
INSERT INTO reflections_v2 (
    id, content, embedding, category, tags, timestamp, project
)
SELECT
    id,
    content,
    embedding,
    'context' as category,  -- Default category
    tags,
    timestamp,
    NULL as project
FROM reflections
WHERE id NOT IN (SELECT id FROM reflections_v2);
"""
