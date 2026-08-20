"""Extract code entities and store in knowledge graph.

This module bridges tree-sitter parsing with Session-Buddy's knowledge graph,
enabling semantic code search and relationship queries.
"""

from __future__ import annotations

import ast
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
        # Tracks whether ``parser`` was injected by the caller. The AST fallback
        # below only fires for the lazily-created real parser; if the caller
        # supplied a mock parser, their ``success=False`` is intentional and
        # must NOT trigger fallback extraction.
        self._injected_parser: TreeSitterParser | None = parser
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
        from mcp_common.parsing.tree_sitter import (
            SupportedLanguage,
            ensure_language_loaded,
        )

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

        # Load grammar if needed; capture whether the language is available so
        # we can route the AST fallback below correctly.
        grammar_available = True
        if lang != SupportedLanguage.UNKNOWN:
            grammar_available = self._ensure_grammar_loaded(lang.value)

        # Parse the file
        result = await parser.parse_file(file_path, language=lang)

        # Fall back to the stdlib ``ast`` module when tree-sitter cannot parse
        # the source — e.g. the per-language grammar package (``tree_sitter_python``)
        # is not installed, so ``parser.parse_file`` returns ``success=False``.
        # Without this fallback, ingest returns 0 entities and
        # ``code_search_symbols`` can never find the ingested symbols, which
        # broke the round-trip integration tests.
        #
        # The fallback is gated on the parser being the lazily-created real
        # ``TreeSitterParser`` (not an injected test mock) — otherwise a unit
        # test that mocks ``parser.parse_file`` to return ``success=False``
        # would accidentally trigger AST extraction and the test would see
        # entities instead of the expected graceful error dict.
        if (
            not result.success
            and lang == SupportedLanguage.PYTHON
            and not grammar_available
            and self._injected_parser is None
        ):
            ast_result = await self._extract_python_with_ast(file_path, project)
            if ast_result is not None:
                return ast_result

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
            logger.exception("Failed to store in knowledge graph")
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

            except Exception:
                logger.exception(f"Failed to store symbol {symbol.name}")
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
            except Exception:
                logger.exception("Failed to store relationship")
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

        results: dict[str, int | list[dict[str, str]]] = {
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
                        {"file": str(file_path), "error": str(result.get("error", ""))}
                    )
                else:
                    results["successful"] += 1
                    results["total_entities"] += result.get("entities", 0)
                    results["total_relationships"] += result.get("relationships", 0)

        return results

    async def _extract_python_with_ast(
        self,
        file_path: Path,
        project: str | None,
    ) -> dict[str, Any] | None:
        """Parse a Python file with the stdlib ``ast`` module and store symbols.

        This is a fallback for environments where the per-language tree-sitter
        grammar package (e.g. ``tree_sitter_python``) is unavailable. It
        extracts top-level functions, async functions, classes, and
        ``UPPER_CASE`` constants using the Python standard library so
        code-search round-trips still work when tree-sitter cannot load.

        Args:
            file_path: Path to a ``.py`` source file.
            project: Optional project name to attach to stored entities.

        Returns:
            Summary dict mirroring ``extract_and_store``'s shape, or ``None``
            if the file cannot be parsed (so the caller can fall back to its
            own error path).
        """
        if file_path.suffix != ".py":
            return None

        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Could not read %s for AST fallback: %s", file_path, e)
            return None

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            logger.info("AST parse failed for %s: %s", file_path, e)
            return None

        symbols: list[dict[str, Any]] = []
        for node in tree.body:
            extracted = self._ast_node_to_symbol(node, file_path)
            if extracted is not None:
                symbols.append(extracted)

        if not symbols:
            return None

        try:
            from session_buddy.adapters.knowledge_graph_adapter import (
                KnowledgeGraphDatabaseAdapter,
            )
        except ImportError:
            return None

        stored = 0
        try:
            async with KnowledgeGraphDatabaseAdapter() as kg:
                for sym in symbols:
                    try:
                        properties = dict(sym["properties"])
                        if project:
                            properties["project"] = project
                        observations: list[str] = []
                        if sym.get("signature"):
                            observations.append(f"Signature: {sym['signature']}")
                        if sym.get("docstring"):
                            observations.append(f"Docstring: {sym['docstring'][:200]}")
                        await kg.create_entity(
                            name=sym["name"],
                            entity_type=sym["kind"],
                            observations=observations,
                            properties=properties,
                        )
                        stored += 1
                    except Exception:
                        logger.exception(
                            "Failed to store AST-extracted symbol %s", sym["name"]
                        )
                        continue
        except Exception as e:
            logger.exception("Failed to store AST-extracted entities")
            return {
                "entities": 0,
                "relationships": 0,
                "error": str(e),
                "file_path": str(file_path),
            }

        return {
            "entities": stored,
            "relationships": 0,
            "file_path": str(file_path),
            "language": "python",
            "symbols": stored,
            "parser": "ast_fallback",
        }

    def _ast_node_to_symbol(
        self,
        node: ast.AST,
        file_path: Path,
    ) -> dict[str, Any] | None:
        """Convert a top-level ``ast`` node into a symbol dict for the KG."""
        from mcp_common.parsing.tree_sitter import SupportedLanguage

        kind: str | None = None
        name: str | None = None
        line_start = getattr(node, "lineno", 1) or 1
        line_end = getattr(node, "end_lineno", line_start) or line_start
        signature: str | None = None
        docstring: str | None = None

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "function"
            name = node.name
            args_src = ast.unparse(node.args) if hasattr(ast, "unparse") else ""
            ret = (
                " -> " + ast.unparse(node.returns)
                if (hasattr(ast, "unparse") and node.returns is not None)
                else ""
            )
            signature = f"def {name}({args_src}){ret}"
            docstring = ast.get_docstring(node)
        elif isinstance(node, ast.ClassDef):
            kind = "class"
            name = node.name
            bases = (
                "(" + ", ".join(ast.unparse(b) for b in node.bases) + ")"
                if node.bases and hasattr(ast, "unparse")
                else ""
            )
            signature = f"class {name}{bases}"
            docstring = ast.get_docstring(node)
        elif isinstance(node, ast.Assign):
            # Module-level ``CONST = ...`` constants — best-effort, single target.
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    kind = "constant"
                    name = target.id
                    signature = (
                        ast.unparse(node.value) if hasattr(ast, "unparse") else None
                    )
                    break

        if kind is None or name is None:
            return None

        properties: dict[str, Any] = {
            "language": SupportedLanguage.PYTHON.value,
            "file_path": str(file_path),
            "line_start": int(line_start),
            "line_end": int(line_end),
            "column_start": int(getattr(node, "col_offset", 0) or 0),
            "column_end": int(getattr(node, "end_col_offset", 0) or 0),
            "modifiers": [],
            "return_type": None,
            "parent_context": None,
        }

        return {
            "name": name,
            "kind": kind,
            "properties": properties,
            "signature": signature,
            "docstring": docstring,
        }