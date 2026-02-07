"""Data encryption utilities for Session-Buddy.

This module provides Fernet-based encryption for sensitive session data,
including session content, API keys, and user credentials.
"""

import os
from base64 import b64encode
from contextlib import suppress

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionError(Exception):
    """Base exception for encryption errors."""

    pass


class KeyNotFoundError(EncryptionError):
    """Raised when encryption key is not found or invalid."""

    pass


class DecryptionError(EncryptionError):
    """Raised when decryption fails."""

    pass


class DataEncryption:
    """Fernet-based encryption for sensitive session data.

    This class provides encrypt/decrypt operations using the Fernet
    symmetric encryption algorithm. Keys are derived from environment
    variables using PBKDF2 for additional security.

    Example:
        >>> enc = DataEncryption()
        >>> encrypted = enc.encrypt("sensitive data")
        >>> decrypted = enc.decrypt(encrypted)
        >>> assert decrypted == "sensitive data"
    """

    def __init__(self, key: str | None = None, password: str | None = None):
        """Initialize encryption with provided key or password.

        Args:
            key: Fernet key (32 url-safe base64-encoded bytes).
                 If not provided, uses SESSION_ENCRYPTION_KEY env variable.
            password: Password for key derivation (alternative to key).
                     Uses PBKDF2 for secure key derivation.

        Raises:
            KeyNotFoundError: If no key or password provided and
                             SESSION_ENCRYPTION_KEY not set.

        Note:
            Prefer using the environment variable SESSION_ENCRYPTION_KEY
            over passing keys directly. Use password only for testing.
        """
        if key:
            self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        elif password:
            # Derive key from password using PBKDF2
            self.cipher = self._derive_key_from_password(password)
        else:
            # Try environment variable
            env_key = os.getenv("SESSION_ENCRYPTION_KEY")
            if not env_key:
                raise KeyNotFoundError(
                    "SESSION_ENCRYPTION_KEY environment variable must be set. "
                    "Generate a secure key with:\n"
                    "  python -c 'from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())'"
                )
            self.cipher = Fernet(env_key.encode())

    def _derive_key_from_password(
        self, password: str, salt: bytes | None = None
    ) -> Fernet:
        """Derive Fernet key from password using PBKDF2.

        Args:
            password: Password to derive key from.
            salt: Salt for key derivation (generates new if None).

        Returns:
            Fernet cipher instance.

        Note:
            This is less secure than using a pre-generated Fernet key
            directly. Prefer SESSION_ENCRYPTION_KEY for production.
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        key = b64encode(kdf.derive(password.encode()))
        return Fernet(key)

    def encrypt(self, data: str | bytes) -> bytes:
        """Encrypt sensitive data before storage.

        Args:
            data: Plaintext to encrypt (string or bytes).

        Returns:
            Encrypted bytes (url-safe base64-encoded).

        Raises:
            EncryptionError: If encryption fails.

        Example:
            >>> enc = DataEncryption(key="test-key")
            >>> encrypted = enc.encrypt("my secret")
            >>> isinstance(encrypted, bytes)
            True
        """
        try:
            if isinstance(data, str):
                data = data.encode("utf-8")
            return self.cipher.encrypt(data)
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}") from e

    def decrypt(self, encrypted_data: bytes) -> str:
        """Decrypt sensitive data after retrieval.

        Args:
            encrypted_data: Encrypted bytes to decrypt.

        Returns:
            Decrypted plaintext string.

        Raises:
            DecryptionError: If decryption fails (invalid token, wrong key).

        Example:
            >>> enc = DataEncryption(key="test-key")
            >>> encrypted = enc.encrypt("my secret")
            >>> decrypted = enc.decrypt(encrypted)
            >>> assert decrypted == "my secret"
        """
        try:
            decrypted = self.cipher.decrypt(encrypted_data)
            return decrypted.decode("utf-8")
        except InvalidToken as e:
            raise DecryptionError(
                "Decryption failed: Invalid token or wrong key"
            ) from e
        except Exception as e:
            raise DecryptionError(f"Decryption failed: {e}") from e

    def encrypt_dict(self, data: dict, fields: list[str] | None = None) -> dict:
        """Encrypt specific fields in a dictionary.

        Args:
            data: Dictionary containing sensitive fields.
            fields: List of field names to encrypt.
                   If None, encrypts common sensitive fields
                   (content, api_key, password, token, secret).

        Returns:
            New dictionary with specified fields encrypted.

        Example:
            >>> enc = DataEncryption(key="test-key")
            >>> data = {"content": "secret", "public": "visible"}
            >>> encrypted = enc.encrypt_dict(data)
            >>> isinstance(encrypted["content"], bytes)
            True
            >>> assert encrypted["public"] == "visible"
        """
        if fields is None:
            fields = [
                "content",
                "reflection",
                "api_key",
                "password",
                "token",
                "secret",
                "session_content",
                "api_keys",
                "user_credentials",
            ]

        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                value = result[field]
                if isinstance(value, str):
                    result[field] = self.encrypt(value)
                elif isinstance(value, bytes):
                    result[field] = self.encrypt(value)
                elif isinstance(value, (list, dict)):
                    # Skip complex types for now
                    # TODO: Implement JSON serialization for complex types
                    pass

        return result

    def decrypt_dict(self, data: dict, fields: list[str] | None = None) -> dict:
        """Decrypt specific fields in a dictionary.

        Args:
            data: Dictionary with encrypted fields.
            fields: List of field names to decrypt.
                   If None, decrypts common sensitive fields.

        Returns:
            New dictionary with specified fields decrypted.

        Example:
            >>> enc = DataEncryption(key="test-key")
            >>> data = {"content": "secret"}
            >>> encrypted = enc.encrypt_dict(data)
            >>> decrypted = enc.decrypt_dict(encrypted)
            >>> assert decrypted["content"] == "secret"
        """
        if fields is None:
            fields = [
                "content",
                "reflection",
                "api_key",
                "password",
                "token",
                "secret",
                "session_content",
                "api_keys",
                "user_credentials",
            ]

        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                value = result[field]
                if isinstance(value, bytes):
                    with suppress(DecryptionError):
                        # Field might not be encrypted, skip
                        result[field] = self.decrypt(value)

        return result

    def generate_key(self) -> str:
        """Generate a new Fernet encryption key.

        Returns:
            URL-safe base64-encoded 32-byte key.

        Note:
            Store this key securely in SESSION_ENCRYPTION_KEY environment
            variable. Do NOT commit to version control.

        Example:
            >>> enc = DataEncryption()
            >>> key = enc.generate_key()
            >>> len(key)
            44  # 32 bytes = 44 chars in base64
        """
        return Fernet.generate_key().decode()

    def rotate_key(self, encrypted_data: bytes, new_cipher: Fernet) -> bytes:
        """Rotate encryption key by decrypting with old and re-encrypting.

        Args:
            encrypted_data: Data encrypted with old key.
            new_cipher: New Fernet cipher instance.

        Returns:
            Data encrypted with new key.

        Raises:
            DecryptionError: If old key cannot decrypt data.

        Example:
            >>> old_enc = DataEncryption(key="old-key")
            >>> new_enc = DataEncryption(key="new-key")
            >>> data = old_enc.encrypt("secret")
            >>> rotated = old_enc.rotate_key(data, new_enc.cipher)
            >>> assert new_enc.decrypt(rotated) == "secret"
        """
        decrypted = self.decrypt(encrypted_data)
        return new_cipher.encrypt(decrypted.encode("utf-8"))


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key.

    This is a convenience function for generating keys during setup.

    Returns:
        URL-safe base64-encoded 32-byte key.

    Example:
        >>> key = generate_encryption_key()
        >>> os.environ['SESSION_ENCRYPTION_KEY'] = key
        >>> enc = DataEncryption()
        >>> enc.encrypt("test")
        b'...'
    """
    return Fernet.generate_key().decode()


