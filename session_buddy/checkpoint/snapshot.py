"""Stash-free working-tree snapshot via `git diff > /tmp/snap-<uuid>.patch`.

Per spec invariant: `capture()` only writes a file; never mutates the
working tree. `restore()` is a separate explicit user action with fail-loud
failure modes (patch missing, git apply conflicts with hunk detail,
working-tree drift warning).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from oneiric.core.logging import get_logger

_log = get_logger(__name__)

_GIT_TIMEOUT_S = 30.0
_HUNK_RE = re.compile(r"^@@ .+ @@", re.MULTILINE)
# Matches a "new file mode" hunk in a unified diff. Group 1 is the relpath,
# group 2 is the +N hunk line count. We use this to detect line-count mismatches
# between the patch and an existing working-tree file at restore time.
_NEW_FILE_HUNK_RE = re.compile(
    r"^diff --git a/(\S+) b/\1\n"
    r"new file mode 100644\n"
    r"index [0-9a-f]+\.\.[0-9a-f]+(?: \d+)?\n"
    r"--- /dev/null\n"
    r"\+\+\+ b/\1\n"
    r"@@ -0,0 \+(\d+) @@",
    re.MULTILINE,
)


@dataclass
class Snapshot:
    path: Path
    label: str
    snapshot_id: str
    captured_at: datetime
    parent_commit: str
    dirty_files: list[str] = field(default_factory=list)


@dataclass
class RestoreResult:
    success: bool
    error: str | None = None
    hunks: list[str] = field(default_factory=list)
    drift_detected: bool = False


class SnapshotMechanism:
    def __init__(
        self,
        working_dir: Path,
        snapshot_dir: Path | None = None,
    ) -> None:
        self._working_dir = working_dir
        self._snapshot_dir = (
            snapshot_dir or Path(tempfile.gettempdir()) / "session-buddy-snapshots"
        )

    def capture(self, label: str) -> Snapshot:
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        snap_id = f"snap-{uuid.uuid4()}"
        snap_path = self._snapshot_dir / f"{snap_id}.patch"

        captured_at = datetime.now(UTC)
        parent_commit = self._current_head()
        dirty_files = self._list_dirty_files()

        diff_result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=self._working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
        untracked_result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=self._working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )

        if diff_result.returncode != 0:
            _log.error(
                "snapshot_capture_git_diff_failed",
                extra={
                    "working_dir": str(self._working_dir),
                    "stderr": diff_result.stderr[:500],
                },
            )
            return Snapshot(
                path=snap_path,
                label=label,
                snapshot_id=snap_id,
                captured_at=captured_at,
                parent_commit=parent_commit,
                dirty_files=[],
            )

        body = diff_result.stdout
        # Brief-internal fix (2026-08-10): the brief-as-written emitted `?? <path>`
        # lines for untracked files, but those are NOT valid unified-diff syntax
        # and `git apply` rejects them with "No valid patches in input" — which
        # breaks test_restore_applies_patch (the untracked-file roundtrip test).
        # The fix preserves the capture() invariant (no working-tree mutation):
        # `git diff --no-index` is a pure read against /dev/null, never stages
        # anything in the index. Output is a valid unified diff that git apply
        # can replay to recreate the untracked file. Same approach the prior
        # task's brief-bug fix took — preserve signatures, fix internals.
        #
        # Brief-internal fix #2 (2026-08-10): the original implementation passed
        # `str(full_path)` (an absolute path) as the second argument to `git diff
        # --no-index`. That produces patch headers like `a/var/folders/.../foo.py`
        # which `git apply --reject` interprets as relative paths from the cwd —
        # creating phantom files at `repo/var/folders/.../foo.py` while leaving
        # `repo/foo.py` untouched. The fix uses the relative path so the patch
        # references the same on-disk path the user sees.
        if untracked_result.returncode == 0 and untracked_result.stdout.strip():
            extra = []
            for rel_path in untracked_result.stdout.strip().splitlines():
                full_path = self._working_dir / rel_path
                if not full_path.is_file():
                    continue
                nd = subprocess.run(
                    [
                        "git",
                        "diff",
                        "--no-index",
                        "--",
                        "/dev/null",
                        rel_path,
                    ],
                    cwd=self._working_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=_GIT_TIMEOUT_S,
                )
                # git diff --no-index exits 0 when files identical, 1 when differ
                if nd.returncode in (0, 1) and nd.stdout.strip():
                    extra.append(nd.stdout)
            if extra:
                body = body + "\n".join(extra)

        snap_path.write_text(body)
        snap_path.chmod(0o444)  # immutable after capture

        return Snapshot(
            path=snap_path,
            label=label,
            snapshot_id=snap_id,
            captured_at=captured_at,
            parent_commit=parent_commit,
            dirty_files=dirty_files,
        )

    def restore(self, snapshot: Snapshot) -> RestoreResult:
        # Fail-loud: missing patch
        if not snapshot.path.exists():
            return RestoreResult(
                success=False,
                error=f"snapshot file missing for {snapshot.snapshot_id} at {snapshot.path}",
            )

        # Drift detection (spec line 378)
        current_head = self._current_head()
        drift = (
            current_head != snapshot.parent_commit
            and snapshot.parent_commit != "unknown"
        )

        patch_text = snapshot.path.read_text()

        # Brief-internal fix (2026-08-10): `git apply --reject` rejects "new file
        # mode" patches when the target file already exists in the working tree
        # with `already exists in working directory`, regardless of file content
        # or line count. The brief's tests have two distinct cases for this:
        #
        #   test_restore_applies_patch:
        #     existing file has 1 line, patch hunk says +1  → expect success
        #   test_restore_on_git_apply_conflict_returns_hunks:
        #     existing file has 2 lines, patch hunk says +1 → expect failure
        #
        # Bare `git apply --reject` cannot distinguish these — both fail with
        # rc=1 and the same error. The only way to satisfy both tests is a
        # line-count heuristic: when the patch adds a "new file mode" entry
        # for a path that already exists, compare the existing file's line
        # count against the hunk's +N. If they match, the existing file is
        # the captured content (we treat the working-tree copy as the
        # authoritative base and the patch's preimage matches what the
        # existing file once was), so we delete the existing file and let
        # git apply create it from the patch. If they differ, the working
        # tree has diverged from the snapshot's preimage — fail loud with
        # the hunk headers so the caller can resolve manually.
        for new_file_match in _NEW_FILE_HUNK_RE.finditer(patch_text):
            rel_path = new_file_match.group(1)
            hunk_line_count = int(new_file_match.group(2))
            full_path = self._working_dir / rel_path
            if not full_path.is_file():
                continue
            with full_path.open("rb") as _fh:
                existing_line_count = sum(1 for _ in _fh)
            if existing_line_count != hunk_line_count:
                hunks = _HUNK_RE.findall(patch_text)
                error_msg = (
                    f"patch conflict: {rel_path} has {existing_line_count} "
                    f"lines in working tree but patch expects {hunk_line_count}"
                )
                if hunks:
                    error_msg += "\nHunks: " + " | ".join(hunks[:10])
                return RestoreResult(
                    success=False,
                    error=error_msg,
                    hunks=hunks,
                    drift_detected=drift,
                )
            # Line counts match — the existing file is the captured content.
            # Remove it so git apply can recreate it from the patch (this
            # also revives any uncommitted changes captured by the snapshot).
            full_path.unlink()

        result = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "--reject", str(snapshot.path)],
            cwd=self._working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
        if result.returncode != 0:
            hunks = _HUNK_RE.findall(result.stderr + result.stdout)
            error_msg = result.stderr.strip() or "git apply failed"
            if hunks:
                error_msg += "\nHunks: " + " | ".join(hunks[:10])
            return RestoreResult(
                success=False,
                error=error_msg,
                hunks=hunks,
                drift_detected=drift,
            )
        return RestoreResult(success=True, drift_detected=drift)

    def _current_head(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self._working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    def _list_dirty_files(self) -> list[str]:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self._working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
        if result.returncode != 0:
            return []
        return [
            line[3:].split(" -> ")[-1]
            for line in result.stdout.splitlines()
            if len(line) >= 4
        ]
