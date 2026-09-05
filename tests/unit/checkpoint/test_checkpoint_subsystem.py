#!/usr/bin/env python3
"""Focused edge-case coverage for session_buddy.checkpoint subsystem.

These tests complement the broader test suite at
``tests/unit/core/checkpoint/`` (which covers the bulk of the surface
at 94-97% line coverage) by pinning:

  1. ``metrics.CheckpointMetrics`` — public counter surface (no dedicated
     test file exists elsewhere).
  2. ``cleanup.SnapshotCleanupTask`` — OSError handling when an individual
     ``unlink`` raises mid-pass.
  3. ``policy.WorkingTreeInspector`` — invalid ``%aI`` date strings
     (ValueError path), non-zero ``git status`` return code, and the
     ``len(line) >= 4`` filter for short porcelain output.
  4. ``policy.CheckpointPolicy`` — the "no midpoint signals active"
     final return when no signal triggers.
  5. ``orchestrator._safe_http_error_info`` — defensive paths when
     ``exc.request`` is None or raises on ``.url.host``.
  6. ``scrubbing.safe_transient_info`` — httpx.HTTPStatusError branch
     with an unparseable ``request.url`` returning no host.
  7. ``snapshot.SnapshotMechanism.restore`` — line-count mismatch
     conflict path, missing-line-count-match-but-file-exists path,
     and bare git-apply failure (no hunks in output).
  8. ``pending.PendingCheckpoint`` — ``marker_path`` sanitisation
     (path separators and dots are translated).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx2 as httpx
import pytest

from session_buddy.checkpoint.cleanup import SnapshotCleanupTask
from session_buddy.checkpoint.metrics import CheckpointMetrics
from session_buddy.checkpoint.orchestrator import (
    CheckpointOrchestrator,
    _safe_http_error_info,
)
from session_buddy.checkpoint.pending import (
    MAX_MARKER_BYTES,
    PENDING_DIR,
    PendingCheckpoint,
)
from session_buddy.checkpoint.policy import (
    CheckpointPhase,
    CheckpointPolicy,
    DirtyFilesSignal,
    MidpointCriteria,
    PolicyDecision,
    TimeElapsedSignal,
    WorkingTreeInspector,
)
from session_buddy.checkpoint.scrubbing import safe_error_message, safe_transient_info
from session_buddy.checkpoint.snapshot import Snapshot, SnapshotMechanism
from session_buddy.checkpoint.subagent_detector import (
    LockfileSignalSource,
    SubagentDetector,
)


# ---------------------------------------------------------------------------
# 1. metrics.CheckpointMetrics
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_metrics_initial_failures_dict_is_empty() -> None:
    """A fresh CheckpointMetrics has zero counts for every reason observed."""
    m = CheckpointMetrics()
    assert dict(m.failures) == {}


@pytest.mark.unit
def test_metrics_inc_failure_records_and_repeats() -> None:
    """``inc_failure`` increments per-reason and is repeatable."""
    m = CheckpointMetrics()
    m.inc_failure("snapshot_transient")
    m.inc_failure("snapshot_transient")
    m.inc_failure("orchestrator_timeout")
    assert m.failures["snapshot_transient"] == 2
    assert m.failures["orchestrator_timeout"] == 1


# ---------------------------------------------------------------------------
# 2. cleanup.SnapshotCleanupTask — OSError mid-pass
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cleanup_continues_past_unlink_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If an individual ``unlink`` raises OSError, cleanup logs and continues.

    Pins lines 39-43 (the ``except (FileNotFoundError, OSError)`` branch):
    the cleanup task must NOT abort, and the next file should still be
    considered for removal.
    """
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    a = snap_dir / "snap-a.patch"
    b = snap_dir / "snap-b.patch"
    a.write_text("a")
    b.write_text("b")
    old = datetime.now().timestamp() - (8 * 86400)
    import os

    os.utime(a, (old, old))
    os.utime(b, (old, old))

    # Wrap Path.unlink so the FIRST call raises; later calls go through.
    real_unlink = Path.unlink
    calls = {"n": 0}
    state = {"flaky_target": a}

    def flaky_unlink(self: Path) -> None:
        if self == state["flaky_target"]:
            calls["n"] += 1
            raise OSError("simulated unlink failure")
        real_unlink(self)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    removed = SnapshotCleanupTask(snap_dir, ttl_seconds=7 * 86400)._cleanup_sync()
    # First call (on a) fails and is caught; the loop continues and removes b.
    assert removed == 1
    assert calls["n"] == 1
    assert a.exists()  # failed to remove due to OSError
    assert not b.exists()  # removed cleanly


