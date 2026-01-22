"""Category Evolution system for Session Buddy (Phase 5).

This module implements intelligent subcategory organization that evolves over time
through clustering and incremental learning. It leverages fingerprint pre-filtering
from Phase 4 for fast assignment.

Architecture:
    KeywordExtractor → SubcategoryClusterer → CategoryEvolutionEngine
          ↓                  ↓                      ↓
    Feature Terms    Clustering Logic      Background Evolution

Usage:
    >>> engine = CategoryEvolutionEngine()
    >>> await engine.initialize()
    >>> # Assign new memory to subcategory
    >>> assignment = await engine.assign_subcategory(memory_dict)
    >>> # Evolve categories periodically
    >>> await engine.evolve_category(TopLevelCategory.SKILLS)
"""

from __future__ import annotations

import logging
import operator
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np

from session_buddy.utils.fingerprint import MinHashSignature

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Data Models
# ============================================================================


class TopLevelCategory(str, Enum):
    """Top-level memory categories following MemU's taxonomy."""

    FACTS = "facts"  # Factual information, concepts, definitions
    PREFERENCES = "preferences"  # User preferences, configurations, choices
    SKILLS = "skills"  # Learned skills, techniques, patterns
    RULES = "rules"  # Rules, principles, heuristics, best practices
    CONTEXT = "context"  # Contextual information, project details, state

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class Subcategory:
    """A subcategory within a top-level category.

    Attributes:
        id: Unique identifier
        parent_category: Top-level category (FACTS, PREFERENCES, etc.)
        name: Subcategory name (e.g., "python-async", "api-design")
        keywords: Extracted keywords for this subcategory
        centroid: Mean embedding of all memories in this subcategory
        centroid_fingerprint: MinHash signature for fast pre-filtering (Phase 4 integration)
        memory_count: Number of memories assigned to this subcategory
        created_at: When this subcategory was created
        updated_at: When this subcategory was last updated
    """

    id: str
    parent_category: TopLevelCategory
    name: str
    keywords: list[str]
    centroid: np.ndarray | None = None
    centroid_fingerprint: bytes | None = None
    memory_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __str__(self) -> str:
        return f"{self.parent_category.value}/{self.name}"

    def __repr__(self) -> str:
        return f"Subcategory({self.parent_category.value}/{self.name}, {self.memory_count} memories)"


@dataclass
class CategoryAssignment:
    """Result of assigning a memory to a subcategory.

    Attributes:
        memory_id: ID of the memory being assigned
        category: Top-level category
        subcategory: Assigned subcategory name (None if no suitable subcategory)
        confidence: Assignment confidence (0.0 to 1.0)
        method: Assignment method ("fingerprint" or "embedding")
    """

    memory_id: str
    category: TopLevelCategory
    subcategory: str | None
    confidence: float
    method: str  # "fingerprint" or "embedding"

    def __repr__(self) -> str:
        sub = self.subcategory or "none"
        return f"CategoryAssignment({self.category.value}/{sub}, {self.confidence:.2f}, {self.method})"


@dataclass
class SubcategoryMatch:
    """Wrapper for subcategory match with similarity score."""

    subcategory: Subcategory
    similarity: float


# ============================================================================
# Keyword Extraction
# ============================================================================


