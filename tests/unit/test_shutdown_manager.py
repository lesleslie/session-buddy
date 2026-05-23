"""Comprehensive tests for graceful shutdown manager.

Tests shutdown coordination, signal handling, cleanup task execution,
error recovery, edge cases, and concurrent access patterns.

Phase 10.2: Production Hardening - Graceful Shutdown Tests
"""

from __future__ import annotations

import asyncio
import atexit
import signal
import tempfile
import time
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from session_buddy.shutdown_manager import (
    CleanupTask,
    ShutdownManager,
    ShutdownStats,
    get_shutdown_manager,
)


# ==============================================================================
# CleanupTask Dataclass Tests
# ==============================================================================

class TestCleanupTaskDataclass:
    """Test CleanupTask dataclass structure and defaults."""

    def test_cleanup_task_creation(self) -> None:
        """Should create CleanupTask with all fields."""
        async def callback():
            pass

        task = CleanupTask(
            name="test_task",
            callback=callback,
            priority=50,
            timeout_seconds=15.0,
            critical=True,
        )

        assert task.name == "test_task"
        assert task.callback is callback
        assert task.priority == 50
        assert task.timeout_seconds == 15.0
        assert task.critical is True

    def test_cleanup_task_defaults(self) -> None:
        """Should have correct default values."""
        def callback():
            pass

        task = CleanupTask(name="default_test", callback=callback)
        assert task.priority == 0
        assert task.timeout_seconds == 30.0
        assert task.critical is False

    def test_cleanup_task_immutable_name(self) -> None:
        """Name should be a string as expected."""
        def callback():
            pass

        task = CleanupTask(name="immutable", callback=callback)
        assert isinstance(task.name, str)


# ==============================================================================
# ShutdownStats Dataclass Tests
# ==============================================================================

class TestShutdownStatsDataclass:
    """Test ShutdownStats dataclass structure and defaults."""

    def test_stats_default_values(self) -> None:
        """Should have correct default values."""
        stats = ShutdownStats()

        assert stats.tasks_registered == 0
        assert stats.tasks_executed == 0
        assert stats.tasks_failed == 0
        assert stats.tasks_timeout == 0
        assert stats.total_duration_ms == 0.0

    def test_stats_custom_values(self) -> None:
        """Should store custom values correctly."""
        stats = ShutdownStats(
            tasks_registered=10,
            tasks_executed=8,
            tasks_failed=1,
            tasks_timeout=1,
            total_duration_ms=150.5,
        )

        assert stats.tasks_registered == 10
        assert stats.tasks_executed == 8
        assert stats.tasks_failed == 1
        assert stats.tasks_timeout == 1
        assert stats.total_duration_ms == 150.5


# ==============================================================================
# ShutdownManager Initialization Tests
# ==============================================================================

class TestShutdownManagerInit:
    """Test ShutdownManager initialization."""

    def test_init_creates_empty_task_list(self) -> None:
        """Should initialize with empty cleanup tasks."""
        manager = ShutdownManager()
        assert manager._cleanup_tasks == []
        assert len(manager._cleanup_tasks) == 0

    def test_init_shutdown_not_initiated(self) -> None:
        """Should start with shutdown not initiated."""
        manager = ShutdownManager()
        assert manager._shutdown_initiated is False
        assert manager.is_shutdown_initiated() is False

    def test_init_creates_shutdown_lock(self) -> None:
        """Should create asyncio Lock for thread safety."""
        manager = ShutdownManager()
        assert isinstance(manager._shutdown_lock, asyncio.Lock)

    def test_init_creates_empty_original_handlers(self) -> None:
        """Should have empty original handlers dict."""
        manager = ShutdownManager()
        assert manager._original_handlers == {}

    def test_init_creates_stats(self) -> None:
        """Should initialize with empty stats."""
        manager = ShutdownManager()
        assert isinstance(manager._stats, ShutdownStats)
        assert manager._stats.tasks_registered == 0


# ==============================================================================
# Cleanup Task Registration Tests
# ==============================================================================

