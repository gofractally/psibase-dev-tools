"""Run psinode for launch_chain / resume_chain MCP jobs (async worker)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

from . import chain_common, locks, psibase_binaries

TOOL_LAUNCH = "launch_chain"
TOOL_RESUME = "resume_chain"

LOCK_SUFFIX = ".psinode.lock"


def _validate_common(data: dict[str, Any], *, allow_skip_boot: bool) -> tuple[bool, str | None]:
    allowed = {
        "workspace_root",
        "db_dir",
        "admin_ip",
        "producer",
        "listen_port",
        "api_url",
        "http_host",
        "psinode_path",
        "psibase_path",
    }
    if allow_skip_boot:
        allowed |= {"skip_boot"}
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        return False, f"Unknown input field(s): {', '.join(unknown)}"
    if "workspace_root" in data and data["workspace_root"] is not None and not isinstance(data["workspace_root"], str):
        return False, "workspace_root must be a string when provided."
    if "db_dir" in data and data["db_dir"] is not None and not isinstance(data["db_dir"], str):
        return False, "db_dir must be a string when provided."
    for key in ("admin_ip", "producer", "api_url", "http_host", "psinode_path", "psibase_path"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            return False, f"{key} must be a string when provided."
    if "listen_port" in data and data["listen_port"] is not None:
        if not isinstance(data["listen_port"], int) or int(data["listen_port"]) < 1 or int(data["listen_port"]) > 65535:
            return False, "listen_port must be an integer 1–65535."
    if allow_skip_boot and "skip_boot" in data and data["skip_boot"] is not None and not isinstance(data["skip_boot"], bool):
        return False, "skip_boot must be a boolean."
    return True, None


def _resolve_db_dir(payload: dict[str, Any], workspace_root: Path) -> Path:
    explicit = payload.get("db_dir")
    if isinstance(explicit, str) and explicit.strip():
        path = Path(explicit).expanduser()
        return path if path.is_absolute() else (workspace_root / path)
    return workspace_root / "db"


def _port_in_use(port: int, *, host: str = "127.0.0.1") -> tuple[bool, str | None]:
    """Return (busy, error_detail) for the requested TCP port.

    There's a small race between this probe and ``Popen``: another process
    can bind in between. Treat the probe as a fast-fail signal, not a
    guarantee. If something does win the race after the probe, psinode will
    still surface the bind error in its own logs.

    We probe loopback only because that's where psinode listens by default.
    A non-loopback bind from another interface won't be caught here, which
    matches the same gap psinode itself has.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, int(port)))
        except OSError as exc:
            return True, f"{exc.__class__.__name__}: {exc}"
        return False, None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _acquire_db_lock(db_dir: Path, *, tool: str, workspace_root: Path):
    return locks.acquire_dir_lock(db_dir, suffix=LOCK_SUFFIX, tool=tool, workspace_root=workspace_root)


def _release_db_lock(lock_path: Path | None) -> None:
    locks.release_dir_lock(lock_path)


def _workspace_root(data: dict[str, Any]) -> Path:
    from psibase_ai_tools.lib.workspace_root import detect_workspace_root

    return detect_workspace_root(data)


def _job_log_paths() -> tuple[Path, Path]:
    job_id = os.environ.get("AI_DEV_MCP_JOB_ID")
    if not job_id:
        raise RuntimeError("AI_DEV_MCP_JOB_ID is not set; chain jobs must be started via the MCP job runner.")
    from psibase_ai_tools.mcp.jobs import stderr_path, stdout_path

    return stdout_path(job_id), stderr_path(job_id)


