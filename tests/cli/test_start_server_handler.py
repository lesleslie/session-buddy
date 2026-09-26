#!/usr/bin/env python3
"""Tests for ``session_buddy.cli.base.start_server_handler`` after the
mcp-common launcher migration (Phase 4d, REQ-013).

The handler now delegates the FastMCP ``run`` call to
``mcp_common.server.launcher.launch`` so transport/http, uvicorn
grace timeout, and secrets loading are enforced by mcp-common rather
than scattered across per-component glue. These tests pin the new
contract:

- The pre-bind ``_port_holder`` check still raises SystemExit when the
  target port is held (the bind-fail-exit death loop fix stays).
- When the port is free, ``start_server_handler`` calls the launcher's
  ``launch(...)`` with the right kwargs (component_name, host, port,
  secrets_path).
- The launcher's ``build_server`` closure returns the module-level
  ``mcp`` instance — no inline ``FastMCP(...)`` rebuild, no
  session_lifecycle loss.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_mcp() -> MagicMock:
    """A MagicMock that quacks like the module-level FastMCP instance."""
    return MagicMock(name="mcp")


# ---------------------------------------------------------------------------
# Port-held pre-bind check (unchanged by migration)
# ---------------------------------------------------------------------------


def test_start_server_handler_raises_systemexit_when_port_held(
    fake_mcp: MagicMock,
) -> None:
    """Pre-bind check fires BEFORE launch() is called.

    Regression pin for the bind-fail-exit death loop fix from
    ``session_buddy.cli.base:117-125``. The launcher must NOT be invoked
    when the port is held.
    """
    with (
        patch("session_buddy.cli.base._port_holder", return_value=(4242, "fake")),
        patch(
            "session_buddy.server_optimized.mcp",
            fake_mcp,
        ),
        patch("mcp_common.server.launch") as mock_launch,
    ):
        from session_buddy.cli.base import start_server_handler

        with pytest.raises(SystemExit) as exc_info:
            start_server_handler()

    assert "4242" in str(exc_info.value)
    mock_launch.assert_not_called()


# ---------------------------------------------------------------------------
# launch() wiring (new post-migration contract)
# ---------------------------------------------------------------------------


def test_start_server_handler_calls_launch_with_lambda_mcp(
    fake_mcp: MagicMock,
) -> None:
    """When the port is free, ``launch(...)`` is called exactly once with
    ``build_server`` returning the module-level ``mcp`` instance.
    """
    with (
        patch("session_buddy.cli.base._port_holder", return_value=None),
        patch(
            "session_buddy.server_optimized.mcp",
            fake_mcp,
        ),
        patch("asyncio.run") as mock_asyncio_run,
        patch("mcp_common.server.launch") as mock_launch,
    ):
        from session_buddy.cli.base import start_server_handler

        start_server_handler()

    mock_asyncio_run.assert_called_once()
    mock_launch.assert_called_once()

    # The single positional arg to asyncio.run is the coroutine from
    # launch(...). Inspect what was passed to launch() directly.
    kwargs = mock_launch.call_args.kwargs
    assert kwargs["component_name"] == "session-buddy"
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8678
    # build_server is a zero-arg callable (variadic per REQ-003).
    assert kwargs["build_server"]() is fake_mcp


def test_start_server_handler_passes_component_name_session_buddy(
    fake_mcp: MagicMock,
) -> None:
    """``component_name`` is the fleet-standard identifier
    ``"session-buddy"`` (matches the value used in plists, logs,
    Akosha routing, and the design note's pre-warm surface)."""
    with (
        patch("session_buddy.cli.base._port_holder", return_value=None),
        patch(
            "session_buddy.server_optimized.mcp",
            fake_mcp,
        ),
        patch("asyncio.run"),
        patch("mcp_common.server.launch") as mock_launch,
    ):
        from session_buddy.cli.base import start_server_handler

        start_server_handler()

    assert mock_launch.call_args.kwargs["component_name"] == "session-buddy"


def test_start_server_handler_passes_secrets_path(
    fake_mcp: MagicMock,
) -> None:
    """``secrets_path`` defaults to ``~/.config/secrets.env``.

    Trap F from the launcher cookbook: the launcher reads this file via
    ``setdefault`` (additive — no regression for vars already set). The
    path is required so launchd-managed processes that don't inherit
    shell init files still get API keys.
    """
    from pathlib import Path

    with (
        patch("session_buddy.cli.base._port_holder", return_value=None),
        patch(
            "session_buddy.server_optimized.mcp",
            fake_mcp,
        ),
        patch("asyncio.run"),
        patch("mcp_common.server.launch") as mock_launch,
    ):
        from session_buddy.cli.base import start_server_handler

        start_server_handler()

    secrets_path = mock_launch.call_args.kwargs["secrets_path"]
    assert isinstance(secrets_path, Path)
    assert str(secrets_path).endswith(".config/secrets.env")


# ---------------------------------------------------------------------------
# Health body shape — REQ-005 patch-not-register
# ---------------------------------------------------------------------------


def test_health_handler_emits_launcher_field() -> None:
    """PATCH the existing /health handler to emit
    ``body["launcher"] = "mcp_common.server.launcher@<version>"``.

    Trap C: this is a PATCH on the existing handler, NOT a duplicate
    ``@app.custom_route("/health", ...)`` registration. The test asserts
    the field is present and the version string is the canonical mcp-common
    version (so editable-install drift doesn't lie about the build).
    """
    import asyncio
    import json

    import mcp_common

    from session_buddy.server_optimized import health_check

    request = MagicMock()

    # Force the "not initialized" branch so the body returns deterministically
    # without pulling the signer singleton or running the aggregator.
    with patch(
        "session_buddy.mcp.signer_feed.get_signer_feed_state",
        return_value=None,
    ):
        response = asyncio.run(health_check(request))

    body = json.loads(response.body)
    assert body["launcher"] == (
        f"mcp_common.server.launcher@{mcp_common.__version__}"
    )
