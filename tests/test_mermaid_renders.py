"""Wave-11 CI guard: every fenced mermaid block in this repo must parse.

Wraps `session_buddy.tools.mermaid_validator.renderer.find_broken_mermaid_blocks`,
which uses `mermaid.parse()` via Node.js (no chrome dependency). Mirrors
the ratchet pattern established by the crackerjack wave-9 guard.

If this test fails, run
`python -c "import importlib.util as u; m=u.spec_from_file_location('r','session_buddy/tools/mermaid_validator/renderer.py'); r=u.module_from_spec(m); m.loader.exec_module(r); [print(e) for e in r.find_broken_mermaid_blocks()]"`
to see the broken blocks directly.

Note: We load `renderer.py` via importlib rather than `from session_buddy.tools
import renderer` because `session_buddy/tools/__init__.py` is a heavy MCP
backward-compat shim that imports all MCP tool modules. Loading the file
directly keeps the test fast and avoids dragging the full MCP stack into
this lightweight validator.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load renderer.py directly to bypass session_buddy/tools/__init__.py.
_RENDERER_PATH = REPO_ROOT / "session_buddy" / "tools" / "mermaid_validator" / "renderer.py"
_spec = importlib.util.spec_from_file_location(
    "session_buddy.tools.mermaid_validator.renderer",
    _RENDERER_PATH,
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"could not load spec for {_RENDERER_PATH}")
_renderer = importlib.util.module_from_spec(_spec)
sys.modules["session_buddy.tools.mermaid_validator.renderer"] = _renderer
sys.modules["session_buddy.tools.mermaid_validator"] = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "session_buddy.tools.mermaid_validator",
        REPO_ROOT / "session_buddy" / "tools" / "mermaid_validator" / "__init__.py",
    )
) if (REPO_ROOT / "session_buddy" / "tools" / "mermaid_validator" / "__init__.py").exists() else importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "session_buddy.tools.mermaid_validator",
        REPO_ROOT / "session_buddy" / "tools" / "mermaid_validator",
    )
)
_spec.loader.exec_module(_renderer)

extract_mermaid_blocks = _renderer.extract_mermaid_blocks
find_broken_mermaid_blocks = _renderer.find_broken_mermaid_blocks


def test_all_mermaid_blocks_parse() -> None:
    """Every fenced ```mermaid block in the repo must parse via mermaid.parse()."""
    try:
        errors = find_broken_mermaid_blocks(root=REPO_ROOT)
    except RuntimeError as exc:
        # If the validator itself fails (e.g., node missing), surface that
        # rather than silently passing.
        pytest.fail(f"mermaid validator unavailable: {exc}")
    if errors:
        formatted = "\n".join(f"  {e.relpath}:{e.line}  {e.error}" for e in errors)
        pytest.fail(f"{len(errors)} broken mermaid block(s):\n{formatted}")


def test_extract_mermaid_blocks_finds_expected_count() -> None:
    """Sanity check: the extractor should find at least one block in the repo.

    If this fails, the extractor is silently broken (e.g., regex changed).
    """
    skip_dirs = {
        ".venv", "venv", "env", ".git", "node_modules", "dist", "build",
        ".egg-info", ".pytest_cache", ".ruff_cache", ".mypy_cache",
        ".worktrees", ".claude",
    }
    markdown_files = [
        p for p in REPO_ROOT.rglob("*.md")
        if not any(part in skip_dirs for part in p.parts)
    ]
    blocks: list = []
    for md_file in markdown_files:
        blocks.extend(extract_mermaid_blocks(md_file))
    assert len(blocks) >= 1, (
        f"expected at least one mermaid block across {len(markdown_files)} markdown files"
    )