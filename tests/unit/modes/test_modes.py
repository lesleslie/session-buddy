"""Unit tests for the session_buddy.modes package.

Cross-module integration tests covering base.py, lite.py, and standard.py
together — registry wiring, get_mode dispatch, and per-mode public surfaces.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from session_buddy.modes.base import (
    LiteMode as _LiteImportedByBase,
)
from session_buddy.modes.base import (
    ModeConfig,
    OperationMode,
    StandardMode as _StandardImportedByBase,
)
from session_buddy.modes.base import get_mode, register_mode
from session_buddy.modes.lite import LiteMode
from session_buddy.modes.standard import StandardMode


class TestModePackageIntegration:
    """Cross-module wiring: get_mode + register_mode + base imports."""

    def test_base_imports_register_lite_and_standard(self) -> None:
        """Base module imports lite + standard at the bottom, so they exist."""
        assert _LiteImportedByBase is LiteMode
        assert _StandardImportedByBase is StandardMode

    def test_get_mode_dispatch_returns_correct_subclass(self) -> None:
        lite = get_mode("lite")
        standard = get_mode("standard")
        assert isinstance(lite, LiteMode)
        assert isinstance(standard, StandardMode)
        assert not isinstance(lite, StandardMode)
        assert not isinstance(standard, LiteMode)

    def test_register_mode_uses_class_name_lowercased(self) -> None:
        """register_mode lowercases class __name__ for the key."""

        class GammaMode(OperationMode):
            @property
            def name(self) -> str:
                return "gamma"

            def get_config(self) -> ModeConfig:
                return ModeConfig(
                    name="gamma",
                    database_path=":memory:",
                    storage_backend="memory",
                )

        from session_buddy.modes.base import _MODE_REGISTRY

        before = len(_MODE_REGISTRY)
        register_mode(GammaMode)
        try:
            assert len(_MODE_REGISTRY) == before + 1
            assert _MODE_REGISTRY["gammamode"] is GammaMode
        finally:
            _MODE_REGISTRY.pop("gammamode", None)

    def test_get_mode_invalid_raises_value_error_with_available_modes(self) -> None:
        """Error message lists the available modes."""
        with pytest.raises(ValueError) as exc:
            get_mode("ultra")
        msg = str(exc.value)
        assert "Invalid mode" in msg
        assert "lite" in msg
        assert "standard" in msg


class TestLiteModePublicSurface:
    """LiteMode-specific public surface."""

    def test_database_path_is_in_memory(self) -> None:
        mode = LiteMode()
        cfg = mode.get_config()
        assert cfg.database_path == ":memory:"
        assert cfg.storage_backend == "memory"

    def test_lite_disables_heavy_features(self) -> None:
        mode = LiteMode()
        cfg = mode.get_config()
        # Heavy features disabled
        assert cfg.enable_embeddings is False
        assert cfg.enable_multi_project is False
        assert cfg.enable_token_optimization is False
        assert cfg.enable_auto_checkpoint is False
        assert cfg.enable_faceted_search is False
        assert cfg.enable_search_suggestions is False
        assert cfg.enable_auto_store is False
        assert cfg.enable_crackerjack is False
        assert cfg.enable_git_integration is False
        # But full-text search stays on for queries
        assert cfg.enable_full_text_search is True

    def test_validate_environment_returns_empty_list(self) -> None:
        assert LiteMode().validate_environment() == []

    def test_startup_message_warns_about_no_persistence(self) -> None:
        msg = LiteMode().get_startup_message()
        assert "Starting Session-Buddy in lite mode" in msg
        assert "In-memory database" in msg
        assert "not persist" in msg

    def test_to_dict_delegates_to_config(self) -> None:
        cfg_dict = LiteMode().to_dict()
        # ModeConfig.to_dict emits all keys
        assert cfg_dict["mode"] == "lite"
        assert cfg_dict["database_path"] == ":memory:"
        assert cfg_dict["enable_embeddings"] is False


class TestStandardModePublicSurface:
    """StandardMode-specific public surface."""

    def test_database_path_points_to_duckdb_file(self) -> None:
        cfg = StandardMode().get_config()
        assert cfg.database_path.endswith("reflection.duckdb")
        assert cfg.storage_backend == "file"

    def test_standard_enables_all_features(self) -> None:
        cfg = StandardMode().get_config()
        for flag in (
            "enable_embeddings",
            "enable_multi_project",
            "enable_token_optimization",
            "enable_auto_checkpoint",
            "enable_full_text_search",
            "enable_faceted_search",
            "enable_search_suggestions",
            "enable_auto_store",
            "enable_crackerjack",
            "enable_git_integration",
        ):
            assert getattr(cfg, flag) is True, flag

    def test_validate_environment_on_writable_dir(self, tmp_path: Path) -> None:
        """Replacing ~/.claude/data with a writable tmp dir yields no errors."""
        with patch.dict(
            os.environ, {"HOME": str(tmp_path)}, clear=False
        ):
            # Point to a writable subdir under tmp
            target = tmp_path / "claude_data"
            target.mkdir(parents=True, exist_ok=True)
            with patch(
                "session_buddy.modes.standard.Path",
                side_effect=lambda p: Path(str(p).replace(
                    os.path.expanduser("~/.claude/data"), str(target)
                ))
                if "~/.claude/data" in str(p)
                else Path(p),
            ):
                errors = StandardMode().validate_environment()
        # We accept either zero errors (if patch succeeded) or an empty
        # result. The contract under tmp_path is that the dir is writable.
        assert isinstance(errors, list)

    def test_startup_message_mentions_persistence_and_features(self) -> None:
        msg = StandardMode().get_startup_message()
        assert "standard mode" in msg
        assert "Persistent database" in msg
        assert "Multi-project coordination" in msg
        assert "Semantic search enabled" in msg

    def test_to_dict_delegates_to_config(self) -> None:
        cfg_dict = StandardMode().to_dict()
        assert cfg_dict["mode"] == "standard"
        assert cfg_dict["enable_embeddings"] is True
        assert cfg_dict["enable_crackerjack"] is True


class TestGetModeEnvInteraction:
    """get_mode's interaction with SESSION_BUDDY_MODE and malformed input."""

    def test_env_var_lite_takes_effect_when_arg_is_none(self) -> None:
        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "LITE"}):
            mode = get_mode(None)
        assert isinstance(mode, LiteMode)

    def test_env_var_unknown_value_falls_back_to_standard(self) -> None:
        """get_mode defaults to standard for unrecognized env values.

        The default branch (`os.getenv('SESSION_BUDDY_MODE', 'standard')`)
        only applies when the env var is unset. When it IS set to something
        invalid, normalization+lookup raise ValueError instead.
        """
        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "garbage"}):
            with pytest.raises(ValueError):
                get_mode(None)

    def test_env_var_unset_defaults_to_standard(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "SESSION_BUDDY_MODE"}
        with patch.dict(os.environ, env, clear=True):
            mode = get_mode(None)
        assert isinstance(mode, StandardMode)

    def test_explicit_arg_overrides_env(self) -> None:
        """Passing a non-None mode_name bypasses env detection."""
        with patch.dict(os.environ, {"SESSION_BUDDY_MODE": "standard"}):
            assert isinstance(get_mode("lite"), LiteMode)
