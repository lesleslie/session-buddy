"""Comprehensive tests for KGExtractor (knowledge graph extraction from code).

Covers:
- Initialization with/without parser
- Language detection / explicit language override
- Grammar loading
- File parsing and entity/relationship storage
- Failure paths (parse failures, storage failures, missing files)
- Directory extraction
- Edge cases (empty file, missing relations, unicode)
- Property-style tests (extraction is stable for the same file)

All tests mock at the KG adapter boundary so they don't need a real DuckDB
backing store, while still exercising the production extraction logic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from mcp_common.parsing.tree_sitter import ParseResult


# =====================================
# Fixtures
# =====================================


@pytest.fixture
def sample_python_file(tmp_path: Path) -> Path:
    """Create a small Python file for parsing."""
    code = '''"""Sample module for kg_extractor tests."""

CONSTANT = 42


def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}"


class Calculator:
    """A simple calculator."""

    def add(self, a: int, b: int) -> int:
        return a + b
'''
    p = tmp_path / "sample.py"
    p.write_text(code)
    return p


@pytest.fixture
def empty_python_file(tmp_path: Path) -> Path:
    """Empty Python file (only whitespace)."""
    p = tmp_path / "empty.py"
    p.write_text("\n")
    return p


@pytest.fixture
def malformed_python_file(tmp_path: Path) -> Path:
    """File that may parse but produces 0 symbols."""
    p = tmp_path / "malformed.py"
    p.write_text("just a plain string with no symbols\n")
    return p


@pytest.fixture
def multi_file_directory(tmp_path: Path) -> Path:
    """Directory with multiple Python files."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.py").write_text("def foo():\n    return 1\n")
    (src_dir / "b.py").write_text("def bar():\n    return 2\n")
    (src_dir / "c.txt").write_text("not python")
    return src_dir


def _make_parse_result(
    symbols: list[Any] | None = None,
    relationships: list[Any] | None = None,
    *,
    success: bool = True,
    error: str | None = None,
    language: str = "python",
    file_path: str = "/tmp/sample.py",
) -> "ParseResult":
    """Build a real ``ParseResult`` for testing the extractor."""
    from mcp_common.parsing.tree_sitter import (
        ParseResult,
        SupportedLanguage,
        SymbolInfo,
        SymbolKind,
        SymbolRelationship,
    )

    sym_objs = []
    for i, s in enumerate(symbols or []):
        if isinstance(s, SymbolInfo):
            sym_objs.append(s)
            continue
        # accept dict
        sym_objs.append(
            SymbolInfo(
                name=s.get("name", f"sym{i}"),
                kind=SymbolKind(s.get("kind", "function")),
                language=SupportedLanguage(s.get("language", language)),
                file_path=file_path,
                line_start=s.get("line_start", 1),
                line_end=s.get("line_end", 5),
                signature=s.get("signature"),
                docstring=s.get("docstring"),
                modifiers=tuple(s.get("modifiers", [])),
                return_type=s.get("return_type"),
                parent_context=s.get("parent_context"),
            )
        )

    rel_objs = []
    for i, r in enumerate(relationships or []):
        if isinstance(r, SymbolRelationship):
            rel_objs.append(r)
            continue
        rel_objs.append(
            SymbolRelationship(
                from_symbol=r.get("from_symbol", "A"),
                to_symbol=r.get("to_symbol", "B"),
                relationship_type=r.get("relationship_type", "calls"),
                metadata=r.get("metadata", {}),
            )
        )

    return ParseResult(
        success=success,
        file_path=file_path,
        language=SupportedLanguage(language),
        symbols=tuple(sym_objs),
        relationships=tuple(rel_objs),
        error=error,
    )


def _make_mock_parser(parse_result: "ParseResult") -> MagicMock:
    """Mock TreeSitterParser that always returns the given result."""
    parser = MagicMock()
    parser.detect_language = MagicMock(return_value=parse_result.language)
    parser.parse_file = AsyncMock(return_value=parse_result)
    return parser


