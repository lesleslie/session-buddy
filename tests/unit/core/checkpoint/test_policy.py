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


@pytest.mark.unit
def test_working_tree_inspector_seconds_since_last_commit_real_repo(tmp_path: Path) -> None:
    """Coverage: lines 50-63 (seconds_since_last_commit with valid iso date)."""
    repo = init_repo(tmp_path)
    secs = WorkingTreeInspector(repo).seconds_since_last_commit()
    # init_repo creates one commit; just-merged, so should be a small non-negative value.
    assert secs >= 0.0


@pytest.mark.unit
def test_working_tree_inspector_seconds_since_last_commit_returns_zero_when_no_head(
    tmp_path: Path,
) -> None:
    """Coverage: line 57 (empty stdout → 0.0)."""
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    subprocess_run = __import__("subprocess").run
    subprocess_run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess_run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess_run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    # Empty repo, no commits: `git log -1 --format=%aI` writes nothing to stdout.
    assert WorkingTreeInspector(repo).seconds_since_last_commit() == 0.0


@pytest.mark.unit
def test_working_tree_inspector_dirty_file_count_empty_stdout(tmp_path: Path) -> None:
    """Coverage: line 67 (git status --porcelain returns non-zero rc → 0)."""
    repo = tmp_path / "not-a-git-repo"
    repo.mkdir()
    assert WorkingTreeInspector(repo).dirty_file_count() == 0


@pytest.mark.unit
def test_working_tree_inspector_dirty_file_count_with_changes(tmp_path: Path) -> None:
    """Coverage: line 74 (dirty file count > 0)."""
    repo = init_repo(tmp_path)
    (repo / "a.py").write_text("a\n")
    (repo / "b.py").write_text("b\n")
    (repo / "c.py").write_text("c\n")
    assert WorkingTreeInspector(repo).dirty_file_count() == 3


@pytest.mark.unit
def test_time_elapsed_signal_is_active_and_describe(tmp_path: Path) -> None:
    """Coverage: lines 88, 91 (TimeElapsedSignal.is_active + describe)."""
    from session_buddy.checkpoint.policy import TimeElapsedSignal

    inspector = WorkingTreeInspector(tmp_path)
    sig = TimeElapsedSignal(min_seconds=0.0)
    assert sig.is_active(inspector) is True  # always active at threshold 0
    assert "0s since last commit" in sig.describe()


@pytest.mark.unit
def test_end_of_task_disabled_when_always_end_false(tmp_path: Path) -> None:
    """Coverage: line 135 (always_end=False branch)."""
    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    policy = CheckpointPolicy(
        midpoint_enabled=True,
        midpoint_criteria=MidpointCriteria(signals=[]),
        subagent_detector=detector,
        working_tree=WorkingTreeInspector(tmp_path),
        always_end=False,
    )
    decision = policy.decide(phase=CheckpointPhase.END_OF_TASK)
    assert decision.should_fire is False
    assert "end_of_task disabled" in decision.reason
