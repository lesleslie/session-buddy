"""Pending-checkpoint durability for subagent-timeout handoff."""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

PENDING_DIR = Path("~/.session-buddy/pending").expanduser()


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
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    p.marker_path.write_text(json.dumps({
        "working_dir": str(p.working_dir),
        "reason": p.reason,
        "created_at": p.created_at.isoformat(),
    }))
    return p.marker_path


def load_pending(path: Path) -> PendingCheckpoint | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
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

    Args:
        marker: Path to the ``~/.session-buddy/pending/*.json`` marker.
        build_orchestrator: Async callable that takes the pending
            ``working_dir`` and returns a freshly-constructed
            ``CheckpointOrchestrator`` (callers wire the appropriate
            forward / policy for their call site).

    """
    pending = load_pending(marker)
    if pending is None:
        marker.unlink(missing_ok=True)
        return
    # Local import: avoid eager load cycles for deployments that never
    # drain pending markers (lite mode with no subagents).
    from session_buddy.checkpoint import CheckpointPhase

    orch = await build_orchestrator(pending.working_dir)
    await orch.run_checkpoint(phase=CheckpointPhase.END_OF_TASK)
    consume_pending(marker)
