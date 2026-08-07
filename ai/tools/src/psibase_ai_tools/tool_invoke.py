"""Invoke schema-backed psibase tools (shared by `ai-tools run` and `ai-tools team`)."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFINITIONS_DIR = PACKAGE_ROOT / "definitions"
GUARDS_DIR = PACKAGE_ROOT / "guards"


def load_definition(tool_name: str) -> dict[str, Any]:
    path = DEFINITIONS_DIR / f"{tool_name}.tool.json"
    if not path.is_file():
        raise FileNotFoundError(f"Tool definition not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def available_tools() -> list[str]:
    return sorted(
        path.name.removesuffix(".tool.json")
        for path in DEFINITIONS_DIR.glob("*.tool.json")
        if path.name != "tool-definition.schema.json"
    )


def activate_tool_environment() -> None:
    os.environ["AI_DEV_TOOL_ACTIVE"] = "1"
    os.environ.setdefault("AI_DEV_TOOL_ACTIVE_BY", "ai-tools-cli")
    if GUARDS_DIR.is_dir():
        path = os.environ.get("PATH", "")
        parts = path.split(os.pathsep) if path else []
        guard = str(GUARDS_DIR)
        if guard not in parts:
            os.environ["PATH"] = guard + os.pathsep + path


def run_tool(tool_name: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    load_definition(tool_name)
    activate_tool_environment()
    module = importlib.import_module(f"psibase_ai_tools.lib.{tool_name}")
    if hasattr(module, "run_with_exit_code"):
        code, result = module.run_with_exit_code(payload)
        return int(code), result
    result = module.run(payload)
    return 0 if result.get("ok") else 1, result
