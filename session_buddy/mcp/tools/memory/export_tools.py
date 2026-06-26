#!/usr/bin/env python3
"""Export + lint MCP tools for session-buddy reflections.

Plan 3 Phase 1 Tier 1 Item #3 — closes the "memory is opaque" gap.

Two MCP tools live here:

- ``export_markdown(reflection_id, format="md"|"html")`` — exports a
  single reflection as a self-contained Markdown (or HTML-wrapped)
  document with YAML frontmatter (id, tags, created_at, source_type,
  project). The output is suitable for sharing, doc pipelines, or
  ingestion into RAG indexes that respect frontmatter.
- ``lint_memory(reflection_id)`` — re-runs an OWASP-style scan over
  the reflection's content for **known false-negatives** of the write
  guard (``memory_guard_adapter.py``): Cyrillic homoglyphs inside
  ASCII-looking tokens (the canonical example being ``skаbc...``
  where the second character is a Cyrillic "а"), and base64 blobs
  long enough to be a plausible exfiltration channel (>= 40 chars).

Both tools are pure functions where possible (input dict → output
str/list) so unit tests can exercise the logic without a live
DuckDB. The async wrappers below resolve the database via the
existing ``require_reflection_database()`` helper, falling back to a
test-injected ``db`` argument when one is supplied.
"""

from __future__ import annotations

import base64
import html
import re
from typing import TYPE_CHECKING, Any

from session_buddy.utils.database_tools import require_reflection_database
from session_buddy.utils.error_management import (
    DatabaseUnavailableError,
    _get_logger,
    validate_required,
)
from session_buddy.utils.messages import ToolMessages

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter import ReflectionDatabaseAdapter

_logger = _get_logger()


# ---------------------------------------------------------------------------
# Constants — public for tests
# ---------------------------------------------------------------------------

#: Minimum base64 length (chars) before we flag it. Short ASCII strings
#: that happen to decode cleanly (e.g. "aGk=" from "hi") are too common
#: to flag — a real exfiltration channel is going to be hundreds of chars.
_MIN_BASE64_LENGTH: int = 40

#: Patterns of **Cyrillic** code points that visually overlap ASCII letters
#: and digits. Used by the homoglyph check to spot obfuscated secrets
#: (the OWASP guard's regex patterns can't see across scripts).
_CYRILLIC_HOMOGLYPHS: dict[str, str] = {
    "А": "A",  # А
    "В": "B",  # В
    "С": "C",  # С
    "Е": "E",  # Е
    "Н": "H",  # Н
    "К": "K",  # К
    "М": "M",  # М
    "О": "O",  # О
    "Р": "P",  # Р
    "Т": "T",  # Т
    "Х": "X",  # Х
    "а": "a",  # а
    "е": "e",  # е
    "о": "o",  # о
    "р": "p",  # р
    "с": "c",  # с
    "у": "y",  # у
    "х": "x",  # х
    "і": "i",  # і
    "ј": "j",  # ј
    "һ": "h",  # һ
    "ѕ": "s",  # ѕ
}

#: Heuristic: a token that contains a Cyrillic homoglyph AND at least
#: 8 word-characters (letters/digits/underscore) is suspicious. Short
#: tokens like "а" alone are noise — exfiltration payloads are long.
_HOMOGLYPH_MIN_TOKEN_LEN: int = 8


# ---------------------------------------------------------------------------
# Frontmatter helpers (pure)
# ---------------------------------------------------------------------------


def _yaml_escape(value: Any) -> str:
    """Escape a value for YAML frontmatter output.

    Strategy: use YAML's inline list notation for ``list[str]``, JSON
    strings for everything else (avoiding the rich-but-fragile YAML
    type machinery that would force callers to think about quoting).
    """
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ", ".join(json_quote(str(v)) for v in value) + "]"
    return json_quote(str(value))


def json_quote(value: str) -> str:
    """Quote a string as a JSON string literal."""
    import json

    return json.dumps(value, ensure_ascii=False)


def _render_frontmatter(reflection: dict[str, Any]) -> str:
    """Render the YAML frontmatter block (without delimiters)."""
    fields: list[tuple[str, Any]] = [
        ("id", reflection.get("id")),
        ("tags", reflection.get("tags") or []),
        ("created_at", reflection.get("created_at")),
        ("source_type", reflection.get("source_type")),
        ("project", reflection.get("project")),
    ]
    lines = ["---"]
    for key, value in fields:
        lines.append(f"{key}: {_yaml_escape(value)}")
    lines.append("---")
    return "\n".join(lines)


