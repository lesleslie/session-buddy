from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
import session_buddy


_CORE_PACKAGE = types.ModuleType("session_buddy.core")
_CORE_PACKAGE.__path__ = []  # type: ignore[attr-defined]
_CORE_PACKAGE.session_manager = types.SimpleNamespace()  # type: ignore[attr-defined]
sys.modules["session_buddy.core"] = _CORE_PACKAGE
setattr(session_buddy, "core", _CORE_PACKAGE)

_REFLECTION_TOOLS_MODULE = types.ModuleType("session_buddy.reflection_tools")
_REFLECTION_TOOLS_MODULE.ReflectionDatabase = types.SimpleNamespace()  # type: ignore[attr-defined]
sys.modules["session_buddy.reflection_tools"] = _REFLECTION_TOOLS_MODULE
setattr(session_buddy, "reflection_tools", _REFLECTION_TOOLS_MODULE)

_FEATURES_PATH = (
    Path(__file__).resolve().parents[2] / "session_buddy" / "core" / "features.py"
)
_FEATURES_SPEC = importlib.util.spec_from_file_location(
    "session_buddy.core.features",
    _FEATURES_PATH,
)
assert _FEATURES_SPEC is not None and _FEATURES_SPEC.loader is not None
_FEATURES_MODULE = importlib.util.module_from_spec(_FEATURES_SPEC)
sys.modules[_FEATURES_SPEC.name] = _FEATURES_MODULE
_FEATURES_SPEC.loader.exec_module(_FEATURES_MODULE)


def test_feature_detector_and_flags_cover_true_and_false_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    features_module = _FEATURES_MODULE

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


def test_feature_detector_import_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    features_module = _FEATURES_MODULE

    def raising_find_spec(name: str):
        if name == "session_buddy.advanced_search":
            raise ImportError("boom")
        return types.SimpleNamespace(name=name)

    monkeypatch.setattr(features_module.importlib.util, "find_spec", raising_find_spec)

    assert features_module.FeatureDetector._check_advanced_search() is False


def test_feature_detector_false_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    features_module = _FEATURES_MODULE

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
) -> None:
    features_module = _FEATURES_MODULE

    def raising_find_spec(name: str):
        if name == module_name:
            raise ImportError("boom")
        return types.SimpleNamespace(name=name)

    monkeypatch.setattr(features_module.importlib.util, "find_spec", raising_find_spec)

    method = getattr(features_module.FeatureDetector, method_name)
    assert method() is False
