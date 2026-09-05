"""Tests for session_buddy.mcp.tools.collaboration.knowledge_graph_tools.

Wave 12 (collaboration/ sweep) — covers the 12 MCP tools, formatters,
entity-extraction helpers, and tool registration for
``knowledge_graph_tools.py`` (948 lines).

Targets:
- ``_check_knowledge_graph_available``: cached probe, ImportError path,
  AttributeError path, duckdb spec absent
- ``_format_entity_result``: with observations (short + truncated),
  without observations
- ``_format_batch_results``: created only, failed only, >10 created,
  >5 failed, mixed
- ``_format_relationship``: outgoing, incoming, both directions
- ``_format_entity_types``: empty dict, populated
- ``_format_relationship_types``: empty dict, populated
- ``_extract_patterns_from_context``: project, library, technology,
  concept; no matches; mixed
- ``create_entity`` flow: happy path with observations/properties,
  empty observations/properties, entity-not-found path
- ``add_observation`` flow: success, entity missing
- ``create_relation`` flow: success, one of entities missing
- ``search_entities`` flow: results, no results
- ``get_entity_relationships`` flow: outgoing/incoming/both directions,
  no relationships
- ``find_path`` flow: paths, no path
- ``get_knowledge_graph_stats`` flow: with connectivity metrics,
  without, with entity/relationship types
- ``extract_entities_from_context`` flow: matched patterns, none,
  auto-create enabled/disabled
- ``batch_create_entities`` flow: all created, partial failure, all fail
- ``generate_embeddings`` flow: results
- ``discover_relationships`` flow: results
- ``analyze_graph_connectivity`` flow: excellent / good / fair / poor,
  recommendations visible
- Error branches: RuntimeError (kg not available) and generic
  exception, via both ``_require_knowledge_graph`` paths
- ``register_knowledge_graph_tools``: registers all 12 tools

Test approach: monkeypatch ``_require_knowledge_graph`` to return an
async context manager yielding a ``MagicMock`` adapter with AsyncMock
methods.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.collaboration import knowledge_graph_tools as kg
from session_buddy.mcp.tools.collaboration.knowledge_graph_tools import (
    ENTITY_PATTERNS,
    _add_observation_impl,
    _add_observation_operation,
    _analyze_graph_connectivity_impl,
    _batch_create_entities_impl,
    _batch_create_entities_operation,
    _check_knowledge_graph_available,
    _create_entity_impl,
    _create_entity_operation,
    _create_relation_impl,
    _create_relation_operation,
    _discover_relationships_impl,
    _execute_kg_operation,
    _extract_entities_from_context_impl,
    _extract_patterns_from_context,
    _find_path_impl,
    _find_path_operation,
    _format_batch_results,
    _format_entity_result,
    _format_entity_types,
    _format_relationship,
    _format_relationship_types,
    _generate_embeddings_impl,
    _get_entity_relationships_impl,
    _get_entity_relationships_operation,
    _get_knowledge_graph_stats_impl,
    _get_knowledge_graph_stats_operation,
    _search_entities_impl,
    _search_entities_operation,
    register_knowledge_graph_tools,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


class _FakeKGContext:
    """Async context manager that yields a provided adapter mock.

    ``_execute_kg_operation`` does ``async with await _require_knowledge_graph()
    as kg``, so the return value of the patched ``_require_knowledge_graph`` must
    be an object whose ``__aenter__`` yields the adapter and ``__aexit__``
    no-ops.
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
    """
    adapter = MagicMock()
    for name, return_value in methods.items():
        setattr(adapter, name, AsyncMock(return_value=return_value))
    return adapter


def _patch_kg(
    monkeypatch: pytest.MonkeyPatch, adapter: MagicMock | None = None
) -> MagicMock:
    """Patch ``_require_knowledge_graph`` to yield ``adapter``.

    Returns the adapter mock for further inspection.
    """
    adapter = adapter if adapter is not None else _make_kg()

    async def fake_require() -> _FakeKGContext:
        return _FakeKGContext(adapter)

    monkeypatch.setattr(kg, "_require_knowledge_graph", fake_require)
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
def _patch_duckdb_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend duckdb is installed by default (override per-test as needed)."""
    fake_spec = MagicMock()
    monkeypatch.setattr(
        "importlib.util.find_spec", lambda _name: fake_spec, raising=False
    )


