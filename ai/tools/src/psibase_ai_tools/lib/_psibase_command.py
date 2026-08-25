#!/usr/bin/env python3
import os
import shutil
import subprocess
from typing import List, Optional, Tuple


def _probe_workspace_cargo_psibase(workspace_root: Optional[str], subcommand: str) -> Optional[List[str]]:
    """
    Look for a repo-built cargo-psibase binary in the workspace's canonical
    CMake build outputs. A fresh repo build always wins over any installed
    binary on PATH, so agents exercise the code they just built.

    The legacy `rust/target/*` paths are intentionally not probed because
    they can hold months-old binaries from a direct `cargo build` and would
    silently shadow the canonical build outputs.
    """
    if not workspace_root:
        return None
    candidates = [
        os.path.join(workspace_root, "build", "rust", "release", "cargo-psibase"),
        os.path.join(workspace_root, "build", "rust", "debug", "cargo-psibase"),
        os.path.join(workspace_root, "build", "bin", "cargo-psibase"),
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return [path, subcommand]
    return None


def choose_psibase_subcommand(
    subcommand: str, workspace_root: Optional[str] = None
) -> Tuple[Optional[List[str]], Optional[str]]:
    """
    Select the psibase command-line prefix for a given subcommand.

    Preference order:
      1. Repo-built `cargo-psibase <subcommand>` from the workspace build tree
      2. `cargo-psibase <subcommand>` discovered via PATH
      3. `cargo psibase <subcommand>` if available
    """
    from_workspace = _probe_workspace_cargo_psibase(workspace_root, subcommand)
    if from_workspace is not None:
        return from_workspace, None

    if shutil.which("cargo-psibase") is not None:
        return ["cargo-psibase", subcommand], None

    if shutil.which("cargo") is not None:
        probe = subprocess.run(
            ["cargo", "psibase", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        probe_text = (probe.stdout + "\n" + probe.stderr).lower()
        if "no such command: `psibase`" not in probe_text:
            return ["cargo", "psibase", subcommand], None

    return None, (
        "Neither `cargo-psibase` nor `cargo psibase` is available in PATH or in the "
        "workspace build tree (build/rust/{release,debug}, build/bin)."
    )
