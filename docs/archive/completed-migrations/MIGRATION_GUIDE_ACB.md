# ACB Adapter Migration Guide

**Migration Status**: Vector Adapter ✅ Complete | Graph Adapter ✅ Complete
**Target Users**: Developers using session-buddy's database layers
**Estimated Time**: 10-15 minutes (both adapters)
**Breaking Changes**: None (100% API compatible)

## Overview

This guide walks you through migrating both database layers to ACB (Asynchronous Component Base) adapters:

1. **Vector Adapter** (Phase 2): Conversations and reflections storage
1. **Graph Adapter** (Phase 3): Knowledge graph storage with hybrid pattern

Both migrations maintain 100% API compatibility while providing improved resource management and ACB integration.

### Why Migrate?

**Benefits**:

- ✅ **Better Resource Management**: Connection pooling and automatic lifecycle management
- ✅ **Improved Testability**: Dependency injection makes testing easier
- ✅ **Future-Proof**: Foundation for additional ACB integrations
- ✅ **Zero Breaking Changes**: Same API, better implementation

**What Changed**:

- Vector database backend moved from direct DuckDB to ACB Vector adapter
- Dependency injection integration for better modularity
- Deferred initialization pattern to prevent event loop conflicts

## Migration Steps

### Step 1: Update Your Imports

**Before** (deprecated):

```text
from session_buddy.reflection_tools import ReflectionDatabase


async def example():
    async with ReflectionDatabase() as db:
        await db.store_conversation("content", metadata)
```

**After** (recommended):

```text
from session_buddy.adapters.reflection_adapter import (
    ReflectionDatabaseAdapter as ReflectionDatabase,
)


async def example():
    async with ReflectionDatabase() as db:
        await db.store_conversation("content", metadata)
```

**Alternative** (alias for compatibility):

```text
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def example():
    async with ReflectionDatabaseAdapter() as db:
        await db.store_conversation("content", metadata)
```

### Step 2: Migrate Existing Data (Optional)

If you have existing conversation/reflection data in the old database format, use the migration script:

```bash
# Navigate to session-buddy directory
cd /path/to/session-buddy

# Dry run to see what would be migrated (safe, no changes)
python scripts/migrate_vector_database.py --dry-run --verbose

# Create backup before migration (recommended)
python scripts/migrate_vector_database.py --backup

# Perform actual migration
python scripts/migrate_vector_database.py

# Verbose output for debugging
python scripts/migrate_vector_database.py --verbose
```

**Migration Script Features**:

- **Dry Run Mode**: Preview changes without modifying data (`--dry-run`)
- **Automatic Backup**: Creates timestamped backup before migration (`--backup`)
- **Validation**: Compares record counts before/after migration
- **Graceful Handling**: Generates missing embeddings automatically
- **Verbose Logging**: Detailed progress reporting (`--verbose`)

**Migration Output Example**:

```
Migration Summary:
  Conversations: 42 migrated
  Reflections: 18 migrated
  Total: 60 records

Validation: ✅ All records migrated successfully
Backup created: ~/.claude/data/reflection_backup_20250111_123456.duckdb
```

### Step 3: Verify Migration (Optional)

After migration, verify your data is accessible:

```text
import asyncio
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def verify_migration():
    async with ReflectionDatabaseAdapter() as db:
        # Check conversation count
        results = await db.search_conversations("test", limit=5)
        print(f"Found {len(results)} conversations")

        # Verify search works
        for result in results:
            print(f"  - {result['content'][:50]}... (score: {result['score']:.2f})")


# Run verification
asyncio.run(verify_migration())
```

## API Compatibility

The new `ReflectionDatabaseAdapter` maintains **100% API compatibility** with the original `ReflectionDatabase`. All methods have identical signatures and return types.

### Core Methods (Unchanged API)

**Conversation Storage**:

