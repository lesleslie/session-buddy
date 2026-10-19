"""MCP Server module - imports and exports the mcp instance.

This module imports the mcp instance from server_optimized and registers
tool modules based on the active ``ToolProfile`` via the W0 helper in
``mcp_common.tools.dispatch``.

Profile configuration
---------------------
The profile is read from the ``SESSION_BUDDY_TOOL_PROFILE`` environment
variable.  When unset or invalid the default is ``FULL`` (all tools).

    SESSION_BUDDY_TOOL_PROFILE=minimal   # minimal core + mandatory health
    SESSION_BUDDY_TOOL_PROFILE=standard  # daily-development essentials
    SESSION_BUDDY_TOOL_PROFILE=full      # all tools (default)

W0 helper integration
---------------------
Tool registration is delegated to ``_apply_tool_profile`` from
``mcp-common>=0.18.0``. ``REGISTRATION_MAP`` and
``SESSION_BUDDY_MANDATORY_GROUPS`` are defined in
``session_buddy/mcp/tools/profiles.py``. ``admin_shell_tracking_tools``
is registered at FULL profile via the same mechanism (preserves
pre-refactor behavior).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp_common.tools.dispatch import _apply_tool_profile

from ..server_optimized import mcp
from .tools.profiles import (
    PROFILE_REGISTRATIONS,
    REGISTRATION_MAP,
    SESSION_BUDDY_MANDATORY_GROUPS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# W0 helper wiring
# ---------------------------------------------------------------------------


def _register_all_tool_groups(server: Any) -> None:
    """Bulk register every tool group at FULL profile.

    The W0 helper invokes this once when ``PROFILE_REGISTRATIONS[FULL]``
    is ``ALL_TOOLS``. We skip the mandatory groups because the helper
    re-registers them in its mandatory_groups pass; running them here
    would create duplicate tool registration warnings from FastMCP.
    """
    for name, fn in REGISTRATION_MAP.items():
        if name in SESSION_BUDDY_MANDATORY_GROUPS:
            continue
        fn(server)


# Apply the profile at module load. ``_apply_tool_profile`` is async; the
# helper raises if called from inside a running event loop, so wrap with
# ``asyncio.run`` (which spins a fresh loop and is safe at module-import
# time when no loop is running). session-buddy is env-only so
# ``yaml_loader=None`` -- no settings/local.yaml lookup.
#
# ``pytest-asyncio``'s ``asyncio_mode = "auto"`` runs every test inside a
# running event loop, which would make ``asyncio.run`` blow up at module
# import under those test runs. Detect that case and defer to a
# background task scheduled on the running loop instead -- the profile
# still gets applied, just not from a freshly-spun loop.
try:
    asyncio.get_running_loop()
    loop_running = True
except RuntimeError:
    loop_running = False

if loop_running:
    import contextlib

    # Schedule the profile dispatch on the running loop. We can't await
    # it here (module import is synchronous), so create a task and let
    # it run when the loop next yields.
    with contextlib.suppress(RuntimeError):
        asyncio.ensure_future(
            _apply_tool_profile(
                mcp,
                profile_env_var="SESSION_BUDDY_TOOL_PROFILE",
                registrations=PROFILE_REGISTRATIONS,
                registration_map=REGISTRATION_MAP,
                register_all_fn=_register_all_tool_groups,
                mandatory_groups=SESSION_BUDDY_MANDATORY_GROUPS,
                essential_tool_names=set(),
                yaml_loader=None,
            )
        )
else:
    asyncio.run(
        _apply_tool_profile(
            mcp,
            profile_env_var="SESSION_BUDDY_TOOL_PROFILE",
            registrations=PROFILE_REGISTRATIONS,
            registration_map=REGISTRATION_MAP,
            register_all_fn=_register_all_tool_groups,
            mandatory_groups=SESSION_BUDDY_MANDATORY_GROUPS,
            essential_tool_names=set(),
            yaml_loader=None,
        )
    )

__all__ = ["mcp"]
