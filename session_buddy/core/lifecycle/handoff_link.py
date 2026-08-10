"""Read-side consumer: render the 'Cross-Repo Work' section of the handoff doc.

Public surface is the staticmethod render_section, which keeps the read path
testable without instantiating a CheckpointCrossRepoAccountant.
"""
from __future__ import annotations

import html
from collections.abc import Iterable

from oneiric.core.logging import get_logger

from session_buddy.memory.cross_repo_work import CrossRepoWorkRowRead

_log = get_logger(__name__)

_MAX_SHAS_PER_REPO = 5


class HandoffLink:
    """Renders the Cross-Repo Work markdown section for the handoff doc."""

    @staticmethod
    def render_section(
        conversation_id: str,
        rows: Iterable[CrossRepoWorkRowRead],
    ) -> str:
        rows_list = list(rows)
        try:
            return HandoffLink._render_inner(conversation_id, rows_list)
        except Exception as exc:  # noqa: BLE001 - sentinel path, never raise
            _log.exception(
                "cross_repo_work_handoff_render_failed",
                extra={"conversation_id": conversation_id, "error": str(exc)},
            )
            return (
                "## Cross-Repo Work\n\n"
                "> Cross-Repo Work could not be captured: "
                f"{type(exc).__name__}. See logs for details.\n"
            )

    @staticmethod
    def _render_inner(
        conversation_id: str,
        rows: list[CrossRepoWorkRowRead],
    ) -> str:
        if not rows:
            return "## Cross-Repo Work\n\n_No cross-repo work captured._\n"

        lines: list[str] = ["## Cross-Repo Work", ""]
        rows_sorted = sorted(rows, key=lambda r: r.repo_name)
        for row in rows_sorted:
            commits = [e for e in row.work_entries if e.kind == "commit"]
            lines.append(
                f"- **{row.repo_name}** ({row.repo_role or 'unknown'}): "
                f"{len(commits)} commit(s) since "
                f"{row.session_window_start.isoformat()}"
            )
            for entry in commits[:_MAX_SHAS_PER_REPO]:
                sha_short = html.escape(entry.sha[:7])
                subject = html.escape(entry.subject or "(no subject)")
                lines.append(f"  - `{sha_short}` {subject}")
            omitted = len(commits) - _MAX_SHAS_PER_REPO
            if omitted > 0:
                lines.append(f"  - … and {omitted} more commit(s)")
        lines.append("")
        return "\n".join(lines)