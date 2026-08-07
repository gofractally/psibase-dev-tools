import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
AI_TOOLS_ROOT = PACKAGE_ROOT.parents[1]
TOOL_DEFINITIONS_DIR = PACKAGE_ROOT / "definitions"
DEFAULT_WORKSPACE_ROOT = Path("/root/psibase")
GUARDS_DIR = PACKAGE_ROOT / "guards"


def ensure_ai_tools_importable() -> None:
    root = str(PACKAGE_ROOT.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


def state_dir() -> Path:
    return Path(
        os.environ.get(
            "AI_TOOLS_STATE_DIR",
            os.environ.get("AI_DEV_STATE_DIR", str(AI_TOOLS_ROOT / "state")),
        )
    )


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


def _host_workspace_root() -> Path:
    """Workspace from host env / cwd only — ignores caller ``workspace_root``."""
    root = _first_mcp_workspace_root() or os.environ.get("WORKSPACE_ROOT")
    if not root:
        cwd = Path.cwd()
        root = str(cwd if cwd.exists() else DEFAULT_WORKSPACE_ROOT)
    return Path(str(root)).expanduser().resolve()


def detect_workspace_root(arguments: Mapping[str, Any] | None = None) -> Path:
    """Resolve the workspace root for a tool call.

    Precedence (first non-empty wins):
      1. Explicit ``workspace_root`` argument on the tool call.
      2. ``MCP_WORKSPACE_ROOTS`` env (Cursor sets this per window). This is
         above ``WORKSPACE_ROOT`` so a per-window setting from the host beats
         a stale process env, which is what makes one MCP server safe to run
         across multiple git worktrees / Cursor windows.
      3. ``WORKSPACE_ROOT`` env (manually set by the user).
      4. CWD where the server was launched.
      5. Built-in default (``/root/psibase``).
    """
    explicit = (arguments or {}).get("workspace_root")
    root = (
        explicit
        or _first_mcp_workspace_root()
        or os.environ.get("WORKSPACE_ROOT")
    )
    if not root:
        cwd = Path.cwd()
        root = str(cwd if cwd.exists() else DEFAULT_WORKSPACE_ROOT)
    return Path(str(root)).expanduser().resolve()


def enforce_host_workspace(arguments: Mapping[str, Any] | None) -> Path:
    """Defense-in-depth: bind tool calls to the host workspace, rejecting overrides.

    When ``MCP_WORKSPACE_ROOTS`` or ``WORKSPACE_ROOT`` is set, an explicit
    ``workspace_root`` on the tool call that disagrees with the host workspace
    is refused so parallel worktrees cannot be targeted by mistake.
    """
    host = _host_workspace_root()
    explicit = (arguments or {}).get("workspace_root")
    if explicit:
        try:
            explicit_path = Path(str(explicit)).expanduser().resolve()
        except OSError as exc:
            raise ValueError(f"invalid workspace_root: {explicit!r}") from exc
        if explicit_path != host:
            raise ValueError(
                f"workspace_root mismatch: caller sent {explicit_path} but host workspace is {host}"
            )
    return host


def resolve_inside_workspace(path_value: str, workspace_root: Path) -> str:
    path = Path(path_value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (workspace_root / path).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(f"Path is outside workspace_root: {resolved}") from exc
    return str(resolved)


def normalize_arguments(
    arguments: Mapping[str, Any] | None,
    *,
    path_fields: Iterable[str] = (),
    add_workspace_root: bool = True,
    enforce_host_scope: bool = True,
) -> dict[str, Any]:
    normalized = dict(arguments or {})
    if enforce_host_scope and (_first_mcp_workspace_root() or os.environ.get("WORKSPACE_ROOT")):
        workspace_root = enforce_host_workspace(normalized)
    else:
        workspace_root = detect_workspace_root(normalized)
    if add_workspace_root:
        normalized["workspace_root"] = str(workspace_root)
    for field in path_fields:
        value = normalized.get(field)
        if isinstance(value, str) and value:
            normalized[field] = resolve_inside_workspace(value, workspace_root)
    return normalized


def activated_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    env["AI_DEV_TOOL_ACTIVE"] = "1"
    env["AI_DEV_TOOL_ACTIVE_BY"] = "mcp"
    if GUARDS_DIR.is_dir():
        env["PATH"] = str(GUARDS_DIR) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(PACKAGE_ROOT.parent) + os.pathsep + env.get("PYTHONPATH", "")
    return env
