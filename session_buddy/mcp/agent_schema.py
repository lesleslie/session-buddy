"""Agent metadata schema (Phase 3 of bodai-skill-agent-distribution plan).

The canonical agent schema lives in
``mcp_common.canonical_schemas.agent``. This module is a thin re-export
shim that preserves the legacy ``AgentMetadata`` class name. New code
should import directly from ``mcp_common.canonical_schemas``.

The previous version of this module carried a 22-field model with
B-4 path-traversal allowlist validators and ``extra="forbid"`` /
``validate_assignment=True`` semantics. All of these now live in
:class:`mcp_common.canonical_schemas.agent.AgentCanonicalSchema`. This
shim preserves ``isinstance(x, AgentMetadata)`` for callers that
import the legacy name.

Note: session-buddy's local schema did NOT enforce the B-6
body-integrity ``model_validator`` (``sha256(system_prompt) ==
content_hash``) — that check is enforced at the agents_tools layer
instead. AkoSHA's local file is the only one that wraps the canonical
schema with the strict body-integrity subclass.
"""

from __future__ import annotations

from mcp_common.canonical_schemas._validators import NAME_OR_SERVER_RE
from mcp_common.canonical_schemas.agent import AgentCanonicalSchema

# Backward-compat alias. ``isinstance(x, AgentMetadata)`` resolves to
# ``isinstance(x, AgentCanonicalSchema)`` because Python treats the
# alias as the same class object.
AgentMetadata = AgentCanonicalSchema


__all__ = ["NAME_OR_SERVER_RE", "AgentMetadata"]
