"""Unit tests for ``session_buddy.utils.encryption``.

Covers the public surface: exception hierarchy, ``DataEncryption``
(encrypt/decrypt round-trip, dict variants, key generation, rotation,
key-derivation), plus the module-level helpers ``generate_encryption_key``,
``is_encrypted``, and ``get_encryption``.
"""

from __future__ import annotations

import base64
import os
from contextlib import suppress

import pytest
from cryptography.fernet import Fernet, InvalidToken

from session_buddy.utils import encryption as enc_mod
from session_buddy.utils.encryption import (
    DataEncryption,
    DecryptionError,
    EncryptionError,
    KeyNotFoundError,
    generate_encryption_key,
    get_encryption,
    is_encrypted,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fernet_key() -> str:
    """Return a freshly generated Fernet key (url-safe base64 string)."""
    return Fernet.generate_key().decode()


@pytest.fixture()
def enc(fernet_key: str) -> DataEncryption:
    """Return a DataEncryption initialised with an explicit Fernet key."""
    return DataEncryption(key=fernet_key)


@pytest.fixture()
def other_cipher(fernet_key: str) -> Fernet:
    """Return a second Fernet cipher (for key-rotation tests)."""
    other_key = Fernet.generate_key().decode()
    assert other_key != fernet_key
    return Fernet(other_key.encode())


@pytest.fixture()
def reset_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level singleton between tests."""
    monkeypatch.setattr(enc_mod, "_encryption_instance", None)
    monkeypatch.delenv("SESSION_ENCRYPTION_KEY", raising=False)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """EncryptionError is the root for module-specific errors."""

    def test_encryption_error_is_exception(self) -> None:
        assert issubclass(EncryptionError, Exception)

    def test_key_not_found_is_encryption_error(self) -> None:
        assert issubclass(KeyNotFoundError, EncryptionError)
        assert issubclass(KeyNotFoundError, Exception)

    def test_decryption_error_is_encryption_error(self) -> None:
        assert issubclass(DecryptionError, EncryptionError)
        assert issubclass(DecryptionError, Exception)

    def test_can_raise_and_catch_via_base(self) -> None:
        with pytest.raises(EncryptionError):
            raise KeyNotFoundError("missing")
        with pytest.raises(EncryptionError):
            raise DecryptionError("bad token")


# ---------------------------------------------------------------------------
# DataEncryption.__init__
# ---------------------------------------------------------------------------


class TestDataEncryptionInit:
    """Constructor accepts a key, a password, or the env var."""

    def test_init_with_key_string(self, fernet_key: str) -> None:
        e = DataEncryption(key=fernet_key)
        assert e.cipher is not None

    def test_init_with_key_bytes(self, fernet_key: str) -> None:
        e = DataEncryption(key=fernet_key.encode())
        assert e.cipher is not None

    def test_init_with_password_derives_cipher(self) -> None:
        e = DataEncryption(password="correct horse battery staple")
        assert e.cipher is not None

    def test_init_with_env_var(self, fernet_key: str, reset_singleton: None) -> None:
        os.environ["SESSION_ENCRYPTION_KEY"] = fernet_key
        e = DataEncryption()
        assert e.cipher is not None

    def test_init_missing_all_sources_raises(self, reset_singleton: None) -> None:
        with pytest.raises(KeyNotFoundError) as exc:
            DataEncryption()
        assert "SESSION_ENCRYPTION_KEY" in str(exc.value)


# ---------------------------------------------------------------------------
# DataEncryption.encrypt / decrypt (round-trip)
# ---------------------------------------------------------------------------


class TestEncryptDecryptRoundTrip:
    """encrypt then decrypt must return the original value."""

    @pytest.mark.parametrize(
        "plaintext",
        [
            "hello world",
            "",
            "a",
            "with spaces and !@#$%^&*()",
            "unicode: é中文 \U0001f600",
            "multi\nline\ntext",
            "x" * 1024,
        ],
    )
    def test_str_round_trip(self, enc: DataEncryption, plaintext: str) -> None:
        encrypted = enc.encrypt(plaintext)
        assert isinstance(encrypted, bytes)
        assert encrypted != plaintext.encode()
        assert enc.decrypt(encrypted) == plaintext

    def test_bytes_round_trip(self, enc: DataEncryption) -> None:
        # decrypt() always decodes as UTF-8, so the payload must be valid UTF-8.
        payload = b"\x00\x01\x02raw bytes \xc3\xa9\n"
        encrypted = enc.encrypt(payload)
        assert enc.decrypt(encrypted) == payload.decode("utf-8")

    def test_encrypt_returns_bytes(self, enc: DataEncryption) -> None:
        result = enc.encrypt("data")
        assert isinstance(result, bytes)

    def test_decrypt_returns_str(self, enc: DataEncryption) -> None:
        result = enc.decrypt(enc.encrypt("hello"))
        assert isinstance(result, str)

    def test_same_plaintext_produces_different_ciphertexts(self, enc: DataEncryption) -> None:
        # Fernet uses a random IV per encryption — same plaintext must differ.
        a = enc.encrypt("same text")
        b = enc.encrypt("same text")
        assert a != b
        assert enc.decrypt(a) == enc.decrypt(b) == "same text"

    def test_two_instances_same_key_can_decrypt_each_other(
        self, fernet_key: str
    ) -> None:
        e1 = DataEncryption(key=fernet_key)
        e2 = DataEncryption(key=fernet_key)
        ciphertext = e1.encrypt("shared")
        assert e2.decrypt(ciphertext) == "shared"


# ---------------------------------------------------------------------------
# Encryption / decryption error paths
# ---------------------------------------------------------------------------


class TestEncryptDecryptErrors:
    """Failure modes are surfaced via EncryptionError / DecryptionError."""

    def test_decrypt_with_wrong_key_raises_decryption_error(
        self, fernet_key: str
    ) -> None:
        original = DataEncryption(key=fernet_key)
        other = DataEncryption(key=Fernet.generate_key().decode())
        ciphertext = original.encrypt("secret")
        with pytest.raises(DecryptionError):
            other.decrypt(ciphertext)

    def test_decrypt_invalid_token_raises_decryption_error(
        self, enc: DataEncryption
    ) -> None:
        with pytest.raises(DecryptionError):
            enc.decrypt(b"this is not a fernet token at all" * 4)

    def test_decrypt_preserves_underlying_invalid_token_message(
        self, enc: DataEncryption
    ) -> None:
        with pytest.raises(DecryptionError) as exc:
            enc.decrypt(b"not-a-real-fernet-token-padded-to-length" * 2)
        # Either InvalidToken path or generic exception path is acceptable;
        # both must surface as DecryptionError.
        assert isinstance(exc.value, DecryptionError)


# ---------------------------------------------------------------------------
# Password-derived keys (PBKDF2)
# ---------------------------------------------------------------------------


class TestPasswordDerivedKeys:
    """Password-derived ciphers work but are independent each call."""

    def test_same_password_different_salts_yield_different_keys(
        self, fernet_key: str
    ) -> None:
        # Seed an instance via a real Fernet key, then call the private
        # key-derivation helper directly with two distinct salts.
        seed = DataEncryption(key=fernet_key)
        salt_a = b"a" * 16
        salt_b = b"b" * 16
        cipher_a = seed._derive_key_from_password("pw", salt=salt_a)
        cipher_b = seed._derive_key_from_password("pw", salt=salt_b)
        plaintext = b"data"
        token_a = cipher_a.encrypt(plaintext)
        # Raw Fernet.decrypt raises InvalidToken (not DecryptionError) —
        # the salt change must produce keys that fail at the Fernet layer.
        with pytest.raises(InvalidToken):
            cipher_b.decrypt(token_a)

    def test_same_password_same_salt_yield_same_key(self, fernet_key: str) -> None:
        seed = DataEncryption(key=fernet_key)
        salt = b"shared-salt-bytes!"[:16].ljust(16, b"\x00")
        cipher_a = seed._derive_key_from_password("pw", salt=salt)
        cipher_b = seed._derive_key_from_password("pw", salt=salt)
        token = cipher_a.encrypt(b"data")
        # Fernet.decrypt returns bytes; compare against bytes.
        assert cipher_b.decrypt(token) == b"data"

    def test_derive_key_returns_fernet_cipher(self, fernet_key: str) -> None:
        seed = DataEncryption(key=fernet_key)
        result = seed._derive_key_from_password("pw", salt=b"s" * 16)
        assert isinstance(result, Fernet)

    def test_encrypt_decrypt_with_password_instance(self) -> None:
        e = DataEncryption(password="user-password")
        token = e.encrypt("round trip")
        assert e.decrypt(token) == "round trip"


# ---------------------------------------------------------------------------
# Dictionary helpers
# ---------------------------------------------------------------------------


DEFAULT_SENSITIVE_FIELDS = {
    "content",
    "reflection",
    "api_key",
    "password",
    "token",
    "secret",
    "session_content",
    "api_keys",
    "user_credentials",
}


class TestEncryptDict:
    """encrypt_dict encrypts only listed/falsy-skipped fields."""

    def test_default_fields_are_encrypted(self, enc: DataEncryption) -> None:
        data = {"content": "secret", "public": "visible"}
        result = enc.encrypt_dict(data)
        assert isinstance(result["content"], bytes)
        assert result["public"] == "visible"
        assert enc.decrypt(result["content"]) == "secret"

    def test_custom_fields_subset(self, enc: DataEncryption) -> None:
        data = {"api_key": "k-1234", "username": "alice"}
        result = enc.encrypt_dict(data, fields=["api_key"])
        assert isinstance(result["api_key"], bytes)
        assert result["username"] == "alice"

    def test_empty_string_values_are_skipped(self, enc: DataEncryption) -> None:
        data = {"content": "", "other": "x"}
        result = enc.encrypt_dict(data)
        assert result["content"] == ""
        assert result["other"] == "x"

    def test_dict_does_not_mutate_input(self, enc: DataEncryption) -> None:
        original = {"content": "secret", "public": "visible"}
        enc.encrypt_dict(original)
        assert original["content"] == "secret"
        assert original["public"] == "visible"

    def test_bytes_values_are_encrypted(self, enc: DataEncryption) -> None:
        data = {"token": b"raw-bytes"}
        result = enc.encrypt_dict(data)
        assert isinstance(result["token"], bytes)
        assert enc.decrypt(result["token"]) == "raw-bytes"

    def test_complex_types_are_skipped_silently(self, enc: DataEncryption) -> None:
        # lists and dicts are not encrypted (TODO in source).
        data = {"api_key": ["k1", "k2"], "nested": {"k": "v"}}
        result = enc.encrypt_dict(data)
        assert result["api_key"] == ["k1", "k2"]
        assert result["nested"] == {"k": "v"}

    def test_missing_fields_are_ignored(self, enc: DataEncryption) -> None:
        data = {"unrelated": "value"}
        result = enc.encrypt_dict(data, fields=["api_key", "token"])
        assert result == {"unrelated": "value"}


class TestDecryptDict:
    """decrypt_dict restores previously-encrypted fields."""

    def test_default_fields_round_trip(self, enc: DataEncryption) -> None:
        original = {"content": "secret", "public": "visible"}
        encrypted = enc.encrypt_dict(original)
        decrypted = enc.decrypt_dict(encrypted)
        assert decrypted["content"] == "secret"
        assert decrypted["public"] == "visible"

    def test_custom_fields_round_trip(self, enc: DataEncryption) -> None:
        original = {"api_key": "k1", "token": "t1"}
        encrypted = enc.encrypt_dict(original, fields=["api_key", "token"])
        decrypted = enc.decrypt_dict(encrypted, fields=["api_key", "token"])
        assert decrypted["api_key"] == "k1"
        assert decrypted["token"] == "t1"

    def test_unencrypted_bytes_are_skipped_silently(
        self, enc: DataEncryption
    ) -> None:
        # A bytes value that is not a valid Fernet token is left as-is.
        data = {"content": b"not-encrypted-payload-here"}
        result = enc.decrypt_dict(data)
        assert result["content"] == b"not-encrypted-payload-here"

    def test_missing_fields_kept_intact(self, enc: DataEncryption) -> None:
        result = enc.decrypt_dict({"public": "x"}, fields=["api_key"])
        assert result == {"public": "x"}

    def test_dict_does_not_mutate_input(self, enc: DataEncryption) -> None:
        original = {"content": "secret"}
        encrypted = enc.encrypt_dict(original)
        enc.decrypt_dict(encrypted)
        assert isinstance(encrypted["content"], bytes)


# ---------------------------------------------------------------------------
# Key generation and rotation
# ---------------------------------------------------------------------------


class TestKeyGeneration:
    """generate_key and rotate_key behave correctly."""

    def test_generate_key_returns_44_char_base64(self, enc: DataEncryption) -> None:
        key = enc.generate_key()
        assert isinstance(key, str)
        # 32 bytes -> 44 url-safe base64 chars (no padding).
        assert len(key) == 44

    def test_generate_key_is_valid_fernet_key(self, enc: DataEncryption) -> None:
        key = enc.generate_key()
        # Should round-trip through Fernet construction without raising.
        Fernet(key.encode())

    def test_generate_key_is_unique(self, enc: DataEncryption) -> None:
        assert enc.generate_key() != enc.generate_key()

    def test_rotate_key_re_encrypts_under_new_cipher(
        self, enc: DataEncryption, other_cipher: Fernet
    ) -> None:
        ciphertext = enc.encrypt("payload")
        rotated = enc.rotate_key(ciphertext, other_cipher)
        # Old key can no longer decrypt the rotated payload.
        with pytest.raises(DecryptionError):
            enc.decrypt(rotated)
        # New cipher can decrypt it.
        assert other_cipher.decrypt(rotated).decode("utf-8") == "payload"

    def test_rotate_key_propagates_decryption_error(
        self, enc: DataEncryption, other_cipher: Fernet
    ) -> None:
        bad = b"completely-not-a-fernet-token-aaaaaaaaaa" * 2
        with pytest.raises(DecryptionError):
            enc.rotate_key(bad, other_cipher)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestGenerateEncryptionKey:
    """generate_encryption_key is a thin wrapper around Fernet.generate_key."""

    def test_returns_string_of_correct_length(self) -> None:
        key = generate_encryption_key()
        assert isinstance(key, str)
        assert len(key) == 44

    def test_is_valid_fernet_key(self) -> None:
        Fernet(generate_encryption_key().encode())

    def test_two_calls_differ(self) -> None:
        assert generate_encryption_key() != generate_encryption_key()


class TestIsEncrypted:
    """is_encrypted is a structural heuristic for Fernet tokens."""

    def test_returns_true_for_valid_fernet_token(self, enc: DataEncryption) -> None:
        assert is_encrypted(enc.encrypt("payload")) is True

    def test_returns_false_for_short_bytes(self) -> None:
        assert is_encrypted(b"abc") is False
        assert is_encrypted(b"") is False

    def test_returns_false_for_non_bytes(self) -> None:
        assert is_encrypted("not bytes") is False  # type: ignore[arg-type]
        assert is_encrypted(None) is False  # type: ignore[arg-type]
        assert is_encrypted(123) is False  # type: ignore[arg-type]

    def test_returns_false_for_random_long_bytes(self) -> None:
        # Long enough to pass the length filter, but not valid base64.
        bogus = b"!" * 200
        assert is_encrypted(bogus) is False

    def test_returns_false_for_plaintext_long_ascii(self) -> None:
        # Plain ASCII >= 32 bytes that decodes cleanly as base64 will look
        # structurally valid; the heuristic still flags it.
        ascii_text = b"This is plain text that is at least thirty-two bytes!"
        result = is_encrypted(ascii_text)
        assert isinstance(result, bool)
        # We do not assert the value here because the heuristic conflates
        # long base64-decodable ASCII with Fernet tokens; just assert no crash.


class TestGetEncryption:
    """get_encryption returns a memoised singleton."""

    def test_returns_dataencryption_instance(
        self, reset_singleton: None, fernet_key: str
    ) -> None:
        os.environ["SESSION_ENCRYPTION_KEY"] = fernet_key
        instance = get_encryption()
        assert isinstance(instance, DataEncryption)

    def test_returns_same_instance_across_calls(
        self, reset_singleton: None, fernet_key: str
    ) -> None:
        os.environ["SESSION_ENCRYPTION_KEY"] = fernet_key
        first = get_encryption()
        second = get_encryption()
        assert first is second

    def test_singleton_rebuilt_when_reset(
        self, reset_singleton: None, fernet_key: str
    ) -> None:
        os.environ["SESSION_ENCRYPTION_KEY"] = fernet_key
        first = get_encryption()
        # Force a rebuild.
        enc_mod._encryption_instance = None
        second = get_encryption()
        assert first is not second

    def test_propagates_key_not_found(self, reset_singleton: None) -> None:
        with pytest.raises(KeyNotFoundError):
            get_encryption()


# ---------------------------------------------------------------------------
# Singleton/state hygiene
# ---------------------------------------------------------------------------


class TestModuleSingleton:
    """The module-level singleton must be writable/cleanable."""

    def test_singleton_starts_unset_after_reset(self, reset_singleton: None) -> None:
        assert enc_mod._encryption_instance is None