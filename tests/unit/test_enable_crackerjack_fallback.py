from session_buddy.config.feature_flags import FeatureFlags, get_feature_flags


def test_enable_crackerjack_fallback_defaults_to_false():
    """Default per project's safe-rollout pattern."""
    flags = FeatureFlags()
    assert flags.enable_crackerjack_fallback is False


def test_get_feature_flags_resolves_yaml_default(monkeypatch, tmp_path):
    """When YAML is loaded and env var is unset, the resolver returns the YAML value."""
    # The default is False; no YAML override -> False
    monkeypatch.delenv("SESSION_BUDDY_CRACKERJACK_FALLBACK", raising=False)
    assert get_feature_flags().enable_crackerjack_fallback is False


def test_env_var_true_overrides_default(monkeypatch):
    monkeypatch.setenv("SESSION_BUDDY_CRACKERJACK_FALLBACK", "true")
    assert get_feature_flags().enable_crackerjack_fallback is True


def test_env_var_one_overrides_default(monkeypatch):
    """_get_env_bool accepts 1/0/yes/no/on/off in addition to true/false."""
    monkeypatch.setenv("SESSION_BUDDY_CRACKERJACK_FALLBACK", "1")
    assert get_feature_flags().enable_crackerjack_fallback is True


def test_env_var_zero_overrides_default(monkeypatch):
    """Operators can disable via =0; the rollback path uses this."""
    monkeypatch.setenv("SESSION_BUDDY_CRACKERJACK_FALLBACK", "0")
    assert get_feature_flags().enable_crackerjack_fallback is False
