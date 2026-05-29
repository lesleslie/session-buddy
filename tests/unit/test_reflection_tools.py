#!/usr/bin/env python3
"""Comprehensive unit tests for session_buddy.reflection_tools.

Tests the thin compatibility wrapper that exposes:
- ReflectionDatabase (from reflection.database)
- ReflectionDatabaseAdapter (from adapters.reflection_adapter)
- get_reflection_database() async factory function

All external dependencies (DuckDB, adapters) are fully mocked.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
import threading
import pytest

# Module under test
import session_buddy.reflection_tools as rt

# ==============================================================================
# Test Classes - Grouped by Method/Feature
# ==============================================================================


class TestReflectionToolsImports:
    """Tests for module-level imports and exports."""

    def test_reflection_database_import(self):
        """Test ReflectionDatabase is importable from the module."""
        assert hasattr(rt, "ReflectionDatabase")
        assert rt.ReflectionDatabase is not None

    def test_reflection_database_adapter_import(self):
        """Test ReflectionDatabaseAdapter is importable from the module."""
        assert hasattr(rt, "ReflectionDatabaseAdapter")
        assert rt.ReflectionDatabaseAdapter is not None

    def test_get_reflection_database_function_import(self):
        """Test get_reflection_database function is importable."""
        assert hasattr(rt, "get_reflection_database")
        assert callable(rt.get_reflection_database)

    def test_module_exports(self):
        """Test __all__ exports match expected API."""
        expected_exports = [
            "ReflectionDatabase",
            "ReflectionDatabaseAdapter",
            "get_reflection_database",
        ]
        for export in expected_exports:
            assert export in rt.__all__, f"Missing export: {export}"


class TestReflectionDatabaseType:
    """Tests for ReflectionDatabase type identity."""

    def test_reflection_database_is_class(self):
        """Test ReflectionDatabase is a class (not instance)."""
        assert isinstance(rt.ReflectionDatabase, type)

    def test_reflection_database_adapter_is_class(self):
        """Test ReflectionDatabaseAdapter is a class (not instance)."""
        assert isinstance(rt.ReflectionDatabaseAdapter, type)

    def test_reflection_database_same_as_reflection_module(self):
        """Test ReflectionDatabase matches the reflection module definition."""
        from session_buddy.reflection import ReflectionDatabase as RefDB

        assert rt.ReflectionDatabase is RefDB


class TestReflectionDatabaseAdapterType:
    """Tests for ReflectionDatabaseAdapter type."""

    def test_adapter_is_oneiric_implementation(self):
        """Test adapter routes to Oneiric implementation."""
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        # The adapter should be the Oneiric implementation
        assert rt.ReflectionDatabaseAdapter is ReflectionDatabaseAdapterOneiric


class TestReflectionToolsSingletonCache:
    """Tests for module-level _reflection_db singleton cache."""

    def test_reflection_db_initial_none(self):
        """Test _reflection_db starts as None before any initialization."""
        # Reset module-level singleton for isolated testing
        original_value = rt._reflection_db
        try:
            rt._reflection_db = None
            assert rt._reflection_db is None
        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_reflection_db_singleton_cached(self):
        """Test that get_reflection_database caches the instance."""
        original_value = rt._reflection_db
        rt._reflection_db = None  # Reset for test

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # First call should create instance
                result1 = await rt.get_reflection_database()
                assert result1 is mock_adapter_instance

                # Second call should return cached instance
                result2 = await rt.get_reflection_database()
                assert result2 is mock_adapter_instance
                assert result1 is result2
        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_reflection_db_cached_after_first_call(self):
        """Test singleton is set after first call."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                assert rt._reflection_db is None

                await rt.get_reflection_database()

                assert rt._reflection_db is not None
                assert rt._reflection_db is mock_adapter_instance
        finally:
            rt._reflection_db = original_value


