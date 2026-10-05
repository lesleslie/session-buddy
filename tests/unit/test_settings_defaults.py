from __future__ import annotations

import pytest

from session_buddy.settings import SessionBuddySettings, SessionMgmtSettings, get_settings


def test_settings_defaults_present() -> None:
    s = get_settings(reload=True)
    # Nested filesystem_extraction group
    assert s.filesystem_extraction.dedupe_ttl_seconds >= 60
    assert s.filesystem_extraction.max_file_size_bytes >= 10000
    assert isinstance(s.filesystem_extraction.ignore_dirs, list)
    # Nested entity_extraction group
    assert s.entity_extraction.timeout >= 1
    assert s.entity_extraction.retries >= 0


def test_legacy_debug_maps_to_enable_debug_mode() -> None:
    """The legacy ``debug: true`` YAML key still maps to
    ``enable_debug_mode=True`` on the nested ``mcp_server`` group
    (the root-level ``debug`` field on OneiricMCPConfig is read
    by the model_validator, which maps it to ``enable_debug_mode``
    in the nested group).
    """
    from session_buddy.settings import SessionBuddySettings

    settings = get_settings()
    # New schema: enable_debug_mode lives in the mcp_server group.
    assert hasattr(settings, "mcp_server")
    assert hasattr(settings.mcp_server, "enable_debug_mode")
    # Direct validator test: the legacy ``debug: True`` mapping is
    # handled by the _map_legacy_debug_flag model_validator on
    # SessionBuddySettings.
    result = SessionBuddySettings.model_validate({"debug": True})
    assert result.mcp_server.enable_debug_mode is True


class TestGitPruneDelayValidation:
    """Test git_gc_prune_delay validation to prevent command injection."""

    def test_valid_prune_delay_formats(self):
        """Valid prune delay formats are accepted."""
        valid_delays = [
            "2.weeks",
            "1.month",
            "30.days",
            "12.hours",
            "now",
            "never",
            "1.day",
        ]

        for delay in valid_delays:
            settings = SessionMgmtSettings(git_gc_prune_delay=delay)
            assert settings.git_gc_prune_delay == delay

    def test_invalid_prune_delay_formats_raise_error(self):
        """Invalid prune delay formats raise ValidationError."""
        import pydantic

        invalid_delays = [
            "now; rm -rf /",  # Command injection
            "2.weeks; malicious",  # Chain injection
            "$(whoami)",  # Command substitution
            "",  # Empty
            "invalid",  # Bad format
            "2",  # No unit
            "weeks",  # No number
        ]

        for delay in invalid_delays:
            with pytest.raises(pydantic.ValidationError):
                SessionMgmtSettings(git_gc_prune_delay=delay)

    def test_now_value_triggers_warning(self):
        """Setting prune_delay to 'now' triggers a warning."""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            SessionMgmtSettings(git_gc_prune_delay="now")

            # Should have triggered a warning
            assert len(w) == 1
            assert "data loss" in str(w[0].message).lower()
            assert "now" in str(w[0].message).lower()

    def test_default_prune_delay_is_safe(self):
        """Default prune delay is safe (2.weeks)."""
        settings = SessionMgmtSettings()
        assert settings.git_gc_prune_delay == "2.weeks"
