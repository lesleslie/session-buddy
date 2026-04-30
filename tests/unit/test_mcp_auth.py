from __future__ import annotations

import pytest

SECRET = "session-buddy-test-secret-at-least-32-chars"


@pytest.fixture(autouse=True)
def _reset_auth():
    try:
        from session_buddy.mcp.auth import _reset_core_config
        _reset_core_config()
    except (ImportError, AttributeError):
        pass
    yield
    try:
        from session_buddy.mcp.auth import _reset_core_config
        _reset_core_config()
    except (ImportError, AttributeError):
        pass


def test_auth_disabled_when_no_secret(monkeypatch):
    monkeypatch.delenv("SESSION_BUDDY_SECRET", raising=False)
    monkeypatch.delenv("BODAI_SHARED_SECRET", raising=False)

    from session_buddy.mcp.auth import is_authentication_enabled

    assert is_authentication_enabled() is False


def test_validate_token_returns_anonymous_when_disabled(monkeypatch):
    monkeypatch.delenv("SESSION_BUDDY_SECRET", raising=False)
    monkeypatch.delenv("BODAI_SHARED_SECRET", raising=False)

    from session_buddy.mcp.auth import validate_token

    result = validate_token("any-token")
    assert result is not None
    assert result.get("auth") == "disabled"


def test_generate_test_token_and_validate(monkeypatch):
    monkeypatch.setenv("SESSION_BUDDY_SECRET", SECRET)

    from session_buddy.mcp.auth import generate_test_token, validate_token

    token = generate_test_token("test_user")
    payload = validate_token(token)
    assert payload is not None
    assert payload.get("auth") != "disabled"
    assert "iss" in payload or "sub" in payload
