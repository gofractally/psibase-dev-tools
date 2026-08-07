import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import PACKAGE_ROOT, activated_subprocess_env, state_dir
from .schemas import load_definition


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "error"}
DEFAULT_POLL_AFTER_SECONDS = 5
DEFAULT_WORKSPACE_HASH = "_default"
DEFAULT_GC_AGE_SECONDS = 24 * 60 * 60


def _now_ms() -> int:
    return int(time.time() * 1000)


def _job_id() -> str:
    return uuid.uuid4().hex[:16]


def workspace_hash(workspace_root: str | None) -> str:
    """Stable short hash used to namespace job state by workspace.

    Empty / None workspace_root falls back to a sentinel bucket so legacy
    callers that don't set workspace_root still work. We use SHA-256 truncated
    to 12 hex chars (~48 bits): comfortably collision-free for the handful of
    worktrees a single user keeps around.
    """
    if not workspace_root:
        return DEFAULT_WORKSPACE_HASH
    return hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest()[:12]


def jobs_root() -> Path:
    root = state_dir() / "jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


# Cache of job_id → job dir, populated on first lookup. Cheap to invalidate
# (on FileNotFoundError) and the cache survives MCP server lifetime, which
# is one Cursor session, so growth is bounded.
_job_dir_cache: dict[str, Path] = {}


def job_dir_for_workspace(job_id: str, workspace_root: str | None) -> Path:
    """Compute the job dir for a known workspace.

    Used by ``start_tool_job`` (we know the workspace at that point) and by
    tests that want a deterministic path. Lookups by job_id alone go through
    ``find_job_dir`` instead.
    """
    return jobs_root() / workspace_hash(workspace_root) / job_id


def find_job_dir(job_id: str) -> Path:
    """Locate the directory for ``job_id`` regardless of workspace.

    Status / log / cancel callers should not need to know the workspace hash
    to address a job. We scan ``state/jobs/<workspace_hash>/`` subdirs and
    cache the hit. Raises ``FileNotFoundError`` if no match is found.
    """
    cached = _job_dir_cache.get(job_id)
    if cached is not None and cached.is_dir():
        return cached
    root = jobs_root()
    for ws_dir in root.iterdir():
        if not ws_dir.is_dir():
            continue
        candidate = ws_dir / job_id
        if candidate.is_dir():
            _job_dir_cache[job_id] = candidate
            return candidate
    raise FileNotFoundError(f"Unknown job_id: {job_id}")


def job_dir(job_id: str) -> Path:
    """Locate an existing job dir; alias for find_job_dir."""
    return find_job_dir(job_id)


def state_path(job_id: str) -> Path:
    return find_job_dir(job_id) / "state.json"


def stdout_path(job_id: str) -> Path:
    return find_job_dir(job_id) / "stdout.log"


def stderr_path(job_id: str) -> Path:
    return find_job_dir(job_id) / "stderr.log"


def _stdout_path_no_create(job_id: str) -> Path:
    """stdout path that returns a non-existent placeholder rather than raising.

    Used by ``_public_state`` (which gets called for jobs we already loaded)
    so that an in-flight cache miss doesn't crash the call. The returned
    path may not exist; downstream callers handle that case.
    """
    try:
        return find_job_dir(job_id) / "stdout.log"
    except FileNotFoundError:
        return jobs_root() / DEFAULT_WORKSPACE_HASH / job_id / "stdout.log"


def _stderr_path_no_create(job_id: str) -> Path:
    try:
        return find_job_dir(job_id) / "stderr.log"
    except FileNotFoundError:
        return jobs_root() / DEFAULT_WORKSPACE_HASH / job_id / "stderr.log"


