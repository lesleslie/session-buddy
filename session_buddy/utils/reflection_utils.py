"""Reflection storage utilities for intelligent checkpoint management.

This module provides utilities for determining when checkpoint reflections
should be automatically stored, balancing signal-to-noise ratio with
comprehensive session memory capture.
"""

import typing as t
from enum import Enum

from session_buddy.settings import get_settings


class CheckpointReason(Enum):
    """Reasons for automatic reflection storage."""

    MANUAL_CHECKPOINT = "manual_checkpoint"
    SESSION_END = "session_end"
    QUALITY_IMPROVEMENT = "quality_improvement"
    QUALITY_DEGRADATION = "quality_degradation"
    EXCEPTIONAL_QUALITY = "exceptional_quality"
    ROUTINE_SKIP = "routine_skip"
    PRE_COMPACT = "pre_compact"  # Before context compaction


class AutoStoreDecision(t.NamedTuple):
    """Decision result for auto-storing a checkpoint reflection."""

    should_store: bool
    reason: CheckpointReason
    metadata: dict[str, t.Any]


def should_auto_store_checkpoint(
    quality_score: int,
    previous_score: int | None = None,
    is_manual: bool = False,
    session_phase: str = "checkpoint",
) -> AutoStoreDecision:
    """Determine if checkpoint deserves automatic reflection storage.

    This function implements selective auto-store logic to maintain high
    signal-to-noise ratio in the reflection database.

    Args:
        quality_score: Current session quality score (0-100)
        previous_score: Previous checkpoint quality score, if available
        is_manual: Whether this is a manually-triggered checkpoint
        session_phase: Session lifecycle phase ('checkpoint', 'end', 'start')

    Returns:
        AutoStoreDecision with storage recommendation and reasoning

    Examples:
        >>> # Manual checkpoint - always store
        >>> decision = should_auto_store_checkpoint(75, is_manual=True)
        >>> decision.should_store
        True
        >>> decision.reason
        <CheckpointReason.MANUAL_CHECKPOINT: 'manual_checkpoint'>

        >>> # Significant quality improvement
        >>> decision = should_auto_store_checkpoint(85, previous_score=70)
        >>> decision.should_store
        True
        >>> decision.reason
        <CheckpointReason.QUALITY_IMPROVEMENT: 'quality_improvement'>

        >>> # Routine checkpoint - skip
        >>> decision = should_auto_store_checkpoint(75, previous_score=73)
        >>> decision.should_store
        False
        >>> decision.reason
        <CheckpointReason.ROUTINE_SKIP: 'routine_skip'>

    """
    config = get_settings()

    # Check if auto-store is globally enabled
    if not config.enable_auto_store_reflections:
        return AutoStoreDecision(
            should_store=False,
            reason=CheckpointReason.ROUTINE_SKIP,
            metadata={"disabled": True},
        )

    # Always store manual checkpoints
    if is_manual and config.auto_store_manual_checkpoints:
        return AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.MANUAL_CHECKPOINT,
            metadata={
                "quality_score": quality_score,
                "previous_score": previous_score,
            },
        )

    # Always store session end
    if session_phase == "end" and config.auto_store_session_end:
        return AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.SESSION_END,
            metadata={
                "quality_score": quality_score,
                "previous_score": previous_score,
            },
        )

    # Store exceptional quality sessions
    if quality_score >= config.auto_store_exceptional_quality_threshold:
        return AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.EXCEPTIONAL_QUALITY,
            metadata={
                "quality_score": quality_score,
                "threshold": config.auto_store_exceptional_quality_threshold,
            },
        )

    # Store significant quality changes
    if previous_score is not None:
        quality_delta = abs(quality_score - previous_score)
        threshold = config.auto_store_quality_delta_threshold

        if quality_delta >= threshold:
            reason = (
                CheckpointReason.QUALITY_IMPROVEMENT
                if quality_score > previous_score
                else CheckpointReason.QUALITY_DEGRADATION
            )
            return AutoStoreDecision(
                should_store=True,
                reason=reason,
                metadata={
                    "quality_score": quality_score,
                    "previous_score": previous_score,
                    "delta": quality_delta,
                    "threshold": threshold,
                },
            )

    # Skip routine checkpoints
    return AutoStoreDecision(
        should_store=False,
        reason=CheckpointReason.ROUTINE_SKIP,
        metadata={
            "quality_score": quality_score,
            "previous_score": previous_score,
            "message": "Routine checkpoint without significant changes",
        },
    )


def generate_auto_store_tags(
    reason: CheckpointReason,
    project: str | None = None,
    quality_score: int | None = None,
) -> list[str]:
    """Generate semantic tags for auto-stored checkpoint reflections.

    Args:
        reason: Why this checkpoint was auto-stored
        project: Project name/identifier
        quality_score: Session quality score

    Returns:
        List of semantic tags for the reflection

    """
    tags = ["checkpoint", "auto-stored", reason.value]

    if project:
        tags.append(project)

    # Add quality-based tags
    if quality_score is not None:
        if quality_score >= 90:
            tags.append("high-quality")
        elif quality_score >= 75:
            tags.append("good-quality")
        elif quality_score < 60:
            tags.append("needs-improvement")

    # Add phase-specific tags
    if reason == CheckpointReason.SESSION_END:
        tags.append("session-summary")
    elif reason == CheckpointReason.MANUAL_CHECKPOINT:
        tags.append("user-initiated")
    elif reason == CheckpointReason.PRE_COMPACT:
        tags.append("context-preserved")
        tags.append("before-compaction")
    elif reason in {
        CheckpointReason.QUALITY_IMPROVEMENT,
        CheckpointReason.QUALITY_DEGRADATION,
    }:
        tags.append("quality-change")

    return tags


def format_auto_store_summary(decision: AutoStoreDecision) -> str:
    """Format a human-readable summary of auto-store decision.

    Args:
        decision: The AutoStoreDecision to summarize

    Returns:
        Formatted summary string

    """
    if not decision.should_store:
        return "⏭️  Routine checkpoint - reflection storage skipped (maintains high signal-to-noise ratio)"

    reason_messages = {
        CheckpointReason.MANUAL_CHECKPOINT: "💾 Manual checkpoint - reflection stored automatically",
        CheckpointReason.SESSION_END: "📝 Session end - final reflection stored",
        CheckpointReason.QUALITY_IMPROVEMENT: "📈 Quality improved significantly - reflection stored",
        CheckpointReason.QUALITY_DEGRADATION: "📉 Quality changed significantly - reflection stored for analysis",
        CheckpointReason.EXCEPTIONAL_QUALITY: "⭐ Exceptional quality session - reflection stored",
        CheckpointReason.PRE_COMPACT: "🗜️ Pre-compact sync - context preserved before compaction",
    }

    message = reason_messages.get(
        decision.reason,
        "💾 Checkpoint reflection stored",
    )

    # Add metadata details
    if "quality_score" in decision.metadata:
        message += f" (quality: {decision.metadata['quality_score']}/100"
        if "delta" in decision.metadata:
            delta = decision.metadata["delta"]
            direction = (
                "+" if decision.reason == CheckpointReason.QUALITY_IMPROVEMENT else "-"
            )
            message += f", {direction}{delta} points"
        message += ")"

    return message
