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


_UTILS_PACKAGE = types.ModuleType("session_buddy.utils")
_UTILS_PACKAGE.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("session_buddy.utils", _UTILS_PACKAGE)

_LOGGING_STUB = types.ModuleType("session_buddy.utils.logging")
_LOGGING_STUB.get_session_logger = lambda: _DummyLogger()
sys.modules.setdefault("session_buddy.utils.logging", _LOGGING_STUB)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "lazy_imports.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.lazy_imports", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.lazy_imports", _MODULE)
_SPEC.loader.exec_module(_MODULE)


def test_get_logger_uses_session_logger_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    lazy_imports = _MODULE

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


def test_lazy_import_success_and_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    lazy_imports = _MODULE

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


def test_lazy_loader_and_decorators(monkeypatch: pytest.MonkeyPatch) -> None:
    lazy_imports = _MODULE

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


def test_mock_module_and_embedding_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    lazy_imports = _MODULE

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


def test_dependency_status_and_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    lazy_imports = _MODULE

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
        "transformers",
        DummyLoader(False),
    )
    monkeypatch.setitem(
        lazy_imports.lazy_loader._loaders,
        "onnxruntime",
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

    assert status["duckdb"]["available"] is True
    assert status["transformers"]["available"] is False
    assert status["_summary"]["core_functionality"] is True
    assert status["_summary"]["embedding_functionality"] is False
    assert status["_summary"]["optimization_functionality"] is False

    lazy_imports.log_dependency_status()
    logger.info.assert_called()


def test_missing_dependency_logging_and_fallback_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    lazy_imports = _MODULE

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
        "transformers",
        DummyLoader(False),
    )
    monkeypatch.setitem(
        lazy_imports.lazy_loader._loaders,
        "onnxruntime",
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
