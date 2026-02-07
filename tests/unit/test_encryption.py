"""Tests for Session-Buddy encryption utilities."""

import os
import pytest
from cryptography.fernet import Fernet

import session_buddy.utils.encryption as encryption_module
from session_buddy.utils.encryption import (
    DataEncryption,
    DecryptionError,
    KeyNotFoundError,
    EncryptionError,
    generate_encryption_key,
    is_encrypted,
    get_encryption,
)


@pytest.fixture
def test_key():
    """Generate a test encryption key."""
    return Fernet.generate_key().decode()


@pytest.fixture
def encryption(test_key):
    """Create DataEncryption instance with test key."""
    return DataEncryption(key=test_key)


class TestDataEncryption:
    """Test DataEncryption class."""

    def test_initialization_with_key(self, test_key):
        """Test initialization with provided key."""
        enc = DataEncryption(key=test_key)
        assert enc.cipher is not None

    def test_initialization_with_password(self):
        """Test initialization with password (key derivation)."""
        enc = DataEncryption(password="test_password")
        assert enc.cipher is not None

    def test_initialization_without_key_raises_error(self):
        """Test that initialization without key raises error."""
        # Ensure env var is not set
        if "SESSION_ENCRYPTION_KEY" in os.environ:
            del os.environ["SESSION_ENCRYPTION_KEY"]

        with pytest.raises(KeyNotFoundError) as exc_info:
            DataEncryption()

        assert "SESSION_ENCRYPTION_KEY" in str(exc_info.value)

    def test_initialization_from_env(self, test_key):
        """Test initialization from environment variable."""
        os.environ["SESSION_ENCRYPTION_KEY"] = test_key
        try:
            enc = DataEncryption()
            assert enc.cipher is not None
        finally:
            del os.environ["SESSION_ENCRYPTION_KEY"]

    def test_encrypt_string(self, encryption):
        """Test encrypting a string."""
        plaintext = "sensitive data"
        encrypted = encryption.encrypt(plaintext)

        assert isinstance(encrypted, bytes)
        assert encrypted != plaintext.encode()

    def test_encrypt_bytes(self, encryption):
        """Test encrypting bytes."""
        plaintext = b"sensitive data"
        encrypted = encryption.encrypt(plaintext)

        assert isinstance(encrypted, bytes)
        assert encrypted != plaintext

    def test_encrypt_unicode(self, encryption):
        """Test encrypting unicode characters."""
        plaintext = "Hello 世界 🌍"
        encrypted = encryption.encrypt(plaintext)

        assert isinstance(encrypted, bytes)

        # Verify decryption works
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == plaintext

    def test_decrypt_string(self, encryption):
        """Test decrypting to string."""
        plaintext = "sensitive data"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert isinstance(decrypted, str)
        assert decrypted == plaintext

    def test_decrypt_bytes(self, encryption):
        """Test decrypting bytes to string."""
        plaintext = b"sensitive data"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == "sensitive data"

    def test_decrypt_wrong_key_raises_error(self, test_key):
        """Test that decrypting with wrong key raises error."""
        enc1 = DataEncryption(key=test_key)
        enc2 = DataEncryption(key=Fernet.generate_key().decode())

        plaintext = "secret"
        encrypted = enc1.encrypt(plaintext)

        with pytest.raises(DecryptionError):
            enc2.decrypt(encrypted)

    def test_decrypt_invalid_token_raises_error(self, encryption):
        """Test that decrypting invalid token raises error."""
        invalid_token = b"not_a_valid_fernet_token"

        with pytest.raises(DecryptionError):
            encryption.decrypt(invalid_token)

    def test_encrypt_dict_default_fields(self, encryption):
        """Test encrypting dict with default sensitive fields."""
        data = {
            "content": "sensitive content",
            "api_key": "secret_key",
            "public": "visible data"
        }

        encrypted = encryption.encrypt_dict(data)

        assert isinstance(encrypted["content"], bytes)
        assert isinstance(encrypted["api_key"], bytes)
        assert encrypted["public"] == "visible data"  # Not encrypted

    def test_encrypt_dict_custom_fields(self, encryption):
        """Test encrypting dict with custom fields."""
        data = {
            "custom_field": "secret",
            "other_field": "not secret"
        }

        encrypted = encryption.encrypt_dict(data, fields=["custom_field"])

        assert isinstance(encrypted["custom_field"], bytes)
        assert encrypted["other_field"] == "not secret"

    def test_encrypt_dict_handles_missing_fields(self, encryption):
        """Test that encrypt_dict handles missing fields gracefully."""
        data = {"public": "visible"}

        # Should not raise error
        encrypted = encryption.encrypt_dict(data)
        assert encrypted["public"] == "visible"

    def test_decrypt_dict_default_fields(self, encryption):
        """Test decrypting dict with default fields."""
        data = {"content": "secret", "public": "visible"}

        # Encrypt
        encrypted = encryption.encrypt_dict(data)

        # Decrypt
        decrypted = encryption.decrypt_dict(encrypted)

        assert decrypted["content"] == "secret"
        assert decrypted["public"] == "visible"

    def test_decrypt_dict_custom_fields(self, encryption):
        """Test decrypting dict with custom fields."""
        data = {"custom": "secret"}

        encrypted = encryption.encrypt_dict(data, fields=["custom"])
        decrypted = encryption.decrypt_dict(encrypted, fields=["custom"])

        assert decrypted["custom"] == "secret"

    def test_decrypt_dict_handles_unencrypted_fields(self, encryption):
        """Test that decrypt_dict skips unencrypted fields."""
        data = {"already_plain": "not encrypted"}

        # Should not raise error
        result = encryption.decrypt_dict(data)
        assert result["already_plain"] == "not encrypted"

    def test_generate_key(self, encryption):
        """Test generating a new Fernet key."""
        key = encryption.generate_key()

        assert isinstance(key, str)
        assert len(key) == 44  # 32 bytes in base64

        # Key should be valid Fernet key
        fernet = Fernet(key)
        assert fernet is not None

    def test_rotate_key(self, encryption, test_key):
        """Test rotating encryption keys."""
        # Create new key
        new_key = Fernet.generate_key().decode()
        new_encryption = DataEncryption(key=new_key)

        # Encrypt with old key
        plaintext = "secret data"
        encrypted = encryption.encrypt(plaintext)

        # Rotate to new key
        rotated = encryption.rotate_key(encrypted, new_encryption.cipher)

        # Decrypt with new key
        decrypted = new_encryption.decrypt(rotated)
        assert decrypted == plaintext

    def test_roundtrip_encryption(self, encryption):
        """Test that encrypt/decrypt roundtrip works."""
        test_cases = [
            "simple text",
            "with numbers 123",
            "special chars !@#$%",
            "unicode 世界 🌍",
            "multi\nline\ntext",
            "very long text " * 100
        ]

        for plaintext in test_cases:
            encrypted = encryption.encrypt(plaintext)
            decrypted = encryption.decrypt(encrypted)
            assert decrypted == plaintext


