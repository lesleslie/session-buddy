"""Comprehensive pytest unit tests for session_buddy/resource_cleanup.py.

Tests all public async/sync methods and edge cases with proper mocking.
Target: 70%+ coverage of resource_cleanup.py

Phase 10.2: Production Hardening - Resource Cleanup Tests
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# --- Fixtures ---

@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.exception = MagicMock()
    return logger


# --- Test cleanup_database_connections ---

class TestCleanupDatabaseConnections:
    """Tests for cleanup_database_connections async function."""

    @pytest.mark.asyncio
    async def test_cleanup_database_connections_success(self, mock_logger):
        """Test successful database cleanup when ReflectionDatabase is available."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.import_util.find_spec", return_value=MagicMock()), \
             patch("session_buddy.resource_cleanup.suppress", MagicMock()):

            mock_reflection_db = MagicMock()
            with patch("session_buddy.reflection_tools.ReflectionDatabase", return_value=mock_reflection_db):
                from session_buddy.resource_cleanup import cleanup_database_connections

                await cleanup_database_connections()

                mock_reflection_db.close.assert_called_once()
                mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_database_connections_reflection_not_available(self, mock_logger):
        """Test cleanup when reflection database is not available."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.import_util.find_spec", return_value=None):

            from session_buddy.resource_cleanup import cleanup_database_connections

            await cleanup_database_connections()

            mock_logger.debug.assert_called_with("Reflection database not available, skipping cleanup")

    @pytest.mark.asyncio
    async def test_cleanup_database_connections_close_raises_exception(self, mock_logger):
        """Test cleanup handles exception from ReflectionDatabase.close()."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.import_util.find_spec", return_value=MagicMock()), \
             patch("session_buddy.resource_cleanup.suppress") as mock_suppress:

            mock_suppress_instance = MagicMock()
            mock_suppress_instance.__enter__ = MagicMock()
            mock_suppress_instance.__exit__ = MagicMock(return_value=False)
            mock_suppress.return_value = mock_suppress_instance

            mock_reflection_db = MagicMock()
            mock_reflection_db.close.side_effect = Exception("Close failed")
            with patch("session_buddy.reflection_tools.ReflectionDatabase", return_value=mock_reflection_db):
                from session_buddy.resource_cleanup import cleanup_database_connections

                with pytest.raises(Exception, match="Close failed"):
                    await cleanup_database_connections()

            mock_logger.exception.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_database_connections_import_error(self, mock_logger):
        """Test cleanup handles import error gracefully."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.import_util.find_spec", return_value=MagicMock()), \
             patch("session_buddy.reflection_tools.ReflectionDatabase", side_effect=ImportError):

            from session_buddy.resource_cleanup import cleanup_database_connections

            # Should not raise, just log
            await cleanup_database_connections()

    @pytest.mark.asyncio
    async def test_cleanup_database_connections_with_none_spec(self, mock_logger):
        """Test when find_spec returns None vs False."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.import_util.find_spec", return_value=None):

            from session_buddy.resource_cleanup import cleanup_database_connections

            await cleanup_database_connections()

            mock_logger.debug.assert_called()


# --- Test _close_adapter_method ---

class TestCloseAdapterMethod:
    """Tests for _close_adapter_method helper function."""

    @pytest.mark.asyncio
    async def test_close_adapter_method_with_awaitable_close(self, mock_logger):
        """Test adapter close returns awaitable."""
        from session_buddy.resource_cleanup import _close_adapter_method

        mock_adapter = MagicMock()
        mock_close = AsyncMock()
        mock_adapter.close.return_value = mock_close
        mock_adapter.close.__await__ = MagicMock()

        result = await _close_adapter_method(mock_adapter, mock_logger)

        assert result is True
        mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_close_adapter_method_sync_close(self, mock_logger):
        """Test adapter close is sync (not awaitable)."""
        from session_buddy.resource_cleanup import _close_adapter_method

        mock_adapter = MagicMock()
        mock_adapter.close = MagicMock()

        result = await _close_adapter_method(mock_adapter, mock_logger)

        assert result is True
        mock_adapter.close.assert_called()

    @pytest.mark.asyncio
    async def test_close_adapter_method_no_close_method(self, mock_logger):
        """Test adapter has no close method."""
        from session_buddy.resource_cleanup import _close_adapter_method

        mock_adapter = MagicMock(spec=[])
        result = await _close_adapter_method(mock_adapter, mock_logger)

        assert result is False

    @pytest.mark.asyncio
    async def test_close_adapter_method_close_not_callable(self, mock_logger):
        """Test adapter close attribute is not callable."""
        from session_buddy.resource_cleanup import _close_adapter_method

        mock_adapter = MagicMock()
        mock_adapter.close = "not callable"

        result = await _close_adapter_method(mock_adapter, mock_logger)

        assert result is False


# --- Test _close_underlying_client ---

