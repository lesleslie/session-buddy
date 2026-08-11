"""Checkpoint-scope exception scrubbing utilities.

These helpers are public within the checkpoint package; do NOT re-export
from the top-level session_buddy namespace. They are intentionally narrow
to the checkpoint subsystem and not a general-purpose logging framework.
"""
from __future__ import annotations

from typing import Any

import httpx


def safe_transient_info(exc: BaseException) -> dict[str, Any]:
    """Operator-visible fields from transient exceptions.

    For httpx.HTTPStatusError, returns ONLY status code and host.
    NEVER echoes URL path, query, userinfo, or response body.
    For other exceptions, returns only the exception type name.
    Captures AttributeError/ValueError/TypeError/RuntimeError defensively.
    """
    info: dict[str, Any] = {"type": type(exc).__name__}
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            info["status"] = exc.response.status_code
        except Exception:  # noqa: BLE001 — best-effort, never raise from logging
            pass
        # `exc.request` is an httpx property that raises RuntimeError
        # when the underlying _request slot is None. Wrap defensively.
        try:
            request = exc.request
        except Exception:  # noqa: BLE001
            request = None
        if request is not None:
            try:
                host = request.url.host
            except (AttributeError, ValueError, TypeError):
                host = None
            if host:
                info["host"] = host
    return info


def safe_error_message(prefix: str, exc: BaseException) -> str:
    """Scrubbed error message string for result.error field.

    Format: f"{prefix} {type_name} (HTTP {status})" for HTTPStatusError,
    f"{prefix} {type_name}" for other exceptions.
    NEVER echoes the raw exception string — that path leaks URL body
    fragments and HTTP response payloads into the persisted result.error
    field.
    """
    parts = [prefix, type(exc).__name__]
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            parts.append(f"(HTTP {exc.response.status_code})")
        except Exception:  # noqa: BLE001
            parts.append("(HTTP ?)")
    return " ".join(parts)
