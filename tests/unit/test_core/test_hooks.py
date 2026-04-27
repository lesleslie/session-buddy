#!/usr/bin/env python3
"""Unit tests for HooksManager class."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from session_buddy.core.hooks import (
    Hook,
    HookContext,
    HookResult,
    HookType,
    HooksManager,
)


def _make_context(
    hook_type: HookType = HookType.POST_CHECKPOINT,
    session_id: str = "test-session",
) -> HookContext:
    """Create a HookContext for testing."""
    return HookContext(
        hook_type=hook_type,
        session_id=session_id,
        timestamp=datetime.now(UTC),
    )


class TestHooksManagerRegistration:
    """Test hook registration."""

    @pytest.mark.asyncio
    async def test_register_hook(self):
        """Test registering a hook via Hook dataclass."""
        manager = HooksManager()

        async def handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True)

        hook = Hook(
            name="test_hook",
            hook_type=HookType.POST_CHECKPOINT,
            priority=100,
            handler=handler,
        )
        await manager.register_hook(hook)

        # Verify it was registered
        assert HookType.POST_CHECKPOINT in manager._hooks
        assert len(manager._hooks[HookType.POST_CHECKPOINT]) == 1
        assert manager._hooks[HookType.POST_CHECKPOINT][0].name == "test_hook"

    @pytest.mark.asyncio
    async def test_register_multiple_hooks_same_type(self):
        """Test registering multiple hooks for the same HookType."""
        manager = HooksManager()

        async def handler1(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"order": 1})

        async def handler2(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"order": 2})

        async def handler3(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"order": 3})

        await manager.register_hook(
            Hook(name="hook1", hook_type=HookType.POST_CHECKPOINT, priority=30, handler=handler3)
        )
        await manager.register_hook(
            Hook(name="hook2", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler1)
        )
        await manager.register_hook(
            Hook(name="hook3", hook_type=HookType.POST_CHECKPOINT, priority=20, handler=handler2)
        )

        # Verify all registered in priority order (10, 20, 30)
        hooks = manager._hooks[HookType.POST_CHECKPOINT]
        assert len(hooks) == 3
        assert hooks[0].name == "hook2"  # priority 10
        assert hooks[1].name == "hook3"  # priority 20
        assert hooks[2].name == "hook1"  # priority 30

    @pytest.mark.asyncio
    async def test_register_hooks_different_types(self):
        """Test registering hooks for different HookTypes."""
        manager = HooksManager()

        async def handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True)

        await manager.register_hook(
            Hook(name="h1", hook_type=HookType.PRE_CHECKPOINT, priority=10, handler=handler)
        )
        await manager.register_hook(
            Hook(name="h2", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler)
        )
        await manager.register_hook(
            Hook(name="h3", hook_type=HookType.POST_FILE_EDIT, priority=10, handler=handler)
        )

        # Verify all were registered
        assert len(manager._hooks) == 3
        assert HookType.PRE_CHECKPOINT in manager._hooks
        assert HookType.POST_CHECKPOINT in manager._hooks
        assert HookType.POST_FILE_EDIT in manager._hooks

    @pytest.mark.asyncio
    async def test_replace_existing_hook(self):
        """Test that registering a hook with the same name replaces it."""
        manager = HooksManager()

        async def handler1(ctx: HookContext) -> HookResult:
            return HookResult(success=True)

        async def handler2(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"replaced": True})

        await manager.register_hook(
            Hook(name="same_name", hook_type=HookType.POST_CHECKPOINT, priority=100, handler=handler1)
        )
        await manager.register_hook(
            Hook(name="same_name", hook_type=HookType.POST_CHECKPOINT, priority=50, handler=handler2)
        )

        hooks = manager._hooks[HookType.POST_CHECKPOINT]
        assert len(hooks) == 1
        assert hooks[0].priority == 50


class TestHooksManagerExecution:
    """Test hook execution."""

    @pytest.mark.asyncio
    async def test_execute_single_hook(self):
        """Test executing a single hook."""
        manager = HooksManager()

        async def handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"message": "Executed"})

        await manager.register_hook(
            Hook(name="test_hook", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler)
        )

        context = _make_context()
        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, context)

        assert len(results) == 1
        assert results[0].success is True
        assert context.metadata["message"] == "Executed"

    @pytest.mark.asyncio
    async def test_execute_multiple_hooks(self):
        """Test executing multiple hooks for the same type."""
        manager = HooksManager()

        async def handler1(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"hook": 1})

        async def handler2(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"hook": 2})

        async def handler3(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"hook": 3})

        await manager.register_hook(
            Hook(name="h1", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler1)
        )
        await manager.register_hook(
            Hook(name="h2", hook_type=HookType.POST_CHECKPOINT, priority=20, handler=handler2)
        )
        await manager.register_hook(
            Hook(name="h3", hook_type=HookType.POST_CHECKPOINT, priority=30, handler=handler3)
        )

        context = _make_context()
        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, context)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_execute_hooks_passes_context(self):
        """Test that hooks receive the correct context."""
        manager = HooksManager()

        captured_context: HookContext | None = None

        async def handler(ctx: HookContext) -> HookResult:
            nonlocal captured_context
            captured_context = ctx
            return HookResult(success=True)

        await manager.register_hook(
            Hook(name="ctx_hook", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler)
        )

        test_context = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="session-123",
            timestamp=datetime.now(UTC),
            metadata={"project": "test", "user": "developer"},
        )
        await manager.execute_hooks(HookType.POST_CHECKPOINT, test_context)

        assert captured_context is test_context
        assert captured_context.session_id == "session-123"
        assert captured_context.metadata["project"] == "test"

    @pytest.mark.asyncio
    async def test_execute_hooks_no_hooks_registered(self):
        """Test executing event with no registered hooks."""
        manager = HooksManager()

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert results == []


class TestHooksManagerErrorHandling:
    """Test error handling in hooks."""

    @pytest.mark.asyncio
    async def test_execute_hook_with_exception(self):
        """Test executing a hook that raises an exception."""
        manager = HooksManager()

        async def failing_handler(ctx: HookContext) -> HookResult:
            raise ValueError("Hook failed")

        await manager.register_hook(
            Hook(name="failing", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=failing_handler)
        )

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error == "Hook failed"

    @pytest.mark.asyncio
    async def test_execute_async_hook_with_exception(self):
        """Test executing an async hook that raises an exception."""
        manager = HooksManager()

        async def failing_handler(ctx: HookContext) -> HookResult:
            await asyncio.sleep(0)
            raise RuntimeError("Async hook failed")

        await manager.register_hook(
            Hook(name="async_failing", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=failing_handler)
        )

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert len(results) == 1
        assert results[0].success is False
        assert "Async hook failed" in results[0].error

    @pytest.mark.asyncio
    async def test_execute_mixed_hooks_with_exceptions(self):
        """Test executing mix of successful and failing hooks."""
        manager = HooksManager()

        async def success_handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"status": "ok"})

        async def failing_handler(ctx: HookContext) -> HookResult:
            raise ValueError("Failed")

        async def another_success_handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"status": "also ok"})

        await manager.register_hook(
            Hook(name="s1", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=success_handler)
        )
        await manager.register_hook(
            Hook(name="f1", hook_type=HookType.POST_CHECKPOINT, priority=20, handler=failing_handler)
        )
        await manager.register_hook(
            Hook(name="s2", hook_type=HookType.POST_CHECKPOINT, priority=30, handler=another_success_handler)
        )

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    @pytest.mark.asyncio
    async def test_hook_error_handler_called(self):
        """Test that a hook's error_handler is invoked on failure."""
        manager = HooksManager()

        error_handler_mock = AsyncMock()

        async def failing_handler(ctx: HookContext) -> HookResult:
            raise ValueError("Boom")

        await manager.register_hook(
            Hook(
                name="with_error_handler",
                hook_type=HookType.POST_CHECKPOINT,
                priority=10,
                handler=failing_handler,
                error_handler=error_handler_mock,
            )
        )

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert len(results) == 1
        assert results[0].success is False
        error_handler_mock.assert_called_once()
        assert isinstance(error_handler_mock.call_args[0][0], ValueError)


