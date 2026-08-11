"""Pending-checkpoint durability for subagent-timeout handoff."""
from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from oneiric.core.logging import get_logger

PENDING_DIR = Path("~/.session-buddy/pending").expanduser()

# Cap on marker file size. A real marker is a few hundred bytes (working_dir
# path + reason string); 64 KiB is generous for legitimate use and prevents
# OOM via a hand-crafted huge marker.
MAX_MARKER_BYTES = 64 * 1024

_log = get_logger(__name__)


@dataclass
class PendingCheckpoint:
    working_dir: Path
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def marker_path(self) -> Path:
        safe = str(self.working_dir).replace("/", "_").replace(".", "_")
        return PENDING_DIR / f"{safe}.json"


def save_pending(p: PendingCheckpoint) -> Path:
    """Atomically persist a pending checkpoint marker.

    Writes to <marker_path>.tmp then ``os.replace`` for crash-safety: a
    crash mid-write leaves either the previous marker intact (no .tmp) or
    the new marker in place — never a half-written JSON file.
    """
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    marker_path = p.marker_path
    tmp_path = marker_path.with_name(marker_path.name + ".tmp")

    payload = json.dumps(
        {
            "working_dir": str(p.working_dir),
            "reason": p.reason,
            "created_at": p.created_at.isoformat(),
        },
        sort_keys=True,
    )

    # Write to .tmp first, then atomic rename. If os.replace raises, the
    # marker does not exist at its final path — callers can retry.
    tmp_path.write_text(payload, encoding="utf-8")
    try:
        os.replace(tmp_path, marker_path)
    except OSError:
        # Clean up the orphan .tmp on rename failure so we don't leak it.
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    return marker_path


def load_pending(path: Path) -> PendingCheckpoint | None:
    """Load a pending checkpoint marker from disk.

    Returns ``None`` if the marker doesn't exist. Raises
    :class:`json.JSONDecodeError` if malformed (caller should handle by
    logging + deleting the poison file). Raises :class:`ValueError` if
    the marker exceeds ``MAX_MARKER_BYTES`` to prevent OOM.
    """
    if not path.exists():
        return None
    size = path.stat().st_size
    if size > MAX_MARKER_BYTES:
        raise ValueError(
            f"Pending marker too large: {size} bytes (max {MAX_MARKER_BYTES})"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return PendingCheckpoint(
        working_dir=Path(data["working_dir"]),
        reason=data["reason"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def consume_pending(path: Path) -> None:
    path.unlink(missing_ok=True)


async def consume_pending_marker(
    marker: Path,
    *,
    build_orchestrator: Callable[[Path], Awaitable[object]],
) -> None:
    """Drain a pending-checkpoint marker by re-firing the orchestrator.

    Shared helper used by both the MCP server lifespan loop (Task 9) and
    ``SessionLifecycleManager.end_session`` (Task 8). Both call sites
    MUST behave identically: load the marker, run a fresh orchestrator at
    ``END_OF_TASK``, then consume the marker. Centralising here prevents
    the lifespan-vs-session-end drift that previously left pending
    markers drained without firing the orchestrator.

    Malformed-state semantics: if ``load_pending`` raises
    :class:`json.JSONDecodeError`, :class:`ValueError`, or
    :class:`OSError`, the marker is logged at warning level and deleted
    (best-effort). A poison marker that fails to parse must not loop
    forever on every tick.

    Args:
        marker: Path to the ``~/.session-buddy/pending/*.json`` marker.
        build_orchestrator: Async callable that takes the pending
            ``working_dir`` and returns a freshly-constructed
            ``CheckpointOrchestrator`` (callers wire the appropriate
            forward / policy for their call site).

    """
    try:
        pending = load_pending(marker)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        _log.warning(
            "pending_marker_unloadable",
            extra={
                "marker": str(marker),
                "type": type(exc).__name__,
            },
        )
        # Best-effort delete; swallow further errors so a delete failure
        # does not propagate and crash the draining loop.
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return

    if pending is None:
        # Marker was deleted between glob and load (race); nothing to do.
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return

    # Local import: avoid eager load cycles for deployments that never
    # drain pending markers (lite mode with no subagents).
    from session_buddy.checkpoint import CheckpointPhase

    orch = await build_orchestrator(pending.working_dir)
    await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    consume_pending(marker)