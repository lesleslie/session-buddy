"""Tests for session_buddy.mcp.tools.collaboration.knowledge_graph_phase3_tools.

Wave 12 (collaboration/ sweep) — covers the 3 Phase 3 MCP tools and the
shared `` ``execute_kg_operation`` helper for
``knowledge_graph_phase3_tools.py`` (318 lines).

Targets:
- ``_discover_transitive_relationships_impl``: happy path with all 4 stats
  surfaces, kwargs delegation (max_depth, min_confidence, limit)
- ``_extract_pattern_relationships_impl``: entity-not-found path,
  no-observations path, happy path, ``pattern_types`` filter, ``auto_create``
  target creation, per-relation failure swallowed by the
- ``_get_relationship_confidence_stats_impl``: empty results, populated
  results with mixed confidences, `` top 5 relation_types truncation,
  invalid JSON falls to `` none`` confidence
- ``_execute_kg_operation``: RuntimeError envelope, generic exception
  envelope with logger.exception
- ``register_phase3_knowledge_graph_tools``: registers exactly the 3
  expected tools, each registered tool is callable end-to-end

Test approach: monkeypatch the ``KnowledgeGraphDatabaseAdapterOneiric``
class imported inline by ``_execute_kg_operation`` to an async context
manager yielding a ``MagicMock`` adapter with AsyncMock methods. Patch
``session_buddy.di.configure`` so it no-ops.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.collaboration import knowledge_graph_phase3_tools as kg3
from session_buddy.mcp.tools.collaboration.knowledge_graph_phase3_tools import (
    _discover_transitive_relationships_impl,
    _execute_kg_operation,
    _extract_pattern_relationships_impl,
    _get_relationship_confidence_stats_impl,
    register_phase3_knowledge_graph_tools,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


class _FakeKGAdapter:
    """Async context manager yielding the provided adapter mock.

    ``_execute_kg_operation`` does ``async with KnowledgeGraphDatabaseAdapterOneiric()
    as kg`` — the patched ``KnowledgeGraphDatabaseAdapterOneiric`` must therefore
    be callable and return an object implementing ``__aenter__``/``__aexit__``.
    """

    def __init__(self, adapter: MagicMock) -> None:
        self._adapter = adapter

    async def __aenter__(self) -> MagicMock:
        return self._adapter

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _make_kg(**methods: Any) -> MagicMock:
    """Build a stub knowledge graph adapter.

    Each kwarg becomes an AsyncMock on the adapter with that return value.
    Methods not listed as kwargs are still AsyncMocks (callable returning
    AsyncMock by default).
    """
    adapter = MagicMock()
    for name, return_value in methods.items():
        setattr(adapter, name, AsyncMock(return_value=return_value))
    return adapter


def _patch_kg_backend(
    monkeypatch: pytest.MonkeyPatch, adapter: MagicMock | None = None
) -> MagicMock:
    """Patch the inline-imported adapter + configure() to yield ``adapter``.

    ``_execute_kg_operation`` does ``from session_buddy.adapters.
    knowledge_graph_adapter_oneiric import KnowledgeGraphDatabaseAdapterOneiric``
    inside its body. Re-imports read the symbol from the source module's
    namespace each call, so monkeypatching the source attribute is enough.
    """
    adapter = adapter if adapter is not None else _make_kg()

    def factory(*_a: Any, **_kw: Any) -> _FakeKGAdapter:
        return _FakeKGAdapter(adapter)

    monkeypatch.setattr(
        "session_buddy.adapters.knowledge_graph_adapter_oneiric."
        "KnowledgeGraphDatabaseAdapterOneiric",
        factory,
    )
    monkeypatch.setattr("session_buddy.di.configure", lambda *_a: None)
    return adapter


class _FakeMCP:
    """FastMCP stand-in recording registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture(autouse=True)