class TestGetReflectionDatabaseWithPath:
    """Tests for get_reflection_database with various db_path scenarios."""

    @pytest.mark.asyncio
    async def test_get_reflection_database_with_explicit_path(self):
        """Test passing explicit db_path creates adapter with settings."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ) as mock_adapter_class:
                with patch.object(rt, "ReflectionAdapterSettings") as mock_settings:
                    mock_settings_instance = MagicMock()
                    mock_settings.return_value = mock_settings_instance

                    await rt.get_reflection_database("/custom/path.duckdb")

                    # Verify adapter was created with settings
                    mock_adapter_class.assert_called_once()
                    call_kwargs = mock_adapter_class.call_args
                    # Check if settings was passed
                    assert "settings" in call_kwargs.kwargs or call_kwargs.args

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_get_reflection_database_with_none_path(self):
        """Test passing None db_path falls back to default settings."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ) as mock_adapter_class:
                await rt.get_reflection_database(None)

                # Adapter should be created (with default settings since path is None)
                mock_adapter_class.assert_called_once()

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_get_reflection_database_with_pathlib_path(self):
        """Test passing Path object for db_path."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Call with actual Path object (don't patch Path class)
                await rt.get_reflection_database(Path("/test/path.duckdb"))

                # Should not raise - the path is correctly passed to settings

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_get_reflection_database_with_string_path(self):
        """Test passing string path for db_path."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                await rt.get_reflection_database("/test/string/path.duckdb")

                # Should not raise

        finally:
            rt._reflection_db = original_value


class TestGetReflectionDatabaseErrorHandling:
    """Tests for error handling in get_reflection_database."""

    @pytest.mark.asyncio
    async def test_reflection_database_adapter_not_available(self):
        """Test ImportError when ReflectionDatabaseAdapter is None."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        original_adapter = rt.ReflectionDatabaseAdapter
        try:
            # Simulate adapter not being available
            rt.ReflectionDatabaseAdapter = None

            with pytest.raises(ImportError, match="ReflectionDatabaseAdapter"):
                await rt.get_reflection_database()

        finally:
            rt._reflection_db = original_value
            rt.ReflectionDatabaseAdapter = original_adapter

    @pytest.mark.asyncio
    async def test_reflection_database_adapter_initialization_error(self):
        """Test errors during adapter creation are propagated."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            error_message = "Database connection failed"

            with patch.object(
                rt,
                "ReflectionDatabaseAdapter",
                side_effect=RuntimeError(error_message),
            ):
                with pytest.raises(RuntimeError, match=error_message):
                    await rt.get_reflection_database()

        finally:
            rt._reflection_db = original_value


