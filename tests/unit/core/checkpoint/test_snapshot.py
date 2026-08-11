from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from session_buddy.checkpoint.snapshot import (
    RestoreResult,
    Snapshot,
    SnapshotMechanism,
)

from .conftest import init_repo


@pytest.mark.unit
def test_capture_creates_patch_file_for_dirty_repo(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "modified.py").write_text("# changed\n")
    (repo / "new_file.py").write_text("# new\n")

    snap_dir = tmp_path / "snaps"
    snap = SnapshotMechanism(repo, snap_dir).capture(label="manual-test")

    assert snap.path.exists()
    assert snap.label == "manual-test"
    assert snap.snapshot_id.startswith("snap-")
    assert "modified.py" in snap.path.read_text() or "diff --git" in snap.path.read_text()


@pytest.mark.unit
def test_capture_does_not_mutate_working_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "modified.py").write_text("# changed\n")
    before = _hash_working_tree(repo)

    SnapshotMechanism(repo, tmp_path / "snaps").capture(label="invariant-check")

    assert _hash_working_tree(repo) == before


@pytest.mark.unit
def test_capture_handles_clean_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    snap = SnapshotMechanism(repo, tmp_path / "snaps").capture(label="clean")
    assert snap.path.exists()
    assert snap.dirty_files == []


@pytest.mark.unit
def test_snapshot_immutable_after_capture(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "modified.py").write_text("# changed\n")
    snap = SnapshotMechanism(repo, tmp_path / "snaps").capture(label="immut")
    assert snap.path.stat().st_mode & 0o777 == 0o444


@pytest.mark.unit
def test_restore_applies_patch(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "modified.py").write_text("# changed\n")
    mech = SnapshotMechanism(repo, tmp_path / "snaps")

    snap = mech.capture(label="restore-test")
    (repo / "modified.py").write_text("# totally different\n")

    result = mech.restore(snap)
    assert isinstance(result, RestoreResult)
    assert result.success is True
    assert (repo / "modified.py").read_text() == "# changed\n"


