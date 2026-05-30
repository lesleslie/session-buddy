from __future__ import annotations

from pathlib import Path

import pytest


def test_lite_mode_configuration_and_messages() -> None:
    from session_buddy.modes.lite import LiteMode

    mode = LiteMode()
    config = mode.get_config()

    assert mode.name == "lite"
    assert config.name == "lite"
    assert config.database_path == ":memory:"
    assert config.storage_backend == "memory"
    assert config.enable_embeddings is False
    assert config.enable_multi_project is False
    assert config.enable_token_optimization is False
    assert config.enable_auto_checkpoint is False
    assert config.enable_full_text_search is True
    assert config.enable_faceted_search is False
    assert config.enable_search_suggestions is False
    assert config.enable_auto_store is False
    assert config.enable_crackerjack is False
    assert config.enable_git_integration is False
    assert mode.validate_environment() == []
    assert "lite mode" in mode.get_startup_message()
    assert mode.to_dict()["mode"] == "lite"


def test_standard_mode_configuration_and_environment_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from session_buddy.modes.standard import StandardMode

    monkeypatch.setattr(
        "session_buddy.modes.standard.os.path.expanduser",
        lambda _: str(tmp_path / ".claude" / "data"),
    )

    mode = StandardMode()
    config = mode.get_config()

    assert mode.name == "standard"
    assert config.name == "standard"
    assert config.database_path.endswith("reflection.duckdb")
    assert config.storage_backend == "file"
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
    assert "standard mode" in mode.get_startup_message()
    assert mode.to_dict()["mode"] == "standard"

    assert mode.validate_environment() == []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Path, "touch", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("nope")))
        errors = mode.validate_environment()
        assert errors and "not writable" in errors[0]
