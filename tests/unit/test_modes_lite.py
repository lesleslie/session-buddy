"""Unit tests for session_buddy.modes.lite module."""

from __future__ import annotations

import pytest

from session_buddy.modes.lite import LiteMode
from session_buddy.modes.base import ModeConfig, OperationMode


class TestLiteMode:
    """Tests for LiteMode class."""

    def test_inherits_from_operation_mode(self):
        """Test that LiteMode inherits from OperationMode."""
        assert issubclass(LiteMode, OperationMode)

    def test_name_property(self):
        """Test name property returns 'lite'."""
        mode = LiteMode()
        assert mode.name == "lite"

    def test_get_config_returns_mode_config(self):
        """Test get_config returns a ModeConfig instance."""
        mode = LiteMode()
        config = mode.get_config()
        assert isinstance(config, ModeConfig)

    def test_get_config_database_path_is_memory(self):
        """Test that database_path is :memory: for lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.database_path == ":memory:"

    def test_get_config_storage_backend_is_memory(self):
        """Test that storage_backend is memory for lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.storage_backend == "memory"

    def test_get_config_name_is_lite(self):
        """Test that config name is 'lite'."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.name == "lite"

    def test_get_config_embeddings_disabled(self):
        """Test that embeddings are disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_embeddings is False

    def test_get_config_multi_project_disabled(self):
        """Test that multi_project is disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_multi_project is False

    def test_get_config_token_optimization_disabled(self):
        """Test that token optimization is disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_token_optimization is False

    def test_get_config_auto_checkpoint_disabled(self):
        """Test that auto_checkpoint is disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_auto_checkpoint is False

    def test_get_config_full_text_search_enabled(self):
        """Test that full_text_search is enabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_full_text_search is True

    def test_get_config_faceted_search_disabled(self):
        """Test that faceted_search is disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_faceted_search is False

    def test_get_config_search_suggestions_disabled(self):
        """Test that search_suggestions is disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_search_suggestions is False

    def test_get_config_auto_store_disabled(self):
        """Test that auto_store is disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_auto_store is False

    def test_get_config_crackerjack_disabled(self):
        """Test that crackerjack is disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_crackerjack is False

    def test_get_config_git_integration_disabled(self):
        """Test that git_integration is disabled in lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        assert config.enable_git_integration is False

    def test_validate_environment_returns_empty_list(self):
        """Test that lite mode validation always passes."""
        mode = LiteMode()
        errors = mode.validate_environment()
        assert errors == []

    def test_get_startup_message_format(self):
        """Test startup message format."""
        mode = LiteMode()
        message = mode.get_startup_message()
        assert "🚀" in message
        assert "lite" in message.lower()
        assert "memory" in message.lower() or "in-memory" in message.lower()

    def test_get_startup_message_contains_warning(self):
        """Test that startup message contains persistence warning."""
        mode = LiteMode()
        message = mode.get_startup_message()
        assert "⚠️" in message or "WARNING" in message or "not persist" in message

    def test_to_dict_returns_dict(self):
        """Test that to_dict returns a dictionary."""
        mode = LiteMode()
        result = mode.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_contains_mode_key(self):
        """Test that to_dict contains 'mode' key."""
        mode = LiteMode()
        result = mode.to_dict()
        assert "mode" in result
        assert result["mode"] == "lite"

    def test_to_dict_contains_database_path(self):
        """Test that to_dict contains database_path."""
        mode = LiteMode()
        result = mode.to_dict()
        assert "database_path" in result
        assert result["database_path"] == ":memory:"

    def test_to_dict_contains_storage_backend(self):
        """Test that to_dict contains storage_backend."""
        mode = LiteMode()
        result = mode.to_dict()
        assert "storage_backend" in result
        assert result["storage_backend"] == "memory"

    def test_to_dict_contains_all_feature_flags(self):
        """Test that to_dict contains all feature flags."""
        mode = LiteMode()
        result = mode.to_dict()
        # Check all feature flags are present
        assert "enable_embeddings" in result
        assert "enable_multi_project" in result
        assert "enable_token_optimization" in result
        assert "enable_auto_checkpoint" in result
        assert "enable_full_text_search" in result
        assert "enable_faceted_search" in result
        assert "enable_search_suggestions" in result
        assert "enable_auto_store" in result
        assert "enable_crackerjack" in result
        assert "enable_git_integration" in result

    def test_multiple_instances_are_independent(self):
        """Test that multiple LiteMode instances are independent."""
        mode1 = LiteMode()
        mode2 = LiteMode()
        # Both should have the same config but be separate instances
        assert mode1.get_config().database_path == mode2.get_config().database_path
        assert mode1 is not mode2

    def test_config_features_list(self):
        """List all features and their expected values for lite mode."""
        mode = LiteMode()
        config = mode.get_config()
        expected = {
            "name": "lite",
            "database_path": ":memory:",
            "storage_backend": "memory",
            "enable_embeddings": False,
            "enable_multi_project": False,
            "enable_token_optimization": False,
            "enable_auto_checkpoint": False,
            "enable_full_text_search": True,
            "enable_faceted_search": False,
            "enable_search_suggestions": False,
            "enable_auto_store": False,
            "enable_crackerjack": False,
            "enable_git_integration": False,
        }
        for key, expected_value in expected.items():
            actual_value = getattr(config, key)
            assert actual_value == expected_value, f"Config.{key} = {actual_value}, expected {expected_value}"
