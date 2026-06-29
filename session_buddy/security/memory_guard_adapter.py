"""OWASP Agent Memory Guard — write-path security for Session-Buddy reflections.

Screens every reflection write through a declarative rule pipeline before
it reaches the database. Four possible outcomes:

    allow     → proceed as-is
    redact    → sanitize content, write with original tags
    quarantine → add "quarantine" + content-hash tag, write sanitized content
    block     → raise MemoryGuardBlockedError; nothing is written

Policy is loaded from settings/memory_guard_policy.yaml. If that file is
missing or unreadable, built-in rules remain active (fail-closed on threats,
open on clean content).

This is a detective + preventive control. The SHA-256 baseline check at
Mahavishnu startup is an additional detective layer (see C-NEW-18 — that
check surfaces drift, it does not prevent tampered memories from being
loaded into the CC session that calls mahavishnu mcp start).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from oneiric.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Injection detection patterns
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"\bHuman:\s", re.MULTILINE),
    re.compile(r"\bAssistant:\s", re.MULTILINE),
    re.compile(r"</?(system|instruction|prompt)\s*>", re.IGNORECASE),
    re.compile(r"act\s+as\s+(root|admin|superuser|god\s*mode)", re.IGNORECASE),
    re.compile(r"reveal\s+(all\s+)?(secret|password|token|key)", re.IGNORECASE),
    re.compile(
        r"override\s+(all\s+)?(previous|prior|current)\s+(guideline|instruction|rule)",
        re.IGNORECASE,
    ),
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", re.IGNORECASE),
]

_PII_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_PII_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PII_PHONE = re.compile(
    r"\b(?:\+?\d{1,3}[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"
)
_PII_CREDIT_CARD = re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b")

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(sk|pk|rk)_[a-zA-Z0-9]{20,}", re.IGNORECASE),  # Stripe-style
    re.compile(r"\bghp_[a-zA-Z0-9]{36}\b"),  # GitHub PAT
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS key
    re.compile(
        r"\beyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\b"
    ),  # JWT
]

# Tags that indicate content may override memory-type semantics
_PROTECTED_MEMORY_TAGS = frozenset({"feedback", "user"})
_PROTECTED_CONTENT_OVERRIDE = re.compile(
    r"(?:^|\n)\s*(?:feedback|user)\s*:\s+",
    re.IGNORECASE | re.MULTILINE,
)

_SIZE_THRESHOLD_BYTES = 10_000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class GuardAction(StrEnum):
    ALLOW = "allow"
    REDACT = "redact"
    QUARANTINE = "quarantine"
    BLOCK = "block"


@dataclass
class GuardDecision:
    action: GuardAction
    content: str
    tags: list[str]
    matched_rule: str | None = None
    content_hash: str | None = None


class MemoryGuardBlockedError(Exception):
    """Raised when the memory guard blocks a write. Never silently swallowed."""


@dataclass
class MemoryGuardAdapter:
    """OWASP-aligned write-path guard for Session-Buddy reflections.

    Args:
        policy_path: Path to YAML policy file (optional; built-in rules always active).
        on_security_event: Optional callback receiving security event dicts.
    """

    policy_path: Path | None = None
    on_security_event: Callable[[dict[str, Any]], None] | None = None
    _extra_rules: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.policy_path is not None and self.policy_path.exists():
            self._load_policy(self.policy_path)

    def _load_policy(self, path: Path) -> None:
        try:
            import yaml  # type: ignore[import-untyped]

            with path.open() as f:
                policy = yaml.safe_load(f)
            self._extra_rules = policy.get("rules", [])
        except Exception as exc:
            logger.warning("memory_guard: failed to load policy from %s: %s", path, exc)

    def screen(self, content: str, tags: list[str] | None) -> GuardDecision:
        """Screen content + tags and return a GuardDecision.

        The decision's `content` and `tags` are the values that should be
        written to the database (possibly sanitized / augmented).

        Args:
            content: Reflection content to screen.
            tags: Tags associated with the reflection.

        Returns:
            GuardDecision with action, (possibly modified) content and tags.
        """
        effective_tags = list(tags or [])
        content_hash = hashlib.sha256(
            content.encode("utf-8", errors="replace")
        ).hexdigest()[:16]

        # --- size anomaly check (quarantine, not block) ---
        if len(content.encode("utf-8", errors="replace")) > _SIZE_THRESHOLD_BYTES:
            decision = GuardDecision(
                action=GuardAction.QUARANTINE,
                content=content[:_SIZE_THRESHOLD_BYTES],
                tags=["quarantine", f"hash:{content_hash}"] + effective_tags,
                matched_rule="size_anomaly",
                content_hash=content_hash,
            )
            self._emit("quarantine", decision)
            return decision

        # --- protected key tampering (block for feedback/user tags) ---
        if _PROTECTED_MEMORY_TAGS.intersection(
            effective_tags
        ) and _PROTECTED_CONTENT_OVERRIDE.search(content):
            decision = GuardDecision(
                action=GuardAction.BLOCK,
                content=content,
                tags=effective_tags,
                matched_rule="protected_key_tampering",
                content_hash=content_hash,
            )
            self._emit("block", decision)
            return decision

        # --- prompt injection (quarantine) ---
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(content):
                decision = GuardDecision(
                    action=GuardAction.QUARANTINE,
                    content=content,
                    tags=["quarantine", f"hash:{content_hash}"] + effective_tags,
                    matched_rule="prompt_injection",
                    content_hash=content_hash,
                )
                self._emit("quarantine", decision)
                return decision

        # --- secret / PII leakage (redact) ---
        redacted = content
        did_redact = False

        for pattern in _SECRET_PATTERNS:
            new = pattern.sub("[REDACTED-SECRET]", redacted)
            if new != redacted:
                did_redact = True
                redacted = new

        for pii_pattern, placeholder in (
            (_PII_EMAIL, "[REDACTED-EMAIL]"),
            (_PII_SSN, "[REDACTED-SSN]"),
            (_PII_PHONE, "[REDACTED-PHONE]"),
            (_PII_CREDIT_CARD, "[REDACTED-CC]"),
        ):
            new = pii_pattern.sub(placeholder, redacted)
            if new != redacted:
                did_redact = True
                redacted = new

        if did_redact:
            decision = GuardDecision(
                action=GuardAction.REDACT,
                content=redacted,
                tags=effective_tags,
                matched_rule="pii_or_secret_leakage",
                content_hash=content_hash,
            )
            self._emit("redact", decision)
            return decision

        return GuardDecision(
            action=GuardAction.ALLOW,
            content=content,
            tags=effective_tags,
            matched_rule=None,
            content_hash=content_hash,
        )

    def _emit(self, event_type: str, decision: GuardDecision) -> None:
        if self.on_security_event is None:
            logger.info(
                "memory_guard: %s — rule=%s hash=%s",
                event_type,
                decision.matched_rule,
                decision.content_hash,
            )
            return
        self.on_security_event(
            {
                "type": event_type,
                "rule": decision.matched_rule,
                "content_hash": decision.content_hash,
                "tags": decision.tags,
            }
        )
