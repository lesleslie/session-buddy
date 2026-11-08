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
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

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

#: Upper bound on a serialised metadata document, in bytes.
#:
#: This is an INDEPENDENT limit from ``_SIZE_THRESHOLD_BYTES`` (which
#: bounds a reflection BODY): the metadata document is a different
#: thing, and it LEGITIMATELY grows — the task system's document
#: carries the task's append-only history, which gains an entry per
#: update (roughly 200 bytes each).
#:
#: 256 KiB is about 1 300 updates' worth of history. Past that the
#: right answer is not a bigger row but a separate table for the
#: history. The caller-facing bag is capped far lower (1 KiB) by the
#: task model; this is the last line of defence for any other writer.
MAX_METADATA_BYTES = 262_144

#: Server-set fields whose values are principals, identifiers or
#: timestamps. They are NEVER rewritten by the metadata screen.
#:
#: A principal is ``user:<email>`` — and the PII redactor matches the
#: email inside it. Rewriting the owner to ``user:[REDACTED-EMAIL]``
#: collapses the task's access control: every authorization decision
#: compares the owner against the caller's identity, and a redacted
#: owner matches nobody. So the screen skips these keys entirely,
#: at any depth.
_PROTECTED_METADATA_KEYS = frozenset(
    {
        # principals
        "owner",
        "created_by",
        "completed_by",
        "workflow_linked_by",
        "actor",
        # identifiers and discriminators
        "kind",
        "task_id",
        "uuid_alias",
        "visibility",
        "status",
        "priority",
        "effort",
        "workflow_id",
        "workflow_linked_at",
        # timestamps and structural values
        "created_at",
        "updated_at",
        "completed_at",
        "due_at",
        "parent_task_id",
        "field",
        "at",
    },
)

#: The key holding the append-only audit trail. Values inside it are
#: REDACTED rather than dropped: deleting a recorded value would delete
#: a record of a change.
_HISTORY_KEY = "history"

#: Sentinel returned by ``_screen_metadata_value`` for a value that must
#: not be written at all (an injection). ``None`` cannot be the sentinel
#: because ``None`` is a legitimate JSON value.
_DROP = object()


