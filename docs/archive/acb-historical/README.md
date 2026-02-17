# Historical ACB Documentation

**Status:** Historical Reference Only
**Current Architecture:** Oneiric (Native DuckDB Adapters)
**Migration Date:** January 2025 (Phase 5)

---

## Overview

The documents in this directory with `ACB_` prefix are **historical references** documenting Session Buddy's migration from external framework dependencies (ACB - Asynchronous Component Base) to native DuckDB adapters (Oneiric).

**These documents are preserved for historical context but no longer reflect the current architecture.**

---

## Historical ACB Documents

The following documents describe the **former ACB adapter architecture** (Phases 2-4) and are now archived in `docs/archive/acb-historical/`:

- `ACB_MIGRATION_PLAN.md` - Original migration plan from legacy to ACB adapters
- `ACB_MIGRATION_COMPLETE.md` - ACB migration completion summary
- `ACB_MIGRATION_SUMMARY.md` - ACB migration benefits and outcomes
- `ACB_MIGRATION_PHASE3_STATUS.md` - Phase 3 status report
- `ACB_STORAGE_ADAPTER_GUIDE.md` - ACB storage adapter usage guide
- `ACB_STORAGE_ADAPTER_FIX.md` - ACB storage adapter bug fixes
- `ACB_GRAPH_ADAPTER_INVESTIGATION.md` - ACB graph adapter research
- `MIGRATION_GUIDE_ACB.md` - User migration guide for ACB
- `ACB_DI_PATTERNS.md` - ACB dependency injection patterns

---

## Current Architecture: Oneiric

**As of Phase 5 (January 2025), Session Buddy uses Oneiric adapters:**

### What is Oneiric?

Oneiric is Session Buddy's **native DuckDB adapter implementation** that replaced ACB external framework dependency.

**Key Benefits:**
- ✅ Removed external framework dependency (simplified stack)
- ✅ Direct DuckDB native operations
- ✅ Maintained 100% API compatibility
- ✅ Improved performance (<1ms operations)
- ✅ Zero new dependencies
- ✅ Simplified codebase

### Oneiric Architecture

**Adapter Files:**
- `session_buddy/adapters/reflection_adapter_oneiric.py` - Vector/reflection storage
- `session_buddy/adapters/knowledge_graph_adapter_oneiric.py` - Graph database
- `session_buddy/adapters/storage_oneiric.py` - Storage abstraction

**Hybrid Pattern:**
```python
async def create_entity(self, name: str, ...) -> dict:
    """Async signature for API consistency, sync operation internally."""
    conn = self._get_conn()  # Sync DuckDB connection
    conn.execute("INSERT INTO kg_entities ...")  # Fast local operation (<1ms)
    return {"id": entity_id, ...}
```

DuckDB operations are fast enough (<1ms) to safely use synchronous code within async contexts without blocking the event loop.

---

## Current Documentation

For **current Session Buddy architecture**, refer to:

### Primary Documentation
- [`../../../CLAUDE.md`](../../../CLAUDE.md) - Main development guide with Oneiric architecture
- [`../../../README.md`](../../../README.md) - Project overview and features
- [`../../migrations/ONEIRIC_MIGRATION_PLAN.md`](../../migrations/ONEIRIC_MIGRATION_PLAN.md) - Oneiric migration details

### Architecture Documentation
- [`../../developer/ARCHITECTURE.md`](../../developer/ARCHITECTURE.md) - Current system architecture
- [`../../reference/API_REFERENCE.md`](../../reference/API_REFERENCE.md) - API documentation

---

## Migration Path: ACB → Oneiric

**Historical Phases:**
- **Phase 2 (Jan 11, 2025):** Migrated reflections/conversations to ACB Vector adapter
- **Phase 3 (Jan 11, 2025):** Migrated knowledge graph to ACB Graph adapter with hybrid pattern
- **Phase 4 (Jan 2025):** Dependency injection refactoring
- **Phase 5 (Jan 2025):** **Oneiric conversion - removed ACB dependency entirely**

**Benefits Retained from ACB Migration:**
- ✅ Dependency injection patterns (kept)
- ✅ Hybrid sync/async pattern (kept)
- ✅ 100% API compatibility (maintained)
- ✅ Better testability (improved)

**Additional Oneiric Benefits:**
- ✅ No external framework dependency
- ✅ Simplified codebase
- ✅ Reduced maintenance burden

---

## Why These Docs Are Preserved

These historical ACB documents are preserved to:

1. **Document Evolution:** Show the architectural journey from legacy → ACB → Oneiric
2. **Understand Decisions:** Explain why certain patterns exist (hybrid async/sync)
3. **Reference Patterns:** ACB patterns that were adapted for Oneiric
4. **Historical Context:** Future developers can understand the migration path

---

## For New Developers

**If you're new to Session Buddy:**

1. ⚠️ **Ignore ACB_* docs** - These are historical only
2. ✅ **Read CLAUDE.md** - Current architecture and development guide
3. ✅ **Read migrations/ONEIRIC_MIGRATION_PLAN.md** - Understand current adapter system
4. ✅ **Study Oneiric adapters** - Current implementation in `session_buddy/adapters/`

**Key Takeaway:** Session Buddy now uses **native DuckDB with Oneiric adapters**. ACB was an intermediate step that is no longer part of the codebase.

---

## Questions?

For questions about:
- **Current architecture:** See `CLAUDE.md` and `developer/ARCHITECTURE.md`
- **Oneiric adapters:** See `migrations/ONEIRIC_MIGRATION_PLAN.md`
- **Historical context:** See ACB_* documents in this directory (read-only reference)

---

**Last Updated:** January 2026
**Architecture Status:** Oneiric (Phase 5+)
**ACB Status:** Removed (historical reference only)