class TestHooksManagerResultAggregation:
    """Test hook result aggregation."""

    @pytest.mark.asyncio
    async def test_aggregate_successful_results(self):
        """Test aggregating results from successful hooks."""
        manager = HooksManager()

        async def handler1(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"count": 1})

        async def handler2(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"count": 2})

        async def handler3(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"count": 3})

        await manager.register_hook(
            Hook(name="h1", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler1)
        )
        await manager.register_hook(
            Hook(name="h2", hook_type=HookType.POST_CHECKPOINT, priority=20, handler=handler2)
        )
        await manager.register_hook(
            Hook(name="h3", hook_type=HookType.POST_CHECKPOINT, priority=30, handler=handler3)
        )

        context = _make_context()
        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, context)

        assert all(r.success for r in results)
        assert len(results) == 3
        # Last hook's modified_context wins for "count" key
        assert context.metadata["count"] == 3

    @pytest.mark.asyncio
    async def test_aggregate_mixed_results(self):
        """Test aggregating mix of successful and failed results."""
        manager = HooksManager()

        async def success_handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"status": "ok"})

        async def failure_handler(ctx: HookContext) -> HookResult:
            return HookResult(success=False, error="Failed")

        await manager.register_hook(
            Hook(name="s1", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=success_handler)
        )
        await manager.register_hook(
            Hook(name="f1", hook_type=HookType.POST_CHECKPOINT, priority=20, handler=failure_handler)
        )

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False
        assert results[1].error == "Failed"