class TestGenerateEncryptionKey:
    """Test generate_encryption_key function."""

    def test_generate_key(self):
        """Test key generation."""
        key = generate_encryption_key()

        assert isinstance(key, str)
        assert len(key) == 44

        # Should be valid Fernet key
        fernet = Fernet(key)
        encrypted = fernet.encrypt(b"test")
        assert fernet.decrypt(encrypted) == b"test"

    def test_generate_unique_keys(self):
        """Test that each generated key is unique."""
        keys = [generate_encryption_key() for _ in range(10)]

        assert len(set(keys)) == 10  # All unique


class TestIsEncrypted:
    """Test is_encrypted function."""

    def test_fernet_encrypted_data(self, encryption):
        """Test that Fernet-encrypted data is detected."""
        encrypted = encryption.encrypt("test")
        assert is_encrypted(encrypted) is True

    def test_plain_bytes(self):
        """Test that plain bytes are not detected as encrypted."""
        assert is_encrypted(b"plain text") is False
        assert is_encrypted(b"") is False

    def test_wrong_version_byte(self):
        """Test data with wrong version byte."""
        # Fernet starts with 128 (0x80)
        wrong_version = b"\x00" + b"s" * 63
        assert is_encrypted(wrong_version) is False

    def test_non_bytes_input(self):
        """Test that non-bytes input returns False."""
        assert is_encrypted("string") is False
        assert is_encrypted(123) is False
        assert is_encrypted(None) is False


