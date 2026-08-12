"""Decide whether a checkpoint should fire given current state.

Per spec: midpoint fires when it adds value AND no subagent is active.
End-of-task always fires (after subagent commit if applicable). Hook
request always fires (user explicit override).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from oneiric.core.logging import get_logger

from session_buddy.checkpoint.scrubbing import safe_transient_info
from session_buddy.checkpoint.subagent_detector import SubagentDetector

_log = get_logger(__name__)


class CheckpointPhase(StrEnum):
    END_OF_TASK = "end_of_task"
    MIDPOINT_TIME = "midpoint_time"
    MIDPOINT_DIRTINESS = "midpoint_dirtiness"
    HOOK_REQUESTED = "hook_requested"


@dataclass
class PolicyDecision:
    should_fire: bool
    reason: str


class WorkingTreeInspector:
    def __init__(self, working_dir: Path) -> None:
        self._working_dir = working_dir

    def is_git_repo(self) -> bool:
        if not self._working_dir.exists():
            return False
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self._working_dir,
            capture_output=True,
            check=False,
            timeout=5.0,
        )
        return result.returncode == 0

    def seconds_since_last_commit(self) -> float:
        if not self.is_git_repo():
            return 0.0
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI"],
            cwd=self._working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return 0.0
        try:
            last = datetime.fromisoformat(result.stdout.strip())
        except ValueError:
            return 0.0
        return max(0.0, (datetime.now(UTC) - last).total_seconds())

    def dirty_file_count(self) -> int:
        if not self.is_git_repo():
            return 0
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self._working_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if result.returncode != 0:
            return 0
        return sum(1 for line in result.stdout.splitlines() if len(line) >= 4)


class ValueAddSignal(Protocol):
    def is_active(self, working_tree: WorkingTreeInspector) -> bool: ...
    def describe(self) -> str: ...


@dataclass
class TimeElapsedSignal:
    min_seconds: float = 300.0

    def is_active(self, working_tree: WorkingTreeInspector) -> bool:
        return working_tree.seconds_since_last_commit() >= self.min_seconds

    def describe(self) -> str:
        return f"{self.min_seconds:.0f}s since last commit"


@dataclass
class DirtyFilesSignal:
    min_count: int = 5

    def is_active(self, working_tree: WorkingTreeInspector) -> bool:
        return working_tree.dirty_file_count() >= self.min_count

    def describe(self) -> str:
        return f"{self.min_count}+ dirty files"


@dataclass
class MidpointCriteria:
    signals: list[ValueAddSignal] = field(
        default_factory=lambda: [
            TimeElapsedSignal(min_seconds=300.0),
            DirtyFilesSignal(min_count=5),
        ]
    )


class CheckpointPolicy:
    def __init__(
        self,
        *,
        always_end: bool = True,
        midpoint_enabled: bool = True,
        midpoint_criteria: MidpointCriteria,
        subagent_detector: SubagentDetector,
        working_tree: WorkingTreeInspector,
    ) -> None:
        self._always_end = always_end
        self._midpoint_enabled = midpoint_enabled
        self._criteria = midpoint_criteria
        self._detector = subagent_detector
        self._working_tree = working_tree

    def decide(
        self, *, phase: CheckpointPhase, hook_request: bool = False
    ) -> PolicyDecision:
        if phase == CheckpointPhase.END_OF_TASK:
            if self._always_end:
                return PolicyDecision(should_fire=True, reason="end_of_task mandatory")
            return PolicyDecision(should_fire=False, reason="end_of_task disabled")

        if hook_request or phase == CheckpointPhase.HOOK_REQUESTED:
            return PolicyDecision(
                should_fire=True, reason="hook_requested explicit override"
            )

        if not self._midpoint_enabled:
            return PolicyDecision(should_fire=False, reason="midpoint disabled")

        if self._detector.is_active():
            return PolicyDecision(
                should_fire=False,
                reason="subagent active — deferring midpoint",
            )

        for signal in self._criteria.signals:
            try:
                if signal.is_active(self._working_tree):
                    return PolicyDecision(
                        should_fire=True,
                        reason=f"signal active: {signal.describe()}",
                    )
            except Exception as exc:  # noqa: BLE001 — per-signal fail-closed per spec
                _log.error(  # ERROR not WARNING per integration-risk L4
                    "policy_signal_evaluation_failed",
                    extra={"signal": signal.describe()} | safe_transient_info(exc),
                )

        return PolicyDecision(should_fire=False, reason="no midpoint signals active")
