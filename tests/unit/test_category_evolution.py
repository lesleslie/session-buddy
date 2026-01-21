"""Unit tests for Phase 5: Category Evolution system."""

import numpy as np
import pytest

from session_buddy.memory.category_evolution import (
    CategoryAssignment,
    CategoryEvolutionEngine,
    KeywordExtractor,
    Subcategory,
    SubcategoryClusterer,
    SubcategoryMatch,
    TopLevelCategory,
)
from session_buddy.utils.fingerprint import MinHashSignature, extract_ngrams


class TestKeywordExtractor:
    """Test keyword extraction functionality."""

    def test_extract_basic_keywords(self):
        """Test basic keyword extraction from content."""
        extractor = KeywordExtractor()

        content = "Python async programming patterns and FastAPI web development"
        keywords = extractor.extract(content)

        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert "python" in keywords
        assert "async" in keywords
        assert "programming" in keywords

    def test_removes_stop_words(self):
        """Test that stop words are filtered out."""
        extractor = KeywordExtractor()

        content = "the use of async in python is good"
        keywords = extractor.extract(content)

        assert "the" not in keywords
        assert "of" not in keywords
        assert "is" not in keywords
        assert "good" not in keywords  # Programming stop word

    def test_extracts_technical_terms(self):
        """Test that technical terms are identified."""
        extractor = KeywordExtractor(include_technical_terms=True)

        content = "Using QueryCache and MinHashSignature for async patterns"
        keywords = extractor.extract(content)

        # Should extract CamelCase
        assert any("query" in kw.lower() for kw in keywords)
        # Should extract snake_case
        assert any("cache" in kw.lower() for kw in keywords)


class TestSubcategoryClusterer:
    """Test subcategory clustering functionality."""

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        clusterer = SubcategoryClusterer()

        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([1.0, 0.0, 0.0])
        vec3 = np.array([0.0, 1.0, 0.0])

        # Identical vectors
        sim = clusterer._cosine_similarity(vec1, vec2)
        assert sim == pytest.approx(1.0)

        # Orthogonal vectors
        sim = clusterer._cosine_similarity(vec1, vec3)
        assert sim == pytest.approx(0.0)

    def test_cluster_memories_empty(self):
        """Test clustering with no memories."""
        clusterer = SubcategoryClusterer()
        result = clusterer.cluster_memories(
            memories=[],
            category=TopLevelCategory.CONTEXT,
        )

        assert result == []

    def test_cluster_memories_creates_subcategories(self):
        """Test that clustering creates subcategories."""
        clusterer = SubcategoryClusterer(min_cluster_size=2, max_clusters=5)

        memories = [
            {
                "id": "1",
                "content": "Python async programming with await and asyncio",
                "embedding": np.array([1.0, 0.0, 0.0]),
                "fingerprint": MinHashSignature.from_ngrams(
                    extract_ngrams("python async", n=3)
                ).to_bytes(),
            },
            {
                "id": "2",
                "content": "Python async patterns and await keywords",
                "embedding": np.array([0.9, 0.1, 0.0]),
                "fingerprint": MinHashSignature.from_ngrams(
                    extract_ngrams("python async", n=3)
                ).to_bytes(),
            },
        ]

        result = clusterer.cluster_memories(
            memories=memories,
            category=TopLevelCategory.SKILLS,
        )

        assert len(result) == 1
        assert result[0].memory_count == 2
        assert result[0].parent_category == TopLevelCategory.SKILLS

    def test_merge_small_subcategories(self):
        """Test that small subcategories are merged."""
        clusterer = SubcategoryClusterer(
            min_cluster_size=3,
            similarity_threshold=0.70,
        )

        # Create subcategories
        sub1 = Subcategory(
            id="1",
            parent_category=TopLevelCategory.SKILLS,
            name="python-async",
            keywords=["python", "async"],
            centroid=np.array([1.0, 0.0]),
            centroid_fingerprint=None,
            memory_count=1,  # Below threshold
        )

        sub2 = Subcategory(
            id="2",
            parent_category=TopLevelCategory.SKILLS,
            name="python-async",
            keywords=["python", "async"],
            centroid=np.array([0.95, 0.05]),  # Similar to sub1
            centroid_fingerprint=None,
            memory_count=5,  # Above threshold
        )

        merged = clusterer._merge_small_subcategories([sub1, sub2])

        assert len(merged) == 1
        assert merged[0].memory_count == 6  # Merged count


