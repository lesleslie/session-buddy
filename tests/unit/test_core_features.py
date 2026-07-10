"""Tests for session_buddy.core.features.

Covers FeatureDetector initialization, every _check_* method, the
get_feature_flags dict projection, and the module-level get_feature_flags
proxy.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Module loading — installed as a private fixture so each test can rebuild
# the features module with its own stub environment.
# ---------------------------------------------------------------------------


_FEATURES_PATH = (
    Path(__file__).resolve().parents[2] / "session_buddy" / "core" / "features.py"
)


class _StubSessionManager:
    """Stand-in for session_buddy.core.session_manager during feature scans."""


class _StubReflectionDatabase:
    """Stand-in for ReflectionDatabase during feature scans."""


@pytest.fixture
def loaded_features():
    """Yield a freshly-imported features module with isolated sys.modules state.

    On teardown, restores the original ``session_buddy.core`` and
    ``session_buddy.reflection_tools`` modules so subsequent tests see
    the real environment.

    Critical: ``session_buddy/__init__.py`` defines a ``__getattr__`` for
    lazy exports, so accessing ``session_buddy.core`` walks
    ``__getattr__`` first. We must bind the stub into the package's
    ``__dict__`` (not just ``sys.modules``) so that attribute access
    returns the stub instead of triggering ``__getattr__('core')``,
    which raises ``AttributeError`` because 'core' isn't in
    ``_LAZY_EXPORTS``.
    """
    # Pre-stub: real session_buddy.core, session_buddy.reflection_tools
    saved_core = sys.modules.get("session_buddy.core")
    saved_rt = sys.modules.get("session_buddy.reflection_tools")
    saved_features = sys.modules.get("session_buddy.core.features")

    # Also remember whether session_buddy was already imported
    saved_session_buddy = sys.modules.get("session_buddy")
    saved_core_in_pkg_dict: object | None = None
    if saved_session_buddy is not None:
        saved_core_in_pkg_dict = saved_session_buddy.__dict__.get("core")

    real_core_init = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "core"
        / "__init__.py"
    )
    core_stub = types.ModuleType("session_buddy.core")
    core_stub.__file__ = str(real_core_init)  # type: ignore[attr-defined]
    core_stub.__path__ = [str(real_core_init.parent)]  # type: ignore[attr-defined]
    core_stub.session_manager = _StubSessionManager  # type: ignore[attr-defined]

    rt_stub = types.ModuleType("session_buddy.reflection_tools")
    real_rt_init = (
        Path(__file__).resolve().parents[2]
        / "session_buddy"
        / "reflection_tools"
        / "__init__.py"
    )
    rt_stub.__file__ = str(real_rt_init)  # type: ignore[attr-defined]
    rt_stub.__path__ = [str(real_rt_init.parent)]  # type: ignore[attr-defined]
    rt_stub.ReflectionDatabase = _StubReflectionDatabase  # type: ignore[attr-defined]

    sys.modules["session_buddy.core"] = core_stub
    sys.modules["session_buddy.reflection_tools"] = rt_stub

    # Bind the stub into the session_buddy package's __dict__ so that
    # `session_buddy.core` attribute access returns the stub.
    if saved_session_buddy is not None:
        saved_session_buddy.__dict__["core"] = core_stub

    spec = importlib.util.spec_from_file_location(
        "session_buddy.core.features",
        _FEATURES_PATH,
    )
    assert spec is not None and spec.loader is not None
    features_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = features_module
    spec.loader.exec_module(features_module)

    yield features_module

    # Teardown: restore the original module entries
    for name, original in (
        ("session_buddy.core.features", saved_features),
        ("session_buddy.core", saved_core),
        ("session_buddy.reflection_tools", saved_rt),
    ):
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original

    # Restore the original entry in the session_buddy package's __dict__
    if saved_session_buddy is not None:
        if saved_core_in_pkg_dict is None:
            saved_session_buddy.__dict__.pop("core", None)
        else:
            saved_session_buddy.__dict__["core"] = saved_core_in_pkg_dict


def _make_fake_find_spec(present: set[str] | None = None) -> types.SimpleNamespace | None:
    """Return a fake find_spec that pretends modules in ``present`` exist."""

    def fake(name: str):
        if present is None:
            return types.SimpleNamespace(name=name)
        if name in present:
            return types.SimpleNamespace(name=name)
        return None

    return fake  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# FeatureDetector — initialization
# ---------------------------------------------------------------------------


class TestFeatureDetectorInit:
    """Verify all 13 feature flags are populated at construction."""

    def test_all_flags_exist_after_init(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            loaded_features.importlib.util, "find_spec", _make_fake_find_spec()
        )
        detector = loaded_features.FeatureDetector()

        # Each instance attribute is a bool
        flag_names = [
            "SESSION_MANAGEMENT_AVAILABLE",
            "REFLECTION_TOOLS_AVAILABLE",
            "ENHANCED_SEARCH_AVAILABLE",
            "UTILITY_FUNCTIONS_AVAILABLE",
            "MULTI_PROJECT_AVAILABLE",
            "ADVANCED_SEARCH_AVAILABLE",
            "CONFIG_AVAILABLE",
            "AUTO_CONTEXT_AVAILABLE",
            "MEMORY_OPTIMIZER_AVAILABLE",
            "APP_MONITOR_AVAILABLE",
            "LLM_PROVIDERS_AVAILABLE",
            "SERVERLESS_MODE_AVAILABLE",
            "CRACKERJACK_INTEGRATION_AVAILABLE",
        ]
        for name in flag_names:
            assert hasattr(detector, name), f"missing flag: {name}"
            assert isinstance(getattr(detector, name), bool)

    def test_flags_true_when_all_modules_present(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The features module checks these module names:
        #   session_buddy.reflection_tools (via real import)
        #   session_buddy.search_enhanced
        #   session_buddy.tools.search_tools
        #   session_buddy.multi_project_coordinator
        #   session_buddy.advanced_search
        #   session_buddy.settings
        #   session_buddy.context_manager
        #   session_buddy.memory_optimizer
        #   session_buddy.app_monitor
        #   session_buddy.llm_providers
        #   session_buddy.serverless_mode
        #   session_buddy.crackerjack_integration
        monkeypatch.setattr(
            loaded_features.importlib.util, "find_spec", _make_fake_find_spec()
        )

        detector = loaded_features.FeatureDetector()
        flags = detector.get_feature_flags()
        # All find_spec paths return "present"
        assert flags["SESSION_MANAGEMENT_AVAILABLE"] is True
        assert flags["REFLECTION_TOOLS_AVAILABLE"] is True
        assert flags["ENHANCED_SEARCH_AVAILABLE"] is True
        assert flags["UTILITY_FUNCTIONS_AVAILABLE"] is True
        assert flags["MULTI_PROJECT_AVAILABLE"] is True
        assert flags["ADVANCED_SEARCH_AVAILABLE"] is True
        assert flags["CONFIG_AVAILABLE"] is True
        assert flags["AUTO_CONTEXT_AVAILABLE"] is True
        assert flags["MEMORY_OPTIMIZER_AVAILABLE"] is True
        assert flags["APP_MONITOR_AVAILABLE"] is True
        assert flags["LLM_PROVIDERS_AVAILABLE"] is True
        assert flags["SERVERLESS_MODE_AVAILABLE"] is True
        assert flags["CRACKERJACK_INTEGRATION_AVAILABLE"] is True


# ---------------------------------------------------------------------------
# Per-method coverage — _check_* paths
# ---------------------------------------------------------------------------


class TestCheckSessionManagement:
    """Verify _check_session_management."""

    def test_returns_true_when_session_manager_present(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The session_buddy.core stub already has session_manager attached
        result = loaded_features.FeatureDetector._check_session_management()
        assert result is True

    def test_returns_false_on_attribute_error(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Break the import by replacing the real __import__ for the duration
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "session_buddy.core":
                raise AttributeError("no submodule")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        # Force the module to fail at import time
        result = loaded_features.FeatureDetector._check_session_management()
        assert result is False

    def test_returns_false_on_import_error(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "session_buddy.core":
                raise ImportError("missing")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        result = loaded_features.FeatureDetector._check_session_management()
        assert result is False


class TestCheckReflectionTools:
    """Verify _check_reflection_tools handles both branches."""

    def test_returns_true_when_module_present(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            loaded_features.importlib.util, "find_spec", _make_fake_find_spec()
        )
        assert (
            loaded_features.FeatureDetector._check_reflection_tools() is True
        )

    def test_returns_false_when_module_missing(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake(name: str):
            return None

        monkeypatch.setattr(loaded_features.importlib.util, "find_spec", fake)
        assert (
            loaded_features.FeatureDetector._check_reflection_tools() is False
        )

    def test_returns_false_on_value_error(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake(name: str):
            raise ValueError("bad spec")

        monkeypatch.setattr(loaded_features.importlib.util, "find_spec", fake)
        assert (
            loaded_features.FeatureDetector._check_reflection_tools() is False
        )

    def test_returns_false_on_import_error(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake(name: str):
            raise ImportError("explode")

        monkeypatch.setattr(loaded_features.importlib.util, "find_spec", fake)
        assert (
            loaded_features.FeatureDetector._check_reflection_tools() is False
        )


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
class TestFindSpecBasedChecks:
    """Verify each find_spec-based check (present, missing, import error)."""

    def test_present(
        self,
        loaded_features,
        monkeypatch: pytest.MonkeyPatch,
        method_name: str,
        module_name: str,
    ) -> None:
        monkeypatch.setattr(
            loaded_features.importlib.util,
            "find_spec",
            _make_fake_find_spec(present={module_name}),
        )
        method = getattr(loaded_features.FeatureDetector, method_name)
        assert method() is True

    def test_missing(
        self,
        loaded_features,
        monkeypatch: pytest.MonkeyPatch,
        method_name: str,
        module_name: str,
    ) -> None:
        def fake(name: str):
            return None

        monkeypatch.setattr(loaded_features.importlib.util, "find_spec", fake)
        method = getattr(loaded_features.FeatureDetector, method_name)
        assert method() is False

    def test_import_error(
        self,
        loaded_features,
        monkeypatch: pytest.MonkeyPatch,
        method_name: str,
        module_name: str,
    ) -> None:
        def fake(name: str):
            if name == module_name:
                raise ImportError("boom")
            return types.SimpleNamespace(name=name)

        monkeypatch.setattr(loaded_features.importlib.util, "find_spec", fake)
        method = getattr(loaded_features.FeatureDetector, method_name)
        assert method() is False


# ---------------------------------------------------------------------------
# get_feature_flags — instance method
# ---------------------------------------------------------------------------


class TestGetFeatureFlags:
    """Verify the dict projection of detector state."""

    def test_returns_dict_of_all_flags(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            loaded_features.importlib.util, "find_spec", _make_fake_find_spec()
        )
        detector = loaded_features.FeatureDetector()
        flags = detector.get_feature_flags()
        assert isinstance(flags, dict)
        # 13 flag names
        assert len(flags) == 13
        # All values are booleans
        for value in flags.values():
            assert isinstance(value, bool)

    def test_dict_keys_match_instance_attributes(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            loaded_features.importlib.util, "find_spec", _make_fake_find_spec()
        )
        detector = loaded_features.FeatureDetector()
        flags = detector.get_feature_flags()
        for name, value in flags.items():
            assert getattr(detector, name) == value

    def test_dict_keys_are_stable(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            loaded_features.importlib.util, "find_spec", _make_fake_find_spec()
        )
        detector = loaded_features.FeatureDetector()
        expected_keys = {
            "SESSION_MANAGEMENT_AVAILABLE",
            "REFLECTION_TOOLS_AVAILABLE",
            "ENHANCED_SEARCH_AVAILABLE",
            "UTILITY_FUNCTIONS_AVAILABLE",
            "MULTI_PROJECT_AVAILABLE",
            "ADVANCED_SEARCH_AVAILABLE",
            "CONFIG_AVAILABLE",
            "AUTO_CONTEXT_AVAILABLE",
            "MEMORY_OPTIMIZER_AVAILABLE",
            "APP_MONITOR_AVAILABLE",
            "LLM_PROVIDERS_AVAILABLE",
            "SERVERLESS_MODE_AVAILABLE",
            "CRACKERJACK_INTEGRATION_AVAILABLE",
        }
        assert set(flags_keys := set(detector.get_feature_flags().keys())) == expected_keys
        assert len(flags_keys) == 13

    def test_flags_reflect_module_presence(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Only some modules are "present"
        present = {
            "session_buddy.search_enhanced",
            "session_buddy.multi_project_coordinator",
            "session_buddy.settings",
        }
        monkeypatch.setattr(
            loaded_features.importlib.util,
            "find_spec",
            _make_fake_find_spec(present=present),
        )
        detector = loaded_features.FeatureDetector()
        flags = detector.get_feature_flags()
        assert flags["ENHANCED_SEARCH_AVAILABLE"] is True
        assert flags["MULTI_PROJECT_AVAILABLE"] is True
        assert flags["CONFIG_AVAILABLE"] is True
        # The rest should be False
        assert flags["UTILITY_FUNCTIONS_AVAILABLE"] is False
        assert flags["ADVANCED_SEARCH_AVAILABLE"] is False
        assert flags["APP_MONITOR_AVAILABLE"] is False
        assert flags["CRACKERJACK_INTEGRATION_AVAILABLE"] is False


# ---------------------------------------------------------------------------
# get_feature_flags — module-level proxy
# ---------------------------------------------------------------------------


class TestModuleLevelGetFeatureFlags:
    """Verify the module-level get_feature_flags proxies the singleton."""

    def test_returns_dict(self, loaded_features) -> None:
        result = loaded_features.get_feature_flags()
        assert isinstance(result, dict)
        assert len(result) == 13

    def test_returns_dict_from_singleton(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            loaded_features.importlib.util, "find_spec", _make_fake_find_spec()
        )
        # Force a fresh detector on the singleton
        loaded_features._feature_detector = loaded_features.FeatureDetector()
        result = loaded_features.get_feature_flags()
        assert result == loaded_features._feature_detector.get_feature_flags()

    def test_singleton_is_feature_detector_instance(self, loaded_features) -> None:
        assert isinstance(loaded_features._feature_detector, loaded_features.FeatureDetector)


# ---------------------------------------------------------------------------
# Module-level attributes and exports
# ---------------------------------------------------------------------------


class TestModuleStructure:
    """Verify the module's basic shape."""

    def test_logger_is_defined(self, loaded_features) -> None:
        # Module-level logger is a stdlib logging.Logger
        import logging

        assert isinstance(loaded_features.logger, logging.Logger)

    def test_logger_name_matches_module(self, loaded_features) -> None:
        assert loaded_features.logger.name == "session_buddy.core.features"


