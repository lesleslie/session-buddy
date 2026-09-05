from __future__ import annotations

from datetime import UTC, datetime, timedelta

from session_buddy.memory.evolution_config import (
    DecayResult,
    EvolutionConfig,
    EvolutionSnapshot,
    _format_bytes,
)


class TestEvolutionConfigValidation:
    """Tests for EvolutionConfig.validate()."""

    def test_defaults_are_valid(self) -> None:
        cfg = EvolutionConfig()
        assert cfg.validate() == []

    def test_temporal_decay_days_must_be_positive(self) -> None:
        cfg = EvolutionConfig(temporal_decay_days=0)
        errors = cfg.validate()
        assert any("temporal_decay_days" in e for e in errors)

        cfg = EvolutionConfig(temporal_decay_days=-5)
        errors = cfg.validate()
        assert any("temporal_decay_days" in e for e in errors)

    def test_decay_access_threshold_must_be_non_negative(self) -> None:
        cfg = EvolutionConfig(decay_access_threshold=-1)
        errors = cfg.validate()
        assert any("decay_access_threshold" in e for e in errors)

    def test_decay_access_threshold_zero_allowed(self) -> None:
        cfg = EvolutionConfig(decay_access_threshold=0)
        assert cfg.validate() == []

    def test_min_silhouette_score_bounds(self) -> None:
        assert any(
            "min_silhouette_score" in e
            for e in EvolutionConfig(min_silhouette_score=-0.1).validate()
        )
        assert any(
            "min_silhouette_score" in e
            for e in EvolutionConfig(min_silhouette_score=1.1).validate()
        )

    def test_min_silhouette_score_edges(self) -> None:
        # Both 0.0 and 1.0 are valid inclusive endpoints.
        assert EvolutionConfig(min_silhouette_score=0.0).validate() == []
        assert EvolutionConfig(min_silhouette_score=1.0).validate() == []

    def test_min_cluster_size_must_be_positive(self) -> None:
        cfg = EvolutionConfig(min_cluster_size=0)
        assert any("min_cluster_size" in e for e in cfg.validate())

    def test_max_clusters_must_be_positive(self) -> None:
        cfg = EvolutionConfig(max_clusters=0)
        assert any("max_clusters" in e for e in cfg.validate())

    def test_similarity_threshold_bounds(self) -> None:
        assert any(
            "similarity_threshold" in e
            for e in EvolutionConfig(similarity_threshold=-0.5).validate()
        )
        assert any(
            "similarity_threshold" in e
            for e in EvolutionConfig(similarity_threshold=1.5).validate()
        )

    def test_fingerprint_threshold_bounds(self) -> None:
        assert any(
            "fingerprint_threshold" in e
            for e in EvolutionConfig(fingerprint_threshold=-0.5).validate()
        )
        assert any(
            "fingerprint_threshold" in e
            for e in EvolutionConfig(fingerprint_threshold=1.5).validate()
        )

    def test_min_cluster_size_cannot_exceed_max_clusters(self) -> None:
        cfg = EvolutionConfig(min_cluster_size=10, max_clusters=5)
        assert any(
            "min_cluster_size" in e and "max_clusters" in e
            for e in cfg.validate()
        )

    def test_min_cluster_size_equal_to_max_clusters_allowed(self) -> None:
        cfg = EvolutionConfig(min_cluster_size=5, max_clusters=5)
        assert cfg.validate() == []

    def test_accumulates_multiple_errors(self) -> None:
        cfg = EvolutionConfig(
            temporal_decay_days=0,
            decay_access_threshold=-1,
            min_silhouette_score=2.0,
            min_cluster_size=0,
            max_clusters=0,
        )
        errors = cfg.validate()
        # At least one error per failing field.
        assert len(errors) >= 5


