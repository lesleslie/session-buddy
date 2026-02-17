# Knowledge Graph Connectivity Improvement Plan

## Current State Analysis

**Database:** `~/.claude/data/knowledge_graph.duckdb` (58.0 MB)

### Statistics
- **Total Entities:** 597
- **Total Relationships:** 19
- **Connectivity Ratio:** 0.032 relationships per entity (extremely low)

### Entity Distribution
- `test`: 312 entities (52%)
- `project`: 135 entities (23%)
- `library`: 91 entities (15%)
- `service`: 58 entities (10%)
- `concept`: 1 entity (<1%)

### Relationship Distribution
- `uses`: 5 relationships (26%)
- `extends`: 5 relationships (26%)
- `depends_on`: 4 relationships (21%)
- `requires`: 2 relationships (11%)
- `connects_to`: 2 relationships (11%)
- `related_to`: 1 relationship (5%)

## Problems Identified

### 1. Missing Embedding Column
- **Issue:** Schema references `embedding` column but it doesn't exist in `kg_entities` table
- **Impact:** Cannot perform semantic similarity-based relationship discovery
- **Solution:** Add `embedding FLOAT[384]` column and generate embeddings for existing entities

### 2. Manual Relationship Creation Only
- **Issue:** All relationships are created manually via MCP tools
- **Impact:** Very low connectivity (0.032 ratio) limits graph usefulness
- **Solution:** Implement automatic relationship discovery during entity creation and periodic analysis

### 3. No Semantic Relationship Discovery
- **Issue:** No mechanism to discover relationships based on entity similarity
- **Impact:** Missed opportunities to connect related concepts, libraries, projects
- **Solution:** Use embeddings to find semantically similar entities and create relationships

### 4. Test Entities Pollution
- **Issue:** 312 test entities (52%) from unit tests
- **Impact:** Skews statistics, reduces graph quality for production use
- **Solution:** Either clean up test data or use separate test database

## Proposed Solutions

### Phase 1: Fix Schema (Critical)

#### 1.1 Add Embedding Column
```python
# Migration script
ALTER TABLE kg_entities ADD COLUMN embedding FLOAT[384]
```

#### 1.2 Generate Embeddings for Existing Entities
- Extract entity names + observations as text
- Generate embeddings using existing ONNX model (all-MiniLM-L6-v2)
- Update entities with embedding vectors

### Phase 2: Implement Auto-Discovery

#### 2.1 Automatic Relationship Creation on Entity Creation
When creating a new entity:
1. Generate embedding for entity (name + observations)
2. Find semantically similar existing entities (cosine similarity > 0.75)
3. Create "related_to" relationships automatically
4. Detect explicit relationships from observations (uses, extends, depends_on)

#### 2.2 Periodic Relationship Discovery
Run periodically or on demand:
1. Find all entities without embeddings
2. Generate missing embeddings
3. For each entity, find similar entities
4. Create relationships with metadata about similarity score

#### 2.3 Entity-Project Linking
- Link entities to projects mentioned in their properties/observations
- Create "part_of" relationships when entity belongs to a project
- Create "references" relationships when entity mentions another

### Phase 3: Semantic Relationship Types

#### 3.1 Relationship Type Hierarchy
```
related_to (generic, low similarity 0.70-0.75)
├── similar_to (medium similarity 0.75-0.85)
├── associated_with (contextual, extracted from text)
├── part_of (composition/hierarchy)
├── uses (dependency/usage)
├── extends (inheritance/extension)
├── depends_on (strong dependency)
└── references (weaker mention)
```

#### 3.2 Relationship Confidence Scores
- Store similarity score in relationship properties
- Allow filtering by confidence threshold
- Use confidence for ranking in graph queries

### Phase 4: Improved MCP Tools

#### 4.1 New Tools

1. **`discover_relationships`** - Automatic relationship discovery
   - Parameters: `similarity_threshold` (default 0.75), `limit` (default 50)
   - Creates relationships between similar entities
   - Returns count of relationships created

2. **`generate_embeddings`** - Generate missing embeddings
   - Processes all entities without embeddings
   - Reports progress and success/failure counts

3. **`analyze_graph_connectivity`** - Graph health metrics
   - Returns: connectivity ratio, isolated entities, relationship distribution
   - Identifies opportunities for new relationships

4. **`create_semantic_relation`** - Smart relationship creation
   - Auto-detects best relationship type from context
   - Adds confidence scores
   - Creates bidirectional relationships when appropriate

#### 4.2 Enhanced Tools

1. **`create_entity`** - Enhanced with auto-discovery
   - Automatically generates embedding
   - Discovers and creates relationships to similar entities
   - Parameter: `auto_discover` (default true)

2. **`get_knowledge_graph_stats`** - Enhanced metrics
   - Connectivity ratio
   - Isolated entities count
   - Average degree (relationships per entity)
   - Relationship type distribution

