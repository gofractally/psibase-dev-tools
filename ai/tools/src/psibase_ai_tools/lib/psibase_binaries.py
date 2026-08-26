"""Resolve psinode / psibase executables for chain and test tools.

Precedence (first hit wins):
  1. Explicit path argument from the tool payload
  2. Environment: PSIBASE_PSINODE / PSIBASE_PSIBASE, or AI_DEV_PSINODE_PATH / AI_DEV_PSIBASE_PATH
  3. Common locations under workspace_root (CMake build tree)
  4. shutil.which on PATH
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional


def _env_path(*names: str) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v and str(v).strip():
            return str(v).strip()
    return None


def _is_executable(p: Path) -> bool:
    return p.is_file() and os.access(p, os.X_OK)


def resolve_psinode(workspace_root: Path, explicit: str | None) -> str:
    if explicit and explicit.strip():
        path = Path(explicit).expanduser()
        resolved = path.resolve() if path.is_absolute() else (workspace_root / path).resolve()
        if not _is_executable(resolved):
            raise FileNotFoundError(f"psinode not found or not executable: {resolved}")
        return str(resolved)

    hit = _env_path("PSIBASE_PSINODE", "AI_DEV_PSINODE_PATH")
    if hit:
        p = Path(hit).expanduser().resolve()
        if not _is_executable(p):
            raise FileNotFoundError(f"psinode from environment not executable: {p}")
        return str(p)

    candidates = [
        workspace_root / "build" / "psinode",
        workspace_root / "build" / "rust" / "release" / "psinode",
    ]
    for c in candidates:
        if _is_executable(c):
            return str(c)

    which = shutil.which("psinode")
    if which:
        return which

    raise FileNotFoundError(
        "Could not find psinode. Set psinode_path, PSIBASE_PSINODE, or build the psibase repo "
        f"(expected under {workspace_root / 'build'})."
    )


def resolve_psibase(workspace_root: Path, explicit: str | None) -> str:
    if explicit and explicit.strip():
        path = Path(explicit).expanduser()
        resolved = path.resolve() if path.is_absolute() else (workspace_root / path).resolve()
        if not _is_executable(resolved):
            raise FileNotFoundError(f"psibase not found or not executable: {resolved}")
        return str(resolved)

    hit = _env_path("PSIBASE_PSIBASE", "AI_DEV_PSIBASE_PATH")
    if hit:
        p = Path(hit).expanduser().resolve()
        if not _is_executable(p):
            raise FileNotFoundError(f"psibase from environment not executable: {p}")
        return str(p)

    candidates = [
        workspace_root / "build" / "rust" / "release" / "psibase",
        workspace_root / "rust" / "target" / "release" / "psibase",
    ]
    for c in candidates:
        if _is_executable(c):
            return str(c)

    which = shutil.which("psibase")
    if which:
        return which

    raise FileNotFoundError(
        "Could not find psibase. Set psibase_path, PSIBASE_PSIBASE, or build the psibase repo "
        f"(expected under {workspace_root / 'build' / 'rust' / 'release'})."
    )
