# Knowledge Graph Connectivity Enhancement - Progress Report

**Date:** 2025-02-09
**Project:** Session Buddy
**Component:** Knowledge Graph
**Status:** Phase 1 Complete, Phase 2 Ready to Start

---

## Executive Summary

The knowledge graph has very low connectivity (0.032 relationships per entity) which limits its usefulness for insights and recommendations. We've completed Phase 1 of the enhancement plan by adding embedding support to the schema. The next phase involves implementing automatic relationship discovery to increase connectivity 10-25x.

---

## Current State

### Database Statistics
```
Database: ~/.claude/data/knowledge_graph.duckdb
Size: 58.0 MB
Tables: 3 (kg_entities, kg_relationships, __duckpgq_internal)

Entities:
  Total: 597
  Types: test (312), project (135), library (91), service (58), concept (1)

Relationships:
  Total: 19
  Types: uses (5), extends (5), depends_on (4), requires (2), connects_to (2), related_to (1)

Connectivity:
  Ratio: 0.032 relationships per entity (extremely low)
  Target: 0.2-0.5 (6-15x improvement needed)

Embeddings:
  Column: ✅ Added (FLOAT[384])
  Coverage: 269/597 entities (45.1%)
  Model: all-MiniLM-L6-v2 (384 dimensions)
```

### Problems Identified

1. **Low Connectivity** (CRITICAL)
   - Only 19 relationships for 597 entities
   - Most entities are isolated (no connections)
   - Graph cannot provide meaningful insights

2. **Missing Auto-Discovery** (HIGH)
   - All relationships created manually
   - No semantic similarity linking
   - No automatic relationship creation

3. **Test Data Pollution** (MEDIUM)
   - 312 test entities (52%) from unit tests
   - Skews statistics, reduces quality
   - Should use separate test database

4. **Incomplete Embeddings** (MEDIUM)
   - Only 45% of entities have embeddings
   - Cannot perform semantic search on all entities
   - Need to generate missing embeddings

---

## Completed Work (Phase 1)

### ✅ 1. Schema Enhancement

**Action:** Added `embedding FLOAT[384]` column to `kg_entities` table

**Files Created:**
- `/Users/les/Projects/session-buddy/scripts/add_kg_embedding_column.py`
- `/Users/les/Projects/session-buddy/scripts/migrate_knowledge_graph_embeddings.py`

**Result:**
```sql
CREATE TABLE kg_entities (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    observations VARCHAR[],
    properties JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,
    embedding FLOAT[384]  -- ✅ NEW COLUMN
)
```

**Status:** ✅ Complete and verified

---

## Next Steps (Phase 2)

### Priority 1: Auto-Discovery System

**Goal:** Automatically create relationships when entities are created

**Implementation:**

1. **Add embedding generation to `create_entity()`**
   ```python
   async def create_entity(
       self,
       name: str,
       entity_type: str,
       observations: list[str] | None = None,
       auto_discover: bool = True,  # NEW
   ) -> dict[str, t.Any]:
       # Create entity
       entity = await self._create_entity_impl(...)

       # Auto-discover similar entities
       if auto_discover:
           await self._auto_discover_relationships(entity)

       return entity
   ```

2. **Implement semantic similarity search**
   ```python
   async def _find_similar_entities(
       self,
       embedding: list[float],
       threshold: float = 0.75,
       limit: int = 10,
   ) -> list[dict[str, t.Any]]:
       # Use DuckDB cosine similarity
       result = conn.execute("""
           SELECT name, entity_type,
                  array_cosine_similarity(embedding, ?) as similarity
           FROM kg_entities
           WHERE array_cosine_similarity(embedding, ?) > ?
           ORDER BY similarity DESC
           LIMIT ?
       """, (embedding, embedding, threshold, limit))
   ```

3. **Create relationships automatically**
   ```python
   async def _auto_discover_relationships(
       self,
       entity: dict[str, t.Any],
   ) -> None:
       # Generate embedding
       embedding = await self._generate_entity_embedding(entity)

       # Find similar entities
       similar = await self._find_similar_entities(embedding)

       # Create relationships
       for sim_entity in similar:
           await self.create_relation(
               from_entity=entity["name"],
               to_entity=sim_entity["name"],
               relation_type="related_to",
               properties={"similarity": sim_entity["score"]}
           )
   ```

**Files to Modify:**
- `session_buddy/adapters/knowledge_graph_adapter_oneiric.py`
- `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py`

**Expected Impact:**
- New entities will automatically connect to similar entities
- Connectivity ratio will increase organically over time
- Graph becomes self-organizing

---

### Priority 2: MCP Tools for Graph Management

**Goal:** Provide tools for manual graph enhancement and analysis

**Tools to Create:**

1. **`discover_relationships`** - Batch relationship discovery
   ```
   Usage: discover_relationships(threshold=0.75, limit=50)

   Action:
   - Find all entities without embeddings
   - Generate embeddings
   - Find similar entities
   - Create relationships

   Returns:
   - Number of relationships created
   - Similarity scores
   ```

