"""Background TTL cleanup for /tmp/snap-*.patch files.

Per spec line 384: "TTL-based: 7-day default TTL. Background cleanup task
removes expired snapshots."
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from oneiric.core.logging import get_logger

from session_buddy.checkpoint.scrubbing import safe_transient_info

_log = get_logger(__name__)


class SnapshotCleanupTask:
    def __init__(self, snapshot_dir: Path, ttl_seconds: int = 7 * 86400) -> None:
        self._snapshot_dir = snapshot_dir
        self._ttl_seconds = ttl_seconds

    async def cleanup_once(self) -> int:
        if not self._snapshot_dir.exists():
            return 0
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._cleanup_sync)

    def _cleanup_sync(self) -> int:
        cutoff = time.time() - self._ttl_seconds
        removed = 0
        for path in self._snapshot_dir.glob("snap-*.patch"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except (FileNotFoundError, OSError) as exc:
                _log.warning("snapshot_cleanup_skip", extra={"path": str(path), **safe_transient_info(exc)})
        if removed:
            _log.info("snapshot_cleanup_completed", extra={"removed": removed})
        return removed
