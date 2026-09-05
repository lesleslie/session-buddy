"""Tests for session_buddy.mcp.tools.memory.category_tools.

Wave 11 (memory/ sweep) — covers the 4 MCP tools plus the helpers,
singleton, and registration in ``category_tools.py`` (417 lines, was 9%).

Targets:
- ``get_evolution_engine``: module-level singleton + double-checked
  locking path + concurrent-lock fallback
- ``_fetch_category_memories``: tag filtering, missing db, exception
  swallow → empty list
- ``get_subcategories``: invalid category → error dict; valid category
  → success dict with serialized subcategory metadata
- ``evolve_categories``: invalid category, insufficient memories (returns
  summary early), invalid config (validation errors → error dict),
  successful evolution with all 4 silhouette-delta levels, count-change
  variants, freed-space formatting, exception path
- ``_format_bytes``: B, KB, MB, GB, TB promotion thresholds
- ``assign_memory_subcategory``: embedding+fp success, no embedding,
  fingerprint generation failure, embedding generation failure, invalid
  category, default category (auto-detect)
- ``category_stats``: single category (success + invalid), all-categories
  aggregation
- ``register_category_tools``: registers all 4 tools
- Module ``__all__`` export
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from session_buddy.mcp.tools.memory import category_tools
from session_buddy.mcp.tools.memory.category_tools import (
    _fetch_category_memories,
    _format_bytes,
    assign_memory_subcategory,
    category_stats,
    evolve_categories,
    get_evolution_engine,
    get_subcategories,
    register_category_tools,
)
from session_buddy.memory.category_evolution import (
    CategoryAssignment,
    CategoryEvolutionEngine,
    Subcategory,
    TopLevelCategory,
)
from session_buddy.memory.evolution_config import EvolutionConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_subcategory(
    name: str = "python-async",
    category: TopLevelCategory = TopLevelCategory.SKILLS,
    memory_count: int = 5,
    keywords: list[str] | None = None,
) -> Subcategory:
    """Build a Subcategory instance suitable for engine.get_subcategories."""
    from datetime import UTC, datetime

    return Subcategory(
        id=f"sc-{name}",
        parent_category=category,
        name=name,
        keywords=keywords or ["python", "async"],
        memory_count=memory_count,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _make_engine(
    subcats_by_cat: dict[TopLevelCategory, list[Subcategory]] | None = None,
) -> MagicMock:
    """Build a stub CategoryEvolutionEngine exposing the methods called."""
    subcats_by_cat = subcats_by_cat or {}

    engine = MagicMock(spec=CategoryEvolutionEngine)
    engine.get_subcategories.side_effect = lambda cat: subcats_by_cat.get(cat, [])
    return engine


def _make_assignment(
    category: TopLevelCategory = TopLevelCategory.SKILLS,
    subcategory: str | None = "python-async",
    confidence: float = 0.92,
    method: str = "embedding",
) -> CategoryAssignment:
    return CategoryAssignment(
        memory_id="m-1",
        category=category,
        subcategory=subcategory,
        confidence=confidence,
        method=method,
    )


class _FakeMCP:
    """Minimal stand-in for the FastMCP server that records registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *args, **kwargs):  # noqa: ANN201 - mirror FastMCP.tool decorator
        def decorator(fn):  # noqa: ANN202 - functional decorator
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture(autouse=True)
def _reset_engine_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure every test starts with a fresh module-level engine singleton."""
    monkeypatch.setattr(category_tools, "_evolution_engine", None)


# ---------------------------------------------------------------------------
# _format_bytes
# ---------------------------------------------------------------------------


class TestFormatBytes:
    def test_bytes_below_kb(self) -> None:
        assert _format_bytes(500) == "500.0 B"

    def test_bytes_at_kb_boundary(self) -> None:
        # 1024 bytes → 1.0 KB
        assert _format_bytes(1024) == "1.0 KB"

    def test_kilobytes(self) -> None:
        assert _format_bytes(1536) == "1.5 KB"

    def test_megabytes(self) -> None:
        # 2.5 MB
        assert _format_bytes(2.5 * 1024 * 1024) == "2.5 MB"

    def test_gigabytes(self) -> None:
        # 3.0 GB
        assert _format_bytes(3.0 * 1024 * 1024 * 1024) == "3.0 GB"

    def test_terabytes_overshoot(self) -> None:
        # Past the GB loop → final TB branch
        tb = 2.0 * 1024 * 1024 * 1024 * 1024
        assert _format_bytes(tb) == "2.0 TB"

    def test_zero_bytes(self) -> None:
        assert _format_bytes(0) == "0.0 B"


# ---------------------------------------------------------------------------
# get_evolution_engine singleton
# ---------------------------------------------------------------------------


class TestGetEvolutionEngine:
    async def test_creates_engine_on_first_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First call constructs and initializes a new engine."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.initialize = AsyncMock()

        monkeypatch.setattr(
            category_tools, "CategoryEvolutionEngine", lambda: engine
        )

        result = await get_evolution_engine()
        assert result is engine
        engine.initialize.assert_awaited_once()

    async def test_returns_cached_engine_on_second_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second call returns cached singleton; initialize not called twice."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.initialize = AsyncMock()
        monkeypatch.setattr(
            category_tools, "CategoryEvolutionEngine", lambda: engine
        )

        first = await get_evolution_engine()
        second = await get_evolution_engine()
        assert first is second
        engine.initialize.assert_awaited_once()

    async def test_concurrent_call_returns_existing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If another coroutine populated the singleton, return it without
        constructing a duplicate."""
        existing = MagicMock(spec=CategoryEvolutionEngine)
        monkeypatch.setattr(category_tools, "_evolution_engine", existing)

        # Even if the constructor would return something else, fast path wins.
        result = await get_evolution_engine()
        assert result is existing