### Phase 5: Data Cleanup

#### 5.1 Test Entity Management
Option A: Separate test database
- Use different database path in tests
- Keep production graph clean

Option B: Tag and filter test entities
- Add `is_test` flag to entity metadata
- Filter out test entities in stats/tools
- Clean up test entities periodically

#### 5.2 Relationship Validation
- Remove duplicate relationships
- Validate entity references exist
- Clean up orphaned relationships

## Implementation Plan

### Step 1: Schema Migration (Immediate)
1. Add `embedding` column to `kg_entities`
2. Generate embeddings for all existing entities
3. Validate embeddings work correctly

### Step 2: Auto-Discovery System (High Priority)
1. Implement embedding generation for new entities
2. Create semantic similarity search function
3. Implement automatic relationship creation
4. Add `discover_relationships` MCP tool

### Step 3: Enhanced Tools (Medium Priority)
1. Update `create_entity` to support auto-discovery
2. Add new analysis tools
3. Enhance statistics reporting

### Step 4: Data Quality (Ongoing)
1. Decide on test entity strategy
2. Implement cleanup/retention policies
3. Add relationship validation

## Success Metrics

### Target Improvements
- **Connectivity Ratio:** 0.032 → 0.2-0.5 (6-15x improvement)
- **Relationships:** 19 → 200-500 (10-25x increase)
- **Entity Embedding Coverage:** 0% → 100%
- **Isolated Entities:** Reduce from ~580 to <100

### Quality Metrics
- **Meaningful Relationships:** >90% should be useful
- **Relationship Confidence:** Average similarity > 0.75
- **Graph Query Performance:** <100ms for path queries
- **Automatic Discovery:** >80% of relationships created automatically

## Technical Considerations

### Performance
- Embedding generation: ~50ms per entity (ONNX, local)
- Similarity search: Uses DuckDB cosine similarity (fast)
- Batch processing: Generate embeddings in batches of 50

### Storage
- Each embedding: 384 floats × 4 bytes = ~1.5 KB
- 597 entities × 1.5 KB = ~900 KB additional storage
- Negligible impact on database size

### Scalability
- Current approach works well up to ~10,000 entities
- Beyond that, consider approximate nearest neighbor (ANN) indexing
- DuckDB vector extensions provide good performance

## Files to Modify

1. **`session_buddy/adapters/knowledge_graph_adapter_oneiric.py`**
   - Add `embedding` column to schema creation
   - Implement embedding generation
   - Add semantic similarity search

2. **`session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py`**
   - Add new MCP tools for auto-discovery
   - Enhance `create_entity` with auto-discovery
   - Add analysis tools

3. **`tests/unit/test_knowledge_graph_adapter.py`**
   - Add tests for embedding generation
   - Add tests for relationship discovery
   - Update existing tests for new schema

4. **`scripts/enhance_knowledge_graph.py`** (NEW)
   - Migration script to add embeddings
   - Relationship discovery script
   - Data cleanup utilities

## Risks & Mitigation

### Risk 1: Performance Degradation
- **Mitigation:** Use batch processing, limit similarity search with indexes

### Risk 2: Low-Quality Auto-Relationships
- **Mitigation:** Use high similarity threshold (0.75), manual review tools

### Risk 3: Storage Bloat
- **Mitigation:** Monitor database size, implement retention policies

### Risk 4: Test Data Pollution
- **Mitigation:** Use separate test databases or filter test entities

## Next Steps

1. ✅ Review and approve this plan
2. ⏳ Implement Phase 1 (schema migration)
3. ⏳ Implement Phase 2 (auto-discovery)
4. ⏳ Implement Phase 3 (semantic relationships)
5. ⏳ Implement Phase 4 (enhanced tools)
6. ⏳ Implement Phase 5 (data cleanup)
7. ⏳ Validate improvements with `test_database_status.py`

## Expected Timeline

- **Phase 1:** 1-2 hours (schema + embeddings)
- **Phase 2:** 3-4 hours (auto-discovery system)
- **Phase 3:** 2-3 hours (semantic relationships)
- **Phase 4:** 2-3 hours (enhanced tools)
- **Phase 5:** 1-2 hours (data cleanup)
- **Total:** 9-14 hours of development

## Conclusion

This plan will transform the knowledge graph from a sparsely connected entity store (0.032 ratio) to a richly connected semantic network (0.2-0.5 ratio), enabling:

1. **Better Recommendations:** Find related projects, libraries, concepts
2. **Insight Discovery:** Uncover hidden relationships between entities
3. **Knowledge Navigation:** Follow semantic connections between topics
4. **Automatic Organization:** Self-organizing knowledge structure

The key insight is that **relationships are more valuable than entities** for knowledge graphs. With 597 entities, we should have 600-3000 relationships to make the graph truly useful.
