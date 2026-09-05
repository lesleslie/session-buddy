"""Tests for session_buddy.storage.akosha_sync.

Covers ``HttpSyncMethod`` and ``HybridAkoshaSync``:

**HttpSyncMethod**
- ``__init__``: state file load + DB path construction
- ``_load_sync_state`` / ``_save_sync_state``: filesystem roundtrip with
  corrupt-file tolerance
- ``is_available`` / ``get_method_name``: smoke tests
- ``_serialize_conversation`` / ``_serialize_reflection`` /
  ``_serialize_entity`` / ``_serialize_relationship``: metadata
  construction and None-value stripping
- ``_init_sync_stats`` / ``_build_sync_result``: zero/default shapes
- ``_update_sync_state``: timestamp recorded
- ``_fetch_*`` / ``_sync_*``: with real DuckDB and httpx mocked
- ``_call_mcp_tool``: JSON-RPC result/error/HTTP retry
- ``_batch_upload_memories``: success / partial / retry on HTTPStatusError
- ``sync`` (public): happy path / HTTPStatusError / RequestError / generic

**HybridAkoshaSync**
- ``__init__``: method ordering
- ``_get_method``: by name
- ``sync_memories``: forced method success, auto mode fallback, all-fail
  raises HybridSyncError

The module imports ``httpx2 as httpx``; tests patch ``httpx`` in the
module namespace to avoid touching the real network. ``duckdb`` paths
are seeded in tmp_path so the tests don't read the real DB.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import httpx2 as httpx
import pytest

from session_buddy.storage import akosha_sync
from session_buddy.storage.akosha_sync import (
    HttpSyncMethod,
    HybridAkoshaSync,
)
from session_buddy.storage.akosha_config import AkoshaSyncConfig
from session_buddy.storage.sync_protocol import (
    HTTPSyncError,
    HybridSyncError,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_config(tmp_path: Path) -> AkoshaSyncConfig:
    """Build a config that points DB paths at tmp_path.

    Avoids touching ``~/.claude/data/reflection.duckdb``.
    """
    return AkoshaSyncConfig(
        system_id="test-system",
        cloud_endpoint="",
        upload_timeout_seconds=5,
        upload_on_session_end=True,
        enable_fallback=True,
        force_method="auto",
    )


@pytest.fixture
def http_sync(tmp_config: AkoshaSyncConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HttpSyncMethod:
    """Build an HttpSyncMethod with DB paths redirected to tmp_path.

    Patches the module-level references so the constructor reads tmp DBs.
    """
    reflection_db = tmp_path / "reflection.duckdb"
    knowledge_db = tmp_path / "knowledge_graph.duckdb"
    state_file = tmp_path / "akosha_sync_state.json"

    # Monkeypatch Path.home() to redirect default paths.
    monkeypatch.setattr(
        akosha_sync.Path, "home", lambda: tmp_path
    )

    # Build the instance. The constructor uses Path.home() for both the
    # state file and the DB paths — redirecting Path.home() handles all.
    instance = HttpSyncMethod(tmp_config)
    # Override the DB paths explicitly to be sure.
    instance.reflection_db_path = reflection_db
    instance.knowledge_graph_db_path = knowledge_db
    instance._sync_state_file = state_file
    instance._last_sync_timestamp = {}
    return instance


def _make_config(**overrides) -> AkoshaSyncConfig:
    base = dict(
        system_id="sys",
        cloud_endpoint="",
        upload_timeout_seconds=5,
    )
    base.update(overrides)
    return AkoshaSyncConfig(**base)


def _seed_reflection_db(db_path: Path) -> None:
    """Apply v2 schema and seed a few conversations + reflections."""
    from session_buddy.memory.migration import apply_migrations

    conn = duckdb.connect(str(db_path))
    try:
        apply_migrations(conn)
        # source_type has CHECK constraint restricting to enumerated
        # values; use 'manual' which is always allowed.
        conn.execute(
            "INSERT INTO conversations_v2 "
            "(id, content, category, importance_score, memory_tier, namespace, "
            "timestamp, searchable_content, reasoning, project, session_id, "
            "user_id, source_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "c1", "content 1", "facts", 0.7, "long_term", "default",
                datetime.now(UTC), "search 1", "reasoning 1",
                "proj-a", "sess-1", "user-1", "manual",
            ],
        )
        conn.execute(
            "INSERT INTO conversations_v2 "
            "(id, content, category, importance_score, memory_tier, namespace, "
            "timestamp, searchable_content, reasoning, project, session_id, "
            "user_id, source_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "c2", "content 2", "skills", 0.9, "long_term", "default",
                datetime.now(UTC), "search 2", None,
                None, None, "default", None,
            ],
        )
        # reflections_v2 with TEXT[] tags + embedding.
        # DuckDB accepts array literals via [a, b, c] syntax.
        conn.execute(
            "INSERT INTO reflections_v2 "
            "(id, content, embedding, category, importance_score, "
            "memory_tier, tags, related_entities, timestamp, project, "
            "namespace, access_count, last_accessed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "r1", "reflection 1", None, "context", 0.6, "long_term",
                ["tag1", "tag2"], ["ent_a"], datetime.now(UTC),
                "proj-a", "default", 0, None,
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _seed_kg_db(db_path: Path) -> None:
    """Apply minimal KG schema and seed entities + relationships."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE kg_entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT,
                observations TEXT[],
                properties TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                metadata TEXT,
                embedding TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE kg_relationships (
                id TEXT PRIMARY KEY,
                from_entity TEXT,
                to_entity TEXT,
                relation_type TEXT,
                properties TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                metadata TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO kg_entities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "e1", "alice", "person",
                ["obs1", "obs2"],
                json.dumps({"k": "v"}),
                datetime.now(UTC),
                datetime.now(UTC),
                json.dumps({"m": "n"}),
                None,
            ],
        )
        conn.execute(
            "INSERT INTO kg_relationships VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "rel1", "alice", "python", "uses",
                json.dumps({"weight": "0.8"}),
                datetime.now(UTC),
                datetime.now(UTC),
                json.dumps({}),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _make_response(status_code: int = 200, json_payload: dict | None = None) -> MagicMock:
    """Build a MagicMock httpx.Response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_payload or {}
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=response,
        )
        if status_code >= 400
        else lambda: None,
    )
    return response


# ---------------------------------------------------------------------------
# HttpSyncMethod — init + state
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_loads_empty_state_when_file_missing(
        self, http_sync: HttpSyncMethod
    ) -> None:
        # No state file → empty dict.
        assert http_sync._last_sync_timestamp == {}

    def test_init_loads_existing_state(
        self, http_sync: HttpSyncMethod
    ) -> None:
        # Write a state file, then re-instantiate.
        http_sync._sync_state_file.parent.mkdir(parents=True, exist_ok=True)
        http_sync._sync_state_file.write_text(
            json.dumps({"conversations": "2026-01-01T00:00:00+00:00"})
        )
        # Reset the in-memory state and reload.
        http_sync._last_sync_timestamp = {}
        http_sync._load_sync_state()
        assert http_sync._last_sync_timestamp == {
            "conversations": "2026-01-01T00:00:00+00:00"
        }

    def test_init_handles_corrupt_state_file(
        self, http_sync: HttpSyncMethod
    ) -> None:
        http_sync._sync_state_file.parent.mkdir(parents=True, exist_ok=True)
        http_sync._sync_state_file.write_text("not valid json {")
        http_sync._last_sync_timestamp = {"stale": "value"}
        http_sync._load_sync_state()
        assert http_sync._last_sync_timestamp == {}

    def test_init_handles_oserror_on_load(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        # Force _sync_state_file.exists() to True, then open() to raise.
        monkeypatch.setattr(Path, "exists", lambda self: True)

        def boom(self, *args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(Path, "open", boom)
        http_sync._load_sync_state()
        assert http_sync._last_sync_timestamp == {}


class TestSaveSyncState:
    def test_save_writes_json(self, http_sync: HttpSyncMethod) -> None:
        http_sync._last_sync_timestamp = {"k": "v"}
        http_sync._save_sync_state()
        assert json.loads(http_sync._sync_state_file.read_text()) == {"k": "v"}

    def test_save_handles_oserror(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        def boom(self, *args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(Path, "open", boom)
        # Should log warning but not raise.
        http_sync._save_sync_state()

    def test_save_creates_parent_dirs(
        self, http_sync: HttpSyncMethod, tmp_path: Path
    ) -> None:
        nested = tmp_path / "deep" / "nested" / "state.json"
        http_sync._sync_state_file = nested
        http_sync._last_sync_timestamp = {"x": 1}
        http_sync._save_sync_state()
        assert nested.exists()


class TestIsAvailable:
    def test_returns_false_when_akosha_not_reachable(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        def boom_get(*args, **kwargs):
            raise httpx.HTTPError("connection refused")

        monkeypatch.setattr(httpx, "get", boom_get)
        assert http_sync.is_available() is False

    def test_returns_true_for_2xx(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        response = MagicMock()
        response.status_code = 200
        monkeypatch.setattr(httpx, "get", lambda *a, **k: response)
        assert http_sync.is_available() is True

    def test_returns_false_for_5xx(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        response = MagicMock()
        response.status_code = 500
        monkeypatch.setattr(httpx, "get", lambda *a, **k: response)
        assert http_sync.is_available() is False


class TestGetMethodName:
    def test_returns_http(self, http_sync: HttpSyncMethod) -> None:
        assert http_sync.get_method_name() == "http"


# ---------------------------------------------------------------------------
# HttpSyncMethod — serializers
# ---------------------------------------------------------------------------


class TestSerializeConversation:
    def test_basic_fields(self, http_sync: HttpSyncMethod) -> None:
        conv = {
            "id": "c1",
            "content": "hello",
            "reasoning": "because",
            "category": "facts",
            "subcategory": "general",
            "importance_score": 0.7,
            "memory_tier": "long_term",
            "source_type": "test",
            "project": "proj-a",
            "namespace": "ns",
            "session_id": "sess",
            "user_id": "user",
            "timestamp": datetime(2026, 1, 1),
            "embedding": [0.1, 0.2],
        }
        result = http_sync._serialize_conversation(conv)

        assert result["memory_id"] == "c1"
        assert "hello" in result["text"]
        assert "Reasoning: because" in result["text"]
        assert result["embedding"] == [0.1, 0.2]
        assert result["metadata"]["source"] == "test-system"
        assert result["metadata"]["original_id"] == "c1"
        assert result["metadata"]["type"] == "conversation"
        assert result["metadata"]["category"] == "facts"
        assert result["metadata"]["created_at"] == "2026-01-01T00:00:00"

    def test_handles_missing_optional_fields(self, http_sync: HttpSyncMethod) -> None:
        conv = {
            "id": "c1",
            "content": "hello",
            "timestamp": "not-a-datetime",  # string passes through
        }
        result = http_sync._serialize_conversation(conv)
        # None values are stripped from metadata.
        assert "subcategory" not in result["metadata"]
        assert "source_type" not in result["metadata"]
        assert "project" not in result["metadata"]
        assert "session_id" not in result["metadata"]
        assert result["metadata"]["created_at"] == "not-a-datetime"
        # No reasoning → text contains only content.
        assert result["text"] == "hello"

    def test_handles_datetime_timestamp(self, http_sync: HttpSyncMethod) -> None:
        conv = {
            "id": "c1",
            "content": "x",
            "timestamp": datetime(2026, 6, 1, 12, 0, 0),
        }
        result = http_sync._serialize_conversation(conv)
        assert result["metadata"]["created_at"] == "2026-06-01T12:00:00"


class TestSerializeReflection:
    def test_basic_fields(self, http_sync: HttpSyncMethod) -> None:
        reflection = {
            "id": "r1",
            "content": "reflection content",
            "embedding": [0.5],
            "category": "context",
            "importance_score": 0.4,
            "memory_tier": "long_term",
            "tags": ["a", "b"],
            "related_entities": ["e1"],
            "project": "proj",
            "namespace": "ns",
            "timestamp": datetime(2026, 1, 1),
        }
        result = http_sync._serialize_reflection(reflection)
        assert result["reflection_id"] == "r1"
        assert result["content"] == "reflection content"
        assert result["metadata"]["tags"] == ["a", "b"]
        assert result["metadata"]["category"] == "context"
        assert result["metadata"]["created_at"] == "2026-01-01T00:00:00"

    def test_default_tags_and_related(self, http_sync: HttpSyncMethod) -> None:
        reflection = {
            "id": "r1",
            "content": "x",
            "timestamp": "raw-string",
        }
        result = http_sync._serialize_reflection(reflection)
        assert result["metadata"]["tags"] == []
        assert result["metadata"]["related_entities"] == []


class TestSerializeEntity:
    def test_basic_fields(self, http_sync: HttpSyncMethod) -> None:
        entity = {
            "id": "e1",
            "name": "alice",
            "entity_type": "person",
            "observations": ["obs1"],
            "properties": {"custom": "v"},
            "metadata": {"m": "n"},
            "created_at": datetime(2026, 1, 1),
        }
        result = http_sync._serialize_entity(entity)
        assert result["name"] == "alice"
        assert result["entity_type"] == "person"
        assert result["properties"]["source_system"] == "test-system"
        assert result["properties"]["original_id"] == "e1"
        assert result["properties"]["custom"] == "v"  # merged from entity props
        assert result["metadata"] == {"m": "n"}

    def test_string_created_at(self, http_sync: HttpSyncMethod) -> None:
        entity = {
            "id": "e1",
            "name": "alice",
            "entity_type": "person",
            "observations": [],
            "properties": {},
            "metadata": {},
            "created_at": "raw",
        }
        result = http_sync._serialize_entity(entity)
        assert result["properties"]["created_at"] == "raw"


class TestSerializeRelationship:
    def test_basic_fields(self, http_sync: HttpSyncMethod) -> None:
        rel = {
            "id": "rel1",
            "from_entity": "alice",
            "to_entity": "python",
            "relation_type": "uses",
            "properties": {"weight": 0.8},
            "metadata": {},
            "created_at": datetime(2026, 1, 1),
        }
        result = http_sync._serialize_relationship(rel)
        assert result["from_entity"] == "alice"
        assert result["to_entity"] == "python"
        assert result["relation_type"] == "uses"
        assert result["properties"]["source_system"] == "test-system"
        assert result["properties"]["original_id"] == "rel1"
        assert result["properties"]["weight"] == 0.8


# ---------------------------------------------------------------------------
# HttpSyncMethod — stats helpers
# ---------------------------------------------------------------------------


class TestSyncStatsHelpers:
    def test_init_sync_stats(self, http_sync: HttpSyncMethod) -> None:
        stats = http_sync._init_sync_stats()
        assert stats == {
            "memories_uploaded": 0,
            "reflections_uploaded": 0,
            "entities_uploaded": 0,
            "relationships_uploaded": 0,
            "bytes_transferred": 0,
            "errors": [],
        }

    def test_build_sync_result_no_errors(self, http_sync: HttpSyncMethod) -> None:
        stats = http_sync._init_sync_stats()
        stats["memories_uploaded"] = 5
        result = http_sync._build_sync_result(stats, 1.5)
        assert result["method"] == "http"
        assert result["success"] is True
        assert result["memories_uploaded"] == 5
        assert result["duration_seconds"] == 1.5
        assert result["errors"] is None  # empty list → None

    def test_build_sync_result_with_errors(self, http_sync: HttpSyncMethod) -> None:
        stats = http_sync._init_sync_stats()
        stats["errors"] = [{"x": "y"}]
        result = http_sync._build_sync_result(stats, 0.1)
        assert result["errors"] == [{"x": "y"}]

    def test_update_sync_state_sets_timestamp(
        self, http_sync: HttpSyncMethod
    ) -> None:
        http_sync._update_sync_state()
        assert "last_sync" in http_sync._last_sync_timestamp
        # The timestamp is parseable.
        datetime.fromisoformat(http_sync._last_sync_timestamp["last_sync"])


# ---------------------------------------------------------------------------
# HttpSyncMethod — _fetch_*
# ---------------------------------------------------------------------------


class TestFetchConversations:
    @pytest.mark.asyncio
    async def test_returns_empty_when_db_missing(
        self, http_sync: HttpSyncMethod
    ) -> None:
        # http_sync points reflection_db_path at a tmp_path file that
        # doesn't exist.
        result = await http_sync._fetch_conversations(
            incremental=True, batch_size=10
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_rows_when_db_present(
        self, http_sync: HttpSyncMethod
    ) -> None:
        _seed_reflection_db(http_sync.reflection_db_path)
        result = await http_sync._fetch_conversations(
            incremental=True, batch_size=10
        )
        assert len(result) == 2
        ids = sorted(r["id"] for r in result)
        assert ids == ["c1", "c2"]

    @pytest.mark.asyncio
    async def test_incremental_filters_by_timestamp(
        self, http_sync: HttpSyncMethod
    ) -> None:
        _seed_reflection_db(http_sync.reflection_db_path)
        # Set last_sync to now+1min so nothing matches.
        http_sync._last_sync_timestamp["conversations"] = (
            datetime.now(UTC) + timedelta(minutes=1)
        ).isoformat()
        result = await http_sync._fetch_conversations(
            incremental=True, batch_size=10
        )
        assert result == []


class TestFetchReflections:
    @pytest.mark.asyncio
    async def test_returns_empty_when_db_missing(
        self, http_sync: HttpSyncMethod
    ) -> None:
        result = await http_sync._fetch_reflections(
            incremental=True, batch_size=10
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_rows_when_db_present(
        self, http_sync: HttpSyncMethod
    ) -> None:
        _seed_reflection_db(http_sync.reflection_db_path)
        result = await http_sync._fetch_reflections(
            incremental=True, batch_size=10
        )
        assert len(result) == 1
        assert result[0]["id"] == "r1"
        assert result[0]["tags"] == ["tag1", "tag2"]


class TestFetchEntities:
    @pytest.mark.asyncio
    async def test_returns_empty_when_db_missing(
        self, http_sync: HttpSyncMethod
    ) -> None:
        result = await http_sync._fetch_entities(
            incremental=True, batch_size=10
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_rows_when_db_present(
        self, http_sync: HttpSyncMethod
    ) -> None:
        _seed_kg_db(http_sync.knowledge_graph_db_path)
        result = await http_sync._fetch_entities(
            incremental=True, batch_size=10
        )
        assert len(result) == 1
        assert result[0]["id"] == "e1"
        assert result[0]["observations"] == ["obs1", "obs2"]
        assert result[0]["properties"] == {"k": "v"}


class TestFetchRelationships:
    @pytest.mark.asyncio
    async def test_returns_empty_when_db_missing(
        self, http_sync: HttpSyncMethod
    ) -> None:
        result = await http_sync._fetch_relationships(
            incremental=True, batch_size=10
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_rows_when_db_present(
        self, http_sync: HttpSyncMethod
    ) -> None:
        _seed_kg_db(http_sync.knowledge_graph_db_path)
        result = await http_sync._fetch_relationships(
            incremental=True, batch_size=10
        )
        assert len(result) == 1
        assert result[0]["id"] == "rel1"
        assert result[0]["relation_type"] == "uses"


# ---------------------------------------------------------------------------
# HttpSyncMethod — _call_mcp_tool
# ---------------------------------------------------------------------------


class TestCallMcpTool:
    @pytest.mark.asyncio
    async def test_returns_result_payload(self, http_sync: HttpSyncMethod) -> None:
        client = AsyncMock()
        client.post.return_value = _make_response(
            200, {"result": {"status": "completed", "stored": 3}}
        )
        result = await http_sync._call_mcp_tool(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            tool_name="batch_store_memories",
            arguments={"memories": []},
        )
        assert result == {"status": "completed", "stored": 3}

    @pytest.mark.asyncio
    async def test_returns_error_payload(self, http_sync: HttpSyncMethod) -> None:
        client = AsyncMock()
        client.post.return_value = _make_response(
            200, {"error": {"message": "rate limit"}}
        )
        result = await http_sync._call_mcp_tool(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            tool_name="batch_store_memories",
            arguments={},
        )
        assert result == {"status": "failed", "error": {"message": "rate limit"}}

    @pytest.mark.asyncio
    async def test_returns_raw_dict_when_no_result_or_error(
        self, http_sync: HttpSyncMethod
    ) -> None:
        client = AsyncMock()
        client.post.return_value = _make_response(200, {"custom": "field"})
        result = await http_sync._call_mcp_tool(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            tool_name="x",
            arguments={},
        )
        assert result == {"custom": "field"}

    @pytest.mark.asyncio
    async def test_handles_non_dict_response(
        self, http_sync: HttpSyncMethod
    ) -> None:
        client = AsyncMock()
        # response.json() returns a non-dict (e.g. a bare list).
        client.post.return_value = _make_response(200, ["not", "a", "dict"])
        result = await http_sync._call_mcp_tool(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            tool_name="x",
            arguments={},
        )
        # Falls back to empty dict.
        assert result == {}

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_on_http_error(
        self, http_sync: HttpSyncMethod
    ) -> None:
        client = AsyncMock()
        client.post.return_value = _make_response(500)
        with pytest.raises(httpx.HTTPStatusError):
            await http_sync._call_mcp_tool(
                client=client,
                akosha_url="http://localhost:8682/mcp",
                tool_name="x",
                arguments={},
            )
        # MAX_RETRIES attempts.
        assert client.post.call_count == akosha_sync.MAX_RETRIES


# ---------------------------------------------------------------------------
# HttpSyncMethod — _batch_upload_memories
# ---------------------------------------------------------------------------


class TestBatchUploadMemories:
    @pytest.mark.asyncio
    async def test_empty_memories_returns_zero(
        self, http_sync: HttpSyncMethod
    ) -> None:
        client = AsyncMock()
        result = await http_sync._batch_upload_memories(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            memories=[],
            batch_size=10,
        )
        assert result == {"count": 0, "bytes": 0, "errors": []}

    @pytest.mark.asyncio
    async def test_happy_path(
        self, http_sync: HttpSyncMethod
    ) -> None:
        client = AsyncMock()
        client.post.return_value = _make_response(
            200, {"result": {"status": "completed", "stored": 2}}
        )
        memories = [
            {"memory_id": "m1", "text": "x"},
            {"memory_id": "m2", "text": "y"},
        ]
        result = await http_sync._batch_upload_memories(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            memories=memories,
            batch_size=10,
        )
        assert result["count"] == 2
        assert result["bytes"] > 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_partial_success_collects_errors(
        self, http_sync: HttpSyncMethod
    ) -> None:
        client = AsyncMock()
        client.post.return_value = _make_response(
            200,
            {
                "result": {
                    "status": "partial",
                    "stored": 1,
                    "errors": [{"id": "m2", "error": "bad"}],
                }
            },
        )
        memories = [
            {"memory_id": "m1", "text": "x"},
            {"memory_id": "m2", "text": "y"},
        ]
        result = await http_sync._batch_upload_memories(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            memories=memories,
            batch_size=10,
        )
        assert result["count"] == 1
        assert result["errors"] == [{"id": "m2", "error": "bad"}]

    @pytest.mark.asyncio
    async def test_complete_failure_stops_retrying(
        self, http_sync: HttpSyncMethod
    ) -> None:
        client = AsyncMock()
        client.post.return_value = _make_response(
            200, {"result": {"status": "failed", "error": "boom"}}
        )
        memories = [{"memory_id": "m1", "text": "x"}]
        result = await http_sync._batch_upload_memories(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            memories=memories,
            batch_size=10,
        )
        assert result["count"] == 0
        assert len(result["errors"]) == 1
        assert "boom" in result["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_http_error_retries_then_gives_up(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        client = AsyncMock()
        client.post.return_value = _make_response(500)
        # Patch asyncio.sleep to skip the backoff delay.
        async def fast_sleep(seconds):
            return None

        monkeypatch.setattr(akosha_sync.asyncio, "sleep", fast_sleep)

        memories = [{"memory_id": "m1", "text": "x"}]
        result = await http_sync._batch_upload_memories(
            client=client,
            akosha_url="http://localhost:8682/mcp",
            memories=memories,
            batch_size=10,
        )
        # _batch_upload_memories retries MAX_RETRIES times internally;
        # each retry itself goes through _call_mcp_tool which retries 3
        # times — so the total call count is MAX_RETRIES * MAX_RETRIES.
        # What matters: errors are recorded, count is 0.
        assert result["count"] == 0
        assert len(result["errors"]) == 1
        assert "500" in result["errors"][0]["error"]


# ---------------------------------------------------------------------------
# HttpSyncMethod — public sync
# ---------------------------------------------------------------------------


def _patched_client_method(return_value):
    """Build an async context manager that yields an AsyncMock with the given .post() return."""
    client = AsyncMock()
    client.post.return_value = return_value
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, client


class TestSync:
    @pytest.mark.asyncio
    async def test_happy_path_no_memories(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        # Empty DB → no memories → sync returns success with 0 counts.
        result = await http_sync.sync()
        assert result["method"] == "http"
        assert result["success"] is True
        assert result["memories_uploaded"] == 0
        assert result["errors"] is None

    @pytest.mark.asyncio
    async def test_happy_path_with_memories(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        _seed_reflection_db(http_sync.reflection_db_path)
        # Mock httpx.AsyncClient to return success for all batch calls.
        client = AsyncMock()
        client.post.return_value = _make_response(
            200, {"result": {"status": "completed", "stored": 2}}
        )
        monkeypatch.setattr(
            akosha_sync.httpx, "AsyncClient",
            lambda **kwargs: _patched_client_method(
                client.post.return_value
            )[0],
        )
        # Monkeypatch the AsyncClient class so the cm pattern works.
        class FakeAsyncClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return client

            async def __aexit__(self, *args):
                return None

        monkeypatch.setattr(akosha_sync.httpx, "AsyncClient", FakeAsyncClient)

        result = await http_sync.sync()
        assert result["success"] is True
        assert result["memories_uploaded"] == 2

    @pytest.mark.asyncio
    async def test_records_http_error_in_result(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        # Production behavior: when _batch_upload_memories exhausts its
        # retries on HTTPStatusError, it records the error in the
        # result dict and DOES NOT re-raise. The public sync() returns
        # success=False-equivalent (errors populated, count=0).
        _seed_reflection_db(http_sync.reflection_db_path)
        client = AsyncMock()
        client.post.return_value = _make_response(500)

        class FakeAsyncClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return client

            async def __aexit__(self, *args):
                return None

        monkeypatch.setattr(akosha_sync.httpx, "AsyncClient", FakeAsyncClient)

        # Skip backoff sleeps between retries.
        async def fast_sleep(seconds):
            return None

        monkeypatch.setattr(akosha_sync.asyncio, "sleep", fast_sleep)

        # The call returns; sync does NOT raise HTTPSyncError for this
        # path because batch_upload catches it internally.
        result = await http_sync.sync()
        assert result["memories_uploaded"] == 0
        assert result["errors"] is not None
        assert len(result["errors"]) >= 1

    @pytest.mark.asyncio
    async def test_records_request_error_in_result(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        # RequestError: batch_upload catches httpx.HTTPError (parent
        # class) and records it without re-raising.
        _seed_reflection_db(http_sync.reflection_db_path)

        class FakeAsyncClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                client = AsyncMock()
                client.post.side_effect = httpx.RequestError("boom")
                return client

            async def __aexit__(self, *args):
                return None

        monkeypatch.setattr(akosha_sync.httpx, "AsyncClient", FakeAsyncClient)

        async def fast_sleep(seconds):
            return None

        monkeypatch.setattr(akosha_sync.asyncio, "sleep", fast_sleep)

        result = await http_sync.sync()
        assert result["memories_uploaded"] == 0
        assert result["errors"] is not None
        assert len(result["errors"]) >= 1

    @pytest.mark.asyncio
    async def test_raises_httpsyncerror_on_generic_exception(
        self, http_sync: HttpSyncMethod, monkeypatch
    ) -> None:
        _seed_reflection_db(http_sync.reflection_db_path)

        class FakeAsyncClient:
            def __init__(self, **kwargs):
                raise RuntimeError("init failed")

        monkeypatch.setattr(akosha_sync.httpx, "AsyncClient", FakeAsyncClient)

        with pytest.raises(HTTPSyncError):
            await http_sync.sync()


# ---------------------------------------------------------------------------
# HybridAkoshaSync
# ---------------------------------------------------------------------------


class TestHybridInit:
    def test_methods_are_in_priority_order(self, tmp_config: AkoshaSyncConfig) -> None:
        hybrid = HybridAkoshaSync(tmp_config)
        names = [m.get_method_name() for m in hybrid.methods]
        assert names[0] == "cloud"
        assert "http" in names


class TestGetMethod:
    def test_returns_method_by_name(self, tmp_config: AkoshaSyncConfig) -> None:
        hybrid = HybridAkoshaSync(tmp_config)
        assert hybrid._get_method("http").get_method_name() == "http"

    def test_returns_none_for_unknown(self, tmp_config: AkoshaSyncConfig) -> None:
        hybrid = HybridAkoshaSync(tmp_config)
        assert hybrid._get_method("nope") is None


class TestSyncMemoriesForced:
    @pytest.mark.asyncio
    async def test_forced_http_method_invokes(
        self, tmp_config: AkoshaSyncConfig, monkeypatch
    ) -> None:
        # Replace methods with a single http mock.
        http_mock = AsyncMock()
        http_mock.get_method_name = lambda: "http"
        http_mock.is_available = lambda: True
        http_mock.sync = AsyncMock(
            return_value={"method": "http", "success": True}
        )
        hybrid = HybridAkoshaSync(tmp_config)
        hybrid.methods = [http_mock]

        result = await hybrid.sync_memories(force_method="http")
        assert result["method"] == "http"
        http_mock.sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_forced_unknown_method_raises(
        self, tmp_config: AkoshaSyncConfig
    ) -> None:
        hybrid = HybridAkoshaSync(tmp_config)
        with pytest.raises(HybridSyncError):
            await hybrid.sync_memories(force_method="nonexistent")


class TestSyncMemoriesAuto:
    @pytest.mark.asyncio
    async def test_first_available_method_succeeds(
        self, tmp_config: AkoshaSyncConfig
    ) -> None:
        first = AsyncMock()
        first.get_method_name = lambda: "first"
        first.is_available = lambda: True
        first.sync = AsyncMock(
            return_value={"method": "first", "success": True}
        )
        # Second method should not even be tried.
        second = AsyncMock()
        second.get_method_name = lambda: "second"
        second.is_available = lambda: True
        second.sync = AsyncMock()

        hybrid = HybridAkoshaSync(tmp_config)
        hybrid.methods = [first, second]
        result = await hybrid.sync_memories()
        assert result["method"] == "first"
        second.sync.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_when_first_unavailable(
        self, tmp_config: AkoshaSyncConfig
    ) -> None:
        first = AsyncMock()
        first.get_method_name = lambda: "first"
        first.is_available = lambda: False
        first.sync = AsyncMock()

        second = AsyncMock()
        second.get_method_name = lambda: "second"
        second.is_available = lambda: True
        second.sync = AsyncMock(
            return_value={"method": "second", "success": True}
        )

        hybrid = HybridAkoshaSync(tmp_config)
        hybrid.methods = [first, second]
        result = await hybrid.sync_memories()
        assert result["method"] == "second"

    @pytest.mark.asyncio
    async def test_falls_back_when_first_fails(
        self, tmp_config: AkoshaSyncConfig
    ) -> None:
        first = AsyncMock()
        first.get_method_name = lambda: "first"
        first.is_available = lambda: True
        first.sync = AsyncMock(
            return_value={"method": "first", "success": False, "error": "nope"}
        )

        second = AsyncMock()
        second.get_method_name = lambda: "second"
        second.is_available = lambda: True
        second.sync = AsyncMock(
            return_value={"method": "second", "success": True}
        )

        hybrid = HybridAkoshaSync(tmp_config)
        hybrid.methods = [first, second]
        result = await hybrid.sync_memories()
        assert result["method"] == "second"

    @pytest.mark.asyncio
    async def test_falls_back_when_first_raises(
        self, tmp_config: AkoshaSyncConfig
    ) -> None:
        first = AsyncMock()
        first.get_method_name = lambda: "first"
        first.is_available = lambda: True
        first.sync = AsyncMock(side_effect=RuntimeError("crashed"))

        second = AsyncMock()
        second.get_method_name = lambda: "second"
        second.is_available = lambda: True
        second.sync = AsyncMock(
            return_value={"method": "second", "success": True}
        )

        hybrid = HybridAkoshaSync(tmp_config)
        hybrid.methods = [first, second]
        result = await hybrid.sync_memories()
        assert result["method"] == "second"

    @pytest.mark.asyncio
    async def test_raises_hybrid_error_when_all_fail(
        self, tmp_config: AkoshaSyncConfig
    ) -> None:
        first = AsyncMock()
        first.get_method_name = lambda: "first"
        first.is_available = lambda: True
        first.sync = AsyncMock(side_effect=RuntimeError("first failed"))

        second = AsyncMock()
        second.get_method_name = lambda: "second"
        second.is_available = lambda: True
        second.sync = AsyncMock(
            return_value={"method": "second", "success": False,
                          "error": "second failed"}
        )

        hybrid = HybridAkoshaSync(tmp_config)
        hybrid.methods = [first, second]
        with pytest.raises(HybridSyncError) as exc_info:
            await hybrid.sync_memories()
        assert len(exc_info.value.errors) == 2

    @pytest.mark.asyncio
    async def test_skips_unavailable_methods(
        self, tmp_config: AkoshaSyncConfig
    ) -> None:
        # Both unavailable → HybridSyncError with 0 errors (no attempts).
        first = AsyncMock()
        first.get_method_name = lambda: "first"
        first.is_available = lambda: False
        first.sync = AsyncMock()

        hybrid = HybridAkoshaSync(tmp_config)
        hybrid.methods = [first]
        with pytest.raises(HybridSyncError):
            await hybrid.sync_memories()


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


def test_module_exports() -> None:
    assert "HttpSyncMethod" in akosha_sync.__all__
    assert "HybridAkoshaSync" in akosha_sync.__all__
