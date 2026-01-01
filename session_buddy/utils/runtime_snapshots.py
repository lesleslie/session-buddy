from __future__ import annotations

import json
import typing as t
from dataclasses import dataclass, field
from datetime import UTC, datetime

from mcp_common import MCPServerSettings
from mcp_common.cli.health import (
    RuntimeHealthSnapshot,
    load_runtime_health,
    write_runtime_health,
)

if t.TYPE_CHECKING:
    from pathlib import Path


@dataclass
class RuntimeTelemetrySnapshot:
    orchestrator_pid: int | None = None
    started_at: str | None = None
    updated_at: str | None = None
    uptime_seconds: float | None = None
    counters: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, t.Any]:
        return {
            "orchestrator_pid": self.orchestrator_pid,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "uptime_seconds": self.uptime_seconds,
            "counters": self.counters.copy(),
        }


@dataclass
class RuntimeSnapshotManager:
    settings: MCPServerSettings
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    counters: dict[str, int] = field(default_factory=dict)

    @classmethod
    def for_server(cls, server_name: str) -> RuntimeSnapshotManager:
        return cls(settings=MCPServerSettings.load(server_name))

    def record(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount

    def write_health_snapshot(
        self,
        pid: int | None,
        health_state: dict[str, t.Any] | None = None,
        watchers_running: bool = True,
    ) -> RuntimeHealthSnapshot:
        snapshot = load_runtime_health(self.settings.health_snapshot_path())
        snapshot.orchestrator_pid = pid
        snapshot.watchers_running = watchers_running
        if health_state is not None:
            snapshot.activity_state = {"health": health_state}
        write_runtime_health(self.settings.health_snapshot_path(), snapshot)
        return snapshot

    def write_telemetry_snapshot(self, pid: int | None) -> RuntimeTelemetrySnapshot:
        uptime_seconds = (datetime.now(UTC) - self.started_at).total_seconds()
        snapshot = RuntimeTelemetrySnapshot(
            orchestrator_pid=pid,
            started_at=self.started_at.isoformat(),
            uptime_seconds=uptime_seconds,
            counters=self.counters.copy(),
        )
        write_runtime_telemetry(self.settings.telemetry_snapshot_path(), snapshot)
        return snapshot


def load_runtime_telemetry(path: Path) -> RuntimeTelemetrySnapshot:
    if not path.exists():
        return RuntimeTelemetrySnapshot()

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return RuntimeTelemetrySnapshot()

    if not isinstance(data, dict):
        return RuntimeTelemetrySnapshot()

    snapshot = RuntimeTelemetrySnapshot()
    snapshot.orchestrator_pid = data.get("orchestrator_pid")
    snapshot.started_at = data.get("started_at")
    snapshot.updated_at = data.get("updated_at")
    snapshot.uptime_seconds = data.get("uptime_seconds")
    counters = data.get("counters")
    snapshot.counters = counters if isinstance(counters, dict) else {}
    return snapshot


def write_runtime_telemetry(path: Path, snapshot: RuntimeTelemetrySnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    snapshot.updated_at = datetime.now(UTC).isoformat()

    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(snapshot.as_dict(), indent=2))
        tmp.chmod(0o600)
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def update_telemetry_counter(
    settings: MCPServerSettings,
    name: str,
    amount: int = 1,
    pid: int | None = None,
) -> RuntimeTelemetrySnapshot:
    path = settings.telemetry_snapshot_path()
    snapshot = load_runtime_telemetry(path)
    now = datetime.now(UTC)

    started_at = _parse_iso_datetime(snapshot.started_at)
    if started_at is None:
        started_at = now
        snapshot.started_at = started_at.isoformat()

    snapshot.orchestrator_pid = pid
    snapshot.uptime_seconds = (now - started_at).total_seconds()
    snapshot.counters[name] = snapshot.counters.get(name, 0) + amount
    write_runtime_telemetry(path, snapshot)
    return snapshot


async def run_snapshot_loop(
    manager: RuntimeSnapshotManager,
    pid: int | None,
    interval_seconds: float,
) -> None:
    while True:
        manager.record("snapshot_updates")
        manager.write_health_snapshot(pid=pid)
        manager.write_telemetry_snapshot(pid=pid)
        await _sleep(interval_seconds)


async def _sleep(interval_seconds: float) -> None:
    import asyncio

    await asyncio.sleep(interval_seconds)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "RuntimeSnapshotManager",
    "RuntimeTelemetrySnapshot",
    "load_runtime_telemetry",
    "run_snapshot_loop",
    "update_telemetry_counter",
    "write_runtime_telemetry",
]
