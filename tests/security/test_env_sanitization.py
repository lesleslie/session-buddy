"""Environment variable sanitization tests.

Tests for sensitive environment variable removal in subprocess calls.
"""

import os
import pytest
from session_buddy.utils.subprocess_helper import _get_safe_environment


def test_environment_sanitization_removes_password():
    """Test PASSWORD-like variables are removed."""
    # Set sensitive variables
    os.environ["TEST_PASSWORD"] = "secret123"
    os.environ["TEST_TOKEN"] = "abc123"
    os.environ["TEST_NORMAL"] = "normal_value"

    safe_env = _get_safe_environment()

    # Sensitive vars should be removed
    assert "TEST_PASSWORD" not in safe_env
    assert "TEST_TOKEN" not in safe_env

    # Normal vars should remain
    assert safe_env.get("TEST_NORMAL") == "normal_value"

    # Cleanup
    del os.environ["TEST_PASSWORD"]
    del os.environ["TEST_TOKEN"]
    del os.environ["TEST_NORMAL"]


def test_environment_sanitization_removes_key():
    """Test KEY-like variables are removed."""
    os.environ["API_KEY"] = "key123"
    os.environ["SECRET_KEY"] = "secret"
    os.environ["PUBLIC_KEY"] = "public"  # Still contains KEY

    safe_env = _get_safe_environment()

    # All KEY-containing vars should be removed
    assert "API_KEY" not in safe_env
    assert "SECRET_KEY" not in safe_env
    assert "PUBLIC_KEY" not in safe_env

    # Cleanup
    del os.environ["API_KEY"]
    del os.environ["SECRET_KEY"]
    del os.environ["PUBLIC_KEY"]


def test_environment_sanitization_case_insensitive():
    """Test sanitization is case-insensitive."""
    # Test various casings
    os.environ["TEST_PASSWORD"] = "lower"
    os.environ["TEST_PaSsWoRd"] = "mixed"
    os.environ["TEST_PASSWORD"] = "UPPER"

    safe_env = _get_safe_environment()

    # All variations should be removed
    assert "TEST_PASSWORD" not in safe_env
    assert "TEST_PaSsWoRd" not in safe_env
    assert "TEST_PASSWORD" not in safe_env

    # Cleanup
    del os.environ["TEST_PASSWORD"]
    del os.environ["TEST_PaSsWoRd"]


def test_environment_sanitization_removes_credential():
    """Test CREDENTIAL-like variables are removed."""
    os.environ["DB_CREDENTIALS"] = "creds"
    os.environ["USER_CREDENTIAL"] = "userpass"

    safe_env = _get_safe_environment()

    # CREDENTIAL vars should be removed
    assert "DB_CREDENTIALS" not in safe_env
    assert "USER_CREDENTIAL" not in safe_env

    # Cleanup
    del os.environ["DB_CREDENTIALS"]
    del os.environ["USER_CREDENTIAL"]


def test_environment_sanitization_removes_api():
    """Test API-like variables are removed."""
    os.environ["API_TOKEN"] = "token"
    os.environ["GITHUB_API"] = "key"
    os.environ["OPENAI_API_KEY"] = "sk-..."

    safe_env = _get_safe_environment()

    # API vars should be removed
    assert "API_TOKEN" not in safe_env
    assert "GITHUB_API" not in safe_env
    assert "OPENAI_API_KEY" not in safe_env

    # Cleanup
    del os.environ["API_TOKEN"]
    del os.environ["GITHUB_API"]
    del os.environ["OPENAI_API_KEY"]


def test_environment_sanitization_preserves_safe_vars():
    """Test safe environment variables are preserved."""
    # Set safe variables
    os.environ["PATH"] = "/usr/bin:/bin"
    os.environ["HOME"] = "/home/user"
    os.environ["USER"] = "testuser"
    os.environ["SHELL"] = "/bin/bash"
    os.environ["LANG"] = "en_US.UTF-8"
    os.environ["TERM"] = "xterm-256color"

    safe_env = _get_safe_environment()

    # Safe vars should remain
    assert "PATH" in safe_env
    assert "HOME" in safe_env
    assert "USER" in safe_env
    assert "SHELL" in safe_env
    assert "LANG" in safe_env
    assert "TERM" in safe_env


def test_environment_sanitization_does_not_modify_os_environ():
    """Test sanitization doesn't modify the actual os.environ."""
    # Set a sensitive variable
    os.environ["SECRET_PASSWORD"] = "sensitive"

    # Get safe environment
    safe_env = _get_safe_environment()

    # Original should still be in os.environ
    assert "SECRET_PASSWORD" in os.environ

    # But not in safe environment
    assert "SECRET_PASSWORD" not in safe_env

    # Cleanup
    del os.environ["SECRET_PASSWORD"]


def test_environment_sanitization_session_and_cookie():
    """Test SESSION and COOKIE variables are removed."""
    os.environ["SESSION_ID"] = "session123"
    os.environ["COOKIE_DATA"] = "cookie=value"
    os.environ["SESSION_TOKEN"] = "token"

    safe_env = _get_safe_environment()

    # Session and cookie vars should be removed
    assert "SESSION_ID" not in safe_env
    assert "COOKIE_DATA" not in safe_env
    assert "SESSION_TOKEN" not in safe_env

    # Cleanup
    del os.environ["SESSION_ID"]
    del os.environ["COOKIE_DATA"]
    del os.environ["SESSION_TOKEN"]


def test_environment_sanitization_auth_var():
    """Test AUTH-like variables are removed."""
    os.environ["AUTH_TOKEN"] = "auth"
    os.environ["BEARER_AUTH"] = "bearer"

    safe_env = _get_safe_environment()

    # AUTH vars should be removed
    assert "AUTH_TOKEN" not in safe_env
    assert "BEARER_AUTH" not in safe_env

    # Cleanup
    del os.environ["AUTH_TOKEN"]
    del os.environ["BEARER_AUTH"]
