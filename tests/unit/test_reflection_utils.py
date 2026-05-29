#!/usr/bin/env python3
"""Tests for the reflection_utils module."""

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from session_buddy.utils.reflection_utils import (
    AutoStoreDecision,
    CheckpointReason,
    generate_auto_store_tags,
    format_auto_store_summary,
    should_auto_store_checkpoint,
)


class UnknownReason:
    value = "unknown_reason"


def test_format_auto_store_summary_should_store():
    """Test formatting of auto-store summary when storing."""
    decision = AutoStoreDecision(
        should_store=True,
        reason=CheckpointReason.QUALITY_IMPROVEMENT,
        metadata={
            "quality_score": 85,
            "delta": 15,
        },
    )

    summary = format_auto_store_summary(decision)

    assert "Quality improved significantly" in summary
    assert "quality: 85/100" in summary
    assert "+15 points" in summary


def test_format_auto_store_summary_should_not_store():
    """Test formatting of auto-store summary when not storing."""
    decision = AutoStoreDecision(
        should_store=False, reason=CheckpointReason.ROUTINE_SKIP, metadata={}
    )

    summary = format_auto_store_summary(decision)

    assert "skipped" in summary
    assert "signal-to-noise ratio" in summary


def test_should_auto_store_checkpoint_quality_improvement(monkeypatch):
    """Test auto-store decision for quality improvement."""
    fake_settings = SimpleNamespace(
        enable_auto_store_reflections=True,
        auto_store_manual_checkpoints=True,
        auto_store_session_end=True,
        auto_store_exceptional_quality_threshold=95,
        auto_store_quality_delta_threshold=10,
    )
    monkeypatch.setattr(
        "session_buddy.utils.reflection_utils.get_settings", lambda: fake_settings
    )
    decision = should_auto_store_checkpoint(
        quality_score=85,
        previous_score=70,
        is_manual=False,
        session_phase="checkpoint",
    )

    assert decision.should_store is True
    assert decision.reason == CheckpointReason.QUALITY_IMPROVEMENT
    assert "delta" in decision.metadata


def test_should_auto_store_checkpoint_no_previous_score():
    """Test auto-store decision when no previous score exists."""
    decision = should_auto_store_checkpoint(
        quality_score=75,
        previous_score=None,
        is_manual=False,
        session_phase="checkpoint",
    )

    # When there's no previous score, it won't trigger quality improvement logic
    # but might still be skipped based on other criteria
    assert isinstance(decision.should_store, bool)
    assert isinstance(decision.reason, CheckpointReason)


def test_should_auto_store_checkpoint_no_previous_score_enabled(monkeypatch):
    """Test the routine-skip branch when enabled and no previous score exists."""
    fake_settings = SimpleNamespace(
        enable_auto_store_reflections=True,
        auto_store_manual_checkpoints=True,
        auto_store_session_end=True,
        auto_store_exceptional_quality_threshold=95,
        auto_store_quality_delta_threshold=10,
    )
    monkeypatch.setattr(
        "session_buddy.utils.reflection_utils.get_settings", lambda: fake_settings
    )

    decision = should_auto_store_checkpoint(
        quality_score=75,
        previous_score=None,
        is_manual=False,
        session_phase="checkpoint",
    )

    assert decision.should_store is False
    assert decision.reason == CheckpointReason.ROUTINE_SKIP
    assert decision.metadata["previous_score"] is None


def test_should_auto_store_checkpoint_manual():
    """Test auto-store decision for manual checkpoint."""
    decision = should_auto_store_checkpoint(
        quality_score=75, previous_score=70, is_manual=True, session_phase="checkpoint"
    )

    assert decision.should_store is True
    assert decision.reason == CheckpointReason.MANUAL_CHECKPOINT


def test_should_auto_store_checkpoint_session_end():
    """Test auto-store decision for session end."""
    decision = should_auto_store_checkpoint(
        quality_score=75, previous_score=70, is_manual=False, session_phase="end"
    )

    assert decision.should_store is True
    assert decision.reason == CheckpointReason.SESSION_END


def test_should_auto_store_checkpoint_exceptional_quality():
    """Test auto-store decision for exceptional quality."""
    decision = should_auto_store_checkpoint(
        quality_score=95,  # Exceptional quality
        previous_score=70,
        is_manual=False,
        session_phase="checkpoint",
    )

    assert decision.should_store is True
    assert decision.reason == CheckpointReason.EXCEPTIONAL_QUALITY


