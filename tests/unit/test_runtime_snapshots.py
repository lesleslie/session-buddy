from __future__ import annotations

import importlib.util
import json
import sys
import types
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class _RuntimeHealthSnapshot:
    orchestrator_pid: int | None = None
    watchers_running: bool = True
    activity_state: dict[str, object] = field(default_factory=dict)


_HEALTH_STORE: dict[str, _RuntimeHealthSnapshot] = {}


class _MCPServerSettings:
    def __init__(self, server_name: str, cache_root: Path) -> None:
        self.server_name = server_name
        self.cache_root = cache_root

    @classmethod
    def load(cls, server_name: str) -> _MCPServerSettings:
        return cls(server_name=server_name, cache_root=Path.cwd())

    def health_snapshot_path(self) -> Path:
        return self.cache_root / f"{self.server_name}.health.json"

    def telemetry_snapshot_path(self) -> Path:
        return self.cache_root / f"{self.server_name}.telemetry.json"


def _load_runtime_health(path: Path) -> _RuntimeHealthSnapshot:
    return _HEALTH_STORE.get(str(path), _RuntimeHealthSnapshot())


def _write_runtime_health(path: Path, snapshot: _RuntimeHealthSnapshot) -> None:
    _HEALTH_STORE[str(path)] = snapshot


_MCP_COMMON = types.ModuleType("mcp_common")
_MCP_COMMON.MCPServerSettings = _MCPServerSettings
_MCP_CLI = types.ModuleType("mcp_common.cli")
_MCP_CLI_HEALTH = types.ModuleType("mcp_common.cli.health")
_MCP_CLI_HEALTH.RuntimeHealthSnapshot = _RuntimeHealthSnapshot
_MCP_CLI_HEALTH.load_runtime_health = _load_runtime_health
_MCP_CLI_HEALTH.write_runtime_health = _write_runtime_health
sys.modules.setdefault("mcp_common", _MCP_COMMON)
sys.modules.setdefault("mcp_common.cli", _MCP_CLI)
sys.modules.setdefault("mcp_common.cli.health", _MCP_CLI_HEALTH)

_UTILS_PACKAGE = types.ModuleType("session_buddy.utils")
_UTILS_PACKAGE.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("session_buddy.utils", _UTILS_PACKAGE)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "runtime_snapshots.py"
_SPEC = importlib.util.spec_from_file_location(
    "session_buddy.utils.runtime_snapshots",
    _MODULE_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.runtime_snapshots", _MODULE)
_SPEC.loader.exec_module(_MODULE)

RuntimeSnapshotManager = _MODULE.RuntimeSnapshotManager
RuntimeTelemetrySnapshot = _MODULE.RuntimeTelemetrySnapshot
load_runtime_telemetry = _MODULE.load_runtime_telemetry
update_telemetry_counter = _MODULE.update_telemetry_counter


def _settings_for_cache(cache_root: Path) -> _MCPServerSettings:
    return _MCPServerSettings(server_name="session-buddy", cache_root=cache_root)


def test_runtime_snapshot_manager_writes_health(tmp_path: Path) -> None:
    settings = _settings_for_cache(tmp_path)
    manager = RuntimeSnapshotManager(settings=settings, started_at=datetime.now(UTC))

    manager.write_health_snapshot(
        pid=12345,
        health_state={"status": "ok"},
        watchers_running=True,
    )

    snapshot = _load_runtime_health(settings.health_snapshot_path())
    assert snapshot.orchestrator_pid == 12345
    assert snapshot.watchers_running is True
    assert snapshot.activity_state["health"]["status"] == "ok"


def test_runtime_snapshot_manager_for_server() -> None:
    manager = RuntimeSnapshotManager.for_server("alpha")
    assert isinstance(manager.settings, _MCPServerSettings)
    assert manager.settings.server_name == "alpha"


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


def test_load_runtime_telemetry_failure_and_non_dict(tmp_path: Path) -> None:
    missing = load_runtime_telemetry(tmp_path / "missing.json")
    assert missing.counters == {}

    path = tmp_path / "bad.json"
    path.write_text("[1, 2, 3]")
    assert load_runtime_telemetry(path).counters == {}

    broken = tmp_path / "broken.json"
    broken.write_text("{}")

    original_read_text = Path.read_text

    def boom_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == broken:
            raise OSError("boom")
        return original_read_text(self, *args, **kwargs)

    Path.read_text = boom_read_text  # type: ignore[assignment]
    try:
        assert load_runtime_telemetry(broken).counters == {}
    finally:
        Path.read_text = original_read_text  # type: ignore[assignment]


def test_write_runtime_telemetry_error_cleanup(tmp_path: Path, monkeypatch) -> None:
    snapshot = RuntimeTelemetrySnapshot(orchestrator_pid=1)
    path = tmp_path / "telemetry.json"

    tmp_path_obj = path.with_suffix(".tmp")
    unlink = Mock()
    monkeypatch.setattr(Path, "unlink", unlink)

    def boom_write_text(self: Path, *args: object, **kwargs: object) -> int:
        if self == tmp_path_obj:
            raise OSError("boom")
        return 0

    monkeypatch.setattr(Path, "write_text", boom_write_text)
    with pytest.raises(OSError):
        _MODULE.write_runtime_telemetry(path, snapshot)

    assert unlink.called


@pytest.mark.asyncio
async def test_run_snapshot_loop_and_sleep(monkeypatch) -> None:
    manager = types.SimpleNamespace(
        record=lambda name, amount=1: None,
        write_health_snapshot=lambda pid=None: None,
        write_telemetry_snapshot=lambda pid=None: None,
    )

    await _MODULE._sleep(0.0)

    async def fake_sleep(interval_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(_MODULE, "_sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await _MODULE.run_snapshot_loop(manager, pid=7, interval_seconds=0.0)


def test_runtime_telemetry_snapshot_as_dict_and_parse_helper() -> None:
    snapshot = RuntimeTelemetrySnapshot(
        orchestrator_pid=7,
        started_at="2026-05-17T12:00:00+00:00",
        updated_at="2026-05-17T12:01:00+00:00",
        uptime_seconds=12.5,
        counters={"updates": 3},
    )

    data = snapshot.as_dict()
    data["counters"]["updates"] = 99

    assert snapshot.counters["updates"] == 3
    assert _MODULE._parse_iso_datetime(None) is None
    assert _MODULE._parse_iso_datetime("not-a-timestamp") is None
    assert _MODULE._parse_iso_datetime("2026-05-17T12:00:00+00:00") is not None
