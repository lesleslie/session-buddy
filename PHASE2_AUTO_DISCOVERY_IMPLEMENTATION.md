# Phase 2: Auto-Discovery System Implementation

## Overview

Implement automatic relationship discovery in the knowledge graph using semantic similarity to increase connectivity from 0.032 to 0.2-0.5.

## Implementation Status

- [x] Phase 1 Complete: Embedding column added to kg_entities table
- [x] Current State: 269/597 entities (45.1%) with embeddings
- [ ] Phase 2 In Progress: Auto-discovery system

## Files to Modify

### 1. session_buddy/adapters/knowledge_graph_adapter_oneiric.py
Add auto-discovery methods:
- `_generate_entity_embedding()` - Generate embeddings for entities
- `_find_similar_entities()` - Find semantically similar entities using cosine similarity
- `_auto_discover_relationships()` - Auto-discover and create relationships
- Modify `create_entity()` to support auto-discovery parameter
- Enhance `get_stats()` with connectivity metrics

### 2. session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py
Add new MCP tools:
- `discover_relationships` - Batch discover relationships for entities
- `generate_embeddings` - Generate embeddings for entities missing them
- `analyze_graph_connectivity` - Analyze graph connectivity and health metrics

## Technical Approach

### Embedding Generation
- Use existing `session_buddy.reflection.embeddings.generate_embedding()`
- Combine entity name + entity_type + observations for rich semantic representation
- Store as FLOAT[384] vector in kg_entities.embedding column

### Similarity Search
- Use DuckDB's `array_cosine_similarity()` function
- Query: `SELECT *, array_cosine_similarity(embedding, ?) as similarity FROM kg_entities WHERE similarity > ?`
- Threshold: 0.75 (configurable)

### Relationship Type Inference
Smart heuristics based on entity types and similarity:
- High similarity (0.9+) = "related_to"
- Both "project" type = "related_to"
- One "project", one "library" = "uses"
- One "service", one "project" = "connects_to"
- One "test", one "project" = "tests"

### Connectivity Metrics
Enhanced statistics:
- `connectivity_ratio` = relationships / entities
- `isolated_entities` = entities with 0 relationships
- `avg_degree` = average relationships per entity
- `embedding_coverage` = entities_with_embeddings / total_entities

## Expected Outcomes

- Before: 19 relationships, 0.032 connectivity
- After: 200-500 relationships, 0.2-0.5 connectivity
- Improvement: 10-25x better connectivity

## Implementation Steps

1. Add auto-discovery methods to KnowledgeGraphDatabaseAdapterOneiric
2. Add relationship type inference logic
3. Add enhanced statistics with connectivity metrics
4. Add MCP tools for batch operations
5. Test auto-discovery on existing entities
6. Verify connectivity improvement

## Success Criteria

- [x] Auto-discovery methods implemented
- [ ] MCP tools added and functional
- [ ] Connectivity improved to 0.2-0.5
- [ ] Embedding coverage increased to 80%+
- [ ] All tests passing
