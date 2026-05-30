#!/usr/bin/env python3
"""Unit tests for HooksManager class."""

import asyncio
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.hooks import (
    DefaultCodeFormatter,
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

    @pytest.mark.asyncio
    async def test_default_code_formatter_is_no_op(self):
        """Test the fallback code formatter returns success."""
        formatter = DefaultCodeFormatter()
        assert await formatter.format_file(Path("example.py")) is True

    @pytest.mark.asyncio
    async def test_initialize_registers_default_hooks(self, monkeypatch: pytest.MonkeyPatch):
        """Test initialize wires up tracker, engine, and built-in hooks."""
        manager = HooksManager()

        fake_tracker = MagicMock()
        fake_tracker.initialize = AsyncMock()

        fake_engine = MagicMock()
        fake_engine.initialize = AsyncMock()

        class FakeTracker:
            def __init__(self, logger):
                self.logger = logger

            async def initialize(self):
                await fake_tracker.initialize()

        class FakeEngine:
            def __init__(self):
                pass

            async def initialize(self):
                await fake_engine.initialize()

        monkeypatch.setitem(
            sys.modules,
            "session_buddy.core.causal_chains",
            SimpleNamespace(CausalChainTracker=FakeTracker),
        )
        monkeypatch.setitem(
            sys.modules,
            "session_buddy.core.intelligence",
            SimpleNamespace(IntelligenceEngine=FakeEngine),
        )

        await manager.initialize()

        assert manager._causal_tracker is not None
        assert manager._intelligence_engine is not None
        assert HookType.POST_FILE_EDIT in manager._hooks
        assert HookType.PRE_CHECKPOINT in manager._hooks
        assert HookType.POST_CHECKPOINT in manager._hooks
        assert HookType.POST_ERROR in manager._hooks
        fake_tracker.initialize.assert_awaited_once()
        fake_engine.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_handles_intelligence_engine_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Test intelligence engine initialization failure fallback."""
        manager = HooksManager()

        class FakeTracker:
            def __init__(self, logger):
                self.logger = logger

            async def initialize(self):
                return None

        class FakeEngine:
            def __init__(self):
                raise RuntimeError("boom")

        monkeypatch.setitem(
            sys.modules,
            "session_buddy.core.causal_chains",
            SimpleNamespace(CausalChainTracker=FakeTracker),
        )
        monkeypatch.setitem(
            sys.modules,
            "session_buddy.core.intelligence",
            SimpleNamespace(IntelligenceEngine=FakeEngine),
        )

        await manager.initialize()

        assert manager._causal_tracker is not None
        assert manager._intelligence_engine is None


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

    @pytest.mark.asyncio
    async def test_execute_hooks_disabled_and_error_handler_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Test disabled hooks are skipped and error handler failures are logged."""
        manager = HooksManager()

        async def failing_handler(ctx: HookContext) -> HookResult:
            raise ValueError("Hook failed")

        async def bad_error_handler(exc: Exception) -> None:
            raise RuntimeError("error handler failed")

        disabled_called = False

        async def disabled_handler(ctx: HookContext) -> HookResult:
            nonlocal disabled_called
            disabled_called = True
            return HookResult(success=True)

        await manager.register_hook(
            Hook(
                name="failing",
                hook_type=HookType.POST_CHECKPOINT,
                priority=10,
                handler=failing_handler,
                error_handler=bad_error_handler,
            )
        )
        await manager.register_hook(
            Hook(
                name="disabled",
                hook_type=HookType.POST_CHECKPOINT,
                priority=20,
                handler=disabled_handler,
                enabled=False,
            )
        )

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, _make_context())

        assert len(results) == 1
        assert results[0].success is False
        assert disabled_called is False


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

    @pytest.mark.asyncio
    async def test_auto_format_handler_paths(self):
        """Test auto format handler no-op, success, and exception paths."""
        manager = HooksManager(formatter=DefaultCodeFormatter())

        no_file = HookContext(
            hook_type=HookType.POST_FILE_EDIT,
            session_id="s",
            timestamp=datetime.now(UTC),
        )
        assert (await manager._auto_format_handler(no_file)).success is True

        not_py = HookContext(
            hook_type=HookType.POST_FILE_EDIT,
            session_id="s",
            timestamp=datetime.now(UTC),
            file_path="/tmp/test.txt",
        )
        assert (await manager._auto_format_handler(not_py)).success is True

        formatter = MagicMock()
        formatter.format_file = AsyncMock(return_value=False)
        manager = HooksManager(formatter=formatter)
        py_context = HookContext(
            hook_type=HookType.POST_FILE_EDIT,
            session_id="s",
            timestamp=datetime.now(UTC),
            file_path="/tmp/test.py",
        )
        assert (await manager._auto_format_handler(py_context)).success is False
        formatter.format_file.assert_awaited_once()

        async def boom(*args, **kwargs):
            raise RuntimeError("format failed")

        formatter = MagicMock()
        formatter.format_file = AsyncMock(side_effect=boom)
        manager = HooksManager(formatter=formatter)
        result = await manager._auto_format_handler(py_context)
        assert result.success is False
        assert "format failed" in result.error

    @pytest.mark.asyncio
    async def test_quality_validation_branches(self):
        """Test quality validation low and high score paths."""
        manager = HooksManager()
        low = HookContext(
            hook_type=HookType.PRE_CHECKPOINT,
            session_id="s",
            timestamp=datetime.now(UTC),
            checkpoint_data={"quality_score": 59},
        )
        high = HookContext(
            hook_type=HookType.PRE_CHECKPOINT,
            session_id="s",
            timestamp=datetime.now(UTC),
            checkpoint_data={"quality_score": 60},
        )

        low_result = await manager._quality_validation_handler(low)
        high_result = await manager._quality_validation_handler(high)

        assert low_result.success is False
        assert "Quality too low" in low_result.error
        assert high_result.success is True
        assert high_result.modified_context == {"validated_quality": 60}

    @pytest.mark.asyncio
    async def test_pattern_learning_paths(self, monkeypatch: pytest.MonkeyPatch):
        """Test pattern learning when engine is absent, successful, and failing."""
        manager = HooksManager()
        context = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="s",
            timestamp=datetime.now(UTC),
            checkpoint_data={"quality_score": 90},
        )

        assert (await manager._pattern_learning_handler(context)).success is True

        class FakeEngine:
            def __init__(self, result=None, boom=False):
                self.result = result or []
                self.boom = boom

            async def learn_from_checkpoint(self, checkpoint):
                if self.boom:
                    raise RuntimeError("learn failed")
                return self.result

        manager._intelligence_engine = FakeEngine(result=["p1", "p2"])
        assert (await manager._pattern_learning_handler(context)).success is True

        manager._intelligence_engine = FakeEngine(result=[])
        assert (await manager._pattern_learning_handler(context)).success is True

        manager._intelligence_engine = FakeEngine(boom=True)
        assert (await manager._pattern_learning_handler(context)).success is True

    @pytest.mark.asyncio
    async def test_causal_chain_handler_paths(self):
        """Test causal chain handler no-op, success, and failure paths."""
        manager = HooksManager()
        base = HookContext(
            hook_type=HookType.POST_ERROR,
            session_id="s",
            timestamp=datetime.now(UTC),
        )
        assert (await manager._causal_chain_handler(base)).success is True

        class FakeTracker:
            async def record_error_event(self, error, context, session_id):
                return "chain-123"

        manager._causal_tracker = FakeTracker()
        error_ctx = HookContext(
            hook_type=HookType.POST_ERROR,
            session_id="s",
            timestamp=datetime.now(UTC),
            error_info={"error_message": "boom", "context": {"x": 1}},
        )
        ok = await manager._causal_chain_handler(error_ctx)
        assert ok.success is True
        assert ok.causal_chain_id == "chain-123"

        class BoomTracker:
            async def record_error_event(self, error, context, session_id):
                raise RuntimeError("tracker failed")

        manager._causal_tracker = BoomTracker()
        failed = await manager._causal_chain_handler(error_ctx)
        assert failed.success is False
        assert "tracker failed" in failed.error

    @pytest.mark.asyncio
    async def test_workflow_metrics_paths(self, monkeypatch: pytest.MonkeyPatch):
        """Test workflow metrics handler success and fallback paths."""
        manager = HooksManager()
        context = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="s",
            timestamp=datetime.now(UTC),
            checkpoint_data={},
        )
        context_with_start = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="s",
            timestamp=datetime.now(UTC),
            checkpoint_data={
                "session_start_time": datetime.now(UTC),
                "working_directory": "/tmp/work",
            },
        )

        class FakeEngine:
            def __init__(self):
                self.initialized = False
                self.calls = []

            async def initialize(self):
                self.initialized = True

            async def collect_session_metrics(self, **kwargs):
                self.calls.append(kwargs)

        fake_engine = FakeEngine()
        monkeypatch.setitem(
            sys.modules,
            "session_buddy.core.workflow_metrics",
            SimpleNamespace(get_workflow_metrics_engine=lambda: fake_engine),
        )

        result = await manager._workflow_metrics_handler(context)
        assert result.success is True
        assert fake_engine.initialized is True
        assert fake_engine.calls[0]["session_id"] == "s"
        assert fake_engine.calls[0]["started_at"] == fake_engine.calls[0]["checkpoint_data"].get("timestamp", fake_engine.calls[0]["started_at"])

        fake_engine.calls.clear()
        result = await manager._workflow_metrics_handler(context_with_start)
        assert result.success is True
        assert fake_engine.calls[0]["started_at"] == context_with_start.checkpoint_data["session_start_time"]

        class BoomEngine(FakeEngine):
            async def collect_session_metrics(self, **kwargs):
                raise RuntimeError("metrics failed")

        monkeypatch.setitem(
            sys.modules,
            "session_buddy.core.workflow_metrics",
            SimpleNamespace(get_workflow_metrics_engine=lambda: BoomEngine()),
        )
        assert (await manager._workflow_metrics_handler(context)).success is True


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
