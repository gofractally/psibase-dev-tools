"""Workspace root detection for tools.lib (mirrors psibase_ai_tools.mcp.paths logic)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


def _first_mcp_workspace_root() -> str | None:
    raw = os.environ.get("MCP_WORKSPACE_ROOTS")
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        decoded = [part for part in raw.split(os.pathsep) if part]
    if isinstance(decoded, str):
        return decoded
    if isinstance(decoded, list) and decoded:
        first = decoded[0]
        if isinstance(first, str):
            return first
    return None


def detect_workspace_root(arguments: Mapping[str, Any] | None = None) -> Path:
    """Resolve the workspace root for a tool call.

    Precedence (first non-empty wins):
      1. Explicit ``workspace_root`` argument on the tool call.
      2. ``MCP_WORKSPACE_ROOTS`` env (the Psibase DX Tools extension sets
         this per window when registering the server).
      3. ``WORKSPACE_ROOT`` env (manually set by the user).
      4. CWD.

    Mirrors :func:`psibase_ai_tools.mcp.paths.detect_workspace_root`. The
    ``MCP_WORKSPACE_ROOTS`` step ranks above ``WORKSPACE_ROOT`` so one MCP
    server installation can drive multiple git worktrees / Cursor windows
    without a hardcoded ``WORKSPACE_ROOT`` overriding the per-window value.
    """
    explicit = (arguments or {}).get("workspace_root")
    root = (
        explicit
        or _first_mcp_workspace_root()
        or os.environ.get("WORKSPACE_ROOT")
        or str(Path.cwd())
    )
    return Path(str(root)).expanduser().resolve()
