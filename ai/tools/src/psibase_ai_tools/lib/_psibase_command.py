#!/usr/bin/env python3
import os
import shutil
import subprocess
from typing import List, Optional, Tuple


def _probe_explicit_cargo_psibase(subcommand: str) -> Optional[List[str]]:
    """
    Look for a repo-built cargo-psibase binary in well-known psibase locations.
    This allows the tooling to work even when PATH in the tool environment
    does not include the interactive shell's additions.

    Order matters: the canonical CMake build outputs (build/rust/release,
    build/rust/debug, build/bin) must be checked before any system-install
    paths so a fresh build always wins over a stale or unrelated install.
    The legacy `rust/target/*` paths are intentionally not probed because
    they can hold months-old binaries from a direct `cargo build` and would
    silently shadow the canonical build outputs.
    """
    candidates = [
        "/root/psibase/build/rust/release/cargo-psibase",
        "/root/psibase/build/rust/debug/cargo-psibase",
        "/root/psibase/build/bin/cargo-psibase",
        "/usr/local/bin/cargo-psibase",
        "/usr/bin/cargo-psibase",
        "/root/.cargo/bin/cargo-psibase",
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return [path, subcommand]
    return None


def choose_psibase_subcommand(subcommand: str) -> Tuple[Optional[List[str]], Optional[str]]:
    """
    Select the psibase command-line prefix for a given subcommand.

    Preference order:
      1. Explicit repo-built `cargo-psibase <subcommand>` from known locations
      2. `cargo-psibase <subcommand>` discovered via PATH
      3. `cargo psibase <subcommand>` if available
    """
    explicit = _probe_explicit_cargo_psibase(subcommand)
    if explicit is not None:
        return explicit, None

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

    return None, "Neither `cargo-psibase` nor `cargo psibase` is available in PATH or in known psibase build locations."


