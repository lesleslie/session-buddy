"""Claude Code transcript ingester.

Claude Code writes conversation transcripts to::

    ~/.claude/projects/<encoded-path>/<session-uuid>.jsonl

This ingester reads each ``.jsonl`` file line by line, parses the
``user``/``assistant`` records, redacts secrets, and writes them to
``conversations_v2`` with provenance columns wired up
(``source_type='claude_code'``, ``turn_parent_id`` linking the assistant
turn to its parent user turn, ``category='claude_turn'``,
``memory_tier='working'``).

Records with a ``type`` other than ``user`` or ``assistant`` (e.g.
``queue-operation`` raw thinking blocks) are dropped.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from session_buddy.ingesters.redaction import (
    ALLOWED_METADATA_KEYS,
    MAX_REDACTION_BYTES,
    REDACTED_MARKER,
    RedactionSizeError,
    redact,
    redact_metadata,
)

if TYPE_CHECKING:
    from session_buddy.adapters.reflection_adapter_oneiric import (
        ReflectionDatabaseAdapterOneiric,
    )

#: The two record types we ingest from a Claude Code transcript.
_INGESTABLE_TYPES: frozenset[str] = frozenset({"user", "assistant"})

#: Provenance tag written to ``conversations_v2.source_type``.
SOURCE_TYPE: str = "claude_code"

#: Memori-inspired category for transcript turns.
_CATEGORY: str = "claude_turn"

#: Working memory tier — short-lived, gets promoted by Conscious Agent.
_MEMORY_TIER: str = "working"


class ClaudeCodeTranscriptIngester:
    """Ingest Claude Code JSONL transcripts into ``conversations_v2``."""

    def __init__(self, db: ReflectionDatabaseAdapterOneiric) -> None:
        """Store the database adapter; nothing else is held in state."""
        self._db = db

    async def ingest_file(
        self,
        path: Path,
        since_timestamp: str | None = None,
    ) -> int:
        """Parse one ``.jsonl`` file and write records to v2.

        Args:
            path: Path to the JSONL transcript.
            since_timestamp: Optional ISO 8601 lower bound; records with
                ``timestamp < since_timestamp`` are skipped (inclusive).

        Returns:
            Number of records successfully written to v2.

        """
        ingested = 0
        for line in _iter_jsonl_lines(path):
            record = _safe_parse(line)
            if record is None:
                continue
            if not _should_ingest(record, since_timestamp):
                continue
            content = _extract_content(record)
            if content is None:
                continue
            if len(content) > MAX_REDACTION_BYTES:
                # Skip oversized payloads — they are almost always
                # accidental binary blobs dumped into a transcript.
                continue
            try:
                redacted = redact(content)
            except RedactionSizeError:
                continue
            metadata = _build_metadata(record, redacted)
            # ``REDACTED_MARKER`` is set so a redaction actually happened.
            if REDACTED_MARKER in redacted:
                metadata["redaction_applied"] = True
            turn_parent = (
                self._resolve_turn_parent(record) if _is_assistant(record) else None
            )
            row_id = await self._db.store_conversation(
                content=redacted,
                metadata=metadata,
                source_type=SOURCE_TYPE,
                turn_parent_id=turn_parent,
                category=_CATEGORY,
                memory_tier=_MEMORY_TIER,
            )
            record_uuid = record.get("uuid")
            if isinstance(record_uuid, str):
                self._track_parent(record_uuid, row_id)
            ingested += 1
        return ingested

    async def ingest_directory(
        self,
        encoded_path: Path,
        since_timestamp: str | None = None,
    ) -> int:
        """Glob ``*.jsonl`` under ``encoded_path`` and ingest each.

        Returns the total number of records ingested across all files.
        """
        total = 0
        for jsonl in sorted(encoded_path.glob("*.jsonl")):
            total += await self.ingest_file(jsonl, since_timestamp=since_timestamp)
        return total

    # -- internal helpers -------------------------------------------------

    def _resolve_turn_parent(self, record: dict[str, Any]) -> str | None:
        """Look up the in-memory parent-id map for an assistant turn.

        Falls back to ``None`` if the parent was not seen in this run
        (e.g. partial transcripts).
        """
        parent_uuid = record.get("parentUuid")
        if not isinstance(parent_uuid, str):
            return None
        return self._parent_id_by_uuid.get(parent_uuid)

    def _track_parent(self, parent_uuid: str, row_id: str) -> None:
        """Record the v2 id produced for ``parent_uuid``."""
        self._parent_id_by_uuid[parent_uuid] = row_id

    # Initialised lazily so we don't shadow the param in __init__.
    _parent_id_by_uuid: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Module-level helpers (free functions keep the class small and testable)
# ---------------------------------------------------------------------------


def _iter_jsonl_lines(path: Path) -> list[str]:
    """Return non-empty lines from ``path`` (split, do not strip newlines)."""
    with path.open("r", encoding="utf-8") as fh:
        return [ln for ln in fh.read().splitlines() if ln.strip()]


def _safe_parse(line: str) -> dict[str, Any] | None:
    """Parse a single JSONL record; return ``None`` on any error."""
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _should_ingest(record: dict[str, Any], since_timestamp: str | None) -> bool:
    """True when ``record`` is user/assistant and meets the time filter."""
    if record.get("type") not in _INGESTABLE_TYPES:
        return False
    if since_timestamp is None:
        return True
    ts = record.get("timestamp")
    if not isinstance(ts, str):
        return False
    return ts >= since_timestamp


def _is_assistant(record: dict[str, Any]) -> bool:
    """True when ``record`` is an assistant turn."""
    return record.get("type") == "assistant"


def _extract_content(record: dict[str, Any]) -> str | None:
    """Pull the textual content from a record's ``message`` block."""
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def _build_metadata(record: dict[str, Any], redacted_content: str) -> dict[str, Any]:
    """Build the allowlisted metadata dict for a single record."""
    metadata: dict[str, Any] = {}
    session_id = record.get("sessionId")
    if isinstance(session_id, str):
        metadata["source_session"] = session_id
    parent_uuid = record.get("parentUuid")
    if isinstance(parent_uuid, str):
        metadata["parent_uuid_chain"] = [parent_uuid]
    tool_name = _extract_tool_name(record)
    if tool_name is not None:
        metadata["tool_names"] = [tool_name]
        metadata["tool_counts"] = {tool_name: 1}
    model = _extract_model(record)
    if model is not None:
        metadata["model"] = model
    token_usage = _extract_token_usage(record)
    if token_usage is not None:
        metadata["token_usage"] = token_usage
    metadata["extracted_at"] = datetime.now(UTC).isoformat()
    # Filter through the standard allowlist to keep the schema honest.
    return redact_metadata(metadata, set(ALLOWED_METADATA_KEYS))


def _extract_tool_name(record: dict[str, Any]) -> str | None:
    """Return the tool name if the record has a ``toolUse`` block."""
    tool_use = record.get("toolUse")
    if isinstance(tool_use, dict):
        name = tool_use.get("name")
        if isinstance(name, str):
            return name
    return None


def _extract_model(record: dict[str, Any]) -> str | None:
    """Model may live at the top level or under ``message``."""
    top = record.get("model")
    if isinstance(top, str):
        return top
    message = record.get("message")
    if isinstance(message, dict):
        nested = message.get("model")
        if isinstance(nested, str):
            return nested
    return None


def _extract_token_usage(record: dict[str, Any]) -> dict[str, int] | None:
    """Return a small ``{input_tokens, output_tokens}`` dict or ``None``."""
    usage = record.get("usage")
    if not isinstance(usage, dict):
        return None
    out: dict[str, int] = {}
    in_tok = usage.get("input_tokens")
    out_tok = usage.get("output_tokens")
    if isinstance(in_tok, int):
        out["input_tokens"] = in_tok
    if isinstance(out_tok, int):
        out["output_tokens"] = out_tok
    return out or None


__all__ = ["ClaudeCodeTranscriptIngester", "SOURCE_TYPE"]
