"""Server-side identity derivation for task-system tools.

Per the spec (v1.1 §Authz Model), owner/created_by/completed_by/actor are
derived from the authenticated MCP caller identity. Caller-supplied values
are silently overwritten.

The MCP context shape (subject to change; verify against current
mcp_common client) is::

    ctx = {
        "auth": {
            "user_email": "les@wedgwoodwebworks.com",  # OR
            "agent_id": "crackerjack-fixer-pool",
        },
        ...
    }
"""
from __future__ import annotations

import re

from session_buddy.mcp.tools.tasks_models import OWNER_PATTERN

# Re-exported here so callers can pre-compile and avoid the cost of
# re.match() recompiling the pattern on every validate_owner_format call.
OWNER_RE = re.compile(OWNER_PATTERN)


def derive_caller_identity(mcp_context: dict) -> str:
    """Return the caller identity string for this MCP request.

    Returns ``user:<email>`` if a user is authenticated, else
    ``agent:<id>`` if an agent is authenticated. Raises
    ``PermissionError`` if neither is present (the spec requires this —
    anonymous calls fail closed).
    """
    auth = mcp_context.get("auth") or {}
    user = auth.get("user_email")
    if user:
        return f"user:{user}"
    agent = auth.get("agent_id")
    if agent:
        return f"agent:{agent}"
    raise PermissionError(
        "MCP caller has no authenticated identity (no user_email, no agent_id)"
    )


def validate_owner_format(owner: str) -> None:
    """Validate that ``owner`` matches the canonical OWNER_PATTERN.

    Raises ``ValueError`` on mismatch. Used for caller-supplied owner
    values; server-set owners bypass this because they're already
    authenticated.
    """
    if not isinstance(owner, str) or not OWNER_RE.match(owner):
        raise ValueError(
            f"owner {owner!r} does not match the canonical format "
            f"(user:<email> | agent:<id>)"
        )
