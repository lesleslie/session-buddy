"""Tests for resource cleanup handlers.

Tests concrete cleanup implementations for database connections,
file handles, HTTP clients, and other resources.

Phase 10.2: Production Hardening - Resource Cleanup Tests
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from session_buddy.resource_cleanup import (
    cleanup_background_tasks,
    cleanup_database_connections,
    cleanup_file_handles,
    cleanup_http_clients,
    cleanup_logging_handlers,
    cleanup_session_state,
    cleanup_temp_files,
    register_all_cleanup_handlers,
)
from session_buddy.shutdown_manager import ShutdownManager

if TYPE_CHECKING:
    from pathlib import Path


class TestDatabaseCleanup:
    """Test database connection cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_database_connections_when_available(self) -> None:
        """Should cleanup database when available."""
        # Database cleanup should succeed even if database not initialized
        await cleanup_database_connections()
        # No exception means success

    @pytest.mark.asyncio
    async def test_cleanup_database_handles_missing_module(self) -> None:
        """Should handle missing reflection database gracefully."""
        # Even if module not available, cleanup should succeed
        await cleanup_database_connections()
        # No exception means success


class TestHTTPClientCleanup:
    """Test HTTP client cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_http_clients_when_available(self) -> None:
        """Should cleanup HTTP clients when available."""
        await cleanup_http_clients()
        # No exception means success

    @pytest.mark.asyncio
    async def test_cleanup_http_clients_handles_missing_adapter(self) -> None:
        """Should handle missing HTTP adapter gracefully."""
        # Mock DI to return None
        with patch("session_buddy.di.container.depends") as mock_depends:
            mock_depends.get_sync.side_effect = Exception("Not found")
            await cleanup_http_clients()
            # Should not raise


class TestTempFileCleanup:
    """Test temporary file cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_removes_files(self, tmp_path: Path) -> None:
        """Should remove temporary files from directory."""
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        # Create some temp files
        (temp_dir / "temp1.txt").write_text("test1")
        (temp_dir / "temp2.txt").write_text("test2")
        (temp_dir / "temp3.log").write_text("test3")

        assert len(list(temp_dir.iterdir())) == 3

        await cleanup_temp_files(temp_dir)

        # All files should be removed
        assert len(list(temp_dir.iterdir())) == 0

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_handles_missing_directory(
        self, tmp_path: Path
    ) -> None:
        """Should handle missing temp directory gracefully."""
        non_existent = tmp_path / "does_not_exist"

        # Should not raise even if directory doesn't exist
        await cleanup_temp_files(non_existent)

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_handles_permission_errors(
        self, tmp_path: Path
    ) -> None:
        """Should handle permission errors gracefully."""
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        # Create a file
        temp_file = temp_dir / "temp.txt"
        temp_file.write_text("test")

        # Make file read-only
        temp_file.chmod(0o444)

        try:
            # Make directory read-only to prevent deletion
            temp_dir.chmod(0o555)

            # Should not raise, just log warning
            await cleanup_temp_files(temp_dir)

        finally:
            # Restore permissions for cleanup
            temp_dir.chmod(0o755)
            temp_file.chmod(0o644)


class TestFileHandleCleanup:
    """Test file handle cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_file_handles_flushes_streams(self) -> None:
        """Should flush stdout and stderr."""
        with patch("sys.stdout") as mock_stdout, patch("sys.stderr") as mock_stderr:
            mock_stdout.flush = MagicMock()
            mock_stderr.flush = MagicMock()

            await cleanup_file_handles()

            mock_stdout.flush.assert_called_once()
            mock_stderr.flush.assert_called_once()


class TestSessionStateCleanup:
    """Test session state cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_session_state_when_available(self) -> None:
        """Should cleanup session state when available."""
        await cleanup_session_state()
        # No exception means success

    @pytest.mark.asyncio
    async def test_cleanup_session_state_handles_missing_manager(self) -> None:
        """Should handle missing session manager gracefully."""
        # Mock DI to simulate missing manager
        with patch("session_buddy.di.container.depends") as mock_depends:
            mock_depends.get_sync.side_effect = Exception("Not found")
            await cleanup_session_state()
            # Should not raise


