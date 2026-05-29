"""Session information parsing and management.

This module provides utilities for reading, parsing, and managing session
information from handoff files and session summaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class SessionInfo:
    """Immutable session information."""

    session_id: str = field(default="")
    ended_at: str = field(default="")
    quality_score: str = field(default="")
    working_directory: str = field(default="")
    top_recommendation: str = field(default="")

    def is_complete(self) -> bool:
        """Check if session info has required fields."""
        return bool(self.ended_at and self.quality_score and self.working_directory)

    @classmethod
    def empty(cls) -> SessionInfo:
        """Create empty session info."""
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> SessionInfo:
        """Create from dictionary with validation."""
        return cls(
            session_id=data.get("session_id", ""),
            ended_at=data.get("ended_at", ""),
            quality_score=data.get("quality_score", ""),
            working_directory=data.get("working_directory", ""),
            top_recommendation=data.get("top_recommendation", ""),
        )


def find_latest_handoff_file(working_dir: Path) -> Path | None:
    """Find the most recent session handoff file."""
    try:
        handoff_dir = working_dir / ".crackerjack" / "session" / "handoff"

        if not handoff_dir.exists():
            # Check for legacy handoff files in project root
            legacy_files = list(working_dir.glob("session_handoff_*.md"))
            if legacy_files:
                # Return the most recent legacy file
                return max(legacy_files, key=lambda f: f.stat().st_mtime)
            return None

        # Find all handoff files
        handoff_files = list(handoff_dir.glob("session_handoff_*.md"))

        if not handoff_files:
            return None

        # Return the most recent file based on timestamp in filename
        return max(handoff_files, key=lambda f: f.name)

    except Exception:
        return None


def discover_session_files(working_dir: Path) -> list[Path]:
    """Find potential session files in priority order."""
    candidates = [
        working_dir / "session_handoff.md",
        working_dir / ".claude" / "session_handoff.md",
        working_dir / "session_summary.md",
    ]
    return [path for path in candidates if path.exists()]


async def read_file_safely(file_path: Path) -> str:
    """Read file content safely."""
    try:
        with file_path.open(encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def extract_session_metadata(lines: list[str]) -> dict[str, str]:
    """Extract session metadata from handoff file lines."""
    info = {}
    for line in lines:
        if line.startswith("**Session ended:**"):
            info["ended_at"] = line.split("**Session ended:**")[1].strip()
        elif line.startswith("**Final quality score:**"):
            info["quality_score"] = line.split("**Final quality score:**")[1].strip()
        elif line.startswith("**Working directory:**"):
            info["working_directory"] = line.split("**Working directory:**")[1].strip()
    return info


def extract_session_recommendations(lines: list[str], info: dict[str, str]) -> None:
    """Extract first recommendation from recommendations section."""
    in_recommendations = False
    for line in lines:
        if "## Recommendations for Next Session" in line:
            in_recommendations = True
            continue
        if in_recommendations and line.strip().startswith("1."):
            info["top_recommendation"] = line.strip()[3:].strip()  # Remove "1. "
            break
        if in_recommendations and line.startswith("##"):
            break  # End of recommendations section


async def parse_session_file(file_path: Path) -> SessionInfo:
    """Parse single session file with error handling."""
    try:
        content = await read_file_safely(file_path)
        if not content:
            return SessionInfo.empty()

        lines = content.split("\n")
        info_dict = extract_session_metadata(lines)
        extract_session_recommendations(lines, info_dict)

        return SessionInfo.from_dict(info_dict)

    except Exception:
        return SessionInfo.empty()


async def read_previous_session_info(handoff_file: Path) -> dict[str, str] | None:
    """Read previous session information."""
    try:
        # Use the async parsing method
        session_info = await parse_session_file(handoff_file)

        if session_info.is_complete():
            return {
                "ended_at": session_info.ended_at,
                "quality_score": session_info.quality_score,
                "working_directory": session_info.working_directory,
                "top_recommendation": session_info.top_recommendation,
            }

        return None

    except Exception:
        return None
