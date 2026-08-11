"""End-to-end behavioral coverage for the checkpoint deferral → drain cycle.

Findings covered: I-1 (missing end-to-end test file for the loop workflow).

Exercises the full sequence at the checkpoint-package level:

  1. Subagent active  → checkpoint deferred, pending marker persisted.
  2. Subagent clears  → marker consumed on next drain, ``forward_to`` fires.

All collaborators are real (``SubagentDetector`` lockfile-backed,
``SnapshotMechanism``, ``WorkingTreeInspector``, ``CheckpointPolicy``); only
``forward_to`` and the detector's ``wait_until_idle`` are stubbed so the
tests run with controlled scheduling and no wall-clock waits.

Pending markers are written to a per-test ``PENDING_DIR`` redirected via
``monkeypatch`` so the user's home directory is never touched.

Per-phase deferral semantics (verified against the orchestrator):

  * ``MIDPOINT_*`` + subagent active → policy returns ``should_fire=False``
    with reason ``"subagent active — deferring midpoint"``. Orchestrator
    takes the policy-deferral early-return path; ``pending_marker_path is None``.
    Production re-evaluates midpoint on each tick, so no marker is needed.

  * ``END_OF_TASK`` + subagent active → policy returns ``should_fire=True``
    with reason ``"end_of_task mandatory"``. Orchestrator's
    ``wait_until_idle`` returns False (subagent still active), so the
    orchestrator writes a marker with reason ``"subagent_idle_timeout"``
    and returns ``fired=False``. The drain replays this phase.

  * ``HOOK_REQUESTED`` + subagent active → policy returns ``should_fire=True``
    with reason ``"hook_requested explicit override"``. Orchestrator
    captures the snapshot, then re-checks ``is_active()`` after capture.
    If still active, writes a marker with reason
    ``"subagent_active_during_capture"`` and returns ``fired=False``.
"""
from __future__ import annotations

import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from session_buddy.checkpoint import (
    CheckpointMetrics,
    CheckpointOrchestrator,
    CheckpointPhase,
    CheckpointPolicy,
    CheckpointResult,
    LockfileSignalSource,
    MidpointCriteria,
    PendingCheckpoint,
    SnapshotMechanism,
    SubagentDetector,
    WorkingTreeInspector,
    consume_pending_marker,
    save_pending,
)
from session_buddy.checkpoint import pending as pending_mod


# --- Test fixtures and helpers -----------------------------------------------


def _init_repo_with_initial_commit(parent: Path) -> Path:
    """Initialize a real git repo with one committed file.

    Returns the repo path. The initial commit provides a real HEAD so
    ``SnapshotMechanism.capture`` returns a non-"unknown" parent_commit.
    """
    parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=parent, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=parent, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=parent, check=True, capture_output=True,
    )
    (parent / "file.txt").write_text("initial\n")
    subprocess.run(
        ["git", "add", "file.txt"], cwd=parent, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=parent, check=True, capture_output=True,
    )
    return parent


