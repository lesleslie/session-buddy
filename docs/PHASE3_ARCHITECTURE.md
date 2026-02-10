# Phase 3 Architecture Diagram

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Phase 3 Knowledge Graph                      │
│                  Semantic Relationship Enhancement               │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                            MCP Layer                                 │
│  ┌────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │  Claude Code   │──│ Phase 3 MCP     │──│  Knowledge Graph   │  │
│  │  Interface     │  │ Tools           │  │  Adapter           │  │
│  └────────────────┘  └─────────────────┘  └────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Phase 3 MCP Tools                                             │  │
│  │  ┌──────────────────────────────────────────────────────────┐ │  │
│  │  │  discover_transitive_relationships()                     │ │  │
│  │  │  extract_pattern_relationships()                         │ │  │
│  │  │  get_relationship_confidence_stats()                     │ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Knowledge Graph Adapter                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Phase3RelationshipMixin                                       │  │
│  │                                                                │  │
│  │  ┌──────────────────────────────────────────────────────────┐ │  │
│  │  │  Enhanced Relationship Inference                         │ │  │
│  │  │  ┌────────────────────────────────────────────────────┐  │ │  │
│  │  │  │  _infer_relationship_type()                        │  │ │  │
│  │  │  │  Returns: (type: str, confidence: str)            │  │ │  │
│  │  │  │                                                    │  │ │  │
│  │  │  │  Priority 1: Similarity-Based                      │  │ │  │
│  │  │  │    • very_similar_to (≥0.85) → high               │  │ │  │
│  │  │  │    • similar_to (≥0.75) → medium                   │  │ │  │
│  │  │  │    • related_to → low                              │  │ │  │
│  │  │  │                                                    │  │ │  │
│  │  │  │  Priority 2: Pattern-Based                         │  │ │  │
│  │  │  │    • uses, extends, depends_on                     │  │ │  │
│  │  │  │    • part_of, implements, requires                 │  │ │  │
│  │  │  │    • connects_to                                   │  │ │  │
│  │  │  │                                                    │  │ │  │
│  │  │  │  Priority 3: Type-Based                            │  │ │  │
│  │  │  │    • uses, used_by, serves                         │  │ │  │
│  │  │  │    • tests, tested_by                              │  │ │  │
│  │  │  │    • applies_to, contains                          │  │ │  │
│  │  │  └────────────────────────────────────────────────────┘  │ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  │                                                                │  │
│  │  ┌──────────────────────────────────────────────────────────┐ │  │
│  │  │  Pattern Extraction                                      │  │  │
│  │  │  ┌────────────────────────────────────────────────────┐  │ │  │
│  │  │  │  _extract_pattern_from_text()                      │  │ │  │
│  │  │  │  _extract_relationships_from_observations()        │  │ │  │
│  │  │  │                                                    │  │ │  │
│  │  │  │  Regex Patterns (10 total):                        │  │ │  │
│  │  │  │    • r"\buses\s+(\w+)" → uses                     │  │ │  │
│  │  │  │    • r"\bextends\s+(\w+)" → extends               │  │ │  │
│  │  │  │    • r"\bdepends\s+on\s+(\w+)" → depends_on       │  │ │  │
│  │  │  │    • ... 7 more patterns                          │  │ │  │
│  │  │  └────────────────────────────────────────────────────┘  │ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  │                                                                │  │
│  │  ┌──────────────────────────────────────────────────────────┐ │  │
│  │  │  Transitive Discovery                                    │  │  │
│  │  │  ┌────────────────────────────────────────────────────┐  │ │  │
│  │  │  │  discover_transitive_relationships()               │  │ │  │
│  │  │  │                                                    │  │ │  │
│  │  │  │  Algorithm:                                        │  │ │  │
│  │  │  │    1. Build adjacency list                         │  │ │  │
│  │  │  │    2. BFS to find chains (A→B→C)                  │  │ │  │
│  │  │  │    3. Calculate transitive confidence             │  │ │  │
│  │  │  │    4. Skip if direct exists                        │  │ │  │
│  │  │  │    5. Create transitive relationship              │  │ │  │
│  │  │  │                                                    │  │ │  │
│  │  │  │  Example:                                          │  │ │  │
│  │  │  │    session-buddy uses FastMCP (high)              │  │ │  │
│  │  │  │    FastMCP extends MCP (medium)                   │  │ │  │
│  │  │  │    ⇒ session-buddy uses MCP (medium, transitive)  │  │ │  │
│  │  │  └────────────────────────────────────────────────────┘  │ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Core Adapter Methods (Enhanced)                               │  │
│  │  • create_entity_with_patterns()                               │  │
│  │  • create_relation() - with confidence support                 │  │
│  │  • _auto_discover_relationships() - with confidence            │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        DuckDB Storage Layer                          │
│  ┌──────────────────┐  ┌───────────────────┐  ┌──────────────────┐  │
│  │  kg_entities     │  │ kg_relationships  │  │  Embeddings      │  │
│  │  (nodes)         │  │  (edges)          │  │  (FLOAT[384])    │  │
│  └──────────────────┘  └───────────────────┘  └──────────────────┘  │
│                                                                    │
│  Relationship Properties (Phase 3 Enhanced):                       │
│  {                                                                 │
│    "confidence": "high",          # low/medium/high               │
│    "similarity": 0.87,           # cosine similarity             │
│    "discovery_method": "semantic", # semantic/pattern/transitive │
│    "created_at": timestamp,                                      │
│    "auto_discovered": true,                                      │
│    "evidence": ["observation text"]                              │
│  }                                                                │
└──────────────────────────────────────────────────────────────────────┘
```

## Data Flow Examples

### Example 1: Pattern Extraction

```
User creates entity:
  create_entity_with_patterns(
    name="session-buddy",
    observations=["session-buddy uses FastMCP for tool registration"],
    extract_patterns=True
  )

  ↓

