"""Unit tests for ``session_buddy.mcp.tools.tasks_identity``.

These tests pin:

- ``derive_caller_identity`` resolves in order: the ``principal``
  payload mcp_common writes, then ``user_email`` / ``agent_id``, then
  the local trust domain when the substrate's auth gate is off.
- The local trust domain is used only while the substrate's auth gate
  is off (or loopback is trusted). With the gate on and loopback
  untrusted, an anonymous call fails closed with ``PermissionError``
  (spec §Authz Model).
- A principal must hold the permission the operation requires; one that
  does not is refused rather than downgraded to another identity.
- ``validate_owner_format`` accepts canonical ``user:`` / ``agent:``
  strings and rejects malformed inputs (missing prefix, missing value,
  no colon at all).
"""

from __future__ import annotations

import pytest
from mcp_common.auth.exceptions import InsufficientPermissionError
from mcp_common.auth.permissions import Permission

from session_buddy.mcp.tools.tasks_identity import (
    OWNER_RE,
    _local_user,
    derive_caller_identity,
    validate_owner_format,
)


def _set_gate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool,
    loopback_trusted: bool,
) -> None:
    """Pin the substrate auth posture the identity resolver consults."""
    from session_buddy.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", enabled)
    monkeypatch.setattr(settings, "auth_loopback_trusted", loopback_trusted)


def test_caller_identity_extracts_user_from_mcp_context() -> None:
    ctx = {"auth": {"user_email": "les@example.com"}}
    assert derive_caller_identity(ctx) == "user:les@example.com"


def test_caller_identity_extracts_agent_from_mcp_context() -> None:
    ctx = {"auth": {"agent_id": "crackerjack-fixer-pool"}}
    assert derive_caller_identity(ctx) == "agent:crackerjack-fixer-pool"


def test_caller_identity_prefers_user_over_agent() -> None:
    # Both fields present — user wins (spec §Authz Model).
    ctx = {"auth": {"user_email": "user@x", "agent_id": "agent-1"}}
    assert derive_caller_identity(ctx) == "user:user@x"


# ---------------------------------------------------------------------------
# principal — the key mcp_common's BearerTokenMiddleware writes
# ---------------------------------------------------------------------------


def test_caller_identity_reads_the_principal_email_claim() -> None:
    ctx = {
        "auth": {
            "principal": {
                "issuer": "anthropic",
                "subject": "user_abc",
                "permissions": ["read"],
                "raw_claims": {"email": "les@wedgwoodwebworks.com"},
            },
        },
    }
    assert derive_caller_identity(ctx) == "user:les@wedgwoodwebworks.com"


def test_caller_identity_falls_back_to_the_principal_subject() -> None:
    # No email in the claims — the subject stands in as an agent identity.
    ctx = {
        "auth": {
            "principal": {
                "issuer": "anthropic",
                "subject": "svc-account-7",
                "permissions": ["read"],
                "raw_claims": {},
            },
        },
    }
    assert derive_caller_identity(ctx) == "agent:svc-account-7"


def test_caller_identity_prefers_the_principal_over_the_legacy_keys() -> None:
    ctx = {
        "auth": {
            "principal": {
                "issuer": "anthropic",
                "subject": "user_abc",
                "permissions": ["read"],
                "raw_claims": {"email": "principal@example.com"},
            },
            "user_email": "legacy@example.com",
            "agent_id": "legacy-agent",
        },
    }
    assert derive_caller_identity(ctx) == "user:principal@example.com"


def test_caller_identity_ignores_a_malformed_principal() -> None:
    # A principal without a subject is not an identity; the resolver
    # falls through to the legacy keys rather than trusting it.
    ctx = {"auth": {"principal": {"issuer": "x"}, "user_email": "legacy@example.com"}}
    assert derive_caller_identity(ctx) == "user:legacy@example.com"


# ---------------------------------------------------------------------------
# The local trust domain — the substrate's loopback-trusted posture
# ---------------------------------------------------------------------------


def test_caller_identity_uses_the_local_identity_when_the_gate_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_gate(monkeypatch, enabled=False, loopback_trusted=True)
    identity = derive_caller_identity({"auth": {}})
    assert identity == f"user:{_local_user()}"
    assert OWNER_RE.match(identity) is not None


def test_caller_identity_uses_the_local_identity_for_a_missing_auth_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_gate(monkeypatch, enabled=False, loopback_trusted=True)
    identity = derive_caller_identity({})
    assert identity == f"user:{_local_user()}"