# ---------------------------------------------------------------------------
# Edge cases / property checks
# ---------------------------------------------------------------------------


class TestFlagInvariants:
    """Invariants that should hold across any environment."""

    def test_session_management_matches_import_success(
        self, loaded_features, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # When the import works, session_management should be True; when it
        # doesn't, False. Use a counter to verify the detector uses a fresh
        # check rather than caching stale state.
        call_count = {"n": 0}
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "session_buddy.core":
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise ImportError("transient")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        first = loaded_features.FeatureDetector._check_session_management()
        # Second call (no transient this time) should reflect the real state
        monkeypatch.setattr(builtins, "__import__", original_import)
        second = loaded_features.FeatureDetector._check_session_management()
        assert first is False
        assert second is True

    def test_module_importable_from_session_buddy_core(
        self, loaded_features
    ) -> None:
        # Sanity: the module is in sys.modules under the canonical name
        assert "session_buddy.core.features" in sys.modules
        assert sys.modules["session_buddy.core.features"] is loaded_features


# ---------------------------------------------------------------------------
# Hypothesis property tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestHypothesis:
    """Property-based tests for flag projection invariants."""

    def test_flag_count_is_stable(self, loaded_features) -> None:
        # The get_feature_flags dict must always contain 13 keys, regardless
        # of which modules are present.
        from hypothesis import given, settings
        from hypothesis import strategies as st

        module_names = [
            "session_buddy.reflection_tools",
            "session_buddy.search_enhanced",
            "session_buddy.tools.search_tools",
            "session_buddy.multi_project_coordinator",
            "session_buddy.advanced_search",
            "session_buddy.settings",
            "session_buddy.context_manager",
            "session_buddy.memory_optimizer",
            "session_buddy.app_monitor",
            "session_buddy.llm_providers",
            "session_buddy.serverless_mode",
            "session_buddy.crackerjack_integration",
        ]

        @given(present=st.sets(st.sampled_from(module_names)))
        @settings(max_examples=10, deadline=None)
        def _inner(present: set[str]) -> None:
            def fake(name: str):
                if name in present:
                    return types.SimpleNamespace(name=name)
                return None

            original = loaded_features.importlib.util.find_spec
            try:
                loaded_features.importlib.util.find_spec = fake
                # Force a fresh detector with these stubbed find_spec values
                detector = loaded_features.FeatureDetector()
                flags = detector.get_feature_flags()
                # Always 13 flags
                assert len(flags) == 13
                # Every value is a bool
                assert all(isinstance(v, bool) for v in flags.values())
            finally:
                loaded_features.importlib.util.find_spec = original

        _inner()
