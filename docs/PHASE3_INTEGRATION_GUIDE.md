# Phase 3 Integration Guide

## Overview

This guide explains how to integrate Phase 3 (Semantic Relationship Enhancement) into the Session Buddy knowledge graph system.

## Prerequisites

- Phase 3 code has been implemented and is ready for integration
- Tests have been written but require DuckDB to be functional
- DuckPGQ extension is currently not available (HTTP 404 error)

## Current State

**DuckPGQ Issue**: The DuckPGQ extension is not available for DuckDB v1.4.4 on macOS. This causes test failures but doesn't affect Phase 3 implementation.

**Solution**: Make DuckPGQ optional and use DuckDB without the property graph extension.

## Integration Steps

### Step 1: Update Settings to Make DuckPGQ Optional

File: `session_buddy/adapters/settings.py`

Change line 61:

```python
# Before:
install_extensions: tuple[str, ...] = ("duckpgq",)

# After:
install_extensions: tuple[str, ...] = ()  # DuckPGQ not available in v1.4.4
```

Or make it conditionally installed:

```python
install_extensions: tuple[str, ...] = (
    "duckpgq" if _duckpgq_available else (),
)
```

### Step 2: Add Phase 3 Methods to Main Adapter

Option A: Use Mixin (Recommended)

```python
# File: session_buddy/adapters/knowledge_graph_adapter_oneiric.py

# Add import at top:
from session_buddy.adapters.knowledge_graph_adapter_phase3 import (
    Phase3RelationshipMixin,
)

# Change class declaration:
class KnowledgeGraphDatabaseAdapterOneiric(Phase3RelationshipMixin):
    """Oneiric-compatible knowledge graph adapter using native DuckDB.

    Phase 3: Enhanced semantic relationships with confidence scoring.
    """
    # ... existing code ...
```

Option B: Copy Methods Directly

Copy methods from `knowledge_graph_phase3_patch.py` into the adapter class.

### Step 3: Update `_infer_relationship_type` Method

The existing method returns only a string. Phase 3 returns a tuple.

```python
# Replace existing method (line 558-603)

def _infer_relationship_type(
    self,
    from_entity: dict[str, t.Any],
    to_entity: dict[str, t.Any],
    similarity: float,
    from_observations: list[str] | None = None,
    to_observations: list[str] | None = None,
) -> tuple[str, str]:
    """Infer relationship type and confidence (Phase 3 enhanced).

    Returns:
        (relationship_type, confidence) where confidence is "low"/"medium"/"high"
    """
    # ... Phase 3 implementation ...
```

### Step 4: Update `_auto_discover_relationships` Method

Update to use new tuple return value:

```python
# Around line 642-650

# Before:
relation_type = self._infer_relationship_type(
    source_entity,
    similar_entity,
    similar_entity["similarity"],
)

# After:
relation_type, confidence = self._infer_relationship_type(
    source_entity,
    similar_entity,
    similar_entity["similarity"],
)

# Then use confidence in properties:
relation = await self.create_relation(
    from_entity=entity_id,
    to_entity=similar_entity["id"],
    relation_type=relation_type,
    properties={
        "similarity": similar_entity["similarity"],
        "confidence": confidence,  # NEW
        "auto_discovered": True,
    },
)
```

### Step 5: Register Phase 3 MCP Tools

File: `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py`

Add at end of `register_knowledge_graph_tools` function:

```python
def register_knowledge_graph_tools(mcp_server: Any) -> None:
    """Register all knowledge graph MCP tools with the server."""

    # ... existing tool registrations ...

    # Phase 3: Enhanced relationship tools
    from session_buddy.mcp.tools.collaboration.knowledge_graph_phase3_tools import (
        register_phase3_knowledge_graph_tools,
    )

    register_phase3_knowledge_graph_tools(mcp_server)
```

### Step 6: Update Imports in Server (if needed)

File: `session_buddy/server.py` or wherever tools are registered

Ensure Phase 3 tools are imported and registered.

## Testing

### Fix DuckPGQ Dependency

Option 1: Skip DuckPGQ

```python
# In settings.py
install_extensions: tuple[str, ...] = ()
```

Option 2: Make it optional with graceful fallback

