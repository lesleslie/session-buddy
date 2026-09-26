"""Oneiric secrets adapter wrapper for Session-Buddy.

Per the Bodai credential-loading convention (oneiric.adapters.secrets), this
module provides a single async ``get_secret(key)`` entry point that delegates
to the configured backend. Backends:

- ``"env"`` (default): ``ONEIRIC_SECRET_<KEY>`` env vars, with legacy ``<KEY>``
  fallback.
- ``"aws"``: AWS Secrets Manager (via ``oneiric.adapters.secrets.aws``).
- ``"file"``: File-based .env-style secrets.
- ``"keyring"``: OS keyring (macOS Keychain, Linux libsecret, Windows
  Credential Store).
- ``"infisical"``: Infisical (Oneiric's HashiCorp-Vault replacement).
- ``"gcp"``: GCP Secret Manager.

Oneiric's ``EnvSecretAdapter`` uses prefix ``"ONEIRIC_SECRET_"`` by default.
For backward compat with existing ``BIFROST_API_KEY`` / ``MINIMAX_API_KEY``
env vars set before this wrapper existed, the env backend falls back to the
unprefixed key when ``ONEIRIC_SECRET_<KEY>`` is absent.

For aws/file/keyring/infisical/gcp, additional backend-specific config must
be set; see ``oneiric.adapters.secrets`` for settings.
"""

from __future__ import annotations

import os
from pathlib import Path

from oneiric.adapters.secrets.env import EnvSecretAdapter, EnvSecretSettings

_VALID_BACKENDS = frozenset({"env", "aws", "file", "keyring", "infisical", "gcp"})


def _resolve_backend() -> str:
    """Read backend selection from ``ONEIRIC_SECRETS_BACKEND`` (default env)."""
    backend = os.environ.get("ONEIRIC_SECRETS_BACKEND", "env").lower()
    if backend not in _VALID_BACKENDS:
        msg = (
            f"ONEIRIC_SECRETS_BACKEND={backend!r} not in "
            f"{sorted(_VALID_BACKENDS)}. See oneiric docs at "
            f"/Users/les/Projects/oneiric/oneiric/adapters/secrets/."
        )
        raise ValueError(msg)
    return backend


async def _get_via_env(
    key: str,
    *,
    settings: EnvSecretSettings | None,
    legacy_fallback: bool,
) -> str | None:
    """Look up ``key`` in process environment.

    Tries ``ONEIRIC_SECRET_<KEY>`` first via ``EnvSecretAdapter``; falls
    back to the bare ``<KEY>`` env var when ``legacy_fallback`` is True.
    """
    adapter = EnvSecretAdapter(settings or EnvSecretSettings())
    val = await adapter.get_secret(key)
    if val is not None:
        return val
    if legacy_fallback:
        return os.environ.get(key)
    return None


async def _get_via_aws(key: str) -> str | None:
    """AWS Secrets Manager. Requires ``AWS_REGION`` env var."""
    from oneiric.adapters.secrets.aws import (
        AWSSecretManagerAdapter,
        AWSSecretManagerSettings,
    )

    region = os.environ.get("AWS_REGION")
    if not region:
        msg = (
            "backend 'aws' requires the AWS_REGION env var; "
            "set it to the AWS region hosting your Secrets Manager."
        )
        raise RuntimeError(msg)
    adapter_settings = AWSSecretManagerSettings(region=region)
    return await AWSSecretManagerAdapter(adapter_settings).get_secret(key)


async def _get_via_file(key: str) -> str | None:
    """File-backed JSON/TOML store. Requires ``ONEIRIC_SECRETS_FILE_PATH`` env var."""
    from oneiric.adapters.secrets.file import (
        FileSecretAdapter,
        FileSecretSettings,
    )

    file_path = os.environ.get("ONEIRIC_SECRETS_FILE_PATH")
    if not file_path:
        msg = (
            "backend 'file' requires the ONEIRIC_SECRETS_FILE_PATH "
            "env var; set it to the absolute path of a JSON/TOML "
            "file containing key/value secrets."
        )
        raise RuntimeError(msg)
    adapter_settings = FileSecretSettings(path=Path(file_path))
    return await FileSecretAdapter(adapter_settings).get_secret(key)


async def _get_via_keyring(key: str) -> str | None:
    """OS keyring. ``KeyringSecretSettings`` ships with safe defaults."""
    from oneiric.adapters.secrets.keyring import (
        KeyringSecretAdapter,
        KeyringSecretSettings,
    )

    return await KeyringSecretAdapter(KeyringSecretSettings()).get_secret(key)


async def _get_via_infisical(key: str) -> str | None:
    """Infisical. Requires ``INFISICAL_TOKEN`` AND ``INFISICAL_ENVIRONMENT`` env vars."""
    from oneiric.adapters.secrets.infisical import (
        InfisicalSecretAdapter,
        InfisicalSecretSettings,
    )

    token = os.environ.get("INFISICAL_TOKEN")
    environment = os.environ.get("INFISICAL_ENVIRONMENT")
    if not token or not environment:
        msg = (
            "backend 'infisical' requires both INFISICAL_TOKEN "
            "and INFISICAL_ENVIRONMENT env vars; set them to your "
            "Infisical machine-identity token and environment slug "
            "(e.g., dev, prod)."
        )
        raise RuntimeError(msg)
    adapter_settings = InfisicalSecretSettings(
        token=token, environment=environment
    )
    return await InfisicalSecretAdapter(adapter_settings).get_secret(key)


async def _get_via_gcp(key: str) -> str | None:
    """GCP Secret Manager. Requires ``GOOGLE_CLOUD_PROJECT`` env var."""
    from oneiric.adapters.secrets.gcp import (
        GCPSecretManagerAdapter,
        GCPSecretManagerSettings,
    )

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        msg = (
            "backend 'gcp' requires the GOOGLE_CLOUD_PROJECT env "
            "var; set it to the GCP project ID hosting your "
            "secrets."
        )
        raise RuntimeError(msg)
    adapter_settings = GCPSecretManagerSettings(project_id=project_id)
    return await GCPSecretManagerAdapter(adapter_settings).get_secret(key)


async def get_secret(
    key: str,
    *,
    settings: EnvSecretSettings | None = None,
    legacy_fallback: bool = True,
) -> str | None:
    """Look up a secret by key via the configured backend.

    For env backend: tries ``ONEIRIC_SECRET_<KEY>`` first, then legacy
    ``<KEY>`` (when ``legacy_fallback`` is True).
    For other backends: delegates to the per-backend helper that
    constructs the adapter's ``Settings`` from canonical env vars.
    """
    backend = _resolve_backend()
    if backend == "env":
        return await _get_via_env(
            key, settings=settings, legacy_fallback=legacy_fallback
        )
    if backend == "aws":
        return await _get_via_aws(key)
    if backend == "file":
        return await _get_via_file(key)
    if backend == "keyring":
        return await _get_via_keyring(key)
    if backend == "infisical":
        return await _get_via_infisical(key)
    if backend == "gcp":
        return await _get_via_gcp(key)
    msg = f"Unreachable: backend {backend!r}"
    raise RuntimeError(msg)