def write_state(job_id: str, state: dict[str, Any]) -> None:
    """Persist ``state.json`` atomically.

    For an existing job we use the cached/found directory. For a brand-new
    job (not yet in the cache) we derive the directory from the state's own
    recorded ``arguments.workspace_root``, which ``start_tool_job`` always
    populates via ``normalize_arguments``.
    """
    try:
        directory = find_job_dir(job_id)
    except FileNotFoundError:
        ws = (state.get("arguments") or {}).get("workspace_root")
        directory = job_dir_for_workspace(job_id, ws)
        directory.mkdir(parents=True, exist_ok=True)
        _job_dir_cache[job_id] = directory
    path = directory / "state.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def read_state(job_id: str) -> dict[str, Any]:
    # ``state_path`` raises FileNotFoundError if the job_id is unknown, which
    # is exactly the contract callers already rely on.
    path = state_path(job_id)
    if not path.is_file():
        raise FileNotFoundError(f"Unknown job_id: {job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _tail(path: Path, max_lines: int = 40) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]


def _line_slice(path: Path, start_line: int | None, end_line: int | None, max_bytes: int | None) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "Log file does not exist.", "lines": [], "total_lines": 0}
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = False
    if max_bytes is not None and max_bytes > 0 and len(text.encode("utf-8")) > max_bytes:
        encoded = text.encode("utf-8")[-max_bytes:]
        text = encoded.decode("utf-8", errors="replace")
        truncated = True
    lines = text.splitlines()
    total = len(lines)
    if start_line is None and end_line is None:
        start = max(1, total - 199)
        end = total
    else:
        start = 1 if start_line is None else max(1, start_line)
        end = total if end_line is None else min(total, end_line)
    selected = [] if end < start else lines[start - 1 : end]
    return {
        "ok": True,
        "path": str(path),
        "start_line": start,
        "end_line": end,
        "total_lines": total,
        "truncated": truncated,
        "lines": selected,
    }


def start_tool_job(tool_name: str, arguments: dict[str, Any], *, family: str) -> dict[str, Any]:
    job_id = _job_id()
    workspace_root = arguments.get("workspace_root")
    directory = job_dir_for_workspace(job_id, workspace_root)
    directory.mkdir(parents=True, exist_ok=True)
    _job_dir_cache[job_id] = directory

    stdout_file = directory / "stdout.log"
    stderr_file = directory / "stderr.log"
    stdout_file.touch()
    stderr_file.touch()

    definition = load_definition(tool_name)
    command = [
        sys.executable,
        "-m",
        "psibase_ai_tools.mcp.job_worker",
        "--job-id",
        job_id,
        "--tool",
        tool_name,
        "--payload-json",
        json.dumps(arguments),
    ]
    state = {
        "job_id": job_id,
        "family": family,
        "tool": tool_name,
        "version": definition.get("version"),
        "status": "starting",
        "command": command,
        "arguments": arguments,
        "started_at_ms": _now_ms(),
        "workspace_hash": workspace_hash(workspace_root),
        "stdout_path": str(stdout_file),
        "stderr_path": str(stderr_file),
        "result": None,
    }
    write_state(job_id, state)
    env = activated_subprocess_env()
    env["AI_DEV_MCP_JOB_ID"] = job_id
    proc = subprocess.Popen(command, cwd=str(PACKAGE_ROOT), env=env, start_new_session=True)
    state["status"] = "running"
    state["pid"] = proc.pid
    write_state(job_id, state)
    return _public_state(state)


def refresh_state(job_id: str) -> dict[str, Any]:
    state = read_state(job_id)
    if state.get("status") == "running":
        pid = state.get("pid")
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                state["status"] = "error"
                state["finished_at_ms"] = _now_ms()
                state["summary"] = "Job process exited without writing final state."
                write_state(job_id, state)
            except OSError:
                pass
    return _public_state(state)


def logs(job_id: str, *, stream: str = "stdout", start_line: int | None = None, end_line: int | None = None, max_bytes: int | None = None) -> dict[str, Any]:
    read_state(job_id)
    path = stderr_path(job_id) if stream == "stderr" else stdout_path(job_id)
    result = _line_slice(path, start_line, end_line, max_bytes)
    result["job_id"] = job_id
    result["stream"] = stream
    return result


