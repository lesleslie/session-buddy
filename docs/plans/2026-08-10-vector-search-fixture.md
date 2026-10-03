# Vector Search Project Filter Fixture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the LOW-severity review finding from `2026-08-10-search-conversations-project-filter.md` — the vector-search regression path was untested by automated tests. Add a fixture that enables both embeddings and DuckDB VSS, then add `test_vector_search_filters_by_project` to the existing `TestProjectScopedSearch` class.

**Architecture:**

1. New fixture `adapter_with_vss` in `tests/unit/conftest.py` that mirrors `fast_temp_db` (from `tests/conftest.py`) but with `enable_embeddings=True` and `enable_vss=True`. The fixture must:

   - Try `INSTALL vss; LOAD vss;` before `await db.initialize()`; `pytest.skip()` on failure (mirrors the `duckdb_connection` pattern at `tests/conftest.py:838-848`)
   - Rely on the existing autouse `_stub_embedding_provider` fixture in `tests/unit/conftest.py:58-91` to supply deterministic 384d vectors via `_try_http_embedding_providers`. **No embedding mock needed in the new fixture.**

1. New test `test_vector_search_filters_by_project` appended to `TestProjectScopedSearch` in `tests/unit/test_reflection_adapter_oneiric.py`. Same shape as `test_text_search_filters_by_project` but uses `adapter_with_vss` and uses two distinct text strings (so the deterministic embeddings produce different vectors, exercising the full vector-comparison path).

**Background:** This is the third phase of work on the `search_conversations` project-filter bug:

| Phase | Plan | Status |
|-------|------|--------|
| 1 | `2026-08-10-search-conversations-project-filter.md` | ✅ Merged `9514239c` |
| 2 | `2026-08-10-v1-sql-cleanup.md` (no plan file — direct execution) | ✅ Merged `8de37260` |
| 3 | **This plan** — vector-search regression test | ⏳ Open |

Phase 1's reviewer flagged vector-search untested as LOW. The reviewer assumed a fixture was needed for the embeddings side; investigation on 2026-08-10 showed that assumption was wrong — the `_stub_embedding_provider` autouse fixture already handles embeddings. The actual blocker is DuckDB's `vss` extension, which the existing `fast_temp_db` fixture disables.

**Key insight:** DuckDB's `array_cosine_similarity()` function (called at `reflection_adapter_oneiric.py:1786` after the v1 cleanup) requires the `vss` community extension. Without it loaded, the SQL fails. Verified locally on 2026-08-10: `INSTALL vss; LOAD vss;` succeeds against `:memory:`.

## Global Constraints

- **Python target**: 3.13+. Use `from __future__ import annotations` as the first non-comment line of every new source file.
- **Hard limits** (from `pyproject.toml`): line-length 100, function args 10, branches 15, returns 6, statements 55 ceiling.
- **Existing patterns to mirror**: `fast_temp_db` fixture in `tests/conftest.py:240-267` (DuckDB path, settings object, `await db.initialize()`/`await _cleanup_db(db)` lifecycle). The new fixture lives in `tests/unit/conftest.py` per Bodai convention for unit-only fixtures; it imports `_get_reflection_database_class` and `_cleanup_db` from `tests.conftest`.
- **Skip semantics**: `pytest.skip(...)` inside a fixture is acceptable when an external dependency is unavailable (matches `duckdb_connection` pattern).
- **Test discipline**: append the new test to the existing `TestProjectScopedSearch` class in `tests/unit/test_reflection_adapter_oneiric.py` — same scope, just exercising the other SQL path.
- **No `assert` in production code.** Tests can use `assert`.
- **ruff + mypy** must pass on the changed files.

## Task 1: Add `adapter_with_vss` fixture + vector-search regression test

**Files:**

- `tests/unit/conftest.py` (append new fixture)
- `tests/unit/test_reflection_adapter_oneiric.py` (append `test_vector_search_filters_by_project` to `TestProjectScopedSearch`)

### Step 1: Add `adapter_with_vss` fixture to `tests/unit/conftest.py`

Open `tests/unit/conftest.py`. Find a good insertion point — after the `_stub_embedding_provider` fixture (lines 58-91) is the natural spot because the new fixture depends on it.

Append:

