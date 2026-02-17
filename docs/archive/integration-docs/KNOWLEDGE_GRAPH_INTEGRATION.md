# Knowledge Graph Integration (DuckPGQ)

**Version:** 2.0
**Status:** Complete (Week 2 Days 1-2)
**Database:** DuckDB + DuckPGQ Extension

______________________________________________________________________

## Overview

The session-buddy server now includes a **semantic memory system** powered by DuckDB's DuckPGQ extension, which implements SQL:2023 Property Graph Queries (SQL/PGQ). This provides a knowledge graph for storing and querying entity-relationship data about projects, libraries, technologies, and concepts.

### What is DuckPGQ?

DuckPGQ is a DuckDB extension that adds SQL/PGQ capabilities:

- **Property Graph Model**: Store nodes (entities) and edges (relationships)
- **SQL:2023 Standard**: Use standard SQL syntax for graph queries
- **High Performance**: In-process analytics with no external dependencies
- **Path Finding**: Built-in graph pattern matching queries

### Knowledge Graph vs. Episodic Memory

| Feature | Episodic Memory (ReflectionDatabase) | Semantic Memory (Knowledge Graph) |
|---------|-------------------------------------|-----------------------------------|
| **Storage** | Conversations & reflections | Entities & relationships |
| **Structure** | Flat documents with embeddings | Graph with nodes & edges |
| **Search** | Vector similarity | Graph pattern matching |
| **Use Case** | "What did we discuss about X?" | "How are X and Y connected?" |
| **Example** | Find past debugging sessions | Map project dependencies |

**They complement each other:**

- Episodic memory stores *what happened*
- Semantic memory stores *what exists and how it relates*

______________________________________________________________________

## Architecture

### Core Components

1. **KnowledgeGraphDatabase Class** (`knowledge_graph_db.py`)

   - 668 lines of production-ready code
   - Async/await support with context managers
   - DuckPGQ property graph creation and management

1. **9 MCP Tools** (`tools/knowledge_graph_tools.py`)

   - Full CRUD operations for entities and relationships
   - Auto-extraction from conversation context
   - Graph statistics and path finding

1. **Database Schema**:

   ```sql
   -- Entities (nodes/vertices)
   CREATE TABLE kg_entities (
       id VARCHAR PRIMARY KEY,
       name VARCHAR NOT NULL,
       entity_type VARCHAR NOT NULL,
       observations VARCHAR[],  -- Facts about this entity
       properties JSON,
       created_at TIMESTAMP,
       updated_at TIMESTAMP,
       metadata JSON
   );

   -- Relationships (edges)
   CREATE TABLE kg_relationships (
       id VARCHAR PRIMARY KEY,
       from_entity VARCHAR NOT NULL,
       to_entity VARCHAR NOT NULL,
       relation_type VARCHAR NOT NULL,
       properties JSON,
       created_at TIMESTAMP,
       metadata JSON,
       FOREIGN KEY (from_entity) REFERENCES kg_entities(id),
       FOREIGN KEY (to_entity) REFERENCES kg_entities(id)
   );

   -- Property graph
   CREATE PROPERTY GRAPH knowledge_graph
       VERTEX TABLES (kg_entities)
       EDGE TABLES (
           kg_relationships
               SOURCE KEY (from_entity) REFERENCES kg_entities (id)
               DESTINATION KEY (to_entity) REFERENCES kg_entities (id)
       );
   ```

______________________________________________________________________

## Available MCP Tools

### 1. `create_entity`

Create a new entity (node) in the knowledge graph.

**Parameters:**

- `name` (str): Entity name (e.g., "session-buddy", "Python 3.13")
- `entity_type` (str): Type (e.g., "project", "language", "library", "concept")
- `observations` (list[str], optional): Facts about this entity
- `properties` (dict, optional): Additional structured properties

**Example:**

```text
create_entity(
    name="session-buddy",
    entity_type="project",
    observations=[
        "Claude session management MCP server",
        "Built with FastMCP and ACB",
        "Uses DuckDB for storage",
    ],
    properties={"language": "Python", "version": "2.0"},
)
```

**Returns:**

```
✅ Entity 'session-buddy' created successfully!
📊 Type: project
🆔 ID: 01947e12-5678-7abc-9def-1a2b3c4d5e6f
📝 Observations: 3
⚙️ Properties: language, version
```

______________________________________________________________________

