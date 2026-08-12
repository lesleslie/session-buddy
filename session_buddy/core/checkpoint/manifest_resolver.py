"""Centralized manifest-path resolution. Eliminates the duplicate
ECOSYSTEM_MANIFEST env-var pattern that previously appeared in both
AmbientPuller and store_cross_repo_work (python-pro M1 / mcp I5).
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_RELATIVE_PATH = Path("settings/ecosystem.yaml")


def resolve_manifest_path(explicit: Path | None = None) -> Path:
    """Return explicit arg if given; else ECOSYSTEM_MANIFEST env var;
    else settings/ecosystem.yaml relative to cwd. Single source of truth."""
    if explicit is not None:
        return explicit
    env = os.environ.get("ECOSYSTEM_MANIFEST")
    if env:
        return Path(env)
    return DEFAULT_RELATIVE_PATH
