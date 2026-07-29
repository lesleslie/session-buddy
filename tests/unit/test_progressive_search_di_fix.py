"""Failing-first tests for the three reflection-tool bugs found in v1 audit.

These tests use real components (not mocks) so they exercise the same code
paths that fail in production. Each test was failing before its fix and
should pass after.

Bug 1 — DI key mismatch in ``search/progressive_search.py:484``:
    The code calls ``depends.get_sync("ReflectionDatabaseAdapter")`` with a
    bare string key, but ``init_reflection_adapter`` registers under the
    fully-qualified class name. The string key never matches, so the
    ``KeyError("Service not registered: ReflectionDatabaseAdapter")``
    surfaces whenever the engine's ``_db`` is None.

Bug 2 — Wrong table queried by ``_quick_search_operation``:
    ``_quick_search_impl`` calls ``db.search_conversations`` (conversations
    table) but ``store_reflection`` writes to the reflections table.
    Storing a reflection and then searching for it via quick_search returns
    nothing.

Bug 3 — ``project`` parameter dropped on write:
    ``ReflectionDatabaseAdapterOneiric.store_reflection`` does not accept a
    ``project`` parameter, so the MCP wrapper also cannot accept one. The
    project field on the reflection row is always NULL even when the caller
    intends one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.adapters.reflection_adapter_oneiric import (
    ReflectionDatabaseAdapterOneiric,
)
from session_buddy.di.container import depends


@pytest.fixture
def registered_adapter(tmp_path: Path):
    """Create a real Oneiric adapter and register it under the class key.

    Mirrors ``init_reflection_adapter`` in ``adapters/lifecycle.py`` but
    scoped to ``tmp_path`` so tests don't pollute the production DB.
    """
    from session_buddy.adapters.settings import ReflectionAdapterSettings

    settings = ReflectionAdapterSettings(
        database_path=tmp_path / "test.duckdb",
        enable_embeddings=False,
    )
    adapter = ReflectionDatabaseAdapterOneiric(settings=settings)

    import asyncio

    asyncio.run(adapter.initialize())

    depends.set(ReflectionDatabaseAdapterOneiric, adapter)
    try:
        yield adapter
    finally:
        # Clean up DI registry so the next test isn't polluted.
        depends._resolver = depends._resolver.__class__()
        depends._instances.clear()


class TestProgressiveSearchDIFix:
    """Bug 1 — DI string key in progressive_search."""

    @pytest.mark.asyncio
    async def test_progressive_search_uses_real_di_when_db_is_none(
        self, registered_adapter: ReflectionDatabaseAdapterOneiric
    ) -> None:
        """Regression: when engine._db is None, progressive_search must
        resolve the adapter via DI without raising.

        Before fix: ``KeyError("Service not registered: ReflectionDatabaseAdapter")``
        because the code uses a bare string key that nothing registers.
        After fix: the code uses the class key (or ``require_reflection_database``)
        and resolves successfully.
        """
        from session_buddy.search.progressive_search import ProgressiveSearchEngine

        engine = ProgressiveSearchEngine()
        assert engine._db is None  # sanity: the bug branch is reachable

        # This must not raise. Pre-fix, it raises KeyError.
        result = await engine.search_progressive(
            query="anything",
            max_tiers=4,
            enable_early_stop=False,
        )
        assert result is not None


class TestQuickSearchRoundTripFix:
    """Bug 2 — ``_quick_search_impl`` queries the conversations table
    instead of the reflections table.

    The MCP ``store_reflection`` path writes to the ``reflections`` table
    (with ``insight_type IS NULL``). The MCP ``quick_search`` path calls
    ``db.search_conversations`` which queries the ``conversations`` table.
    The two paths never meet, so a stored reflection is invisible to
    quick_search.

    The fix changes ``_quick_search_operation`` to call ``search_reflections``
    instead. This test stores a reflection via the MCP wrapper and asserts
    quick_search returns it.
    """

    @pytest.mark.asyncio
    async def test_quick_search_finds_stored_reflection(
        self, registered_adapter: ReflectionDatabaseAdapterOneiric
    ) -> None:
        """Roundtrip: store a reflection, then quick-search for it.

        The assertion checks for content unique to the stored record
        (``"Always use"``) rather than just the query echo — otherwise the
        test passes even when the search returns no rows, because the
        MCP layer always prints the query back in its output banner.
        """
        from session_buddy.mcp.tools.memory.memory_tools import (
            _quick_search_impl,
            _store_reflection_impl,
        )

        stored = await _store_reflection_impl(
            "Always use context managers for resources",
            tags=["python", "best-practice"],
        )
        assert "success" in stored.lower() or "stored" in stored.lower(), stored

        # Search for a substring of what we just stored.
        result = await _quick_search_impl(
            "context managers",
            min_score=0.1,
        )
        # Bug 2: ``_quick_search_impl`` calls ``db.search_conversations``
        # which queries the ``conversations_v2`` table. The reflection is
        # in ``reflections_v2`` so the search returns "No results found"
        # and "Always use" (a substring of the stored content) does not
        # appear in the output.
        assert "no results" not in result.lower(), (
            f"quick_search did not find the stored reflection: {result!r}"
        )
        assert "Always use" in result, (
            f"quick_search returned a result but not the stored content: {result!r}"
        )


class TestStoreReflectionProjectFix:
    """Bug 3 — ``project`` parameter dropped on write.

    The Oneiric adapter's ``store_reflection`` does not accept a ``project``
    argument, so the field is always NULL. The MCP wrapper cannot accept
    a project either, because it forwards directly to the adapter.

    The fix adds ``project`` to both signatures and threads it into the
    INSERT. This test stores a reflection with a project, then asserts the
    row has the project field populated.
    """

    @pytest.mark.asyncio
    async def test_store_reflection_accepts_project(
        self, registered_adapter: ReflectionDatabaseAdapterOneiric
    ) -> None:
        """The Oneiric adapter's store_reflection must accept and store
        a project value.
        """
        # Pre-fix: ReflectionDatabaseAdapterOneiric.store_reflection does
        # not accept ``project=``, so this call raises TypeError.
        reflection_id = await registered_adapter.store_reflection(
            "Always use context managers",
            tags=["python"],
            project="myproject",
        )
        assert reflection_id is not None

        # The row should be retrievable with the same project.
        results = await registered_adapter.search_reflections(
            "context managers",
            project="myproject",
            use_embeddings=False,
        )
        assert any(r["content"] == "Always use context managers" for r in results)


class TestLatentDIKeyBugs:
    """Latent Bug 1 instances — bare-string DI lookups that would fail
    the moment the corresponding code path is exercised.

    ``session_buddy.rewriting.query_rewriter`` calls
    ``depends.get_sync("LLMManager")`` even though ``LLMManager`` is
    registered via ``depends.set(LLMManager, manager)`` (class key). The
    string lookup will raise ``KeyError("Service not registered: LLMManager")``
    on first exercise.

    ``session_buddy.mcp.tools.advanced.rewriting_tools`` calls
    ``depends.get_sync("QueryRewriter")`` even though ``QueryRewriter`` is
    not registered with DI at all. This raises immediately.

    Both are the same Bug 1 anti-pattern in places that just haven't been
    exercised in production yet. Fixes use the canonical getter pattern
    (and add DI registration for ``QueryRewriter``).
    """

    def test_llm_manager_lookup_via_class_key_succeeds(self) -> None:
        """After ``get_llm_manager()`` registers the singleton, the
        class-key lookup must succeed and the bare-string lookup must
        fail. This is the exact Bug 1 pattern from
        ``progressive_search.py:484``: bare-string DI lookups never
        match class-key registrations.

        Pre-fix: the call sites in ``query_rewriter.py`` used
        ``depends.get_sync("LLMManager")`` (string key), which would
        raise ``KeyError`` whenever the rewrite path ran after the
        manager had been registered.

        Post-fix: call sites use ``await get_llm_manager()`` (the
        canonical getter), and this test guards the registration
        contract.
        """
        from session_buddy.di.container import depends
        from session_buddy.llm_providers import LLMManager
        from session_buddy.utils.instance_managers import get_llm_manager

        import asyncio

        # Trigger the canonical registration path.
        manager = asyncio.run(get_llm_manager())
        assert manager is not None, (
            "get_llm_manager() returned None — the registration "
            "path is broken"
        )

        # Class-key lookup succeeds (this is what the fixed call sites use).
        resolved = depends.get_sync(LLMManager)
        assert resolved is manager, (
            "Class-key lookup returned a different instance than "
            "the one returned by get_llm_manager(). This means "
            "depends.set() was called with the wrong key."
        )

        # Bare-string lookup fails — the Bug 1 anti-pattern. If anyone
        # reintroduces ``depends.get_sync("LLMManager")`` in the future,
        # this assertion catches them.
        with pytest.raises(KeyError, match="Service not registered: LLMManager"):
            depends.get_sync("LLMManager")

    def test_query_rewriter_lookup_via_class_key_succeeds(self) -> None:
        """``QueryRewriter`` should be registered with DI under its
        class key. The MCP tools at ``rewriting_tools.py`` used to call
        ``depends.get_sync("QueryRewriter")`` (string key) which raised
        ``KeyError`` because nothing registered that string.

        Post-fix: ``get_query_rewriter()`` registers the singleton,
        and the class-key lookup succeeds.
        """
        from session_buddy.di.container import depends
        from session_buddy.rewriting.query_rewriter import QueryRewriter
        from session_buddy.utils.instance_managers import get_query_rewriter

        import asyncio

        rewriter = asyncio.run(get_query_rewriter())
        assert rewriter is not None, (
            "get_query_rewriter() returned None — the registration "
            "path is broken"
        )

        resolved = depends.get_sync(QueryRewriter)
        assert resolved is rewriter

        with pytest.raises(KeyError, match="Service not registered: QueryRewriter"):
            depends.get_sync("QueryRewriter")