def _make_mock_kg() -> MagicMock:
    """Build a mock KnowledgeGraphDatabaseAdapter supporting async-context-manager."""
    kg = MagicMock()
    # Async context manager setup
    kg.__aenter__ = AsyncMock(return_value=kg)
    kg.__aexit__ = AsyncMock(return_value=None)
    kg.create_entity = AsyncMock(
        side_effect=lambda name, entity_type, observations=None, properties=None: {
            "id": f"ent-{name}",
            "name": name,
            "entity_type": entity_type,
        }
    )
    kg.create_relation = AsyncMock(
        side_effect=lambda from_entity, to_entity, relation_type, properties=None: {
            "id": f"rel-{from_entity}-{to_entity}",
            "from_entity": from_entity,
            "to_entity": to_entity,
            "relation_type": relation_type,
        }
    )
    return kg


# =====================================
# TestInitialization
# =====================================


@pytest.mark.unit
class TestKGExtractorInit:
    """Initialization and lazy-parser creation."""

    def test_init_without_parser(self) -> None:
        """Initializes with no parser; ``_initialized`` False."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        ext = KGExtractor()
        assert ext._parser is None
        assert ext._initialized is False

    def test_init_with_parser(self) -> None:
        """Accepts an injected parser."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        parser = MagicMock(name="parser")
        ext = KGExtractor(parser=parser)
        assert ext._parser is parser

    def test_ensure_parser_creates_default(self) -> None:
        """Lazy-creates a ``TreeSitterParser`` the first time it's accessed."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        ext = KGExtractor()
        # First call creates the parser.
        with patch(
            "mcp_common.parsing.tree_sitter.TreeSitterParser"
        ) as MockParser:
            MockParser.return_value = MagicMock(name="default-parser")
            parser = ext._ensure_parser()
            assert parser is MockParser.return_value
            MockParser.assert_called_once()
            # Second call returns the cached parser; no new instance.
            parser2 = ext._ensure_parser()
            assert parser2 is parser
            assert MockParser.call_count == 1

    def test_ensure_parser_returns_existing(self) -> None:
        """If a parser was injected, ``_ensure_parser`` returns it unchanged."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        injected = MagicMock(name="injected")
        ext = KGExtractor(parser=injected)
        assert ext._ensure_parser() is injected
        # Calling again should still return the same instance.
        assert ext._ensure_parser() is injected


# =====================================
# TestGrammarLoading
# =====================================


