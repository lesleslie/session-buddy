from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mcp_common import MCPServerSettings
from mcp_common.cli.health import load_runtime_health
from session_buddy.utils.runtime_snapshots import (
    RuntimeSnapshotManager,
    load_runtime_telemetry,
    update_telemetry_counter,
)

if TYPE_CHECKING:
    from pathlib import Path


def _settings_for_cache(cache_root: Path) -> MCPServerSettings:
    return MCPServerSettings(server_name="session-buddy", cache_root=cache_root)


def test_runtime_snapshot_manager_writes_health(tmp_path: Path) -> None:
    settings = _settings_for_cache(tmp_path)
    manager = RuntimeSnapshotManager(settings=settings, started_at=datetime.now(UTC))

    manager.write_health_snapshot(
        pid=12345,
        health_state={"status": "ok"},
        watchers_running=True,
    )

    snapshot = load_runtime_health(settings.health_snapshot_path())
    assert snapshot.orchestrator_pid == 12345
    assert snapshot.watchers_running is True
    assert snapshot.activity_state["health"]["status"] == "ok"


def test_runtime_snapshot_manager_writes_telemetry(tmp_path: Path) -> None:
    settings = _settings_for_cache(tmp_path)
    manager = RuntimeSnapshotManager(settings=settings, started_at=datetime.now(UTC))

    manager.record("snapshot_updates")
    manager.write_telemetry_snapshot(pid=42)

    snapshot = load_runtime_telemetry(settings.telemetry_snapshot_path())
    assert snapshot.orchestrator_pid == 42
    assert snapshot.started_at is not None
    assert snapshot.uptime_seconds is not None
    assert snapshot.counters.get("snapshot_updates") == 1


def test_update_telemetry_counter(tmp_path: Path) -> None:
    settings = _settings_for_cache(tmp_path)

    update_telemetry_counter(settings, name="health_probes", pid=101)
    snapshot = load_runtime_telemetry(settings.telemetry_snapshot_path())

    assert snapshot.orchestrator_pid == 101
    assert snapshot.counters.get("health_probes") == 1
