"""Integration tests for core systems working together.

Tests that hooks, causal chains, intelligence, and workflow metrics
integrate correctly as a unified system.

Phase: Pre-Phase 5 - Integration Verification
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.hooks import (
    Hook,
    HookContext,
    HookResult,
    HooksManager,
    HookType,
)


class TestHooksManagerInitialization:
    """Test HooksManager initializes with CausalChainTracker."""

    @pytest.mark.asyncio
    async def test_hooks_manager_creates_causal_tracker(self) -> None:
        """HooksManager.initialize() should create CausalChainTracker."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker_instance = AsyncMock()
            MockTracker.return_value = mock_tracker_instance

            await manager.initialize()

            # Verify CausalChainTracker was created and initialized
            MockTracker.assert_called_once()
            mock_tracker_instance.initialize.assert_called_once()
            assert manager._causal_tracker is mock_tracker_instance

    @pytest.mark.asyncio
    async def test_hooks_manager_registers_default_hooks(self) -> None:
        """HooksManager.initialize() should register all default hooks."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker_instance = AsyncMock()
            MockTracker.return_value = mock_tracker_instance

            await manager.initialize()

            # Verify all 5 default hooks were registered
            all_hooks = manager.list_hooks()

            # Check for expected hook types
            assert HookType.POST_FILE_EDIT in all_hooks
            assert HookType.PRE_CHECKPOINT in all_hooks
            assert HookType.POST_CHECKPOINT in all_hooks
            assert HookType.POST_ERROR in all_hooks

            # Check specific hook names
            post_checkpoint_hooks = [
                h["name"] for h in all_hooks.get(HookType.POST_CHECKPOINT, [])
            ]
            assert "learn_from_checkpoint" in post_checkpoint_hooks
            assert "collect_workflow_metrics" in post_checkpoint_hooks

            post_error_hooks = [
                h["name"] for h in all_hooks.get(HookType.POST_ERROR, [])
            ]
            assert "track_error_fix_chain" in post_error_hooks


class TestCausalChainIntegration:
    """Test hooks system integration with causal chain tracking."""

    @pytest.mark.asyncio
    async def test_post_error_hook_triggers_causal_tracking(self) -> None:
        """POST_ERROR hook should call CausalChainTracker.record_error_event()."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            mock_tracker.record_error_event.return_value = "err-12345678"
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            # Create error context
            error_context = HookContext(
                hook_type=HookType.POST_ERROR,
                session_id="test-session-123",
                timestamp=datetime.now(UTC),
                error_info={
                    "error_message": "ImportError: module not found",
                    "context": {"file": "main.py", "line": 42},
                },
            )

            # Execute POST_ERROR hooks
            results = await manager.execute_hooks(
                HookType.POST_ERROR, error_context
            )

            # Verify causal chain tracking was called
            assert len(results) >= 1
            assert any(r.success for r in results)

            # Verify record_error_event was called with correct args
            mock_tracker.record_error_event.assert_called_once()
            call_args = mock_tracker.record_error_event.call_args
            assert call_args.kwargs["error"] == "ImportError: module not found"
            assert call_args.kwargs["session_id"] == "test-session-123"

    @pytest.mark.asyncio
    async def test_post_error_hook_returns_chain_id(self) -> None:
        """POST_ERROR hook should return causal_chain_id in result."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            mock_tracker.record_error_event.return_value = "err-abcd1234"
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            error_context = HookContext(
                hook_type=HookType.POST_ERROR,
                session_id="test-session",
                timestamp=datetime.now(UTC),
                error_info={
                    "error_message": "TypeError: expected string",
                    "context": {},
                },
            )

            results = await manager.execute_hooks(
                HookType.POST_ERROR, error_context
            )

            # Find the causal chain hook result
            causal_result = next(
                (r for r in results if r.causal_chain_id), None
            )
            assert causal_result is not None
            assert causal_result.causal_chain_id == "err-abcd1234"

    @pytest.mark.asyncio
    async def test_post_error_hook_handles_missing_tracker(self) -> None:
        """POST_ERROR hook should succeed gracefully without tracker."""
        manager = HooksManager()

        # Initialize without mocking (tracker will fail to initialize)
        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            mock_tracker.record_error_event.side_effect = Exception(
                "DB unavailable"
            )
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            error_context = HookContext(
                hook_type=HookType.POST_ERROR,
                session_id="test-session",
                timestamp=datetime.now(UTC),
                error_info={"error_message": "Test error", "context": {}},
            )

            # Should not raise, should handle gracefully
            results = await manager.execute_hooks(
                HookType.POST_ERROR, error_context
            )

            # Hook should return failure but not crash
            assert len(results) >= 1


class TestWorkflowMetricsIntegration:
    """Test hooks system integration with workflow metrics."""

    @pytest.mark.asyncio
    async def test_post_checkpoint_triggers_metrics_collection(self) -> None:
        """POST_CHECKPOINT hook should trigger workflow metrics collection."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            # Mock workflow metrics engine
            with patch(
                "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
            ) as mock_get_engine:
                mock_engine = AsyncMock()
                mock_get_engine.return_value = mock_engine

                checkpoint_context = HookContext(
                    hook_type=HookType.POST_CHECKPOINT,
                    session_id="session-456",
                    timestamp=datetime.now(UTC),
                    checkpoint_data={
                        "quality_score": 85,
                        "working_directory": "/path/to/project",
                        "session_start_time": datetime.now(UTC)
                        - timedelta(hours=1),
                        "timestamp": datetime.now(UTC),
                    },
                )

                results = await manager.execute_hooks(
                    HookType.POST_CHECKPOINT, checkpoint_context
                )

                # Verify metrics collection was triggered
                mock_engine.initialize.assert_called()
                mock_engine.collect_session_metrics.assert_called_once()

                # Verify correct session_id passed
                call_kwargs = mock_engine.collect_session_metrics.call_args.kwargs
                assert call_kwargs["session_id"] == "session-456"
                assert call_kwargs["project_path"] == "/path/to/project"

    @pytest.mark.asyncio
    async def test_metrics_collection_failure_does_not_fail_checkpoint(
        self,
    ) -> None:
        """Workflow metrics failure should not fail the checkpoint hook."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            with patch(
                "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
            ) as mock_get_engine:
                mock_engine = AsyncMock()
                mock_engine.collect_session_metrics.side_effect = Exception(
                    "Metrics DB error"
                )
                mock_get_engine.return_value = mock_engine

                checkpoint_context = HookContext(
                    hook_type=HookType.POST_CHECKPOINT,
                    session_id="session-789",
                    timestamp=datetime.now(UTC),
                    checkpoint_data={
                        "quality_score": 75,
                        "working_directory": "/project",
                    },
                )

                # Should not raise - metrics failure is non-fatal
                results = await manager.execute_hooks(
                    HookType.POST_CHECKPOINT, checkpoint_context
                )

                # Find the metrics hook result - should still succeed
                # (the handler catches exceptions and returns success=True)
                metrics_results = [
                    r for r in results if r.success
                ]
                assert len(metrics_results) >= 1


class TestQualityValidationIntegration:
    """Test quality validation hook integration."""

    @pytest.mark.asyncio
    async def test_pre_checkpoint_validates_quality(self) -> None:
        """PRE_CHECKPOINT hook should validate quality threshold."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            # Test with low quality - should fail validation
            low_quality_context = HookContext(
                hook_type=HookType.PRE_CHECKPOINT,
                session_id="session-low",
                timestamp=datetime.now(UTC),
                checkpoint_data={"quality_score": 45},
            )

            results = await manager.execute_hooks(
                HookType.PRE_CHECKPOINT, low_quality_context
            )

            # Find quality validation result
            validation_result = next(
                (r for r in results if not r.success and r.error), None
            )
            assert validation_result is not None
            assert "Quality too low" in validation_result.error

    @pytest.mark.asyncio
    async def test_pre_checkpoint_passes_high_quality(self) -> None:
        """PRE_CHECKPOINT hook should pass for quality >= 60."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            high_quality_context = HookContext(
                hook_type=HookType.PRE_CHECKPOINT,
                session_id="session-high",
                timestamp=datetime.now(UTC),
                checkpoint_data={"quality_score": 85},
            )

            results = await manager.execute_hooks(
                HookType.PRE_CHECKPOINT, high_quality_context
            )

            # All should succeed
            assert all(r.success for r in results)

            # Should have modified context with validated_quality
            validation_result = next(
                (r for r in results if r.modified_context), None
            )
            assert validation_result is not None
            assert validation_result.modified_context["validated_quality"] == 85


class TestPatternLearningIntegration:
    """Test pattern learning hook integration."""

    @pytest.mark.asyncio
    async def test_post_checkpoint_learns_high_quality_patterns(self) -> None:
        """POST_CHECKPOINT should trigger pattern learning for quality > 85."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            # Mock IntelligenceEngine
            with patch(
                "session_buddy.core.intelligence.IntelligenceEngine"
            ) as MockEngine:
                mock_engine = AsyncMock()
                mock_engine.initialize = AsyncMock()
                mock_engine.learn_from_checkpoint.return_value = []
                MockEngine.return_value = mock_engine

                await manager.initialize()

                # Mock workflow metrics to avoid side effects
                with patch(
                    "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
                ) as mock_get_engine:
                    mock_engine_metrics = AsyncMock()
                    mock_get_engine.return_value = mock_engine_metrics

                high_quality_context = HookContext(
                    hook_type=HookType.POST_CHECKPOINT,
                    session_id="session-excellent",
                    timestamp=datetime.now(UTC),
                    checkpoint_data={
                        "quality_score": 92,
                        "working_directory": "/project",
                    },
                )

                # Execute hooks - pattern learning logs info for quality > 85
                results = await manager.execute_hooks(
                    HookType.POST_CHECKPOINT, high_quality_context
                )

                # Pattern learning hook should succeed
                learning_results = [r for r in results if r.success]
                assert len(learning_results) >= 1

                # Verify IntelligenceEngine was called
                mock_engine.learn_from_checkpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_intelligence_engine_integration(self) -> None:
        """IntelligenceEngine.learn_from_checkpoint should be called for high quality."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            # Mock IntelligenceEngine
            with patch(
                "session_buddy.core.intelligence.IntelligenceEngine"
            ) as MockEngine:
                mock_engine = AsyncMock()
                mock_engine.initialize = AsyncMock()
                mock_engine.learn_from_checkpoint.return_value = ["pattern-1", "pattern-2"]
                MockEngine.return_value = mock_engine

                await manager.initialize()

                # Verify IntelligenceEngine was initialized
                mock_engine.initialize.assert_called_once()
                assert manager._intelligence_engine is mock_engine

                # Mock workflow metrics to avoid side effects
                with patch(
                    "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
                ) as mock_get_engine:
                    mock_engine_metrics = AsyncMock()
                    mock_get_engine.return_value = mock_engine_metrics

                    # Create high-quality checkpoint context
                    checkpoint_context = HookContext(
                        hook_type=HookType.POST_CHECKPOINT,
                        session_id="session-intelligence-test",
                        timestamp=datetime.now(UTC),
                        checkpoint_data={
                            "quality_score": 90,
                            "working_directory": "/test/project",
                            "files_modified": ["main.py", "test.py"],
                        },
                    )

                    # Execute POST_CHECKPOINT hooks
                    results = await manager.execute_hooks(
                        HookType.POST_CHECKPOINT, checkpoint_context
                    )

                    # Verify learn_from_checkpoint was called
                    mock_engine.learn_from_checkpoint.assert_called_once()
                    call_args = mock_engine.learn_from_checkpoint.call_args
                    assert call_args.kwargs["checkpoint"]["quality_score"] == 90
                    assert call_args.kwargs["checkpoint"]["working_directory"] == "/test/project"

                    # Verify hook succeeded
                    assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_intelligence_engine_skips_low_quality_checkpoints(self) -> None:
        """IntelligenceEngine should NOT be called for quality <= 85."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            # Mock IntelligenceEngine
            with patch(
                "session_buddy.core.intelligence.IntelligenceEngine"
            ) as MockEngine:
                mock_engine = AsyncMock()
                mock_engine.initialize = AsyncMock()
                mock_engine.learn_from_checkpoint.return_value = []
                MockEngine.return_value = mock_engine

                await manager.initialize()

                # Mock workflow metrics to avoid side effects
                with patch(
                    "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
                ) as mock_get_engine:
                    mock_engine_metrics = AsyncMock()
                    mock_get_engine.return_value = mock_engine_metrics

                    # Create low-quality checkpoint context
                    low_quality_context = HookContext(
                        hook_type=HookType.POST_CHECKPOINT,
                        session_id="session-low-quality",
                        timestamp=datetime.now(UTC),
                        checkpoint_data={
                            "quality_score": 75,  # Below threshold
                            "working_directory": "/test/project",
                        },
                    )

                    # Execute POST_CHECKPOINT hooks
                    results = await manager.execute_hooks(
                        HookType.POST_CHECKPOINT, low_quality_context
                    )

                    # Verify learn_from_checkpoint was NOT called
                    mock_engine.learn_from_checkpoint.assert_not_called()

                    # Hooks should still succeed (pattern learning just skipped)
                    assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_intelligence_failure_does_not_fail_checkpoint(self) -> None:
        """IntelligenceEngine failure should not fail the checkpoint."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            # Mock IntelligenceEngine that raises exception
            with patch(
                "session_buddy.core.intelligence.IntelligenceEngine"
            ) as MockEngine:
                mock_engine = AsyncMock()
                mock_engine.initialize = AsyncMock()
                mock_engine.learn_from_checkpoint.side_effect = Exception(
                    "Intelligence engine failure"
                )
                MockEngine.return_value = mock_engine

                await manager.initialize()

                # Mock workflow metrics to avoid side effects
                with patch(
                    "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
                ) as mock_get_engine:
                    mock_engine_metrics = AsyncMock()
                    mock_get_engine.return_value = mock_engine_metrics

                    # Create high-quality checkpoint context
                    checkpoint_context = HookContext(
                        hook_type=HookType.POST_CHECKPOINT,
                        session_id="session-failure-test",
                        timestamp=datetime.now(UTC),
                        checkpoint_data={
                            "quality_score": 92,
                            "working_directory": "/test/project",
                        },
                    )

                    # Execute POST_CHECKPOINT hooks - should not raise
                    results = await manager.execute_hooks(
                        HookType.POST_CHECKPOINT, checkpoint_context
                    )

                    # Hooks should still succeed (pattern learning handles error gracefully)
                    assert all(r.success for r in results)

                    # Verify intelligence engine was called despite failure
                    mock_engine.learn_from_checkpoint.assert_called_once()


class TestHookPriorityExecution:
    """Test hooks execute in correct priority order."""

    @pytest.mark.asyncio
    async def test_hooks_execute_in_priority_order(self) -> None:
        """Hooks should execute in ascending priority order."""
        manager = HooksManager()
        execution_order = []

        async def make_handler(name: str):
            async def handler(ctx: HookContext) -> HookResult:
                execution_order.append(name)
                return HookResult(success=True)

            return handler

        # Register hooks with different priorities
        await manager.register_hook(
            Hook(
                name="hook_c",
                hook_type=HookType.SESSION_START,
                priority=300,
                handler=await make_handler("hook_c"),
            )
        )
        await manager.register_hook(
            Hook(
                name="hook_a",
                hook_type=HookType.SESSION_START,
                priority=100,
                handler=await make_handler("hook_a"),
            )
        )
        await manager.register_hook(
            Hook(
                name="hook_b",
                hook_type=HookType.SESSION_START,
                priority=200,
                handler=await make_handler("hook_b"),
            )
        )

        context = HookContext(
            hook_type=HookType.SESSION_START,
            session_id="test",
            timestamp=datetime.now(UTC),
        )

        await manager.execute_hooks(HookType.SESSION_START, context)

        # Should execute in priority order: a(100), b(200), c(300)
        assert execution_order == ["hook_a", "hook_b", "hook_c"]

    @pytest.mark.asyncio
    async def test_disabled_hooks_are_skipped(self) -> None:
        """Disabled hooks should not execute."""
        manager = HooksManager()
        executed = []

        async def handler(ctx: HookContext) -> HookResult:
            executed.append("should_not_run")
            return HookResult(success=True)

        await manager.register_hook(
            Hook(
                name="disabled_hook",
                hook_type=HookType.SESSION_START,
                priority=100,
                handler=handler,
                enabled=False,
            )
        )

        context = HookContext(
            hook_type=HookType.SESSION_START,
            session_id="test",
            timestamp=datetime.now(UTC),
        )

        results = await manager.execute_hooks(HookType.SESSION_START, context)

        assert executed == []
        assert len(results) == 0


class TestContextModificationPropagation:
    """Test that hook context modifications propagate correctly."""

    @pytest.mark.asyncio
    async def test_modified_context_propagates_to_later_hooks(self) -> None:
        """Context modifications from early hooks should be visible to later hooks."""
        manager = HooksManager()
        captured_metadata = []

        async def first_hook(ctx: HookContext) -> HookResult:
            return HookResult(
                success=True,
                modified_context={"enriched_by": "first_hook", "value": 42},
            )

        async def second_hook(ctx: HookContext) -> HookResult:
            # Capture the metadata to verify it was modified
            captured_metadata.append(dict(ctx.metadata))
            return HookResult(success=True)

        await manager.register_hook(
            Hook(
                name="first",
                hook_type=HookType.SESSION_START,
                priority=100,
                handler=first_hook,
            )
        )
        await manager.register_hook(
            Hook(
                name="second",
                hook_type=HookType.SESSION_START,
                priority=200,
                handler=second_hook,
            )
        )

        context = HookContext(
            hook_type=HookType.SESSION_START,
            session_id="test",
            timestamp=datetime.now(UTC),
        )

        await manager.execute_hooks(HookType.SESSION_START, context)

        # Second hook should have seen the modifications from first
        assert len(captured_metadata) == 1
        assert captured_metadata[0]["enriched_by"] == "first_hook"
        assert captured_metadata[0]["value"] == 42


class TestErrorHandling:
    """Test error handling in hooks system."""

    @pytest.mark.asyncio
    async def test_hook_failure_does_not_stop_other_hooks(self) -> None:
        """One hook failing should not prevent other hooks from running."""
        manager = HooksManager()
        executed = []

        async def failing_hook(ctx: HookContext) -> HookResult:
            executed.append("failing")
            raise ValueError("Intentional failure")

        async def passing_hook(ctx: HookContext) -> HookResult:
            executed.append("passing")
            return HookResult(success=True)

        await manager.register_hook(
            Hook(
                name="failing",
                hook_type=HookType.SESSION_START,
                priority=100,
                handler=failing_hook,
            )
        )
        await manager.register_hook(
            Hook(
                name="passing",
                hook_type=HookType.SESSION_START,
                priority=200,
                handler=passing_hook,
            )
        )

        context = HookContext(
            hook_type=HookType.SESSION_START,
            session_id="test",
            timestamp=datetime.now(UTC),
        )

        results = await manager.execute_hooks(HookType.SESSION_START, context)

        # Both hooks should have executed
        assert "failing" in executed
        assert "passing" in executed

        # Should have results for both
        assert len(results) == 2
        assert not results[0].success  # First hook failed
        assert results[1].success  # Second hook succeeded

    @pytest.mark.asyncio
    async def test_error_handler_is_called_on_failure(self) -> None:
        """Custom error handler should be called when hook fails."""
        manager = HooksManager()
        error_handled = []

        async def failing_hook(ctx: HookContext) -> HookResult:
            raise RuntimeError("Test error")

        async def error_handler(exc: Exception) -> None:
            error_handled.append(str(exc))

        await manager.register_hook(
            Hook(
                name="with_error_handler",
                hook_type=HookType.SESSION_START,
                priority=100,
                handler=failing_hook,
                error_handler=error_handler,
            )
        )

        context = HookContext(
            hook_type=HookType.SESSION_START,
            session_id="test",
            timestamp=datetime.now(UTC),
        )

        await manager.execute_hooks(HookType.SESSION_START, context)

        assert len(error_handled) == 1
        assert "Test error" in error_handled[0]


class TestEndToEndIntegration:
    """End-to-end integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_error_to_fix_workflow(self) -> None:
        """Test complete error → causal chain → fix workflow."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            mock_tracker.record_error_event.return_value = "err-workflow123"
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            # Step 1: Error occurs
            error_context = HookContext(
                hook_type=HookType.POST_ERROR,
                session_id="workflow-session",
                timestamp=datetime.now(UTC),
                error_info={
                    "error_message": "AttributeError: 'NoneType' has no attribute 'split'",
                    "context": {
                        "file": "parser.py",
                        "line": 156,
                        "function": "parse_input",
                    },
                },
            )

            error_results = await manager.execute_hooks(
                HookType.POST_ERROR, error_context
            )

            # Verify error was tracked
            assert any(r.causal_chain_id == "err-workflow123" for r in error_results)

            # Verify tracking was called with correct error
            mock_tracker.record_error_event.assert_called_once()
            call_kwargs = mock_tracker.record_error_event.call_args.kwargs
            assert "AttributeError" in call_kwargs["error"]
            assert call_kwargs["session_id"] == "workflow-session"

    @pytest.mark.asyncio
    async def test_checkpoint_triggers_all_post_hooks(self) -> None:
        """POST_CHECKPOINT should trigger pattern learning and metrics."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            with patch(
                "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
            ) as mock_get_engine:
                mock_engine = AsyncMock()
                mock_get_engine.return_value = mock_engine

                checkpoint_context = HookContext(
                    hook_type=HookType.POST_CHECKPOINT,
                    session_id="complete-workflow",
                    timestamp=datetime.now(UTC),
                    checkpoint_data={
                        "quality_score": 88,
                        "working_directory": "/my/project",
                        "files_modified": ["src/main.py", "tests/test_main.py"],
                        "commit_count": 5,
                    },
                )

                results = await manager.execute_hooks(
                    HookType.POST_CHECKPOINT, checkpoint_context
                )

                # Both pattern learning and metrics should have executed
                assert len(results) >= 2

                # Metrics collection should have been called
                mock_engine.collect_session_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_session_lifecycle_hooks(self) -> None:
        """Test hooks fire correctly through full session lifecycle."""
        manager = HooksManager()
        hook_sequence = []

        # Create tracking hooks for each lifecycle phase
        async def make_tracker(phase: str):
            async def handler(ctx: HookContext) -> HookResult:
                hook_sequence.append(phase)
                return HookResult(success=True)
            return handler

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            await manager.initialize()

            # Add lifecycle tracking hooks
            await manager.register_hook(
                Hook(
                    name="track_session_start",
                    hook_type=HookType.SESSION_START,
                    priority=1,
                    handler=await make_tracker("session_start"),
                )
            )
            await manager.register_hook(
                Hook(
                    name="track_session_end",
                    hook_type=HookType.SESSION_END,
                    priority=1,
                    handler=await make_tracker("session_end"),
                )
            )

            session_id = f"lifecycle-{uuid.uuid4().hex[:8]}"

            # Simulate session lifecycle
            # 1. Session start
            await manager.execute_hooks(
                HookType.SESSION_START,
                HookContext(
                    hook_type=HookType.SESSION_START,
                    session_id=session_id,
                    timestamp=datetime.now(UTC),
                ),
            )

            # 2. Pre-checkpoint validation
            with patch(
                "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
            ) as mock_get_engine:
                mock_engine = AsyncMock()
                mock_get_engine.return_value = mock_engine

                await manager.execute_hooks(
                    HookType.PRE_CHECKPOINT,
                    HookContext(
                        hook_type=HookType.PRE_CHECKPOINT,
                        session_id=session_id,
                        timestamp=datetime.now(UTC),
                        checkpoint_data={"quality_score": 75},
                    ),
                )

                # 3. Post-checkpoint (metrics + learning)
                await manager.execute_hooks(
                    HookType.POST_CHECKPOINT,
                    HookContext(
                        hook_type=HookType.POST_CHECKPOINT,
                        session_id=session_id,
                        timestamp=datetime.now(UTC),
                        checkpoint_data={
                            "quality_score": 75,
                            "working_directory": "/test",
                        },
                    ),
                )

            # 4. Session end
            await manager.execute_hooks(
                HookType.SESSION_END,
                HookContext(
                    hook_type=HookType.SESSION_END,
                    session_id=session_id,
                    timestamp=datetime.now(UTC),
                ),
            )

            # Verify lifecycle sequence
            assert "session_start" in hook_sequence
            assert "session_end" in hook_sequence
            assert hook_sequence.index("session_start") < hook_sequence.index("session_end")