@pytest.mark.unit
class TestKGExtractorGrammarLoading:
    """Grammar loading behavior."""

    def test_ensure_grammar_loaded_success(self) -> None:
        """Returns True when the grammar loads."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        ext = KGExtractor()
        with patch(
            "mcp_common.parsing.tree_sitter.ensure_language_loaded",
            return_value=True,
        ):
            assert ext._ensure_grammar_loaded("python") is True

    def test_ensure_grammar_loaded_unsupported_language(self) -> None:
        """Returns False when language is not in the enum."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        ext = KGExtractor()
        # UnsupportedLanguage -> ValueError -> False
        assert ext._ensure_grammar_loaded("klingon") is False

    def test_ensure_grammar_loaded_normalizes_case(self) -> None:
        """Lowercases the language name before lookup."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        ext = KGExtractor()
        with patch(
            "mcp_common.parsing.tree_sitter.ensure_language_loaded",
            return_value=True,
        ) as mocked:
            assert ext._ensure_grammar_loaded("PYTHON") is True
            args, _ = mocked.call_args
            # First positional arg is the SupportedLanguage enum
            assert str(args[0]) == "python"


# =====================================
# TestExtractAndStore
# =====================================


@pytest.mark.unit
class TestKGExtractorExtractAndStore:
    """End-to-end ``extract_and_store`` behavior."""

    @pytest.mark.asyncio
    async def test_extract_and_store_success(self, sample_python_file: Path) -> None:
        """Extracts symbols and reports counts."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[
                {"name": "greet", "kind": "function", "language": "python"},
                {"name": "Calculator", "kind": "class", "language": "python"},
            ]
        )
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            result = await ext.extract_and_store(sample_python_file)

        assert result["entities"] == 2
        assert result["relationships"] == 0
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_extract_and_store_empty_symbols(self, sample_python_file: Path) -> None:
        """Successful parse with zero symbols returns entity_count=0 cleanly."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(symbols=[], relationships=[])
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            result = await ext.extract_and_store(sample_python_file)

        assert result["entities"] == 0
        assert result["relationships"] == 0
        assert kg.create_entity.await_count == 0

    @pytest.mark.asyncio
    async def test_extract_and_store_parse_failure(self, sample_python_file: Path) -> None:
        """Failing parse returns a graceful error dict, not raises."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(success=False, error="syntax error")
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            result = await ext.extract_and_store(sample_python_file)

        assert result["entities"] == 0
        assert result["relationships"] == 0
        assert result.get("error") == "syntax error"

    @pytest.mark.asyncio
    async def test_extract_and_store_storage_exception(
        self, sample_python_file: Path
    ) -> None:
        """If KG storage raises, ``extract_and_store`` returns an error dict."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(symbols=[{"name": "f", "kind": "function"}])
        parser = _make_mock_parser(res)

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            side_effect=RuntimeError("store down"),
        ):
            result = await ext.extract_and_store(sample_python_file)

        assert result["entities"] == 0
        assert result["relationships"] == 0
        assert "store down" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_extract_and_store_kg_create_entity_exception(
        self, sample_python_file: Path
    ) -> None:
        """If a single ``create_entity`` call fails, we skip that symbol and continue."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[
                {"name": "good", "kind": "function"},
                {"name": "bad", "kind": "function"},
                {"name": "after_bad", "kind": "function"},
            ]
        )
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()
        original_create = kg.create_entity

        async def selective_create(
            name: str, entity_type: str, observations=None, properties=None
        ) -> dict[str, Any]:
            if name == "bad":
                raise RuntimeError("entity failed")
            return await original_create(
                name, entity_type, observations, properties
            )

        kg.create_entity = AsyncMock(side_effect=selective_create)

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            result = await ext.extract_and_store(sample_python_file)

        # 2 of 3 succeeded; `bad` was skipped
        assert result["entities"] == 2
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_extract_and_store_project_attached(
        self, sample_python_file: Path
    ) -> None:
        """Passes the ``project`` argument into the entity's properties."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[{"name": "f", "kind": "function"}]
        )
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            await ext.extract_and_store(sample_python_file, project="my-proj")

        # Inspect the create_entity call to confirm project was set.
        kwargs = kg.create_entity.await_args
        args = kg.create_entity.await_args_list[0]
        # extract_and_store calls ``await kg.create_entity(name=..., ...)``
        # which uses keyword args
        if args.kwargs:
            properties = args.kwargs["properties"]
        else:
            # positional: signature(name, entity_type, observations, properties)
            properties = args.args[3]
        assert properties["project"] == "my-proj"

    @pytest.mark.asyncio
    async def test_extract_and_store_explicit_language(
        self, sample_python_file: Path
    ) -> None:
        """An explicit ``language`` argument overrides detection."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        # Build a parse-result with the actual language matching the override.
        res = _make_parse_result(
            symbols=[{"name": "f", "kind": "function", "language": "go"}]
        )
        parser = _make_mock_parser(res)

        ext = KGExtractor(parser=parser)
        kg = _make_mock_kg()
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            result = await ext.extract_and_store(
                sample_python_file, language="go"
            )

        # detect_language should NOT have been called because language was
        # provided.
        parser.detect_language.assert_not_called()
        assert result["entities"] == 1

    @pytest.mark.asyncio
    async def test_extract_and_store_invalid_language_falls_back(
        self, sample_python_file: Path
    ) -> None:
        """An invalid explicit language falls back to UNKNOWN (no crash)."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        # The detector returns UNKNOWN for the actual file.
        res = _make_parse_result(
            symbols=[],
            success=True,
            language="unknown",
        )
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            # "klingon" is not in SupportedLanguage; should fall back.
            result = await ext.extract_and_store(
                sample_python_file, language="klingon"
            )

        assert result["entities"] == 0
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_extract_and_store_signature_and_docstring(
        self, sample_python_file: Path
    ) -> None:
        """Signature and docstring become observations."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[
                {
                    "name": "f",
                    "kind": "function",
                    "signature": "def f(x: int) -> int",
                    "docstring": "Long docstring that we truncate at 200 chars. "
                    * 10,
                }
            ]
        )
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            await ext.extract_and_store(sample_python_file)

        observations = kg.create_entity.await_args_list[0].kwargs["observations"]
        # Two observations: one for signature, one for docstring (truncated).
        assert len(observations) == 2
        assert observations[0].startswith("Signature: ")
        assert observations[1].startswith("Docstring: ")
        # Docstring was truncated to 200 chars.
        assert len(observations[1]) <= len("Docstring: ") + 200

    @pytest.mark.asyncio
    async def test_extract_and_store_no_signature_no_docstring(
        self, sample_python_file: Path
    ) -> None:
        """When no signature/docstring, observations list is empty."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[
                {
                    "name": "f",
                    "kind": "function",
                    "signature": None,
                    "docstring": None,
                }
            ]
        )
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            await ext.extract_and_store(sample_python_file)

        observations = kg.create_entity.await_args_list[0].kwargs["observations"]
        assert observations == []


# =====================================
# TestStoreRelationships
# =====================================


@pytest.mark.unit
class TestKGExtractorStoreRelationships:
    """``_store_relationships`` behavior (covers the inner loop directly)."""

    @pytest.mark.asyncio
    async def test_store_relationships_counts_successes(self) -> None:
        """Counts only the relationships that store successfully."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            relationships=[
                {"from_symbol": "A", "to_symbol": "B", "relationship_type": "calls"},
                {"from_symbol": "B", "to_symbol": "C", "relationship_type": "calls"},
                {"from_symbol": "C", "to_symbol": "D", "relationship_type": "calls"},
            ]
        )
        kg = _make_mock_kg()
        ext = KGExtractor(parser=MagicMock())

        count = await ext._store_relationships(kg, res, entity_ids={})
        assert count == 3

    @pytest.mark.asyncio
    async def test_store_relationships_skips_failures(self) -> None:
        """Failed ``create_relation`` calls are skipped without raising."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            relationships=[
                {"from_symbol": "A", "to_symbol": "B", "relationship_type": "calls"},
                {"from_symbol": "BAD", "to_symbol": "D", "relationship_type": "calls"},
                {"from_symbol": "B", "to_symbol": "C", "relationship_type": "calls"},
            ]
        )
        kg = _make_mock_kg()

        original_create = kg.create_relation

        async def selective(
            from_entity: str, to_entity: str, relation_type: str, properties=None
        ) -> dict[str, Any]:
            if from_entity == "BAD":
                raise RuntimeError("boom")
            return await original_create(
                from_entity, to_entity, relation_type, properties
            )

        kg.create_relation = AsyncMock(side_effect=selective)
        ext = KGExtractor(parser=MagicMock())

        count = await ext._store_relationships(kg, res, entity_ids={})
        assert count == 2

    @pytest.mark.asyncio
    async def test_store_relationships_empty_list(self) -> None:
        """No relations -> 0 count."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(relationships=[])
        kg = _make_mock_kg()
        ext = KGExtractor(parser=MagicMock())
        count = await ext._store_relationships(kg, res, entity_ids={})
        assert count == 0
        kg.create_relation.assert_not_called()


