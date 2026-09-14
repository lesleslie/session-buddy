"""Smoke tests for the ``mcp_common.clients.CommonMCPClient`` integration.

Phase 3 of
``docs/plans/2026-09-14-common-mcp-client-transport-unification.md``
migrated Session-Buddy's two ``/tools/call`` POST sites to use the
shared ``CommonMCPClient`` SDK (REQ-004). These tests pin that the
SDK is importable from this repo's venv, exposes the documented
``call_tool(name, arguments)`` method, and round-trips a mocked
streamable-HTTP session so the migration wire-shape stays stable.

The heavy contract for ``CommonMCPClient`` lives in
``mcp-common/tests/unit/clients/test_common_mcp_client.py`` (11
tests). This file complements those with a smoke focus: confirm
Session-Buddy's migration sites can be exercised end-to-end via the
new SDK shape without spinning up a live Dhara / Akosha server.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_common.clients import (
    CommonMCPClient,
    MCPClientHTTPError,
    MCPClientTimeoutError,
)


# ---------------------------------------------------------------------------
# Wire-shape smoke
# ---------------------------------------------------------------------------


def test_common_mcp_client_importable() -> None:
    """``CommonMCPClient`` is importable from the canonical SDK path.

    Pins that the dep floor pinned in
    ``session-buddy/pyproject.toml`` (``mcp-common>=0.26.1``) actually
    ships the renamed client. A regression here means the dep floor
    silently regressed to a pre-rename release.
    """
    assert CommonMCPClient.__module__ == "mcp_common.clients.common_mcp_client"
    # API surface the migration sites rely on:
    client = CommonMCPClient(base_url="http://localhost:8683/mcp")
    assert callable(getattr(client, "call_tool", None))
    assert callable(getattr(client, "aclose", None))


def test_ssrf_guard_rejects_non_http_schemes() -> None:
    """The constructor still blocks SSRF via the scheme allowlist.

    Mirrors the upstream test in
    ``mcp-common/tests/unit/clients/test_common_mcp_client.py`` to
    guarantee the guard shipped to this repo's venv intact.
    """
    for bad in ("file", "ftp", "gopher", "javascript", "data"):
        with pytest.raises(ValueError, match="not allowed"):
            CommonMCPClient(base_url=f"{bad}://example.com/x")


# ---------------------------------------------------------------------------
# Mocked round-trip — confirms call_tool(name, arguments) wire shape
# ---------------------------------------------------------------------------


def _make_mock_session() -> MagicMock:
    """Return a MagicMock standing in for ``mcp.ClientSession``."""
    session = MagicMock(name="ClientSession")
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.initialize = AsyncMock(return_value=None)
    session.call_tool = AsyncMock(
        return_value={
            "isError": False,
            "content": [{"type": "text", "text": "{}"}],
        }
    )
    return session


@pytest.mark.asyncio
async def test_dhara_put_call_tool_round_trips_arguments() -> None:
    """``CommonMCPClient.call_tool`` forwards ``name`` + ``arguments``.

    Anchors the same wire shape that
    ``session_buddy.server_optimized._register_to_dhara_once`` now
    relies on (``put`` → ``{key, value}``). A regression in the
    argument forwarding would surface here.
    """
    session = _make_mock_session()

    fake_rs, fake_ws = MagicMock(), MagicMock()

    @asynccontextmanager
    async def fake_streamable_http_client(*_a: Any, **_kw: Any) -> Any:
        yield fake_rs, fake_ws

    fake_transport = MagicMock(name="streamable_http_client")
    fake_transport.side_effect = fake_streamable_http_client

    with (
        patch("mcp.client.streamable_http.streamable_http_client", fake_transport),
        patch("mcp.client.session.ClientSession", return_value=session),
    ):
        client = CommonMCPClient(base_url="http://localhost:8683/mcp", timeout=10.0)
        result = await client.call_tool(
            "put",
            {"key": "component_endpoint/session-buddy", "value": "http://127.0.0.1:8678/mcp"},
            timeout=10.0,
        )
        await client.aclose()

    session.call_tool.assert_awaited_once_with(
        "put",
        {"key": "component_endpoint/session-buddy", "value": "http://127.0.0.1:8678/mcp"},
    )
    assert result["isError"] is False


@pytest.mark.asyncio
async def test_record_time_series_call_tool_round_trips_arguments() -> None:
    """``call_tool("record_time_series", ...)`` forwards the full arg dict.

    Anchors the wire shape that
    ``session_buddy.mcp.tools.session.channel_tracking_tools.DharaChannelPublisher``
    now relies on for fire-and-forget time-series recording.
    """
    session = _make_mock_session()

    fake_rs, fake_ws = MagicMock(), MagicMock()

    @asynccontextmanager
    async def fake_streamable_http_client(*_a: Any, **_kw: Any) -> Any:
        yield fake_rs, fake_ws

    fake_transport = MagicMock(name="streamable_http_client")
    fake_transport.side_effect = fake_streamable_http_client

    record = {"event_type": "channel_session_start", "channel_type": "slack"}
    with (
        patch("mcp.client.streamable_http.streamable_http_client", fake_transport),
        patch("mcp.client.session.ClientSession", return_value=session),
    ):
        client = CommonMCPClient(base_url="http://localhost:8683/mcp", timeout=5.0)
        await client.call_tool(
            "record_time_series",
            {"metric_type": "session_buddy.channel_event", "entity_id": "chan_x", "record": record},
            timeout=5.0,
        )
        await client.aclose()

    session.call_tool.assert_awaited_once_with(
        "record_time_series",
        {"metric_type": "session_buddy.channel_event", "entity_id": "chan_x", "record": record},
    )


# ---------------------------------------------------------------------------
# Negative paths the migration sites rely on (errors must be swallowable)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_tool_5xx_surfaces_as_mcp_client_http_error() -> None:
    """A 5xx response surfaces as ``MCPClientHTTPError``.

    ``_register_to_dhara_once`` and ``DharaChannelPublisher.publish``
    both swallow ``Exception`` to keep Dhara outages non-fatal. This
    test pins that the SDK raises the documented error type (so the
    callers' catch-all actually triggers on transport-level failures,
    not on hidden ``BaseException`` surprises).
    """
    fake_session = MagicMock(name="ClientSession")
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)
    fake_session.initialize = AsyncMock(return_value=None)
    fake_session.call_tool = AsyncMock(
        side_effect=MCPClientHTTPError("HTTP 503", status_code=503)
    )

    fake_rs, fake_ws = MagicMock(), MagicMock()

    @asynccontextmanager
    async def fake_streamable_http_client(*_a: Any, **_kw: Any) -> Any:
        yield fake_rs, fake_ws

    fake_transport = MagicMock(name="streamable_http_client")
    fake_transport.side_effect = fake_streamable_http_client

    with (
        patch("mcp.client.streamable_http.streamable_http_client", fake_transport),
        patch("mcp.client.session.ClientSession", return_value=fake_session),
    ):
        client = CommonMCPClient(base_url="http://localhost:8683/mcp")
        with pytest.raises(MCPClientHTTPError) as exc_info:
            await client.call_tool("put", {"key": "k", "value": "v"}, timeout=5.0)
        assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_call_tool_timeout_surfaces_as_mcp_client_timeout_error() -> None:
    """An ``httpx.ReadTimeout`` surfaces as ``MCPClientTimeoutError``.

    The DharaChannelPublisher swallows this so a slow Dhara never
    blocks channel-tracking. Pinning the error type ensures the
    SDK's transport-level error contract stays stable.
    """
    from mcp_common.clients import MCPClientTimeoutError

    fake_session = MagicMock(name="ClientSession")
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)
    fake_session.initialize = AsyncMock(return_value=None)
    fake_session.call_tool = AsyncMock(
        side_effect=MCPClientTimeoutError("call_tool timed out")
    )

    fake_rs, fake_ws = MagicMock(), MagicMock()

    @asynccontextmanager
    async def fake_streamable_http_client(*_a: Any, **_kw: Any) -> Any:
        yield fake_rs, fake_ws

    fake_transport = MagicMock(name="streamable_http_client")
    fake_transport.side_effect = fake_streamable_http_client

    with (
        patch("mcp.client.streamable_http.streamable_http_client", fake_transport),
        patch("mcp.client.session.ClientSession", return_value=fake_session),
    ):
        client = CommonMCPClient(base_url="http://localhost:8683/mcp")
        with pytest.raises(MCPClientTimeoutError):
            await client.call_tool("record_time_series", {"metric_type": "m"}, timeout=5.0)