2. **`generate_embeddings`** - Generate missing embeddings
   ```
   Usage: generate_embeddings(entity_type=None, batch_size=20)

   Action:
   - Process entities without embeddings
   - Generate embeddings in batches
   - Update database

   Returns:
   - Number processed
   - Success/failure counts
   ```

3. **`analyze_graph_connectivity`** - Graph health metrics
   ```
   Usage: analyze_graph_connectivity()

   Returns:
   - Connectivity ratio
   - Isolated entities count
   - Relationship distribution
   - Embedding coverage
   - Recommendations
   ```

4. **`create_semantic_relation`** - Smart relationship creation
   ```
   Usage: create_semantic_relation(from_entity, to_entity, context)

   Action:
   - Analyze context to determine relationship type
   - Calculate similarity score
   - Create bidirectional relationship if appropriate

   Returns:
   - Created relationship
   - Confidence score
   - Relationship type
   ```

**Files to Modify:**
- `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py`

---

### Priority 3: Enhanced Statistics

**Goal:** Better insight into graph health and connectivity

**Implementation:**

```python
async def get_stats(self) -> dict[str, t.Any]:
    """Get enhanced knowledge graph statistics."""

    # Basic counts
    entity_count = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
    relationship_count = conn.execute("SELECT COUNT(*) FROM kg_relationships").fetchone()[0]

    # Connectivity metrics
    connectivity_ratio = relationship_count / entity_count

    # Isolated entities (no relationships)
    isolated = conn.execute("""
        SELECT COUNT(DISTINCT e.id)
        FROM kg_entities e
        LEFT JOIN kg_relationships r ON (e.id = r.from_entity OR e.id = r.to_entity)
        WHERE r.id IS NULL
    """).fetchone()[0]

    # Embedding coverage
    with_embeddings = conn.execute(
        "SELECT COUNT(*) FROM kg_entities WHERE embedding IS NOT NULL"
    ).fetchone()[0]

    # Relationship type distribution
    rel_types = conn.execute("""
        SELECT relation_type, COUNT(*) as count
        FROM kg_relationships
        GROUP BY relation_type
        ORDER BY count DESC
    """).fetchall()

    return {
        "total_entities": entity_count,
        "total_relationships": relationship_count,
        "connectivity_ratio": round(connectivity_ratio, 3),
        "isolated_entities": isolated,
        "average_degree": round(relationship_count * 2 / entity_count, 2) if entity_count > 0 else 0,
        "embedding_coverage": round(with_embeddings / entity_count, 2) if entity_count > 0 else 0,
        "entity_types": {...},
        "relationship_types": dict(rel_types),
    }
```

**Files to Modify:**
- `session_buddy/adapters/knowledge_graph_adapter_oneiric.py`

---

### Priority 4: Testing & Validation

**Goal:** Ensure auto-discovery works correctly and performs well

**Tests to Create:**

1. **Unit Tests**
   ```python
   # test_knowledge_graph_discovery.py
   async def test_auto_discover_on_create():
       """Test that relationships are auto-created."""
       kg = KnowledgeGraphDatabaseAdapterOneiric()

       # Create entity with auto-discover
       entity1 = await kg.create_entity("test-project", "project", auto_discover=False)
       entity2 = await kg.create_entity("similar-project", "project", auto_discover=True)

       # Check that relationships were created
       relationships = await kg.get_relationships(entity2["name"])
       assert len(relationships) > 0
   ```

2. **Integration Tests**
   ```python
   async def test_discover_relationships_tool():
       """Test batch relationship discovery tool."""
       result = await discover_relationships_impl(threshold=0.75)
       assert "created" in result
       assert result["created"] > 0
   ```

3. **Performance Tests**
   ```python
   async def test_similarity_search_performance():
       """Test that similarity search is fast."""
       start = time.time()
       similar = await kg._find_similar_entities(embedding, limit=10)
       elapsed = time.time() - start
       assert elapsed < 0.1  # Should be < 100ms
   ```

**Files to Create:**
- `tests/unit/test_knowledge_graph_discovery.py`
- `tests/integration/test_kg_auto_discovery.py`
- `tests/performance/test_kg_similarity_search.py`

---

## Implementation Timeline

### Week 1: Core Auto-Discovery
- [ ] Day 1-2: Add embedding generation methods
- [ ] Day 3-4: Implement semantic similarity search
- [ ] Day 5: Integrate auto-discovery into create_entity()

### Week 2: MCP Tools
- [ ] Day 1-2: Implement discover_relationships tool
- [ ] Day 3: Implement generate_embeddings tool
- [ ] Day 4: Implement analyze_graph_connectivity tool
- [ ] Day 5: Implement create_semantic_relation tool