def _render_markdown_body(reflection: dict[str, Any]) -> str:
    """Render the body section between frontmatter and end-of-document."""
    content = reflection.get("content") or ""
    return f"\n\n{content}\n"


def _wrap_html(markdown_body: str, reflection: dict[str, Any]) -> str:
    """Wrap a Markdown body in a minimal HTML shell.

    The body section is HTML-escaped so the document is safe to render
    in a browser without a Markdown pass. The frontmatter is rendered
    inside a ``<pre>`` block.
    """
    fm = _render_frontmatter(reflection)
    safe_fm = html.escape(fm)
    safe_body = html.escape(markdown_body.lstrip("\n").rstrip())
    title = html.escape(str(reflection.get("id") or "reflection"))
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        f'  <meta charset="utf-8">\n'
        f"  <title>{title}</title>\n"
        "</head>\n"
        "<body>\n"
        f"  <pre>{safe_fm}</pre>\n"
        f"  <pre>{safe_body}</pre>\n"
        "</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# export_markdown — pure function
# ---------------------------------------------------------------------------


def _export_markdown_impl(
    reflection: dict[str, Any],
    *,
    format: str = "md",
) -> str:
    """Render a single reflection as Markdown (or HTML-wrapped Markdown).

    Args:
        reflection: v2-shaped reflection dict. Must contain at least
            ``id`` and ``content``; ``tags``, ``created_at``,
            ``source_type``, and ``project`` are optional and rendered
            into the frontmatter when present.
        format: ``"md"`` (default) emits pure Markdown. ``"html"``
            emits an HTML shell containing the Markdown as
            ``<pre>`` blocks.

    Returns:
        The rendered document. Always a string.

    Raises:
        ValueError: When ``format`` is not one of ``"md"`` / ``"html"``.
    """
    if format not in {"md", "html"}:
        raise ValueError(f"unsupported format: {format!r}; expected 'md' or 'html'")

    fm = _render_frontmatter(reflection)
    body = _render_markdown_body(reflection)

    if format == "md":
        return f"{fm}{body}"

    # format == "html"
    return _wrap_html(fm + body, reflection)


# ---------------------------------------------------------------------------
# lint_memory — pure function
# ---------------------------------------------------------------------------


_HOMOGLYPH_TOKEN_PATTERN: re.Pattern[str] = re.compile(
    "[A-Za-z0-9_Ѐ-ӿ]{" + str(_HOMOGLYPH_MIN_TOKEN_LEN) + ",}"
)


def _iter_long_tokens(content: str) -> list[tuple[int, str]]:
    """Yield ``(start_offset, token)`` for word-tokens >= homoglyph threshold.

    Word boundary is loose (alphanumeric or underscore) — sufficient for
    spotting API-key-shaped and token-shaped payloads where homoglyph
    substitution hides the trigger pattern.
    """
    return [(m.start(), m.group(0)) for m in _HOMOGLYPH_TOKEN_PATTERN.finditer(content)]


def _find_homoglyph_issues(content: str) -> list[dict[str, Any]]:
    """Find Cyrillic-homoglyph false negatives.

    Walks long tokens, flags any that contain at least one Cyrillic
    code point in ``_CYRILLIC_HOMOGLYPHS``. The evidence string names
    the offending character so reviewers can spot it.
    """
    issues: list[dict[str, Any]] = []
    for start, token in _iter_long_tokens(content):
        bad: list[str] = []
        for ch in token:
            if ch in _CYRILLIC_HOMOGLYPHS:
                bad.append(f"{ch!r} (Cyrillic → ASCII {_CYRILLIC_HOMOGLYPHS[ch]!r})")
        if bad:
            issues.append(
                {
                    "kind": "homoglyph",
                    "position": start,
                    "evidence": (
                        f"token {token!r} contains Cyrillic homoglyphs: "
                        + ", ".join(bad)
                    ),
                }
            )
    return issues


_BASE64_RE: re.Pattern[str] = re.compile(
    "[A-Za-z0-9+/]{" + str(_MIN_BASE64_LENGTH) + ",}={0,2}"
)


