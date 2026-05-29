#!/usr/bin/env python3
"""Unit tests for knowledge_graph_phase3_tools.py.

Tests cover:
- _discover_transitive_relationships_impl
- _extract_pattern_relationships_impl
- _get_relationship_confidence_stats_impl
- register_phase3_knowledge_graph_tools
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.collaboration import knowledge_graph_phase3_tools as phase3mod


# ============================================================================
# Fixtures
# ============================================================================


class MockLogger:
    """Mock logger that accepts any keyword arguments."""

    def __init__(self):
        self._records: list[logging.LogRecord] = []
        self._last_call_args = None

    def info(self, msg, *args, **kwargs):
        self._records.append(msg)
        self._last_call_args = (args, kwargs)

    def warning(self, msg, *args, **kwargs):
        pass

    def error(self, msg, *args, **kwargs):
        pass

    def exception(self, msg, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def patch_logger():
    """Auto-patch _get_logger for all tests."""
    mock_logger = MockLogger()
    with patch.object(
        phase3mod,
        "_get_logger",
        return_value=mock_logger,
    ):
        yield mock_logger


@pytest.fixture
def mock_kg():
    """Create a mock knowledge graph database adapter."""
    kg = MagicMock()
    kg.discover_transitive_relationships = AsyncMock(return_value={
        "created": 5,
        "skipped": 3,
        "duplicate": 2,
        "total_examined": 10,
    })
    kg.find_entity_by_name = AsyncMock(return_value=None)
    kg._extract_relationships_from_observations = MagicMock(return_value=[])
    kg.create_entity = AsyncMock(return_value={"id": "entity-456", "name": "TestEntity"})
    kg.create_relation = AsyncMock(return_value={"id": "rel-789"})
    kg._get_conn = MagicMock()
    kg.__aenter__ = AsyncMock(return_value=kg)
    kg.__aexit__ = AsyncMock(return_value=None)
    return kg


@pytest.fixture
def mock_server():
    """Create a mock FastMCP server."""
    server = MagicMock()
    server.tool = MagicMock(return_value=MagicMock())
    return server


# Helper function to create async operation wrapper
def make_kg_operation_wrapper(kg, operation_fn):
    """Create an async operation wrapper that calls operation_fn with kg."""
    async def wrapper(op):
        return await op(kg)
    return wrapper


# ============================================================================
# Test _discover_transitive_relationships_impl
# ============================================================================


class TestDiscoverTransitiveRelationshipsImpl:
    """Tests for _discover_transitive_relationships_impl function."""

    @pytest.mark.asyncio
    async def test_returns_success_message_with_results(self, mock_kg):
        """Should return success message with discovered relationship counts."""
        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._discover_transitive_relationships_impl(
                max_depth=3,
                min_confidence="medium",
                limit=100,
            )

        assert "🔗 Transitive Relationship Discovery Results" in result
        assert "✅ Created: 5" in result
        assert "⏭️ Skipped: 3" in result
        assert "🔁 Duplicates Avoided: 2" in result
        assert "📊 Total Examined: 10" in result

        mock_kg.discover_transitive_relationships.assert_called_once_with(
            max_depth=3,
            min_confidence="medium",
            limit=100,
        )

    @pytest.mark.asyncio
    async def test_uses_default_parameters(self, mock_kg):
        """Should use default parameters when not specified."""
        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._discover_transitive_relationships_impl()

        assert "✅ Created: 5" in result
        mock_kg.discover_transitive_relationships.assert_called_once_with(
            max_depth=3,
            min_confidence="medium",
            limit=100,
        )

    @pytest.mark.asyncio
    async def test_respects_custom_max_depth(self, mock_kg):
        """Should pass custom max_depth to the knowledge graph."""
        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            await phase3mod._discover_transitive_relationships_impl(max_depth=5)

        mock_kg.discover_transitive_relationships.assert_called_once_with(
            max_depth=5,
            min_confidence="medium",
            limit=100,
        )

    @pytest.mark.asyncio
    async def test_respects_custom_min_confidence(self, mock_kg):
        """Should pass custom min_confidence to the knowledge graph."""
        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            await phase3mod._discover_transitive_relationships_impl(min_confidence="high")

        mock_kg.discover_transitive_relationships.assert_called_once_with(
            max_depth=3,
            min_confidence="high",
            limit=100,
        )

    @pytest.mark.asyncio
    async def test_respects_custom_limit(self, mock_kg):
        """Should pass custom limit to the knowledge graph."""
        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            await phase3mod._discover_transitive_relationships_impl(limit=50)

        mock_kg.discover_transitive_relationships.assert_called_once_with(
            max_depth=3,
            min_confidence="medium",
            limit=50,
        )

    @pytest.mark.asyncio
    async def test_handles_low_confidence_filter(self, mock_kg):
        """Should pass low confidence filter to the knowledge graph."""
        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            await phase3mod._discover_transitive_relationships_impl(min_confidence="low")

        mock_kg.discover_transitive_relationships.assert_called_once_with(
            max_depth=3,
            min_confidence="low",
            limit=100,
        )


# ============================================================================
# Test _extract_pattern_relationships_impl
# ============================================================================


class TestExtractPatternRelationshipsImpl:
    """Tests for _extract_pattern_relationships_impl function."""

    @pytest.mark.asyncio
    async def test_returns_error_when_entity_not_found(self, mock_kg):
        """Should return error message when entity doesn't exist."""
        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._extract_pattern_relationships_impl(
                entity_name="NonExistentEntity"
            )

        assert "❌ Entity 'NonExistentEntity' not found" in result

    @pytest.mark.asyncio
    async def test_returns_info_when_entity_has_no_observations(self, mock_kg):
        """Should return info message when entity has no observations."""
        mock_kg.find_entity_by_name = AsyncMock(
            return_value={"id": "entity-123", "name": "TestEntity", "observations": []}
        )

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._extract_pattern_relationships_impl(
                entity_name="TestEntity"
            )

        assert "ℹ️ Entity 'TestEntity' has no observations to process" in result

    @pytest.mark.asyncio
    async def test_extracts_patterns_from_entity_observations(self, mock_kg):
        """Should extract patterns from entity observations."""
        mock_kg.find_entity_by_name = AsyncMock(
            return_value={
                "id": "entity-123",
                "name": "TestEntity",
                "observations": ["used_by:ServiceA", "depends_on:DatabaseB"],
            }
        )
        mock_kg._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "from_name": "TestEntity",
                    "to_name": "ServiceA",
                    "relation_type": "used_by",
                    "confidence": 0.8,
                    "discovery_method": "pattern",
                    "evidence": "observed in: used_by:ServiceA",
                },
                {
                    "from_name": "TestEntity",
                    "to_name": "DatabaseB",
                    "relation_type": "depends_on",
                    "confidence": 0.9,
                    "discovery_method": "pattern",
                    "evidence": "observed in: depends_on:DatabaseB",
                },
            ]
        )
        mock_kg.create_relation = AsyncMock(return_value={"id": "rel-new"})

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._extract_pattern_relationships_impl(
                entity_name="TestEntity"
            )

        assert "🔍 Pattern Extraction Results for 'TestEntity'" in result
        assert "📊 Patterns Found: 2" in result
        assert "✅ Relationships Created: 2" in result
        assert "❌ Failed: 0" in result

    @pytest.mark.asyncio
    async def test_filters_by_pattern_types_when_specified(self, mock_kg):
        """Should filter discovered patterns by specified pattern types."""
        mock_kg.find_entity_by_name = AsyncMock(
            return_value={
                "id": "entity-123",
                "name": "TestEntity",
                "observations": ["used_by:ServiceA", "depends_on:DatabaseB"],
            }
        )
        mock_kg._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "from_name": "TestEntity",
                    "to_name": "ServiceA",
                    "relation_type": "used_by",
                    "confidence": 0.8,
                    "discovery_method": "pattern",
                    "evidence": "test",
                },
                {
                    "from_name": "TestEntity",
                    "to_name": "DatabaseB",
                    "relation_type": "depends_on",
                    "confidence": 0.9,
                    "discovery_method": "pattern",
                    "evidence": "test",
                },
            ]
        )

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._extract_pattern_relationships_impl(
                entity_name="TestEntity",
                pattern_types=["used_by"],
            )

        assert "📊 Patterns Found: 1" in result  # Only used_by should remain

    @pytest.mark.asyncio
    async def test_auto_creates_target_entities_when_enabled(self, mock_kg):
        """Should auto-create target entities when auto_create is True and target doesn't exist."""
        # First call finds the entity, second call is for target entity which doesn't exist
        mock_kg.find_entity_by_name = AsyncMock(
            side_effect=[
                {"id": "entity-123", "name": "TestEntity", "observations": ["used_by:ServiceA"]},
                None,  # ServiceA not found initially
                {"id": "entity-456", "name": "ServiceA"},  # After auto-create
            ]
        )
        mock_kg._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "from_name": "TestEntity",
                    "to_name": "ServiceA",
                    "relation_type": "used_by",
                    "confidence": 0.8,
                    "discovery_method": "pattern",
                    "evidence": "test",
                },
            ]
        )
        mock_kg.create_entity = AsyncMock(return_value={"id": "entity-new", "name": "ServiceA"})

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._extract_pattern_relationships_impl(
                entity_name="TestEntity",
                auto_create=True,
            )

        mock_kg.create_entity.assert_called_once_with(
            name="ServiceA",
            entity_type="unknown",
            observations=["Auto-created via pattern extraction"],
        )

    @pytest.mark.asyncio
    async def test_does_not_create_relationship_when_target_missing_and_no_auto_create(self, mock_kg):
        """Should not create relationship when target doesn't exist and auto_create is False."""
        mock_kg.find_entity_by_name = AsyncMock(
            side_effect=[
                {"id": "entity-123", "name": "TestEntity", "observations": ["depends_on:MissingTarget"]},
                None,  # MissingTarget not found
            ]
        )
        mock_kg._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "from_name": "TestEntity",
                    "to_name": "MissingTarget",
                    "relation_type": "depends_on",
                    "confidence": 0.7,
                    "discovery_method": "pattern",
                    "evidence": "test",
                },
            ]
        )

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._extract_pattern_relationships_impl(
                entity_name="TestEntity",
                auto_create=False,
            )

        assert "❌ Failed: 1" in result  # Target not found and not auto-created

    @pytest.mark.asyncio
    async def test_limits_output_to_first_10_patterns(self, mock_kg):
        """Should limit displayed patterns to first 10."""
        mock_kg.find_entity_by_name = AsyncMock(
            return_value={
                "id": "entity-123",
                "name": "TestEntity",
                "observations": ["rel:Target"] * 15,
            }
        )
        mock_kg._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "from_name": "TestEntity",
                    "to_name": f"Target{i}",
                    "relation_type": "relates_to",
                    "confidence": 0.8,
                    "discovery_method": "pattern",
                    "evidence": "test",
                }
                for i in range(15)
            ]
        )
        mock_kg.create_relation = AsyncMock(return_value={"id": "rel-new"})

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._extract_pattern_relationships_impl(
                entity_name="TestEntity"
            )

        assert "... and 5 more" in result  # 15 - 10 = 5

    @pytest.mark.asyncio
    async def test_includes_confidence_in_created_relationships(self, mock_kg):
        """Should include confidence and discovery_method in relationship properties."""
        mock_kg.find_entity_by_name = AsyncMock(
            return_value={
                "id": "entity-123",
                "name": "TestEntity",
                "observations": ["used_by:ServiceA"],
            }
        )
        mock_kg._extract_relationships_from_observations = MagicMock(
            return_value=[
                {
                    "from_name": "TestEntity",
                    "to_name": "ServiceA",
                    "relation_type": "used_by",
                    "confidence": 0.85,
                    "discovery_method": "pattern",
                    "evidence": "observed in text",
                },
            ]
        )
        mock_kg.create_relation = AsyncMock(return_value={"id": "rel-new"})

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            await phase3mod._extract_pattern_relationships_impl(
                entity_name="TestEntity"
            )

        # Verify create_relation was called with properties containing confidence
        call_args = mock_kg.create_relation.call_args
        properties = call_args.kwargs.get("properties", {})
        assert properties["confidence"] == 0.85
        assert properties["discovery_method"] == "pattern"
        assert properties["evidence"] == "observed in text"