### Week 3: Testing & Refinement
- [ ] Day 1-2: Write unit tests
- [ ] Day 3: Write integration tests
- [ ] Day 4: Performance testing and optimization
- [ ] Day 5: Bug fixes and refinement

### Week 4: Polish & Documentation
- [ ] Day 1-2: Clean up test data
- [ ] Day 3: Add comprehensive documentation
- [ ] Day 4: Create usage examples
- [ ] Day 5: Final review and validation

---

## Expected Results

### Before (Current)
```
Entities: 597
Relationships: 19
Connectivity: 0.032
Isolated: ~580 entities (97%)
Embedding Coverage: 45%
Auto-Discovery: Disabled
```

### After (Target)
```
Entities: 597
Relationships: 200-500 (10-25x increase)
Connectivity: 0.33-0.84 (10-25x improvement)
Isolated: <100 entities (<17%)
Embedding Coverage: 100%
Auto-Discovery: Enabled
```

### Benefits

1. **Better Recommendations**
   - Find related projects, libraries, concepts
   - Discover hidden connections between topics
   - Navigate knowledge graph semantically

2. **Automatic Organization**
   - Graph self-organizes as entities are added
   - Relationships emerge naturally from similarity
   - Minimal manual intervention required

3. **Enhanced Search**
   - Semantic similarity search
   - Graph-based path finding
   - Multi-hop relationship queries

4. **Insight Discovery**
   - Uncover unexpected connections
   - Identify entity clusters
   - Find influential entities (high degree)

---

## Success Metrics

### Quantitative
- [ ] Connectivity ratio > 0.2 (10x improvement)
- [ ] 100% embedding coverage
- [ ] < 100 isolated entities
- [ ] Average relationship confidence > 0.75
- [ ] Graph query performance < 100ms

### Qualitative
- [ ] New entities automatically connect to similar entities
- [ ] Search results improve with semantic similarity
- [ ] Users discover unexpected connections
- [ ] Graph provides actionable insights

---

## Files Created/Modified

### Created
1. `/Users/les/Projects/session-buddy/scripts/add_kg_embedding_column.py`
2. `/Users/les/Projects/session-buddy/scripts/migrate_knowledge_graph_embeddings.py`
3. `/Users/les/Projects/session-buddy/KNOWLEDGE_GRAPH_CONNECTIVITY_PLAN.md`
4. `/Users/les/Projects/session-buddy/IMPLEMENTATION_SUMMARY.md`
5. `/Users/les/Projects/session-buddy/KNOWLEDGE_GRAPH_ENHANCEMENT_REPORT.md`

### To Modify (Next Phase)
1. `session_buddy/adapters/knowledge_graph_adapter_oneiric.py`
   - Add `_generate_entity_embedding()` method
   - Add `_find_similar_entities()` method
   - Modify `create_entity()` to support auto-discover
   - Enhance `get_stats()` with connectivity metrics

2. `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py`
   - Add `discover_relationships` tool
   - Add `generate_embeddings` tool
   - Add `analyze_graph_connectivity` tool
   - Add `create_semantic_relation` tool

3. `tests/unit/test_knowledge_graph_adapter.py`
   - Add tests for embedding generation
   - Add tests for similarity search
   - Add tests for auto-discovery

---

## Risks & Mitigation

### Risk 1: Performance Degradation
**Impact:** Slow entity creation due to embedding generation and similarity search
**Probability:** Medium
**Mitigation:**
- Use async operations for blocking calls
- Implement caching for similarity search
- Batch operations where possible

### Risk 2: Low-Quality Auto-Relationships
**Impact:** Noisy relationships reduce graph quality
**Probability:** Medium
**Mitigation:**
- Use high similarity threshold (0.75)
- Store confidence scores for manual review
- Provide tools to delete bad relationships

### Risk 3: Database Bloat
**Impact:** Increased database size from embeddings and relationships
**Probability:** Low
**Mitigation:**
- Monitor database size
- Implement retention policies if needed
- Archive old test entities

### Risk 4: Test Data Pollution
**Impact:** Test entities skew statistics and recommendations
**Probability:** High
**Mitigation:**
- Use separate test database (preferred)
- Or add `is_test` flag and filter in queries
- Periodically clean up test entities

---

## Conclusion

Phase 1 is complete. The knowledge graph schema now supports embeddings for semantic similarity search. The next phase involves implementing automatic relationship discovery to increase connectivity from 0.032 to 0.2-0.5, making the graph 10-25x more useful for insights and recommendations.

The key insight is that **relationships are more valuable than entities** in knowledge graphs. With 597 entities, we should have 600-3000 relationships to make the graph truly useful. Auto-discovery will achieve this organically as new entities are added.

**Next Action:** Begin Phase 2 implementation by adding auto-discovery to the knowledge graph adapter.

---

**Report Prepared By:** Data Engineering Specialist
**Report Date:** 2025-02-09
**Status:** Phase 1 Complete, Phase 2 Ready
