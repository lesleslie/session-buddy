# 🎯 Phase 3: Semantic Relationship Enhancement

**Status:** 🟢 SHIPPED — Phase 3 integrated into session-buddy (4/6 items delivered)
**Reconciled:** 2026-07-15 (drift-sync)
**Dependencies:** Phase 2 (Auto-Discovery) - ✅ COMPLETE
**Estimated Effort:** 2-3 hours (original estimate)
**Priority:** Medium (Optional enhancement)

> **Phase 3 Status Note**
> 
> 4 of 6 items have been integrated into the live codebase. The remaining items — most notably the **relationship quality metrics tool** — are tracked as follow-up under the active quality-tools backlog. See `PHASE3_INTEGRATION_GUIDE.md` for the integration history.

______________________________________________________________________

## Phase 3 Overview

Building on the massive success of Phase 2 (27.3x connectivity improvement), Phase 3 focuses on **making relationships smarter and more expressive** through:

1. **Relationship Type Hierarchy** - Rich relationship vocabulary
1. **Confidence Scoring** - Track relationship quality/strength
1. **Transitive Relationships** - A uses B, B uses C → A uses C
1. **Contextual Pattern Extraction** - Auto-detect relationship types from observations

______________________________________________________________________

## Phase 3 Components

### 1. Relationship Type Hierarchy

**Current (Phase 2):**

```
related_to (generic, catch-all)
```

**Enhanced (Phase 3):**

```
related_to (generic, low similarity 0.70-0.75)
├── similar_to (medium similarity 0.75-0.85)
│   └── very_similar_to (high similarity 0.85-0.95)
├── associated_with (contextual, from co-occurrence)
│   ├── part_of (composition/hierarchy)
│   ├── contains (inverse of part_of)
│   ├── uses (dependency/usage)
│   ├── used_by (inverse of uses)
│   ├── extends (inheritance/extension)
│   ├── extends_from (inverse of extends)
│   ├── depends_on (strong dependency)
│   ├── required_by (inverse of depends_on)
│   ├── connects_to (integration)
│   ├── connected_by (inverse of connects_to)
│   ├── references (weaker mention)
│   ├── referenced_by (inverse of references)
│   └── implements (interface/contract)
└── derived_from (lineage/evolution)
```

### 2. Confidence Scoring System

**Add metadata to relationships:**

```python
{
    "similarity": 0.87,          # Cosine similarity
    "confidence": "high",         # low/medium/high
    "discovery_method": "semantic", # semantic/pattern/manual
    "created_at": "2026-02-09",
    "auto_discovered": true,
    "supporting_evidence": ["both mentioned in same commit"]
}
```

### 3. Transitive Relationship Discovery

**Example:**

```
If: session-buddy → uses → FastMCP
And: FastMCP → extends → MCP
Then: session-buddy → uses → MCP (transitive)
```

**Algorithm:**

```python
async def discover_transitive_relationships(max_depth: int = 3):
    """Discover transitive relationships (A→B→C implies A→C)."""
    # Find chains: A → B → C
    # Create transitive relationship A → C
    # Track confidence = product of edge confidences
    # Skip if direct relationship already exists
```

### 4. Contextual Pattern Extraction

**Extract from entity observations:**

```python
# Example observation:
"session-buddy uses FastMCP for tool registration"

# Extracted relationships:
session-buddy --[uses]--> FastMCP
session-buddy --[uses]--> tool (concept)
FastMCP --[used_by]--> session-buddy
```

**Pattern Matching:**

- "X uses Y" → uses relationship
- "X extends Y" → extends relationship
- "X depends on Y" → depends_on relationship
- "X is part of Y" → part_of relationship
- "X implements Y" → implements relationship

______________________________________________________________________

## Implementation Plan

### Step 1: Enhanced Relationship Type Inference (45 min)

**File:** `session_buddy/adapters/knowledge_graph_adapter_oneiric.py`

**Add to `_infer_relationship_type()`:**

```python
def _infer_relationship_type(
    from_type: str,
    to_type: str,
    similarity: float,
    from_observations: list[str] | None = None,
    to_observations: list[str] | None = None
) -> tuple[str, str]:
    """Infer relationship type and confidence.

    Returns:
        (relationship_type, confidence_level)
    """

    # High similarity → very_similar_to
    if similarity >= 0.85:
        return "very_similar_to", "high"

    # Medium similarity → similar_to
    if similarity >= 0.75:
        return "similar_to", "medium"

    # Pattern extraction from observations
    if from_observations or to_observations:
        # Check for explicit patterns
        for obs in (from_observations or []):
            if f"uses {to_type}" in obs.lower():
                return "uses", "high"
            if f"extends {to_type}" in obs.lower():
                return "extends", "high"
            # ... more patterns

    # Type-based heuristics
    type_pairs = {
        ("project", "library"): ("uses", "medium"),
        ("project", "service"): ("connects_to", "medium"),
        ("test", "project"): ("tests", "high"),
        # ... more pairs
    }

    if (from_type, to_type) in type_pairs:
        return type_pairs[(from_type, to_type)]

    # Default
    return "related_to", "low"
```