# ============================================================================
# Test _get_relationship_confidence_stats_impl
# ============================================================================


class TestGetRelationshipConfidenceStatsImpl:
    """Tests for _get_relationship_confidence_stats_impl function."""

    @pytest.mark.asyncio
    async def test_returns_statistics_message(self, mock_kg):
        """Should return statistics message with confidence distribution."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (json.dumps({"confidence": "high"}), "calls"),
            (json.dumps({"confidence": "high"}), "calls"),
            (json.dumps({"confidence": "medium"}), "uses"),
            (json.dumps({"confidence": "low"}), "depends_on"),
            (json.dumps({"confidence": "none"}), "references"),
        ]
        mock_kg._get_conn.return_value = mock_conn

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._get_relationship_confidence_stats_impl()

        assert "📊 Relationship Confidence Statistics" in result
        assert "📈 Total Relationships: 5" in result

    @pytest.mark.asyncio
    async def test_calculates_percentages_correctly(self, mock_kg):
        """Should calculate confidence percentages correctly."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (json.dumps({"confidence": "high"}), "type_a"),
            (json.dumps({"confidence": "high"}), "type_b"),
            (json.dumps({"confidence": "medium"}), "type_c"),
            (json.dumps({"confidence": "medium"}), "type_d"),
        ]
        mock_kg._get_conn.return_value = mock_conn

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._get_relationship_confidence_stats_impl()

        assert "🔴 Low: 0 (0.0%)" in result
        assert "🟡 Medium: 2 (50.0%)" in result
        assert "🟢 High: 2 (50.0%)" in result

    @pytest.mark.asyncio
    async def test_shows_top_5_relationship_types_per_confidence(self, mock_kg):
        """Should show top 5 relationship types for each confidence level."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (json.dumps({"confidence": "high"}), "calls"),
            (json.dumps({"confidence": "high"}), "calls"),
            (json.dumps({"confidence": "high"}), "uses"),
        ]
        mock_kg._get_conn.return_value = mock_conn

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._get_relationship_confidence_stats_impl()

        assert "🔵 High Confidence Types:" in result
        assert "calls: 2" in result
        assert "uses: 1" in result

    @pytest.mark.asyncio
    async def test_handles_empty_relationships(self, mock_kg):
        """Should handle case with no relationships."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_kg._get_conn.return_value = mock_conn

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._get_relationship_confidence_stats_impl()

        assert "📈 Total Relationships: 0" in result
        assert "🔴 Low: 0 (0.0%)" in result
        assert "⚪ Not Scored: 0 (0.0%)" in result

    @pytest.mark.asyncio
    async def test_handles_missing_properties_json(self, mock_kg):
        """Should handle rows with None or invalid properties JSON."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (None, "calls"),
            ('{"confidence": "high"}', "uses"),
            ("invalid-json", "depends_on"),  # Invalid JSON string
        ]
        mock_kg._get_conn.return_value = mock_conn

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._get_relationship_confidence_stats_impl()

        # Should not raise exception, should handle gracefully
        assert "📊 Relationship Confidence Statistics" in result
        assert "📈 Total Relationships: 3" in result

    @pytest.mark.asyncio
    async def test_handles_json_decode_error(self, mock_kg):
        """Should handle JSON decode errors gracefully."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (json.dumps({"confidence": "high"}), "calls"),
            ("not valid json{", "uses"),
        ]
        mock_kg._get_conn.return_value = mock_conn

        async def mock_execute_kg_operation(name, op):
            return await op(mock_kg)

        with patch.object(
            phase3mod,
            "_execute_kg_operation",
            mock_execute_kg_operation,
        ):
            result = await phase3mod._get_relationship_confidence_stats_impl()

        # Should not raise exception
        assert "📈 Total Relationships: 2" in result


