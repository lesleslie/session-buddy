#!/usr/bin/env python3
"""Test suite for session_buddy.__main__ entry-point.

The module itself is tiny — just a thin wrapper that imports the CLI
factory and invokes ``cli.main()``. The tests here pin three contracts:

1. ``main()`` is callable as the ``python -m session_buddy`` entry-point.
2. ``main()`` delegates to ``session_buddy.cli.main`` (NOT to ``SessionBuddyCLI`` directly).
3. ``__main__.py`` exposes the public ``main`` symbol.

We avoid ``importlib.util.spec_from_file_location`` (see wave-N memory notes
on coverage-tracking breaks) — pytest-cov can only observe lines that
the regular import machinery touches, so we rely on the package import.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_module_exposes_main_callable() -> None:
    """The entry-point module exports a ``main`` callable.

    Mirrors the runtime contract: ``python -m session_buddy`` resolves
    to ``session_buddy.__main__.main()``.
    """
    import session_buddy.__main__ as sb_main

    assert hasattr(sb_main, "main"), "__main__ must export a main() function"
    assert callable(sb_main.main)


def test_main_delegates_to_cli_main() -> None:
    """main() must invoke session_buddy.cli.main exactly once.

    ``__main__.py`` is a thin shim; its only job is to defer to the CLI
    factory's ``main`` so the Typer app dispatches. We assert the
    delegation target so a future refactor that bypasses the CLI (and
    drops sub-command wiring) is caught here.
    """
    import session_buddy.__main__ as sb_main

    with patch("session_buddy.cli.main") as mocked_cli_main:
        sb_main.main()

    mocked_cli_main.assert_called_once_with()


def test_main_returns_none() -> None:
    """main() returns None on success.

    The shim does not collect a return value from the CLI runner —
    ``session_buddy.cli.main`` is also ``-> None``. Pin the contract so
    callers that rely on ``main()`` having no return value keep working.
    """
    import session_buddy.__main__ as sb_main

    with patch("session_buddy.cli.main"):
        result = sb_main.main()

    assert result is None


def test_main_propagates_cli_exceptions() -> None:
    """Errors raised by the CLI surface through main().

    ``__main__`` must not swallow exceptions — Typer/Click exit codes
    and tracebacks should reach the operator as-is. We assert the
    exception passes through unmodified.
    """
    import session_buddy.__main__ as sb_main

    class _BoomError(RuntimeError):
        pass

    with patch(
        "session_buddy.cli.main",
        side_effect=_BoomError("synthetic CLI failure"),
    ):
        with pytest.raises(_BoomError, match="synthetic CLI failure"):
            sb_main.main()


def test_main_invokes_cli_main_via_attribute_path() -> None:
    """The CLI delegation uses the lazy import inside main(), not module-level.

    Pinning the import target string so a refactor that switches to
    ``from session_buddy.cli import main as cli_main`` at module scope
    is intentional and observable — we patch the string the function
    uses internally.
    """
    import session_buddy.__main__ as sb_main

    with patch("session_buddy.cli.main") as mocked_cli_main:
        sb_main.main()

    # Second call still hits the (mocked) cli.main — not a cached binding.
    with patch("session_buddy.cli.main") as mocked_cli_main_2:
        sb_main.main()

    assert mocked_cli_main.called
    assert mocked_cli_main_2.called


def test_dunder_name_guard_present() -> None:
    """The ``if __name__ == '__main__'`` guard exists at module bottom.

    This block is the runtime entry-point for ``python -m session_buddy``.
    Importing the module does NOT execute it (pytest-cov measures the
    line, but the conditional body is skipped). We assert the guard
    exists so a future "tidy-up" PR does not delete it.
    """
    import session_buddy.__main__ as sb_main

    source = open(sb_main.__file__).read()
    assert 'if __name__ == "__main__":' in source, (
        "__main__.py must keep its __main__-guard so `python -m session_buddy` works"
    )