class TestHooksManagerExecutionOrder:
    """Test hook execution ordering."""

    @pytest.mark.asyncio
    async def test_hooks_execute_in_priority_order(self):
        """Test that hooks execute in priority order (lower first)."""
        manager = HooksManager()

        execution_order: list[str] = []

        async def handler_a(ctx: HookContext) -> HookResult:
            execution_order.append("a")
            return HookResult(success=True)

        async def handler_b(ctx: HookContext) -> HookResult:
            execution_order.append("b")
            return HookResult(success=True)

        async def handler_c(ctx: HookContext) -> HookResult:
            execution_order.append("c")
            return HookResult(success=True)

        # Register in reverse priority order
        await manager.register_hook(
            Hook(name="c", hook_type=HookType.POST_CHECKPOINT, priority=300, handler=handler_c)
        )
        await manager.register_hook(
            Hook(name="a", hook_type=HookType.POST_CHECKPOINT, priority=100, handler=handler_a)
        )
        await manager.register_hook(
            Hook(name="b", hook_type=HookType.POST_CHECKPOINT, priority=200, handler=handler_b)
        )

        await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert execution_order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_disabled_hooks_are_skipped(self):
        """Test that disabled hooks are not executed."""
        manager = HooksManager()

        execution_order: list[str] = []

        async def handler_a(ctx: HookContext) -> HookResult:
            execution_order.append("a")
            return HookResult(success=True)

        async def handler_b(ctx: HookContext) -> HookResult:
            execution_order.append("b")
            return HookResult(success=True)

        await manager.register_hook(
            Hook(name="a", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler_a)
        )
        await manager.register_hook(
            Hook(name="b", hook_type=HookType.POST_CHECKPOINT, priority=20, handler=handler_b, enabled=False)
        )

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert len(results) == 1
        assert execution_order == ["a"]


class TestHooksManagerContextModification:
    """Test context modification by hooks."""

    @pytest.mark.asyncio
    async def test_hook_can_modify_context(self):
        """Test that hooks can modify context metadata for subsequent hooks."""
        manager = HooksManager()

        async def handler1(ctx: HookContext) -> HookResult:
            ctx.metadata["value"] = 1
            return HookResult(success=True)

        async def handler2(ctx: HookContext) -> HookResult:
            ctx.metadata["value"] = ctx.metadata.get("value", 0) + 1
            return HookResult(success=True)

        async def handler3(ctx: HookContext) -> HookResult:
            ctx.metadata["final"] = ctx.metadata.get("value", 0) * 2
            return HookResult(success=True)

        await manager.register_hook(
            Hook(name="h1", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler1)
        )
        await manager.register_hook(
            Hook(name="h2", hook_type=HookType.POST_CHECKPOINT, priority=20, handler=handler2)
        )
        await manager.register_hook(
            Hook(name="h3", hook_type=HookType.POST_CHECKPOINT, priority=30, handler=handler3)
        )

        context = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="test-session",
            timestamp=datetime.now(UTC),
            metadata={"initial": True},
        )
        await manager.execute_hooks(HookType.POST_CHECKPOINT, context)

        assert context.metadata["value"] == 2  # h1 set to 1, h2 added 1
        assert context.metadata["final"] == 4  # h3 doubled it
        assert context.metadata["initial"] is True


