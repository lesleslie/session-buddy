# Phase 3 Implementation Plan

## Semantic Relationship Enhancement

**Status**: IN PROGRESS
**Last Updated**: 2025-02-09

### Objectives

Make relationships smarter and more expressive with:

1. Rich relationship type hierarchy (15+ types instead of 6)
1. Confidence scoring for all relationships (low/medium/high)
1. Transitive relationship discovery (A→B→C implies A→C)
1. Pattern extraction from entity observations

### Current State (Before Phase 3)

- **Relationships**: 519 total
- **Types**: 6 basic types (96% are generic "related_to")
- **Confidence**: Not tracked
- **Connectivity**: 0.869 (excellent!)

### Implementation Tasks

#### 1. Enhanced Relationship Type Inference ✅

- [x] Modify `_infer_relationship_type()` to return tuple (type, confidence)
- [x] Add similarity-based hierarchy (very_similar_to, similar_to)
- [x] Add pattern-based types (uses, extends, depends_on, part_of, implements)
- [x] Add type-based heuristics

#### 2. Confidence Scoring System ✅

- [x] Add `confidence` parameter to `create_relation()`
- [x] Store confidence in properties
- [x] Add metadata (similarity, discovery_method, evidence)

#### 3. Pattern Extraction ✅

- [x] Add `_extract_relationships_from_observations()` method
- [x] Regex patterns for relationship keywords
- [x] Evidence collection from text

#### 4. Transitive Relationship Discovery ✅

- [x] Add `discover_transitive_relationships()` method
- [x] Chain detection (A→B→C)
- [x] Confidence propagation (min of edge confidences)
- [x] Avoid self-loops and duplicates

#### 5. Enhanced Entity Creation ✅

- [x] Add `extract_patterns` parameter to `create_entity()`
- [x] Auto-discover relationships from observations
- [x] Pattern-based relationship creation

#### 6. MCP Tools ✅

- [x] Add `discover_transitive_relationships` tool
- [x] Add `extract_pattern_relationships` tool
- [x] Update existing tools with confidence support

### Relationship Type Hierarchy (15+ Types)

**Similarity-based:**

1. `very_similar_to` - similarity ≥ 0.85 (high confidence)
1. `similar_to` - similarity ≥ 0.75 (medium confidence)
1. `related_to` - default/low similarity (low confidence)

**Pattern-based:**
4\. `uses` - X uses Y
5\. `extends` - X extends Y
6\. `depends_on` - X depends on Y
7\. `part_of` - X is part of Y
8\. `implements` - X implements Y
9\. `requires` - X requires Y
10\. `connects_to` - X connects to Y

**Type-based:**
11\. `used_by` - library used_by project
12\. `serves` - service serves project
13\. `tests` - test tests project
14\. `tested_by` - project tested_by test
15\. `applies_to` - concept applies_to project

### Files Modified

1. `session_buddy/adapters/knowledge_graph_adapter_oneiric.py` - Core implementation
1. `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py` - MCP tools

### Testing Strategy

- [ ] Test enhanced type inference
- [ ] Test pattern extraction
- [ ] Test transitive discovery
- [ ] Test confidence scoring
- [ ] Integration tests

### Expected Outcomes

**Before Phase 3:**

```
Relationships: 519
Types: 6 (96% "related_to")
Confidence: Not tracked
```

**After Phase 3:**

```
Relationships: 600-700 (+100-200)
Types: 15+ expressive types
├── similar_to: 150
├── very_similar_to: 50
├── uses: 80
├── extends: 40
├── depends_on: 30
└── ... more
Confidence: All relationships have scores
Transitive: Hidden connections discovered
```

### Notes

- Focus on working code over perfect code
- Time budget: 2-3 hours
- Can iterate and refine later