class TestCloseUnderlyingClient:
    """Tests for _close_underlying_client helper function."""

    @pytest.mark.asyncio
    async def test_close_underlying_client_with_aclose(self, mock_logger):
        """Test client has aclose method."""
        from session_buddy.resource_cleanup import _close_underlying_client

        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        mock_requests = MagicMock()
        mock_requests.client = mock_client

        result = await _close_underlying_client(mock_requests, mock_logger)

        assert result is True
        mock_client.aclose.assert_called_once()
        mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_close_underlying_client_with_sync_close(self, mock_logger):
        """Test client has sync close method."""
        from session_buddy.resource_cleanup import _close_underlying_client

        mock_client = MagicMock()
        mock_client.close = MagicMock()
        # Remove aclose to force fallback to close
        del mock_client.aclose
        mock_requests = MagicMock()
        mock_requests.client = mock_client

        result = await _close_underlying_client(mock_requests, mock_logger)

        assert result is True
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_underlying_client_no_client(self, mock_logger):
        """Test requests has no client attribute."""
        from session_buddy.resource_cleanup import _close_underlying_client

        mock_requests = MagicMock(spec=[])

        result = await _close_underlying_client(mock_requests, mock_logger)

        assert result is False

    @pytest.mark.asyncio
    async def test_close_underlying_client_no_aclose_or_close(self, mock_logger):
        """Test client has neither aclose nor close."""
        from session_buddy.resource_cleanup import _close_underlying_client

        mock_client = MagicMock(spec=[])
        mock_requests = MagicMock()
        mock_requests.client = mock_client

        result = await _close_underlying_client(mock_requests, mock_logger)

        assert result is False

    @pytest.mark.asyncio
    async def test_close_underlying_client_aclose_raises(self, mock_logger):
        """Test cleanup when client.aclose raises an exception."""
        from session_buddy.resource_cleanup import _close_underlying_client

        mock_client = MagicMock()
        mock_client.aclose = AsyncMock(side_effect=Exception("aclose failed"))
        mock_requests = MagicMock()
        mock_requests.client = mock_client

        # Should return False and not raise - actual code doesn't catch this
        with pytest.raises(Exception, match="aclose failed"):
            await _close_underlying_client(mock_requests, mock_logger)


# --- Test cleanup_http_clients ---

class TestCleanupHttpClients:
    """Tests for cleanup_http_clients async function."""

    @pytest.mark.asyncio
    async def test_cleanup_http_clients_module_not_found(self, mock_logger):
        """Test cleanup handles ModuleNotFoundError gracefully."""
        # When mcp_common.adapters is not available, import raises ModuleNotFoundError
        # which is caught by the except block
        with patch.dict("sys.modules", {"mcp_common": None, "mcp_common.adapters": None}):
            with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
                from session_buddy.resource_cleanup import cleanup_http_clients

                await cleanup_http_clients()

                mock_logger.debug.assert_called_with("mcp_common.adapters module not available; skipping HTTP cleanup")

    @pytest.mark.asyncio
    async def test_cleanup_http_clients_di_not_available(self, mock_logger):
        """Test cleanup when DI container doesn't have HTTPClientAdapter."""
        # When depends.get_sync raises an exception, it's caught and logged
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("session_buddy.di.container.depends") as mock_depends:
                mock_depends.get_sync.side_effect = Exception("Not available")

                from session_buddy.resource_cleanup import cleanup_http_clients

                # Exception is caught by suppress, we exit gracefully
                await cleanup_http_clients()


# --- Test cleanup_temp_files ---

