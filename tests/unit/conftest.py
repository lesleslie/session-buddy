"""Unit test conftest that unmocks settings.

This ensures tests in tests/unit/ get real SessionMgmtSettings
instead of the mocked version from tests/conftest.py.
"""

from __future__ import annotations

import hashlib

from unittest.mock import patch, Mock, MagicMock
import pytest


def _deterministic_embedding(text: str) -> list[float]:
    """Generate a deterministic 384-dim vector from text.

    The vector combines whole-word and 3-character n-gram features so
    that:
    - Identical inputs produce identical vectors
    - Texts that share whole words (e.g. "database") AND share character
      n-grams (e.g. "async" and "async/await" both contain "asy",
      "syn", "ync") have high cosine similarity
    - Texts that share nothing have low similarity

    Properties:
    - Deterministic: same input always produces the same vector
    - Bags-of-features so shared words/n-grams lift similarity
    - 384 dimensions, roughly half-positive half-negative
    """
    import re

    # Normalize: lowercase, strip non-alphanumeric
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if not normalized:
        return [0.0] * 384

    from collections import Counter
    # Combine whole words + 3-char n-grams
    tokens = normalized.split()
    features: list[str] = []
    for token in tokens:
        features.append(f"w:{token}")
        for i in range(len(token) - 2):
            features.append(f"n:{token[i:i+3]}")
    feature_counts = Counter(features)

    vec = [0.0] * 384
    for feat, count in feature_counts.items():
        digest = hashlib.sha256(feat.encode("utf-8")).digest()  # 32 bytes
        for i in range(8):
            offset = (digest[i % 32] + i) % 384
            sign = 1.0 if digest[(i + 16) % 32] % 2 == 0 else -1.0
            vec[offset] += sign * float(count)
    return vec


@pytest.fixture(autouse=True)
def _stub_embedding_provider(monkeypatch: pytest.MonkeyPatch):
    """Auto-stub the HTTP embedding providers so unit tests don't need a live service.

    Tests that need to assert the "no providers" path can simply clear the
    monkeypatch.setattr themselves inside the test (or pass
    ``clear_embedding_provider=True`` — currently unimplemented, this
    fixture provides a default-success path).

    Tests that need a *specific* embedding (e.g. an empty list, or an
    exception) can re-monkeypatch `_try_http_embedding_providers` inside
    their own test; the inner ``monkeypatch.setattr`` takes precedence
    and is reverted on teardown.

    The module-level embedding cache is cleared before and after the test
    so cache state from one test does not bleed into another.
    """
    from session_buddy.reflection import embeddings as embeddings_module
    from session_buddy.reflection.embeddings import clear_embedding_cache

    async def fake_try(text: str) -> list[float]:
        return _deterministic_embedding(text)

    # Only stub if the test isn't already monkeypatching it
    if not isinstance(
        getattr(embeddings_module, "_try_http_embedding_providers", None),
        (MagicMock,),
    ):
        monkeypatch.setattr(
            embeddings_module, "_try_http_embedding_providers", fake_try
        )
    clear_embedding_cache()
    yield
    clear_embedding_cache()


@pytest.fixture(autouse=True)
def unmock_settings():
    """Undo the mock_settings patch from tests/conftest.py BEFORE test runs.

    The root conftest.py has an autouse=True mock_settings fixture that
    patches SessionMgmtSettings at module level. We need to restore
    the real class so that unit tests can test actual settings behavior.
    """
    import sys

    settings_module = sys.modules.get("session_buddy.settings")
    if settings_module is None:
        yield
        return

    # Get the real SessionMgmtSettings from the settings module itself
    real_class = settings_module.SessionMgmtSettings

    # Check if it's been mocked (look for Mock attributes)
    is_mock = isinstance(real_class, (Mock, MagicMock))

    if is_mock:
        # Need to import and restore the real class
        import importlib

        # Reload the existing module so the mocked attribute is replaced with
        # the real class without forcing a second NumPy extension import.
        FreshModule = importlib.reload(settings_module)
        FreshClass = FreshModule.SessionMgmtSettings
        settings_module.SessionMgmtSettings = FreshClass
        settings_module._settings = None

    yield

    # No cleanup needed - each test gets fresh import via cache clearing