class KeywordExtractor:
    """Extract meaningful keywords from memory content for clustering.

    Uses a combination of stop word filtering and technical term detection
    to identify keywords that distinguish subcategories.
    """

    # Common English stop words
    STOP_WORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "that",
        "the",
        "to",
        "was",
        "were",
        "will",
        "with",
        "i",
        "you",
        "we",
        "they",
        "this",
        "that",
        "these",
        "those",
        "am",
        "pm",
        "been",
        "being",
        "have",
        "had",
        "do",
        "does",
        "did",
        "but",
        "or",
        "if",
        "because",
        "as",
        "until",
        "while",
        "of",
        "at",
        "by",
        "for",
        "with",
        "about",
        "against",
        "between",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "to",
        "from",
        "up",
        "down",
        "in",
        "out",
        "on",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "can",
        "will",
        "just",
        "don",
        "should",
        "now",
        # Programming-specific stop words
        "use",
        "used",
        "using",
        "make",
        "made",
        "get",
        "got",
        "also",
        "well",
        "back",
        "into",
        "over",
        "just",
        "can",
        "need",
        "required",
        "based",
        "new",
        "old",
        "good",
        "bad",
        "better",
        "worse",
        "first",
        "last",
        "next",
        "previous",
        "following",
    }

    # Technical term patterns (programming, tools, concepts)
    TECH_PATTERNS = [
        r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b",  # CamelCase
        r"\b[a-z]+_[a-z_]+\b",  # snake_case
        r"\b__[a-z_]+__\b",  # Python dunder
        r"\b\.{2}[a-z_]+\b",  # Dotted notation
        r"\b[a-z]+://[^\s]+\b",  # URLs
        r"\b\w+\(\)\b",  # Function calls
    ]

    def __init__(
        self,
        min_keyword_length: int = 3,
        max_keywords: int = 10,
        include_technical_terms: bool = True,
    ):
        """Initialize keyword extractor."""
        self.min_keyword_length = min_keyword_length
        self.max_keywords = max_keywords
        self.include_technical_terms = include_technical_terms

    def extract(self, content: str) -> list[str]:
        """Extract keywords from content."""
        content = content.lower()
        content = re.sub(r"[^\w\s\-_.:()<>]", " ", content)
        words = content.split()

        word_freq: dict[str, int] = {}
        for word in words:
            if (
                len(word) >= self.min_keyword_length
                and word not in self.STOP_WORDS
                and not word.isdigit()
            ):
                word_freq[word] = word_freq.get(word, 0) + 1

        # Extract technical terms if enabled
        if self.include_technical_terms:
            for pattern in self.TECH_PATTERNS:
                matches = re.findall(pattern, content)
                for match in matches:
                    if len(match) >= self.min_keyword_length:
                        word_freq[match] = word_freq.get(match, 0) + 2

        sorted_words = sorted(
            word_freq.items(), key=operator.itemgetter(1), reverse=True
        )
        keywords = [word for word, _ in sorted_words[: self.max_keywords]]

        return keywords


# ============================================================================
# Subcategory Clustering
# ============================================================================


