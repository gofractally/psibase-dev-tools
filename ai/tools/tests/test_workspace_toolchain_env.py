from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from psibase_ai_tools.mcp.paths import GUARDS_DIR, activated_subprocess_env
from psibase_ai_tools.mcp.workspace_toolchain_env import (
    contributor_toolchain_env,
    flake_fingerprint,
    load_nix_dev_env,
    merge_env,
    missing_toolchain_bins,
    resolve_workspace_toolchain_env,
    which_real_binary,
)


def test_merge_env_prepends_path() -> None:
    merged = merge_env({"PATH": "/bin"}, {"PATH": "/opt/cargo/bin"})
    assert merged["PATH"].split(os.pathsep)[:2] == ["/opt/cargo/bin", "/bin"]


def test_contributor_env_sets_psibase_root_and_build_paths(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    build = ws / "build" / "psidk" / "bin"
    build.mkdir(parents=True)
    env = contributor_toolchain_env(ws)
    assert env["PSIBASE_ROOT"] == str(ws.resolve())
    assert str(ws / "build" / "psidk" / "bin") in env["PATH"]
    assert env["HOST_IP"] == "127.0.0.1"


def test_load_cursor_session_env(tmp_path: Path) -> None:
    ws = tmp_path / "psibase"
    ws.mkdir()
    (ws / "flake.nix").write_text("# flake", encoding="utf-8")
    fingerprint = flake_fingerprint(ws)

    cache_dir = ws / ".direnv"
    cache_dir.mkdir()
    (cache_dir / "cursor-session-env.json").write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "env": {"PATH": "/nix/store/make/bin", "IN_NIX_SHELL": "1"},
            }
        ),
        encoding="utf-8",
    )

    env = load_nix_dev_env(ws)
    assert env is not None
    assert env.get("IN_NIX_SHELL") == "1"
    assert "/nix/store/make/bin" in env["PATH"]


def test_resolve_workspace_without_flake_uses_contributor(tmp_path: Path) -> None:
    ws = tmp_path / "psibase"
    (ws / "packages").mkdir(parents=True)
    (ws / "packages" / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    env = resolve_workspace_toolchain_env(ws)
    assert env["PSIBASE_ROOT"] == str(ws.resolve())


def test_which_real_binary_skips_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_bin = tmp_path / "bin"
    real_bin.mkdir()
    make = real_bin / "make"
    make.write_text("#!/bin/sh\n", encoding="utf-8")
    make.chmod(0o755)

    guard_dir = tmp_path / "guards"
    guard_dir.mkdir()
    (guard_dir / "make").write_text("#!/bin/sh\n", encoding="utf-8")
    (guard_dir / "make").chmod(0o755)

    monkeypatch.setattr(
        "psibase_ai_tools.mcp.workspace_toolchain_env.GUARDS_DIR",
        guard_dir,
    )
    env = {"PATH": f"{guard_dir}{os.pathsep}{real_bin}"}
    assert which_real_binary("make", env) == str(make)


def test_activated_subprocess_env_merges_cursor_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "psibase"
    ws.mkdir()
    (ws / "packages" / "Cargo.toml").parent.mkdir(parents=True, exist_ok=True)
    (ws / "packages" / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    (ws / "flake.nix").write_text("# flake", encoding="utf-8")

    fingerprint = flake_fingerprint(ws)
    direnv = ws / ".direnv"
    direnv.mkdir()
    (direnv / "cursor-session-env.json").write_text(
        json.dumps({"fingerprint": fingerprint, "env": {"PATH": "/toolchain/bin"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("MCP_WORKSPACE_ROOTS", json.dumps([str(ws)]))
    monkeypatch.delenv("AI_TOOLS_WORKSPACE_ENV_FILE", raising=False)

    env = activated_subprocess_env()
    assert env["WORKSPACE_ROOT"] == str(ws.resolve())
    assert "/toolchain/bin" in env["PATH"]
    assert str(GUARDS_DIR) in env["PATH"].split(os.pathsep)[0]


def test_missing_toolchain_bins_detects_guard_shim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", f"{GUARDS_DIR}{os.pathsep}/usr/bin")
    missing = missing_toolchain_bins(["make"], os.environ)
    assert "make" in missing