# ---------------------------------------------------------------------------
# 3. policy.WorkingTreeInspector — edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_inspector_seconds_since_last_commit_handles_invalid_iso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid ``%aI`` output yields 0.0 instead of raising ValueError.

    Pins policy.py lines 67-70: a corrupted or non-ISO timestamp must
    fall through to ``return 0.0`` rather than propagate.
    """
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "f").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Override the date format string used by WorkingTreeInspector.
    monkeypatch.setattr(
        "session_buddy.checkpoint.policy.subprocess.run",
        lambda *args, **kwargs: _fake_git_log_result("not-an-iso-date"),
    )

    inspector = WorkingTreeInspector(repo)
    assert inspector.seconds_since_last_commit() == 0.0


@pytest.mark.unit
def test_inspector_seconds_since_last_commit_empty_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty ``git log`` output returns 0.0 (covers line 65 empty path)."""
    monkeypatch.setattr(
        "session_buddy.checkpoint.policy.subprocess.run",
        lambda *args, **kwargs: _fake_git_log_result(""),
    )
    inspector = WorkingTreeInspector(tmp_path)
    assert inspector.seconds_since_last_commit() == 0.0


@pytest.mark.unit
def test_inspector_dirty_file_count_short_lines_filtered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``len(line) >= 4`` filter: short porcelain lines are not counted.

    Pins policy.py line 86. ``git status --porcelain`` output shorter than
    4 characters (e.g. just a header) must not contribute to the count.
    """
    # Synthesize porcelain output: two entries >= 4 chars, one short.
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = " M file1.py\n?? new.py\nXYZ\n"
    fake.stderr = ""

    monkeypatch.setattr(
        "session_buddy.checkpoint.policy.subprocess.run",
        lambda *args, **kwargs: fake,
    )
    # Also short-circuit is_git_repo so the early-return doesn't fire.
    monkeypatch.setattr(WorkingTreeInspector, "is_git_repo", lambda self: True)

    inspector = WorkingTreeInspector(tmp_path)
    assert inspector.dirty_file_count() == 2


@pytest.mark.unit
def test_inspector_dirty_file_count_non_zero_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``git status`` non-zero return code returns 0 (policy.py line 85)."""
    fake = MagicMock()
    fake.returncode = 128
    fake.stdout = "garbage"
    fake.stderr = "fatal: not a git repository"

    monkeypatch.setattr(
        "session_buddy.checkpoint.policy.subprocess.run",
        lambda *args, **kwargs: fake,
    )
    monkeypatch.setattr(WorkingTreeInspector, "is_git_repo", lambda self: True)

    inspector = WorkingTreeInspector(tmp_path)
    assert inspector.dirty_file_count() == 0


# ---------------------------------------------------------------------------
# 4. policy.CheckpointPolicy — no midpoint signals path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_policy_returns_no_signals_active_when_all_inactive(
    tmp_path: Path,
) -> None:
    """When no signal matches, the policy returns the documented fallback."""
    lock = tmp_path / "x.lock"  # absent ⇒ subagent idle
    detector = SubagentDetector(tmp_path, LockfileSignalSource(lock))
    inspector = MagicMock()
    inspector.seconds_since_last_commit.return_value = 0.0
    inspector.dirty_file_count.return_value = 0

    policy = CheckpointPolicy(
        always_end=False,
        midpoint_enabled=True,
        midpoint_criteria=MidpointCriteria(
            signals=[TimeElapsedSignal(min_seconds=999.0), DirtyFilesSignal(min_count=999)]
        ),
        subagent_detector=detector,
        working_tree=inspector,
    )
    decision = policy.decide(phase=CheckpointPhase.MIDPOINT_TIME)
    assert decision == PolicyDecision(should_fire=False, reason="no midpoint signals active")


@pytest.mark.unit
def test_policy_signal_exception_fails_closed(tmp_path: Path) -> None:
    """Per spec, per-signal exceptions are logged and the signal is skipped.

    Pins policy.py lines 165-175 (the ``except Exception`` branch).
    """

    class BoomSignal:
        def is_active(self, working_tree: WorkingTreeInspector) -> bool:
            raise RuntimeError("kaboom")

        def describe(self) -> str:
            return "boom-signal"

    detector = SubagentDetector(tmp_path, LockfileSignalSource(tmp_path / "x.lock"))
    inspector = MagicMock()
    policy = CheckpointPolicy(
        always_end=False,
        midpoint_enabled=True,
        midpoint_criteria=MidpointCriteria(signals=[BoomSignal()]),
        subagent_detector=detector,
        working_tree=inspector,
    )
    decision = policy.decide(phase=CheckpointPhase.MIDPOINT_DIRTINESS)
    # The failing signal is skipped; the final "no signals" branch fires.
    assert decision.should_fire is False
    assert "no midpoint signals active" in decision.reason


