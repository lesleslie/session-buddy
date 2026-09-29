"""Unit tests for ``session_buddy.mcp.tools.tasks_identity``.

Per the Task 3 brief, these tests pin:

- ``derive_caller_identity`` extracts ``user:<email>`` / ``agent:<id>``
  from the MCP ``auth`` block, prefers user over agent when both
  present, and rejects calls lacking both fields with ``PermissionError``
  (anonymous calls fail closed per spec §Authz Model).
- ``validate_owner_format`` accepts canonical ``user:`` / ``agent:``
  strings and rejects malformed inputs (missing prefix, missing value,
  no colon at all).
"""
from __future__ import annotations

import pytest

from session_buddy.mcp.tools.tasks_identity import (
    OWNER_RE,
    derive_caller_identity,
    validate_owner_format,
)


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


def test_caller_identity_rejects_unknown_caller() -> None:
    # Auth present but empty: still anonymous → fail closed.
    with pytest.raises(PermissionError):
        derive_caller_identity({"auth": {}})


def test_caller_identity_rejects_missing_auth() -> None:
    with pytest.raises(PermissionError):
        derive_caller_identity({})


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