def _find_base64_issues(content: str) -> list[dict[str, Any]]:
    """Find base64 payloads (>= 40 chars) that decode cleanly.

    A long string of base64 alphabet characters that decodes without
    error is a plausible exfiltration channel — the write-path guard
    only screens for known secret patterns, not encoded versions.
    """
    issues: list[dict[str, Any]] = []
    for m in _BASE64_RE.finditer(content):
        candidate = m.group(0)
        try:
            decoded = base64.b64decode(candidate, validate=True)
        except Exception:  # noqa: BLE001 — b64decode raises on bad padding/charset
            continue
        if not decoded:
            continue
        # Require the decoded bytes to be "interesting" — printable or
        # contain non-ASCII. This rules out runs of base64-looking
        # characters that happen to decode to a single byte repeated.
        if not any(32 <= b < 127 or b >= 128 for b in decoded):
            continue
        issues.append(
            {
                "kind": "base64",
                "position": m.start(),
                "evidence": (
                    f"base64 payload ({len(candidate)} chars) "
                    f"decoded to {len(decoded)} bytes"
                ),
            }
        )
    return issues


def _lint_memory_impl(reflection: dict[str, Any]) -> list[dict[str, Any]]:
    """Lint a reflection for guard false-negatives.

    Returns a list of issue dicts, each with shape:
    ``{"kind": str, "position": int, "evidence": str}``.

    Currently detects:
    - ``homoglyph``: Cyrillic characters inside otherwise long
      word-tokens (a known OWASP-guard blind spot).
    - ``base64``: base64-decodable payloads >= 40 chars.

    Args:
        reflection: v2-shaped reflection dict.

    Returns:
        Sorted-by-position list of issue dicts; ``[]`` when clean.
    """
    content = reflection.get("content") or ""
    if not content:
        return []

    issues: list[dict[str, Any]] = []
    issues.extend(_find_homoglyph_issues(content))
    issues.extend(_find_base64_issues(content))
    issues.sort(key=lambda i: i["position"])
    return issues


# ---------------------------------------------------------------------------
# Async wrappers — DB-bound path
# ---------------------------------------------------------------------------


async def _resolve_reflection(
    reflection_id: str,
    db: ReflectionDatabaseAdapter | None,
) -> dict[str, Any] | None:
    """Resolve a reflection row by id, using ``db`` if provided else the global.

    The optional ``db`` argument exists so unit tests can inject a
    stub without going through ``require_reflection_database()`` (which
    requires a configured Oneiric settings path).
    """
    if db is None:
        try:
            db = await require_reflection_database()
        except DatabaseUnavailableError as e:
            _logger.exception("export_markdown: db unavailable: %s", e)
            return None
    getter = getattr(db, "get_reflection_by_id", None)
    if getter is None:
        return None
    return await getter(reflection_id)


def _format_markdown_result(reflection_id: str, document: str | None) -> str:
    """Format the result string for the export_markdown MCP tool."""
    if document is None:
        return ToolMessages.not_available(
            "Export markdown", f"reflection {reflection_id!r} not found"
        )
    return document


async def export_markdown(
    reflection_id: str,
    *,
    format: str = "md",
    db: ReflectionDatabaseAdapter | None = None,
) -> str:
    """Export a single reflection as a Markdown (or HTML) document.

    Plan 3 Phase 1 Tier 1 Item #3. Output is a self-contained
    document with YAML frontmatter (id, tags, created_at,
    source_type, project) and the reflection body verbatim. Suitable
    for sharing, doc pipelines, or RAG ingestion.

    Args:
        reflection_id: ID of the reflection to export.
        format: ``"md"`` (default) or ``"html"``.
        db: Optional pre-resolved ``ReflectionDatabaseAdapter`` —
            used by tests to inject a stub.

    Returns:
        Markdown (or HTML) document.

    Raises:
        ValueError: When ``reflection_id`` is empty, ``format`` is
            unsupported, or the reflection does not exist in the database.
    """
    if not reflection_id:
        raise ValueError("reflection_id must be a non-empty string")
    if format not in {"md", "html"}:
        raise ValueError(f"unsupported format: {format!r}; expected 'md' or 'html'")

    reflection = await _resolve_reflection(reflection_id, db)
    if reflection is None:
        raise ValueError(f"reflection {reflection_id!r} not found")
    return _export_markdown_impl(reflection, format=format)