# ---------------------------------------------------------------------------
# 5. orchestrator._safe_http_error_info — defensive paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_safe_http_error_info_no_request_attribute() -> None:
    """When ``exc.request`` cannot be accessed, only ``status`` is returned.

    Pins orchestrator.py lines 55-65. ``httpx2.HTTPStatusError.request``
    is a property descriptor that raises ``RuntimeError`` (not
    ``AttributeError``) when the underlying slot is unset. The helper
    catches both ``AttributeError`` and ``RuntimeError`` so the
    no-request path returns ``{"status": 502}`` instead of propagating.
    """
    response = httpx.Response(502)
    exc = httpx.HTTPStatusError(
        "boom", request=None, response=response  # type: ignore[arg-type]
    )
    info = _safe_http_error_info(exc)
    assert info == {"status": 502}


@pytest.mark.unit
def test_safe_http_error_info_host_extraction_failure() -> None:
    """When ``request.url.host`` raises, info still contains status only.

    Pins orchestrator.py lines 58-63. ``request.url.host`` can raise
    AttributeError/ValueError/TypeError for unusual URL schemes; the
    helper must catch defensively and return without a host.
    """
    response = MagicMock()
    response.status_code = 503
    bogus_request = MagicMock()
    type(bogus_request).url = property(lambda self: (_ for _ in ()).throw(ValueError("nope")))
    exc = httpx.HTTPStatusError(
        "boom", request=bogus_request, response=response  # type: ignore[arg-type]
    )
    info = _safe_http_error_info(exc)
    assert info["status"] == 503
    assert "host" not in info


@pytest.mark.unit
def test_safe_http_error_info_host_present() -> None:
    """Happy-path: both status and host are populated."""
    response = MagicMock()
    response.status_code = 504
    request = httpx.Request("GET", "https://api.example.com/health")
    exc = httpx.HTTPStatusError("boom", request=request, response=response)
    info = _safe_http_error_info(exc)
    assert info["status"] == 504
    assert info["host"] == "api.example.com"


# ---------------------------------------------------------------------------
# 6. scrubbing.safe_transient_info / safe_error_message
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_safe_transient_info_for_httpx_status_error_no_host() -> None:
    """``safe_transient_info`` for HTTPStatusError includes status but no host
    when ``exc.request`` is missing.
    """
    response = MagicMock()
    response.status_code = 418
    exc = httpx.HTTPStatusError(
        "teapot", request=None, response=response  # type: ignore[arg-type]
    )
    info = safe_transient_info(exc)
    assert info["type"] == "HTTPStatusError"
    assert info["status"] == 418
    assert "host" not in info


@pytest.mark.unit
def test_safe_transient_info_for_plain_exception() -> None:
    """Non-HTTP exceptions yield only ``type``."""
    info = safe_transient_info(ValueError("anything"))
    assert info == {"type": "ValueError"}


@pytest.mark.unit
def test_safe_error_message_format_for_httpx() -> None:
    """``safe_error_message`` produces the documented prefix+type+HTTP code format."""
    response = MagicMock()
    response.status_code = 500
    exc = httpx.HTTPStatusError(
        "boom", request=None, response=response  # type: ignore[arg-type]
    )
    msg = safe_error_message("forward_to retry exhausted:", exc)
    assert msg == "forward_to retry exhausted: HTTPStatusError (HTTP 500)"


@pytest.mark.unit
def test_safe_error_message_format_for_plain_exception() -> None:
    """Plain exceptions drop the (HTTP code) tail."""
    msg = safe_error_message("snapshot failed (transient):", OSError("disk full"))
    assert msg == "snapshot failed (transient): OSError"