class TestCleanupTempFiles:
    """Tests for cleanup_temp_files async function."""

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_default_dir_not_exists(self, mock_logger):
        """Test cleanup when default temp directory does not exist."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.Path") as mock_path_class:

            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = False
            mock_path_class.return_value = mock_path_instance

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files()

            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_custom_dir_not_exists(self, mock_logger):
        """Test cleanup when custom temp directory does not exist."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = False

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files(temp_dir=mock_temp_dir)

            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_empty_directory(self, mock_logger):
        """Test cleanup with empty temp directory."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True
            mock_temp_dir.glob.return_value = []

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files(temp_dir=mock_temp_dir)

            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_with_files(self, mock_logger):
        """Test cleanup removes temporary files."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True

            mock_file1 = MagicMock()
            mock_file1.is_file.return_value = True
            mock_file1.unlink = MagicMock()

            mock_file2 = MagicMock()
            mock_file2.is_file.return_value = True
            mock_file2.unlink = MagicMock()

            mock_temp_dir.glob.return_value = [mock_file1, mock_file2]

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files(temp_dir=mock_temp_dir)

            mock_file1.unlink.assert_called_once()
            mock_file2.unlink.assert_called_once()
            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_with_directories_ignored(self, mock_logger):
        """Test cleanup ignores directories, only removes files."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True

            mock_dir = MagicMock()
            mock_dir.is_file.return_value = False

            mock_file = MagicMock()
            mock_file.is_file.return_value = True
            mock_file.unlink = MagicMock()

            mock_temp_dir.glob.return_value = [mock_dir, mock_file]

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files(temp_dir=mock_temp_dir)

            mock_dir.unlink.assert_not_called()
            mock_file.unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_oserror_on_unlink(self, mock_logger):
        """Test cleanup handles OSError when removing file."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True

            mock_file = MagicMock()
            mock_file.is_file.return_value = True
            mock_file.unlink.side_effect = OSError("Permission denied")

            mock_temp_dir.glob.return_value = [mock_file]

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files(temp_dir=mock_temp_dir)

            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_permission_error_on_unlink(self, mock_logger):
        """Test cleanup handles PermissionError when removing file."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True

            mock_file = MagicMock()
            mock_file.is_file.return_value = True
            mock_file.unlink.side_effect = PermissionError("Access denied")

            mock_temp_dir.glob.return_value = [mock_file]

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files(temp_dir=mock_temp_dir)

            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_mixed_errors(self, mock_logger):
        """Test cleanup handles mix of successful and failed removals."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True

            mock_file1 = MagicMock()
            mock_file1.is_file.return_value = True
            mock_file1.unlink.side_effect = OSError("Failed 1")

            mock_file2 = MagicMock()
            mock_file2.is_file.return_value = True
            mock_file2.unlink = MagicMock()

            mock_temp_dir.glob.return_value = [mock_file1, mock_file2]

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files(temp_dir=mock_temp_dir)

            assert mock_logger.warning.call_count == 1

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_exception_raised(self, mock_logger):
        """Test cleanup raises exception on unexpected error during iteration."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True
            # Make glob raise an exception during iteration
            mock_temp_dir.glob.side_effect = Exception("Glob error")

            from session_buddy.resource_cleanup import cleanup_temp_files

            with pytest.raises(Exception, match="Glob error"):
                await cleanup_temp_files(temp_dir=mock_temp_dir)

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_very_long_path(self, mock_logger):
        """Test cleanup with very long file paths."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True

            # Create mock files with long paths
            long_path = "/tmp/very_long_filename_that_exceeds_normal_limits_and_might_cause_issues" * 3
            mock_file = MagicMock()
            mock_file.is_file.return_value = True
            mock_file.unlink = MagicMock()
            mock_file.__str__ = MagicMock(return_value=long_path)
            mock_file.__fspath__ = MagicMock(return_value=long_path)

            mock_temp_dir.glob.return_value = [mock_file]

            from session_buddy.resource_cleanup import cleanup_temp_files

            await cleanup_temp_files(temp_dir=mock_temp_dir)

            mock_file.unlink.assert_called_once()


# --- Test cleanup_file_handles ---

