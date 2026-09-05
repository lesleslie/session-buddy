"""Unit tests for session_buddy.rewriting.hooks_integration.

Exercises every branch of ``_query_rewriting_handler`` and the hook
registration done by ``initialize_query_rewriting_hooks``. ``QueryRewriter``
is replaced with an ``AsyncMock`` so the tests run without an LLM backend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.core.hooks import (
    HookContext,
    HookResult,
    HooksManager,
    HookType,
)
from session_buddy.rewriting.hooks_integration import (
    _query_rewriting_handler,
    initialize_query_rewriting_hooks,
)
from session_buddy.rewriting.query_rewriter import (
    QueryRewriter,
    QueryRewriteResult,
    RewriteContext,
)


def _make_context(
    metadata: dict | None = None,
    session_id: str = "test-session",
) -> HookContext:
    """Build a HookContext for the PRE_SEARCH_QUERY hook."""
    return HookContext(
        hook_type=HookType.PRE_SEARCH_QUERY,
        session_id=session_id,
        timestamp=datetime.now(UTC),
        metadata=metadata if metadata is not None else {},
    )


def _build_rewriter(result: QueryRewriteResult) -> AsyncMock:
    """Build an AsyncMock QueryRewriter that returns ``result``."""
    rewriter = AsyncMock(spec=QueryRewriter)
    rewriter.rewrite_query = AsyncMock(return_value=result)
    return rewriter


def _build_raising_rewriter(exc: Exception) -> AsyncMock:
    """Build an AsyncMock QueryRewriter that raises ``exc``."""
    rewriter = AsyncMock(spec=QueryRewriter)
    rewriter.rewrite_query = AsyncMock(side_effect=exc)
    return rewriter


class TestHandlerEmptyQuery:
    """Handler branch: no query in metadata returns HookResult(success=True)."""

    async def test_missing_query_key_returns_success_without_rewrite(self) -> None:
        """No 'query' key in metadata → skip rewriting entirely."""
        context = _make_context(metadata={"recent_files": ["x.py"]})
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query="",
                rewritten_query="",
                was_rewritten=False,
                confidence=0.0,
                llm_provider=None,
                latency_ms=0.0,
                context_used=False,
            ),
        )

        result = await _query_rewriting_handler(context, rewriter)

        assert isinstance(result, HookResult)
        assert result.success is True
        assert result.modified_context is None
        assert result.error is None
        rewriter.rewrite_query.assert_not_awaited()

    async def test_empty_string_query_returns_success_without_rewrite(self) -> None:
        """Empty-string query → skip rewriting entirely."""
        context = _make_context(metadata={"query": ""})
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query="",
                rewritten_query="",
                was_rewritten=False,
                confidence=0.0,
                llm_provider=None,
                latency_ms=0.0,
                context_used=False,
            ),
        )

        result = await _query_rewriting_handler(context, rewriter)

        assert result.success is True
        assert result.modified_context is None
        rewriter.rewrite_query.assert_not_awaited()


class TestHandlerClearQuery:
    """Handler branch: query is clear, no rewrite needed."""

    async def test_clear_query_returns_success_without_modified_context(self) -> None:
        """``was_rewritten=False`` → no context modification, no error."""
        original = "how to use httpx client"
        context = _make_context(metadata={"query": original})
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query=original,
                rewritten_query=original,
                was_rewritten=False,
                confidence=0.0,
                llm_provider=None,
                latency_ms=1.0,
                context_used=False,
                cache_hit=False,
            ),
        )

        result = await _query_rewriting_handler(context, rewriter)

        assert result.success is True
        assert result.modified_context is None
        assert result.error is None
        rewriter.rewrite_query.assert_awaited_once()

    async def test_clear_query_passes_metadata_to_rewrite_context(self) -> None:
        """Verify metadata fields are wired into RewriteContext correctly."""
        original = "specific python question"
        recent_conversations = [{"id": "c1", "content": "talked about async"}]
        recent_files = ["module.py", "other.py"]
        context = _make_context(
            metadata={
                "query": original,
                "recent_conversations": recent_conversations,
                "project": "test-project",
                "recent_files": recent_files,
                "extra_field": "preserved-in-session-context",
            },
        )
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query=original,
                rewritten_query=original,
                was_rewritten=False,
                confidence=0.0,
                llm_provider=None,
                latency_ms=1.0,
                context_used=False,
            ),
        )

        await _query_rewriting_handler(context, rewriter)

        rewriter.rewrite_query.assert_awaited_once()
        call = rewriter.rewrite_query.await_args
        assert call is not None
        # kwargs: query, context (RewriteContext), force_rewrite
        kwargs = call.kwargs
        assert kwargs["query"] == original
        assert kwargs["force_rewrite"] is False
        rc: RewriteContext = kwargs["context"]
        assert isinstance(rc, RewriteContext)
        assert rc.query == original
        assert rc.recent_conversations == recent_conversations
        assert rc.project == "test-project"
        assert rc.recent_files == recent_files
        # session_context should be the full metadata dict
        assert rc.session_context == context.metadata


class TestHandlerAmbiguousQuery:
    """Handler branch: ambiguous query was rewritten → modify context."""

    async def test_rewritten_query_returns_modified_context(self) -> None:
        """``was_rewritten=True`` → success with full modified_context."""
        original = "what did I learn about async"
        rewritten = "what did I learn about async/await in our discussion of error handling"
        context = _make_context(metadata={"query": original})
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query=original,
                rewritten_query=rewritten,
                was_rewritten=True,
                confidence=0.85,
                llm_provider="minimax",
                latency_ms=120.0,
                context_used=True,
                cache_hit=False,
            ),
        )

        result = await _query_rewriting_handler(context, rewriter)

        assert result.success is True
        assert result.error is None
        assert result.modified_context is not None
        modified = result.modified_context
        assert modified["query"] == rewritten
        assert modified["original_query"] == original
        assert modified["rewrite_confidence"] == 0.85
        assert modified["rewrite_cache_hit"] is False

    async def test_rewritten_cache_hit_propagates_cache_hit_field(self) -> None:
        """Cache-hit rewrite still flows through as a normal rewrite."""
        original = "fix it"
        rewritten = "fix the authentication bug in JWT validation"
        context = _make_context(metadata={"query": original})
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query=original,
                rewritten_query=rewritten,
                was_rewritten=True,
                confidence=0.9,
                llm_provider="minimax",
                latency_ms=2.5,
                context_used=True,
                cache_hit=True,
            ),
        )

        result = await _query_rewriting_handler(context, rewriter)

        assert result.success is True
        assert result.modified_context is not None
        assert result.modified_context["query"] == rewritten
        assert result.modified_context["rewrite_cache_hit"] is True
        assert result.modified_context["rewrite_confidence"] == 0.9

    async def test_metadata_defaults_when_optional_fields_missing(self) -> None:
        """RewriteContext gets empty/None defaults when metadata lacks fields."""
        original = "what did I do yesterday"
        rewritten = "what did I do in the codebase on 2026-09-04"
        context = _make_context(metadata={"query": original})
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query=original,
                rewritten_query=rewritten,
                was_rewritten=True,
                confidence=0.7,
                llm_provider=None,
                latency_ms=50.0,
                context_used=True,
            ),
        )

        await _query_rewriting_handler(context, rewriter)

        call = rewriter.rewrite_query.await_args
        assert call is not None
        rc: RewriteContext = call.kwargs["context"]
        assert rc.recent_conversations == []
        assert rc.project is None
        assert rc.recent_files == []
        # session_context is still the (empty-extras) metadata dict
        assert rc.session_context == {"query": original}


class TestHandlerException:
    """Handler branch: exception in rewrite path → success=True with error."""

    async def test_runtime_error_returns_success_with_error_message(self) -> None:
        """LLM unavailable → search still proceeds (success=True), error captured."""
        context = _make_context(metadata={"query": "what did I learn about async"})
        rewriter = _build_raising_rewriter(RuntimeError("no LLM provider"))

        result = await _query_rewriting_handler(context, rewriter)

        assert isinstance(result, HookResult)
        # Critical contract: rewriting failure does NOT fail the search.
        assert result.success is True
        assert result.error == "no LLM provider"
        assert result.modified_context is None

    async def test_value_error_does_not_fail_search(self) -> None:
        """Any exception type is swallowed and surfaced in ``error`` field."""
        context = _make_context(metadata={"query": "fix this"})
        rewriter = _build_raising_rewriter(ValueError("bad query"))

        result = await _query_rewriting_handler(context, rewriter)

        assert result.success is True
        assert result.error == "bad query"

    async def test_attribute_error_when_metadata_missing(self) -> None:
        """Defensive: if ``metadata.get`` blows up, handler still returns success."""
        # Use a plain MagicMock (no spec=) so we can attach a ``metadata``
        # attribute whose ``.get`` raises. ``MagicMock(spec=HookContext)``
        # strips dataclass fields and refuses to expose ``metadata``.
        context = MagicMock()
        context.metadata = MagicMock()
        context.metadata.get.side_effect = AttributeError("metadata missing")
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query="",
                rewritten_query="",
                was_rewritten=False,
                confidence=0.0,
                llm_provider=None,
                latency_ms=0.0,
                context_used=False,
            ),
        )

        result = await _query_rewriting_handler(context, rewriter)

        assert result.success is True
        assert result.error == "metadata missing"


class TestInitializeHooks:
    """``initialize_query_rewriting_hooks`` registration behavior."""

    async def test_registers_pre_search_query_hook(self) -> None:
        """Hook is registered under PRE_SEARCH_QUERY with priority 100."""
        manager = HooksManager()
        rewriter = AsyncMock(spec=QueryRewriter)

        await initialize_query_rewriting_hooks(manager, rewriter=rewriter)

        listed = manager.list_hooks(HookType.PRE_SEARCH_QUERY)
        assert HookType.PRE_SEARCH_QUERY in listed
        hooks = listed[HookType.PRE_SEARCH_QUERY]
        assert any(h["name"] == "query_rewriting" for h in hooks)
        assert any(h["priority"] == 100 for h in hooks)

    async def test_default_rewriter_is_created_when_none_provided(self) -> None:
        """Passing ``rewriter=None`` does not raise and still registers."""
        manager = HooksManager()

        await initialize_query_rewriting_hooks(manager, rewriter=None)

        listed = manager.list_hooks(HookType.PRE_SEARCH_QUERY)
        assert HookType.PRE_SEARCH_QUERY in listed
        assert any(h["name"] == "query_rewriting" for h in listed[HookType.PRE_SEARCH_QUERY])

    async def test_registered_handler_invokes_rewriter(self) -> None:
        """End-to-end: hook fires via HooksManager and the rewriter is called."""
        manager = HooksManager()
        rewriter = _build_rewriter(
            QueryRewriteResult(
                original_query="fix it",
                rewritten_query="fix the JWT bug in auth",
                was_rewritten=True,
                confidence=0.9,
                llm_provider="minimax",
                latency_ms=5.0,
                context_used=True,
            ),
        )

        await initialize_query_rewriting_hooks(manager, rewriter=rewriter)

        context = _make_context(metadata={"query": "fix it"})
        results = await manager.execute_hooks(HookType.PRE_SEARCH_QUERY, context)

        assert len(results) == 1
        assert results[0].success is True
        rewriter.rewrite_query.assert_awaited_once()
        # modified_context should be merged into context.metadata by the manager
        assert context.metadata.get("query") == "fix the JWT bug in auth"
        assert context.metadata.get("original_query") == "fix it"


@pytest.fixture
def sample_rewriter() -> AsyncMock:
    """Convenience fixture: a working AsyncMock QueryRewriter."""
    return _build_rewriter(
        QueryRewriteResult(
            original_query="what did I learn about async",
            rewritten_query="what did I learn about async/await in error handling",
            was_rewritten=True,
            confidence=0.8,
            llm_provider="minimax",
            latency_ms=10.0,
            context_used=True,
        ),
    )


async def test_handler_uses_real_hook_context_metadata(sample_rewriter: AsyncMock) -> None:
    """Smoke: handler integrates cleanly with the real HookContext dataclass."""
    context = HookContext(
        hook_type=HookType.PRE_SEARCH_QUERY,
        session_id="smoke",
        timestamp=datetime.now(UTC),
        metadata={"query": "what did I learn about async"},
    )

    result = await _query_rewriting_handler(context, sample_rewriter)

    assert result.success is True
    assert result.modified_context is not None
    assert result.modified_context["query"].startswith("what did I learn")
