"""Tests for session_buddy.mcp.tools.memory.akosha_tools.

Covers the Akosha sync MCP tools:
- ``sync_to_akosha``: happy path (cloud + http), fallback disabled,
  exception → error result, forced method propagated, triggered_by
  metadata always set
- ``akosha_sync_status``: returns expected status dict shape,
  cloud_configured/cloud_should_use flags, configuration sub-dict
- ``register_akosha_tools``: attaches both tools to the MCP server
- ``__all__`` exports

The tests patch ``settings_module.get_settings`` and the
``HybridAkoshaSync.sync_memories`` to avoid real network/storage
operations.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_buddy.mcp.tools.memory import akosha_tools
from session_buddy.mcp.tools.memory.akosha_tools import (
    akosha_sync_status,
    register_akosha_tools,
    sync_to_akosha,
)
from session_buddy.storage.akosha_sync import HybridAkoshaSync


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_settings(**overrides) -> SimpleNamespace:
    """Build a settings namespace that AkoshaSyncConfig.from_settings consumes."""
    base = dict(
        akosha_cloud_bucket="my-bucket",
        akosha_cloud_endpoint="https://s3.example.com",
        akosha_cloud_region="us-east-1",
        akosha_system_id="test-system",
        akosha_upload_on_session_end=True,
        akosha_enable_fallback=True,
        akosha_force_method="auto",
        akosha_upload_timeout_seconds=300,
        akosha_max_retries=3,
        akosha_retry_backoff_seconds=2.0,
        akosha_enable_compression=True,
        akosha_enable_deduplication=True,
        akosha_chunk_size_mb=5,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# sync_to_akosha
# ---------------------------------------------------------------------------


class TestSyncToAkosha:
    @pytest.mark.asyncio
    async def test_happy_path_auto(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_settings = _fake_settings()
        monkeypatch.setattr(
            akosha_tools.settings_module, "get_settings",
            lambda: fake_settings,
        )

        # Patch HybridAkoshaSync.sync_memories
        async def fake_sync_memories(self, force_method="auto"):
            assert force_method == "auto"
            return {
                "method": "cloud",
                "success": True,
                "files_uploaded": ["x"],
                "bytes_transferred": 100,
                "duration_seconds": 1.5,
                "upload_id": "upl-1",
                "error": None,
            }

        monkeypatch.setattr(
            HybridAkoshaSync, "sync_memories", fake_sync_memories
        )

        result = await sync_to_akosha(method="auto")
        assert result["method"] == "cloud"
        assert result["success"] is True
        assert result["triggered_by"] == "manual"

    @pytest.mark.asyncio
    async def test_forced_http(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_settings = _fake_settings()
        monkeypatch.setattr(
            akosha_tools.settings_module, "get_settings",
            lambda: fake_settings,
        )

        async def fake_sync_memories(self, force_method="auto"):
            return {
                "method": "http",
                "success": True,
                "files_uploaded": [],
                "bytes_transferred": 0,
                "duration_seconds": 0.1,
                "upload_id": "upl-2",
                "error": None,
            }

        monkeypatch.setattr(
            HybridAkoshaSync, "sync_memories", fake_sync_memories
        )

        result = await sync_to_akosha(method="http")
        assert result["method"] == "http"
        assert result["triggered_by"] == "manual"

    @pytest.mark.asyncio
    async def test_exception_returns_error_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_settings = _fake_settings()
        monkeypatch.setattr(
            akosha_tools.settings_module, "get_settings",
            lambda: fake_settings,
        )

        # Force sync to raise.
        async def boom(self, force_method="auto"):
            raise RuntimeError("adapter construction failed")

        monkeypatch.setattr(HybridAkoshaSync, "sync_memories", boom)

        result = await sync_to_akosha(method="auto")
        assert result["method"] == "auto"
        assert result["success"] is False
        assert "adapter construction failed" in result["error"]
        assert result["triggered_by"] == "manual"

    @pytest.mark.asyncio
    async def test_fallback_disabled_overrides_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_settings = _fake_settings(akosha_enable_fallback=True)
        monkeypatch.setattr(
            akosha_tools.settings_module, "get_settings",
            lambda: fake_settings,
        )

        captured_config: list = []

        async def fake_sync_memories(self, force_method="auto"):
            # Capture the config the HybridAkoshaSync was built with.
            captured_config.append(self.config.enable_fallback)
            return {
                "method": "cloud",
                "success": True,
                "files_uploaded": [],
                "bytes_transferred": 0,
                "duration_seconds": 0.1,
                "upload_id": "upl-3",
                "error": None,
            }

        monkeypatch.setattr(
            HybridAkoshaSync, "sync_memories", fake_sync_memories
        )

        await sync_to_akosha(method="cloud", enable_fallback=False)
        # enable_fallback was True in settings, but sync_to_akosha
        # overrode it to False on the constructed config.
        assert captured_config == [False]

    @pytest.mark.asyncio
    async def test_forced_cloud_propagates_to_sync(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_settings = _fake_settings()
        monkeypatch.setattr(
            akosha_tools.settings_module, "get_settings",
            lambda: fake_settings,
        )

        captured: list = []

        async def fake_sync_memories(self, force_method="auto"):
            captured.append(force_method)
            return {
                "method": "cloud",
                "success": True,
                "files_uploaded": [],
                "bytes_transferred": 0,
                "duration_seconds": 0.1,
                "upload_id": "upl-4",
                "error": None,
            }

        monkeypatch.setattr(
            HybridAkoshaSync, "sync_memories", fake_sync_memories
        )

        await sync_to_akosha(method="cloud")
        assert captured == ["cloud"]


# ---------------------------------------------------------------------------
# akosha_sync_status
# ---------------------------------------------------------------------------


class TestAkoshaSyncStatus:
    @pytest.mark.asyncio
    async def test_returns_expected_shape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_settings = _fake_settings()
        monkeypatch.setattr(
            akosha_tools.settings_module, "get_settings",
            lambda: fake_settings,
        )

        result = await akosha_sync_status()
        assert result["cloud_configured"] is True
        assert result["system_id"] == "test-system"
        # The should_use_* helpers depend on internal config logic; we
        # only verify they're booleans (not their specific values).
        assert isinstance(result["should_use_cloud"], bool)
        assert isinstance(result["should_use_http"], bool)
        assert result["force_method"] == "auto"
        assert result["enable_fallback"] is True
        assert result["upload_on_session_end"] is True
        # Configuration sub-dict.
        cfg = result["configuration"]
        assert cfg["cloud_bucket"] == "my-bucket"
        assert cfg["cloud_endpoint"] == "https://s3.example.com"
        assert cfg["cloud_region"] == "us-east-1"
        assert cfg["system_id"] == "test-system"
        assert cfg["enable_compression"] is True
        assert cfg["enable_deduplication"] is True
        assert cfg["chunk_size_mb"] == 5
        assert cfg["upload_timeout_seconds"] == 300
        assert cfg["max_retries"] == 3
        assert cfg["retry_backoff_seconds"] == 2.0

    @pytest.mark.asyncio
    async def test_handles_missing_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # All Akosha settings empty → cloud_configured = False.
        monkeypatch.setattr(
            akosha_tools.settings_module, "get_settings",
            lambda: SimpleNamespace(),
        )

        result = await akosha_sync_status()
        assert result["cloud_configured"] is False
        assert result["configuration"]["cloud_bucket"] == ""


# ---------------------------------------------------------------------------
# register_akosha_tools
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registers_both_tools(self) -> None:
        mcp = MagicMock()
        tool_calls: list[object] = []

        def tool_decorator():
            def decorator(fn):
                tool_calls.append(fn)
                return fn
            return decorator

        mcp.tool = tool_decorator
        register_akosha_tools(mcp)
        # Both tools registered.
        assert sync_to_akosha in tool_calls
        assert akosha_sync_status in tool_calls

    def test_module_exports(self) -> None:
        assert "akosha_sync_status" in akosha_tools.__all__
        assert "register_akosha_tools" in akosha_tools.__all__
        assert "sync_to_akosha" in akosha_tools.__all__
