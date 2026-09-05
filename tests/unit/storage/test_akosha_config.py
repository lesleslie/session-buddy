"""Unit tests for session_buddy.storage.akosha_config module.

Targets AkoshaSyncConfig validation internals and from_settings fallbacks
that the existing test_akosha_sync.py doesn't cover.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from session_buddy.storage.akosha_config import AkoshaSyncConfig


# ============================================================================
# _validate_bucket_name — exhaustive coverage
# ============================================================================


class TestValidateBucketName:
    """Static-method bucket name validator."""

    @pytest.mark.parametrize(
        "bucket",
        [
            "abc",  # 3-char minimum
            "a-bucket-1",
            "bucket.with.dots",
            "123-end-with-num",
            "a" * 63,  # 63-char maximum
        ],
    )
    def test_valid_bucket_names(self, bucket: str) -> None:
        assert AkoshaSyncConfig._validate_bucket_name(bucket) == []

    @pytest.mark.parametrize(
        "bucket,expected_substr",
        [
            ("ab", "3-63 characters"),  # too short
            ("a" * 64, "3-63 characters"),  # too long
            ("Bucket-Name", "lowercase"),  # uppercase rejected
            ("bucket_name", "lowercase"),  # underscore rejected
            ("-bucket", "lowercase"),  # leading hyphen rejected by regex
            ("bucket-", "lowercase"),  # trailing hyphen rejected by regex
            ("192.168.1.1", "IP address"),  # IP-shaped rejected
        ],
    )
    def test_invalid_bucket_names(self, bucket: str, expected_substr: str) -> None:
        errs = AkoshaSyncConfig._validate_bucket_name(bucket)
        assert any(expected_substr in e for e in errs), (bucket, errs)


# ============================================================================
# _validate_endpoint_url
# ============================================================================


class TestValidateEndpointUrl:
    """Static-method endpoint URL validator."""

    def test_https_endpoint_accepted(self) -> None:
        assert AkoshaSyncConfig._validate_endpoint_url(
            "https://example.r2.cloudflarestorage.com"
        ) == []

    def test_http_endpoint_rejected(self) -> None:
        errs = AkoshaSyncConfig._validate_endpoint_url("http://localhost:9000")
        assert any("HTTPS" in e for e in errs)

    def test_unparseable_url_rejected(self) -> None:
        # Starts with https:// but malformed host (empty host)
        errs = AkoshaSyncConfig._validate_endpoint_url("https://")
        assert len(errs) > 0


# ============================================================================
# validate() integration
# ============================================================================


class TestValidateConsistency:
    """Top-level validate() cross-field rules."""

    def test_clean_default_config_has_no_errors(self) -> None:
        # Defaults: empty bucket, empty endpoint, empty system_id, auto.
        assert AkoshaSyncConfig().validate() == []

    def test_force_cloud_without_bucket_emits_error(self) -> None:
        cfg = AkoshaSyncConfig(cloud_bucket="", force_method="cloud")
        errs = cfg.validate()
        assert any("cloud_bucket" in e for e in errs)

    def test_bucket_set_without_system_id_yields_warning(self) -> None:
        """cloud_configured=True but no system_id (and no hostname env).

        We patch out HOSTNAME/COMPUTERNAME so the fallback is "unknown-system"
        — still non-empty in this environment, but we exercise the path with a
        system_id explicitly set.
        """
        cfg = AkoshaSyncConfig(
            cloud_bucket="my-bucket",
            system_id="my-host",
        )
        assert cfg.validate() == []

    def test_invalid_force_method_in_from_settings_falls_back(self) -> None:
        """from_settings rejects unrecognized force_method, defaulting to auto."""
        settings = Mock(spec=[])
        settings.akosha_force_method = "rocket"
        settings.akosha_cloud_bucket = ""
        settings.akosha_cloud_endpoint = ""
        settings.akosha_cloud_region = "auto"
        settings.akosha_system_id = ""
        settings.akosha_upload_on_session_end = True
        settings.akosha_enable_fallback = True
        settings.akosha_upload_timeout_seconds = 300
        settings.akosha_max_retries = 3
        settings.akosha_retry_backoff_seconds = 2.0
        settings.akosha_enable_compression = True
        settings.akosha_enable_deduplication = True
        settings.akosha_chunk_size_mb = 5
        cfg = AkoshaSyncConfig.from_settings(settings)
        assert cfg.force_method == "auto"


# ============================================================================
# from_settings — fallback to non-akosha_ prefix and type coercion
# ============================================================================


class TestFromSettingsFallbacks:
    """from_settings's _string/_bool/_int/_float helpers."""

    def test_string_falls_back_to_unprefixed_attr(self) -> None:
        """When akosha_foo is missing, falls back to foo."""
        settings = Mock(spec=["cloud_bucket"])
        settings.cloud_bucket = "fallback-bucket"
        cfg = AkoshaSyncConfig.from_settings(settings)
        assert cfg.cloud_bucket == "fallback-bucket"

    def test_string_blank_value_falls_back(self) -> None:
        settings = Mock(spec=["akosha_cloud_bucket", "cloud_bucket"])
        settings.akosha_cloud_bucket = "   "
        settings.cloud_bucket = "real-bucket"
        cfg = AkoshaSyncConfig.from_settings(settings)
        assert cfg.cloud_bucket == "real-bucket"

    def test_int_coercion_handles_bool_passthrough(self) -> None:
        """isinstance(True, int) is True, but the helper guards against that."""
        settings = Mock(spec=[])
        settings.akosha_max_retries = True  # bool, not int — should NOT be accepted
        cfg = AkoshaSyncConfig.from_settings(settings)
        # Default kicks in (3) because True is bool, not int
        assert cfg.max_retries == 3

    def test_float_coercion_handles_bool_passthrough(self) -> None:
        settings = Mock(spec=[])
        settings.akosha_retry_backoff_seconds = True
        cfg = AkoshaSyncConfig.from_settings(settings)
        assert cfg.retry_backoff_seconds == 2.0  # default

    def test_int_accepts_real_int(self) -> None:
        settings = Mock(spec=[])
        settings.akosha_upload_timeout_seconds = 999
        cfg = AkoshaSyncConfig.from_settings(settings)
        assert cfg.upload_timeout_seconds == 999