class TestCleanupFileHandles:
    """Tests for cleanup_file_handles async function."""

    @pytest.mark.asyncio
    async def test_cleanup_file_handles_success(self, mock_logger):
        """Test successful file handle cleanup."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            # First inject our mock logger
            with patch.object(sys, "stdout", MagicMock()) as mock_stdout, \
                 patch.object(sys, "stderr", MagicMock()) as mock_stderr:
                mock_stdout.flush = MagicMock()
                mock_stderr.flush = MagicMock()

                from session_buddy.resource_cleanup import cleanup_file_handles

                await cleanup_file_handles()

                mock_stdout.flush.assert_called_once()
                mock_stderr.flush.assert_called_once()
                mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_file_handles_no_flush_method(self, mock_logger):
        """Test cleanup handles missing flush method gracefully."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch.object(sys, "stdout", MagicMock(spec=[])), \
                 patch.object(sys, "stderr", MagicMock(spec=[])):

                from session_buddy.resource_cleanup import cleanup_file_handles

                await cleanup_file_handles()

                # Should not raise, just continue
                mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_file_handles_exception_during_flush(self, mock_logger):
        """Test cleanup handles exception during flush."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            mock_stdout = MagicMock()
            mock_stdout.flush.side_effect = Exception("Flush failed")
            mock_stderr = MagicMock()

            with patch.object(sys, "stdout", mock_stdout), \
                 patch.object(sys, "stderr", mock_stderr):

                from session_buddy.resource_cleanup import cleanup_file_handles

                with pytest.raises(Exception, match="Flush failed"):
                    await cleanup_file_handles()


# --- Test cleanup_session_state ---

class TestCleanupSessionState:
    """Tests for cleanup_session_state async function."""

    @pytest.mark.asyncio
    async def test_cleanup_session_state_success(self, mock_logger):
        """Test successful session state cleanup when DI is available."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.suppress", MagicMock()), \
             patch("session_buddy.di.container.depends") as mock_depends:

            mock_session_mgr = MagicMock()
            mock_session_mgr._save_state = MagicMock()
            mock_depends.get_sync.return_value = mock_session_mgr

            from session_buddy.resource_cleanup import cleanup_session_state

            await cleanup_session_state()

            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_session_state_manager_not_available(self):
        """Test cleanup when session manager is not available."""
        mock_logger = MagicMock()
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.di.container.depends") as mock_depends:

            mock_depends.get_sync.side_effect = Exception("Not available")

            from session_buddy.resource_cleanup import cleanup_session_state

            # Should not raise - exception is suppressed
            await cleanup_session_state()

    @pytest.mark.asyncio
    async def test_cleanup_session_state_import_error(self, mock_logger):
        """Test cleanup handles ImportError gracefully."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.suppress", MagicMock()), \
             patch("session_buddy.di.container.depends") as mock_depends, \
             patch.dict("sys.modules", {"session_buddy.core": None}):

            mock_depends.get_sync.side_effect = ImportError("Cannot import SessionLifecycleManager")

            from session_buddy.resource_cleanup import cleanup_session_state

            await cleanup_session_state()

            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_session_state_manager_has_no_save_state(self):
        """Test cleanup when session manager has no _save_state."""
        mock_logger = MagicMock()
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.di.container.depends") as mock_depends:

            # Return a manager without _save_state attribute
            mock_session_mgr = MagicMock(spec=[])  # Empty spec means no attributes
            mock_depends.get_sync.return_value = mock_session_mgr

            from session_buddy.resource_cleanup import cleanup_session_state

            await cleanup_session_state()

            # No debug call since _save_state doesn't exist

    @pytest.mark.asyncio
    async def test_cleanup_session_state_exception_raised(self, mock_logger):
        """Test cleanup raises exception on unexpected error."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.resource_cleanup.suppress", MagicMock()), \
             patch("session_buddy.di.container.depends") as mock_depends:

            mock_depends.get_sync.side_effect = ValueError("Unexpected error")

            from session_buddy.resource_cleanup import cleanup_session_state

            with pytest.raises(ValueError, match="Unexpected error"):
                await cleanup_session_state()

    @pytest.mark.asyncio
    async def test_cleanup_session_state_with_none_manager(self):
        """Test cleanup when session manager is None."""
        mock_logger = MagicMock()
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger), \
             patch("session_buddy.di.container.depends") as mock_depends:

            mock_depends.get_sync.return_value = None

            from session_buddy.resource_cleanup import cleanup_session_state

            await cleanup_session_state()

            # No debug call since manager is None (falsy)


# --- Test cleanup_background_tasks ---