class TestCleanupTaskRegistration:
    """Test cleanup task registration functionality."""

    def test_register_sync_cleanup_task(self) -> None:
        """Should register synchronous cleanup task."""
        manager = ShutdownManager()

        def sync_cleanup():
            pass

        manager.register_cleanup("sync_task", sync_cleanup, priority=10)

        assert len(manager._cleanup_tasks) == 1
        task = manager._cleanup_tasks[0]
        assert task.name == "sync_task"
        assert task.priority == 10
        assert task.callback == sync_cleanup

    def test_register_async_cleanup_task(self) -> None:
        """Should register asynchronous cleanup task."""
        manager = ShutdownManager()

        async def async_cleanup():
            pass

        manager.register_cleanup("async_task", async_cleanup, priority=20)

        assert len(manager._cleanup_tasks) == 1
        task = manager._cleanup_tasks[0]
        assert task.name == "async_task"
        assert task.priority == 20

    def test_register_multiple_tasks_with_priorities(self) -> None:
        """Should register multiple tasks with different priorities."""
        manager = ShutdownManager()

        manager.register_cleanup("low", lambda: None, priority=10)
        manager.register_cleanup("high", lambda: None, priority=100)
        manager.register_cleanup("medium", lambda: None, priority=50)

        assert len(manager._cleanup_tasks) == 3
        assert manager._stats.tasks_registered == 3

    def test_register_critical_task(self) -> None:
        """Should register critical cleanup task."""
        manager = ShutdownManager()

        manager.register_cleanup("critical", lambda: None, critical=True)

        task = manager._cleanup_tasks[0]
        assert task.critical is True

    def test_register_task_with_custom_timeout(self) -> None:
        """Should register task with custom timeout."""
        manager = ShutdownManager()

        manager.register_cleanup("slow", lambda: None, timeout_seconds=60.0)

        task = manager._cleanup_tasks[0]
        assert task.timeout_seconds == 60.0

    def test_register_increments_stats(self) -> None:
        """Should increment tasks_registered in stats."""
        manager = ShutdownManager()

        manager.register_cleanup("task1", lambda: None)
        manager.register_cleanup("task2", lambda: None)

        assert manager._stats.tasks_registered == 2

    def test_register_task_with_all_parameters(self) -> None:
        """Should register task with all custom parameters."""
        manager = ShutdownManager()

        async def custom_callback():
            pass

        manager.register_cleanup(
            name="full_custom",
            callback=custom_callback,
            priority=75,
            timeout_seconds=45.0,
            critical=True,
        )

        task = manager._cleanup_tasks[0]
        assert task.name == "full_custom"
        assert task.callback is custom_callback
        assert task.priority == 75
        assert task.timeout_seconds == 45.0
        assert task.critical is True


# ==============================================================================
# Signal Handler Setup Tests
# ==============================================================================

class TestSignalHandlerSetup:
    """Test signal handler registration and restoration."""

    @pytest.mark.asyncio
    async def test_setup_signal_handlers_registers_handlers(self) -> None:
        """Should register signal handlers for SIGTERM and SIGINT."""
        manager = ShutdownManager()

        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        try:
            manager.setup_signal_handlers()

            # Handlers should be changed
            sigterm_handler = signal.getsignal(signal.SIGTERM)
            sigint_handler = signal.getsignal(signal.SIGINT)

            assert sigterm_handler != original_sigterm, "SIGTERM handler should be changed"
            assert sigint_handler != original_sigint, "SIGINT handler should be changed"

            # Should have saved original handlers
            assert signal.SIGTERM in manager._original_handlers
            assert signal.SIGINT in manager._original_handlers

        finally:
            manager.restore_signal_handlers()

    @pytest.mark.asyncio
    async def test_setup_signal_handlers_registers_atexit(self) -> None:
        """Should register atexit handler."""
        manager = ShutdownManager()

        # We can't easily test if atexit.register was called without mocking,
        # but we can verify setup_signal_handlers completes without error
        manager.setup_signal_handlers()

        try:
            manager.restore_signal_handlers()
        finally:
            pass

    def test_restore_signal_handlers_restores_originals(self) -> None:
        """Should restore original signal handlers."""
        manager = ShutdownManager()

        original_sigterm = signal.getsignal(signal.SIGTERM)

        manager.setup_signal_handlers()
        # Handler changed
        assert signal.getsignal(signal.SIGTERM) != original_sigterm

        manager.restore_signal_handlers()
        # Handler restored
        assert signal.getsignal(signal.SIGTERM) == original_sigterm

    def test_restore_handlers_clears_original_handlers_dict(self) -> None:
        """Should clear original handlers after restore."""
        manager = ShutdownManager()

        manager.setup_signal_handlers()
        assert len(manager._original_handlers) > 0

        manager.restore_signal_handlers()
        assert len(manager._original_handlers) == 0

    @pytest.mark.asyncio
    async def test_restore_handlers_handles_invalid_signals(self) -> None:
        """Should handle errors gracefully when restoring invalid signals."""
        manager = ShutdownManager()

        # Add a fake signal handler to test error handling
        manager._original_handlers[9999] = signal.SIG_DFL

        # Should not raise, just log warning
        with patch("session_buddy.shutdown_manager._get_logger") as mock_logger:
            manager.restore_signal_handlers()

    def test_setup_handlers_catches_os_error(self) -> None:
        """Should catch OSError when signal handler registration fails."""
        manager = ShutdownManager()

        # Mock signal.signal to raise OSError
        with patch("signal.signal") as mock_signal:
            mock_signal.side_effect = OSError("Invalid signal")

            # Should not raise, just log warning
            with patch("session_buddy.shutdown_manager._get_logger") as mock_logger:
                manager.setup_signal_handlers()


# ==============================================================================
# Signal Handler Execution Tests
# ==============================================================================

class TestSignalHandlerExecution:
    """Test signal handler behavior."""

    @pytest.mark.asyncio
    async def test_signal_handler_triggers_shutdown(self) -> None:
        """Should trigger shutdown when signal received."""
        manager = ShutdownManager()
        executed = []

        def cleanup():
            executed.append("cleaned")

        manager.register_cleanup("test", cleanup)
        manager.setup_signal_handlers()

        try:
            # Manually call signal handler (simulating signal)
            manager._signal_handler(signal.SIGTERM, None)

            # Give it time to execute
            await asyncio.sleep(0.1)

            # Cleanup should have run
            assert "cleaned" in executed

        finally:
            manager.restore_signal_handlers()

    @pytest.mark.asyncio
    async def test_signal_handler_with_running_loop(self) -> None:
        """Should schedule shutdown on running event loop."""
        manager = ShutdownManager()
        executed = []

        async def cleanup():
            executed.append("done")

        manager.register_cleanup("async_cleanup", cleanup)
        manager.setup_signal_handlers()

        try:
            loop = asyncio.get_running_loop()
            # Schedule signal handler to be called
            loop.call_soon(lambda: manager._signal_handler(signal.SIGTERM, None))

            # Wait for execution
            await asyncio.sleep(0.2)

            assert "done" in executed
        finally:
            manager.restore_signal_handlers()

    def test_signal_handler_without_running_loop(self) -> None:
        """Should handle case when no event loop is running."""
        manager = ShutdownManager()
        executed = []

        async def cleanup():
            executed.append("done")

        manager.register_cleanup("no_loop_cleanup", cleanup)

        # Call signal handler when no running loop exists
        # This should create a new event loop via asyncio.run()
        manager._signal_handler(signal.SIGTERM, None)

        # Give it time to execute
        time.sleep(0.2)

        assert "done" in executed

    def test_signal_handler_gets_sig_name(self) -> None:
        """Should correctly identify signal name."""
        manager = ShutdownManager()
        manager.register_cleanup("test", lambda: None)  # Prevent atexit triggering actual shutdown

        with patch("session_buddy.shutdown_manager._get_logger") as mock_logger:
            manager._signal_handler(signal.SIGTERM, None)

            # Should have logged info calls - check first one is signal message
            info_calls = mock_logger().info.call_args_list
            assert len(info_calls) >= 1
            # First call should be the signal received message
            first_call_args = info_calls[0][0][0]
            assert "SIGTERM" in first_call_args


# ==============================================================================
# Shutdown Execution Tests
# ==============================================================================

class TestShutdownExecution:
    """Test shutdown execution and task coordination."""

    @pytest.mark.asyncio
    async def test_execute_sync_cleanup_tasks(self) -> None:
        """Should execute synchronous cleanup tasks successfully."""
        manager = ShutdownManager()
        executed = []

        def cleanup1():
            executed.append(1)

        def cleanup2():
            executed.append(2)

        manager.register_cleanup("task1", cleanup1)
        manager.register_cleanup("task2", cleanup2)

        stats = await manager.shutdown()

        assert executed == [1, 2]
        assert stats.tasks_executed == 2
        assert stats.tasks_failed == 0

    @pytest.mark.asyncio
    async def test_execute_async_cleanup_tasks(self) -> None:
        """Should execute asynchronous cleanup tasks successfully."""
        manager = ShutdownManager()
        executed = []

        async def cleanup1():
            executed.append(1)

        async def cleanup2():
            executed.append(2)

        manager.register_cleanup("task1", cleanup1)
        manager.register_cleanup("task2", cleanup2)

        stats = await manager.shutdown()

        assert executed == [1, 2]
        assert stats.tasks_executed == 2

    @pytest.mark.asyncio
    async def test_execute_tasks_by_priority_order(self) -> None:
        """Should execute tasks in priority order (highest first)."""
        manager = ShutdownManager()
        execution_order = []

        def low():
            execution_order.append("low")

        def high():
            execution_order.append("high")

        def medium():
            execution_order.append("medium")

        # Register in random order
        manager.register_cleanup("low", low, priority=10)
        manager.register_cleanup("high", high, priority=100)
        manager.register_cleanup("medium", medium, priority=50)

        await manager.shutdown()

        # Should execute high -> medium -> low
        assert execution_order == ["high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_execute_mixed_sync_async_tasks(self) -> None:
        """Should execute mix of sync and async tasks in order."""
        manager = ShutdownManager()
        execution_order = []

        async def async_high():
            execution_order.append("async_high")

        def sync_low():
            execution_order.append("sync_low")

        async def async_medium():
            execution_order.append("async_medium")

        manager.register_cleanup("async_high", async_high, priority=100)
        manager.register_cleanup("sync_low", sync_low, priority=10)
        manager.register_cleanup("async_medium", async_medium, priority=50)

        await manager.shutdown()

        assert execution_order == ["async_high", "async_medium", "sync_low"]

    @pytest.mark.asyncio
    async def test_shutdown_with_no_tasks(self) -> None:
        """Should handle shutdown with no registered tasks."""
        manager = ShutdownManager()

        stats = await manager.shutdown()

        assert stats.tasks_executed == 0
        assert stats.tasks_failed == 0
        assert stats.total_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_shutdown_tracks_duration(self) -> None:
        """Should track total shutdown duration."""
        manager = ShutdownManager()

        async def slow_cleanup():
            await asyncio.sleep(0.01)  # 10ms

        manager.register_cleanup("slow", slow_cleanup)

        stats = await manager.shutdown()

        assert stats.total_duration_ms > 0
        assert stats.total_duration_ms >= 10  # At least the sleep time


# ==============================================================================
# Task Timeout Handling Tests
# ==============================================================================

class TestTaskTimeoutHandling:
    """Test timeout enforcement on cleanup tasks."""

    @pytest.mark.asyncio
    async def test_handle_task_timeout(self) -> None:
        """Should handle task timeout gracefully."""
        manager = ShutdownManager()

        async def slow_task():
            await asyncio.sleep(2.0)  # Will timeout

        manager.register_cleanup("slow", slow_task, timeout_seconds=0.1)

        stats = await manager.shutdown()

        assert stats.tasks_timeout == 1
        assert stats.tasks_executed == 0

    @pytest.mark.asyncio
    async def test_critical_task_timeout_stops_cleanup(self) -> None:
        """Should stop cleanup when critical task times out."""
        manager = ShutdownManager()
        executed = []

        async def critical_slow():
            await asyncio.sleep(10.0)

        def later_task():
            executed.append("later")

        manager.register_cleanup(
            "critical_slow", critical_slow, priority=100, timeout_seconds=0.1, critical=True
        )
        manager.register_cleanup("later", later_task, priority=10)

        stats = await manager.shutdown()

        # Later task should not execute due to critical timeout
        assert "later" not in executed
        assert stats.tasks_timeout == 1
        assert stats.tasks_executed == 0

    @pytest.mark.asyncio
    async def test_non_critical_task_timeout_continues(self) -> None:
        """Should continue cleanup when non-critical task times out."""
        manager = ShutdownManager()
        execution_order = []

        async def slow_task():
            await asyncio.sleep(10.0)

        def after_timeout():
            execution_order.append("after_timeout")

        manager.register_cleanup(
            "slow", slow_task, priority=100, timeout_seconds=0.1, critical=False
        )
        manager.register_cleanup("after", after_timeout, priority=10)

        stats = await manager.shutdown()

        # After task should still execute
        assert "after_timeout" in execution_order
        assert stats.tasks_timeout == 1
        assert stats.tasks_executed == 1


# ==============================================================================
# Task Failure Handling Tests
# ==============================================================================

class TestTaskFailureHandling:
    """Test error handling during cleanup tasks."""

    @pytest.mark.asyncio
    async def test_handle_task_exception(self) -> None:
        """Should handle task exception and continue for non-critical."""
        manager = ShutdownManager()
        executed = []

        def failing_task():
            raise RuntimeError("Cleanup failed")

        def successful_task():
            executed.append("success")

        manager.register_cleanup("fail", failing_task, priority=100, critical=False)
        manager.register_cleanup("success", successful_task, priority=10)

        stats = await manager.shutdown()

        # Failed task should not stop other tasks
        assert "success" in executed
        assert stats.tasks_failed == 1
        assert stats.tasks_executed == 1

    @pytest.mark.asyncio
    async def test_critical_task_failure_stops_cleanup(self) -> None:
        """Should stop cleanup when critical task fails."""
        manager = ShutdownManager()
        executed = []

        def critical_failing():
            raise RuntimeError("Critical failure")

        def later_task():
            executed.append("later")

        manager.register_cleanup(
            "critical", critical_failing, priority=100, critical=True
        )
        manager.register_cleanup("later", later_task, priority=10)

        stats = await manager.shutdown()

        # Later task should not execute
        assert "later" not in executed
        assert stats.tasks_failed == 1
        assert stats.tasks_executed == 0

    @pytest.mark.asyncio
    async def test_non_critical_failure_continues_cleanup(self) -> None:
        """Should continue cleanup when non-critical task fails."""
        manager = ShutdownManager()
        execution_order = []

        def failing_task():
            raise ValueError("Non-critical failure")

        def task2():
            execution_order.append("task2")

        def task3():
            execution_order.append("task3")

        manager.register_cleanup("fail", failing_task, priority=100, critical=False)
        manager.register_cleanup("task2", task2, priority=50, critical=False)
        manager.register_cleanup("task3", task3, priority=10, critical=False)

        stats = await manager.shutdown()

        # Both remaining tasks should execute
        assert "task2" in execution_order
        assert "task3" in execution_order
        assert stats.tasks_failed == 1
        assert stats.tasks_executed == 2

    @pytest.mark.asyncio
    async def test_multiple_failures_tracked_individually(self) -> None:
        """Should track each failure individually."""
        manager = ShutdownManager()

        def fail1():
            raise RuntimeError("Fail 1")

        def fail2():
            raise ValueError("Fail 2")

        def success():
            pass

        manager.register_cleanup("fail1", fail1, priority=100, critical=False)
        manager.register_cleanup("fail2", fail2, priority=50, critical=False)
        manager.register_cleanup("success", success, priority=10, critical=False)

        stats = await manager.shutdown()

        assert stats.tasks_failed == 2
        assert stats.tasks_executed == 1


# ==============================================================================
# Concurrent Shutdown Tests
# ==============================================================================

class TestConcurrentShutdown:
    """Test concurrent shutdown request handling."""

    @pytest.mark.asyncio
    async def test_prevent_multiple_simultaneous_shutdowns(self) -> None:
        """Should prevent multiple simultaneous shutdowns."""
        manager = ShutdownManager()
        shutdown_count = [0]

        async def track_shutdown():
            shutdown_count[0] += 1
            await asyncio.sleep(0.1)  # Simulate work

        manager.register_cleanup("track", track_shutdown)

        # Start two shutdowns concurrently
        results = await asyncio.gather(
            manager.shutdown(),
            manager.shutdown(),
        )

        # Should only execute once
        assert shutdown_count[0] == 1

        # Both should return same stats
        assert results[0] is results[1]

    @pytest.mark.asyncio
    async def test_second_shutdown_returns_immediately(self) -> None:
        """Should return immediately on second concurrent shutdown."""
        manager = ShutdownManager()
        execution_times = []

        async def slow_cleanup():
            await asyncio.sleep(0.3)
            execution_times.append(time.perf_counter())

        manager.register_cleanup("slow", slow_cleanup)

        start = time.perf_counter()

        # Start two shutdowns with small delay using create_task
        async def delayed_shutdown():
            await asyncio.sleep(0.01)
            return await manager.shutdown()

        results = await asyncio.gather(
            manager.shutdown(),
            delayed_shutdown(),
        )

        end = time.perf_counter()

        # Total time should be close to single shutdown duration
        # (not double), since second one returns immediately
        total_duration = end - start
        assert total_duration < 0.5  # Should be less than double sleep

    @pytest.mark.asyncio
    async def test_shutdown_initiated_flag_after_concurrent_access(self) -> None:
        """Should correctly track shutdown state after concurrent access."""
        manager = ShutdownManager()

        async def cleanup():
            await asyncio.sleep(0.1)

        manager.register_cleanup("test", cleanup)

        # Trigger multiple concurrent shutdowns
        await asyncio.gather(
            manager.shutdown(),
            manager.shutdown(),
            manager.shutdown(),
        )

        assert manager.is_shutdown_initiated() is True


# ==============================================================================
# Graceful vs Force Shutdown Tests
# ==============================================================================

class TestGracefulVsForceShutdown:
    """Test different shutdown modes."""

    @pytest.mark.asyncio
    async def test_graceful_shutdown_executes_all_tasks(self) -> None:
        """Graceful shutdown should execute all tasks in order."""
        manager = ShutdownManager()
        execution_order = []

        for i in range(5):
            def make_task(n):
                def task():
                    execution_order.append(n)
                return task
            manager.register_cleanup(f"task_{i}", make_task(i), priority=i)

        stats = await manager.shutdown()

        assert stats.tasks_executed == 5
        assert len(execution_order) == 5

    @pytest.mark.asyncio
    async def test_shutdown_respects_critical_flag(self) -> None:
        """Should stop early if critical task fails/times out."""
        manager = ShutdownManager()
        executed = []

        manager.register_cleanup(
            "critical_stop", lambda: (_ for _ in ()).throw(RuntimeError("Stop")),
            priority=100,
            critical=True,
        )
        manager.register_cleanup("after_stop", lambda: executed.append("after"), priority=10)

        stats = await manager.shutdown()

        assert "after" not in executed
        assert stats.tasks_executed == 0
        assert stats.tasks_failed == 1


# ==============================================================================
# Resource Finalization Tests
# ==============================================================================

class TestResourceFinalization:
    """Test resource cleanup and finalization."""

    @pytest.mark.asyncio
    async def test_file_resources_cleaned_up(self) -> None:
        """Should properly clean up file resources."""
        manager = ShutdownManager()
        temp_files = []

        def create_and_register_temp_file():
            # Create temp file
            f = tempfile.NamedTemporaryFile(delete=False)
            temp_files.append(f.name)
            f.close()
            return f.name

        def cleanup_file():
            import os
            name = create_and_register_temp_file()
            if os.path.exists(name):
                os.unlink(name)

        manager.register_cleanup("file_cleanup", cleanup_file)

        stats = await manager.shutdown()

        # All temp files should be cleaned
        import os
        for temp_file in temp_files:
            assert not os.path.exists(temp_file), f"Temp file {temp_file} was not cleaned"

    @pytest.mark.asyncio
    async def test_multiple_resources_finalized(self) -> None:
        """Should finalize multiple different resources."""
        manager = ShutdownManager()
        cleanup_order = []

        def resource_a():
            cleanup_order.append("resource_a")

        def resource_b():
            cleanup_order.append("resource_b")

        def resource_c():
            cleanup_order.append("resource_c")

        manager.register_cleanup("res_a", resource_a, priority=30)
        manager.register_cleanup("res_b", resource_b, priority=20)
        manager.register_cleanup("res_c", resource_c, priority=10)

        await manager.shutdown()

        assert cleanup_order == ["resource_a", "resource_b", "resource_c"]

    @pytest.mark.asyncio
    async def test_zombie_resource_prevention(self) -> None:
        """Should prevent zombie resources by running all cleanups."""
        manager = ShutdownManager()
        resources_cleaned = []

        # Simulate resources that need cleanup
        for i in range(10):
            def make_cleanup(n):
                def cleanup():
                    resources_cleaned.append(n)
                return cleanup
            manager.register_cleanup(f"resource_{i}", make_cleanup(i), priority=i)

        stats = await manager.shutdown()

        # All resources should be cleaned
        assert len(resources_cleaned) == 10
        assert stats.tasks_executed == 10


# ==============================================================================
# Interrupted Shutdown Tests
# ==============================================================================

class TestInterruptedShutdown:
    """Test shutdown interruption handling."""

    @pytest.mark.asyncio
    async def test_shutdown_can_be_interrupted_by_critical_failure(self) -> None:
        """Should stop shutdown sequence on critical failure."""
        manager = ShutdownManager()
        executed = []

        def critical_fail():
            executed.append("critical_start")
            raise RuntimeError("Critical failure")

        def after_critical():
            executed.append("after_critical")

        manager.register_cleanup("critical", critical_fail, priority=100, critical=True)
        manager.register_cleanup("after", after_critical, priority=50, critical=False)

        await manager.shutdown()

        # Only first task should execute
        assert executed == ["critical_start"]
        assert "after_critical" not in executed

    @pytest.mark.asyncio
    async def test_shutdown_with_partial_failure_and_continue(self) -> None:
        """Should continue after non-critical failures."""
        manager = ShutdownManager()
        execution_order = []

        def fail_once():
            if "fail_attempted" not in execution_order:
                execution_order.append("fail_attempted")
                raise RuntimeError("First failure")
            execution_order.append("fail_recovered")

        def succeed():
            execution_order.append("success")

        manager.register_cleanup("fail", fail_once, priority=100, critical=False)
        manager.register_cleanup("succeed", succeed, priority=50, critical=False)

        stats = await manager.shutdown()

        # Should have attempted fail and succeeded
        assert "fail_attempted" in execution_order
        assert "success" in execution_order
        assert stats.tasks_failed == 1


# ==============================================================================
# Internal Method Tests
# ==============================================================================

class TestInternalMethods:
    """Test internal ShutdownManager methods."""

    @pytest.mark.asyncio
    async def test_execute_cleanup_task_for_async(self) -> None:
        """Should execute async cleanup task correctly."""
        manager = ShutdownManager()
        executed = []

        async def async_task():
            executed.append("async_done")

        task = CleanupTask(
            name="test_async",
            callback=async_task,
            priority=10,
            timeout_seconds=5.0,
            critical=False,
        )

        await manager._execute_cleanup_task(task)

        assert "async_done" in executed

    @pytest.mark.asyncio
    async def test_execute_cleanup_task_for_sync(self) -> None:
        """Should execute sync cleanup task correctly."""
        manager = ShutdownManager()
        executed = []

        def sync_task():
            executed.append("sync_done")

        task = CleanupTask(
            name="test_sync",
            callback=sync_task,
            priority=10,
            timeout_seconds=5.0,
            critical=False,
        )

        await manager._execute_cleanup_task(task)

        assert "sync_done" in executed

    @pytest.mark.asyncio
    async def test_execute_cleanup_task_timeout(self) -> None:
        """Should raise TimeoutError when task times out."""
        manager = ShutdownManager()

        async def slow_task():
            await asyncio.sleep(10.0)

        task = CleanupTask(
            name="timeout_task",
            callback=slow_task,
            priority=10,
            timeout_seconds=0.1,
            critical=False,
        )

        with pytest.raises(TimeoutError):
            await manager._execute_cleanup_task(task)

    def test_handle_task_timeout_returns_true_for_critical(self) -> None:
        """Should return True for critical task timeout."""
        manager = ShutdownManager()

        task = CleanupTask(
            name="critical_timeout",
            callback=lambda: None,
            priority=10,
            timeout_seconds=0.1,
            critical=True,
        )

        result = manager._handle_task_timeout(task)

        assert result is True
        assert manager._stats.tasks_timeout == 1

    def test_handle_task_timeout_returns_false_for_non_critical(self) -> None:
        """Should return False for non-critical task timeout."""
        manager = ShutdownManager()

        task = CleanupTask(
            name="non_critical_timeout",
            callback=lambda: None,
            priority=10,
            timeout_seconds=0.1,
            critical=False,
        )

        result = manager._handle_task_timeout(task)

        assert result is False
        assert manager._stats.tasks_timeout == 1

    def test_handle_task_failure_returns_true_for_critical(self) -> None:
        """Should return True for critical task failure."""
        manager = ShutdownManager()

        task = CleanupTask(
            name="critical_fail",
            callback=lambda: None,
            priority=10,
            timeout_seconds=30.0,
            critical=True,
        )

        result = manager._handle_task_failure(task, RuntimeError("Test error"))

        assert result is True
        assert manager._stats.tasks_failed == 1

    def test_handle_task_failure_returns_false_for_non_critical(self) -> None:
        """Should return False for non-critical task failure."""
        manager = ShutdownManager()

        task = CleanupTask(
            name="non_critical_fail",
            callback=lambda: None,
            priority=10,
            timeout_seconds=30.0,
            critical=False,
        )

        result = manager._handle_task_failure(task, RuntimeError("Test error"))

        assert result is False
        assert manager._stats.tasks_failed == 1

    def test_finalize_shutdown_updates_stats(self) -> None:
        """Should update stats with final duration."""
        manager = ShutdownManager()

        tasks = [
            CleanupTask(name="t1", callback=lambda: None, priority=10),
            CleanupTask(name="t2", callback=lambda: None, priority=5),
        ]

        start = time.perf_counter() - 0.1  # 100ms ago

        manager._finalize_shutdown(tasks, start)

        assert manager._stats.total_duration_ms >= 100

    def test_finalize_shutdown_logs_warning_on_failures(self) -> None:
        """Should log warning when there are failures."""
        manager = ShutdownManager()
        manager._stats.tasks_failed = 2
        manager._stats.tasks_timeout = 1

        tasks = [CleanupTask(name="t1", callback=lambda: None, priority=10)]

        with patch("session_buddy.shutdown_manager._get_logger") as mock_logger:
            manager._finalize_shutdown(tasks, time.perf_counter())

            # Should have logged warning
            mock_logger().warning.assert_called()


# ==============================================================================
# Atexit Handler Tests
# ==============================================================================

class TestAtexitHandler:
    """Test atexit handler behavior."""

    def test_atexit_handler_runs_when_not_shutdown(self) -> None:
        """Should run shutdown when atexit triggered without prior shutdown."""
        manager = ShutdownManager()
        executed = []

        def cleanup():
            executed.append("atexit_cleanup")

        manager.register_cleanup("atexit", cleanup)

        # Simulate atexit call
        manager._atexit_handler()

        # Give async operation time to complete
        time.sleep(0.1)

        assert "atexit_cleanup" in executed

    def test_atexit_handler_skips_when_already_shutdown(self) -> None:
        """Should skip shutdown when already initiated and not log."""
        manager = ShutdownManager()
        executed = []

        def cleanup():
            executed.append("cleanup")

        manager.register_cleanup("test", cleanup)

        # First shutdown
        import asyncio as aio
        aio.run(manager.shutdown())

        # Verify shutdown was already initiated
        assert manager._shutdown_initiated is True

        # Now simulate atexit - should skip silently since already shutdown
        with patch("session_buddy.shutdown_manager._get_logger") as mock_logger:
            manager._atexit_handler()

            # Should NOT log info because shutdown is already initiated
            mock_logger().info.assert_not_called()

    def test_atexit_handler_handles_runtime_error(self) -> None:
        """Should handle RuntimeError from asyncio.run."""
        manager = ShutdownManager()
        executed = []

        def cleanup():
            executed.append("cleanup")

        manager.register_cleanup("test", cleanup)

        # Simulate scenario where asyncio.run might fail
        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = RuntimeError("No event loop")

            # Should use suppress to handle gracefully
            with patch("session_buddy.shutdown_manager._get_logger"):
                manager._atexit_handler()  # Should not raise


# ==============================================================================
# Stats Access Tests
# ==============================================================================

class TestStatsAccess:
    """Test stats retrieval."""

    def test_get_stats_returns_current_stats(self) -> None:
        """Should return current stats object."""
        manager = ShutdownManager()

        manager.register_cleanup("task1", lambda: None)
        manager.register_cleanup("task2", lambda: None)

        stats = manager.get_stats()

        assert stats.tasks_registered == 2
        assert isinstance(stats, ShutdownStats)

    def test_get_stats_returns_same_object(self) -> None:
        """Should return same stats object reference."""
        manager = ShutdownManager()

        stats1 = manager.get_stats()
        stats2 = manager.get_stats()

        assert stats1 is stats2  # Same reference


# ==============================================================================
# Global Singleton Tests
# ==============================================================================

class TestGlobalShutdownManager:
    """Test global shutdown manager singleton."""

    def test_get_shutdown_manager_returns_singleton(self) -> None:
        """Should return same instance each time."""
        # Reset global for test
        import session_buddy.shutdown_manager as sm
        sm._global_shutdown_manager = None

        mgr1 = get_shutdown_manager()
        mgr2 = get_shutdown_manager()

        assert mgr1 is mgr2

    def test_global_manager_is_shutdown_manager_instance(self) -> None:
        """Should return ShutdownManager instance."""
        mgr = get_shutdown_manager()

        assert isinstance(mgr, ShutdownManager)

    def test_global_manager_persists_across_calls(self) -> None:
        """Should persist same instance across multiple calls."""
        import session_buddy.shutdown_manager as sm
        sm._global_shutdown_manager = None

        mgr1 = get_shutdown_manager()
        mgr2 = get_shutdown_manager()
        mgr3 = get_shutdown_manager()

        assert mgr1 is mgr2
        assert mgr2 is mgr3


# ==============================================================================
# Edge Cases and Error Conditions
# ==============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_cleanup_task_with_exception_in_callback(self) -> None:
        """Should handle exceptions in cleanup callbacks."""
        manager = ShutdownManager()

        def exceptional_cleanup():
            raise RuntimeError("Callback exception")

        manager.register_cleanup("exceptional", exceptional_cleanup, critical=False)

        stats = await manager.shutdown()

        assert stats.tasks_failed == 1

    @pytest.mark.asyncio
    async def test_shutdown_with_lambda_callbacks(self) -> None:
        """Should work with lambda callbacks."""
        manager = ShutdownManager()
        result = []

        manager.register_cleanup("lambda1", lambda: result.append(1))
        manager.register_cleanup("lambda2", lambda: result.append(2))

        stats = await manager.shutdown()

        assert result == [1, 2]
        assert stats.tasks_executed == 2

    @pytest.mark.asyncio
    async def test_shutdown_with_partial_coroutine_failure(self) -> None:
        """Should handle partial coroutine failures."""
        manager = ShutdownManager()
        execution_order = []

        async def async_fail():
            execution_order.append("async_fail_start")
            await asyncio.sleep(0.01)
            raise RuntimeError("Async failure")

        def sync_after():
            execution_order.append("sync_after")

        manager.register_cleanup("async_fail", async_fail, priority=100, critical=False)
        manager.register_cleanup("sync_after", sync_after, priority=50, critical=False)

        stats = await manager.shutdown()

        # Should have attempted async and then sync
        assert "async_fail_start" in execution_order
        assert "sync_after" in execution_order
        assert stats.tasks_failed == 1

    def test_signal_handler_with_sigint(self) -> None:
        """Should handle SIGINT signal correctly."""
        manager = ShutdownManager()
        executed = []

        def cleanup():
            executed.append("sigint_cleanup")

        manager.register_cleanup("sigint_test", cleanup)

        # Call signal handler with SIGINT
        manager._signal_handler(signal.SIGINT, None)

        # Give time for async execution
        time.sleep(0.2)

        assert "sigint_cleanup" in executed

    @pytest.mark.asyncio
    async def test_priority_equal_executes_in_registration_order(self) -> None:
        """When priorities equal, should execute in registration order."""
        manager = ShutdownManager()
        execution_order = []

        manager.register_cleanup("first", lambda: execution_order.append("first"), priority=50)
        manager.register_cleanup("second", lambda: execution_order.append("second"), priority=50)
        manager.register_cleanup("third", lambda: execution_order.append("third"), priority=50)

        await manager.shutdown()

        # Within same priority, earlier registration comes first
        assert execution_order == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self) -> None:
        """Calling shutdown multiple times should be safe."""
        manager = ShutdownManager()
        execution_count = 0

        def counting_cleanup():
            nonlocal execution_count
            execution_count += 1

        manager.register_cleanup("counting", counting_cleanup)

        # Call shutdown multiple times
        await manager.shutdown()
        await manager.shutdown()
        await manager.shutdown()

        # Should only execute once
        assert execution_count == 1

    @pytest.mark.asyncio
    async def test_empty_name_task_registration(self) -> None:
        """Should allow tasks with empty names."""
        manager = ShutdownManager()

        manager.register_cleanup("", lambda: None)

        assert len(manager._cleanup_tasks) == 1
        assert manager._cleanup_tasks[0].name == ""


# ==============================================================================
# Integration-style Tests
# ==============================================================================

class TestIntegration:
    """Integration-style tests for full shutdown scenarios."""

    @pytest.mark.asyncio
    async def test_full_graceful_shutdown_sequence(self) -> None:
        """Test complete graceful shutdown with all features."""
        manager = ShutdownManager()
        cleanup_sequence = []

        # Register various cleanup tasks
        def db_close():
            cleanup_sequence.append("db_close")

        async def cache_flush():
            await asyncio.sleep(0.01)
            cleanup_sequence.append("cache_flush")

        def file_save():
            cleanup_sequence.append("file_save")

        def metrics_report():
            cleanup_sequence.append("metrics_report")

        manager.register_cleanup("db", db_close, priority=100, critical=True)
        manager.register_cleanup("cache", cache_flush, priority=80, critical=False)
        manager.register_cleanup("file", file_save, priority=50, critical=False)
        manager.register_cleanup("metrics", metrics_report, priority=20, critical=False)

        stats = await manager.shutdown()

        # All tasks should execute in priority order
        assert cleanup_sequence == ["db_close", "cache_flush", "file_save", "metrics_report"]
        assert stats.tasks_executed == 4
        assert stats.tasks_failed == 0
        assert stats.tasks_timeout == 0
        assert manager.is_shutdown_initiated() is True

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_failures(self) -> None:
        """Test graceful shutdown with some task failures."""
        manager = ShutdownManager()
        executed = []

        def fail_db():
            raise RuntimeError("DB failure")

        def cleanup_cache():
            executed.append("cache")

        def cleanup_metrics():
            executed.append("metrics")

        manager.register_cleanup("db", fail_db, priority=100, critical=True)
        manager.register_cleanup("cache", cleanup_cache, priority=80, critical=False)
        manager.register_cleanup("metrics", cleanup_metrics, priority=50, critical=False)

        stats = await manager.shutdown()

        # Critical failure stops cleanup
        assert "cache" not in executed
        assert "metrics" not in executed
        assert stats.tasks_failed == 1
        assert stats.tasks_executed == 0

    @pytest.mark.asyncio
    async def test_signal_initiated_shutdown_sequence(self) -> None:
        """Test shutdown sequence initiated by signal handler."""
        manager = ShutdownManager()
        cleanup_done = []

        async def cleanup_task():
            cleanup_done.append("signal_cleanup")

        manager.register_cleanup("signal_test", cleanup_task)

        # Simulate signal handler invocation
        manager._signal_handler(signal.SIGTERM, None)

        # Wait for async shutdown to complete
        await asyncio.sleep(0.2)

        assert "signal_cleanup" in cleanup_done
        assert manager.is_shutdown_initiated() is True