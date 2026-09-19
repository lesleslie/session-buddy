"""Agent metadata schema (Phase 3 of bodai-skill-agent-distribution plan).

Per docs/superpowers/plans/2026-09-14-dhara-mcp-decomposition-implementation.md
Phase 10 task 4, the canonical agent schema now lives in
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

Refs:
- docs/superpowers/specs/2026-09-14-dhara-mcp-decomposition-design.md §4.11
- docs/audits/2026-09-15-decomposition-final-review.md §2.1 W4
"""

from __future__ import annotations

from mcp_common.canonical_schemas._validators import NAME_OR_SERVER_RE
from mcp_common.canonical_schemas.agent import AgentCanonicalSchema

# Backward-compat alias. ``isinstance(x, AgentMetadata)`` resolves to
# ``isinstance(x, AgentCanonicalSchema)`` because Python treats the
# alias as the same class object.
AgentMetadata = AgentCanonicalSchema


__all__ = ["NAME_OR_SERVER_RE", "AgentMetadata"]