```python
# In knowledge_graph_adapter_oneiric.py
try:
    for extension in extensions:
        self.conn.execute(f"INSTALL {extension} FROM community")
        self.conn.execute(f"LOAD {extension}")
    self._duckpgq_installed = True
except Exception as e:
    logger.warning(f"Failed to install extension {extension}: {e}")
    self._duckpgq_installed = False
    # Continue without extension - basic operations still work
```

### Run Tests

```bash
# Run Phase 3 specific tests
pytest tests/unit/test_phase3_relationships.py -v

# Run all knowledge graph tests
pytest tests/unit/test_knowledge_graph_adapter.py -v

# Run with coverage
pytest tests/unit/test_phase3_relationships.py --cov=session_buddy.adapters.knowledge_graph_adapter_oneiric
```

## Verification Checklist

- [ ] Settings updated to make DuckPGQ optional
- [ ] Phase 3 mixin integrated into adapter class
- [ ] `_infer_relationship_type` returns tuple (type, confidence)
- [ ] `_auto_discover_relationships` uses confidence
- [ ] Phase 3 MCP tools registered
- [ ] Tests passing
- [ ] Documentation updated

## Rollback Plan

If issues occur, you can rollback by:

1. Remove Phase3RelationshipMixin from class inheritance
1. Restore original `_infer_relationship_type` method
1. Remove Phase 3 MCP tool registration
1. Delete Phase 3 test files (optional)

## Usage Examples

### Pattern Extraction

```python
# Create entity with pattern extraction
entity = await kg.create_entity_with_patterns(
    name="session-buddy",
    entity_type="project",
    observations=["session-buddy uses FastMCP for tool registration"],
    extract_patterns=True
)

# Result: entity + relationship (session-buddy --[uses]--> FastMCP)
```

### Transitive Discovery

```python
# Discover hidden connections
result = await kg.discover_transitive_relationships(
    max_depth=2,
    min_confidence="medium",
    limit=50
)

print(f"Created {result['created']} transitive relationships")
# Example output: "Created 45 transitive relationships"
```

### MCP Tools

```
# In Claude Code
discover_transitive_relationships(max_depth=2, min_confidence="medium")
extract_pattern_relationships(entity_name="session-buddy", auto_create=True)
get_relationship_confidence_stats()
```

## Expected Results

After integration:

1. **Relationship Types**: 15+ expressive types instead of 6
1. **Confidence Scoring**: All relationships have confidence (low/medium/high)
1. **Pattern Extraction**: Auto-extract relationships from observations
1. **Transitive Discovery**: Hidden connections discovered
1. **Better Inference**: Smarter relationship type selection

## Troubleshooting

### Issue: Tests fail with DuckPGQ error

**Solution**: Make DuckPGQ optional in settings

### Issue: Confidence not appearing in relationships

**Solution**: Ensure `_infer_relationship_type` returns tuple and `_auto_discover_relationships` unpacks it

### Issue: Phase 3 tools not available

**Solution**: Check tool registration in knowledge_graph_tools.py

### Issue: Pattern extraction not working

**Solution**: Check regex patterns and ensure observations contain text

## Files Summary

### Created (5 files):

1. `session_buddy/adapters/knowledge_graph_adapter_phase3.py` - Mixin class
1. `session_buddy/adapters/knowledge_graph_phase3_patch.py` - Standalone functions
1. `tests/unit/test_phase3_relationships.py` - Unit tests
1. `session_buddy/mcp/tools/collaboration/knowledge_graph_phase3_tools.py` - MCP tools
1. `PHASE3_IMPLEMENTATION.md` - Implementation plan

### To Modify (3 files):

1. `session_buddy/adapters/settings.py` - Make DuckPGQ optional
1. `session_buddy/adapters/knowledge_graph_adapter_oneiric.py` - Integrate mixin
1. `session_buddy/mcp/tools/collaboration/knowledge_graph_tools.py` - Register tools

## Next Steps

1. Fix DuckPGQ dependency issue
1. Integrate Phase 3 mixin into adapter
1. Update tool registration
1. Run tests and verify
1. Update documentation
1. Deploy to production

## Support

For issues or questions:

1. Check this integration guide
1. Review test files for examples
1. Check PHASE3_COMPLETION_SUMMARY.md for overview
1. Review implementation in knowledge_graph_adapter_phase3.py

______________________________________________________________________

**Status**: Ready for integration
**Estimated Time**: 1-2 hours
**Risk Level**: Low (backward compatible, can be rolled back)
