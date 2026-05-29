from __future__ import annotations

import asyncio

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


def test_validate_token_logs_warning_for_invalid_token(monkeypatch, caplog):
    monkeypatch.setenv("SESSION_BUDDY_SECRET", SECRET)

    from mcp_common.auth.exceptions import AuthError

    from session_buddy.mcp.auth import validate_token

    def raise_auth_error(*args, **kwargs):
        raise AuthError("invalid token")

    monkeypatch.setattr(
        "session_buddy.mcp.auth._verify_token",
        raise_auth_error,
    )

    caplog.set_level("WARNING")
    result = validate_token("bad-token")

    assert result is None
    assert "token validation failed" in caplog.text


def test_generate_test_token_and_validate(monkeypatch):
    monkeypatch.setenv("SESSION_BUDDY_SECRET", SECRET)

    from session_buddy.mcp.auth import generate_test_token, validate_token

    token = generate_test_token("test_user")
    payload = validate_token(token)
    assert payload is not None
    assert payload.get("auth") != "disabled"
    assert "iss" in payload or "sub" in payload


def test_auth_config_properties_reflect_core_config(monkeypatch):
    monkeypatch.setenv("SESSION_BUDDY_SECRET", SECRET)

    from session_buddy.mcp.auth import AuthConfig, get_auth_config

    config = get_auth_config()

    assert isinstance(config, AuthConfig)
    assert config.enabled is True
    assert config.secret == SECRET


def test_require_auth_allows_calls_when_disabled(monkeypatch):
    monkeypatch.delenv("SESSION_BUDDY_SECRET", raising=False)
    monkeypatch.delenv("BODAI_SHARED_SECRET", raising=False)

    from session_buddy.mcp.auth import require_auth

    calls: list[tuple[str, str]] = []

    @require_auth()
    async def handler(*, user_id: str = "anonymous") -> str:
        calls.append(("user", user_id))
        return user_id

    result = asyncio.run(handler())

    assert result == "anonymous"
    assert calls == [("user", "anonymous")]


def test_require_auth_rejects_missing_and_invalid_tokens(monkeypatch):
    monkeypatch.setenv("SESSION_BUDDY_SECRET", SECRET)

    from session_buddy.mcp.auth import require_auth

    @require_auth()
    async def handler(*, user_id: str) -> str:
        return user_id

    missing = asyncio.run(handler())
    invalid = asyncio.run(handler(token="not-a-real-token"))

    assert missing == "❌ Authentication failed: Token required (SESSION_BUDDY_SECRET is set)"
    assert invalid == "❌ Authentication failed: invalid or expired token"


def test_require_auth_passes_user_id_from_valid_token(monkeypatch):
    monkeypatch.setenv("SESSION_BUDDY_SECRET", SECRET)

    from session_buddy.mcp.auth import generate_test_token, require_auth

    seen_user_ids: list[str] = []

    @require_auth()
    async def handler(*, user_id: str) -> str:
        seen_user_ids.append(user_id)
        return user_id

    token = generate_test_token("alpha")
    result = asyncio.run(handler(token=token))

    assert result == "unknown"
    assert seen_user_ids == ["unknown"]


def test_cross_project_auth_sign_and_verify() -> None:
    from session_buddy.mcp.auth import CrossProjectAuth

    auth = CrossProjectAuth("shared-secret")
    message = {"b": 2, "a": 1}
    signature = auth.sign_message(message)

    assert auth.verify_message(message, signature) is True
    assert auth.verify_message(message, "bad-signature") is False
