"""Configuration for category evolution behavior.

This module provides configuration classes for controlling how category
evolution behaves, including temporal decay settings, quality thresholds,
and clustering parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class EvolutionConfig:
    """Configuration for category evolution behavior.

    Attributes:
        temporal_decay_enabled: Whether to apply temporal decay to remove stale subcategories
        temporal_decay_days: Number of days of inactivity before a subcategory is considered stale
        decay_access_threshold: Minimum access count below which subcategories are decay candidates
        archive_option: If True, archive stale subcategories; if False, delete them
        min_silhouette_score: Minimum acceptable silhouette score (below this, evolution is questionable)

        # Cluster settings
        min_cluster_size: Minimum memories required to form a subcategory
        max_clusters: Maximum number of subcategories per top-level category
        similarity_threshold: Minimum cosine similarity for subcategory assignment
        fingerprint_threshold: MinHash similarity threshold for pre-filtering
    """

    # Temporal decay settings
    temporal_decay_enabled: bool = True
    temporal_decay_days: int = 90
    decay_access_threshold: int = 5
    archive_option: bool = False  # If False, delete; if True, archive

    # Quality thresholds
    min_silhouette_score: float = 0.2

    # Cluster settings
    min_cluster_size: int = 3
    max_clusters: int = 10
    similarity_threshold: float = 0.75
    fingerprint_threshold: float = 0.90

    def validate(self) -> list[str]:
        """Validate configuration settings.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if self.temporal_decay_days < 1:
            errors.append("temporal_decay_days must be >= 1")

        if self.decay_access_threshold < 0:
            errors.append("decay_access_threshold must be >= 0")

        if not 0 <= self.min_silhouette_score <= 1:
            errors.append("min_silhouette_score must be between 0 and 1")

        if self.min_cluster_size < 1:
            errors.append("min_cluster_size must be >= 1")

        if self.max_clusters < 1:
            errors.append("max_clusters must be >= 1")

        if not 0 <= self.similarity_threshold <= 1:
            errors.append("similarity_threshold must be between 0 and 1")

        if not 0 <= self.fingerprint_threshold <= 1:
            errors.append("fingerprint_threshold must be between 0 and 1")

        if self.min_cluster_size > self.max_clusters:
            errors.append("min_cluster_size cannot exceed max_clusters")

        return errors


@dataclass
class DecayResult:
    """Results from applying temporal decay to subcategories.

    Attributes:
        removed_count: Number of subcategories removed
        archived: Whether subcategories were archived (True) or deleted (False)
        freed_space: Estimated bytes freed from storage
        message: Human-readable description of what happened
        timestamp: When the decay operation completed
        decayed_subcategories: List of names of decayed subcategories
    """

    removed_count: int
    archived: bool
    freed_space: int
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    decayed_subcategories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of decay results
        """
        return {
            "removed_count": self.removed_count,
            "archived": self.archived,
            "freed_space": self.freed_space,
            "freed_space_human": _format_bytes(self.freed_space),
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "decayed_subcategories": self.decayed_subcategories,
        }


def _format_bytes(bytes_count: int) -> str:
    """Format bytes as human-readable string.

    Args:
        bytes_count: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 KB", "2.3 MB")
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_count < 1024:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f} TB"


@dataclass
class EvolutionSnapshot:
    """Snapshot of category evolution results.

    Captures before/after state to track evolution quality over time.

    Attributes:
        id: Unique snapshot identifier
        category: Top-level category that was evolved
        before_state: Dictionary with before-state metrics
        after_state: Dictionary with after-state metrics
        decay_results: Dictionary with temporal decay results
        duration_ms: How long the evolution took in milliseconds
        timestamp: When the snapshot was created
    """

    id: str
    category: str
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    decay_results: dict[str, Any]
    duration_ms: float
    timestamp: datetime

    def improvement_summary(self) -> str:
        """Generate human-readable summary of evolution impact.

        Returns:
            Human-readable description of what changed
        """
        silhouette_delta = (
            self.after_state.get("silhouette", 0) -
            self.before_state.get("silhouette", 0)
        )

        # Interpret silhouette score change
        if silhouette_delta > 0.1:
            level = "Significant improvement"
        elif silhouette_delta > 0:
            level = "Moderate improvement"
        elif silhouette_delta > -0.1:
            level = "Minor change (acceptable)"
        else:
            level = f"Quality decreased: {silhouette_delta:.2f} ⚠️"

        # Subcategory count change
        count_delta = (
            self.after_state.get("subcategory_count", 0) -
            self.before_state.get("subcategory_count", 0)
        )

        count_change = ""
        if count_delta > 0:
            count_change = f"Created {count_delta} subcategories"
        elif count_delta < 0:
            count_change = f"Removed {abs(count_delta)} subcategories"
        else:
            count_change = "Maintained subcategory count"

        # Storage freed
        freed = self.decay_results.get("bytes_freed", 0)
        storage = f" freed {_format_bytes(freed)}" if freed > 0 else ""

        return f"{level} (silhouette: {silhouette_delta:+.2f}), {count_change},{storage}."

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage.

        Returns:
            Dictionary representation suitable for database insertion
        """
        return {
            "id": self.id,
            "category": self.category,
            "before_subcategory_count": self.before_state.get("subcategory_count", 0),
            "before_silhouette": self.before_state.get("silhouette"),
            "before_total_memories": self.before_state.get("total_memories", 0),
            "after_subcategory_count": self.after_state.get("subcategory_count", 0),
            "after_silhouette": self.after_state.get("silhouette"),
            "after_total_memories": self.after_state.get("total_memories", 0),
            "decayed_count": self.decay_results.get("removed_count", 0),
            "archived_count": self.decay_results.get("archived_count", 0),
            "bytes_freed": self.decay_results.get("freed_space", 0),
            "evolution_duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }
