"""Pending-checkpoint durability for subagent-timeout handoff."""
from __future__ import annotations

import json
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