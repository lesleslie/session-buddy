"""Comprehensive tests for Git maintenance service.

Tests the hook-based architecture, process tracking, rate limiting,
and TOCTOU prevention mechanisms.

Week 8 Day 2 - Phase 5: Test service architecture improvements.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from session_buddy.core.hooks import HookContext, HookResult, HookType, HooksManager
from session_buddy.services.git_maintenance import (
    GitMaintenanceConfig,
    GitMaintenanceService,
    GitProcessTracker,
    get_git_maintenance_service,
)
from tests.fixtures import tmp_git_repo


@pytest.mark.asyncio
class TestGitProcessTracker:
    """Test process tracking and lifecycle management."""

    def test_track_process(self):
        """GitProcessTracker tracks processes successfully."""
        tracker = GitProcessTracker()

        # Create mock Popen object
        mock_popen = Mock()
        mock_popen.poll = Mock(return_value=None)  # Still running

        # Track process
        process_id = tracker.track_process(
            mock_popen,
            Path("/tmp/test_repo"),
            "2.weeks",
            6700,
        )

        assert process_id is not None
        assert "test_repo" in process_id
        assert tracker.get_active_count() == 1

    def test_cleanup_finished_processes(self):
        """GitProcessTracker cleans up finished processes."""
        tracker = GitProcessTracker()

        # Create mock processes (some finished, some running)
        running_popen = Mock()
        running_popen.poll = Mock(return_value=None)  # Still running

        finished_popen = Mock()
        finished_popen.poll = Mock(return_value=0)  # Finished
        finished_popen.returncode = 0

        tracker.track_process(running_popen, Path("/tmp/repo1"), "2.weeks", 6700)
        tracker.track_process(finished_popen, Path("/tmp/repo2"), "1.month", 5000)

        # Cleanup
        tracker.cleanup_finished_processes()

        # Only running process remains
        assert tracker.get_active_count() == 1
        assert len(tracker.finished_processes) == 1

    def test_wait_for_completion_timeout(self):
        """GitProcessTracker handles timeout correctly."""
        tracker = GitProcessTracker()

        # Create mock process that never finishes
        mock_popen = Mock()
        mock_popen.poll = Mock(return_value=None)

        tracker.track_process(mock_popen, Path("/tmp/repo"), "2.weeks", 6700)

        # Wait with short timeout
        result = tracker.wait_for_completion(timeout=0.5)

        assert result is False  # Should timeout
        assert tracker.get_active_count() == 1

    def test_terminate_all(self):
        """GitProcessTracker terminates all processes."""
        tracker = GitProcessTracker()

        # Create mock processes
        mock_popen1 = Mock()
        mock_popen1.poll = Mock(return_value=None)

        mock_popen2 = Mock()
        mock_popen2.poll = Mock(return_value=None)

        tracker.track_process(mock_popen1, Path("/tmp/repo1"), "2.weeks", 6700)
        tracker.track_process(mock_popen2, Path("/tmp/repo2"), "1.month", 5000)

        # Terminate all
        tracker.terminate_all()

        assert tracker.get_active_count() == 0
        mock_popen1.terminate.assert_called_once()
        mock_popen2.terminate.assert_called_once()


@pytest.mark.asyncio
class TestGitMaintenanceService:
    """Test git maintenance service functionality."""

    def test_singleton_instance(self):
        """get_git_maintenance_service returns singleton instance."""
        service1 = get_git_maintenance_service()
        service2 = get_git_maintenance_service()

        assert service1 is service2

    def test_rate_limiting(self, tmp_git_repo: Path):
        """GitMaintenanceService enforces rate limiting."""
        config = GitMaintenanceConfig(
            enabled=True, min_gc_interval=3600  # 1 hour
        )
        service = GitMaintenanceService(config)

        with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc") as mock_gc:
            mock_gc.return_value = (True, "Scheduled")

            # First call should succeed
            result1 = service.perform_maintenance(tmp_git_repo)
            assert result1["success"] is True

            # Immediate second call should be rate limited
            result2 = service.perform_maintenance(tmp_git_repo)
            assert result2["success"] is False
            assert "Rate limit" in result2["message"]

    def test_disabled_service(self, tmp_git_repo: Path):
        """GitMaintenanceService skips gc when disabled."""
        config = GitMaintenanceConfig(enabled=False)
        service = GitMaintenanceService(config)

        result = service.perform_maintenance(tmp_git_repo)

        assert result["success"] is False
        assert "disabled" in result["message"].lower()

    def test_git_operation_in_progress(self, tmp_git_repo: Path):
        """GitMaintenanceService skips gc during active git operations."""
        config = GitMaintenanceConfig(only_when_clean=True)
        service = GitMaintenanceService(config)

        with patch("session_buddy.services.git_maintenance.is_git_operation_in_progress") as mock_check:
            mock_check.return_value = True

            result = service.perform_maintenance(tmp_git_repo)

            assert result["success"] is False
            assert "in progress" in result["message"].lower()

    def test_max_concurrent_processes(self, tmp_git_repo: Path):
        """GitMaintenanceService respects max concurrent process limit."""
        config = GitMaintenanceConfig(max_concurrent_gc=1)
        service = GitMaintenanceService(config)

        # Add a fake active process
        mock_popen = Mock()
        mock_popen.poll = Mock(return_value=None)
        service.process_tracker.track_process(
            mock_popen, tmp_git_repo, "2.weeks", 6700
        )

        with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc"):
            result = service.perform_maintenance(tmp_git_repo)

            assert result["success"] is False
            assert "concurrent" in result["message"].lower()

    def test_invalid_prune_delay(self, tmp_git_repo: Path):
        """GitMaintenanceService rejects invalid prune delays."""
        config = GitMaintenanceConfig(prune_delay="malicious; rm -rf /")
        service = GitMaintenanceService(config)

        result = service.perform_maintenance(tmp_git_repo)

        assert result["success"] is False
        assert "Invalid" in result["message"]

    async def test_hook_registration(self):
        """GitMaintenanceService registers hooks correctly."""
        service = GitMaintenanceService()

        # Mock hooks manager to avoid DI dependencies
        mock_hooks_manager = AsyncMock()

        # Register hooks
        await service.register_hooks(mock_hooks_manager)

        # Verify register_hook was called
        mock_hooks_manager.register_hook.assert_called_once()

        # Get the hook that was registered
        call_args = mock_hooks_manager.register_hook.call_args
        registered_hook = call_args[0][0]

        assert registered_hook.name == "git_maintenance_post_checkpoint"
        assert registered_hook.priority == 100

    async def test_on_post_checkpoint_handler(self, tmp_git_repo: Path):
        """GitMaintenanceService handles post-checkpoint hooks."""
        config = GitMaintenanceConfig(enabled=True, min_gc_interval=0)
        service = GitMaintenanceService(config)

        with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc") as mock_gc:
            mock_gc.return_value = (True, "Scheduled")

            # Create hook context
            context = HookContext(
                hook_type=HookType.POST_CHECKPOINT,
                session_id="test-session",
                timestamp=None,  # type: ignore[arg-type]
                checkpoint_data={"repository": str(tmp_git_repo)},
            )

            # Call handler
            result = await service._on_post_checkpoint(context)

            assert result.success is True

    def test_lock_acquisition_and_release(self, tmp_git_repo: Path):
        """GitMaintenanceService properly acquires and releases locks."""
        service = GitMaintenanceService()

        with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc") as mock_gc:
            mock_gc.return_value = (True, "Scheduled")

            result = service.perform_maintenance(tmp_git_repo)

            # Lock should be acquired and released
            assert result["success"] is True
            assert service._lock_file_handle is None  # Released after operation

    def test_lock_already_held(self, tmp_git_repo: Path):
        """GitMaintenanceService handles busy lock gracefully."""
        service = GitMaintenanceService()

        # Simulate lock already held
        with patch("os.open", side_effect=OSError("Lock held")):
            with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc"):
                result = service.perform_maintenance(tmp_git_repo)

                assert result["success"] is False
                assert "lock" in result["message"].lower()

    def test_shutdown_cleanup(self, tmp_git_repo: Path):
        """GitMaintenanceService cleans up resources on shutdown."""
        service = GitMaintenanceService()

        # Add some mock processes
        for i in range(3):
            mock_popen = Mock()
            mock_popen.poll = Mock(return_value=None)
            service.process_tracker.track_process(
                mock_popen, tmp_git_repo, "2.weeks", 6700
            )

        # Shutdown
        service.shutdown()

        # Processes should be terminated
        assert service.process_tracker.get_active_count() == 0


@pytest.mark.asyncio
class TestTOCTOUPrevention:
    """Test TOCTOU race condition prevention."""

    def test_atomic_check_and_execute(self, tmp_git_repo: Path):
        """Lock acquisition prevents race between check and execute."""
        service = GitMaintenanceService()

        call_order = []

        def mock_acquire_lock(repo: Path) -> bool:
            call_order.append("acquire_lock")
            return True

        def mock_release_lock() -> None:
            call_order.append("release_lock")

        def mock_gc(*args, **kwargs):
            call_order.append("gc_executed")
            return (True, "Scheduled")

        with patch.object(service, "_acquire_lock", side_effect=mock_acquire_lock):
            with patch.object(service, "_release_lock", side_effect=mock_release_lock):
                with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc", side_effect=mock_gc):
                    service.perform_maintenance(tmp_git_repo)

                    # Verify atomic sequence: lock -> gc -> release
                    assert call_order == ["acquire_lock", "gc_executed", "release_lock"]

    def test_lock_failure_prevents_gc(self, tmp_git_repo: Path):
        """Failed lock acquisition prevents gc execution."""
        service = GitMaintenanceService()

        gc_called = False

        def mock_gc(*args, **kwargs):
            nonlocal gc_called
            gc_called = True
            return (True, "Scheduled")

        with patch.object(service, "_acquire_lock", return_value=False):
            with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc", side_effect=mock_gc):
                result = service.perform_maintenance(tmp_git_repo)

                assert result["success"] is False
                assert gc_called is False  # GC should not execute

    async def test_concurrent_gcs_prevented(self, tmp_git_repo: Path):
        """Multiple concurrent gc calls are serialized by locking."""
        config = GitMaintenanceConfig(max_concurrent_gc=1, min_gc_interval=0)  # Disable rate limiting
        service = GitMaintenanceService(config)

        gc_calls = []

        def mock_gc(*args, **kwargs):
            gc_calls.append("gc_executed")
            return (True, "Scheduled")

        with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc", side_effect=mock_gc):
            # First call should succeed
            result1 = service.perform_maintenance(tmp_git_repo)
            assert result1["success"] is True
            assert len(gc_calls) == 1

            # Clear rate limit tracker to allow second call
            service.last_gc_time.clear()

            # Add mock active process (simulates first GC still running)
            mock_popen = Mock()
            mock_popen.poll = Mock(return_value=None)
            service.process_tracker.track_process(
                mock_popen, tmp_git_repo, "2.weeks", 6700
            )

            # Second call should be blocked by process limit
            result2 = service.perform_maintenance(tmp_git_repo)
            assert result2["success"] is False
            # Should fail due to concurrent process limit, not rate limit
            assert "concurrent" in result2["message"].lower() or "max" in result2["message"].lower()

            # No additional GC call should have been made
            assert len(gc_calls) == 1


@pytest.mark.asyncio
class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_custom_rate_limit_interval(self, tmp_git_repo: Path):
        """Custom rate limit interval is respected."""
        config = GitMaintenanceConfig(min_gc_interval=10)  # 10 seconds
        service = GitMaintenanceService(config)

        with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc") as mock_gc:
            mock_gc.return_value = (True, "Scheduled")

            # First call
            result1 = service.perform_maintenance(tmp_git_repo)
            assert result1["success"] is True

            # Immediate second call
            result2 = service.perform_maintenance(tmp_git_repo)
            assert result2["success"] is False
            assert "Rate limit" in result2["message"]

    def test_rate_limit_per_repository(self, tmp_git_repo: Path):
        """Rate limiting is per-repository, not global."""
        config = GitMaintenanceConfig(min_gc_interval=3600)
        service = GitMaintenanceService(config)

        with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc") as mock_gc:
            mock_gc.return_value = (True, "Scheduled")

            # Call on same repo twice
            result1 = service.perform_maintenance(tmp_git_repo)
            result2 = service.perform_maintenance(tmp_git_repo)

            assert result1["success"] is True
            assert result2["success"] is False  # Rate limited


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling and graceful degradation."""

    def test_exception_releases_lock(self, tmp_git_repo: Path):
        """Exceptions during gc execution still release the lock."""
        service = GitMaintenanceService()

        lock_released = False

        def mock_release():
            nonlocal lock_released
            lock_released = True

        with patch.object(service, "_release_lock", side_effect=mock_release):
            with patch("session_buddy.services.git_maintenance.schedule_automatic_git_gc", side_effect=Exception("GC failed")):
                result = service.perform_maintenance(tmp_git_repo)

                assert result["success"] is False
                assert lock_released is True  # Lock released despite exception

    def test_hook_error_doesnt_crash(self, tmp_git_repo: Path):
        """Hook errors are caught and logged."""
        service = GitMaintenanceService()

        context = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="test-session",
            timestamp=None,  # type: ignore[arg-type]
            checkpoint_data={"repository": str(tmp_git_repo)},
        )

        # Force an exception
        with patch.object(service, "perform_maintenance", side_effect=Exception("Test error")):
            result = asyncio.run(service._on_post_checkpoint(context))

            # Should return error result, not crash
            assert result.success is False
            assert result.error == "Test error"
