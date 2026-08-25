#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import sys
import time
from typing import Any, Dict, Optional, Tuple

from pathlib import Path

from . import locks
from ._streaming import stream_subprocess
from .build_diagnostics import count_build_diagnostics
from .workspace_root import detect_workspace_root

BUILD_LOCK_SUFFIX = ".ai-tools-build.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build one package target via make.")
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
    allowed = {"make_target", "workspace_root", "build_dir", "jobs"}
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        return False, f"Unknown input field(s): {', '.join(unknown)}"
    if "make_target" not in data or not isinstance(data["make_target"], str) or not data["make_target"].strip():
        return False, "make_target is required and must be a non-empty string."
    if "workspace_root" in data and not isinstance(data["workspace_root"], str):
        return False, "workspace_root must be a string."
    if "build_dir" in data and not isinstance(data["build_dir"], str):
        return False, "build_dir must be a string."
    if "jobs" in data and (not isinstance(data["jobs"], int) or data["jobs"] < 1):
        return False, "jobs must be an integer >= 1."
    return True, None


def default_jobs() -> int:
    cpu = os.cpu_count() or 1
    return max(1, cpu // 3)


def resolve_build_dir(workspace_root: str, build_dir: str) -> str:
    if os.path.isabs(build_dir):
        return build_dir
    return os.path.join(workspace_root, build_dir)


def result_obj(
    *,
    ok: bool,
    status: str,
    workspace_root: str,
    build_dir: str,
    make_target: str,
    command: list[str],
    summary: str,
    stdout: str,
    stderr: str,
    exit_code: Optional[int],
    error_code: Optional[str],
    error_category: Optional[str],
    duration_seconds: Optional[float],
) -> Dict[str, Any]:
    combined = "\n".join([stdout, stderr])
    diagnostics = count_build_diagnostics(combined)
    psi_output_hint = os.path.join(build_dir, "share", "psibase", "packages", f"{make_target}.psi")
    return {
        "ok": ok,
        "tool": "build_package",
        "status": status,
        "workspace_root": workspace_root,
        "build_dir": build_dir,
        "make_target": make_target,
        "command": command,
        "psi_output_hint": psi_output_hint,
        "psi_output_exists": os.path.isfile(psi_output_hint),
        "duration_seconds": duration_seconds,
        "parse_quality": diagnostics["parse_quality"],
        "error_count": diagnostics["error_count"],
        "warning_count": diagnostics["warning_count"],
        "error_word_hits": diagnostics["error_word_hits"],
        "warning_word_hits": diagnostics["warning_word_hits"],
        "summary": summary,
        "error_code": error_code,
        "error_category": error_category,
        "failure_excerpt": None if ok else "\n".join(combined.splitlines()[-20:]).strip() or None,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


def main() -> int:
    try:
        data = read_input(parse_args())
    except Exception as exc:
        out = result_obj(
            ok=False,
            status="error",
            workspace_root="",
            build_dir="",
            make_target="",
            command=[],
            summary=f"Failed to parse input JSON: {exc}",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="invalid_input",
            error_category="input_validation",
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    valid, msg = validate_input(data)
    if not valid:
        out = result_obj(
            ok=False,
            status="error",
            workspace_root=str(data.get("workspace_root", "")),
            build_dir=str(data.get("build_dir", "")),
            make_target=str(data.get("make_target", "")),
            command=[],
            summary=msg or "Invalid input.",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="invalid_input",
            error_category="input_validation",
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    workspace_root = str(detect_workspace_root(data))
    build_dir = resolve_build_dir(workspace_root, data.get("build_dir", "build"))
    make_target = data["make_target"].strip()
    jobs = data.get("jobs", default_jobs())
    command = ["make", make_target, f"-j{jobs}"]

    if shutil.which("make") is None:
        out = result_obj(
            ok=False,
            status="error",
            workspace_root=workspace_root,
            build_dir=build_dir,
            make_target=make_target,
            command=command,
            summary="make executable is not available.",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="environment_missing",
            error_category="environment",
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    if not os.path.isdir(build_dir):
        out = result_obj(
            ok=False,
            status="error",
            workspace_root=workspace_root,
            build_dir=build_dir,
            make_target=make_target,
            command=command,
            summary="Build directory does not exist.",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="build_dir_missing",
            error_category="build_configuration",
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    if not os.path.isfile(os.path.join(build_dir, "CMakeCache.txt")):
        out = result_obj(
            ok=False,
            status="error",
            workspace_root=workspace_root,
            build_dir=build_dir,
            make_target=make_target,
            command=command,
            summary="Build directory is not configured (missing CMakeCache.txt).",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="cmake_not_configured",
            error_category="build_configuration",
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    lock_path, holder = locks.acquire_dir_lock(
        Path(build_dir),
        suffix=BUILD_LOCK_SUFFIX,
        tool="build_package",
        workspace_root=Path(workspace_root),
    )
    if lock_path is None:
        out = result_obj(
            ok=False,
            status="error",
            workspace_root=workspace_root,
            build_dir=build_dir,
            make_target=make_target,
            command=command,
            summary=(
                f"Another build job is already using build_dir={build_dir} "
                f"(holder pid={(holder or {}).get('pid')}, "
                f"job_id={(holder or {}).get('job_id')}, "
                f"tool={(holder or {}).get('tool')}). "
                "Pass a distinct build_dir, wait for the holder to finish, or cancel it."
            ),
            stdout="",
            stderr="",
            exit_code=None,
            error_code="resource_busy",
            error_category="concurrency",
            duration_seconds=None,
        )
        out["lock_holder"] = holder
        print(json.dumps(out, indent=2))
        return 1

    try:
        start = time.monotonic()
        run = stream_subprocess(
            command,
            cwd=build_dir,
            section_header=f"\n===== build_package: {make_target} -j{jobs} =====\n$ {' '.join(command)}",
        )
        duration = time.monotonic() - start
        combined = "\n".join([run.stdout, run.stderr]).lower()
        if run.returncode != 0:
            err_code = "invalid_target" if "no rule to make target" in combined else "build_failed"
            err_category = "target_resolution" if err_code == "invalid_target" else "build_execution"
            out = result_obj(
                ok=False,
                status="failed",
                workspace_root=workspace_root,
                build_dir=build_dir,
                make_target=make_target,
                command=command,
                summary="Package build failed.",
                stdout=run.stdout,
                stderr=run.stderr,
                exit_code=run.returncode,
                error_code=err_code,
                error_category=err_category,
                duration_seconds=duration,
            )
            print(json.dumps(out, indent=2))
            return 1

        out = result_obj(
            ok=True,
            status="passed",
            workspace_root=workspace_root,
            build_dir=build_dir,
            make_target=make_target,
            command=command,
            summary="Package build completed successfully.",
            stdout=run.stdout,
            stderr=run.stderr,
            exit_code=run.returncode,
            error_code=None,
            error_category=None,
            duration_seconds=duration,
        )
        print(json.dumps(out, indent=2))
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