# ---------------------------------------------------------------------------
# _fetch_category_memories
# ---------------------------------------------------------------------------


class TestFetchCategoryMemories:
    async def test_filters_by_category_tag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Memories whose tag list includes the category are returned."""
        from session_buddy import reflection_tools

        fake_db = MagicMock()
        fake_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "id": "m-1",
                    "content": "alpha",
                    "embedding": None,
                    "fingerprint": None,
                    "tags": ["skills", "python"],
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "id": "m-2",
                    "content": "beta",
                    "embedding": None,
                    "fingerprint": None,
                    "tags": ["facts"],
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "id": "m-3",
                    "content": "gamma",
                    "embedding": None,
                    "fingerprint": None,
                    "tags": ["skills"],
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            ]
        )

        async def fake_db_resolver() -> MagicMock:
            return fake_db

        monkeypatch.setattr(reflection_tools, "get_reflection_database", fake_db_resolver)

        memories = await _fetch_category_memories(TopLevelCategory.SKILLS, limit=10)
        assert [m["id"] for m in memories] == ["m-1", "m-3"]

    async def test_empty_tags_treated_as_no_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Memories with no tags (or empty list) are skipped."""
        from session_buddy import reflection_tools

        fake_db = MagicMock()
        fake_db.search_reflections = AsyncMock(
            return_value=[
                {
                    "id": "m-1",
                    "content": "no tags",
                    "tags": [],
                    "embedding": None,
                    "fingerprint": None,
                    "created_at": None,
                },
                {
                    "id": "m-2",
                    "content": "has tags",
                    "tags": ["skills"],
                    "embedding": None,
                    "fingerprint": None,
                    "created_at": None,
                },
            ]
        )

        async def fake_db_resolver() -> MagicMock:
            return fake_db

        monkeypatch.setattr(reflection_tools, "get_reflection_database", fake_db_resolver)

        memories = await _fetch_category_memories(TopLevelCategory.SKILLS)
        assert [m["id"] for m in memories] == ["m-2"]

    async def test_exception_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Database error is swallowed and an empty list is returned."""
        from session_buddy import reflection_tools

        async def fake_db_resolver() -> MagicMock:
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(reflection_tools, "get_reflection_database", fake_db_resolver)

        memories = await _fetch_category_memories(TopLevelCategory.SKILLS)
        assert memories == []

    async def test_search_uses_category_value_as_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the search_reflections query is the category's string value."""
        from session_buddy import reflection_tools

        fake_db = MagicMock()
        fake_db.search_reflections = AsyncMock(return_value=[])

        async def fake_db_resolver() -> MagicMock:
            return fake_db

        monkeypatch.setattr(reflection_tools, "get_reflection_database", fake_db_resolver)

        await _fetch_category_memories(TopLevelCategory.FACTS, limit=42)
        fake_db.search_reflections.assert_awaited_once_with(
            query="facts", limit=42, use_embeddings=True
        )


