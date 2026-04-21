from pathlib import Path
from typing import Any


async def _code_ingest_file_impl(
    file_path: str, project: str | None = None, language: str | None = None
) -> dict[str, Any]:
    """Parse a code file and store entities in knowledge graph."""
    from session_buddy.code_analysis.kg_extractor import KGExtractor

    try:
        extractor = KGExtractor()
        result = await extractor.extract_and_store(
            Path(file_path), project=project, language=language
        )
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Failed to ingest file: {e}")
        return {"status": "error", "error": str(e), "file_path": file_path}


async def _code_ingest_directory_impl(
    directory: str,
    pattern: str = "**/*.py",
    project: str | None = None,
    max_files: int = 100,
) -> dict[str, Any]:
    """Parse all code files in a directory and store in knowledge graph."""
    from session_buddy.code_analysis.kg_extractor import KGExtractor

    try:
        extractor = KGExtractor()
        result = await extractor.extract_directory(
            Path(directory), pattern=pattern, project=project, max_files=max_files
        )
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Failed to ingest directory: {e}")
        return {"status": "error", "error": str(e), "directory": directory}


async def _code_search_symbols_impl(
    query: str,
    symbol_kind: str | None = None,
    language: str | None = None,
    project: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search for code symbols in the knowledge graph."""
    from session_buddy.adapters.knowledge_graph_adapter import (
        KnowledgeGraphDatabaseAdapter,
    )

    try:
        async with KnowledgeGraphDatabaseAdapter() as kg:
            entities = await kg.search_entities(
                query=query, entity_type=symbol_kind, limit=limit * 2
            )
            filtered = []
            for e in entities:
                props = e.get("properties", {})
                if language and props.get("language") != language.lower():
                    continue
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


async def _code_get_symbol_graph_impl(
    symbol_name: str, depth: int = 2
) -> dict[str, Any]:
    """Get a symbol with its knowledge graph relationships."""
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
            relationships = []
            if entity_id:
                try:
                    relationships = await kg.get_entity_relationships(
                        entity_id, max_depth=min(depth, 3)
                    )
                except Exception:
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
        return {"status": "error", "error": str(e), "symbol_name": symbol_name}


async def _code_list_projects_impl() -> dict[str, Any]:
    """List all projects that have been ingested."""
    from session_buddy.adapters.knowledge_graph_adapter import (
        KnowledgeGraphDatabaseAdapter,
    )

    try:
        async with KnowledgeGraphDatabaseAdapter() as kg:
            entities = await kg.search_entities(query="*", limit=1000)
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
        return {"status": "error", "error": str(e), "projects": []}


def register_code_analysis_tools(mcp: FastMCP) -> None:
    """Register 3 code analysis tools for Session-Buddy.

    Args:
        mcp: FastMCP server instance"""
    "Register 3 code analysis tools for Session-Buddy.\n\n    Args:\n        mcp: FastMCP server instance\n    "
    mcp.tool()(_code_ingest_file_impl)
    mcp.tool()(_code_ingest_directory_impl)
    mcp.tool()(_code_search_symbols_impl)
    mcp.tool()(_code_get_symbol_graph_impl)
    mcp.tool()(_code_list_projects_impl)
