#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from ._psibase_command import choose_psibase_subcommand
from ._streaming import stream_subprocess


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
SUMMARY_RE = re.compile(
    r"test result:\s*(ok|FAILED)\.\s*"
    r"(\d+)\s*passed;\s*"
    r"(\d+)\s*failed;\s*"
    r"(\d+)\s*ignored;\s*"
    r"(\d+)\s*measured;\s*"
    r"(\d+)\s*filtered out;"
    r"(?:\s*finished in\s*([0-9.]+)s)?"
)
RUNNING_WASM_RE = re.compile(r"Running\s+([^\s]*\.wasm)")
RUNNING_TESTS_RE = re.compile(r"running\s+(\d+)\s+tests?")
TEST_STARTED_RE = re.compile(r"^test\s+([^\s].*?)\s+\.\.\.")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run psibase service tests.")
    parser.add_argument("--input-file", help="Path to JSON input file.")
    parser.add_argument("--input-json", help="Raw JSON input.")
    return parser.parse_args()


def error_result(
    *,
    command: List[str],
    service_manifest_path: Optional[str],
    test_filter: Optional[str],
    error_code: str,
    error_category: str,
    summary: str,
    stdout: str = "",
    stderr: str = "",
    exit_code: Optional[int] = None,
    failure_excerpt: Optional[str] = None,
    last_test_started: Optional[str] = None,
    tests_started_hint: Optional[int] = None,
    lookup_hint: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "tool": "run_service_tests",
        "status": "error",
        "command": command,
        "service_manifest_path": service_manifest_path or "",
        "test_filter": test_filter,
        "stats": None,
        "test_binaries": [],
        "summary_line": None,
        "duration_seconds": None,
        "zero_tests": False,
        "summary": summary,
        "error_code": error_code,
        "error_category": error_category,
        "failure_excerpt": failure_excerpt,
        "last_test_started": last_test_started,
        "tests_started_hint": tests_started_hint,
        "lookup_hint": lookup_hint,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


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
        "service_manifest_path",
        "test_filter",
        "target_dir",
        "psitest_path",
        "assert_nonzero_tests",
        "workspace_root",
    }
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        return False, f"Unknown input field(s): {', '.join(unknown)}"
    if "service_manifest_path" not in data or not isinstance(data["service_manifest_path"], str):
        return False, "service_manifest_path is required and must be a string."
    if "test_filter" in data and data["test_filter"] is not None and not isinstance(data["test_filter"], str):
        return False, "test_filter must be a string when provided."
    if "target_dir" in data and data["target_dir"] is not None and not isinstance(data["target_dir"], str):
        return False, "target_dir must be a string when provided."
    if "psitest_path" in data and data["psitest_path"] is not None and not isinstance(data["psitest_path"], str):
        return False, "psitest_path must be a string when provided."
    if "assert_nonzero_tests" in data and not isinstance(data["assert_nonzero_tests"], bool):
        return False, "assert_nonzero_tests must be a boolean."
    if "workspace_root" in data and data["workspace_root"] is not None and not isinstance(data["workspace_root"], str):
        return False, "workspace_root must be a string when provided."
    return True, None