```text
async with ReflectionDatabaseAdapter() as db:
    # Store conversation (same API)
    conv_id = await db.store_conversation(
        content="User asked about ACB adapters",
        metadata={"project": "session-buddy", "session_id": "abc123"},
    )

    # Search conversations (same API)
    results = await db.search_conversations(
        query="ACB adapters", limit=10, min_score=0.7, project="session-buddy"
    )
```

**Reflection Storage**:

```text
async with ReflectionDatabaseAdapter() as db:
    # Store reflection (same API)
    refl_id = await db.store_reflection(
        content="ACB adapters improve resource management",
        tags=["architecture", "performance"],
    )

    # Search reflections (same API)
    results = await db.search_reflections(
        query="resource management", limit=5, min_score=0.75
    )
```

**Statistics & Utilities**:

```text
async with ReflectionDatabaseAdapter() as db:
    # Get statistics (same API)
    stats = await db.get_stats()
    print(f"Total conversations: {stats['total_conversations']}")
    print(f"Total reflections: {stats['total_reflections']}")

    # Test embedding system (same API)
    status = await db.test_embedding_system()
    print(f"Embeddings: {status}")
```

## Code Examples: Old → New

### Example 1: Basic Conversation Storage

**Before** (deprecated):

```text
from session_buddy.reflection_tools import ReflectionDatabase


async def store_user_query(query: str, project: str):
    async with ReflectionDatabase() as db:
        return await db.store_conversation(content=query, metadata={"project": project})
```

**After** (recommended):

```text
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def store_user_query(query: str, project: str):
    async with ReflectionDatabaseAdapter() as db:
        return await db.store_conversation(content=query, metadata={"project": project})
```

**Change**: Only the import statement changed - function logic identical.

### Example 2: Semantic Search with Filtering

**Before** (deprecated):

```text
from session_buddy.reflection_tools import ReflectionDatabase


async def find_related_conversations(topic: str, project_name: str):
    async with ReflectionDatabase() as db:
        results = await db.search_conversations(
            query=topic, limit=20, min_score=0.8, project=project_name
        )
        return [r for r in results if r["score"] > 0.85]
```

**After** (recommended):

```text
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def find_related_conversations(topic: str, project_name: str):
    async with ReflectionDatabaseAdapter() as db:
        results = await db.search_conversations(
            query=topic, limit=20, min_score=0.8, project=project_name
        )
        return [r for r in results if r["score"] > 0.85]
```

**Change**: Only the import statement changed - search logic identical.

### Example 3: Test Fixtures (pytest)

**Before** (deprecated):

```text
import pytest
from session_buddy.reflection_tools import ReflectionDatabase


@pytest.fixture
async def reflection_db():
    async with ReflectionDatabase(db_path=":memory:") as db:
        yield db
```

**After** (recommended):

```text
import pytest
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


@pytest.fixture
async def reflection_db():
    async with ReflectionDatabaseAdapter(db_path=":memory:") as db:
        yield db
```

**Change**: Only the import statement changed - fixture pattern identical.

## Troubleshooting

### Issue 1: DeprecationWarning Messages

**Symptom**:

```
DeprecationWarning: ReflectionDatabase is deprecated and will be removed in a future release.
Use ReflectionDatabaseAdapter from session_buddy.adapters.reflection_adapter instead.
```

**Solution**: Update your import to use `ReflectionDatabaseAdapter`:

```python
# Change this:
from session_buddy.reflection_tools import ReflectionDatabase

# To this:
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter
```

**Temporary Workaround** (if you need time to migrate):

```python
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
```

### Issue 2: Import Error - Module Not Found

**Symptom**:

```
ImportError: cannot import name 'ReflectionDatabaseAdapter' from 'session_buddy.adapters.reflection_adapter'
```

**Solution**: Ensure you have the latest version of session-buddy:

```bash
cd /path/to/session-buddy
uv sync --group dev
```

**Check Installation**:

```text
python -c "from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter; print('✅ Migration available')"
```

