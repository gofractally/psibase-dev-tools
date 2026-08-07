"""Profile-aware MCP async tool starters."""

from __future__ import annotations

from typing import Any

from psibase_ai_tools.project_profile import ProjectProfile, packaged_default_profile

from . import jobs
from .paths import detect_workspace_root, normalize_arguments


def _active_profile() -> ProjectProfile:
    try:
        from psibase_ai_tools.project_profile import load_profile

        ws = detect_workspace_root({})
        return load_profile(ws)
    except Exception:
        return packaged_default_profile()


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


def build_starters_for_profile(profile: ProjectProfile | None = None) -> dict[str, tuple[str, tuple[str, ...]]]:
    profile = profile or _active_profile()
    starters = dict(BUILD_STARTERS)
    if "build" not in profile.mcp_tool_families_enabled:
        return {}
    return starters


def test_starters_for_profile(profile: ProjectProfile | None = None) -> dict[str, tuple[str, tuple[str, ...]]]:
    profile = profile or _active_profile()
    if "test" not in profile.mcp_tool_families_enabled:
        return {}
    return dict(TEST_STARTERS)


def chain_starters_for_profile(profile: ProjectProfile | None = None) -> dict[str, tuple[str, tuple[str, ...]]]:
    profile = profile or _active_profile()
    if "chain" not in profile.mcp_tool_families_enabled:
        return {}
    return dict(CHAIN_STARTERS)


def start_build(mcp_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    starters = build_starters_for_profile()
    if mcp_name not in starters:
        raise ValueError(f"build starter not enabled: {mcp_name}")
    tool_name, path_fields = starters[mcp_name]
    normalized = normalize_arguments(arguments, path_fields=path_fields)
    return jobs.start_tool_job(tool_name, normalized, family="build")


def start_tests(arguments: dict[str, Any] | None) -> dict[str, Any]:
    starters = test_starters_for_profile()
    if "start_service_tests" not in starters:
        raise ValueError("test starters not enabled for active profile")
    tool_name, path_fields = starters["start_service_tests"]
    normalized = normalize_arguments(arguments, path_fields=path_fields)
    return jobs.start_tool_job(tool_name, normalized, family="test")


def start_chain(mcp_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    starters = chain_starters_for_profile()
    if mcp_name not in starters:
        raise ValueError(f"chain starter not enabled: {mcp_name}")
    tool_name, path_fields = starters[mcp_name]
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