def manifest_has_psibase_server(manifest_path: str) -> bool:
    in_psibase_metadata = False
    with open(manifest_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line.startswith("["):
                in_psibase_metadata = line == "[package.metadata.psibase]"
            elif in_psibase_metadata and line.startswith("server"):
                return True
    return False


def parse_test_output(stdout: str, stderr: str) -> Dict[str, Any]:
    combined = strip_ansi("\n".join([stdout, stderr]))
    lines = combined.splitlines()

    last_binary: Optional[str] = None
    running_hint: Optional[int] = None
    last_test_started: Optional[str] = None
    summary_entries: List[Dict[str, Any]] = []
    summary_line: Optional[str] = None

    for line in lines:
        wasm_match = RUNNING_WASM_RE.search(line)
        if wasm_match:
            last_binary = os.path.basename(wasm_match.group(1))

        running_match = RUNNING_TESTS_RE.search(line)
        if running_match:
            running_hint = int(running_match.group(1))

        test_started_match = TEST_STARTED_RE.search(line.strip())
        if test_started_match:
            last_test_started = test_started_match.group(1)

        summary_match = SUMMARY_RE.search(line)
        if summary_match:
            summary_line = line.strip()
            status_word = summary_match.group(1)
            passed = int(summary_match.group(2))
            failed = int(summary_match.group(3))
            ignored = int(summary_match.group(4))
            measured = int(summary_match.group(5))
            filtered_out = int(summary_match.group(6))
            duration = float(summary_match.group(7)) if summary_match.group(7) else None
            discovered = passed + failed + ignored + measured

            summary_entries.append(
                {
                    "binary": last_binary or f"unknown_{len(summary_entries) + 1}",
                    "status": "passed" if status_word == "ok" and failed == 0 else "failed",
                    "summary_line": summary_line,
                    "duration_seconds": duration,
                    "stats": {
                        "tests_discovered": discovered,
                        "tests_passed": passed,
                        "tests_failed": failed,
                        "tests_ignored": ignored,
                        "tests_measured": measured,
                        "tests_filtered_out": filtered_out,
                    },
                }
            )

    aggregate = None
    if summary_entries:
        aggregate = {
            "tests_discovered": sum(x["stats"]["tests_discovered"] for x in summary_entries),
            "tests_passed": sum(x["stats"]["tests_passed"] for x in summary_entries),
            "tests_failed": sum(x["stats"]["tests_failed"] for x in summary_entries),
            "tests_ignored": sum(x["stats"]["tests_ignored"] for x in summary_entries),
            "tests_measured": sum(x["stats"]["tests_measured"] for x in summary_entries),
            "tests_filtered_out": sum(x["stats"]["tests_filtered_out"] for x in summary_entries),
        }

    return {
        "stats": aggregate,
        "test_binaries": summary_entries,
        "summary_line": summary_line,
        "duration_seconds": summary_entries[-1]["duration_seconds"] if summary_entries else None,
        "last_test_started": last_test_started,
        "tests_started_hint": running_hint,
        "combined": combined,
    }


def classify_failure(parsed: Dict[str, Any], exit_code: int) -> Tuple[str, str]:
    combined = parsed["combined"]
    if parsed["stats"] is not None and parsed["stats"]["tests_failed"] > 0:
        return "test_failed", "test_execution"
    if parsed["tests_started_hint"] is not None and parsed["stats"] is None:
        return "test_run_aborted", "test_execution"
    if "Failed running:" in combined and parsed["stats"] is None:
        return "test_run_aborted", "test_execution"
    if exit_code != 0:
        return "build_failed", "build_or_compile"
    return "unknown_error", "unknown"


def infer_lookup_hint(combined: str, error_code: str, zero_tests: bool) -> Optional[str]:
    text = combined.lower()

    if zero_tests or error_code == "zero_tests_discovered":
        return "running 0 tests manifest test discovery"
    if "service 'tokens' not initialized" in text or "service 'nft' not initialized" in text:
        return "test_case packages dependencies tokens nft"
    if "tokens" in text and "not initialized" in text:
        return "test_case packages dependencies tokens nft"
    if ("404" in text and "/graphql" in text) or "the resource '/graphql' was not found" in text:
        return "graphql registerServer 404 routing service tests"
    if "duplicate" in text and "transaction" in text:
        return "chain.start_block duplicate transaction tests"
    if "package-name" in text and "case" in text:
        return "packages case-sensitive package-name cargo toml"
    return None


def summary_text(stats: Dict[str, int]) -> str:
    return (
        f"{stats['tests_passed']} passed; "
        f"{stats['tests_failed']} failed; "
        f"{stats['tests_ignored']} ignored; "
        f"{stats['tests_measured']} measured; "
        f"{stats['tests_filtered_out']} filtered out"
    )


def choose_test_command_prefix() -> Tuple[Optional[List[str]], Optional[str]]:
    # Prefer the repo-built cargo-psibase binary when available, falling back to
    # the cargo subcommand only if necessary.
    return choose_psibase_subcommand("test")


def infer_psitest_path(workspace_root: str) -> Optional[str]:
    path_candidate = shutil.which("psitest")
    if path_candidate:
        return path_candidate

    candidates = [
        os.path.join(workspace_root, "build", "psidk", "bin", "psitest"),
        os.path.join(workspace_root, "build", "psitest"),
        "/root/psibase/build/psidk/bin/psitest",
        "/root/psibase/build/psitest",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def main() -> int:
    args = parse_args()
    command: List[str] = []
    input_data: Dict[str, Any]

    try:
        input_data = read_input(args)
    except Exception as exc:
        result = error_result(
            command=command,
            service_manifest_path=None,
            test_filter=None,
            error_code="invalid_input",
            error_category="input_validation",
            summary=f"Failed to parse input JSON: {exc}",
        )
        print(json.dumps(result, indent=2))
        return 1

    valid, message = validate_input(input_data)
    if not valid:
        result = error_result(
            command=command,
            service_manifest_path=input_data.get("service_manifest_path"),
            test_filter=input_data.get("test_filter"),
            error_code="invalid_input",
            error_category="input_validation",
            summary=message or "Invalid input.",
        )
        print(json.dumps(result, indent=2))
        return 1

    service_manifest_path = input_data["service_manifest_path"]
    test_filter = input_data.get("test_filter")
    target_dir = input_data.get("target_dir")
    psitest_path = input_data.get("psitest_path")
    assert_nonzero_tests = input_data.get("assert_nonzero_tests", True)
    workspace_root = input_data.get("workspace_root")

    if not os.path.isabs(service_manifest_path):
        result = error_result(
            command=command,
            service_manifest_path=service_manifest_path,
            test_filter=test_filter,
            error_code="invalid_manifest_path",
            error_category="input_validation",
            summary="service_manifest_path must be an absolute path.",
        )
        print(json.dumps(result, indent=2))
        return 1

    if not os.path.isfile(service_manifest_path):
        result = error_result(
            command=command,
            service_manifest_path=service_manifest_path,
            test_filter=test_filter,
            error_code="invalid_manifest_path",
            error_category="input_validation",
            summary=f"Manifest file not found: {service_manifest_path}",
        )
        print(json.dumps(result, indent=2))
        return 1

    if not manifest_has_psibase_server(service_manifest_path):
        result = error_result(
            command=command,
            service_manifest_path=service_manifest_path,
            test_filter=test_filter,
            error_code="unsupported_manifest",
            error_category="input_validation",
            summary="Manifest is not a psibase service crate (missing [package.metadata.psibase].server).",
        )
        print(json.dumps(result, indent=2))
        return 1

    if not workspace_root:
        workspace_root = os.path.dirname(service_manifest_path)

    command_prefix, prefix_error = choose_test_command_prefix()
    if command_prefix is None:
        result = error_result(
            command=command,
            service_manifest_path=service_manifest_path,
            test_filter=test_filter,
            error_code="environment_missing",
            error_category="environment",
            summary=prefix_error or "No supported psibase test runner is available.",
        )
        print(json.dumps(result, indent=2))
        return 1

    if not psitest_path:
        psitest_path = infer_psitest_path(workspace_root)

    if psitest_path:
        if not os.path.isabs(psitest_path):
            result = error_result(
                command=command,
                service_manifest_path=service_manifest_path,
                test_filter=test_filter,
                error_code="missing_psitest",
                error_category="input_validation",
                summary="psitest_path must be an absolute path.",
            )
            print(json.dumps(result, indent=2))
            return 1
        if not os.path.isfile(psitest_path):
            result = error_result(
                command=command,
                service_manifest_path=service_manifest_path,
                test_filter=test_filter,
                error_code="missing_psitest",
                error_category="input_validation",
                summary=f"psitest binary not found at {psitest_path}",
            )
            print(json.dumps(result, indent=2))
            return 1

    command = list(command_prefix)
    if test_filter:
        command.append(test_filter)
    command.extend(["--manifest-path", service_manifest_path])
    if target_dir:
        command.extend(["--target-dir", target_dir])
    if psitest_path:
        command.extend(["--psitest", psitest_path])

    run = stream_subprocess(
        command,
        cwd=workspace_root,
        section_header=(
            f"\n===== run_service_tests: {os.path.basename(os.path.dirname(service_manifest_path)) or 'service'} =====\n"
            f"$ {' '.join(command)}"
        ),
    )

    parsed = parse_test_output(run.stdout, run.stderr)
    stats = parsed["stats"]
    zero_tests = stats is not None and stats["tests_discovered"] == 0

    if stats is not None and stats["tests_failed"] == 0 and run.returncode == 0:
        if assert_nonzero_tests and zero_tests:
            lookup_hint = infer_lookup_hint(parsed["combined"], "zero_tests_discovered", True)
            result = error_result(
                command=command,
                service_manifest_path=service_manifest_path,
                test_filter=test_filter,
                error_code="zero_tests_discovered",
                error_category="test_discovery",
                summary="Command succeeded but discovered zero tests.",
                stdout=run.stdout,
                stderr=run.stderr,
                exit_code=run.returncode,
                last_test_started=parsed["last_test_started"],
                tests_started_hint=parsed["tests_started_hint"],
                lookup_hint=lookup_hint,
            )
            result["zero_tests"] = True
            print(json.dumps(result, indent=2))
            return 1

        result = {
            "ok": True,
            "tool": "run_service_tests",
            "status": "passed",
            "command": command,
            "service_manifest_path": service_manifest_path,
            "test_filter": test_filter,
            "stats": stats,
            "test_binaries": parsed["test_binaries"],
            "summary_line": parsed["summary_line"],
            "duration_seconds": parsed["duration_seconds"],
            "zero_tests": bool(zero_tests),
            "summary": summary_text(stats),
            "error_code": None,
            "error_category": None,
            "failure_excerpt": None,
            "last_test_started": parsed["last_test_started"],
            "tests_started_hint": parsed["tests_started_hint"],
            "lookup_hint": None,
            "stdout": run.stdout,
            "stderr": run.stderr,
            "exit_code": run.returncode,
        }
        print(json.dumps(result, indent=2))
        return 0

    missing_runner_text = strip_ansi("\n".join([run.stdout, run.stderr])).lower()
    if "no such command: `psibase`" in missing_runner_text:
        result = error_result(
            command=command,
            service_manifest_path=service_manifest_path,
            test_filter=test_filter,
            error_code="environment_missing",
            error_category="environment",
            summary="No supported psibase test runner is available in this environment.",
            stdout=run.stdout,
            stderr=run.stderr,
            exit_code=run.returncode,
        )
        print(json.dumps(result, indent=2))
        return 1

    error_code, error_category = classify_failure(parsed, run.returncode)
    status = "aborted" if error_code == "test_run_aborted" else "failed"
    lookup_hint = infer_lookup_hint(parsed["combined"], error_code, bool(zero_tests))
    excerpt_lines = parsed["combined"].splitlines()[-12:]
    failure_excerpt = "\n".join(excerpt_lines).strip() or None

    result = {
        "ok": False,
        "tool": "run_service_tests",
        "status": status,
        "command": command,
        "service_manifest_path": service_manifest_path,
        "test_filter": test_filter,
        "stats": stats,
        "test_binaries": parsed["test_binaries"],
        "summary_line": parsed["summary_line"],
        "duration_seconds": parsed["duration_seconds"],
        "zero_tests": bool(zero_tests),
        "summary": "Service test run failed.",
        "error_code": error_code,
        "error_category": error_category,
        "failure_excerpt": failure_excerpt,
        "last_test_started": parsed["last_test_started"],
        "tests_started_hint": parsed["tests_started_hint"],
        "lookup_hint": lookup_hint,
        "stdout": run.stdout,
        "stderr": run.stderr,
        "exit_code": run.returncode,
    }
    print(json.dumps(result, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    from ._invoke import run_main_with_payload
    return run_main_with_payload(sys.modules[__name__], payload)


def run_with_exit_code(payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    from ._invoke import run_main_with_payload_and_exit_code
    return run_main_with_payload_and_exit_code(sys.modules[__name__], payload)