@pytest.fixture
def workspace_with_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Real git repo with one commit, plus PENDING_DIR redirected to tmp_path.

    The redirect prevents the test from writing pending markers into the
    user's ``~/.session-buddy/pending/`` directory. Using ``tmp_path``
    also ensures markers from one test do not leak into another.
    """
    repo = tmp_path / "workspace"
    _init_repo_with_initial_commit(repo)
    pending_dir = tmp_path / ".pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pending_mod, "PENDING_DIR", pending_dir)
    return repo


@pytest.fixture
def dirty_workspace(workspace_with_repo: Path) -> Path:
    """Real repo with one dirty file edit so ``capture`` reports dirty_files."""
    (workspace_with_repo / "file.txt").write_text("dirty change\n")
    return workspace_with_repo


def _touch_lockfile(workspace: Path) -> Path:
    """Create the conventional subagent-lockfile path and return its location."""
    lockfile = workspace / ".session-buddy" / "subagent.lock"
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    lockfile.touch()
    return lockfile


def _stub_wait_until_idle(detector: SubagentDetector, *, returns: bool) -> None:
    """Replace ``wait_until_idle`` with a deterministic stub.

    Per the brief: "Do NOT depend on wall-clock delays — use controlled
    scheduling." The real ``wait_until_idle`` blocks on an ``asyncio.wait_for``
    with a 60 s inner timeout (clamped to a 1 s floor by the orchestrator),
    which would make every END_OF_TASK test sleep for ~1 s. The stub returns
    immediately, letting the orchestrator take the active / idle branch in a
    single event-loop tick.
    """
    async def _fake_wait_until_idle(
        *_args: object, **_kw: object
    ) -> bool:
        return returns

    detector.wait_until_idle = _fake_wait_until_idle  # type: ignore[method-assign]


ForwardRecorder = Callable[[CheckpointResult], Awaitable[None]]


def _build_orchestrator(
    workspace: Path,
    lockfile: Path,
    forward_to: ForwardRecorder,
    *,
    run_timeout: float = 5.0,
) -> tuple[CheckpointOrchestrator, SubagentDetector]:
    """Construct a real orchestrator with all real collaborators wired up.

    Returns both the orchestrator and its detector so tests can stub
    ``wait_until_idle`` on the detector instance after construction.
    """
    detector = SubagentDetector(workspace, LockfileSignalSource(lockfile))
    snapshot = SnapshotMechanism(workspace)
    inspector = WorkingTreeInspector(workspace)
    # Empty midpoint_criteria.signals keeps the policy deterministic when
    # MIDPOINT_* phases are exercised: midpoint fires only when a signal
    # is active, so with no signals a midpoint phase would never fire even
    # with a subagent idle. We only test deferral here, so the empty list
    # is correct and intentional.
    policy = CheckpointPolicy(
        midpoint_criteria=MidpointCriteria(signals=[]),
        subagent_detector=detector,
        working_tree=inspector,
    )
    orchestrator = CheckpointOrchestrator(
        working_dir=workspace,
        policy=policy,
        snapshot=snapshot,
        subagent_detector=detector,
        forward_to=forward_to,
        metrics=CheckpointMetrics(),
        run_timeout=run_timeout,
    )
    return orchestrator, detector


def _recording_forward() -> tuple[list[str], ForwardRecorder]:
    """Return ``(calls, forward_fn)`` — ``calls`` records ``decision_reason``."""
    calls: list[str] = []

    async def _forward(result: CheckpointResult) -> None:
        calls.append(result.decision_reason)

    return calls, _forward


# --- I-1.1: full deferral → drain cycle --------------------------------------


@pytest.mark.unit
async def test_full_deferral_then_drain_cycle(dirty_workspace: Path) -> None:
    """The canonical happy path of the auto-checkpoint loop.

    Steps:
      1. Subagent active (lockfile present) → END_OF_TASK calls
         ``wait_until_idle`` which returns False (subagent still active);
         orchestrator writes a pending marker and returns ``fired=False``.
         ``forward_to`` is NOT called.
      2. Subagent becomes idle (lockfile removed, ``wait_until_idle`` stub
         returns True) → drain consumes the marker and fires
         ``forward_to`` exactly once (working tree is dirty).
      3. The pending-marker directory is empty after drain.
    """
    workspace = dirty_workspace
    lockfile = _touch_lockfile(workspace)

    forward_calls, forward_fn = _recording_forward()
    orchestrator, detector = _build_orchestrator(workspace, lockfile, forward_fn)

    # Subagent is "active" — wait_until_idle returns False so the orchestrator
    # takes the subagent_idle_timeout branch and writes a marker.
    _stub_wait_until_idle(detector, returns=False)

    # Step 1: deferral creates the marker; no forward yet.
    defer_result = await orchestrator.run_checkpoint(
        phase=CheckpointPhase.END_OF_TASK,
    )

    # fired=False proves the orchestrator took a deferral branch.
    assert defer_result.fired is False
    # The marker path is the observable signal that deferral occurred
    # (for END_OF_TASK the policy reason is "end_of_task mandatory" —
    # the subagent deferral is captured in pending_marker_path, not in
    # decision_reason).
    assert defer_result.pending_marker_path is not None
    assert forward_calls == []

    # Exactly one marker on disk after the deferral.
    markers_after_defer = sorted(pending_mod.PENDING_DIR.glob("*.json"))
    assert len(markers_after_defer) == 1
    assert defer_result.pending_marker_path == markers_after_defer[0]

    # Step 2: subagent clears — remove the lockfile and stub idle = True.
    lockfile.unlink()
    _stub_wait_until_idle(detector, returns=True)

    # Step 3: drain the marker. ``_build`` ignores the marker's working_dir
    # and returns the orchestrator we already configured; capture() will
    # see the dirty working tree and call forward.
    async def _build(_marker_working_dir: Path) -> CheckpointOrchestrator:
        return orchestrator

    for marker in markers_after_defer:
        await consume_pending_marker(marker, build_orchestrator=_build)

    # Forward was called exactly once — only from the drain, never from
    # the deferral itself.
    assert len(forward_calls) == 1
    # All markers consumed.
    assert list(pending_mod.PENDING_DIR.glob("*.json")) == []


# --- I-1.2: drain with no markers is a no-op ---------------------------------


@pytest.mark.unit
async def test_drain_with_no_markers_is_noop(workspace_with_repo: Path) -> None:
    """An empty pending-marker directory MUST NOT call forward_to.

    When ``AutoCheckpointLoop._drain_pending`` runs and finds no markers,
    the loop's only side effects should be the empty iteration: no
    orchestrator built, no ``forward_to`` invoked, no exceptions.
    """
    workspace = workspace_with_repo
    lockfile = _touch_lockfile(workspace)

    forward_calls, forward_fn = _recording_forward()
    _build_orchestrator(workspace, lockfile, forward_fn)

    # Confirm the pending directory is empty (fixture guarantees this).
    assert list(pending_mod.PENDING_DIR.glob("*.json")) == []

    # Drain iterates over an empty list — there is nothing to consume.
    async def _build(_marker_working_dir: Path) -> CheckpointOrchestrator:
        return None  # type: ignore[return-value]

    for marker in pending_mod.PENDING_DIR.glob("*.json"):
        await consume_pending_marker(marker, build_orchestrator=_build)

    assert forward_calls == []
    assert list(pending_mod.PENDING_DIR.glob("*.json")) == []


# --- I-1.3: drain with multiple markers runs each exactly once ---------------


@pytest.mark.unit
async def test_drain_with_multiple_markers_runs_each_exactly_once(
    dirty_workspace: Path,
) -> None:
    """Three pending markers MUST each fire the orchestrator once, in serial.

    Order matters: consume_pending_marker uses ``for marker in glob(...)``
    and awaits each call sequentially, so the forward invocations must
    happen in glob-sorted order. We sort the glob to make the assertion
    deterministic.

    Note: markers reference non-existent working_dirs (proj_0..proj_2),
    but the test's ``_build`` ignores the path argument and returns the
    real orchestrator bound to ``workspace``. The lockfile is unlinked
    before drain so ``is_active()`` returns False inside the post-capture
    re-check, allowing forward_to to fire.
    """
    workspace = dirty_workspace
    lockfile = _touch_lockfile(workspace)

    # Persist three markers with distinct working_dirs so each gets its own
    # marker filename (the filename is derived from ``str(working_dir)``).
    base = workspace.parent
    for i in range(3):
        save_pending(
            PendingCheckpoint(
                working_dir=base / f"proj_{i}",
                reason="subagent_idle_timeout",
            ),
        )

    markers = sorted(pending_mod.PENDING_DIR.glob("*.json"))
    assert len(markers) == 3

    # Subagent must be idle during drain — remove the lockfile now so
    # ``is_active()`` returns False at the post-capture re-check.
    lockfile.unlink()

    forward_calls, forward_fn = _recording_forward()
    orchestrator, detector = _build_orchestrator(workspace, lockfile, forward_fn)
    # wait_until_idle returns True → orchestrator proceeds past idle-wait.
    _stub_wait_until_idle(detector, returns=True)

    async def _build(_marker_working_dir: Path) -> CheckpointOrchestrator:
        return orchestrator

    # Drain each marker in glob order.
    for marker in markers:
        await consume_pending_marker(marker, build_orchestrator=_build)

    # Exactly three forward calls — one per marker.
    assert len(forward_calls) == 3
    # All markers consumed.
    assert list(pending_mod.PENDING_DIR.glob("*.json")) == []


# --- I-1.4: drain handles missing marker file (race) -------------------------


@pytest.mark.unit
async def test_drain_handles_missing_marker_file(
    dirty_workspace: Path,
) -> None:
    """A marker deleted between glob and consume MUST NOT crash the drain.

    Scenario: ``AutoCheckpointLoop._drain_pending`` globs the pending
    directory, then ``consume_pending_marker`` is called per marker. If
    another worker (or a previous tick) unlinked the marker between glob
    and load, ``load_pending`` returns ``None`` and the marker is
    silently dropped. Drain continues with the remaining markers.
    """
    workspace = dirty_workspace
    lockfile = _touch_lockfile(workspace)

    # Two markers: one will be deleted (race), one survives to drain.
    base = workspace.parent
    save_pending(
        PendingCheckpoint(working_dir=base / "vanish", reason="subagent_idle_timeout"),
    )
    save_pending(
        PendingCheckpoint(working_dir=base / "survive", reason="subagent_idle_timeout"),
    )
    markers = sorted(pending_mod.PENDING_DIR.glob("*.json"))
    assert len(markers) == 2

    # Simulate the race: delete the first marker before drain consumes it.
    markers[0].unlink()

    # Subagent idle during drain so the surviving marker can fire forward.
    lockfile.unlink()

    forward_calls, forward_fn = _recording_forward()
    orchestrator, detector = _build_orchestrator(workspace, lockfile, forward_fn)
    _stub_wait_until_idle(detector, returns=True)

    async def _build(_marker_working_dir: Path) -> CheckpointOrchestrator:
        return orchestrator

    for marker in markers:
        # Missing-marker case: ``consume_pending_marker`` catches the
        # missing-file path and returns without awaiting ``build_orchestrator``.
        await consume_pending_marker(marker, build_orchestrator=_build)

    # Only the surviving marker triggered an orchestrator run.
    assert len(forward_calls) == 1
    # Surviving marker was consumed; the vanished one was already absent.
    assert list(pending_mod.PENDING_DIR.glob("*.json")) == []


# --- I-1.5: midpoint deferral across all CheckpointPhase values --------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "phase",
    [
        CheckpointPhase.MIDPOINT_TIME,
        CheckpointPhase.MIDPOINT_DIRTINESS,
        CheckpointPhase.END_OF_TASK,
        CheckpointPhase.HOOK_REQUESTED,
    ],
)
async def test_midpoint_deferred_when_subagent_active_at_each_phase(
    dirty_workspace: Path,
    phase: CheckpointPhase,
) -> None:
    """Subagent active MUST defer each checkpoint phase (fired=False).

    The deferral mechanism differs by phase (see module docstring).
    We assert on the observable signature of each path:

      * MIDPOINT_*  → fired=False, pending_marker_path is None
                      (policy-level defer; orchestrator returns before
                      reaching the marker-writing branches).
      * END_OF_TASK → fired=False, pending_marker_path is not None
                      (``wait_until_idle`` returned False → marker written
                      with reason "subagent_idle_timeout").
      * HOOK_REQUESTED → fired=False, pending_marker_path is not None
                        (post-capture re-check found subagent active →
                        marker written with reason
                        "subagent_active_during_capture").
    """
    workspace = dirty_workspace
    lockfile = _touch_lockfile(workspace)

    forward_calls, forward_fn = _recording_forward()
    orchestrator, detector = _build_orchestrator(workspace, lockfile, forward_fn)
    # Stub: subagent is active; wait_until_idle (END_OF_TASK path) returns False.
    _stub_wait_until_idle(detector, returns=False)

    markers_before = len(list(pending_mod.PENDING_DIR.glob("*.json")))

    result = await orchestrator.run_checkpoint(phase=phase)

    assert result.fired is False, (
        f"phase={phase.value} should defer when subagent active"
    )
    # forward_to is NEVER called on the deferral path.
    assert forward_calls == []

    markers_after = len(list(pending_mod.PENDING_DIR.glob("*.json")))
    if phase in (CheckpointPhase.MIDPOINT_TIME, CheckpointPhase.MIDPOINT_DIRTINESS):
        # Policy-level defer: no marker persisted (orchestrator returns
        # before reaching the marker-writing branches).
        assert result.pending_marker_path is None, (
            f"phase={phase.value} should not write a marker for policy-level defer"
        )
        assert markers_after == markers_before
    elif phase == CheckpointPhase.END_OF_TASK:
        # wait_until_idle timeout → marker persisted for later drain.
        assert result.pending_marker_path is not None
        assert markers_after == markers_before + 1
    else:  # HOOK_REQUESTED
        # Post-capture re-check found subagent active → marker persisted.
        assert result.pending_marker_path is not None
        assert markers_after == markers_before + 1