### Issue 3: Database Connection Issues

**Symptom**:

```
RuntimeError: Connection not initialized. Call initialize() first.
```

**Solution**: Ensure you're using the async context manager pattern:

```text
# ✅ Correct (async context manager)
async with ReflectionDatabaseAdapter() as db:
    await db.store_conversation(...)

# ❌ Incorrect (missing context manager)
db = ReflectionDatabaseAdapter()
await db.store_conversation(...)  # Error!
```

### Issue 4: Vector Search Returns Empty Results

**Symptom**: Search queries return empty results or low similarity scores after migration.

**Possible Causes**:

1. **Embeddings not migrated**: Run migration script with `--verbose` to check
1. **ACB vector search bug**: Ensure you're using ACB with the vector search fix

**Solution**:

```bash
# Re-run migration with verbose output
python scripts/migrate_vector_database.py --backup --verbose

# Verify embeddings exist
python -c "
import asyncio
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

async def check():
    async with ReflectionDatabaseAdapter() as db:
        results = await db.search_conversations('test', limit=1)
        if results:
            print(f'✅ Vector search working (score: {results[0][\"score\"]:.2f})')
        else:
            print('⚠️ No results - check embeddings')

asyncio.run(check())
"
```

### Issue 5: Performance Degradation After Migration

**Symptom**: Slower query performance after migrating to ACB adapter.

**Investigation**:

```text
import time
import asyncio
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


async def benchmark_search():
    async with ReflectionDatabaseAdapter() as db:
        start = time.perf_counter()
        results = await db.search_conversations("test query", limit=10)
        elapsed = time.perf_counter() - start
        print(f"Search completed in {elapsed:.3f}s ({len(results)} results)")


asyncio.run(benchmark_search())
```

**Solution**: ACB adapter includes connection pooling which should improve performance. If you see degradation:

1. Check DuckDB configuration in `session_buddy/di/__init__.py`
1. Verify `threads=4` and `memory_limit="2GB"` settings
1. Ensure proper async/await usage (no blocking calls)

## Advanced Topics

### Custom Database Path

Both old and new implementations support custom database paths:

```text
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

# Custom path
custom_path = "/path/to/my/reflection.duckdb"
async with ReflectionDatabaseAdapter(db_path=custom_path) as db:
    await db.store_conversation("test", {})
```

### Dependency Injection Integration

The new adapter integrates with ACB's dependency injection system:

```python
from session_buddy.di import configure
from bevy import depends
from acb.adapters.vector.duckdb import Vector

# Configure DI container
configure()

# Access vector adapter directly
vector_adapter = depends.get_sync(Vector)
print(f"Vector adapter configured: {vector_adapter.config.vector.database_path}")
```

### Testing with Mock Adapters

The new architecture makes testing easier with dependency injection:

```python
import pytest
from unittest.mock import AsyncMock
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter


@pytest.fixture
async def mock_reflection_db(monkeypatch):
    """Mock reflection database for testing."""
    mock_db = AsyncMock(spec=ReflectionDatabaseAdapter)
    mock_db.store_conversation.return_value = "test-id"
    mock_db.search_conversations.return_value = [
        {"content": "test", "score": 0.95, "timestamp": "2025-01-11"}
    ]
    return mock_db
```

## Knowledge Graph Migration (Phase 3 - Complete!)

**Status**: ✅ The knowledge graph adapter migration is **complete and production-ready!**

**Hybrid Pattern Implementation**:
The graph adapter uses a hybrid sync/async pattern - async method signatures with synchronous DuckDB operations. This works because DuckDB is a fast local database with no network I/O.

### Why Hybrid Pattern?

**The Challenge**:

- `duckdb-engine` (SQLAlchemy dialect) is sync-only, cannot be used with async SQLAlchemy
- No production-ready async DuckDB drivers exist (`aioduckdb` is experimental)
- Need API consistency with Vector adapter (async signatures)