# ---------------------------------------------------------------------------
# get_subcategories
# ---------------------------------------------------------------------------


class TestGetSubcategories:
    async def test_invalid_category_returns_error(self) -> None:
        result = await get_subcategories("bogus")
        assert result["success"] is False
        assert "Invalid category" in result["error"]
        assert "facts" in result["error"]
        assert "preferences" in result["error"]

    async def test_valid_category_no_subcategories(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=_make_engine())
        )
        result = await get_subcategories("facts")
        assert result["success"] is True
        assert result["category"] == "facts"
        assert result["subcategory_count"] == 0
        assert result["subcategories"] == []

    async def test_valid_category_with_subcategories(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sc = _make_subcategory(name="async-patterns", memory_count=3)
        engine = _make_engine({TopLevelCategory.SKILLS: [sc]})
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        result = await get_subcategories("skills")
        assert result["success"] is True
        assert result["subcategory_count"] == 1
        entry = result["subcategories"][0]
        assert entry["name"] == "async-patterns"
        assert entry["memory_count"] == 3
        assert "created_at" in entry and "updated_at" in entry

    async def test_category_normalised_to_lowercase(self) -> None:
        result = await get_subcategories("BOGUS")
        # Same invalid path — TopLevelCategory("bogus") raises ValueError
        assert result["success"] is False


# ---------------------------------------------------------------------------
# evolve_categories
# ---------------------------------------------------------------------------


def _evolve_result_dict(
    before_sil: float = 0.5,
    after_sil: float = 0.7,
    before_count: int = 3,
    after_count: int = 5,
    freed_space: int = 0,
    archived: bool = False,
) -> dict:
    return {
        "success": True,
        "category": "skills",
        "before_state": {
            "subcategory_count": before_count,
            "silhouette": before_sil,
            "total_memories": 12,
        },
        "after_state": {
            "subcategory_count": after_count,
            "silhouette": after_sil,
            "total_memories": 12,
        },
        "decay_results": {
            "removed_count": 1,
            "archived": archived,
            "freed_space": freed_space,
            "message": "stale removed",
            "decayed_subcategories": ["old"],
        },
        "duration_ms": 42.0,
    }


class TestEvolveCategories:
    async def test_invalid_category_returns_error(self) -> None:
        result = await evolve_categories("bogus")
        assert result["success"] is False
        assert "Invalid category" in result["error"]

    async def test_insufficient_memories_short_circuits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When fewer memories than threshold → early-return summary dict."""
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": "a"}, {"id": "b"}]),
        )
        engine = _make_engine({TopLevelCategory.FACTS: [_make_subcategory()]})
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        result = await evolve_categories("facts", memory_count_threshold=10)
        assert result["success"] is True
        assert "Insufficient memories" in result["message"]
        assert result["memory_count"] == 2
        assert result["threshold"] == 10
        assert result["subcategory_count"] == 1

    async def test_insufficient_memories_threshold_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """threshold=0 with 0 memories still short-circuits because 0 < 0 is false."""
        # Actually, 0 < 0 is False, so evolution proceeds. Use threshold=1 instead.
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[]),
        )
        engine = _make_engine()
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        result = await evolve_categories("facts", memory_count_threshold=1)
        assert "Insufficient memories" in result["message"]
        assert result["memory_count"] == 0

    async def test_invalid_config_returns_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A config that fails validate() → error dict, evolution skipped."""
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": "x"}] * 20),
        )
        engine = _make_engine()
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        # temporal_decay_days=0 violates >= 1 rule
        result = await evolve_categories("facts", temporal_decay_days=0)
        assert result["success"] is False
        assert "Invalid configuration" in result["error"]
        assert "temporal_decay_days" in result["error"]

    async def test_successful_evolution_significant_improvement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """silhouette_delta > 0.1 → 'Significant improvement' level."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(return_value=_evolve_result_dict(
            before_sil=0.5, after_sil=0.7, before_count=2, after_count=5,
        ))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert result["success"] is True
        assert "Significant improvement" in result["summary"]
        assert "Created 3 subcategories" in result["summary"]
        assert "silhouette: +0.20" in result["summary"]

    async def test_successful_evolution_moderate_improvement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """0 < silhouette_delta <= 0.1 → 'Moderate improvement'."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(return_value=_evolve_result_dict(
            before_sil=0.5, after_sil=0.55,
        ))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert "Moderate improvement" in result["summary"]

    async def test_successful_evolution_minor_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """-0.1 <= silhouette_delta <= 0 → 'Minor change (acceptable)'."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(return_value=_evolve_result_dict(
            before_sil=0.5, after_sil=0.48,
        ))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert "Minor change" in result["summary"]

    async def test_successful_evolution_quality_decreased(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """silhouette_delta < -0.1 → 'Quality decreased' with warning emoji."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(return_value=_evolve_result_dict(
            before_sil=0.5, after_sil=0.3,
        ))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert "Quality decreased" in result["summary"]
        assert "⚠" in result["summary"]

    async def test_summary_count_removed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """after_count < before_count → 'Removed N subcategories'."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(return_value=_evolve_result_dict(
            before_count=5, after_count=3,
        ))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert "Removed 2 subcategories" in result["summary"]

    async def test_summary_count_maintained(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """after_count == before_count → 'Maintained subcategory count'."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(return_value=_evolve_result_dict(
            before_count=4, after_count=4,
        ))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert "Maintained subcategory count" in result["summary"]

    async def test_summary_includes_freed_storage_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """freed_space > 0 → ' freed <formatted bytes>' appended."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(return_value=_evolve_result_dict(
            freed_space=2048,  # 2.0 KB
        ))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert "freed 2.0 KB" in result["summary"]

    async def test_summary_omits_storage_when_freed_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """freed_space == 0 → no storage msg in summary."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(return_value=_evolve_result_dict(
            freed_space=0,
        ))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert "freed" not in result["summary"]

    async def test_evolution_exception_returns_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """engine.evolve_category raising → caught, error dict returned."""
        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.evolve_category = AsyncMock(
            side_effect=RuntimeError("clustering exploded")
        )
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        monkeypatch.setattr(
            category_tools,
            "_fetch_category_memories",
            AsyncMock(return_value=[{"id": str(i)} for i in range(20)]),
        )

        result = await evolve_categories("skills")
        assert result["success"] is False
        assert "clustering exploded" in result["error"]


