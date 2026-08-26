"""Resolve psibase workspace build toolchain environment for MCP job subprocesses.

Agent shells in Cursor can receive Nix devShell variables via ``.cursor/hooks``,
but MCP jobs are spawned from the extension host with a sparse environment.
This module bridges that gap for:

* **Nix flakes** — reuse ``.direnv/cursor-session-env.json`` (written by the
  psibase repo hook) or evaluate ``nix print-dev-env`` with caching under
  ``AI_TOOLS_STATE_DIR``.
* **psibase-contributor Docker** — prepend standard container paths
  (``/opt/cargo/bin``, workspace ``build/`` outputs, etc.) when no flake env
  is available.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Mapping

from .paths import GUARDS_DIR, state_dir


_SKIP_ENV_KEY = re.compile(
    r"^(_|SHLVL|OLDPWD|PWD|SHELLOPTS|BASHOPTS|PPID|UID|EUID|COLUMNS|LINES|TERM|"
    r"TERMINFO|COLORTERM|SSH_AUTH_SOCK|SSH_AGENT_PID|DISPLAY|WAYLAND_DISPLAY|"
    r"XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|CURSOR_AGENT|CI|BASH_FUNC_.*|"
    r"shellHook|buildPhase|phases|builder|stdenv|outputs|out|name|system|shell|"
    r"preferLocalBuild|strictDeps|doCheck|doInstallCheck|dontAddDisableDepTrack|"
    r"__structuredAttrs|propagatedBuildInputs|propagatedNativeBuildInputs|"
    r"nativeBuildInputs|buildInputs|depsBuildBuild|depsBuildBuildPropagated|"
    r"depsBuildTarget|depsBuildTargetPropagated|depsHostHost|depsHostHostPropagated|"
    r"depsTargetTarget|depsTargetTargetPropagated|cmakeFlags|configureFlags|"
    r"mesonFlags|patches|TEMP|TMP|TEMPDIR|NIX_BUILD_TOP|NIX_BUILD_CORES|"
    r"SOURCE_DATE_EPOCH|DETERMINISTIC_BUILD|PYTHONHASHSEED|_PYTHON_HOST_PLATFORM|"
    r"_PYTHON_SYSCONFIGDATA_NAME|NIX_ENFORCE_NO_NATIVE|NIX_STORE|DIRENV_DIFF|"
    r"DIRENV_WATCHES|buildPhase)$"
)

_CONTRIBUTOR_PATH_DIRS = (
    "/opt/cargo/bin",
    "/usr/local/bin",
    "/usr/bin",
)


def flake_fingerprint(workspace_root: Path) -> str:
    parts: list[str] = []
    for name in ("flake.nix", "flake.lock"):
        path = workspace_root / name
        if path.is_file():
            stat = path.stat()
            parts.append(f"{name}:{int(stat.st_mtime)}:{stat.st_size}")
    return "|".join(parts)


def _filter_env(raw: Mapping[str, object]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if _SKIP_ENV_KEY.match(key):
            continue
        filtered[key] = value
    return filtered


def _merge_path(existing: str, extra: str) -> str:
    seen: set[str] = set()
    parts: list[str] = []
    for segment in (extra + os.pathsep + existing).split(os.pathsep):
        if not segment or segment in seen:
            continue
        seen.add(segment)
        parts.append(segment)
    return os.pathsep.join(parts)


def merge_env(base: Mapping[str, str], overlay: Mapping[str, str]) -> dict[str, str]:
    merged = dict(base)
    for key, value in overlay.items():
        if key == "PATH":
            merged["PATH"] = _merge_path(merged.get("PATH", ""), value)
        else:
            merged[key] = value
    return merged


def _workspace_output_path_env(workspace_root: Path) -> dict[str, str]:
    """Paths for locally built psibase binaries (shared by Nix shellHook and Docker)."""
    prefixes: list[str] = []
    for relative in ("build/psidk/bin", "build/rust/release", "build"):
        path = workspace_root / relative
        if path.is_dir():
            prefixes.append(str(path))
    if not prefixes:
        return {}
    return {"PATH": os.pathsep.join(prefixes)}


def contributor_toolchain_env(workspace_root: Path) -> dict[str, str]:
    """Toolchain env for psibase-contributor-style containers without Nix."""
    env: dict[str, str] = {
        "PSIBASE_ROOT": str(workspace_root),
        "HOST_IP": os.environ.get("HOST_IP", "127.0.0.1"),
    }
    if "RUSTC_WRAPPER" not in os.environ:
        env["RUSTC_WRAPPER"] = "sccache"

    path_parts = list(_workspace_output_path_env(workspace_root).get("PATH", "").split(os.pathsep))
    for directory in _CONTRIBUTOR_PATH_DIRS:
        if Path(directory).is_dir():
            path_parts.append(directory)
    path_parts = [part for part in path_parts if part]
    if path_parts:
        env["PATH"] = os.pathsep.join(path_parts)
    return env


def _cursor_session_env_path(workspace_root: Path) -> Path:
    return workspace_root / ".direnv" / "cursor-session-env.json"


def _load_json_env_file(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    env = payload.get("env") if isinstance(payload, dict) else None
    if not isinstance(env, dict):
        return None
    return _filter_env(env)


def _load_cursor_session_env(workspace_root: Path, fingerprint: str) -> dict[str, str] | None:
    path = _cursor_session_env_path(workspace_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("fingerprint") != fingerprint:
        return None
    env = payload.get("env")
    if not isinstance(env, dict):
        return None
    return _filter_env(env)


def _toolchain_cache_path(workspace_root: Path) -> Path:
    digest = hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest()[:12]
    return state_dir() / "workspace-toolchain" / digest / "env.json"


def _load_toolchain_cache(workspace_root: Path, fingerprint: str) -> dict[str, str] | None:
    path = _toolchain_cache_path(workspace_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("fingerprint") != fingerprint:
        return None
    env = payload.get("env")
    if not isinstance(env, dict):
        return None
    return _filter_env(env)


def _save_toolchain_cache(
    workspace_root: Path,
    fingerprint: str,
    source: str,
    env: Mapping[str, str],
) -> None:
    path = _toolchain_cache_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fingerprint": fingerprint, "source": source, "env": dict(env)}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _collect_via_nix_print_dev_env(workspace_root: Path) -> dict[str, str] | None:
    if shutil.which("nix") is None:
        return None
    try:
        proc = subprocess.run(
            ["nix", "print-dev-env"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    script = proc.stdout
    bash = shutil.which("bash") or "/bin/bash"
    try:
        env_json = subprocess.run(
            [
                bash,
                "--noprofile",
                "--norc",
                "-c",
                "set -euo pipefail\n"
                "exec 3>&1\n"
                "exec 1>/dev/null\n"
                "source /dev/stdin\n"
                "exec 1>&3\n"
                "python3 -c 'import json, os; print(json.dumps(dict(os.environ)))'",
            ],
            input=script,
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if env_json.returncode != 0 or not env_json.stdout.strip():
        return None
    try:
        decoded = json.loads(env_json.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    return _filter_env(decoded)


def load_nix_dev_env(workspace_root: Path) -> dict[str, str] | None:
    """Load Nix devShell env for a flake workspace, or None when unavailable."""
    if not (workspace_root / "flake.nix").is_file():
        return None

    fingerprint = flake_fingerprint(workspace_root)
    if not fingerprint:
        return None

    for loader, source in (
        (lambda: _load_cursor_session_env(workspace_root, fingerprint), "cursor-session"),
        (lambda: _load_toolchain_cache(workspace_root, fingerprint), "cache"),
        (lambda: _collect_via_nix_print_dev_env(workspace_root), "nix-print-dev-env"),
    ):
        env = loader()
        if env:
            if source == "nix-print-dev-env":
                _save_toolchain_cache(workspace_root, fingerprint, source, env)
            return env
    return None


def resolve_workspace_toolchain_env(workspace_root: Path) -> dict[str, str]:
    """Build toolchain env overlays for MCP-managed subprocesses."""
    workspace_root = workspace_root.expanduser().resolve()

    override_file = os.environ.get("AI_TOOLS_WORKSPACE_ENV_FILE")
    if override_file:
        override = _load_json_env_file(Path(override_file))
        if override:
            return merge_env(_workspace_output_path_env(workspace_root), override)

    merged = _workspace_output_path_env(workspace_root)
    nix_env = load_nix_dev_env(workspace_root)
    if nix_env:
        merged = merge_env(merged, nix_env)
    else:
        merged = merge_env(merged, contributor_toolchain_env(workspace_root))
    return merged


def which_real_binary(name: str, env: Mapping[str, str] | None = None) -> str | None:
    """Locate a real executable, ignoring guard shims prepended to PATH."""
    environment = dict(os.environ if env is None else env)
    guard_dir = str(GUARDS_DIR.resolve())
    for segment in environment.get("PATH", "").split(os.pathsep):
        if not segment:
            continue
        try:
            if Path(segment).resolve() == Path(guard_dir):
                continue
        except OSError:
            if segment == guard_dir:
                continue
        candidate = Path(segment) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def missing_toolchain_bins(names: list[str], env: Mapping[str, str] | None = None) -> list[str]:
    return [name for name in names if which_real_binary(name, env) is None]


__all__ = [
    "contributor_toolchain_env",
    "flake_fingerprint",
    "load_nix_dev_env",
    "merge_env",
    "missing_toolchain_bins",
    "resolve_workspace_toolchain_env",
    "which_real_binary",
]
