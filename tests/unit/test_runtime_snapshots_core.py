from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from session_buddy.utils.runtime_snapshots import (
    RuntimeSnapshotManager,
    RuntimeTelemetrySnapshot,
    load_runtime_telemetry,
    run_snapshot_loop,
    update_telemetry_counter,
    write_runtime_telemetry,
)


def test_load_runtime_telemetry_handles_missing_invalid_and_partial_files(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    assert load_runtime_telemetry(missing) == RuntimeTelemetrySnapshot()

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not json}")
    assert load_runtime_telemetry(invalid) == RuntimeTelemetrySnapshot()

    list_file = tmp_path / "list.json"
    list_file.write_text(json.dumps([1, 2, 3]))
    assert load_runtime_telemetry(list_file) == RuntimeTelemetrySnapshot()

    partial = tmp_path / "partial.json"
    partial.write_text(
        json.dumps(
            {
                "orchestrator_pid": 42,
                "started_at": "2026-05-17T12:00:00+00:00",
                "updated_at": "2026-05-17T12:01:00+00:00",
                "uptime_seconds": 12.5,
                "counters": ["not", "a", "dict"],
            }
        )
    )

    snapshot = load_runtime_telemetry(partial)
    assert snapshot.orchestrator_pid == 42
    assert snapshot.started_at == "2026-05-17T12:00:00+00:00"
    assert snapshot.counters == {}


def test_write_runtime_telemetry_updates_timestamp_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.json"
    snapshot = RuntimeTelemetrySnapshot(
        orchestrator_pid=99,
        started_at="2026-05-17T12:00:00+00:00",
        counters={"updates": 2},
    )

    write_runtime_telemetry(path, snapshot)

    persisted = json.loads(path.read_text())
    assert persisted["orchestrator_pid"] == 99
    assert persisted["counters"] == {"updates": 2}
    assert snapshot.updated_at is not None
    assert persisted["updated_at"] == snapshot.updated_at


def test_write_runtime_telemetry_does_not_reuse_a_stale_temp_file(
    tmp_path: Path,
) -> None:
    """A leftover temp file must never be reused for the new write.

    Reusing a fixed-name temp file means the snapshot content lands in a
    file whose mode was decided by an earlier (possibly crashed) write,
    and a symlink planted at that path is followed -- so the write can
    clobber an arbitrary file. The write must use a fresh, uniquely named
    temp file instead.
    """
    path = tmp_path / "telemetry.json"
    stale = path.with_suffix(".tmp")
    stale.write_text("stale payload")
    stale.chmod(0o644)

    write_runtime_telemetry(path, RuntimeTelemetrySnapshot(orchestrator_pid=7))

    assert stale.exists(), "the write consumed the pre-existing temp file"
    assert stale.read_text() == "stale payload"
    assert json.loads(path.read_text())["orchestrator_pid"] == 7


def test_write_runtime_telemetry_does_not_follow_a_symlinked_temp_file(
    tmp_path: Path,
) -> None:
    """A symlink planted at the temp path must not be written through."""
    victim = tmp_path / "victim.txt"
    victim.write_text("do not touch")
    path = tmp_path / "telemetry.json"
    path.with_suffix(".tmp").symlink_to(victim)

    write_runtime_telemetry(path, RuntimeTelemetrySnapshot(orchestrator_pid=7))

    assert victim.read_text() == "do not touch"
    assert json.loads(path.read_text())["orchestrator_pid"] == 7


