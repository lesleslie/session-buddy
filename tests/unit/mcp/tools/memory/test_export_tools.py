#!/usr/bin/env python3
"""Unit tests for export + lint MCP tools.

Plan 3 Phase 1 Tier 1 Item #3: ``export_markdown`` and ``lint_memory``.

TDD discipline: 5 tests total per task spec.
"""

from __future__ import annotations

from typing import Any


def _reflection(
    reflection_id: str,
    content: str,
    *,
    tags: list[str] | None = None,
    source_type: str | None = None,
) -> dict[str, Any]:
    """Build a v2-shaped reflection dict for use in fixture data."""
    return {
        "id": reflection_id,
        "content": content,
        "tags": tags or [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "source_type": source_type,
    }


class _StubDB:
    """Stub reflection db that resolves a single reflection by id."""

    def __init__(self, refl: dict[str, Any] | None) -> None:
        self._refl = refl

    async def get_reflection_by_id(self, _id: str) -> dict[str, Any] | None:
        return self._refl


def test_export_markdown_returns_yaml_frontmatter() -> None:
    """export_markdown emits a YAML frontmatter block with the required fields."""
    import asyncio

    from session_buddy.mcp.tools.memory.export_tools import export_markdown

    refl = _reflection(
        "test-id",
        "Reflection body",
        tags=["alpha", "beta"],
        source_type="claude_code",
    )

    md = asyncio.run(
        export_markdown(reflection_id="test-id", db=_StubDB(refl))  # type: ignore[arg-type]
    )

    assert isinstance(md, str)
    assert md.startswith("---\n")
    assert "\n---\n" in md
    head = md.split("\n---\n", 1)[0]
    assert "id:" in head and "test-id" in head
    assert "tags:" in head
    assert "created_at:" in head
    assert "source_type:" in head


def test_export_markdown_body_contains_content() -> None:
    """The body section of the export contains the reflection's content."""
    import asyncio

    from session_buddy.mcp.tools.memory.export_tools import export_markdown

    refl = _reflection("abc", "This is the body line we want to see verbatim.")

    md = asyncio.run(
        export_markdown(reflection_id="abc", db=_StubDB(refl))  # type: ignore[arg-type]
    )

    assert "This is the body line we want to see verbatim." in md


def test_export_markdown_unknown_id_raises() -> None:
    """export_markdown raises ValueError when the reflection does not exist."""
    import asyncio

    import pytest

    from session_buddy.mcp.tools.memory.export_tools import export_markdown

    with pytest.raises(ValueError):
        asyncio.run(
            export_markdown(
                reflection_id="nonexistent", db=_StubDB(None)  # type: ignore[arg-type]
            )
        )


def test_lint_memory_clean_content_returns_empty() -> None:
    """lint_memory returns an empty list when content has no anomalies."""
    import asyncio

    from session_buddy.mcp.tools.memory.export_tools import lint_memory

    refl = _reflection("clean", "Always validate input before persisting it.")

    issues = asyncio.run(
        lint_memory(reflection_id="clean", db=_StubDB(refl))  # type: ignore[arg-type]
    )

    assert issues == []


def test_lint_memory_detects_homoglyph() -> None:
    """lint_memory flags content with a Cyrillic homoglyph in a long token."""
    import asyncio

    from session_buddy.mcp.tools.memory.export_tools import lint_memory

    # "skаbc1234567890XYZdefghij" contains a Cyrillic 'а' (U+0430) inside
    # an otherwise-ASCII long token — a known false-negative of the write guard.
    content = "API key looks like skаbc1234567890XYZdefghij — guard missed it"
    refl = _reflection("homo", content)

    issues = asyncio.run(
        lint_memory(reflection_id="homo", db=_StubDB(refl))  # type: ignore[arg-type]
    )

    assert isinstance(issues, list)
    assert len(issues) >= 1
    hit = next((i for i in issues if i.get("kind") == "homoglyph"), None)
    assert hit is not None, f"No homoglyph issue in {issues}"
