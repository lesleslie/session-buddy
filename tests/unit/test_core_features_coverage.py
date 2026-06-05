from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


_FEATURES_PATH = (
    Path(__file__).resolve().parents[2] / "session_buddy" / "core" / "features.py"
)


@pytest.fixture(scope="module")
def _module_stubs():
    """Install `session_buddy.core` and `session_buddy.reflection_tools` stubs
    for the duration of this test module.

    The original code did this at module load time (which polluted other
    test files). This fixture scopes the pollution to *this* module only,
    and restores the real modules on teardown so subsequent test files
    see the un-polluted state.
    """
    core_stub = types.ModuleType("session_buddy.core")
    core_stub.__path__ = []  # type: ignore[attr-defined]
    core_stub.session_manager = types.SimpleNamespace()  # type: ignore[attr-defined]
    reflection_tools_stub = types.ModuleType("session_buddy.reflection_tools")
    reflection_tools_stub.ReflectionDatabase = types.SimpleNamespace()  # type: ignore[attr-defined]

    saved_core = sys.modules.get("session_buddy.core")
    saved_rt = sys.modules.get("session_buddy.reflection_tools")
    saved_features = sys.modules.get("session_buddy.core.features")

    sys.modules["session_buddy.core"] = core_stub
    sys.modules["session_buddy.reflection_tools"] = reflection_tools_stub

    spec = importlib.util.spec_from_file_location(
        "session_buddy.core.features",
        _FEATURES_PATH,
    )
    assert spec is not None and spec.loader is not None
    features_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = features_module
    spec.loader.exec_module(features_module)

    yield features_module

    # Teardown: restore the real modules
    for name, original in (
        ("session_buddy.core.features", saved_features),
        ("session_buddy.core", saved_core),
        ("session_buddy.reflection_tools", saved_rt),
    ):
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


def test_feature_detector_and_flags_cover_true_and_false_paths(
    monkeypatch: pytest.MonkeyPatch, _module_stubs
) -> None:
    features_module = _module_stubs

    def fake_find_spec(name: str):
        if name in {
            "session_buddy.tools.search_tools",
            "session_buddy.crackerjack_integration",
        }:
            return None
        return types.SimpleNamespace(name=name)

    monkeypatch.setattr(features_module.importlib.util, "find_spec", fake_find_spec)

    detector = features_module.FeatureDetector()
    flags = detector.get_feature_flags()

    assert flags["SESSION_MANAGEMENT_AVAILABLE"] is True
    assert flags["REFLECTION_TOOLS_AVAILABLE"] is True
    assert flags["ENHANCED_SEARCH_AVAILABLE"] is True
    assert flags["UTILITY_FUNCTIONS_AVAILABLE"] is False
    assert flags["MULTI_PROJECT_AVAILABLE"] is True
    assert flags["ADVANCED_SEARCH_AVAILABLE"] is True
    assert flags["CONFIG_AVAILABLE"] is True
    assert flags["AUTO_CONTEXT_AVAILABLE"] is True
    assert flags["MEMORY_OPTIMIZER_AVAILABLE"] is True
    assert flags["APP_MONITOR_AVAILABLE"] is True
    assert flags["LLM_PROVIDERS_AVAILABLE"] is True
    assert flags["SERVERLESS_MODE_AVAILABLE"] is True
    assert flags["CRACKERJACK_INTEGRATION_AVAILABLE"] is False

    features_module._feature_detector = detector
    assert features_module.get_feature_flags() == flags


def test_feature_detector_import_error_path(
    monkeypatch: pytest.MonkeyPatch, _module_stubs
) -> None:
    features_module = _module_stubs

    def raising_find_spec(name: str):
        if name == "session_buddy.advanced_search":
            raise ImportError("boom")
        return types.SimpleNamespace(name=name)

    monkeypatch.setattr(features_module.importlib.util, "find_spec", raising_find_spec)

    assert features_module.FeatureDetector._check_advanced_search() is False


def test_feature_detector_false_branches(
    monkeypatch: pytest.MonkeyPatch, _module_stubs
) -> None:
    features_module = _module_stubs

    def missing_find_spec(name: str):
        return None

    monkeypatch.setattr(features_module.importlib.util, "find_spec", missing_find_spec)

    import builtins

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"session_buddy.core", "session_buddy.reflection_tools"}:
            raise ImportError("missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert features_module.FeatureDetector._check_session_management() is False
    assert features_module.FeatureDetector._check_reflection_tools() is False
    assert features_module.FeatureDetector._check_enhanced_search() is False
    assert features_module.FeatureDetector._check_utility_functions() is False
    assert features_module.FeatureDetector._check_multi_project() is False
    assert features_module.FeatureDetector._check_advanced_search() is False
    assert features_module.FeatureDetector._check_config() is False
    assert features_module.FeatureDetector._check_auto_context() is False
    assert features_module.FeatureDetector._check_memory_optimizer() is False
    assert features_module.FeatureDetector._check_app_monitor() is False
    assert features_module.FeatureDetector._check_llm_providers() is False
    assert features_module.FeatureDetector._check_serverless_mode() is False
    assert features_module.FeatureDetector._check_crackerjack() is False


@pytest.mark.parametrize(
    ("method_name", "module_name"),
    [
        ("_check_enhanced_search", "session_buddy.search_enhanced"),
        ("_check_utility_functions", "session_buddy.tools.search_tools"),
        ("_check_multi_project", "session_buddy.multi_project_coordinator"),
        ("_check_advanced_search", "session_buddy.advanced_search"),
        ("_check_config", "session_buddy.settings"),
        ("_check_auto_context", "session_buddy.context_manager"),
        ("_check_memory_optimizer", "session_buddy.memory_optimizer"),
        ("_check_app_monitor", "session_buddy.app_monitor"),
        ("_check_llm_providers", "session_buddy.llm_providers"),
        ("_check_serverless_mode", "session_buddy.serverless_mode"),
        ("_check_crackerjack", "session_buddy.crackerjack_integration"),
    ],
)
def test_feature_detector_handles_import_error_from_find_spec(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    module_name: str,
    _module_stubs,
) -> None:
    features_module = _module_stubs

    def raising_find_spec(name: str):
        if name == module_name:
            raise ImportError("boom")
        return types.SimpleNamespace(name=name)

    monkeypatch.setattr(features_module.importlib.util, "find_spec", raising_find_spec)

    method = getattr(features_module.FeatureDetector, method_name)
    assert method() is False
