"""MCP tools for code analysis - storage focused.

These tools integrate tree-sitter parsing with Session-Buddy's knowledge graph
for semantic code search and relationship queries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


def register_code_analysis_tools(mcp: FastMCP) -> None:
    """Register 3 code analysis tools for Session-Buddy.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    async def code_ingest_file(
        file_path: str,
        project: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Parse a code file and store entities in knowledge graph.

        Extracts functions, classes, methods, imports, and relationships
        from source code and stores them for semantic search.

        Args:
            file_path: Absolute path to source file
            project: Optional project name for grouping
            language: Optional language override (python, go, etc.)

        Returns:
            Summary of ingested entities and relationships
        """
        from pathlib import Path

        from session_buddy.code_analysis.kg_extractor import KGExtractor

        try:
            extractor = KGExtractor()
            result = await extractor.extract_and_store(
                Path(file_path),
                project=project,
                language=language,
            )
            return {
                "status": "success",
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to ingest file: {e}")
            return {
                "status": "error",
                "error": str(e),
                "file_path": file_path,
            }

    @mcp.tool()
    async def code_ingest_directory(
        directory: str,
        pattern: str = "**/*.py",
        project: str | None = None,
        max_files: int = 100,
    ) -> dict[str, Any]:
        """Parse all code files in a directory and store in knowledge graph.

        Args:
            directory: Directory path to scan
            pattern: Glob pattern (default: Python files)
            project: Optional project name for grouping
            max_files: Maximum files to process (default 100)

        Returns:
            Summary of bulk ingestion results
        """
        from pathlib import Path

        from session_buddy.code_analysis.kg_extractor import KGExtractor

        try:
            extractor = KGExtractor()
            result = await extractor.extract_directory(
                Path(directory),
                pattern=pattern,
                project=project,
                max_files=max_files,
            )
            return {
                "status": "success",
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to ingest directory: {e}")
            return {
                "status": "error",
                "error": str(e),
                "directory": directory,
            }

    @mcp.tool()
    async def code_search_symbols(
        query: str,
        symbol_kind: str | None = None,
        language: str | None = None,
        project: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search for code symbols in the knowledge graph.

        Performs semantic search across stored code entities.

        Args:
            query: Search query (symbol name or pattern)
            symbol_kind: Filter by kind (function, class, method, variable, etc.)
            language: Filter by language (python, go, etc.)
            project: Filter by project name
            limit: Maximum results to return (default 20)

        Returns:
            Matching symbols with context
        """
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        try:
            async with KnowledgeGraphDatabaseAdapter() as kg:
                entities = await kg.search_entities(
                    query=query,
                    entity_type=symbol_kind,
                    limit=limit * 2,  # Get extra for filtering
                )

                # Apply filters
                filtered = []
                for e in entities:
                    props = e.get("properties", {})

                    # Filter by language
                    if language and props.get("language") != language.lower():
                        continue

                    # Filter by project
                    if project and props.get("project") != project:
                        continue

                    filtered.append(e)
                    if len(filtered) >= limit:
                        break

                return {
                    "status": "success",
                    "query": query,
                    "total": len(filtered),
                    "symbols": [
                        {
                            "name": e.get("name", ""),
                            "kind": e.get("entity_type", ""),
                            "file": e.get("properties", {}).get("file_path", ""),
                            "line": e.get("properties", {}).get("line_start", 0),
                            "language": e.get("properties", {}).get("language", ""),
                            "project": e.get("properties", {}).get("project", ""),
                        }
                        for e in filtered
                    ],
                }
        except Exception as e:
            logger.error(f"Failed to search symbols: {e}")
            return {
                "status": "error",
                "error": str(e),
                "query": query,
                "total": 0,
                "symbols": [],
            }

    @mcp.tool()
    async def code_get_symbol_graph(
        symbol_name: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """Get a symbol with its knowledge graph relationships.

        Retrieves a symbol and traverses its relationships to show
        connections like imports, calls, extends, etc.

        Args:
            symbol_name: Name of the symbol to explore
            depth: Relationship traversal depth (max 3)

        Returns:
            Symbol with connected entities and relationships
        """
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        try:
            async with KnowledgeGraphDatabaseAdapter() as kg:
                entities = await kg.search_entities(query=symbol_name, limit=1)

                if not entities:
                    return {
                        "status": "not_found",
                        "error": f"Symbol not found: {symbol_name}",
                    }

                entity = entities[0]
                entity_id = entity.get("id")

                # Get relationships
                relationships = []
                if entity_id:
                    try:
                        relationships = await kg.get_entity_relationships(
                            entity_id,
                            max_depth=min(depth, 3),
                        )
                    except Exception:
                        # Relationships may not be available
                        pass

                return {
                    "status": "success",
                    "symbol": {
                        "name": entity.get("name", ""),
                        "kind": entity.get("entity_type", ""),
                        "properties": entity.get("properties", {}),
                        "observations": entity.get("observations", []),
                    },
                    "relationships": relationships,
                }
        except Exception as e:
            logger.error(f"Failed to get symbol graph: {e}")
            return {
                "status": "error",
                "error": str(e),
                "symbol_name": symbol_name,
            }

    @mcp.tool()
    async def code_list_projects() -> dict[str, Any]:
        """List all projects that have been ingested.

        Returns:
            List of unique project names with file counts
        """
        from session_buddy.adapters.knowledge_graph_adapter import (
            KnowledgeGraphDatabaseAdapter,
        )

        try:
            async with KnowledgeGraphDatabaseAdapter() as kg:
                # Search for all code entities and extract projects
                entities = await kg.search_entities(
                    query="*",  # Wildcard to get all
                    limit=1000,
                )

                projects: dict[str, int] = {}
                for e in entities:
                    props = e.get("properties", {})
                    project = props.get("project")
                    if project:
                        projects[project] = projects.get(project, 0) + 1

                return {
                    "status": "success",
                    "projects": [
                        {"name": name, "file_count": count}
                        for name, count in sorted(projects.items())
                    ],
                    "total_projects": len(projects),
                }
        except Exception as e:
            logger.error(f"Failed to list projects: {e}")
            return {
                "status": "error",
                "error": str(e),
                "projects": [],
            }
