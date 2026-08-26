import argparse
import importlib
import json
import sys
from typing import Any, Dict


def parse_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
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


def main(tool_name: str, description: str = "Run ai-dev schema-backed tool.") -> int:
    module = importlib.import_module(f"psibase_ai_tools.lib.{tool_name}")
    # Delegate to the original CLI implementation preserved in psibase_ai_tools.lib.<tool>.main.
    return int(module.main())