@pytest.fixture
def real_settings(tmp_path):
    """Provide real SessionMgmtSettings instance for testing.

    Uses tmp_path to provide unique data/log directories per test
    to avoid conflicts.
    """
    from pathlib import Path
    from session_buddy.settings import SessionMgmtSettings

    test_data_dir = tmp_path / "data"
    test_data_dir.mkdir(exist_ok=True)
    test_log_dir = tmp_path / "logs"
    test_log_dir.mkdir(exist_ok=True)

    return SessionMgmtSettings(
        data_dir=test_data_dir,
        log_dir=test_log_dir,
        database_path=test_data_dir / "test.duckdb",
        log_file_path=test_log_dir / "test.log",
    )


def pytest_pycollect_makemodule(module_path, parent):
    """Purge session_buddy / mcp_common stubs before each test module is imported.

    A safety net for test files that install their own stubs via
    ``sys.modules`` at module load time, leaving the stub in place
    when the next test file's import runs.
    """
    import sys
    # Inline the purge logic (don't import from tests.conftest to avoid
    # sys.modules side effects during conftest collection).
    for name in list(sys.modules):
        if (
            name != "session_buddy"
            and not name.startswith("session_buddy.")
            and not name.startswith("mcp_common")
        ):
            continue
        module = sys.modules.get(name)
        if module is None:
            continue
        module_file = getattr(module, "__file__", None)
        module_path_attr = getattr(module, "__path__", None)
        # Use length-based check for __path__ to avoid the KeyError that
        # _NamespacePath.__eq__ can raise on namespace packages.
        is_empty_path = False
        if module_path_attr is not None:
            try:
                is_empty_path = len(module_path_attr) == 0
            except (TypeError, KeyError):
                is_empty_path = False
        is_stub = module_file is None and (
            module_path_attr is None or is_empty_path
        )
        is_orphan = module_file is None and module_path_attr is None
        if is_stub or is_orphan:
            # Use pop() rather than del to be safe against a parallel
            # fixture teardown that may have already removed the entry
            # from sys.modules while we iterate.
            sys.modules.pop(name, None)
        # Also catch synthetic packages installed via
        # ``types.ModuleType(name); module.__path__ = [str(real_path)]``
        # (no ``__file__`` but with a real ``__path__``). These look
        # like legitimate packages to the heuristic above but are in
        # fact stubs. The trigger: ``__file__`` is None AND the
        # module is not a sub-module of a real package.
        elif module_file is None and not name.endswith(".conftest"):
            sys.modules.pop(name, None)

    # Defensive: re-import session_buddy.core from disk if it's missing
    # or is a stub (no __file__). This handles module-level stubs like
    # those installed by ``test_mcp_quality_scorer.py``'s
    # ``_ensure_package`` call, which leave ``session_buddy.core`` as a
    # fake module with ``__path__`` set but no real attributes.
    core = sys.modules.get("session_buddy.core")
    if core is None or getattr(core, "__file__", None) is None:
        sys.modules.pop("session_buddy.core", None)
        try:
            import session_buddy.core  # noqa: F401
        except ImportError:
            pass

    _re_attach_runtime_snapshots_submodule()


# Submodules of ``session_buddy.utils`` that the conftest must
# re-attach as parent-package attributes before each test. Tests use
# string-form ``monkeypatch.setattr("session_buddy.utils.X.Y", ...)``;
# when a prior test (e.g. ``test_database_tools.py``) caused
# ``session_buddy.utils`` to be re-imported, the freshly imported
# package object has no ``X`` attribute and the monkeypatch call
# raises ``AttributeError``. These helpers do the re-attach with
# direct imports (no dynamic ``importlib.import_module``) to keep
# static-analysis warnings at bay.


