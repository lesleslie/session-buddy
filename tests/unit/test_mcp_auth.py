"""Unit tests for Session-Buddy MCP authentication module.

Tests JWT token creation, validation, and error handling.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest


# Import auth module directly to avoid import chain issues
import sys
from pathlib import Path
from importlib import util

# Load auth module directly without triggering __init__.py
auth_spec = util.spec_from_file_location(
    "auth_module",
    Path(__file__).parent.parent.parent / "session_buddy" / "mcp" / "auth.py"
)
auth = util.module_from_spec(auth_spec)
auth_spec.loader.exec_module(auth)


class TestAuthConfig:
    """Test AuthConfig class."""

    def test_auth_config_defaults(self):
        """Test AuthConfig default values."""
        config = auth.AuthConfig()

        assert config.algorithm == "HS256"
        assert config.expire_minutes == 60
        assert config.enabled is False  # No secret set

    def test_auth_config_enabled(self):
        """Test AuthConfig with secret."""
        with patch.dict("os.environ", {"SESSION_BUDDY_SECRET": "x" * 32}):
            # Force reload of config
            auth._auth_config = None
            config = auth.get_auth_config()

            assert config.enabled is True
            assert config.secret == "x" * 32

    def test_auth_config_secret_too_short(self):
        """Test AuthConfig rejects short secrets."""
        with patch.dict("os.environ", {"SESSION_BUDDY_SECRET": "short"}):
            # Force reload of config
            auth._auth_config = None
            config = auth.get_auth_config()

            with pytest.raises(ValueError, match="must be at least 32 characters"):
                _ = config.secret

    def test_auth_config_no_secret(self):
        """Test AuthConfig error when secret not set."""
        # Force reload of config
        auth._auth_config = None
        config = auth.get_auth_config()

        with pytest.raises(ValueError, match="SESSION_BUDDY_SECRET environment variable"):
            _ = config.secret


class TestJWTManager:
    """Test JWTManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        # Set a test secret
        self.test_secret = "test-secret-key-for-demo-purposes-min-32-chars"
        patcher = patch.dict("os.environ", {"SESSION_BUDDY_SECRET": self.test_secret})
        patcher.start()
        self.addCleanup(patcher.stop)

        # Force reload of config
        auth._auth_config = None

    def test_jwt_manager_init(self):
        """Test JWTManager initialization."""
        manager = auth.JWTManager()

        assert manager.secret == self.test_secret
        assert manager.algorithm == "HS256"
        assert manager.expire_minutes == 60

    def test_create_token(self):
        """Test token creation."""
        manager = auth.JWTManager()
        token = manager.create_token("test_user")

        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify structure
        parts = token.split(".")
        assert len(parts) == 3  # header.payload.signature

    def test_verify_token(self):
        """Test token verification."""
        manager = auth.JWTManager()
        token = manager.create_token("test_user")
        payload = manager.verify_token(token)

        assert payload["user_id"] == "test_user"
        assert payload["type"] == "access"
        assert payload["iss"] == "session-buddy"
        assert "exp" in payload
        assert "iat" in payload

    def test_verify_expired_token(self):
        """Test expired token rejection."""
        import jwt

        manager = auth.JWTManager()

        # Create expired token
        payload = {
            "user_id": "test_user",
            "exp": datetime.now(tz=UTC) - timedelta(minutes=1),
            "iat": datetime.now(tz=UTC) - timedelta(minutes=61),
            "type": "access",
        }
        expired_token = jwt.encode(payload, self.test_secret, algorithm="HS256")

        with pytest.raises(ValueError, match="Token has expired"):
            manager.verify_token(expired_token)

    def test_verify_invalid_token(self):
        """Test invalid token rejection."""
        manager = auth.JWTManager()

        with pytest.raises(ValueError, match="Invalid token"):
            manager.verify_token("invalid.token.here")

    def test_refresh_token(self):
        """Test token refresh."""
        import time

        manager = auth.JWTManager()
        original_token = manager.create_token("test_user")

        # Wait a moment to ensure timestamp changes
        time.sleep(0.1)

        refreshed_token = manager.refresh_token(original_token)

        # Tokens should be different
        assert original_token != refreshed_token

        # Both should be valid
        original_payload = manager.verify_token(original_token)
        refreshed_payload = manager.verify_token(refreshed_token)

        assert original_payload["user_id"] == refreshed_payload["user_id"]
        assert "refreshed_at" in refreshed_payload

    def test_create_token_disabled(self):
        """Test token creation fails when auth disabled."""
        # Remove secret
        patcher = patch.dict("os.environ", {}, clear=True)
        patcher.start()
        auth._auth_config = None

        manager = auth.JWTManager()

        with pytest.raises(ValueError, match="authentication is disabled"):
            manager.create_token("test_user")

        patcher.stop()

    def test_verify_token_disabled(self):
        """Test token verification fails when auth disabled."""
        # Remove secret
        patcher = patch.dict("os.environ", {}, clear=True)
        patcher.start()
        auth._auth_config = None

        manager = auth.JWTManager()

        with pytest.raises(ValueError, match="authentication is disabled"):
            manager.verify_token("any.token.here")

        patcher.stop()


