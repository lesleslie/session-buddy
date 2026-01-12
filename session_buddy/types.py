"""Shared type aliases for session-buddy.

Kept intentionally small; most modules should prefer local, explicit types.
"""

from __future__ import annotations

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

JsonDict = dict[str, JsonValue]
