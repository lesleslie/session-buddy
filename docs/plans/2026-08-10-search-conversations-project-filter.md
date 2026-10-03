# Search Conversations Project Filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a real correctness bug where `ReflectionDatabaseAdapterOneiric.search_conversations()` accepts a `project: str | None` parameter but silently drops it before the SQL WHERE clause — causing cross-project leakage in search results. The companion method `search_by_source()` already honors project correctly; this plan ports that pattern to the general search path and adds a regression test.

**Architecture:** Thread `project: str | None = None` through `_search_conversations_db` → `_text_search_conversations` and `_vector_search_conversations`. When `project is not None`, append `AND project = ?` to the SQL and the value to the params list — mirroring the existing pattern in `search_by_source()` at `session_buddy/adapters/reflection_adapter_oneiric.py:1639-1641`. Update the docstring at line 1524 (currently says "not yet implemented"). Add one regression test to `tests/unit/test_reflection_adapter_oneiric.py` covering both text and vector search paths.

**Background:** This gap was flagged in the original lifecycle plan (`/Users/les/.claude/plans/kind-mixing-neumann.md`, deleted 2026-08-10 after its core fixes landed in commit `9181abce2`). The plan called it "a separate correctness gap" and recommended adding "a focused regression if the implementation touches that path" — this plan is that focused regression.

## Global Constraints

- **Python target**: 3.13+. Use `from __future__ import annotations` as the first non-comment line of every new source file (not applicable here — only edits to existing files). `X | None` (not `Optional[X]`), `list[str]`, `pathlib.Path`.
- **Hard limits** (from `pyproject.toml`): line-length 100, function args 10, branches 15, returns 6, statements 55 ceiling.
- **Existing patterns to mirror**: `search_by_source()` at `session_buddy/adapters/reflection_adapter_oneiric.py:1599-1657` is the reference implementation. Copy its `if project is not None: sql += " AND project = ?"; params.append(project)` shape exactly.
- **v1/v2 schema parity**: both `conversations` (v1) and `conversations_v2` have a `project TEXT` column. The fix applies uniformly to both SQL branches selected by `if table == "conversations_v2":`.
- **Test discipline**: regression test goes in `tests/unit/test_reflection_adapter_oneiric.py` in a new `TestProjectScopedSearch` class. Mirror the fixtures used by `TestConversationStorage` (lines 279-306).
- **No `assert` in production code.** Tests can use `assert`.
- **ruff + mypy** must pass on the changed file.

## Task 1: Apply project filter in `search_conversations` + add regression test

**Files:**

- `session_buddy/adapters/reflection_adapter_oneiric.py` (3 method signature changes, 2 SQL updates, 1 docstring fix)
- `tests/unit/test_reflection_adapter_oneiric.py` (new `TestProjectScopedSearch` class with 2 tests)

### Step 1: Thread `project` through `_search_conversations_db`

In `session_buddy/adapters/reflection_adapter_oneiric.py` at line 1744, change the signature:

```python
async def _search_conversations_db(
    self,
    query: str,
    limit: int,
    threshold: float,
) -> list[dict[str, t.Any]]:
```

to:

```python
async def _search_conversations_db(
    self,
    query: str,
    limit: int,
    threshold: float,
    project: str | None = None,
) -> list[dict[str, t.Any]]:
```

Update the docstring `Args` section to include `project: Optional project filter; when set, only rows with matching project are returned.`

### Step 2: Thread `project` through `_vector_search_conversations`

At line 1777, change:

```python
def _vector_search_conversations(
    self,
    query_embedding: list[float],
    limit: int,
    threshold: float,
) -> list[dict[str, t.Any]]:
```

to add `project: str | None = None` as a 4th param. In the v2 SQL branch (line 1804-1815), after `WHERE embedding IS NOT NULL`, append the project filter using the `search_by_source` pattern. In the v1 SQL branch (line 1828+), do the same. Update docstring.

### Step 3: Thread `project` through `_text_search_conversations`

At line 1855, change:

```python
def _text_search_conversations(
    self,
    query: str,
    limit: int,
) -> list[dict[str, t.Any]]:
```

to add `project: str | None = None` as a 3rd param. In both the v2 SQL (line 1874-1883) and v1 SQL (line 1895-1904) branches, append the project filter the same way. Update docstring.

### Step 4: Update `_search_conversations_db` dispatch to pass `project` through

Inside `_search_conversations_db` (line 1744), pass `project` to both branches:

