"""MCP async tool starters.

Maps each async MCP tool name to its ``psibase_ai_tools.lib`` implementation
module and the argument fields that must resolve inside the workspace.
"""

from __future__ import annotations

from typing import Any

from . import jobs
from .paths import detect_workspace_root, normalize_arguments


BUILD_STARTERS = {
    "start_full_build": ("run_full_build", ("build_dir",)),
    "start_package_build": ("build_package", ("build_dir",)),
    "start_rust_service_build": ("build_rust_service", ("target_dir", "psibase_binary_path")),
}

TEST_STARTERS = {
    "start_service_tests": ("run_service_tests", ("service_manifest_path", "target_dir", "psitest_path")),
}

CHAIN_STARTERS = {
    "launch_chain": ("launch_chain", ("workspace_root", "db_dir", "psinode_path", "psibase_path")),
    "resume_chain": ("resume_chain", ("workspace_root", "db_dir", "psinode_path", "psibase_path")),
}


def start_build(mcp_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    if mcp_name not in BUILD_STARTERS:
        raise ValueError(f"unknown build starter: {mcp_name}")
    tool_name, path_fields = BUILD_STARTERS[mcp_name]
    normalized = normalize_arguments(arguments, path_fields=path_fields)
    return jobs.start_tool_job(tool_name, normalized, family="build")


def start_tests(arguments: dict[str, Any] | None) -> dict[str, Any]:
    tool_name, path_fields = TEST_STARTERS["start_service_tests"]
    normalized = normalize_arguments(arguments, path_fields=path_fields)
    return jobs.start_tool_job(tool_name, normalized, family="test")


def start_chain(mcp_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    if mcp_name not in CHAIN_STARTERS:
        raise ValueError(f"unknown chain starter: {mcp_name}")
    tool_name, path_fields = CHAIN_STARTERS[mcp_name]
    normalized = normalize_arguments(arguments, path_fields=path_fields)
    return jobs.start_tool_job(tool_name, normalized, family="chain")


def status(job_id: str) -> dict[str, Any]:
    return jobs.refresh_state(job_id)


def logs(arguments: dict[str, Any] | None, *, default_stream: str = "stdout") -> dict[str, Any]:
    args = dict(arguments or {})
    job_id = str(args["job_id"])
    stream = str(args.get("stream") or default_stream)
    return jobs.logs(
        job_id,
        stream=stream,
        start_line=args.get("start_line"),
        end_line=args.get("end_line"),
        max_bytes=args.get("max_bytes"),
    )


def cancel(arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = dict(arguments or {})
    job_id = str(args["job_id"])
    force = bool(args.get("force") or False)
    caller_ws = str(detect_workspace_root(args))
    return jobs.cancel(job_id, caller_workspace_root=caller_ws, force=force)
