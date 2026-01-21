"""Memory module for Session Buddy.

This module contains memory-related features including:
- Conscious agent operations
- Entity extraction
- Schema definitions
- Migration utilities
- Persistence management
- Category evolution system (Phase 5)
"""

from session_buddy.memory.category_evolution import (  # noqa: F401
    CategoryAssignment,
    CategoryEvolutionEngine,
    KeywordExtractor,
    Subcategory,
    SubcategoryClusterer,
    SubcategoryMatch,
    TopLevelCategory,
)

__all__ = [
    "CategoryAssignment",
    "CategoryEvolutionEngine",
    "KeywordExtractor",
    "Subcategory",
    "SubcategoryClusterer",
    "SubcategoryMatch",
    "TopLevelCategory",
]
