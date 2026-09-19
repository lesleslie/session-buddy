"""Detect whether a subagent is currently working in the same project tree.

Signal source is pluggable: lockfile (default), env var, or MCP probe.
Per spec invariant: failures fail OPEN to "active" (assume subagent active,
defer) — safer to defer unnecessarily than to risk clobbering.

Lockfile path is per-working-tree: <working_dir>/.session-buddy/subagent.lock.
Prevents cross-project false deferral in multi-session deployments.

Producer surface: ``SubagentDetector.write()`` creates/clears the lockfile
with a JSON payload (pid, started_at_ms, node_id, parent_agent_id) via an
atomic write-temp+rename. Three runtime paths: Python API, CLI
(``session_buddy checkpoint subagent-marker``), and the MCP tool
``subagent_marker``.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from oneiric.core.logging import get_logger

from session_buddy.checkpoint.scrubbing import safe_transient_info

_log = get_logger(__name__)


# Env vars consulted by ``SubagentDetector.write()`` when no explicit
# metadata is supplied. The CLI / MCP tool never passes metadata so these
# default-fill the payload.
_NODE_ID_ENV = "SESSION_BUDDY_NODE_ID"
_PARENT_AGENT_ID_ENV = "SESSION_BUDDY_PARENT_AGENT_ID"


class SignalSource(Protocol):
    def read(self) -> bool: ...
    def write(self, active: bool) -> None: ...


@dataclass(frozen=True)
class SubagentMetadata:
    """Payload written to ``<working_dir>/.session-buddy/subagent.lock``.

    Fields are populated by ``SubagentDetector.write()`` from ``os.getpid()``,
    ``time.time()``, and the ``SESSION_BUDDY_NODE_ID`` /
    ``SESSION_BUDDY_PARENT_AGENT_ID`` env vars when not passed explicitly.
    """

    pid: int
    started_at_ms: int
    node_id: str
    parent_agent_id: str


class LockfileSignalSource:
    """Lockfile-backed SignalSource. Lockfile presence == subagent active.

    When ``write(active=True, payload=...)`` is called with a payload,
    the lockfile is written atomically (temp + ``os.replace``) so
    concurrent readers never see a partial file. When ``payload`` is
    omitted, the legacy fast-path (``path.touch()``) is used — preserves
    the existing public contract and the tests in
    ``tests/unit/core/checkpoint/test_subagent_detector.py``.
    """

    def __init__(self, lockfile_path: Path) -> None:
        self._path = lockfile_path

    def read(self) -> bool:
        try:
            return self._path.exists()
        except OSError as exc:
            _log.warning("subagent_signal_read_failed", extra=safe_transient_info(exc))
            return True  # fail open per spec

    def write(self, active: bool, payload: dict[str, Any] | None = None) -> None:
        try:
            if active:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                if payload is None:
                    self._path.touch()
                else:
                    self._atomic_write_json(payload)
            else:
                self._path.unlink(missing_ok=True)
        except OSError as exc:
            _log.warning("subagent_signal_write_failed", extra=safe_transient_info(exc))

    def _atomic_write_json(self, payload: dict[str, Any]) -> None:
        """Atomically write JSON payload to the lockfile via mkstemp + replace.

        Raises ``OSError`` on failure; the outer ``write`` handler swallows
        it per the fail-open contract.
        """
        fd, tmp_str = tempfile.mkstemp(
            prefix=f"{self._path.name}.",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(payload, fh)
            os.replace(tmp_str, self._path)
        except Exception:
            # Best-effort cleanup of the orphan tmp file. Swallow errors
            # here — the outer write already handles the failure mode.
            try:
                Path(tmp_str).unlink()
            except OSError:
                pass
            raise


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
                extra=safe_transient_info(exc)
                | {"working_dir": str(self._working_dir)},
            )
            return True

    def write(
        self,
        active: bool,
        metadata: SubagentMetadata | None = None,
    ) -> None:
        """Producer side: create or clear the lockfile.

        When ``active=True`` and no ``metadata`` is supplied, a
        ``SubagentMetadata`` is auto-constructed from ``os.getpid()``,
        ``time.time()``, the ``SESSION_BUDDY_NODE_ID`` /
        ``SESSION_BUDDY_PARENT_AGENT_ID`` env vars (falling back to
        ``socket.gethostname()`` for node_id). When ``active=False``,
        the lockfile is unlinked regardless of metadata.

        Atomicity is delegated to ``LockfileSignalSource._atomic_write_json``;
        a write failure fails OPEN at the OS layer (logged, not raised) so
        the consumer side's ``is_active()`` continues to work.
        """
        if active:
            meta = metadata or self._default_metadata()
            payload = {
                "pid": meta.pid,
                "started_at_ms": meta.started_at_ms,
                "node_id": meta.node_id,
                "parent_agent_id": meta.parent_agent_id,
            }
            self._signal.write(active=True, payload=payload)
        else:
            self._signal.write(active=False)

    def _default_metadata(self) -> SubagentMetadata:
        node_id = os.environ.get(_NODE_ID_ENV) or socket.gethostname()
        parent_id = os.environ.get(_PARENT_AGENT_ID_ENV, "")
        return SubagentMetadata(
            pid=os.getpid(),
            started_at_ms=int(time.time() * 1000),
            node_id=node_id,
            parent_agent_id=parent_id,
        )

    async def wait_until_idle(self, timeout: float = 60.0) -> bool:
        """Block until subagent is idle or timeout. Returns True if idle."""
        try:
            await asyncio.wait_for(self._poll_until_idle(), timeout=timeout)
            return True
        except TimeoutError:
            _log.warning(
                "subagent_detector_wait_timeout",
                extra={"timeout_s": timeout, "working_dir": str(self._working_dir)},
            )
            return False

    async def _poll_until_idle(self) -> None:
        while self.is_active():
            await asyncio.sleep(0.1)


class SubagentLifecycleHook(Protocol):
    """Protocol for runtime hooks that fire on subagent start/end.

    Implementations are called by whichever subagent runtime is in use
    (Claude Code Task tool, Mahavishnu ``PoolManager.spawn_pool``, etc.).
    The default implementation (``DefaultSubagentLifecycleHook``) wraps a
    ``SubagentDetector`` and writes/removes the lockfile.
    """

    def on_subagent_start(
        self, working_dir: Path, metadata: SubagentMetadata
    ) -> None: ...

    def on_subagent_end(self, working_dir: Path) -> None: ...


class DefaultSubagentLifecycleHook:
    """Concrete ``SubagentLifecycleHook``: writes/removes the lockfile.

    ``detector_factory`` is injectable for testing; default builds a
    ``SubagentDetector`` over the standard
    ``<working_dir>/.session-buddy/subagent.lock`` path.
    """

    def __init__(
        self,
        detector_factory: Callable[[Path], SubagentDetector] | None = None,
    ) -> None:
        self._factory = detector_factory or self._default_factory

    @staticmethod
    def _default_factory(working_dir: Path) -> SubagentDetector:
        lock = working_dir / ".session-buddy" / "subagent.lock"
        return SubagentDetector(working_dir, LockfileSignalSource(lock))

    def on_subagent_start(
        self, working_dir: Path, metadata: SubagentMetadata
    ) -> None:
        self._factory(working_dir).write(active=True, metadata=metadata)

    def on_subagent_end(self, working_dir: Path) -> None:
        self._factory(working_dir).write(active=False)