def test_should_auto_store_checkpoint_disabled(monkeypatch):
    """Test auto-store decision when global setting disables reflection storage."""
    fake_settings = SimpleNamespace(
        enable_auto_store_reflections=False,
        auto_store_manual_checkpoints=True,
        auto_store_session_end=True,
        auto_store_exceptional_quality_threshold=90,
        auto_store_quality_delta_threshold=10,
    )
    monkeypatch.setattr(
        "session_buddy.utils.reflection_utils.get_settings", lambda: fake_settings
    )

    decision = should_auto_store_checkpoint(quality_score=100)

    assert decision.should_store is False
    assert decision.reason == CheckpointReason.ROUTINE_SKIP
    assert decision.metadata == {"disabled": True}


def test_should_auto_store_checkpoint_routine_skip(monkeypatch):
    """Test routine checkpoint skip when nothing significant changed."""
    fake_settings = SimpleNamespace(
        enable_auto_store_reflections=True,
        auto_store_manual_checkpoints=True,
        auto_store_session_end=True,
        auto_store_exceptional_quality_threshold=95,
        auto_store_quality_delta_threshold=10,
    )
    monkeypatch.setattr(
        "session_buddy.utils.reflection_utils.get_settings", lambda: fake_settings
    )

    decision = should_auto_store_checkpoint(
        quality_score=75,
        previous_score=72,
        is_manual=False,
        session_phase="checkpoint",
    )

    assert decision.should_store is False
    assert decision.reason == CheckpointReason.ROUTINE_SKIP
    assert decision.metadata["message"].startswith("Routine checkpoint")


def test_generate_auto_store_tags_branches() -> None:
    assert generate_auto_store_tags(
        CheckpointReason.SESSION_END, project="proj", quality_score=95
    ) == [
        "checkpoint",
        "auto-stored",
        "session_end",
        "proj",
        "high-quality",
        "session-summary",
    ]

    assert generate_auto_store_tags(
        CheckpointReason.MANUAL_CHECKPOINT, quality_score=80
    ) == [
        "checkpoint",
        "auto-stored",
        "manual_checkpoint",
        "good-quality",
        "user-initiated",
    ]

    assert generate_auto_store_tags(
        CheckpointReason.PRE_COMPACT, quality_score=50
    ) == [
        "checkpoint",
        "auto-stored",
        "pre_compact",
        "needs-improvement",
        "context-preserved",
        "before-compaction",
    ]

    assert generate_auto_store_tags(
        CheckpointReason.QUALITY_IMPROVEMENT, quality_score=70
    ) == [
        "checkpoint",
        "auto-stored",
        "quality_improvement",
        "quality-change",
    ]

    assert generate_auto_store_tags(
        CheckpointReason.QUALITY_DEGRADATION, quality_score=55
    ) == [
        "checkpoint",
        "auto-stored",
        "quality_degradation",
        "needs-improvement",
        "quality-change",
    ]

    assert generate_auto_store_tags(CheckpointReason.ROUTINE_SKIP, quality_score=None) == [
        "checkpoint",
        "auto-stored",
        "routine_skip",
    ]

    assert generate_auto_store_tags(
        CheckpointReason.ROUTINE_SKIP, quality_score=80
    ) == [
        "checkpoint",
        "auto-stored",
        "routine_skip",
        "good-quality",
    ]


def test_generate_auto_store_tags_unknown_reason() -> None:
    """Test fallback branch for unknown reasons."""
    unknown_reason = UnknownReason()
    assert generate_auto_store_tags(
        unknown_reason, project=None, quality_score=None
    ) == [
        "checkpoint",
        "auto-stored",
        "unknown_reason",
    ]


def test_format_auto_store_summary_other_reasons() -> None:
    assert "Manual checkpoint" in format_auto_store_summary(
        AutoStoreDecision(True, CheckpointReason.MANUAL_CHECKPOINT, {})
    )
    assert "Session end" in format_auto_store_summary(
        AutoStoreDecision(True, CheckpointReason.SESSION_END, {})
    )
    assert "Pre-compact" in format_auto_store_summary(
        AutoStoreDecision(True, CheckpointReason.PRE_COMPACT, {})
    )
    assert "Quality changed significantly" in format_auto_store_summary(
        AutoStoreDecision(True, CheckpointReason.QUALITY_DEGRADATION, {})
    )


def test_format_auto_store_summary_fallback_and_no_delta() -> None:
    """Test fallback summary text and metadata without delta."""
    unknown_reason = UnknownReason()
    summary = format_auto_store_summary(
        AutoStoreDecision(
            True,
            unknown_reason,
            {"quality_score": 88},
        )
    )

    assert summary == "💾 Checkpoint reflection stored (quality: 88/100)"


if __name__ == "__main__":
    pytest.main([__file__])
