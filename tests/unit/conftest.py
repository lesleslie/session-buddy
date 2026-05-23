"""Unit test conftest that unmocks settings.

This ensures tests in tests/unit/ get real SessionMgmtSettings
instead of the mocked version from tests/conftest.py.
"""

from __future__ import annotations

from unittest.mock import patch, Mock, MagicMock
import pytest


@pytest.fixture(autouse=True)
def unmock_settings():
    """Undo the mock_settings patch from tests/conftest.py BEFORE test runs.

    The root conftest.py has an autouse=True mock_settings fixture that
    patches SessionMgmtSettings at module level. We need to restore
    the real class so that unit tests can test actual settings behavior.
    """
    import session_buddy.settings as settings_module

    # Get the real SessionMgmtSettings from the settings module itself
    real_class = settings_module.SessionMgmtSettings

    # Check if it's been mocked (look for Mock attributes)
    is_mock = isinstance(real_class, (Mock, MagicMock))

    if is_mock:
        # Need to import and restore the real class
        # We import the real class directly from the module source
        import importlib
        import sys

        # Remove cached version of module if any
        if 'session_buddy.settings' in sys.modules:
            del sys.modules['session_buddy.settings']

        # Re-import to get fresh real class
        from session_buddy.settings import SessionMgmtSettings as FreshClass
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