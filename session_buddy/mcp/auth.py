"""JWT-based authentication for Session-Buddy MCP tools.

This module provides JWT token validation for MCP tool authentication,
using the same HS256 algorithm as Mahavishnu for cross-project compatibility.

Security Architecture:
    - JWT tokens signed with HS256 algorithm
    - Secret loaded from SESSION_BUDDY_SECRET environment variable
    - Token validation middleware for protected MCP tools
    - Cross-project authentication compatible with Mahavishnu

Environment Variables:
    SESSION_BUDDY_SECRET: JWT secret key (generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))')

Token Generation:
    Clients can generate tokens using:
    >>> import jwt
    >>> token = jwt.encode({"user_id": "user123", "exp": datetime.now(tz=UTC) + timedelta(minutes=60)},
    ...                    SECRET, algorithm="HS256")

Example Usage:
    >>> from session_buddy.mcp.auth import validate_token, get_auth_error
    >>> payload = validate_token("eyJ...")
    >>> if payload is None:
    ...     print(get_auth_error())
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import jwt

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable


# ============================================================================
# Configuration
# ============================================================================


class AuthConfig:
    """Authentication configuration for JWT tokens."""

    # Minimum entropy requirements for JWT secrets
    MIN_SECRET_LENGTH = 32  # characters

    def __init__(self) -> None:
        """Initialize authentication configuration from environment."""
        self._secret = os.getenv("SESSION_BUDDY_SECRET")
        self._algorithm = "HS256"
        self._expire_minutes = 60

    @property
    def enabled(self) -> bool:
        """Check if authentication is enabled (secret is set)."""
        return self._secret is not None

    @property
    def secret(self) -> str:
        """Get JWT secret from environment.

        Raises:
            ValueError: If SESSION_BUDDY_SECRET is not set or too short
        """
        if not self._secret:
            msg = (
                "SESSION_BUDDY_SECRET environment variable must be set for authentication. "
                "Generate a secure secret with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
            raise ValueError(msg)

        # Validate minimum entropy (length check as proxy for entropy)
        if len(self._secret) < self.MIN_SECRET_LENGTH:
            msg = (
                f"JWT secret must be at least {self.MIN_SECRET_LENGTH} characters long. "
                f"Current length: {len(self._secret)} characters. "
                "Generate a secure secret with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
            raise ValueError(msg)

        return self._secret

    @property
    def algorithm(self) -> str:
        """Get JWT algorithm."""
        return self._algorithm

    @property
    def expire_minutes(self) -> int:
        """Get token expiration time in minutes."""
        return self._expire_minutes


# Global configuration instance
_auth_config: AuthConfig | None = None


def get_auth_config() -> AuthConfig:
    """Get global authentication configuration instance.

    Returns:
        AuthConfig: Singleton authentication configuration
    """
    global _auth_config
    if _auth_config is None:
        _auth_config = AuthConfig()
    return _auth_config


# ============================================================================
# JWT Token Management
# ============================================================================


class JWTManager:
    """JWT token management for authentication.

    This class provides token creation and validation using the same
    HS256 algorithm as Mahavishnu for cross-project compatibility.

    Attributes:
        config: Authentication configuration
        secret: JWT secret key
        algorithm: JWT algorithm (HS256)
        expire_minutes: Token expiration time in minutes
    """

    def __init__(self, config: AuthConfig | None = None) -> None:
        """Initialize JWT manager with authentication configuration.

        Args:
            config: Optional authentication configuration (uses global config if not provided)

        Raises:
            ValueError: If authentication is enabled but secret is not set or too short
        """
        self.config = config or get_auth_config()

        if self.config.enabled:
            self.secret = self.config.secret
            self.algorithm = self.config.algorithm
            self.expire_minutes = self.config.expire_minutes
            logger.info("JWT authentication initialized with HS256 algorithm")
        else:
            self.secret = None
            self.algorithm = None
            self.expire_minutes = None
            logger.warning("JWT authentication disabled (SESSION_BUDDY_SECRET not set)")

    def create_token(
        self,
        user_id: str,
        additional_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create a JWT token for a user.

        Args:
            user_id: User identifier
            additional_claims: Optional additional claims to include in token

        Returns:
            JWT token string

        Raises:
            ValueError: If authentication is disabled
        """
        if not self.config.enabled:
            msg = "Cannot create token: authentication is disabled (SESSION_BUDDY_SECRET not set)"
            raise ValueError(msg)

        payload = {
            "user_id": user_id,
            "exp": datetime.now(tz=UTC) + timedelta(minutes=self.expire_minutes),  # type: ignore[operator]
            "iat": datetime.now(tz=UTC),
            "type": "access",
            "iss": "session-buddy",  # Issuer
        }

        if additional_claims:
            payload.update(additional_claims)

        token = jwt.encode(payload, self.secret, algorithm=self.algorithm)  # type: ignore[arg-type]
        logger.debug(f"Created token for user {user_id}")
        return token

    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify a JWT token and return the payload.

        Args:
            token: JWT token string

        Returns:
            Token payload dictionary

        Raises:
            ValueError: If token is expired or invalid
        """
        if not self.config.enabled:
            msg = "Cannot verify token: authentication is disabled (SESSION_BUDDY_SECRET not set)"
            raise ValueError(msg)

        if self.secret is None:
            msg = "Cannot verify token: secret not configured"
            raise ValueError(msg)

        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],  # type: ignore[list-item]
            )
            logger.debug(f"Verified token for user {payload.get('user_id', 'unknown')}")
            return payload
        except jwt.ExpiredSignatureError as e:
            logger.warning("Token verification failed: token has expired")
            msg = "Token has expired"
            raise ValueError(msg) from e
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token verification failed: invalid token ({e})")
            msg = "Invalid token"
            raise ValueError(msg) from e

    def refresh_token(self, token: str) -> str:
        """Refresh an existing token.

        Args:
            token: Existing JWT token

        Returns:
            New JWT token with updated expiration

        Raises:
            ValueError: If token is invalid or authentication is disabled
        """
        if not self.config.enabled:
            msg = "Cannot refresh token: authentication is disabled (SESSION_BUDDY_SECRET not set)"
            raise ValueError(msg)

        payload = self.verify_token(token)

        # Remove exp to create fresh expiration
        if "exp" in payload:
            del payload["exp"]

        payload["exp"] = datetime.now(tz=UTC) + timedelta(minutes=self.expire_minutes)  # type: ignore[operator]
        payload["refreshed_at"] = datetime.now(tz=UTC).isoformat()

        new_token = jwt.encode(payload, self.secret, algorithm=self.algorithm)  # type: ignore[arg-type]
        logger.debug(f"Refreshed token for user {payload.get('user_id', 'unknown')}")
        return new_token


# ============================================================================
# Token Validation Middleware
# ============================================================================


# Global error storage for last authentication failure
_last_auth_error: str | None = None


def get_auth_error() -> str | None:
    """Get the last authentication error message.

    Returns:
        Last authentication error or None
    """
    global _last_auth_error
    return _last_auth_error


def _set_auth_error(error: str) -> None:
    """Set the last authentication error message.

    Args:
        error: Error message to store
    """
    global _last_auth_error
    _last_auth_error = error


def validate_token(token: str) -> dict[str, Any] | None:
    """Validate JWT token and return payload.

    This is a convenience function that creates a JWT manager
    and validates the token. Returns None if validation fails.

    Args:
        token: JWT token string

    Returns:
        Token payload dictionary or None if validation fails

    Example:
        >>> payload = validate_token("eyJ...")
        >>> if payload:
        ...     user_id = payload.get("user_id")
        ...     print(f"Authenticated as {user_id}")
        >>> else:
        ...     print(f"Authentication failed: {get_auth_error()}")
    """
    global _last_auth_error
    _last_auth_error = None

    # Check if authentication is enabled
    config = get_auth_config()
    if not config.enabled:
        logger.debug("Authentication disabled - token validation skipped")
        return {"user_id": "anonymous", "auth": "disabled"}

    try:
        manager = JWTManager(config)
        payload = manager.verify_token(token)
        return payload
    except ValueError as e:
        _last_auth_error = str(e)
        return None


def require_auth(
    optional: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to require JWT authentication for MCP tools.

    This decorator validates the JWT token from the 'token' parameter
    before executing the wrapped function. If authentication is disabled
    (SESSION_BUDDY_SECRET not set), the decorator passes without validation.

    Args:
        optional: If True, allows anonymous access when auth is disabled
                  If False (default), requires auth when enabled

    Returns:
        Decorator function

    Example:
        >>> @require_auth()
        ... async def protected_tool(user_id: str, token: str) -> str:
        ...     # token is automatically validated
        ...     return f"Hello {user_id}"

        >>> @require_auth(optional=True)
        ... async def optional_auth_tool(token: str | None = None) -> str:
        ...     # Works with or without authentication
        ...     return "Success"
    """
    from functools import wraps

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract token from kwargs
            token = kwargs.get("token")

            # Check if authentication is enabled
            config = get_auth_config()
            if not config.enabled:
                # Authentication disabled - proceed without validation
                logger.debug(f"Authentication disabled for {func.__name__}")
                return await func(*args, **kwargs)

            # Authentication enabled - validate token
            if not token:
                _set_auth_error("Token required but not provided")
                return "❌ Authentication failed: Token required (SESSION_BUDDY_SECRET is set)"

            payload = validate_token(token)
            if payload is None:
                error = get_auth_error()
                logger.warning(f"Authentication failed for {func.__name__}: {error}")
                return f"❌ Authentication failed: {error}"

            # Add user_id from token to kwargs
            kwargs["user_id"] = payload.get("user_id", "unknown")
            logger.info(f"Authenticated {func.__name__} for user {kwargs['user_id']}")

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract token from kwargs
            token = kwargs.get("token")

            # Check if authentication is enabled
            config = get_auth_config()
            if not config.enabled:
                # Authentication disabled - proceed without validation
                logger.debug(f"Authentication disabled for {func.__name__}")
                return func(*args, **kwargs)

            # Authentication enabled - validate token
            if not token:
                _set_auth_error("Token required but not provided")
                return "❌ Authentication failed: Token required (SESSION_BUDDY_SECRET is set)"

            payload = validate_token(token)
            if payload is None:
                error = get_auth_error()
                logger.warning(f"Authentication failed for {func.__name__}: {error}")
                return f"❌ Authentication failed: {error}"

            # Add user_id from token to kwargs
            kwargs["user_id"] = payload.get("user_id", "unknown")
            logger.info(f"Authenticated {func.__name__} for user {kwargs['user_id']}")

            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# Cross-Project Authentication
