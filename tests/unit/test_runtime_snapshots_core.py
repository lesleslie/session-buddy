from __future__ import annotations

import asyncio
import json
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


def test_write_runtime_telemetry_cleans_up_temp_file_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "telemetry.json"
    snapshot = RuntimeTelemetrySnapshot(orchestrator_pid=7)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text("stale")

    write_text_mock = Mock(side_effect=OSError("disk full"))
    unlink_mock = Mock(wraps=temp_path.unlink)
    monkeypatch.setattr(Path, "write_text", write_text_mock)
    monkeypatch.setattr(Path, "unlink", unlink_mock)

    with pytest.raises(OSError, match="disk full"):
        write_runtime_telemetry(path, snapshot)

    assert unlink_mock.called
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
