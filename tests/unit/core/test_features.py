"""Tests for session_buddy.core.features.

Exercises the FeatureDetector class and the module-level
``get_feature_flags`` proxy. Uses a **normal** import of
``session_buddy.core.features`` (NOT ``importlib.util.spec_from_file_location``)
so that coverage instrumentation observes the executed lines.

Coverage strategy
-----------------
The 13 ``_check_*`` methods are tested under all observable branches:

* ``_check_session_management`` (the only non-find_spec check)
  - True: ``session_buddy.core.session_manager`` resolves
  - False (AttributeError): attribute access raises ``AttributeError``
  - False (ImportError): the import itself fails

* ``_check_reflection_tools`` (find_spec-based with extra ValueError branch)
  - True: spec is present
  - False: spec is ``None``
  - False (ValueError): find_spec raises ``ValueError`` (stubbed spec)
  - False (ImportError): find_spec raises ``ImportError``

* The remaining 11 ``_check_*`` methods share identical
  present/missing/ImportError shape. They are exercised through a single
  parametrize block.

The ``__init__`` assignments and ``get_feature_flags()`` dict projection are
covered by the singleton tests at the bottom of the file.
"""

from __future__ import annotations

import types

import pytest

import session_buddy.core.features as features
from session_buddy.core.features import (
    FeatureDetector,
    _feature_detector,
    get_feature_flags,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _present_specs(module_names: set[str] | None = None):
    """Return a fake ``find_spec`` that reports ``module_names`` as present.

    ``find_spec`` is checked with ``is not None`` so a ``SimpleNamespace``
    is sufficient. If ``module_names`` is ``None`` every module is reported
    as present.
    """

    def fake_find_spec(name: str):
        if module_names is None:
            return types.SimpleNamespace(name=name)
        if name in module_names:
            return types.SimpleNamespace(name=name)
        return None

    return fake_find_spec


def _fake_spec_with_none():
    """Return a fake ``find_spec`` that always reports every module missing."""

    def fake_find_spec(name: str):
        return None

    return fake_find_spec


# ---------------------------------------------------------------------------
# _check_session_management — only non-find_spec check
# ---------------------------------------------------------------------------


class TestCheckSessionManagement:
    """Verify the three branches of ``_check_session_management``."""

    def test_returns_true_when_session_manager_resolvable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the real ``session_buddy.core.session_manager`` is importable."""
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _fake_spec_with_none()
        )
        # Real import path: ``session_buddy.core.session_manager`` is a module
        # attribute already accessible at import time (verified manually), so
        # the static check returns True.
        assert FeatureDetector._check_session_management() is True

    def test_returns_false_on_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ImportError raised during ``import session_buddy.core`` is mapped to False."""
        # Patch find_spec first; the import path is exercised via
        # ``builtins.__import__``.
        import builtins

        monkeypatch.setattr(
            features.importlib.util, "find_spec", _fake_spec_with_none()
        )
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "session_buddy.core":
                raise ImportError("simulated missing submodule")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert FeatureDetector._check_session_management() is False

    def test_returns_false_on_attribute_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AttributeError raised by ``session_buddy.core.session_manager`` is mapped to False.

        The production code path catches AttributeError separately because
        ``session_buddy`` defines a ``__getattr__`` that may resolve the
        submodule lazily. If ``session_buddy.core.session_manager`` does not
        exist (e.g. when the feature detector is being scanned in isolation
        or when the module is being stubbed), the attribute access — rather
        than the import itself — raises.
        """
        # Delete the attribute so the subsequent ``.session_manager``
        # access raises AttributeError. ``monkeypatch.delattr`` restores
        # the attribute on teardown.
        import session_buddy.core as sb_core

        monkeypatch.delattr(sb_core, "session_manager")
        assert FeatureDetector._check_session_management() is False


# ---------------------------------------------------------------------------
# _check_reflection_tools — find_spec-based with extra ValueError branch
# ---------------------------------------------------------------------------


class TestCheckReflectionTools:
    """``_check_reflection_tools`` has an extra ValueError branch the others lack."""

    def test_returns_true_when_spec_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _present_specs()
        )
        assert FeatureDetector._check_reflection_tools() is True

    def test_returns_false_when_spec_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec returned as ``None`` is treated as missing."""
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _fake_spec_with_none()
        )
        assert FeatureDetector._check_reflection_tools() is False

    def test_returns_false_on_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``ValueError`` is mapped to False (caught for stubbed spec objects)."""

        def raising(name: str):
            raise ValueError("simulated invalid spec")

        monkeypatch.setattr(features.importlib.util, "find_spec", raising)
        assert FeatureDetector._check_reflection_tools() is False

    def test_returns_false_on_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``ImportError`` from find_spec is mapped to False."""

        def raising(name: str):
            raise ImportError("simulated finder raised")

        monkeypatch.setattr(features.importlib.util, "find_spec", raising)
        assert FeatureDetector._check_reflection_tools() is False


