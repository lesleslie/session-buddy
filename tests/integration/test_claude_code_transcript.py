"""Integration tests for the Claude Code transcript ingester.

Phase 1 Feature #1: LLM Conversation Capture. Claude Code writes transcripts
to ``~/.claude/projects/<encoded-path>/<session-uuid>.jsonl``. Each
``user``/``assistant`` record should be parsed, redacted, and written to
``conversations_v2`` with provenance columns wired up.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from session_buddy.ingesters.claude_code_transcript import (
    ClaudeCodeTranscriptIngester,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _v2_rows(db: object) -> list[dict[str, object]]:
    """Return all rows from ``conversations_v2`` as dicts."""
    rows = db.conn.execute(  # type: ignore[attr-defined]
        "SELECT id, content, category, memory_tier, source_type, "
        "turn_parent_id, metadata, timestamp FROM conversations_v2"
    ).fetchall()
    columns = [
        "id",
        "content",
        "category",
        "memory_tier",
        "source_type",
        "turn_parent_id",
        "metadata",
        "timestamp",
    ]
    return [dict(zip(columns, row, strict=False)) for row in rows]


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> Path:
    """Write ``records`` to ``path`` as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")
    return path


# ---------------------------------------------------------------------------
# Test 1: user + assistant records land in v2 with lineage
# ---------------------------------------------------------------------------


async def test_ingest_user_record_creates_v2_row(
    fast_temp_db: AsyncGenerator,
    tmp_path: Path,
) -> None:
    """A user+assistant turn pair should land as two v2 rows with lineage."""
    db = fast_temp_db
    transcript = tmp_path / "sess-abc.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "uuid": "u-1",
                "parentUuid": None,
                "sessionId": "sess-abc",
                "timestamp": "2026-06-01T10:00:00Z",
                "message": {
                    "content": "What is the capital of France?",
                    "model": "claude-opus-4-8",
                },
                "toolUse": None,
            },
            {
                "type": "assistant",
                "uuid": "a-1",
                "parentUuid": "u-1",
                "sessionId": "sess-abc",
                "timestamp": "2026-06-01T10:00:05Z",
                "message": {"content": "Paris is the capital of France."},
                "model": "claude-opus-4-8",
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
        ],
    )

    ingester = ClaudeCodeTranscriptIngester(db=db)
    ingested = await ingester.ingest_file(path=transcript)

    assert ingested == 2, f"expected 2 rows ingested, got {ingested}"

    rows = _v2_rows(db)
    assert len(rows) == 2, f"expected 2 rows in conversations_v2, got {len(rows)}"

    # First row: user turn
    user_row = rows[0]
    assert user_row["content"] == "What is the capital of France?"
    assert user_row["category"] == "claude_turn"
    assert user_row["memory_tier"] == "working"
    assert user_row["source_type"] == "claude_code"
    # The metadata JSON is stored as a string; parse to inspect.
    user_meta = json.loads(str(user_row["metadata"]))
    assert user_meta["source_session"] == "sess-abc"

    # Second row: assistant turn with lineage
    assistant_row = rows[1]
    assert assistant_row["content"] == "Paris is the capital of France."
    assert assistant_row["category"] == "claude_turn"
    assert assistant_row["turn_parent_id"] == user_row["id"], (
        f"expected turn_parent_id={user_row['id']!r}, "
        f"got {assistant_row['turn_parent_id']!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: redaction runs before write
# ---------------------------------------------------------------------------


async def test_ingest_redacts_secrets_in_prompts(
    fast_temp_db: AsyncGenerator,
    tmp_path: Path,
) -> None:
    """A secret-shaped string in a user prompt must be redacted before write."""
    db = fast_temp_db
    transcript = tmp_path / f"sess-redact-{uuid.uuid4().hex}.jsonl"
    # Build a synthetic GitHub-PAT-shaped placeholder. The body is a
    # repeated single character so it cannot be mistaken for a leaked
    # credential by secret scanners, but is still long enough (36 chars)
    # to match the redact() regex ``ghp_[A-Za-z0-9]{36}``.
    placeholder_token = "ghp_" + ("a" * 36)
    prompt_with_secret = (
        f"Here is a token for the deploy job: {placeholder_token}, please use it"
    )
    _write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "uuid": "u-redact-1",
                "parentUuid": None,
                "sessionId": "sess-redact",
                "timestamp": "2026-06-01T11:00:00Z",
                "message": {
                    "content": prompt_with_secret,
                    "model": "claude-opus-4-8",
                },
                "toolUse": None,
            },
        ],
    )

    ingester = ClaudeCodeTranscriptIngester(db=db)
    await ingester.ingest_file(path=transcript)

    rows = _v2_rows(db)
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    content = str(rows[0]["content"])
    assert "ghp_" not in content, (
        f"GitHub PAT prefix leaked through ingestion: {content!r}"
    )
    assert "[REDACTED]" in content, (
        f"expected [REDACTED] marker in content, got: {content!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: metadata fields are extracted into the row metadata
# ---------------------------------------------------------------------------


async def test_ingest_extracts_metadata_fields(
    fast_temp_db: AsyncGenerator,
    tmp_path: Path,
) -> None:
    """Tool use, model, and token usage should appear in row metadata."""
    db = fast_temp_db
    transcript = tmp_path / f"sess-meta-{uuid.uuid4().hex}.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "uuid": "u-meta-1",
                "parentUuid": None,
                "sessionId": "sess-meta",
                "timestamp": "2026-06-01T12:00:00Z",
                "message": {
                    "content": "Read /etc/hosts for me",
                    "model": "claude-opus-4-8",
                },
                "toolUse": None,
            },
            {
                "type": "assistant",
                "uuid": "a-meta-1",
                "parentUuid": "u-meta-1",
                "sessionId": "sess-meta",
                "timestamp": "2026-06-01T12:00:05Z",
                "message": {"content": "Reading now."},
                "model": "claude-opus-4-8",
                "toolUse": {"name": "Read", "input": {"path": "/etc/hosts"}},
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        ],
    )

    ingester = ClaudeCodeTranscriptIngester(db=db)
    await ingester.ingest_file(path=transcript)

    rows = _v2_rows(db)
    # Find the assistant row (the one with toolUse)
    assistant_row = next(
        r for r in rows if str(r["content"]) == "Reading now."
    )
    meta = json.loads(str(assistant_row["metadata"]))
    assert "tool_names" in meta, f"expected tool_names in metadata, got {meta!r}"
    assert "Read" in meta["tool_names"], (
        f"expected 'Read' in tool_names, got {meta['tool_names']!r}"
    )
    assert meta["model"] == "claude-opus-4-8", (
        f"expected model='claude-opus-4-8', got {meta.get('model')!r}"
    )
    assert meta["token_usage"] == {
        "input_tokens": 100,
        "output_tokens": 50,
    }, f"unexpected token_usage: {meta.get('token_usage')!r}"


