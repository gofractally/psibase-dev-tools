#!/usr/bin/env python3
import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate psibase GraphQL test template.")
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
    required = ["package_name", "test_name", "graphql_query_name", "graphql_query_body"]
    for field in required:
        if not isinstance(data.get(field), str) or not data[field].strip():
            return False, f"{field} is required and must be a non-empty string."
    for opt in ("seed_calls", "result_assertions"):
        if opt in data and (
            not isinstance(data[opt], list) or not all(isinstance(x, str) for x in data[opt])
        ):
            return False, f"{opt} must be an array of strings when provided."
    if "graphql_service_constant" in data and not isinstance(data["graphql_service_constant"], str):
        return False, "graphql_service_constant must be a string when provided."
    return True, None


def main() -> int:
    try:
        data = read_input(parse_args())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "tool": "add_graphql_test",
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
                    "tool": "add_graphql_test",
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
    test_name = data["test_name"].strip()
    query_name = data["graphql_query_name"].strip()
    query_body = data["graphql_query_body"].strip()
    service_constant = data.get("graphql_service_constant", "Wrapper::SERVICE")
    seed_calls: List[str] = data.get("seed_calls", [])
    result_assertions: List[str] = data.get("result_assertions", ["// assert GraphQL response fields here"])

    seed_block = "\n".join([f"    {line}" for line in seed_calls]) if seed_calls else "    // seed state via actions"
    assertion_block = "\n".join([f"    {line}" for line in result_assertions])

    snippet = f"""#[derive(serde::Deserialize)]
struct GraphQlResponse<T> {{
    data: T,
}}

#[derive(serde::Deserialize)]
struct {query_name}Data {{
    // fill to match GraphQL shape
}}

#[psibase::test_case(packages("{package_name}"))]
fn {test_name}(chain: psibase::Chain) -> Result<(), psibase::Error> {{
{seed_block}

    let value: serde_json::Value = chain.graphql(
        {service_constant},
        r#"{query_body}"#,
    )?;
    let response: GraphQlResponse<{query_name}Data> = serde_json::from_value(value)?;

{assertion_block}
    Ok(())
}}"""

    line_by_line_why = [
        "The response wrapper struct mirrors GraphQL's top-level { data: ... } envelope.",
        "The query-specific data struct should match only fields asserted in the test.",
        "The test_case attribute ensures package deployment on the simulated chain.",
        "Seed calls must use normal actions so GraphQL reflects real on-chain state transitions.",
        "chain.graphql(...) exercises the query-service endpoint behavior under auth/context rules.",
        "serde_json::from_value gives strongly typed assertions on returned data.",
    ]

    print(
        json.dumps(
            {
                "ok": True,
                "tool": "add_graphql_test",
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
