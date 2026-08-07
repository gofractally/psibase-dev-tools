#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict


DEFAULT_SERVICE_URL = "http://127.0.0.1:8100"
DEFAULT_RUNNER_TOKEN = "ralph-runner-token-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve code context from local RAG service.")
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


def result_payload(
    *,
    ok: bool,
    status: str,
    query: str,
    top_k: int,
    results: Any,
    summary: str,
    error_code: str = None,
    error_category: str = None,
    index_info: Any = None,
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "tool": "rag_retrieve",
        "status": status,
        "query": query,
        "top_k": top_k,
        "results": results,
        "index_info": index_info,
        "summary": summary,
        "error_code": error_code,
        "error_category": error_category,
    }


def validate_input(data: Dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return "Input must be a JSON object."
    allowed = {"query", "top_k", "filters", "service_url", "timeout_seconds"}
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        return f"Unknown input field(s): {', '.join(unknown)}"
    query = data.get("query")
    if not isinstance(query, str) or not query.strip():
        return "query is required and must be a non-empty string."
    top_k = data.get("top_k", 8)
    if not isinstance(top_k, int) or top_k < 1 or top_k > 20:
        return "top_k must be an integer between 1 and 20."
    if "filters" in data and not isinstance(data["filters"], dict):
        return "filters must be an object when provided."
    if "service_url" in data and (not isinstance(data["service_url"], str) or not data["service_url"].strip()):
        return "service_url must be a non-empty string when provided."
    if "timeout_seconds" in data:
        timeout = data["timeout_seconds"]
        if not isinstance(timeout, (int, float)) or timeout < 0.5 or timeout > 30:
            return "timeout_seconds must be a number between 0.5 and 30."
    return ""


def main() -> int:
    args = parse_args()
    raw_query = ""
    top_k = 8

    try:
        input_data = read_input(args)
    except Exception as exc:
        print(
            json.dumps(
                result_payload(
                    ok=False,
                    status="error",
                    query=raw_query,
                    top_k=top_k,
                    results=[],
                    summary=f"Failed to parse input JSON: {exc}",
                    error_code="invalid_input",
                    error_category="input_validation",
                ),
                indent=2,
            )
        )
        return 1

    raw_query = str(input_data.get("query", ""))
    maybe_top_k = input_data.get("top_k", 8)
    top_k = int(maybe_top_k) if isinstance(maybe_top_k, int) else 8

    validation_error = validate_input(input_data)
    if validation_error:
        print(
            json.dumps(
                result_payload(
                    ok=False,
                    status="error",
                    query=raw_query,
                    top_k=top_k,
                    results=[],
                    summary=validation_error,
                    error_code="invalid_input",
                    error_category="input_validation",
                ),
                indent=2,
            )
        )
        return 1

    query = input_data["query"].strip()
    top_k = input_data.get("top_k", 8)
    filters = input_data.get("filters", {})
    service_url = input_data.get("service_url", DEFAULT_SERVICE_URL).rstrip("/")
    timeout_seconds = float(input_data.get("timeout_seconds", 8))

    request_payload = {
        "query": query,
        "top_k": top_k,
        "filters": filters,
    }
    body = json.dumps(request_payload).encode("utf-8")
    request = urllib.request.Request(
        f"{service_url}/retrieve",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Ralph-Runner-Token": os.getenv("RALPH_RAG_RUNNER_TOKEN", DEFAULT_RUNNER_TOKEN),
        },
        method="POST",
    )

    # NOTE: tool intentionally degrades gracefully when local RAG service is unavailable.
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw.strip() else {}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        print(
            json.dumps(
                result_payload(
                    ok=True,
                    status="degraded",
                    query=query,
                    top_k=top_k,
                    results=[],
                    summary=f"RAG service unavailable at {service_url}; continuing without RAG context ({exc}).",
                    error_code="service_unavailable",
                    error_category="network",
                ),
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                result_payload(
                    ok=True,
                    status="degraded",
                    query=query,
                    top_k=top_k,
                    results=[],
                    summary=f"Unexpected retrieval failure; continuing without RAG context ({exc}).",
                    error_code="service_unavailable",
                    error_category="runtime",
                ),
                indent=2,
            )
        )
        return 0

    service_status = str(payload.get("status", "error"))
    if service_status == "ok":
        results = payload.get("results", []) if isinstance(payload.get("results"), list) else []
        print(
            json.dumps(
                result_payload(
                    ok=True,
                    status="passed",
                    query=query,
                    top_k=top_k,
                    results=results,
                    index_info=payload.get("index_info"),
                    summary=f"Returned {len(results)} retrieval result(s) from local RAG service.",
                ),
                indent=2,
            )
        )
        return 0

    if service_status == "not_indexed":
        print(
            json.dumps(
                result_payload(
                    ok=True,
                    status="degraded",
                    query=query,
                    top_k=top_k,
                    results=[],
                    index_info=payload.get("index_info"),
                    summary=payload.get(
                        "message",
                        "RAG service reachable but index is missing; continuing without RAG context.",
                    ),
                    error_code="service_unavailable",
                    error_category="index_state",
                ),
                indent=2,
            )
        )
        return 0

    print(
        json.dumps(
            result_payload(
                ok=True,
                status="degraded",
                query=query,
                top_k=top_k,
                results=[],
                index_info=payload.get("index_info") if isinstance(payload, dict) else None,
                summary=payload.get("message", "RAG service returned an error response; continuing without RAG context.")
                if isinstance(payload, dict)
                else "RAG service returned an invalid response; continuing without RAG context.",
                error_code="service_error",
                error_category="runtime",
            ),
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
