#!/usr/bin/env python3
"""Tests for the reflection_utils module."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

_SETTINGS_STUB = types.ModuleType("session_buddy.settings")
class _SessionMgmtSettings:
    pass


_SETTINGS_STUB.SessionMgmtSettings = _SessionMgmtSettings
_SETTINGS_STUB.get_settings = lambda: SimpleNamespace(
    enable_auto_store_reflections=True,
    auto_store_manual_checkpoints=True,
    auto_store_session_end=True,
    auto_store_exceptional_quality_threshold=95,
    auto_store_quality_delta_threshold=10,
)
sys.modules.setdefault("session_buddy.settings", _SETTINGS_STUB)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "reflection_utils.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.reflection_utils", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.reflection_utils", _MODULE)
_SPEC.loader.exec_module(_MODULE)

AutoStoreDecision = _MODULE.AutoStoreDecision
CheckpointReason = _MODULE.CheckpointReason
generate_auto_store_tags = _MODULE.generate_auto_store_tags
format_auto_store_summary = _MODULE.format_auto_store_summary
should_auto_store_checkpoint = _MODULE.should_auto_store_checkpoint


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


def test_format_auto_store_summary_fallback_reason():
    """Test the fallback message for an unknown reason."""
    decision = AutoStoreDecision(
        should_store=True,
        reason=UnknownReason(),
        metadata={},
    )

    summary = format_auto_store_summary(decision)
    assert summary == "💾 Checkpoint reflection stored"


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
        _MODULE, "get_settings", lambda: fake_settings
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
    monkeypatch.setattr(_MODULE, "get_settings", lambda: fake_settings)

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
    monkeypatch.setattr(_MODULE, "get_settings", lambda: fake_settings)

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
    monkeypatch.setattr(_MODULE, "get_settings", lambda: fake_settings)

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
