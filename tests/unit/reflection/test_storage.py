"""Unit tests for session_buddy/reflection/storage.py.

Covers the CRUD operations exposed by storage.py:

- ``store_conversation`` / ``get_conversation`` round-trip
- ``store_reflection`` / ``get_reflection`` round-trip
- ``store_code_graph`` / ``get_code_graph`` / ``list_code_graphs`` round-trip
- ``has_get_conn`` Protocol helper
- ``_encode_text_for_db`` / ``_decode_text_from_db`` round-trip
- ``_serialize_metadata`` / ``_parse_metadata`` round-trip
- ``_table_columns`` table introspection

Tests use the existing ``duckdb_connection`` fixture (defined in
``tests/conftest.py``) and initialize the schema via
``session_buddy.reflection.schema.initialize_schema`` to mirror production.
"""

from __future__ import annotations

from typing import Any

import pytest

from session_buddy.reflection.schema import initialize_schema
from session_buddy.reflection.storage import (
    _decode_text_from_db,
    _encode_text_for_db,
    _parse_metadata,
    _serialize_metadata,
    _table_columns,
    get_code_graph,
    get_conversation,
    get_reflection,
    has_get_conn,
    list_code_graphs,
    store_code_graph,
    store_conversation,
    store_reflection,
)


class FakeDb:
    """Stand-in object exposing ``_get_conn`` for Protocol coverage tests."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def _get_conn(self) -> Any:
        return self._conn


class TestEncodeDecodeText:
    """Text codec round-trips for plain ASCII and surrogate-pair Unicode."""

    def test_plain_ascii_passes_through(self) -> None:
        assert _encode_text_for_db("hello world") == "hello world"

    def test_decode_plain_text_returns_input(self) -> None:
        encoded = _encode_text_for_db("plain")
        assert _decode_text_from_db(encoded) == "plain"

    def test_decode_non_surrogate_prefix_returns_input(self) -> None:
        # Anything lacking the magic marker is treated as plain text.
        assert _decode_text_from_db("no marker here") == "no marker here"


class TestSerializeParseMetadata:
    """Metadata JSON round-trips and degrades gracefully on bad input."""

    def test_none_metadata_serializes_to_none(self) -> None:
        assert _serialize_metadata(None) is None
        assert _serialize_metadata({}) is None

    def test_round_trip_dict(self) -> None:
        payload = {"project": "test", "count": 3}
        serialized = _serialize_metadata(payload)
        assert serialized is not None
        assert _parse_metadata(serialized) == payload

    def test_parse_none_returns_empty_dict(self) -> None:
        assert _parse_metadata(None) == {}

    def test_parse_empty_string_returns_empty_dict(self) -> None:
        assert _parse_metadata("") == {}

    def test_parse_invalid_json_returns_empty_dict(self) -> None:
        # Logger warning logged; result falls back to empty dict.
        assert _parse_metadata("{not json") == {}


class TestTableColumns:
    """``_table_columns`` reflects ``PRAGMA table_info``."""

    def test_returns_known_columns(self, duckdb_connection: Any) -> None:
        duckdb_connection.execute(
            "CREATE TABLE widgets (id VARCHAR, value INTEGER)"
        )
        cols = _table_columns(duckdb_connection, "widgets")
        assert cols == {"id", "value"}

    def test_missing_table_returns_empty_set(
        self, duckdb_connection: Any
    ) -> None:
        assert _table_columns(duckdb_connection, "no_such_table") == set()


class TestHasGetConn:
    """``has_get_conn`` Protocol predicate."""

    def test_returns_true_when_method_present(
        self, duckdb_connection: Any
    ) -> None:
        wrapper = FakeDb(duckdb_connection)
        assert has_get_conn(wrapper) is True

    def test_returns_false_when_method_missing(self) -> None:
        assert has_get_conn(object()) is False


class TestStoreConversation:
    """``store_conversation`` insert + retrieval round-trip."""

    async def test_round_trip(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        conv_id = await store_conversation(
            duckdb_connection,
            content="Hello, world!",
            metadata={"project": "proj-A", "tag": "demo"},
            embedding=None,
        )
        row = await get_conversation(duckdb_connection, conv_id)
        assert row is not None
        assert row["id"] == conv_id
        assert row["content"] == "Hello, world!"
        assert row["project"] == "proj-A"
        assert row["metadata"] == {"project": "proj-A", "tag": "demo"}
        assert row["embedding"] is None
        assert row["timestamp"] is not None

    async def test_missing_id_returns_none(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        result = await get_conversation(duckdb_connection, "not-there")
        assert result is None

    async def test_unicode_round_trip(self, duckdb_connection: Any) -> None:
        # Surrogate characters must survive the encode/decode cycle.
        initialize_schema(duckdb_connection)
        text = "naïve café 🦆"
        conv_id = await store_conversation(
            duckdb_connection,
            content=text,
            metadata={"project": "unicode-test"},
            embedding=None,
        )
        row = await get_conversation(duckdb_connection, conv_id)
        assert row is not None
        assert row["content"] == text

    async def test_with_embedding_stores_vector(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        vec = [0.1] * 384
        conv_id = await store_conversation(
            duckdb_connection,
            content="with vec",
            metadata={"project": "embed"},
            embedding=vec,
        )
        row = await get_conversation(duckdb_connection, conv_id)
        assert row is not None
        assert row["embedding"] is not None


class TestStoreReflection:
    """``store_reflection`` insert + retrieval round-trip."""

    async def test_round_trip(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        refl_id = await store_reflection(
            duckdb_connection,
            content="useful insight",
            tags=["ai", "ml"],
            metadata={"project": "proj-A"},
            embedding=None,
        )
        row = await get_reflection(duckdb_connection, refl_id)
        assert row is not None
        assert row["id"] == refl_id
        assert row["content"] == "useful insight"
        assert row["project"] == "proj-A"
        assert sorted(row["tags"]) == ["ai", "ml"]
        assert row["metadata"] == {"project": "proj-A"}

    async def test_missing_id_returns_none(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        result = await get_reflection(duckdb_connection, "missing-id")
        assert result is None

    async def test_none_content_raises(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        with pytest.raises(TypeError):
            await store_reflection(
                duckdb_connection,
                content=None,
                tags=None,
                metadata={},
                embedding=None,
            )

    async def test_none_tags_default_to_empty_list(
        self, duckdb_connection: Any
    ) -> None:
        initialize_schema(duckdb_connection)
        refl_id = await store_reflection(
            duckdb_connection,
            content="no tags",
            tags=None,
            metadata={},
            embedding=None,
        )
        row = await get_reflection(duckdb_connection, refl_id)
        assert row is not None
        assert row["tags"] == []


class TestStoreCodeGraph:
    """``store_code_graph`` / ``get_code_graph`` round-trip and list API."""

    async def test_store_and_get_round_trip(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        graph = {
            "nodes": [{"id": 1, "name": "foo"}, {"id": 2, "name": "bar"}],
            "edges": [{"from": 1, "to": 2}],
        }
        gid = await store_code_graph(
            duckdb_connection,
            repo_path="/tmp/repo",
            commit_hash="abc123",
            indexed_at="2026-01-01T00:00:00Z",
            nodes_count=2,
            graph_data=graph,
            metadata={"source": "test"},
        )
        assert gid == "/tmp/repo:abc123"
        row = await get_code_graph(
            duckdb_connection, "/tmp/repo", "abc123"
        )
        assert row is not None
        assert row["repo_path"] == "/tmp/repo"
        assert row["commit_hash"] == "abc123"
        assert row["nodes_count"] == 2
        assert row["graph_data"] == graph
        assert row["metadata"] == {"source": "test"}

    async def test_get_missing_returns_none(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        result = await get_code_graph(
            duckdb_connection, "/no/repo", "deadbeef"
        )
        assert result is None

    async def test_insert_or_replace_overwrites(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        first = {"nodes": [{"id": 1}], "edges": []}
        second = {"nodes": [{"id": 2}], "edges": []}
        await store_code_graph(
            duckdb_connection,
            "/tmp/r",
            "cafebabe",
            "2026-01-01T00:00:00Z",
            1,
            first,
        )
        await store_code_graph(
            duckdb_connection,
            "/tmp/r",
            "cafebabe",
            "2026-02-01T00:00:00Z",
            1,
            second,
        )
        row = await get_code_graph(duckdb_connection, "/tmp/r", "cafebabe")
        assert row is not None
        assert row["graph_data"] == second
        assert row["nodes_count"] == 1

    async def test_list_filters_by_repo(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        await store_code_graph(
            duckdb_connection,
            "/tmp/repo-a",
            "commit1",
            "2026-01-01T00:00:00Z",
            5,
            {"nodes": [], "edges": []},
        )
        await store_code_graph(
            duckdb_connection,
            "/tmp/repo-b",
            "commit2",
            "2026-01-02T00:00:00Z",
            7,
            {"nodes": [], "edges": []},
        )
        result = await list_code_graphs(
            duckdb_connection, repo_path="/tmp/repo-a"
        )
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["code_graphs"][0]["repo_path"] == "/tmp/repo-a"

    async def test_list_no_filter_returns_all(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        for i in range(3):
            await store_code_graph(
                duckdb_connection,
                f"/tmp/repo-{i}",
                f"commit-{i}",
                "2026-01-01T00:00:00Z",
                i,
                {"nodes": [], "edges": []},
            )
        result = await list_code_graphs(duckdb_connection, limit=10)
        assert result["status"] == "success"
        assert result["count"] == 3
        assert len(result["code_graphs"]) == 3

    async def test_list_limit_caps_results(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        for i in range(5):
            await store_code_graph(
                duckdb_connection,
                f"/tmp/repo-{i}",
                f"commit-{i}",
                "2026-01-01T00:00:00Z",
                i,
                {"nodes": [], "edges": []},
            )
        result = await list_code_graphs(duckdb_connection, limit=2)
        assert result["count"] == 2
        assert len(result["code_graphs"]) == 2


class TestTempDbLockPath:
    """``is_temp_db=True`` + lock branches are exercised through the public API."""

    async def test_store_conversation_with_lock(self, duckdb_connection: Any) -> None:
        import threading

        initialize_schema(duckdb_connection)
        lock = threading.Lock()
        conv_id = await store_conversation(
            duckdb_connection,
            content="temp db",
            metadata={"project": "tmp"},
            embedding=None,
            is_temp_db=True,
            lock=lock,
        )
        row = await get_conversation(
            duckdb_connection,
            conv_id,
            is_temp_db=True,
            lock=lock,
        )
        assert row is not None
        assert row["content"] == "temp db"

    async def test_store_reflection_with_lock(self, duckdb_connection: Any) -> None:
        import threading

        initialize_schema(duckdb_connection)
        lock = threading.Lock()
        refl_id = await store_reflection(
            duckdb_connection,
            content="tmp reflection",
            tags=["x"],
            metadata={},
            embedding=None,
            is_temp_db=True,
            lock=lock,
        )
        row = await get_reflection(
            duckdb_connection,
            refl_id,
            is_temp_db=True,
            lock=lock,
        )
        assert row is not None
        assert row["content"] == "tmp reflection"

    async def test_store_code_graph_with_lock(self, duckdb_connection: Any) -> None:
        import threading

        initialize_schema(duckdb_connection)
        lock = threading.Lock()
        gid = await store_code_graph(
            duckdb_connection,
            "/tmp/locked",
            "commit-lock",
            "2026-03-01T00:00:00Z",
            3,
            {"nodes": [1, 2, 3], "edges": []},
            metadata=None,
            lock=lock,
        )
        row = await get_code_graph(
            duckdb_connection, "/tmp/locked", "commit-lock", lock=lock
        )
        assert row is not None
        assert gid == "/tmp/locked:commit-lock"


class TestSchemaBranchCoverage:
    """Both legacy and ``*_ulid`` schemas are exercised by ``store_*``."""

    async def test_store_reflection_without_ulid_column(
        self, duckdb_connection: Any
    ) -> None:
        # Drop reflection_ulid to mimic the pre-ULID schema.
        duckdb_connection.execute(
            """
            CREATE TABLE reflections (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                embedding FLOAT[384],
                project VARCHAR,
                tags VARCHAR[],
                timestamp TIMESTAMP,
                metadata JSON
            )
            """
        )
        refl_id = await store_reflection(
            duckdb_connection,
            content="legacy schema",
            tags=["legacy"],
            metadata={},
            embedding=None,
        )
        row = await get_reflection(duckdb_connection, refl_id)
        assert row is not None
        assert row["content"] == "legacy schema"
        assert row["reflection_ulid"] is None

    async def test_store_conversation_without_ulid_column(
        self, duckdb_connection: Any
    ) -> None:
        duckdb_connection.execute(
            """
            CREATE TABLE conversations (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                embedding FLOAT[384],
                project VARCHAR,
                timestamp TIMESTAMP,
                metadata JSON
            )
            """
        )
        conv_id = await store_conversation(
            duckdb_connection,
            content="legacy conv",
            metadata={"project": "legacy"},
            embedding=None,
        )
        row = await get_conversation(duckdb_connection, conv_id)
        assert row is not None
        assert row["content"] == "legacy conv"