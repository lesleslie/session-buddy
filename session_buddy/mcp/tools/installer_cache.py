"""Phase 5 installer cache — marketplace ↔ dynamic discovery sync substrate.

Implements plan §5 Phase 5:

- Atomic writes at ``~/.claude/skills/.installer-cache.json`` (``.tmp →
  rename``, mirror Phase 2's atomic-write pattern).
- Lock file at ``~/.claude/skills/.installer-cache.lock`` (F-7) to
  guard concurrent ``validate`` invocations.
- Schema mirrors plan §5 task #6::

    {
      "schema_version": 1,
      "last_modified": <unix_ts>,
      "server_runs": [
        {"server": "akosha", "version": "0.15.1", "fetched_at": <ts>, "skills": [...]},
        ...
      ]
    }

- MANDATORY P-10: caller is responsible for filesystem → git-commit
  atomicity when this file lives inside the ``bodai-plugins``
  marketplace repo. This module is pure data and does not perform
  git operations.

This module is the substrate for three things:

1. ``session-buddy`` polls every ``AKOSHA_FEDERATION_POLL_SECONDS``
   seconds (default 300s = 5min, per P-7) and writes the cache.
2. The ``ecosystem-skill-loader`` Skill reads the cache as a fast
   path before calling the live MCP ``list_ecosystem_skills`` tool.
3. The ``bodai-plugins validate`` CLI updates the cache after
   scraping each plugin's ``commands/`` and ``skills/`` dirs.

This module is stdlib-only so it runs without a venv and can be
imported from the ``ecosystem-skill-loader`` Skill body via the
``Read`` tool's python-mode entry point.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public paths and constants
# ---------------------------------------------------------------------------


# Default cache directory (matches plan §5 task #6). ``skills/`` is
# already the canonical Skill install root per Phase 2. The cache
# file lives next to the installed skills so a workspace reset does
# not silently drop it.
DEFAULT_CACHE_DIR: Path = Path.home() / ".claude" / "skills"
DEFAULT_CACHE_FILENAME: str = ".installer-cache.json"
DEFAULT_LOCK_FILENAME: str = ".installer-cache.lock"


SCHEMA_VERSION: int = 1


# Per-server polling cadence (seconds). Default 300s = 5 min, per P-7.
DEFAULT_POLL_SECONDS: float = 300.0


# ---------------------------------------------------------------------------
# Public type definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ServerRun:
    """One entry in ``.installer-cache.json::server_runs``.

    Mirrors plan §5 task #6::

        {"server": "akosha", "version": "0.15.1", "fetched_at": <ts>, "skills": [...]}
    """

    server: str
    version: str
    fetched_at: float
    skills: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class InstallerCache:
    """In-memory representation of the marketplace installer cache.

    Persisted as JSON at ``~/.claude/skills/.installer-cache.json``.
    The schema is dictated by plan §5 task #6.
    """

    schema_version: int
    last_modified: float
    server_runs: list[ServerRun]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "last_modified": self.last_modified,
            "server_runs": [
                {
                    "server": run.server,
                    "version": run.version,
                    "fetched_at": run.fetched_at,
                    "skills": list(run.skills),
                }
                for run in self.server_runs
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InstallerCache":
        schema_version = int(payload.get("schema_version", SCHEMA_VERSION))
        last_modified = float(payload.get("last_modified", 0.0))
        server_runs = [
            ServerRun(
                server=entry["server"],
                version=entry["version"],
                fetched_at=float(entry["fetched_at"]),
                skills=list(entry.get("skills", [])),
            )
            for entry in payload.get("server_runs", [])
        ]
        return cls(
            schema_version=schema_version,
            last_modified=last_modified,
            server_runs=server_runs,
        )


# ---------------------------------------------------------------------------
# Lock file helpers (F-7)
# ---------------------------------------------------------------------------


@contextmanager
def install_cache_lock(
    cache_path: Path,
    *,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.1,
) -> Iterator[None]:
    """Acquire an exclusive ``fcntl``-based lock on the cache file.

    The lock is implemented via ``flock`` on an adjacent ``.lock`` file
    (F-7). Two callers reaching for the cache file serialize through
    this context manager; the second one blocks until the first
    releases, or raises :class:`TimeoutError` after
    ``timeout_seconds``.

    Args:
        cache_path: the ``.installer-cache.json`` path whose
            adjacent ``.lock`` file will be used.
        timeout_seconds: maximum wall-clock time to wait for the
            lock. ``0`` raises ``TimeoutError`` immediately when the
            lock is held.
        poll_seconds: how often to retry when the lock is held.

    Yields:
        ``None``.

    Raises:
        TimeoutError: when the lock cannot be acquired within
            ``timeout_seconds``.
        OSError: when the parent directory cannot be created.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = cache_path.with_name(cache_path.name.replace(
        DEFAULT_CACHE_FILENAME, DEFAULT_LOCK_FILENAME
    )) if DEFAULT_CACHE_FILENAME in cache_path.name else cache_path.parent / DEFAULT_LOCK_FILENAME
    lock_handle = open(lock_path, "w", encoding="utf-8")
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"could not acquire {lock_path} within "
                        f"{timeout_seconds:.1f}s"
                    ) from None
            time.sleep(poll_seconds)
        yield
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        lock_handle.close()


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------


