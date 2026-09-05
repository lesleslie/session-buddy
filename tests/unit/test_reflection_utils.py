"""Tests for session_buddy.utils.reflection_utils.

Covers the reflection-storage decision tree: the auto-store reason enum,
the named-tuple decision shape, the heuristic that decides whether to
store a checkpoint reflection, the tag-generation helper, and the
human-readable summary formatter.

NOTE: This test file imports the module normally so pytest-cov's
coverage hooks attach. Earlier revisions used
``importlib.util.spec_from_file_location`` which bypassed coverage
tracking entirely, leaving the module at 15% recorded coverage even
though all branches were tested.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import session_buddy.utils.reflection_utils as ru
from session_buddy.utils.reflection_utils import (
    AutoStoreDecision,
    CheckpointReason,
    format_auto_store_summary,
    generate_auto_store_tags,
    should_auto_store_checkpoint,
)


# ---------------------------------------------------------------------------
# CheckpointReason and AutoStoreDecision
# ---------------------------------------------------------------------------


class TestCheckpointReason:
    def test_values_are_strings(self) -> None:
        for reason in CheckpointReason:
            assert isinstance(reason.value, str)

    def test_all_expected_members_present(self) -> None:
        expected = {
            "MANUAL_CHECKPOINT",
            "SESSION_END",
            "QUALITY_IMPROVEMENT",
            "QUALITY_DEGRADATION",
            "EXCEPTIONAL_QUALITY",
            "ROUTINE_SKIP",
            "PRE_COMPACT",
        }
        actual = {m.name for m in CheckpointReason}
        assert actual == expected


class TestAutoStoreDecision:
    def test_is_namedtuple(self) -> None:
        decision = AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.ROUTINE_SKIP,
            metadata={},
        )
        # NamedTuple supports attribute access.
        assert decision.should_store is True
        assert decision.reason == CheckpointReason.ROUTINE_SKIP
        assert decision.metadata == {}

    def test_unpacks_as_tuple(self) -> None:
        decision = AutoStoreDecision(
            should_store=False,
            reason=CheckpointReason.SESSION_END,
            metadata={"k": "v"},
        )
        flag, reason, meta = decision
        assert flag is False
        assert reason == CheckpointReason.SESSION_END
        assert meta == {"k": "v"}


# ---------------------------------------------------------------------------
# should_auto_store_checkpoint
# ---------------------------------------------------------------------------


def _settings(**overrides):
    """Helper: build a settings SimpleNamespace with sensible defaults."""
    base = dict(
        enable_auto_store_reflections=True,
        auto_store_manual_checkpoints=True,
        auto_store_session_end=True,
        auto_store_exceptional_quality_threshold=95,
        auto_store_quality_delta_threshold=10,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestShouldAutoStoreDisabled:
    def test_disabled_returns_skip(self, monkeypatch) -> None:
        settings = _settings(enable_auto_store_reflections=False)
        monkeypatch.setattr(ru, "get_settings", lambda: settings)
        decision = should_auto_store_checkpoint(quality_score=100)
        assert decision.should_store is False
        assert decision.reason == CheckpointReason.ROUTINE_SKIP
        assert decision.metadata == {"disabled": True}

    def test_disabled_takes_precedence_over_manual(self, monkeypatch) -> None:
        settings = _settings(enable_auto_store_reflections=False)
        monkeypatch.setattr(ru, "get_settings", lambda: settings)
        decision = should_auto_store_checkpoint(quality_score=50, is_manual=True)
        # The disabled gate runs BEFORE the manual-store branch.
        assert decision.should_store is False
        assert "disabled" in decision.metadata


class TestShouldAutoStoreManual:
    def test_manual_when_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        decision = should_auto_store_checkpoint(quality_score=50, is_manual=True)
        assert decision.should_store is True
        assert decision.reason == CheckpointReason.MANUAL_CHECKPOINT
        assert decision.metadata["quality_score"] == 50
        assert decision.metadata["previous_score"] is None

    def test_manual_not_stored_when_disabled(self, monkeypatch) -> None:
        settings = _settings(auto_store_manual_checkpoints=False)
        monkeypatch.setattr(ru, "get_settings", lambda: settings)
        # Manual flag is set but config disables it; should fall through to
        # routine-skip rather than store.
        decision = should_auto_store_checkpoint(quality_score=50, is_manual=True)
        # Falls through to the routine-skip path (no prior score, no
        # exceptional, no delta).
        assert decision.should_store is False


class TestShouldAutoStoreSessionEnd:
    def test_session_end_when_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        decision = should_auto_store_checkpoint(
            quality_score=50, session_phase="end"
        )
        assert decision.should_store is True
        assert decision.reason == CheckpointReason.SESSION_END
        assert decision.metadata["quality_score"] == 50

    def test_session_end_not_stored_when_disabled(self, monkeypatch) -> None:
        settings = _settings(auto_store_session_end=False)
        monkeypatch.setattr(ru, "get_settings", lambda: settings)
        # session_phase="end" but auto_store_session_end=False → falls through.
        decision = should_auto_store_checkpoint(
            quality_score=50, session_phase="end"
        )
        assert decision.should_store is False


class TestShouldAutoStoreExceptional:
    def test_quality_at_threshold_triggers(self, monkeypatch) -> None:
        # Default threshold is 95.
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        decision = should_auto_store_checkpoint(
            quality_score=95, previous_score=80
        )
        assert decision.should_store is True
        assert decision.reason == CheckpointReason.EXCEPTIONAL_QUALITY
        assert decision.metadata["threshold"] == 95

    def test_quality_above_threshold_triggers(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        decision = should_auto_store_checkpoint(quality_score=100)
        assert decision.reason == CheckpointReason.EXCEPTIONAL_QUALITY

    def test_quality_below_threshold_no_trigger(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        # 94 is below 95 threshold, no previous score → routine skip.
        decision = should_auto_store_checkpoint(quality_score=94)
        assert decision.reason == CheckpointReason.ROUTINE_SKIP


class TestShouldAutoStoreQualityDelta:
    def test_improvement_above_threshold_triggers(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        decision = should_auto_store_checkpoint(
            quality_score=85, previous_score=70  # delta=15, above 10
        )
        assert decision.should_store is True
        assert decision.reason == CheckpointReason.QUALITY_IMPROVEMENT
        assert decision.metadata["delta"] == 15
        assert decision.metadata["threshold"] == 10

    def test_degradation_above_threshold_triggers(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        decision = should_auto_store_checkpoint(
            quality_score=50, previous_score=80  # delta=30, degradation
        )
        assert decision.should_store is True
        assert decision.reason == CheckpointReason.QUALITY_DEGRADATION
        assert decision.metadata["delta"] == 30

    def test_small_delta_does_not_trigger(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        # delta=5 < threshold=10 → routine skip.
        decision = should_auto_store_checkpoint(quality_score=75, previous_score=70)
        assert decision.should_store is False
        assert decision.reason == CheckpointReason.ROUTINE_SKIP

    def test_no_previous_score_no_delta_check(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        decision = should_auto_store_checkpoint(quality_score=75, previous_score=None)
        # previous_score=None → skip the delta branch entirely.
        assert decision.reason == CheckpointReason.ROUTINE_SKIP
        assert decision.metadata["previous_score"] is None


class TestShouldAutoStoreRoutineSkip:
    def test_default_args_skip(self, monkeypatch) -> None:
        monkeypatch.setattr(ru, "get_settings", lambda: _settings())
        # quality=75, no prev, not manual, not end → routine skip.
        decision = should_auto_store_checkpoint(quality_score=75)
        assert decision.should_store is False
        assert decision.reason == CheckpointReason.ROUTINE_SKIP
        assert decision.metadata["message"].startswith("Routine checkpoint")


# ---------------------------------------------------------------------------
# generate_auto_store_tags
# ---------------------------------------------------------------------------


class TestGenerateAutoStoreTags:
    def test_base_tags_always_present(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.ROUTINE_SKIP)
        assert "checkpoint" in tags
        assert "auto-stored" in tags
        assert "routine_skip" in tags

    def test_project_appended_when_provided(self) -> None:
        tags = generate_auto_store_tags(
            CheckpointReason.SESSION_END, project="my-project"
        )
        assert "my-project" in tags

    def test_high_quality_tag_at_90(self) -> None:
        tags = generate_auto_store_tags(
            CheckpointReason.SESSION_END, quality_score=90
        )
        assert "high-quality" in tags

    def test_high_quality_tag_above_90(self) -> None:
        tags = generate_auto_store_tags(
            CheckpointReason.SESSION_END, quality_score=99
        )
        assert "high-quality" in tags

    def test_good_quality_tag_at_75(self) -> None:
        tags = generate_auto_store_tags(
            CheckpointReason.MANUAL_CHECKPOINT, quality_score=75
        )
        assert "good-quality" in tags

    def test_good_quality_tag_at_89(self) -> None:
        tags = generate_auto_store_tags(
            CheckpointReason.MANUAL_CHECKPOINT, quality_score=89
        )
        assert "good-quality" in tags

    def test_no_quality_tag_below_60(self) -> None:
        tags = generate_auto_store_tags(
            CheckpointReason.PRE_COMPACT, quality_score=59
        )
        assert "high-quality" not in tags
        assert "good-quality" not in tags
        assert "needs-improvement" in tags

    def test_needs_improvement_tag_at_0(self) -> None:
        tags = generate_auto_store_tags(
            CheckpointReason.PRE_COMPACT, quality_score=0
        )
        assert "needs-improvement" in tags

    def test_no_quality_tag_in_middle_range(self) -> None:
        # 60..74 falls between "needs-improvement" (<60) and "good-quality"
        # (>=75). The function leaves a gap and adds no quality tag.
        tags = generate_auto_store_tags(
            CheckpointReason.MANUAL_CHECKPOINT, quality_score=65
        )
        assert "high-quality" not in tags
        assert "good-quality" not in tags
        assert "needs-improvement" not in tags

    def test_no_quality_tag_when_quality_score_is_none(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.ROUTINE_SKIP)
        assert "high-quality" not in tags
        assert "good-quality" not in tags

    def test_session_end_adds_session_summary(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.SESSION_END)
        assert "session-summary" in tags

    def test_manual_checkpoint_adds_user_initiated(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.MANUAL_CHECKPOINT)
        assert "user-initiated" in tags

    def test_pre_compact_adds_context_preserved_and_before_compaction(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.PRE_COMPACT)
        assert "context-preserved" in tags
        assert "before-compaction" in tags

    def test_quality_improvement_adds_quality_change(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.QUALITY_IMPROVEMENT)
        assert "quality-change" in tags

    def test_quality_degradation_adds_quality_change(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.QUALITY_DEGRADATION)
        assert "quality-change" in tags

    def test_routine_skip_has_no_phase_specific_tag(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.ROUTINE_SKIP)
        assert "session-summary" not in tags
        assert "user-initiated" not in tags
        assert "context-preserved" not in tags
        assert "quality-change" not in tags

    def test_exceptional_quality_has_no_phase_specific_tag(self) -> None:
        tags = generate_auto_store_tags(CheckpointReason.EXCEPTIONAL_QUALITY)
        assert "session-summary" not in tags
        assert "quality-change" not in tags


# ---------------------------------------------------------------------------
# format_auto_store_summary
# ---------------------------------------------------------------------------


class TestFormatAutoStoreSummary:
    def test_routine_skip_message(self) -> None:
        decision = AutoStoreDecision(
            should_store=False,
            reason=CheckpointReason.ROUTINE_SKIP,
            metadata={},
        )
        msg = format_auto_store_summary(decision)
        assert "skipped" in msg
        assert "signal-to-noise ratio" in msg

    def test_manual_checkpoint_message(self) -> None:
        decision = AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.MANUAL_CHECKPOINT,
            metadata={"quality_score": 80, "previous_score": 70},
        )
        msg = format_auto_store_summary(decision)
        assert "Manual checkpoint" in msg
        assert "80/100" in msg

    def test_session_end_message(self) -> None:
        decision = AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.SESSION_END,
            metadata={"quality_score": 75, "previous_score": 70},
        )
        msg = format_auto_store_summary(decision)
        assert "Session end" in msg

    def test_quality_improvement_message_includes_delta(self) -> None:
        decision = AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.QUALITY_IMPROVEMENT,
            metadata={"quality_score": 85, "previous_score": 70, "delta": 15},
        )
        msg = format_auto_store_summary(decision)
        assert "improved" in msg.lower() or "Quality" in msg
        assert "+15" in msg
        assert "85/100" in msg

    def test_quality_degradation_delta_uses_minus_prefix(self) -> None:
        decision = AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.QUALITY_DEGRADATION,
            metadata={"quality_score": 50, "previous_score": 80, "delta": 30},
        )
        msg = format_auto_store_summary(decision)
        assert "-30" in msg

    def test_exceptional_quality_message(self) -> None:
        decision = AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.EXCEPTIONAL_QUALITY,
            metadata={"quality_score": 99, "threshold": 95},
        )
        msg = format_auto_store_summary(decision)
        assert "Exceptional" in msg or "exceptional" in msg
        assert "99/100" in msg

    def test_pre_compact_message(self) -> None:
        decision = AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.PRE_COMPACT,
            metadata={"quality_score": 70, "previous_score": 65},
        )
        msg = format_auto_store_summary(decision)
        assert "Pre-compact" in msg or "compaction" in msg

    def test_unknown_reason_falls_back(self) -> None:
        class WeirdReason:
            value = "weird"

        decision = AutoStoreDecision(
            should_store=True,
            reason=WeirdReason(),  # type: ignore[arg-type]
            metadata={},
        )
        msg = format_auto_store_summary(decision)
        assert msg == "💾 Checkpoint reflection stored"

    def test_summary_without_quality_score_no_parens(self) -> None:
        decision = AutoStoreDecision(
            should_store=True,
            reason=CheckpointReason.MANUAL_CHECKPOINT,
            metadata={},  # no quality_score
        )
        msg = format_auto_store_summary(decision)
        # The formatter appends " (quality: ...)" only when quality_score is
        # in metadata. With empty metadata, no parens.
        assert "(quality:" not in msg
