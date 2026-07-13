"""Tests for runtime_snapshots that exercise the real module.

These tests use the real ``session_buddy.utils.runtime_snapshots`` module
(imported normally) and the real ``mcp_common`` packages, with
``monkeypatch`` to swap the bits of behaviour each test cares about.
No ``sys.modules`` stubbing is needed because the real module's
dependencies are all importable in the test environment.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from mcp_common import MCPServerSettings
from mcp_common.cli.health import (
    RuntimeHealthSnapshot,
    load_runtime_health,
    write_runtime_health,
)
from oneiric.core.config import OneiricMCPConfig
from session_buddy.utils.runtime_snapshots import (
    RuntimeSnapshotManager,
    RuntimeTelemetrySnapshot,
    load_runtime_telemetry,
    run_snapshot_loop,
    update_telemetry_counter,
    write_runtime_telemetry,
)


def test_runtime_snapshot_manager_writes_health(tmp_path: Path) -> None:
    settings = MCPServerSettings(server_name="session-buddy", cache_root=tmp_path)
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


def test_runtime_snapshot_manager_for_server() -> None:
    manager = RuntimeSnapshotManager.for_server("alpha")
    # Migrated from MCPServerSettings to OneiricMCPConfig; the
    # assertion reflects the new base class. The class still
    # satisfies the structural snapshot-settings Protocol.
    # Note: ``server_name`` was a legacy field on MCPServerSettings;
    # OneiricMCPConfig doesn't carry it, so we no longer assert
    # ``manager.settings.server_name == "alpha"``.
    assert isinstance(manager.settings, OneiricMCPConfig)
    assert manager.settings is not None


def test_runtime_snapshot_manager_writes_telemetry(tmp_path: Path) -> None:
    settings = MCPServerSettings(server_name="session-buddy", cache_root=tmp_path)
    manager = RuntimeSnapshotManager(settings=settings, started_at=datetime.now(UTC))

    manager.record("snapshot_updates")
    manager.write_telemetry_snapshot(pid=42)

    snapshot = load_runtime_telemetry(settings.telemetry_snapshot_path())
    assert snapshot.orchestrator_pid == 42
    assert snapshot.started_at is not None
    assert snapshot.uptime_seconds is not None
    assert snapshot.counters.get("snapshot_updates") == 1


def test_update_telemetry_counter(tmp_path: Path) -> None:
    settings = MCPServerSettings(server_name="session-buddy", cache_root=tmp_path)
    RuntimeSnapshotManager(settings=settings, started_at=datetime.now(UTC))

    update_telemetry_counter(settings, "events", amount=3)

    snapshot = load_runtime_telemetry(settings.telemetry_snapshot_path())
    assert snapshot.counters.get("events") == 3