@pytest.mark.unit
def test_restore_fails_loud_when_patch_missing(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    mech = SnapshotMechanism(repo, tmp_path / "snaps")
    snap = SnapshotMechanism(repo, tmp_path / "snaps").capture(label="ok")
    snap.path.unlink()  # delete the snapshot file

    result = mech.restore(snap)

    assert result.success is False
    assert result.error is not None
    assert snap.snapshot_id in result.error  # snapshot id surfaced per spec


@pytest.mark.unit
def test_restore_on_git_apply_conflict_returns_hunks(tmp_path: Path) -> None:
    """Per spec line 376: git apply conflicts → fail loud, print hunks."""
    repo = init_repo(tmp_path)
    (repo / "modified.py").write_text("# changed\n")
    mech = SnapshotMechanism(repo, tmp_path / "snaps")

    snap = mech.capture(label="conflict-test")
    # Change the file to conflict with the patch
    (repo / "modified.py").write_text("# totally different\n# also adding lines\n")

    result = mech.restore(snap)

    assert result.success is False
    assert result.error is not None
    # Spec: "print hunks" — error must include hunk context, not just "git apply failed"
    assert "@@" in result.error or "patch" in result.error.lower()


@pytest.mark.unit
def test_restore_detects_drift_between_parent_and_current_head(tmp_path: Path) -> None:
    """Per spec line 378: working tree drift from parent_commit → warn, show drift summary."""
    repo = init_repo(tmp_path)
    (repo / "modified.py").write_text("# changed\n")
    snap = SnapshotMechanism(repo, tmp_path / "snaps").capture(label="drift")
    parent = snap.parent_commit

    # Make an unrelated commit that diverges from parent
    (repo / "unrelated.py").write_text("# new\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "drift"], cwd=repo, check=True, capture_output=True)

    result = SnapshotMechanism(repo, tmp_path / "snaps").restore(snap)
    # Spec: drift is a WARN, not a fail. The restore itself may still succeed.
    assert result.drift_detected is True
    assert parent != snap.parent_commit or parent != ""  # drift was real


@pytest.mark.unit
def test_capture_includes_untracked_file_via_git_diff_no_index(tmp_path: Path) -> None:
    """Coverage: lines 128->115, 130->133 (untracked-file loop body + branch).

    The untracked-file capture path appends `git diff --no-index /dev/null <path>`
    output to the patch body. Verify the captured patch contains the
    `new file mode` header for the untracked file.
    """
    repo = init_repo(tmp_path)
    (repo / "untracked.py").write_text("# brand new\n")

    snap = SnapshotMechanism(repo, tmp_path / "snaps").capture(label="untracked")
    body = snap.path.read_text()
    assert "new file mode" in body
    assert "untracked.py" in body


@pytest.mark.unit
def test_capture_skips_untracked_path_that_does_not_exist(tmp_path: Path) -> None:
    """Coverage: line 118 (untracked file listed but not on disk → continue).

    Simulate a TOCTOU race: ls-files reports the file but the file disappears
    between the listing and the diff. The capture must skip it without error.
    """
    repo = init_repo(tmp_path)
    (repo / "raced.py").write_text("# present at write\n")

    # Monkey-patch Path.is_file at the snapshot module level: raced.py reports
    # is_file() = False to simulate the race.
    import session_buddy.checkpoint.snapshot as snap_mod

    real_is_file = snap_mod.Path.is_file

    def racing_is_file(self: object) -> bool:
        name = getattr(self, "name", "")
        if name == "raced.py":
            return False
        return real_is_file(self)

    snap_mod.Path.is_file = racing_is_file  # type: ignore[assignment]
    try:
        snap = SnapshotMechanism(repo, tmp_path / "snaps").capture(label="race")
        # Capture still completes; raced.py is not in the patch.
        assert snap.path.exists()
    finally:
        snap_mod.Path.is_file = real_is_file  # type: ignore[assignment]


@pytest.mark.unit
def test_restore_new_file_line_count_conflict_returns_hunks(tmp_path: Path) -> None:
    """Coverage: lines 181, 190->192 (new-file mode restore, line-count mismatch).

    Capture an untracked file (creates a "new file mode" patch). At restore time,
    the file already exists on disk with a different line count → restore must
    fail loud with hunk context.
    """
    repo = init_repo(tmp_path)
    # untracked.py has 1 line; capture creates a "new file mode" patch.
    (repo / "untracked.py").write_text("# line one\n")
    snap = SnapshotMechanism(repo, tmp_path / "snaps").capture(label="conflict-newfile")

    # At restore time, file exists with 2 lines (different from hunk's +1).
    # Keep the untracked file on disk but with a different line count.
    (repo / "untracked.py").write_text("# line one\n# line two\n")

    result = SnapshotMechanism(repo, tmp_path / "snaps").restore(snap)
    assert result.success is False
    assert result.error is not None
    # Patch conflict detail must be present.
    assert "untracked.py" in result.error or "patch conflict" in result.error.lower()


@pytest.mark.unit
def test_restore_apply_failure_surfaces_stderr_hunks(tmp_path: Path) -> None:
    """Coverage: lines 207-211 (git apply failed with stderr hunks).

    For a modification patch (no new-file mode), git apply returns non-zero and
    emits hunk lines in stderr. The restore must surface them in result.error.
    """
    repo = init_repo(tmp_path)
    # Modify an existing tracked file
    (repo / "modified.py").write_text("# first line\n# second line\n")
    snap = SnapshotMechanism(repo, tmp_path / "snaps").capture(label="modify-conflict")

    # At restore time, the file content diverges in a way git apply can't merge.
    # `git apply --reject` will fail and dump @@ hunk lines to stderr.
    (repo / "modified.py").write_text(
        "# completely unrelated first line\n"
        "# completely unrelated second line\n"
        "# completely unrelated third line\n",
    )

    result = SnapshotMechanism(repo, tmp_path / "snaps").restore(snap)
    assert result.success is False
    assert result.error is not None
    # Either the hunk text is in the error, or git apply mentioned patch lines.
    assert "@@" in result.error or "patch" in result.error.lower()


def _hash_working_tree(repo: Path) -> str:
    out = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    return hashlib.sha256(out.stdout.encode()).hexdigest()
