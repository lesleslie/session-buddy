"""Unit tests for session_buddy/ingesters/claude_code_transcript.py.

Covers:
- Module-level helpers: _iter_jsonl_lines, _safe_parse, _should_ingest,
  _is_assistant, _extract_content, _build_metadata, _extract_tool_name,
  _extract_model, _extract_token_usage
- ClaudeCodeTranscriptIngester.ingest_file: writes records, propagates
  provenance columns, links assistant turns to user turns, skips disallowed
  types / oversized payloads / malformed lines.
- ClaudeCodeTranscriptIngester.ingest_directory: glob over *.jsonl.
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.ingesters import claude_code_transcript as module
from session_buddy.ingesters.claude_code_transcript import (
    SOURCE_TYPE,
    ClaudeCodeTranscriptIngester,
    _build_metadata,
    _extract_content,
    _extract_model,
    _extract_token_usage,
    _extract_tool_name,
    _is_assistant,
    _iter_jsonl_lines,
    _safe_parse,
    _should_ingest,
)


# ============================================================================
# Module-level helpers
# ============================================================================


class TestIterJsonlLines:
    def test_reads_non_empty_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "sample.jsonl"
        p.write_text('{"a":1}\n{"b":2}\n\n   \n{"c":3}\n')
        assert _iter_jsonl_lines(p) == ['{"a":1}', '{"b":2}', '{"c":3}']

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        assert _iter_jsonl_lines(p) == []


class TestSafeParse:
    def test_parses_dict(self) -> None:
        result = _safe_parse('{"type":"user","x":1}')
        assert result == {"type": "user", "x": 1}

    def test_returns_none_on_invalid_json(self) -> None:
        assert _safe_parse("not-json {") is None

    def test_returns_none_when_not_dict(self) -> None:
        assert _safe_parse("[1, 2, 3]") is None
        assert _safe_parse('"a string"') is None
        assert _safe_parse("42") is None


class TestShouldIngest:
    def test_accepts_user_record_without_time_filter(self) -> None:
        assert _should_ingest({"type": "user"}, None) is True

    def test_accepts_assistant_record_without_time_filter(self) -> None:
        assert _should_ingest({"type": "assistant"}, None) is True

    def test_rejects_other_types(self) -> None:
        assert _should_ingest({"type": "queue-operation"}, None) is False
        assert _should_ingest({"type": "file-history-snapshot"}, None) is False
        assert _should_ingest({}, None) is False

    def test_since_timestamp_filter(self) -> None:
        # Inclusive lower bound
        assert _should_ingest(
            {"type": "user", "timestamp": "2026-01-01T00:00:00Z"},
            "2026-01-01T00:00:00Z",
        ) is True
        assert _should_ingest(
            {"type": "user", "timestamp": "2026-01-01T00:00:01Z"},
            "2026-01-01T00:00:00Z",
        ) is True
        assert _should_ingest(
            {"type": "user", "timestamp": "2025-12-31T23:59:59Z"},
            "2026-01-01T00:00:00Z",
        ) is False

    def test_since_timestamp_requires_string_timestamp(self) -> None:
        assert _should_ingest(
            {"type": "user", "timestamp": 1234},
            "2026-01-01T00:00:00Z",
        ) is False
        assert _should_ingest({"type": "user"}, "2026-01-01T00:00:00Z") is False


class TestIsAssistant:
    def test_returns_true_for_assistant_type(self) -> None:
        assert _is_assistant({"type": "assistant"}) is True

    def test_returns_false_for_other_types(self) -> None:
        assert _is_assistant({"type": "user"}) is False
        assert _is_assistant({"type": "tool"}) is False
        assert _is_assistant({}) is False


class TestExtractContent:
    def test_extracts_string_content(self) -> None:
        assert _extract_content({"message": {"content": "hello"}}) == "hello"

    def test_returns_none_when_message_missing(self) -> None:
        assert _extract_content({}) is None

    def test_returns_none_when_content_not_string(self) -> None:
        assert _extract_content({"message": {"content": [1, 2, 3]}}) is None
        assert _extract_content({"message": {"content": None}}) is None
        assert _extract_content({"message": "not a dict"}) is None


class TestExtractToolName:
    def test_returns_tool_name_from_tool_use_block(self) -> None:
        assert _extract_tool_name({"toolUse": {"name": "Bash"}}) == "Bash"

    def test_returns_none_when_no_tool_use(self) -> None:
        assert _extract_tool_name({}) is None
        assert _extract_tool_name({"toolUse": {"name": 42}}) is None
        assert _extract_tool_name({"toolUse": "not a dict"}) is None


class TestExtractModel:
    def test_top_level_model(self) -> None:
        assert _extract_model({"model": "claude-opus-4-7"}) == "claude-opus-4-7"

    def test_nested_message_model(self) -> None:
        assert (
            _extract_model({"message": {"model": "claude-sonnet-4-6"}})
            == "claude-sonnet-4-6"
        )

    def test_top_level_takes_precedence(self) -> None:
        result = _extract_model(
            {"model": "outer", "message": {"model": "inner"}}
        )
        assert result == "outer"

    def test_returns_none_when_missing(self) -> None:
        assert _extract_model({}) is None
        assert _extract_model({"model": 123}) is None
        assert _extract_model({"message": {"model": 99}}) is None


class TestExtractTokenUsage:
    def test_extracts_both_tokens(self) -> None:
        assert _extract_token_usage(
            {"usage": {"input_tokens": 100, "output_tokens": 50}}
        ) == {"input_tokens": 100, "output_tokens": 50}

    def test_extracts_only_input(self) -> None:
        assert _extract_token_usage(
            {"usage": {"input_tokens": 100}}
        ) == {"input_tokens": 100}

    def test_extracts_only_output(self) -> None:
        assert _extract_token_usage(
            {"usage": {"output_tokens": 50}}
        ) == {"output_tokens": 50}

    def test_returns_none_when_missing_or_empty(self) -> None:
        assert _extract_token_usage({}) is None
        assert _extract_token_usage({"usage": {}}) is None
        assert _extract_token_usage({"usage": "not dict"}) is None
        assert _extract_token_usage({"usage": {"input_tokens": "x"}}) is None


class TestBuildMetadata:
    def test_includes_only_known_keys(self) -> None:
        record = {
            "type": "user",
            "sessionId": "abc-123",
            "parentUuid": "parent-1",
            "toolUse": {"name": "Read"},
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "junk_field_should_be_dropped": "ignore me",
        }

        metadata = _build_metadata(record, "redacted content")

        # Allowed keys only
        assert set(metadata.keys()) <= {
            "source_session",
            "parent_uuid_chain",
            "tool_names",
            "tool_counts",
            "model",
            "token_usage",
            "extracted_at",
            "redaction_applied",
            "project",
        }
        assert metadata["source_session"] == "abc-123"
        assert metadata["parent_uuid_chain"] == ["parent-1"]
        assert metadata["tool_names"] == ["Read"]
        assert metadata["tool_counts"] == {"Read": 1}
        assert metadata["model"] == "claude-opus-4-7"
        assert metadata["token_usage"] == {
            "input_tokens": 10,
            "output_tokens": 5,
        }
        assert "extracted_at" in metadata

    def test_omits_missing_keys(self) -> None:
        record = {"type": "user", "message": {"content": "hi"}}
        metadata = _build_metadata(record, "hi")
        # source_session, parent_uuid_chain, tool_names, tool_counts,
        # model, token_usage should all be absent.
        for key in (
            "source_session",
            "parent_uuid_chain",
            "tool_names",
            "tool_counts",
            "model",
            "token_usage",
        ):
            assert key not in metadata
        assert "extracted_at" in metadata


# ============================================================================
# Ingester — happy path & edge cases
# ============================================================================


def _write_record(record: dict[str, Any]) -> str:
    return json.dumps(record)


def _make_record(
    type_: str = "user",
    content: str = "hello",
    parent_uuid: str | None = None,
    record_uuid: str | None = None,
    timestamp: str = "2026-01-01T00:00:00Z",
    **extra: Any,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": type_,
        "message": {"content": content},
        "timestamp": timestamp,
    }
    if parent_uuid:
        record["parentUuid"] = parent_uuid
    if record_uuid:
        record["uuid"] = record_uuid
    record.update(extra)
    return record


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock for ReflectionDatabaseAdapterOneiric."""
    db = MagicMock()
    counter = {"n": 0}

    async def _store(**kwargs: Any) -> str:
        counter["n"] += 1
        return f"row-{counter['n']:04d}-{kwargs['content'][:8]}"

    db.store_conversation = AsyncMock(side_effect=_store)
    return db


