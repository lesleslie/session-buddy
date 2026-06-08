"""Round-trip integration tests for code indexing.

These tests exercise the full code-indexing pipeline end-to-end:

    write Python file  →  code_ingest_file  →  KnowledgeGraph
                                                    ↓
                            code_search_symbols  ←  ←

The earlier ``_get_conn`` regression slipped through because no test
exercised this round-trip. A single assertion here ("ingest a file
with a known symbol, search for it, find it") would have caught the
production bug at CI time. These tests are that assertion.

The tests use real DuckDB and real DuckPGQ knowledge-graph storage
via the autouse ``isolated_test_db_path`` fixture in ``tests/conftest.py``.
They do NOT mock the adapter, the extractor, or the search index.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from session_buddy.mcp.tools.code_analysis.tools import (
    _code_ingest_directory_impl,
    _code_ingest_file_impl,
    _code_search_symbols_impl,
)


pytestmark = pytest.mark.asyncio(scope="function")


class TestCodeIndexingRoundTrip:
    """End-to-end tests for the code-indexing MCP tools."""

    async def test_ingest_file_then_search_finds_symbol(self, tmp_path: Path) -> None:
        """Ingesting a real Python file should make its symbols searchable.

        Regression guard for the ``_get_conn`` AttributeError that crashed
        ``code_search_symbols`` in production.
        """
        marker = f"RoundTripMarker_{uuid.uuid4().hex[:8]}"
        src = f"""\
def {marker}():
    return 42


class {marker}Class:
    '''A test class named after the same marker.'''
    def method(self):
        return {marker}()
"""
        target = tmp_path / f"{marker}.py"
        target.write_text(src)
        project_name = f"round_trip_{uuid.uuid4().hex[:6]}"

        ingest_result = await _code_ingest_file_impl(
            str(target), project=project_name
        )
        assert ingest_result.get("status") == "success", (
            f"Ingest failed: {ingest_result}"
        )

        search = await _code_search_symbols_impl(
            marker, project=project_name, limit=10
        )
        # The round-trip is the assertion: a symbol that was just
        # ingested MUST be findable by search.
        assert search.get("status") == "success", f"Search failed: {search}"
        assert search.get("total", 0) >= 1, (
            f"Expected at least 1 hit for {marker!r}, got {search}"
        )
        names = {s.get("name") for s in search.get("symbols", [])}
        assert marker in names, (
            f"Symbol {marker!r} missing from search results {names!r}"
        )

    async def test_ingested_symbol_persists_across_adapter_instances(
        self, tmp_path: Path
    ) -> None:
        """Indexed data must survive adapter restart (separate connection)."""
        marker = f"PersistenceMarker_{uuid.uuid4().hex[:8]}"
        target = tmp_path / f"{marker}.py"
        target.write_text(f"def {marker}():\n    return 'persisted'\n")
        project_name = f"persist_{uuid.uuid4().hex[:6]}"

        # Ingest via the MCP tool.
        ingest = await _code_ingest_file_impl(
            str(target), project=project_name
        )
        assert ingest.get("status") == "success", ingest

        # Search via a brand-new search call (which internally reopens
        # the DuckDB connection). The autouse isolated_test_db_path
        # fixture makes sure we're using the same on-disk DB across
        # both tool invocations.
        search = await _code_search_symbols_impl(
            marker, project=project_name, limit=5
        )
        names = {s.get("name") for s in search.get("symbols", [])}
        assert marker in names, (
            f"Symbol {marker!r} did not persist across calls: {names!r}"
        )

    async def test_ingest_directory_then_search_finds_all_files(
        self, tmp_path: Path
    ) -> None:
        """Ingesting a directory of Python files should make ALL symbols searchable."""
        markers = [
            f"DirMarker_{uuid.uuid4().hex[:6]}_{i}" for i in range(3)
        ]
        project_name = f"dir_round_trip_{uuid.uuid4().hex[:6]}"

        # Write three files, each with a unique marker symbol.
        for i, marker in enumerate(markers):
            (tmp_path / f"file_{i}.py").write_text(
                f"def {marker}():\n    return {i}\n"
            )
        # Add a non-Python file to confirm pattern filtering.
        (tmp_path / "readme.txt").write_text("not a python file")

        result = await _code_ingest_directory_impl(
            str(tmp_path), pattern="**/*.py", project=project_name, max_files=10
        )
        assert result.get("status") == "success", (
            f"Directory ingest failed: {result}"
        )

        # Each marker should be findable.
        for marker in markers:
            search = await _code_search_symbols_impl(
                marker, project=project_name, limit=5
            )
            names = {s.get("name") for s in search.get("symbols", [])}
            assert marker in names, (
                f"Directory-ingest marker {marker!r} missing: {names!r}"
            )

    async def test_search_for_nonexistent_symbol_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """Searching for a symbol that was never ingested should return 0 hits cleanly.

        This is the inverse of the round-trip: a missing symbol must NOT
        raise (the bug we hit when ``_get_conn`` was missing) — it must
        just return an empty result.
        """
        bogus = f"NeverExisted_{uuid.uuid4().hex[:8]}"
        search = await _code_search_symbols_impl(
            bogus, project=f"empty_{uuid.uuid4().hex[:6]}", limit=5
        )
        assert search.get("status") == "success", search
        assert search.get("total", 0) == 0
        assert search.get("symbols", []) == []
