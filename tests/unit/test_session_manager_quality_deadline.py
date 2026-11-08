#!/usr/bin/env python3
"""Tests for the quality-assessment deadline guard.

The end tool's deliverable is the handoff file, and it is written AFTER
the quality assessment. The assessment shells out to crackerjack
(``run --comp --skip-hooks``, ~25s measured) plus git, security and type
scans; on a cold metrics cache the whole ``end`` call measured ~54s.
That is close enough to the MCP client's request timeout that a
transient stall turned the call into a timeout -- and a timed-out client
disconnects, which cancels the server-side handler, so the handoff was
never written at all.

These tests pin the guard: a slow assessment must cost the SCORE, never
the ARTIFACT.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from session_buddy.core import session_manager as session_manager_module
from session_buddy.core.session_manager import SessionLifecycleManager


async def _slow_assessment(*args, **kwargs) -> tuple[int, dict]:
    """Stand in for an assessment that overruns the deadline."""
    await asyncio.sleep(5)
    return 99, {"total_score": 99, "recommendations": [], "breakdown": {}}


@pytest.mark.asyncio
class TestQualityAssessmentDeadline:
    """The assessment must never block its caller past the deadline."""

    async def test_fast_assessment_passes_through_untouched(self):
        """A quick assessment returns its real score and data."""
        manager = SessionLifecycleManager()
        manager.perform_quality_assessment = AsyncMock(
            return_value=(88, {"total_score": 88}),
        )

        score, data = await manager._quality_assessment_with_deadline(Path("/tmp"))

        assert score == 88
        assert data["total_score"] == 88

    async def test_slow_assessment_degrades_instead_of_raising(self):
        """An overrunning assessment yields a degraded score, not an error."""
        manager = SessionLifecycleManager()
        manager.perform_quality_assessment = _slow_assessment

        with patch.object(session_manager_module, "_QUALITY_ASSESSMENT_DEADLINE_S", 0.05):
            score, data = await manager._quality_assessment_with_deadline(Path("/tmp"))

        assert score == 75
        assert data["total_score"] == 75

    async def test_degraded_result_keeps_the_handoff_writer_shape(self):
        """The handoff writer reads these keys with ``.get()`` -- they must exist."""
        manager = SessionLifecycleManager()
        manager.perform_quality_assessment = _slow_assessment

        with patch.object(session_manager_module, "_QUALITY_ASSESSMENT_DEADLINE_S", 0.05):
            _, data = await manager._quality_assessment_with_deadline(Path("/tmp"))

        assert isinstance(data.get("recommendations"), list)
        assert isinstance(data.get("breakdown"), dict)

    async def test_end_session_still_writes_the_handoff_when_slow(self):
        """The regression this guard exists for: a slow score must not
        cost the handoff file."""
        manager = SessionLifecycleManager()
        manager.perform_quality_assessment = _slow_assessment

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("os.getcwd", return_value=temp_dir),
                patch.object(
                    session_manager_module, "_QUALITY_ASSESSMENT_DEADLINE_S", 0.05
                ),
            ):
                result = await manager.end_session(working_directory=temp_dir)

            assert result["success"] is True

            handoff_dir = Path(temp_dir) / ".claude" / "handoff"
            handoff_files = list(handoff_dir.glob("session_handoff_*.md"))
            assert handoff_files, "the handoff file must exist even when the assessment is slow"
