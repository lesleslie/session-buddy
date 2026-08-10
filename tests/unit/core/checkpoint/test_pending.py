from __future__ import annotations

from pathlib import Path

import pytest

from session_buddy.checkpoint.pending import (
    PendingCheckpoint,
    consume_pending,
    load_pending,
    save_pending,
)


@pytest.mark.unit
def test_save_then_load_round_trip(tmp_path: Path) -> None:
    pending = PendingCheckpoint(
        working_dir=tmp_path / "proj",
        reason="subagent_idle_timeout",
    )
    marker = save_pending(pending)
    assert marker.exists()

    loaded = load_pending(marker)
    assert loaded is not None
    assert loaded.reason == "subagent_idle_timeout"


@pytest.mark.unit
def test_load_missing_returns_none(tmp_path: Path) -> None:
    assert load_pending(tmp_path / "nonexistent.json") is None


@pytest.mark.unit
def test_consume_pending_removes_file(tmp_path: Path) -> None:
    pending = PendingCheckpoint(working_dir=tmp_path, reason="x")
    marker = save_pending(pending)
    consume_pending(marker)
    assert not marker.exists()


@pytest.mark.unit
def test_metrics_inc_failure_counts_by_reason() -> None:
    from session_buddy.checkpoint.metrics import CheckpointMetrics

    m = CheckpointMetrics()
    m.inc_failure("subagent_idle_timeout")
    m.inc_failure("subagent_idle_timeout")
    m.inc_failure("forward_transient_retry_exhausted")
    assert m.failures["subagent_idle_timeout"] == 2
    assert m.failures["forward_transient_retry_exhausted"] == 1