"""MCP library: start psinode on existing db (continue block production)."""

from __future__ import annotations

from typing import Any, Dict

from psibase_ai_tools.lib.chain_psinode import run_psinode_session


def run_with_exit_code(payload: Dict[str, Any]) -> tuple[int, dict[str, Any]]:
    return run_psinode_session(payload, wipe_db=False)
