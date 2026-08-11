"""Detect whether a subagent is currently working in the same project tree.

Signal source is pluggable: lockfile (default), env var, or MCP probe.
Per spec invariant: failures fail OPEN to "active" (assume subagent active,
defer) — safer to defer unnecessarily than to risk clobbering.

Lockfile path is per-working-tree: <working_dir>/.session-buddy/subagent.lock.
Prevents cross-project false deferral in multi-session deployments.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from oneiric.core.logging import get_logger

from session_buddy.checkpoint.scrubbing import safe_transient_info

_log = get_logger(__name__)


class SignalSource(Protocol):
    def read(self) -> bool: ...
    def write(self, active: bool) -> None: ...


class LockfileSignalSource:
    """Lockfile-backed SignalSource. Lockfile presence == subagent active.

    The .write() method has no in-codebase caller at present; the
    producer (creating <working_dir>/.session-buddy/subagent.lock when a
    subagent starts) is owned by the subagent-runtime team and tracked
    externally. Until the producer lands, the re-check branch
    (`subagent_active_during_capture`) is effectively a no-op; the
    primary `wait_until_idle` gate still protects end-of-task commits
    because it uses the same lockfile with fail-open → True semantics.

    See C-1 in docs/superpowers/plans/2026-08-10-auto-checkpoint-implementation-summary.md
    for the follow-up plan.
    """

    def __init__(self, lockfile_path: Path) -> None:
        self._path = lockfile_path

    def read(self) -> bool:
        try:
            return self._path.exists()
        except OSError as exc:
            _log.warning("subagent_signal_read_failed", extra=safe_transient_info(exc))
            return True  # fail open per spec

    def write(self, active: bool) -> None:
        try:
            if active:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.touch()
            else:
                self._path.unlink(missing_ok=True)
        except OSError as exc:
            _log.warning("subagent_signal_write_failed", extra=safe_transient_info(exc))


class SubagentDetector:
    def __init__(self, working_dir: Path, signal_source: SignalSource) -> None:
        self._working_dir = working_dir
        self._signal = signal_source

    def is_active(self) -> bool:
        try:
            return self._signal.read()
        except Exception as exc:  # noqa: BLE001 — fail open per spec
            _log.warning(
                "subagent_detector_is_active_failed",
                extra={**safe_transient_info(exc), "working_dir": str(self._working_dir)},
            )
            return True

    async def wait_until_idle(self, timeout: float = 60.0) -> bool:
        """Block until subagent is idle or timeout. Returns True if idle."""
        try:
            await asyncio.wait_for(self._poll_until_idle(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            _log.warning(
                "subagent_detector_wait_timeout",
                extra={"timeout_s": timeout, "working_dir": str(self._working_dir)},
            )
            return False

    async def _poll_until_idle(self) -> None:
        while self.is_active():
            await asyncio.sleep(0.1)
