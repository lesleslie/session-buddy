from __future__ import annotations

import os
import gzip
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from session_buddy.backends.base import SessionState
from session_buddy.backends.local_backend import LocalFileStorage


def _make_state(
    session_id: str = "session-1",
    user_id: str = "user-1",
    project_id: str = "project-1",
) -> SessionState:
    now = datetime.now().isoformat()
    return SessionState(
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        created_at=now,
        last_activity=now,
    )


def test_initialization_warns_and_creates_storage_dir(tmp_path: Path) -> None:
    storage_dir = tmp_path / "sessions"

    with pytest.warns(DeprecationWarning, match="LocalFileStorage is deprecated"):
        storage = LocalFileStorage({"storage_dir": storage_dir})

    assert storage.storage_dir == storage_dir
    assert storage.storage_dir.exists()
    assert storage.logger.name == "serverless.localfilestorage"


@pytest.mark.asyncio
async def test_store_retrieve_delete_round_trip(tmp_path: Path) -> None:
    storage = LocalFileStorage({"storage_dir": tmp_path / "sessions"})
    state = _make_state()

    assert await storage.store_session(state) is True

    session_file = storage._get_session_file(state.session_id)
    assert session_file.exists()

    with session_file.open("rb") as handle:
        payload = json.loads(gzip.decompress(handle.read()).decode("utf-8"))
    assert payload["session_id"] == state.session_id
    assert payload["user_id"] == state.user_id

    restored = await storage.retrieve_session(state.session_id)
    assert restored == state

    assert await storage.delete_session(state.session_id) is True
    assert await storage.retrieve_session(state.session_id) is None
    assert await storage.delete_session(state.session_id) is False


@pytest.mark.asyncio
async def test_list_sessions_applies_filters(tmp_path: Path) -> None:
    storage = LocalFileStorage({"storage_dir": tmp_path / "sessions"})

    session_a = _make_state("session-a", "user-1", "project-1")
    session_b = _make_state("session-b", "user-2", "project-1")
    session_c = _make_state("session-c", "user-1", "project-2")

    assert await storage.store_session(session_a) is True
    assert await storage.store_session(session_b) is True
    assert await storage.store_session(session_c) is True

    assert set(await storage.list_sessions()) == {
        session_a.session_id,
        session_b.session_id,
        session_c.session_id,
    }
    assert set(await storage.list_sessions(user_id="user-1")) == {
        session_a.session_id,
        session_c.session_id,
    }
    assert set(await storage.list_sessions(project_id="project-1")) == {
        session_a.session_id,
        session_b.session_id,
    }
    assert set(
        await storage.list_sessions(user_id="user-1", project_id="project-2"),
    ) == {session_c.session_id}


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_removes_old_files(tmp_path: Path) -> None:
    storage = LocalFileStorage({"storage_dir": tmp_path / "sessions"})

    fresh_state = _make_state("fresh-session")
    stale_state = _make_state("stale-session")

    assert await storage.store_session(fresh_state) is True
    assert await storage.store_session(stale_state) is True

    stale_file = storage._get_session_file(stale_state.session_id)
    old_timestamp = (datetime.now() - timedelta(days=8)).timestamp()
    stale_file.touch()
    stale_file.chmod(0o600)
    os.utime(stale_file, (old_timestamp, old_timestamp))

    cleaned = await storage.cleanup_expired_sessions()
    assert cleaned == 1
    assert stale_file.exists() is False
    assert storage._get_session_file(fresh_state.session_id).exists() is True


@pytest.mark.asyncio
async def test_is_available_handles_directory_and_file(tmp_path: Path) -> None:
    storage = LocalFileStorage({"storage_dir": tmp_path / "sessions"})
    assert await storage.is_available() is True

    file_path = tmp_path / "not_a_directory"
    file_path.write_text("content")
    storage.storage_dir = file_path

    assert await storage.is_available() is False


def test_helpers_extract_and_match_filters(tmp_path: Path) -> None:
    storage = LocalFileStorage({"storage_dir": tmp_path / "sessions"})
    state = _make_state("session-x", "user-x", "project-x")

    assert storage._extract_session_id(Path("/tmp/session-x.json.gz")) == "session-x"
    assert storage._matches_filters(state, "user-x", None) is True
    assert storage._matches_filters(state, None, "project-x") is True
    assert storage._matches_filters(state, "different-user", None) is False
    assert storage._matches_filters(state, None, "different-project") is False
