import json
from typing import Any

from .paths import TOOL_DEFINITIONS_DIR


def load_definition(tool_name: str) -> dict[str, Any]:
    path = TOOL_DEFINITIONS_DIR / f"{tool_name}.tool.json"
    return json.loads(path.read_text(encoding="utf-8"))


def description_for(definition: dict[str, Any], *, mcp_name: str, extra: str = "") -> str:
    description = definition.get("description", "").rstrip(".")
    version = definition.get("version", "0.0.0")
    parts = [description]
    if extra:
        parts.append(extra.strip())
    parts.append(f"Use MCP tool `{mcp_name}` with the schema below. (v{version})")
    return " ".join(part for part in parts if part)