class SubcategoryClusterer:
    """Clusters memories into subcategories using embeddings and fingerprints."""

    def __init__(
        self,
        min_cluster_size: int = 3,
        max_clusters: int = 10,
        similarity_threshold: float = 0.75,
        fingerprint_threshold: float = 0.90,
    ):
        """Initialize subcategory clusterer."""
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters
        self.similarity_threshold = similarity_threshold
        self.fingerprint_threshold = fingerprint_threshold

    def cluster_memories(
        self,
        memories: list[dict[str, Any]],
        category: TopLevelCategory = TopLevelCategory.CONTEXT,
        existing_subcategories: list[Subcategory] | None = None,
    ) -> list[Subcategory]:
        """Cluster memories into subcategories."""
        if not memories:
            return existing_subcategories or []

        logger.info(f"Clustering {len(memories)} memories for {category.value}")

        subcategories = existing_subcategories or []
        subcategory_map = {sc.name: sc for sc in subcategories}

        # Extract embeddings
        embeddings_list = [m.get("embedding") for m in memories]
        valid_embeddings = [e for e in embeddings_list if e is not None]
        unassigned_indices = [i for i, e in enumerate(embeddings_list) if e is not None]

        # Assign to existing subcategories
        for idx in unassigned_indices.copy():
            memory = memories[idx]
            embedding = valid_embeddings[idx]

            best_match = self._find_best_subcategory(memory, embedding, subcategories)
            if best_match:
                self._update_centroid(best_match, embedding)
                if memory.get("fingerprint"):
                    self._update_fingerprint_centroid(best_match, memory["fingerprint"])
                best_match.memory_count += 1
                best_match.updated_at = datetime.now(UTC)
                unassigned_indices.remove(idx)

        # Create new subcategories
        if unassigned_indices and len(subcategories) < self.max_clusters:
            new_subcategories = self._create_new_subcategories(
                [memories[i] for i in unassigned_indices],
                [valid_embeddings[i] for i in unassigned_indices],
                category,
                set(subcategory_map.keys()),
            )
            subcategories.extend(new_subcategories)

        # Merge small subcategories
        subcategories = self._merge_small_subcategories(subcategories)

        logger.info(f"Clustering complete: {len(subcategories)} subcategories")
        return subcategories

    def _find_best_subcategory(
        self,
        memory: dict[str, Any],
        embedding: np.ndarray,
        subcategories: list[Subcategory],
    ) -> Subcategory | None:
        """Find best matching subcategory for a memory."""
        if not subcategories:
            return None

        # Try fingerprint pre-filtering first
        if memory.get("fingerprint"):
            fingerprint_match = self._fingerprint_prefilter(
                memory["fingerprint"], subcategories
            )
            if fingerprint_match:
                return fingerprint_match

        # Fallback to embedding-based similarity
        for subcategory in subcategories:
            if subcategory.centroid is not None:
                similarity = self._cosine_similarity(embedding, subcategory.centroid)
                if similarity >= self.similarity_threshold:
                    return subcategory

        return None

    def _fingerprint_prefilter(
        self,
        fingerprint: bytes,
        subcategories: list[Subcategory],
    ) -> Subcategory | None:
        """Fast fingerprint-based pre-filtering."""
        if not fingerprint or not subcategories:
            return None

        fingerprint_sig = MinHashSignature.from_bytes(fingerprint)

        matches = []
        for subcat in subcategories:
            if subcat.centroid_fingerprint:
                subcat_sig = MinHashSignature.from_bytes(subcat.centroid_fingerprint)
                similarity = fingerprint_sig.estimate_jaccard_similarity(subcat_sig)

                if similarity >= self.fingerprint_threshold:
                    matches.append((subcat, similarity))

        if matches:
            best_subcat, _ = max(matches, key=operator.itemgetter(1))
            return best_subcat

        return None

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if 0 in (norm1, norm2):
            return 0.0

        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def _update_centroid(
        self, subcategory: Subcategory, new_embedding: np.ndarray
    ) -> None:
        """Incrementally update subcategory centroid."""
        if subcategory.centroid is None:
            subcategory.centroid = new_embedding.copy()
        else:
            count = subcategory.memory_count
            subcategory.centroid = (subcategory.centroid * count + new_embedding) / (
                count + 1
            )

    def _update_fingerprint_centroid(
        self, subcategory: Subcategory, new_fingerprint: bytes
    ) -> None:
        """Update subcategory's fingerprint centroid."""
        subcategory.centroid_fingerprint = new_fingerprint

    def _create_new_subcategories(
        self,
        memories: list[dict[str, Any]],
        embeddings: list[np.ndarray],
        category: TopLevelCategory,
        existing_names: set[str],
    ) -> list[Subcategory]:
        """Create new subcategories from unassigned memories."""
        if len(memories) < self.min_cluster_size:
            return []

        extractor = KeywordExtractor()
        all_keywords: dict[str, int] = {}

        for memory in memories:
            keywords = extractor.extract(memory.get("content", ""))
            for keyword in keywords:
                all_keywords[keyword] = all_keywords.get(keyword, 0) + 1

        top_keywords = sorted(
            all_keywords.items(), key=operator.itemgetter(1), reverse=True
        )
        subcat_name = "-".join([kw for kw, _ in top_keywords[:3]])

        counter = 1
        base_name = subcat_name
        while subcat_name in existing_names:
            subcat_name = f"{base_name}-{counter}"
            counter += 1

        valid_embeddings = [e for e in embeddings if e is not None]
        centroid = np.mean(valid_embeddings, axis=0) if valid_embeddings else None

        centroid_fingerprint = None
        for memory in memories:
            if memory.get("fingerprint"):
                centroid_fingerprint = memory["fingerprint"]
                break

        subcategory = Subcategory(
            id=str(uuid.uuid4()),
            parent_category=category,
            name=subcat_name,
            keywords=[kw for kw, _ in top_keywords[:10]],
            centroid=centroid,
            centroid_fingerprint=centroid_fingerprint,
            memory_count=len(memories),
        )

        return [subcategory]

    def _merge_small_subcategories(
        self, subcategories: list[Subcategory]
    ) -> list[Subcategory]:
        """Merge small subcategories into similar ones."""
        if len(subcategories) <= 1:
            return subcategories

        small_subcats = [
            sc for sc in subcategories if sc.memory_count < self.min_cluster_size
        ]
        if not small_subcats:
            return subcategories

        merged = subcategories.copy()
        for small_cat in small_subcats:
            best_match = self._find_best_merge_target(small_cat, merged)

            if best_match:
                self._merge_categories(best_match, small_cat)
                merged.remove(small_cat)
                logger.info(f"Merged '{small_cat.name}' into '{best_match.name}'")

        return merged

    def _find_best_merge_target(
        self, small_cat: Subcategory, subcategories: list[Subcategory]
    ) -> Subcategory | None:
        """Find the best subcategory to merge a small category into.

        Args:
            small_cat: Small subcategory to merge
            subcategories: List of all subcategories

        Returns:
            Best matching subcategory or None
        """
        best_match = None
        best_similarity = 0.0

        for other_cat in subcategories:
            if self._is_valid_merge_target(small_cat, other_cat):
                if small_cat.centroid is not None and other_cat.centroid is not None:
                    similarity = self._cosine_similarity(
                        small_cat.centroid, other_cat.centroid
                    )
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = other_cat

        if best_match and best_similarity >= self.similarity_threshold:
            return best_match

        return None

    def _is_valid_merge_target(
        self, small_cat: Subcategory, other_cat: Subcategory
    ) -> bool:
        """Check if a subcategory is a valid merge target.

        Args:
            small_cat: Small subcategory to merge
            other_cat: Potential target subcategory

        Returns:
            True if valid merge target
        """
        return (
            other_cat is not small_cat
            and other_cat.memory_count >= self.min_cluster_size
            and small_cat.centroid is not None
            and other_cat.centroid is not None
        )

    def _merge_categories(self, target: Subcategory, source: Subcategory) -> None:
        """Merge source subcategory into target subcategory.

        Args:
            target: Target subcategory (will be modified)
            source: Source subcategory (will be removed)
        """
        if target.centroid is not None and source.centroid is not None:
            total_count = source.memory_count + target.memory_count
            target.centroid = (
                target.centroid * target.memory_count
                + source.centroid * source.memory_count
            ) / total_count

        target.memory_count += source.memory_count
        target.updated_at = datetime.now(UTC)


