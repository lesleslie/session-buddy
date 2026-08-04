from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from session_buddy.mcp.tools.memory.akosha_tools import (
    akosha_sync_status,
    register_akosha_tools,
    sync_to_akosha,
)
from session_buddy.storage.akosha_config import AkoshaSyncConfig


def _config() -> AkoshaSyncConfig:
    return AkoshaSyncConfig(
        cloud_bucket="test-bucket",
        cloud_endpoint="https://storage.example.com",
        cloud_region="us-east-1",
        system_id="test-system",
        upload_on_session_end=False,
        enable_fallback=True,
        force_method="auto",
        upload_timeout_seconds=120,
        max_retries=4,
        retry_backoff_seconds=1.5,
        enable_compression=False,
        enable_deduplication=False,
        chunk_size_mb=8,
    )


async def test_sync_to_akosha_returns_success_with_manual_metadata() -> None:
    config = _config()
    sync_result = {
        "method": "cloud",
        "success": True,
        "files_uploaded": ["reflection.duckdb"],
    }
    sync_instance = SimpleNamespace(sync_memories=AsyncMock(return_value=sync_result))

    with (
        patch.object(AkoshaSyncConfig, "from_settings", return_value=config),
        patch(
            "session_buddy.mcp.tools.memory.akosha_tools.HybridAkoshaSync",
            return_value=sync_instance,
        ) as sync_class,
    ):
        result = await sync_to_akosha(method="cloud")

    assert result == {**sync_result, "triggered_by": "manual"}
    sync_class.assert_called_once_with(config)
    sync_instance.sync_memories.assert_awaited_once_with(force_method="cloud")


async def test_sync_to_akosha_disables_fallback_without_losing_config() -> None:
    config = _config()
    sync_instance = SimpleNamespace(
        sync_memories=AsyncMock(return_value={"method": "http", "success": True})
    )

    with (
        patch.object(AkoshaSyncConfig, "from_settings", return_value=config),
        patch(
            "session_buddy.mcp.tools.memory.akosha_tools.HybridAkoshaSync",
            return_value=sync_instance,
        ) as sync_class,
    ):
        result = await sync_to_akosha(method="http", enable_fallback=False)

    rebuilt_config = sync_class.call_args.args[0]
    assert rebuilt_config == AkoshaSyncConfig(
        cloud_bucket="test-bucket",
        cloud_endpoint="https://storage.example.com",
        cloud_region="us-east-1",
        system_id="test-system",
        upload_on_session_end=False,
        enable_fallback=False,
        force_method="auto",
        upload_timeout_seconds=120,
        max_retries=4,
        retry_backoff_seconds=1.5,
        enable_compression=False,
        enable_deduplication=False,
        chunk_size_mb=8,
    )
    assert result["triggered_by"] == "manual"


async def test_sync_to_akosha_returns_structured_failure() -> None:
    with patch.object(
        AkoshaSyncConfig,
        "from_settings",
        side_effect=RuntimeError("configuration unavailable"),
    ):
        result = await sync_to_akosha(method="auto")

    assert result == {
        "method": "auto",
        "success": False,
        "error": "configuration unavailable",
        "triggered_by": "manual",
    }


async def test_akosha_sync_status_reports_resolved_configuration() -> None:
    config = _config()

    with patch.object(AkoshaSyncConfig, "from_settings", return_value=config):
        result = await akosha_sync_status()

    assert result == {
        "cloud_configured": True,
        "system_id": "test-system",
        "should_use_cloud": True,
        "should_use_http": True,
        "force_method": "auto",
        "enable_fallback": True,
        "upload_on_session_end": False,
        "configuration": {
            "cloud_bucket": "test-bucket",
            "cloud_endpoint": "https://storage.example.com",
            "cloud_region": "us-east-1",
            "system_id": "test-system",
            "enable_compression": False,
            "enable_deduplication": False,
            "chunk_size_mb": 8,
            "upload_timeout_seconds": 120,
            "max_retries": 4,
            "retry_backoff_seconds": 1.5,
        },
    }


async def test_akosha_sync_status_propagates_configuration_errors() -> None:
    with (
        patch.object(
            AkoshaSyncConfig,
            "from_settings",
            side_effect=ValueError("invalid configuration"),
        ),
        pytest.raises(ValueError, match="invalid configuration"),
    ):
        await akosha_sync_status()


def test_register_akosha_tools_registers_both_public_tools() -> None:
    registered: list[object] = []
    mcp_instance = Mock()
    mcp_instance.tool.return_value = registered.append

    register_akosha_tools(mcp_instance)

    assert registered == [sync_to_akosha, akosha_sync_status]
    assert mcp_instance.tool.call_count == 2


def test_register_akosha_tools_propagates_registration_errors() -> None:
    mcp_instance = Mock()
    mcp_instance.tool.side_effect = RuntimeError("registration failed")

    with pytest.raises(RuntimeError, match="registration failed"):
        register_akosha_tools(mcp_instance)


def test_akosha_mcp_tools_registration_smoke() -> None:
    assert sync_to_akosha is not None
    assert akosha_sync_status is not None
    assert register_akosha_tools is not None
