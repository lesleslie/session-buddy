# Knowledge Graph Connectivity Enhancement - Implementation Summary

## Status: Phase 1 Complete

### Completed Tasks

#### 1. Schema Migration ✅
- **File:** `/Users/les/Projects/session-buddy/scripts/add_kg_embedding_column.py`
- **Action:** Added `embedding FLOAT[384]` column to `kg_entities` table
- **Status:** Column successfully added and verified
- **Database:** `~/.claude/data/knowledge_graph.duckdb`

#### 2. Migration Script Created ✅
- **File:** `/Users/les/Projects/session-buddy/scripts/migrate_knowledge_graph_embeddings.py`
- **Features:**
  - Batch processing of entities
  - Embedding generation using existing ONNX model
  - Progress tracking and error handling
  - Dry-run mode for testing
- **Note:** Script works but embedding generation is slow for 597 entities
- **Decision:** Generate embeddings on-demand instead of batch migration

### Current Knowledge Graph State

```
Database: ~/.claude/data/knowledge_graph.duckdb (58.0 MB)

Schema:
  kg_entities (597 rows)
    - id, name, entity_type
    - observations, properties
    - created_at, updated_at, metadata
    - embedding FLOAT[384] ✅ NEW

  kg_relationships (19 rows)
    - id, from_entity, to_entity
    - relation_type, properties
    - created_at, updated_at, metadata

Connectivity Issues:
  - 597 entities, 19 relationships = 0.032 ratio (very low)
  - 312 test entities (52%) polluting production graph
  - No automatic relationship discovery
  - No semantic similarity linking
```

### Next Steps (Prioritized)

#### Priority 1: Auto-Discovery System

**Files to Modify:**
1. `session_buddy/adapters/knowledge_graph_adapter_oneiric.py`
2. `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py`

**Implementation:**

```python
# In knowledge_graph_adapter_oneiric.py

async def create_entity(
    self,
    name: str,
    entity_type: str,
    observations: list[str] | None = None,
    properties: dict[str, t.Any] | None = None,
    metadata: dict[str, t.Any] | None = None,
    auto_discover: bool = True,  # NEW: Enable auto-discovery
) -> dict[str, t.Any]:
    """Create entity with optional automatic relationship discovery."""

    # Create entity
    entity = await self._create_entity_impl(...)

    # Generate embedding
    if auto_discover:
        embedding = await self._generate_entity_embedding(entity)
        # Update entity with embedding

        # Discover similar entities
        similar = await self._find_similar_entities(
            embedding=embedding,
            threshold=0.75,
            limit=10
        )

        # Create relationships
        for similar_entity in similar:
            await self.create_relation(
                from_entity=name,
                to_entity=similar_entity["name"],
                relation_type="related_to",
                properties={"similarity": similar_entity["score"]}
            )

    return entity
```

#### Priority 2: Semantic Similarity Search

```python
async def _find_similar_entities(
    self,
    embedding: list[float] | None = None,
    entity_name: str | None = None,
    threshold: float = 0.75,
    limit: int = 10,
) -> list[dict[str, t.Any]]:
    """Find semantically similar entities using cosine similarity."""

    conn = self._get_conn()

    # Use provided embedding or generate from entity name
    if embedding is None:
        entity = await self.find_entity_by_name(entity_name)
        embedding = entity.get("embedding")

    if not embedding:
        return []

    # DuckDB cosine similarity search
    result = conn.execute("""
        SELECT
            name,
            entity_type,
            array_cosine_similarity(embedding, ?) as similarity
        FROM kg_entities
        WHERE embedding IS NOT NULL
          AND array_cosine_similarity(embedding, ?) > ?
          AND name != ?
        ORDER BY similarity DESC
        LIMIT ?
    """, (embedding, embedding, threshold, entity_name, limit)).fetchall()

    return [
        {
            "name": row[0],
            "entity_type": row[1],
            "score": float(row[2])
        }
        for row in result
    ]
```

#### Priority 3: New MCP Tools

```python
# Tool 1: discover_relationships
@mcp_server.tool()
async def discover_relationships(
    similarity_threshold: float = 0.75,
    limit: int = 50
) -> str:
    """Automatically discover and create relationships between similar entities."""
    # Implementation creates relationships for entities without connections

# Tool 2: generate_embeddings
@mcp_server.tool()
async def generate_embeddings(
    entity_type: str | None = None,
    batch_size: int = 20
) -> str:
    """Generate embeddings for entities missing them."""
    # Implementation processes entities without embeddings

# Tool 3: analyze_graph_connectivity
@mcp_server.tool()
async def analyze_graph_connectivity() -> str:
    """Analyze graph health and connectivity metrics."""
    # Returns connectivity ratio, isolated entities, recommendations

# Tool 4: create_semantic_relation
@mcp_server.tool()
async def create_semantic_relation(
    from_entity: str,
    to_entity: str,
    context: str | None = None
) -> str:
    """Create relationship with automatic type detection."""
    # Analyzes context to determine best relationship type
```

#### Priority 4: Enhanced Statistics