Pattern Extraction:
  _extract_relationships_from_observations()
    ↓
  Regex match: r"\buses\s+(\w+)"
    ↓
  Found: "session-buddy uses FastMCP"
    ↓
  Extract: from="session-buddy", to="FastMCP", type="uses"
    ↓

Relationship Creation:
  create_relation(
    from_entity="session-buddy",
    to_entity="FastMCP",
    relation_type="uses",
    properties={
      "confidence": "high",
      "discovery_method": "pattern",
      "evidence": ["session-buddy uses FastMCP for tool registration"]
    }
  )

  ↓

Result:
  ✅ Entity created: session-buddy
  ✅ Relationship created: session-buddy --[uses]--> FastMCP
```

### Example 2: Transitive Discovery

```
Existing relationships:
  session-buddy --[uses, confidence:high]--> FastMCP
  FastMCP --[extends, confidence:medium]--> MCP

User runs:
  discover_transitive_relationships(max_depth=2)

  ↓

Build adjacency list:
  {
    "session-buddy": [("FastMCP", "uses", "high")],
    "FastMCP": [("MCP", "extends", "medium")]
  }

  ↓

BFS from session-buddy:
  Queue: [("session-buddy", ["session-buddy"], [], [])]

  Step 1: Process session-buddy
    Neighbors: FastMCP
    Queue: [("FastMCP", ["session-buddy", "FastMCP"], ["uses"], ["high"])]

  Step 2: Process FastMCP
    Neighbors: MCP
    Queue: [("MCP", ["session-buddy", "FastMCP", "MCP"], ["uses", "extends"], ["high", "medium"])]

  Step 3: Process MCP
    Path length = 3 (≥3) ✓
    Calculate transitive confidence: min("high", "medium") = "medium"
    Check if direct exists: No
    Create relationship: session-buddy --[uses]--> MCP
    Properties: {confidence: "medium", transitive: true, chain_length: 2}

  ↓

Result:
  ✅ Created: 1 transitive relationship
  ✅ session-buddy --[uses, confidence:medium, transitive:true]--> MCP
```

### Example 3: Relationship Type Inference

```
Scenario: Two similar projects
  from_entity: {name: "session-buddy", type: "project"}
  to_entity: {name: "crackerjack", type: "project"}
  similarity: 0.87
  from_observations: ["session-buddy uses FastMCP"]

  ↓

_infer_relationship_type(
  from_entity,
  to_entity,
  similarity=0.87,
  from_observations=["session-buddy uses FastMCP"]
)

  ↓