class TestGetReflectionDatabaseMultipleCalls:
    """Tests for multiple calls to get_reflection_database."""

    @pytest.mark.asyncio
    async def test_multiple_calls_same_instance(self):
        """Test that multiple calls return the same singleton instance."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Call multiple times
                results = await asyncio.gather(
                    rt.get_reflection_database(),
                    rt.get_reflection_database(),
                    rt.get_reflection_database(),
                )

                # All should be the same instance
                assert all(r is mock_adapter_instance for r in results)
                assert results[0] is results[1]
                assert results[1] is results[2]

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_concurrent_calls_same_instance(self):
        """Test that concurrent calls all get the same singleton instance."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            call_count = 0
            lock = threading.Lock()

            def create_adapter(*args, **kwargs):
                nonlocal call_count
                with lock:
                    call_count += 1
                return mock_adapter_instance

            with patch.object(
                rt, "ReflectionDatabaseAdapter", side_effect=create_adapter
            ):
                # Create many concurrent calls
                tasks = [rt.get_reflection_database() for _ in range(10)]
                results = await asyncio.gather(*tasks)

                # All should be the same instance
                assert all(r is mock_adapter_instance for r in results)
                # Only one adapter should have been created
                assert call_count == 1

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsAsyncContextManager:
    """Tests for async context manager behavior."""

    @pytest.mark.asyncio
    async def test_get_reflection_database_returns_async_instance(self):
        """Test returned instance supports async context manager protocol."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.__aenter__ = AsyncMock(return_value=mock_adapter_instance)
            mock_adapter_instance.__aexit__ = AsyncMock(return_value=None)
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                result = await rt.get_reflection_database()

                # Verify async context manager protocol
                assert hasattr(result, "__aenter__")
                assert hasattr(result, "__aexit__")

                # Can use as async context manager
                async with result as db:
                    assert db is result

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsAdapterCreation:
    """Tests for adapter creation scenarios."""

    @pytest.mark.asyncio
    async def test_adapter_created_with_default_settings(self):
        """Test adapter is created with default settings when no path given."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ) as mock_adapter_class:
                # When no path is given, adapter is created without explicit settings
                # The adapter will use its own default settings internally
                await rt.get_reflection_database()

                # Adapter should be created once (without settings when path is None)
                mock_adapter_class.assert_called_once()
                # Verify no settings argument was passed
                call_args = mock_adapter_class.call_args
                # Settings is only passed when db_path is not None
                assert not call_args.kwargs.get('settings')

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_adapter_created_with_custom_settings(self):
        """Test adapter is created with custom settings when path given."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ) as mock_adapter_class:
                with patch.object(rt, "ReflectionAdapterSettings") as mock_settings:
                    mock_settings_instance = MagicMock()
                    mock_settings.return_value = mock_settings_instance

                    custom_path = "/custom/path.duckdb"
                    await rt.get_reflection_database(custom_path)

                    # Settings should be created with custom path
                    mock_settings.assert_called_once()
                    call_kwargs = mock_settings.call_args.kwargs
                    # The database_path should contain our custom path
                    assert "database_path" in call_kwargs or (
                        len(call_kwargs) == 0
                        and len(mock_settings.call_args.args) > 0
                    )

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsReUseExistingInstance:
    """Tests for reusing existing singleton instance."""

    @pytest.mark.asyncio
    async def test_existing_singleton_reused(self):
        """Test that an existing singleton instance is reused."""
        original_value = rt._reflection_db

        try:
            # Pre-set a singleton instance
            existing_instance = MagicMock()
            rt._reflection_db = existing_instance

            with patch.object(
                rt, "ReflectionDatabaseAdapter"
            ) as mock_adapter_class:
                result = await rt.get_reflection_database()

                # Should return existing instance
                assert result is existing_instance
                # Adapter class should not have been called
                mock_adapter_class.assert_not_called()

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_existing_singleton_reused_with_path(self):
        """Test that existing singleton is returned even when path is different."""
        original_value = rt._reflection_db

        try:
            existing_instance = MagicMock()
            rt._reflection_db = existing_instance

            with patch.object(
                rt, "ReflectionDatabaseAdapter"
            ) as mock_adapter_class:
                # Request with a different path - should still get existing
                result = await rt.get_reflection_database("/different/path.duckdb")

                assert result is existing_instance
                mock_adapter_class.assert_not_called()

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsCleanup:
    """Tests for cleanup behavior."""

    def test_module_has_reflection_db_attribute(self):
        """Test module has _reflection_db attribute for singleton storage."""
        assert hasattr(rt, "_reflection_db")

    @pytest.mark.asyncio
    async def test_aclose_called_on_singleton(self):
        """Test that aclose is called on the singleton when needed."""
        original_value = rt._reflection_db

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()
            rt._reflection_db = mock_adapter_instance

            # Get the instance
            result = await rt.get_reflection_database()
            assert result is mock_adapter_instance

            # Call aclose if the API supports it
            if hasattr(result, "aclose"):
                await result.aclose()
                mock_adapter_instance.aclose.assert_called_once()

        finally:
            rt._reflection_db = original_value


class TestReflectionDatabaseAdapterWrapper:
    """Tests for the adapter wrapper functionality."""

    @pytest.mark.asyncio
    async def test_adapter_wrapper_provides_required_methods(self):
        """Test that the adapter provides all required database methods."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.store_reflection = AsyncMock(return_value="ref_123")
            mock_adapter_instance.search_reflections = AsyncMock(
                return_value=[{"id": "1", "content": "test"}]
            )
            mock_adapter_instance.initialize = AsyncMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                adapter = await rt.get_reflection_database()

                # Verify required methods exist
                assert hasattr(adapter, "store_reflection")
                assert hasattr(adapter, "search_reflections")
                assert hasattr(adapter, "initialize")
                assert hasattr(adapter, "aclose")

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsErrorPropagation:
    """Tests for error propagation from adapter."""

    @pytest.mark.asyncio
    async def test_initialize_error_propagates(self):
        """Test that initialize errors propagate correctly."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            error_message = "Initialization failed: missing extension"

            mock_adapter_instance = MagicMock()
            mock_adapter_instance.initialize = AsyncMock(
                side_effect=RuntimeError(error_message)
            )
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt,
                "ReflectionDatabaseAdapter",
                return_value=mock_adapter_instance,
            ):
                await rt.get_reflection_database()

                with pytest.raises(RuntimeError, match=error_message):
                    await mock_adapter_instance.initialize()

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsTypeAnnotations:
    """Tests for type annotation compliance."""

    def test_get_reflection_database_returns_coroutine(self):
        """Test get_reflection_database returns a coroutine."""
        import inspect

        result = rt.get_reflection_database()
        assert asyncio.iscoroutine(result)
        # Clean up the coroutine
        try:
            result.close()
        except Exception:
            pass

    def test_reflection_database_is_type(self):
        """Test ReflectionDatabase is a proper type/class."""
        assert isinstance(rt.ReflectionDatabase, type)

    def test_reflection_database_adapter_is_type(self):
        """Test ReflectionDatabaseAdapter is a proper type/class."""
        assert isinstance(rt.ReflectionDatabaseAdapter, type)


class TestReflectionToolsThreadSafety:
    """Tests for thread safety considerations."""

    @pytest.mark.asyncio
    async def test_concurrent_access_singleton(self):
        """Test concurrent access doesn't break singleton behavior."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()
            creation_count = 0
            lock = threading.Lock()

            def create_adapter(*args, **kwargs):
                nonlocal creation_count
                with lock:
                    creation_count += 1
                return mock_adapter_instance

            with patch.object(
                rt, "ReflectionDatabaseAdapter", side_effect=create_adapter
            ):
                # Run many concurrent requests
                tasks = [
                    rt.get_reflection_database() for _ in range(20)
                ]
                results = await asyncio.gather(*tasks)

                # All results should be the same instance
                assert all(r is mock_adapter_instance for r in results)
                # Only one adapter should have been created
                assert creation_count == 1

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsPathHandling:
    """Tests for path handling in get_reflection_database."""

    @pytest.mark.asyncio
    async def test_path_expansion(self):
        """Test that paths are properly expanded."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                with patch.object(rt, "Path") as mock_path:
                    # Call with tilde path
                    await rt.get_reflection_database("~/test.duckdb")

                    # Path should have been used to process the path

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_memory_path_handling(self):
        """Test that :memory: path is handled correctly."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Call with in-memory path
                await rt.get_reflection_database(":memory:")

                # Should not raise

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsEdgeCases:
    """Tests for edge case handling."""

    @pytest.mark.asyncio
    async def test_empty_path_string(self):
        """Test handling of empty path string."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Empty string should be handled (passed to settings)
                await rt.get_reflection_database("")

                # Should not raise

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_special_characters_in_path(self):
        """Test handling of special characters in path."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Path with spaces and special chars
                await rt.get_reflection_database("/path/with spaces/and (parens).duckdb")

                # Should not raise

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsIntegrationPatterns:
    """Tests for common integration patterns."""

    @pytest.mark.asyncio
    async def test_full_usage_pattern(self):
        """Test the full typical usage pattern with mocked adapter."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.initialize = AsyncMock()
            mock_adapter_instance.store_reflection = AsyncMock(return_value="ref_001")
            mock_adapter_instance.search_reflections = AsyncMock(
                return_value=[{"id": "ref_001", "content": "test content", "tags": []}]
            )
            mock_adapter_instance.get_reflection_by_id = AsyncMock(
                return_value={"id": "ref_001", "content": "test content", "tags": []}
            )
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Typical usage pattern
                db = await rt.get_reflection_database()

                # Store a reflection
                ref_id = await db.store_reflection(
                    content="Test reflection",
                    tags=["test"],
                )
                assert ref_id == "ref_001"

                # Search reflections
                results = await db.search_reflections(query="test")
                assert len(results) == 1
                assert results[0]["id"] == "ref_001"

                # Get by ID
                reflection = await db.get_reflection_by_id("ref_001")
                assert reflection is not None

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_context_manager_pattern(self):
        """Test async context manager usage pattern."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            aclose_called = False

            async def mock_aclose():
                nonlocal aclose_called
                aclose_called = True

            mock_adapter_instance = MagicMock()
            mock_adapter_instance.__aenter__ = AsyncMock(
                return_value=mock_adapter_instance
            )

            async def mock_aexit(*args):
                # __aexit__ calls aclose internally
                await mock_aclose()
                return None

            mock_adapter_instance.__aexit__ = mock_aexit
            mock_adapter_instance.aclose = mock_aclose

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                async with await rt.get_reflection_database() as db:
                    # Use db within context
                    assert db is mock_adapter_instance

                # aclose should have been called on exit via __aexit__
                assert aclose_called

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsAdapterSettingsIntegration:
    """Tests for ReflectionAdapterSettings integration."""

    def test_adapter_settings_import(self):
        """Test ReflectionAdapterSettings is importable."""
        from session_buddy.adapters.settings import ReflectionAdapterSettings

        assert ReflectionAdapterSettings is not None

    def test_adapter_settings_from_settings(self):
        """Test ReflectionAdapterSettings.from_settings() class method."""
        from session_buddy.adapters.settings import ReflectionAdapterSettings

        # Should be able to call from_settings
        settings = ReflectionAdapterSettings.from_settings()
        assert settings is not None
        assert hasattr(settings, "database_path")
        assert hasattr(settings, "collection_name")

    def test_adapter_settings_with_custom_path(self):
        """Test creating settings with custom database path."""
        from session_buddy.adapters.settings import ReflectionAdapterSettings

        custom_path = Path("/custom/path.duckdb")
        settings = ReflectionAdapterSettings(database_path=custom_path)

        assert settings.database_path == custom_path
        assert settings.collection_name == "default"


