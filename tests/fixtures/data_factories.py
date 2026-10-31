"""Data factories for generating test data for session-mgmt-mcp tests.

Uses factory_boy and faker to generate realistic test data for:
- Reflections and conversations (used in performance tests)
- Security testing scenarios (used in security tests)
- Large dataset generation (used in performance tests)

Note: After DI migration cleanup (Phase 2.7), unused factories have been removed.
Only factories with active test usage remain.
"""

import random
import uuid
from datetime import datetime, timedelta

import factory
from faker import Faker

from session_buddy.memory.embedding_dim import DEFAULT_EMBEDDING_DIM

fake = Faker()


class ReflectionDataFactory(factory.Factory):
    """Factory for reflection and conversation test data."""

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n)
    content = factory.LazyAttribute(lambda obj: fake.paragraph(nb_sentences=3))
    project = factory.LazyAttribute(lambda obj: fake.slug())
    timestamp = factory.LazyFunction(
        lambda: datetime.now()
        - timedelta(
            days=random.randint(0, 30),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        ),
    )
    tags = factory.LazyFunction(
        lambda: random.sample(
            [
                "authentication",
                "database",
                "api",
                "frontend",
                "backend",
                "testing",
                "deployment",
                "security",
                "performance",
                "bug-fix",
                "feature",
                "refactoring",
                "documentation",
                "monitoring",
            ],
            k=random.randint(1, 4),
        ),
    )

    # Embedding simulation (canonical-width vector)
    embedding = factory.LazyFunction(
        lambda: [random.uniform(-1, 1) for _ in range(DEFAULT_EMBEDDING_DIM)],
    )

    # Conversation metadata
    conversation_length = factory.LazyAttribute(lambda obj: random.randint(100, 2000))
    tool_calls_count = factory.LazyAttribute(lambda obj: random.randint(0, 20))
    error_count = factory.LazyAttribute(lambda obj: random.randint(0, 3))


# Specialized Factories for Complex Scenarios


class LargeDatasetFactory(factory.Factory):
    """Factory for large dataset testing."""

    class Meta:
        model = dict

    @classmethod
    def generate_large_reflection_dataset(cls, count: int = 1000) -> list[dict]:
        """Generate large reflection dataset for performance testing."""
        return ReflectionDataFactory.build_batch(count)

    @classmethod
    def generate_conversation_history(cls, days: int = 30) -> list[dict]:
        """Generate conversation history over specified days."""
        reflections = []
        for day in range(days):
            day_reflections = ReflectionDataFactory.build_batch(random.randint(1, 10))
            for reflection in day_reflections:
                reflection["timestamp"] = datetime.now() - timedelta(days=day)
            reflections.extend(day_reflections)
        return reflections


class SecurityTestDataFactory(factory.Factory):
    """Factory for security testing data."""

    class Meta:
        model = dict

    # Authentication data
    valid_token = factory.LazyFunction(lambda: str(uuid.uuid4()))
    invalid_token = factory.LazyFunction(lambda: "invalid_" + str(uuid.uuid4()))
    expired_token = factory.LazyFunction(lambda: "expired_" + str(uuid.uuid4()))

    # Permission data
    operation = factory.Iterator(
        [
            "read_reflections",
            "write_reflections",
            "delete_reflections",
            "session_init",
            "session_checkpoint",
            "session_end",
            "database_access",
            "file_system_access",
        ],
    )
    permission_level = factory.Iterator(["none", "read", "write", "admin"])

    # Security threats
    malicious_input = factory.Iterator(
        [
            "'; DROP TABLE reflections; --",
            "<script>alert('xss')</script>",
            "../../../../etc/passwd",
            "rm -rf /*",
        ],
    )

    # Rate limiting
    request_rate = factory.LazyAttribute(lambda obj: random.randint(1, 1000))
    rate_limit_threshold = factory.Iterator([10, 50, 100, 500])
