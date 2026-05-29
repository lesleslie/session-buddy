"""Unit tests for session_buddy.modes.base module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import tempfile

import pytest

from session_buddy.modes.base import (
    ModeConfig,
    OperationMode,
    register_mode,
    get_mode,
    _MODE_REGISTRY,
)


class TestModeConfig:
    """Tests for ModeConfig dataclass."""

    def test_create_minimal_config(self):
        """Test creating ModeConfig with only required fields."""
        config = ModeConfig(
            name="test",
            database_path="/path/to/db",
            storage_backend="file",
        )
        assert config.name == "test"
        assert config.database_path == "/path/to/db"
        assert config.storage_backend == "file"

    def test_default_feature_flags(self):
        """Test that default feature flags are all True except embeddings."""
        config = ModeConfig(
            name="test",
            database_path=":memory:",
            storage_backend="memory",
        )
        assert config.enable_embeddings is True
        assert config.enable_multi_project is True
        assert config.enable_token_optimization is True
        assert config.enable_auto_checkpoint is True
        assert config.enable_full_text_search is True
        assert config.enable_faceted_search is True
        assert config.enable_search_suggestions is True
        assert config.enable_auto_store is True
        assert config.enable_crackerjack is True
        assert config.enable_git_integration is True

    def test_custom_feature_flags(self):
        """Test creating ModeConfig with custom feature flags."""
        config = ModeConfig(
            name="custom",
            database_path="/path",
            storage_backend="s3",
            enable_embeddings=False,
            enable_multi_project=False,
            enable_token_optimization=False,
            enable_auto_checkpoint=False,
            enable_full_text_search=False,
            enable_faceted_search=False,
            enable_search_suggestions=False,
            enable_auto_store=False,
            enable_crackerjack=False,
            enable_git_integration=False,
        )
        assert config.enable_embeddings is False
        assert config.enable_multi_project is False
        assert config.enable_token_optimization is False
        assert config.enable_auto_checkpoint is False
        assert config.enable_full_text_search is False
        assert config.enable_faceted_search is False
        assert config.enable_search_suggestions is False
        assert config.enable_auto_store is False
        assert config.enable_crackerjack is False
        assert config.enable_git_integration is False

    def test_additional_settings(self):
        """Test additional_settings parameter."""
        config = ModeConfig(
            name="extra",
            database_path="/db",
            storage_backend="file",
            additional_settings={"custom_key": "custom_value", "timeout": 30},
        )
        assert config.additional_settings == {"custom_key": "custom_value", "timeout": 30}

    def test_to_dict_basic(self):
        """Test to_dict returns correct structure."""
        config = ModeConfig(
            name="dict_test",
            database_path="/path/to/db",
            storage_backend="file",
        )
        result = config.to_dict()
        assert isinstance(result, dict)
        assert result["mode"] == "dict_test"
        assert result["database_path"] == "/path/to/db"
        assert result["storage_backend"] == "file"

    def test_to_dict_includes_all_features(self):
        """Test to_dict includes all feature flags."""
        config = ModeConfig(
            name="features",
            database_path=":memory:",
            storage_backend="memory",
            enable_embeddings=True,
            enable_multi_project=True,
            enable_token_optimization=True,
            enable_auto_checkpoint=True,
            enable_full_text_search=True,
            enable_faceted_search=True,
            enable_search_suggestions=True,
            enable_auto_store=True,
            enable_crackerjack=True,
            enable_git_integration=True,
        )
        result = config.to_dict()
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

    def test_to_dict_includes_additional_settings(self):
        """Test to_dict includes additional_settings merged in."""
        config = ModeConfig(
            name="extra",
            database_path="/db",
            storage_backend="file",
            additional_settings={"custom": "value", "count": 5},
        )
        result = config.to_dict()
        assert result["custom"] == "value"
        assert result["count"] == 5

    def test_dataclass_is_frozen(self):
        """Test that ModeConfig is frozen."""
        config = ModeConfig(
            name="frozen",
            database_path="/db",
            storage_backend="memory",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            config.name = "changed"

    def test_dataclass_with_fresh_fields(self):
        """Test creating config with various field values."""
        config = ModeConfig(
            name="fields",
            database_path=":memory:",
            storage_backend="memory",
            enable_embeddings=False,
            enable_crackerjack=False,
        )
        assert config.enable_embeddings is False
        assert config.enable_crackerjack is False


class TestOperationMode:
    """Tests for OperationMode abstract base class."""

    def test_cannot_instantiate_directly(self):
        """Test that OperationMode cannot be instantiated directly."""
        with pytest.raises(TypeError):
            OperationMode()

    def test_abstract_methods_defined(self):
        """Test that name property and get_config are abstract."""
        # OperationMode should have name as an abstract property
        # and get_config as an abstract method
        assert hasattr(OperationMode, "name")
        assert hasattr(OperationMode, "get_config")

    def test_validate_environment_default_returns_empty_list(self):
        """Test that validate_environment returns [] by default."""

        class MinimalMode(OperationMode):
            @property
            def name(self) -> str:
                return "minimal"

            def get_config(self) -> ModeConfig:
                return ModeConfig(name="minimal", database_path=":memory:", storage_backend="memory")

        mode = MinimalMode()
        result = mode.validate_environment()
        assert result == []

    def test_get_startup_message_default_format(self):
        """Test that get_startup_message returns formatted string."""

        class SimpleMode(OperationMode):
            @property
            def name(self) -> str:
                return "simple"

            def get_config(self) -> ModeConfig:
                return ModeConfig(name="simple", database_path=":memory:", storage_backend="memory")

        mode = SimpleMode()
        result = mode.get_startup_message()
        assert "🚀" in result
        assert "simple" in result


class TestRegisterMode:
    """Tests for register_mode function."""

    def test_register_mode_adds_to_registry(self):
        """Test that register_mode adds mode class to registry."""

        class CustomMode(OperationMode):
            @property
            def name(self) -> str:
                return "custom"

            def get_config(self) -> ModeConfig:
                return ModeConfig(name="custom", database_path="/db", storage_backend="file")

        initial_registry_size = len(_MODE_REGISTRY)
        register_mode(CustomMode)
        assert len(_MODE_REGISTRY) == initial_registry_size + 1
        assert "custommode" in _MODE_REGISTRY

    def test_register_mode_normalizes_name(self):
        """Test that register_mode lowercases class name."""

        class MyCustomMode(OperationMode):
            @property
            def name(self) -> str:
                return "mycustom"

            def get_config(self) -> ModeConfig:
                return ModeConfig(name="mycustom", database_path="/db", storage_backend="file")

        register_mode(MyCustomMode)
        assert "mycustommode" in _MODE_REGISTRY


class TestGetMode:
    """Tests for get_mode function."""

    def test_get_mode_lite(self):
        """Test get_mode returns LiteMode for 'lite'."""
        mode = get_mode("lite")
        assert isinstance(mode, OperationMode)
        assert mode.name == "lite"

    def test_get_mode_standard(self):
        """Test get_mode returns StandardMode for 'standard'."""
        mode = get_mode("standard")
        assert isinstance(mode, OperationMode)
        assert mode.name == "standard"

    def test_get_mode_case_insensitive(self):
        """Test get_mode is case insensitive."""
        mode_upper = get_mode("LITE")
        mode_title = get_mode("Lite")
        assert isinstance(mode_upper, OperationMode)
        assert isinstance(mode_title, OperationMode)
        assert mode_upper.name == "lite"
        assert mode_title.name == "lite"

    def test_get_mode_with_underscores_and_dashes(self):
        """Test get_mode normalizes underscores and dashes by removing them.

        Note: After removing underscores/dashes, the result must exactly match
        'lite' or 'standard' - so 'lite_mode' becomes 'litemode' which is invalid.
        """
        # These normalize to "lite" and should work
        mode1 = get_mode("lite")
        assert isinstance(mode1, OperationMode)
        assert mode1.name == "lite"

        # These normalize to "litemode" which doesn't match any mode
        # so they should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            get_mode("lite_mode")
        assert "Invalid mode" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            get_mode("lite-mode")
        assert "Invalid mode" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            get_mode("litemode")
        assert "Invalid mode" in str(exc_info.value)

    def test_get_mode_invalid_name_raises_error(self):
        """Test get_mode raises ValueError for invalid mode name."""
        with pytest.raises(ValueError) as exc_info:
            get_mode("invalid_mode_name")
        assert "Invalid mode" in str(exc_info.value)
        # After normalization, underscores are removed, so 'invalid_mode_name' becomes 'invalidmodename'
        assert "invalidmodename" in str(exc_info.value)

    def test_get_mode_none_uses_environment_variable(self):
        """Test get_mode uses SESSION_BUDDY_MODE env var when mode_name is None."""
        with patch.dict("os.environ", {"SESSION_BUDDY_MODE": "standard"}):
            mode = get_mode(None)
            assert isinstance(mode, OperationMode)
            assert mode.name == "standard"

        with patch.dict("os.environ", {"SESSION_BUDDY_MODE": "lite"}):
            mode = get_mode(None)
            assert isinstance(mode, OperationMode)
            assert mode.name == "lite"

    def test_get_mode_none_defaults_to_standard(self):
        """Test get_mode defaults to standard mode when env var not set."""
        with patch.dict("os.environ", {}, clear=True):
            mode = get_mode(None)
            assert isinstance(mode, OperationMode)
            assert mode.name == "standard"

    def test_get_mode_explicit_none_overrides_env(self):
        """Test that explicit mode_name=None still uses environment variable."""
        with patch.dict("os.environ", {"SESSION_BUDDY_MODE": "lite"}):
            mode = get_mode(None)
            assert mode.name == "lite"

    def test_get_mode_with_standard_string(self):
        """Test get_mode with 'standard' string."""
        mode = get_mode("standard")
        assert isinstance(mode, OperationMode)
        assert mode.name == "standard"

    def test_get_mode_with_empty_string_normalizes_to_empty_and_fails(self):
        """Test that empty string gets normalized and fails since '' is not 'lite' or 'standard'."""
        with patch.dict("os.environ", {"SESSION_BUDDY_MODE": "standard"}):
            # Empty string passes the None check and gets normalized to empty string
            # which then fails validation since '' doesn't match any mode
            with pytest.raises(ValueError) as exc_info:
                get_mode("")
            assert "Invalid mode" in str(exc_info.value)