**The Solution**:
DuckDB operations are fast enough (\<1ms typically) that sync operations within async contexts don't block the event loop. This is the same pattern ACB's Vector adapter uses successfully.

### Migration Steps

#### Step 1: Update Your Imports

**Before** (original):

```text
from session_buddy.knowledge_graph import KnowledgeGraphDatabase


async def example():
    async with KnowledgeGraphDatabase() as db:
        entity_id = await db.create_entity("example", "concept")
```

**After** (recommended):

```text
from session_buddy.adapters.knowledge_graph_adapter import (
    KnowledgeGraphDatabaseAdapter as KnowledgeGraphDatabase,
)


async def example():
    async with KnowledgeGraphDatabase() as db:
        entity_id = await db.create_entity("example", "concept")
```

**Alternative** (explicit adapter):

```text
from session_buddy.adapters.knowledge_graph_adapter import (
    KnowledgeGraphDatabaseAdapter,
)


async def example():
    async with KnowledgeGraphDatabaseAdapter() as db:
        entity_id = await db.create_entity("example", "concept")
```

#### Step 2: Migrate Existing Data (Optional)

If you have existing knowledge graph data, use the migration script:

```bash
# Navigate to session-buddy directory
cd /path/to/session-buddy

# Dry run to see what would be migrated (safe, no changes)
python scripts/migrate_graph_database.py --dry-run --verbose

# Create backup before migration (recommended)
python scripts/migrate_graph_database.py --backup

# Perform actual migration
python scripts/migrate_graph_database.py

# Verbose output for debugging
python scripts/migrate_graph_database.py --verbose
```

**Migration Script Features**:

- **Dry Run Mode**: Preview changes without modifying data (`--dry-run`)
- **Automatic Backup**: Creates timestamped backup before migration (`--backup`)
- **Validation**: Compares record counts before/after migration
- **Preserves Data**: Maintains IDs and timestamps during migration
- **Verbose Logging**: Detailed progress reporting (`--verbose`)

**Migration Output Example**:

```
Migration Summary:
  Entities: 125 migrated
  Relationships: 87 migrated
  Total: 212 records

Validation: ✅ All records migrated successfully
Backup created: ~/.claude/data/knowledge_graph_backup_20250111_123456.duckdb
```

#### Step 3: Verify Migration (Optional)

After migration, verify your data is accessible:

```text
import asyncio
from session_buddy.adapters.knowledge_graph_adapter import (
    KnowledgeGraphDatabaseAdapter,
)


async def verify_migration():
    async with KnowledgeGraphDatabaseAdapter() as db:
        # Check entity count
        stats = await db.get_stats()
        print(f"Total entities: {stats['total_entities']}")
        print(f"Total relationships: {stats['total_relationships']}")

        # Test entity search
        results = await db.search_entities("test", limit=5)
        print(f"Found {len(results)} entities")


# Run verification
asyncio.run(verify_migration())
```

### API Compatibility

The new `KnowledgeGraphDatabaseAdapter` maintains **100% API compatibility** with the original `KnowledgeGraphDatabase`. All methods have identical signatures and return types.

### Core Methods (Unchanged API)

**Entity Management**:

```text
async with KnowledgeGraphDatabaseAdapter() as db:
    # Create entity (same API)
    entity_id = await db.create_entity(
        name="session-buddy",
        entity_type="project",
        observations=["MCP server for session management"],
        properties={"language": "Python", "version": "0.7.4"},
    )

    # Get entity by ID (same API)
    entity = await db.get_entity(entity_id)

    # Search entities (same API)
    results = await db.search_entities(
        query="mcp server", entity_type="project", limit=10
    )
```

**Relationship Management**:

```text
async with KnowledgeGraphDatabaseAdapter() as db:
    # Create relationship (same API)
    rel_id = await db.create_relation(
        from_entity="session-buddy",
        to_entity="ACB",
        relation_type="uses",
        properties={"version": ">=0.25.2"},
    )

    # Get relationships (same API)
    relationships = await db.get_relationships(
        entity_name="session-buddy", direction="outgoing"
    )
```