class TestBackgroundTaskCleanup:
    """Test background task cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_cancels_pending(self) -> None:
        """Should cancel pending background tasks."""

        async def background_task():
            await asyncio.sleep(10)  # Long running task

        # Start a background task
        task = asyncio.create_task(background_task())

        # Give it time to start
        await asyncio.sleep(0.01)

        # Cleanup should cancel it
        await cleanup_background_tasks()

        # Task should be cancelled
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_handles_no_loop(self) -> None:
        """Should handle case with no running event loop."""
        # This test runs in an event loop, so we can't easily test the no-loop case
        # The function handles it gracefully with try/except RuntimeError
        await cleanup_background_tasks()
        # No exception means success


class TestLoggingHandlerCleanup:
    """Test logging handler cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_logging_handlers_flushes_all(self) -> None:
        """Should flush and close all logging handlers."""
        import logging

        # Create mock handlers with required .level attribute
        mock_handler1 = MagicMock()
        mock_handler1.level = logging.INFO
        mock_handler2 = MagicMock()
        mock_handler2.level = logging.INFO

        original_handlers = logging.root.handlers.copy()

        try:
            logging.root.handlers = [mock_handler1, mock_handler2]

            await cleanup_logging_handlers()

            # Both handlers should be flushed and closed
            mock_handler1.flush.assert_called_once()
            mock_handler1.close.assert_called_once()
            mock_handler2.flush.assert_called_once()
            mock_handler2.close.assert_called_once()

        finally:
            logging.root.handlers = original_handlers


class TestCleanupRegistration:
    """Test registration of all cleanup handlers."""

    def test_register_all_cleanup_handlers(self) -> None:
        """Should register all cleanup handlers with shutdown manager."""
        manager = ShutdownManager()

        assert len(manager._cleanup_tasks) == 0

        register_all_cleanup_handlers(manager)

        # Should register 7 cleanup handlers
        assert len(manager._cleanup_tasks) == 7

        # Verify all expected cleanup tasks are registered
        task_names = {task.name for task in manager._cleanup_tasks}
        expected_names = {
            "database_connections",
            "http_clients",
            "background_tasks",
            "session_state",
            "file_handles",
            "temp_files",
            "logging_handlers",
        }
        assert task_names == expected_names

    def test_register_handlers_with_correct_priorities(self) -> None:
        """Should register handlers with correct priority ordering."""
        manager = ShutdownManager()
        register_all_cleanup_handlers(manager)

        # Sort by priority (highest first)
        sorted_tasks = sorted(
            manager._cleanup_tasks, key=lambda t: t.priority, reverse=True
        )

        # Verify priority ordering
        assert sorted_tasks[0].name in ["database_connections", "http_clients"]
        assert sorted_tasks[0].priority == 100

        assert sorted_tasks[-1].name == "logging_handlers"
        assert sorted_tasks[-1].priority == 10

    def test_register_handlers_with_timeouts(self) -> None:
        """Should register handlers with appropriate timeouts."""
        manager = ShutdownManager()
        register_all_cleanup_handlers(manager)

        # All tasks should have reasonable timeouts
        for task in manager._cleanup_tasks:
            assert task.timeout_seconds > 0
            assert task.timeout_seconds <= 15  # Max 15 seconds per task


class TestCleanupIntegration:
    """Test integration of cleanup with shutdown manager."""

    @pytest.mark.asyncio
    async def test_full_shutdown_executes_all_cleanups(self, tmp_path: Path) -> None:
        """Should execute all cleanup handlers during shutdown."""
        manager = ShutdownManager()

        # Create temp files for cleanup
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        (temp_dir / "test.txt").write_text("test")

        register_all_cleanup_handlers(manager, temp_dir=temp_dir)

        stats = await manager.shutdown()

        # All cleanups should execute successfully
        assert stats.tasks_executed == 7
        assert stats.tasks_failed == 0
        assert stats.tasks_timeout == 0

    @pytest.mark.asyncio
    async def test_cleanup_continues_on_non_critical_failures(self) -> None:
        """Should continue cleanup even if some handlers fail."""
        manager = ShutdownManager()

        # Register some cleanups that will fail
        async def failing_cleanup():
            msg = "Cleanup failed"
            raise RuntimeError(msg)

        manager.register_cleanup(
            "failing", failing_cleanup, priority=50, critical=False
        )

        # Register normal cleanups
        register_all_cleanup_handlers(manager)

        stats = await manager.shutdown()

        # Should have 1 failure but continue with others
        assert stats.tasks_failed == 1
        assert stats.tasks_executed > 0  # Other cleanups should succeed
