"""Unit tests for ``session_buddy.core.checkpoint.manifest_resolver``.

The function under test has three branches:
1. explicit arg wins (regardless of env var)
2. ECOSYSTEM_MANIFEST env var set (when no explicit arg)
3. neither -> default ``settings/ecosystem.yaml`` (relative to cwd)
"""

from __future__ import annotations

from pathlib import Path

from session_buddy.core.checkpoint.manifest_resolver import (
    DEFAULT_RELATIVE_PATH,
    resolve_manifest_path,
)


class TestResolveManifestPathExplicit:
    """Branch 1: ``explicit`` argument is returned verbatim."""

    def test_returns_exact_path_when_provided(self) -> None:
        result = resolve_manifest_path(Path("/tmp/custom.yaml"))
        assert result == Path("/tmp/custom.yaml")

    def test_explicit_wins_over_env_var(self, monkeypatch) -> None:
        monkeypatch.setenv("ECOSYSTEM_MANIFEST", "/from/env.yaml")
        explicit = Path("/tmp/explicit-wins.yaml")
        result = resolve_manifest_path(explicit)
        assert result == explicit

    def test_explicit_pathlib_object_preserved(self) -> None:
        explicit = Path("relative/explicit.yaml")
        result = resolve_manifest_path(explicit)
        assert isinstance(result, Path)
        assert result == explicit

    def test_explicit_zero_is_treated_as_set(self) -> None:
        """A valid Path object must be honored, not coerced to falsy."""
        explicit = Path("settings/zero.yaml")
        result = resolve_manifest_path(explicit)
        assert result == explicit


class TestResolveManifestPathEnvVar:
    """Branch 2: ECOSYSTEM_MANIFEST env var supplies the path."""

    def test_env_var_returned_when_no_explicit(self, monkeypatch) -> None:
        monkeypatch.setenv("ECOSYSTEM_MANIFEST", "/opt/eco/manifest.yaml")
        monkeypatch.delenv("ECOSYSTEM_MANIFEST", raising=False)  # no-op
        monkeypatch.setenv("ECOSYSTEM_MANIFEST", "/opt/eco/manifest.yaml")
        result = resolve_manifest_path()
        assert result == Path("/opt/eco/manifest.yaml")

    def test_env_var_returned_when_explicit_is_none(
        self, monkeypatch,
    ) -> None:
        monkeypatch.setenv("ECOSYSTEM_MANIFEST", "/etc/ecosystem.yaml")
        result = resolve_manifest_path(None)
        assert result == Path("/etc/ecosystem.yaml")

    def test_empty_env_var_falls_through_to_default(
        self, monkeypatch,
    ) -> None:
        """Empty string is falsy -> default branch is taken."""
        monkeypatch.setenv("ECOSYSTEM_MANIFEST", "")
        result = resolve_manifest_path()
        assert result == DEFAULT_RELATIVE_PATH


class TestResolveManifestPathDefault:
    """Branch 3: no explicit, no env var -> default ``settings/ecosystem.yaml``."""

    def test_default_when_no_explicit_and_no_env(self, monkeypatch) -> None:
        monkeypatch.delenv("ECOSYSTEM_MANIFEST", raising=False)
        result = resolve_manifest_path()
        assert result == DEFAULT_RELATIVE_PATH
        assert result == Path("settings/ecosystem.yaml")

    def test_default_is_a_path_instance(self, monkeypatch) -> None:
        monkeypatch.delenv("ECOSYSTEM_MANIFEST", raising=False)
        result = resolve_manifest_path()
        assert isinstance(result, Path)

    def test_default_constant_value(self) -> None:
        assert DEFAULT_RELATIVE_PATH == Path("settings/ecosystem.yaml")


class TestResolveManifestPathReturnType:
    """Sanity checks on return-type contract."""

    def test_always_returns_path(self, monkeypatch) -> None:
        monkeypatch.delenv("ECOSYSTEM_MANIFEST", raising=False)
        for arg in (None, Path("/a.yaml"), Path("b.yaml")):
            result = resolve_manifest_path(arg)
            assert isinstance(result, Path)

    def test_env_var_returns_path_even_for_relative(
        self, monkeypatch,
    ) -> None:
        monkeypatch.setenv("ECOSYSTEM_MANIFEST", "relative/env.yaml")
        result = resolve_manifest_path()
        assert isinstance(result, Path)
        assert result == Path("relative/env.yaml")