**Graph Operations**:

```text
async with KnowledgeGraphDatabaseAdapter() as db:
    # Find path between entities (same API)
    paths = await db.find_path(
        from_entity="session-buddy", to_entity="DuckDB", max_depth=3
    )

    # Get statistics (same API)
    stats = await db.get_stats()
    print(f"Entities: {stats['total_entities']}")
    print(f"Relationships: {stats['total_relationships']}")
```

### Code Examples: Old → New

#### Example 1: Basic Entity Creation

**Before** (original):

```text
from session_buddy.knowledge_graph import KnowledgeGraphDatabase


async def create_project_entity(name: str, language: str):
    async with KnowledgeGraphDatabase() as db:
        return await db.create_entity(
            name=name,
            entity_type="project",
            observations=[f"Project written in {language}"],
            properties={"language": language},
        )
```

**After** (recommended):

```text
from session_buddy.adapters.knowledge_graph_adapter import (
    KnowledgeGraphDatabaseAdapter,
)


async def create_project_entity(name: str, language: str):
    async with KnowledgeGraphDatabaseAdapter() as db:
        return await db.create_entity(
            name=name,
            entity_type="project",
            observations=[f"Project written in {language}"],
            properties={"language": language},
        )
```

**Change**: Only the import statement changed - function logic identical.

#### Example 2: Graph Traversal

**Before** (original):

```text
from session_buddy.knowledge_graph import KnowledgeGraphDatabase


async def find_dependencies(project: str):
    async with KnowledgeGraphDatabase() as db:
        # Get all outgoing "uses" relationships
        deps = await db.get_relationships(
            entity_name=project, relation_type="uses", direction="outgoing"
        )
        return [rel["to_entity"] for rel in deps]
```

**After** (recommended):

```text
from session_buddy.adapters.knowledge_graph_adapter import (
    KnowledgeGraphDatabaseAdapter,
)


async def find_dependencies(project: str):
    async with KnowledgeGraphDatabaseAdapter() as db:
        # Get all outgoing "uses" relationships
        deps = await db.get_relationships(
            entity_name=project, relation_type="uses", direction="outgoing"
        )
        return [rel["to_entity"] for rel in deps]
```

**Change**: Only the import statement changed - graph traversal logic identical.

### Understanding the Hybrid Pattern

The hybrid pattern is safe for DuckDB because:

1. **Local Operations**: DuckDB database is a local file or in-memory (no network I/O)
1. **Fast Execution**: Operations typically complete in \<1ms
1. **No Blocking**: No waiting for external resources or slow I/O
1. **Event Loop Safe**: Sync operations that complete quickly don't block the event loop

**Under the Hood**:

```text
class KnowledgeGraphDatabaseAdapter:
    """Hybrid pattern: async signatures, sync operations."""

    async def create_entity(self, name: str, entity_type: str, ...) -> dict:
        """Async signature for API consistency."""
        conn = self._get_conn()  # Get sync DuckDB connection

        # Sync DuckDB execution (fast local operation <1ms)
        conn.execute(
            """INSERT INTO kg_entities (...) VALUES (?, ?, ...)""",
            (entity_id, name, entity_type, ...)
        )

        return {"id": entity_id, "name": name, ...}
```

### Benefits of Hybrid Pattern

- ✅ **Zero New Dependencies**: No need for `duckdb-engine` or async drivers
- ✅ **API Consistency**: Same async interface as Vector adapter
- ✅ **ACB Integration**: Uses ACB Config for database path configuration
- ✅ **Simpler Implementation**: Direct DuckDB operations (no SQLAlchemy layer)
- ✅ **Proven Pattern**: Same approach ACB's Vector adapter uses successfully

### Migration FAQ

