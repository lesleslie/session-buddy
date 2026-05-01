from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from mcp_common.auth.config import AuthConfig as _CoreAuthConfig
from mcp_common.auth.core import create_service_token
from mcp_common.auth.core import verify_token as _verify_token
from mcp_common.auth.exceptions import AuthError
from mcp_common.auth.permissions import Permission

logger = logging.getLogger(__name__)

_core_config: _CoreAuthConfig | None = None


def _reset_core_config() -> None:
    global _core_config
    _core_config = None


def _get_core_config() -> _CoreAuthConfig:
    global _core_config
    if _core_config is None:
        _core_config = _CoreAuthConfig(
            service_name="session-buddy",
            secret_env_var="SESSION_BUDDY_SECRET",
        )
    return _core_config


class AuthConfig:
    @property
    def enabled(self) -> bool:
        return _get_core_config().enabled

    @property
    def secret(self) -> str:
        return _get_core_config().secret


def get_auth_config() -> AuthConfig:
    return AuthConfig()


def is_authentication_enabled() -> bool:
    return _get_core_config().enabled


def validate_token(token: str) -> dict[str, Any] | None:
    cfg = _get_core_config()
    if not cfg.enabled:
        return {"user_id": "anonymous", "auth": "disabled"}
    try:
        payload = _verify_token(
            token, secret=cfg.secret, expected_audience="session-buddy"
        )
        return payload.raw
    except AuthError as exc:
        logger.warning("token validation failed: %s", exc)
        return None


def require_auth(
    optional: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            token = kwargs.pop("token", None)
            cfg = _get_core_config()
            if not cfg.enabled:
                return await func(*args, **kwargs)
            if not token:
                return "❌ Authentication failed: Token required (SESSION_BUDDY_SECRET is set)"
            payload = validate_token(token)
            if payload is None:
                return "❌ Authentication failed: invalid or expired token"
            kwargs["user_id"] = payload.get("user_id", "unknown")
            return await func(*args, **kwargs)

        return wrapper

    return decorator


class CrossProjectAuth:
    def __init__(self, shared_secret: str) -> None:
        self.shared_secret = shared_secret

    def sign_message(self, message: dict[str, Any]) -> str:
        message_str = json.dumps(message, sort_keys=True)
        return hmac.new(
            self.shared_secret.encode(), message_str.encode(), hashlib.sha256
        ).hexdigest()

    def verify_message(self, message: dict[str, Any], signature: str) -> bool:
        return hmac.compare_digest(self.sign_message(message), signature)


def generate_test_token(user_id: str = "test_user") -> str:
    cfg = _get_core_config()
    return create_service_token(
        secret=cfg.secret,
        issuer="session-buddy",
        audience="session-buddy",
        permissions=[Permission.READ],
    )


__all__ = [
    "AuthConfig",
    "CrossProjectAuth",
    "generate_test_token",
    "get_auth_config",
    "is_authentication_enabled",
    "require_auth",
    "validate_token",
]