def _patch_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``_get_logger`` so log calls accept arbitrary kwargs."""
    fake_logger = MagicMock()
    monkeypatch.setattr(kg3, "_get_logger", lambda: fake_logger)


# ---------------------------------------------------------------------------
# _discover_transitive_relationships_impl
# ---------------------------------------------------------------------------


class TestDiscoverTransitiveRelationshipsImpl:
    async def test_happy_path_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _patch_kg_backend(
            monkeypatch,
            _make_kg(
                discover_transitive_relationships={
                    "created": 4,
                    "skipped": 2,
                    "duplicate": 1,
                    "total_examined": 7,
                }
            ),
        )
        out = await _discover_transitive_relationships_impl(
            max_depth=5, min_confidence="high", limit=50
        )
        assert "Created: 4" in out
        assert "Skipped: 2" in out
        assert "Duplicates Avoided: 1" in out
        assert "Total Examined: 7" in out
        assert "Transitive Relationship Discovery" in out
        adapter.discover_transitive_relationships.assert_awaited_once()

    async def test_delegates_kwargs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _patch_kg_backend(
            monkeypatch,
            _make_kg(
                discover_transitive_relationships={
                    "created": 0,
                    "skipped": 0,
                    "duplicate": 0,
                    "total_examined": 0,
                }
            ),
        )
        await _discover_transitive_relationships_impl(
            max_depth=4, min_confidence="low", limit=25
        )
        kwargs = adapter.discover_transitive_relationships.await_args.kwargs
        assert kwargs["max_depth"] == 4
        assert kwargs["min_confidence"] == "low"
        assert kwargs["limit"] == 25


# ---------------------------------------------------------------------------
# _extract_pattern_relationships_impl
# ---------------------------------------------------------------------------


class TestExtractPatternRelationshipsImpl:
    async def test_entity_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _patch_kg_backend(monkeypatch, _make_kg(find_entity_by_name=None))
        out = await _extract_pattern_relationships_impl("missing-entity")
        assert "not found" in out
        assert "missing-entity" in out
        adapter.find_entity_by_name.assert_awaited_once_with("missing-entity")

    async def test_entity_has_no_observations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _patch_kg_backend(
            monkeypatch,
            _make_kg(find_entity_by_name={"id": "e1", "observations": []}),
        )
        out = await _extract_pattern_relationships_impl("e1")
        assert "no observations" in out
        assert "e1" in out

    async def test_happy_path_creates_relations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = MagicMock()
        adapter.find_entity_by_name = AsyncMock(
            side_effect=[
                {"id": "src", "observations": ["uses foo", "calls bar"]},
                {"id": "tgt-foo", "observations": []},
                {"id": "tgt-bar", "observations": []},
            ]
        )
        adapter.create_entity = AsyncMock(return_value={"id": "auto"})
        adapter.create_relation = AsyncMock(return_value={"id": "r"})
        # Sync method — stub a plain function
        adapter._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "relation_type": "uses",
                    "from_name": "src",
                    "to_name": "foo",
                    "confidence": 0.9,
                    "discovery_method": "regex",
                    "evidence": "uses foo",
                },
                {
                    "relation_type": "calls",
                    "from_name": "src",
                    "to_name": "bar",
                    "confidence": 0.7,
                    "discovery_method": "regex",
                    "evidence": "calls bar",
                },
            ]
        )
        _patch_kg_backend(monkeypatch, adapter)

        out = await _extract_pattern_relationships_impl("src")
        assert "Patterns Found: 2" in out
        assert "Relationships Created: 2" in out
        assert "Failed: 0" in out
        assert "src --[uses]--> foo" in out
        assert "src --[calls]--> bar" in out
        assert adapter.create_relation.await_count == 2

    async def test_pattern_types_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = MagicMock()
        adapter.find_entity_by_name = AsyncMock(
            side_effect=[
                {"id": "src", "observations": ["uses foo"]},
                {"id": "tgt-foo", "observations": []},
            ]
        )
        adapter.create_entity = AsyncMock()
        adapter.create_relation = AsyncMock()
        adapter._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "relation_type": "uses",
                    "from_name": "src",
                    "to_name": "foo",
                    "confidence": 0.9,
                    "discovery_method": "r",
                    "evidence": "e",
                },
                {
                    "relation_type": "calls",
                    "from_name": "src",
                    "to_name": "bar",
                    "confidence": 0.9,
                    "discovery_method": "r",
                    "evidence": "e",
                },
            ]
        )
        _patch_kg_backend(monkeypatch, adapter)

        out = await _extract_pattern_relationships_impl(
            "src", pattern_types=["calls"]
        )
        # Only the ``calls`` pattern passes the filter.
        assert "Patterns Found: 1" in out
        assert "Relationships Created: 1" in out
        assert "src --[calls]--> bar" in out
        assert "src --[uses]--> foo" not in out

    async def test_auto_create_creates_missing_targets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = MagicMock()
        # First call: find source. Second call: target NOT found, third call:
        # ditto for the second target. ``create_entity`` returns a fresh id.
        adapter.find_entity_by_name = AsyncMock(
            side_effect=[
                {"id": "src", "observations": ["uses foo"]},
                None,
                None,
            ]
        )
        adapter.create_entity = AsyncMock(
            side_effect=[{"id": "new-foo"}, {"id": "new-bar"}]
        )
        adapter.create_relation = AsyncMock(return_value={"id": "r"})
        adapter._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "relation_type": "uses",
                    "from_name": "src",
                    "to_name": "foo",
                    "confidence": 0.9,
                    "discovery_method": "r",
                    "evidence": "e",
                },
            ]
        )
        _patch_kg_backend(monkeypatch, adapter)

        out = await _extract_pattern_relationships_impl("src", auto_create=True)
        assert "Relationships Created: 1" in out
        assert adapter.create_entity.await_count == 1

    async def test_target_missing_without_auto_create_counts_as_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = MagicMock()
        adapter.find_entity_by_name = AsyncMock(
            side_effect=[
                {"id": "src", "observations": ["uses foo"]},
                None,
            ]
        )
        adapter.create_entity = AsyncMock()
        adapter.create_relation = AsyncMock(return_value={"id": "r"})
        adapter._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "relation_type": "uses",
                    "from_name": "src",
                    "to_name": "foo",
                    "confidence": 0.9,
                    "discovery_method": "r",
                    "evidence": "e",
                },
            ]
        )
        _patch_kg_backend(monkeypatch, adapter)

        out = await _extract_pattern_relationships_impl("src", auto_create=False)
        assert "Relationships Created: 0" in out
        assert "Failed: 1" in out
        adapter.create_entity.assert_not_called()
        adapter.create_relation.assert_not_called()

    async def test_per_relation_exception_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = MagicMock()
        adapter.find_entity_by_name = AsyncMock(
            side_effect=[
                {"id": "src", "observations": ["uses foo"]},
                {"id": "tgt-foo", "observations": []},
                {"id": "tgt-bar", "observations": []},
            ]
        )
        adapter.create_entity = AsyncMock()
        # First create_relation call raises — second succeeds.
        adapter.create_relation = AsyncMock(
            side_effect=[RuntimeError("boom"), {"id": "r2"}]
        )
        adapter._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "relation_type": "uses",
                    "from_name": "src",
                    "to_name": "foo",
                    "confidence": 0.9,
                    "discovery_method": "r",
                    "evidence": "e",
                },
                {
                    "relation_type": "calls",
                    "from_name": "src",
                    "to_name": "bar",
                    "confidence": 0.9,
                    "discovery_method": "r",
                    "evidence": "e",
                },
            ]
        )
        _patch_kg_backend(monkeypatch, adapter)

        out = await _extract_pattern_relationships_impl("src")
        assert "Patterns Found: 2" in out
        assert "Relationships Created: 1" in out
        assert "Failed: 1" in out

    async def test_more_than_ten_patterns_shows_truncation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Build 12 patterns; we should see only the first 10 plus an
        # "and 2 more" tail.
        adapter = MagicMock()
        adapter.find_entity_by_name = AsyncMock(
            side_effect=[
                {"id": "src", "observations": ["x"]},
                *[{"id": f"tgt-{i}", "observations": []} for i in range(12)],
            ]
        )
        adapter.create_entity = AsyncMock()
        adapter.create_relation = AsyncMock(return_value={"id": "r"})
        adapter._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "relation_type": "uses",
                    "from_name": "src",
                    "to_name": f"tgt-{i}",
                    "confidence": 0.9,
                    "discovery_method": "r",
                    "evidence": "e",
                }
                for i in range(12)
            ]
        )
        _patch_kg_backend(monkeypatch, adapter)

        out = await _extract_pattern_relationships_impl("src")
        assert "Patterns Found: 12" in out
        assert "and 2 more" in out


# ---------------------------------------------------------------------------
# _get_relationship_confidence_stats_impl
# ---------------------------------------------------------------------------


class TestGetRelationshipConfidenceStatsImpl:
    def _adapter_with_rows(self, rows: list[tuple[str, str]]) -> MagicMock:
        """Build a mock kg whose ``_get_conn().execute().fetchall()`` returns rows.

        Each row is ``(properties_json, relation_type)``.
        """
        adapter = MagicMock()
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = rows
        adapter._get_conn.return_value = conn
        return adapter

    async def test_empty_results(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_kg_backend(monkeypatch, self._adapter_with_rows([]))
        out = await _get_relationship_confidence_stats_impl()
        assert "Total Relationships: 0" in out
        # Zero division is guarded by ``if total > 0``.
        assert "Low: 0" in out
        assert "Not Scored: 0" in out

    async def test_mixed_confidence_distribution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rows = [
            ('{"confidence": "high"}', "uses"),
            ('{"confidence": "high"}', "uses"),
            ('{"confidence": "medium"}', "calls"),
            ('{"confidence": "low"}', "imports"),
            ('{}', "mentions"),
        ]
        _patch_kg_backend(monkeypatch, self._adapter_with_rows(rows))
        out = await _get_relationship_confidence_stats_impl()
        assert "Total Relationships: 5" in out
        assert "High: 2" in out
        assert "Medium: 1" in out
        assert "Low: 1" in out
        assert "Not Scored: 1" in out

    async def test_invalid_json_falls_to_none_confidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # First row has invalid JSON; second row has no JSON at all (None).
        # Both should land in the `` none`` bucket via the
        # ``json.JSONDecodeError, TypeError, ValueError`` except clause.
        rows = [
            ("not-json-at-all", "broken"),
            (None, "empty"),
        ]
        _patch_kg_backend(monkeypatch, self._adapter_with_rows(rows))
        out = await _get_relationship_confidence_stats_impl()
        assert "Not Scored: 2" in out

    async def test_top_5_relation_types_truncated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Six high-confidence relation_types — only top 5 should appear.
        rows = [
            ('{"confidence": "high"}', f"type-{i}") for i in range(6)
        ]
        _patch_kg_backend(monkeypatch, self._adapter_with_rows(rows))
        out = await _get_relationship_confidence_stats_impl()
        assert "High Confidence Types:" in out
        assert "type-0" in out
        assert "type-5" not in out

    async def test_sorted_by_count_descending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``uses`` should appear above ``calls`` because uses has count 3
        # vs. calls' count 1 — both are high confidence.
        rows = [
            ('{"confidence": "high"}', "uses"),
            ('{"confidence": "high"}', "uses"),
            ('{"confidence": "high"}', "uses"),
            ('{"confidence": "high"}', "calls"),
        ]
        _patch_kg_backend(monkeypatch, self._adapter_with_rows(rows))
        out = await _get_relationship_confidence_stats_impl()
        assert out.index("uses") < out.index("calls")


# ---------------------------------------------------------------------------
# _execute_kg_operation: error envelope
# ---------------------------------------------------------------------------


class TestExecuteKGOperation:
    async def test_runtime_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: Any, **_kw: Any) -> _FakeKGAdapter:
            raise RuntimeError("duckdb missing")

        monkeypatch.setattr(
            "session_buddy.adapters.knowledge_graph_adapter_oneiric."
            "KnowledgeGraphDatabaseAdapterOneiric",
            boom,
        )
        monkeypatch.setattr("session_buddy.di.configure", lambda *_a: None)

        async def op(_adapter: Any) -> str:
            return "never reached"

        out = await _execute_kg_operation("Phase 3 op", op)
        assert "duckdb missing" in out
        assert "Install dependencies" in out

    async def test_generic_exception_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: Any, **_kw: Any) -> _FakeKGAdapter:
            raise OSError("disk gone")

        monkeypatch.setattr(
            "session_buddy.adapters.knowledge_graph_adapter_oneiric."
            "KnowledgeGraphDatabaseAdapterOneiric",
            boom,
        )
        monkeypatch.setattr("session_buddy.di.configure", lambda *_a: None)

        async def op(_adapter: Any) -> str:
            return "never reached"

        out = await _execute_kg_operation("Phase 3 op", op)
        assert "Phase 3 op failed" in out
        assert "disk gone" in out

    async def test_adapter_context_manager_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Happy path: confirm the async context manager protocol is honored.
        adapter = _make_kg(some_op="ok")
        _patch_kg_backend(monkeypatch, adapter)

        async def op(kg: Any) -> str:
            return await kg.some_op()

        out = await _execute_kg_operation("Phase 3 op", op)
        assert out == "ok"


# ---------------------------------------------------------------------------
# register_phase3_knowledge_graph_tools
# ---------------------------------------------------------------------------


class TestRegisterPhase3KnowledgeGraphTools:
    def test_registers_three_tools(self) -> None:
        mcp = _FakeMCP()
        register_phase3_knowledge_graph_tools(mcp)
        expected = {
            "discover_transitive_relationships",
            "extract_pattern_relationships",
            "get_relationship_confidence_stats",
        }
        assert expected == set(mcp.tools)
        assert len(mcp.tools) == 3

    async def test_registered_discover_transitive_is_callable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _patch_kg_backend(
            monkeypatch,
            _make_kg(
                discover_transitive_relationships={
                    "created": 1,
                    "skipped": 0,
                    "duplicate": 0,
                    "total_examined": 1,
                }
            ),
        )
        mcp = _FakeMCP()
        register_phase3_knowledge_graph_tools(mcp)
        out = await mcp.tools["discover_transitive_relationships"]()
        assert "Transitive Relationship Discovery" in out
        adapter.discover_transitive_relationships.assert_awaited()

    async def test_registered_extract_pattern_is_callable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_kg_backend(monkeypatch, _make_kg(find_entity_by_name=None))
        mcp = _FakeMCP()
        register_phase3_knowledge_graph_tools(mcp)
        out = await mcp.tools["extract_pattern_relationships"]("missing")
        assert "not found" in out

    async def test_registered_get_confidence_stats_is_callable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = MagicMock()
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        adapter._get_conn.return_value = conn
        _patch_kg_backend(monkeypatch, adapter)
        mcp = _FakeMCP()
        register_phase3_knowledge_graph_tools(mcp)
        out = await mcp.tools["get_relationship_confidence_stats"]()
        assert "Total Relationships: 0" in out