async def lint_memory(
    reflection_id: str,
    *,
    db: ReflectionDatabaseAdapter | None = None,
) -> list[dict[str, Any]]:
    """Lint a reflection for OWASP memory-guard false-negatives.

    Plan 3 Phase 1 Tier 1 Item #3. Returns a list of issue dicts
    describing homoglyph / base64 false-negatives — patterns the
    write-path guard doesn't catch (``memory_guard_adapter.py`` only
    screens known secret shapes like ``sk_...`` and JWT literals).

    Args:
        reflection_id: ID of the reflection to lint.
        db: Optional pre-resolved ``ReflectionDatabaseAdapter`` —
            used by tests to inject a stub.

    Returns:
        List of ``{"kind", "position", "evidence"}`` dicts sorted by
        position; empty when clean or when the reflection is missing.
    """
    if not reflection_id:
        return []

    try:
        reflection = await _resolve_reflection(reflection_id, db)
    except DatabaseUnavailableError as e:
        _logger.exception("lint_memory: db unavailable: %s", e)
        return []
    except Exception as e:  # noqa: BLE001 — MCP boundary
        _logger.exception("lint_memory failed for %s: %s", reflection_id, e)
        return []

    if reflection is None:
        return []

    return _lint_memory_impl(reflection)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register_export_tools(mcp: Any) -> None:
    """Register ``export_markdown`` and ``lint_memory`` on the MCP server."""

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def export_markdown(
        reflection_id: str,
        format: str = "md",
    ) -> str:
        """Export a single reflection as a Markdown (or HTML) document.

        Plan 3 Phase 1 Tier 1 Item #3. Output is a self-contained
        document with YAML frontmatter (id, tags, created_at,
        source_type, project) and the reflection body verbatim.

        Args:
            reflection_id: ID of the reflection to export.
            format: ``"md"`` (default) or ``"html"``.
        """
        # Re-validate here so the MCP validator runs before any DB call.
        validate_required(reflection_id, "reflection_id")
        if format not in {"md", "html"}:
            return ToolMessages.validation_error("format", "'md' or 'html'")
        return await _export_markdown_async_wrapper(reflection_id, format)

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def lint_memory(reflection_id: str) -> list[dict[str, Any]]:
        """Lint a reflection for OWASP memory-guard false-negatives.

        Plan 3 Phase 1 Tier 1 Item #3. Detects two patterns the
        write-path guard does not screen for:

        - ``homoglyph`` — Cyrillic characters inside an
          otherwise-ASCII long token (e.g. ``skаbc...``).
        - ``base64`` — base64-decodable payloads >= 40 chars.

        Returns a list of issue dicts sorted by position; ``[]`` when
        the content is clean or the reflection is missing.

        Args:
            reflection_id: ID of the reflection to lint.
        """
        validate_required(reflection_id, "reflection_id")
        return await _lint_memory_async_wrapper(reflection_id)


async def _export_markdown_async_wrapper(reflection_id: str, format: str) -> str:
    """Async body for the registered ``export_markdown`` tool."""
    try:
        reflection = await _resolve_reflection(reflection_id, None)
    except DatabaseUnavailableError as e:
        return ToolMessages.not_available("Export markdown", str(e))
    except Exception as e:  # noqa: BLE001 — MCP boundary
        _logger.exception("export_markdown failed for %s: %s", reflection_id, e)
        return ToolMessages.operation_failed("Export markdown", e)

    if reflection is None:
        return ToolMessages.not_available(
            "Export markdown", f"reflection {reflection_id!r} not found"
        )
    return _format_markdown_result(
        reflection_id, _export_markdown_impl(reflection, format=format)
    )


async def _lint_memory_async_wrapper(
    reflection_id: str,
) -> list[dict[str, Any]]:
    """Async body for the registered ``lint_memory`` tool."""
    try:
        reflection = await _resolve_reflection(reflection_id, None)
    except DatabaseUnavailableError as e:
        _logger.exception("lint_memory: db unavailable: %s", e)
        return []
    except Exception as e:  # noqa: BLE001 — MCP boundary
        _logger.exception("lint_memory failed for %s: %s", reflection_id, e)
        return []
    if reflection is None:
        return []
    return _lint_memory_impl(reflection)
