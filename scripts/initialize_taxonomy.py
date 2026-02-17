#!/usr/bin/env python3
"""Initialize skills taxonomy with predefined categories, modalities, and dependencies.

This script populates the Phase 4 skills taxonomy tables with predefined data:
- skill_categories: Hierarchical categories for organizing skills
- skill_modalities: Multi-modal skill type definitions
- skill_dependencies: Co-occurrence relationships between skills

Usage:
    python scripts/initialize_taxonomy.py

The script is idempotent - it can be run multiple times safely.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ============================================================================
# Logging Configuration
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ============================================================================
# Taxonomy Data
# ============================================================================

# Predefined skill categories
CATEGORIES = [
    {
        "category_name": "Code Quality",
        "description": "Tools for checking and improving code quality",
        "domain": "code",
        "examples": ["ruff-check", "mypy", "pylint", "black-format", "isort"],
    },
    {
        "category_name": "Testing",
        "description": "Test execution and coverage tools",
        "domain": "testing",
        "examples": [
            "pytest-run",
            "coverage-report",
            "hypothesis-test",
            "pytest-watch",
        ],
    },
    {
        "category_name": "Documentation",
        "description": "Documentation generation and checking",
        "domain": "documentation",
        "examples": ["sphinx-build", "docstring-check", "api-docs", "markdown-lint"],
    },
    {
        "category_name": "Build & Deploy",
        "description": "Build and deployment tools",
        "domain": "deployment",
        "examples": ["docker-build", "k8s-deploy", "terraform-apply", "github-release"],
    },
    {
        "category_name": "Git & Version Control",
        "description": "Git and version control operations",
        "domain": "code",
        "examples": ["git-commit", "git-push", "git-status", "git-diff"],
    },
    {
        "category_name": "Linting & Formatting",
        "description": "Code linting and auto-formatting",
        "domain": "code",
        "examples": ["ruff-check", "black-format", "isort", "autopep8"],
    },
]

# Multi-modal skill type definitions
MODALITIES = [
    {
        "skill_name": "ruff-check",
        "modality_type": "code",
        "input_format": "python_source",
        "output_format": "diagnostics",
        "requires_human_review": False,
    },
    {
        "skill_name": "pytest-run",
        "modality_type": "testing",
        "input_format": "python_tests",
        "output_format": "test_results",
        "requires_human_review": False,
    },
    {
        "skill_name": "sphinx-build",
        "modality_type": "documentation",
        "input_format": "rst_docs",
        "output_format": "html_docs",
        "requires_human_review": True,
    },
    {
        "skill_name": "docker-build",
        "modality_type": "deployment",
        "input_format": "dockerfile",
        "output_format": "docker_image",
        "requires_human_review": False,
    },
]

# Skill co-occurrence dependencies
DEPENDENCIES = [
    {
        "skill_a": "ruff-check",
        "skill_b": "black-format",
        "expected_lift": 3.5,  # Often used together
    },
    {
        "skill_a": "pytest-run",
        "skill_b": "coverage-report",
        "expected_lift": 2.8,  # Coverage after tests
    },
    {
        "skill_a": "git-commit",
        "skill_b": "git-push",
        "expected_lift": 4.2,  # Commit then push
    },
    {
        "skill_a": "docker-build",
        "skill_b": "k8s-deploy",
        "expected_lift": 2.1,  # Build then deploy
    },
]


# ============================================================================
# Database Operations
# ============================================================================


def check_migration_applied(db_path: Path) -> bool:
    """Check if V4 migration has been applied.

    Args:
        db_path: Path to database file

    Returns:
        True if V4 migration applied, False otherwise
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Check for skill_categories table (added in V4)
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='skill_categories'
                """
            )

            return cursor.fetchone() is not None

    except sqlite3.Error as e:
        logger.error(f"Failed to check migration status: {e}")
        return False


def initialize_categories(db_path: Path) -> int:
    """Initialize skill categories.

    Args:
        db_path: Path to database file

    Returns:
        Number of categories inserted
    """
    inserted = 0

    try:
        with sqlite3.connect(db_path) as conn:
            for category in CATEGORIES:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO skill_categories
                        (category_name, description, domain, created_at)
                        VALUES (?, ?, ?, datetime('now'))
                        """,
                        (
                            category["category_name"],
                            category["description"],
                            category["domain"],
                        ),
                    )
                    if conn.total_changes > 0:
                        inserted += 1
                        logger.info(
                            f"  ✓ Category: {category['category_name']} ({category['domain']})"
                        )

                except sqlite3.Error as e:
                    logger.warning(
                        f"  ✗ Failed to insert category {category['category_name']}: {e}"
                    )

            conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Failed to initialize categories: {e}")
        return 0

    return inserted


def initialize_modalities(db_path: Path) -> int:
    """Initialize skill modality types.

    Args:
        db_path: Path to database file

    Returns:
        Number of modalities inserted
    """
    inserted = 0

    try:
        with sqlite3.connect(db_path) as conn:
            for modality in MODALITIES:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO skill_modalities
                        (skill_name, modality_type, input_format, output_format,
                         requires_human_review, created_at)
                        VALUES (?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (
                            modality["skill_name"],
                            modality["modality_type"],
                            modality["input_format"],
                            modality["output_format"],
                            1 if modality["requires_human_review"] else 0,
                        ),
                    )
                    if conn.total_changes > 0:
                        inserted += 1
                        logger.info(
                            f"  ✓ Modality: {modality['skill_name']} "
                            f"({modality['modality_type']}: "
                            f"{modality['input_format']} → {modality['output_format']})"
                        )

                except sqlite3.Error as e:
                    logger.warning(
                        f"  ✗ Failed to insert modality {modality['skill_name']}: {e}"
                    )

            conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Failed to initialize modalities: {e}")
        return 0

    return inserted


