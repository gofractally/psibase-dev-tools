"""Advisory PID-based directory locks for ai-tools jobs.

Used by chain (`db_dir`) and build (`build_dir`) tools to fail-fast when two
parallel agents would otherwise fight over the same directory. Locks are
exclusive, file-based, and live next to the protected directory so a wipe of
that directory (e.g. ``launch_chain``'s ``rmtree(db_dir)``) does not destroy
the lock.

Stale locks (PID no longer alive) are reclaimed automatically. Locks are
released only by the owning PID, so a ``cancel_*`` issued by the parent MCP
server will not strip a lock that a still-running grandchild created.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def lock_path_for(target_dir: Path, *, suffix: str) -> Path:
    """Return the sibling lock-file path for ``target_dir``.

    The lock lives at ``<parent>/<name><suffix>`` (sibling, not child) so that
    callers which wipe ``target_dir`` (e.g. ``rmtree(db_dir)`` in
    ``launch_chain``) do not delete their own lock file mid-session.
    """
    return target_dir.parent / (target_dir.name + suffix)


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_lock(lock_path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def acquire_dir_lock(
    target_dir: Path,
    *,
    suffix: str,
    tool: str,
    workspace_root: Path,
) -> tuple[Path | None, dict[str, Any] | None]:
    """Try to take an exclusive lock on ``target_dir``.

    Returns ``(lock_path, None)`` on success and ``(None, holder_info)`` if
    another live process holds it. A stale lock (holder PID no longer alive)
    is reclaimed transparently.

    The parent of ``target_dir`` is created if missing; ``target_dir`` itself
    is **not** created here, since chain tools intentionally wipe and recreate
    it after taking the lock.
    """
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    lock_path = lock_path_for(target_dir, suffix=suffix)
    payload = {
        "pid": os.getpid(),
        "job_id": os.environ.get("AI_DEV_MCP_JOB_ID"),
        "tool": tool,
        "workspace_root": str(workspace_root),
        "target_dir": str(target_dir),
        "started_at_ms": int(time.time() * 1000),
    }
    serialized = json.dumps(payload, sort_keys=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        existing = _read_lock(lock_path) or {}
        holder_pid = existing.get("pid")
        if isinstance(holder_pid, int) and _process_alive(holder_pid):
            return None, existing
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return None, _read_lock(lock_path) or {}
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(serialized)
    return lock_path, None


def release_dir_lock(lock_path: Path | None) -> None:
    """Release a lock previously acquired by this PID.

    Locks created by other PIDs are never removed here, so a stray
    ``release`` from the parent server cannot strip a lock owned by a
    still-running worker.
    """
    if lock_path is None:
        return
    try:
        existing = _read_lock(lock_path) or {}
        if existing.get("pid") != os.getpid():
            return
        lock_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass
