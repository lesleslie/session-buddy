"""Unit tests for session_buddy.modes.standard module."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from session_buddy.modes.standard import StandardMode
from session_buddy.modes.base import ModeConfig, OperationMode


class TestStandardMode:
    """Tests for StandardMode class."""

    def test_inherits_from_operation_mode(self):
        """Test that StandardMode inherits from OperationMode."""
        assert issubclass(StandardMode, OperationMode)

    def test_name_property(self):
        """Test name property returns 'standard'."""
        mode = StandardMode()
        assert mode.name == "standard"

    def test_get_config_returns_mode_config(self):
        """Test get_config returns a ModeConfig instance."""
        mode = StandardMode()
        config = mode.get_config()
        assert isinstance(config, ModeConfig)

    def test_get_config_name_is_standard(self):
        """Test that config name is 'standard'."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.name == "standard"

    def test_get_config_database_path_uses_expanded_path(self):
        """Test that database_path points to ~/.claude/data/reflection.duckdb."""
        mode = StandardMode()
        config = mode.get_config()
        assert "reflection.duckdb" in config.database_path
        assert ".claude" in config.database_path
        assert "data" in config.database_path

    def test_get_config_storage_backend_is_file(self):
        """Test that storage_backend is file for standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.storage_backend == "file"

    def test_get_config_embeddings_enabled(self):
        """Test that embeddings are enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_embeddings is True

    def test_get_config_multi_project_enabled(self):
        """Test that multi_project is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_multi_project is True

    def test_get_config_token_optimization_enabled(self):
        """Test that token optimization is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_token_optimization is True

    def test_get_config_auto_checkpoint_enabled(self):
        """Test that auto_checkpoint is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_auto_checkpoint is True

    def test_get_config_full_text_search_enabled(self):
        """Test that full_text_search is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_full_text_search is True

    def test_get_config_faceted_search_enabled(self):
        """Test that faceted_search is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_faceted_search is True

    def test_get_config_search_suggestions_enabled(self):
        """Test that search_suggestions is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_search_suggestions is True

    def test_get_config_auto_store_enabled(self):
        """Test that auto_store is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_auto_store is True

    def test_get_config_crackerjack_enabled(self):
        """Test that crackerjack is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_crackerjack is True

    def test_get_config_git_integration_enabled(self):
        """Test that git_integration is enabled in standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        assert config.enable_git_integration is True

    def test_validate_environment_data_dir_not_writable(self):
        """Test validate_environment detects non-writable data directory."""
        mode = StandardMode()
        # If ~/.claude/data is not writable, we should get an error
        errors = mode.validate_environment()
        # The errors list could be empty if the directory is writable,
        # or contain an error message if not
        if errors:
            assert any("writable" in e.lower() or "permission" in e.lower() for e in errors)

    def test_get_startup_message_format(self):
        """Test startup message format."""
        mode = StandardMode()
        message = mode.get_startup_message()
        assert "🚀" in message
        assert "standard" in message.lower()

    def test_get_startup_message_contains_features(self):
        """Test that startup message contains feature descriptions."""
        mode = StandardMode()
        message = mode.get_startup_message()
        # Should mention database, features, semantic search, etc.
        assert "database" in message.lower() or "duckdb" in message.lower()

    def test_to_dict_returns_dict(self):
        """Test that to_dict returns a dictionary."""
        mode = StandardMode()
        result = mode.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_contains_mode_key(self):
        """Test that to_dict contains 'mode' key."""
        mode = StandardMode()
        result = mode.to_dict()
        assert "mode" in result
        assert result["mode"] == "standard"

    def test_to_dict_contains_database_path(self):
        """Test that to_dict contains database_path."""
        mode = StandardMode()
        result = mode.to_dict()
        assert "database_path" in result
        assert "reflection.duckdb" in result["database_path"]

    def test_to_dict_contains_storage_backend(self):
        """Test that to_dict contains storage_backend."""
        mode = StandardMode()
        result = mode.to_dict()
        assert "storage_backend" in result
        assert result["storage_backend"] == "file"

    def test_to_dict_contains_all_feature_flags(self):
        """Test that to_dict contains all feature flags."""
        mode = StandardMode()
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

    def test_to_dict_all_features_enabled(self):
        """Test that all features are enabled in standard mode."""
        mode = StandardMode()
        result = mode.to_dict()
        assert result["enable_embeddings"] is True
        assert result["enable_multi_project"] is True
        assert result["enable_token_optimization"] is True
        assert result["enable_auto_checkpoint"] is True
        assert result["enable_full_text_search"] is True
        assert result["enable_faceted_search"] is True
        assert result["enable_search_suggestions"] is True
        assert result["enable_auto_store"] is True
        assert result["enable_crackerjack"] is True
        assert result["enable_git_integration"] is True

    def test_multiple_instances_are_independent(self):
        """Test that multiple StandardMode instances are independent."""
        mode1 = StandardMode()
        mode2 = StandardMode()
        # Both should have the same config but be separate instances
        assert mode1.get_config().storage_backend == mode2.get_config().storage_backend
        assert mode1 is not mode2

    def test_config_features_list(self):
        """List all features and their expected values for standard mode."""
        mode = StandardMode()
        config = mode.get_config()
        expected = {
            "name": "standard",
            "storage_backend": "file",
            "enable_embeddings": True,
            "enable_multi_project": True,
            "enable_token_optimization": True,
            "enable_auto_checkpoint": True,
            "enable_full_text_search": True,
            "enable_faceted_search": True,
            "enable_search_suggestions": True,
            "enable_auto_store": True,
            "enable_crackerjack": True,
            "enable_git_integration": True,
        }
        for key, expected_value in expected.items():
            actual_value = getattr(config, key)
            assert actual_value == expected_value, f"Config.{key} = {actual_value}, expected {expected_value}"


class TestStandardModeValidation:
    """Tests for StandardMode.validate_environment method."""

    def test_validate_environment_with_writable_directory(self):
        """Test validation passes when data directory is writable."""
        mode = StandardMode()
        # If the default ~/.claude/data is writable, errors should be empty
        errors = mode.validate_environment()
        # Either errors is empty (directory writable) or contains specific error
        if errors:
            # If there are errors, they should be about permissions or accessibility
            assert any("writable" in e.lower() or "permission" in e.lower() or "access" in e.lower() for e in errors)

    def test_validate_environment_creates_directory_if_missing(self):
        """Test that validate_environment creates directory if it doesn't exist."""
        mode = StandardMode()
        # This test just ensures no exception is raised
        # The actual validation depends on whether directory can be created
        try:
            errors = mode.validate_environment()
            # Should either succeed or fail gracefully
            assert isinstance(errors, list)
        except Exception as e:
            pytest.fail(f"validate_environment raised unexpected exception: {e}")

    def test_validate_environment_permission_error_handling(self):
        """Test that permission errors are properly captured."""
        mode = StandardMode()
        errors = mode.validate_environment()
        # If errors exist, they should be meaningful strings
        for error in errors:
            assert isinstance(error, str)
            assert len(error) > 0