# ============================================================================
# Category Evolution Engine
# ============================================================================


class CategoryEvolutionEngine:
    """Main engine for category evolution and subcategory assignment."""

    def __init__(
        self,
        min_cluster_size: int = 3,
        max_clusters: int = 10,
        similarity_threshold: float = 0.75,
        fingerprint_threshold: float = 0.90,
        enable_fingerprint_prefilter: bool = True,
        db_adapter: Any = None,  # ReflectionDatabaseAdapterOneiric
    ):
        """Initialize category evolution engine.

        Args:
            min_cluster_size: Minimum memories required to form a subcategory
            max_clusters: Maximum number of subcategories per top-level category
            similarity_threshold: Minimum cosine similarity for subcategory assignment
            fingerprint_threshold: MinHash similarity threshold for pre-filtering
            enable_fingerprint_prefilter: Whether to use fingerprint pre-filtering
            db_adapter: Optional database adapter for persistence (ReflectionDatabaseAdapterOneiric)
        """
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters
        self.similarity_threshold = similarity_threshold
        self.fingerprint_threshold = fingerprint_threshold
        self.enable_fingerprint_prefilter = enable_fingerprint_prefilter
        self._db_adapter = db_adapter

        self.keyword_extractor = KeywordExtractor()
        self.clusterer = SubcategoryClusterer(
            min_cluster_size=min_cluster_size,
            max_clusters=max_clusters,
            similarity_threshold=similarity_threshold,
            fingerprint_threshold=fingerprint_threshold,
        )

        self._subcategories: dict[TopLevelCategory, list[Subcategory]] = {}

    async def initialize(self) -> None:
        """Initialize the evolution engine and load persisted subcategories."""
        logger.info("Initializing CategoryEvolutionEngine")

        # Initialize empty categories
        for category in TopLevelCategory:
            self._subcategories[category] = []

        # Load persisted subcategories if database adapter available
        if self._db_adapter is not None:
            await self._load_subcategories()

    async def assign_subcategory(
        self,
        memory: dict[str, Any],
        category: TopLevelCategory | None = None,
        use_fingerprint_prefilter: bool | None = None,
    ) -> CategoryAssignment:
        """Assign a memory to a subcategory."""
        if category is None:
            category = self._detect_category(memory)

        subcategories = self._subcategories.get(category, [])

        if use_fingerprint_prefilter is None:
            use_fingerprint_prefilter = self.enable_fingerprint_prefilter

        # Try fast fingerprint pre-filtering
        if use_fingerprint_prefilter and memory.get("fingerprint") and subcategories:
            match = self._fingerprint_match(memory["fingerprint"], subcategories)
            if match:
                return CategoryAssignment(
                    memory_id=memory.get("id", ""),
                    category=category,
                    subcategory=match.subcategory.name,
                    confidence=match.similarity,
                    method="fingerprint",
                )

        # Fallback to embedding-based assignment
        if memory.get("embedding") is not None:
            match = self._embedding_match(memory, subcategories)
            if match:
                return CategoryAssignment(
                    memory_id=memory.get("id", ""),
                    category=category,
                    subcategory=match.subcategory.name,
                    confidence=match.similarity,
                    method="embedding",
                )

        # No suitable subcategory
        return CategoryAssignment(
            memory_id=memory.get("id", ""),
            category=category,
            subcategory=None,
            confidence=0.0,
            method="none",
        )

    async def evolve_category(
        self,
        category: TopLevelCategory,
        memories: list[dict[str, Any]],
    ) -> list[Subcategory]:
        """Evolve subcategories for a top-level category."""
        logger.info(f"Evolving subcategories for {category.value}")

        existing_subcats = self._subcategories.get(category, [])
        new_subcats = self.clusterer.cluster_memories(
            memories=memories,
            category=category,
            existing_subcategories=existing_subcats,
        )

        self._subcategories[category] = new_subcats
        await self._persist_subcategories(category, new_subcats)

        logger.info(f"Evolution complete: {len(new_subcats)} subcategories")
        return new_subcats

    def get_subcategories(self, category: TopLevelCategory) -> list[Subcategory]:
        """Get all subcategories for a top-level category."""
        return self._subcategories.get(category, [])

    def _detect_category(self, memory: dict[str, Any]) -> TopLevelCategory:
        """Auto-detect top-level category from memory content."""
        content = memory.get("content", "").lower()

        if any(word in content for word in ("prefer", "config", "setting", "option")):
            return TopLevelCategory.PREFERENCES
        if any(word in content for word in ("learn", "skill", "technique", "how to")):
            return TopLevelCategory.SKILLS
        if any(
            word in content for word in ("rule", "principle", "should", "best practice")
        ):
            return TopLevelCategory.RULES
        if any(
            word in content for word in ("fact", "definition", "means", "refers to")
        ):
            return TopLevelCategory.FACTS

        return TopLevelCategory.CONTEXT

    def _fingerprint_match(
        self,
        fingerprint: bytes,
        subcategories: list[Subcategory],
    ) -> SubcategoryMatch | None:
        """Find best fingerprint match among subcategories."""
        if not fingerprint or not subcategories:
            return None

        fingerprint_sig = MinHashSignature.from_bytes(fingerprint)

        matches = []
        for subcat in subcategories:
            if subcat.centroid_fingerprint:
                subcat_sig = MinHashSignature.from_bytes(subcat.centroid_fingerprint)
                similarity = fingerprint_sig.estimate_jaccard_similarity(subcat_sig)

                if similarity >= self.fingerprint_threshold:
                    matches.append((subcat, similarity))

        if matches:
            best_subcat, best_sim = max(matches, key=operator.itemgetter(1))
            return SubcategoryMatch(subcategory=best_subcat, similarity=best_sim)

        return None

    def _embedding_match(
        self,
        memory: dict[str, Any],
        subcategories: list[Subcategory],
    ) -> SubcategoryMatch | None:
        """Find best embedding match among subcategories."""
        embedding = memory.get("embedding")

        if embedding is None or not subcategories:
            return None

        matches = []
        for subcat in subcategories:
            if subcat.centroid is not None:
                similarity = self.clusterer._cosine_similarity(
                    embedding, subcat.centroid
                )

                if similarity >= self.similarity_threshold:
                    matches.append((subcat, similarity))

        if matches:
            best_subcat, best_sim = max(matches, key=operator.itemgetter(1))
            return SubcategoryMatch(subcategory=best_subcat, similarity=best_sim)

        return None

    async def _persist_subcategories(
        self,
        category: TopLevelCategory,
        subcategories: list[Subcategory],
    ) -> None:
        """Persist subcategories to database.

        Performs upsert operations:
        - Updates existing subcategories
        - Inserts new subcategories
        - Removes deleted subcategories
        """
        if self._db_adapter is None:
            logger.debug("No database adapter available, skipping persistence")
            return

        logger.info(
            f"Persisting {len(subcategories)} subcategories for {category.value}"
        )

        try:
            conn = self._db_adapter.conn

            # Upsert each subcategory
            for subcat in subcategories:
                # Convert centroid to list for storage
                centroid_list = (
                    subcat.centroid.tolist() if subcat.centroid is not None else None
                )

                conn.execute(
                    """
                    INSERT INTO memory_subcategories
                        (id, parent_category, name, keywords, centroid, centroid_fingerprint, memory_count, updated_at)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (parent_category, name)
                    DO UPDATE SET
                        keywords = excluded.keywords,
                        centroid = excluded.centroid,
                        centroid_fingerprint = excluded.centroid_fingerprint,
                        memory_count = excluded.memory_count,
                        updated_at = excluded.updated_at
                    """,
                    [
                        subcat.id,
                        category.value,
                        subcat.name,
                        subcat.keywords,
                        centroid_list,
                        subcat.centroid_fingerprint,
                        subcat.memory_count,
                        subcat.updated_at,
                    ],
                )

            # Remove subcategories that no longer exist
            current_names = {sc.name for sc in subcategories}
            conn.execute(
                """
                DELETE FROM memory_subcategories
                WHERE parent_category = ? AND name NOT IN ?
                """,
                [category.value, list(current_names)],
            )

            logger.info(f"Successfully persisted {len(subcategories)} subcategories")

        except Exception as e:
            logger.error(f"Failed to persist subcategories: {e}")

    async def _load_subcategories(self) -> None:
        """Load subcategories from database on initialization.

        Populates the in-memory subcategory cache with persisted data.
        """
        if self._db_adapter is None:
            logger.debug("No database adapter available, skipping load")
            return

        logger.info("Loading subcategories from database")

        try:
            conn = self._db_adapter.conn

            # Query all subcategories
            result = conn.execute(
                """
                SELECT
                    id, parent_category, name, keywords,
                    centroid, centroid_fingerprint, memory_count,
                    created_at, updated_at
                FROM memory_subcategories
                ORDER BY parent_category, memory_count DESC
                """
            ).fetchall()

            # Group by parent category
            loaded_count = 0
            for row in result:
                (
                    subcat_id,
                    parent_category,
                    name,
                    keywords,
                    centroid,
                    centroid_fingerprint,
                    memory_count,
                    created_at,
                    updated_at,
                ) = row

                # Parse parent category
                try:
                    category = TopLevelCategory(parent_category)
                except ValueError:
                    logger.warning(f"Invalid parent category: {parent_category}")
                    continue

                # Convert centroid back to numpy array
                centroid_array = np.array(centroid) if centroid is not None else None

                # Create subcategory object
                subcategory = Subcategory(
                    id=subcat_id,
                    parent_category=category,
                    name=name,
                    keywords=keywords or [],
                    centroid=centroid_array,
                    centroid_fingerprint=centroid_fingerprint,
                    memory_count=memory_count or 0,
                    created_at=created_at,
                    updated_at=updated_at,
                )

                self._subcategories[category].append(subcategory)
                loaded_count += 1

            logger.info(
                f"Successfully loaded {loaded_count} subcategories from database"
            )

        except Exception as e:
            logger.error(f"Failed to load subcategories: {e}")
            # Continue with empty subcategories
