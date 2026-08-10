"""Verify SessionLifecycleManager routes checkpoint through orchestrator.

Task 8 wires CheckpointOrchestrator into SessionLifecycleManager so
``perform_git_checkpoint`` is reached only after a safe capture-then-commit
cycle. Lite mode (``ModeConfig.enable_auto_checkpoint=False``) bypasses
the orchestrator entirely. Standard mode captures a defensive snapshot
(advisory) and always proceeds to the legacy commit per spec Constraint
#1 (end-of-task is mandatory). The orchestrator is advisory only — the
actual commit authority is the existing Stop hook path.

Security: ``current_dir`` is validated before being passed to the
orchestrator's subprocess surface. If validation fails, the orchestrator
is skipped and the legacy commit still runs.

NOTE: The brief uses ``SessionManager`` (the natural short-form name) but
the actual class is ``SessionLifecycleManager`` in this codebase — the
test imports the real class.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.core.session_manager import SessionLifecycleManager


@pytest.mark.unit
async def test_lite_mode_bypasses_orchestrator(tmp_path: Path) -> None:
    """Lite mode never instantiates the orchestrator; legacy path runs."""
    from session_buddy.modes import LiteMode

    real = SessionLifecycleManager.__new__(SessionLifecycleManager)  # bypass __init__
    real._mode_config = LiteMode().get_config()  # enable_auto_checkpoint=False
    real.perform_git_checkpoint = AsyncMock(return_value=["legacy-output"])
    real.logger = MagicMock()

    result = await real._checkpoint_with_safety_capture(
        phase="end_of_task", current_dir=tmp_path, quality_score=80,
    )

    real.perform_git_checkpoint.assert_awaited_once()
    assert result == ["legacy-output"]


@pytest.mark.unit
async def test_standard_mode_wraps_orchestrator(tmp_path: Path) -> None:
    """Standard mode routes through orchestrator; legacy output preserved."""
    from session_buddy.modes import StandardMode

    real = SessionLifecycleManager.__new__(SessionLifecycleManager)
    real._mode_config = StandardMode().get_config()  # enable_auto_checkpoint=True
    real.perform_git_checkpoint = AsyncMock(return_value=["📦 git commit abc123"])
    real.logger = MagicMock()

    result = await real._checkpoint_with_safety_capture(
        phase="end_of_task", current_dir=tmp_path, quality_score=80,
    )

    real.perform_git_checkpoint.assert_awaited_once()
    # Legacy output preserved
    assert "📦 git commit abc123" in "\n".join(result)
    # Plus decision summary appended
    assert any("checkpoint_orchestrator_decision" in line for line in result)


@pytest.mark.unit
async def test_invalid_path_skips_orchestrator_but_keeps_commit(
    tmp_path: Path,
) -> None:
    """Security: invalid ``current_dir`` skips orchestrator, legacy commit runs.

    The orchestrator instantiates subprocess-bound components
    (SubagentDetector, WorkingTreeInspector, SnapshotMechanism). Passing
    an unvalidated path risks feeding hostile filesystem state into those
    surfaces. The wrapper must validate ``current_dir`` first and fall
    through to the legacy commit on any failure — never block the user's
    end-of-task commit on a path-validation edge case.
    """
    from session_buddy.modes import StandardMode

    real = SessionLifecycleManager.__new__(SessionLifecycleManager)
    real._mode_config = StandardMode().get_config()  # enable_auto_checkpoint=True
    real.perform_git_checkpoint = AsyncMock(return_value=["📦 git commit abc123"])
    real.logger = MagicMock()

    # Path that does not exist on disk — Path.resolve(strict=True) raises.
    bad_path = tmp_path / "does_not_exist" / "nested"

    # The CheckpointOrchestrator / SubagentDetector / etc. classes must
    # NOT be instantiated when validation fails. We patch the module
    # imports inside ``session_buddy.checkpoint`` and assert none of
    # them were touched.
    with (
        patch("session_buddy.checkpoint.SubagentDetector") as detector_cls,
        patch("session_buddy.checkpoint.WorkingTreeInspector") as inspector_cls,
        patch("session_buddy.checkpoint.SnapshotMechanism") as snapshot_cls,
        patch("session_buddy.checkpoint.CheckpointPolicy") as policy_cls,
        patch("session_buddy.checkpoint.CheckpointOrchestrator") as orchestrator_cls,
    ):
        result = await real._checkpoint_with_safety_capture(
            phase="end_of_task", current_dir=bad_path, quality_score=80,
        )

    # Orchestrator components must not have been instantiated.
    detector_cls.assert_not_called()
    inspector_cls.assert_not_called()
    snapshot_cls.assert_not_called()
    policy_cls.assert_not_called()
    orchestrator_cls.assert_not_called()

    # Legacy commit must still run (we don't break end-of-task on edge case).
    real.perform_git_checkpoint.assert_awaited_once()

    # Output includes legacy commit line and a skipped indicator.
    joined = "\n".join(result)
    assert "📦 git commit abc123" in joined
    assert "safety_capture_skipped" in joined
    assert "reason=invalid_path" in joined