@pytest.mark.asyncio
class TestIngestFile:
    async def test_writes_user_record_with_provenance(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"
        record = _make_record(type_="user", content="first turn")
        path.write_text(_write_record(record))

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        n = await ingester.ingest_file(path)

        assert n == 1
        mock_db.store_conversation.assert_awaited_once()
        kwargs = mock_db.store_conversation.await_args.kwargs
        assert kwargs["content"] == "first turn"
        assert kwargs["source_type"] == SOURCE_TYPE == "claude_code"
        assert kwargs["turn_parent_id"] is None  # user turns have no parent
        assert kwargs["category"] == "claude_turn"
        assert kwargs["memory_tier"] == "working"
        # no sessionId was provided, so the key is dropped entirely
        assert "source_session" not in kwargs["metadata"]
        assert "extracted_at" in kwargs["metadata"]

    async def test_links_assistant_to_user_via_parent_uuid(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"

        user = _make_record(
            type_="user",
            content="ask",
            record_uuid="user-uuid-1",
        )
        assistant = _make_record(
            type_="assistant",
            content="answer",
            parent_uuid="user-uuid-1",
            record_uuid="assistant-uuid-1",
        )
        path.write_text(_write_record(user) + "\n" + _write_record(assistant) + "\n")

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        n = await ingester.ingest_file(path)

        assert n == 2

        # First call (user) — no turn parent
        first_call = mock_db.store_conversation.await_args_list[0]
        first_kwargs = first_call.kwargs
        assert first_kwargs["turn_parent_id"] is None

        # Second call (assistant) — must reference the user row id
        second_kwargs = mock_db.store_conversation.await_args_list[1].kwargs
        # Reconstruct the user row id from the mock side effect:
        # the first call content is "ask" → row id was "row-0001-ask"
        user_row_id = f"row-0001-{first_kwargs['content'][:8]}"
        assert second_kwargs["turn_parent_id"] == user_row_id
        # And the assistant record kept its own uuid chain in metadata
        assert second_kwargs["metadata"]["parent_uuid_chain"] == ["user-uuid-1"]

    async def test_assistant_with_unknown_parent_uuid_gets_none(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"
        record = _make_record(
            type_="assistant",
            content="orphan",
            parent_uuid="never-seen-user",
            record_uuid="assistant-uuid",
        )
        path.write_text(_write_record(record))

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        await ingester.ingest_file(path)

        kwargs = mock_db.store_conversation.await_args.kwargs
        assert kwargs["turn_parent_id"] is None

    async def test_skips_unknown_record_types(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"
        path.write_text(
            _write_record(_make_record(type_="queue-operation"))
            + "\n"
            + _write_record(_make_record(type_="user", content="keep me"))
            + "\n"
        )

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        n = await ingester.ingest_file(path)

        assert n == 1
        # only the user record made it through
        kwargs = mock_db.store_conversation.await_args.kwargs
        assert kwargs["content"] == "keep me"

    async def test_skips_malformed_jsonl_lines(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"
        path.write_text(
            "not valid json\n"
            + _write_record(_make_record(type_="user", content="survive"))
            + "\n"
            + "another bad line\n"
            + '{"not_a_dict": true}\n'
        )

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        n = await ingester.ingest_file(path)

        assert n == 1
        kwargs = mock_db.store_conversation.await_args.kwargs
        assert kwargs["content"] == "survive"

    async def test_skips_records_without_content(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"
        path.write_text(
            _write_record({"type": "user", "timestamp": "2026-01-01T00:00:00Z"})
            + "\n"
            + _write_record(
                _make_record(type_="user", content="has content")
            )
            + "\n"
        )

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        n = await ingester.ingest_file(path)

        assert n == 1

    async def test_respects_since_timestamp(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"
        path.write_text(
            _write_record(
                _make_record(
                    type_="user",
                    content="old",
                    timestamp="2025-12-31T00:00:00Z",
                )
            )
            + "\n"
            + _write_record(
                _make_record(
                    type_="user",
                    content="new",
                    timestamp="2026-01-02T00:00:00Z",
                )
            )
            + "\n"
        )

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        n = await ingester.ingest_file(path, since_timestamp="2026-01-01T00:00:00Z")

        assert n == 1
        kwargs = mock_db.store_conversation.await_args.kwargs
        assert kwargs["content"] == "new"

    async def test_metadata_marks_redaction_applied(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"
        # The redact() function replaces AWS keys with [REDACTED].
        path.write_text(
            _write_record(
                _make_record(
                    type_="user",
                    content="my key is AKIAABCDEFGHIJKLMNOP",
                )
            )
        )

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        await ingester.ingest_file(path)

        kwargs = mock_db.store_conversation.await_args.kwargs
        assert "AKIA" not in kwargs["content"]
        assert "[REDACTED]" in kwargs["content"]
        assert kwargs["metadata"]["redaction_applied"] is True

    async def test_no_redaction_flag_when_content_clean(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        path = tmp_path / "transcript.jsonl"
        path.write_text(_write_record(_make_record(type_="user", content="clean")))

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        await ingester.ingest_file(path)

        kwargs = mock_db.store_conversation.await_args.kwargs
        assert kwargs["metadata"].get("redaction_applied") is None or (
            kwargs["metadata"].get("redaction_applied") is False
        )


@pytest.mark.asyncio
class TestIngestDirectory:
    async def test_globs_jsonl_files(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        (tmp_path / "a.jsonl").write_text(
            _write_record(_make_record(type_="user", content="a1"))
        )
        (tmp_path / "b.jsonl").write_text(
            _write_record(_make_record(type_="user", content="b1"))
            + "\n"
            + _write_record(_make_record(type_="user", content="b2"))
        )
        # non-jsonl must be ignored
        (tmp_path / "ignore.txt").write_text("ignore")

        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        n = await ingester.ingest_directory(tmp_path)

        assert n == 3

    async def test_empty_directory_returns_zero(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        n = await ingester.ingest_directory(tmp_path)
        assert n == 0
        mock_db.store_conversation.assert_not_called()


# ============================================================================
# Sanity: module exports + SOURCE_TYPE constant
# ============================================================================


class TestModuleSurface:
    def test_exports(self) -> None:
        assert hasattr(module, "ClaudeCodeTranscriptIngester")
        assert hasattr(module, "SOURCE_TYPE")
        assert module.SOURCE_TYPE == "claude_code"

    def test_private_helpers_present(self) -> None:
        # Guard against accidental rename during refactors
        for name in (
            "_iter_jsonl_lines",
            "_safe_parse",
            "_should_ingest",
            "_is_assistant",
            "_extract_content",
            "_build_metadata",
            "_extract_tool_name",
            "_extract_model",
            "_extract_token_usage",
        ):
            assert hasattr(module, name), f"missing helper: {name}"


# ============================================================================
# Sanity: ensure _resolve_turn_parent / _track_parent are exposed on instance
# ============================================================================


class TestParentTracking:
    @pytest.mark.asyncio
    async def test_track_parent_persists_uuid(
        self, mock_db: MagicMock
    ) -> None:
        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        ingester._track_parent("parent-uuid", "row-id-123")
        assert ingester._parent_id_by_uuid["parent-uuid"] == "row-id-123"

        # Resolve via the same instance
        record = {"parentUuid": "parent-uuid"}
        assert ingester._resolve_turn_parent(record) == "row-id-123"

    def test_resolve_turn_parent_returns_none_for_missing_uuid(
        self, mock_db: MagicMock
    ) -> None:
        ingester = ClaudeCodeTranscriptIngester(db=mock_db)
        assert ingester._resolve_turn_parent({}) is None
        assert ingester._resolve_turn_parent({"parentUuid": "never-seen"}) is None
        assert ingester._resolve_turn_parent({"parentUuid": 1234}) is None
