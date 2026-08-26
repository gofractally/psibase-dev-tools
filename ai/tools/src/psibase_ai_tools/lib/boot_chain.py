"""MCP library: run psibase boot against an API URL (sync)."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict

from psibase_ai_tools.lib import chain_common, psibase_binaries
from psibase_ai_tools.lib.workspace_root import detect_workspace_root


def _validate(data: Dict[str, Any]) -> tuple[bool, str | None]:
    allowed = {
        "workspace_root",
        "api_url",
        "http_host",
        "listen_port",
        "producer",
        "admin_ip",
        "psibase_path",
    }
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        return False, f"Unknown input field(s): {', '.join(unknown)}"
    if "api_url" in data and data["api_url"] is not None and not isinstance(data["api_url"], str):
        return False, "api_url must be a string when provided."
    for key in ("workspace_root", "http_host", "producer", "admin_ip", "psibase_path"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            return False, f"{key} must be a string when provided."
    if "listen_port" in data and data["listen_port"] is not None:
        if not isinstance(data["listen_port"], int) or not (1 <= int(data["listen_port"]) <= 65535):
            return False, "listen_port must be an integer 1–65535."
    return True, None


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    ok_meta, err = _validate(payload)
    if not ok_meta:
        return {
            "ok": False,
            "tool": "boot_chain",
            "status": "error",
            "summary": err or "Invalid input.",
            "error_code": "invalid_input",
            "error_category": "input",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    workspace_root = detect_workspace_root(payload)
    producer = str(payload.get("producer") or "myprod").strip() or "myprod"
    listen_port = int(payload.get("listen_port") or 8080)
    http_host = (
        str(payload.get("http_host") or chain_common.DEFAULT_API_HTTP_HOST).strip()
        or chain_common.DEFAULT_API_HTTP_HOST
    )
    api = payload.get("api_url")
    if isinstance(api, str) and api.strip():
        api_base = api.strip()
        if not api_base.endswith("/"):
            api_base = api_base + "/"
    else:
        api_base = chain_common.default_api_url(http_host=http_host, port=listen_port)

    psibase_arg = payload.get("psibase_path")
    try:
        psibase_path = psibase_binaries.resolve_psibase(
            workspace_root,
            psibase_arg if isinstance(psibase_arg, str) else None,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "tool": "boot_chain",
            "status": "error",
            "summary": str(exc),
            "error_code": "environment_missing",
            "error_category": "environment",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    env = dict(os.environ)
    admin_ip = str(payload.get("admin_ip") or "").strip()
    if admin_ip:
        env["PSIBASE_ADMIN_IP"] = admin_ip

    cmd = [psibase_path, "boot", "-a", api_base, "-p", producer]
    proc = subprocess.run(
        cmd,
        cwd=str(workspace_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    ok = proc.returncode == 0
    return {
        "ok": ok,
        "tool": "boot_chain",
        "status": "passed" if ok else "failed",
        "summary": "psibase boot completed." if ok else "psibase boot failed.",
        "command": cmd,
        "workspace_root": str(workspace_root),
        "api_url": api_base,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "exit_code": proc.returncode,
        "error_code": None if ok else "boot_failed",
        "error_category": None if ok else "chain_runtime",
    }
