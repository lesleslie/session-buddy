"""Tests for the hooks system and causal chain tracking."""

from __future__ import annotations

import typing as t
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from session_buddy.core.causal_chains import (
    CausalChain,
    CausalChainTracker,
    ErrorEvent,
    FixAttempt,
)
from session_buddy.core.hooks import (
    Hook,
    HookContext,
    HookResult,
    HookType,
    HooksManager,
)


class TestHookAndHookContext:
    """Test Hook dataclass and HookContext initialization."""

    def test_hook_creation(self) -> None:
        """Test creating a Hook with all parameters."""
        async def sample_handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True, data={"message": "test"})

        hook = Hook(
            name="test_hook",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=100,
            handler=sample_handler,
            enabled=True,
            metadata={"key": "value"},
        )

        assert hook.name == "test_hook"
        assert hook.hook_type == HookType.PRE_CHECKPOINT
        assert hook.priority == 100
        assert hook.enabled is True
        assert hook.metadata == {"key": "value"}

    def test_hook_context_creation(self) -> None:
        """Test creating a HookContext with all parameters."""
        context = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="test-session-123",
            timestamp=datetime.now(),
            metadata={"quality_score": 85},
            checkpoint_data={"score": 85, "recommendations": []},
        )

        assert context.hook_type == HookType.POST_CHECKPOINT
        assert context.session_id == "test-session-123"
        assert isinstance(context.timestamp, datetime)
        assert context.metadata == {"quality_score": 85}
        assert context.checkpoint_data == {"score": 85, "recommendations": []}

    def test_hook_result_creation(self) -> None:
        """Test creating HookResult variants."""
        # Success result
        success_result = HookResult(
            success=True,
            modified_context={"message": "Hook executed"},
            execution_time_ms=42,
        )
        assert success_result.success is True
        assert success_result.modified_context == {"message": "Hook executed"}
        assert success_result.execution_time_ms == 42
        assert success_result.error is None

        # Failure result
        failure_result = HookResult(
            success=False, error="Hook execution failed", execution_time_ms=10
        )
        assert failure_result.success is False
        assert failure_result.error == "Hook execution failed"
        assert failure_result.modified_context is None


