#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from pathlib import Path

from . import locks
from ._streaming import stream_subprocess
from .build_diagnostics import count_build_diagnostics
from .workspace_root import detect_workspace_root

BUILD_LOCK_SUFFIX = ".ai-tools-build.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run psibase canonical full build.")
    parser.add_argument("--input-file", help="Path to JSON input file.")
    parser.add_argument("--input-json", help="Raw JSON input.")
    return parser.parse_args()


def read_input(args: argparse.Namespace) -> Dict[str, Any]:
    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            return json.load(f)
    if args.input_json:
        return json.loads(args.input_json)
    if not sys.stdin.isatty():
        return json.load(sys.stdin)
    raise ValueError("No input provided. Use --input-file, --input-json, or stdin JSON.")


def validate_input(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(data, dict):
        return False, "Input must be a JSON object."
    allowed = {
        "workspace_root",
        "build_dir",
        "configure_if_needed",
        "cmake_args",
        "install_target",
        "jobs",
    }
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        return False, f"Unknown input field(s): {', '.join(unknown)}"
    if "workspace_root" in data and not isinstance(data["workspace_root"], str):
        return False, "workspace_root must be a string."
    if "build_dir" in data and not isinstance(data["build_dir"], str):
        return False, "build_dir must be a string."
    if "configure_if_needed" in data and not isinstance(data["configure_if_needed"], bool):
        return False, "configure_if_needed must be a boolean."
    if "cmake_args" in data:
        if not isinstance(data["cmake_args"], list) or not all(
            isinstance(x, str) for x in data["cmake_args"]
        ):
            return False, "cmake_args must be an array of strings."
    if "install_target" in data and not isinstance(data["install_target"], str):
        return False, "install_target must be a string."
    if "jobs" in data and (not isinstance(data["jobs"], int) or data["jobs"] < 1):
        return False, "jobs must be an integer >= 1."
    return True, None


def resolve_build_dir(workspace_root: str, build_dir: str) -> str:
    if os.path.isabs(build_dir):
        return build_dir
    return os.path.join(workspace_root, build_dir)


def default_jobs() -> int:
    cpu = os.cpu_count() or 1
    return max(1, cpu // 3)


def base_result(
    *,
    status: str,
    ok: bool,
    workspace_root: str,
    build_dir: str,
    configured_this_run: bool,
    jobs: int,
    command_sequence: List[List[str]],
    summary: str,
    error_code: Optional[str],
    error_category: Optional[str],
    stdout: str,
    stderr: str,
    exit_code: Optional[int],
    duration_seconds: Optional[float],
) -> Dict[str, Any]:
    combined = "\n".join([stdout, stderr])
    diagnostics = count_build_diagnostics(combined)
    excerpt_lines = combined.splitlines()[-20:]
    failure_excerpt = ("\n".join(excerpt_lines).strip() or None) if not ok else None
    return {
        "ok": ok,
        "tool": "run_full_build",
        "status": status,
        "workspace_root": workspace_root,
        "build_dir": build_dir,
        "configured_this_run": configured_this_run,
        "jobs": jobs,
        "command_sequence": command_sequence,
        "duration_seconds": duration_seconds,
        "parse_quality": diagnostics["parse_quality"],
        "error_count": diagnostics["error_count"],
        "warning_count": diagnostics["warning_count"],
        "error_word_hits": diagnostics["error_word_hits"],
        "warning_word_hits": diagnostics["warning_word_hits"],
        "summary": summary,
        "error_code": error_code,
        "error_category": error_category,
        "failure_excerpt": failure_excerpt,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


def run_command(cmd: List[str], cwd: str, *, section_header: Optional[str] = None) -> subprocess.CompletedProcess:
    return stream_subprocess(cmd, cwd=cwd, section_header=section_header)


def main() -> int:
    try:
        data = read_input(parse_args())
    except Exception as exc:
        result = base_result(
            status="error",
            ok=False,
            workspace_root="",
            build_dir="",
            configured_this_run=False,
            jobs=1,
            command_sequence=[],
            summary=f"Failed to parse input JSON: {exc}",
            error_code="invalid_input",
            error_category="input_validation",
            stdout="",
            stderr="",
            exit_code=None,
            duration_seconds=None,
        )
        print(json.dumps(result, indent=2))
        return 1

    valid, msg = validate_input(data)
    if not valid:
        result = base_result(
            status="error",
            ok=False,
            workspace_root=str(data.get("workspace_root", "")),
            build_dir=str(data.get("build_dir", "")),
            configured_this_run=False,
            jobs=1,
            command_sequence=[],
            summary=msg or "Invalid input.",
            error_code="invalid_input",
            error_category="input_validation",
            stdout="",
            stderr="",
            exit_code=None,
            duration_seconds=None,
        )
        print(json.dumps(result, indent=2))
        return 1

    workspace_root = str(detect_workspace_root(data))
    build_dir_input = data.get("build_dir", "build")
    build_dir = resolve_build_dir(workspace_root, build_dir_input)
    configure_if_needed = data.get("configure_if_needed", True)
    install_target = data.get("install_target", "install")
    jobs = data.get("jobs", default_jobs())
    cmake_args = data.get(
        "cmake_args",
        [
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_DEBUG_WASM=ON",
            "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache",
            "-DCMAKE_C_COMPILER_LAUNCHER=ccache",
            "-DCMAKE_INSTALL_PREFIX=psidk",
            "..",
        ],
    )

    if shutil.which("make") is None or shutil.which("cmake") is None:
        result = base_result(
            status="error",
            ok=False,
            workspace_root=workspace_root,
            build_dir=build_dir,
            configured_this_run=False,
            jobs=jobs,
            command_sequence=[],
            summary="Required build tools (cmake/make) are not available.",
            error_code="environment_missing",
            error_category="environment",
            stdout="",
            stderr="",
            exit_code=None,
            duration_seconds=None,
        )
        print(json.dumps(result, indent=2))
        return 1

    configured_this_run = False
    commands: List[List[str]] = []
    out_parts: List[str] = []
    err_parts: List[str] = []
    start = time.monotonic()

    if not os.path.isdir(build_dir):
        if not configure_if_needed:
            result = base_result(
                status="error",
                ok=False,
                workspace_root=workspace_root,
                build_dir=build_dir,
                configured_this_run=False,
                jobs=jobs,
                command_sequence=[],
                summary="Build directory is missing and configure_if_needed is false.",
                error_code="build_dir_missing",
                error_category="build_configuration",
                stdout="",
                stderr="",
                exit_code=None,
                duration_seconds=None,
            )
            print(json.dumps(result, indent=2))
            return 1
        os.makedirs(build_dir, exist_ok=True)

    lock_path, holder = locks.acquire_dir_lock(
        Path(build_dir),
        suffix=BUILD_LOCK_SUFFIX,
        tool="run_full_build",
        workspace_root=Path(workspace_root),
    )
    if lock_path is None:
        result = base_result(
            status="error",
            ok=False,
            workspace_root=workspace_root,
            build_dir=build_dir,
            configured_this_run=False,
            jobs=jobs,
            command_sequence=[],
            summary=(
                f"Another build job is already using build_dir={build_dir} "
                f"(holder pid={(holder or {}).get('pid')}, "
                f"job_id={(holder or {}).get('job_id')}, "
                f"tool={(holder or {}).get('tool')}). "
                "Pass a distinct build_dir, wait for the holder to finish, or cancel it."
            ),
            error_code="resource_busy",
            error_category="concurrency",
            stdout="",
            stderr="",
            exit_code=None,
            duration_seconds=None,
        )
        result["lock_holder"] = holder
        print(json.dumps(result, indent=2))
        return 1

    try:
        cmake_cache = os.path.join(build_dir, "CMakeCache.txt")
        if not os.path.isfile(cmake_cache):
            if not configure_if_needed:
                result = base_result(
                    status="error",
                    ok=False,
                    workspace_root=workspace_root,
                    build_dir=build_dir,
                    configured_this_run=False,
                    jobs=jobs,
                    command_sequence=[],
                    summary="Build directory is not configured and configure_if_needed is false.",
                    error_code="cmake_not_configured",
                    error_category="build_configuration",
                    stdout="",
                    stderr="",
                    exit_code=None,
                    duration_seconds=None,
                )
                print(json.dumps(result, indent=2))
                return 1
            configure_cmd = ["cmake"] + cmake_args
            commands.append(configure_cmd)
            configured_this_run = True
            configure = run_command(
                configure_cmd,
                build_dir,
                section_header=f"\n===== run_full_build: cmake configure =====\n$ {' '.join(configure_cmd)}",
            )
            out_parts.append(configure.stdout)
            err_parts.append(configure.stderr)
            if configure.returncode != 0:
                result = base_result(
                    status="failed",
                    ok=False,
                    workspace_root=workspace_root,
                    build_dir=build_dir,
                    configured_this_run=configured_this_run,
                    jobs=jobs,
                    command_sequence=commands,
                    summary="CMake configure step failed.",
                    error_code="cmake_config_failed",
                    error_category="build_configuration",
                    stdout="\n".join(out_parts),
                    stderr="\n".join(err_parts),
                    exit_code=configure.returncode,
                    duration_seconds=time.monotonic() - start,
                )
                print(json.dumps(result, indent=2))
                return 1

        make_cmd = ["make", install_target, f"-j{jobs}"]
        commands.append(make_cmd)
        build = run_command(
            make_cmd,
            build_dir,
            section_header=f"\n===== run_full_build: make {install_target} -j{jobs} =====\n$ {' '.join(make_cmd)}",
        )
        out_parts.append(build.stdout)
        err_parts.append(build.stderr)

        if build.returncode != 0:
            result = base_result(
                status="failed",
                ok=False,
                workspace_root=workspace_root,
                build_dir=build_dir,
                configured_this_run=configured_this_run,
                jobs=jobs,
                command_sequence=commands,
                summary="Full build failed.",
                error_code="build_failed",
                error_category="build_execution",
                stdout="\n".join(out_parts),
                stderr="\n".join(err_parts),
                exit_code=build.returncode,
                duration_seconds=time.monotonic() - start,
            )
            print(json.dumps(result, indent=2))
            return 1

        result = base_result(
            status="passed",
            ok=True,
            workspace_root=workspace_root,
            build_dir=build_dir,
            configured_this_run=configured_this_run,
            jobs=jobs,
            command_sequence=commands,
            summary="Full baseline build completed successfully.",
            error_code=None,
            error_category=None,
            stdout="\n".join(out_parts),
            stderr="\n".join(err_parts),
            exit_code=build.returncode,
            duration_seconds=time.monotonic() - start,
        )
        print(json.dumps(result, indent=2))
        return 0
    finally:
        locks.release_dir_lock(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    from ._invoke import run_main_with_payload
    return run_main_with_payload(sys.modules[__name__], payload)


def run_with_exit_code(payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    from ._invoke import run_main_with_payload_and_exit_code
    return run_main_with_payload_and_exit_code(sys.modules[__name__], payload)
