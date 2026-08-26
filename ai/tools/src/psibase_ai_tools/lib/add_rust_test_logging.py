#!/usr/bin/env python3
import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Rust test logging snippet.")
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


def validate(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(data, dict):
        return False, "Input must be a JSON object."
    if not isinstance(data.get("test_name"), str) or not data["test_name"].strip():
        return False, "test_name is required and must be a non-empty string."
    if "log_values" in data and (
        not isinstance(data["log_values"], list) or not all(isinstance(x, str) for x in data["log_values"])
    ):
        return False, "log_values must be an array of strings."
    if "include_trace_helper" in data and not isinstance(data["include_trace_helper"], bool):
        return False, "include_trace_helper must be boolean."
    return True, None


def main() -> int:
    try:
        data = read_input(parse_args())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "tool": "add_rust_test_logging",
                    "status": "error",
                    "test_name": "",
                    "snippet": "",
                    "notes": [],
                    "error_code": f"invalid_input: {exc}",
                },
                indent=2,
            )
        )
        return 1

    valid, msg = validate(data)
    if not valid:
        print(
            json.dumps(
                {
                    "ok": False,
                    "tool": "add_rust_test_logging",
                    "status": "error",
                    "test_name": str(data.get("test_name", "")),
                    "snippet": "",
                    "notes": [],
                    "error_code": f"invalid_input: {msg}",
                },
                indent=2,
            )
        )
        return 1

    test_name = data["test_name"].strip()
    log_values: List[str] = data.get("log_values", [])
    include_trace_helper = data.get("include_trace_helper", True)

    log_lines = [f'println!("DEBUG {test_name}: start");']
    for item in log_values:
        key = item.replace('"', '\\"')
        log_lines.append(f'println!("DEBUG {test_name}: {key}={{:?}}", {item});')
    if include_trace_helper:
        log_lines.append('// For failed action calls, inspect trace.error and print it before assert.')

    snippet = "\n".join(log_lines)
    notes = [
        "Logs emitted from Rust test code (println!/eprintln!) are visible in test stdout when using the psibase test runner.",
        "Service-side logs are not guaranteed to appear in stdout in this flow; prefer asserting returned values/trace fields from the test side.",
        "When debugging failures from push/get, print trace.error (or equivalent) before asserting.",
    ]
    print(
        json.dumps(
            {
                "ok": True,
                "tool": "add_rust_test_logging",
                "status": "ready",
                "test_name": test_name,
                "snippet": snippet,
                "notes": notes,
                "error_code": None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    from ._invoke import run_main_with_payload
    return run_main_with_payload(sys.modules[__name__], payload)


def run_with_exit_code(payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    from ._invoke import run_main_with_payload_and_exit_code
    return run_main_with_payload_and_exit_code(sys.modules[__name__], payload)
