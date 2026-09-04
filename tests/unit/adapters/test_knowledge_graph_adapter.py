"""Tests for the compatibility-shim ``session_buddy.adapters.knowledge_graph_adapter``.

The module is a thin re-export shim that aliases
``KnowledgeGraphDatabaseAdapterOneiric`` to the historical name
``KnowledgeGraphDatabaseAdapter`` so callers using the old import path
continue to work after the Oneiric refactor.

This file uses a **normal** import of the module (NOT
``importlib.util.spec_from_file_location``) so that coverage.py can observe
the executed lines:

* module docstring (executed at import)
* ``from __future__ import annotations``
* ``from session_buddy.adapters.knowledge_graph_adapter_oneiric import ...``
* ``__all__ = ["KnowledgeGraphDatabaseAdapter"]``

The test below verifies that:

1. The public name exists on the module.
2. The public name is an alias for the Oneiric class (identity, not just
   equality).
3. ``__all__`` is exactly ``["KnowledgeGraphDatabaseAdapter"]``.
4. Instantiation flows through the alias to the Oneiric implementation
   (this also exercises the duckdb-backed ``_initialized`` and ``close``
   paths without requiring a live DB by using an in-memory adapter).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import session_buddy.adapters.knowledge_graph_adapter as kg_shim
from session_buddy.adapters.knowledge_graph_adapter import (
    KnowledgeGraphDatabaseAdapter,
)
from session_buddy.adapters.knowledge_graph_adapter_oneiric import (
    KnowledgeGraphDatabaseAdapterOneiric,
)


class TestShimPublicSurface:
    """Verify the re-export shim's public surface."""

    def test_knowledge_graph_database_adapter_attribute_exists(self) -> None:
        """The shim exposes ``KnowledgeGraphDatabaseAdapter`` as a module attribute."""
        assert hasattr(kg_shim, "KnowledgeGraphDatabaseAdapter")

    def test_knowledge_graph_database_adapter_is_aliased_class(self) -> None:
        """``KnowledgeGraphDatabaseAdapter`` is the Oneiric class (identity)."""
        # Identity check — the shim must rebind, not subclass.
        assert KnowledgeGraphDatabaseAdapter is KnowledgeGraphDatabaseAdapterOneiric

    def test_dunder_all_lists_only_public_name(self) -> None:
        """``__all__`` is exactly ``["KnowledgeGraphDatabaseAdapter"]``."""
        assert kg_shim.__all__ == ["KnowledgeGraphDatabaseAdapter"]

    def test_module_docstring_is_present(self) -> None:
        """The module carries the compatibility-shim docstring."""
        assert kg_shim.__doc__ is not None
        assert "shim" in kg_shim.__doc__.lower()

    def test_module_resolves_via_sys_modules(self) -> None:
        """After import, the module is registered in ``sys.modules``."""
        assert "session_buddy.adapters.knowledge_graph_adapter" in sys.modules
        assert (
            sys.modules["session_buddy.adapters.knowledge_graph_adapter"]
            is kg_shim
        )

    def test_public_attribute_appears_in_dir(self) -> None:
        """``KnowledgeGraphDatabaseAdapter`` shows up in ``dir(module)``."""
        assert "KnowledgeGraphDatabaseAdapter" in dir(kg_shim)

    def test_no_other_public_functions_exported(self) -> None:
        """The shim must not re-export anything besides ``KnowledgeGraphDatabaseAdapter``."""
        # If anyone added a helper here in the future, __all__ would need
        # updating. Validate the invariant.
        public_names = {
            n
            for n in dir(kg_shim)
            if not n.startswith("_")
            and n
            not in {
                # standard module-level noise we don't care about
                "__builtins__",
                "__cached__",
                "__loader__",
                "__spec__",
                "__path__",
                "__file__",
                "__doc__",
                "__name__",
                "__package__",
                "__annotations__",
                "annotations",
            }
        }
        assert public_names == {"KnowledgeGraphDatabaseAdapter"}


