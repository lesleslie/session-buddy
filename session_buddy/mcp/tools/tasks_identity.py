"""Server-side identity derivation for task-system tools.

Per the spec (v1.1 §Authz Model), owner/created_by/completed_by/actor are
derived from the authenticated MCP caller identity. Caller-supplied values
are silently overwritten.

The MCP context shape (subject to change; verify against current
mcp_common client) is::

    ctx = {
        "auth": {
            "principal": {          # mcp_common's BearerTokenMiddleware
                "issuer": "anthropic",
                "subject": "user_abc",
                "permissions": ["read"],
                "expires_at": "...",
                "raw_claims": {"email": "les@wedgwoodwebworks.com"},
            },
            "user_email": "les@wedgwoodwebworks.com",  # OR
            "agent_id": "crackerjack-fixer-pool",
        },
        ...
    }

Resolution order
----------------

1. **``principal``** -- the key ``mcp_common.auth.middleware.BearerTokenMiddleware``
   writes. This is the authenticated path, and the one the rest of the
   fleet reads.
2. **``user_email`` / ``agent_id``** -- the task system's original
   contract, kept so a middleware that populates those keys directly
   still works.
3. **The local trust domain** -- when neither is present *and* the
   substrate's auth gate is off.

The third path is the substrate's documented deployment posture: the
substrate auth gate is off by default and the loopback-trusted path is
its escape hatch ("Off by default -- the loopback-trusted path is the
Phase E1 escape hatch", ``oneiric.core.substrate_settings``). On a
single-host deployment every MCP caller reaches the server over
loopback, so they all share one identity. That sharing is load-bearing,
not incidental: the cross-repo handoff flow (``tasks_handoff_to_workflow``
in mahavishnu) calls this server's ``tasks_get`` / ``tasks_update``, and
those calls are visibility-filtered by owner -- per-caller identities
would make the handoff unable to see the task it is handing off.

When the substrate auth gate is *on* and loopback is not trusted, no
identity is available and the call fails closed.
"""

from __future__ import annotations

import os
import pwd
import re

from session_buddy.mcp.tools.tasks_models import OWNER_PATTERN

# Re-exported here so callers can pre-compile and avoid the cost of
# re.match() recompiling the pattern on every validate_owner_format call.
OWNER_RE = re.compile(OWNER_PATTERN)

#: The characters ``OWNER_PATTERN`` accepts in the ``user:`` local part.
_LOCAL_USER_ALLOWED = re.compile(r"[^A-Za-z0-9._@-]")


def _local_user() -> str:
    """Return the OS account name of the user running the server.

    ``pwd.getpwuid`` is used rather than ``getpass.getuser`` because it
    reads the passwd database directly: a launchd-spawned process has a
    minimal environment, and the ``USER``/``LOGNAME`` variables it does
    inherit are not guaranteed to be present.
    """
    try:
        name = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        # No passwd entry for this uid (synthetic uid in a container).
        name = ""
    except OSError:
        # The passwd database itself is unreadable.
        name = ""
    name = _LOCAL_USER_ALLOWED.sub("", name)
    return name or "local"


def _identity_from_principal(principal: object) -> str | None:
    """Derive an identity from an mcp_common ``Principal`` payload.

    The payload is the dict form written by
    ``mcp_common.auth.principal.Principal.to_dict``: ``issuer``,
    ``subject``, ``permissions``, ``expires_at``, ``raw_claims``.

    An email in the claims wins, because ``user:<email>`` is the identity
    form the spec names first and it is what a human recognises. With no
    email the subject stands in as an agent identity.
    """
    if not isinstance(principal, dict):
        return None
    subject = principal.get("subject")
    if not subject:
        return None
    claims = principal.get("raw_claims")
    claims = claims if isinstance(claims, dict) else {}
    email = claims.get("email") or claims.get("preferred_username")
    if email:
        return f"user:{email}"
    return f"agent:{subject}"


def _local_trust_domain_allowed() -> bool:
    """Return whether an unauthenticated caller may use the local identity.

    Mirrors the substrate's auth posture:

    * Gate off (``auth_enabled`` false) -- the substrate does not
      authenticate at all, so refusing would make the tools unusable.
    * Gate on but loopback trusted -- loopback callers are trusted by
      policy, and this server binds ``127.0.0.1`` only.
    * Gate on and loopback untrusted -- a shared-tenant deployment. No
      identity is available, so the call fails closed.
    """
    try:
        from session_buddy.settings import get_settings

        settings = get_settings()
    except Exception:  # noqa: BLE001 - settings unavailable: fail closed
        return False
    if not settings.auth_enabled:
        return True
    return bool(settings.auth_loopback_trusted)


def derive_caller_identity(mcp_context: dict) -> str:
    """Return the caller identity string for this MCP request.

    Returns ``user:<email>`` if a user is authenticated, else
    ``agent:<id>`` if an agent is authenticated, else the local
    trust-domain identity when the substrate's auth gate is off.

    Raises ``PermissionError`` when no identity can be derived -- the
    spec requires anonymous calls to fail closed, and the one exception
    is the loopback-trusted deployment the substrate describes.
    """
    auth = mcp_context.get("auth") or {}

    principal_identity = _identity_from_principal(auth.get("principal"))
    if principal_identity is not None:
        return principal_identity

    user = auth.get("user_email")
    if user:
        return f"user:{user}"
    agent = auth.get("agent_id")
    if agent:
        return f"agent:{agent}"

    if _local_trust_domain_allowed():
        return f"user:{_local_user()}"

    raise PermissionError(
        "MCP caller has no authenticated identity (no principal, no "
        "user_email, no agent_id) and the substrate auth gate does not "
        "trust loopback callers"
    )


def validate_owner_format(owner: str) -> None:
    """Validate that ``owner`` matches the canonical OWNER_PATTERN.

    Raises ``ValueError`` on mismatch. Used for caller-supplied owner
    values; server-set owners bypass this because they're already
    authenticated.
    """
    if not isinstance(owner, str) or not OWNER_RE.match(owner):
        raise ValueError(
            f"owner {owner!r} does not match the canonical format "
            f"(user:<email> | agent:<id>)"
        )
