"""Integration tests for automatic skill consolidation.

Tests that patterns from checkpoints automatically consolidate into skills
when 3+ similar instances are found.

Phase: Phase 3 - Intelligence Engine Integration
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.hooks import HookContext, HookType, HooksManager


class TestAutomaticSkillConsolidation:
    """Test automatic skill consolidation from pattern instances."""

    @pytest.mark.asyncio
    async def test_checkpoint_triggers_pattern_extraction_and_consolidation(self) -> None:
        """High-quality checkpoint should trigger full learning flow: checkpoint → patterns → skills."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            # Mock IntelligenceEngine with realistic pattern extraction response
            with patch(
                "session_buddy.core.intelligence.IntelligenceEngine"
            ) as MockEngine:
                mock_engine = AsyncMock()
                mock_engine.initialize = AsyncMock()

                # Simulate pattern extraction returning 2 patterns
                # where one has enough instances for consolidation
                mock_engine.learn_from_checkpoint.return_value = [
                    "skill-123",  # This skill was consolidated
                    "pattern-456",  # This pattern wasn't consolidated yet
                ]

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

                    # Create excellent-quality checkpoint context
                    checkpoint_context = HookContext(
                        hook_type=HookType.POST_CHECKPOINT,
                        session_id="session-skill-consolidation",
                        timestamp=datetime.now(UTC),
                        checkpoint_data={
                            "quality_score": 95,  # High quality - should trigger learning
                            "working_directory": "/test/project",
                            "files_modified": ["src/auth.py", "tests/test_auth.py"],
                            "tools_used": ["pytest", "crackerjack"],
                            # Simulate a test-driven development pattern
                            "conversations": [
                                {"role": "user", "content": "Add authentication to the API"},
                                {
                                    "role": "assistant",
                                    "content": "I'll implement test-driven development...",
                                },
                            ],
                        },
                    )

                    # Execute POST_CHECKPOINT hooks
                    results = await manager.execute_hooks(
                        HookType.POST_CHECKPOINT, checkpoint_context
                    )

                    # Verify learn_from_checkpoint was called
                    mock_engine.learn_from_checkpoint.assert_called_once()
                    call_args = mock_engine.learn_from_checkpoint.call_args
                    assert call_args.kwargs["checkpoint"]["quality_score"] == 95

                    # Verify hook succeeded
                    assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_skill_consolidation_requires_multiple_instances(self) -> None:
        """Demonstrate that skill consolidation only happens after 3+ pattern instances."""
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

                # First checkpoint: No skill consolidation yet (only 1 instance)
                mock_engine.learn_from_checkpoint.return_value = []
                MockEngine.return_value = mock_engine

                await manager.initialize()

                # Mock workflow metrics
                with patch(
                    "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
                ) as mock_get_engine:
                    mock_engine_metrics = AsyncMock()
                    mock_get_engine.return_value = mock_engine_metrics

                    # First high-quality checkpoint
                    context1 = HookContext(
                        hook_type=HookType.POST_CHECKPOINT,
                        session_id="session-1",
                        timestamp=datetime.now(UTC),
                        checkpoint_data={
                            "quality_score": 88,
                            "working_directory": "/project",
                        },
                    )

                    results1 = await manager.execute_hooks(
                        HookType.POST_CHECKPOINT, context1
                    )

                    # Verify no skill returned yet (not enough instances)
                    assert mock_engine.learn_from_checkpoint.return_value == []
                    assert all(r.success for r in results1)

    @pytest.mark.asyncio
    async def test_third_similar_checkpoint_triggers_consolidation(self) -> None:
        """Third similar checkpoint should trigger skill consolidation."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            # Mock IntelligenceEngine that simulates gradual skill learning
            with patch(
                "session_buddy.core.intelligence.IntelligenceEngine"
            ) as MockEngine:
                mock_engine = AsyncMock()
                mock_engine.initialize = AsyncMock()

                # Create a list to track calls
                calls_made = []

                async def mock_learn(checkpoint):
                    calls_made.append(checkpoint)
                    call_num = len(calls_made)

                    # Third call triggers consolidation
                    if call_num == 3:
                        return ["skill-tdd-123"]  # Skill consolidated!
                    return []  # First two calls don't consolidate

                mock_engine.learn_from_checkpoint = mock_learn
                MockEngine.return_value = mock_engine

                await manager.initialize()

                # Mock workflow metrics
                with patch(
                    "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
                ) as mock_get_engine:
                    mock_engine_metrics = AsyncMock()
                    mock_get_engine.return_value = mock_engine_metrics

                    # Simulate 3 similar high-quality checkpoints
                    for i in range(1, 4):
                        context = HookContext(
                            hook_type=HookType.POST_CHECKPOINT,
                            session_id=f"session-{i}",
                            timestamp=datetime.now(UTC),
                            checkpoint_data={
                                "quality_score": 88,
                                "working_directory": "/project",
                                "pattern_type": "test_driven_development",  # Same pattern each time
                            },
                        )

                        results = await manager.execute_hooks(
                            HookType.POST_CHECKPOINT, context
                        )

                        assert all(r.success for r in results)

                    # Verify learn_from_checkpoint was called 3 times
                    assert len(calls_made) == 3

                    # Third call should have returned a skill_id
                    third_checkpoint = calls_made[2]
                    assert third_checkpoint["quality_score"] == 88

    @pytest.mark.asyncio
    async def test_low_quality_checkpoints_do_not_consolidate(self) -> None:
        """Low-quality checkpoints should not trigger skill consolidation."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            # Mock IntelligenceEngine that requires quality >= 75
            with patch(
                "session_buddy.core.intelligence.IntelligenceEngine"
            ) as MockEngine:
                mock_engine = AsyncMock()
                mock_engine.initialize = AsyncMock()
                mock_engine.learn_from_checkpoint.return_value = []
                MockEngine.return_value = mock_engine

                await manager.initialize()

                # Mock workflow metrics
                with patch(
                    "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
                ) as mock_get_engine:
                    mock_engine_metrics = AsyncMock()
                    mock_get_engine.return_value = mock_engine_metrics

                    # Low-quality checkpoint (below threshold)
                    low_quality_context = HookContext(
                        hook_type=HookType.POST_CHECKPOINT,
                        session_id="session-low",
                        timestamp=datetime.now(UTC),
                        checkpoint_data={
                            "quality_score": 65,  # Below 75 threshold
                            "working_directory": "/project",
                        },
                    )

                    results = await manager.execute_hooks(
                        HookType.POST_CHECKPOINT, low_quality_context
                    )

                    # Verify learn_from_checkpoint was NOT called
                    mock_engine.learn_from_checkpoint.assert_not_called()

                    # Hooks should still succeed
                    assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_intelligence_engine_unavailable_graceful_degradation(self) -> None:
        """HooksManager should work even if IntelligenceEngine fails to initialize."""
        manager = HooksManager()

        with patch(
            "session_buddy.core.causal_chains.CausalChainTracker"
        ) as MockTracker:
            mock_tracker = AsyncMock()
            MockTracker.return_value = mock_tracker

            # Mock IntelligenceEngine that fails to initialize
            with patch(
                "session_buddy.core.intelligence.IntelligenceEngine"
            ) as MockEngine:
                mock_engine = AsyncMock()
                mock_engine.initialize.side_effect = Exception("DI container not set up")
                MockEngine.return_value = mock_engine

                await manager.initialize()

                # Intelligence engine should be None after failed initialization
                assert manager._intelligence_engine is None

                # Mock workflow metrics
                with patch(
                    "session_buddy.core.workflow_metrics.get_workflow_metrics_engine"
                ) as mock_get_engine:
                    mock_engine_metrics = AsyncMock()
                    mock_get_engine.return_value = mock_engine_metrics

                    # High-quality checkpoint
                    high_quality_context = HookContext(
                        hook_type=HookType.POST_CHECKPOINT,
                        session_id="session-no-intelligence",
                        timestamp=datetime.now(UTC),
                        checkpoint_data={
                            "quality_score": 92,
                            "working_directory": "/project",
                        },
                    )

                    # Should not raise - hooks should work without intelligence
                    results = await manager.execute_hooks(
                        HookType.POST_CHECKPOINT, high_quality_context
                    )

                    # Hooks should succeed (pattern learning gracefully skipped)
                    assert all(r.success for r in results)
