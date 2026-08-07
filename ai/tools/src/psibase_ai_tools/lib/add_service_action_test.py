#!/usr/bin/env python3
import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate psibase service action test template.")
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
    required = ["package_name", "wrapper_alias", "action_name", "test_name"]
    for field in required:
        if not isinstance(data.get(field), str) or not data[field].strip():
            return False, f"{field} is required and must be a non-empty string."
    for opt in ("setup_calls", "assertions"):
        if opt in data and (
            not isinstance(data[opt], list) or not all(isinstance(x, str) for x in data[opt])
        ):
            return False, f"{opt} must be an array of strings when provided."
    if "action_call" in data and not isinstance(data["action_call"], str):
        return False, "action_call must be a string when provided."
    return True, None


def main() -> int:
    try:
        data = read_input(parse_args())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "tool": "add_service_action_test",
                    "status": "error",
                    "test_name": "",
                    "snippet": "",
                    "line_by_line_why": [],
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
                    "tool": "add_service_action_test",
                    "status": "error",
                    "test_name": str(data.get("test_name", "")),
                    "snippet": "",
                    "line_by_line_why": [],
                    "error_code": f"invalid_input: {msg}",
                },
                indent=2,
            )
        )
        return 1

    package_name = data["package_name"].strip()
    wrapper_alias = data["wrapper_alias"].strip()
    action_name = data["action_name"].strip()
    test_name = data["test_name"].strip()
    setup_calls: List[str] = data.get("setup_calls", [])
    action_call = data.get(
        "action_call",
        f"{wrapper_alias}::push(&chain).{action_name}(/* args */).get()?;",
    )
    assertions: List[str] = data.get("assertions", ["// assert expected state/result here"])

    setup_block = "\n".join([f"    {line}" for line in setup_calls]) if setup_calls else "    // setup preconditions"
    assertion_block = "\n".join([f"    {line}" for line in assertions])

    snippet = f"""#[psibase::test_case(packages("{package_name}"))]
fn {test_name}(chain: psibase::Chain) -> Result<(), psibase::Error> {{
{setup_block}

    {action_call}

{assertion_block}
    Ok(())
}}"""

    line_by_line_why = [
        "The test_case attribute boots a simulated chain with the package(s) required by the action path.",
        "The chain parameter is the test harness context used for account setup and action pushes.",
        "Setup calls create all preconditions explicitly (accounts, balances, init actions).",
        "The Wrapper::push / push_from action call exercises the on-chain behavior under test.",
        "Assertions check observable results or table/query outcomes, not just call success.",
        "Returning Ok(()) keeps error propagation explicit via ? operators above.",
    ]

    print(
        json.dumps(
            {
                "ok": True,
                "tool": "add_service_action_test",
                "status": "ready",
                "test_name": test_name,
                "snippet": snippet,
                "line_by_line_why": line_by_line_why,
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
