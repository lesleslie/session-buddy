"""Predictive analytics for skill success probability.

This module provides machine learning-based prediction of skill invocation
success probability based on historical patterns and contextual features.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

if TYPE_CHECKING:
    pass


@dataclass
class SessionContext:
    """Context information about the current session.

    Attributes:
        session_id: Unique session identifier
        session_start_time: When session started (ISO format)
        skills_used_in_session: List of skills already used
        project_name: Optional project name
    """

    session_id: str
    session_start_time: str
    skills_used_in_session: list[str]
    project_name: str | None = None


class SkillSuccessPredictor:
    """Predict skill success probability using machine learning.

    Uses RandomForest classifier trained on historical invocation data
    to predict the probability that a skill invocation will succeed
    based on temporal patterns, performance metrics, and user familiarity.

    Example:
        >>> predictor = SkillSuccessPredictor(Path("skills.db"))
        >>> predictor.train_model()
        >>> context = SessionContext(
        ...     session_id="abc123",
        ...     session_start_time="2025-02-10T12:00:00",
        ...     skills_used_in_session=["pytest-run", "ruff-check"]
        ... )
        >>> prob = predictor.predict_success_probability(
        ...     "semantic-search",
        ...     "Find similar code patterns",
        ...     "execution",
        ...     context
        ... )
        >>> print(f"Success probability: {prob:.2%}")
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize predictor with database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.model: RandomForestClassifier | None = None
        self.scaler: StandardScaler | None = None
        self.feature_names: list[str] = [
            "hour_of_day",
            "day_of_week",
            "invocation_count_24h",
            "avg_completion_rate_24h",
            "workflow_phase_encoded",
            "session_length_minutes",
            "user_skill_familiarity",
        ]
        self._phase_encoding: dict[str, int] = {}

    def extract_features(
        self,
        skill_name: str,
        user_query: str | None,
        workflow_phase: str | None,
        session_context: SessionContext,
    ) -> dict[str, float]:
        """Extract 7 features from skill invocation context.

        Args:
            skill_name: Name of skill being invoked
            user_query: User's query/description (optional)
            workflow_phase: Current workflow phase (e.g., "setup", "execution")
            session_context: Session context information

        Returns:
            Dictionary mapping feature names to float values
        """
        now = datetime.now()

        # Feature 1: hour_of_day (0-23)
        hour_of_day = float(now.hour)

        # Feature 2: day_of_week (0-6, Monday=0)
        day_of_week = float(now.weekday())

        # Query historical data for remaining features
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Feature 3: invocation_count_24h
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM skill_invocation
                WHERE skill_name = ?
                AND datetime(invoked_at) >= datetime('now', '-24 hours')
                """,
                (skill_name,),
            )
            row = cursor.fetchone()
            invocation_count_24h = float(row["count"] if row else 0)

            # Feature 4: avg_completion_rate_24h
            cursor.execute(
                """
                SELECT AVG(CASE WHEN completed = 1 THEN 1.0 ELSE 0.0 END) as rate
                FROM skill_invocation
                WHERE skill_name = ?
                AND datetime(invoked_at) >= datetime('now', '-24 hours')
                """,
                (skill_name,),
            )
            row = cursor.fetchone()
            avg_completion_rate_24h = float(row["rate"] if row and row["rate"] else 0.0)

        # Feature 5: workflow_phase_encoded
        if workflow_phase:
            if workflow_phase not in self._phase_encoding:
                self._phase_encoding[workflow_phase] = len(self._phase_encoding)
            workflow_phase_encoded = float(self._phase_encoding[workflow_phase])
        else:
            workflow_phase_encoded = 0.0

        # Feature 6: session_length_minutes
        try:
            session_start = datetime.fromisoformat(session_context.session_start_time)
            session_length_minutes = float((now - session_start).total_seconds() / 60)
        except (ValueError, TypeError):
            session_length_minutes = 0.0

        # Feature 7: user_skill_familiarity
        # Count how many times user has successfully used this skill
        skill_familiarity_count = 0
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM skill_invocation
                WHERE skill_name = ?
                AND session_id = ?
                AND completed = 1
                """,
                (skill_name, session_context.session_id),
            )
            row = cursor.fetchone()
            skill_familiarity_count = row["count"] if row else 0

        user_skill_familiarity = float(skill_familiarity_count)

        return {
            "hour_of_day": hour_of_day,
            "day_of_week": day_of_week,
            "invocation_count_24h": invocation_count_24h,
            "avg_completion_rate_24h": avg_completion_rate_24h,
            "workflow_phase_encoded": workflow_phase_encoded,
            "session_length_minutes": session_length_minutes,
            "user_skill_familiarity": user_skill_familiarity,
        }

    def train_model(self, days: int = 30) -> dict[str, object]:
        """Train RandomForest classifier on historical data.

        Args:
            days: Number of days of historical data to use (default: 30)

        Returns:
            Dictionary with training statistics:
                - samples_used: Number of training samples
                - success_rate: Overall success rate in training data
                - feature_importance: Dict of feature importance scores

        Raises:
            ValueError: If insufficient training data available
        """
        # Query historical invocations
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                f"""
                SELECT
                    skill_name,
                    invoked_at,
                    workflow_phase,
                    session_id,
                    completed
                FROM skill_invocation
                WHERE datetime(invoked_at) >= datetime('now', '-{days} days')
                AND completed IS NOT NULL
                ORDER BY invoked_at DESC
                """
            )

            rows = cursor.fetchall()

        if len(rows) < 10:
            raise ValueError(
                f"Insufficient training data: {len(rows)} samples. "
                "Need at least 10 invocations to train model."
            )

        # Prepare training data
        X = []  # Features
        y = []  # Labels (completed=1, abandoned=0)

        for row in rows:
            # Create session context
            context = SessionContext(
                session_id=row["session_id"],
                session_start_time=row["invoked_at"],
                skills_used_in_session=[],
            )

            # Extract features
            features = self.extract_features(
                skill_name=row["skill_name"],
                user_query=None,
                workflow_phase=row["workflow_phase"],
                session_context=context,
            )

            feature_vector = [features[name] for name in self.feature_names]
            X.append(feature_vector)
            y.append(1 if row["completed"] else 0)

        # Convert to numpy arrays
        X_train = np.array(X)
        y_train = np.array(y)

        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)

        # Train model
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X_train_scaled, y_train)

        # Calculate statistics
        success_rate = float(np.mean(y_train))
        feature_importance = dict(
            zip(self.feature_names, self.model.feature_importances_.tolist())
        )

        return {
            "samples_used": len(rows),
            "success_rate": success_rate,
            "feature_importance": feature_importance,
        }

    def predict_success_probability(
        self,
        skill_name: str,
        user_query: str | None,
        workflow_phase: str | None,
        session_context: SessionContext,
    ) -> float:
        """Predict probability of skill success for given context.

        Args:
            skill_name: Name of skill being invoked
            user_query: User's query/description (optional)
            workflow_phase: Current workflow phase
            session_context: Session context information

        Returns:
            Probability of success (0.0 to 1.0)

        Raises:
            RuntimeError: If model not trained yet
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError(
                "Model not trained. Call train_model() before predicting."
            )

        # Extract features
        features = self.extract_features(
            skill_name=skill_name,
            user_query=user_query,
            workflow_phase=workflow_phase,
            session_context=session_context,
        )

        # Create feature vector
        feature_vector = np.array([[features[name] for name in self.feature_names]])

        # Scale features
        feature_vector_scaled = self.scaler.transform(feature_vector)

        # Predict probability
        probability = self.model.predict_proba(feature_vector_scaled)[0, 1]

        return float(probability)

    def get_feature_explanation(
        self,
        skill_name: str,
        user_query: str | None,
        workflow_phase: str | None,
        session_context: SessionContext,
    ) -> dict[str, object]:
        """Get feature values with explanations for prediction.

        Args:
            skill_name: Name of skill being invoked
            user_query: User's query/description (optional)
            workflow_phase: Current workflow phase
            session_context: Session context information

        Returns:
            Dictionary with feature values and interpretations
        """
        features = self.extract_features(
            skill_name=skill_name,
            user_query=user_query,
            workflow_phase=workflow_phase,
            session_context=session_context,
        )

        explanations = {
            "hour_of_day": {
                "value": features["hour_of_day"],
                "interpretation": f"Current hour (0-23): {int(features['hour_of_day'])}",
            },
            "day_of_week": {
                "value": features["day_of_week"],
                "interpretation": f"Day of week (0=Mon, 6=Sun): {int(features['day_of_week'])}",
            },
            "invocation_count_24h": {
                "value": features["invocation_count_24h"],
                "interpretation": f"Recent invocations (24h): {int(features['invocation_count_24h'])}",
            },
            "avg_completion_rate_24h": {
                "value": features["avg_completion_rate_24h"],
                "interpretation": f"Recent success rate (24h): {features['avg_completion_rate_24h']:.1%}",
            },
            "workflow_phase_encoded": {
                "value": features["workflow_phase_encoded"],
                "interpretation": f"Workflow phase encoding: {int(features['workflow_phase_encoded'])}",
            },
            "session_length_minutes": {
                "value": features["session_length_minutes"],
                "interpretation": f"Session length: {features['session_length_minutes']:.1f} minutes",
            },
            "user_skill_familiarity": {
                "value": features["user_skill_familiarity"],
                "interpretation": f"Previous successful uses: {int(features['user_skill_familiarity'])}",
            },
        }

        return explanations


def get_predictor(db_path: Path | None = None) -> SkillSuccessPredictor:
    """Get or create skill success predictor instance.

    Args:
        db_path: Path to database file. Defaults to
            `.session-buddy/skills.db` in current directory.

    Returns:
        SkillSuccessPredictor instance
    """
    if db_path is None:
        db_path = Path.cwd() / ".session-buddy" / "skills.db"

    return SkillSuccessPredictor(db_path=db_path)