@pytest.fixture(autouse=True)
def _patch_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``_get_logger`` so log calls accept arbitrary kwargs.

    The production code does ``from session_buddy.utils.error_management
    import _get_logger`` which binds the name in the module namespace, so we
    patch the module-level reference in ``knowledge_graph_tools`` directly.
    """
    fake_logger = MagicMock()
    monkeypatch.setattr(kg, "_get_logger", lambda: fake_logger)


# ---------------------------------------------------------------------------
# _check_knowledge_graph_available
# ---------------------------------------------------------------------------


class TestCheckKnowledgeGraphAvailable:
    def test_returns_true_when_duckdb_spec_present(self) -> None:
        assert _check_knowledge_graph_available() is True

    def test_returns_false_when_no_spec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "importlib.util.find_spec", lambda _name: None, raising=False
        )
        assert _check_knowledge_graph_available() is False

    def test_import_error_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_name: str) -> None:
            raise ImportError("nope")

        monkeypatch.setattr(
            "importlib.util.find_spec", boom, raising=False
        )
        assert _check_knowledge_graph_available() is False


# ---------------------------------------------------------------------------
# _format_entity_result
# ---------------------------------------------------------------------------


class TestFormatEntityResult:
    def test_with_observations_short(self) -> None:
        out = _format_entity_result(
            {
                "name": "foo",
                "entity_type": "project",
                "observations": ["bar baz"],
            }
        )
        joined = "\n".join(out)
        assert "foo" in joined and "project" in joined
        assert "Observations: 1" in joined
        assert "bar baz" in joined

    def test_with_long_observation_truncates(self) -> None:
        long = "x" * 200
        out = _format_entity_result(
            {
                "name": "foo",
                "entity_type": "library",
                "observations": [long],
            }
        )
        joined = "\n".join(out)
        assert "..." in joined
        # Only 80 chars of the original, no full long string
        assert long not in joined

    def test_without_observations(self) -> None:
        out = _format_entity_result(
            {"name": "foo", "entity_type": "project"}
        )
        joined = "\n".join(out)
        assert "Observations" not in joined


# ---------------------------------------------------------------------------
# _format_batch_results
# ---------------------------------------------------------------------------


class TestFormatBatchResults:
    def test_created_only(self) -> None:
        out = _format_batch_results(["alpha", "beta"], [])
        joined = "\n".join(out)
        assert "Successfully Created: 2" in joined
        assert "alpha" in joined and "beta" in joined
        assert "Failed" not in joined

    def test_failed_only(self) -> None:
        out = _format_batch_results([], [("alpha", "boom")])
        joined = "\n".join(out)
        assert "Successfully Created: 0" in joined
        assert "Failed: 1" in joined
        assert "alpha: boom" in joined

    def test_truncates_created_over_ten(self) -> None:
        names = [f"n{i}" for i in range(15)]
        out = _format_batch_results(names, [])
        joined = "\n".join(out)
        assert "and 5 more" in joined

    def test_truncates_failed_over_five(self) -> None:
        failed = [(f"n{i}", "err") for i in range(8)]
        out = _format_batch_results([], failed)
        joined = "\n".join(out)
        assert "and 3 more" in joined

    def test_mixed_created_and_failed(self) -> None:
        out = _format_batch_results(["ok"], [("bad", "err")])
        joined = "\n".join(out)
        assert "Successfully Created: 1" in joined
        assert "Failed: 1" in joined


# ---------------------------------------------------------------------------
# _format_relationship
# ---------------------------------------------------------------------------


class TestFormatRelationship:
    def test_outgoing_arrow(self) -> None:
        rel = {
            "from_entity": "A",
            "to_entity": "B",
            "relation_type": "uses",
        }
        line = _format_relationship(rel, "outgoing", "A")
        assert "A --[uses]--> B" in line

    def test_incoming_arrow(self) -> None:
        rel = {
            "from_entity": "A",
            "to_entity": "B",
            "relation_type": "uses",
        }
        line = _format_relationship(rel, "incoming", "B")
        assert "A <--[uses]-- B" in line

    def test_both_outgoing_when_match(self) -> None:
        rel = {
            "from_entity": "A",
            "to_entity": "B",
            "relation_type": "uses",
        }
        line = _format_relationship(rel, "both", "A")
        assert "-->" in line

    def test_both_incoming_when_no_match(self) -> None:
        rel = {
            "from_entity": "A",
            "to_entity": "B",
            "relation_type": "uses",
        }
        line = _format_relationship(rel, "both", "B")
        assert "<--" in line


# ---------------------------------------------------------------------------
# _format_entity_types / _format_relationship_types
# ---------------------------------------------------------------------------


class TestFormatEntityTypes:
    def test_empty(self) -> None:
        assert _format_entity_types({}) == []

    def test_populated(self) -> None:
        out = _format_entity_types({"project": 3, "library": 5})
        joined = "\n".join(out)
        assert "project: 3" in joined
        assert "library: 5" in joined


class TestFormatRelationshipTypes:
    def test_empty(self) -> None:
        assert _format_relationship_types({}) == []

    def test_populated(self) -> None:
        out = _format_relationship_types({"uses": 7})
        joined = "\n".join(out)
        assert "uses: 7" in joined


# ---------------------------------------------------------------------------
# _extract_patterns_from_context
# ---------------------------------------------------------------------------


class TestExtractPatternsFromContext:
    def test_no_matches(self) -> None:
        assert _extract_patterns_from_context("nothing here") == {}

    def test_project_pattern(self) -> None:
        out = _extract_patterns_from_context("Working on Mahavishnu-repo here")
        assert "project" in out
        assert "Mahavishnu-repo" in out["project"]

    def test_library_pattern(self) -> None:
        out = _extract_patterns_from_context("Using FastMCP and DuckDB now")
        assert "library" in out
        assert "FastMCP" in out["library"]
        assert "DuckDB" in out["library"]

    def test_technology_pattern(self) -> None:
        out = _extract_patterns_from_context("Built with Python and Docker")
        assert "technology" in out
        assert "Python" in out["technology"]

    def test_concept_pattern(self) -> None:
        out = _extract_patterns_from_context(
            "Discussed semantic memory and vector search"
        )
        assert "concept" in out
        assert "semantic memory" in out["concept"]

    def test_case_insensitive(self) -> None:
        # The regex preserves original case in the captured group, but
        # ``re.IGNORECASE`` lets it match mixed-case input.
        out = _extract_patterns_from_context("PYTEST and PYTHON")
        assert "PYTEST" in out["library"]
        assert "PYTHON" in out["technology"]


# ---------------------------------------------------------------------------
# create_entity flow
# ---------------------------------------------------------------------------


class TestCreateEntityOperation:
    async def test_happy_path(self) -> None:
        adapter = _make_kg(
            create_entity={
                "id": "ent-1",
                "name": "foo",
                "entity_type": "project",
            }
        )
        out = await _create_entity_operation(
            adapter, "foo", "project", ["obs1"], {"k": "v"}
        )
        assert "foo" in out
        assert "project" in out
        assert "ent-1" in out
        assert "Observations: 1" in out
        assert "k" in out

    async def test_empty_observations_and_properties(self) -> None:
        adapter = _make_kg(
            create_entity={
                "id": "ent-1",
                "name": "foo",
                "entity_type": "project",
            }
        )
        out = await _create_entity_operation(adapter, "foo", "project", [], {})
        assert "Observations" not in out
        assert "Properties" not in out


class TestCreateEntityImpl:
    async def test_delegates_to_kg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(
            monkeypatch,
            _make_kg(
                create_entity={
                    "id": "x",
                    "name": "foo",
                    "entity_type": "project",
                }
            ),
        )
        out = await _create_entity_impl("foo", "project", ["obs"], {"k": "v"})
        kwargs = adapter.create_entity.await_args.kwargs
        assert kwargs["name"] == "foo"
        assert kwargs["entity_type"] == "project"
        assert kwargs["observations"] == ["obs"]
        assert kwargs["properties"] == {"k": "v"}
        assert "foo" in out

    async def test_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def boom() -> _FakeKGContext:
            raise RuntimeError("kg down")

        monkeypatch.setattr(kg, "_require_knowledge_graph", boom)
        out = await _create_entity_impl("foo", "project")
        assert "kg down" in out
        assert "Install dependencies" in out

    async def test_generic_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> _FakeKGContext:
            raise ValueError("db crashed")

        monkeypatch.setattr(kg, "_require_knowledge_graph", boom)
        out = await _create_entity_impl("foo", "project")
        assert "Create entity failed" in out
        assert "db crashed" in out


# ---------------------------------------------------------------------------
# add_observation flow
# ---------------------------------------------------------------------------


class TestAddObservationOperation:
    async def test_success(self) -> None:
        adapter = _make_kg(add_observation=True)
        out = await _add_observation_operation(adapter, "foo", "hello")
        assert "foo" in out
        assert "hello" in out

    async def test_entity_not_found(self) -> None:
        adapter = _make_kg(add_observation=False)
        out = await _add_observation_operation(adapter, "missing", "obs")
        assert "not found" in out
        assert "missing" in out


class TestAddObservationImpl:
    async def test_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(monkeypatch, _make_kg(add_observation=True))
        out = await _add_observation_impl("foo", "obs")
        assert "Observation added" in out
        adapter.add_observation.assert_awaited_once_with("foo", "obs")


# ---------------------------------------------------------------------------
# create_relation flow
# ---------------------------------------------------------------------------


class TestCreateRelationOperation:
    async def test_success(self) -> None:
        adapter = _make_kg(
            create_relation={"id": "rel-1", "from_entity": "A", "to_entity": "B"}
        )
        out = await _create_relation_operation(
            adapter, "A", "B", "uses", {"k": "v"}
        )
        assert "A --[uses]--> B" in out
        assert "rel-1" in out
        assert "k" in out

    async def test_relation_returns_empty(self) -> None:
        adapter = _make_kg(create_relation=None)
        out = await _create_relation_operation(adapter, "A", "B", "uses", {})
        assert "not found" in out


class TestCreateRelationImpl:
    async def test_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(
            monkeypatch, _make_kg(create_relation={"id": "r", "from_entity": "A", "to_entity": "B"})
        )
        out = await _create_relation_impl("A", "B", "uses")
        assert "Relationship created" in out
        kwargs = adapter.create_relation.await_args.kwargs
        assert kwargs["from_entity"] == "A"
        assert kwargs["to_entity"] == "B"
        assert kwargs["relation_type"] == "uses"


# ---------------------------------------------------------------------------
# search_entities flow
# ---------------------------------------------------------------------------


class TestSearchEntitiesOperation:
    async def test_no_results(self) -> None:
        adapter = _make_kg(search_entities=[])
        out = await _search_entities_operation(adapter, "missing", None, 10)
        assert "No entities found" in out
        assert "missing" in out

    async def test_with_results(self) -> None:
        adapter = _make_kg(
            search_entities=[
                {
                    "name": "foo",
                    "entity_type": "project",
                    "observations": ["bar"],
                }
            ]
        )
        out = await _search_entities_operation(adapter, "foo", "project", 5)
        assert "Found 1" in out
        assert "foo" in out
        assert "project" in out


class TestSearchEntitiesImpl:
    async def test_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(
            monkeypatch,
            _make_kg(
                search_entities=[
                    {"name": "foo", "entity_type": "project", "observations": []}
                ]
            ),
        )
        out = await _search_entities_impl("foo", "project", 5)
        kwargs = adapter.search_entities.await_args.kwargs
        assert kwargs["query"] == "foo"
        assert kwargs["entity_type"] == "project"
        assert kwargs["limit"] == 5
        assert "Found 1" in out


# ---------------------------------------------------------------------------
# get_entity_relationships flow
# ---------------------------------------------------------------------------


class TestGetEntityRelationshipsOperation:
    async def test_no_relationships(self) -> None:
        adapter = _make_kg(get_relationships=[])
        out = await _get_entity_relationships_operation(
            adapter, "foo", None, "both"
        )
        assert "No relationships" in out
        assert "foo" in out

    async def test_with_relationships(self) -> None:
        adapter = _make_kg(
            get_relationships=[
                {
                    "from_entity": "foo",
                    "to_entity": "bar",
                    "relation_type": "uses",
                }
            ]
        )
        out = await _get_entity_relationships_operation(
            adapter, "foo", "uses", "outgoing"
        )
        assert "Found 1" in out
        assert "foo --[uses]--> bar" in out


class TestGetEntityRelationshipsImpl:
    async def test_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(
            monkeypatch,
            _make_kg(
                get_relationships=[
                    {
                        "from_entity": "foo",
                        "to_entity": "bar",
                        "relation_type": "uses",
                    }
                ]
            ),
        )
        out = await _get_entity_relationships_impl("foo", "uses", "incoming")
        kwargs = adapter.get_relationships.await_args.kwargs
        assert kwargs["entity_name"] == "foo"
        assert kwargs["relation_type"] == "uses"
        assert kwargs["direction"] == "incoming"
        assert "Found 1" in out


# ---------------------------------------------------------------------------
# find_path flow
# ---------------------------------------------------------------------------


class TestFindPathOperation:
    async def test_no_path(self) -> None:
        adapter = _make_kg(find_path=[])
        out = await _find_path_operation(adapter, "A", "B", 5)
        assert "No path found" in out
        assert "A" in out and "B" in out

    async def test_paths(self) -> None:
        adapter = _make_kg(
            find_path=[
                {
                    "from_entity": "A",
                    "to_entity": "B",
                    "path_length": 2,
                }
            ]
        )
        out = await _find_path_operation(adapter, "A", "B", 5)
        assert "Found 1 path" in out
        assert "Path length: 2" in out


class TestFindPathImpl:
    async def test_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(
            monkeypatch,
            _make_kg(
                find_path=[
                    {
                        "from_entity": "A",
                        "to_entity": "B",
                        "path_length": 1,
                    }
                ]
            ),
        )
        out = await _find_path_impl("A", "B", 3)
        kwargs = adapter.find_path.await_args.kwargs
        assert kwargs["from_entity"] == "A"
        assert kwargs["to_entity"] == "B"
        assert kwargs["max_depth"] == 3
        assert "Found 1 path" in out


# ---------------------------------------------------------------------------
# get_knowledge_graph_stats flow
# ---------------------------------------------------------------------------


class TestGetKnowledgeGraphStatsOperation:
    async def test_with_connectivity(self) -> None:
        adapter = _make_kg(
            get_stats={
                "total_entities": 10,
                "total_relationships": 5,
                "connectivity_ratio": 0.5,
                "avg_degree": 1.0,
                "isolated_entities": 2,
                "embedding_coverage": 0.8,
                "entity_types": {"project": 6, "library": 4},
                "relationship_types": {"uses": 5},
                "database_path": "/tmp/kg.db",
            }
        )
        out = await _get_knowledge_graph_stats_operation(adapter)
        assert "Total Entities: 10" in out
        assert "Total Relationships: 5" in out
        assert "Connectivity Ratio: 0.500" in out
        assert "Embedding Coverage" in out
        assert "project: 6" in out
        assert "uses: 5" in out
        assert "/tmp/kg.db" in out

    async def test_without_connectivity(self) -> None:
        adapter = _make_kg(
            get_stats={
                "total_entities": 0,
                "total_relationships": 0,
                "entity_types": {},
                "relationship_types": {},
            }
        )
        out = await _get_knowledge_graph_stats_operation(adapter)
        assert "Connectivity Ratio" not in out
        assert "Total Entities: 0" in out


class TestGetKnowledgeGraphStatsImpl:
    async def test_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_kg(
            monkeypatch,
            _make_kg(
                get_stats={
                    "total_entities": 1,
                    "total_relationships": 0,
                    "entity_types": {},
                    "relationship_types": {},
                }
            ),
        )
        out = await _get_knowledge_graph_stats_impl()
        assert "Total Entities: 1" in out


# ---------------------------------------------------------------------------
# extract_entities_from_context flow
# ---------------------------------------------------------------------------


class TestExtractEntitiesFromContextImpl:
    async def test_no_matches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_kg(monkeypatch, _make_kg())
        out = await _extract_entities_from_context_impl("nothing here")
        assert "No entities detected" in out

    async def test_matches_without_auto_create(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_kg(monkeypatch, _make_kg())
        out = await _extract_entities_from_context_impl(
            "Using FastMCP and Python", auto_create=False
        )
        assert "Extracted Entities" in out
        assert "FastMCP" in out
        assert "Total Extracted" in out
        assert "Auto-created" not in out

    async def test_matches_with_auto_create(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _patch_kg(
            monkeypatch,
            _make_kg(
                find_entity_by_name=None,
                create_entity={"id": "x", "name": "foo"},
            ),
        )
        out = await _extract_entities_from_context_impl(
            "Project mahavishnu-repo here", auto_create=True
        )
        assert "Auto-created: 1" in out


# ---------------------------------------------------------------------------
# batch_create_entities flow
# ---------------------------------------------------------------------------


class TestBatchCreateEntitiesOperation:
    async def test_all_succeed(self) -> None:
        adapter = _make_kg()
        adapter.create_entity = AsyncMock(
            side_effect=[
                {"id": "x", "name": "a"},
                {"id": "y", "name": "b"},
            ]
        )
        out = await _batch_create_entities_operation(
            adapter,
            [
                {"name": "a", "entity_type": "project"},
                {"name": "b", "entity_type": "project"},
            ],
        )
        assert "Successfully Created: 2" in out
        assert "a" in out and "b" in out
        assert "Failed" not in out

    async def test_partial_failure(self) -> None:
        adapter = _make_kg()
        adapter.create_entity = AsyncMock(
            side_effect=[
                {"id": "x", "name": "ok"},
                RuntimeError("constraint violation"),
            ]
        )
        out = await _batch_create_entities_operation(
            adapter,
            [
                {"name": "ok", "entity_type": "project"},
                {"name": "bad", "entity_type": "project"},
            ],
        )
        assert "Successfully Created: 1" in out
        assert "Failed: 1" in out
        assert "bad: constraint violation" in out


class TestBatchCreateEntitiesImpl:
    async def test_delegate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(monkeypatch, _make_kg())
        adapter.create_entity = AsyncMock(
            return_value={"id": "x", "name": "a"}
        )
        out = await _batch_create_entities_impl(
            [{"name": "a", "entity_type": "project"}]
        )
        assert "Successfully Created: 1" in out


# ---------------------------------------------------------------------------
# generate_embeddings / discover_relationships
# ---------------------------------------------------------------------------


class TestGenerateEmbeddingsImpl:
    async def test_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_kg(
            monkeypatch,
            _make_kg(
                generate_embeddings_for_entities={
                    "generated": 5,
                    "failed": 1,
                    "total_processed": 6,
                }
            ),
        )
        out = await _generate_embeddings_impl("project", 10, False)
        assert "Generated: 5" in out
        assert "Failed: 1" in out
        assert "Total Processed: 6" in out

    async def test_delegate_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(
            monkeypatch,
            _make_kg(
                generate_embeddings_for_entities={
                    "generated": 0,
                    "failed": 0,
                    "total_processed": 0,
                }
            ),
        )
        await _generate_embeddings_impl("library", 25, True)
        kwargs = adapter.generate_embeddings_for_entities.await_args.kwargs
        assert kwargs["entity_type"] == "library"
        assert kwargs["batch_size"] == 25
        assert kwargs["overwrite"] is True


class TestDiscoverRelationshipsImpl:
    async def test_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_kg(
            monkeypatch,
            _make_kg(
                batch_discover_relationships={
                    "entities_processed": 10,
                    "relationships_created": 7,
                    "avg_relationships_per_entity": 0.7,
                }
            ),
        )
        out = await _discover_relationships_impl("project", 0.8, 50, 5)
        assert "Entities Processed: 10" in out
        assert "Relationships Created: 7" in out

    async def test_delegate_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _patch_kg(
            monkeypatch,
            _make_kg(
                batch_discover_relationships={
                    "entities_processed": 0,
                    "relationships_created": 0,
                    "avg_relationships_per_entity": 0.0,
                }
            ),
        )
        await _discover_relationships_impl(None, 0.5, 200, 20)
        kwargs = adapter.batch_discover_relationships.await_args.kwargs
        assert kwargs["entity_type"] is None
        assert kwargs["threshold"] == 0.5
        assert kwargs["limit"] == 200
        assert kwargs["batch_size"] == 20


# ---------------------------------------------------------------------------
# analyze_graph_connectivity flow
# ---------------------------------------------------------------------------


class TestAnalyzeGraphConnectivityImpl:
    @pytest.mark.parametrize(
        "ratio,expected",
        [
            (0.6, "Excellent"),
            (0.3, "Good"),
            (0.15, "Fair"),
            (0.05, "Poor"),
        ],
    )
    async def test_health_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
        ratio: float,
        expected: str,
    ) -> None:
        _patch_kg(
            monkeypatch,
            _make_kg(
                get_stats={
                    "total_entities": 100,
                    "isolated_entities": 5,
                    "connectivity_ratio": ratio,
                    "avg_degree": 1.0,
                    "embedding_coverage": 0.5,
                    "entities_with_embeddings": 50,
                }
            ),
        )
        out = await _analyze_graph_connectivity_impl()
        assert expected in out
        assert "Health Status" in out

    async def test_recommendations_for_poor_connectivity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_kg(
            monkeypatch,
            _make_kg(
                get_stats={
                    "total_entities": 10,
                    "isolated_entities": 8,
                    "connectivity_ratio": 0.05,
                    "avg_degree": 0.1,
                    "embedding_coverage": 0.5,
                    "entities_with_embeddings": 5,
                }
            ),
        )
        out = await _analyze_graph_connectivity_impl()
        assert "Recommendations" in out
        assert "generate_embeddings" in out
        assert "discover_relationships" in out

    async def test_recommendations_for_low_embeddings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_kg(
            monkeypatch,
            _make_kg(
                get_stats={
                    "total_entities": 100,
                    "isolated_entities": 5,
                    "connectivity_ratio": 0.5,
                    "avg_degree": 2.0,
                    "embedding_coverage": 0.5,
                    "entities_with_embeddings": 50,
                }
            ),
        )
        out = await _analyze_graph_connectivity_impl()
        assert "Recommendations" in out


# ---------------------------------------------------------------------------
# _execute_kg_operation: error envelope
# ---------------------------------------------------------------------------


class TestExecuteKGOperation:
    async def test_runtime_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> _FakeKGContext:
            raise RuntimeError("not configured")

        monkeypatch.setattr(kg, "_require_knowledge_graph", boom)

        async def op(_adapter: Any) -> str:
            return "never reached"

        out = await _execute_kg_operation("My op", op)
        assert "not configured" in out
        assert "Install dependencies" in out

    async def test_generic_exception_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom() -> _FakeKGContext:
            raise OSError("disk gone")

        monkeypatch.setattr(kg, "_require_knowledge_graph", boom)

        async def op(_adapter: Any) -> str:
            return "never reached"

        out = await _execute_kg_operation("My op", op)
        assert "My op failed" in out
        assert "disk gone" in out


# ---------------------------------------------------------------------------
# register_knowledge_graph_tools
# ---------------------------------------------------------------------------


class TestRegisterKnowledgeGraphTools:
    def test_registers_all_twelve_tools(self) -> None:
        mcp = _FakeMCP()
        register_knowledge_graph_tools(mcp)
        expected = {
            "create_entity",
            "add_observation",
            "create_relation",
            "search_entities",
            "get_entity_relationships",
            "find_path",
            "get_knowledge_graph_stats",
            "extract_entities_from_context",
            "batch_create_entities",
            "generate_embeddings",
            "discover_relationships",
            "analyze_graph_connectivity",
        }
        assert expected.issubset(set(mcp.tools))
        assert len(mcp.tools) == 12

    async def test_registered_create_entity_is_callable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _patch_kg(
            monkeypatch,
            _make_kg(
                create_entity={
                    "id": "x",
                    "name": "foo",
                    "entity_type": "project",
                }
            ),
        )
        mcp = _FakeMCP()
        register_knowledge_graph_tools(mcp)
        out = await mcp.tools["create_entity"]("foo", "project")
        assert "foo" in out
        adapter.create_entity.assert_awaited()