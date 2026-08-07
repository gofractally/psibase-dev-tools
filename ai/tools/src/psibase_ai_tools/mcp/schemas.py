import json
from pathlib import Path
from typing import Any

from .paths import TOOL_DEFINITIONS_DIR


EXCLUDED_MCP_TOOLS = {"lookup", "rag_retrieve"}


def load_definition(tool_name: str) -> dict[str, Any]:
    path = TOOL_DEFINITIONS_DIR / f"{tool_name}.tool.json"
    return json.loads(path.read_text(encoding="utf-8"))


def iter_definitions() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for path in sorted(Path(TOOL_DEFINITIONS_DIR).glob("*.tool.json")):
        if path.name == "tool-definition.schema.json":
            continue
        definition = json.loads(path.read_text(encoding="utf-8"))
        if definition.get("name") not in EXCLUDED_MCP_TOOLS:
            definitions.append(definition)
    return definitions


def description_for(definition: dict[str, Any], *, mcp_name: str, extra: str = "") -> str:
    description = definition.get("description", "").rstrip(".")
    version = definition.get("version", "0.0.0")
    parts = [description]
    if extra:
        parts.append(extra.strip())
    parts.append(f"Use MCP tool `{mcp_name}` with the schema below. (v{version})")
    return " ".join(part for part in parts if part)


def input_schema(tool_name: str) -> dict[str, Any]:
    return dict(load_definition(tool_name).get("inputSchema", {"type": "object"}))