def test_overlapping_writers_do_not_corrupt_the_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two writers overlapping on one path must neither crash nor mix.

    The server's snapshot loop and the CLI health probe write the same
    file from separate processes. A shared fixed-name temp file lets the
    second writer rename the temp out from under the first, which then
    fails on rename -- and can publish the other writer's bytes.
    """
    path = tmp_path / "telemetry.json"
    real_replace = os.replace
    state = {"nested": False}

    def replace_with_nested_writer(src: object, dst: object) -> None:
        if not state["nested"]:
            state["nested"] = True
            # A second writer publishes while the first is mid-flight.
            write_runtime_telemetry(
                path,
                RuntimeTelemetrySnapshot(orchestrator_pid=99, counters={"b": 2}),
            )
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace_with_nested_writer)

    try:
        write_runtime_telemetry(
            path,
            RuntimeTelemetrySnapshot(orchestrator_pid=7, counters={"a": 1}),
        )
    except FileNotFoundError as exc:
        pytest.fail(f"overlapping writers raced on a shared temp file: {exc}")

    persisted = json.loads(path.read_text())
    # The published file must be exactly one writer's snapshot -- never a
    # mix of the two and never a truncated blend.
    assert persisted["orchestrator_pid"] in {7, 99}
    assert persisted["counters"] in ({"a": 1}, {"b": 2})


def test_write_runtime_telemetry_cleans_up_temp_file_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed publish must leave no temp file behind."""
    path = tmp_path / "telemetry.json"
    snapshot = RuntimeTelemetrySnapshot(orchestrator_pid=7)

    def failing_replace(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        write_runtime_telemetry(path, snapshot)

    assert [p for p in tmp_path.iterdir() if p.is_file()] == []
    assert snapshot.updated_at is not None


def test_update_telemetry_counter_initializes_invalid_start_time(
    tmp_path: Path,
) -> None:
    settings = SimpleNamespace(
        telemetry_snapshot_path=lambda: tmp_path / "telemetry.json",
    )
    (tmp_path / "telemetry.json").write_text(
        json.dumps(
            {
                "orchestrator_pid": 7,
                "started_at": "not-a-timestamp",
                "counters": {"updates": 3},
            }
        )
    )

    snapshot = update_telemetry_counter(settings, "updates", amount=4, pid=11)

    assert snapshot.orchestrator_pid == 11
    assert snapshot.counters["updates"] == 7
    assert snapshot.started_at is not None
    assert snapshot.uptime_seconds is not None


def test_runtime_snapshot_manager_for_server_and_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Mock()
    settings.health_snapshot_path.return_value = Path("/tmp/health.json")
    settings.telemetry_snapshot_path.return_value = Path("/tmp/telemetry.json")
    load_mock = Mock(return_value=RuntimeTelemetrySnapshot())
    write_mock = Mock()
    health_write_mock = Mock(return_value=Mock())

    monkeypatch.setattr(
        "session_buddy.utils.runtime_snapshots.MCPServerSettings.load",
        Mock(return_value=settings),
    )
    monkeypatch.setattr(
        "session_buddy.utils.runtime_snapshots.load_runtime_health",
        health_write_mock,
    )
    monkeypatch.setattr(
        "session_buddy.utils.runtime_snapshots.write_runtime_health",
        Mock(),
    )
    monkeypatch.setattr(
        "session_buddy.utils.runtime_snapshots.write_runtime_telemetry",
        write_mock,
    )
    monkeypatch.setattr(
        "session_buddy.utils.runtime_snapshots.load_runtime_telemetry",
        load_mock,
    )

    manager = RuntimeSnapshotManager.for_server("session-buddy")
    manager.record("snapshot_updates", amount=2)
    telemetry = manager.write_telemetry_snapshot(pid=321)
    health = manager.write_health_snapshot(
        pid=123,
        health_state={"status": "ok"},
        watchers_running=False,
    )

    assert manager.settings is settings
    assert manager.counters["snapshot_updates"] == 2
    assert telemetry.orchestrator_pid == 321
    assert write_mock.called
    assert health.orchestrator_pid == 123
    assert health.watchers_running is False


@pytest.mark.asyncio
async def test_run_snapshot_loop_records_once_and_can_be_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = Mock()
    manager.record = Mock()
    manager.write_health_snapshot = Mock()
    manager.write_telemetry_snapshot = Mock()

    async def fake_sleep(interval_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "session_buddy.utils.runtime_snapshots._sleep",
        fake_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await run_snapshot_loop(manager, pid=555, interval_seconds=0.01)

    manager.record.assert_called_once_with("snapshot_updates")
    manager.write_health_snapshot.assert_called_once_with(pid=555)
    manager.write_telemetry_snapshot.assert_called_once_with(pid=555)