def cancel(job_id: str, *, caller_workspace_root: str | None = None, force: bool = False) -> dict[str, Any]:
    """Cancel a running job, refusing if the caller's workspace differs.

    The check exists so that one subagent / Cursor window can't reach in
    and kill another's job by guessing a job_id. Both sides supply a
    workspace_root: the job records its own at start time, the caller's
    is resolved per-call by ``mcp.paths.detect_workspace_root``.

    Pass ``force=True`` to bypass the check (useful for cleanup scripts
    and for jobs whose recorded workspace_root is missing or stale).
    """
    state = read_state(job_id)
    if state.get("status") in TERMINAL_STATUSES:
        return _public_state(state)

    if not force:
        recorded = (state.get("arguments") or {}).get("workspace_root")
        if recorded and caller_workspace_root and recorded != caller_workspace_root:
            return {
                **_public_state(state),
                "ok": False,
                "error_code": "workspace_mismatch",
                "error_category": "ownership",
                "summary": (
                    f"Refusing to cancel job_id={job_id}: it was started by "
                    f"workspace_root={recorded}, but this call resolved "
                    f"workspace_root={caller_workspace_root}. Pass force=true "
                    "to override."
                ),
            }

    pid = state.get("pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.killpg(pid, signal.SIGTERM)
            time.sleep(1)
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            # Group already gone, or pid is no longer a valid process group
            # leader (e.g., the worker exited between status read and kill).
            pass
    state["status"] = "cancelled"
    state["finished_at_ms"] = _now_ms()
    state["summary"] = "Job was cancelled."
    write_state(job_id, state)
    return _public_state(state)


def gc_terminal_jobs(*, max_age_seconds: int = DEFAULT_GC_AGE_SECONDS, now_ms: int | None = None) -> dict[str, Any]:
    """Delete job dirs whose state is terminal and older than the cutoff.

    Called once at server startup. Returns a small audit dict listing what
    was removed, for self-tests and for surfacing in resources later. We
    consider both ``finished_at_ms`` and ``started_at_ms`` so a job that
    crashed before recording a finish time still GCs.

    Empty workspace-hash buckets are pruned afterwards so the on-disk layout
    stays tidy.
    """
    cutoff_ms = (now_ms if now_ms is not None else _now_ms()) - max_age_seconds * 1000
    removed: list[dict[str, Any]] = []
    kept_running: list[str] = []
    errors: list[dict[str, Any]] = []
    root = jobs_root()
    if not root.is_dir():
        return {"removed": removed, "kept_running": kept_running, "errors": errors}
    for ws_dir in list(root.iterdir()):
        if not ws_dir.is_dir():
            continue
        for job_d in list(ws_dir.iterdir()):
            if not job_d.is_dir():
                continue
            state_file = job_d / "state.json"
            if not state_file.is_file():
                continue
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append({"job_dir": str(job_d), "error": str(exc)})
                continue
            status = state.get("status")
            if status not in TERMINAL_STATUSES:
                kept_running.append(str(job_d))
                continue
            ended = state.get("finished_at_ms") or state.get("started_at_ms") or 0
            if ended >= cutoff_ms:
                continue
            try:
                import shutil
                shutil.rmtree(job_d)
                removed.append({"job_dir": str(job_d), "status": status, "ended_at_ms": ended})
                _job_dir_cache.pop(state.get("job_id"), None)
            except OSError as exc:
                errors.append({"job_dir": str(job_d), "error": str(exc)})
        try:
            if not any(ws_dir.iterdir()):
                ws_dir.rmdir()
        except OSError:
            pass
    return {"removed": removed, "kept_running": kept_running, "errors": errors}


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    job_id = str(state["job_id"])
    result = state.get("result")
    status = state.get("status")
    arguments = state.get("arguments") or {}
    out_path = _stdout_path_no_create(job_id)
    err_path = _stderr_path_no_create(job_id)
    public = {
        "job_id": job_id,
        "family": state.get("family"),
        "tool": state.get("tool"),
        "version": state.get("version"),
        "status": status,
        "poll_after_seconds": DEFAULT_POLL_AFTER_SECONDS if status not in TERMINAL_STATUSES else None,
        "started_at_ms": state.get("started_at_ms"),
        "finished_at_ms": state.get("finished_at_ms"),
        "pid": state.get("pid"),
        "workspace_hash": state.get("workspace_hash"),
        "workspace_root": arguments.get("workspace_root"),
        "db_dir": arguments.get("db_dir"),
        "build_dir": arguments.get("build_dir"),
        "listen_port": arguments.get("listen_port"),
        "stdout_path": str(out_path),
        "stderr_path": str(err_path),
        "tail": _tail(out_path),
        "stderr_tail": _tail(err_path, 20),
        "result": result,
    }
    if isinstance(result, dict):
        public["summary"] = result.get("summary")
        public["exit_code"] = result.get("exit_code")
        public["ok"] = result.get("ok")
        public["error_code"] = result.get("error_code")
        public["error_category"] = result.get("error_category")
        # Result-side overrides win when the worker resolved a different
        # value than the input argument (e.g. db_dir defaulted from
        # workspace_root, build_dir resolved to an absolute path).
        for key in ("workspace_root", "db_dir", "build_dir"):
            if result.get(key):
                public[key] = result.get(key)
    elif state.get("summary"):
        public["summary"] = state.get("summary")
    return public
