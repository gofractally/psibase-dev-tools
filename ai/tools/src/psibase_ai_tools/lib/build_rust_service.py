#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from ._psibase_command import choose_psibase_subcommand
from ._streaming import stream_subprocess
from .build_diagnostics import count_build_diagnostics
from .workspace_root import detect_workspace_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Rust service/query-service by CMake target.")
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
    allowed = {"cmake_target_name", "service_kind", "workspace_root", "target_dir", "psibase_binary_path"}
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        return False, f"Unknown input field(s): {', '.join(unknown)}"
    if "cmake_target_name" not in data or not isinstance(data["cmake_target_name"], str):
        return False, "cmake_target_name is required and must be a string."
    if "service_kind" in data and data["service_kind"] not in ("service", "query-service", "both"):
        return False, "service_kind must be one of: service, query-service, both."
    if "workspace_root" in data and not isinstance(data["workspace_root"], str):
        return False, "workspace_root must be a string."
    if "target_dir" in data and data["target_dir"] is not None and not isinstance(data["target_dir"], str):
        return False, "target_dir must be a string when provided."
    if "psibase_binary_path" in data and data["psibase_binary_path"] is not None and not isinstance(
        data["psibase_binary_path"], str
    ):
        return False, "psibase_binary_path must be a string when provided."
    return True, None


