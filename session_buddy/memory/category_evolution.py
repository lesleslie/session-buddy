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
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import numpy as np

from session_buddy.memory.evolution_config import DecayResult, EvolutionConfig
from session_buddy.utils.fingerprint import MinHashSignature

if TYPE_CHECKING:
    import json

logger = logging.getLogger(__name__)

# ============================================================================
# Enums and Data Models
# ============================================================================


class TopLevelCategory(StrEnum):
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
        last_accessed_at: When this subcategory was last accessed during evolution
        access_count: Number of times memories were assigned to this subcategory
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
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0

    def __str__(self) -> str:
        return f"{self.parent_category.value}/{self.name}"

    def __repr__(self) -> str:
        return f"Subcategory({self.parent_category.value}/{self.name}, {self.memory_count} memories)"

    def record_access(self) -> None:
        """Record that this subcategory was accessed during evolution.

        Updates last_accessed_at timestamp and increments access_count.
        Should be called whenever a memory is assigned to this subcategory.
        """
        self.last_accessed_at = datetime.now(UTC)
        self.access_count += 1
        self.updated_at = datetime.now(UTC)


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
                best_match.record_access()  # Track access for temporal decay
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
        """Update subcategory's fingerprint centroid using MinHash union.

        MinHash signatures support union operation via element-wise minimum,
        which approximates the Jaccard similarity of the union set.
        """
        if subcategory.centroid_fingerprint is None:
            # First fingerprint for this subcategory
            subcategory.centroid_fingerprint = new_fingerprint
            return

        # Aggregate using MinHash union (element-wise minimum)
        existing_sig = MinHashSignature.from_bytes(subcategory.centroid_fingerprint)
        new_sig = MinHashSignature.from_bytes(new_fingerprint)

        # Element-wise minimum approximates union of sets
        union_signature = np.minimum(existing_sig.signature, new_sig.signature)

        # Create new MinHashSignature with union
        aggregated_sig = MinHashSignature(
            signature=union_signature.tolist(), num_hashes=existing_sig.num_hashes
        )

        subcategory.centroid_fingerprint = aggregated_sig.to_bytes()

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
        config: EvolutionConfig | None = None,
    ) -> dict[str, Any]:
        """Evolve subcategories for a top-level category.

        Args:
            category: Top-level category to evolve
            memories: Memories to cluster into subcategories
            config: Optional evolution configuration

        Returns:
            Dictionary with comprehensive evolution results including:
            - success: Boolean indicating success
            - before_state: Dict with before metrics
            - after_state: Dict with after metrics
            - decay_results: Dict with temporal decay results
            - snapshot_id: ID of created snapshot (if saved)
        """
        import time

        logger.info(f"Evolving subcategories for {category.value}")
        start_time = time.time()

        # Use default config if not provided
        if config is None:
            config = EvolutionConfig()

        # Capture before state
        before_subcats = self._subcategories.get(category, [])
        before_silhouette = self.calculate_silhouette_score(before_subcats, memories)
        before_state = {
            "subcategory_count": len(before_subcats),
            "silhouette": before_silhouette,
            "total_memories": len(memories),
        }

        # Apply temporal decay first (remove stale subcategories)
        decay_result = DecayResult(
            removed_count=0,
            archived=config.archive_option,
            freed_space=0,
            message="Temporal decay not enabled",
            decayed_subcategories=[],
        )

        if config.temporal_decay_enabled:
            decay_result = await self.apply_temporal_decay(category, config)
            logger.info(f"Temporal decay: {decay_result.message}")

        # Perform clustering
        new_subcats = self.clusterer.cluster_memories(
            memories=memories,
            category=category,
            existing_subcategories=self._subcategories.get(category, []),
        )

        self._subcategories[category] = new_subcats
        await self._persist_subcategories(category, new_subcats)

        # Calculate after state
        after_silhouette = self.calculate_silhouette_score(new_subcats, memories)
        after_state = {
            "subcategory_count": len(new_subcats),
            "silhouette": after_silhouette,
            "total_memories": len(memories),
        }

        duration_ms = (time.time() - start_time) * 1000

        # Save snapshot
        await self._save_evolution_snapshot(
            category=category,
            before_state=before_state,
            after_state=after_state,
            decay_results=decay_result,
            duration_ms=duration_ms,
        )

        logger.info(
            f"Evolution complete: {len(new_subcats)} subcategories, "
            f"silhouette: {before_silhouette:.3f} → {after_silhouette:.3f}, "
            f"duration: {duration_ms:.1f}ms"
        )

        return {
            "success": True,
            "category": category.value,
            "before_state": before_state,
            "after_state": after_state,
            "decay_results": decay_result.to_dict(),
            "duration_ms": duration_ms,
        }

    async def apply_temporal_decay(
        self,
        category: TopLevelCategory,
        config: EvolutionConfig,
    ) -> DecayResult:
        """Remove stale subcategories based on inactivity.

        Stale subcategories are those that:
        - Haven't been accessed in `temporal_decay_days` days
        - Have low access counts (< `decay_access_threshold`)

        Args:
            category: Category to apply decay to
            config: Evolution configuration

        Returns:
            DecayResult with counts and space freed
        """
        if not config.temporal_decay_enabled:
            return DecayResult(
                removed_count=0,
                archived=config.archive_option,
                freed_space=0,
                message="Temporal decay disabled",
                decayed_subcategories=[],
            )

        cutoff = datetime.now(UTC) - timedelta(days=config.temporal_decay_days)
        subcategories = self._subcategories.get(category, [])

        # Find stale subcategories
        stale = [
            sc
            for sc in subcategories
            if sc.last_accessed_at < cutoff
            and sc.access_count < config.decay_access_threshold
        ]

        if not stale:
            return DecayResult(
                removed_count=0,
                archived=config.archive_option,
                freed_space=0,
                message="No stale subcategories found",
                decayed_subcategories=[],
            )

        # Record names for result
        decayed_names = [sc.name for sc in stale]

        # Archive or delete
        if config.archive_option:
            await self._archive_subcategories(stale, category)
        else:
            await self._delete_subcategories(stale, category)

        # Remove from in-memory state
        for sc in stale:
            self._subcategories[category].remove(sc)

        freed = self._estimate_space_freed(stale)

        logger.info(
            f"Temporal decay: {'archived' if config.archive_option else 'deleted'} {len(stale)} subcategories"
        )

        return DecayResult(
            removed_count=len(stale),
            archived=config.archive_option,
            freed_space=freed,
            message=f"{'Archived' if config.archive_option else 'Deleted'} {len(stale)} stale subcategories",
            decayed_subcategories=decayed_names,
        )

    def _estimate_space_freed(self, subcategories: list[Subcategory]) -> int:
        """Estimate bytes freed by removing subcategories.

        Args:
            subcategories: Subcategories being removed

        Returns:
            Estimated bytes freed
        """
        # Rough estimate: 1KB per subcategory + metadata
        return len(subcategories) * 1024

    async def _archive_subcategories(
        self,
        subcategories: list[Subcategory],
        category: TopLevelCategory,
    ) -> None:
        """Archive subcategories to cold storage.

        Args:
            subcategories: Subcategories to archive
            category: Parent category
        """
        if not self._db_adapter:
            logger.warning("No database adapter available, skipping archive")
            return

        try:
            conn = self._db_adapter.conn

            for sc in subcategories:
                # Convert to dict for JSON storage
                sc_dict = {
                    "id": sc.id,
                    "parent_category": sc.parent_category.value,
                    "name": sc.name,
                    "keywords": sc.keywords,
                    "memory_count": sc.memory_count,
                    "centroid_fingerprint": sc.centroid_fingerprint,
                }

                conn.execute(
                    """
                    INSERT INTO archived_subcategories (
                        id, original_subcategory_id, parent_category, name,
                        keywords, memory_count, centroid_fingerprint,
                        archived_at, reason, original_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), 'Temporal decay', ?)
                    """,
                    sc.id,
                    sc.id,
                    sc.parent_category.value,
                    sc.name,
                    json.dumps(sc.keywords),
                    sc.memory_count,
                    sc.centroid_fingerprint,
                    json.dumps(sc_dict),
                )

            logger.info(f"Archived {len(subcategories)} subcategories")
        except Exception as e:
            logger.error(f"Error archiving subcategories: {e}")

    async def _delete_subcategories(
        self,
        subcategories: list[Subcategory],
        category: TopLevelCategory,
    ) -> None:
        """Delete subcategories from database.

        Args:
            subcategories: Subcategories to delete
            category: Parent category
        """
        if not self._db_adapter:
            logger.warning("No database adapter available, skipping delete")
            return

        try:
            conn = self._db_adapter.conn

            for sc in subcategories:
                conn.execute(
                    f"""
                    DELETE FROM {self._db_adapter.collection_name}_subcategories
                    WHERE id = ?
                    """,
                    (sc.id,),
                )

            logger.info(f"Deleted {len(subcategories)} subcategories")
        except Exception as e:
            logger.error(f"Error deleting subcategories: {e}")

    def get_subcategories(self, category: TopLevelCategory) -> list[Subcategory]:
        """Get all subcategories for a top-level category."""
        return self._subcategories.get(category, [])

    def calculate_silhouette_score(
        self, subcategories: list[Subcategory], memories: list[dict[str, Any]]
    ) -> float:
        """Calculate overall cluster quality using silhouette score.

        Silhouette score ranges from -1 to +1:
        - +1: Perfect clustering (dense, well-separated)
        -  0: Overlapping clusters
        - -1: Incorrect clustering

        Args:
            subcategories: List of subcategories to evaluate
            memories: All memories (used to find cluster assignments)

        Returns:
            Silhouette score (higher is better). Returns 1.0 if < 2 clusters or < 2 points.
        """
        if len(subcategories) < 2:
            return 1.0  # Perfect if only 1 cluster

        # Build X (embeddings) and labels (subcategory assignments)
        X = []
        labels = []

        for subcat_idx, subcat in enumerate(subcategories):
            # Get embeddings for memories in this subcategory
            for memory in memories:
                if self._is_memory_in_subcategory(memory, subcat):
                    embedding = memory.get("embedding")
                    if embedding is not None:
                        X.append(embedding)
                        labels.append(subcat_idx)

        if len(X) < 2:
            return 1.0  # Can't calculate with < 2 points

        # Calculate silhouette score
        try:
            import numpy as np
            from sklearn.metrics import silhouette_score

            X_array = np.array(X)
            score = silhouette_score(X_array, labels)
            return float(score)
        except Exception as e:
            logger.warning(f"Failed to calculate silhouette score: {e}")
            return 0.0  # Return neutral score on error

    def _is_memory_in_subcategory(
        self, memory: dict[str, Any], subcategory: Subcategory
    ) -> bool:
        """Check if a memory belongs to a subcategory.

        Uses centroid similarity as a proxy for membership.
        A memory belongs to a subcategory if its embedding is sufficiently
        similar to the subcategory's centroid.

        Args:
            memory: Memory dictionary with optional 'embedding' field
            subcategory: Subcategory to check membership against

        Returns:
            True if memory belongs to subcategory, False otherwise
        """
        embedding = memory.get("embedding")
        if not embedding or subcategory.centroid is None:
            return False

        similarity = self._cosine_similarity(embedding, subcategory.centroid)
        return similarity >= self.similarity_threshold

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
                similarity = self._cosine_similarity(embedding, subcat.centroid)

                if similarity >= self.similarity_threshold:
                    matches.append((subcat, similarity))

        if matches:
            best_subcat, best_sim = max(matches, key=operator.itemgetter(1))
            return SubcategoryMatch(subcategory=best_subcat, similarity=best_sim)

        return None

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (0.0 to 1.0)
        """
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if 0 in (norm1, norm2):
            return 0.0

        return float(np.dot(vec1, vec2) / (norm1 * norm2))

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
                    created_at, updated_at, last_accessed_at, access_count
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
                    last_accessed_at,
                    access_count,
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
                    last_accessed_at=last_accessed_at or created_at,
                    access_count=access_count or 0,
                )

                self._subcategories[category].append(subcategory)
                loaded_count += 1

            logger.info(
                f"Successfully loaded {loaded_count} subcategories from database"
            )

        except Exception as e:
            logger.error(f"Failed to load subcategories: {e}")

    async def _save_evolution_snapshot(
        self,
        category: TopLevelCategory,
        before_state: dict[str, Any],
        after_state: dict[str, Any],
        decay_results: DecayResult,
        duration_ms: float,
    ) -> None:
        """Save evolution snapshot to database.

        Args:
            category: Category that was evolved
            before_state: Dict with before-state metrics
            after_state: Dict with after-state metrics
            decay_results: DecayResult from temporal decay
            duration_ms: Duration of evolution in milliseconds
        """
        if self._db_adapter is None:
            logger.debug("No database adapter available, skipping snapshot save")
            return

        try:
            from session_buddy.memory.evolution_config import EvolutionSnapshot

            conn = self._db_adapter.conn

            # Create snapshot
            snapshot = EvolutionSnapshot(
                id=str(uuid.uuid4()),
                category=category.value,
                before_state=before_state,
                after_state=after_state,
                decay_results=decay_results.to_dict(),
                duration_ms=duration_ms,
                timestamp=datetime.now(UTC),
            )

            # Save to database
            conn.execute(
                """
                INSERT INTO category_evolution_snapshots (
                    id, category, before_subcategory_count, before_silhouette,
                    before_total_memories, after_subcategory_count, after_silhouette,
                    after_total_memories, decayed_count, archived_count,
                    bytes_freed, evolution_duration_ms, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    snapshot.id,
                    snapshot.category,
                    snapshot.before_state.get("subcategory_count", 0),
                    snapshot.before_state.get("silhouette"),
                    snapshot.before_state.get("total_memories", 0),
                    snapshot.after_state.get("subcategory_count", 0),
                    snapshot.after_state.get("silhouette"),
                    snapshot.after_state.get("total_memories", 0),
                    snapshot.decay_results.get("removed_count", 0),
                    1 if snapshot.decay_results.get("archived", False) else 0,
                    snapshot.decay_results.get("freed_space", 0),
                    snapshot.duration_ms,
                    snapshot.timestamp,
                ],
            )

            logger.info(f"Saved evolution snapshot {snapshot.id}")

        except Exception as e:
            logger.error(f"Failed to save evolution snapshot: {e}")

    async def get_evolution_history(
        self,
        category: TopLevelCategory,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent evolution snapshots for a category.

        Args:
            category: Category to get history for
            limit: Maximum number of snapshots to return

        Returns:
            List of snapshot dictionaries with improvement summaries
        """
        if self._db_adapter is None:
            logger.debug("No database adapter available, returning empty history")
            return []

        try:
            rows = self._query_evolution_snapshots(category.value, limit)
            snapshots = [self._build_snapshot_dict(row) for row in rows]
            logger.info(f"Retrieved {len(snapshots)} evolution snapshots")
            return snapshots

        except Exception as e:
            logger.error(f"Failed to get evolution history: {e}")
            return []

    def _query_evolution_snapshots(
        self,
        category_value: str,
        limit: int,
    ) -> list[tuple[Any, ...]]:
        """Query evolution snapshots from database.

        Args:
            category_value: Category value to query
            limit: Maximum results to return

        Returns:
            List of snapshot row tuples
        """
        conn = self._db_adapter.conn
        return conn.execute(
            """
            SELECT
                id, category, before_subcategory_count, before_silhouette,
                before_total_memories, after_subcategory_count, after_silhouette,
                after_total_memories, decayed_count, archived_count,
                bytes_freed, evolution_duration_ms, timestamp
            FROM category_evolution_snapshots
            WHERE category = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            [category_value, limit],
        ).fetchall()

    def _build_snapshot_dict(self, row: tuple[Any, ...]) -> dict[str, Any]:
        """Build a snapshot dictionary from a database row.

        Args:
            row: Database row containing snapshot data

        Returns:
            Snapshot dictionary with all fields and summary
        """
        (
            snapshot_id,
            cat,
            before_count,
            before_sil,
            before_memories,
            after_count,
            after_sil,
            after_memories,
            decayed,
            archived,
            bytes_freed,
            duration_ms,
            timestamp,
        ) = row

        silhouette_delta = (after_sil or 0.0) - (before_sil or 0.0)
        count_delta = after_count - before_count

        return {
            "id": snapshot_id,
            "category": cat,
            "timestamp": timestamp.isoformat() if timestamp else None,
            "summary": self._format_snapshot_summary(
                silhouette_delta,
                count_delta,
                bytes_freed,
            ),
            "before_silhouette": before_sil,
            "after_silhouette": after_sil,
            "before_subcategory_count": before_count,
            "after_subcategory_count": after_count,
            "decayed_count": decayed,
            "archived_count": archived,
            "bytes_freed": bytes_freed,
            "duration_ms": duration_ms,
        }

    def _format_snapshot_summary(
        self, silhouette_delta: float, count_delta: int, bytes_freed: int
    ) -> str:
        """Format a human-readable summary of evolution changes.

        Args:
            silhouette_delta: Change in silhouette score
            count_delta: Change in subcategory count
            bytes_freed: Bytes freed by decay

        Returns:
            Formatted summary string
        """
        level = self._get_improvement_level(silhouette_delta)
        count_change = self._get_count_change_description(count_delta)
        storage = f" freed {_format_bytes(bytes_freed)}" if bytes_freed > 0 else ""

        return (
            f"{level} (silhouette: {silhouette_delta:+.2f}), {count_change},{storage}."
        )

    def _get_improvement_level(self, silhouette_delta: float) -> str:
        """Get improvement level description from silhouette delta.

        Args:
            silhouette_delta: Change in silhouette score

        Returns:
            Description string of improvement level
        """
        if silhouette_delta > 0.1:
            return "Significant improvement"
        if silhouette_delta > 0:
            return "Moderate improvement"
        if silhouette_delta > -0.1:
            return "Minor change (acceptable)"
        return f"Quality decreased: {silhouette_delta:.2f} \u26a0"

    def _get_count_change_description(self, count_delta: int) -> str:
        """Get description of subcategory count change.

        Args:
            count_delta: Change in subcategory count

        Returns:
            Description string
        """
        if count_delta > 0:
            return f"Created {count_delta} subcategories"
        if count_delta < 0:
            return f"Removed {abs(count_delta)} subcategories"
        return "Maintained subcategory count"


def _format_bytes(bytes_count: float) -> str:
    """Format bytes as human-readable string.

    Args:
        bytes_count: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 KB", "2.3 MB")
    """
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_count < 1024:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f} TB"