class TestAdapterAliasFunctionality:
    """Verify the alias can actually be used as if it were the Oneiric class.

    These tests instantiate the adapter in-memory through the alias so we
    exercise a tiny bit of real DuckDB-backed code. They guard against the
    possibility that the alias reference is wrong, stale, or points to a
    removed class.
    """

    def test_alias_is_instantiable_with_path(self, tmp_path: Path) -> None:
        """The shim-resolved class accepts a database path like the original."""
        db_path = str(tmp_path / "shim.duckdb")
        # Use the alias from the shim — same class as the Oneiric one.
        adapter = KnowledgeGraphDatabaseAdapter(db_path)
        try:
            # Initial state matches the Oneiric implementation contract.
            assert adapter.db_path == db_path
            assert adapter.conn is None
            assert adapter._initialized is False
        finally:
            adapter.close()

    def test_alias_is_instantiable_with_path_object(self, tmp_path: Path) -> None:
        """The alias accepts a ``Path`` object too (str() coercion in __init__)."""
        db_path = tmp_path / "alias.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(db_path)
        try:
            assert adapter.db_path == str(db_path)
        finally:
            adapter.close()

    def test_alias_is_subclass_of_phase3_mixin(self) -> None:
        """The Oneiric class extends ``Phase3RelationshipMixin`` — alias must too."""
        # If the alias points to a different class, this guard fails fast.
        assert hasattr(KnowledgeGraphDatabaseAdapter, "_infer_relationship_type")

    def test_alias_mro_includes_phase3_mixin(self) -> None:
        """The alias class's MRO must include ``Phase3RelationshipMixin``."""
        import session_buddy.adapters.knowledge_graph_adapter_phase3 as phase3_mod

        assert phase3_mod.Phase3RelationshipMixin in KnowledgeGraphDatabaseAdapter.__mro__


class TestShimImportResolution:
    """Verify the shim's re-export always routes to the Oneiric class.

    These tests catch regressions where someone replaces the alias with a
    stub class without inheriting from the Oneiric implementation.
    """

    def test_alias_resolves_to_oneiric_class(self) -> None:
        """``shim.KnowledgeGraphDatabaseAdapter is oneiric.KnowledgeGraphDatabaseAdapterOneiric``."""
        assert (
            kg_shim.KnowledgeGraphDatabaseAdapter
            is KnowledgeGraphDatabaseAdapterOneiric
        )

    def test_module_path_under_adapters(self) -> None:
        """The shim lives at ``session_buddy/adapters/knowledge_graph_adapter.py``."""
        assert kg_shim.__name__ == "session_buddy.adapters.knowledge_graph_adapter"

    def test_importing_alias_twice_returns_same_object(self) -> None:
        """A re-import produces the same class object (no duplicate registration)."""
        import session_buddy.adapters.knowledge_graph_adapter as kg_shim_2

        assert (
            kg_shim.KnowledgeGraphDatabaseAdapter
            is kg_shim_2.KnowledgeGraphDatabaseAdapter
        )


class TestAdapterContextManager:
    """Lightweight exercise of async lifecycle paths through the shim alias.

    Enough to confirm the shim's class reference is fully functional —
    no DB scheme checks are performed; we just want any non-trivial
    async method to run.
    """

    @pytest.mark.asyncio
    async def test_async_context_manager_initializes(self, tmp_path: Path) -> None:
        """``async with`` should set ``conn`` and ``_initialized`` to truthy values."""
        db_path = tmp_path / "ctx.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(str(db_path))
        async with adapter as kg:
            assert kg is adapter
            assert adapter.conn is not None
            assert adapter._initialized is True
        # Cleanup completed on exit.
        assert adapter.conn is None

    def test_sync_context_manager_raises(self, tmp_path: Path) -> None:
        """``with`` (sync) must raise — the class is async-only."""
        db_path = tmp_path / "sync.duckdb"
        adapter = KnowledgeGraphDatabaseAdapter(str(db_path))
        with pytest.raises(
            RuntimeError,
            match=r"async with.*KnowledgeGraphDatabaseAdapter",
        ):
            with adapter:
                pass  # pragma: no cover - exception short-circuits