class TestGetEncryption:
    """Test get_encryption singleton function."""

    def test_singleton_behavior(self, test_key):
        """Test that get_encryption returns same instance."""
        os.environ["SESSION_ENCRYPTION_KEY"] = test_key

        try:
            enc1 = get_encryption()
            enc2 = get_encryption()

            assert enc1 is enc2
        finally:
            del os.environ["SESSION_ENCRYPTION_KEY"]

    def test_raises_without_env_key(self):
        """Test that get_encryption raises error without key."""
        # Save current state
        old_key = os.environ.get("SESSION_ENCRYPTION_KEY")
        old_instance = encryption_module._encryption_instance

        try:
            # Reset singleton and env
            encryption_module._encryption_instance = None
            if "SESSION_ENCRYPTION_KEY" in os.environ:
                del os.environ["SESSION_ENCRYPTION_KEY"]

            with pytest.raises(KeyNotFoundError):
                get_encryption()
        finally:
            # Restore state
            encryption_module._encryption_instance = old_instance
            if old_key:
                os.environ["SESSION_ENCRYPTION_KEY"] = old_key
            elif "SESSION_ENCRYPTION_KEY" in os.environ:
                del os.environ["SESSION_ENCRYPTION_KEY"]


class TestIntegration:
    """Integration tests for encryption workflow."""

    def test_session_encryption_workflow(self, encryption):
        """Test typical session encryption workflow."""
        # Simulate session data
        session_data = {
            "session_id": "abc123",
            "content": "User asked about API implementation",
            "reflection": "Discussed REST vs GraphQL",
            "api_key": "sk_test_12345",  # Sensitive
            "timestamp": "2026-02-02T12:00:00Z",
            "user_id": "user_456"
        }

        # Encrypt sensitive fields
        encrypted_data = encryption.encrypt_dict(session_data)

        # Verify sensitive fields are encrypted
        assert isinstance(encrypted_data["content"], bytes)
        assert isinstance(encrypted_data["reflection"], bytes)
        assert isinstance(encrypted_data["api_key"], bytes)

        # Verify non-sensitive fields are intact
        assert encrypted_data["session_id"] == "abc123"
        assert encrypted_data["timestamp"] == "2026-02-02T12:00:00Z"

        # Decrypt all fields
        decrypted_data = encryption.decrypt_dict(encrypted_data)

        # Verify all fields match original
        assert decrypted_data["session_id"] == session_data["session_id"]
        assert decrypted_data["content"] == session_data["content"]
        assert decrypted_data["reflection"] == session_data["reflection"]
        assert decrypted_data["api_key"] == session_data["api_key"]
        assert decrypted_data["timestamp"] == session_data["timestamp"]

    def test_key_rotation_workflow(self):
        """Test key rotation for existing encrypted data."""
        # Old key
        old_key = Fernet.generate_key().decode()
        old_enc = DataEncryption(key=old_key)

        # Encrypt data with old key
        data = "sensitive session content"
        encrypted = old_enc.encrypt(data)

        # Generate new key
        new_key = Fernet.generate_key().decode()
        new_enc = DataEncryption(key=new_key)

        # Rotate
        rotated = old_enc.rotate_key(encrypted, new_enc.cipher)

        # Verify new key can decrypt
        decrypted = new_enc.decrypt(rotated)
        assert decrypted == data

        # Verify old key cannot decrypt rotated data
        with pytest.raises(DecryptionError):
            old_enc.decrypt(rotated)