def test_caller_identity_uses_the_local_identity_when_loopback_is_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Gate on, but the substrate trusts loopback callers — and this
    # server binds 127.0.0.1 only.
    _set_gate(monkeypatch, enabled=True, loopback_trusted=True)
    assert derive_caller_identity({"auth": {}}) == f"user:{_local_user()}"


def test_caller_identity_rejects_unknown_caller_when_loopback_is_untrusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Gate on and loopback untrusted — a shared-tenant deployment. No
    # identity is available, so the call fails closed.
    _set_gate(monkeypatch, enabled=True, loopback_trusted=False)
    with pytest.raises(PermissionError):
        derive_caller_identity({"auth": {}})


def test_caller_identity_rejects_missing_auth_when_loopback_is_untrusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_gate(monkeypatch, enabled=True, loopback_trusted=False)
    with pytest.raises(PermissionError):
        derive_caller_identity({})


def test_an_authenticated_caller_ignores_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The gate never rejects a caller that carries an identity.
    _set_gate(monkeypatch, enabled=True, loopback_trusted=False)
    ctx = {"auth": {"user_email": "les@example.com"}}
    assert derive_caller_identity(ctx) == "user:les@example.com"


def test_local_user_matches_the_owner_pattern() -> None:
    local = _local_user()
    assert local, "the local user name must not be empty"
    assert OWNER_RE.match(f"user:{local}") is not None


# ---------------------------------------------------------------------------
# Permission scope — an authenticated principal is not automatically
# authorized.
# ---------------------------------------------------------------------------


def _principal_ctx(*permissions: str) -> dict:
    return {
        "auth": {
            "principal": {
                "issuer": "anthropic",
                "subject": "user_abc",
                "permissions": list(permissions),
                "raw_claims": {"email": "les@wedgwoodwebworks.com"},
            },
        },
    }


def test_a_principal_holding_the_scope_is_accepted() -> None:
    ctx = _principal_ctx("read", "write")
    identity = derive_caller_identity(ctx, Permission.WRITE)
    assert identity == "user:les@wedgwoodwebworks.com"


def test_a_principal_missing_the_scope_is_refused() -> None:
    # Authenticated, but only a reader -- a write operation must not be
    # authorized.
    ctx = _principal_ctx("read")
    with pytest.raises(InsufficientPermissionError):
        derive_caller_identity(ctx, Permission.WRITE)


def test_a_refused_principal_is_not_downgraded_to_the_local_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The refusal must not fall through to the legacy keys or to the
    # local trust domain -- the local identity carries full local access,
    # so falling through would silently upgrade the caller.
    _set_gate(monkeypatch, enabled=False, loopback_trusted=True)
    ctx = _principal_ctx("read")
    with pytest.raises(InsufficientPermissionError):
        derive_caller_identity(ctx, Permission.WRITE)


def test_a_principal_with_no_permissions_is_refused() -> None:
    ctx = _principal_ctx()
    with pytest.raises(InsufficientPermissionError):
        derive_caller_identity(ctx, Permission.READ)


def test_a_read_principal_may_read() -> None:
    ctx = _principal_ctx("read")
    assert derive_caller_identity(ctx, Permission.READ) == (
        "user:les@wedgwoodwebworks.com"
    )


# ---------------------------------------------------------------------------
# validate_owner_format
# ---------------------------------------------------------------------------


def test_validate_owner_format_accepts_valid_user() -> None:
    validate_owner_format("user:les@wedgwoodwebworks.com")  # no exception


def test_validate_owner_format_accepts_valid_agent() -> None:
    validate_owner_format("agent:crackerjack-fixer-pool")  # no exception


def test_validate_owner_format_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        validate_owner_format("not-a-valid-owner")
    with pytest.raises(ValueError):
        validate_owner_format("user:")  # missing value
    with pytest.raises(ValueError):
        validate_owner_format(":les@example.com")  # missing prefix


def test_owner_re_compiled_from_t1_pattern() -> None:
    # Sanity: OWNER_RE matches the same strings as T1's OWNER_PATTERN
    # would. Proves we derived it from T1 (single source of truth).
    assert OWNER_RE.match("user:alice@example.com") is not None
    assert OWNER_RE.match("agent:crackerjack-fixer-pool") is not None
    assert OWNER_RE.match("not-a-valid-owner") is None