# ---------------------------------------------------------------------------
# Test 4: non user/assistant records are skipped
# ---------------------------------------------------------------------------


async def test_ingest_skips_non_user_assistant_records(
    fast_temp_db: AsyncGenerator,
    tmp_path: Path,
) -> None:
    """queue-operation (and other non user/assistant) records are dropped."""
    db = fast_temp_db
    transcript = tmp_path / f"sess-skip-{uuid.uuid4().hex}.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "timestamp": "2026-06-01T13:00:00Z",
                "content": "raw thinking block content here",
            },
            {
                "type": "user",
                "uuid": "u-skip-1",
                "parentUuid": None,
                "sessionId": "sess-skip",
                "timestamp": "2026-06-01T13:00:05Z",
                "message": {
                    "content": "Hello world",
                    "model": "claude-opus-4-8",
                },
                "toolUse": None,
            },
        ],
    )

    ingester = ClaudeCodeTranscriptIngester(db=db)
    ingested = await ingester.ingest_file(path=transcript)

    assert ingested == 1, f"expected 1 row ingested (queue-op dropped), got {ingested}"
    rows = _v2_rows(db)
    assert len(rows) == 1, f"expected 1 v2 row, got {len(rows)}"
    assert rows[0]["content"] == "Hello world"
    # The dropped record's content must not have leaked through.
    all_content = " ".join(str(r["content"]) for r in rows)
    assert "raw thinking block" not in all_content, (
        f"raw thinking content leaked: {all_content!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: since_timestamp filters out older records
# ---------------------------------------------------------------------------


async def test_ingest_incremental_since_timestamp(
    fast_temp_db: AsyncGenerator,
    tmp_path: Path,
) -> None:
    """Records with timestamp < since_timestamp are skipped."""
    db = fast_temp_db
    transcript = tmp_path / f"sess-inc-{uuid.uuid4().hex}.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "uuid": "u-inc-1",
                "parentUuid": None,
                "sessionId": "sess-inc",
                "timestamp": "2026-06-01T10:00:00Z",
                "message": {
                    "content": "first",
                    "model": "claude-opus-4-8",
                },
                "toolUse": None,
            },
            {
                "type": "user",
                "uuid": "u-inc-2",
                "parentUuid": None,
                "sessionId": "sess-inc",
                "timestamp": "2026-06-01T10:05:00Z",
                "message": {
                    "content": "second",
                    "model": "claude-opus-4-8",
                },
                "toolUse": None,
            },
            {
                "type": "user",
                "uuid": "u-inc-3",
                "parentUuid": None,
                "sessionId": "sess-inc",
                "timestamp": "2026-06-01T10:10:00Z",
                "message": {
                    "content": "third",
                    "model": "claude-opus-4-8",
                },
                "toolUse": None,
            },
        ],
    )

    ingester = ClaudeCodeTranscriptIngester(db=db)
    ingested = await ingester.ingest_file(
        path=transcript,
        since_timestamp="2026-06-01T10:05:00Z",
    )

    assert ingested == 2, (
        f"expected 2 rows (>= 10:05), got {ingested}"
    )
    rows = _v2_rows(db)
    assert len(rows) == 2
    contents = sorted(str(r["content"]) for r in rows)
    assert contents == ["second", "third"], (
        f"unexpected contents: {contents!r}"
    )
