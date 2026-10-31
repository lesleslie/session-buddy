"""Skill metadata schema (Phase 1 of bodai-skill-agent-distribution plan).

The canonical skill schema lives in
``mcp_common.canonical_schemas.skill``. This module is a thin re-export
shim that preserves the legacy ``SkillMetadata`` class name. New code
should import directly from ``mcp_common.canonical_schemas``.

The previous version of this module carried an 18-field model with
B-4 path-traversal allowlist validators (``server`` and ``name``),
``extra="forbid"``, ``str_strip_whitespace=True``, and
``validate_assignment=True`` semantics. All of these now live in
:class:`mcp_common.canonical_schemas.skill.SkillCanonicalSchema`. This
shim preserves ``isinstance(x, SkillMetadata)`` for callers that
import the legacy name.
"""

from __future__ import annotations

from mcp_common.canonical_schemas._validators import NAME_OR_SERVER_RE
from mcp_common.canonical_schemas.skill import SkillCanonicalSchema

# Backward-compat alias. ``isinstance(x, SkillMetadata)`` resolves to
# ``isinstance(x, SkillCanonicalSchema)`` because Python treats the
# alias as the same class object.
SkillMetadata = SkillCanonicalSchema


__all__ = ["NAME_OR_SERVER_RE", "SkillMetadata"]
