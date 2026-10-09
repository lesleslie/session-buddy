"""Wire-shape payload extractor for FastMCP tool results.

Local copy of the FastMCP ``CallToolResult`` -> payload extractor. The
shape of a tool call result is documented in
``~/.claude/projects/-Users-les-Projects-mahavishnu/memory/fastmcp-call-tool-returns-calltoolresult.md``:
``result.content[0].text`` is the JSON-encoded string payload the
tool returned.

Per the bodai-search-infrastructure-fix plan §5 (REQ-012), the
regression tests assert on the wire-shape envelope — i.e. the JSON
``result.content[0].text`` — NOT on the in-process return value. This
helper centralises the parsing so individual test files do not
duplicate the iteration over ``result.content``.

The module deliberately does NOT depend on any other Bodai package
(no ``mahavishnu``, no ``akosha``, no ``session_buddy`` outside the
TYPE_CHECKING block) so a regression test can import it from any
worktree without dragging in unrelated transitive deps.

Example:
    >>> result = await client.call_tool("quick_search", {"query": "python"})
    >>> assert not result.is_error
    >>> payload = _extract_tool_payload(result)
    >>> assert "Found" in payload  # or "No results" — wire-shape check
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.tools import CallToolResult  # type: ignore[import-not-found]


def _extract_tool_payload(result: Any) -> str:
    """Return the ``content[0].text`` string from a FastMCP tool result.

    FastMCP returns a ``CallToolResult`` (or duck-typed equivalent)
    with:
      - ``is_error`` (bool): whether the tool raised
      - ``content``: list of content blocks; the first one is a
        ``TextContent`` with ``.text`` set to a JSON-encoded payload

    The MCP wrapper around the session-buddy handlers returns ``str``
    (the human-formatted output, not a JSON object), so the typical
    consumer can use this helper as a string-returning accessor.

    Args:
        result: The tool call result returned by ``Client.call_tool``.

    Returns:
        The decoded text payload (already a string for the
        session-buddy memory tools).

    Raises:
        AssertionError: if the result has no content blocks (which
            would indicate a malformed wire-shape).
    """
    content = getattr(result, "content", None)
    assert content, (
        f"Tool result has no .content attribute or empty content: {result!r}"
    )
    first = content[0]
    text = getattr(first, "text", None)
    if text is None:
        # Some FastMCP versions return dicts instead of objects. Fall
        # back gracefully — the session-buddy handlers always emit
        # string payloads so we don't need the full JSON-decode branch
        # in this codebase, but keep it for forward-compat.
        if isinstance(first, dict):
            text = first.get("text")
        if text is None:
            msg = f"Tool result content[0] has no .text: {first!r}"
            raise AssertionError(msg)
    # The session-buddy handlers return JSON-encoded strings (the
    # FastMCP wrapper serializes them). Decode so the test can
    # inspect the inner string cleanly.
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError):
        decoded = text
    return decoded if isinstance(decoded, str) else text