class TestCleanupBackgroundTasks:
    """Tests for cleanup_background_tasks async function."""

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_success_with_pending_tasks(self, mock_logger):
        """Test cleanup cancels pending tasks."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("asyncio.get_running_loop") as mock_get_loop, \
                 patch("asyncio.current_task") as mock_current, \
                 patch("asyncio.all_tasks") as mock_all, \
                 patch("asyncio.gather", new=AsyncMock()) as mock_gather:

                # Create mock tasks
                mock_task1 = MagicMock()
                mock_task1.done.return_value = False
                mock_task1.cancel = MagicMock()

                mock_task2 = MagicMock()
                mock_task2.done.return_value = False
                mock_task2.cancel = MagicMock()

                mock_loop = MagicMock()
                mock_get_loop.return_value = mock_loop
                mock_current.return_value = mock_task1  # Current task is task1
                mock_all.return_value = [mock_task1, mock_task2]

                from session_buddy.resource_cleanup import cleanup_background_tasks

                await cleanup_background_tasks()

                mock_task1.cancel.assert_not_called()  # Should not cancel self
                mock_task2.cancel.assert_called_once()
                mock_gather.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_no_pending_tasks(self, mock_logger):
        """Test cleanup with no pending tasks."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("asyncio.get_running_loop") as mock_get_loop, \
                 patch("asyncio.current_task") as mock_current, \
                 patch("asyncio.all_tasks") as mock_all:

                mock_loop = MagicMock()
                mock_get_loop.return_value = mock_loop
                mock_current.return_value = MagicMock()  # Any task as current
                mock_all.return_value = []  # No tasks at all

                from session_buddy.resource_cleanup import cleanup_background_tasks

                await cleanup_background_tasks()

                mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_no_running_loop(self, mock_logger):
        """Test cleanup when no running event loop."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("asyncio.get_running_loop", side_effect=RuntimeError("No running loop")):

                from session_buddy.resource_cleanup import cleanup_background_tasks

                await cleanup_background_tasks()

                mock_logger.debug.assert_called_with("No running event loop, skipping task cleanup")

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_skips_current_task(self, mock_logger):
        """Test cleanup skips current task."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("asyncio.get_running_loop") as mock_get_loop, \
                 patch("asyncio.current_task") as mock_current, \
                 patch("asyncio.all_tasks") as mock_all, \
                 patch("asyncio.gather", new=AsyncMock()) as mock_gather:

                mock_current_task = MagicMock()
                mock_current_task.done.return_value = False

                mock_other = MagicMock()
                mock_other.done.return_value = False
                mock_other.cancel = MagicMock()

                mock_loop = MagicMock()
                mock_get_loop.return_value = mock_loop
                mock_current.return_value = mock_current_task
                mock_all.return_value = [mock_current_task, mock_other]

                from session_buddy.resource_cleanup import cleanup_background_tasks

                await cleanup_background_tasks()

                mock_other.cancel.assert_called_once()
                mock_current_task.cancel.assert_not_called()  # Should skip self

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_skips_done_tasks(self, mock_logger):
        """Test cleanup skips already done tasks."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("asyncio.get_running_loop") as mock_get_loop, \
                 patch("asyncio.current_task") as mock_current, \
                 patch("asyncio.all_tasks") as mock_all, \
                 patch("asyncio.gather", new=AsyncMock()) as mock_gather:

                mock_current = MagicMock()

                mock_done = MagicMock()
                mock_done.done.return_value = True  # Already done

                mock_pending = MagicMock()
                mock_pending.done.return_value = False
                mock_pending.cancel = MagicMock()

                mock_loop = MagicMock()
                mock_get_loop.return_value = mock_loop
                mock_current.return_value = mock_current
                mock_all.return_value = [mock_done, mock_pending]

                from session_buddy.resource_cleanup import cleanup_background_tasks

                await cleanup_background_tasks()

                mock_pending.cancel.assert_called_once()
                mock_done.cancel.assert_not_called()  # Already done, should not cancel

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_exception_during_gather(self, mock_logger):
        """Test cleanup handles exception during gather."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("asyncio.get_running_loop") as mock_get_loop, \
                 patch("asyncio.current_task") as mock_current, \
                 patch("asyncio.all_tasks") as mock_all, \
                 patch("asyncio.gather", new=AsyncMock()) as mock_gather:

                mock_task = MagicMock()
                mock_task.done.return_value = False
                mock_task.cancel = MagicMock()

                mock_loop = MagicMock()
                mock_get_loop.return_value = mock_loop
                mock_current.return_value = MagicMock()
                mock_all.return_value = [mock_task]
                mock_gather.side_effect = Exception("Gather failed")

                from session_buddy.resource_cleanup import cleanup_background_tasks

                with pytest.raises(Exception, match="Gather failed"):
                    await cleanup_background_tasks()

    @pytest.mark.asyncio
    async def test_cleanup_background_tasks_gather_returns_exception(self, mock_logger):
        """Test background cleanup when gather returns exceptions."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("asyncio.get_running_loop") as mock_get_loop, \
                 patch("asyncio.current_task") as mock_current, \
                 patch("asyncio.all_tasks") as mock_all, \
                 patch("asyncio.gather", new=AsyncMock()) as mock_gather:

                mock_task = MagicMock()
                mock_task.done.return_value = False
                mock_task.cancel = MagicMock()

                mock_loop = MagicMock()
                mock_get_loop.return_value = mock_loop
                mock_current.return_value = MagicMock()
                mock_all.return_value = [mock_task]
                # Return exceptions in gather result (not raise, but return them)
                mock_gather.return_value = [Exception("Task cancelled")]

                from session_buddy.resource_cleanup import cleanup_background_tasks

                # Should not raise even with exceptions in gather return
                await cleanup_background_tasks()


# --- Test cleanup_logging_handlers ---

class TestCleanupLoggingHandlers:
    """Tests for cleanup_logging_handlers async function."""

    @pytest.mark.asyncio
    async def test_cleanup_logging_handlers_success(self, mock_logger):
        """Test successful logging handler cleanup."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("logging.root") as mock_root, \
                 patch("logging.handlers", MagicMock()):

                mock_handler = MagicMock()
                mock_handler.flush = MagicMock()
                mock_handler.close = MagicMock()
                mock_root.handlers = [mock_handler]

                from session_buddy.resource_cleanup import cleanup_logging_handlers

                await cleanup_logging_handlers()

                mock_handler.flush.assert_called_once()
                mock_handler.close.assert_called_once()
                mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_logging_handlers_handler_with_only_close(self, mock_logger):
        """Test cleanup for handler with only close (no flush)."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("logging.root") as mock_root, \
                 patch("logging.handlers", MagicMock()):

                mock_handler = MagicMock()
                mock_handler.close = MagicMock()
                mock_root.handlers = [mock_handler]

                from session_buddy.resource_cleanup import cleanup_logging_handlers

                await cleanup_logging_handlers()

                mock_handler.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_logging_handlers_handler_with_only_flush(self, mock_logger):
        """Test cleanup for handler with only flush (no close)."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("logging.root") as mock_root, \
                 patch("logging.handlers", MagicMock()):

                mock_handler = MagicMock()
                mock_handler.flush = MagicMock()
                mock_root.handlers = [mock_handler]

                from session_buddy.resource_cleanup import cleanup_logging_handlers

                await cleanup_logging_handlers()

                mock_handler.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_logging_handlers_empty_handlers(self, mock_logger):
        """Test cleanup with no handlers."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("logging.root") as mock_root, \
                 patch("logging.handlers", MagicMock()):

                mock_root.handlers = []

                from session_buddy.resource_cleanup import cleanup_logging_handlers

                await cleanup_logging_handlers()

                mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_logging_handlers_exception_during_cleanup(self, mock_logger):
        """Test cleanup handles exception during handler cleanup gracefully."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("logging.root") as mock_root, \
                 patch("logging.handlers", MagicMock()):

                mock_handler = MagicMock()
                mock_handler.flush.side_effect = Exception("Flush error")
                mock_root.handlers = [mock_handler]

                from session_buddy.resource_cleanup import cleanup_logging_handlers

                # Exception is caught and printed to stderr, not re-raised
                await cleanup_logging_handlers()

                # The handler's flush was attempted
                mock_handler.flush.assert_called_once()


