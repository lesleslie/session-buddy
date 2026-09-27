"""CI guard: keep version stamps in lockstep with pyproject.toml.

Mirrors ``akosha/tests/unit/test_version_sync.py`` (commit 3203ea2).
Replaces the hardcoded literal ``__version__ = "0.25.7"`` path with
the runtime single-source-of-truth contract enforced via
:func:`importlib.metadata.version`.
"""

from __future__ import annotations

import importlib.util
import re
from importlib import metadata
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Sentinel used when ``importlib.metadata.version`` raises
# ``PackageNotFoundError`` (PEP 440 local-version label).
_FALLBACK_VERSION = "0+unknown"


def _read_pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        pytest.fail("pyproject.toml does not contain a version field")
    return match.group(1)


def test_pyproject_version_is_canonical() -> None:
    version = _read_pyproject_version()
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), (
        f"pyproject version {version!r} is not a valid PEP 440 stamp"
    )


def test_runtime_equals_metadata_version() -> None:
    """``session_buddy.__version__`` must equal ``metadata.version('session-buddy')``."""
    import session_buddy

    assert session_buddy.__version__ == metadata.version("session-buddy"), (
        f"session_buddy.__version__={session_buddy.__version__!r} "
        f"diverged from installed metadata "
        f"{metadata.version('session-buddy')!r}"
    )


def test_version_fallback_when_metadata_unavailable() -> None:
    """``PackageNotFoundError`` falls back to the PEP 440 sentinel."""
    spec = importlib.util.spec_from_file_location(
        "session_buddy_fallback_probe",
        ROOT / "session_buddy" / "__init__.py",
    )
    assert spec is not None
    fresh = importlib.util.module_from_spec(spec)

    with patch("importlib.metadata.version", side_effect=metadata.PackageNotFoundError):
        spec.loader.exec_module(fresh)  # type: ignore[union-attr]

    assert fresh.__version__ == _FALLBACK_VERSION, (
        f"Fallback returned {fresh.__version__!r}; expected sentinel "
        f"{_FALLBACK_VERSION!r} when metadata is unavailable"
    )


def test_no_hardcoded_version_literals() -> None:
    """Regression: no hardcoded ``X.Y.Z`` version stamps in package code."""
    package_root = ROOT / "session_buddy"
    offenders: list[tuple[str, str]] = []
    literal_pattern = re.compile(
        r"""(?:__version__|APP_VERSION|SERVICE_VERSION)\s*[:=]\s*["']"""
        r"""(\d+\.\d+(?:\.\d+)?)["']"""
    )
    for py_file in sorted(package_root.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        text = py_file.read_text(encoding="utf-8")
        for match in literal_pattern.finditer(text):
            offenders.append((str(py_file.relative_to(ROOT)), match.group(1)))
    assert not offenders, (
        f"Hardcoded version literals re-introduced drift: {offenders}"
    )