class TestCategoryEvolutionEngine:
    """Test category evolution engine functionality."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test engine initialization."""
        engine = CategoryEvolutionEngine()
        await engine.initialize()

        assert engine.get_subcategories(TopLevelCategory.FACTS) == []
        assert engine.get_subcategories(TopLevelCategory.SKILLS) == []
        assert engine.get_subcategories(TopLevelCategory.CONTEXT) == []

    @pytest.mark.asyncio
    async def test_assign_subcategory_no_match(self):
        """Test assignment when no suitable subcategory exists."""
        engine = CategoryEvolutionEngine()
        await engine.initialize()

        memory = {
            "id": "test123",
            "content": "learning about Python decorators",
            "embedding": np.array([1.0, 0.0, 0.0]),
        }

        result = await engine.assign_subcategory(memory)

        assert result.memory_id == "test123"
        assert result.category == TopLevelCategory.SKILLS  # Auto-detected
        assert result.subcategory is None  # No matching subcategory
        assert result.confidence == 0.0
        assert result.method == "none"

    @pytest.mark.asyncio
    async def test_assign_subcategory_with_embedding_match(self):
        """Test assignment with embedding-based matching."""
        engine = CategoryEvolutionEngine()
        await engine.initialize()

        # Create an existing subcategory in SKILLS
        subcategory = Subcategory(
            id="sub1",
            parent_category=TopLevelCategory.SKILLS,
            name="python-async",
            keywords=["python", "async"],
            centroid=np.array([1.0, 0.0, 0.0]),
            centroid_fingerprint=None,
            memory_count=5,
        )
        engine._subcategories[TopLevelCategory.SKILLS] = [subcategory]

        # Similar memory with "learn" keyword for SKILLS detection
        memory = {
            "id": "test456",
            "content": "I learned Python async programming",  # "learned" triggers SKILLS
            "embedding": np.array([0.95, 0.05, 0.0]),  # Similar to centroid
        }

        result = await engine.assign_subcategory(memory, use_fingerprint_prefilter=False)

        assert result.memory_id == "test456"
        assert result.category == TopLevelCategory.SKILLS
        assert result.subcategory == "python-async"
        assert result.confidence > 0.7
        assert result.method == "embedding"

    @pytest.mark.asyncio
    async def test_assign_subcategory_with_fingerprint_match(self):
        """Test assignment with fingerprint pre-filtering."""
        engine = CategoryEvolutionEngine()
        await engine.initialize()

        # Create subcategory with fingerprint centroid in SKILLS
        fingerprint = MinHashSignature.from_ngrams(
            extract_ngrams("python async patterns", n=3)
        ).to_bytes()

        subcategory = Subcategory(
            id="sub1",
            parent_category=TopLevelCategory.SKILLS,
            name="python-async",
            keywords=["python", "async"],
            centroid=np.array([1.0, 0.0, 0.0]),
            centroid_fingerprint=fingerprint,
            memory_count=5,
        )
        engine._subcategories[TopLevelCategory.SKILLS] = [subcategory]

        # Similar memory with same fingerprint and "learn" keyword
        memory = {
            "id": "test789",
            "content": "I learned Python async programming patterns",  # SKILLS keyword
            "embedding": np.array([0.9, 0.1, 0.0]),
            "fingerprint": fingerprint,
        }

        result = await engine.assign_subcategory(memory, use_fingerprint_prefilter=True)

        assert result.memory_id == "test789"
        assert result.category == TopLevelCategory.SKILLS
        assert result.subcategory == "python-async"
        assert result.confidence >= 0.90  # High fingerprint similarity
        assert result.method == "fingerprint"  # Fast path used

    @pytest.mark.asyncio
    async def test_evolve_category(self):
        """Test category evolution."""
        engine = CategoryEvolutionEngine(min_cluster_size=2, max_clusters=3)
        await engine.initialize()

        memories = [
            {
                "id": "1",
                "content": "Python async programming",
                "embedding": np.array([1.0, 0.0, 0.0]),
            },
            {
                "id": "2",
                "content": "Async patterns in Python",
                "embedding": np.array([0.95, 0.05, 0.0]),
            },
            {
                "id": "3",
                "content": "FastAPI web development",
                "embedding": np.array([0.0, 1.0, 0.0]),
            },
        ]

        result = await engine.evolve_category(
            category=TopLevelCategory.SKILLS,
            memories=memories,
        )

        assert len(result) >= 1  # Should create at least one subcategory
        assert all(sc.parent_category == TopLevelCategory.SKILLS for sc in result)

    def test_detect_category_skills(self):
        """Test auto-detection of SKILLS category."""
        engine = CategoryEvolutionEngine()

        memory = {"content": "I learned how to use async patterns"}
        category = engine._detect_category(memory)

        assert category == TopLevelCategory.SKILLS

    def test_detect_category_preferences(self):
        """Test auto-detection of PREFERENCES category."""
        engine = CategoryEvolutionEngine()

        memory = {"content": "My preferred config is to use type hints"}
        category = engine._detect_category(memory)

        assert category == TopLevelCategory.PREFERENCES

    def test_detect_category_rules(self):
        """Test auto-detection of RULES category."""
        engine = CategoryEvolutionEngine()

        memory = {"content": "The best practice is to follow PEP 8"}
        category = engine._detect_category(memory)

        assert category == TopLevelCategory.RULES


class TestSubcategoryMatch:
    """Test SubcategoryMatch wrapper."""

    def test_creation(self):
        """Test SubcategoryMatch creation."""
        subcategory = Subcategory(
            id="test",
            parent_category=TopLevelCategory.SKILLS,
            name="python-async",
            keywords=["python"],
            centroid=None,
            centroid_fingerprint=None,
            memory_count=5,
        )

        match = SubcategoryMatch(subcategory=subcategory, similarity=0.85)

        assert match.subcategory == subcategory
        assert match.similarity == 0.85
