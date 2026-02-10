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
    reasoning TEXT  -- Why this memory is important
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
    last_accessed TIMESTAMP
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
CREATE TABLE IF NOT EXISTS memory_access_log (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    access_type TEXT,  -- search, retrieve, promote, demote
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES conversations_v2(id)
);

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
