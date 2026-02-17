# ACB Graph Adapter Migration - Phase 3 Deferred

## Status: Deferred to Future Release

**Date**: January 11, 2025
**Phase**: 3 (Knowledge Graph Migration)
**Decision**: Deferred

## Summary

Phase 3 (Knowledge Graph ACB migration) has been deferred to a future release. The existing `KnowledgeGraphDatabase` class will continue to function using direct DuckDB connections.

## Rationale

### 1. Dependency Requirements

- ACB's Graph adapter requires `duckdb-engine` (SQLAlchemy DuckDB dialect)
- This would add a new production dependency
- Current implementation uses DuckDB directly without SQLAlchemy

### 2. Implementation Complexity

- Full migration requires converting all SQL queries to SQLAlchemy syntax
- Estimated ~600+ lines of code changes across 10+ methods
- Time investment doesn't match current project priorities

### 3. Working Solution Available

- Original `KnowledgeGraphDatabase` is fully functional
- Uses DuckDB PGQ extension directly
- No reported issues or performance problems

### 4. Phase Scope Management

- Phase 2 (Vector Adapter) is complete and tested ✅
- Completing Phases 4-5 (Testing & Documentation) provides immediate value
- Graph migration can be tackled when additional graph features are needed

## What Was Completed

✅ **Phase 3.1**: Created `KnowledgeGraphDatabaseAdapter` stub (scaffolding for future work)
✅ **Phase 3.2**: Updated `knowledge_graph_tools.py` type hints to support future adapter
✅ **Phase 3.3**: Tested hybrid approach and identified dependency requirements

## What Remains (For Future)

🔲 **Full SQLAlchemy Conversion**: Convert all 10 methods to use `sqlalchemy.text()` and async connections
🔲 **Dependency Addition**: Add `duckdb-engine>=0.11.2` to pyproject.toml
🔲 **Integration Testing**: Full test suite validation with ACB Graph adapter
🔲 **Migration Script**: Create data migration tool (similar to vector migration)

## Current State

### Working Approach

```text
# Current - Direct DuckDB (WORKS)
from session_buddy.knowledge_graph_db import KnowledgeGraphDatabase

async with KnowledgeGraphDatabase() as kg:
    entity = await kg.create_entity("name", "type", ["observation"])
    # ✅ Fully functional
```

### Future Approach (When Completed)

```text
# Future - ACB Graph Adapter (DEFERRED)
from session_buddy.adapters.knowledge_graph_adapter import (
    KnowledgeGraphDatabaseAdapter,
)

async with KnowledgeGraphDatabaseAdapter() as kg:
    entity = await kg.create_entity("name", "type", ["observation"])
    # 🔲 Requires duckdb-engine and SQLAlchemy conversion
```

## Migration Plan (When Ready)

### Prerequisites

1. Add dependency: `uv add "duckdb-engine>=0.11.2"`
1. Review ACB Graph adapter patterns in `/Users/les/Projects/acb/acb/adapters/graph/duckdb_pgq.py`

### Implementation Steps

1. Convert all methods to use SQLAlchemy async connections:

   ```text
   engine = await self.graph_adapter._ensure_client()
   async with engine.begin() as conn:
       result = await conn.execute(text("SELECT ..."), params)
   ```

1. Update parameter binding from `?` placeholders to `:param` style:

   ```text
   # Old:  conn.execute("WHERE id = ?", (entity_id,))
   # New:  await conn.execute(text("WHERE id = :id"), {"id": entity_id})
   ```

1. Handle result sets via SQLAlchemy Result objects:

   ```text
   result = await conn.execute(...)
   rows = result.fetchall()  # Returns list of Row objects
   ```

1. Test all 10 methods:

   - create_entity
   - get_entity
   - find_entity_by_name
   - create_relation
   - add_observation
   - search_entities
   - get_relationships
   - find_path (SQL/PGQ)
   - get_stats

1. Create migration script using same pattern as `scripts/migrate_vector_database.py`

### Estimated Effort

- **Code Changes**: 2-3 hours (10 methods × 15-20 minutes each)
- **Testing**: 1-2 hours (integration tests + migration validation)
- **Documentation**: 30 minutes (CLAUDE.md updates, migration guide)
- **Total**: ~4-6 hours

## Related Files

- **Adapter Stub**: `session_buddy/adapters/knowledge_graph_adapter.py` (created, needs completion)
- **Original Class**: `session_buddy/knowledge_graph_db.py` (active, fully functional)
- **Tools Integration**: `session_buddy/tools/knowledge_graph_tools.py` (ready for either approach)
- **DI Registration**: `session_buddy/di/__init__.py` (graph adapter registration exists)

## Impact Assessment

### User Impact

- **None** - Knowledge graph functionality continues to work
- No breaking changes to MCP tools or API
- Future migration will be transparent (same API)

### Technical Debt

- Minimal - Graph adapter is independent subsystem
- Can be migrated incrementally when needed
- No coupling with vector adapter migration (Phase 2)

### Benefits of Deferral

- ✅ Completes Phase 2 (Vector) with high confidence
- ✅ Allows focus on testing & documentation (Phases 4-5)
- ✅ Avoids scope creep during current release
- ✅ Provides clear migration path for future work

## Recommendation

**Proceed with Phases 4-5** (Testing & Documentation) using the following approach:

1. **Phase 4**: Update test fixtures to support **both** implementations:

   - Tests should work with `KnowledgeGraphDatabase` (current)
   - Tests should be adapter-agnostic (works with future adapter)

1. **Phase 5**: Document migration status clearly:

   - Mark `ReflectionDatabase` as deprecated (vector migration complete)
   - Note `KnowledgeGraphDatabase` as "stable, future ACB migration planned"
   - Provide this document as reference for future contributors

## Approval

**Decision**: Deferred
**Approved By**: Migration architect (Phase 2.7)
**Date**: 2025-01-11
**Reason**: Pragmatic scope management - complete vector migration first, defer graph migration to future release when additional dependencies can be justified.
