import argparse
import json
import select
import sys
from pathlib import Path
from typing import Any

from psibase_ai_tools.tool_invoke import available_tools, run_tool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ai-tools", description="Run psibase schema-backed tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run a schema-backed tool by name.")
    run.add_argument("tool_name", help="Tool name, e.g. run_service_tests")
    run.add_argument("--input-file", help="Path to JSON input")
    run.add_argument("--input-json", help="Inline JSON input")

    subparsers.add_parser("list", help="List available tool names.")
    return parser.parse_args()


def load_input(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "input_file", None):
        return json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    if getattr(args, "input_json", None):
        return json.loads(args.input_json)
    if not sys.stdin.isatty():
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return {}
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}
        return json.loads(raw)
    return {}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "team":
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "agent-team CLI is not included in this package yet",
                    "error_code": "team_not_packaged",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    args = parse_args()
    if args.command == "list":
        print(json.dumps({"ok": True, "tools": available_tools()}, indent=2))
        return 0

    payload = load_input(args)
    try:
        code, result = run_tool(args.tool_name, payload)
    except Exception as exc:  # pragma: no cover - exercised via tests with bad tool names
        code = 1
        result = {"ok": False, "tool": args.tool_name, "error": str(exc)}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
