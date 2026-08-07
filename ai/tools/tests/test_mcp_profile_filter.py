from __future__ import annotations

from psibase_ai_tools.mcp.server import tool_specs
from psibase_ai_tools.project_profile import packaged_default_profile


def test_psibase_profile_registers_chain_and_knowledge() -> None:
    profile = packaged_default_profile()
    names = {t.name for t in tool_specs(profile)}
    assert "start_full_build" in names
    assert "launch_chain" in names
    assert "add_graphql_test" in names


def test_minimal_profile_filters_chain_tools() -> None:
    raw = dict(packaged_default_profile().raw)
    raw["mcp_server"] = {"name": "minimal-mcp", "tools": {"enabled": ["build", "test"]}}
    from psibase_ai_tools.project_profile import parse_profile

    profile = parse_profile(raw)
    names = {t.name for t in tool_specs(profile)}
    assert "start_full_build" in names
    assert "launch_chain" not in names
    assert "lookup" not in names