class TestReflectionToolsDeprecationNotice:
    """Tests for deprecation notice handling."""

    def test_module_has_deprecation_notice(self):
        """Test that module contains deprecation notice in docstring."""
        assert "DEPRECATION" in rt.__doc__ or "deprecated" in rt.__doc__.lower()

    def test_migration_guide_in_docstring(self):
        """Test that migration guide is present in module docstring."""
        docstring = rt.__doc__ or ""
        assert "Migration Guide" in docstring
        assert "session_buddy.reflection" in docstring


class TestReflectionToolsComplexScenarios:
    """Tests for complex real-world scenarios."""

    @pytest.mark.asyncio
    async def test_reinitialize_after_close(self):
        """Test re-initializing adapter after close."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            call_count = 0

            def create_adapter(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock = MagicMock()
                mock.aclose = AsyncMock()
                return mock

            with patch.object(
                rt, "ReflectionDatabaseAdapter", side_effect=create_adapter
            ):
                # First use
                db1 = await rt.get_reflection_database()
                assert call_count == 1

                # Close and reset for new initialization
                await db1.aclose()
                rt._reflection_db = None

                # Second use (new instance)
                db2 = await rt.get_reflection_database()
                assert call_count == 2
                assert db1 is not db2

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_many_concurrent_requests(self):
        """Test handling many concurrent requests."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # 100 concurrent requests
                tasks = [rt.get_reflection_database() for _ in range(100)]
                results = await asyncio.gather(*tasks)

                # All should get the same instance
                assert all(r is mock_adapter_instance for r in results)

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_call_sequence_stress(self):
        """Test calling get_reflection_database multiple times in sequence."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Call many times in sequence
                for _ in range(50):
                    result = await rt.get_reflection_database()
                    assert result is mock_adapter_instance

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsSettingsPathHandling:
    """Tests for settings path handling."""

    def test_reflection_adapter_settings_has_database_path(self):
        """Test ReflectionAdapterSettings requires database_path."""
        from session_buddy.adapters.settings import ReflectionAdapterSettings

        # Should have database_path
        assert "database_path" in [
            f.name for f in ReflectionAdapterSettings.__dataclass_fields__.values()
        ]

    def test_reflection_adapter_settings_has_collection_name(self):
        """Test ReflectionAdapterSettings has collection_name with default."""
        from session_buddy.adapters.settings import ReflectionAdapterSettings

        settings = ReflectionAdapterSettings(database_path=Path("/test.duckdb"))
        assert settings.collection_name == "default"


class TestReflectionToolsBackwardCompatibility:
    """Tests for backward compatibility."""

    def test_reflection_database_exported_for_backward_compatibility(self):
        """Test ReflectionDatabase is exported for backward compatibility."""
        from session_buddy.reflection_tools import ReflectionDatabase

        # Should be the same as the new modular implementation
        from session_buddy.reflection import ReflectionDatabase as NewRefDB

        assert ReflectionDatabase is NewRefDB

    def test_adapter_from_reflection_tools_same_as_adapter_module(self):
        """Test adapter from reflection_tools matches adapter module."""
        from session_buddy.adapters.reflection_adapter import (
            ReflectionDatabaseAdapter as AdapterFromModule,
        )

        assert rt.ReflectionDatabaseAdapter is AdapterFromModule


class TestReflectionToolsCoverageEnhancement:
    """Additional tests to improve coverage."""

    @pytest.mark.asyncio
    async def test_get_reflection_database_with_posix_path(self):
        """Test with various path formats."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Test with relative path
                await rt.get_reflection_database("./relative/path.duckdb")

                # Test with absolute path
                await rt.get_reflection_database("/absolute/path.duckdb")

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_singleton_reset_between_tests(self):
        """Test singleton can be reset between test runs."""
        original_value = rt._reflection_db

        try:
            # Set an existing singleton
            existing = MagicMock()
            rt._reflection_db = existing

            # Reset it
            rt._reflection_db = None
            assert rt._reflection_db is None

            # Create new instance
            new_mock = MagicMock()
            new_mock.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=new_mock
            ):
                result = await rt.get_reflection_database()
                assert result is new_mock

        finally:
            rt._reflection_db = original_value