class TestFormatBytes:
    """Tests for the _format_bytes helper."""

    def test_bytes(self) -> None:
        assert _format_bytes(500) == "500.0 B"
        assert _format_bytes(0) == "0.0 B"

    def test_kilobytes(self) -> None:
        result = _format_bytes(2048)
        assert "KB" in result
        assert result.startswith("2.0")

    def test_megabytes(self) -> None:
        result = _format_bytes(2 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self) -> None:
        result = _format_bytes(1.5 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_terabytes(self) -> None:
        # Anything larger than 1 TB crosses all thresholds and lands in the
        # fallback TB branch.
        result = _format_bytes(2 * 1024 * 1024 * 1024 * 1024)
        assert "TB" in result


class TestDecayResult:
    """Tests for the DecayResult dataclass."""

    def test_required_fields_only(self) -> None:
        r = DecayResult(
            removed_count=0,
            archived=False,
            freed_space=0,
            message="nothing to do",
        )
        assert r.removed_count == 0
        assert r.archived is False
        assert r.message == "nothing to do"
        assert r.decayed_subcategories == []
        assert isinstance(r.timestamp, datetime)
        # The default timestamp is timezone-aware (UTC).
        assert r.timestamp.tzinfo is not None
        # Timestamp was just created — must be very recent.
        assert (datetime.now(UTC) - r.timestamp) < timedelta(seconds=5)

    def test_to_dict_shape(self) -> None:
        r = DecayResult(
            removed_count=3,
            archived=True,
            freed_space=5120,
            message="archived 3",
            decayed_subcategories=["a", "b", "c"],
        )
        d = r.to_dict()
        assert d["removed_count"] == 3
        assert d["archived"] is True
        assert d["freed_space"] == 5120
        assert "KB" in d["freed_space_human"]
        assert d["message"] == "archived 3"
        assert d["decayed_subcategories"] == ["a", "b", "c"]
        assert isinstance(d["timestamp"], str)

    def test_to_dict_bytes_format_for_each_unit(self) -> None:
        # Bytes branch
        d_b = DecayResult(0, False, 100, "m").to_dict()
        assert d_b["freed_space_human"].endswith("B")
        # KB branch
        d_kb = DecayResult(0, False, 5 * 1024, "m").to_dict()
        assert "KB" in d_kb["freed_space_human"]
        # MB branch
        d_mb = DecayResult(0, False, 5 * 1024 * 1024, "m").to_dict()
        assert "MB" in d_mb["freed_space_human"]
        # GB branch
        d_gb = DecayResult(0, False, 2 * 1024 * 1024 * 1024, "m").to_dict()
        assert "GB" in d_gb["freed_space_human"]


class TestEvolutionSnapshot:
    """Tests for EvolutionSnapshot.improvement_summary() and to_dict()."""

    def _make(self) -> EvolutionSnapshot:
        return EvolutionSnapshot(
            id="snap-1",
            category="skills",
            before_state={
                "subcategory_count": 2,
                "silhouette": 0.3,
                "total_memories": 100,
            },
            after_state={
                "subcategory_count": 3,
                "silhouette": 0.45,
                "total_memories": 120,
            },
            decay_results={"removed_count": 1, "archived_count": 0, "freed_space": 2048},
            duration_ms=150.0,
            timestamp=datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC),
        )

    def test_improvement_summary_significant_improvement(self) -> None:
        snap = EvolutionSnapshot(
            id="snap-1",
            category="skills",
            before_state={
                "subcategory_count": 2,
                "silhouette": 0.3,
                "total_memories": 100,
            },
            after_state={
                "subcategory_count": 3,
                "silhouette": 0.45,
                "total_memories": 120,
            },
            # improvement_summary reads "freed_space" from decay_results
            # — the canonical key produced by DecayResult.to_dict().
            # ``EvolutionSnapshot.to_dict()`` later renames the key to
            # ``bytes_freed`` for the DB column, but the runtime dict
            # this summary consumes still has ``freed_space``.
            decay_results={
                "removed_count": 1,
                "archived_count": 0,
                "freed_space": 2048,
            },
            duration_ms=150.0,
            timestamp=datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC),
        )
        # silhouette delta = 0.15 > 0.1 → "Significant improvement"
        text = snap.improvement_summary()
        assert "Significant improvement" in text
        # Created 1 subcategory
        assert "Created 1 subcategories" in text
        # Freed 2 KB
        assert "2.0 KB" in text
        assert text.endswith(".")

    def test_improvement_summary_quality_decreased_branch(self) -> None:
        snap = EvolutionSnapshot(
            id="snap-2",
            category="facts",
            before_state={"silhouette": 0.6, "subcategory_count": 5},
            after_state={"silhouette": 0.3, "subcategory_count": 3},
            decay_results={"removed_count": 2, "archived_count": 0, "freed_space": 0},
            duration_ms=10.0,
            timestamp=datetime.now(UTC),
        )
        text = snap.improvement_summary()
        assert "Quality decreased" in text
        assert "Removed" in text

    def test_improvement_summary_minor_change(self) -> None:
        snap = EvolutionSnapshot(
            id="snap-3",
            category="context",
            before_state={"silhouette": 0.5, "subcategory_count": 4},
            after_state={"silhouette": 0.45, "subcategory_count": 4},
            decay_results={"removed_count": 0, "archived_count": 0, "freed_space": 0},
            duration_ms=10.0,
            timestamp=datetime.now(UTC),
        )
        text = snap.improvement_summary()
        # delta = -0.05, which falls in the (-0.1, 0.0) bucket → "Minor change".
        assert "Minor change" in text
        assert "Maintained subcategory count" in text

    def test_improvement_summary_moderate_improvement(self) -> None:
        snap = EvolutionSnapshot(
            id="snap-4",
            category="preferences",
            before_state={"silhouette": 0.4, "subcategory_count": 1},
            after_state={"silhouette": 0.45, "subcategory_count": 3},
            decay_results={"removed_count": 0, "archived_count": 0, "freed_space": 0},
            duration_ms=10.0,
            timestamp=datetime.now(UTC),
        )
        text = snap.improvement_summary()
        assert "Moderate improvement" in text

    def test_to_dict_shape(self) -> None:
        snap = self._make()
        d = snap.to_dict()
        assert d["id"] == "snap-1"
        assert d["category"] == "skills"
        assert d["before_subcategory_count"] == 2
        assert d["before_silhouette"] == 0.3
        assert d["before_total_memories"] == 100
        assert d["after_subcategory_count"] == 3
        assert d["after_silhouette"] == 0.45
        assert d["after_total_memories"] == 120
        assert d["decayed_count"] == 1
        assert d["archived_count"] == 0
        assert d["bytes_freed"] == 2048
        assert d["evolution_duration_ms"] == 150.0
        assert isinstance(d["timestamp"], str)

    def test_to_dict_missing_keys_default_to_zero(self) -> None:
        snap = EvolutionSnapshot(
            id="snap-empty",
            category="rules",
            before_state={},
            after_state={},
            decay_results={},
            duration_ms=0.0,
            timestamp=datetime.now(UTC),
        )
        d = snap.to_dict()
        assert d["before_subcategory_count"] == 0
        assert d["before_silhouette"] is None
        assert d["decayed_count"] == 0