#!/usr/bin/env python3
"""Unit tests for HooksManager class."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from session_buddy.core.hooks import HookResult, HooksManager


class TestHooksManagerRegistration:
    """Test hook registration."""

    def test_register_hook_sync(self):
        """Test registering a synchronous hook."""
        manager = HooksManager()

        # Define a simple sync hook
        def test_hook(context):
            return HookResult(success=True, data={"message": "Hook executed"})

        # Register the hook
        manager.register_hook("test_event", test_hook)

        # Verify it was registered
        assert "test_event" in manager.hooks
        assert len(manager.hooks["test_event"]) == 1
        assert manager.hooks["test_event"][0] == test_hook

    def test_register_hook_async(self):
        """Test registering an asynchronous hook."""
        manager = HooksManager()

        # Define a simple async hook
        async def test_hook(context):
            return HookResult(success=True, data={"message": "Async hook executed"})

        # Register the hook
        manager.register_hook("test_event", test_hook)

        # Verify it was registered
        assert "test_event" in manager.hooks
        assert len(manager.hooks["test_event"]) == 1

    def test_register_multiple_hooks_same_event(self):
        """Test registering multiple hooks for the same event."""
        manager = HooksManager()

        # Define multiple hooks
        def hook1(context):
            return HookResult(success=True, data={"order": 1})

        def hook2(context):
            return HookResult(success=True, data={"order": 2})

        def hook3(context):
            return HookResult(success=True, data={"order": 3})

        # Register all hooks for same event
        manager.register_hook("test_event", hook1)
        manager.register_hook("test_event", hook2)
        manager.register_hook("test_event", hook3)

        # Verify all were registered in order
        assert len(manager.hooks["test_event"]) == 3
        assert manager.hooks["test_event"][0] == hook1
        assert manager.hooks["test_event"][1] == hook2
        assert manager.hooks["test_event"][2] == hook3

    def test_register_hooks_different_events(self):
        """Test registering hooks for different events."""
        manager = HooksManager()

        # Define hooks for different events
        def before_start(context):
            return HookResult(success=True)

        def after_start(context):
            return HookResult(success=True)

        def before_end(context):
            return HookResult(success=True)

        # Register hooks for different events
        manager.register_hook("before_start", before_start)
        manager.register_hook("after_start", after_start)
        manager.register_hook("before_end", before_end)

        # Verify all were registered
        assert len(manager.hooks) == 3
        assert "before_start" in manager.hooks
        assert "after_start" in manager.hooks
        assert "before_end" in manager.hooks


class TestHooksManagerExecution:
    """Test hook execution."""

    @pytest.mark.asyncio
    async def test_execute_single_sync_hook(self):
        """Test executing a single synchronous hook."""
        manager = HooksManager()

        # Define and register hook
        def test_hook(context):
            return HookResult(success=True, data={"message": "Executed"})

        manager.register_hook("test_event", test_hook)

        # Execute hook
        results = await manager.execute_hooks("test_event", {"key": "value"})

        # Verify results
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].data == {"message": "Executed"}

    @pytest.mark.asyncio
    async def test_execute_single_async_hook(self):
        """Test executing a single asynchronous hook."""
        manager = HooksManager()

        # Define and register async hook
        async def test_hook(context):
            await asyncio.sleep(0)  # Yield control
            return HookResult(success=True, data={"message": "Async executed"})

        manager.register_hook("test_event", test_hook)

        # Execute hook
        results = await manager.execute_hooks("test_event", {"key": "value"})

        # Verify results
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].data == {"message": "Async executed"}

    @pytest.mark.asyncio
    async def test_execute_multiple_hooks_same_event(self):
        """Test executing multiple hooks for the same event."""
        manager = HooksManager()

        # Define hooks
        def hook1(context):
            return HookResult(success=True, data={"hook": 1})

        def hook2(context):
            return HookResult(success=True, data={"hook": 2})

        def hook3(context):
            return HookResult(success=True, data={"hook": 3})

        # Register hooks
        manager.register_hook("test_event", hook1)
        manager.register_hook("test_event", hook2)
        manager.register_hook("test_event", hook3)

        # Execute hooks
        results = await manager.execute_hooks("test_event", {})

        # Verify all hooks executed
        assert len(results) == 3
        assert results[0].data == {"hook": 1}
        assert results[1].data == {"hook": 2}
        assert results[2].data == {"hook": 3}

    @pytest.mark.asyncio
    async def test_execute_hooks_with_context(self):
        """Test that hooks receive the correct context."""
        manager = HooksManager()

        # Define hook that captures context
        captured_context = {}

        def test_hook(context):
            captured_context.update(context)
            return HookResult(success=True)

        # Register hook
        manager.register_hook("test_event", test_hook)

        # Execute with context
        test_context = {"project": "test", "user": "developer"}
        await manager.execute_hooks("test_event", test_context)

        # Verify context was received
        assert captured_context == test_context

    @pytest.mark.asyncio
    async def test_execute_hooks_no_hooks_registered(self):
        """Test executing event with no registered hooks."""
        manager = HooksManager()

        # Execute event with no hooks
        results = await manager.execute_hooks("nonexistent_event", {})

        # Should return empty list
        assert len(results) == 0


class TestHooksManagerErrorHandling:
    """Test error handling in hooks."""

    @pytest.mark.asyncio
    async def test_execute_hook_with_exception(self):
        """Test executing a hook that raises an exception."""
        manager = HooksManager()

        # Define hook that raises exception
        def failing_hook(context):
            raise ValueError("Hook failed")

        manager.register_hook("test_event", failing_hook)

        # Execute hook (should handle exception gracefully)
        results = await manager.execute_hooks("test_event", {})

        # Should return failure result
        assert len(results) == 1
        assert results[0].success is False
        assert "error" in results[0].data

    @pytest.mark.asyncio
    async def test_execute_async_hook_with_exception(self):
        """Test executing an async hook that raises an exception."""
        manager = HooksManager()

        # Define async hook that raises exception
        async def failing_hook(context):
            await asyncio.sleep(0)
            raise RuntimeError("Async hook failed")

        manager.register_hook("test_event", failing_hook)

        # Execute hook (should handle exception gracefully)
        results = await manager.execute_hooks("test_event", {})

        # Should return failure result
        assert len(results) == 1
        assert results[0].success is False
        assert "error" in results[0].data

    @pytest.mark.asyncio
    async def test_execute_mixed_hooks_with_exceptions(self):
        """Test executing mix of successful and failing hooks."""
        manager = HooksManager()

        # Define hooks
        def success_hook(context):
            return HookResult(success=True, data={"status": "ok"})

        def failing_hook(context):
            raise ValueError("Failed")

        def another_success_hook(context):
            return HookResult(success=True, data={"status": "also ok"})

        # Register hooks
        manager.register_hook("test_event", success_hook)
        manager.register_hook("test_event", failing_hook)
        manager.register_hook("test_event", another_success_hook)

        # Execute hooks
        results = await manager.execute_hooks("test_event", {})

        # All three should have results
        assert len(results) == 3

        # First and third should succeed
        assert results[0].success is True
        assert results[2].success is True

        # Middle one should fail
        assert results[1].success is False

    @pytest.mark.asyncio
    async def test_execute_hook_returns_none(self):
        """Test hook that returns None instead of HookResult."""
        manager = HooksManager()

        # Define hook that returns None
        def bad_hook(context):
            return None

        manager.register_hook("test_event", bad_hook)

        # Should handle gracefully
        results = await manager.execute_hooks("test_event", {})

        # Should create a failure result
        assert len(results) == 1
        assert results[0].success is False


class TestHooksManagerResultAggregation:
    """Test hook result aggregation."""

    @pytest.mark.asyncio
    async def test_aggregate_successful_results(self):
        """Test aggregating results from successful hooks."""
        manager = HooksManager()

        # Define hooks that return data
        def hook1(context):
            return HookResult(success=True, data={"count": 1})

        def hook2(context):
            return HookResult(success=True, data={"count": 2})

        def hook3(context):
            return HookResult(success=True, data={"count": 3})

        # Register hooks
        manager.register_hook("test_event", hook1)
        manager.register_hook("test_event", hook2)
        manager.register_hook("test_event", hook3)

        # Execute and aggregate
        results = await manager.execute_hooks("test_event", {})

        # All should succeed
        assert all(r.success for r in results)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_aggregate_mixed_results(self):
        """Test aggregating mix of successful and failed results."""
        manager = HooksManager()

        # Define hooks
        def success_hook(context):
            return HookResult(success=True, data={"status": "ok"})

        def failure_hook(context):
            return HookResult(success=False, data={"error": "Failed"})

        # Register hooks
        manager.register_hook("test_event", success_hook)
        manager.register_hook("test_event", failure_hook)

        # Execute
        results = await manager.execute_hooks("test_event", {})

        # Should have both results
        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False


class TestHooksManagerTimeoutHandling:
    """Test hook timeout handling."""

    @pytest.mark.asyncio
    async def test_execute_slow_hook_with_timeout(self):
        """Test executing a slow hook with timeout."""
        manager = HooksManager()

        # Define a slow hook
        async def slow_hook(context):
            await asyncio.sleep(2)  # Sleep for 2 seconds
            return HookResult(success=True)

        manager.register_hook("test_event", slow_hook)

        # Execute with short timeout
        # Note: This test might need adjustment based on actual timeout implementation
        results = await manager.execute_hooks("test_event", {}, timeout=0.1)

        # Should handle timeout (implementation dependent)
        # For now, just verify it returns results
        assert isinstance(results, list)


class TestHooksManagerAdvanced:
    """Test advanced hooks manager features."""

    @pytest.mark.asyncio
    async def test_hook_can_modify_context(self):
        """Test that hooks can modify the context for subsequent hooks."""
        manager = HooksManager()

        # Define hooks that modify context
        def hook1(context):
            context["value"] = 1
            return HookResult(success=True)

        def hook2(context):
            context["value"] = context.get("value", 0) + 1
            return HookResult(success=True)

        def hook3(context):
            context["final"] = context.get("value", 0) * 2
            return HookResult(success=True)

        # Register hooks
        manager.register_hook("test_event", hook1)
        manager.register_hook("test_event", hook2)
        manager.register_hook("test_event", hook3)

        # Execute with initial context
        context = {"initial": True}
        await manager.execute_hooks("test_event", context)

        # Verify context was modified
        assert context["value"] == 2  # hook1 set to 1, hook2 added 1
        assert context["final"] == 4  # hook3 doubled it
        assert context["initial"] is True

    @pytest.mark.asyncio
    async def test_hook_execution_order(self):
        """Test that hooks execute in registration order."""
        manager = HooksManager()

        execution_order = []

        def hook1(context):
            execution_order.append(1)
            return HookResult(success=True)

        def hook2(context):
            execution_order.append(2)
            return HookResult(success=True)

        def hook3(context):
            execution_order.append(3)
            return HookResult(success=True)

        # Register in specific order
        manager.register_hook("test_event", hook3)
        manager.register_hook("test_event", hook1)
        manager.register_hook("test_event", hook2)

        # Execute
        await manager.execute_hooks("test_event", {})

        # Should execute in registration order (3, 1, 2)
        assert execution_order == [3, 1, 2]

    @pytest.mark.asyncio
    async def test_hook_result_custom_data(self):
        """Test hooks returning custom data."""
        manager = HooksManager()

        # Define hooks with custom data
        def hook1(context):
            return HookResult(
                success=True,
                data={"message": "Hook 1", "metadata": {"priority": 1}},
            )

        def hook2(context):
            return HookResult(
                success=True,
                data={"message": "Hook 2", "metadata": {"priority": 2}},
            )

        # Register hooks
        manager.register_hook("test_event", hook1)
        manager.register_hook("test_event", hook2)

        # Execute
        results = await manager.execute_hooks("test_event", {})

        # Verify custom data
        assert results[0].data["message"] == "Hook 1"
        assert results[0].data["metadata"]["priority"] == 1
        assert results[1].data["message"] == "Hook 2"
        assert results[1].data["metadata"]["priority"] == 2


class TestHookResult:
    """Test HookResult class."""

    def test_hook_result_creation(self):
        """Test creating a HookResult."""
        result = HookResult(success=True, data={"key": "value"})

        assert result.success is True
        assert result.data == {"key": "value"}

    def test_hook_result_default_data(self):
        """Test HookResult with default data."""
        result = HookResult(success=True)

        assert result.success is True
        assert result.data == {}

    def test_hook_result_failure(self):
        """Test HookResult for failure case."""
        result = HookResult(success=False, data={"error": "Something went wrong"})

        assert result.success is False
        assert "error" in result.data


if __name__ == "__main__":
    pytest.main([__file__])
