"""Ambient capture of git commits from sibling repos.

Returns per-repo groups (dict[str, list[CommitEntry]]) plus per-repo
failure names. Per-repo timeout 10s, per-batch timeout 30s, transient
git failure retry 2x with backoff. Never raises.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from datetime import datetime
from itertools import starmap
from pathlib import Path

import yaml
from oneiric.core.logging import get_logger

from session_buddy.core.checkpoint.manifest_resolver import resolve_manifest_path
from session_buddy.memory.cross_repo_work import CommitEntry

_log = get_logger(__name__)

_PER_REPO_TIMEOUT_S = 10.0
_BATCH_TIMEOUT_S = 30.0
_MAX_COMMITS = 500
_GIT_RETRY_BACKOFF_S = (0.25, 0.75)
_TRANSIENT_GIT_EXIT_CODES = frozenset({128, 129})  # lock-related

# Strip C0 control characters (NUL, \t, \n, \r, escape sequences, etc.)
# from git porcelain output so a malicious sibling repo cannot smuggle fake
# log lines or terminal escape codes through our logging and downstream
# markdown renderers. Also neutralize < and > in the parsed values to
# prevent forged-boundary attacks on the `name <email>` author field.
_CTRL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_field(value: str) -> str:
    """Strip C0 control characters; neutralize angle brackets."""
    return _CTRL_CHARS_RE.sub("", value).replace("<", "(").replace(">", ")")


class AmbientPuller:
    def __init__(
        self,
        manifest_path: Path | None = None,
        *,
        git_bin: Path | None = None,
    ) -> None:
        self._manifest_path = resolve_manifest_path(manifest_path)
        self._git_bin = git_bin or Path("git")

    async def capture(
        self,
        *,
        working_directory: Path,
        conversation_id: str,
        session_window_start: datetime,
        session_window_end: datetime,
    ) -> tuple[dict[str, list[CommitEntry]], list[str]]:
        repos = self._load_repos(working_directory)
        if not repos:
            return {}, []

        captured: dict[str, list[CommitEntry]] = {}
        failures: list[str] = []

        async def _run_one(target_name: str, target_path: Path) -> None:
            for attempt in range(3):  # initial + 2 retries
                try:
                    entries = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._git_log,
                            target_path,
                            session_window_start,
                            session_window_end,
                        ),
                        timeout=_PER_REPO_TIMEOUT_S,
                    )
                    captured[target_name] = entries
                    return
                except TimeoutError:
                    _log.warning(
                        "ambient_pull_git_log_timeout",
                        extra={"repo": target_name, "timeout_s": _PER_REPO_TIMEOUT_S},
                    )
                    failures.append(target_name)
                    return
                except subprocess.CalledProcessError as exc:
                    if exc.returncode in _TRANSIENT_GIT_EXIT_CODES and attempt < 2:
                        await asyncio.sleep(_GIT_RETRY_BACKOFF_S[attempt])
                        continue
                    _log.warning(
                        "ambient_pull_failed",
                        extra={"repo": target_name, "error": str(exc)},
                    )
                    failures.append(target_name)
                    return
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "ambient_pull_failed",
                        extra={"repo": target_name, "error": str(exc)},
                    )
                    failures.append(target_name)
                    return

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *starmap(_run_one, repos),
                    return_exceptions=True,
                ),
                timeout=_BATCH_TIMEOUT_S,
            )
        except TimeoutError:
            _log.warning(
                "ambient_pull_batch_timeout", extra={"timeout_s": _BATCH_TIMEOUT_S}
            )
        return captured, failures

    def _load_repos(self, working_directory: Path) -> list[tuple[str, Path]]:
        if not self._manifest_path.exists():
            _log.info(
                "ambient_pull_manifest_missing",
                extra={"path": str(self._manifest_path)},
            )
            return []
        try:
            data = yaml.safe_load(self._manifest_path.read_text())
        except yaml.YAMLError as exc:
            _log.warning("ambient_pull_manifest_malformed", extra={"error": str(exc)})
            return []
        if not isinstance(data, dict) or "ecosystem" not in data:
            return []
        local = working_directory.resolve()
        result: list[tuple[str, Path]] = []
        for name, entry in data["ecosystem"].items():
            if not isinstance(entry, dict) or "path" not in entry:
                continue
            path = Path(entry["path"]).resolve()
            if path == local:
                continue  # non-local filter
            result.append((name, path))
        return result

    def _git_log(
        self,
        repo_path: Path,
        start: datetime,
        end: datetime,
    ) -> list[CommitEntry]:
        argv = [
            str(self._git_bin),
            "log",
            f"--since={int(start.timestamp())}",
            f"--until={int(end.timestamp())}",
            f"-n{_MAX_COMMITS}",
            "--format=%H%x09%s%x09%an%x09%ae%x09%aI",
        ]
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=_PER_REPO_TIMEOUT_S + 1,
            cwd=str(repo_path),
        )
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, argv, proc.stderr)
        result: list[CommitEntry] = []
        for line in proc.stdout.splitlines():
            parts = line.split("\t", 5)
            if len(parts) < 5:
                continue
            sha, subject, author_name, author_email, ts = parts[:5]
            safe_name = _sanitize_field(author_name)
            safe_email = _sanitize_field(author_email)
            safe_subject = _sanitize_field(subject)
            safe_sha = _sanitize_field(sha)
            result.append(
                CommitEntry(
                    kind="commit",
                    sha=safe_sha,
                    subject=safe_subject or None,
                    author=f"{safe_name} <{safe_email}>",
                    timestamp=datetime.fromisoformat(ts),
                    provenance="ambient",
                )
            )
        return result
