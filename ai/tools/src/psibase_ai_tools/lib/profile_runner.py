"""Profile-driven dispatcher for build/test invocations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from psibase_ai_tools.project_profile import KindSpec, ProjectProfile, TargetSpec
from psibase_ai_tools.tool_invoke import run_tool

from . import shell_runner


@dataclass
class TargetInvocationResult:
    target_name: str
    runner: str
    ok: bool
    status: str
    summary: str
    error_code: str | None
    duration_seconds: float | None
    raw_result: dict[str, Any] = field(default_factory=dict)


@dataclass
class GroupInvocationResult:
    invocation_kind: Literal["full", "scoped_build", "scoped_test"]
    invocation_label: str
    ok: bool
    summary: str
    targets: list[TargetInvocationResult]
    primary_log_fields: dict[str, str] = field(default_factory=dict)


def _resolve_target_value(kind: KindSpec, target_value: str, workspace_root: Path) -> str:
    if kind.target_arg_kind == "path":
        p = Path(target_value)
        if not p.is_absolute():
            return str((workspace_root / p).resolve())
    return target_value


def _run_target(
    *,
    target: TargetSpec,
    profile: ProjectProfile,
    workspace_root: Path,
    payload_overrides: Mapping[str, Any] | None,
    target_arg_value: str | None = None,
) -> TargetInvocationResult:
    if target.runner == "psibase_tool":
        payload: dict[str, Any] = {
            **dict(target.defaults),
            **dict(payload_overrides or {}),
            "workspace_root": str(workspace_root),
        }
        tool_name = target.tool or ""
        code, raw = run_tool(tool_name, payload)
        ok = code == 0 and bool(raw.get("ok"))
        return TargetInvocationResult(
            target_name=target.name,
            runner=target.runner,
            ok=ok,
            status=str(raw.get("status") or ("passed" if ok else "failed")),
            summary=str(raw.get("summary") or ""),
            error_code=raw.get("error_code"),
            duration_seconds=raw.get("duration_seconds"),
            raw_result=raw,
        )

    header = f"\n===== profile_runner: {target.name} =====\n"
    raw = shell_runner.run_shell_target(
        target=target,
        workspace_root=workspace_root,
        section_header=header,
        target_arg_value=target_arg_value,
    )
    ok = bool(raw.get("ok"))
    return TargetInvocationResult(
        target_name=target.name,
        runner=target.runner,
        ok=ok,
        status=str(raw.get("status") or ("passed" if ok else "failed")),
        summary=str(raw.get("summary") or ""),
        error_code=raw.get("error_code"),
        duration_seconds=raw.get("duration_seconds"),
        raw_result=raw,
    )


def _run_kind(
    *,
    kind: KindSpec,
    profile: ProjectProfile,
    workspace_root: Path,
    target_value: str,
    payload_overrides: Mapping[str, Any] | None,
) -> TargetInvocationResult:
    resolved_value = _resolve_target_value(kind, target_value, workspace_root)
    if kind.runner == "psibase_tool":
        payload: dict[str, Any] = {
            **dict(payload_overrides or {}),
            "workspace_root": str(workspace_root),
            kind.target_arg: resolved_value,
        }
        tool_name = kind.tool or ""
        code, raw = run_tool(tool_name, payload)
        ok = code == 0 and bool(raw.get("ok"))
        return TargetInvocationResult(
            target_name=f"{kind.name}:{target_value}",
            runner=kind.runner,
            ok=ok,
            status=str(raw.get("status") or ("passed" if ok else "failed")),
            summary=str(raw.get("summary") or ""),
            error_code=raw.get("error_code"),
            duration_seconds=raw.get("duration_seconds"),
            raw_result=raw,
        )

    header = f"\n===== profile_runner: {kind.name} ({target_value}) =====\n"
    raw = shell_runner.run_shell_kind(
        kind=kind,
        workspace_root=workspace_root,
        target_value=resolved_value,
        section_header=header,
    )
    ok = bool(raw.get("ok"))
    return TargetInvocationResult(
        target_name=f"{kind.name}:{target_value}",
        runner=kind.runner,
        ok=ok,
        status=str(raw.get("status") or ("passed" if ok else "failed")),
        summary=str(raw.get("summary") or ""),
        error_code=raw.get("error_code"),
        duration_seconds=raw.get("duration_seconds"),
        raw_result=raw,
    )


def _aggregate(
    *,
    invocation_kind: Literal["full", "scoped_build", "scoped_test"],
    invocation_label: str,
    group_name: str,
    profile: ProjectProfile,
    results: list[TargetInvocationResult],
) -> GroupInvocationResult:
    ok = all(r.ok for r in results)
    target_names = ", ".join(r.target_name for r in results)
    summary = "; ".join(r.summary for r in results if r.summary) or (
        "All targets passed." if ok else "One or more targets failed."
    )
    primary_log_fields = {
        "tool": profile.full_build_event_tag if invocation_kind == "full" else results[0].target_name.split(":", 1)[0] if results else "",
        "target": target_names,
        "group": group_name,
        "status": "success" if ok else "failed",
    }
    return GroupInvocationResult(
        invocation_kind=invocation_kind,
        invocation_label=invocation_label,
        ok=ok,
        summary=summary,
        targets=results,
        primary_log_fields=primary_log_fields,
    )


def invoke_full_build(
    *,
    profile: ProjectProfile,
    workspace_root: Path,
    group_name: str | None = None,
    target_name: str | None = None,
    payload_overrides: Mapping[str, Any] | None = None,
) -> GroupInvocationResult:
    if target_name:
        if target_name not in profile.full_build_targets:
            raise ValueError(f"unknown full-build target: {target_name!r}")
        target_names = (target_name,)
        label = target_name
        group = ""
    else:
        gname = group_name or profile.full_build_default_group
        group_spec = profile.full_build_groups.get(gname)
        if group_spec is None:
            raise ValueError(f"unknown full-build group: {gname!r}")
        target_names = group_spec.target_names
        label = gname
        group = gname

    results: list[TargetInvocationResult] = []
    for tname in target_names:
        target = profile.full_build_targets[tname]
        results.append(
            _run_target(
                target=target,
                profile=profile,
                workspace_root=workspace_root,
                payload_overrides=payload_overrides,
            )
        )
        if not results[-1].ok:
            break

    return _aggregate(
        invocation_kind="full",
        invocation_label=label,
        group_name=group,
        profile=profile,
        results=results,
    )


def invoke_scoped_build(
    *,
    profile: ProjectProfile,
    workspace_root: Path,
    kind: str,
    target_value: str,
    payload_overrides: Mapping[str, Any] | None = None,
) -> GroupInvocationResult:
    kind_spec = profile.scoped_build_kinds.get(kind)
    if kind_spec is None:
        raise ValueError(f"unknown scoped build kind: {kind!r}")
    result = _run_kind(
        kind=kind_spec,
        profile=profile,
        workspace_root=workspace_root,
        target_value=target_value,
        payload_overrides=payload_overrides,
    )
    return _aggregate(
        invocation_kind="scoped_build",
        invocation_label=kind,
        group_name="",
        profile=profile,
        results=[result],
    )


def invoke_scoped_test(
    *,
    profile: ProjectProfile,
    workspace_root: Path,
    kind: str,
    target_value: str,
    payload_overrides: Mapping[str, Any] | None = None,
) -> GroupInvocationResult:
    kind_spec = profile.scoped_test_kinds.get(kind)
    if kind_spec is None:
        raise ValueError(f"unknown scoped test kind: {kind!r}")
    result = _run_kind(
        kind=kind_spec,
        profile=profile,
        workspace_root=workspace_root,
        target_value=target_value,
        payload_overrides=payload_overrides,
    )
    return GroupInvocationResult(
        invocation_kind="scoped_test",
        invocation_label=kind,
        ok=result.ok,
        summary=result.summary,
        targets=[result],
        primary_log_fields={
            "tool": kind_spec.tool or kind,
            "target": f"{kind}:{target_value}",
            "group": "",
            "status": "success" if result.ok else "failed",
        },
    )