```python
@pytest.fixture
async def adapter_with_vss(tmp_path):
    """ReflectionDatabaseAdapterOneiric with embeddings + VSS enabled.

    Embeddings: the autouse `_stub_embedding_provider` fixture above
    patches `_try_http_embedding_providers` to return deterministic
    384d vectors from a text hash. No HTTP, no model loading.

    VSS: requires DuckDB's `vss` community extension for
    `array_cosine_similarity()`. Skips if install/load fails (matches
    `duckdb_connection` skip semantics).

    Used by `TestProjectScopedSearch.test_vector_search_filters_by_project`
    to exercise the vector-search SQL branch in `search_conversations`.
    """
    from session_buddy.adapters.settings import ReflectionAdapterSettings
    from tests.conftest import _cleanup_db, _get_reflection_database_class

    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "test_vss.duckdb",
        collection_name="default",
        embedding_dim=384,
        distance_metric="cosine",
        enable_embeddings=True,   # stubbed by autouse _stub_embedding_provider
        enable_vss=True,
        threads=1,
        memory_limit="512MB",
    )
    adapter = _get_reflection_database_class()(settings=settings)
    try:
        adapter.conn.execute("INSTALL vss; LOAD vss;")
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"duckdb-vss extension unavailable: {exc}")
    await adapter.initialize()
    yield adapter
    await _cleanup_db(adapter)
```

The lazy imports inside the fixture body mirror the `_stub_embedding_provider` pattern at `tests/unit/conftest.py:75-76` — keeps top-of-file imports minimal and avoids pulling ReflectionAdapterSettings into the conftest import graph unconditionally.

### Step 2: Add `test_vector_search_filters_by_project` to `TestProjectScopedSearch`

Open `tests/unit/test_reflection_adapter_oneiric.py`. Find the `TestProjectScopedSearch` class (added in commit `9514239c`). After the existing `test_text_search_without_project_returns_all` method, append:

```python
    async def test_vector_search_filters_by_project(self, adapter_with_vss) -> None:
        """search_conversations(project='alpha') must not return beta rows
        via the vector-search path.

        Uses two distinct text strings so the deterministic embeddings
        produce different vectors, exercising the full
        array_cosine_similarity comparison path.
        """
        await adapter_with_vss.store_conversation(
            "quantum entanglement physics relativity",
            metadata={"project": "alpha"},
        )
        await adapter_with_vss.store_conversation(
            "shakespeare sonnet theatre drama",
            metadata={"project": "beta"},
        )

        results = await adapter_with_vss.search_conversations(
            "quantum entanglement physics", project="alpha", use_cache=False
        )
        assert results, "should match the alpha row"
        assert all(r.get("project") == "alpha" for r in results), (
            f"cross-project leakage: {results}"
        )

        # Inverse: beta scope returns only the beta row
        beta_results = await adapter_with_vss.search_conversations(
            "shakespeare sonnet theatre", project="beta", use_cache=False
        )
        assert all(r.get("project") == "beta" for r in beta_results), (
            f"cross-project leakage: {beta_results}"
        )
```

### Step 3: Verify

```bash
uv run pytest tests/unit/test_reflection_adapter_oneiric.py::TestProjectScopedSearch -v
uv run ruff check tests/unit/conftest.py tests/unit/test_reflection_adapter_oneiric.py
uv run mypy tests/unit/conftest.py tests/unit/test_reflection_adapter_oneiric.py
uv run python -c "import tests.unit.conftest; print('import OK')"
```

All four must pass. The test suite should show **3 passed** in `TestProjectScopedSearch` (the two existing text-search tests + the new vector-search test).

### Step 4: Commit + squash-merge

Commit message: `test(adapter): cover vector-search project filter via VSS-enabled fixture`

Branch: `test/vector-search-project-filter`. Squash-merge to `main` per Bodai pre-1.0 policy. Update `.superpowers/sdd/2026-08-10-vector-search-fixture/progress.md` to mark Task 1 complete.

______________________________________________________________________

## Critical files

- `tests/unit/conftest.py` — new `adapter_with_vss` fixture (~25 lines)
- `tests/unit/test_reflection_adapter_oneiric.py` — new `test_vector_search_filters_by_project` (~20 lines appended to `TestProjectScopedSearch`)

## Rollback signal

If the VSS extension install fails on a CI runner that lacks community extension access (proxy, no network, blocked mirror), the test will skip rather than fail — by design. If a different fixture dependency is missing (e.g. `_get_reflection_database_class` import path changed), `pytest.skip` covers it. No code path can crash due to VSS unavailability.

If the test fails on the second-pass `Inverse` assertion (i.e. beta_results is empty when it should match the beta row), the most likely cause is the deterministic embedding returning a vector that's too distant from the search query to clear the `threshold`. Read the threshold default (in `ReflectionAdapterSettings`) and either: (a) lower it, (b) use more text overlap, or (c) investigate why the hash-based embeddings are not similar enough.