def is_encrypted(data: bytes) -> bool:
    """Check if data appears to be Fernet-encrypted.

    Fernet tokens are base64-encoded and have a specific structure.
    This is a heuristic check, not a definitive validation.

    Args:
        data: Bytes to check.

    Returns:
        True if data looks like a Fernet token.

    Example:
        >>> enc = DataEncryption(key="test-key")
        >>> encrypted = enc.encrypt("test")
        >>> is_encrypted(encrypted)
        True
        >>> is_encrypted(b"not encrypted")
        False
    """
    if not isinstance(data, bytes):
        return False
    # Fernet tokens are base64-encoded, so they have specific lengths
    # and valid base64 characters. This is a simple heuristic.
    if len(data) < 32:  # Minimum Fernet token length
        return False

    # Check if it's valid base64 and has reasonable length
    try:
        import base64

        # Try to decode as base64
        decoded = base64.urlsafe_b64decode(data + b"=" * (-len(data) % 4))
        # Fernet tokens decode to at least 1 byte (version) + 8 bytes (timestamp)
        return len(decoded) >= 9
    except Exception:
        return False


# Singleton instance for lazy loading
_encryption_instance: DataEncryption | None = None


def get_encryption() -> DataEncryption:
    """Get or create singleton encryption instance.

    Returns:
        DataEncryption instance configured from environment.

    Raises:
        KeyNotFoundError: If SESSION_ENCRYPTION_KEY not set.

    Example:
        >>> enc = get_encryption()
        >>> enc.encrypt("sensitive")
        b'...'
    """
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = DataEncryption()
    return _encryption_instance
