#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


WORD_RE = re.compile(r"[a-z0-9_]+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lookup psibase knowledge snippets.")
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


def tokenize(text: str) -> List[str]:
    return WORD_RE.findall(text.lower())


def validate_input(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(data, dict):
        return False, "Input must be a JSON object."
    allowed = {"query", "top_k"}
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        return False, f"Unknown input field(s): {', '.join(unknown)}"
    query = data.get("query")
    if not isinstance(query, str) or not query.strip():
        return False, "query is required and must be a non-empty string."
    top_k = data.get("top_k", 3)
    if not isinstance(top_k, int) or top_k < 1 or top_k > 10:
        return False, "top_k must be an integer between 1 and 10."
    return True, None


def result_error(
    *,
    query: str,
    top_k: int,
    error_code: str,
    error_category: str,
    summary: str,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "tool": "lookup",
        "status": "error",
        "query": query,
        "top_k": top_k,
        "matches": [],
        "summary": summary,
        "error_code": error_code,
        "error_category": error_category,
    }


def load_index(index_path: str) -> Dict[str, Any]:
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_index(index: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    snippets = index.get("snippets")
    if not isinstance(snippets, list):
        return False, "index.json must contain a snippets array."
    for i, item in enumerate(snippets):
        if not isinstance(item, dict):
            return False, f"snippets[{i}] must be an object."
        if not isinstance(item.get("file"), str) or not item["file"].strip():
            return False, f"snippets[{i}].file must be a non-empty string."
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            return False, f"snippets[{i}].title must be a non-empty string."
        tags = item.get("tags")
        if not isinstance(tags, list) or not all(isinstance(x, str) and x.strip() for x in tags):
            return False, f"snippets[{i}].tags must be a non-empty string array."
    return True, None


def score_snippet(query_tokens: List[str], title: str, tags: List[str], file_name: str) -> int:
    haystack_tokens = set(tokenize(" ".join([title, " ".join(tags), file_name])))
    score = 0
    for token in query_tokens:
        if token in haystack_tokens:
            score += 3
            continue
        if any(token in ht for ht in haystack_tokens):
            score += 1
    return score


def main() -> int:
    args = parse_args()
    raw_query = ""
    top_k = 3

    try:
        input_data = read_input(args)
    except Exception as exc:
        print(
            json.dumps(
                result_error(
                    query=raw_query,
                    top_k=top_k,
                    error_code="invalid_input",
                    error_category="input_validation",
                    summary=f"Failed to parse input JSON: {exc}",
                ),
                indent=2,
            )
        )
        return 1

    raw_query = str(input_data.get("query", ""))
    top_k = int(input_data.get("top_k", 3)) if isinstance(input_data.get("top_k", 3), int) else 3
    valid, message = validate_input(input_data)
    if not valid:
        print(
            json.dumps(
                result_error(
                    query=raw_query,
                    top_k=top_k,
                    error_code="invalid_input",
                    error_category="input_validation",
                    summary=message or "Invalid input.",
                ),
                indent=2,
            )
        )
        return 1

    query = input_data["query"].strip()
    top_k = input_data.get("top_k", 3)
    query_tokens = tokenize(query)

    # Same root and env override as mcp.resources: <ai-tools root>/knowledge,
    # where the ai-tools root is two levels above the package (src/.. = ai/tools).
    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools_root = os.path.normpath(os.path.join(package_root, "..", ".."))
    knowledge_dir = os.environ.get("AI_TOOLS_KNOWLEDGE_DIR") or os.path.join(tools_root, "knowledge")
    index_path = os.path.join(knowledge_dir, "index.json")

    if not os.path.isfile(index_path):
        print(
            json.dumps(
                result_error(
                    query=query,
                    top_k=top_k,
                    error_code="knowledge_index_missing",
                    error_category="filesystem",
                    summary=f"Knowledge index not found: {index_path}",
                ),
                indent=2,
            )
        )
        return 1

    try:
        index = load_index(index_path)
    except Exception as exc:
        print(
            json.dumps(
                result_error(
                    query=query,
                    top_k=top_k,
                    error_code="knowledge_index_missing",
                    error_category="filesystem",
                    summary=f"Unable to read knowledge index: {exc}",
                ),
                indent=2,
            )
        )
        return 1

    index_valid, index_message = validate_index(index)
    if not index_valid:
        print(
            json.dumps(
                result_error(
                    query=query,
                    top_k=top_k,
                    error_code="invalid_index",
                    error_category="input_validation",
                    summary=index_message or "Knowledge index is invalid.",
                ),
                indent=2,
            )
        )
        return 1

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for snippet in index["snippets"]:
        score = score_snippet(
            query_tokens=query_tokens,
            title=snippet["title"],
            tags=snippet["tags"],
            file_name=snippet["file"],
        )
        if score > 0:
            scored.append((score, snippet))

    scored.sort(key=lambda x: (-x[0], x[1]["title"]))
    selected = scored[:top_k]
    matches: List[Dict[str, Any]] = []

    for score, snippet in selected:
        snippet_path = os.path.join(knowledge_dir, snippet["file"])
        try:
            with open(snippet_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except Exception as exc:
            print(
                json.dumps(
                    result_error(
                        query=query,
                        top_k=top_k,
                        error_code="snippet_read_failed",
                        error_category="filesystem",
                        summary=f"Unable to read snippet {snippet['file']}: {exc}",
                    ),
                    indent=2,
                )
            )
            return 1

        matches.append(
            {
                "file": snippet["file"],
                "title": snippet["title"],
                "tags": snippet["tags"],
                "score": score,
                "content": content,
            }
        )

    if matches:
        summary = f"Returned {len(matches)} snippet(s) for query: {query}"
    else:
        summary = (
            f"No matching snippets found for query: {query}. "
            "Try broader keywords (for example: test_case, graphql, packages, init)."
        )

    result = {
        "ok": True,
        "tool": "lookup",
        "status": "passed",
        "query": query,
        "top_k": top_k,
        "matches": matches,
        "summary": summary,
        "error_code": None,
        "error_category": None,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    from ._invoke import run_main_with_payload
    return run_main_with_payload(sys.modules[__name__], payload)


def run_with_exit_code(payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    from ._invoke import run_main_with_payload_and_exit_code
    return run_main_with_payload_and_exit_code(sys.modules[__name__], payload)