# ============================================================================


class CrossProjectAuth:
    """Shared authentication for cross-project communication.

    This class provides HMAC-SHA256 signatures for cross-project message
    authentication, compatible with Mahavishnu's CrossProjectAuth.
    """

    def __init__(self, shared_secret: str) -> None:
        """Initialize cross-project authentication.

        Args:
            shared_secret: Shared secret for HMAC signing
        """
        self.shared_secret = shared_secret

    def sign_message(self, message: dict[str, Any]) -> str:
        """Generate HMAC-SHA256 signature for cross-project messages.

        Args:
            message: Message dictionary to sign

        Returns:
            Hexadecimal signature string
        """
        import hashlib
        import hmac
        import json

        message_str = json.dumps(message, sort_keys=True)
        hmac_obj = hmac.new(
            self.shared_secret.encode(),
            message_str.encode(),
            hashlib.sha256,
        )
        return hmac_obj.hexdigest()

    def verify_message(self, message: dict[str, Any], signature: str) -> bool:
        """Verify message signature.

        Args:
            message: Message dictionary
            signature: Signature to verify

        Returns:
            True if signature is valid, False otherwise
        """
        import hmac

        expected = self.sign_message(message)
        return hmac.compare_digest(expected, signature)


# ============================================================================
# Utility Functions
# ============================================================================


def is_authentication_enabled() -> bool:
    """Check if JWT authentication is enabled.

    Returns:
        True if SESSION_BUDDY_SECRET is set, False otherwise
    """
    config = get_auth_config()
    return config.enabled


def generate_test_token(user_id: str = "test_user") -> str:
    """Generate a test token for development/testing.

    WARNING: Only use this for development/testing. Never use in production.

    Args:
        user_id: User ID for the test token

    Returns:
        JWT token string

    Raises:
        ValueError: If authentication is not enabled
    """
    config = get_auth_config()
    if not config.enabled:
        msg = "Cannot generate test token: authentication is disabled (SESSION_BUDDY_SECRET not set)"
        raise ValueError(msg)

    manager = JWTManager(config)
    return manager.create_token(user_id)


__all__ = [
    # Configuration
    "AuthConfig",
    "get_auth_config",
    # JWT Management
    "JWTManager",
    "validate_token",
    "get_auth_error",
    "require_auth",
    # Cross-Project
    "CrossProjectAuth",
    # Utilities
    "is_authentication_enabled",
    "generate_test_token",
]
