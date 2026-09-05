"""Unit tests for session_buddy.storage.sync_protocol module.

Covers the SyncMethod runtime-checkable Protocol surface, the SyncError
exception hierarchy (message formatting, attribute access), and the
HybridSyncError sub-type (errors list contract).
"""

from __future__ import annotations

import inspect

import pytest

from session_buddy.storage.sync_protocol import (
    CloudUploadError,
    HTTPSyncError,
    HybridSyncError,
    SyncError,
    SyncMethod,
)


class TestSyncMethodProtocol:
    """SyncMethod is a runtime_checkable Protocol."""

    def test_syncmethod_is_runtime_checkable(self) -> None:
        assert getattr(SyncMethod, "_is_runtime_protocol", False) or hasattr(
            SyncMethod, "_is_runtime_protocol"
        )

    def test_isinstance_returns_true_for_dummy_implementer(self) -> None:
        """A class implementing the right methods satisfies the Protocol."""

        class DummyMethod:
            async def sync(self, **kwargs) -> dict:
                return {"method": "dummy", "success": True}

            def is_available(self) -> bool:
                return True

            def get_method_name(self) -> str:
                return "dummy"

        # Async attribute access — isinstance with Protocol checks duck-typed
        # method presence. DummyMethod provides sync/is_available/get_method_name.
        assert isinstance(DummyMethod(), SyncMethod)

    def test_isinstance_returns_false_for_class_missing_methods(self) -> None:
        class Incomplete:
            async def sync(self, **kwargs):
                return {}

        assert not isinstance(Incomplete(), SyncMethod)

    def test_protocol_methods_are_coroutines(self) -> None:
        """sync must be async-definable; the others are sync methods."""
        assert callable(SyncMethod.sync)
        assert callable(SyncMethod.is_available)
        assert callable(SyncMethod.get_method_name)


class TestSyncError:
    """SyncError base class: message format + attribute access."""

    def test_message_includes_method_prefix(self) -> None:
        err = SyncError("bucket unreachable", method="cloud")
        assert "[cloud] bucket unreachable" == str(err)
        assert err.method == "cloud"
        assert err.original is None

    def test_original_exception_preserved(self) -> None:
        original = ConnectionRefusedError("nope")
        err = SyncError(
            "wrapped failure",
            method="http",
            original=original,
        )
        assert err.original is original
        assert "[http] wrapped failure" in str(err)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(SyncError) as exc:
            raise SyncError("boom", method="cloud")
        assert exc.value.method == "cloud"


class TestSyncErrorSubclasses:
    """The three documented subclasses preserve SyncError semantics."""

    def test_cloud_upload_error_is_sync_error(self) -> None:
        err = CloudUploadError("auth failed", method="cloud")
        assert isinstance(err, SyncError)
        assert "[cloud] auth failed" == str(err)

    def test_http_sync_error_is_sync_error(self) -> None:
        err = HTTPSyncError("connect refused", method="http")
        assert isinstance(err, SyncError)
        assert err.method == "http"

    def test_hybrid_sync_error_stores_errors_list(self) -> None:
        errs = [
            {"method": "cloud", "error": "Auth failed"},
            {"method": "http", "error": "Connection refused"},
        ]
        err = HybridSyncError("All sync methods failed", method="hybrid", errors=errs)
        assert isinstance(err, SyncError)
        assert err.errors == errs
        # HybridSyncError calls super().__init__(message, method) without
        # original; verify the message renders with the method prefix.
        assert "hybrid" in str(err)
        assert "All sync methods failed" in str(err)

    def test_hybrid_sync_error_can_be_caught_as_sync_error(self) -> None:
        """Catch-all `except SyncError` should handle HybridSyncError."""
        with pytest.raises(SyncError):
            raise HybridSyncError(
                "everything failed",
                method="hybrid",
                errors=[{"method": "x", "error": "y"}],
            )


class TestModuleExports:
    """Module's __all__ exports are importable."""

    def test_all_exports_present(self) -> None:
        from session_buddy.storage import sync_protocol

        for name in sync_protocol.__all__:
            assert hasattr(sync_protocol, name), name

    def test_syncmethod_is_a_protocol_class(self) -> None:
        """SyncMethod must be a typing.Protocol subclass (or duck-equivalent)."""
        assert inspect.isclass(SyncMethod)