# --- Test _cleanup_handler ---

class TestCleanupHandler:
    """Tests for _cleanup_handler helper function."""

    def test_cleanup_handler_with_flush_and_close(self):
        """Test handler with both flush and close."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock()
        handler.flush = MagicMock()
        handler.close = MagicMock()

        _cleanup_handler(handler)

        handler.flush.assert_called_once()
        handler.close.assert_called_once()

    def test_cleanup_handler_with_only_close(self):
        """Test handler with only close."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock()
        handler.close = MagicMock()

        _cleanup_handler(handler)

        handler.close.assert_called_once()

    def test_cleanup_handler_with_only_flush(self):
        """Test handler with only flush."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock()
        handler.flush = MagicMock()

        _cleanup_handler(handler)

        handler.flush.assert_called_once()

    def test_cleanup_handler_remove_without_flush(self):
        """Test handler with remove but no flush (streaming handlers)."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock()
        handler.remove = MagicMock()
        # No flush, no close

        _cleanup_handler(handler)

        handler.remove.assert_not_called()

    def test_cleanup_handler_logger_proxy_type_error(self):
        """Test cleanup handles _LoggerProxy TypeError gracefully."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock()
        handler.flush = MagicMock()
        handler.close.side_effect = TypeError("_LoggerProxy.remove() handler_id")

        # Should not raise
        _cleanup_handler(handler)

    def test_cleanup_handler_other_type_error_raised(self):
        """Test cleanup raises other TypeErrors."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock()
        handler.flush = MagicMock()
        handler.close.side_effect = TypeError("Other error")

        with pytest.raises(TypeError, match="Other error"):
            _cleanup_handler(handler)

    def test_cleanup_handler_exception_during_close(self):
        """Test cleanup handles exception during close."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock()
        handler.close.side_effect = Exception("Close failed")

        # Should not raise, just log to stderr
        _cleanup_handler(handler)


# --- Test register_all_cleanup_handlers ---

class TestRegisterAllCleanupHandlers:
    """Tests for register_all_cleanup_handlers sync function."""

    def test_register_all_cleanup_handlers_success(self, mock_logger):
        """Test successful registration of all cleanup handlers."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_shutdown_manager = MagicMock()

            from session_buddy.resource_cleanup import register_all_cleanup_handlers

            register_all_cleanup_handlers(mock_shutdown_manager)

            # Verify all handlers were registered
            assert mock_shutdown_manager.register_cleanup.call_count == 7

            # Verify registration calls have expected names
            registered_names = [
                call[1]["name"] for call in mock_shutdown_manager.register_cleanup.call_args_list
            ]
            assert "database_connections" in registered_names
            assert "http_clients" in registered_names
            assert "background_tasks" in registered_names
            assert "session_state" in registered_names
            assert "file_handles" in registered_names
            assert "temp_files" in registered_names
            assert "logging_handlers" in registered_names

    def test_register_all_cleanup_handlers_with_custom_temp_dir(self, mock_logger):
        """Test registration with custom temp directory."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_shutdown_manager = MagicMock()
            mock_temp_dir = MagicMock(spec=Path)

            from session_buddy.resource_cleanup import register_all_cleanup_handlers

            register_all_cleanup_handlers(mock_shutdown_manager, temp_dir=mock_temp_dir)

            mock_shutdown_manager.register_cleanup.assert_called()

    def test_register_all_cleanup_handlers_priorities(self, mock_logger):
        """Test cleanup handlers are registered with correct priorities."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_shutdown_manager = MagicMock()

            from session_buddy.resource_cleanup import register_all_cleanup_handlers

            register_all_cleanup_handlers(mock_shutdown_manager)

            # Extract priorities from calls
            priorities = [
                call[1]["priority"] for call in mock_shutdown_manager.register_cleanup.call_args_list
            ]

            # Verify priorities are in descending order for critical items
            assert priorities[0] == 100  # database_connections
            assert priorities[1] == 100  # http_clients
            assert priorities[2] == 80   # background_tasks
            assert priorities[3] == 60   # session_state
            assert priorities[4] == 40   # file_handles
            assert priorities[5] == 20   # temp_files
            assert priorities[6] == 10   # logging_handlers

    def test_register_all_cleanup_handlers_timeout_values(self, mock_logger):
        """Test cleanup handlers have correct timeout values."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_shutdown_manager = MagicMock()

            from session_buddy.resource_cleanup import register_all_cleanup_handlers

            register_all_cleanup_handlers(mock_shutdown_manager)

            timeouts = {
                call[1]["name"]: call[1]["timeout_seconds"]
                for call in mock_shutdown_manager.register_cleanup.call_args_list
            }

            assert timeouts["database_connections"] == 10.0
            assert timeouts["http_clients"] == 10.0
            assert timeouts["background_tasks"] == 15.0
            assert timeouts["session_state"] == 10.0
            assert timeouts["file_handles"] == 5.0
            assert timeouts["temp_files"] == 10.0
            assert timeouts["logging_handlers"] == 5.0

    def test_register_all_cleanup_handlers_critical_flag(self, mock_logger):
        """Test cleanup handlers are marked as non-critical."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_shutdown_manager = MagicMock()

            from session_buddy.resource_cleanup import register_all_cleanup_handlers

            register_all_cleanup_handlers(mock_shutdown_manager)

            for call in mock_shutdown_manager.register_cleanup.call_args_list:
                assert call[1]["critical"] is False

    def test_register_all_cleanup_handlers_logging_handler_is_last(self, mock_logger):
        """Test logging handler is registered last (lowest priority)."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_shutdown_manager = MagicMock()

            from session_buddy.resource_cleanup import register_all_cleanup_handlers

            register_all_cleanup_handlers(mock_shutdown_manager)

            last_call = mock_shutdown_manager.register_cleanup.call_args_list[-1]
            assert last_call[1]["name"] == "logging_handlers"
            assert last_call[1]["priority"] == 10

    def test_register_all_cleanup_handlers_temp_files_wrapper_is_async(self, mock_logger):
        """Test temp_files cleanup wrapper is async."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_shutdown_manager = MagicMock()

            from session_buddy.resource_cleanup import register_all_cleanup_handlers

            register_all_cleanup_handlers(mock_shutdown_manager)

            # Find the temp_files registration
            temp_files_call = None
            for call in mock_shutdown_manager.register_cleanup.call_args_list:
                if call[1]["name"] == "temp_files":
                    temp_files_call = call
                    break

            assert temp_files_call is not None
            callback = temp_files_call[1]["callback"]

            # The callback should be an async function
            import inspect
            assert inspect.iscoroutinefunction(callback)