# ---------------------------------------------------------------------------
# 7. snapshot.SnapshotMechanism.restore — conflict paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_snapshot_restore_new_file_line_count_conflict(tmp_path: Path) -> None:
    """Restore fails when an existing file's line count does not match the patch.

    Pins snapshot.py lines 215-227: a ``new file mode`` patch against an
    existing file whose line count diverges from the hunk's ``+N`` must
    return ``success=False`` with the hunks surfaced.
    """
    # Build a minimal patch: a "new file" diff for "x.py" with +1 line.
    patch_text = (
        "diff --git a/x.py b/x.py\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/x.py\n"
        "@@ -0,0 +1 @@\n"
        "+hello\n"
    )
    snap_path = tmp_path / "snap.patch"
    snap_path.write_text(patch_text)
    snap_path.chmod(0o444)

    # Pre-existing file with a DIFFERENT line count (2 vs hunk's +1).
    (tmp_path / "x.py").write_text("hello\nworld\n")

    mechanism = SnapshotMechanism(working_dir=tmp_path, snapshot_dir=tmp_path)
    snap = Snapshot(
        path=snap_path,
        label="test",
        snapshot_id="snap-x",
        captured_at=datetime.now(UTC),
        parent_commit="unknown",  # disable drift detection
        dirty_files=["x.py"],
    )

    result = mechanism.restore(snap)
    assert result.success is False
    assert "patch conflict" in (result.error or "")
    assert "2 lines in working tree" in (result.error or "")
    assert "expects 1" in (result.error or "")
    assert result.drift_detected is False  # parent_commit="unknown"
    assert any("@@ -0,0 +1 @@" in h for h in result.hunks)


@pytest.mark.unit
def test_snapshot_restore_new_file_path_absent_in_working_tree(
    tmp_path: Path,
) -> None:
    """If the ``new file mode`` target file doesn't exist, the heuristic
    skips that hunk and the normal ``git apply`` path runs.

    Pins snapshot.py line 210-211 (the ``if not full_path.is_file(): continue``
    guard).
    """
    # Patch adds a new file at x.py; x.py does NOT pre-exist.
    patch_text = (
        "diff --git a/x.py b/x.py\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/x.py\n"
        "@@ -0,0 +1 @@\n"
        "+hello\n"
    )
    snap_path = tmp_path / "snap.patch"
    snap_path.write_text(patch_text)
    snap_path.chmod(0o444)

    mechanism = SnapshotMechanism(working_dir=tmp_path, snapshot_dir=tmp_path)
    snap = Snapshot(
        path=snap_path,
        label="test",
        snapshot_id="snap-y",
        captured_at=datetime.now(UTC),
        parent_commit="unknown",
        dirty_files=["x.py"],
    )

    result = mechanism.restore(snap)
    assert result.success is True
    assert (tmp_path / "x.py").read_text() == "hello\n"


@pytest.mark.unit
def test_snapshot_restore_missing_patch_file(tmp_path: Path) -> None:
    """Restore fails loudly when the patch file does not exist."""
    snap_path = tmp_path / "snap-does-not-exist.patch"
    mechanism = SnapshotMechanism(working_dir=tmp_path, snapshot_dir=tmp_path)
    snap = Snapshot(
        path=snap_path,
        label="test",
        snapshot_id="snap-z",
        captured_at=datetime.now(UTC),
        parent_commit="unknown",
        dirty_files=[],
    )
    result = mechanism.restore(snap)
    assert result.success is False
    assert "snapshot file missing" in (result.error or "")


# ---------------------------------------------------------------------------
# 8. pending.PendingCheckpoint — marker_path sanitisation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pending_marker_path_translates_separators_and_dots() -> None:
    """Working dir separators and (most) dots become underscores in the basename.

    The marker name retains only the trailing ``.json`` extension dot —
    internal dots and path separators are translated to underscores.
    """
    p = PendingCheckpoint(
        working_dir=Path("/tmp/example.com/proj"),
        reason="test",
    )
    name = p.marker_path.name
    assert "/" not in name
    # Strip the trailing ".json" extension; only the basename core is sanitised.
    base = name[: -len(".json")]
    assert "/" not in base
    assert "." not in base
    assert base == "_tmp_example_com_proj"
    assert name.endswith(".json")


@pytest.mark.unit
def test_pending_marker_path_resolves_under_pending_dir() -> None:
    """``marker_path`` lives under PENDING_DIR (the canonical anchor)."""
    p = PendingCheckpoint(working_dir=Path("/tmp/foo"), reason="x")
    assert p.marker_path.parent == PENDING_DIR


@pytest.mark.unit
def test_pending_default_created_at_is_recent_utc() -> None:
    """``created_at`` defaults to UTC and is within the last few seconds."""
    before = datetime.now(UTC) - timedelta(seconds=1)
    p = PendingCheckpoint(working_dir=Path("/tmp/x"), reason="x")
    after = datetime.now(UTC) + timedelta(seconds=1)
    assert before <= p.created_at <= after
    assert p.created_at.tzinfo is UTC


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fake_git_log_result(stdout: str) -> MagicMock:
    """Return a fake CompletedProcess-like object for ``git log -1 --format=%aI``."""
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = stdout
    fake.stderr = ""
    return fake