def _contains_injection(text: str) -> bool:
    """True when any injection pattern matches this string."""
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def _redact_text(text: str) -> str:
    """Apply the secret + PII patterns to one string."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED-SECRET]", redacted)
    for pii_pattern, placeholder in (
        (_PII_EMAIL, "[REDACTED-EMAIL]"),
        (_PII_SSN, "[REDACTED-SSN]"),
        (_PII_PHONE, "[REDACTED-PHONE]"),
        (_PII_CREDIT_CARD, "[REDACTED-CC]"),
    ):
        redacted = pii_pattern.sub(placeholder, redacted)
    return redacted


def _stronger(left: GuardAction, right: GuardAction) -> GuardAction:
    """Return the more severe of two actions (QUARANTINE > REDACT > ALLOW)."""
    rank = {GuardAction.ALLOW: 0, GuardAction.REDACT: 1, GuardAction.QUARANTINE: 2}
    return left if rank[left] >= rank[right] else right


def _screen_metadata_key(key: Any) -> tuple[Any, GuardAction]:
    """Screen a document KEY.

    A key is as readable as a value: an injection hidden in a key
    reaches the model just as surely as one hidden in a value.
    """
    if not isinstance(key, str):
        return key, GuardAction.ALLOW
    if _contains_injection(key):
        return _DROP, GuardAction.QUARANTINE
    redacted = _redact_text(key)
    if redacted != key:
        return redacted, GuardAction.REDACT
    return key, GuardAction.ALLOW


def _screen_metadata_value(
    value: Any,
    *,
    drop_injections: bool = True,
) -> tuple[Any, GuardAction]:
    """Screen one metadata value, recursing into containers.

    Strings are screened individually: an injection DROPS the value (its
    key or list item goes), a secret or PII match REDACTS it in place.
    Everything else is returned unchanged.

    ``drop_injections=False`` switches the injection rule from DROP to
    REDACT. The audit trail uses it: a history entry records a field's
    before/after values, and deleting the value would delete a RECORD
    of a change — a silent loss in the audit trail, which is the very
    thing the history exists to prevent. There the value is replaced
    with an explicit marker instead.
    """
    if isinstance(value, str):
        if _contains_injection(value):
            if drop_injections:
                return _DROP, GuardAction.QUARANTINE
            return "[REDACTED-INJECTION]", GuardAction.QUARANTINE
        redacted = _redact_text(value)
        if redacted != value:
            return redacted, GuardAction.REDACT
        return value, GuardAction.ALLOW
    if isinstance(value, dict):
        screened: dict[Any, Any] = {}
        action = GuardAction.ALLOW
        for key, item in value.items():
            if isinstance(key, str) and key in _PROTECTED_METADATA_KEYS:
                # A principal, identifier or timestamp: never rewritten.
                screened[key] = item
                continue
            new_key, key_action = _screen_metadata_key(key)
            action = _stronger(action, key_action)
            if new_key is _DROP:
                continue
            new_item, item_action = _screen_metadata_value(
                item,
                drop_injections=drop_injections and key != _HISTORY_KEY,
            )
            action = _stronger(action, item_action)
            if new_item is _DROP:
                continue
            screened[new_key] = new_item
        return screened, action
    if isinstance(value, list | tuple):
        screened_list: list[Any] = []
        action = GuardAction.ALLOW
        for item in value:
            new_item, item_action = _screen_metadata_value(
                item,
                drop_injections=drop_injections,
            )
            action = _stronger(action, item_action)
            if new_item is _DROP:
                continue
            screened_list.append(new_item)
        return screened_list, action
    return value, GuardAction.ALLOW


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


class _EmittableDecision(Protocol):
    """The attributes the shared security-event path reports on.

    Both :class:`GuardDecision` (content) and
    :class:`MetadataGuardDecision` (metadata) satisfy it.
    """

    matched_rule: str | None
    content_hash: str | None
    tags: list[str]


@dataclass
class MetadataGuardDecision:
    """The outcome of screening a metadata document.

    Mirrors :class:`GuardDecision` for the metadata channel: the
    ``metadata`` attribute carries the document that should be written.

    ``QUARANTINE`` here means "an injection was found in this document
    and the offending VALUE was removed" — not "the whole document was
    discarded". A task's metadata document is server-built and holds
    the task's identity (``owner``, ``task_id``, ``kind``); dropping the
    document would destroy the task. The free-text VALUES are what carry
    an injection, so those are what go.
    """

    action: GuardAction
    metadata: dict[str, Any]
    matched_rule: str | None = None
    content_hash: str | None = None
    #: Present so the shared ``_emit`` path can report the event.
    tags: list[str] = field(default_factory=list)


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
        except (
            OSError,
            ImportError,
            AttributeError,
            ValueError,
            yaml.YAMLError,
        ) as exc:
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

    def screen_metadata(self, metadata: dict[str, Any] | None) -> MetadataGuardDecision:
        """Screen a metadata document with the same rules as the content.

        The metadata document is a SECOND write channel into the same
        canonical store: it is persisted alongside the content and read
        back into future contexts. Screening only the content leaves it
        unscreened — a caller can park a prompt injection or a
        credential in it and have it surface later.

        The rules applied are the ones that make sense for a structured
        document: prompt injection (the offending value is DROPPED) and
        secret / PII leakage (the value is REDACTED in place). The size
        rule is not applied here — the adapter caps the document at the
        write path — and the protected-key rule governs the memory
        BODY's semantics, not a metadata bag.

        Args:
            metadata: The document about to be written (``None`` or an
                empty document is allowed).

        Returns:
            The decision and the document that should be written.
        """
        if not metadata:
            return MetadataGuardDecision(action=GuardAction.ALLOW, metadata={})

        serialized = json.dumps(metadata, sort_keys=True, default=str)
        content_hash = hashlib.sha256(
            serialized.encode("utf-8", errors="replace"),
        ).hexdigest()[:16]

        screened, action = _screen_metadata_value(metadata)
        if action == GuardAction.ALLOW:
            return MetadataGuardDecision(
                action=GuardAction.ALLOW,
                metadata=metadata,
                content_hash=content_hash,
            )

        rule = (
            "prompt_injection"
            if action == GuardAction.QUARANTINE
            else "pii_or_secret_leakage"
        )
        decision = MetadataGuardDecision(
            action=action,
            metadata=screened,
            matched_rule=rule,
            content_hash=content_hash,
        )
        self._emit(
            "quarantine" if action == GuardAction.QUARANTINE else "redact", decision
        )
        return decision

    def _emit(self, event_type: str, decision: _EmittableDecision) -> None:
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