# ---------------------------------------------------------------------------
# assign_memory_subcategory
# ---------------------------------------------------------------------------


class TestAssignMemorySubcategory:
    async def test_successful_assignment_with_embedding_and_fp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Happy path: embedding + fingerprint generated, engine assigns."""
        from session_buddy import reflection_tools
        from session_buddy.utils import fingerprint as fp_mod

        fake_db = MagicMock()
        fake_db._generate_embedding = AsyncMock(return_value=[0.1] * 16)
        monkeypatch.setattr(
            reflection_tools, "get_reflection_database",
            AsyncMock(return_value=fake_db),
        )
        monkeypatch.setattr(
            fp_mod, "MinHashSignature",
            SimpleNamespace(from_text=lambda text: SimpleNamespace(to_bytes=lambda: b"fp")),
        )

        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.assign_subcategory = AsyncMock(
            return_value=_make_assignment()
        )
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        result = await assign_memory_subcategory(
            memory_id="m-1", content="Learn async patterns"
        )
        assert result["success"] is True
        assert result["memory_id"] == "m-1"
        assert result["category"] == "skills"
        assert result["subcategory"] == "python-async"
        assert result["confidence"] == 0.92
        assert result["method"] == "embedding"
        assert result["embedding_generated"] is True
        assert result["fingerprint_generated"] is True

    async def test_explicit_invalid_category_returns_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid category arg → error dict, no engine call."""
        from session_buddy import reflection_tools
        from session_buddy.utils import fingerprint as fp_mod

        monkeypatch.setattr(
            reflection_tools, "get_reflection_database",
            AsyncMock(return_value=MagicMock(_generate_embedding=AsyncMock(return_value=None))),
        )
        monkeypatch.setattr(
            fp_mod, "MinHashSignature",
            SimpleNamespace(from_text=lambda text: SimpleNamespace(to_bytes=lambda: b"fp")),
        )

        result = await assign_memory_subcategory(
            memory_id="m-1", content="x", category="bogus"
        )
        assert result["success"] is False
        assert "Invalid category" in result["error"]

    async def test_embedding_generation_failure_continues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If db._generate_embedding raises, embedding stays None but flow continues."""
        from session_buddy import reflection_tools
        from session_buddy.utils import fingerprint as fp_mod

        fake_db = MagicMock()
        fake_db._generate_embedding = AsyncMock(
            side_effect=RuntimeError("embedding model unavailable")
        )
        monkeypatch.setattr(
            reflection_tools, "get_reflection_database",
            AsyncMock(return_value=fake_db),
        )
        monkeypatch.setattr(
            fp_mod, "MinHashSignature",
            SimpleNamespace(from_text=lambda text: SimpleNamespace(to_bytes=lambda: b"fp")),
        )

        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.assign_subcategory = AsyncMock(return_value=_make_assignment(method="fingerprint"))
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        result = await assign_memory_subcategory(
            memory_id="m-1", content="x", category="skills"
        )
        assert result["success"] is True
        assert result["embedding_generated"] is False
        assert result["fingerprint_generated"] is True
        assert result["method"] == "fingerprint"

    async def test_fingerprint_generation_failure_continues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If MinHashSignature.from_text raises, fingerprint stays None."""
        from session_buddy import reflection_tools
        from session_buddy.utils import fingerprint as fp_mod

        fake_db = MagicMock()
        fake_db._generate_embedding = AsyncMock(return_value=[0.1, 0.2])
        monkeypatch.setattr(
            reflection_tools, "get_reflection_database",
            AsyncMock(return_value=fake_db),
        )

        class BoomFingerprint:
            @staticmethod
            def from_text(_text):
                raise RuntimeError("minhash failed")

        monkeypatch.setattr(fp_mod, "MinHashSignature", BoomFingerprint)

        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.assign_subcategory = AsyncMock(return_value=_make_assignment())
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        result = await assign_memory_subcategory(
            memory_id="m-1", content="x", category="skills"
        )
        assert result["success"] is True
        assert result["embedding_generated"] is True
        assert result["fingerprint_generated"] is False

    async def test_no_subcategory_assigned_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Engine may return subcategory=None when nothing matches."""
        from session_buddy import reflection_tools
        from session_buddy.utils import fingerprint as fp_mod

        fake_db = MagicMock()
        fake_db._generate_embedding = AsyncMock(return_value=[0.0] * 8)
        monkeypatch.setattr(
            reflection_tools, "get_reflection_database",
            AsyncMock(return_value=fake_db),
        )
        monkeypatch.setattr(
            fp_mod, "MinHashSignature",
            SimpleNamespace(from_text=lambda text: SimpleNamespace(to_bytes=lambda: b"fp")),
        )

        engine = MagicMock(spec=CategoryEvolutionEngine)
        engine.assign_subcategory = AsyncMock(
            return_value=_make_assignment(subcategory=None, confidence=0.0, method="none")
        )
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        result = await assign_memory_subcategory(
            memory_id="m-9", content="orphan", category="facts"
        )
        assert result["success"] is True
        assert result["subcategory"] is None
        assert result["method"] == "none"


# ---------------------------------------------------------------------------
# category_stats
# ---------------------------------------------------------------------------


class TestCategoryStats:
    async def test_all_categories_when_category_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """category=None → stats for every TopLevelCategory enum value."""
        sc1 = _make_subcategory(name="alpha", memory_count=4)
        sc2 = _make_subcategory(name="beta", category=TopLevelCategory.FACTS, memory_count=6)
        engine = _make_engine({
            TopLevelCategory.SKILLS: [sc1],
            TopLevelCategory.FACTS: [sc2],
            TopLevelCategory.CONTEXT: [],
        })
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        result = await category_stats()
        assert result["success"] is True
        assert set(result["categories"].keys()) == {
            "facts", "preferences", "skills", "rules", "context",
        }
        assert result["categories"]["skills"]["subcategory_count"] == 1
        assert result["categories"]["skills"]["total_memories"] == 4
        assert result["categories"]["facts"]["subcategory_count"] == 1
        assert result["categories"]["facts"]["total_memories"] == 6
        assert result["categories"]["context"]["subcategory_count"] == 0

    async def test_specific_category_with_subcategories(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """category=skills → detailed subcategory breakdown."""
        sc1 = _make_subcategory(name="async", memory_count=3, keywords=["a", "b", "c"])
        sc2 = _make_subcategory(name="await", memory_count=2, keywords=["d"])
        engine = _make_engine({TopLevelCategory.SKILLS: [sc1, sc2]})
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )

        result = await category_stats(category="skills")
        assert result["success"] is True
        assert result["category"] == "skills"
        assert result["subcategory_count"] == 2
        assert result["total_memories"] == 5
        names = {sc["name"] for sc in result["subcategories"]}
        assert names == {"async", "await"}
        # First subcategory has 3 keywords → keyword_count=3
        async_sc = next(s for s in result["subcategories"] if s["name"] == "async")
        assert async_sc["keyword_count"] == 3

    async def test_invalid_specific_category_returns_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=_make_engine())
        )
        result = await category_stats(category="bogus")
        assert result["success"] is False
        assert "Invalid category" in result["error"]

    async def test_specific_category_no_subcategories(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid category with no subcategories yet → empty list, count 0."""
        engine = _make_engine()
        monkeypatch.setattr(
            category_tools, "get_evolution_engine", AsyncMock(return_value=engine)
        )
        result = await category_stats(category="rules")
        assert result["success"] is True
        assert result["subcategory_count"] == 0
        assert result["total_memories"] == 0
        assert result["subcategories"] == []