### Step 2: Confidence Scoring (30 min)

**Update `create_relation()`:**

```python
async def create_relation(
    self,
    from_entity: str,
    to_entity: str,
    relation_type: str,
    confidence: str = "medium",  # NEW PARAMETER
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a relationship with confidence scoring."""

    # Enhance properties with confidence metadata
    props = properties or {}
    props["confidence"] = confidence
    props["created_at"] = datetime.now(UTC).isoformat()
    props["discovery_method"] = "manual"

    # Store relationship
    # ... existing code ...
```

### Step 3: Transitive Discovery (60 min)

**New method:**

```python
async def discover_transitive_relationships(
    self,
    max_depth: int = 3,
    min_confidence: str = "medium",
    similarity_threshold: float = 0.75
) -> dict[str, int]:
    """Discover transitive relationships (A→B→C implies A→C)."""

    # Get all relationships
    # Find chains: A → B → C where depth ≤ max_depth
    # Calculate transitive confidence = product of edge confidences
    # Create transitive relationship if:
    #   - Direct relationship doesn't exist
    #   - Transitive confidence >= min_confidence
    #   - Not creating self-loop
```

### Step 4: Pattern Extraction (45 min)

**New method:**

```python
def _extract_relationships_from_observations(
    self,
    entity_id: str,
    observations: list[str]
) -> list[dict[str, Any]]:
    """Extract relationships from text observations.

    Patterns:
        - "X uses Y" → X uses Y
        - "X extends Y" → X extends Y
        - "X depends on Y" → X depends_on Y
        - "X is part of Y" → X part_of Y
        - "X implements Y" → X implements Y
    """

    import re

    relationships = []
    entity = await self.get_entity(entity_id)
    entity_name = entity["name"]

    # Pattern: "uses", "extends", "depends on", "part of", "implements"
    patterns = {
        r"uses\s+(\w+)": "uses",
        r"extends\s+(\w+)": "extends",
        r"depends\s+on\s+(\w+)": "depends_on",
        r"part\s+of\s+(\w+)": "part_of",
        r"implements\s+(\w+)": "implements",
    }

    for obs in observations:
        for pattern, rel_type in patterns.items():
            matches = re.findall(pattern, obs, re.IGNORECASE)
            for match in matches:
                relationships.append({
                    "from_entity": entity_id,
                    "to_entity": match,
                    "relation_type": rel_type,
                    "confidence": "medium",
                    "evidence": obs,
                    "discovery_method": "pattern_extraction"
                })

    return relationships
```

______________________________________________________________________

## Expected Results

### Before Phase 3 (Current)

```
Relationships: 519
Types: 6 generic types
├── related_to: 501 (96.5%)
├── extends: 5 (1.0%)
├── uses: 5 (1.0%)
├── depends_on: 4 (0.8%)
├── connects_to: 2 (0.4%)
└── requires: 2 (0.4%)
```

### After Phase 3 (Target)

```
Relationships: 600-700 (+100-200)
Types: 15+ expressive types
├── related_to: 200 (30%)
├── similar_to: 150 (23%)
├── very_similar_to: 50 (8%)
├── uses: 80 (12%)
├── extends: 40 (6%)
├── depends_on: 30 (5%)
├── part_of: 25 (4%)
├── connects_to: 20 (3%)
├── implements: 15 (2%)
└── ... more
```

### Quality Improvements

- **More granular** - 15+ types vs 6 generic types
- **Confidence tracking** - Know which relationships are strong/weak
- **Transitive closure** - Discover hidden connections
- **Evidence-based** - Support relationships with observation patterns

______________________________________________________________________

## Success Criteria

✅ **Complete when:**

1. [ ] Relationship type hierarchy implemented
1. [ ] Confidence scoring added to all relationships
1. [ ] Transitive relationship discovery functional
1. [ ] Pattern extraction from observations working
1. [ ] 15+ relationship types in use
1. [ ] Relationship quality metrics available

______________________________________________________________________

## Activation Command (When Implemented)

```bash
# Run Phase 3 enhancement
python scripts/activate_phase3_enhanced.py --extract-patterns --transitive
```

______________________________________________________________________

## Recommendation

**Phase 3 Status:** 📋 **OPTIONAL ENHANCEMENT**

**Reason:** Phase 2 already achieved **excellent results** (0.869 connectivity vs 0.2-0.5 target). Phase 3 provides **incremental value** for specialized use cases:

**Do Phase 3 if:**

- ✅ You need very granular relationship types
- ✅ You want confidence scoring for query ranking
- ✅ You need transitive relationship queries
- ✅ You want pattern extraction from observations

**Skip Phase 3 if:**

- ✅ Current 0.869 connectivity is sufficient
- ✅ Generic "related_to" relationships meet your needs
- ✅ You have higher priority features to implement

**My Assessment:** Phase 2 was the critical breakthrough (27x improvement). Phase 3 is a **nice-to-have** enhancement that can be implemented later when specific use cases arise.

______________________________________________________________________

**Documentation:** See `KNOWLEDGE_GRAPH_CONNECTIVITY_PLAN.md` for full details.
