"""Extract code entities and store in knowledge graph.

This module bridges tree-sitter parsing with Session-Buddy's knowledge graph,
enabling semantic code search and relationship queries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_common.parsing.tree_sitter import ParseResult, TreeSitterParser

logger = logging.getLogger(__name__)


class KGExtractor:
    """Bridge between tree-sitter parsing and knowledge graph storage.

    Parses source files using tree-sitter and stores extracted symbols,
    relationships, and metadata in the knowledge graph for semantic queries.

    Example:
        >>> extractor = KGExtractor()
        >>> result = await extractor.extract_and_store(Path("example.py"))
        >>> print(f"Stored {result['entities']} entities")
    """

    def __init__(self, parser: TreeSitterParser | None = None) -> None:
        """Initialize the extractor.

        Args:
            parser: Optional TreeSitterParser instance (lazy-created if not provided)
        """
        self._parser = parser
        self._initialized = False

    def _ensure_parser(self) -> TreeSitterParser:
        """Ensure parser is initialized."""
        if self._parser is None:
            from mcp_common.parsing.tree_sitter import TreeSitterParser

            self._parser = TreeSitterParser()
        return self._parser

    def _ensure_grammar_loaded(self, language: str) -> bool:
        """Ensure grammar is loaded for the given language.

        Args:
            language: Language name (python, go, etc.)

        Returns:
            True if grammar is available
        """
        from mcp_common.parsing.tree_sitter import SupportedLanguage, ensure_language_loaded

        try:
            lang = SupportedLanguage(language.lower())
            return ensure_language_loaded(lang)
        except ValueError:
            return False

    async def extract_and_store(
        self,
        file_path: Path,
        project: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Parse file and store entities in knowledge graph.

        Args:
            file_path: Path to source file
            project: Optional project name for grouping
            language: Optional language override (auto-detected if not provided)

        Returns:
            Summary with counts of entities and relationships stored
        """
        from mcp_common.parsing.tree_sitter import SupportedLanguage

        parser = self._ensure_parser()

        # Detect language if not provided
        if language:
            try:
                lang = SupportedLanguage(language.lower())
            except ValueError:
                lang = SupportedLanguage.UNKNOWN
        else:
            lang = parser.detect_language(file_path)

        # Load grammar if needed
        if lang != SupportedLanguage.UNKNOWN:
            self._ensure_grammar_loaded(lang.value)

        # Parse the file
        result = await parser.parse_file(file_path, language=lang)

        if not result.success:
            return {
                "entities": 0,
                "relationships": 0,
                "error": result.error,
                "file_path": str(file_path),
            }

        # Store in knowledge graph
        try:
            from session_buddy.adapters.knowledge_graph_adapter import (
                KnowledgeGraphDatabaseAdapter,
            )

            async with KnowledgeGraphDatabaseAdapter() as kg:
                entity_ids = await self._store_symbols(
                    kg, result, str(file_path), project
                )
                relationship_count = await self._store_relationships(
                    kg, result, entity_ids
                )

            return {
                "entities": len(entity_ids),
                "relationships": relationship_count,
                "file_path": str(file_path),
                "language": result.language.value,
                "symbols": len(result.symbols),
            }

        except Exception as e:
            logger.error(f"Failed to store in knowledge graph: {e}")
            return {
                "entities": 0,
                "relationships": 0,
                "error": str(e),
                "file_path": str(file_path),
            }

    async def _store_symbols(
        self,
        kg: Any,
        result: ParseResult,
        file_path: str,
        project: str | None,
    ) -> dict[str, str]:
        """Store symbols in knowledge graph.

        Args:
            kg: Knowledge graph adapter
            result: Parse result with symbols
            file_path: File path for context
            project: Optional project name

        Returns:
            Dict mapping symbol names to entity IDs
        """
        entity_ids: dict[str, str] = {}

        for symbol in result.symbols:
            try:
                observations = []
                if symbol.signature:
                    observations.append(f"Signature: {symbol.signature}")
                if symbol.docstring:
                    observations.append(f"Docstring: {symbol.docstring[:200]}")

                properties: dict[str, Any] = {
                    "language": symbol.language.value,
                    "file_path": file_path,
                    "line_start": symbol.line_start,
                    "line_end": symbol.line_end,
                    "column_start": symbol.column_start,
                    "column_end": symbol.column_end,
                    "modifiers": list(symbol.modifiers),
                    "return_type": symbol.return_type,
                    "parent_context": symbol.parent_context,
                }

                if project:
                    properties["project"] = project

                entity = await kg.create_entity(
                    name=symbol.name,
                    entity_type=symbol.kind.value,
                    observations=observations,
                    properties=properties,
                )
                entity_ids[symbol.name] = entity.get("id", "")

            except Exception as e:
                logger.warning(f"Failed to store symbol {symbol.name}: {e}")
                continue

        return entity_ids

    async def _store_relationships(
        self,
        kg: Any,
        result: ParseResult,
        entity_ids: dict[str, str],
    ) -> int:
        """Store relationships in knowledge graph.

        Args:
            kg: Knowledge graph adapter
            result: Parse result with relationships
            entity_ids: Map of symbol names to entity IDs

        Returns:
            Number of relationships stored
        """
        count = 0

        for rel in result.relationships:
            try:
                await kg.create_relation(
                    from_entity=rel.from_symbol,
                    to_entity=rel.to_symbol,
                    relation_type=rel.relationship_type,
                    properties=rel.metadata,
                )
                count += 1
            except Exception as e:
                logger.debug(f"Failed to store relationship: {e}")
                continue

        return count

    async def extract_directory(
        self,
        directory: Path,
        pattern: str = "**/*.py",
        project: str | None = None,
        max_files: int = 100,
    ) -> dict[str, Any]:
        """Extract and store all files in a directory.

        Args:
            directory: Directory to scan
            pattern: Glob pattern for files
            project: Optional project name
            max_files: Maximum files to process

        Returns:
            Summary of extraction results
        """
        files = list(directory.glob(pattern))[:max_files]

        results = {
            "total_files": len(files),
            "successful": 0,
            "failed": 0,
            "total_entities": 0,
            "total_relationships": 0,
            "errors": [],
        }

        for file_path in files:
            if file_path.is_file():
                result = await self.extract_and_store(file_path, project=project)
                if "error" in result and result.get("entities", 0) == 0:
                    results["failed"] += 1
                    results["errors"].append(
                        {"file": str(file_path), "error": result.get("error")}
                    )
                else:
                    results["successful"] += 1
                    results["total_entities"] += result.get("entities", 0)
                    results["total_relationships"] += result.get("relationships", 0)

        return results
