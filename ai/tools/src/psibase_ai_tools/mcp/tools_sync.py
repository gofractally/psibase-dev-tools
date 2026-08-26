import importlib
from typing import Any

from .paths import normalize_arguments


SYNC_TOOLS = {
    "add_rust_test_logging": "psibase_ai_tools.lib.add_rust_test_logging",
    "add_service_action_test": "psibase_ai_tools.lib.add_service_action_test",
    "add_graphql_test": "psibase_ai_tools.lib.add_graphql_test",
    "boot_chain": "psibase_ai_tools.lib.boot_chain",
}


def call_sync_tool(tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    from .paths import ensure_ai_tools_importable

    ensure_ai_tools_importable()
    normalized = normalize_arguments(arguments, add_workspace_root=True, enforce_host_scope=True)
    module_name = SYNC_TOOLS[tool_name]
    module = importlib.import_module(module_name)
    return module.run(normalized)