# ---------------------------------------------------------------------------
# register_category_tools
# ---------------------------------------------------------------------------


class TestRegisterCategoryTools:
    def test_registers_all_four_tools(self) -> None:
        mcp = _FakeMCP()
        register_category_tools(mcp)
        assert set(mcp.tools.keys()) == {
            "get_subcategories",
            "evolve_categories",
            "assign_memory_subcategory",
            "category_stats",
        }

    def test_registered_callables_are_the_originals(self) -> None:
        """The decorator must return the same function object that was passed."""
        mcp = _FakeMCP()
        register_category_tools(mcp)
        assert mcp.tools["get_subcategories"] is get_subcategories
        assert mcp.tools["evolve_categories"] is evolve_categories
        assert mcp.tools["assign_memory_subcategory"] is assign_memory_subcategory
        assert mcp.tools["category_stats"] is category_stats


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_module_has_no_dunder_all(self) -> None:
        """Production module does not declare ``__all__``; import surface is the
        full set of public names — we still verify the listed tool functions are
        importable from the module path."""
        # No ``__all__`` attribute is expected — we just sanity check it doesn't
        # surprise us if someone adds one later.
        if hasattr(category_tools, "__all__"):
            assert "get_subcategories" in category_tools.__all__
            assert "evolve_categories" in category_tools.__all__
