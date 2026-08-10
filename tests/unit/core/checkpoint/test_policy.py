from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from session_buddy.checkpoint.policy import (
    CheckpointPhase,
    CheckpointPolicy,
    DirtyFilesSignal,
    MidpointCriteria,
    PolicyDecision,
    TimeElapsedSignal,
    WorkingTreeInspector,
)
from session_buddy.checkpoint.subagent_detector import LockfileSignalSource, SubagentDetector

from .conftest import init_repo


@pytest.mark.unit
def test_end_of_task_phase_always_fires(tmp_path: Path) -> None:
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    policy = CheckpointPolicy(
        midpoint_enabled=True, midpoint_criteria=MidpointCriteria(signals=[]),
        subagent_detector=detector, working_tree=WorkingTreeInspector(tmp_path),
    )
    decision = policy.decide(phase=CheckpointPhase.END_OF_TASK)
    assert decision.should_fire is True
    assert decision.reason


@pytest.mark.unit
def test_hook_requested_phase_always_fires(tmp_path: Path) -> None:
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    policy = CheckpointPolicy(
        midpoint_enabled=False, midpoint_criteria=MidpointCriteria(signals=[]),
        subagent_detector=detector, working_tree=WorkingTreeInspector(tmp_path),
    )
    decision = policy.decide(phase=CheckpointPhase.MIDPOINT_TIME, hook_request=True)
    assert decision.should_fire is True
    assert "hook" in decision.reason.lower()


@pytest.mark.unit
def test_midpoint_deferred_when_subagent_active(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    lock.touch()
    detector = SubagentDetector(tmp_path, LockfileSignalSource(lock))
    policy = CheckpointPolicy(
        midpoint_enabled=True,
        midpoint_criteria=MidpointCriteria(signals=[DirtyFilesSignal(min_count=1)]),
        subagent_detector=detector, working_tree=WorkingTreeInspector(tmp_path),
    )
    decision = policy.decide(phase=CheckpointPhase.MIDPOINT_DIRTINESS)
    assert decision.should_fire is False
    assert "subagent" in decision.reason.lower()


@pytest.mark.unit
def test_midpoint_fires_when_signals_active_and_subagent_idle(tmp_path: Path) -> None:
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    inspector = MagicMock()
    inspector.dirty_file_count.return_value = 10
    inspector.seconds_since_last_commit.return_value = 1000.0
    policy = CheckpointPolicy(
        midpoint_enabled=True,
        midpoint_criteria=MidpointCriteria(signals=[DirtyFilesSignal(min_count=5)]),
        subagent_detector=detector, working_tree=inspector,
    )
    assert policy.decide(phase=CheckpointPhase.MIDPOINT_DIRTINESS).should_fire is True


@pytest.mark.unit
def test_midpoint_disabled_returns_skip(tmp_path: Path) -> None:
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    inspector = MagicMock()
    inspector.dirty_file_count.return_value = 10
    policy = CheckpointPolicy(
        midpoint_enabled=False,
        midpoint_criteria=MidpointCriteria(signals=[DirtyFilesSignal(min_count=1)]),
        subagent_detector=detector, working_tree=inspector,
    )
    assert policy.decide(phase=CheckpointPhase.MIDPOINT_DIRTINESS).should_fire is False


@pytest.mark.unit
def test_policy_decision_reason_always_non_empty(tmp_path: Path) -> None:
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    policy = CheckpointPolicy(
        midpoint_enabled=False, midpoint_criteria=MidpointCriteria(signals=[]),
        subagent_detector=detector, working_tree=WorkingTreeInspector(tmp_path),
    )
    for phase in CheckpointPhase:
        d = policy.decide(phase=phase)
        assert d.reason, f"empty reason for {phase}"


@pytest.mark.unit
def test_signal_evaluation_exception_does_not_skip_other_signals(tmp_path: Path) -> None:
    """Per spec line 369: signal.is_active raising → fail closed. Per-signal catch."""
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    inspector = MagicMock()
    inspector.dirty_file_count.return_value = 100

    bad_signal = MagicMock()
    bad_signal.describe.return_value = "broken"
    bad_signal.is_active.side_effect = RuntimeError("boom")
    good_signal = DirtyFilesSignal(min_count=5)

    policy = CheckpointPolicy(
        midpoint_enabled=True,
        midpoint_criteria=MidpointCriteria(signals=[bad_signal, good_signal]),
        subagent_detector=detector, working_tree=inspector,
    )
    decision = policy.decide(phase=CheckpointPhase.MIDPOINT_DIRTINESS)
    assert decision.should_fire is True


@pytest.mark.unit
def test_working_tree_inspector_dirty_file_count_on_real_repo(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "a.py").write_text("a\n")
    (repo / "b.py").write_text("b\n")
    inspector = WorkingTreeInspector(repo)
    assert inspector.dirty_file_count() == 2


@pytest.mark.unit
def test_working_tree_inspector_is_git_repo(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    assert WorkingTreeInspector(repo).is_git_repo() is True
    assert WorkingTreeInspector(tmp_path / "not-a-repo").is_git_repo() is False
