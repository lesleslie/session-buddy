"""XDG Base Directory resolution for Session-Buddy runtime data.

Session-Buddy's runtime data used to live under ``~/.claude/data`` — a
Claude-Code-specific directory. Storing state there asserts that Claude
Code owns the data, which is wrong: Session-Buddy is harness-agnostic and
runs under any MCP client. This module resolves the XDG Base Directory
locations instead so the data owner is always Session-Buddy itself.

Layout:

* ``~/.local/share/session-buddy`` — persistent data (databases, indexes)
* ``~/.local/state/session-buddy`` — state (logs, sync state, locks)
* ``~/.cache/session-buddy`` — regenerable caches
* ``~/.config/session-buddy`` — settings

Each repository carries its own copy of this module. session-buddy,
crackerjack and mahavishnu are released (non-editable) installs of one
another, so a cross-repo import would need a publish first; a ~40-line
module duplicated per repo is the accepted cost of not gating this change
on a release.

Resolution rules:

* Each root honours its XDG environment variable (``XDG_DATA_HOME`` and
  friends) and falls back to the XDG spec default relative to the home
  directory.
* ``os.environ.get`` / ``os.path.expanduser`` are used rather than
  ``Path.home()`` so tests can override ``HOME`` and the XDG variables.
* Nothing is created on disk: these functions are pure path resolution
  with no import-time side effects.

"""

from __future__ import annotations

import os
from pathlib import Path

#: The data owner. Never the consuming repository's own app name.
APP_NAME = "session-buddy"

#: XDG spec defaults, relative to the home directory.
DATA_FALLBACK = ".local/share"
STATE_FALLBACK = ".local/state"
CACHE_FALLBACK = ".cache"
CONFIG_FALLBACK = ".config"


def _xdg_root(env_var: str, fallback: str) -> Path:
    """Resolve one XDG base directory root.

    Args:
        env_var: Environment variable that overrides the root.
        fallback: Root relative to the home directory, per the XDG spec.

    Returns:
        The resolved root directory. It is never created on disk.

    """
    raw = os.environ.get(env_var)
    if raw:
        return Path(os.path.expanduser(raw))
    return Path(os.path.expanduser("~")) / fallback


def data_dir(app: str = APP_NAME) -> Path:
    """Return the persistent-data directory for ``app``.

    Example:
        >>> data_dir()  # doctest: +SKIP
        PosixPath('/home/user/.local/share/session-buddy')

    """
    return _xdg_root("XDG_DATA_HOME", DATA_FALLBACK) / app


def state_dir(app: str = APP_NAME) -> Path:
    """Return the state directory for ``app``.

    Example:
        >>> state_dir()  # doctest: +SKIP
        PosixPath('/home/user/.local/state/session-buddy')

    """
    return _xdg_root("XDG_STATE_HOME", STATE_FALLBACK) / app


def cache_dir(app: str = APP_NAME) -> Path:
    """Return the regenerable-cache directory for ``app``.

    Example:
        >>> cache_dir()  # doctest: +SKIP
        PosixPath('/home/user/.cache/session-buddy')

    """
    return _xdg_root("XDG_CACHE_HOME", CACHE_FALLBACK) / app


def config_dir(app: str = APP_NAME) -> Path:
    """Return the settings directory for ``app``.

    Example:
        >>> config_dir()  # doctest: +SKIP
        PosixPath('/home/user/.config/session-buddy')

    """
    return _xdg_root("XDG_CONFIG_HOME", CONFIG_FALLBACK) / app


def data_dir_under(home: Path, app: str = APP_NAME) -> Path:
    """Return the persistent-data directory for ``app`` beneath ``home``.

    Used when a caller needs an isolated tree (tests, the DI fallback that
    relocates everything under a temporary directory). The XDG environment
    variables are deliberately ignored here: an explicit home wins so the
    tree stays self-contained.

    Args:
        home: Home directory to anchor the XDG layout beneath.
        app: Data owner directory name.

    Returns:
        The resolved directory. It is never created on disk.

    """
    return home / DATA_FALLBACK / app


def state_dir_under(home: Path, app: str = APP_NAME) -> Path:
    """Return the state directory for ``app`` beneath ``home``.

    Args:
        home: Home directory to anchor the XDG layout beneath.
        app: Data owner directory name.

    Returns:
        The resolved directory. It is never created on disk.

    """
    return home / STATE_FALLBACK / app


__all__ = [
    "APP_NAME",
    "CACHE_FALLBACK",
    "CONFIG_FALLBACK",
    "DATA_FALLBACK",
    "STATE_FALLBACK",
    "cache_dir",
    "config_dir",
    "data_dir",
    "data_dir_under",
    "state_dir",
    "state_dir_under",
]
