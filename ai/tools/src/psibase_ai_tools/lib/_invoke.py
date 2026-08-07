import contextlib
import io
import json
from types import SimpleNamespace
from typing import Any, Dict, Tuple


def run_main_with_payload(module: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    _code, result = run_main_with_payload_and_exit_code(module, payload)
    return result


def run_main_with_payload_and_exit_code(module: Any, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    old_read_input = getattr(module, "read_input", None)
    old_parse_args = getattr(module, "parse_args", None)

    def read_input(_args: Any) -> Dict[str, Any]:
        return payload

    def parse_args() -> SimpleNamespace:
        return SimpleNamespace(input_file=None, input_json=None)

    module.read_input = read_input
    module.parse_args = parse_args
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            code = int(module.main())
    finally:
        if old_read_input is not None:
            module.read_input = old_read_input
        if old_parse_args is not None:
            module.parse_args = old_parse_args

    raw = stdout.getvalue().strip()
    if not raw:
        return code, {"ok": code == 0, "error": "Tool produced no JSON output."}
    try:
        return code, json.loads(raw)
    except json.JSONDecodeError as exc:
        return code or 1, {
            "ok": False,
            "error": "Tool output was not valid JSON.",
            "parse_error": str(exc),
            "raw_output": raw,
        }