class TestHookResult:
    """Test HookResult class."""

    def test_hook_result_creation(self):
        """Test creating a HookResult."""
        result = HookResult(success=True, modified_context={"key": "value"})

        assert result.success is True
        assert result.modified_context == {"key": "value"}

    def test_hook_result_defaults(self):
        """Test HookResult default values."""
        result = HookResult(success=True)

        assert result.success is True
        assert result.modified_context is None
        assert result.error is None
        assert result.execution_time_ms == 0.0
        assert result.causal_chain_id is None

    def test_hook_result_failure(self):
        """Test HookResult for failure case."""
        result = HookResult(success=False, error="Something went wrong")

        assert result.success is False
        assert result.error == "Something went wrong"


class TestHookContext:
    """Test HookContext class."""

    def test_hook_context_creation(self):
        """Test creating a HookContext."""
        ctx = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="session-123",
            timestamp=datetime.now(UTC),
            metadata={"key": "value"},
        )

        assert ctx.hook_type == HookType.POST_CHECKPOINT
        assert ctx.session_id == "session-123"
        assert ctx.metadata == {"key": "value"}

    def test_hook_context_error_info(self):
        """Test HookContext with error_info."""
        ctx = HookContext(
            hook_type=HookType.POST_ERROR,
            session_id="session-123",
            timestamp=datetime.now(UTC),
            error_info={"error_message": "test error", "context": {}},
        )

        assert ctx.error_info["error_message"] == "test error"

    def test_hook_context_file_path(self):
        """Test HookContext with file_path."""
        ctx = HookContext(
            hook_type=HookType.POST_FILE_EDIT,
            session_id="session-123",
            timestamp=datetime.now(UTC),
            file_path="/tmp/test.py",
        )

        assert ctx.file_path == "/tmp/test.py"


class TestHookType:
    """Test HookType enum."""

    def test_hook_type_values(self):
        """Test HookType enum has expected values."""
        assert HookType.PRE_CHECKPOINT == "pre_checkpoint"
        assert HookType.POST_CHECKPOINT == "post_checkpoint"
        assert HookType.POST_FILE_EDIT == "post_file_edit"
        assert HookType.POST_ERROR == "post_error"
        assert HookType.SESSION_START == "session_start"
        assert HookType.SESSION_END == "session_end"


class TestHooksManagerListHooks:
    """Test list_hooks method."""

    @pytest.mark.asyncio
    async def test_list_hooks_all(self):
        """Test listing all registered hooks."""
        manager = HooksManager()

        async def handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True)

        await manager.register_hook(
            Hook(name="h1", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler, metadata={"tag": "a"})
        )
        await manager.register_hook(
            Hook(name="h2", hook_type=HookType.PRE_CHECKPOINT, priority=20, handler=handler)
        )

        result = manager.list_hooks()

        assert HookType.POST_CHECKPOINT in result
        assert HookType.PRE_CHECKPOINT in result
        assert len(result[HookType.POST_CHECKPOINT]) == 1
        assert result[HookType.POST_CHECKPOINT][0]["name"] == "h1"
        assert result[HookType.POST_CHECKPOINT][0]["metadata"] == {"tag": "a"}

    @pytest.mark.asyncio
    async def test_list_hooks_filtered(self):
        """Test listing hooks filtered by type."""
        manager = HooksManager()

        async def handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True)

        await manager.register_hook(
            Hook(name="h1", hook_type=HookType.POST_CHECKPOINT, priority=10, handler=handler)
        )
        await manager.register_hook(
            Hook(name="h2", hook_type=HookType.PRE_CHECKPOINT, priority=20, handler=handler)
        )

        result = manager.list_hooks(hook_type=HookType.POST_CHECKPOINT)

        assert len(result) == 1
        assert HookType.POST_CHECKPOINT in result
        assert HookType.PRE_CHECKPOINT not in result

    @pytest.mark.asyncio
    async def test_list_hooks_empty(self):
        """Test listing hooks when none are registered."""
        manager = HooksManager()

        result = manager.list_hooks()

        assert result == {}


if __name__ == "__main__":
    pytest.main([__file__])
