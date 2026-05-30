from __future__ import annotations

import importlib


def _reload_auth_module():
    import session_buddy.realtime.auth as auth_module

    return importlib.reload(auth_module)


def test_get_authenticator_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SESSION_BUDDY_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("SESSION_BUDDY_JWT_SECRET", raising=False)
    monkeypatch.delenv("SESSION_BUDDY_TOKEN_EXPIRY", raising=False)

    auth = _reload_auth_module()

    assert auth.AUTH_ENABLED is False
    assert auth.get_authenticator() is None


def test_generate_and_verify_token_in_dev_mode(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_BUDDY_AUTH_ENABLED", "false")
    monkeypatch.setenv("SESSION_BUDDY_JWT_SECRET", "dev-secret-change-in-production")
    monkeypatch.setenv("SESSION_BUDDY_TOKEN_EXPIRY", "3600")

    auth = _reload_auth_module()

    token = auth.generate_token("user-123")
    payload = auth.verify_token(token)

    assert isinstance(token, str)
    assert payload is not None
    assert payload.get("user_id") == "user-123"
    assert payload.get("permissions") == ["session-buddy:read"]


def test_get_authenticator_enabled(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_BUDDY_AUTH_ENABLED", "true")
    monkeypatch.setenv("SESSION_BUDDY_JWT_SECRET", "session-buddy-test-secret")
    monkeypatch.setenv("SESSION_BUDDY_TOKEN_EXPIRY", "1800")

    auth = _reload_auth_module()

    authenticator = auth.get_authenticator()
    assert authenticator is not None
    token = authenticator.create_token({"user_id": "x"})
    assert auth.verify_token(token) is not None