### 2. `add_observation`

Add a fact/observation to an existing entity.

**Parameters:**

- `entity_name` (str): Name of the entity
- `observation` (str): Fact to add

**Example:**

```python
add_observation(
    entity_name="session-buddy", observation="Supports automatic context compaction"
)
```

______________________________________________________________________

### 3. `create_relation`

Create a relationship between two entities.

**Parameters:**

- `from_entity` (str): Source entity name
- `to_entity` (str): Target entity name
- `relation_type` (str): Relationship type (e.g., "uses", "depends_on", "developed_by")
- `properties` (dict, optional): Relationship properties

**Common Relationship Types:**

- `uses` - Project uses library/technology
- `depends_on` - Project depends on another project
- `developed_by` - Project developed by person/team
- `implements` - Project implements concept
- `extends` - Library extends another library

**Example:**

```text
create_relation(
    from_entity="session-buddy",
    to_entity="ACB",
    relation_type="uses",
    properties={"since_version": "1.0"},
)
```

**Returns:**

```
✅ Relationship created: session-buddy --[uses]--> ACB
🆔 Relation ID: 01947e12-1234-5678-9abc-def012345678
⚙️ Properties: since_version
```

______________________________________________________________________

### 4. `search_entities`

Search for entities by name or observations.

**Parameters:**

- `query` (str): Search query (matches name and observations)
- `entity_type` (str, optional): Filter by type
- `limit` (int, default=10): Maximum results

**Example:**

```text
search_entities(query="session management", entity_type="project", limit=5)
```

**Returns:**

```
🔍 Found 2 entities matching 'session management':

📌 session-buddy (project)
   📝 Observations: 3
   └─ Claude session management MCP server

📌 crackerjack (project)
   📝 Observations: 2
   └─ Includes session management features
```

______________________________________________________________________

### 5. `get_entity_relationships`

Get all relationships for a specific entity.

**Parameters:**

- `entity_name` (str): Entity to find relationships for
- `relation_type` (str, optional): Filter by relationship type
- `direction` (str, default="both"): "outgoing", "incoming", or "both"

**Example:**

```python
get_entity_relationships(entity_name="session-buddy", direction="outgoing")
```

**Returns:**

```
🔗 Found 5 relationships for 'session-buddy':

  session-buddy --[uses]--> ACB
  session-buddy --[uses]--> FastMCP
  session-buddy --[uses]--> DuckDB
  session-buddy --[depends_on]--> Python 3.13
  session-buddy --[implements]--> Model Context Protocol
```

______________________________________________________________________

### 6. `find_path`

Find paths between two entities using SQL/PGQ graph queries.

**Parameters:**

- `from_entity` (str): Starting entity name
- `to_entity` (str): Target entity name
- `max_depth` (int, default=5): Maximum path length

**Example:**

```python
find_path(from_entity="session-buddy", to_entity="Claude", max_depth=5)
```

**Returns:**

```
🛤️ Found 2 path(s) from 'session-buddy' to 'Claude':

1. Path length: 3 hop(s)
   session-buddy ➜ ... ➜ Claude

2. Path length: 4 hop(s)
   session-buddy ➜ ... ➜ Claude
```

**Behind the scenes (SQL/PGQ query):**

```sql
SELECT *
FROM GRAPH_TABLE (knowledge_graph
    MATCH (start)-[path:*1..5]->(end)
    WHERE start.id = '...'
      AND end.id = '...'
    COLUMNS (
        start.name AS from_name,
        end.name AS to_name,
        length(path) AS path_length
    )
)
```

______________________________________________________________________

### 7. `get_knowledge_graph_stats`

Get statistics about the knowledge graph.

**Returns:**

```
📊 Knowledge Graph Statistics

📌 Total Entities: 42
🔗 Total Relationships: 68

📊 Entity Types:
   • project: 12
   • library: 15
   • technology: 8
   • concept: 7

🔗 Relationship Types:
   • uses: 35
   • depends_on: 18
   • implements: 10
   • extends: 5

💾 Database: ~/.claude/data/knowledge_graph.duckdb
🔧 DuckPGQ: ✅ Installed
```

______________________________________________________________________

### 8. `extract_entities_from_context`

Auto-extract entities from conversation context using pattern matching.

**Parameters:**

- `context` (str): Text to extract entities from
- `auto_create` (bool, default=False): Automatically create detected entities

**Detection Patterns:**

- **Projects**: Kebab-case names (e.g., "session-buddy", "mcp-common")
- **Libraries**: Known names (ACB, FastMCP, DuckDB, pytest, pydantic, etc.)
- **Technologies**: Python, JavaScript, TypeScript, Docker, Kubernetes
- **Concepts**: "dependency injection", "semantic memory", "property graph", etc.

**Example:**

```text
extract_entities_from_context(
    context="The session-buddy project uses ACB for dependency injection and DuckDB for semantic memory.",
    auto_create=True,
)
```

**Returns:**

```
🔍 Extracted Entities from Context:

📊 Project:
   • session-buddy

📊 Library:
   • ACB
   • DuckDB

📊 Concept:
   • dependency injection
   • semantic memory

📊 Total Extracted: 5
✅ Auto-created: 3 new entities
```

______________________________________________________________________

### 9. `batch_create_entities`

Bulk create multiple entities in one operation.

**Parameters:**

- `entities` (list[dict]): List of entity dictionaries with keys:
  - `name` (str, required)
  - `entity_type` (str, required)
  - `observations` (list[str], optional)
  - `properties` (dict, optional)

**Example:**

```text
batch_create_entities(
    [
        {
            "name": "FastMCP",
            "entity_type": "library",
            "observations": ["MCP server framework", "Built by Jlowin"],
        },
        {
            "name": "ACB",
            "entity_type": "library",
            "observations": ["Asynchronous Component Base framework"],
        },
        {
            "name": "DuckDB",
            "entity_type": "database",
            "observations": ["In-process analytics database"],
        },
    ]
)
```

**Returns:**

```
📦 Batch Entity Creation Results:

✅ Successfully Created: 3
   • FastMCP
   • ACB
   • DuckDB

❌ Failed: 0
```

______________________________________________________________________

## Usage Patterns

### Pattern 1: Project Documentation

Build a knowledge graph of your project dependencies:

```python
# 1. Create project entities
create_entity(
    name="session-buddy",
    entity_type="project",
    observations=["Claude session management server"],
)

create_entity(
    name="mcp-common",
    entity_type="library",
    observations=["ACB-native foundation library for MCP servers"],
)

# 2. Create relationships
create_relation(
    from_entity="session-buddy",
    to_entity="mcp-common",
    relation_type="depends_on",
    properties={"version": "2.0.0"},
)

# 3. Query dependencies
get_entity_relationships(entity_name="session-buddy", direction="outgoing")
```

______________________________________________________________________

### Pattern 2: Technology Stack Mapping

Map your technology choices and their relationships:

```python
# Auto-extract from architecture discussions
extract_entities_from_context(
    context="""
    Our stack uses Python 3.13 with FastMCP for the MCP server.
    We use DuckDB for storage and ACB for dependency injection.
    """,
    auto_create=True,
)

# Find how technologies connect
find_path(from_entity="Python 3.13", to_entity="DuckDB", max_depth=3)
```

______________________________________________________________________

### Pattern 3: Concept Relationship Exploration

Understand how concepts relate across your projects:

```python
# Create concept entities
create_entity(
    name="dependency injection",
    entity_type="concept",
    observations=[
        "Design pattern for loose coupling",
        "Implemented via ACB in session-buddy",
    ],
)

create_entity(
    name="semantic memory",
    entity_type="concept",
    observations=["Knowledge graph storage", "Implemented via DuckPGQ"],
)

# Link concepts to implementations
create_relation(
    from_entity="session-buddy",
    to_entity="dependency injection",
    relation_type="implements",
)

create_relation(
    from_entity="session-buddy",
    to_entity="semantic memory",
    relation_type="implements",
)

# Search for related concepts
search_entities(query="memory", entity_type="concept")
```

______________________________________________________________________

## Performance & Scalability

### Database Storage

- **Location**: `~/.claude/data/knowledge_graph.duckdb`
- **Size**: Scales with entity/relationship count
- **Typical Size**: 1MB for 1,000 entities + 2,000 relationships
- **Max Practical**: 100K+ entities (DuckDB can handle millions)

### Query Performance

| Operation | Complexity | Performance |
|-----------|-----------|-------------|
| Create entity | O(1) | \<1ms |
| Search entities | O(n) | \<10ms for 1K entities |
| Get relationships | O(r) | \<5ms for 100 rels |
| Find path (depth 5) | O(b^d) | \<50ms in typical graphs |

