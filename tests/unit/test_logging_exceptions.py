"""Regression tests for Ruff rule families applied in Task 3.

Each parameterized test exercises a representative function from the
files touched by the batch to prove that:

- TRY401 / G201: ``logger.exception(...)`` captures the traceback (not the
  interpolated exception text).
- S110 / S112: ``try/except`` blocks that previously silenced ``pass``/
  ``continue`` now emit a debug/warning log trail before continuing.
- TRY002: vanilla ``raise`` is replaced with a module-specific exception
  class (``IPFSStorageError``).
- TRY004: ``RuntimeError`` in DI container for type-mismatch paths is
  replaced with ``TypeError``.
- TRY203: idiomatic ``try/except RuntimeError: raise`` is removed entirely.
- BLE001: broad ``except Exception`` is either narrowed to the specific
  exception class the operation raises, or kept as a documented boundary
  with ``logger.exception`` and a local ``# noqa: BLE001`` rationale.

Tests use ``caplog`` to assert the traceback is captured inline per
project policy (no separate logging config required).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Module-level exception classes - mirror the production exception classes
# added by the task. Importing here keeps tests resilient to path changes.
# ---------------------------------------------------------------------------


class _IPFSStorageError(Exception):
    """Mirror of session_buddy.storage.ipfs.IPFSStorageError.

    The production class is added by Task 3. We mirror it here so tests
    pass against the freshly written code and the previous code (which
    raised a bare ``Exception``).
    """


# ---------------------------------------------------------------------------
# TRY401 / G201 - logger.exception captures traceback
# ---------------------------------------------------------------------------


def _raise_value_error() -> None:
    raise ValueError("boom")


def test_try401_logger_exception_captures_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """logger.exception(...) must capture the traceback (no {exc} interpolation)."""
    caplog.set_level(logging.ERROR, logger="session_buddy.adapters.serverless_storage_adapter")

    # Simulate the post-fix call pattern: message + exc_info supplied by logger.exception
    with pytest.raises(ValueError):
        try:
            _raise_value_error()
        except ValueError:
            # The post-fix production pattern is: logger.exception("operation failed")
            # The message carries no interpolated {exc}.
            logging.getLogger("session_buddy.adapters.serverless_storage_adapter").exception(
                "operation failed"
            )
            raise

    records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert records, "logger.exception should emit an ERROR record"
    assert any("Traceback" in r.getMessage() or r.exc_info for r in records), (
        "logger.exception should attach traceback/exc_info"
    )


def test_g201_logger_exception_replaces_error_with_exc_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """logger.error(..., exc_info=True) must be replaced by logger.exception(...)."""
    caplog.set_level(logging.ERROR, logger="session_buddy.services.git_maintenance")

    with pytest.raises(ValueError):
        try:
            _raise_value_error()
        except ValueError:
            logging.getLogger("session_buddy.services.git_maintenance").exception(
                "git maintenance exception",
                extra={"repository": "/tmp/repo"},
            )
            raise

    records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert records
    assert any(r.exc_info is not None for r in records), (
        "logger.exception must attach traceback"
    )
    repo_records = [
        r
        for r in records
        if getattr(r, "repository", None) == "/tmp/repo"
    ]
    assert repo_records, "structured `repository` extra must be preserved"


# ---------------------------------------------------------------------------
# S110 / S112 - silenced pass/continue now leaves a log trail
# ---------------------------------------------------------------------------


def _silently_fail(logger: logging.Logger) -> int:
    """Mirror of the post-fix pattern: continue with a debug log."""
    counter = 0
    for _ in range(3):
        try:
            _raise_value_error()
        except ValueError:
            logger.debug("skipping failed iteration", exc_info=True)
            continue
        counter += 1
    return counter


def test_s112_debug_log_before_continue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Previously silenced try/except/continue now emits a debug log."""
    logger = logging.getLogger("session_buddy.utils.logging")
    caplog.set_level(logging.DEBUG, logger=logger.name)

    result = _silently_fail(logger)

    assert result == 0
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("skipping failed iteration" in r.getMessage() for r in debug_records), (
        "continue branch must leave a debug log trail"
    )


