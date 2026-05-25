"""Unit tests for entity_extraction_tools MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.advanced.entity_extraction_tools import (
    extract_and_store_memory,
    register_extraction_tools,
)


# ---------------------------------------------------------------------------
# Helper: mock FastMCP server collector
# ---------------------------------------------------------------------------


def _make_server_and_tools():
    """Create a mock FastMCP server and collect registered tools."""
    tools: dict = {}

    class MockServer:
        def tool(self):
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

    server = MockServer()
    register_extraction_tools(server)  # type: ignore[arg-type]
    return server, tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_feature_flags_enabled():
    """Enable both feature flags so extraction runs."""
    from session_buddy.config.feature_flags import FeatureFlags

    return patch(
        "session_buddy.mcp.tools.advanced.entity_extraction_tools.get_feature_flags",
        return_value=FeatureFlags(
            enable_llm_entity_extraction=True,
            use_schema_v2=True,
        ),
    )


@pytest.fixture
def mock_feature_flags_disabled():
    """Disable feature flags so extraction is skipped."""
    from session_buddy.config.feature_flags import FeatureFlags

    return patch(
        "session_buddy.mcp.tools.advanced.entity_extraction_tools.get_feature_flags",
        return_value=FeatureFlags(
            enable_llm_entity_extraction=False,
            use_schema_v2=False,
        ),
    )


@pytest.fixture
def mock_extraction_result():
    """Return a canned EntityExtractionResult."""
    from session_buddy.memory.entity_extractor import (
        EntityExtractionResult,
        ExtractedEntity,
        ProcessedMemory,
    )
    return EntityExtractionResult(
        processed_memory=ProcessedMemory(
            category="facts",
            importance_score=0.7,
            summary="Test conversation",
            searchable_content="user input assistant output",
            reasoning="Test reasoning",
            entities=[
                ExtractedEntity(
                    entity_type="technology",
                    entity_value="Python",
                    confidence=0.9,
                ),
            ],
            relationships=[],
            suggested_tier="long_term",
            tags=["test"],
        ),
        entities_count=1,
        relationships_count=0,
        extraction_time_ms=42.0,
        llm_provider="openai",
    )


@pytest.fixture
def mock_persist_result():
    """Return a canned PersistResult."""
    from session_buddy.memory.persistence import PersistResult
    return PersistResult(
        memory_id="mem_abc123",
        entity_ids=["ent_001"],
        relationship_ids=[],
    )


# ---------------------------------------------------------------------------
# extract_and_store_memory unit tests
# ---------------------------------------------------------------------------


class TestExtractAndStoreMemory:
    """Unit tests for the extract_and_store_memory function."""

    @pytest.mark.asyncio
    async def test_returns_skipped_when_extraction_disabled(
        self, mock_feature_flags_disabled
    ) -> None:
        with mock_feature_flags_disabled:
            result = await extract_and_store_memory(
                user_input="Hello",
                ai_output="Hi there",
            )
        assert result["status"] == "skipped"
        assert result["reason"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_skipped_when_schema_v2_disabled(
        self, mock_feature_flags_disabled
    ) -> None:
        """Even if LLM extraction is on but schema_v2 is off, skip."""
        from session_buddy.config.feature_flags import FeatureFlags

        with patch(
            "session_buddy.mcp.tools.advanced.entity_extraction_tools.get_feature_flags",
            return_value=FeatureFlags(
                enable_llm_entity_extraction=True,
                use_schema_v2=False,
            ),
        ):
            result = await extract_and_store_memory(
                user_input="Hello",
                ai_output="Hi there",
            )
        assert result["status"] == "skipped"
        assert result["reason"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_full_extraction_flow(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """Happy-path: flags enabled, extraction succeeds, persistence succeeds."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ):
                    # Mock the adapter used for embedding generation
                    with patch(
                        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                    ) as MockDB:
                        mock_instance = MagicMock()
                        mock_instance._generate_embedding = AsyncMock(
                            return_value=[0.1] * 1536
                        )
                        MockDB.return_value.__aenter__ = AsyncMock(
                            return_value=mock_instance
                        )
                        MockDB.return_value.__aexit__ = AsyncMock()

                        result = await extract_and_store_memory(
                            user_input="I prefer Python",
                            ai_output="Python is great",
                            project="test-project",
                            namespace="default",
                            activity_score=0.8,
                        )

        assert result["status"] == "ok"
        assert result["llm_provider"] == "openai"
        assert result["extraction_time_ms"] == 42.0
        assert result["memory_id"] == "mem_abc123"
        assert result["entity_ids"] == ["ent_001"]
        assert result["relationship_ids"] == []

    @pytest.mark.asyncio
    async def test_embedding_failure_still_succeeds(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """If embedding generation raises, extraction still succeeds with embedding=None."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ):
                    with patch(
                        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                    ) as MockDB:
                        MockDB.return_value.__aenter__ = AsyncMock(
                            side_effect=RuntimeError("Embedding model not available")
                        )
                        MockDB.return_value.__aexit__ = AsyncMock()

                        result = await extract_and_store_memory(
                            user_input="Test",
                            ai_output="Result",
                        )

        assert result["status"] == "ok"
        assert result["memory_id"] == "mem_abc123"

    @pytest.mark.asyncio
    async def test_activity_score_blends_with_importance(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """activity_score should blend with LLM importance (0.7 LLM + 0.3 activity)."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ) as mock_insert:
                    with patch(
                        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                    ) as MockDB:
                        mock_instance = MagicMock()
                        mock_instance._generate_embedding = AsyncMock(
                            return_value=[0.1] * 1536
                        )
                        MockDB.return_value.__aenter__ = AsyncMock(
                            return_value=mock_instance
                        )
                        MockDB.return_value.__aexit__ = AsyncMock()

                        await extract_and_store_memory(
                            user_input="Test",
                            ai_output="Result",
                            activity_score=1.0,  # max activity
                        )

                # pm is the first positional arg to insert_processed_memory
                call_pm = mock_insert.call_args.args[0]
                # activity_score=1.0: clamp(1.0)=1.0, blend = 0.7*0.7 + 0.3*1.0 = 0.79
                assert call_pm.importance_score == pytest.approx(0.79)

    @pytest.mark.asyncio
    async def test_activity_score_out_of_range_is_clamped(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """activity_score outside [0,1] is clamped before blending."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ) as mock_insert:
                    with patch(
                        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                    ) as MockDB:
                        mock_instance = MagicMock()
                        mock_instance._generate_embedding = AsyncMock(
                            return_value=[0.1] * 1536
                        )
                        MockDB.return_value.__aenter__ = AsyncMock(
                            return_value=mock_instance
                        )
                        MockDB.return_value.__aexit__ = AsyncMock()

                        # activity_score = 5.0 should be clamped to 1.0
                        await extract_and_store_memory(
                            user_input="Test",
                            ai_output="Result",
                            activity_score=5.0,
                        )

                call_pm = mock_insert.call_args.args[0]
                # activity_score=5.0: clamp to 1.0, blend = 0.7*0.7 + 0.3*1.0 = 0.79
                assert call_pm.importance_score == pytest.approx(0.79)

    @pytest.mark.asyncio
    async def test_log_memory_access_is_called(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """log_memory_access should be called with extract:{provider}."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ):
                    # log_memory_access is imported inside the function from
                    # session_buddy.memory.persistence; patch it there
                    with patch(
                        "session_buddy.memory.persistence.log_memory_access",
                    ) as mock_log:
                        with patch(
                            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                        ) as MockDB:
                            MockDB.return_value.__aenter__ = AsyncMock()
                            MockDB.return_value.__aexit__ = AsyncMock()

                            await extract_and_store_memory(
                                user_input="Test",
                                ai_output="Result",
                            )

                    mock_log.assert_called_once_with(
                        "mem_abc123", access_type="extract:openai"
                    )

    @pytest.mark.asyncio
    async def test_log_memory_access_error_is_suppressed(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """If log_memory_access raises, it is suppressed and extraction still succeeds."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ):
                    with patch(
                        "session_buddy.memory.persistence.log_memory_access",
                        side_effect=RuntimeError("DB full"),
                    ):
                        with patch(
                            "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                        ) as MockDB:
                            MockDB.return_value.__aenter__ = AsyncMock()
                            MockDB.return_value.__aexit__ = AsyncMock()

                            # Should NOT raise
                            result = await extract_and_store_memory(
                                user_input="Test",
                                ai_output="Result",
                            )

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_project_and_namespace_passed_to_persistence(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """project and namespace flow through to insert_processed_memory."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ) as mock_insert:
                    with patch(
                        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                    ) as MockDB:
                        MockDB.return_value.__aenter__ = AsyncMock()
                        MockDB.return_value.__aexit__ = AsyncMock()

                        await extract_and_store_memory(
                            user_input="Test",
                            ai_output="Result",
                            project="my-project",
                            namespace="custom-ns",
                        )

                kwargs = mock_insert.call_args.kwargs
                assert kwargs["project"] == "my-project"
                assert kwargs["namespace"] == "custom-ns"

    @pytest.mark.asyncio
    async def test_none_activity_score_skips_blending(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """When activity_score is None, importance_score is not modified."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ) as mock_insert:
                    with patch(
                        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                    ) as MockDB:
                        MockDB.return_value.__aenter__ = AsyncMock()
                        MockDB.return_value.__aexit__ = AsyncMock()

                        await extract_and_store_memory(
                            user_input="Test",
                            ai_output="Result",
                            activity_score=None,
                        )

                call_pm = mock_insert.call_args.args[0]
                # Should be original LLM score (0.7), no blending
                assert call_pm.importance_score == 0.7


# ---------------------------------------------------------------------------
# MCP tool registration + contract tests
# ---------------------------------------------------------------------------


class TestExtractAndStoreMemoryTool:
    """Test that the MCP tool wrapper passes parameters correctly."""

    def setup_method(self):
        _, self.tools = _make_server_and_tools()

    def test_tool_is_registered(self) -> None:
        assert "extract_and_store_memory_tool" in self.tools

    @pytest.mark.asyncio
    async def test_tool_returns_skipped_when_disabled(
        self, mock_feature_flags_disabled
    ) -> None:
        with mock_feature_flags_disabled:
            result = await self.tools["extract_and_store_memory_tool"](
                user_input="Hello",
                ai_output="Hi",
            )
        assert result["status"] == "skipped"
        assert result["reason"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_tool_passes_all_parameters(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ):
                    with patch(
                        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                    ) as MockDB:
                        MockDB.return_value.__aenter__ = AsyncMock()
                        MockDB.return_value.__aexit__ = AsyncMock()

                        result = await self.tools["extract_and_store_memory_tool"](
                            user_input="I like Python",
                            ai_output="Python is great",
                            project="test-proj",
                            namespace="test-ns",
                            activity_score=0.5,
                        )

        assert result["status"] == "ok"
        assert result["memory_id"] == "mem_abc123"

    @pytest.mark.asyncio
    async def test_tool_defaults_for_optional_params(
        self,
        mock_feature_flags_enabled,
        mock_extraction_result,
        mock_persist_result,
    ) -> None:
        """Tool should work without project/namespace/activity_score."""
        with mock_feature_flags_enabled:
            with patch(
                "session_buddy.mcp.tools.advanced.entity_extraction_tools.EntityExtractionEngine"
            ) as MockEngine:
                mock_engine = MagicMock()
                mock_engine.extract_entities = AsyncMock(
                    return_value=mock_extraction_result
                )
                MockEngine.return_value = mock_engine

                with patch(
                    "session_buddy.mcp.tools.advanced.entity_extraction_tools.insert_processed_memory",
                    return_value=mock_persist_result,
                ):
                    with patch(
                        "session_buddy.adapters.reflection_adapter_oneiric.ReflectionDatabaseAdapterOneiric"
                    ) as MockDB:
                        MockDB.return_value.__aenter__ = AsyncMock()
                        MockDB.return_value.__aexit__ = AsyncMock()

                        result = await self.tools["extract_and_store_memory_tool"](
                            user_input="Hello",
                            ai_output="Hi",
                        )

        assert result["status"] == "ok"


class TestRegistration:
    """Verify register_extraction_tools wiring."""

    def test_registers_one_tool(self) -> None:
        _, tools = _make_server_and_tools()
        # extract_and_store_memory_tool is the only tool defined
        assert len(tools) == 1
        assert "extract_and_store_memory_tool" in tools

    def test_tool_function_has_docstring(self) -> None:
        _, tools = _make_server_and_tools()
        assert tools["extract_and_store_memory_tool"].__doc__ is not None
        assert "Extract entities" in tools["extract_and_store_memory_tool"].__doc__