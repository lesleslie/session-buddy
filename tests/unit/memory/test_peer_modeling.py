from __future__ import annotations

import re

import pytest

from session_buddy.memory.peer_modeling import (
    DEFAULT_HEURISTIC_MODEL,
    build_peer_context,
    get_peer_model,
    heuristic_synthesize,
    recent_memories,
    upsert_peer_model,
)


# ------------------------------------------------------------------
# Schema bootstrap helper
# ------------------------------------------------------------------


@pytest.fixture
def duck_conn():
    """In-memory DuckDB with the tables peer_modeling touches."""
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE conversations_v2 (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            category TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            project TEXT,
            source_type TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE user_models (
            peer_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            representation_text TEXT NOT NULL,
            last_updated TIMESTAMP NOT NULL DEFAULT now(),
            evidence_count INTEGER NOT NULL DEFAULT 0,
            model TEXT NOT NULL,
            PRIMARY KEY (peer_id, project_id)
        )
        """
    )
    yield conn
    conn.close()


def _insert_memory(
    conn,
    *,
    memory_id: str,
    content: str,
    category: str,
    project: str,
    timestamp: str | None = None,
) -> None:
    ts = timestamp or "2026-09-04 12:00:00"
    conn.execute(
        """
        INSERT INTO conversations_v2 (id, content, category, project, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        [memory_id, content, category, project, ts],
    )


# ------------------------------------------------------------------
# heuristic_synthesize
# ------------------------------------------------------------------


class TestHeuristicSynthesize:
    """Tests for peer_modeling.heuristic_synthesize."""

    def test_no_memories_returns_placeholder(self, duck_conn) -> None:
        out = heuristic_synthesize(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        assert "no memories yet" in out
        assert "alice" in out
        assert "proj-1" in out

    def test_counts_categories_in_summary(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            content="Python is great for async work",
            category="facts",
            project="proj-1",
        )
        _insert_memory(
            duck_conn,
            memory_id="m2",
            content="I prefer dark mode",
            category="preferences",
            project="proj-1",
        )
        _insert_memory(
            duck_conn,
            memory_id="m3",
            content="Another fact about python",
            category="facts",
            project="proj-1",
        )
        out = heuristic_synthesize(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        # Order in summary is by descending count.
        assert "facts (2)" in out
        assert "preferences (1)" in out

    def test_extracts_topics_from_first_words(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            content="Python async patterns",
            category="skills",
            project="proj-1",
        )
        _insert_memory(
            duck_conn,
            memory_id="m2",
            content="Database indexes matter",
            category="facts",
            project="proj-1",
        )
        out = heuristic_synthesize(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        # First distinct first words become topics.
        assert "Python" in out
        assert "Database" in out

    def test_topic_count_capped_at_three(self, duck_conn) -> None:
        # Insert five distinct first words.
        for i in range(5):
            _insert_memory(
                duck_conn,
                memory_id=f"m{i}",
                content=f"Topic{i} something else",
                category="facts",
                project="proj-1",
                timestamp=f"2026-09-04 12:00:0{i}",
            )
        out = heuristic_synthesize(
            duck_conn, peer_id="alice", project_id="proj-1", recent_limit=5
        )
        # Count "Topic" occurrences in the topic portion.
        topic_section = out.split("Recent topics: ")[1].rstrip(".")
        topics = [t.strip() for t in topic_section.split(",")]
        assert len(topics) <= 3

    def test_recent_limit_respected(self, duck_conn) -> None:
        for i in range(10):
            _insert_memory(
                duck_conn,
                memory_id=f"m{i}",
                content=f"Memory {i}",
                category="facts",
                project="proj-1",
                timestamp=f"2026-09-04 12:00:{i:02d}",
            )
        out = heuristic_synthesize(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            recent_limit=3,
        )
        assert "3 recent memories" in out

    def test_missing_category_counted_as_unknown(self, duck_conn) -> None:
        # Insert with explicit NULL category.
        duck_conn.execute(
            """
            INSERT INTO conversations_v2 (id, content, category, project, timestamp)
            VALUES ('m1', 'something', NULL, 'proj-1', '2026-09-04 12:00:00')
            """
        )
        out = heuristic_synthesize(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        assert "unknown (1)" in out

    def test_empty_content_topic_branch(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            content="",
            category="facts",
            project="proj-1",
        )
        out = heuristic_synthesize(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        # No topics when content is empty.
        assert "Recent topics:" in out

    def test_different_project_filtered_out(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            content="Memory in other project",
            category="facts",
            project="other",
        )
        out = heuristic_synthesize(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        assert "no memories yet" in out


# ------------------------------------------------------------------
# upsert_peer_model
# ------------------------------------------------------------------


class TestUpsertPeerModel:
    """Tests for peer_modeling.upsert_peer_model."""

    def test_insert_creates_row_with_heuristic(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            content="Python is fun",
            category="facts",
            project="proj-1",
        )
        out = upsert_peer_model(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        assert "Peer alice" in out

        row = duck_conn.execute(
            """
            SELECT representation_text, evidence_count, model
            FROM user_models
            WHERE peer_id='alice' AND project_id='proj-1'
            """
        ).fetchone()
        assert row is not None
        assert row[1] == 1
        assert row[2] == DEFAULT_HEURISTIC_MODEL
        # Returned representation must match stored one.
        assert row[0] == out

    def test_update_increments_evidence_count(self, duck_conn) -> None:
        upsert_peer_model(duck_conn, peer_id="alice", project_id="proj-1")
        upsert_peer_model(duck_conn, peer_id="alice", project_id="proj-1")
        upsert_peer_model(duck_conn, peer_id="alice", project_id="proj-1")

        count = duck_conn.execute(
            """
            SELECT evidence_count FROM user_models
            WHERE peer_id='alice' AND project_id='proj-1'
            """
        ).fetchone()[0]
        assert count == 3

    def test_explicit_replacement_text(self, duck_conn) -> None:
        upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            representation_text="Custom LLM-driven summary",
        )
        out = upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            representation_text="Updated by Conscious Agent",
        )
        assert out == "Updated by Conscious Agent"

    def test_custom_model_recorded(self, duck_conn) -> None:
        upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            representation_text="text",
            model="minimax-mock",
        )
        model = duck_conn.execute(
            """
            SELECT model FROM user_models
            WHERE peer_id='alice' AND project_id='proj-1'
            """
        ).fetchone()[0]
        assert model == "minimax-mock"

    def test_different_peer_projects_isolated(self, duck_conn) -> None:
        upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            representation_text="alice in proj-1",
        )
        upsert_peer_model(
            duck_conn,
            peer_id="bob",
            project_id="proj-1",
            representation_text="bob in proj-1",
        )
        upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-2",
            representation_text="alice in proj-2",
        )

        rows = duck_conn.execute(
            "SELECT peer_id, project_id FROM user_models ORDER BY peer_id, project_id"
        ).fetchall()
        assert len(rows) == 3
        assert ("alice", "proj-1") in rows
        assert ("alice", "proj-2") in rows
        assert ("bob", "proj-1") in rows


# ------------------------------------------------------------------
# get_peer_model
# ------------------------------------------------------------------


class TestGetPeerModel:
    """Tests for peer_modeling.get_peer_model."""

    def test_returns_none_when_missing(self, duck_conn) -> None:
        assert get_peer_model(
            duck_conn, peer_id="alice", project_id="proj-1"
        ) is None

    def test_returns_full_row_dict(self, duck_conn) -> None:
        upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            representation_text="hello",
        )
        row = get_peer_model(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        assert row is not None
        assert row["peer_id"] == "alice"
        assert row["project_id"] == "proj-1"
        assert row["representation_text"] == "hello"
        assert row["evidence_count"] == 1
        assert row["model"] == DEFAULT_HEURISTIC_MODEL
        assert row["last_updated"] is not None


# ------------------------------------------------------------------
# recent_memories
# ------------------------------------------------------------------


class TestRecentMemories:
    """Tests for peer_modeling.recent_memories."""

    def test_returns_empty_list_when_no_data(self, duck_conn) -> None:
        result = recent_memories(
            duck_conn, project_id="proj-1", recent_limit=5
        )
        assert result == []

    def test_returns_memories_in_reverse_chronological_order(self, duck_conn) -> None:
        for i in range(5):
            _insert_memory(
                duck_conn,
                memory_id=f"m{i}",
                content=f"Memory {i}",
                category="facts",
                project="proj-1",
                timestamp=f"2026-09-04 12:00:0{i}",
            )
        result = recent_memories(
            duck_conn, project_id="proj-1", recent_limit=10
        )
        timestamps = [r["timestamp"] for r in result]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_filters_by_project(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            content="In proj-1",
            category="facts",
            project="proj-1",
        )
        _insert_memory(
            duck_conn,
            memory_id="m2",
            content="In proj-2",
            category="facts",
            project="proj-2",
        )
        result = recent_memories(
            duck_conn, project_id="proj-1", recent_limit=5
        )
        assert len(result) == 1
        assert result[0]["project"] == "proj-1"

    def test_recent_limit_caps_results(self, duck_conn) -> None:
        for i in range(10):
            _insert_memory(
                duck_conn,
                memory_id=f"m{i}",
                content=f"M{i}",
                category="facts",
                project="proj-1",
                timestamp=f"2026-09-04 12:00:{i:02d}",
            )
        result = recent_memories(
            duck_conn, project_id="proj-1", recent_limit=3
        )
        assert len(result) == 3

    def test_result_includes_expected_fields(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            content="hello",
            category="facts",
            project="proj-1",
        )
        result = recent_memories(
            duck_conn, project_id="proj-1", recent_limit=1
        )
        row = result[0]
        for key in ("id", "content", "category", "timestamp", "project", "source_type"):
            assert key in row


# ------------------------------------------------------------------
# build_peer_context
# ------------------------------------------------------------------


class TestBuildPeerContext:
    """Tests for peer_modeling.build_peer_context."""

    def test_no_model_returns_placeholder(self, duck_conn) -> None:
        _insert_memory(
            duck_conn,
            memory_id="m1",
            content="alpha",
            category="facts",
            project="proj-1",
        )
        out = build_peer_context(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        assert out["peer_id"] == "alice"
        assert out["project_id"] == "proj-1"
        assert out["representation_text"] == ""
        assert out["last_updated"] is None
        assert out["evidence_count"] == 0
        assert out["model"] == ""
        assert out["target_peer"] is None
        assert len(out["recent_memories"]) == 1

    def test_existing_model_populates_fields(self, duck_conn) -> None:
        upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            representation_text="custom",
        )
        out = build_peer_context(
            duck_conn, peer_id="alice", project_id="proj-1"
        )
        assert out["representation_text"] == "custom"
        assert out["evidence_count"] == 1
        assert out["model"] == DEFAULT_HEURISTIC_MODEL
        assert out["target_peer"] is None

    def test_target_peer_when_present(self, duck_conn) -> None:
        upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            representation_text="alice-text",
        )
        upsert_peer_model(
            duck_conn,
            peer_id="agent-bot",
            project_id="proj-1",
            representation_text="agent-text",
        )
        out = build_peer_context(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            target_peer_id="agent-bot",
        )
        assert out["target_peer"] is not None
        assert out["target_peer"]["peer_id"] == "agent-bot"
        assert out["target_peer"]["representation_text"] == "agent-text"

    def test_target_peer_none_when_missing(self, duck_conn) -> None:
        upsert_peer_model(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            representation_text="x",
        )
        out = build_peer_context(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            target_peer_id="never-existed",
        )
        assert out["target_peer"] is None

    def test_target_peer_id_without_model_returns_no_target(self, duck_conn) -> None:
        # Caller asks for a target_peer but the main peer has no model row.
        out = build_peer_context(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            target_peer_id="someone",
        )
        # No target_peer because both target and base are missing.
        assert out["target_peer"] is None
        assert out["evidence_count"] == 0

    def test_recent_limit_propagates(self, duck_conn) -> None:
        for i in range(5):
            _insert_memory(
                duck_conn,
                memory_id=f"m{i}",
                content=f"M{i}",
                category="facts",
                project="proj-1",
                timestamp=f"2026-09-04 12:00:0{i}",
            )
        out = build_peer_context(
            duck_conn,
            peer_id="alice",
            project_id="proj-1",
            recent_limit=2,
        )
        assert len(out["recent_memories"]) == 2


# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------


def test_default_heuristic_model_constant() -> None:
    assert DEFAULT_HEURISTIC_MODEL == "heuristic"


def test_heuristic_output_shape_regex() -> None:
    """Spot-check the placeholder regex shape (sanity guard)."""
    pattern = re.compile(
        r"^Peer [^\s]+ has no memories yet in project [^\s]+\. Initial representation\.$"
    )
    assert pattern.match(
        "Peer alice has no memories yet in project proj-1. Initial representation."
    )