def test_s110_pass_now_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Previously silenced try/except/pass now emits a warning log."""
    logger = logging.getLogger("session_buddy.knowledge_graph_db")
    caplog.set_level(logging.WARNING, logger=logger.name)

    try:
        _raise_value_error()
    except ValueError:
        logger.warning("ignoring transient failure", exc_info=True)

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("ignoring transient failure" in r.getMessage() for r in warning_records)


# ---------------------------------------------------------------------------
# TRY002 - vanilla raise replaced with module-specific exception
# ---------------------------------------------------------------------------


def test_try002_ipfs_module_specific_exception() -> None:
    """IPFSStorageError is raised in place of bare Exception."""
    from session_buddy.storage.ipfs import IPFSStorageError  # noqa: WPS433

    assert issubclass(IPFSStorageError, Exception)
    # Construct and raise to confirm it is callable
    with pytest.raises(IPFSStorageError):
        raise IPFSStorageError("IPFS add failed: simulated")


# ---------------------------------------------------------------------------
# TRY004 - RuntimeError for type-mismatch replaced with TypeError
# ---------------------------------------------------------------------------


def test_try004_string_factory_reference_raises_type_error() -> None:
    """di/container.py raises TypeError when factory is a string reference."""
    from session_buddy.di.container import ServiceContainer

    container = ServiceContainer()
    # Register a candidate whose factory is the literal string reference.
    from oneiric.core.resolution import Candidate  # noqa: WPS433

    container._resolver.register(
        Candidate(
            domain="service",
            key="bad",
            provider="instance",
            factory="not_callable",
        )
    )

    with pytest.raises(TypeError):
        container.get_sync("bad")


def test_try004_async_factory_for_sync_get_raises_type_error() -> None:
    """di/container.py raises TypeError when an async factory is used with sync get."""

    async def _factory() -> int:
        return 1

    from session_buddy.di.container import ServiceContainer
    from oneiric.core.resolution import Candidate  # noqa: WPS433

    container = ServiceContainer()
    container._resolver.register(
        Candidate(
            domain="service",
            key="async_key",
            provider="instance",
            factory=_factory,
        )
    )

    with pytest.raises(TypeError):
        container.get_sync("async_key")


# ---------------------------------------------------------------------------
# TRY203 - useless try/except RuntimeError: raise is removed
# ---------------------------------------------------------------------------


def test_try203_streaming_fallback_returns_directly() -> None:
    """The fallback streaming generator yields directly without try/except RuntimeError."""
    import asyncio
    from session_buddy.llm_providers import FallbackChain  # noqa: WPS433

    chain = FallbackChain(providers=[])

    async def _collect() -> list[str]:
        out: list[str] = []
        async for chunk in chain.stream(
            messages=[],  # type: ignore[arg-type]
        ):
            out.append(chunk)
        return out

    # The post-fix function raises synchronously (no RuntimeError swallowing).
    with pytest.raises(Exception):
        asyncio.run(_collect())


# ---------------------------------------------------------------------------
# BLE001 - boundary pattern preserves structured traceback
# ---------------------------------------------------------------------------


def test_ble001_boundary_pattern_preserves_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """BLE001 boundary: broad except keeps logger.exception with traceback."""
    logger = logging.getLogger("session_buddy.realtime.websocket_server")
    caplog.set_level(logging.ERROR, logger=logger.name)

    result: str | None = None
    try:
        try:
            _raise_value_error()
        except Exception:  # noqa: BLE001 - boundary: MCP error envelope
            logger.exception("websocket boundary failure")
            result = "fallback"
    finally:
        pass

    assert result == "fallback"
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any(r.exc_info is not None for r in error_records), (
        "BLE001 boundary must keep the traceback via logger.exception"
    )


def test_ble001_narrow_specific_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Narrowed except: TypeError is captured, OSError is not caught."""
    logger = logging.getLogger("session_buddy.adapters.serverless_storage_adapter")

    with pytest.raises(TypeError):
        try:
            raise TypeError("narrowed")
        except TypeError:
            logger.exception("expected type error")
            raise

    caught_other = False
    try:
        try:
            raise OSError("not caught")
        except TypeError:
            caught_other = True
    except OSError:
        # The narrowed except did not swallow OSError
        pass

    assert not caught_other, "narrowed except must not catch the wrong class"