def make_result(
    *,
    ok: bool,
    status: str,
    cmake_target_name: str,
    service_kind: str,
    commands: List[List[str]],
    summary: str,
    stdout: str,
    stderr: str,
    exit_code: Optional[int],
    error_code: Optional[str],
    error_category: Optional[str],
    resolved_package_path: Optional[str],
    resolved_manifests: List[str],
    duration_seconds: Optional[float],
) -> Dict[str, Any]:
    combined = "\n".join([stdout, stderr])
    diagnostics = count_build_diagnostics(combined)
    return {
        "ok": ok,
        "tool": "build_rust_service",
        "status": status,
        "cmake_target_name": cmake_target_name,
        "service_kind": service_kind,
        "resolved_package_path": resolved_package_path,
        "resolved_manifests": resolved_manifests,
        "commands": commands,
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


def find_cargo_package_path(workspace_root: str, cmake_target_name: str) -> Optional[str]:
    cmake_file = os.path.join(workspace_root, "CMakeLists.txt")
    if not os.path.isfile(cmake_file):
        return None
    with open(cmake_file, "r", encoding="utf-8") as f:
        text = f.read()
    for match in re.finditer(r"cargo_psibase_package\s*\((.*?)\)", text, flags=re.DOTALL):
        block = match.group(1)
        output_match = re.search(r"OUTPUT\s+\$\{SERVICE_DIR\}/([A-Za-z0-9_-]+)\.psi", block)
        path_match = re.search(r"PATH\s+([^\s\)]+)", block)
        if output_match and path_match and output_match.group(1) == cmake_target_name:
            return path_match.group(1)
    return None


def choose_build_prefix(
    psibase_binary_path: Optional[str], workspace_root: Optional[str] = None
) -> Tuple[Optional[List[str]], Optional[str]]:
    if psibase_binary_path:
        if os.path.isfile(psibase_binary_path):
            return [psibase_binary_path, "build"], None
        return None, f"Specified psibase_binary_path does not exist: {psibase_binary_path}"

    # Prefer the repo-built cargo-psibase binary when available, falling back to
    # the cargo subcommand only if necessary.
    return choose_psibase_subcommand("build", workspace_root)


def manifests_for_kind(package_root: str, service_kind: str) -> List[str]:
    candidates: List[str] = []
    if service_kind in ("service", "both"):
        candidates.append(os.path.join(package_root, "service", "Cargo.toml"))
    if service_kind in ("query-service", "both"):
        candidates.append(os.path.join(package_root, "query-service", "Cargo.toml"))
    return [c for c in candidates if os.path.isfile(c)]


def main() -> int:
    try:
        data = read_input(parse_args())
    except Exception as exc:
        out = make_result(
            ok=False,
            status="error",
            cmake_target_name="",
            service_kind="service",
            commands=[],
            summary=f"Failed to parse input JSON: {exc}",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="invalid_input",
            error_category="input_validation",
            resolved_package_path=None,
            resolved_manifests=[],
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    valid, msg = validate_input(data)
    if not valid:
        out = make_result(
            ok=False,
            status="error",
            cmake_target_name=str(data.get("cmake_target_name", "")),
            service_kind=str(data.get("service_kind", "service")),
            commands=[],
            summary=msg or "Invalid input.",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="invalid_input",
            error_category="input_validation",
            resolved_package_path=None,
            resolved_manifests=[],
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    cmake_target_name = data["cmake_target_name"].strip()
    service_kind = data.get("service_kind", "service")
    workspace_root = str(detect_workspace_root(data))
    target_dir = data.get("target_dir")
    psibase_binary_path = data.get("psibase_binary_path")

    rel_pkg = find_cargo_package_path(workspace_root, cmake_target_name)
    if rel_pkg is None:
        out = make_result(
            ok=False,
            status="error",
            cmake_target_name=cmake_target_name,
            service_kind=service_kind,
            commands=[],
            summary="CMake target could not be mapped to a cargo_psibase_package PATH.",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="resolution_failed",
            error_category="target_resolution",
            resolved_package_path=None,
            resolved_manifests=[],
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    package_root = os.path.join(workspace_root, rel_pkg)
    if not os.path.isdir(package_root):
        out = make_result(
            ok=False,
            status="error",
            cmake_target_name=cmake_target_name,
            service_kind=service_kind,
            commands=[],
            summary=f"Resolved package path does not exist: {package_root}",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="resolution_failed",
            error_category="target_resolution",
            resolved_package_path=package_root,
            resolved_manifests=[],
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    manifests = manifests_for_kind(package_root, service_kind)
    if not manifests:
        out = make_result(
            ok=False,
            status="error",
            cmake_target_name=cmake_target_name,
            service_kind=service_kind,
            commands=[],
            summary="No matching service/query-service Cargo.toml found for requested service_kind.",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="manifest_not_found",
            error_category="target_resolution",
            resolved_package_path=package_root,
            resolved_manifests=[],
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    prefix, prefix_error = choose_build_prefix(psibase_binary_path, workspace_root)
    if prefix is None:
        out = make_result(
            ok=False,
            status="error",
            cmake_target_name=cmake_target_name,
            service_kind=service_kind,
            commands=[],
            summary=prefix_error or "No supported build runner available.",
            stdout="",
            stderr="",
            exit_code=None,
            error_code="environment_missing",
            error_category="environment",
            resolved_package_path=package_root,
            resolved_manifests=manifests,
            duration_seconds=None,
        )
        print(json.dumps(out, indent=2))
        return 1

    commands: List[List[str]] = []
    stdout_parts: List[str] = []
    stderr_parts: List[str] = []
    start = time.monotonic()
    last_exit_code: Optional[int] = None

    for manifest in manifests:
        cmd = list(prefix) + ["--manifest-path", manifest]
        if target_dir:
            cmd.extend(["--target-dir", target_dir])
        commands.append(cmd)
        run = stream_subprocess(
            cmd,
            cwd=workspace_root,
            section_header=f"\n===== build_rust_service: {cmake_target_name} ({manifest}) =====\n$ {' '.join(cmd)}",
        )
        last_exit_code = run.returncode
        stdout_parts.append(f"### {manifest}\n{run.stdout}")
        stderr_parts.append(f"### {manifest}\n{run.stderr}")
        if run.returncode != 0:
            out = make_result(
                ok=False,
                status="failed",
                cmake_target_name=cmake_target_name,
                service_kind=service_kind,
                commands=commands,
                summary="Rust service build failed.",
                stdout="\n".join(stdout_parts),
                stderr="\n".join(stderr_parts),
                exit_code=last_exit_code,
                error_code="build_failed",
                error_category="build_execution",
                resolved_package_path=package_root,
                resolved_manifests=manifests,
                duration_seconds=time.monotonic() - start,
            )
            print(json.dumps(out, indent=2))
            return 1

    out = make_result(
        ok=True,
        status="passed",
        cmake_target_name=cmake_target_name,
        service_kind=service_kind,
        commands=commands,
        summary="Rust service build completed successfully.",
        stdout="\n".join(stdout_parts),
        stderr="\n".join(stderr_parts),
        exit_code=last_exit_code,
        error_code=None,
        error_category=None,
        resolved_package_path=package_root,
        resolved_manifests=manifests,
        duration_seconds=time.monotonic() - start,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    from ._invoke import run_main_with_payload
    return run_main_with_payload(sys.modules[__name__], payload)


def run_with_exit_code(payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    from ._invoke import run_main_with_payload_and_exit_code
    return run_main_with_payload_and_exit_code(sys.modules[__name__], payload)
