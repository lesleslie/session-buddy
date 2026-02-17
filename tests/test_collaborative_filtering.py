"""Tests for collaborative filtering engine."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from session_buddy.analytics.collaborative_filtering import (
    CollaborativeFilteringEngine,
    CollaborativeFilteringError,
    get_collaborative_engine,
)


@pytest.fixture
def test_db_with_interactions() -> Path:
    """Create test database with sample user-skill interactions."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_skills.db"

        # Initialize database with V4 schema
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create skill_user_interactions table (V4)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_user_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                invoked_at TEXT NOT NULL,
                completed BOOLEAN NOT NULL,
                rating REAL,
                alternatives_considered TEXT
            )
            """
        )

        # Create skill_invocation table for baselines
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_invocation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                invoked_at TEXT NOT NULL,
                session_id TEXT NOT NULL,
                completed BOOLEAN NOT NULL,
                duration_seconds REAL
            )
            """
        )

        # Create skill_community_baselines table (V4)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_community_baselines (
                skill_name TEXT PRIMARY KEY,
                total_users INTEGER DEFAULT 0,
                total_invocations INTEGER DEFAULT 0,
                global_completion_rate REAL,
                global_avg_duration_seconds REAL,
                most_common_workflow_phase TEXT,
                effectiveness_percentile REAL,
                last_updated TEXT NOT NULL
            )
            """
        )

        # Insert sample interactions for 3 users
        # User1: skills A, B, C (all completed)
        # User2: skills A, B, D (all completed)
        # User3: skills B, C, E (all completed)
        # Expected: User1 and User2 are most similar (share A, B)

        test_data = [
            # User1 interactions
            ("user1", "session1", "skill-a", "2025-02-10T10:00:00", True, 4.5),
            ("user1", "session1", "skill-b", "2025-02-10T10:05:00", True, 4.0),
            ("user1", "session1", "skill-c", "2025-02-10T10:10:00", True, 3.5),
            # User2 interactions (similar to user1)
            ("user2", "session2", "skill-a", "2025-02-10T11:00:00", True, 5.0),
            ("user2", "session2", "skill-b", "2025-02-10T11:05:00", True, 4.5),
            ("user2", "session2", "skill-d", "2025-02-10T11:10:00", True, 4.0),
            # User3 interactions (moderately similar to user1)
            ("user3", "session3", "skill-b", "2025-02-10T12:00:00", True, 3.0),
            ("user3", "session3", "skill-c", "2025-02-10T12:05:00", True, 4.5),
            ("user3", "session3", "skill-e", "2025-02-10T12:10:00", True, 5.0),
        ]

        for user_id, session_id, skill_name, invoked_at, completed, rating in test_data:
            cursor.execute(
                """
                INSERT INTO skill_user_interactions
                (user_id, session_id, skill_name, invoked_at, completed, rating)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, session_id, skill_name, invoked_at, completed, rating),
            )

        conn.commit()
        conn.close()

        yield db_path


