"""
Conscious Agent - Background memory optimization inspired by Memori.

Analyzes conversation patterns to promote frequently-accessed memories
from long-term to short-term storage for faster retrieval.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import tempfile
import typing as t
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Lockfile used to elect a single Conscious Agent per host. The path is
# anchored at ``tempfile.gettempdir()`` so the lock is per-user, not
# per-filesystem, and survives worker restarts. The PID of the winning
# worker is written to the file so operators can ``cat`` it to diagnose
# which process owns the agent.
_CONSCIOUS_AGENT_LOCK_PATH = "session-buddy-conscious-agent.lock"

# In-process state. POSIX ``flock`` locks the *open file description*,
# not the inode — so a second ``open()`` of the same path from the
# same process gets a fresh file description and would acquire its
# own lock. To make the in-process case behave the same as the
# cross-process case (only one election per process), we cache the
# election result here. The cache is per-process so a multi-process
# host still gets one agent per host (the OS-level ``flock`` handles
# that).
_conscious_agent_lock_fd: t.Any = None
_conscious_agent_elected: bool = False


def _start_conscious_agent_with_lock(settings: Any) -> bool:
    """Try to start the background Conscious Agent, gated by a host-wide lock.

    Multiple Session-Buddy workers may run on the same host (a local
    dev server, a CLI invocation, a periodic cron, etc.). Only one of
    them should run the background analysis loop — otherwise the
    promotion logic thrashes. This function is the single entry point
    for "start the agent"; it elects one winner per host using a
    POSIX ``fcntl`` file lock and returns True to the winner, False
    to everyone else.

    Behavior:

    1. If ``settings.enable_conscious_agent`` is False, return False
       immediately. The background loop is off — the write path is
       still active (it is unconditional; see
       ``_log_access`` in ``reflection_adapter_oneiric.py``) so the
       analysis loop has data to chew on the day it is enabled.
    2. Acquire an exclusive, non-blocking ``fcntl`` lock on
       ``session-buddy-conscious-agent.lock`` in the temp directory.
       If the lock is held by another process, return False.
    3. Write the winning PID to the lockfile (best effort) and
       return True. The caller is expected to actually start the
       background task; this function only handles the election.

    Args:
        settings: An object with an ``enable_conscious_agent`` boolean
            attribute. ``SessionMgmtSettings`` works; ``SimpleNamespace``
            works for tests.

    Returns:
        True if this process should start the agent, False otherwise.
        The function never raises — election failures are logged and
        treated as "another worker has it".

    """
    # Short-circuit: feature flag off -> no agent, no lockfile, no work.
    if not getattr(settings, "enable_conscious_agent", False):
        return False

    # In-process election cache. POSIX ``flock`` locks the *open file
    # description* (per-process), not the inode, so a second ``open()``
    # of the same path from the same process would acquire a fresh
    # lock and double-elect. The cache here makes the in-process case
    # behave the same as the cross-process case.
    global _conscious_agent_lock_fd, _conscious_agent_elected
    if _conscious_agent_elected:
        return False

    lock_path = Path(tempfile.gettempdir()) / _CONSCIOUS_AGENT_LOCK_PATH

    # Open the lockfile and try to grab an exclusive, non-blocking
    # POSIX lock. ``LOCK_NB`` makes the call return immediately with
    # ``BlockingIOError`` if another process already holds the lock —
    # we never want a new worker to wait for the lock because the
    # holder could be long-lived.
    try:
        lock_path.touch(exist_ok=True)
        lock_fd = open(lock_path, "w")
    except OSError as exc:
        logger.debug(
            "Conscious Agent lockfile could not be opened at %s: %s",
            lock_path,
            exc,
        )
        return False

    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Another worker holds the lock. Close our handle and bail.
        lock_fd.close()
        logger.info(
            "Conscious Agent already running in another worker (pid unknown); "
            "this process will not start a new loop"
        )
        return False
    except OSError as exc:
        # fcntl can fail on platforms that don't support it. Treat
        # the same as "another worker has it" so we still avoid
        # double-starting on Linux/macOS while not crashing on Windows.
        lock_fd.close()
        logger.debug(
            "Conscious Agent flock failed on %s: %s", lock_path, exc
        )
        return False

    # We have the lock. Record our PID so operators can identify the
    # owner. Best-effort: a failure here is not fatal.
    try:
        lock_fd.seek(0)
        lock_fd.write(str(os.getpid()))
        lock_fd.truncate()
        lock_fd.flush()
    except OSError:
        pass

    logger.info(
        "Conscious Agent elected by worker pid=%s (lock=%s)",
        os.getpid(),
        lock_path,
    )
    # NOTE: We deliberately do NOT close ``lock_fd`` here. The POSIX
    # file lock is bound to the open file description; closing the fd
    # would release the lock and let the next worker steal the
    # election. The caller is expected to keep the adapter's
    # lifetime long enough that this is not a problem; if the
    # process exits, the OS reclaims the lock automatically.
    _conscious_agent_lock_fd = lock_fd
    _conscious_agent_elected = True
    return True


@dataclass
class MemoryAccessPattern:
    """Tracks memory access frequency and recency."""

    memory_id: str
    access_count: int
    last_accessed: datetime
    access_velocity: float  # accesses per hour
    semantic_importance: float  # 0.0-1.0
    category: str  # facts, preferences, skills, rules, context


@dataclass
class PromotionCandidate:
    """Memory candidate for promotion to short-term storage."""

    memory_id: str
    priority_score: float
    reason: str
    current_tier: str  # long_term, short_term, working


class ConsciousAgent:
    """
    Background agent that analyzes memory patterns and optimizes storage.

    Inspired by Memori's Conscious Agent pattern but adapted for
    session-mgmt-mcp's development workflow context.
    """

    def __init__(
        self,
        reflection_db: Any,
        analysis_interval_hours: int = 6,
        promotion_threshold: float = 0.75,
    ):
        """
        Initialize the Conscious Agent.

        Args:
            reflection_db: ReflectionDatabase instance
            analysis_interval_hours: How often to run analysis (default: 6 hours)
            promotion_threshold: Minimum score for promotion (0.0-1.0)

        """
        self.reflection_db = reflection_db
        self.analysis_interval = timedelta(hours=analysis_interval_hours)
        self.promotion_threshold = promotion_threshold
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background conscious agent."""
        if self._running:
            logger.warning("Conscious agent already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Conscious agent started (interval: {self.analysis_interval.total_seconds() / 3600:.1f}h)"
        )

    async def stop(self) -> None:
        """Stop the background conscious agent."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Conscious agent stopped")

    async def _run_loop(self) -> None:
        """Main background loop for memory analysis."""
        while self._running:
            try:
                await self._analyze_and_optimize()
                await asyncio.sleep(self.analysis_interval.total_seconds())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Conscious agent error: {e}")
                # Continue running despite errors
                await asyncio.sleep(300)  # Wait 5 minutes before retry

    async def _analyze_and_optimize(self) -> dict[str, Any]:
        """
        Analyze memory patterns and optimize storage.

        Returns:
            dict: Analysis results with promotion statistics

        """
        logger.info("Running conscious agent memory analysis...")

        # 1. Analyze access patterns
        patterns = await self._analyze_access_patterns()

        # 2. Calculate priority scores
        candidates = await self._calculate_promotion_priorities(patterns)

        # 3. Promote high-priority memories
        promoted = await self._promote_memories(candidates)

        # 4. Demote stale memories
        demoted = await self._demote_stale_memories()

        results = {
            "timestamp": datetime.now().isoformat(),
            "patterns_analyzed": len(patterns),
            "promotion_candidates": len(candidates),
            "promoted_count": len(promoted),
            "demoted_count": len(demoted),
            "promoted_ids": promoted,
            "demoted_ids": demoted,
        }

        logger.info(
            f"Conscious agent analysis complete: "
            f"{results['promoted_count']} promoted, "
            f"{results['demoted_count']} demoted"
        )

        return results

    async def _analyze_access_patterns(self) -> list[MemoryAccessPattern]:
        """
        Analyze memory access patterns from database.

        Returns:
            list[MemoryAccessPattern]: Access patterns for all memories

        """
        # Query DuckDB for access patterns in v2 tables
        import duckdb  # Local import to avoid hard dep when unused

        from session_buddy.settings import get_database_path

        patterns: list[MemoryAccessPattern] = []
        try:
            conn = duckdb.connect(
                get_database_path(),
                config={"allow_unsigned_extensions": True},
            )
        except Exception:
            return patterns

        try:
            rows = conn.execute(
                """
                WITH base AS (
                    SELECT
                        l.memory_id,
                        COUNT(*) AS access_count,
                        MIN(l.timestamp) AS first_access,
                        MAX(l.timestamp) AS last_accessed
                    FROM memory_access_log l
                    GROUP BY l.memory_id
                )
                SELECT
                    b.memory_id,
                    b.access_count,
                    b.first_access,
                    b.last_accessed,
                    c.category,
                    COALESCE(c.importance_score, 0.5) AS importance
                FROM base b
                JOIN conversations_v2 c ON c.id = b.memory_id
                """
            ).fetchall()

            now = datetime.now()
            for r in rows:
                memory_id = str(r[0])
                access_count = int(r[1])
                first_access = r[2]
                last_accessed = r[3]
                category = str(r[4])
                importance = float(r[5])

                try:
                    # Compute accesses per hour since first access
                    hours = max((now - first_access).total_seconds() / 3600.0, 1e-6)
                    velocity = access_count / hours
                except Exception:
                    velocity = float(access_count)

                # Coerce last_accessed to datetime if needed
                if not isinstance(last_accessed, datetime):
                    try:
                        last_accessed = datetime.fromisoformat(str(last_accessed))
                    except Exception:
                        last_accessed = now

                patterns.append(
                    MemoryAccessPattern(
                        memory_id=memory_id,
                        access_count=access_count,
                        last_accessed=last_accessed,
                        access_velocity=velocity,
                        semantic_importance=importance,
                        category=category,
                    )
                )
        except Exception:
            # If tables missing or query fails, return empty list
            return []
        finally:
            with contextlib.suppress(Exception):
                conn.close()

        return patterns

    async def _calculate_promotion_priorities(
        self, patterns: list[MemoryAccessPattern]
    ) -> list[PromotionCandidate]:
        """
        Calculate promotion priority scores for memories.

        Priority score factors:
        - Access frequency (40%)
        - Recency (30%)
        - Semantic importance (20%)
        - Category weight (10%)

        Args:
            patterns: List of memory access patterns

        Returns:
            list[PromotionCandidate]: Sorted by priority score (highest first)

        """
        candidates: list[PromotionCandidate] = []

        for pattern in patterns:
            # Calculate weighted score
            frequency_score = min(pattern.access_count / 10.0, 1.0)  # Normalize to 0-1
            recency_score = self._calculate_recency_score(pattern.last_accessed)
            semantic_score = pattern.semantic_importance
            category_score = self._get_category_weight(pattern.category)

            priority_score = (
                frequency_score * 0.4
                + recency_score * 0.3
                + semantic_score * 0.2
                + category_score * 0.1
            )

            if priority_score >= self.promotion_threshold:
                candidate = PromotionCandidate(
                    memory_id=pattern.memory_id,
                    priority_score=priority_score,
                    reason=self._generate_promotion_reason(pattern, priority_score),
                    current_tier="long_term",  # Assume long-term by default
                )
                candidates.append(candidate)

        # Sort by priority score (highest first)
        candidates.sort(key=lambda c: c.priority_score, reverse=True)

        return candidates

    def _calculate_recency_score(self, last_accessed: datetime) -> float:
        """
        Calculate recency score (0.0-1.0) based on time since last access.

        Args:
            last_accessed: Timestamp of last access

        Returns:
            float: Recency score (1.0 = accessed now, 0.0 = very old)

        """
        time_delta = datetime.now() - last_accessed
        hours_ago = time_delta.total_seconds() / 3600

        # Exponential decay: score = e^(-hours/24)
        # Recent (0-6h): 0.78-1.0
        # Medium (6-24h): 0.37-0.78
        # Old (24h+): 0.0-0.37
        import math

        return math.exp(-hours_ago / 24)

    def _get_category_weight(self, category: str) -> float:
        """
        Get importance weight for memory category.

        Args:
            category: Memory category (facts, preferences, skills, rules, context)

        Returns:
            float: Category weight (0.0-1.0)

        """
        weights = {
            "preferences": 1.0,  # User preferences are highest priority
            "skills": 0.9,  # User skills/knowledge
            "rules": 0.8,  # Learned rules/patterns
            "facts": 0.7,  # Factual information
            "context": 0.6,  # Contextual information
        }
        return weights.get(category, 0.5)

    def _generate_promotion_reason(
        self, pattern: MemoryAccessPattern, score: float
    ) -> str:
        """Generate human-readable promotion reason."""
        reasons = []

        if pattern.access_count > 5:
            reasons.append(f"high access frequency ({pattern.access_count}x)")

        recency_hours = (datetime.now() - pattern.last_accessed).total_seconds() / 3600
        if recency_hours < 6:
            reasons.append("recently accessed")

        if pattern.semantic_importance > 0.8:
            reasons.append("high semantic importance")

        if pattern.category in ("preferences", "skills"):
            reasons.append(f"critical category ({pattern.category})")

        reason = ", ".join(reasons) if reasons else "high priority score"
        return f"{reason} (score: {score:.2f})"

    async def _promote_memories(
        self, candidates: list[PromotionCandidate]
    ) -> list[str]:
        """
        Promote high-priority memories to short-term storage.

        Args:
            candidates: Sorted list of promotion candidates

        Returns:
            list[str]: IDs of promoted memories

        """
        promoted: list[str] = []

        import duckdb

        from session_buddy.settings import get_database_path

        for candidate in candidates:
            try:
                conn = duckdb.connect(
                    get_database_path(),
                    config={"allow_unsigned_extensions": True},
                )
                conn.execute(
                    "UPDATE conversations_v2 SET memory_tier='short_term' WHERE id=?",
                    [candidate.memory_id],
                )
                conn.execute(
                    "INSERT INTO memory_promotions (id, memory_id, from_tier, to_tier, reason, priority_score) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        f"prom_{candidate.memory_id}",
                        candidate.memory_id,
                        candidate.current_tier,
                        "short_term",
                        candidate.reason,
                        candidate.priority_score,
                    ],
                )
                conn.close()
                promoted.append(candidate.memory_id)
                logger.debug(
                    f"Promoted memory {candidate.memory_id}: {candidate.reason}"
                )

            except Exception as e:
                logger.exception(f"Failed to promote memory {candidate.memory_id}: {e}")

        return promoted

    async def _demote_stale_memories(self) -> list[str]:
        """
        Demote stale memories from short-term to long-term storage.

        Returns:
            list[str]: IDs of demoted memories

        """
        demoted: list[str] = []

        import duckdb

        from session_buddy.settings import get_database_path

        conn = duckdb.connect(
            str(get_database_path()), config={"allow_unsigned_extensions": True}
        )
        rows = conn.execute(
            """
            SELECT c.id
            FROM conversations_v2 c
            LEFT JOIN (
                SELECT memory_id, MAX(timestamp) AS last_access
                FROM memory_access_log
                GROUP BY memory_id
            ) a ON a.memory_id = c.id
            WHERE c.memory_tier='short_term'
              AND (a.last_access IS NULL OR a.last_access < NOW() - INTERVAL 7 DAY)
            """
        ).fetchall()
        for (mid,) in rows:
            conn.execute(
                "UPDATE conversations_v2 SET memory_tier='long_term' WHERE id=?",
                [mid],
            )
            demoted.append(str(mid))
        conn.close()
        return demoted

    async def force_analysis(self) -> dict[str, Any]:
        """
        Force immediate analysis (for testing/debugging).

        Returns:
            dict: Analysis results

        """
        logger.info("Forcing conscious agent analysis...")
        return await self._analyze_and_optimize()