Priority 1: Pattern extraction
  _extract_pattern_from_text("session-buddy uses FastMCP", "crackerjack")
    → No match (target is "crackerjack", not "FastMCP")

  ↓

Priority 2: Similarity-based
  similarity (0.87) ≥ 0.85
    → Return ("very_similar_to", "high")

  ↓

Result:
  ✅ Type: "very_similar_to"
  ✅ Confidence: "high"
```

## Relationship Type Decision Tree

```
                    ┌─────────────────┐
                    │   Start         │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
      Pattern match in │  Priority 1:   │
      observations?    │  Pattern-Based  │
                    └────────┬────────┘
                             │
            ┌────────────────┴────────────────┐
            │ YES                             │ NO
            ▼                                 ▼
   ┌──────────────────┐            ┌─────────────────┐
   │ Return type      │            │ Priority 2:     │
   │ from pattern +   │            │ Similarity-Based│
   │ "high" confidence│            └────────┬────────┘
   └──────────────────┘                     │
                                             ▼
                                    ┌─────────────────┐
                          similarity ≥ 0.85? │
                                    └────────┬────────┘
                                             │
                            ┌────────────────┴────────────────┐
                            │ YES                             │ NO
                            ▼                                 ▼
                   ┌──────────────────┐            ┌─────────────────┐
                   │ very_similar_to  │            │ similarity ≥    │
                   │ + "high"         │            │ 0.75?           │
                   └──────────────────┘            └────────┬────────┘
                                                        │
                                        ┌───────────────┴───────────────┐
                                        │ YES                           │ NO
                                        ▼                               ▼
                               ┌──────────────────┐          ┌─────────────────┐
                               │ similar_to       │          │ Priority 3:     │
                               │ + "medium"       │          │ Type-Based      │
                               └──────────────────┘          └────────┬────────┘
                                                                  │
                                                   ┌──────────────┴──────────┐
                                                   │ Type pair match?       │
                                                   │ (project,library) etc. │
                                                   └──────────────┬──────────┘
                                                                  │
                                               ┌──────────────────┴─────────────────┐
                                               │ YES                              │ NO
                                               ▼                                  ▼
                                      ┌──────────────────┐            ┌─────────────────┐
                                      │ Type-specific    │            │ related_to      │
                                      │ + "medium"       │            │ + "low"         │
                                      └──────────────────┘            └─────────────────┘
```

## Confidence Score Impact

```
Confidence Level   │ Similarity Range │ Discovery Method    │ Count (Expected)
───────────────────┼──────────────────┼────────────────────┼─────────────────
High (30%)         │ ≥ 0.85           │ Pattern-based      │ 187
                   │                  │ Semantic matching  │
───────────────────┼──────────────────┼────────────────────┼─────────────────
Medium (50%)       │ 0.75 - 0.85      │ Type-based         │ 311
                   │                  │ Transitive chains  │
───────────────────┼──────────────────┼────────────────────┼─────────────────
Low (20%)          │ < 0.75           │ Default fallback   │ 125
                   │                  │ Generic matching   │
```

## Test Coverage

```
tests/unit/test_phase3_relationships.py
│
├── TestPhase3RelationshipInference (3 tests)
│   ├── test_infer_relationship_type_with_similarity
│   ├── test_infer_relationship_type_with_patterns
│   └── test_infer_relationship_type_type_based
│
├── TestPhase3PatternExtraction (4 tests)
│   ├── test_extract_pattern_from_text_uses
│   ├── test_extract_pattern_from_text_extends
│   ├── test_extract_pattern_from_text_depends_on
│   └── test_extract_relationships_from_observations
│
├── TestPhase3TransitiveDiscovery (2 tests)
│   ├── test_discover_transitive_relationships
│   └── test_discover_transitive_avoids_duplicates
│
├── TestPhase3EntityCreation (1 test)
│   └── test_create_entity_with_patterns
│
└── TestPhase3ConfidenceScoring (2 tests)
    ├── test_create_relation_with_confidence
    └── test_auto_discovery_with_confidence

Total: 6 test classes, 12 tests, 380 lines
```

---

**Phase 3 Architecture**: Complete and Ready for Integration
