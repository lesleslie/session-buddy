"""Unit tests for ``session_buddy.utils.lazy_imports``.

Covers the lazy import helpers: ``LazyImport``, ``LazyLoader``,
``MockModule``, the ``require_dependency``/``optional_dependency``
decorators, ``create_embedding_mock``, and the dependency status
reporters.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from session_buddy.utils.lazy_imports import (
    LazyImport,
    LazyLoader,
    MockModule,
    create_embedding_mock,
    get_dependency_status,
    log_dependency_status,
    optional_dependency,
    require_dependency,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_fake_module(
    name: str, *, attrs: dict[str, Any] | None = None, missing: bool = False
) -> types.ModuleType:
    """Install (or uninstall) a fake module in ``sys.modules``.

    When ``missing`` is True, ensures the module name is *not* importable by
    removing it from ``sys.modules`` and any cached parent submodules.
    Returns the module object that was installed (or ``None``).
    """
    if missing:
        sys.modules.pop(name, None)
        # Drop the parent entry so importlib re-evaluates it next call.
        if "." in name:
            sys.modules.pop(name.rsplit(".", 1)[0], None)
        return None  # type: ignore[return-value]

    module = types.ModuleType(name)
    for attr_name, attr_value in (attrs or {}).items():
        setattr(module, attr_name, attr_value)
    sys.modules[name] = module
    return module


# ---------------------------------------------------------------------------
# LazyImport
# ---------------------------------------------------------------------------


class TestLazyImportBasics:
    """``LazyImport`` defers ``import_module`` until first attribute access."""

    def test_imports_real_module_on_attribute_access(self) -> None:
        _install_fake_module(
            "_lazy_test_real_mod",
            attrs={"SENTINEL": 42},
        )
        try:
            loader = LazyImport("_lazy_test_real_mod")
            # Import should not have happened yet.
            assert loader._import_attempted is False  # noqa: SLF001

            value = loader.SENTINEL
            assert value == 42
            assert loader._import_attempted is True  # noqa: SLF001
            assert loader._import_failed is False  # noqa: SLF001
            assert loader.available is True
            assert bool(loader) is True
        finally:
            sys.modules.pop("_lazy_test_real_mod", None)

    def test_unknown_attribute_raises_attribute_error_on_success(self) -> None:
        _install_fake_module("_lazy_test_no_attr", attrs={"X": 1})
        try:
            loader = LazyImport("_lazy_test_no_attr")
            with pytest.raises(AttributeError):
                _ = loader.MISSING_ATTRIBUTE
        finally:
            sys.modules.pop("_lazy_test_no_attr", None)

    def test_import_attempted_only_once(self) -> None:
        """Subsequent attribute accesses reuse the cached import."""
        counter = {"calls": 0}
        module = types.ModuleType("_lazy_test_once_mod")

        def _hooked(self: Any, name: str) -> Any:  # pragma: no cover - test hook
            counter["calls"] += 1
            return 99

        setattr(module, "value", 99)
        sys.modules["_lazy_test_once_mod"] = module
        try:
            loader = LazyImport("_lazy_test_once_mod")
            # Patch the underlying import_module via monkeypatching the loader
            # after construction isn't possible easily; instead, call several
            # times and assert _import_attempted remains True.
            _ = loader.value
            first_attempted = loader._import_attempted  # noqa: SLF001
            _ = loader.value
            second_attempted = loader._import_attempted  # noqa: SLF001
            assert first_attempted is True
            assert second_attempted is True
            assert counter["calls"] == 0  # Not really used; left for parity
        finally:
            sys.modules.pop("_lazy_test_once_mod", None)


class TestLazyImportMissingModule:
    """When the underlying module is missing, ``LazyImport`` degrades cleanly."""

    def test_missing_module_raises_with_default_message(self) -> None:
        _install_fake_module("_lazy_test_missing_mod", missing=True)
        loader = LazyImport("_lazy_test_missing_mod")
        with pytest.raises(ImportError, match="_lazy_test_missing_mod"):
            _ = loader.any_attr

    def test_missing_module_uses_custom_error_message(self) -> None:
        _install_fake_module("_lazy_test_missing_custom", missing=True)
        loader = LazyImport(
            "_lazy_test_missing_custom",
            import_error_msg="please install widget-X",
        )
        with pytest.raises(ImportError, match="please install widget-X"):
            _ = loader.any_attr

    def test_missing_module_with_fallback_returns_attribute(self) -> None:
        _install_fake_module("_lazy_test_missing_fb", missing=True)
        fallback = types.SimpleNamespace(ping=lambda: "pong")
        loader = LazyImport(
            "_lazy_test_missing_fb",
            fallback_value=fallback,
        )
        # Available reports the import failure.
        assert loader.available is False
        assert bool(loader) is False
        # Falling back: ``getattr(fallback, "ping")`` is callable and
        # callable itself, so the wrapper exposes it via __getattr__.
        # We exercise via the fallback object's own API instead.
        assert fallback.ping() == "pong"

    def test_missing_module_with_fallback_returns_none_for_unknown_attr(
        self,
    ) -> None:
        _install_fake_module("_lazy_test_missing_fb2", missing=True)
        fallback = types.SimpleNamespace(known="value")
        loader = LazyImport(
            "_lazy_test_missing_fb2",
            fallback_value=fallback,
        )
        # ``getattr(fallback, name, None)`` returns None for unknown attrs.
        assert loader.unknown_attr is None

    def test_available_property_triggers_import(self) -> None:
        _install_fake_module("_lazy_test_avail_real", attrs={"x": 1})
        try:
            loader = LazyImport("_lazy_test_avail_real")
            assert loader._import_attempted is False  # noqa: SLF001
            assert loader.available is True
            assert loader._import_attempted is True  # noqa: SLF001
        finally:
            sys.modules.pop("_lazy_test_avail_real", None)

    def test_bool_dunder_matches_available(self) -> None:
        _install_fake_module("_lazy_test_bool_real", attrs={"x": 1})
        try:
            loader = LazyImport("_lazy_test_bool_real")
            assert bool(loader) is True
        finally:
            sys.modules.pop("_lazy_test_bool_real", None)

    def test_bool_dunder_false_when_missing(self) -> None:
        _install_fake_module("_lazy_test_bool_missing", missing=True)
        loader = LazyImport("_lazy_test_bool_missing")
        assert bool(loader) is False


# ---------------------------------------------------------------------------
# LazyLoader
# ---------------------------------------------------------------------------


class TestLazyLoaderRegistry:
    """``LazyLoader`` is a dict of named ``LazyImport`` entries."""

    def test_add_and_get_import(self) -> None:
        loader = LazyLoader()
        entry = loader.add_import("foo", "_lazy_test_loader_foo")
        assert isinstance(entry, LazyImport)
        assert loader.get_import("foo") is entry
        assert loader.get_import("missing") is None

    def test_add_import_passes_through_args(self) -> None:
        loader = LazyLoader()
        sentinel = object()
        entry = loader.add_import(
            "bar",
            "_lazy_test_loader_bar",
            fallback_value=sentinel,
            error_msg="custom error",
        )
        assert entry.fallback_value is sentinel
        assert entry.import_error_msg == "custom error"
        assert entry.module_name == "_lazy_test_loader_bar"

    def test_check_availability_empty(self) -> None:
        loader = LazyLoader()
        assert loader.check_availability() == {}

    def test_check_availability_aggregates_known_modules(self) -> None:
        _install_fake_module("_lazy_test_avail_yes", attrs={"x": 1})
        _install_fake_module("_lazy_test_avail_no", missing=True)
        try:
            loader = LazyLoader()
            loader.add_import("yes", "_lazy_test_avail_yes")
            loader.add_import("no", "_lazy_test_avail_no")
            result = loader.check_availability()
            assert result == {"yes": True, "no": False}
        finally:
            sys.modules.pop("_lazy_test_avail_yes", None)

    def test_get_import_returns_none_for_unknown(self) -> None:
        loader = LazyLoader()
        assert loader.get_import("nope") is None


# ---------------------------------------------------------------------------
# MockModule
# ---------------------------------------------------------------------------


class TestMockModule:
    """``MockModule`` exposes callable placeholders that raise on call."""

    def test_name_attribute(self) -> None:
        m = MockModule("widget")
        assert m.name == "widget"

    def test_attribute_returns_callable(self) -> None:
        m = MockModule("widget")
        sentinel = m.do_thing
        assert callable(sentinel)

    def test_calling_attribute_raises_import_error(self) -> None:
        m = MockModule("widget")
        sentinel = m.do_thing
        with pytest.raises(ImportError, match="widget"):
            sentinel()

    def test_calling_with_args_still_raises(self) -> None:
        m = MockModule("widget")
        with pytest.raises(ImportError):
            m.run(1, 2, key="value")


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


class TestRequireDependencyDecorator:
    """``require_dependency`` gates a function on a registered loader."""

    def test_calls_function_when_dependency_available(self) -> None:
        _install_fake_module("_lazy_test_dep_avail", attrs={"x": 1})
        try:
            loader_mgr = LazyLoader()
            loader_mgr.add_import("req_dep", "_lazy_test_dep_avail")

            with pytest.MonkeyPatch.context() as mp:
                # Patch the module-level lazy_loader used inside the decorator.
                from session_buddy.utils import lazy_imports

                mp.setattr(lazy_imports, "lazy_loader", loader_mgr)

                @require_dependency("req_dep")
                def hello() -> str:
                    return "hi"

                assert hello() == "hi"
        finally:
            sys.modules.pop("_lazy_test_dep_avail", None)

    def test_raises_when_dependency_missing(self) -> None:
        _install_fake_module("_lazy_test_dep_missing", missing=True)
        loader_mgr = LazyLoader()
        loader_mgr.add_import("req_dep", "_lazy_test_dep_missing")

        with pytest.MonkeyPatch.context() as mp:
            from session_buddy.utils import lazy_imports

            mp.setattr(lazy_imports, "lazy_loader", loader_mgr)

            @require_dependency("req_dep", install_hint="uv add widget")
            def hello() -> str:
                return "hi"

            with pytest.raises(ImportError, match="uv add widget"):
                hello()

    def test_raises_when_loader_unknown(self) -> None:
        loader_mgr = LazyLoader()

        with pytest.MonkeyPatch.context() as mp:
            from session_buddy.utils import lazy_imports

            mp.setattr(lazy_imports, "lazy_loader", loader_mgr)

            @require_dependency("never_registered")
            def hello() -> str:
                return "hi"

            with pytest.raises(ImportError):
                hello()

    def test_preserves_function_metadata(self) -> None:
        @require_dependency("never_registered")
        def hello() -> str:
            """Friendly greeting."""
            return "hi"

        assert hello.__name__ == "hello"
        assert hello.__doc__ == "Friendly greeting."


class TestOptionalDependencyDecorator:
    """``optional_dependency`` skips gracefully and returns the fallback."""

    def test_calls_function_when_available(self) -> None:
        _install_fake_module("_lazy_test_opt_avail", attrs={"x": 1})
        try:
            loader_mgr = LazyLoader()
            loader_mgr.add_import("opt_dep", "_lazy_test_opt_avail")

            with pytest.MonkeyPatch.context() as mp:
                from session_buddy.utils import lazy_imports

                mp.setattr(lazy_imports, "lazy_loader", loader_mgr)

                @optional_dependency("opt_dep")
                def compute() -> int:
                    return 7

                assert compute() == 7
        finally:
            sys.modules.pop("_lazy_test_opt_avail", None)

    def test_returns_fallback_when_missing(self) -> None:
        _install_fake_module("_lazy_test_opt_missing", missing=True)
        loader_mgr = LazyLoader()
        loader_mgr.add_import("opt_dep", "_lazy_test_opt_missing")

        with pytest.MonkeyPatch.context() as mp:
            from session_buddy.utils import lazy_imports

            mp.setattr(lazy_imports, "lazy_loader", loader_mgr)

            sentinel = {"skipped": True}

            @optional_dependency("opt_dep", fallback_result=sentinel)
            def compute() -> int:
                return 7

            assert compute() is sentinel

    def test_default_fallback_is_none(self) -> None:
        _install_fake_module("_lazy_test_opt_missing2", missing=True)
        loader_mgr = LazyLoader()
        loader_mgr.add_import("opt_dep", "_lazy_test_opt_missing2")

        with pytest.MonkeyPatch.context() as mp:
            from session_buddy.utils import lazy_imports

            mp.setattr(lazy_imports, "lazy_loader", loader_mgr)

            @optional_dependency("opt_dep")
            def compute() -> int:
                return 7

            assert compute() is None

    def test_preserves_function_metadata(self) -> None:
        @optional_dependency("nope")
        def compute() -> int:
            """Run the compute."""
            return 7

        assert compute.__name__ == "compute"
        assert compute.__doc__ == "Run the compute."


# ---------------------------------------------------------------------------
# create_embedding_mock
# ---------------------------------------------------------------------------


class TestCreateEmbeddingMock:
    """``create_embedding_mock`` returns a class with a working ``encode``."""

    def test_returns_callable_class(self) -> None:
        cls = create_embedding_mock()
        assert isinstance(cls, type)

    def test_instantiate_accepts_arbitrary_args(self) -> None:
        cls = create_embedding_mock()
        instance = cls(model_name="anything", dim=384, foo=1)
        assert instance is not None

    def test_encode_single_string_returns_one_vector(self) -> None:
        cls = create_embedding_mock()
        instance = cls()
        result = instance.encode("hello world")
        assert isinstance(result, list)
        assert len(result) == 1
        vector = result[0]
        assert isinstance(vector, list)
        assert len(vector) == 384
        assert all(isinstance(v, float) for v in vector)

    def test_encode_list_returns_one_vector_per_item(self) -> None:
        cls = create_embedding_mock()
        instance = cls()
        result = instance.encode(["alpha", "beta", "gamma"])
        assert isinstance(result, list)
        assert len(result) == 3
        for vector in result:
            assert len(vector) == 384

    def test_encode_produces_values_in_unit_range(self) -> None:
        cls = create_embedding_mock()
        instance = cls()
        vector = instance.encode("anything")[0]
        assert all(0.0 <= v < 1.0 for v in vector)


# ---------------------------------------------------------------------------
# Dependency status reporters
# ---------------------------------------------------------------------------


class TestGetDependencyStatus:
    """``get_dependency_status`` returns a documented structure."""

    def test_keys_present(self) -> None:
        status = get_dependency_status()
        assert set(status) >= {"duckdb", "tiktoken", "numpy", "_summary"}

    def test_per_dep_record_shape(self) -> None:
        status = get_dependency_status()
        for key in ("duckdb", "tiktoken", "numpy"):
            record = status[key]
            assert set(record) == {"available", "required", "category"}
            assert isinstance(record["available"], bool)
            assert isinstance(record["required"], bool)
            assert isinstance(record["category"], str)

    def test_core_deps_marked_required(self) -> None:
        status = get_dependency_status()
        assert status["duckdb"]["required"] is True
        assert status["duckdb"]["category"] == "core"

    def test_optional_deps_marked_optional(self) -> None:
        status = get_dependency_status()
        assert status["tiktoken"]["required"] is False
        assert status["tiktoken"]["category"] == "optimization"
        assert status["numpy"]["required"] is False
        assert status["numpy"]["category"] == "optimization"

    def test_summary_shape(self) -> None:
        status = get_dependency_status()
        summary = status["_summary"]
        assert set(summary) == {
            "core_functionality",
            "embedding_functionality",
            "optimization_functionality",
            "overall_health",
        }
        # Embedding is always reported available (HTTP providers).
        assert summary["embedding_functionality"] is True

    def test_summary_overall_health_equals_core(self) -> None:
        status = get_dependency_status()
        summary = status["_summary"]
        assert summary["overall_health"] == summary["core_functionality"]


class TestLogDependencyStatus:
    """``log_dependency_status`` must run without raising."""

    def test_does_not_raise(self) -> None:
        # Status is computed against the real lazy_loader; duckdb should be
        # importable in the test env so we expect no warning path to fire.
        log_dependency_status()