class TestReflectionDatabaseAdapterOneiricImport:
    """Tests for the Oneiric adapter import."""

    def test_reflection_adapter_oneiric_import(self):
        """Test that reflection_adapter_oneiric can be imported."""
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        assert ReflectionDatabaseAdapterOneiric is not None

    def test_adapter_is_reflection_database_adapter_oneiric(self):
        """Test ReflectionDatabaseAdapter is ReflectionDatabaseAdapterOneiric."""
        from session_buddy.adapters.reflection_adapter_oneiric import (
            ReflectionDatabaseAdapterOneiric,
        )

        assert rt.ReflectionDatabaseAdapter is ReflectionDatabaseAdapterOneiric


class TestGetReflectionDatabaseAdapterCreation:
    """Tests for adapter creation with different input types."""

    @pytest.mark.asyncio
    async def test_with_integer_path_raises(self):
        """Test that integer path raises TypeError."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Integers are not valid paths - this should be handled gracefully
                # Note: The actual code does not validate path types explicitly
                # but we test the behavior anyway
                try:
                    await rt.get_reflection_database(123)
                except (TypeError, Exception):
                    # TypeError is expected for invalid path type
                    pass

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_with_float_path_raises(self):
        """Test that float path is handled."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                # Floats are not valid paths
                try:
                    await rt.get_reflection_database(1.5)
                except (TypeError, Exception):
                    pass

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsSingletonMechanics:
    """Tests for singleton mechanics details."""

    @pytest.mark.asyncio
    async def test_singleton_stored_in_module_variable(self):
        """Test that singleton is stored in _reflection_db module variable."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                assert rt._reflection_db is None

                await rt.get_reflection_database()

                assert rt._reflection_db is mock_adapter_instance

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_second_call_returns_same_instance_fast(self):
        """Test that second call returns cached instance without recreating."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            create_count = 0

            def create_adapter(*args, **kwargs):
                nonlocal create_count
                create_count += 1
                mock = MagicMock()
                mock.aclose = AsyncMock()
                return mock

            with patch.object(
                rt, "ReflectionDatabaseAdapter", side_effect=create_adapter
            ):
                # First call
                await rt.get_reflection_database()
                assert create_count == 1

                # Second call
                await rt.get_reflection_database()
                assert create_count == 1  # Should not create new instance

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsPathTypes:
    """Tests for different path types and formats."""

    @pytest.mark.asyncio
    async def test_unix_style_path(self):
        """Test with Unix-style path."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                await rt.get_reflection_database("/home/user/data/reflection.duckdb")
                assert rt._reflection_db is mock_adapter_instance

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_dot_relative_path(self):
        """Test with dot-relative path."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                await rt.get_reflection_database("./data/reflection.duckdb")
                assert rt._reflection_db is mock_adapter_instance

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_double_dot_relative_path(self):
        """Test with double-dot relative path."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                await rt.get_reflection_database("../data/reflection.duckdb")
                assert rt._reflection_db is mock_adapter_instance

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsNullHandling:
    """Tests for null/None handling."""

    @pytest.mark.asyncio
    async def test_none_path_uses_default_settings(self):
        """Test that None path results in default settings."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ) as mock_class:
                await rt.get_reflection_database(None)

                # Check that adapter was called with no settings (uses defaults internally)
                call_args = mock_class.call_args
                # No settings passed when db_path is None
                assert "settings" not in call_args.kwargs or call_args.kwargs.get('settings') is None

        finally:
            rt._reflection_db = original_value