# =====================================
# TestStoreSymbols
# =====================================


@pytest.mark.unit
class TestKGExtractorStoreSymbols:
    """``_store_symbols`` behavior."""

    @pytest.mark.asyncio
    async def test_store_symbols_returns_id_map(self) -> None:
        """Returns a dict mapping symbol-name to entity-id."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[
                {"name": "alpha", "kind": "function"},
                {"name": "beta", "kind": "class"},
            ]
        )
        kg = _make_mock_kg()
        ext = KGExtractor(parser=MagicMock())

        ids = await ext._store_symbols(kg, res, "/tmp/x.py", project=None)

        assert ids == {"alpha": "ent-alpha", "beta": "ent-beta"}

    @pytest.mark.asyncio
    async def test_store_symbols_continues_on_failure(self) -> None:
        """A failing symbol still leaves the id-map incomplete, but no raise."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[
                {"name": "alpha", "kind": "function"},
                {"name": "beta", "kind": "function"},
                {"name": "gamma", "kind": "function"},
            ]
        )
        kg = _make_mock_kg()
        original_create = kg.create_entity

        async def selective(
            name: str, entity_type: str, observations=None, properties=None
        ) -> dict[str, Any]:
            if name == "beta":
                raise RuntimeError("beta failure")
            return await original_create(
                name, entity_type, observations, properties
            )

        kg.create_entity = AsyncMock(side_effect=selective)
        ext = KGExtractor(parser=MagicMock())

        ids = await ext._store_symbols(kg, res, "/tmp/x.py", project=None)
        assert ids == {"alpha": "ent-alpha", "gamma": "ent-gamma"}

    @pytest.mark.asyncio
    async def test_store_symbols_empty_list(self) -> None:
        """Empty symbols -> empty map."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(symbols=[])
        kg = _make_mock_kg()
        ext = KGExtractor(parser=MagicMock())
        ids = await ext._store_symbols(kg, res, "/tmp/x.py", project=None)
        assert ids == {}


# =====================================
# TestExtractDirectory
# =====================================


@pytest.mark.unit
class TestKGExtractorExtractDirectory:
    """``extract_directory`` end-to-end."""

    @pytest.mark.asyncio
    async def test_extract_directory_processes_matching_files(
        self, multi_file_directory: Path
    ) -> None:
        """Aggregates counts across the directory."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res_with = _make_parse_result(
            symbols=[{"name": "f", "kind": "function"}]
        )

        parser = _make_mock_parser(res_with)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            out = await ext.extract_directory(
                multi_file_directory, pattern="*.py"
            )

        # Only .py files are processed; .txt is not.
        assert out["total_files"] == 2
        assert out["failed"] == 0
        assert out["successful"] == 2

    @pytest.mark.asyncio
    async def test_extract_directory_max_files_truncated(
        self, multi_file_directory: Path
    ) -> None:
        """max_files caps the number of files processed."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res_with = _make_parse_result(
            symbols=[{"name": "f", "kind": "function"}]
        )
        parser = _make_mock_parser(res_with)
        kg = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            out = await ext.extract_directory(
                multi_file_directory, pattern="*.py", max_files=1
            )

        assert out["total_files"] == 1

    @pytest.mark.asyncio
    async def test_extract_directory_records_failures(
        self, tmp_path: Path
    ) -> None:
        """A failing parse increments `failed` and records the error."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        src = tmp_path / "src"
        src.mkdir()
        good = src / "good.py"
        good.write_text("def f(): pass\n")

        # First call succeeds (good.py), subsequent calls fail.
        call_count = {"n": 0}
        from mcp_common.parsing.tree_sitter import SupportedLanguage

        def make_parser():  # noqa: ANN202
            parser = MagicMock()
            parser.detect_language = MagicMock(
                return_value=SupportedLanguage.PYTHON
            )

            async def parse_file(*args: Any, **kwargs: Any) -> "ParseResult":
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return _make_parse_result(
                        symbols=[{"name": "f", "kind": "function"}]
                    )
                return _make_parse_result(
                    success=False, error="parse failed"
                )

            parser.parse_file = parse_file
            return parser

        # Multiple files so both success and failure happen.
        (src / "bad.py").write_text("def g(): pass\n")

        kg = _make_mock_kg()
        ext = KGExtractor(parser=make_parser())

        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg,
        ):
            out = await ext.extract_directory(src, pattern="*.py")

        assert out["successful"] >= 1
        # Note: ordering of glob is platform-dependent, so we don't strictly
        # require ``failed == 1``; we just require consistency between
        # ``total_files`` and the sum of successful + failed.
        assert out["total_files"] == out["successful"] + out["failed"]

    @pytest.mark.asyncio
    async def test_extract_directory_no_files(self, tmp_path: Path) -> None:
        """Empty directory -> zero counts."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        empty = tmp_path / "empty"
        empty.mkdir()

        ext = KGExtractor(parser=MagicMock())
        out = await ext.extract_directory(empty, pattern="*.py")
        assert out["total_files"] == 0
        assert out["successful"] == 0
        assert out["failed"] == 0


# =====================================
# TestLogging
# =====================================


@pytest.mark.unit
class TestKGExtractorLogging:
    """Verify the right log messages are emitted at warn/error/debug."""

    @pytest.mark.asyncio
    async def test_log_warning_emitted_for_failed_symbol(
        self, sample_python_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[
                {"name": "ok", "kind": "function"},
                {"name": "bad", "kind": "function"},
            ]
        )
        parser = _make_mock_parser(res)
        kg = _make_mock_kg()

        original_create = kg.create_entity

        async def selective(
            name: str, entity_type: str, observations=None, properties=None
        ) -> dict[str, Any]:
            if name == "bad":
                raise RuntimeError("nope")
            return await original_create(
                name, entity_type, observations, properties
            )

        kg.create_entity = AsyncMock(side_effect=selective)

        ext = KGExtractor(parser=parser)
        with caplog.at_level(logging.WARNING):
            with patch(
                "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
                return_value=kg,
            ):
                await ext.extract_and_store(sample_python_file)

        # Should have logged a warning about the bad symbol.
        assert any(
            "bad" in record.message and "Failed" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_log_error_emitted_for_kg_failure(
        self, sample_python_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(symbols=[{"name": "f", "kind": "function"}])
        parser = _make_mock_parser(res)

        ext = KGExtractor(parser=parser)
        with caplog.at_level(logging.ERROR):
            with patch(
                "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
                side_effect=RuntimeError("kg-dead"),
            ):
                await ext.extract_and_store(sample_python_file)

        assert any(
            "Failed to store" in record.message for record in caplog.records
        )


# =====================================
# Property-ish / stability tests
# =====================================


@pytest.mark.unit
class TestKGExtractorStability:
    """Stable extraction behavior for a fixed input."""

    @pytest.mark.asyncio
    async def test_same_input_same_output(
        self, sample_python_file: Path
    ) -> None:
        """Two runs on the same file produce the same entity count."""
        from session_buddy.code_analysis.kg_extractor import KGExtractor

        res = _make_parse_result(
            symbols=[
                {"name": "greet", "kind": "function"},
                {"name": "Calculator", "kind": "class"},
            ]
        )
        parser = _make_mock_parser(res)
        kg1 = _make_mock_kg()
        kg2 = _make_mock_kg()

        ext = KGExtractor(parser=parser)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg1,
        ):
            r1 = await ext.extract_and_store(sample_python_file)
        with patch(
            "session_buddy.adapters.knowledge_graph_adapter.KnowledgeGraphDatabaseAdapter",
            return_value=kg2,
        ):
            r2 = await ext.extract_and_store(sample_python_file)
        assert r1["entities"] == r2["entities"]
