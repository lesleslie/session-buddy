"""Atomic, owner-only file writes.

One audited implementation of the "write to a temp file, then rename over
the destination" pattern. The naive fixed-name version of this pattern
has three distinct failure modes, all of which are closed by using a
uniquely named temp file:

1. **Stale temp reuse.** With a fixed temp name, a file left behind by
   an earlier write is reused rather than recreated. The new content
   therefore lands in a file whose permissions were decided by that
   earlier -- possibly crashed -- write, and the mode argument passed to
   ``os.open`` is not applied because the file was not *created*.
2. **Symlink following.** Opening a fixed temp path with ``O_CREAT |
   O_TRUNC`` follows symlinks. Anything able to write into the
   destination directory can plant a symlink there and redirect the
   write -- and its truncation -- at an arbitrary file.
3. **Concurrent-writer collision.** Two writers sharing one temp name
   race: whichever renames first moves the file out from under the
   other, which then fails with ``FileNotFoundError`` -- and can
   publish the other writer's bytes.

``tempfile.mkstemp`` closes all three: it creates a fresh file with a
unique name, at 0600, and refuses to follow an existing path.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["atomic_write_bytes", "atomic_write_text"]


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    """Write ``data`` to ``path`` atomically, with owner-only permissions.

    The content is written to a uniquely named temp file in the
    destination directory, flushed and fsynced, then renamed over
    ``path`` with ``os.replace``. That rename is atomic on POSIX, so a
    concurrent reader sees either the previous file or the complete new
    one -- never a half-written file.

    The published file's mode is set with ``fchmod`` on the open
    descriptor rather than ``chmod`` on the path, so the file is never
    observable at a wider mode than requested, even momentarily. This
    matters for secrets: a file created by ``Path.write_bytes`` takes
    the ambient umask (0644 under the default 022) and only narrows
    when a later ``chmod`` runs, so its contents are readable by other
    local users in between.

    Args:
        path: Destination path. Its parent directory must already exist.
        data: The bytes to write.
        mode: Permission bits for the published file.

    Raises:
        OSError: If the temp file cannot be created, written, or renamed.
    """
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    """Write ``text`` to ``path`` atomically, with owner-only permissions.

    See :func:`atomic_write_bytes` for the guarantees this provides.
    """
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)