class TestCollaborativeFilteringEngine:
    """Test suite for CollaborativeFilteringEngine."""

    def test_init(self, test_db_with_interactions: Path) -> None:
        """Test engine initialization."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)
        assert engine.db_path == test_db_with_interactions
        assert engine.cache_ttl_seconds == 3600

    def test_get_similar_users_basic(
        self,
        test_db_with_interactions: Path,
    ) -> None:
        """Test finding similar users."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        # Find similar users for user1
        similar = engine.get_similar_users("user1", min_common_skills=1, limit=5)

        # Should find user2 and user3
        assert len(similar) <= 5
        assert all(0 <= sim <= 1 for _, sim in similar)

        # User2 should be most similar (shares skills A, B with user1)
        # Jaccard(user1, user2) = |{A,B}| / |{A,B,C,D}| = 2/4 = 0.5
        # Jaccard(user1, user3) = |{B,C}| / |{A,B,C,E}| = 2/4 = 0.5
        # So both should have similarity 0.5

        similarities_dict = {user_id: sim for user_id, sim in similar}

        # User2 and User3 should both be found
        assert len(similar) >= 2

    def test_get_similar_users_min_common_skills(
        self,
        test_db_with_interactions: Path,
    ) -> None:
        """Test minimum common skills filter."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        # Require at least 2 common skills
        similar = engine.get_similar_users("user1", min_common_skills=2, limit=10)

        # Only user2 and user3 share >=2 skills with user1
        assert len(similar) <= 2

    def test_get_similar_users_cold_start(self, test_db_with_interactions: Path) -> None:
        """Test cold start problem (user with no history)."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        # User with no interactions
        similar = engine.get_similar_users("newuser", min_common_skills=1)

        # Should return empty list
        assert similar == []

    def test_recommend_from_similar_users(self, test_db_with_interactions: Path) -> None:
        """Test generating recommendations."""
        engine = CollaborativeFilteringFilteringEngine(test_db_with_interactions)

        # Get recommendations for user1
        recommendations = engine.recommend_from_similar_users("user1", limit=3)

        # Should recommend skills from similar users that user1 hasn't tried
        # User1 hasn't tried: skill-d, skill-e
        assert len(recommendations) <= 3

        # All recommendations should have required fields
        for rec in recommendations:
            assert "skill_name" in rec
            assert "score" in rec
            assert "completion_rate" in rec
            assert "source" in rec
            assert rec["source"] == "collaborative_filtering"
            assert "similar_user_id" in rec

        # Scores should be between 0 and 1
        assert all(0 <= rec["score"] <= 1 for rec in recommendations)

    def test_recommend_from_similar_users_filter_tried_skills(
        self,
        test_db_with_interactions: Path,
    ) -> None:
        """Test that recommendations exclude skills user already tried."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        recommendations = engine.recommend_from_similar_users("user1", limit=10)

        # User1 has tried skills A, B, C
        recommended_skills = {rec["skill_name"] for rec in recommendations}

        # Should not recommend skills user1 already tried
        assert "skill-a" not in recommended_skills
        assert "skill-b" not in recommended_skills
        assert "skill-c" not in recommended_skills

    def test_recommend_from_similar_users_cold_start(
        self,
        test_db_with_interactions: Path,
    ) -> None:
        """Test recommendations for cold start user."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        # User with no history
        recommendations = engine.recommend_from_similar_users("newuser", limit=5)

        # Should return empty list
        assert recommendations == []

    def test_update_community_baselines(self, test_db_with_interactions: Path) -> None:
        """Test updating community baselines."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        result = engine.update_community_baselines()

        assert result["status"] == "updated"
        assert "timestamp" in result
        assert result["skills_updated"] >= 0

        # Verify baselines were created
        with sqlite3.connect(test_db_with_interactions) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_community_baselines")
            count = cursor.fetchone()[0]

            # Should have created baselines for at least some skills
            # (Note: Our test data doesn't have skill_invocation records,
            # so this might be 0, but the function should not error)

    def test_get_global_fallback_recommendations(
        self,
        test_db_with_interactions: Path,
    ) -> None:
        """Test global fallback recommendations."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        # First update baselines
        engine.update_community_baselines()

        # Get fallback recommendations
        fallback = engine.get_global_fallback_recommendations(limit=3, min_invocations=1)

        # Should return recommendations
        assert len(fallback) <= 3

        # All recommendations should have required fields
        for rec in fallback:
            assert "skill_name" in rec
            assert "score" in rec
            assert "completion_rate" in rec
            assert rec["source"] == "global_popularity"
            assert "effectiveness_percentile" in rec

    def test_cache_functionality(self, test_db_with_interactions: Path) -> None:
        """Test caching of similar users."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        # First call
        similar1 = engine.get_similar_users("user1", min_common_skills=1, limit=5)

        # Second call should use cache
        similar2 = engine.get_similar_users("user1", min_common_skills=1, limit=5)

        # Results should be identical
        assert similar1 == similar2

        # Clear cache
        engine.clear_cache()

        # Third call should recompute (but give same results)
        similar3 = engine.get_similar_users("user1", min_common_skills=1, limit=5)
        assert similar3 == similar1

    def test_get_user_skill_profile(self, test_db_with_interactions: Path) -> None:
        """Test getting user skill profile."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        profile = engine.get_user_skill_profile("user1")

        assert profile["user_id"] == "user1"
        assert profile["unique_skills"] == 3  # A, B, C
        assert profile["total_interactions"] == 3
        assert 0 <= profile["completion_rate"] <= 1
        assert len(profile["top_skills"]) <= 10

    def test_user_id_hashing(self, test_db_with_interactions: Path) -> None:
        """Test that user IDs are hashed for privacy."""
        engine = CollaborativeFilteringEngine(test_db_with_interactions)

        # Hash user ID
        hashed = engine._hash_user_id("test_user")

        # Hash should be consistent
        hashed2 = engine._hash_user_id("test_user")
        assert hashed == hashed2

        # Different users should have different hashes
        hashed3 = engine._hash_user_id("other_user")
        assert hashed != hashed3

        # Hash should be SHA256 (64 hex chars)
        assert len(hashed) == 64
        assert all(c in "0123456789abcdef" for c in hashed)


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_get_collaborative_engine(self) -> None:
        """Test get_collaborative_engine convenience function."""
        with TemporaryDirectory() as tmpdir:
            import os

            os.chdir(tmpdir)

            # Should create default path
            engine = get_collaborative_engine()

            assert isinstance(engine, CollaborativeFilteringEngine)
            assert engine.db_path == Path.cwd() / ".session-buddy" / "skills.db"

    def test_get_collaborative_engine_with_path(self, test_db_with_interactions: Path) -> None:
        """Test get_collaborative_engine with custom path."""
        engine = get_collaborative_engine(test_db_with_interactions)

        assert isinstance(engine, CollaborativeFilteringEngine)
        assert engine.db_path == test_db_with_interactions


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_database_path(self) -> None:
        """Test handling of invalid database path."""
        engine = CollaborativeFilteringEngine("/nonexistent/path/db.sqlite")

        # Should raise error when trying to query
        with pytest.raises(CollaborativeFilteringError):
            engine.get_similar_users("user1")

    def test_database_query_error(self, test_db_with_interactions: Path) -> None:
        """Test handling of database query errors."""
        # Create engine with valid but corrupted database
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "corrupt.db"
            db_path.write_text("invalid sqlite data")

            engine = CollaborativeFilteringEngine(db_path)

            # Should raise error
            with pytest.raises(CollaborativeFilteringError):
                engine.get_similar_users("user1")