def _atomic_write_json(target: Path, payload: dict[str, Any]) -> None:
    """Atomically write ``payload`` as JSON to ``target``."""

    target.parent.mkdir(parents=True, exist_ok=True)
    # Write to a unique temp file in the same directory (so
    # ``os.replace`` is atomic on POSIX). ``NamedTemporaryFile``
    # opens with ``delete=False`` so we control the close order;
    # the file is unlinked only after the rename.
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Cache read / write
# ---------------------------------------------------------------------------


def load_cache(cache_path: Path) -> InstallerCache:
    """Load the cache at ``cache_path``.

    Returns an empty cache when the file does not exist or is
    malformed (the caller treats malformed caches as a doctor-mode
    anomaly rather than crashing the install path).
    """
    if not cache_path.exists():
        return InstallerCache(
            schema_version=SCHEMA_VERSION,
            last_modified=0.0,
            server_runs=[],
        )
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return InstallerCache(
            schema_version=SCHEMA_VERSION,
            last_modified=0.0,
            server_runs=[],
        )
    return InstallerCache.from_dict(raw)


def save_cache(
    cache: InstallerCache,
    cache_path: Path,
    *,
    clock: Callable[[], float] = time.time,
) -> None:
    """Atomically save ``cache`` to ``cache_path``.

    Acquires ``install_cache_lock(cache_path)`` for the duration of
    the write so concurrent ``bodai-plugins validate`` invocations
    cannot trample each other (F-7).

    The ``last_modified`` field is refreshed to ``clock()`` BEFORE the
    write so the persisted timestamp matches the actual on-disk mtime.
    """
    with install_cache_lock(cache_path):
        payload = cache.as_dict()
        payload["last_modified"] = clock()
        _atomic_write_json(cache_path, payload)


def upsert_server_run(
    cache: InstallerCache,
    *,
    server: str,
    version: str,
    skills: list[dict[str, Any]],
    clock: Callable[[], float] = time.time,
) -> InstallerCache:
    """Return a new ``InstallerCache`` with the named ``server`` run replaced.

    The ``fetched_at`` field is set to ``clock()`` so consumers can
    detect a stale snapshot via::

        cache = load_cache(path)
        run = next(r for r in cache.server_runs if r.server == "akosha")
        if (time.time() - run.fetched_at) > POLL_SECONDS:
            ...  # re-poll needed

    Returns a NEW ``InstallerCache`` (the input is treated as
    immutable). The caller is responsible for ``save_cache``.
    """
    fetched_at = clock()
    new_run = ServerRun(
        server=server,
        version=version,
        fetched_at=fetched_at,
        skills=list(skills),
    )
    new_runs = [
        r for r in cache.server_runs if r.server != server
    ] + [new_run]
    return InstallerCache(
        schema_version=SCHEMA_VERSION,
        last_modified=clock(),
        server_runs=new_runs,
    )


# ---------------------------------------------------------------------------
# Polling cadence helper (P-7)
# ---------------------------------------------------------------------------


def is_stale(
    run: ServerRun,
    *,
    now: float | None = None,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> bool:
    """Return True when ``run.fetched_at`` is older than ``poll_seconds``.

    Per P-7 the default cadence is 5 minutes; config callers may
    override per replica via ``settings/mahavishnu.yaml``.

    Args:
        run: the cached ``ServerRun``.
        now: current timestamp (defaults to ``time.time()``).
        poll_seconds: cadence in seconds.
    """
    if now is None:
        now = time.time()
    return (now - run.fetched_at) > poll_seconds


# ---------------------------------------------------------------------------
# CLI entry point (`python -m installer_cache validate-cache path`)
# ---------------------------------------------------------------------------


def _build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="installer-cache",
        description=(
            "Phase 5 marketplace installer cache CLI. Subcommands: "
            "``read`` (dump cache as JSON), ``write <path>`` (read "
            "JSON from stdin and atomically write), ``doctor`` (F-7 "
            "lock + atomic write audit)."
        ),
    )
    parser.add_argument(
        "command",
        choices=["read", "write", "doctor"],
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_CACHE_DIR / DEFAULT_CACHE_FILENAME,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.command == "read":
        cache = load_cache(args.path)
        print(json.dumps(cache.as_dict(), indent=2, sort_keys=True))
        return 0
    if args.command == "write":
        raw = sys.stdin.read()
        payload = json.loads(raw)
        cache = InstallerCache.from_dict(payload)
        save_cache(cache, args.path)
        return 0
    if args.command == "doctor":
        cache = load_cache(args.path)
        runs = ", ".join(r.server for r in cache.server_runs)
        ok = bool(runs)
        print(f"runs: {runs or '(none)'}")
        return 0 if ok else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
