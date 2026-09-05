"""Unit tests for session_buddy/reflection/search.py.

Covers the public search functions:

- ``search_conversations`` (semantic + text fallback paths)
- ``search_reflections`` (semantic + text fallback paths)

And the private helpers:

- ``_semantic_search_conversations`` and ``_text_search_conversations``
- ``_semantic_search_reflections`` and ``_text_search_reflections``
- ``_decode_text_from_db`` round-trip with surrogate-pair Unicode

Tests use the existing ``duckdb_connection`` fixture (defined in
``tests/conftest.py``) and initialize the schema via
``session_buddy.reflection.schema.initialize_schema`` to mirror production.
The semantic-search branch relies on the DuckDB ``vss`` community extension
for ``array_cosine_similarity``; tests that require it are skipped when the
extension is not loadable.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest

from session_buddy.reflection.schema import (
    create_conversations_table,
    create_reflections_table,
    initialize_schema,
)
from session_buddy.reflection.search import (
    _decode_text_from_db,
    _semantic_search_conversations,
    _semantic_search_reflections,
    _text_search_conversations,
    _text_search_reflections,
    search_conversations,
    search_reflections,
)
from session_buddy.reflection.storage import _encode_text_for_db


def _try_load_vss(conn: Any) -> bool:
    """Best-effort load of the DuckDB VSS extension.

    Returns True when ``array_cosine_similarity`` is callable, False otherwise.
    Tests that need vector similarity skip when this returns False.
    """
    try:
        conn.execute("INSTALL vss; LOAD vss;")
    except Exception:
        return False
    try:
        conn.execute(
            "SELECT array_cosine_similarity([1.0, 0.0]::FLOAT[2], "
            "[1.0, 0.0]::FLOAT[2])"
        )
    except Exception:
        return False
    return True


def _make_embedding(value: float = 0.1) -> list[float]:
    """Build a 384-dim vector suitable for the FLOAT[384] column."""
    return [float(value)] * 384


class TestSearchConversationsEmpty:
    """Empty-database paths return empty results for both branches."""

    async def test_text_search_empty_db_returns_empty(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        results = await search_conversations(
            duckdb_connection, "anything", None
        )
        assert results == []

    async def test_semantic_search_empty_db_returns_empty(
        self, duckdb_connection: Any
    ) -> None:
        create_conversations_table(duckdb_connection)
        results = await search_conversations(
            duckdb_connection, "anything", _make_embedding()
        )
        # Without VSS, semantic SQL raises and falls back to text search.
        # Either way, an empty DB must yield an empty list.
        assert results == []

    async def test_semantic_search_with_vss_empty_db(
        self, duckdb_connection: Any
    ) -> None:
        create_conversations_table(duckdb_connection)
        if not _try_load_vss(duckdb_connection):
            pytest.skip("duckdb-vss extension unavailable")
        results = await search_conversations(
            duckdb_connection, "anything", _make_embedding()
        )
        assert results == []


class TestSearchConversationsTextFallback:
    """Text search path: query_embedding=None triggers LIKE-based search."""

    async def test_finds_matching_content(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, project, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["c1", "Python programming is great", "proj-a"],
        )
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, project, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["c2", "JavaScript frameworks are popular", "proj-b"],
        )

        results = await search_conversations(
            duckdb_connection, "python", None
        )
        assert len(results) == 1
        assert "Python" in results[0]["content"]
        assert results[0]["id"] == "c1"

    async def test_no_match_returns_empty(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["c1", "Just a plain string"],
        )
        results = await search_conversations(
            duckdb_connection, "unobtanium", None
        )
        assert results == []

    async def test_empty_query_returns_empty(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["c1", "Some content"],
        )
        results = await search_conversations(duckdb_connection, "", None)
        assert results == []

    async def test_score_is_zero_for_text_match(
        self, duckdb_connection: Any
    ) -> None:
        create_conversations_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["c1", "Python is fun"],
        )
        results = await search_conversations(
            duckdb_connection, "python", None
        )
        assert results[0]["score"] == 0.0

    async def test_project_filter(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, project, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["c1", "Python is great", "proj-a"],
        )
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, project, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["c2", "Python is also great", "proj-b"],
        )

        results = await search_conversations(
            duckdb_connection, "python", None, project="proj-a"
        )
        assert len(results) == 1
        assert results[0]["project"] == "proj-a"

    async def test_limit_caps_results(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        for i in range(5):
            duckdb_connection.execute(
                "INSERT INTO conversations (id, content, timestamp) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                [f"c{i}", f"Python note number {i}"],
            )
        results = await search_conversations(
            duckdb_connection, "python", None, limit=2
        )
        assert len(results) == 2

    async def test_unicode_round_trip(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        encoded = _encode_text_for_db("Python 𝕌𝕟𝕚𝕔𝕠𝕕𝕖 rules")
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["c1", encoded],
        )
        results = await search_conversations(
            duckdb_connection, "python", None
        )
        assert len(results) == 1
        assert "𝕌𝕟𝕚𝕔𝕠𝕕𝕖" in results[0]["content"]

    async def test_metadata_round_trip(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        metadata = {"user": "alice", "session": "sess-42"}
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, metadata, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["c1", "Python note", json.dumps(metadata)],
        )
        results = await search_conversations(
            duckdb_connection, "python", None
        )
        assert results[0]["metadata"] == metadata


class TestSearchConversationsSemantic:
    """Semantic path: query_embedding provided, falls back on VSS errors."""

    async def test_semantic_with_vss_returns_scored_results(
        self, duckdb_connection: Any
    ) -> None:
        create_conversations_table(duckdb_connection)
        if not _try_load_vss(duckdb_connection):
            pytest.skip("duckdb-vss extension unavailable")

        # Use a unique, orthogonal embedding for the row and a matching
        # embedding for the query so cosine similarity is high.
        duckdb_connection.execute(
            "INSERT INTO conversations "
            "(id, content, embedding, timestamp) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["c1", "first", _make_embedding(0.5)],
        )
        duckdb_connection.execute(
            "INSERT INTO conversations "
            "(id, content, embedding, timestamp) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["c2", "second", _make_embedding(0.9)],
        )

        results = await search_conversations(
            duckdb_connection, "second", _make_embedding(0.9), min_score=0.5
        )
        assert len(results) >= 1
        assert results[0]["id"] == "c2"
        assert results[0]["score"] >= 0.5

    async def test_semantic_filters_by_project(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        if not _try_load_vss(duckdb_connection):
            pytest.skip("duckdb-vss extension unavailable")

        duckdb_connection.execute(
            "INSERT INTO conversations "
            "(id, content, embedding, project, timestamp) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ["c1", "first", _make_embedding(0.9), "proj-a"],
        )
        duckdb_connection.execute(
            "INSERT INTO conversations "
            "(id, content, embedding, project, timestamp) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ["c2", "second", _make_embedding(0.9), "proj-b"],
        )

        results = await search_conversations(
            duckdb_connection,
            "match",
            _make_embedding(0.9),
            project="proj-a",
            min_score=0.5,
        )
        assert len(results) == 1
        assert results[0]["project"] == "proj-a"

    async def test_semantic_no_match_falls_back_to_text(
        self, duckdb_connection: Any
    ) -> None:
        """When semantic SQL raises (no VSS) the search must fall back to text."""
        create_conversations_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["c1", "alpha bravo charlie"],
        )

        # query_embedding is provided, but VSS is unlikely loaded. The except
        # branch must fall back to text search.
        results = await search_conversations(
            duckdb_connection, "bravo", _make_embedding()
        )
        # Without VSS, exception handler falls back to text search and finds
        # the row by substring.
        assert isinstance(results, list)
        assert any("bravo" in r["content"] for r in results)


class TestSearchConversationsTempDb:
    """is_temp_db=True routes through the supplied lock."""

    async def test_temp_db_uses_lock(self, duckdb_connection: Any) -> None:
        create_conversations_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["c1", "alpha content"],
        )

        # search.py uses synchronous `with lock:` so it must be a
        # threading.Lock (or any context-manager that supports __enter__).
        lock = threading.Lock()
        results = await _text_search_conversations(
            duckdb_connection,
            "alpha",
            limit=5,
            project=None,
            is_temp_db=True,
            lock=lock,
        )
        assert len(results) == 1
        assert "alpha" in results[0]["content"]


class TestSearchReflectionsEmpty:
    """Empty-database paths return empty results for both branches."""

    async def test_text_search_empty_db_returns_empty(
        self, duckdb_connection: Any
    ) -> None:
        create_reflections_table(duckdb_connection)
        results = await search_reflections(duckdb_connection, "anything", None)
        assert results == []

    async def test_semantic_search_empty_db_returns_empty(
        self, duckdb_connection: Any
    ) -> None:
        create_reflections_table(duckdb_connection)
        results = await search_reflections(
            duckdb_connection, "anything", _make_embedding()
        )
        assert results == []

    async def test_semantic_search_with_vss_empty_db(
        self, duckdb_connection: Any
    ) -> None:
        create_reflections_table(duckdb_connection)
        if not _try_load_vss(duckdb_connection):
            pytest.skip("duckdb-vss extension unavailable")
        results = await search_reflections(
            duckdb_connection, "anything", _make_embedding()
        )
        assert results == []


class TestSearchReflectionsTextFallback:
    """Text search path: query_embedding=None triggers LIKE-based search."""

    async def test_finds_matching_content(self, duckdb_connection: Any) -> None:
        create_reflections_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, project, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r1", "Python testing insights", "proj-a"],
        )
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, project, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r2", "JavaScript testing tools", "proj-b"],
        )

        results = await search_reflections(duckdb_connection, "python", None)
        assert len(results) == 1
        assert "Python" in results[0]["content"]

    async def test_searches_tags(self, duckdb_connection: Any) -> None:
        create_reflections_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, tags, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r1", "Generic note", ["python", "testing"]],
        )

        # The tag "python" is matched even though the content does not
        # contain the word "python".
        results = await search_reflections(duckdb_connection, "python", None)
        assert len(results) == 1
        assert results[0]["id"] == "r1"

    async def test_empty_query_returns_all_rows(self, duckdb_connection: Any) -> None:
        """Reflections text search returns all rows when the query is empty."""
        create_reflections_table(duckdb_connection)
        for i in range(3):
            duckdb_connection.execute(
                "INSERT INTO reflections (id, content, timestamp) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                [f"r{i}", f"note {i}"],
            )

        results = await search_reflections(duckdb_connection, "", None)
        assert len(results) == 3

    async def test_project_filter(self, duckdb_connection: Any) -> None:
        create_reflections_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, project, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r1", "Python note A", "proj-a"],
        )
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, project, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r2", "Python note B", "proj-b"],
        )

        results = await search_reflections(
            duckdb_connection, "python", None, project="proj-b"
        )
        assert len(results) == 1
        assert results[0]["id"] == "r2"

    async def test_limit_caps_results(self, duckdb_connection: Any) -> None:
        create_reflections_table(duckdb_connection)
        for i in range(5):
            duckdb_connection.execute(
                "INSERT INTO reflections (id, content, timestamp) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                [f"r{i}", f"Python reflection {i}"],
            )
        results = await search_reflections(
            duckdb_connection, "python", None, limit=2
        )
        assert len(results) == 2

    async def test_result_includes_tags_field(self, duckdb_connection: Any) -> None:
        create_reflections_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, tags, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r1", "A note", ["alpha", "beta"]],
        )
        results = await search_reflections(duckdb_connection, "note", None)
        assert results[0]["tags"] == ["alpha", "beta"]

    async def test_unicode_round_trip(self, duckdb_connection: Any) -> None:
        create_reflections_table(duckdb_connection)
        encoded = _encode_text_for_db("Reflection with 𝕌𝕟𝕚𝕔𝕠𝕕𝕖")
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["r1", encoded],
        )
        results = await search_reflections(duckdb_connection, "reflection", None)
        assert len(results) == 1
        assert "𝕌𝕟𝕚𝕔𝕠𝕕𝕖" in results[0]["content"]


class TestSearchReflectionsSemantic:
    """Semantic path: query_embedding provided, falls back on VSS errors."""

    async def test_semantic_with_vss_returns_scored_results(
        self, duckdb_connection: Any
    ) -> None:
        create_reflections_table(duckdb_connection)
        if not _try_load_vss(duckdb_connection):
            pytest.skip("duckdb-vss extension unavailable")

        duckdb_connection.execute(
            "INSERT INTO reflections "
            "(id, content, embedding, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r1", "alpha", _make_embedding(0.7)],
        )

        results = await search_reflections(
            duckdb_connection,
            "alpha",
            _make_embedding(0.7),
            min_score=0.5,
        )
        assert len(results) == 1
        assert results[0]["score"] >= 0.5

    async def test_semantic_no_match_falls_back_to_text(
        self, duckdb_connection: Any
    ) -> None:
        create_reflections_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["r1", "alpha bravo charlie"],
        )
        results = await search_reflections(
            duckdb_connection, "bravo", _make_embedding()
        )
        assert isinstance(results, list)
        assert any("bravo" in r["content"] for r in results)

    async def test_semantic_filters_by_project(self, duckdb_connection: Any) -> None:
        create_reflections_table(duckdb_connection)
        if not _try_load_vss(duckdb_connection):
            pytest.skip("duckdb-vss extension unavailable")

        duckdb_connection.execute(
            "INSERT INTO reflections "
            "(id, content, embedding, project, timestamp) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ["r1", "alpha", _make_embedding(0.7), "proj-a"],
        )
        duckdb_connection.execute(
            "INSERT INTO reflections "
            "(id, content, embedding, project, timestamp) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ["r2", "alpha", _make_embedding(0.7), "proj-b"],
        )

        results = await search_reflections(
            duckdb_connection,
            "alpha",
            _make_embedding(0.7),
            project="proj-a",
            min_score=0.5,
        )
        assert len(results) == 1
        assert results[0]["project"] == "proj-a"


class TestSearchReflectionsTempDb:
    """is_temp_db=True routes through the supplied lock."""

    async def test_temp_db_uses_lock(self, duckdb_connection: Any) -> None:
        create_reflections_table(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, tags, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r1", "alpha content", ["python"]],
        )

        lock = threading.Lock()
        results = await _text_search_reflections(
            duckdb_connection,
            "alpha",
            limit=5,
            project=None,
            is_temp_db=True,
            lock=lock,
        )
        assert len(results) == 1


class TestDecodeTextRoundTrip:
    """``_decode_text_from_db`` is re-exported and used by search internals."""

    def test_plain_text_returns_input(self) -> None:
        assert _decode_text_from_db("hello world") == "hello world"

    def test_surrogate_prefix_round_trip(self) -> None:
        # Construct a string with a lone surrogate that requires the
        # ``surrogatepass`` codec — this is the only way to make
        # ``str.encode("utf-8")`` raise UnicodeEncodeError and trigger
        # the __SB64__ branch in _encode_text_for_db.
        surrogate = "\udc00"
        try:
            surrogate.encode("utf-8")
            pytest.skip("Lone surrogate did not raise UnicodeEncodeError")
        except UnicodeEncodeError:
            pass
        encoded = _encode_text_for_db(surrogate)
        assert encoded.startswith("__SB64__")
        assert _decode_text_from_db(encoded) == surrogate


class TestInitializeSchemaHook:
    """``initialize_schema`` creates both tables in one shot (mirrors prod)."""

    async def test_initialize_schema_allows_search(self, duckdb_connection: Any) -> None:
        initialize_schema(duckdb_connection)
        duckdb_connection.execute(
            "INSERT INTO conversations (id, content, timestamp) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ["c1", "alpha"],
        )
        duckdb_connection.execute(
            "INSERT INTO reflections (id, content, tags, timestamp) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ["r1", "beta", ["python"]],
        )
        conv = await search_conversations(duckdb_connection, "alpha", None)
        refl = await search_reflections(duckdb_connection, "beta", None)
        assert len(conv) == 1
        assert len(refl) == 1
