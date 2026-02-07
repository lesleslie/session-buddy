"""Database schema definitions for reflection system.

Defines all SQL schemas, indexes, and initialization logic for the
reflection database tables.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def create_conversations_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create conversations table with vector embeddings support.

    Args:
        conn: DuckDB connection

    Schema:
        - id: Unique conversation identifier
        - content: Conversation text content
        - embedding: FLOAT[384] vector for semantic search
        - project: Project identifier (optional)
        - timestamp: Creation timestamp
        - metadata: JSON metadata
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id VARCHAR PRIMARY KEY,
            content TEXT NOT NULL,
            embedding FLOAT[384],
            project VARCHAR,
            timestamp TIMESTAMP,
            metadata JSON
        )
        """
    )


def create_reflections_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create reflections table with vector embeddings support.

    Args:
        conn: DuckDB connection

    Schema:
        - id: Unique reflection identifier
        - content: Reflection text content
        - embedding: FLOAT[384] vector for semantic search
        - project: Project identifier (optional)
        - tags: Array of tags for categorization
        - timestamp: Creation timestamp
        - metadata: JSON metadata
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reflections (
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


def create_reflection_tags_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create reflection_tags table for tag-based search.

    Args:
        conn: DuckDB connection

    Note:
        No foreign key to reflections table (DuckDB has limitations on updates).
        Application-level consistency is maintained.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reflection_tags (
            reflection_id VARCHAR,
            tag VARCHAR,
            PRIMARY KEY (reflection_id, tag)
        )
        """
    )


def create_project_groups_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create project_groups table for multi-project coordination.

    Args:
        conn: DuckDB connection

    Schema:
        - id: Unique group identifier
        - name: Group name
        - description: Group description (optional)
        - projects: Array of project paths in this group
        - created_at: Group creation timestamp
        - metadata: JSON metadata
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_groups (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT,
            projects VARCHAR[] NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            metadata JSON
        )
        """
    )


def create_project_dependencies_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create project_dependencies table for project relationships.

    Args:
        conn: DuckDB connection

    Schema:
        - id: Unique dependency identifier
        - source_project: Source project path
        - target_project: Target project path
        - dependency_type: Type of relationship (related, continuation, reference)
        - description: Dependency description (optional)
        - created_at: Dependency creation timestamp
        - metadata: JSON metadata
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_dependencies (
            id VARCHAR PRIMARY KEY,
            source_project VARCHAR NOT NULL,
            target_project VARCHAR NOT NULL,
            dependency_type VARCHAR NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            metadata JSON,
            UNIQUE(source_project, target_project, dependency_type)
        )
        """
    )


def create_session_links_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create session_links table for cross-project session coordination.

    Args:
        conn: DuckDB connection

    Schema:
        - id: Unique link identifier
        - source_session_id: Source session identifier
        - target_session_id: Target session identifier
        - link_type: Type of link (continuation, reference, related)
        - created_at: Link creation timestamp
        - metadata: JSON metadata
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_links (
            id VARCHAR PRIMARY KEY,
            source_session_id VARCHAR NOT NULL,
            target_session_id VARCHAR NOT NULL,
            link_type VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            metadata JSON
        )
        """
    )


def create_access_log_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create access_log_v2 table for reflection access tracking.

    Args:
        conn: DuckDB connection

    Schema:
        - reflection_id: Reflection identifier
        - access_timestamp: Last access timestamp
        - access_count: Number of times accessed
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS access_log_v2 (
            reflection_id VARCHAR PRIMARY KEY,
            access_timestamp TIMESTAMP,
            access_count INTEGER DEFAULT 0
        )
        """
    )


def create_code_graphs_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create code_graphs table for storing indexed code graphs from Mahavishnu.

    Args:
        conn: DuckDB connection

    Schema:
        - id: Unique code graph identifier (repo_path + commit_hash)
        - repo_path: Path to the repository
        - commit_hash: Git commit hash
        - indexed_at: When the graph was indexed
        - nodes_count: Number of nodes in the code graph
        - graph_data: JSON serialized code graph data
        - timestamp: When this record was created
        - metadata: Additional metadata JSON
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS code_graphs (
            id VARCHAR PRIMARY KEY,
            repo_path TEXT NOT NULL,
            commit_hash TEXT NOT NULL,
            indexed_at TIMESTAMP NOT NULL,
            nodes_count INTEGER NOT NULL,
            graph_data JSON NOT NULL,
            timestamp TIMESTAMP DEFAULT NOW(),
            metadata JSON
        )
        """
    )


def create_all_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all database tables.

    Args:
        conn: DuckDB connection

    Creates all tables in the correct order to handle dependencies.
    """
    # Core tables
    create_conversations_table(conn)
    create_reflections_table(conn)
    create_reflection_tags_table(conn)

    # Multi-project coordination tables
    create_project_groups_table(conn)
    create_project_dependencies_table(conn)
    create_session_links_table(conn)

    # Access tracking
    create_access_log_table(conn)

    # Cross-system integration
    create_code_graphs_table(conn)


def create_indexes(conn: duckdb.DuckDBPyConnection) -> None:
    """Create performance indexes for all tables.

    Args:
        conn: DuckDB connection

    Note:
        Some indexes might not be supported in all DuckDB versions.
        Errors are suppressed to allow graceful degradation.
    """
    indexes = [
        # Conversations indexes
        "CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project)",
        "CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)",
        # Reflections indexes
        "CREATE INDEX IF NOT EXISTS idx_reflections_project ON reflections(project)",
        "CREATE INDEX IF NOT EXISTS idx_reflections_timestamp ON reflections(timestamp)",
        # Tags indexes
        "CREATE INDEX IF NOT EXISTS idx_reflection_tags_tag ON reflection_tags(tag)",
        # Code graphs indexes
        "CREATE INDEX IF NOT EXISTS idx_code_graphs_repo_path ON code_graphs(repo_path)",
        "CREATE INDEX IF NOT EXISTS idx_code_graphs_commit_hash ON code_graphs(commit_hash)",
        "CREATE INDEX IF NOT EXISTS idx_code_graphs_indexed_at ON code_graphs(indexed_at DESC)",
    ]

    for index_sql in indexes:
        with suppress(Exception):
            # Some indexes might not be supported in all DuckDB versions, continue
            conn.execute(index_sql)


def initialize_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Initialize complete database schema with tables and indexes.

    Args:
        conn: DuckDB connection

    This is the main entry point for schema initialization.
    """
    create_all_tables(conn)
    create_indexes(conn)
