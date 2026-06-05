from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


class _DummyLogger:
    def __init__(self) -> None:
        self.debug = Mock()
        self.warning = Mock()
        self.info = Mock()


# Snapshot of any real session_buddy.* packages already imported before this
# test file ran. We restore this snapshot in :func:`_isolated_lazy_imports` so
# the synthetic stubs below cannot leak into later test files.
_PRESERVED_MODULES: dict[str, object] = {
    name: module
    for name, module in sys.modules.items()
    if name == "session_buddy" or name.startswith("session_buddy.")
}


@pytest.fixture
def _isolated_lazy_imports():
    """Install the lazy_imports stubs for the duration of a single test.

    The original test file did the stub installation at module-import time,
    which leaked the empty-``__path__`` :class:`types.ModuleType` for
    ``session_buddy.utils`` into later test files and broke their
    :mod:`session_buddy.utils.*` imports. Scoping the stubs to this
    fixture (and removing them on teardown) confines the pollution to a
    single test.
    """

    utils_package = types.ModuleType("session_buddy.utils")
    utils_package.__path__ = []  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils"] = utils_package

    logging_stub = types.ModuleType("session_buddy.utils.logging")
    logging_stub.get_session_logger = lambda: _DummyLogger()  # type: ignore[attr-defined]
    sys.modules["session_buddy.utils.logging"] = logging_stub

    module_path = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "utils"
        / "lazy_imports.py"
    )
    spec = importlib.util.spec_from_file_location(
        "session_buddy.utils.lazy_imports", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["session_buddy.utils.lazy_imports"] = module
    spec.loader.exec_module(module)

    yield module

    # Tear down: drop the synthetic stubs and restore the real packages
    # that were present before this test started.
    for name in (
        "session_buddy.utils.lazy_imports",
        "session_buddy.utils.logging",
        "session_buddy.utils",
    ):
        sys.modules.pop(name, None)
    sys.modules.update(_PRESERVED_MODULES)


def test_get_logger_uses_session_logger_and_fallback(monkeypatch: pytest.MonkeyPatch, _isolated_lazy_imports) -> None:
    lazy_imports = _isolated_lazy_imports

    logger = _DummyLogger()
    monkeypatch.setattr(lazy_imports, "_logger", None)
    monkeypatch.setattr(lazy_imports, "get_session_logger", lambda: logger)

    assert lazy_imports._get_logger() is logger

    monkeypatch.setattr(lazy_imports, "_logger", None)
    monkeypatch.setattr(
        lazy_imports,
        "get_session_logger",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    fallback = lazy_imports._get_logger()
    assert fallback is lazy_imports._logger
    assert fallback.name == lazy_imports.__name__


def test_lazy_import_success_and_failure_paths(monkeypatch: pytest.MonkeyPatch, _isolated_lazy_imports) -> None:
    lazy_imports = _isolated_lazy_imports

    logger = _DummyLogger()
    monkeypatch.setattr(lazy_imports, "_logger", logger)

    fresh_loader = lazy_imports.LazyImport("fresh")
    monkeypatch.setattr(
        lazy_imports.importlib,
        "import_module",
        lambda name: SimpleNamespace(answer=42),
    )
    assert bool(fresh_loader) is True

    module = SimpleNamespace(answer=42)
    monkeypatch.setattr(lazy_imports.importlib, "import_module", lambda name: module)

    loader = lazy_imports.LazyImport("example")
    assert loader.available is True
    assert bool(loader) is True
    assert loader.answer == 42
    logger.debug.assert_called()

    monkeypatch.setattr(
        lazy_imports.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("missing")),
    )
    failing = lazy_imports.LazyImport("missing", import_error_msg="install missing")
    assert failing.available is False
    assert bool(failing) is False
    with pytest.raises(ImportError, match="install missing"):
        _ = failing.answer
    logger.warning.assert_called()

    fallback = SimpleNamespace(answer=7)
    with_fallback = lazy_imports.LazyImport("missing", fallback_value=fallback)
    assert with_fallback.answer == 7


def test_lazy_loader_and_decorators(monkeypatch: pytest.MonkeyPatch, _isolated_lazy_imports) -> None:
    lazy_imports = _isolated_lazy_imports

    logger = _DummyLogger()
    monkeypatch.setattr(lazy_imports, "_logger", logger)

    loader = lazy_imports.LazyLoader()
    ok = loader.add_import("ok", "ok")
    missing = loader.add_import("missing", "missing")
    assert loader.get_import("ok") is ok

    monkeypatch.setattr(
        lazy_imports.importlib,
        "import_module",
        lambda name: SimpleNamespace(name=name)
        if name == "ok"
        else (_ for _ in ()).throw(ImportError("missing")),
    )

    assert loader.check_availability() == {"ok": True, "missing": False}

    monkeypatch.setattr(lazy_imports, "lazy_loader", loader)

    @lazy_imports.require_dependency("ok")
    def required(value: int) -> int:
        return value + 1

    @lazy_imports.optional_dependency("ok", fallback_result="fallback")
    def optional_ok() -> str:
        return "used"

    @lazy_imports.optional_dependency("missing", fallback_result="fallback")
    def optional() -> str:
        return "should not run"

    assert required(1) == 2
    assert optional_ok() == "used"
    assert optional() == "fallback"

    with pytest.raises(ImportError, match="requires missing"):
        @lazy_imports.require_dependency("missing", install_hint="pip install missing")
        def broken() -> None:
            raise AssertionError

        broken()


def test_mock_module_and_embedding_mock(monkeypatch: pytest.MonkeyPatch, _isolated_lazy_imports) -> None:
    lazy_imports = _isolated_lazy_imports

    module = lazy_imports.MockModule("demo")
    with pytest.raises(ImportError, match="Mock function encode called"):
        module.encode()

    embedding_factory = lazy_imports.create_embedding_mock()
    embedding = embedding_factory()
    one = embedding.encode("hello")
    many = embedding.encode(["a", "b"])

    assert len(one) == 1
    assert len(one[0]) == 384
    assert len(many) == 2
    assert all(len(row) == 384 for row in many)


def test_dependency_status_and_logging(monkeypatch: pytest.MonkeyPatch, _isolated_lazy_imports) -> None:
    lazy_imports = _isolated_lazy_imports

    logger = _DummyLogger()
    monkeypatch.setattr(lazy_imports, "_logger", logger)

    class DummyLoader:
        def __init__(self, available: bool) -> None:
            self.available = available

    monkeypatch.setitem(
        lazy_imports.lazy_loader._loaders,
        "duckdb",
        DummyLoader(True),
    )
    monkeypatch.setitem(
        lazy_imports.lazy_loader._loaders,
        "tiktoken",
        DummyLoader(False),
    )
    monkeypatch.setitem(
        lazy_imports.lazy_loader._loaders,
        "numpy",
        DummyLoader(True),
    )

    status = lazy_imports.get_dependency_status()

    # transformers/onnxruntime were removed in favour of HTTP embedding
    # providers (llama-server / Ollama); get_dependency_status() no longer
    # surfaces them. Embedding functionality is now always reported as
    # available.
    assert status["duckdb"]["available"] is True
    assert status["_summary"]["core_functionality"] is True
    assert status["_summary"]["embedding_functionality"] is True
    assert status["_summary"]["optimization_functionality"] is False

    lazy_imports.log_dependency_status()
    logger.info.assert_called()


def test_missing_dependency_logging_and_fallback_attribute(monkeypatch: pytest.MonkeyPatch, _isolated_lazy_imports) -> None:
    lazy_imports = _isolated_lazy_imports

    logger = _DummyLogger()
    monkeypatch.setattr(lazy_imports, "_logger", logger)

    missing_fallback = SimpleNamespace(present=123)
    loader = lazy_imports.LazyImport("missing", fallback_value=missing_fallback)
    monkeypatch.setattr(
        lazy_imports.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("missing")),
    )

    assert loader.present == 123
    assert loader.absent is None

    class DummyLoader:
        def __init__(self, available: bool) -> None:
            self.available = available

    monkeypatch.setitem(
        lazy_imports.lazy_loader._loaders,
        "duckdb",
        DummyLoader(False),
    )
    monkeypatch.setitem(
        lazy_imports.lazy_loader._loaders,
        "tiktoken",
        DummyLoader(False),
    )
    monkeypatch.setitem(
        lazy_imports.lazy_loader._loaders,
        "numpy",
        DummyLoader(False),
    )

    lazy_imports.log_dependency_status()

    assert logger.warning.called
    assert logger.info.call_count >= 2
