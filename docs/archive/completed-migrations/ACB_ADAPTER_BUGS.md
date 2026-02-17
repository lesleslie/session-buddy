# ACB Adapter Bugs Discovered During Migration

**Phase 2.7 - Week 7 Day 6** (January 2025)

This document tracks bugs discovered in the ACB (Asynchronous Component Base) framework during the migration of session-buddy from direct DuckDB connections to ACB adapters.

## Bug #1: Graph Adapter SSL Property Shadowing

**Status:** ✅ RESOLVED (Fixed in ACB PR)

**Component:** `acb/adapters/graph/duckdb_pgq.py`

**Description:**
The `Graph` adapter class has both an `ssl_enabled` property from `BaseAdapter` and a local `self.ssl_enabled` attribute, causing property shadowing and `RecursionError`.

**Error:**

```python
RecursionError: maximum recursion depth exceeded
  File: acb/adapters/graph/duckdb_pgq.py:41
  Code: self.ssl_enabled = ssl_enabled  # Calls property setter recursively
```

**Root Cause:**

```python
class Graph(BaseAdapter):
    ssl_enabled: bool  # Property from BaseAdapter

    def __post_init__(self):
        self.ssl_enabled = self.config.graph.get(..., False)  # ERROR: recursion
```

**Resolution:**
Fixed in ACB repository. Property shadowing eliminated.

______________________________________________________________________

## Bug #2: Vector Search Array Dimension Type Cast

**Status:** ✅ RESOLVED (Fixed in ACB - session-buddy/Phase 2.7)

**Component:** `acb/adapters/vector/duckdb.py`

**Description:**
The vector search query builder uses `$1::FLOAT[]` without specifying array dimensions, causing DuckDB VSS extension functions to fail with type mismatch errors.

**Error:**

```
Binder Error: No function matches the given name and argument types
'array_distance(FLOAT[384], FLOAT[])'. You might need to add explicit type casts.
	Candidate functions:
	array_distance(FLOAT[ANY], FLOAT[ANY]) -> FLOAT
	array_distance(DOUBLE[ANY], DOUBLE[ANY]) -> DOUBLE
```

**Location:** `acb/adapters/vector/duckdb.py` lines 155-179

**Problematic Code:**

```text
def _build_search_query(
    self,
    table_name: str,
    select_fields: str,
    filter_expr: dict[str, t.Any] | None,
    limit: int,
) -> str:
    """Build the main search query with VSS."""
    query = f"""
        SELECT {safe_select_fields},
               array_distance(vector, $1::FLOAT[]) as score  # ❌ Missing dimension
        FROM {safe_table_name}
    """
    # ...
    return query
```

**Fix Required:**

```text
def _build_search_query(
    self,
    table_name: str,
    select_fields: str,
    filter_expr: dict[str, t.Any] | None,
    limit: int,
    dimension: int,
) -> str:  # Add dimension parameter
    """Build the main search query with VSS."""
    query = f"""
        SELECT {safe_select_fields},
               array_cosine_similarity(vector, $1::FLOAT[{dimension}]) as score
        FROM {safe_table_name}
    """
    # ...
    query += f" ORDER BY score DESC LIMIT {limit}"  # DESC for similarity
    return query
```

**Additional Issues:**

1. Uses `array_distance()` instead of `array_cosine_similarity()` - distance semantics are inverted (lower=better) vs similarity (higher=better)
1. Orders by ASC instead of DESC when using similarity metrics
1. Dimension information is available in `self.config.vector.default_dimension` but not passed to query builder

**Impact:**

- All vector searches fail and fall back to `_build_fallback_query()`
- Fallback query returns `score=0.0` for all results
- Semantic search completely non-functional

**Fix Applied** (session-buddy/Phase 2.7):

Modified `_build_search_query()` in `/Users/les/Projects/acb/acb/adapters/vector/duckdb.py`:

```python
def _build_search_query(
    self,
    table_name: str,
    select_fields: str,
    filter_expr: dict[str, t.Any] | None,
    limit: int,
) -> str:
    """Build the main search query with VSS."""
    safe_table_name = self._validate_table_name(table_name)
    safe_select_fields = self._validate_select_fields(select_fields)

    # Get dimension from config for proper type casting
    dimension = self.config.vector.default_dimension

    query = f"""
        SELECT {safe_select_fields},
               array_cosine_similarity(vector, $1::FLOAT[{dimension}]) as score
        FROM {safe_table_name}
    """  # Now includes {dimension} in cast and uses cosine_similarity

    if filter_expr:
        filter_conditions = self._build_filter_conditions(filter_expr)
        if filter_conditions:
            query += " WHERE " + " AND ".join(filter_conditions)

    query += f" ORDER BY score DESC LIMIT {limit}"  # DESC for similarity
    return query
```

**Changes Made:**

1. Added `dimension = self.config.vector.default_dimension` to get dimension from config
1. Changed `$1::FLOAT[]` → `$1::FLOAT[{dimension}]` to include explicit array size
1. Changed `array_distance()` → `array_cosine_similarity()` for proper similarity semantics
1. Changed `ORDER BY score ASC` → `ORDER BY score DESC` (higher similarity = better)

**Verification:**

```bash
# Test that fixed ACB search() method returns proper scores
python3 -c "
import asyncio
from session_buddy.di import configure
from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

configure(force=True)

async def test_fix():
    async with ReflectionDatabaseAdapter() as db:
        # Store test data
        await db.store_conversation(
            content='Python async patterns',
            metadata={'project': 'test'}
        )

        # Search using ACB adapter (should work now)
        results = await db.search_conversations(
            query='Python async',
            limit=5,
            min_score=0.3
        )

        # Verify scores are in valid range [0.0, 1.0]
        assert len(results) > 0, 'No results returned'
        assert all(0.0 <= r['score'] <= 1.0 for r in results), 'Invalid scores'
        print(f'✅ Fix verified: {len(results)} results with scores {[r[\"score\"] for r in results]}')

asyncio.run(test_fix())
"
# Output: ✅ Fix verified: 3 results with scores [0.8884, 0.8879, 0.8858]
```

______________________________________________________________________

## Summary

- **2 bugs discovered** during ACB adapter migration (Phase 2.7)
- **2 bugs resolved** ✅
  - Graph adapter SSL property shadowing (fixed in ACB)
  - Vector search array dimension casting (fixed in ACB - session-buddy/Phase 2.7)

**Impact on Migration:**
Both critical bugs have been resolved, allowing full ACB adapter integration:

- Vector adapter: ✅ Fully functional with semantic search
- Graph adapter: ✅ Ready for integration (SSL bug fixed)

**Phase 2 (Vector Migration) Status:**

- ACB adapter registration: ✅ Complete
- ReflectionDatabaseAdapter wrapper: ✅ Complete and tested
- All features working: Storage, search, statistics, filtering

**Next Steps:**

1. ✅ Complete Phase 2 vector migration
1. Begin Phase 3 graph adapter migration
1. Update memory_tools.py and search_tools.py to use new adapter
