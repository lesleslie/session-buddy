# DuckPGQ Knowledge Graph Implementation

**Date**: 2025-10-26
**Status**: In Progress

______________________________________________________________________

## Overview

Adding semantic memory (knowledge graph) to session-buddy using:

- **DuckDB + DuckPGQ** extension (no external database required!)
- **Separate database file**: `~/.claude/data/knowledge_graph.duckdb`
- **SQL/PGQ standard** (Property Graph Queries - SQL:2023)
- **Auto entity extraction** from conversations

______________________________________________________________________

## Architecture

### Dual Memory System

```
session-buddy Memory System
├── Episodic Memory (reflection.duckdb)
│   ├── conversations (vector search)
│   ├── reflections
│   └── Full conversation history
│
└── Semantic Memory (knowledge_graph.duckdb)
    ├── kg_entities (graph nodes)
    ├── kg_relationships (graph edges)
    └── Knowledge graph structure
```

### Why Separate Databases?

1. **Clean separation of concerns** - Conversations vs structured knowledge
1. **Independent scaling** - Can optimize each database separately
1. **Easier backup/restore** - Can backup knowledge graph independently
1. **Follows single responsibility principle**

______________________________________________________________________

## DuckPGQ Extension

### What is DuckPGQ?

DuckPGQ is a **community extension** for DuckDB that adds:

- SQL/PGQ support (Property Graph Queries - official SQL:2023 standard)
- Graph pattern matching with Cypher-like syntax
- Property graphs with nodes and edges
- Graph algorithms (shortest path, etc.)
- Persistent graphs

### Installation

```python
import duckdb

conn = duckdb.connect("~/.claude/data/knowledge_graph.duckdb")
conn.execute("INSTALL duckpgq FROM community")
conn.execute("LOAD duckpgq")
```

That's it! No external database needed.

### SQL/PGQ Query Examples

```sql
-- Find all projects that use Python
SELECT *
FROM GRAPH_TABLE (knowledge_graph
    MATCH (proj:Project)-[r:uses]->(lang:Language)
    WHERE lang.name = 'Python'
    COLUMNS (proj.name AS project_name, lang.name AS language)
);

-- Find paths between entities
SELECT *
FROM GRAPH_TABLE (knowledge_graph
    MATCH (start:Project)-[path:*1..3]->(end:Technology)
    WHERE start.name = 'session-buddy'
      AND end.name = 'ACB'
    COLUMNS (start.name AS from, end.name AS to, path)
);
```

______________________________________________________________________

## Implementation Components

### 1. KnowledgeGraphDatabase Class

**File**: `session_buddy/knowledge_graph_db.py`

**Key Methods**:

- `create_entity(name, entity_type, observations)` - Add node
- `create_relation(from, to, relation_type)` - Add edge
- `search_entities(query)` - Find nodes
- `find_path(from, to, max_depth)` - SQL/PGQ path finding
- `get_stats()` - Graph statistics

### 2. MCP Tools (10 total)

**File**: `session_buddy/tools/knowledge_graph_tools.py`

1. `create_entity` - Create node
1. `create_relation` - Create edge
1. `add_observation` - Add fact to entity
1. `search_entities` - Find entities
1. `find_relationships` - Get connections
1. `find_path` - Path between entities
1. `get_entity_details` - Full entity info
1. `list_entity_types` - Show all types
1. `list_relation_types` - Show all relations
1. `knowledge_graph_stats` - Statistics

### 3. Auto Entity Extraction

**File**: `session_buddy/extractors/entity_extractor.py`

Automatically extracts entities from conversations using:

- Regex patterns for projects, libraries, technologies
- Confidence scoring
- Integration with conversation storage

______________________________________________________________________

## Design Decisions

✅ **Separate database file** - Clean isolation
✅ **Separate KnowledgeGraphDatabase class** - Single responsibility
✅ **Auto entity extraction** - Knowledge graph builds automatically
✅ **Full testing** - Unit tests + integration tests

______________________________________________________________________

## Timeline

- **Phase 1**: Foundation & Schema (2-3 hours) - ✅ IN PROGRESS
- **Phase 2**: MCP Tools (3-4 hours)
- **Phase 3**: Auto Entity Extraction (4-5 hours)
- **Phase 4**: Testing (3-4 hours)
- **Phase 5**: Documentation & Migration (1-2 hours)

**Total**: ~14 hours over 4 days

______________________________________________________________________

## Benefits

1. ✅ **Zero installation** - DuckDB already in dependencies
1. ✅ **No external processes** - Everything embedded
1. ✅ **SQL standard** - SQL/PGQ is official SQL:2023
1. ✅ **Active development** - DuckDB blog post Oct 2025
1. ✅ **Perfect for local development**
1. ✅ **Auto-builds from conversations**

______________________________________________________________________

## References

- DuckPGQ: https://duckpgq.org/
- DuckDB Blog (Oct 2025): https://duckdb.org/2025/10/22/duckdb-graph-queries-duckpgq
- SQL/PGQ Documentation: https://duckpgq.org/documentation/sql_pgq/
