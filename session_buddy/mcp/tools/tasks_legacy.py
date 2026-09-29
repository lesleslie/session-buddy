"""Legacy coercion path for backwards-compatible ``tags=["todo"]`` rows.

Implements spec §Migration & Backwards Compatibility. Legacy reflections
created via the old ``store_reflection(tags=["todo"])`` API are surfaced
as ``LegacyTaskRow`` envelopes when ``tasks_list(include_legacy=True)``
matches them. Default behavior excludes them so legacy noise doesn't
surface as ghost tasks.

Functions:
    coerce_legacy_reflection(reflection) -> LegacyTaskRow | None
"""
from __future__ import annotations

from typing import Any

from session_buddy.mcp.tools.tasks_events import _CONTROL_CHARS
from session_buddy.mcp.tools.tasks_models import LegacyTaskRow
from session_buddy.mcp.tools.tasks_security import MAX_CONTENT_BYTES


def coerce_legacy_reflection(
    reflection: dict[str, Any],
) -> LegacyTaskRow | None:
    """Coerce a legacy ``store_reflection(tags=["todo"])`` row to LegacyTaskRow.

    Returns None if the row is malformed (missing id/content) or if the
    content fails the same validation as new tasks (length cap, control
    chars). Rejected rows are silently dropped — they do NOT appear in
    any list output. The spec documents this exclusion policy.

    Per spec §Migration & Backwards Compatibility line 696-706:
    - id = reflection ID (NOT a synthetic t-{32hex}; legacy rows predate UUID7)
    - content = as-is (must pass validation)
    - tags = as-is
    - coerced marker = True (set by LegacyTaskRow default)
    """
    reflection_id = reflection.get("id")
    content = reflection.get("content")
    if not isinstance(reflection_id, str) or not reflection_id:
        return None
    if not isinstance(content, str):
        return None

    # Reject content failing same validation as new tasks (spec §Migration).
    if len(content) > MAX_CONTENT_BYTES:
        return None
    if _CONTROL_CHARS.search(content):
        return None

    return LegacyTaskRow(
        id=reflection_id,
        content=content,
        tags=list(reflection.get("tags") or []),
    )