from __future__ import annotations

import time
from pathlib import Path

import pytest

from session_buddy.checkpoint.cleanup import SnapshotCleanupTask


@pytest.mark.unit
async def test_cleanup_removes_files_older_than_ttl(tmp_path: Path) -> None:
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    old = snap_dir / "snap-old.patch"
    new = snap_dir / "snap-new.patch"
    old.write_text("old")
    new.write_text("new")
    # Make `old` 8 days old (TTL is 7 days)
    old_mtime = time.time() - (8 * 86400)
    import os
    os.utime(old, (old_mtime, old_mtime))

    removed = await SnapshotCleanupTask(snap_dir, ttl_seconds=7 * 86400).cleanup_once()
    assert removed == 1
    assert not old.exists()
    assert new.exists()


@pytest.mark.unit
async def test_cleanup_zero_ttl_keeps_everything(tmp_path: Path) -> None:
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    f = snap_dir / "snap.patch"
    f.write_text("x")

    removed = await SnapshotCleanupTask(snap_dir, ttl_seconds=0).cleanup_once()
    assert removed == 0
    assert f.exists()


@pytest.mark.unit
async def test_cleanup_handles_missing_directory(tmp_path: Path) -> None:
    # No exception if dir doesn't exist
    removed = await SnapshotCleanupTask(tmp_path / "nope", ttl_seconds=86400).cleanup_once()
    assert removed == 0