# ---------------------------------------------------------------------------
# Parametrized find_spec-based checks — 11 identical shape methods
# ---------------------------------------------------------------------------


_FIND_SPEC_CHECKS = [
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
]


@pytest.mark.parametrize(("method_name", "module_name"), _FIND_SPEC_CHECKS)
class TestFindSpecBasedChecks:
    """Parametric coverage for the 11 shape-identical ``_check_*`` methods."""

    def test_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
        method_name: str,
        module_name: str,
    ) -> None:
        """When ``find_spec`` returns a non-None spec, the check passes."""
        monkeypatch.setattr(
            features.importlib.util,
            "find_spec",
            _present_specs({module_name}),
        )
        method = getattr(FeatureDetector, method_name)
        assert method() is True

    def test_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        method_name: str,
        module_name: str,
    ) -> None:
        """When ``find_spec`` returns ``None`` for the module, the check fails."""
        monkeypatch.setattr(
            features.importlib.util,
            "find_spec",
            _fake_spec_with_none(),
        )
        method = getattr(FeatureDetector, method_name)
        assert method() is False

    def test_import_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        method_name: str,
        module_name: str,
    ) -> None:
        """When ``find_spec`` raises ``ImportError`` for the module, the check fails."""

        def raising(name: str):
            if name == module_name:
                raise ImportError("simulated")
            return types.SimpleNamespace(name=name)

        monkeypatch.setattr(features.importlib.util, "find_spec", raising)
        method = getattr(FeatureDetector, method_name)
        assert method() is False


# ---------------------------------------------------------------------------
# FeatureDetector.__init__ — populates all 13 flags
# ---------------------------------------------------------------------------