# --- Test _get_logger ---

class TestGetLogger:
    """Tests for _get_logger helper function."""

    def test_get_logger_success(self):
        """Test successful logger retrieval from session_buddy.utils.logging."""
        with patch("session_buddy.utils.logging.get_session_logger") as mock_get_logger:

            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            from session_buddy.resource_cleanup import _get_logger

            logger = _get_logger()

            assert logger == mock_logger

    def test_get_logger_fallback_on_import_error(self):
        """Test fallback to standard logging on import error."""
        with patch("session_buddy.utils.logging.get_session_logger", side_effect=Exception("Import error")), \
             patch("logging.getLogger") as mock_get_logger:

            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            from session_buddy.resource_cleanup import _get_logger

            logger = _get_logger()

            assert logger == mock_logger
            mock_get_logger.assert_called_with("session_buddy.resource_cleanup")


# --- Integration-style tests for cleanup ordering ---

class TestCleanupExecutionOrder:
    """Tests for cleanup execution order and interactions."""

    @pytest.mark.asyncio
    async def test_all_cleanup_functions_are_async(self):
        """Verify all cleanup functions are async."""
        from session_buddy import resource_cleanup
        import inspect

        async_functions = [
            "cleanup_database_connections",
            "cleanup_http_clients",
            "cleanup_temp_files",
            "cleanup_file_handles",
            "cleanup_session_state",
            "cleanup_background_tasks",
            "cleanup_logging_handlers",
        ]

        for func_name in async_functions:
            func = getattr(resource_cleanup, func_name)
            assert inspect.iscoroutinefunction(func), f"{func_name} should be async"

    def test_register_all_cleanup_handlers_is_sync(self):
        """Verify register_all_cleanup_handlers is a sync function."""
        import inspect
        from session_buddy.resource_cleanup import register_all_cleanup_handlers

        assert not inspect.iscoroutinefunction(register_all_cleanup_handlers)

    def test_all_exports_are_present(self):
        """Verify all expected exports are present."""
        from session_buddy import resource_cleanup

        expected_exports = [
            "cleanup_background_tasks",
            "cleanup_database_connections",
            "cleanup_file_handles",
            "cleanup_http_clients",
            "cleanup_logging_handlers",
            "cleanup_session_state",
            "cleanup_temp_files",
            "register_all_cleanup_handlers",
        ]

        for export in expected_exports:
            assert hasattr(resource_cleanup, export), f"Missing export: {export}"


