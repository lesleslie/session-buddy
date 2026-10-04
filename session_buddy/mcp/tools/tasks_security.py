"""Input caps, rate limiting, visibility filter for task-system tools.

Implements spec (v1.1) §Authz Model + §Input Limits.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from session_buddy.mcp.tools.tasks_models import Task


# Input caps (per spec §Input Limits).
MAX_CONTENT_BYTES = 4096
MAX_METADATA_BYTES = 1024
MAX_TAGS = 32
MAX_TAG_LEN = 64


@dataclass
class RateLimiter:
    """Sliding-window rate limiter keyed by caller identity.

    Quotas (per spec §Input Limits):

    - tasks_create: 60/min per caller
    - tasks_update + tasks_complete: 120/min per caller
    - tasks_handoff_to_workflow: 10/min per caller
    """

    limit: int
    window_seconds: int = 60
    # ``defaultdict`` so a never-seen caller materializes a fresh empty
    # deque without a KeyError. Per-caller isolation falls out of the
    # dict keying.
    _buckets: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(deque)
    )

    def check(self, caller: str, *, now: float | None = None) -> None:
        """Raise ``RateLimitError`` if caller has exceeded limit in window."""
        current = now if now is not None else time.time()
        window_start = current - self.window_seconds
        bucket = self._buckets[caller]
        # Drop entries that fell out of the sliding window.
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise RateLimitError(
                f"Rate limit exceeded for caller {caller!r}: "
                f"{self.limit}/{self.window_seconds}s. "
                f"Retry after {self.window_seconds - (current - bucket[0]):.0f}s."
            )
        bucket.append(current)


class RateLimitError(Exception):
    """Raised by ``RateLimiter.check()`` when caller exceeds quota."""


def enforce_visibility_filter(caller: str, task: Task) -> bool:
    """Return True iff ``caller`` is allowed to read ``task`` under its visibility.

    - private: caller must match ``task.owner``
    - team: treated as private in v1 (no team ACL yet; v1.1 follow-up)
    - public: anyone
    """
    if task.visibility == "public":
        return True
    if task.visibility == "team":
        return caller == task.owner
    return caller == task.owner
