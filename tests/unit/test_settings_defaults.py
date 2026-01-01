from __future__ import annotations

from session_buddy.settings import SessionMgmtSettings, get_settings


def test_settings_defaults_present() -> None:
    s = get_settings(reload=True)
    assert s.filesystem_dedupe_ttl_seconds >= 60
    assert s.filesystem_max_file_size_bytes >= 10000
    assert isinstance(s.filesystem_ignore_dirs, list)
    assert s.llm_extraction_timeout >= 1
    assert s.llm_extraction_retries >= 0


def test_legacy_debug_maps_to_enable_debug_mode() -> None:
    settings = SessionMgmtSettings.model_validate({"debug": True})
    assert settings.enable_debug_mode is True
