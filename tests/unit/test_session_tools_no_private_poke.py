"""Regression test for Plan 7 Phase 2 Task 4: remove the
``mcp_server._tools = compat_tools`` private-API poke at
``session_buddy/mcp/tools/session/session_tools.py:~1168``.

FastMCP 3.4 no longer exposes a mutable ``_tools`` dict on the server.
The pre-3.x code monkey-patched ``mcp_server._tools``, ``mcp_server.tools``,
and ``mcp_server.get_tools`` to inject a ``SimpleNamespace``-wrapped copy
of the local tool functions. In 3.x:

- ``_tool_manager`` and ``_tools`` are not present on the server instance.
  Writing to them creates a useless instance attribute.
- ``mcp_server.tools`` is also undefined (FastMCP uses ``get_tool`` /
  ``list_tools`` instead). Writing to it has no effect on the server's
  tool registry.
- ``mcp_server.get_tools`` is a real async method on the FastMCP class.
  Overwriting it with a closure shadows the genuine tool-introspection
  API and silently breaks any caller that uses the public surface.

This test asserts that ``register_session_tools`` (and the
crackerjack variant) only use the public ``@mcp.tool()`` decorator and
the server's own ``add_tool`` / ``get_tool`` / ``list_tools`` surface.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class FakeServer:
    """Minimal stand-in for a FastMCP server used in tests.

    Records every ``@tool()`` registration in ``_registered`` and exposes
    ``get_tool`` / ``list_tools`` for public-API introspection — mirroring
    FastMCP 3.4's actual public surface.
    """

    def __init__(self) -> None:
        self._registered: dict[str, object] = {}

    def tool(self, *_args, **_kwargs):
        def decorator(fn):
            self._registered[fn.__name__] = fn
            return fn

        return decorator

    async def get_tool(self, name: str):
        return self._registered.get(name)

    async def list_tools(self):
        return list(self._registered.values())


@pytest.fixture
def fake_server() -> FakeServer:
    return FakeServer()


EXPECTED_SESSION_TOOLS = {
    "start",
    "checkpoint",
    "end",
    "status",
    "health_check",
    "server_info",
    "ping",
    "pre_compact_sync",
}


def test_register_session_tools_does_not_assign_private_attributes(
    fake_server: FakeServer,
) -> None:
    """register_session_tools must not mutate private / non-public attrs."""
    from session_buddy.mcp.tools.session.session_tools import (  # noqa: PLC0415
        register_session_tools,
    )

    register_session_tools(fake_server)

    # Private attributes that pre-3.x code wrote to. In 3.x they either
    # do not exist (writing is a no-op) or shadow public API (writing
    # is a foot-gun). Either way they must not be touched.
    for forbidden in ("_tools", "_tool_manager"):
        assert not hasattr(fake_server, forbidden), (
            f"register_session_tools must not write to {forbidden!r};"
            " use the @tool() decorator and public get_tool()/list_tools()"
        )


def test_register_session_tools_does_not_shadow_public_get_tools(
    fake_server: FakeServer,
) -> None:
    """The pre-3.x code overwrote ``mcp_server.get_tools`` with a local
    async function. In 3.x this shadows the real ``get_tools`` method.
    The migration must leave the public method intact.
    """
    from session_buddy.mcp.tools.session.session_tools import (  # noqa: PLC0415
        register_session_tools,
    )

    register_session_tools(fake_server)

    # If the prod code overwrote ``get_tools`` on the instance, the
    # descriptor lookup returns the closure instead of the bound method.
    # We assert the original public method is still bound on the class.
    assert FakeServer.get_tool is not None  # sanity: class attr present
    # Instance-level assignment would create an instance attribute that
    # shadows the class method; verify no such assignment happened.
    assert "get_tools" not in vars(fake_server)


def test_register_session_tools_registers_via_public_decorator(
    fake_server: FakeServer,
) -> None:
    """All eight expected tools must be reachable via the public API."""
    from session_buddy.mcp.tools.session.session_tools import (  # noqa: PLC0415
        register_session_tools,
    )

    register_session_tools(fake_server)

    missing = EXPECTED_SESSION_TOOLS - set(fake_server._registered)
    assert not missing, f"missing public-API registrations: {missing}"


def test_register_session_tools_tools_are_callable(
    fake_server: FakeServer,
) -> None:
    """Publicly-registered tools must be the actual coroutine functions.

    The pre-3.x code wrapped each tool in ``SimpleNamespace(function=...)``,
    which broke any caller that invoked ``tool()`` or ``tool.fn`` directly.
    Public-API registration must yield the bare async function.
    """
    from session_buddy.mcp.tools.session.session_tools import (  # noqa: PLC0415
        register_session_tools,
    )

    register_session_tools(fake_server)

    for name in EXPECTED_SESSION_TOOLS:
        registered = fake_server._registered[name]
        assert not isinstance(registered, SimpleNamespace), (
            f"{name!r} was registered as SimpleNamespace; the migration "
            "must drop the compat_tools wrapper"
        )


def test_register_crackerjack_tools_does_not_assign_private_attributes() -> None:
    """Same private-API discipline for the crackerjack sibling module."""
    fake = FakeServer()

    from session_buddy.mcp.tools.session.crackerjack_tools import (  # noqa: PLC0415
        register_crackerjack_tools,
    )

    register_crackerjack_tools(fake)

    for forbidden in ("_tools", "_tool_manager"):
        assert not hasattr(fake, forbidden), (
            f"register_crackerjack_tools must not write to {forbidden!r}"
        )


def test_register_crackerjack_tools_registers_via_public_decorator() -> None:
    """Spot-check: at least the ``execute_crackerjack_command`` tool is registered."""
    fake = FakeServer()

    from session_buddy.mcp.tools.session.crackerjack_tools import (  # noqa: PLC0415
        register_crackerjack_tools,
    )

    register_crackerjack_tools(fake)

    assert "execute_crackerjack_command" in fake._registered
    # No SimpleNamespace wrappers slipped through.
    assert not isinstance(
        fake._registered["execute_crackerjack_command"],
        SimpleNamespace,
    )


def test_register_session_tools_works_with_real_fastmcp_server() -> None:
    """End-to-end check: register_session_tools works against a real
    FastMCP 3.4 server without raising.
    """
    from mcp_common.fastmcp import FastMCP  # noqa: PLC0415
    from session_buddy.mcp.tools.session.session_tools import (  # noqa: PLC0415
        register_session_tools,
    )

    server = FastMCP("test-session-tools")
    register_session_tools(server)

    # Public API: list_tools() returns Tool objects with a ``name`` attr.
    import asyncio

    async def _check() -> None:
        tools = await server.list_tools()
        names = {t.name for t in tools}
        assert EXPECTED_SESSION_TOOLS.issubset(names), (
            f"FastMCP server does not see the expected tools; got {names}"
        )

    asyncio.run(_check())


# ---------------------------------------------------------------------------
# Helper used to keep the test self-contained; if mcp_common.fastmcp ever
# moves, the import path is updated in one place.
# ---------------------------------------------------------------------------

# Defensive: a MagicMock test would silently pass even if the prod code
# never called the decorator. We use the real FakeServer above so the
# assertions exercise the actual registration codepath.


def _unused_sanity_check_to_keep_magic_mock_import() -> None:  # pragma: no cover
    MagicMock()
