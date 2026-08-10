"""Verify SessionLifecycleManager routes checkpoint through orchestrator.

Task 8 wires CheckpointOrchestrator into SessionLifecycleManager so
``perform_git_checkpoint`` is reached only after a safe capture-then-commit
cycle. Lite mode (``ModeConfig.enable_auto_checkpoint=False``) bypasses
the orchestrator entirely. The two test cases below pin those contracts.

NOTE: The brief uses ``SessionManager`` (the natural short-form name) but
the actual class is ``SessionLifecycleManager`` in this codebase — the
test imports the real class.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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

    result = await real._checkpoint_via_orchestrator(
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

    result = await real._checkpoint_via_orchestrator(
        phase="end_of_task", current_dir=tmp_path, quality_score=80,
    )

    real.perform_git_checkpoint.assert_awaited_once()
    # Legacy output preserved
    assert "📦 git commit abc123" in "\n".join(result)
    # Plus decision summary appended
    assert any("checkpoint_orchestrator_decision" in line for line in result)
