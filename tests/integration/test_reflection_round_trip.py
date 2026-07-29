"""End-to-end roundtrip tests for the reflection memory layer.

These tests exercise the MCP wrappers against a real Oneiric adapter
(no mocks of the database itself) to catch any divergence between the
write path (``store_reflection``) and the read paths (``quick_search``,
``search_by_concept``, ``search_summary``). The unit tests use mocks
that mask such divergences — see ``tests/unit/test_memory_tools.py``
where ``test_quick_search_with_results`` enshrined the wrong-table bug
(Bug 2 from the v1 audit) by mocking ``search_conversations`` instead
of ``search_reflections``.

Each roundtrip test:

1. Stores a reflection via ``_store_reflection_impl`` (MCP wrapper).
2. Searches for it via the relevant MCP wrapper (``_quick_search_impl``,
   ``_search_by_concept_impl``, ``_search_summary_impl``).
3. Asserts the stored record's identity (id and content) appears in
   the search results — not just ``len >= 1``, which passes for any
   unrelated record.

The tests use a temp DB so they're isolated and don't pollute the
production state.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.adapters.settings import ReflectionAdapterSettings
from session_buddy.di.container import depends


@pytest.fixture
def isolated_adapter(tmp_path: Path):
    """Real Oneiric adapter registered in DI, scoped to ``tmp_path``.

    Mirrors what ``adapters/lifecycle.init_reflection_adapter`` does in
    production (registers under the class key) but isolates state so
    tests don't pollute each other.
    """
    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "roundtrip.duckdb",
        enable_embeddings=False,
    )
    adapter = ReflectionDatabaseAdapterOneiric(settings=settings)
    asyncio.run(adapter.initialize())
    depends.set(ReflectionDatabaseAdapterOneiric, adapter)
    try:
        yield adapter
    finally:
        depends._resolver = depends._resolver.__class__()
        depends._instances.clear()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_store_then_quick_search_round_trip(isolated_adapter) -> None:
    """The end-to-end path most users will exercise: store a reflection,
    then immediately search for it via the MCP ``quick_search`` tool.

    Bug 2 of the v1 audit: ``_quick_search_impl`` previously called
    ``db.search_conversations`` (conversations_v2 table) while
    ``store_reflection`` wrote to reflections_v2. Storing and then
    quick-searching the same content always returned "No results found".
    This test would have failed pre-fix and now confirms identity.
    """
    from session_buddy.mcp.tools.memory.memory_tools import (
        _quick_search_impl,
        _store_reflection_impl,
    )

    unique_content = "Roundtrip unique marker abc123 quick search"
    stored = await _store_reflection_impl(
        unique_content,
        tags=["roundtrip", "test"],
    )
    assert "success" in stored.lower() or "stored" in stored.lower(), stored

    result = await _quick_search_impl("abc123 quick search", min_score=0.1)

    # Identity assertion: not just "any result returned", but
    # "the result contains content we just stored".
    assert "no results" not in result.lower(), (
        f"quick_search returned no results for content we just stored: {result!r}"
    )
    assert unique_content in result, (
        f"Stored content not echoed in quick_search output: {result!r}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_store_then_search_by_concept_round_trip(isolated_adapter) -> None:
    """Same shape as quick_search but via ``search_by_concept``.

    Concept search is a different code path; this guards against
    class-of-bug where one search entrypoint is fixed but a sibling
    entrypoint remains broken.
    """
    from session_buddy.mcp.tools.memory.memory_tools import (
        _search_by_concept_impl,
        _store_reflection_impl,
    )

    unique_content = "Roundtrip unique marker xyz789 search by concept"
    await _store_reflection_impl(unique_content, tags=["concept-test"])

    result = await _search_by_concept_impl(
        "xyz789 search by concept",
        limit=5,
    )
    assert "no results" not in result.lower(), (
        f"search_by_concept returned no results: {result!r}"
    )
    assert unique_content in result


@pytest.mark.asyncio
@pytest.mark.integration
async def test_store_then_search_summary_round_trip(isolated_adapter) -> None:
    """Same shape via ``search_summary``.

    search_summary aggregates results across categories and outputs
    statistics (project distribution, theme counts), not raw content
    matches. The identity assertion here checks the summary identifies
    the stored record via ``Total results: N >= 1`` rather than echoing
    the content string — same bug-2 fix story, different output shape.
    """
    from session_buddy.mcp.tools.memory.memory_tools import (
        _search_summary_impl,
        _store_reflection_impl,
    )

    unique_content = "Roundtrip unique marker summary456 search summary"
    await _store_reflection_impl(unique_content, tags=["summary-test"])

    result = await _search_summary_impl(
        "summary456 search summary",
        min_score=0.0,
    )
    assert "Total results: 0" not in result, (
        f"search_summary reported zero results for content we just stored: {result!r}"
    )
    # Verify the word-frequency breakdown includes our stored term.
    assert "summary456" in result, (
        f"Stored term not present in search_summary output: {result!r}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_round_trip_preserves_record_identity(isolated_adapter) -> None:
    """Beyond content presence, verify the search returns the SAME
    record (matching ID) that we stored. This is the identity contract
    that ``len(results) >= 1`` cannot verify — a search returning
    ANY record passes that loose check, but only the right record
    passes this one.
    """
    reflection_id = await isolated_adapter.store_reflection(
        "Identity contract marker id-abc-def-9999",
        tags=["identity-test"],
    )
    assert reflection_id is not None

    # Use the adapter directly (not the MCP wrapper) to verify the
    # adapter-level contract. The MCP wrapper tests above verify the
    # tool layer; this verifies the data layer.
    results = await isolated_adapter.search_reflections(
        "id-abc-def-9999",
        use_embeddings=False,
    )
    assert any(r["id"] == reflection_id for r in results), (
        f"Stored reflection {reflection_id!r} not found via "
        f"search_reflections. Got: {[r['id'] for r in results]!r}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_store_with_project_filters_by_project(isolated_adapter) -> None:
    """Bug 3 of the v1 audit: ``project`` was silently dropped on
    store, so project-scoped recall saw every reflection as belonging
    to no project. This test stores two reflections with different
    projects and asserts project-scoped search returns only the
    matching one.
    """
    # Store one reflection per project.
    project_a_content = "Project A marker project-aaa-111"
    project_b_content = "Project B marker project-bbb-222"
    id_a = await isolated_adapter.store_reflection(
        project_a_content,
        tags=["t"],
        project="aaa",
    )
    id_b = await isolated_adapter.store_reflection(
        project_b_content,
        tags=["t"],
        project="bbb",
    )
    assert id_a != id_b

    # Project A search returns A, not B.
    results_a = await isolated_adapter.search_reflections(
        "marker project-aaa-111",
        project="aaa",
        use_embeddings=False,
    )
    assert any(r["id"] == id_a for r in results_a)
    assert all(r.get("project") == "aaa" for r in results_a if r.get("project"))

    # Project B search returns B, not A.
    results_b = await isolated_adapter.search_reflections(
        "marker project-bbb-222",
        project="bbb",
        use_embeddings=False,
    )
    assert any(r["id"] == id_b for r in results_b)
    assert all(r.get("project") == "bbb" for r in results_b if r.get("project"))