def initialize_dependencies(db_path: Path) -> int:
    """Initialize skill dependencies.

    Args:
        db_path: Path to database file

    Returns:
        Number of dependencies inserted
    """
    inserted = 0

    try:
        with sqlite3.connect(db_path) as conn:
            for dep in DEPENDENCIES:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO skill_dependencies
                        (skill_a, skill_b, co_occurrence_count, lift_score, last_updated)
                        VALUES (?, ?, 1, ?, datetime('now'))
                        """,
                        (dep["skill_a"], dep["skill_b"], dep["expected_lift"]),
                    )
                    if conn.total_changes > 0:
                        inserted += 1
                        logger.info(
                            f"  ✓ Dependency: {dep['skill_a']} ↔ {dep['skill_b']} "
                            f"(lift: {dep['expected_lift']})"
                        )

                except sqlite3.Error as e:
                    logger.warning(
                        f"  ✗ Failed to insert dependency {dep['skill_a']}→{dep['skill_b']}: {e}"
                    )

            conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Failed to initialize dependencies: {e}")
        return 0

    return inserted


def verify_initialization(db_path: Path) -> dict[str, int]:
    """Verify taxonomy initialization by counting records.

    Args:
        db_path: Path to database file

    Returns:
        Dictionary with counts for each table
    """
    counts = {
        "categories": 0,
        "modalities": 0,
        "dependencies": 0,
    }

    try:
        with sqlite3.connect(db_path) as conn:
            # Count categories
            cursor = conn.execute("SELECT COUNT(*) FROM skill_categories")
            counts["categories"] = cursor.fetchone()[0]

            # Count modalities
            cursor = conn.execute("SELECT COUNT(*) FROM skill_modalities")
            counts["modalities"] = cursor.fetchone()[0]

            # Count dependencies
            cursor = conn.execute("SELECT COUNT(*) FROM skill_dependencies")
            counts["dependencies"] = cursor.fetchone()[0]

    except sqlite3.Error as e:
        logger.error(f"Failed to verify initialization: {e}")

    return counts


def display_summary(counts: dict[str, int]) -> None:
    """Display initialization summary.

    Args:
        counts: Dictionary with record counts
    """
    logger.info("\n" + "=" * 60)
    logger.info("TAXONOMY INITIALIZATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Categories:     {counts['categories']} records")
    logger.info(f"Modalities:      {counts['modalities']} records")
    logger.info(f"Dependencies:    {counts['dependencies']} records")
    logger.info("=" * 60)

    if counts["categories"] > 0:
        logger.info("\nCategories initialized:")
        with sqlite3.connect(Path(".session-buddy/skills.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT category_name, domain, description
                FROM skill_categories
                ORDER BY category_name
                """
            )
            for row in cursor.fetchall():
                logger.info(f"  • {row['category_name']:20s} [{row['domain']}]")
                logger.info(f"    {row['description']}")

    if counts["modalities"] > 0:
        logger.info("\nModalities initialized:")
        with sqlite3.connect(Path(".session-buddy/skills.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT skill_name, modality_type, input_format, output_format
                FROM skill_modalities
                ORDER BY skill_name
                """
            )
            for row in cursor.fetchall():
                review_flag = " [requires review]" if row["output_format"] else ""
                logger.info(
                    f"  • {row['skill_name']:20s} [{row['modality_type']}]{review_flag}"
                )
                logger.info(f"    {row['input_format']} → {row['output_format']}")

    if counts["dependencies"] > 0:
        logger.info("\nDependencies initialized:")
        with sqlite3.connect(Path(".session-buddy/skills.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT skill_a, skill_b, lift_score
                FROM skill_dependencies
                ORDER BY lift_score DESC
                """
            )
            for row in cursor.fetchall():
                logger.info(
                    f"  • {row['skill_a']} ↔ {row['skill_b']:20s} "
                    f"(lift: {row['lift_score']:.1f})"
                )


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> int:
    """Main initialization routine.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    # Database path
    db_path = Path(".session-buddy/skills.db")

    # Check if database exists
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        logger.error("Please run Session-Buddy migration first.")
        return 1

    # Check if V4 migration applied
    logger.info("Checking migration status...")
    if not check_migration_applied(db_path):
        logger.error("V4 migration not applied.")
        logger.error("Please run V4 migration first:")
        logger.error("  python -m session_buddy.storage.migrations migrate")
        return 1

    logger.info("✓ V4 migration verified\n")

    # Initialize taxonomy
    logger.info("Initializing skills taxonomy...\n")

    logger.info("Step 1: Initializing categories...")
    categories_count = initialize_categories(db_path)
    logger.info(f"Categories initialized: {categories_count}\n")

    logger.info("Step 2: Initializing modalities...")
    modalities_count = initialize_modalities(db_path)
    logger.info(f"Modalities initialized: {modalities_count}\n")

    logger.info("Step 3: Initializing dependencies...")
    dependencies_count = initialize_dependencies(db_path)
    logger.info(f"Dependencies initialized: {dependencies_count}\n")

    # Verify and display summary
    logger.info("Verifying initialization...")
    counts = verify_initialization(db_path)

    if (
        counts["categories"] == 0
        and counts["modalities"] == 0
        and counts["dependencies"] == 0
    ):
        logger.warning("No records inserted (may already exist)")
        display_summary(counts)
        return 0

    display_summary(counts)

    logger.info("\n✓ Taxonomy initialization complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