def _re_attach_runtime_snapshots_submodule() -> None:
    """Re-attach ``runtime_snapshots`` as an attribute on the real parent.

    The conftest's autouse ``restore_session_buddy_modules`` fixture
    purges ``session_buddy.utils`` from ``sys.modules`` between tests
    when it appears to be a stub. After such a purge, the real
    ``session_buddy.utils`` package will be reloaded on the next
    access, but its ``__init__.py`` does not eagerly import the
    ``runtime_snapshots`` submodule (it is only used via lazy
    import inside functions). String-form ``monkeypatch.setattr(
    "session_buddy.utils.runtime_snapshots.X", ...)`` in the core
    snapshot tests then fails because ``session_buddy.utils`` has no
    ``runtime_snapshots`` attribute.

    This function forces the import of ``runtime_snapshots`` (and
    the rest of the ``session_buddy.utils`` package) so the parent
    attribute chain is intact for the duration of the test.
    """
    import sys  # noqa: PLC0415

    utils_pkg = sys.modules.get("session_buddy.utils")
    if utils_pkg is None:
        try:
            import session_buddy.utils  # noqa: PLC0415, F401
        except Exception:
            return
        utils_pkg = sys.modules.get("session_buddy.utils")

    if utils_pkg is None or hasattr(utils_pkg, "runtime_snapshots"):
        return

    try:
        import session_buddy.utils.runtime_snapshots  # noqa: PLC0415, F401
    except Exception:
        return

    rt_snapshots = sys.modules.get("session_buddy.utils.runtime_snapshots")
    if rt_snapshots is not None:
        utils_pkg.runtime_snapshots = rt_snapshots  # type: ignore[attr-defined]


def _re_attach_git_worktrees_submodule() -> None:
    """Re-attach ``git_worktrees`` as an attribute on ``session_buddy.utils``.

    Tests in :mod:`tests.unit.test_git_operations` use string-form
    ``monkeypatch.setattr("session_buddy.utils.git_worktrees.X", ...)`` to
    patch subprocess calls. When a prior test (notably
    ``test_database_tools.py``'s module-scoped ``_isolated_stubs`` fixture)
    caused ``session_buddy.utils`` to be re-imported, the freshly
    imported package object has no ``git_worktrees`` attribute and the
    monkeypatch call raises
    ``AttributeError: module 'session_buddy.utils' has no attribute 'git_worktrees'``.

    This function forces the import of ``git_worktrees`` so the parent
    attribute chain is intact for the duration of the test.
    """
    import sys  # noqa: PLC0415

    utils_pkg = sys.modules.get("session_buddy.utils")
    if utils_pkg is None:
        try:
            import session_buddy.utils  # noqa: PLC0415, F401
        except Exception:
            return
        utils_pkg = sys.modules.get("session_buddy.utils")

    if utils_pkg is None or hasattr(utils_pkg, "git_worktrees"):
        return

    try:
        import session_buddy.utils.git_worktrees  # noqa: PLC0415, F401
    except Exception:
        return

    git_worktrees = sys.modules.get("session_buddy.utils.git_worktrees")
    if git_worktrees is not None:
        utils_pkg.git_worktrees = git_worktrees  # type: ignore[attr-defined]


def pytest_runtest_setup(item):
    """Re-attach lazy submodules as parent-package attributes before each test.

    Belt-and-suspenders safety net: the ``pytest_pycollect_makemodule``
    hook above runs at collection time, but Python's import machinery
    can re-execute a parent package's ``__init__.py`` between
    collection and test execution (e.g. when a conftest fixture
    imports it or a previous test reloaded the package). This hook
    fires immediately before each test, so the lazily-imported
    submodules below are guaranteed present on the parent package for
    the duration of the test. Without this, string-form
    ``monkeypatch.setattr("session_buddy.utils.X.Y", ...)`` calls in
    tests like ``test_git_operations.py`` fail with
    ``AttributeError: module 'session_buddy.utils' has no attribute 'X'``
    when run after ``test_database_tools.py``.
    """
    _re_attach_runtime_snapshots_submodule()
    _re_attach_git_worktrees_submodule()