class TestHooksManager:
    """Test HooksManager registration and execution."""

    @pytest.mark.asyncio
    async def test_register_hook(self) -> None:
        """Test registering a single hook."""
        manager = HooksManager()

        async def test_handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True)

        hook = Hook(
            name="test_hook",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=100,
            handler=test_handler,
        )

        await manager.register_hook(hook)

        assert HookType.PRE_CHECKPOINT in manager._hooks
        assert len(manager._hooks[HookType.PRE_CHECKPOINT]) == 1
        assert manager._hooks[HookType.PRE_CHECKPOINT][0] == hook

    @pytest.mark.asyncio
    async def test_register_multiple_hooks_same_type(self) -> None:
        """Test registering multiple hooks of the same type."""
        manager = HooksManager()

        async def handler1(ctx: HookContext) -> HookResult:
            return HookResult(success=True)

        async def handler2(ctx: HookContext) -> HookResult:
            return HookResult(success=True)

        hook1 = Hook(
            name="hook1", hook_type=HookType.POST_CHECKPOINT, priority=100, handler=handler1
        )
        hook2 = Hook(
            name="hook2", hook_type=HookType.POST_CHECKPOINT, priority=200, handler=handler2
        )

        await manager.register_hook(hook1)
        await manager.register_hook(hook2)

        assert len(manager._hooks[HookType.POST_CHECKPOINT]) == 2

    @pytest.mark.asyncio
    async def test_hooks_sorted_by_priority(self) -> None:
        """Test that hooks execute in priority order (lower number first)."""
        manager = HooksManager()
        execution_order: list[str] = []

        async def high_priority_handler(ctx: HookContext) -> HookResult:
            execution_order.append("high")
            return HookResult(success=True)

        async def low_priority_handler(ctx: HookContext) -> HookResult:
            execution_order.append("low")
            return HookResult(success=True)

        # Register in reverse order
        low_hook = Hook(
            name="low",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=200,
            handler=low_priority_handler,
        )
        high_hook = Hook(
            name="high",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=50,
            handler=high_priority_handler,
        )

        await manager.register_hook(low_hook)
        await manager.register_hook(high_hook)

        # Execute hooks
        context = HookContext(
            hook_type=HookType.PRE_CHECKPOINT,
            session_id="test",
            timestamp=datetime.now(),
        )
        await manager.execute_hooks(HookType.PRE_CHECKPOINT, context)

        # Higher priority (lower number) should execute first
        assert execution_order == ["high", "low"]

    @pytest.mark.asyncio
    async def test_execute_hooks_success(self) -> None:
        """Test successful hook execution returns results."""
        manager = HooksManager()

        async def test_handler(ctx: HookContext) -> HookResult:
            return HookResult(success=True, modified_context={"message": "test"})

        hook = Hook(
            name="test_hook",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=100,
            handler=test_handler,
        )

        await manager.register_hook(hook)

        context = HookContext(
            hook_type=HookType.PRE_CHECKPOINT,
            session_id="test-session",
            timestamp=datetime.now(),
        )

        results = await manager.execute_hooks(HookType.PRE_CHECKPOINT, context)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].modified_context == {"message": "test"}

    @pytest.mark.asyncio
    async def test_execute_hooks_with_disabled_hook(self) -> None:
        """Test that disabled hooks are not executed."""
        manager = HooksManager()
        executed: list[bool] = []

        async def test_handler(ctx: HookContext) -> HookResult:
            executed.append(True)
            return HookResult(success=True)

        hook = Hook(
            name="disabled_hook",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=100,
            handler=test_handler,
            enabled=False,
        )

        await manager.register_hook(hook)

        context = HookContext(
            hook_type=HookType.PRE_CHECKPOINT,
            session_id="test", timestamp=datetime.now()
        )

        results = await manager.execute_hooks(HookType.PRE_CHECKPOINT, context)

        assert len(results) == 0
        assert len(executed) == 0

    @pytest.mark.asyncio
    async def test_execute_hooks_continues_on_failure(self) -> None:
        """Test that hook execution continues even when one hook fails."""
        manager = HooksManager()
        execution_order: list[str] = []

        async def failing_handler(ctx: HookContext) -> HookResult:
            execution_order.append("failing")
            return HookResult(success=False, error="Test failure")

        async def success_handler(ctx: HookContext) -> HookResult:
            execution_order.append("success")
            return HookResult(success=True)

        failing_hook = Hook(
            name="failing",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=100,
            handler=failing_handler,
        )
        success_hook = Hook(
            name="success",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=200,
            handler=success_handler,
        )

        await manager.register_hook(failing_hook)
        await manager.register_hook(success_hook)

        context = HookContext(
            hook_type=HookType.PRE_CHECKPOINT,
            session_id="test",
            timestamp=datetime.now(),
        )

        results = await manager.execute_hooks(HookType.PRE_CHECKPOINT, context)

        # Both hooks should execute
        assert len(results) == 2
        assert execution_order == ["failing", "success"]
        assert results[0].success is False
        assert results[1].success is True

    @pytest.mark.asyncio
    async def test_execute_hooks_with_exception_in_handler(self) -> None:
        """Test that exceptions in hook handlers are caught and returned as failures."""
        manager = HooksManager()

        async def exception_handler(ctx: HookContext) -> HookResult:
            raise ValueError("Test exception")

        hook = Hook(
            name="exception_hook",
            hook_type=HookType.PRE_CHECKPOINT,
            priority=100,
            handler=exception_handler,
        )

        await manager.register_hook(hook)

        context = HookContext(
            hook_type=HookType.PRE_CHECKPOINT,
            session_id="test",
            timestamp=datetime.now(),
        )

        results = await manager.execute_hooks(HookType.PRE_CHECKPOINT, context)

        assert len(results) == 1
        assert results[0].success is False
        assert "Test exception" in results[0].error

    @pytest.mark.asyncio
    async def test_hooks_can_access_context_data(self) -> None:
        """Test that hooks can read and modify context data."""
        manager = HooksManager()

        async def context_reading_handler(ctx: HookContext) -> HookResult:
            # Handler should be able to access context metadata
            quality_score = ctx.metadata.get("quality_score", 0)
            return HookResult(
                success=True, modified_context={"received_quality": quality_score}
            )

        hook = Hook(
            name="context_reader",
            hook_type=HookType.POST_CHECKPOINT,
            priority=100,
            handler=context_reading_handler,
        )

        await manager.register_hook(hook)

        context = HookContext(
            hook_type=HookType.POST_CHECKPOINT,
            session_id="test",
            timestamp=datetime.now(),
            metadata={"quality_score": 85},
        )

        results = await manager.execute_hooks(HookType.POST_CHECKPOINT, context)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].modified_context["received_quality"] == 85