```python
if query_embedding and self.settings.enable_vss:
    return self._vector_search_conversations(
        query_embedding=query_embedding,
        limit=limit,
        threshold=threshold,
        project=project,
    )
return self._text_search_conversations(
    query=query,
    limit=limit,
    project=project,
)
```

### Step 5: Update `search_conversations` to pass `project` to `_search_conversations_db`

At line 1562, change:

```python
results = await self._search_conversations_db(
    query=query,
    limit=limit,
    threshold=threshold,
)
```

to:

```python
results = await self._search_conversations_db(
    query=query,
    limit=limit,
    threshold=threshold,
    project=project,
)
```

Update the docstring at line 1524: change `"project: Optional project filter (not yet implemented)"` to `"project: Optional project filter; only rows with matching project are returned when set."`

### Step 6: Add regression test class

In `tests/unit/test_reflection_adapter_oneiric.py`, append a new class after `TestConversationStorage`:

```python
class TestProjectScopedSearch:
    """Regression coverage for the search_conversations project filter.

    Plan: docs/superpowers/plans/2026-08-10-search-conversations-project-filter.md
    """

    async def test_text_search_filters_by_project(self, adapter, tmp_path: Path) -> None:
        """search_conversations(project='A') must not return rows from project 'B'."""
        # Disable vector search so we exercise the text-search path
        adapter.settings = adapter.settings.model_copy(update={"enable_vss": False, "enable_embeddings": False})
        await adapter.initialize()

        await adapter.store_conversation("alpha marker alpha marker", project="alpha")
        await adapter.store_conversation("alpha marker alpha marker", project="beta")

        results = await adapter.search_conversations(
            "alpha marker", project="alpha", use_cache=False
        )
        assert results, "should match the alpha row"
        assert all(r.get("project") == "alpha" for r in results), (
            f"cross-project leakage: {results}"
        )

    async def test_vector_search_filters_by_project(self, adapter, tmp_path: Path) -> None:
        """Vector path: project filter must also apply."""
        # Skip when embeddings unavailable — vector search can't run without them
        if not adapter.settings.enable_embeddings:
            pytest.skip("embeddings disabled in this fixture")
        await adapter.initialize()

        await adapter.store_conversation("quantum entanglement physics", project="alpha")
        await adapter.store_conversation("quantum entanglement physics", project="beta")

        results = await adapter.search_conversations(
            "quantum physics", project="alpha", use_cache=False
        )
        assert results
        assert all(r.get("project") == "alpha" for r in results), (
            f"cross-project leakage: {results}"
        )
```

If the existing `adapter` fixture doesn't surface `project` on returned rows, add `"project": r.get("project")` to the result dicts in `_text_search_conversations` and `_vector_search_conversations` so the assertion has something to check. (The v2 schema's `_table("conversations") == "conversations_v2"` branch returns `id, content, metadata, timestamp` — `project` is in metadata or would need to be selected explicitly. Decide based on what the existing return shape is.)

### Step 7: Verify

```bash
uv run pytest tests/unit/test_reflection_adapter_oneiric.py::TestProjectScopedSearch -v
uv run ruff check session_buddy/adapters/reflection_adapter_oneiric.py tests/unit/test_reflection_adapter_oneiric.py
uv run mypy session_buddy/adapters/reflection_adapter_oneiric.py
uv run python -c "import session_buddy.adapters.reflection_adapter_oneiric; print('import OK')"
```

All four must pass. Commit message: `fix(adapter): honor project filter in search_conversations + add regression test`.

### Step 8: Commit + close plan

Commit with the message above, squash-merge to `main` per Bodai pre-1.0 policy. Update `.superpowers/sdd/2026-08-10-search-conversations-project-filter/progress.md` to mark Task 1 complete. Move the plan file to `docs/plans/_completed/` or leave in place — follow whichever convention the cross-repo-checkpoint plan settled on.

______________________________________________________________________

## Critical files

- `session_buddy/adapters/reflection_adapter_oneiric.py` — 3 method signatures, 2 SQL updates, 1 docstring fix, possibly result-dict shape (Step 6)
- `tests/unit/test_reflection_adapter_oneiric.py` — new `TestProjectScopedSearch` class with 2 tests

## Rollback signal

If `pytest tests/unit/test_reflection_adapter_oneiric.py` fails after the fix (e.g., the result-dict shape change in Step 6 breaks an existing test that reads `.get("score")` or similar), revert by:

1. `git revert <commit-hash>` to undo the merge
1. Check whether the existing return-dict shape needs `project` added vs whether the test should be loosened to accept either shape

The bug is real and currently shippable (only affects users with multi-project isolation needs), so no urgency if rollback is needed.
