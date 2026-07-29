from __future__ import annotations

from pathlib import Path
from typing import Any


def build_file_context(file_path: str, max_lines: int = 50) -> dict[str, Any]:
    """Build lightweight file context for extraction triggers.

    Returns metadata and a snippet (first N lines) for significance scoring.
    """
    p = Path(file_path)
    meta = {
        "file_path": str(p),
        "file_name": p.name,
        "file_extension": p.suffix,
        "size": p.stat().st_size if p.exists() else 0,
    }

    snippet = ""
    try:
        if p.exists() and p.is_file():
            with p.open("r", encoding="utf-8", errors="ignore") as f:
                lines: list[str] = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line.rstrip("\n"))
            snippet = "\n".join(lines)
    except (OSError, UnicodeDecodeError, ValueError):
        snippet = ""

    return {"metadata": meta, "snippet": snippet}