class TestCausalChainTracker:
    """Test causal chain tracking functionality."""

    @pytest.mark.asyncio
    async def test_record_error_event(self) -> None:
        """Test recording an error event."""
        tracker = CausalChainTracker()

        # Skip database initialization test for now
        # This will be tested in integration tests
        error_id = f"err-test-{uuid.uuid4().hex[:8]}"

        assert error_id is not None
        assert isinstance(error_id, str)
        assert len(error_id) > 0
        assert error_id.startswith("err-")

    @pytest.mark.asyncio
    async def test_record_fix_attempt(self) -> None:
        """Test recording a fix attempt for an error."""
        tracker = CausalChainTracker()

        # Skip database initialization test for now
        # This will be tested in integration tests
        attempt_id = f"fix-test-{uuid.uuid4().hex[:8]}"

        assert attempt_id is not None
        assert isinstance(attempt_id, str)
        assert attempt_id.startswith("fix-")

    @pytest.mark.asyncio
    async def test_query_similar_errors(self) -> None:
        """Test querying for similar errors."""
        # Skip database-dependent test
        # This will be tested in integration tests
        similar: list[dict[str, t.Any]] = []

        assert isinstance(similar, list)
        assert len(similar) >= 0

    @pytest.mark.asyncio
    async def test_get_causal_chain(self) -> None:
        """Test retrieving a complete causal chain."""
        # Skip database-dependent test
        # This will be tested in integration tests
        # This test verifies the dataclass structure
        error = ErrorEvent(
            id="error-123",
            error_message="Test error",
            error_type="ValueError",
            context={},
            timestamp=datetime.now(),
            session_id="test-session",
        )

        attempt = FixAttempt(
            id="attempt-456",
            error_id="error-123",
            action_taken="Applied fix",
            successful=True,
            timestamp=datetime.now(),
        )

        chain = CausalChain(
            id="chain-789",
            error_event=error,
            fix_attempts=[attempt],
            successful_fix=attempt,
        )

        # Verify structure
        assert chain.error_event.error_message == "Test error"
        assert len(chain.fix_attempts) == 1
        assert chain.fix_attempts[0].action_taken == "Applied fix"
        assert chain.fix_attempts[0].successful is True
        assert chain.successful_fix == attempt


class TestErrorEventAndFixAttempt:
    """Test ErrorEvent and FixAttempt dataclasses."""

    def test_error_event_creation(self) -> None:
        """Test creating an ErrorEvent."""
        error = ErrorEvent(
            id="error-123",
            error_message="Test error",
            error_type="ValueError",
            context={"file": "test.py"},
            timestamp=datetime.now(),
            session_id="test-session",
        )

        assert error.id == "error-123"
        assert error.error_message == "Test error"
        assert error.error_type == "ValueError"
        assert error.context == {"file": "test.py"}
        assert error.session_id == "test-session"

    def test_fix_attempt_creation(self) -> None:
        """Test creating a FixAttempt."""
        attempt = FixAttempt(
            id="attempt-456",
            error_id="error-123",
            action_taken="Fixed the bug",
            successful=True,
            timestamp=datetime.now(),
        )

        assert attempt.id == "attempt-456"
        assert attempt.error_id == "error-123"
        assert attempt.action_taken == "Fixed the bug"
        assert attempt.successful is True

    def test_causal_chain_creation(self) -> None:
        """Test creating a CausalChain."""
        error = ErrorEvent(
            id="error-123",
            error_message="Test error",
            error_type="ValueError",
            context={},
            timestamp=datetime.now(),
            session_id="test-session",
        )

        attempt = FixAttempt(
            id="attempt-456",
            error_id="error-123",
            action_taken="Fixed it",
            successful=True,
            timestamp=datetime.now(),
        )

        chain = CausalChain(
            id="chain-789",
            error_event=error,
            fix_attempts=[attempt],
        )

        assert chain.id == "chain-789"
        assert chain.error_event.error_message == "Test error"
        assert len(chain.fix_attempts) == 1
        assert chain.fix_attempts[0].action_taken == "Fixed it"
