"""Generic shell command runner for profile-defined build/test targets."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Mapping

from psibase_ai_tools.project_profile import KindSpec, TargetSpec

from ._streaming import stream_subprocess
from .build_diagnostics import count_build_diagnostics


def _resolve_cwd(workspace_root: Path, cwd: str | None) -> str:
    if not cwd:
        return str(workspace_root)
    p = Path(cwd)
    if p.is_absolute():
        return str(p)
    return str((workspace_root / p).resolve())


def _apply_template(command: tuple[str, ...], target_value: str | None) -> list[str]:
    out: list[str] = []
    for part in command:
        if part == "{{target}}":
            out.append(target_value or "")
        else:
            out.append(part.replace("{{target}}", target_value or ""))
    return out


def _base_result(
    *,
    target_name: str,
    ok: bool,
    status: str,
    workspace_root: str,
    command_sequence: list[list[str]],
    summary: str,
    error_code: str | None,
    error_category: str | None,
    stdout: str,
    stderr: str,
    exit_code: int | None,
    duration_seconds: float | None,
) -> dict[str, Any]:
    combined = "\n".join([stdout, stderr])
    diagnostics = count_build_diagnostics(combined)
    excerpt_lines = combined.splitlines()[-20:]
    failure_excerpt = ("\n".join(excerpt_lines).strip() or None) if not ok else None
    return {
        "ok": ok,
        "tool": target_name,
        "status": status,
        "workspace_root": workspace_root,
        "command_sequence": command_sequence,
        "duration_seconds": duration_seconds,
        "parse_quality": diagnostics["parse_quality"],
        "error_count": diagnostics["error_count"],
        "warning_count": diagnostics["warning_count"],
        "error_word_hits": diagnostics["error_word_hits"],
        "warning_word_hits": diagnostics["warning_word_hits"],
        "summary": summary,
        "error_code": error_code,
        "error_category": error_category,
        "failure_excerpt": failure_excerpt,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


def run_shell_target(
    *,
    target: TargetSpec,
    workspace_root: Path,
    section_header: str,
    target_arg_value: str | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if target.command is None:
        return _base_result(
            target_name=target.name,
            ok=False,
            status="error",
            workspace_root=str(workspace_root),
            command_sequence=[],
            summary=f"Target {target.name!r} has no shell command configured.",
            error_code="invalid_target",
            error_category="profile_validation",
            stdout="",
            stderr="",
            exit_code=None,
            duration_seconds=None,
        )

    cmd = _apply_template(target.command, target_arg_value)
    cwd = _resolve_cwd(workspace_root, target.cwd)
    env = os.environ.copy()
    env.update(target.env)
    if extra_env:
        env.update(extra_env)

    start = time.monotonic()
    try:
        completed = stream_subprocess(
            cmd,
            cwd=cwd,
            env=env,
            section_header=section_header,
        )
        duration = time.monotonic() - start
        ok = completed.returncode == 0
        return _base_result(
            target_name=target.name,
            ok=ok,
            status="passed" if ok else "failed",
            workspace_root=str(workspace_root),
            command_sequence=[cmd],
            summary=f"Shell target {target.name!r} {'completed successfully' if ok else 'failed'}.",
            error_code=None if ok else "build_failed",
            error_category=None if ok else "build_execution",
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            duration_seconds=duration,
        )
    except Exception as exc:
        duration = time.monotonic() - start
        return _base_result(
            target_name=target.name,
            ok=False,
            status="error",
            workspace_root=str(workspace_root),
            command_sequence=[cmd],
            summary=f"Shell target {target.name!r} raised: {exc}",
            error_code="execution_error",
            error_category="build_execution",
            stdout="",
            stderr=str(exc),
            exit_code=None,
            duration_seconds=duration,
        )


def run_shell_kind(
    *,
    kind: KindSpec,
    workspace_root: Path,
    target_value: str,
    section_header: str,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if kind.command_template is None:
        return _base_result(
            target_name=kind.name,
            ok=False,
            status="error",
            workspace_root=str(workspace_root),
            command_sequence=[],
            summary=f"Kind {kind.name!r} has no shell command_template configured.",
            error_code="invalid_kind",
            error_category="profile_validation",
            stdout="",
            stderr="",
            exit_code=None,
            duration_seconds=None,
        )
    pseudo = TargetSpec(
        name=kind.name,
        runner="shell",
        tool=None,
        command=kind.command_template,
        cwd=None,
        env={},
        defaults={},
        timeout_seconds=None,
        glob=None,
    )
    return run_shell_target(
        target=pseudo,
        workspace_root=workspace_root,
        section_header=section_header,
        target_arg_value=target_value,
        extra_env=extra_env,
    )
