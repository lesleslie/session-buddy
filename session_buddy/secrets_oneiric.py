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

from oneiric.adapters.secrets.env import EnvSecretAdapter, EnvSecretSettings

_VALID_BACKENDS = frozenset(
    {"env", "aws", "file", "keyring", "infisical", "gcp"}
)


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


async def get_secret(
    key: str,
    *,
    settings: EnvSecretSettings | None = None,
    legacy_fallback: bool = True,
) -> str | None:
    """Look up a secret by key via the configured backend.

    For env backend: tries ``ONEIRIC_SECRET_<KEY>`` first, then legacy
    ``<KEY>`` (when ``legacy_fallback`` is True).
    For other backends: delegates to the adapter (which manages its own
    config from env / config files).
    """
    backend = _resolve_backend()
    if backend == "env":
        adapter = EnvSecretAdapter(settings or EnvSecretSettings())
        val = await adapter.get_secret(key)
        if val is not None:
            return val
        if legacy_fallback:
            return os.environ.get(key)
        return None
    if backend == "aws":
        from oneiric.adapters.secrets.aws import (
            AWSSecretManagerAdapter,
            AWSSecretManagerSettings,
        )

        return await AWSSecretManagerAdapter(
            AWSSecretManagerSettings()
        ).get_secret(key)
    if backend == "file":
        from oneiric.adapters.secrets.file import (
            FileSecretAdapter,
            FileSecretSettings,
        )

        return await FileSecretAdapter(
            FileSecretSettings()
        ).get_secret(key)
    if backend == "keyring":
        from oneiric.adapters.secrets.keyring import (
            KeyringSecretAdapter,
            KeyringSecretSettings,
        )

        return await KeyringSecretAdapter(
            KeyringSecretSettings()
        ).get_secret(key)
    if backend == "infisical":
        from oneiric.adapters.secrets.infisical import (
            InfisicalSecretAdapter,
            InfisicalSecretSettings,
        )

        return await InfisicalSecretAdapter(
            InfisicalSecretSettings()
        ).get_secret(key)
    if backend == "gcp":
        from oneiric.adapters.secrets.gcp import (
            GCPSecretManagerAdapter,
            GCPSecretManagerSettings,
        )

        return await GCPSecretManagerAdapter(
            GCPSecretManagerSettings()
        ).get_secret(key)
    msg = f"Unreachable: backend {backend!r}"
    raise RuntimeError(msg)
