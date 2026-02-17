"""Collaborative filtering engine for skill recommendations.

This module provides user-based collaborative filtering to recommend skills
based on what similar users used successfully. Uses Jaccard similarity for
user similarity calculation and combines with skill completion rates for
recommendation scoring.

Example:
    >>> engine = CollaborativeFilteringEngine(Path("skills.db"))
    >>> similar = engine.get_similar_users("user123", min_common_skills=3)
    >>> for user_id, similarity in similar:
    ...     print(f"User {user_id}: {similarity:.2f}")
    >>> recommendations = engine.recommend_from_similar_users("user123", limit=5)
    >>> for rec in recommendations:
    ...     print(f"{rec['skill_name']}: {rec['score']:.2f}")
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ============================================================================
# Exceptions
# ============================================================================


class CollaborativeFilteringError(Exception):
    """Base exception for collaborative filtering errors."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


# ============================================================================
# Collaborative Filtering Engine
# ============================================================================


class CollaborativeFilteringEngine:
    """Generate recommendations based on user-skill interactions.

    Uses user-based collaborative filtering with Jaccard similarity to find
    users with similar skill usage patterns, then recommends skills based on
    what similar users used successfully.

    Algorithm:
        1. Find users with similar skill usage patterns (Jaccard similarity)
        2. Get skills they used successfully
        3. Filter out skills current user already tried
        4. Score by: user_similarity × skill_completion_rate

    Attributes:
        db_path: Path to SQLite database
        cache_ttl_seconds: Time-to-live for cached results (default: 1 hour)
    """

    def __init__(
        self,
        db_path: str | Path,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        """Initialize collaborative filtering engine.

        Args:
            db_path: Path to SQLite database file
            cache_ttl_seconds: Cache TTL for similar users (default: 3600s = 1 hour)
        """
        self.db_path = Path(db_path)
        self.cache_ttl_seconds = cache_ttl_seconds

        # Cache for similar users calculations
        self._similar_users_cache: dict[str, tuple[list[tuple[str, float]], float]] = {}

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # Connection Management
    # ========================================================================

    @contextmanager
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with proper configuration.

        Yields:
            Configured SQLite connection
        """
        conn = sqlite3.connect(
            self.db_path,
            timeout=5.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row

        # Configure connection
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        try:
            yield conn
        finally:
            conn.close()

    def _hash_user_id(self, user_id: str) -> str:
        """Hash user ID for privacy.

        Args:
            user_id: Raw user identifier

        Returns:
            SHA256 hash of user ID
        """
        return hashlib.sha256(user_id.encode()).hexdigest()

    # ========================================================================
    # User Similarity
    # ========================================================================

    def get_similar_users(
        self,
        user_id: str,
        min_common_skills: int = 3,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Find users with similar skill usage patterns.

        Uses Jaccard similarity on skill sets:
            Jaccard(A, B) = |A ∩ B| / |A ∪ B|

        Where A and B are sets of skills used by users.

        Args:
            user_id: User to find similar users for
            min_common_skills: Minimum common skills required (default: 3)
            limit: Maximum number of similar users (default: 10)

        Returns:
            List of (user_id, jaccard_similarity) tuples sorted by similarity

        Raises:
            CollaborativeFilteringError: If query fails

        Example:
            >>> engine = CollaborativeFilteringEngine("skills.db")
            >>> similar = engine.get_similar_users("user123", min_common_skills=3, limit=10)
            >>> for user_id, similarity in similar:
            ...     print(f"User {user_id}: {similarity:.2f}")
        """
        # Check cache first
        cache_key = f"{user_id}:{min_common_skills}:{limit}"
        if cache_key in self._similar_users_cache:
            cached_results, cached_time = self._similar_users_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl_seconds:
                return cached_results

        # Hash user ID for privacy
        hashed_user_id = self._hash_user_id(user_id)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Get target user's skill set
                cursor.execute(
                    """
                    SELECT DISTINCT skill_name
                    FROM skill_user_interactions
                    WHERE user_id = ? AND completed = 1
                    """,
                    (hashed_user_id,),
                )

                target_skills = {row["skill_name"] for row in cursor.fetchall()}

                # Cold start: user has no skill history
                if not target_skills:
                    return []

                target_skills_count = len(target_skills)

                # Find similar users using Jaccard similarity
                # SQL implements: Jaccard = |A ∩ B| / |A ∪ B|
                cursor.execute(
                    """
                    WITH other_user_skills AS (
                        SELECT
                            user_id,
                            COUNT(*) as total_skills,
                            COUNT(CASE WHEN skill_name IN (
                                SELECT skill_name
                                FROM skill_user_interactions
                                WHERE user_id = ? AND completed = 1
                            ) THEN 1 END) as common_skills
                        FROM skill_user_interactions
                        WHERE completed = 1 AND user_id != ?
                        GROUP BY user_id
                        HAVING common_skills >= ?
                    )
                    SELECT
                        user_id,
                        common_skills,
                        CAST(common_skills AS REAL) / (total_skills + ? - common_skills) as jaccard_similarity
                    FROM other_user_skills
                    ORDER BY jaccard_similarity DESC
                    LIMIT ?
                    """,
                    (
                        hashed_user_id,
                        hashed_user_id,
                        min_common_skills,
                        target_skills_count,
                        limit,
                    ),
                )

                results = [
                    (row["user_id"], row["jaccard_similarity"])
                    for row in cursor.fetchall()
                ]

                # Cache results
                self._similar_users_cache[cache_key] = (results, time.time())

                return results

        except sqlite3.Error as e:
            raise CollaborativeFilteringError(
                f"Failed to find similar users for {user_id}",
                cause=e,
            ) from e

    # ========================================================================
    # Recommendations
    # ========================================================================

    def recommend_from_similar_users(
        self,
        user_id: str,
        limit: int = 5,
        min_common_skills: int = 3,
    ) -> list[dict[str, object]]:
        """Recommend skills based on what similar users used successfully.

        Algorithm:
            1. Find similar users
            2. Get skills they used successfully
            3. Filter out skills current user already tried
            4. Score by: similarity × skill_completion_rate

        Args:
            user_id: User to generate recommendations for
            limit: Maximum number of recommendations (default: 5)
            min_common_skills: Minimum common skills for similar users (default: 3)

        Returns:
            List of recommendations:
                [{
                    "skill_name": str,
                    "score": float,
                    "completion_rate": float,
                    "source": "collaborative_filtering",
                    "similar_user_id": str
                }, ...]

        Raises:
            CollaborativeFilteringError: If recommendation generation fails

        Example:
            >>> engine = CollaborativeFilteringEngine("skills.db")
            >>> recommendations = engine.recommend_from_similar_users("user123", limit=5)
            >>> for rec in recommendations:
            ...     print(f"{rec['skill_name']}: {rec['score']:.2f} "
            ...           f"(rate: {rec['completion_rate']:.1%})")
        """
        hashed_user_id = self._hash_user_id(user_id)

        try:
            # Step 1: Get similar users
            similar_users = self.get_similar_users(
                user_id,
                min_common_skills=min_common_skills,
                limit=10,  # Get more users for better recommendations
            )

            if not similar_users:
                # No similar users found - cold start problem
                return []

            # Step 2: Get skills current user already tried
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT DISTINCT skill_name
                    FROM skill_user_interactions
                    WHERE user_id = ?
                    """,
                    (hashed_user_id,),
                )

                tried_skills = {row["skill_name"] for row in cursor.fetchall()}

            # Step 3: Get skills from similar users with completion rates
            skill_candidates: dict[str, dict[str, object]] = {}

            for similar_user_id, similarity in similar_users:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Get skills this similar user used successfully
                    cursor.execute(
                        """
                        SELECT
                            skill_name,
                            CAST(SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS REAL) /
                                COUNT(*) as completion_rate
                        FROM skill_user_interactions
                        WHERE user_id = ?
                        GROUP BY skill_name
                        """,
                        (similar_user_id,),
                    )

                    for row in cursor.fetchall():
                        skill_name = row["skill_name"]
                        completion_rate = row["completion_rate"]

                        # Skip if user already tried this skill
                        if skill_name in tried_skills:
                            continue

                        # Calculate recommendation score
                        score = similarity * completion_rate

                        # Keep best score per skill (from most similar user)
                        if skill_name not in skill_candidates:
                            skill_candidates[skill_name] = {
                                "skill_name": skill_name,
                                "score": score,
                                "completion_rate": completion_rate,
                                "source": "collaborative_filtering",
                                "similar_user_id": similar_user_id,
                            }
                        else:
                            # Update if this similar user gives higher score
                            if score > skill_candidates[skill_name]["score"]:
                                skill_candidates[skill_name].update(
                                    {
                                        "score": score,
                                        "completion_rate": completion_rate,
                                        "similar_user_id": similar_user_id,
                                    }
                                )

            # Step 4: Sort by score and return top N
            recommendations = sorted(
                skill_candidates.values(),
                key=lambda x: x["score"],
                reverse=True,
            )

            return recommendations[:limit]

        except sqlite3.Error as e:
            raise CollaborativeFilteringError(
                f"Failed to generate recommendations for {user_id}",
                cause=e,
            ) from e

    # ========================================================================
    # Community Baselines
    # ========================================================================

    def update_community_baselines(self) -> dict[str, object]:
        """Update global skill effectiveness baselines.

        Aggregates skill effectiveness across all users to create community
        averages for comparison and fallback recommendations.

        Returns:
            Update status:
                {
                    "status": "updated",
                    "timestamp": str,
                    "skills_updated": int
                }

        Raises:
            CollaborativeFilteringError: If update fails

        Example:
            >>> engine = CollaborativeFilteringEngine("skills.db")
            >>> result = engine.update_community_baselines()
            >>> print(f"Updated {result['skills_updated']} skills")
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Calculate community baselines from invocations
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO skill_community_baselines (
                        skill_name,
                        total_users,
                        total_invocations,
                        global_completion_rate,
                        global_avg_duration_seconds,
                        most_common_workflow_phase,
                        effectiveness_percentile,
                        last_updated
                    )
                    SELECT
                        si.skill_name,
                        COUNT(DISTINCT si.session_id) as total_users,
                        COUNT(*) as total_invocations,
                        AVG(CASE WHEN si.completed = 1 THEN 1.0 ELSE 0.0 END) as global_completion_rate,
                        AVG(si.duration_seconds) as global_avg_duration_seconds,
                        (
                            SELECT workflow_phase
                            FROM skill_invocation si2
                            WHERE si2.skill_name = si.skill_name
                            GROUP BY workflow_phase
                            ORDER BY COUNT(*) DESC
                            LIMIT 1
                        ) as most_common_workflow_phase,
                        NULL as effectiveness_percentile,  -- Calculated below
                        datetime('now') as last_updated
                    FROM skill_invocation si
                    GROUP BY si.skill_name
                    """
                )

                skills_updated = cursor.rowcount

                # Calculate effectiveness percentile (relative to other skills)
                cursor.execute(
                    """
                    WITH skill_rates AS (
                        SELECT
                            skill_name,
                            global_completion_rate
                        FROM skill_community_baselines
                    ),
                    percentiles AS (
                        SELECT
                            skill_name,
                            global_completion_rate,
                            -- Percentile rank: percentage of skills with lower completion rate
                            CAST(
                                SUM(CASE
                                    WHEN sr2.global_completion_rate < sr1.global_completion_rate
                                    THEN 1
                                    ELSE 0
                                END) AS REAL) * 100.0 / COUNT(*) as percentile
                        FROM skill_rates sr1
                        CROSS JOIN skill_rates sr2
                        GROUP BY sr1.skill_name, sr1.global_completion_rate
                    )
                    UPDATE skill_community_baselines
                    SET effectiveness_percentile = (
                        SELECT percentile
                        FROM percentiles
                        WHERE percentiles.skill_name = skill_community_baselines.skill_name
                    )
                    """
                )

                timestamp = datetime.now().isoformat()

                return {
                    "status": "updated",
                    "timestamp": timestamp,
                    "skills_updated": skills_updated,
                }

        except sqlite3.Error as e:
            raise CollaborativeFilteringError(
                "Failed to update community baselines",
                cause=e,
            ) from e

    def get_global_fallback_recommendations(
        self,
        limit: int = 5,
        min_invocations: int = 10,
    ) -> list[dict[str, object]]:
        """Get globally popular skills as fallback for cold start.

        When no similar users exist, fall back to globally effective skills
        based on community baselines.

        Args:
            limit: Maximum number of recommendations (default: 5)
            min_invocations: Minimum invocations required (default: 10)

        Returns:
            List of recommendations:
                [{
                    "skill_name": str,
                    "score": float,
                    "completion_rate": float,
                    "source": "global_popularity",
                    "effectiveness_percentile": float
                }, ...]

        Example:
            >>> engine = CollaborativeFilteringEngine("skills.db")
            >>> fallback = engine.get_global_fallback_recommendations(limit=5)
            >>> for rec in fallback:
            ...     print(f"{rec['skill_name']}: {rec['completion_rate']:.1%}")
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT
                        skill_name,
                        global_completion_rate as completion_rate,
                        effectiveness_percentile,
                        total_invocations
                    FROM skill_community_baselines
                    WHERE total_invocations >= ?
                    ORDER BY effectiveness_percentile DESC
                    LIMIT ?
                    """,
                    (min_invocations, limit),
                )

                return [
                    {
                        "skill_name": row["skill_name"],
                        "score": row["effectiveness_percentile"]
                        / 100.0,  # Normalize to 0-1
                        "completion_rate": row["completion_rate"],
                        "source": "global_popularity",
                        "effectiveness_percentile": row["effectiveness_percentile"],
                    }
                    for row in cursor.fetchall()
                ]

        except sqlite3.Error as e:
            raise CollaborativeFilteringError(
                "Failed to get global fallback recommendations",
                cause=e,
            ) from e

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def clear_cache(self) -> None:
        """Clear cached similar users calculations.

        Example:
            >>> engine = CollaborativeFilteringEngine("skills.db")
            >>> engine.clear_cache()
        """
        self._similar_users_cache.clear()

    def get_user_skill_profile(
        self,
        user_id: str,
    ) -> dict[str, object]:
        """Get user's skill usage profile.

        Args:
            user_id: User to get profile for

        Returns:
            User profile:
                {
                    "user_id": str,
                    "unique_skills": int,
                    "total_interactions": int,
                    "completion_rate": float,
                    "top_skills": list[tuple[str, int]]
                }

        Example:
            >>> engine = CollaborativeFilteringEngine("skills.db")
            >>> profile = engine.get_user_skill_profile("user123")
            >>> print(f"User has {profile['unique_skills']} unique skills")
        """
        hashed_user_id = self._hash_user_id(user_id)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Get overall stats
                cursor.execute(
                    """
                    SELECT
                        COUNT(DISTINCT skill_name) as unique_skills,
                        COUNT(*) as total_interactions,
                        AVG(CASE WHEN completed = 1 THEN 1.0 ELSE 0.0 END) as completion_rate
                    FROM skill_user_interactions
                    WHERE user_id = ?
                    """,
                    (hashed_user_id,),
                )

                row = cursor.fetchone()

                # Get top skills
                cursor.execute(
                    """
                    SELECT
                        skill_name,
                        COUNT(*) as invocation_count
                    FROM skill_user_interactions
                    WHERE user_id = ?
                    GROUP BY skill_name
                    ORDER BY invocation_count DESC
                    LIMIT 10
                    """,
                    (hashed_user_id,),
                )

                top_skills = [
                    (row["skill_name"], row["invocation_count"])
                    for row in cursor.fetchall()
                ]

                return {
                    "user_id": user_id,
                    "unique_skills": row["unique_skills"],
                    "total_interactions": row["total_interactions"],
                    "completion_rate": row["completion_rate"] or 0.0,
                    "top_skills": top_skills,
                }

        except sqlite3.Error as e:
            raise CollaborativeFilteringError(
                f"Failed to get profile for {user_id}",
                cause=e,
            ) from e


# ============================================================================
# Convenience Functions
# ============================================================================


def get_collaborative_engine(
    db_path: str | Path | None = None,
) -> CollaborativeFilteringEngine:
    """Get or create collaborative filtering engine instance.

    Args:
        db_path: Path to database file. Defaults to
            `.session-buddy/skills.db` in current directory.

    Returns:
        CollaborativeFilteringEngine instance

    Example:
        >>> engine = get_collaborative_engine()
        >>> recommendations = engine.recommend_from_similar_users("user123")
    """
    if db_path is None:
        db_path = Path.cwd() / ".session-buddy" / "skills.db"

    return CollaborativeFilteringEngine(db_path=db_path)
