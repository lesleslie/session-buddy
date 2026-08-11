"""Auto-checkpoint orchestration: policy + snapshot + subagent detector."""
from __future__ import annotations

from session_buddy.checkpoint.cleanup import SnapshotCleanupTask
from session_buddy.checkpoint.metrics import CheckpointMetrics
from session_buddy.checkpoint.orchestrator import (
    CheckpointOrchestrator,
    CheckpointResult,
)
from session_buddy.checkpoint.pending import (
    PendingCheckpoint,
    consume_pending,
    consume_pending_marker,
    load_pending,
    save_pending,
)
from session_buddy.checkpoint.policy import (
    CheckpointPhase,
    CheckpointPolicy,
    DirtyFilesSignal,
    MidpointCriteria,
    PolicyDecision,
    TimeElapsedSignal,
    ValueAddSignal,
    WorkingTreeInspector,
)
from session_buddy.checkpoint.snapshot import (
    RestoreResult,
    Snapshot,
    SnapshotMechanism,
)
from session_buddy.checkpoint.subagent_detector import (
    LockfileSignalSource,
    SignalSource,
    SubagentDetector,
)

__all__ = [
    "CheckpointOrchestrator",
    "CheckpointPhase",
    "CheckpointPolicy",
    "CheckpointResult",
    "CheckpointMetrics",
    "DirtyFilesSignal",
    "LockfileSignalSource",
    "MidpointCriteria",
    "PendingCheckpoint",
    "PolicyDecision",
    "RestoreResult",
    "SignalSource",
    "Snapshot",
    "SnapshotCleanupTask",
    "SnapshotMechanism",
    "SubagentDetector",
    "TimeElapsedSignal",
    "ValueAddSignal",
    "WorkingTreeInspector",
    "consume_pending",
    "consume_pending_marker",
    "load_pending",
    "save_pending",
]