class TestFeatureDetectorInit:
    """All 13 boolean attributes are populated at construction time."""

    EXPECTED_FLAGS = (
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
    )

    def test_all_attributes_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _present_specs()
        )
        detector = FeatureDetector()
        for name in self.EXPECTED_FLAGS:
            assert hasattr(detector, name), f"missing flag: {name}"
            assert isinstance(getattr(detector, name), bool), (
                f"{name} should be bool, got {type(getattr(detector, name))}"
            )

    def test_all_true_when_all_modules_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All flags are True when find_spec reports every required module as present."""
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _present_specs()
        )
        flags = FeatureDetector().get_feature_flags()
        assert all(flags.values()), flags

    def test_reflection_tools_and_session_management_true_in_real_environment(
        self,
    ) -> None:
        """In the test environment (real modules), two well-known flags are True.

        This guards against the case where the ``_feature_detector`` module-level
        singleton has been unintentionally mutated to ``False``.
        """
        flags = get_feature_flags()
        # session_manager is a real submodule in session_buddy.core — True
        # reflection_tools is a real submodule of session_buddy — True
        assert flags["SESSION_MANAGEMENT_AVAILABLE"] is True
        assert flags["REFLECTION_TOOLS_AVAILABLE"] is True


# ---------------------------------------------------------------------------
# get_feature_flags instance method — dict projection
# ---------------------------------------------------------------------------


class TestGetFeatureFlagsInstanceMethod:
    """Verify ``FeatureDetector.get_feature_flags()`` projects state into a dict."""

    def test_returns_dict_of_size_13(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _present_specs()
        )
        flags = FeatureDetector().get_feature_flags()
        assert isinstance(flags, dict)
        assert len(flags) == 13

    def test_all_values_are_bool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _fake_spec_with_none()
        )
        flags = FeatureDetector().get_feature_flags()
        for value in flags.values():
            assert isinstance(value, bool)

    def test_dict_matches_instance_attributes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each key in the dict equals the corresponding instance attribute."""
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _present_specs()
        )
        detector = FeatureDetector()
        flags = detector.get_feature_flags()
        for name, value in flags.items():
            assert getattr(detector, name) == value

    def test_dict_keys_are_stable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _present_specs()
        )
        detector = FeatureDetector()
        keys = set(detector.get_feature_flags().keys())
        expected = {
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
        assert keys == expected
        assert len(keys) == 13

    def test_partial_presence_is_reflected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Selective find_spec presence is faithfully projected."""
        present = {
            "session_buddy.search_enhanced",
            "session_buddy.settings",
        }
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _present_specs(present)
        )
        flags = FeatureDetector().get_feature_flags()
        assert flags["ENHANCED_SEARCH_AVAILABLE"] is True
        assert flags["CONFIG_AVAILABLE"] is True
        # Some other flags should be False
        assert flags["APP_MONITOR_AVAILABLE"] is False
        assert flags["CRACKERJACK_INTEGRATION_AVAILABLE"] is False


# ---------------------------------------------------------------------------
# Module-level proxy + singleton
# ---------------------------------------------------------------------------


class TestModuleLevelGetFeatureFlags:
    """Verify the module-level ``get_feature_flags`` proxies the singleton."""

    def test_returns_dict(self) -> None:
        flags = get_feature_flags()
        assert isinstance(flags, dict)
        assert len(flags) == 13

    def test_module_proxy_matches_singleton(self) -> None:
        """Module-level call returns the same dict the singleton would return."""
        flags = get_feature_flags()
        assert flags == _feature_detector.get_feature_flags()

    def test_singleton_is_feature_detector_instance(self) -> None:
        assert isinstance(_feature_detector, FeatureDetector)

    def test_module_proxy_uses_singleton_after_swap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Swapping the singleton on the module affects subsequent ``get_feature_flags`` calls."""
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _present_specs()
        )
        new_detector = FeatureDetector()
        # Temporarily replace the module-level singleton.
        original_singleton = features._feature_detector
        features._feature_detector = new_detector
        try:
            assert get_feature_flags() == new_detector.get_feature_flags()
        finally:
            features._feature_detector = original_singleton


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------


class TestModuleStructure:
    """Smoke checks on the module's public surface."""

    def test_logger_is_logging_logger(self) -> None:
        import logging

        assert isinstance(features.logger, logging.Logger)

    def test_logger_name_matches_dotted_module_path(self) -> None:
        assert features.logger.name == "session_buddy.core.features"

    def test_top_level_names(self) -> None:
        """The module exposes the expected top-level names."""
        expected = {"FeatureDetector", "get_feature_flags", "logger"}
        actual = set(dir(features))
        for name in expected:
            assert name in actual


# ---------------------------------------------------------------------------
# Property-based checks — invariant properties
# ---------------------------------------------------------------------------


class TestInvariants:
    """Properties that should hold regardless of environment state."""

    def test_flag_count_always_thirteen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even when every ``find_spec`` is mocked to return None, the dict stays 13-wide."""
        monkeypatch.setattr(
            features.importlib.util, "find_spec", _fake_spec_with_none()
        )
        detector = FeatureDetector()
        flags = detector.get_feature_flags()
        assert len(flags) == 13

    def test_session_management_does_not_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each ``_check_session_management`` call re-evaluates — no stale state."""
        import builtins

        # First call: ImportError
        original_import = builtins.__import__

        def boom_import(name, *args, **kwargs):
            if name == "session_buddy.core":
                raise ImportError("transient")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", boom_import)
        assert FeatureDetector._check_session_management() is False

        # Second call: real import recovers
        monkeypatch.setattr(builtins, "__import__", original_import)
        assert FeatureDetector._check_session_management() is True

    def test_real_environment_has_at_least_one_flag_true(self) -> None:
        """In the real test environment at least one flag is True (sanity)."""
        flags = get_feature_flags()
        assert any(flags.values()), "all flags False — environment is broken"
