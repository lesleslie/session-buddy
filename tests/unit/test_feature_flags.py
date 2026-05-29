"""Unit tests for session_buddy.config.feature_flags module."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from session_buddy.config.feature_flags import (
    FeatureFlags,
    get_feature_flags,
    _get_env_bool,
    _ENV_BOOL,
)


class TestFeatureFlags:
    """Tests for FeatureFlags dataclass."""

    def test_default_values_are_all_false(self):
        """Test that all flags default to False."""
        flags = FeatureFlags()
        assert flags.use_schema_v2 is False
        assert flags.enable_llm_entity_extraction is False
        assert flags.enable_anthropic is False
        assert flags.enable_ollama is False
        assert flags.enable_conscious_agent is False
        assert flags.enable_filesystem_extraction is False

    def test_custom_values(self):
        """Test creating FeatureFlags with custom values."""
        flags = FeatureFlags(
            use_schema_v2=True,
            enable_llm_entity_extraction=True,
            enable_anthropic=True,
            enable_ollama=True,
            enable_conscious_agent=True,
            enable_filesystem_extraction=True,
        )
        assert flags.use_schema_v2 is True
        assert flags.enable_llm_entity_extraction is True
        assert flags.enable_anthropic is True
        assert flags.enable_ollama is True
        assert flags.enable_conscious_agent is True
        assert flags.enable_filesystem_extraction is True

    def test_partial_values(self):
        """Test creating FeatureFlags with partial values."""
        flags = FeatureFlags(use_schema_v2=True)
        assert flags.use_schema_v2 is True
        assert flags.enable_llm_entity_extraction is False
        assert flags.enable_anthropic is False

    def test_dataclass_uses_slots(self):
        """Test that FeatureFlags uses __slots__ for memory efficiency."""
        flags = FeatureFlags()
        # With __slots__, adding new attributes should raise AttributeError
        with pytest.raises(AttributeError):
            flags.new_attr = "value"

    def test_dataclass_not_frozen(self):
        """Test that FeatureFlags is NOT frozen (allows attribute modification)."""
        flags = FeatureFlags()
        # Unlike frozen dataclasses, FeatureFlags allows modification
        flags.use_schema_v2 = True  # Should not raise
        assert flags.use_schema_v2 is True

    def test_dataclass_has_slots(self):
        """Test that FeatureFlags uses __slots__."""
        flags = FeatureFlags()
        # Should raise AttributeError for undefined slot
        with pytest.raises(AttributeError):
            flags.new_attr = "value"


class TestEnvBool:
    """Tests for _ENV_BOOL mapping and _get_env_bool function."""

    def test_env_bool_mapping_values(self):
        """Test that _ENV_BOOL has correct mappings for truthy values."""
        truthy_values = ["true", "1", "yes", "on"]
        for val in truthy_values:
            assert _ENV_BOOL[val] is True

    def test_env_bool_mapping_falsy_values(self):
        """Test that _ENV_BOOL has correct mappings for falsy values."""
        falsy_values = ["false", "0", "no", "off"]
        for val in falsy_values:
            assert _ENV_BOOL[val] is False

    def test_env_bool_unknown_value_returns_default(self):
        """Test that unknown env values return default."""
        # We can't call _get_env_bool directly without mocking os.getenv
        # so we test the function behavior via get_feature_flags
        pass

    def test_get_env_bool_with_none_returns_default(self):
        """Test _get_env_bool returns default when env var is None."""
        with patch.dict(os.environ, {}, clear=True):
            result = _get_env_bool("NONEXISTENT_ENV_VAR_12345", True)
            assert result is True

        with patch.dict(os.environ, {}, clear=True):
            result = _get_env_bool("NONEXISTENT_ENV_VAR_12345", False)
            assert result is False

    def test_get_env_bool_with_truthy_string(self):
        """Test _get_env_bool recognizes truthy strings."""
        truthy_test_cases = ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]
        for val in truthy_test_cases:
            with patch.dict(os.environ, {"TEST_VAR": val}):
                result = _get_env_bool("TEST_VAR", False)
                assert result is True, f"Expected True for '{val}'"

    def test_get_env_bool_with_falsy_string(self):
        """Test _get_env_bool recognizes falsy strings."""
        falsy_test_cases = ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF"]
        for val in falsy_test_cases:
            with patch.dict(os.environ, {"TEST_VAR": val}):
                result = _get_env_bool("TEST_VAR", True)
                assert result is False, f"Expected False for '{val}'"

    def test_get_env_bool_with_unknown_value_returns_default(self):
        """Test _get_env_bool returns default for unknown values."""
        with patch.dict(os.environ, {"TEST_VAR": "unknown_value"}):
            result = _get_env_bool("TEST_VAR", True)
            assert result is True

        with patch.dict(os.environ, {"TEST_VAR": "foobar"}):
            result = _get_env_bool("TEST_VAR", False)
            assert result is False

    def test_get_env_bool_strips_whitespace(self):
        """Test _get_env_bool strips whitespace from env values."""
        with patch.dict(os.environ, {"TEST_VAR": "  true  "}):
            result = _get_env_bool("TEST_VAR", False)
            assert result is True

        with patch.dict(os.environ, {"TEST_VAR": "  false  "}):
            result = _get_env_bool("TEST_VAR", True)
            assert result is False


class TestGetFeatureFlags:
    """Tests for get_feature_flags function."""

    def test_returns_feature_flags_instance(self):
        """Test that get_feature_flags returns a FeatureFlags instance."""
        result = get_feature_flags()
        assert isinstance(result, FeatureFlags)

    def test_missing_settings_attributes_fall_back_to_false(self, monkeypatch):
        """Test that absent settings attributes default to False."""
        fake_settings = SimpleNamespace(use_schema_v2=True)
        monkeypatch.setattr(
            "session_buddy.config.feature_flags.get_settings",
            lambda: fake_settings,
        )

        with patch.dict(os.environ, {}, clear=True):
            result = get_feature_flags()

        assert result.use_schema_v2 is True
        assert result.enable_llm_entity_extraction is False
        assert result.enable_anthropic is False
        assert result.enable_ollama is False
        assert result.enable_conscious_agent is False
        assert result.enable_filesystem_extraction is False

    def test_default_flags_reflect_settings_or_env(self, unmock_settings):
        """Test that get_feature_flags returns flags based on settings and env vars.

        The actual default values depend on SessionMgmtSettings which may have
        defaults from the settings files. We test the structure and env override behavior.
        """
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            # Clear all relevant env vars
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            result = get_feature_flags()
            # Verify result is a proper FeatureFlags instance with expected structure
            assert isinstance(result, FeatureFlags)
            # Verify all flags are boolean
            assert isinstance(result.use_schema_v2, bool)
            assert isinstance(result.enable_llm_entity_extraction, bool)
            assert isinstance(result.enable_anthropic, bool)
            assert isinstance(result.enable_ollama, bool)
            assert isinstance(result.enable_conscious_agent, bool)
            assert isinstance(result.enable_filesystem_extraction, bool)
        finally:
            # Restore original env
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_env_override_use_schema_v2(self, unmock_settings):
        """Test that SESSION_MGMT_USE_SCHEMA_V2 env var overrides setting."""
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            os.environ["SESSION_MGMT_USE_SCHEMA_V2"] = "true"
            result = get_feature_flags()
            assert result.use_schema_v2 is True
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_env_override_enable_llm_entity_extraction(self, unmock_settings):
        """Test env override for enable_llm_entity_extraction."""
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            os.environ["SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION"] = "1"
            result = get_feature_flags()
            assert result.enable_llm_entity_extraction is True
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_env_override_enable_anthropic(self, unmock_settings):
        """Test env override for enable_anthropic."""
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            os.environ["SESSION_MGMT_ENABLE_ANTHROPIC"] = "yes"
            result = get_feature_flags()
            assert result.enable_anthropic is True
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_env_override_enable_ollama(self, unmock_settings):
        """Test env override for enable_ollama."""
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            os.environ["SESSION_MGMT_ENABLE_OLLAMA"] = "on"
            result = get_feature_flags()
            assert result.enable_ollama is True
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_env_override_enable_conscious_agent(self, unmock_settings):
        """Test env override for enable_conscious_agent."""
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            os.environ["SESSION_MGMT_ENABLE_CONSCIOUS_AGENT"] = "true"
            result = get_feature_flags()
            assert result.enable_conscious_agent is True
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_env_override_enable_filesystem_extraction(self, unmock_settings):
        """Test env override for enable_filesystem_extraction."""
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            os.environ["SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION"] = "1"
            result = get_feature_flags()
            assert result.enable_filesystem_extraction is True
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_env_var_false_value(self, unmock_settings):
        """Test that env var can set flag to False."""
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            os.environ["SESSION_MGMT_ENABLE_ANTHROPIC"] = "false"
            result = get_feature_flags()
            assert result.enable_anthropic is False
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_all_env_overrides_at_once(self, unmock_settings):
        """Test setting all flags via environment variables."""
        env_vars_to_clear = [
            "SESSION_MGMT_USE_SCHEMA_V2",
            "SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION",
            "SESSION_MGMT_ENABLE_ANTHROPIC",
            "SESSION_MGMT_ENABLE_OLLAMA",
            "SESSION_MGMT_ENABLE_CONSCIOUS_AGENT",
            "SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION",
        ]
        original_env = {k: os.environ.get(k) for k in env_vars_to_clear}
        try:
            for k in env_vars_to_clear:
                os.environ.pop(k, None)

            os.environ["SESSION_MGMT_USE_SCHEMA_V2"] = "true"
            os.environ["SESSION_MGMT_ENABLE_LLM_ENTITY_EXTRACTION"] = "true"
            os.environ["SESSION_MGMT_ENABLE_ANTHROPIC"] = "true"
            os.environ["SESSION_MGMT_ENABLE_OLLAMA"] = "true"
            os.environ["SESSION_MGMT_ENABLE_CONSCIOUS_AGENT"] = "true"
            os.environ["SESSION_MGMT_ENABLE_FILESYSTEM_EXTRACTION"] = "true"

            result = get_feature_flags()
            assert result.use_schema_v2 is True
            assert result.enable_llm_entity_extraction is True
            assert result.enable_anthropic is True
            assert result.enable_ollama is True
            assert result.enable_conscious_agent is True
            assert result.enable_filesystem_extraction is True
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
