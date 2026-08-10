from __future__ import annotations

import pytest


@pytest.mark.unit
def test_checkpoint_module_exports_all_classes() -> None:
    from session_buddy.checkpoint import (  # noqa: F401
        CheckpointOrchestrator,
        CheckpointPhase,
        CheckpointPolicy,
        CheckpointResult,
        DirtyFilesSignal,
        LockfileSignalSource,
        MidpointCriteria,
        PendingCheckpoint,
        PolicyDecision,
        RestoreResult,
        SignalSource,
        Snapshot,
        SnapshotCleanupTask,
        SnapshotMechanism,
        SubagentDetector,
        TimeElapsedSignal,
        WorkingTreeInspector,
        load_pending,
        save_pending,
        consume_pending,
    )
    assert CheckpointOrchestrator is not None