class TestValidateToken:
    """Test validate_token function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_secret = "test-secret-key-for-demo-purposes-min-32-chars"
        patcher = patch.dict("os.environ", {"SESSION_BUDDY_SECRET": self.test_secret})
        patcher.start()
        self.addCleanup(patcher.stop)

        # Force reload of config
        auth._auth_config = None

    def test_validate_token_success(self):
        """Test successful token validation."""
        manager = auth.JWTManager()
        token = manager.create_token("test_user")

        payload = auth.validate_token(token)

        assert payload is not None
        assert payload["user_id"] == "test_user"

    def test_validate_token_invalid(self):
        """Test invalid token returns None."""
        payload = auth.validate_token("invalid.token")

        assert payload is None
        assert auth.get_auth_error() is not None

    def test_validate_token_disabled(self):
        """Test validation when auth disabled."""
        # Remove secret
        patcher = patch.dict("os.environ", {}, clear=True)
        patcher.start()
        auth._auth_config = None

        # Should return anonymous payload when disabled
        payload = auth.validate_token("any.token")

        assert payload is not None
        assert payload["user_id"] == "anonymous"
        assert payload["auth"] == "disabled"

        patcher.stop()


class TestRequireAuth:
    """Test require_auth decorator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_secret = "test-secret-key-for-demo-purposes-min-32-chars"

    @pytest.mark.asyncio
    async def test_require_auth_disabled(self):
        """Test decorator passes when auth disabled."""
        # Remove secret
        patcher = patch.dict("os.environ", {}, clear=True)
        patcher.start()
        auth._auth_config = None

        @auth.require_auth()
        async def test_tool(user_id: str = "default") -> str:
            return f"Hello {user_id}"

        result = await test_tool()
        assert result == "Hello default"

        patcher.stop()

    @pytest.mark.asyncio
    async def test_require_auth_valid_token(self):
        """Test decorator passes with valid token."""
        patcher = patch.dict("os.environ", {"SESSION_BUDDY_SECRET": self.test_secret})
        patcher.start()
        auth._auth_config = None

        # Create valid token
        manager = auth.JWTManager()
        token = manager.create_token("test_user")

        @auth.require_auth()
        async def test_tool(user_id: str = "default") -> str:
            return f"Hello {user_id}"

        result = await test_tool(token=token)
        assert result == "Hello test_user"

        patcher.stop()

    @pytest.mark.asyncio
    async def test_require_auth_missing_token(self):
        """Test decorator rejects missing token."""
        patcher = patch.dict("os.environ", {"SESSION_BUDDY_SECRET": self.test_secret})
        patcher.start()
        auth._auth_config = None

        @auth.require_auth()
        async def test_tool(user_id: str = "default") -> str:
            return f"Hello {user_id}"

        result = await test_tool()
        assert "❌ Authentication failed" in result

        patcher.stop()

    @pytest.mark.asyncio
    async def test_require_auth_invalid_token(self):
        """Test decorator rejects invalid token."""
        patcher = patch.dict("os.environ", {"SESSION_BUDDY_SECRET": self.test_secret})
        patcher.start()
        auth._auth_config = None

        @auth.require_auth()
        async def test_tool(user_id: str = "default") -> str:
            return f"Hello {user_id}"

        result = await test_tool(token="invalid.token")
        assert "❌ Authentication failed" in result

        patcher.stop()


class TestUtilityFunctions:
    """Test utility functions."""

    def test_is_authentication_enabled_true(self):
        """Test is_authentication_enabled returns True when secret set."""
        patcher = patch.dict("os.environ", {"SESSION_BUDDY_SECRET": "x" * 32})
        patcher.start()
        auth._auth_config = None

        assert auth.is_authentication_enabled() is True

        patcher.stop()

    def test_is_authentication_enabled_false(self):
        """Test is_authentication_enabled returns False when no secret."""
        patcher = patch.dict("os.environ", {}, clear=True)
        patcher.start()
        auth._auth_config = None

        assert auth.is_authentication_enabled() is False

        patcher.stop()

    def test_generate_test_token(self):
        """Test generate_test_token utility."""
        patcher = patch.dict("os.environ", {"SESSION_BUDDY_SECRET": "x" * 32})
        patcher.start()
        auth._auth_config = None

        token = auth.generate_test_token("test_user")

        assert isinstance(token, str)
        assert len(token) > 0

        # Verify it's a valid token
        manager = auth.JWTManager()
        payload = manager.verify_token(token)
        assert payload["user_id"] == "test_user"

        patcher.stop()

    def test_generate_test_token_disabled(self):
        """Test generate_test_token fails when auth disabled."""
        patcher = patch.dict("os.environ", {}, clear=True)
        patcher.start()
        auth._auth_config = None

        with pytest.raises(ValueError, match="authentication is disabled"):
            auth.generate_test_token("test_user")

        patcher.stop()


class TestCrossProjectAuth:
    """Test CrossProjectAuth class."""

    def test_sign_message(self):
        """Test message signing."""
        shared_secret = "shared-secret-key"
        cross_auth = auth.CrossProjectAuth(shared_secret)

        message = {"action": "test", "timestamp": 123456}
        signature = cross_auth.sign_message(message)

        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex length

    def test_verify_message_valid(self):
        """Test message verification with valid signature."""
        shared_secret = "shared-secret-key"
        cross_auth = auth.CrossProjectAuth(shared_secret)

        message = {"action": "test", "timestamp": 123456}
        signature = cross_auth.sign_message(message)

        assert cross_auth.verify_message(message, signature) is True

    def test_verify_message_invalid(self):
        """Test message verification with invalid signature."""
        shared_secret = "shared-secret-key"
        cross_auth = auth.CrossProjectAuth(shared_secret)

        message = {"action": "test", "timestamp": 123456}
        fake_signature = "x" * 64

        assert cross_auth.verify_message(message, fake_signature) is False

    def test_verify_message_tampered(self):
        """Test message verification with tampered message."""
        shared_secret = "shared-secret-key"
        cross_auth = auth.CrossProjectAuth(shared_secret)

        original_message = {"action": "test", "timestamp": 123456}
        signature = cross_auth.sign_message(original_message)

        tampered_message = {"action": "hack", "timestamp": 123456}

        assert cross_auth.verify_message(tampered_message, signature) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