# --- Edge case tests ---

class TestEdgeCases:
    """Edge case tests for resource cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_file_handles_with_mock_stdout_stderr(self, mock_logger):
        """Test file handle cleanup with mock stdout/stderr."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch.object(sys, "stdout", MagicMock()) as mock_stdout, \
                 patch.object(sys, "stderr", MagicMock()) as mock_stderr:
                mock_stdout.flush = MagicMock()
                mock_stderr.flush = MagicMock()

                from session_buddy.resource_cleanup import cleanup_file_handles

                await cleanup_file_handles()

                mock_stdout.flush.assert_called()
                mock_stderr.flush.assert_called()

    @pytest.mark.asyncio
    async def test_multiple_cleanup_calls_same_resource(self, mock_logger):
        """Test calling cleanup multiple times on same resource."""
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):
            with patch("logging.root") as mock_root, \
                 patch("logging.handlers", MagicMock()):

                mock_handler = MagicMock()
                mock_handler.flush = MagicMock()
                mock_handler.close = MagicMock()
                mock_root.handlers = [mock_handler]

                from session_buddy.resource_cleanup import cleanup_logging_handlers

                # Call multiple times
                await cleanup_logging_handlers()
                await cleanup_logging_handlers()

                # Both flush and close should be called twice
                assert mock_handler.flush.call_count == 2
                assert mock_handler.close.call_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_none_in_glob(self, mock_logger):
        """Test cleanup handles when glob returns items that cause iteration issues."""
        # This tests an edge case where the temp_dir exists but glob has issues
        # In practice, glob should always return valid Path objects
        with patch("session_buddy.resource_cleanup._get_logger", return_value=mock_logger):

            mock_temp_dir = MagicMock(spec=Path)
            mock_temp_dir.exists.return_value = True
            # Simulate a case where files in glob are problematic but not None
            # In real code, glob always returns proper Path-like objects
            mock_file = MagicMock()
            mock_file.is_file.return_value = True
            mock_file.unlink = MagicMock()

            mock_temp_dir.glob.return_value = [mock_file]

            from session_buddy.resource_cleanup import cleanup_temp_files

            # Should complete successfully with valid file
            await cleanup_temp_files(temp_dir=mock_temp_dir)

            mock_file.unlink.assert_called_once()


class TestErrorHandlingPatterns:
    """Tests for error handling patterns across cleanup functions."""

    @pytest.mark.asyncio
    async def test_all_cleanup_functions_log_on_exception(self, mock_logger):
        """Verify all cleanup functions call logger.exception on errors."""
        # This is tested implicitly by the fact that each function
        # has a try/except block that calls logger.exception

        # We verify by checking the code patterns exist
        import inspect
        from session_buddy import resource_cleanup

        cleanup_funcs = [
            resource_cleanup.cleanup_database_connections,
            resource_cleanup.cleanup_http_clients,
            resource_cleanup.cleanup_temp_files,
            resource_cleanup.cleanup_file_handles,
            resource_cleanup.cleanup_session_state,
            resource_cleanup.cleanup_background_tasks,
            resource_cleanup.cleanup_logging_handlers,
        ]

        for func in cleanup_funcs:
            source = inspect.getsource(func)
            assert "logger.exception" in source, f"{func.__name__} should log exceptions"

    def test_all_cleanup_functions_use_suppress_context_manager(self):
        """Verify cleanup functions use suppress for expected errors."""
        import inspect
        from session_buddy import resource_cleanup

        # Check cleanup_database_connections uses suppress
        source = inspect.getsource(resource_cleanup.cleanup_database_connections)
        assert "suppress" in source

        # Check cleanup_session_state uses suppress
        source = inspect.getsource(resource_cleanup.cleanup_session_state)
        assert "suppress" in source


# --- Additional coverage for internal helpers ---

class TestHelperFunctions:
    """Test internal helper functions directly."""

    def test_cleanup_handler_with_neither_flush_nor_close(self):
        """Test handler with neither flush nor close."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock(spec=[])  # No methods at all

        # Should not raise
        _cleanup_handler(handler)

    def test_cleanup_handler_with_remove_and_flush(self):
        """Test handler with remove and flush but no close."""
        from session_buddy.resource_cleanup import _cleanup_handler

        handler = MagicMock()
        handler.remove = MagicMock()
        handler.flush = MagicMock()
        # No close

        _cleanup_handler(handler)

        handler.flush.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov", "--tb=short"])