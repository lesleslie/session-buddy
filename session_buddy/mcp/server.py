"""MCP Server module - imports and exports the mcp instance.

This module imports the mcp instance from server_optimized. The
``ToolProfile``-driven tool registration is applied by
``server_optimized.build_live_server()``, which the launcher calls when
the server is about to serve -- so this module hands out the same
instance the live process serves, and the live process completes its
tool surface at start-up.

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
``session_buddy/mcp/tools/profiles.py``, which also owns the dispatch
itself (``apply_tool_profile_sync``, called by
``server_optimized.build_live_server()``).
``admin_shell_tracking_tools`` is registered at FULL profile via the
same mechanism (preserves pre-refactor behavior).
"""

from __future__ import annotations

import logging

from ..server_optimized import mcp

logger = logging.getLogger(__name__)

# The profile dispatch used to live here, applied to ``mcp`` at module
# load. It now lives in ``session_buddy/mcp/tools/profiles.py`` and is
# applied by ``session_buddy.server_optimized.build_live_server()``,
# which the launcher calls when the server is about to serve.
#
# It could not stay here: this module imports ``mcp`` from
# ``server_optimized``, so ``server_optimized`` cannot import this
# module back without an import cycle -- and ``server_optimized`` is
# the module that *owns* the instance and must apply the profile to it.

__all__ = ["mcp"]