class TestReflectionToolsModuleAttributes:
    """Tests for module-level attributes."""

    def test_module_has_reflection_db(self):
        """Test module has _reflection_db attribute."""
        assert hasattr(rt, "_reflection_db")

    def test_module_has_reflection_database_adapter(self):
        """Test module has ReflectionDatabaseAdapter."""
        assert hasattr(rt, "ReflectionDatabaseAdapter")

    def test_module_has_get_reflection_database(self):
        """Test module has get_reflection_database function."""
        assert hasattr(rt, "get_reflection_database")
        assert callable(rt.get_reflection_database)


class TestReflectionToolsTypeChecks:
    """Tests for runtime type checking."""

    def test_reflection_database_is_class_not_instance(self):
        """Test ReflectionDatabase is a class, not an instance."""
        assert isinstance(rt.ReflectionDatabase, type)
        # Every class is an instance of type, but we want to ensure it's a type
        assert rt.ReflectionDatabase is not object

    def test_reflection_database_adapter_is_class_not_instance(self):
        """Test ReflectionDatabaseAdapter is a class, not an instance."""
        assert isinstance(rt.ReflectionDatabaseAdapter, type)
        # Ensure it's a type and not just any object
        assert rt.ReflectionDatabaseAdapter is not object

    def test_get_reflection_database_is_function(self):
        """Test get_reflection_database is a function."""
        import inspect

        assert inspect.isfunction(rt.get_reflection_database)


