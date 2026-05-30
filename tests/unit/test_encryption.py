"""Tests for Session-Buddy encryption utilities."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

_UTILS_PACKAGE = types.ModuleType("session_buddy.utils")
_UTILS_PACKAGE.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("session_buddy.utils", _UTILS_PACKAGE)

_MODULE_PATH = Path(__file__).resolve().parents[2] / "session_buddy" / "utils" / "encryption.py"
_SPEC = importlib.util.spec_from_file_location("session_buddy.utils.encryption", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
encryption_module = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("session_buddy.utils.encryption", encryption_module)
_SPEC.loader.exec_module(encryption_module)

DataEncryption = encryption_module.DataEncryption
DecryptionError = encryption_module.DecryptionError
KeyNotFoundError = encryption_module.KeyNotFoundError
EncryptionError = encryption_module.EncryptionError
generate_encryption_key = encryption_module.generate_encryption_key
is_encrypted = encryption_module.is_encrypted
get_encryption = encryption_module.get_encryption


@pytest.fixture
def test_key() -> str:
    """Generate a test encryption key."""
    return Fernet.generate_key().decode()


@pytest.fixture
def encryption(test_key: str) -> DataEncryption:
    """Create DataEncryption instance with test key."""
    return DataEncryption(key=test_key)


class TestDataEncryption:
    """Test DataEncryption class."""

    def test_initialization_with_key(self, test_key: str) -> None:
        enc = DataEncryption(key=test_key)
        assert enc.cipher is not None

    def test_initialization_with_password(self) -> None:
        enc = DataEncryption(password="test_password")
        assert enc.cipher is not None

    def test_initialization_without_key_raises_error(self) -> None:
        if "SESSION_ENCRYPTION_KEY" in os.environ:
            del os.environ["SESSION_ENCRYPTION_KEY"]

        with pytest.raises(KeyNotFoundError) as exc_info:
            DataEncryption()

        assert "SESSION_ENCRYPTION_KEY" in str(exc_info.value)

    def test_initialization_from_env(self, test_key: str) -> None:
        os.environ["SESSION_ENCRYPTION_KEY"] = test_key
        try:
            enc = DataEncryption()
            assert enc.cipher is not None
        finally:
            del os.environ["SESSION_ENCRYPTION_KEY"]

    def test_encrypt_string(self, encryption: DataEncryption) -> None:
        plaintext = "sensitive data"
        encrypted = encryption.encrypt(plaintext)

        assert isinstance(encrypted, bytes)
        assert encrypted != plaintext.encode()

    def test_encrypt_bytes(self, encryption: DataEncryption) -> None:
        plaintext = b"sensitive data"
        encrypted = encryption.encrypt(plaintext)

        assert isinstance(encrypted, bytes)
        assert encrypted != plaintext

    def test_encrypt_error_raises_encryption_error(
        self,
        encryption: DataEncryption,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            encryption.cipher,
            "encrypt",
            lambda data: (_ for _ in ()).throw(RuntimeError("encrypt boom")),
        )

        with pytest.raises(EncryptionError, match="Encryption failed: encrypt boom"):
            encryption.encrypt("data")

    def test_encrypt_unicode(self, encryption: DataEncryption) -> None:
        plaintext = "Hello 世界 🌍"
        encrypted = encryption.encrypt(plaintext)

        assert isinstance(encrypted, bytes)

        decrypted = encryption.decrypt(encrypted)
        assert decrypted == plaintext

    def test_decrypt_string(self, encryption: DataEncryption) -> None:
        plaintext = "sensitive data"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert isinstance(decrypted, str)
        assert decrypted == plaintext

    def test_decrypt_bytes(self, encryption: DataEncryption) -> None:
        plaintext = b"sensitive data"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == "sensitive data"

    def test_decrypt_wrong_key_raises_error(self, test_key: str) -> None:
        enc1 = DataEncryption(key=test_key)
        enc2 = DataEncryption(key=Fernet.generate_key().decode())

        plaintext = "secret"
        encrypted = enc1.encrypt(plaintext)

        with pytest.raises(DecryptionError):
            enc2.decrypt(encrypted)

    def test_decrypt_invalid_token_raises_error(self, encryption: DataEncryption) -> None:
        invalid_token = b"not_a_valid_fernet_token"

        with pytest.raises(DecryptionError):
            encryption.decrypt(invalid_token)

    def test_decrypt_generic_error_raises_decryption_error(
        self,
        encryption: DataEncryption,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            encryption.cipher,
            "decrypt",
            lambda data: (_ for _ in ()).throw(RuntimeError("decrypt boom")),
        )

        with pytest.raises(DecryptionError, match="Decryption failed: decrypt boom"):
            encryption.decrypt(b"ciphertext")

    def test_encrypt_dict_default_fields(self, encryption: DataEncryption) -> None:
        data = {
            "content": "sensitive content",
            "api_key": "secret_key",
            "public": "visible data",
        }

        encrypted = encryption.encrypt_dict(data)

        assert isinstance(encrypted["content"], bytes)
        assert isinstance(encrypted["api_key"], bytes)
        assert encrypted["public"] == "visible data"

    def test_encrypt_dict_custom_fields(self, encryption: DataEncryption) -> None:
        data = {
            "custom_field": "secret",
            "other_field": "not secret",
        }

        encrypted = encryption.encrypt_dict(data, fields=["custom_field"])

        assert isinstance(encrypted["custom_field"], bytes)
        assert encrypted["other_field"] == "not secret"

    def test_encrypt_dict_bytes_field(self, encryption: DataEncryption) -> None:
        data = {"token": b"secret-bytes", "public": "visible"}

        encrypted = encryption.encrypt_dict(data, fields=["token"])

        assert isinstance(encrypted["token"], bytes)
        assert encrypted["public"] == "visible"

    def test_encrypt_dict_handles_missing_fields(self, encryption: DataEncryption) -> None:
        data = {"public": "visible"}

        encrypted = encryption.encrypt_dict(data)
        assert encrypted["public"] == "visible"

    def test_encrypt_dict_skips_complex_types(self, encryption: DataEncryption) -> None:
        data = {
            "content": ["nested", "list"],
            "api_key": {"value": "secret"},
            "public": "visible",
        }

        encrypted = encryption.encrypt_dict(data)

        assert encrypted["content"] == ["nested", "list"]
        assert encrypted["api_key"] == {"value": "secret"}
        assert encrypted["public"] == "visible"

    def test_decrypt_dict_default_fields(self, encryption: DataEncryption) -> None:
        data = {"content": "secret", "public": "visible"}

        encrypted = encryption.encrypt_dict(data)
        decrypted = encryption.decrypt_dict(encrypted)

        assert decrypted["content"] == "secret"
        assert decrypted["public"] == "visible"

    def test_decrypt_dict_custom_fields(self, encryption: DataEncryption) -> None:
        data = {"custom": "secret"}

        encrypted = encryption.encrypt_dict(data, fields=["custom"])
        decrypted = encryption.decrypt_dict(encrypted, fields=["custom"])

        assert decrypted["custom"] == "secret"

    def test_decrypt_dict_handles_unencrypted_fields(self, encryption: DataEncryption) -> None:
        data = {"already_plain": "not encrypted"}

        result = encryption.decrypt_dict(data)
        assert result["already_plain"] == "not encrypted"

    def test_decrypt_dict_skips_non_bytes_values(self, encryption: DataEncryption) -> None:
        data = {"content": "already plain", "api_key": 123}

        result = encryption.decrypt_dict(data)

        assert result == data

    def test_generate_key(self, encryption: DataEncryption) -> None:
        key = encryption.generate_key()

        assert isinstance(key, str)
        assert len(key) == 44

        fernet = Fernet(key)
        assert fernet is not None

    def test_rotate_key(self, encryption: DataEncryption, test_key: str) -> None:
        new_key = Fernet.generate_key().decode()
        new_encryption = DataEncryption(key=new_key)

        plaintext = "secret data"
        encrypted = encryption.encrypt(plaintext)

        rotated = encryption.rotate_key(encrypted, new_encryption.cipher)

        decrypted = new_encryption.decrypt(rotated)
        assert decrypted == plaintext

    def test_roundtrip_encryption(self, encryption: DataEncryption) -> None:
        test_cases = [
            "simple text",
            "with numbers 123",
            "special chars !@#$%",
            "unicode 世界 🌍",
            "multi\nline\ntext",
            "very long text " * 100,
        ]

        for plaintext in test_cases:
            encrypted = encryption.encrypt(plaintext)
            decrypted = encryption.decrypt(encrypted)
            assert decrypted == plaintext


class TestGenerateEncryptionKey:
    """Test generate_encryption_key function."""

    def test_generate_key(self) -> None:
        key = generate_encryption_key()

        assert isinstance(key, str)
        assert len(key) == 44

        fernet = Fernet(key)
        encrypted = fernet.encrypt(b"test")
        assert fernet.decrypt(encrypted) == b"test"

    def test_generate_unique_keys(self) -> None:
        keys = [generate_encryption_key() for _ in range(10)]

        assert len(set(keys)) == 10


class TestIsEncrypted:
    """Test is_encrypted function."""

    def test_fernet_encrypted_data(self, encryption: DataEncryption) -> None:
        encrypted = encryption.encrypt("test")
        assert is_encrypted(encrypted) is True

    def test_plain_bytes(self) -> None:
        assert is_encrypted(b"plain text") is False
        assert is_encrypted(b"") is False

    def test_wrong_version_byte(self) -> None:
        wrong_version = b"\x00" + b"s" * 63
        assert is_encrypted(wrong_version) is False

    def test_non_bytes_input(self) -> None:
        assert is_encrypted("string") is False
        assert is_encrypted(123) is False
        assert is_encrypted(None) is False

    def test_short_and_invalid_base64_inputs(self) -> None:
        assert is_encrypted(b"short") is False
        assert is_encrypted(b"!@#$%^&*()_+INVALIDTOKEN!!!!!") is False


class TestGetEncryption:
    """Test get_encryption singleton function."""

    def test_singleton_behavior(self, test_key: str) -> None:
        os.environ["SESSION_ENCRYPTION_KEY"] = test_key

        try:
            enc1 = get_encryption()
            enc2 = get_encryption()

            assert enc1 is enc2
        finally:
            del os.environ["SESSION_ENCRYPTION_KEY"]

    def test_raises_without_env_key(self) -> None:
        old_key = os.environ.get("SESSION_ENCRYPTION_KEY")
        old_instance = encryption_module._encryption_instance

        try:
            encryption_module._encryption_instance = None
            if "SESSION_ENCRYPTION_KEY" in os.environ:
                del os.environ["SESSION_ENCRYPTION_KEY"]

            with pytest.raises(KeyNotFoundError):
                get_encryption()
        finally:
            encryption_module._encryption_instance = old_instance
            if old_key:
                os.environ["SESSION_ENCRYPTION_KEY"] = old_key
            elif "SESSION_ENCRYPTION_KEY" in os.environ:
                del os.environ["SESSION_ENCRYPTION_KEY"]

    def test_reuses_existing_instance(self, test_key: str) -> None:
        old_instance = encryption_module._encryption_instance
        try:
            encryption_module._encryption_instance = DataEncryption(key=test_key)
            instance = get_encryption()
            assert instance is encryption_module._encryption_instance
        finally:
            encryption_module._encryption_instance = old_instance


class TestIntegration:
    """Integration tests for encryption workflow."""

    def test_session_encryption_workflow(self, encryption: DataEncryption) -> None:
        session_data = {
            "session_id": "abc123",
            "content": "User asked about API implementation",
            "reflection": "Discussed REST vs GraphQL",
            "api_key": "sk_test_12345",
            "timestamp": "2026-02-02T12:00:00Z",
            "user_id": "user_456",
        }

        encrypted_data = encryption.encrypt_dict(session_data)

        assert isinstance(encrypted_data["content"], bytes)
        assert isinstance(encrypted_data["reflection"], bytes)
        assert isinstance(encrypted_data["api_key"], bytes)

        assert encrypted_data["session_id"] == "abc123"
        assert encrypted_data["timestamp"] == "2026-02-02T12:00:00Z"

        decrypted_data = encryption.decrypt_dict(encrypted_data)

        assert decrypted_data["session_id"] == session_data["session_id"]
        assert decrypted_data["content"] == session_data["content"]
        assert decrypted_data["reflection"] == session_data["reflection"]
        assert decrypted_data["api_key"] == session_data["api_key"]
        assert decrypted_data["timestamp"] == session_data["timestamp"]

    def test_key_rotation_workflow(self) -> None:
        old_key = Fernet.generate_key().decode()
        old_enc = DataEncryption(key=old_key)

        data = "sensitive session content"
        encrypted = old_enc.encrypt(data)

        new_key = Fernet.generate_key().decode()
        new_enc = DataEncryption(key=new_key)

        rotated = old_enc.rotate_key(encrypted, new_enc.cipher)

        decrypted = new_enc.decrypt(rotated)
        assert decrypted == data

        with pytest.raises(DecryptionError):
            old_enc.decrypt(rotated)
