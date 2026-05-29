from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_feature_detector_and_flags_cover_true_and_false_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.core import features as features_module

    def fake_find_spec(name: str):
        if name in {
            "session_buddy.tools.search_tools",
            "session_buddy.crackerjack_integration",
        }:
            return None
        return SimpleNamespace(name=name)

    monkeypatch.setattr(features_module.importlib.util, "find_spec", fake_find_spec)

    reloaded = importlib.reload(features_module)

    detector = reloaded.FeatureDetector()
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

    assert reloaded.get_feature_flags() == flags


def test_feature_detector_import_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from session_buddy.core import features as features_module

    def raising_find_spec(name: str):
        if name == "session_buddy.advanced_search":
            raise ImportError("boom")
        return SimpleNamespace(name=name)

    monkeypatch.setattr(features_module.importlib.util, "find_spec", raising_find_spec)

    assert features_module.FeatureDetector._check_advanced_search() is False