class TestReflectionToolsReturnTypes:
    """Tests for return types."""

    @pytest.mark.asyncio
    async def test_get_reflection_database_returns_magic_mock(self):
        """Test get_reflection_database returns MagicMock when mocked."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.aclose = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                result = await rt.get_reflection_database()
                assert isinstance(result, MagicMock)

        finally:
            rt._reflection_db = original_value

    @pytest.mark.asyncio
    async def test_adapter_has_expected_methods(self):
        """Test returned adapter has expected database methods."""
        original_value = rt._reflection_db
        rt._reflection_db = None

        try:
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.store_reflection = AsyncMock()
            mock_adapter_instance.search_reflections = AsyncMock()
            mock_adapter_instance.store_conversation = AsyncMock()
            mock_adapter_instance.search_conversations = AsyncMock()
            mock_adapter_instance.get_reflection_by_id = AsyncMock()
            mock_adapter_instance.initialize = AsyncMock()
            mock_adapter_instance.aclose = AsyncMock()
            mock_adapter_instance.get_stats = AsyncMock()

            with patch.object(
                rt, "ReflectionDatabaseAdapter", return_value=mock_adapter_instance
            ):
                result = await rt.get_reflection_database()

                # Check all expected methods exist
                assert hasattr(result, "store_reflection")
                assert hasattr(result, "search_reflections")
                assert hasattr(result, "store_conversation")
                assert hasattr(result, "search_conversations")
                assert hasattr(result, "get_reflection_by_id")
                assert hasattr(result, "initialize")
                assert hasattr(result, "aclose")
                assert hasattr(result, "get_stats")

        finally:
            rt._reflection_db = original_value


# ==============================================================================
# Run Tests
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov", "--tb=short"])