**Q: Do I need to migrate my knowledge graph data immediately?**
A: No. The original `KnowledgeGraphDatabase` class continues to work. Migrate when convenient.

**Q: What if I don't run the migration script?**
A: New data will be stored in the new schema. Old data remains in the old database until you migrate it.

**Q: Can I use both old and new classes simultaneously?**
A: Technically yes, but not recommended. They use different database files. Migrate fully to avoid data fragmentation.

**Q: Will the hybrid pattern cause performance issues?**
A: No. DuckDB operations are so fast (\<1ms) that sync operations don't block the event loop. This is the same pattern ACB uses successfully.

**Q: What about async best practices?**
A: The hybrid pattern follows pragmatic async design: prioritize user experience (API consistency) over theoretical purity when safe to do so.

## Rollback Procedure

If you encounter critical issues after migration, you can rollback:

### Step 1: Restore Backup (If Created)

```bash
# Find your backup
ls -la ~/.claude/data/reflection_backup_*.duckdb

# Restore backup
cp ~/.claude/data/reflection_backup_YYYYMMDD_HHMMSS.duckdb ~/.claude/data/reflection.duckdb
```

### Step 2: Revert Code Changes

```text
# Temporarily use deprecated class (generates warnings)
from session_buddy.reflection_tools import ReflectionDatabase

async with ReflectionDatabase() as db:
    # Your existing code continues to work
    await db.store_conversation(...)
```

### Step 3: Report Issues

If you need to rollback, please report issues:

1. Create GitHub issue with error details
1. Include migration script output (`--verbose`)
1. Provide database size and record counts
1. Note any custom configuration or usage patterns

## FAQ

**Q: Do I need to migrate immediately?**
A: No. The old `ReflectionDatabase` class continues to work (with deprecation warnings). Migrate when convenient.

**Q: Will my existing data be lost?**
A: No. The migration script copies data from the old schema to the new schema. Use `--backup` for safety.

**Q: What if I don't run the migration script?**
A: New data will be stored in the new schema. Old data remains in the old database file until you migrate it.

**Q: Can I use both old and new classes simultaneously?**
A: Technically yes, but not recommended. They use different database schemas. Migrate fully to avoid data fragmentation.

**Q: How long does migration take?**
A: Depends on data size. Typical installations (100-1000 conversations) migrate in 1-5 seconds.

**Q: What about the knowledge graph database?**
A: Knowledge graph migration is deferred. Continue using `KnowledgeGraphDatabase` - it's fully functional and won't be deprecated yet.

**Q: Are there any performance differences?**
A: ACB adapter provides connection pooling which can improve performance for concurrent operations. Embedding generation speed is unchanged.

**Q: What Python version is required?**
A: Python 3.13+ (same requirement as before migration).

## Next Steps

After migration:

1. ✅ **Update imports** to use `ReflectionDatabaseAdapter`
1. ✅ **Run migration script** if you have existing data
1. ✅ **Test your application** to verify everything works
1. ✅ **Update tests** to use new import
1. ✅ **Monitor deprecation warnings** and address them

## Additional Resources

- **Full Migration Details**: `docs/ACB_MIGRATION_COMPLETE.md`
- **Phase 3 Deferral Rationale**: `docs/ACB_MIGRATION_PHASE3_DEFERRED.md`
- **ACB Framework Documentation**: `/Users/les/Projects/acb/README.md`
- **Migration Script Source**: `scripts/migrate_vector_database.py`

## Support

For migration assistance:

- Check `docs/ACB_MIGRATION_COMPLETE.md` for technical details
- Review `session_buddy/adapters/reflection_adapter.py` source code
- Open GitHub issue for migration-specific problems
- Consult CLAUDE.md for architecture overview

______________________________________________________________________

**Migration Status**: Ready for Production ✅
**Last Updated**: January 11, 2025
**Phase**: 2.7 Complete (Vector Adapter)