def run_psinode_session(payload: dict[str, Any], *, wipe_db: bool) -> tuple[int, dict[str, Any]]:
    tool = TOOL_LAUNCH if wipe_db else TOOL_RESUME
    ok_meta, err = _validate_common(payload, allow_skip_boot=wipe_db)
    if not ok_meta:
        return 1, {
            "ok": False,
            "tool": tool,
            "status": "error",
            "summary": err or "Invalid input.",
            "error_code": "invalid_input",
            "error_category": "input",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    try:
        workspace_root = _workspace_root(payload)
    except Exception as exc:  # noqa: BLE001
        return 1, {
            "ok": False,
            "tool": tool,
            "status": "error",
            "summary": str(exc),
            "error_code": "invalid_workspace",
            "error_category": "input",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    admin_ip = str(payload.get("admin_ip") or "127.0.0.1").strip() or "127.0.0.1"
    producer = str(payload.get("producer") or "myprod").strip() or "myprod"
    listen_port = int(payload.get("listen_port") or 8080)
    http_host = (
        str(payload.get("http_host") or chain_common.DEFAULT_API_HTTP_HOST).strip()
        or chain_common.DEFAULT_API_HTTP_HOST
    )
    api_url = payload.get("api_url")
    if isinstance(api_url, str) and api_url.strip():
        api_base = api_url.strip()
        if not api_base.endswith("/"):
            api_base = api_base + "/"
    else:
        api_base = chain_common.default_api_url(http_host=http_host, port=listen_port)

    skip_boot = bool(payload.get("skip_boot")) if wipe_db else False

    db_dir = _resolve_db_dir(payload, workspace_root)
    psinode_exe = payload.get("psinode_path")
    psibase_exe = payload.get("psibase_path")

    try:
        psinode_path = psibase_binaries.resolve_psinode(workspace_root, psinode_exe if isinstance(psinode_exe, str) else None)
        psibase_path = psibase_binaries.resolve_psibase(workspace_root, psibase_exe if isinstance(psibase_exe, str) else None)
    except FileNotFoundError as exc:
        return 1, {
            "ok": False,
            "tool": tool,
            "status": "error",
            "summary": str(exc),
            "error_code": "environment_missing",
            "error_category": "environment",
            "workspace_root": str(workspace_root),
            "db_dir": str(db_dir),
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    lock_path, holder = _acquire_db_lock(db_dir, tool=tool, workspace_root=workspace_root)
    if lock_path is None:
        return 1, {
            "ok": False,
            "tool": tool,
            "status": "error",
            "summary": (
                f"Another psinode job is already using db_dir={db_dir} "
                f"(holder pid={holder.get('pid') if holder else 'unknown'}, "
                f"job_id={holder.get('job_id') if holder else 'unknown'}, "
                f"workspace_root={holder.get('workspace_root') if holder else 'unknown'}). "
                "Pass a distinct db_dir, or cancel the holder job first."
            ),
            "error_code": "resource_busy",
            "error_category": "concurrency",
            "workspace_root": str(workspace_root),
            "db_dir": str(db_dir),
            "lock_holder": holder,
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    try:
        busy, busy_detail = _port_in_use(listen_port)
        if busy:
            return 1, {
                "ok": False,
                "tool": tool,
                "status": "error",
                "summary": (
                    f"listen_port={listen_port} is already in use ({busy_detail}). "
                    "Pass a distinct listen_port (and matching api_url / http_host) "
                    "or stop the process holding the port."
                ),
                "error_code": "port_in_use",
                "error_category": "concurrency",
                "workspace_root": str(workspace_root),
                "db_dir": str(db_dir),
                "listen_port": listen_port,
                "stdout": "",
                "stderr": "",
                "exit_code": None,
            }

        if wipe_db:
            try:
                if db_dir.exists():
                    shutil.rmtree(db_dir)
            except OSError as exc:
                return 1, {
                    "ok": False,
                    "tool": tool,
                    "status": "error",
                    "summary": f"Failed to remove old database directory: {exc}",
                    "error_code": "db_wipe_failed",
                    "error_category": "filesystem",
                    "workspace_root": str(workspace_root),
                    "db_dir": str(db_dir),
                    "stdout": "",
                    "stderr": "",
                    "exit_code": None,
                }

        db_dir.mkdir(parents=True, exist_ok=True)

        out_log, err_log = _job_log_paths()
        out_f = open(out_log, "a", encoding="utf-8", buffering=1)
        err_f = open(err_log, "a", encoding="utf-8", buffering=1)

        env = dict(os.environ)
        env["PSIBASE_ADMIN_IP"] = admin_ip

        psinode_cmd = [psinode_path, str(db_dir), "-p", producer, "-l", str(listen_port)]
        header = (
            f"[{tool}] Starting psinode: {' '.join(psinode_cmd)}\n"
            f"workspace_root={workspace_root}\n"
            f"db_dir={db_dir}\n"
            f"db_lock={lock_path}\n"
            f"api_url (boot target)={api_base}\n"
        )
        out_f.write(header)
        out_f.flush()

        proc = subprocess.Popen(
            psinode_cmd,
            cwd=str(workspace_root),
            env=env,
            stdout=out_f,
            stderr=err_f,
        )

        ready_ok, ready_body, ready_status = chain_common.wait_for_admin_status(
            api_base,
            total_timeout_sec=60.0,
            request_timeout_sec=2.0,
            poll_interval_sec=0.25,
        )
        if not ready_ok:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            out_f.write(f"\n[{tool}] Node did not become ready in time (last error: {ready_body!r}, status={ready_status})\n")
            out_f.flush()
            out_f.close()
            err_f.close()
            tail_out = chain_common.read_log_tail(out_log)
            tail_err = chain_common.read_log_tail(err_log)
            return 1, {
                "ok": False,
                "tool": tool,
                "status": "failed",
                "summary": "psinode did not become ready (HTTP /native/admin/status without startup) within 60s.",
                "error_code": "node_not_ready",
                "error_category": "chain_runtime",
                "command": psinode_cmd,
                "workspace_root": str(workspace_root),
                "db_dir": str(db_dir),
                "api_url": api_base,
                "stdout": tail_out,
                "stderr": tail_err,
                "exit_code": None,
                "failure_excerpt": ready_body,
            }

        out_f.write(f"\n[{tool}] Node is ready (GET /native/admin/status is OK and startup finished).\n")
        out_f.flush()

        if wipe_db and not skip_boot:
            boot_cmd = [psibase_path, "boot", "-a", api_base, "-p", producer]
            out_f.write(f"[{tool}] Running: {' '.join(boot_cmd)}\n")
            out_f.flush()
            boot = subprocess.run(
                boot_cmd,
                cwd=str(workspace_root),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if boot.returncode != 0:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                if boot.stdout:
                    out_f.write(boot.stdout)
                if boot.stderr:
                    err_f.write(boot.stderr)
                out_f.flush()
                err_f.flush()
                out_f.close()
                err_f.close()
                return 1, {
                    "ok": False,
                    "tool": tool,
                    "status": "failed",
                    "summary": "psibase boot failed.",
                    "error_code": "boot_failed",
                    "error_category": "chain_runtime",
                    "command": psinode_cmd,
                    "boot_command": boot_cmd,
                    "workspace_root": str(workspace_root),
                    "db_dir": str(db_dir),
                    "api_url": api_base,
                    "stdout": chain_common.read_log_tail(out_log),
                    "stderr": chain_common.read_log_tail(err_log),
                    "exit_code": boot.returncode,
                }
            out_f.write(boot.stdout or "")
            err_f.write(boot.stderr or "")
            out_f.write(f"\n[{tool}] Boot completed successfully.\n")
            out_f.flush()
            err_f.flush()
        elif wipe_db and skip_boot:
            out_f.write(f"\n[{tool}] skip_boot=true: not running psibase boot.\n")
            out_f.flush()

        out_f.write(f"\n[{tool}] Running psinode (pid={proc.pid}); this job stays active until psinode exits.\n")
        out_f.flush()

        exit_code = proc.wait()
        out_f.write(f"\n[{tool}] psinode exited with code {exit_code}\n")
        out_f.flush()
        out_f.close()
        err_f.close()

        ok = exit_code == 0
        return (
            0 if ok else 1,
            {
                "ok": ok,
                "tool": tool,
                "status": "passed" if ok else "failed",
                "summary": "psinode exited normally." if ok else f"psinode exited with code {exit_code}.",
                "command": psinode_cmd,
                "workspace_root": str(workspace_root),
                "db_dir": str(db_dir),
                "api_url": api_base,
                "stdout": chain_common.read_log_tail(out_log),
                "stderr": chain_common.read_log_tail(err_log),
                "exit_code": exit_code,
                "error_code": None if ok else "psinode_exit_nonzero",
                "error_category": None if ok else "chain_runtime",
            },
        )
    finally:
        _release_db_lock(lock_path)