**Optimizations:**

- Indexes on `entity_type`, `name`, `relation_type`
- DuckDB's columnar storage for analytics
- Lazy initialization (database opened on first use)

______________________________________________________________________

## Integration with Existing Systems

### With ReflectionDatabase (Episodic Memory)

```python
# Store conversation in episodic memory
store_reflection(
    content="Discussed ACB integration patterns for session-buddy",
    tags=["acb", "architecture"],
)

# Extract entities and store in knowledge graph
extract_entities_from_context(
    context="Discussed ACB integration patterns for session-buddy", auto_create=True
)

# Link conversation to entities
# (Future feature: automatic linking via entity mentions)
```

### With Crackerjack Quality Metrics

```python
# After running crackerjack analysis
create_entity(
    name="session-buddy-v2.0",
    entity_type="release",
    observations=[
        f"Test coverage: {coverage_percent}%",
        f"Quality score: {quality_score}/100",
    ],
)
```

______________________________________________________________________

## Development Guidelines

### Entity Naming Conventions

- **Projects**: Use kebab-case (e.g., `session-buddy`)
- **Libraries**: Use official name (e.g., `FastMCP`, `DuckDB`)
- **Technologies**: Use canonical name (e.g., `Python 3.13`)
- **Concepts**: Use lowercase with spaces (e.g., `dependency injection`)

### Relationship Types

**Standard Types** (use these for consistency):

- `uses` - Direct usage relationship
- `depends_on` - Dependency relationship
- `implements` - Implementation of concept/interface
- `extends` - Extension or subclassing
- `developed_by` - Authorship/ownership
- `references` - Documentation or citation

**Custom Types**: Create as needed, but document them in observations.

### Observations Best Practices

✅ **Good Observations:**

- "Built with FastMCP 2.0 framework"
- "Test coverage: 94.57%"
- "Implements SQL:2023 property graph queries"

❌ **Avoid:**

- "Good" (too vague)
- "Created on 2025-10-26" (use metadata instead)
- Duplicate information already in properties

______________________________________________________________________

## Testing

See `tests/unit/test_knowledge_graph_tools.py` for comprehensive test coverage:

- ✅ Entity creation and retrieval
- ✅ Relationship management
- ✅ Search functionality
- ✅ Path finding
- ✅ Auto-extraction patterns
- ✅ Batch operations
- ✅ Error handling

**Run tests:**

```bash
pytest tests/unit/test_knowledge_graph_tools.py -v
```

______________________________________________________________________

## Future Enhancements

### Planned Features (Week 3+)

1. **Auto-linking**: Automatically link conversations to mentioned entities
1. **Semantic Search**: Combine vector embeddings with graph queries
1. **Visualization**: Export to graph visualization formats (Graphviz, Mermaid)
1. **Import/Export**: JSON/CSV import/export for bulk operations
1. **Graph Analytics**: Centrality, clustering, community detection

### Integration Opportunities

- **GitHub Integration**: Auto-create entities from repository analysis
- **Documentation**: Link API docs to entity observations
- **Metrics Tracking**: Store quality metrics as time-series observations

______________________________________________________________________

## Troubleshooting

### DuckPGQ Installation

**Error:** `Failed to install DuckPGQ extension`

**Solution:**

```bash
# DuckPGQ requires DuckDB ≥0.9.0
uv sync  # Ensures correct DuckDB version

# Manual test:
python -c "
import duckdb
conn = duckdb.connect(':memory:')
conn.execute('INSTALL duckpgq FROM community')
conn.execute('LOAD duckpgq')
print('✅ DuckPGQ installed successfully')
"
```

### Database File Locked

**Error:** `database is locked`

**Cause**: Multiple processes accessing the same database file.

**Solution**:

- Knowledge graph uses async context managers for proper cleanup
- Ensure tools complete before running concurrent operations
- Database automatically closes on context manager exit

______________________________________________________________________

## References

- **DuckPGQ Documentation**: https://duckpgq.com/
- **SQL/PGQ Standard**: ISO/IEC 9075-16:2023
- **DuckDB Documentation**: https://duckdb.org/
- **Implementation**: `session_buddy/knowledge_graph_db.py`

______________________________________________________________________

**Last Updated:** Week 2 Day 2 (2025-10-26)
**Status:** ✅ Production Ready