# ============================================================================
# Test register_phase3_knowledge_graph_tools
# ============================================================================


class TestRegisterPhase3KnowledgeGraphTools:
    """Tests for register_phase3_knowledge_graph_tools function."""

    def test_registers_three_tools(self, mock_server):
        """Should register exactly three MCP tools."""
        phase3mod.register_phase3_knowledge_graph_tools(mock_server)

        assert mock_server.tool.call_count == 3

    def test_registers_all_phase3_tools(self, mock_server):
        """Should register all three Phase 3 tools."""
        phase3mod.register_phase3_knowledge_graph_tools(mock_server)

        # Verify tool() was called exactly 3 times (one for each phase 3 tool)
        assert mock_server.tool.call_count == 3
        # Verify all three tools are registered by checking the mock was called 3 times
        calls = mock_server.tool.call_args_list
        assert len(calls) == 3

    def test_tools_have_correct_signatures(self, mock_server):
        """Should register tools with expected parameters."""
        phase3mod.register_phase3_knowledge_graph_tools(mock_server)

        calls = mock_server.tool.call_args_list
        # Build a dict of function_name -> call_args
        func_infos = {}
        for call in calls:
            func = call[0][0] if call[0] else None
            if func and hasattr(func, '__name__'):
                name = func.__name__
                # Get the function's parameters
                import inspect
                sig = inspect.signature(func)
                func_infos[name] = sig

        # Check discover_transitive_relationships signature
        if "discover_transitive_relationships" in func_infos:
            params = list(func_infos["discover_transitive_relationships"].parameters.keys())
            assert "max_depth" in params
            assert "min_confidence" in params
            assert "limit" in params

        # Check extract_pattern_relationships signature
        if "extract_pattern_relationships" in func_infos:
            params = list(func_infos["extract_pattern_relationships"].parameters.keys())
            assert "entity_name" in params
            assert "pattern_types" in params
            assert "auto_create" in params


# ============================================================================
# Test module exports
# ============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_all_exports_are_present(self):
        """Should export all expected functions."""
        assert hasattr(phase3mod, "register_phase3_knowledge_graph_tools")
        assert hasattr(phase3mod, "_discover_transitive_relationships_impl")
        assert hasattr(phase3mod, "_extract_pattern_relationships_impl")
        assert hasattr(phase3mod, "_get_relationship_confidence_stats_impl")

    def test_all_exports_are_callable(self):
        """Should have all exports be callable functions."""
        assert callable(phase3mod.register_phase3_knowledge_graph_tools)
        assert callable(phase3mod._discover_transitive_relationships_impl)
        assert callable(phase3mod._extract_pattern_relationships_impl)
        assert callable(phase3mod._get_relationship_confidence_stats_impl)