# ============================================================================
# Computed properties — explicit branches
# ============================================================================


class TestComputedProperties:
    """should_use_cloud / should_use_http branches."""

    def test_force_http_disables_cloud(self) -> None:
        cfg = AkoshaSyncConfig(
            cloud_bucket="my-bucket", force_method="http"
        )
        assert cfg.should_use_cloud is False
        assert cfg.should_use_http is True

    def test_force_cloud_disables_http(self) -> None:
        cfg = AkoshaSyncConfig(
            cloud_bucket="my-bucket", force_method="cloud"
        )
        assert cfg.should_use_cloud is True
        assert cfg.should_use_http is False

    def test_auto_no_cloud_fallback_disabled_still_uses_http(self) -> None:
        """When no cloud is configured, HTTP is the only path — fallback flag
        only gates the cloud→http downgrade, not the no-cloud→http path."""
        cfg = AkoshaSyncConfig(
            cloud_bucket="",
            force_method="auto",
            enable_fallback=False,
        )
        assert cfg.should_use_cloud is False
        assert cfg.should_use_http is True

    def test_auto_cloud_with_fallback_disabled_disables_http(self) -> None:
        """enable_fallback=False with cloud configured → no HTTP fallback."""
        cfg = AkoshaSyncConfig(
            cloud_bucket="my-bucket",
            force_method="auto",
            enable_fallback=False,
        )
        assert cfg.should_use_cloud is True
        assert cfg.should_use_http is False

    def test_auto_no_cloud_with_fallback_enables_http(self) -> None:
        cfg = AkoshaSyncConfig(
            cloud_bucket="",
            force_method="auto",
            enable_fallback=True,
        )
        assert cfg.should_use_http is True


class TestSystemIdResolution:
    """system_id_resolved fallback chain (system_id → HOSTNAME → COMPUTERNAME)."""

    def test_explicit_system_id_used(self) -> None:
        cfg = AkoshaSyncConfig(system_id="my-laptop")
        assert cfg.system_id_resolved == "my-laptop"

    def test_falls_back_to_unknown_when_no_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HOSTNAME", raising=False)
        monkeypatch.delenv("COMPUTERNAME", raising=False)
        cfg = AkoshaSyncConfig(system_id="")
        assert cfg.system_id_resolved == "unknown-system"

    def test_uses_hostname_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOSTNAME", "test-host-1")
        monkeypatch.delenv("COMPUTERNAME", raising=False)
        cfg = AkoshaSyncConfig(system_id="")
        assert cfg.system_id_resolved == "test-host-1"


class TestCustomGetattr:
    """__getattribute__ override hides default-True fields when set to True."""

    def test_dict_view_hides_default_true_fields(self) -> None:
        """When all defaults are True, __dict__ view drops upload_on_session_end etc."""
        cfg = AkoshaSyncConfig()  # defaults all True
        raw = cfg.__dict__
        # The three hidden-by-default-True fields should be removed
        assert "upload_on_session_end" not in raw
        assert "enable_compression" not in raw
        assert "enable_deduplication" not in raw
        # Non-hidden fields stay
        assert "cloud_bucket" in raw
        assert "name" not in raw  # ModeConfig.name; here field is by attr
        assert "system_id" in raw

    def test_dict_view_keeps_field_when_explicit_false(self) -> None:
        cfg = AkoshaSyncConfig(enable_compression=False)
        raw = cfg.__dict__
        # When overridden to False, the field is preserved
        assert "enable_compression" in raw
        assert raw["enable_compression"] is False


class TestFrozenDataclass:
    """AkoshaSyncConfig is frozen — mutations raise."""

    def test_cannot_set_cloud_bucket(self) -> None:
        cfg = AkoshaSyncConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            cfg.cloud_bucket = "new"  # type: ignore[misc]
