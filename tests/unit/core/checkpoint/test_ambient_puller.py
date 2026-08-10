from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from session_buddy.core.checkpoint.ambient_puller import AmbientPuller


def _git_init(path: Path) -> None:
    subprocess.check_call(["git", "init", "--quiet", str(path)])
    subprocess.check_call(["git", "-C", str(path), "config", "user.email", "test@example.com"])
    subprocess.check_call(["git", "-C", str(path), "config", "user.name", "Test"])


def _commit(path: Path, msg: str) -> str:
    subprocess.check_call(["git", "-C", str(path), "commit", "--allow-empty", "-m", msg])
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"]
    ).decode().strip()


def _write_manifest(tmp_path: Path, repos: list[dict[str, str]]) -> Path:
    p = tmp_path / "ecosystem.yaml"
    p.write_text(yaml.safe_dump({
        "ecosystem": {
            r["name"]: {"path": r["path"], "role": r["role"]}
            for r in repos
        }
    }))
    return p


async def _capture(puller, **kwargs):
    return await puller.capture(
        working_directory=kwargs["working_directory"],
        conversation_id=kwargs["conversation_id"],
        session_window_start=kwargs["session_window_start"],
        session_window_end=kwargs["session_window_end"],
    )


@pytest.mark.asyncio
async def test_per_repo_grouping_from_start(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sib_a = tmp_path / "a"; sib_a.mkdir(); _git_init(sib_a)
    sib_b = tmp_path / "b"; sib_b.mkdir(); _git_init(sib_b)
    sha_a = _commit(sib_a, "feat(a): 1")
    sha_b = _commit(sib_b, "feat(b): 2")
    manifest = _write_manifest(tmp_path, [
        {"name": "a", "path": str(sib_a), "role": "x"},
        {"name": "b", "path": str(sib_b), "role": "x"},
    ])
    puller = AmbientPuller(manifest_path=manifest)
    start = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    end = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    grouped, failures = await _capture(
        puller,
        working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=start,
        session_window_end=end,
    )
    assert failures == []
    # Per-repo: each sibling has its own bucket
    assert "a" in grouped
    assert "b" in grouped
    assert any(e.sha == sha_a for e in grouped["a"])
    assert any(e.sha == sha_b for e in grouped["b"])
    # NO "<ambient>" placeholder key
    assert "<ambient>" not in grouped


@pytest.mark.asyncio
async def test_non_local_filter_skips_working_directory(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    _git_init(workdir)
    sha_local = _commit(workdir, "feat(work): local")
    manifest = _write_manifest(tmp_path, [{"name": "work", "path": str(workdir), "role": "x"}])
    puller = AmbientPuller(manifest_path=manifest)
    grouped, _ = await _capture(
        puller, working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        session_window_end=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    assert all(e.sha != sha_local for grouped_entries in grouped.values() for e in grouped_entries)


@pytest.mark.asyncio
async def test_missing_manifest_no_raise(tmp_path: Path) -> None:
    puller = AmbientPuller(manifest_path=tmp_path / "missing.yaml")
    grouped, failures = await _capture(
        puller, working_directory=tmp_path / "work",
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc),
        session_window_end=datetime.now(tz=timezone.utc),
    )
    assert grouped == {}
    assert failures == []


@pytest.mark.asyncio
async def test_per_repo_timeout_kills_hung_git(tmp_path: Path) -> None:
    """Spec §Error handling resilience C2: 10s per-repo timeout."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    sib = tmp_path / "hung_sibling"
    sib.mkdir()
    # Inject a git wrapper that sleeps for 60s
    sleep_bin = tmp_path / "git-sleep"
    sleep_bin.mkdir()
    (sleep_bin / "git").write_text("#!/bin/sh\nsleep 60\n")
    (sleep_bin / "git").chmod(0o755)
    manifest_path = tmp_path / "ecosystem.yaml"
    manifest_path.write_text(
        f"ecosystem:\n  hung_sibling:\n    path: {sib}\n    role: x\n"
    )
    puller = AmbientPuller(manifest_path=manifest_path, git_bin=tmp_path / "git-sleep" / "git")
    start = datetime.now(tz=timezone.utc)
    end = start + timedelta(hours=1)
    # Should return within ~15s, not 60s
    grouped, failures = await asyncio.wait_for(
        _capture(puller, working_directory=workdir, conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
                  session_window_start=start, session_window_end=end),
        timeout=15,
    )
    assert "hung_sibling" in failures


@pytest.mark.asyncio
async def test_git_log_retry_on_transient_failure(tmp_path: Path) -> None:
    """Spec §Error handling resilience I1: 2x retry on lock/EAGAIN transient."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    sib = tmp_path / "sibling"; sib.mkdir()
    _git_init(sib)
    sha = _commit(sib, "feat(sibling): hi")
    # Wrapper that fails twice then succeeds
    fail_bin = tmp_path / "git-flaky"
    fail_bin.mkdir()
    state_file = tmp_path / ".flaky_state"
    state_file.write_text("0")
    (fail_bin / "git").write_text(
        f"#!/bin/sh\nn=$(cat {state_file})\n"
        f"if [ $n -lt 2 ]; then echo $((n+1)) > {state_file}; exit 128; fi\n"
        f"exec /usr/bin/git \"$@\"\n"
    )
    (fail_bin / "git").chmod(0o755)
    manifest = _write_manifest(tmp_path, [{"name": "sibling", "path": str(sib), "role": "x"}])
    puller = AmbientPuller(manifest_path=manifest, git_bin=fail_bin / "git")
    grouped, failures = await _capture(
        puller, working_directory=workdir,
        conversation_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        session_window_start=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        session_window_end=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    assert failures == []
    assert any(e.sha == sha for e in grouped.get("sibling", []))


def test_sanitizes_control_chars_in_git_porcelain(tmp_path: Path) -> None:
    """A malicious sibling repo could stage commits with control characters in
    the author name, email, or subject. We must strip them at the parse
    boundary so they cannot reach downstream log records or markdown renderers.
    Also neutralize < and > in the name to prevent forged-boundary attacks on
    the `name <email>` author field.
    """
    puller = AmbientPuller(manifest_path=tmp_path / "missing.yaml")
    # Use \x1b (ESC) and \x07 (BEL) — both are in the C0 range our regex
    # strips, but neither is in str.splitlines()'s split chars, so the line
    # survives parsing and exercises the sanitization path.
    # Author name has < and > to forge the `name <email>` boundary.
    malicious_stdout = (
        "abc1234\t"
        "subject\x1b[31m_ansi\x1b[0m_with\x07_bel\t"
        "attacker<fake>\t"
        "les@example.com\t"
        "2026-08-06T00:00:00+00:00\n"
    )
    fake_proc = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=malicious_stdout, stderr=""
    )
    start = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    end = datetime.now(tz=timezone.utc)
    with patch(
        "session_buddy.core.checkpoint.ambient_puller.subprocess.run",
        return_value=fake_proc,
    ):
        entries = puller._git_log(tmp_path / "sibling", start, end)
    assert len(entries) == 1
    entry = entries[0]
    # Control chars stripped from subject (ANSI ESC and BEL are gone).
    assert "\x1b" not in (entry.subject or "")
    assert "\x07" not in (entry.subject or "")
    # No control chars in author.
    assert "\x1b" not in entry.author
    assert "\x07" not in entry.author
    # Angle brackets in name neutralized: < and > become ( and ).
    # "attacker<fake>" -> "attacker(fake)"
    name_part = entry.author.split(" <", 1)[0]
    assert "<" not in name_part
    assert ">" not in name_part
    assert name_part == "attacker(fake)"
    # Email is preserved (no < or > to neutralize, no control chars).
    assert entry.author.endswith(" <les@example.com>")