```python
async def get_stats(self) -> dict[str, t.Any]:
    """Get enhanced knowledge graph statistics."""

    conn = self._get_conn()

    # Basic counts
    entity_count = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
    relationship_count = conn.execute("SELECT COUNT(*) FROM kg_relationships").fetchone()[0]

    # Connectivity metrics
    isolated_entities = conn.execute("""
        SELECT COUNT(DISTINCT e.id)
        FROM kg_entities e
        LEFT JOIN kg_relationships r ON (e.id = r.from_entity OR e.id = r.to_entity)
        WHERE r.id IS NULL
    """).fetchone()[0]

    # Connectivity ratio
    connectivity_ratio = relationship_count / entity_count if entity_count > 0 else 0

    # Embedding coverage
    entities_with_embeddings = conn.execute(
        "SELECT COUNT(*) FROM kg_entities WHERE embedding IS NOT NULL"
    ).fetchone()[0]

    return {
        "total_entities": entity_count,
        "total_relationships": relationship_count,
        "connectivity_ratio": connectivity_ratio,
        "isolated_entities": isolated_entities,
        "embedding_coverage": entities_with_embeddings / entity_count if entity_count > 0 else 0,
        "entity_types": {...},
        "relationship_types": {...},
    }
```

### Implementation Order

1. **Week 1: Core Auto-Discovery**
   - [ ] Add `_generate_entity_embedding()` method
   - [ ] Add `_find_similar_entities()` method
   - [ ] Modify `create_entity()` to support `auto_discover` parameter
   - [ ] Add embedding generation on entity creation

2. **Week 2: MCP Tools**
   - [ ] Implement `discover_relationships` tool
   - [ ] Implement `generate_embeddings` tool
   - [ ] Implement `analyze_graph_connectivity` tool
   - [ ] Implement `create_semantic_relation` tool

3. **Week 3: Enhanced Statistics & Testing**
   - [ ] Enhance `get_stats()` with connectivity metrics
   - [ ] Add unit tests for auto-discovery
   - [ ] Add integration tests for semantic search
   - [ ] Performance testing with 1000+ entities

4. **Week 4: Data Quality**
   - [ ] Clean up test entities (or filter them out)
   - [ ] Validate existing relationships
   - [ ] Add relationship confidence scoring
   - [ ] Documentation and examples

### Expected Results

**Before (Current):**
- Entities: 597
- Relationships: 19
- Connectivity: 0.032
- Embedding coverage: 0%

**After (Target):**
- Entities: 597
- Relationships: 200-500 (3-8x increase)
- Connectivity: 0.33-0.84 (10-25x improvement)
- Embedding coverage: 100%
- Auto-discovery: Enabled for new entities

### Testing Strategy

```bash
# 1. Test schema changes
python scripts/test_database_status.py

# 2. Test embedding generation
python scripts/generate_test_embeddings.py

# 3. Test auto-discovery
pytest tests/unit/test_knowledge_graph_discovery.py -v

# 4. Test MCP tools
pytest tests/integration/test_knowledge_graph_tools.py -v

# 5. Performance test
pytest tests/performance/test_kg_scaling.py -v
```

### Risks & Mitigation

**Risk 1: Performance**
- Embedding generation: ~50ms per entity
- Similarity search: Fast with DuckDB cosine similarity
- Mitigation: Batch processing, async operations

**Risk 2: Low-Quality Relationships**
- Auto-discovery might create noisy relationships
- Mitigation: High similarity threshold (0.75), manual review tools

**Risk 3: Database Size**
- 597 entities × 1.5 KB = ~900 KB for embeddings
- Mitigation: Monitor size, implement retention if needed

### Success Metrics

- [ ] 100% embedding coverage for all entities
- [ ] Connectivity ratio > 0.2 (10x improvement)
- [ ] < 100 isolated entities (down from ~580)
- [ ] Average relationship confidence > 0.75
- [ ] Graph query performance < 100ms
- [ ] Auto-discovery enabled by default

### Files Modified

1. **Created:**
   - `/Users/les/Projects/session-buddy/scripts/add_kg_embedding_column.py`
   - `/Users/les/Projects/session-buddy/scripts/migrate_knowledge_graph_embeddings.py`
   - `/Users/les/Projects/session-buddy/KNOWLEDGE_GRAPH_CONNECTIVITY_PLAN.md`
   - `/Users/les/Projects/session-buddy/IMPLEMENTATION_SUMMARY.md`

2. **To Modify:**
   - `session_buddy/adapters/knowledge_graph_adapter_oneiric.py`
   - `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py`
   - `tests/unit/test_knowledge_graph_adapter.py`

### Next Actions

1. ✅ Add embedding column to schema
2. ⏳ Implement auto-discovery in adapter
3. ⏳ Add semantic similarity search
4. ⏳ Create new MCP tools
5. ⏳ Enhance statistics reporting
6. ⏳ Add comprehensive tests
7. ⏳ Clean up test data
8. ⏳ Document usage patterns

---

**Phase 1 Status:** ✅ COMPLETE
**Phase 2 Status:** ⏳ PENDING (Auto-Discovery Implementation)
**Overall Progress:** 20% COMPLETE
