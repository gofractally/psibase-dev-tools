"""Load and validate ``.agent-team/project-profile.yaml``.

The packaged default (psibase shape) lives at ``data/project-profile.yaml``.
When a worktree has ``.agent-team/project-profile.yaml``, that file wins;
otherwise the packaged default is used. ``ensure_project_profile_file`` merges
missing top-level keys on upgrade without clobbering user-owned target/group
definitions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Mapping

import yaml

from psibase_ai_tools.tool_invoke import available_tools
from psibase_ai_tools.yamlutil import load_yaml

PACKAGED_PROFILE_FILENAME = "project-profile.yaml"
MCP_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
VALID_MCP_FAMILIES = frozenset({"build", "test", "chain", "knowledge"})
VALID_RUNNERS = frozenset({"shell", "psibase_tool"})
VALID_TARGET_ARG_KINDS = frozenset({"string", "path"})


@dataclass(frozen=True)
class TargetSpec:
    name: str
    runner: Literal["shell", "psibase_tool"]
    tool: str | None
    command: tuple[str, ...] | None
    cwd: str | None
    env: Mapping[str, str]
    defaults: Mapping[str, Any]
    timeout_seconds: int | None
    glob: str | None


@dataclass(frozen=True)
class GroupSpec:
    name: str
    target_names: tuple[str, ...]
    dispatch_raw: Mapping[str, Any] | None


@dataclass(frozen=True)
class KindSpec:
    name: str
    runner: Literal["shell", "psibase_tool"]
    tool: str | None
    command_template: tuple[str, ...] | None
    target_arg: str
    target_arg_kind: Literal["string", "path"]


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    grants_invoke_of_groups: tuple[str, ...]
    grants_invoke_of_kinds: tuple[str, ...]
    grants_mcp_tools: tuple[str, ...]


@dataclass(frozen=True)
class ProjectProfile:
    schema: int
    profile_name: str
    mcp_server_name: str
    mcp_tool_families_enabled: frozenset[str]
    full_build_targets: Mapping[str, TargetSpec]
    full_build_groups: Mapping[str, GroupSpec]
    full_build_default_group: str
    scoped_build_kinds: Mapping[str, KindSpec]
    scoped_test_kinds: Mapping[str, KindSpec]
    full_build_event_tag: str
    require_full_build_before_review: bool
    required_full_build_group: str
    build_czar_required: bool
    capabilities: Mapping[str, CapabilitySpec]
    raw: Mapping[str, Any] = field(default_factory=dict)


class ProjectProfileError(Exception):
    error_code: str
    error_category: str = "profile_validation"

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _packaged_default_path() -> resources.abc.Traversable:
    return resources.files("psibase_ai_tools.data").joinpath(PACKAGED_PROFILE_FILENAME)


def packaged_default_text() -> str:
    return _packaged_default_path().read_text(encoding="utf-8")


def packaged_default_profile() -> ProjectProfile:
    data = yaml.safe_load(packaged_default_text())
    if not isinstance(data, dict):
        raise ProjectProfileError("packaged default profile is not a mapping", error_code="invalid_default")
    return parse_profile(data)


def profile_path_for(worktree: Path) -> Path:
    return worktree.resolve() / ".agent-team" / PACKAGED_PROFILE_FILENAME


def load_profile(worktree: Path) -> ProjectProfile:
    path = profile_path_for(worktree)
    if not path.is_file():
        return packaged_default_profile()
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ProjectProfileError(f"{path} must be a YAML mapping", error_code="invalid_yaml")
    return parse_profile(data)


def load_profile_from_agent_team_dir(agent_team_dir: Path) -> ProjectProfile:
    path = agent_team_dir.resolve() / PACKAGED_PROFILE_FILENAME
    if not path.is_file():
        return packaged_default_profile()
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ProjectProfileError(f"{path} must be a YAML mapping", error_code="invalid_yaml")
    return parse_profile(data)


def _require_mapping(raw: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProjectProfileError(f"{path} must be a mapping", error_code="invalid_field")
    return raw


def _require_str(raw: Any, *, path: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ProjectProfileError(f"{path} must be a non-empty string", error_code="invalid_field")
    return raw.strip()


def _require_bool(raw: Any, *, path: str) -> bool:
    if not isinstance(raw, bool):
        raise ProjectProfileError(f"{path} must be a boolean", error_code="invalid_field")
    return raw


def _coerce_str_tuple(raw: Any, *, path: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise ProjectProfileError(f"{path} must be a non-empty list", error_code="invalid_field")
    out: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise ProjectProfileError(f"{path}[{i}] must be a non-empty string", error_code="invalid_field")
        out.append(item.strip())
    return tuple(out)


def _parse_target(name: str, raw: Mapping[str, Any]) -> TargetSpec:
    runner = _require_str(raw.get("runner"), path=f"build.full.targets.{name}.runner")
    if runner not in VALID_RUNNERS:
        raise ProjectProfileError(
            f"build.full.targets.{name}.runner must be one of: shell, psibase_tool",
            error_code="invalid_runner",
        )
    tool = raw.get("tool")
    command_raw = raw.get("command")
    command: tuple[str, ...] | None = None
    if runner == "psibase_tool":
        tool_name = _require_str(tool, path=f"build.full.targets.{name}.tool")
        known = set(available_tools())
        if tool_name not in known:
            raise ProjectProfileError(
                f"build.full.targets.{name}.tool unknown tool: {tool_name!r}",
                error_code="unknown_tool",
            )
        tool = tool_name
    else:
        tool = None
        command = _coerce_str_tuple(command_raw, path=f"build.full.targets.{name}.command")
    cwd = raw.get("cwd")
    cwd_s = str(cwd).strip() if isinstance(cwd, str) and cwd.strip() else None
    env_raw = raw.get("env") or {}
    if not isinstance(env_raw, dict):
        raise ProjectProfileError(f"build.full.targets.{name}.env must be a mapping", error_code="invalid_field")
    env = {str(k): str(v) for k, v in env_raw.items()}
    defaults_raw = raw.get("defaults") or {}
    if not isinstance(defaults_raw, dict):
        raise ProjectProfileError(
            f"build.full.targets.{name}.defaults must be a mapping",
            error_code="invalid_field",
        )
    timeout = raw.get("timeout_seconds")
    timeout_i: int | None = None
    if timeout is not None:
        if not isinstance(timeout, int) or timeout < 1:
            raise ProjectProfileError(
                f"build.full.targets.{name}.timeout_seconds must be a positive integer",
                error_code="invalid_field",
            )
        timeout_i = timeout
    glob = raw.get("glob")
    glob_s = str(glob).strip() if isinstance(glob, str) and glob.strip() else None
    return TargetSpec(
        name=name,
        runner=runner,  # type: ignore[arg-type]
        tool=tool,
        command=command,
        cwd=cwd_s,
        env=env,
        defaults=defaults_raw,
        timeout_seconds=timeout_i,
        glob=glob_s,
    )


def _parse_kind(name: str, raw: Mapping[str, Any], *, section: str) -> KindSpec:
    runner = _require_str(raw.get("runner"), path=f"{section}.kinds.{name}.runner")
    if runner not in VALID_RUNNERS:
        raise ProjectProfileError(
            f"{section}.kinds.{name}.runner must be one of: shell, psibase_tool",
            error_code="invalid_runner",
        )
    tool = raw.get("tool")
    command_template_raw = raw.get("command_template")
    command_template: tuple[str, ...] | None = None
    if runner == "psibase_tool":
        tool_name = _require_str(tool, path=f"{section}.kinds.{name}.tool")
        known = set(available_tools())
        if tool_name not in known:
            raise ProjectProfileError(
                f"{section}.kinds.{name}.tool unknown tool: {tool_name!r}",
                error_code="unknown_tool",
            )
        tool = tool_name
    else:
        tool = None
        command_template = _coerce_str_tuple(
            command_template_raw,
            path=f"{section}.kinds.{name}.command_template",
        )
    target_arg = _require_str(raw.get("target_arg"), path=f"{section}.kinds.{name}.target_arg")
    target_arg_kind_raw = raw.get("target_arg_kind", "string")
    target_arg_kind = _require_str(target_arg_kind_raw, path=f"{section}.kinds.{name}.target_arg_kind")
    if target_arg_kind not in VALID_TARGET_ARG_KINDS:
        raise ProjectProfileError(
            f"{section}.kinds.{name}.target_arg_kind must be string or path",
            error_code="invalid_field",
        )
    return KindSpec(
        name=name,
        runner=runner,  # type: ignore[arg-type]
        tool=tool,
        command_template=command_template,
        target_arg=target_arg,
        target_arg_kind=target_arg_kind,  # type: ignore[arg-type]
    )


def _optional_str_tuple(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return tuple(out)


def _parse_capabilities(raw: Mapping[str, Any]) -> dict[str, CapabilitySpec]:
    out: dict[str, CapabilitySpec] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise ProjectProfileError(f"capabilities.{name} must be a mapping", error_code="invalid_field")
        groups = _optional_str_tuple(entry.get("grants_invoke_of_groups"))
        kinds = _optional_str_tuple(entry.get("grants_invoke_of_kinds"))
        mcp_tools = _optional_str_tuple(entry.get("grants_mcp_tools"))
        out[name] = CapabilitySpec(
            name=name,
            grants_invoke_of_groups=groups,
            grants_invoke_of_kinds=kinds,
            grants_mcp_tools=mcp_tools,
        )
    return out


def parse_profile(raw: Mapping[str, Any]) -> ProjectProfile:
    schema = raw.get("schema")
    if schema != 1:
        raise ProjectProfileError(f"unsupported schema: {schema!r} (expected 1)", error_code="schema_unsupported")
    profile_name = _require_str(raw.get("profile_name"), path="profile_name")

    mcp_server = _require_mapping(raw.get("mcp_server"), path="mcp_server")
    mcp_server_name = _require_str(mcp_server.get("name"), path="mcp_server.name")
    if not MCP_NAME_RE.match(mcp_server_name):
        raise ProjectProfileError(
            f"mcp_server.name must match {MCP_NAME_RE.pattern!r}",
            error_code="invalid_mcp_name",
        )
    tools_cfg = _require_mapping(mcp_server.get("tools"), path="mcp_server.tools")
    enabled_raw = tools_cfg.get("enabled")
    enabled_list = _coerce_str_tuple(enabled_raw, path="mcp_server.tools.enabled")
    families: set[str] = set()
    for fam in enabled_list:
        if fam not in VALID_MCP_FAMILIES:
            raise ProjectProfileError(
                f"mcp_server.tools.enabled contains unknown family: {fam!r}",
                error_code="invalid_mcp_family",
            )
        families.add(fam)

    build = _require_mapping(raw.get("build"), path="build")
    build_full = _require_mapping(build.get("full"), path="build.full")
    targets_raw = _require_mapping(build_full.get("targets"), path="build.full.targets")
    if not targets_raw:
        raise ProjectProfileError("build.full.targets must contain at least one target", error_code="invalid_field")
    full_build_targets = {name: _parse_target(name, entry) for name, entry in targets_raw.items()}

    groups_raw = _require_mapping(build_full.get("groups"), path="build.full.groups")
    if not groups_raw:
        raise ProjectProfileError("build.full.groups must contain at least one group", error_code="invalid_field")
    full_build_groups: dict[str, GroupSpec] = {}
    for gname, members in groups_raw.items():
        if isinstance(members, list):
            member_names = _coerce_str_tuple(members, path=f"build.full.groups.{gname}")
            dispatch_raw = None
        elif isinstance(members, dict):
            member_list = members.get("targets") or members.get("members")
            member_names = _coerce_str_tuple(member_list, path=f"build.full.groups.{gname}")
            dispatch_raw = members.get("dispatch")
        else:
            raise ProjectProfileError(
                f"build.full.groups.{gname} must be a list or mapping",
                error_code="invalid_field",
            )
        for tname in member_names:
            if tname not in full_build_targets:
                raise ProjectProfileError(
                    f"build.full.groups.{gname} references unknown target: {tname!r}",
                    error_code="unknown_target",
                )
        full_build_groups[gname] = GroupSpec(name=gname, target_names=member_names, dispatch_raw=dispatch_raw)

    default_group = _require_str(build_full.get("default_group"), path="build.full.default_group")
    if default_group not in full_build_groups:
        raise ProjectProfileError(
            f"build.full.default_group unknown group: {default_group!r}",
            error_code="unknown_group",
        )

    scoped_build_kinds: dict[str, KindSpec] = {}
    build_scoped = build.get("scoped")
    if isinstance(build_scoped, dict):
        kinds_raw = build_scoped.get("kinds")
        if isinstance(kinds_raw, dict):
            for kname, entry in kinds_raw.items():
                scoped_build_kinds[kname] = _parse_kind(kname, entry, section="build.scoped")

    scoped_test_kinds: dict[str, KindSpec] = {}
    test = raw.get("test")
    if isinstance(test, dict):
        test_scoped = test.get("scoped")
        if isinstance(test_scoped, dict):
            kinds_raw = test_scoped.get("kinds")
            if isinstance(kinds_raw, dict):
                for kname, entry in kinds_raw.items():
                    scoped_test_kinds[kname] = _parse_kind(kname, entry, section="test.scoped")

    evidence = _require_mapping(raw.get("evidence"), path="evidence")
    full_build_event_tag = _require_str(evidence.get("full_build_event_tag"), path="evidence.full_build_event_tag")
    require_full_build = _require_bool(
        evidence.get("require_full_build_before_review"),
        path="evidence.require_full_build_before_review",
    )
    required_full_build_group = _require_str(
        evidence.get("required_full_build_group"),
        path="evidence.required_full_build_group",
    )
    if required_full_build_group not in full_build_groups:
        raise ProjectProfileError(
            f"evidence.required_full_build_group unknown group: {required_full_build_group!r}",
            error_code="unknown_group",
        )
    diff_base = evidence.get("diff_base")
    if diff_base is not None and diff_base != "working_tree":
        raise ProjectProfileError(
            "evidence.diff_base must be working_tree when set",
            error_code="invalid_field",
        )

    roles = _require_mapping(raw.get("roles"), path="roles")
    build_czar = _require_mapping(roles.get("build_czar"), path="roles.build_czar")
    build_czar_required = _require_bool(build_czar.get("required"), path="roles.build_czar.required")

    capabilities_raw = _require_mapping(raw.get("capabilities"), path="capabilities")
    capabilities = _parse_capabilities(capabilities_raw)

    for cap in capabilities.values():
        for gname in cap.grants_invoke_of_groups:
            if gname not in full_build_groups:
                raise ProjectProfileError(
                    f"capability {cap.name!r} references unknown group: {gname!r}",
                    error_code="unknown_group",
                )
        for kname in cap.grants_invoke_of_kinds:
            if kname not in scoped_build_kinds and kname not in scoped_test_kinds:
                raise ProjectProfileError(
                    f"capability {cap.name!r} references unknown kind: {kname!r}",
                    error_code="unknown_kind",
                )

    return ProjectProfile(
        schema=1,
        profile_name=profile_name,
        mcp_server_name=mcp_server_name,
        mcp_tool_families_enabled=frozenset(families),
        full_build_targets=full_build_targets,
        full_build_groups=full_build_groups,
        full_build_default_group=default_group,
        scoped_build_kinds=scoped_build_kinds,
        scoped_test_kinds=scoped_test_kinds,
        full_build_event_tag=full_build_event_tag,
        require_full_build_before_review=require_full_build,
        required_full_build_group=required_full_build_group,
        build_czar_required=build_czar_required,
        capabilities=capabilities,
        raw=dict(raw),
    )


def _merge_missing_keys(local: dict[str, Any], packaged: dict[str, Any], *, depth: int = 0) -> bool:
    changed = False
    for key, val in packaged.items():
        if key not in local:
            local[key] = val
            changed = True
            continue
        if depth >= 1:
            continue
        if isinstance(val, dict) and isinstance(local.get(key), dict):
            if _merge_missing_keys(local[key], val, depth=depth + 1):  # type: ignore[index]
                changed = True
    return changed


def ensure_project_profile_file(profile_path: Path) -> bool:
    """Create or merge-update project-profile.yaml. Returns True if modified."""
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    packaged = yaml.safe_load(packaged_default_text())
    if not isinstance(packaged, dict):
        packaged = {}

    if not profile_path.is_file():
        profile_path.write_text(packaged_default_text(), encoding="utf-8")
        return True

    local = load_yaml(profile_path)
    if not isinstance(local, dict):
        return False

    changed = _merge_missing_keys(local, packaged)
    if changed:
        profile_path.write_text(
            yaml.safe_dump(local, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return changed


def required_full_build_targets(profile: ProjectProfile) -> tuple[str, ...]:
    group = profile.full_build_groups.get(profile.required_full_build_group)
    if group is None:
        return ()
    return group.target_names


def capability_grants_group(profile: ProjectProfile, cap: str, group: str) -> bool:
    spec = profile.capabilities.get(cap)
    return spec is not None and group in spec.grants_invoke_of_groups


def capability_grants_kind(profile: ProjectProfile, cap: str, kind: str) -> bool:
    spec = profile.capabilities.get(cap)
    return spec is not None and kind in spec.grants_invoke_of_kinds


def capability_grants_mcp_tool(profile: ProjectProfile, cap: str, tool: str) -> bool:
    spec = profile.capabilities.get(cap)
    return spec is not None and tool in spec.grants_mcp_tools


def capability_for_legacy_tool_name(profile: ProjectProfile, tool: str) -> str | None:
    """Map a legacy psibase tool name to the capability that grants it."""
    mapping = {
        "run_full_build": "full_build",
        "build_package": "scoped_build",
        "build_rust_service": "scoped_build",
        "run_service_tests": "scoped_test",
    }
    cap = mapping.get(tool.strip())
    if cap and cap in profile.capabilities:
        return cap
    return None


def resolved_tools_for_capabilities(profile: ProjectProfile, capabilities: tuple[str, ...]) -> tuple[str, ...]:
    tools: set[str] = set()
    for cap in capabilities:
        spec = profile.capabilities.get(cap)
        if spec is None:
            continue
        for gname in spec.grants_invoke_of_groups:
            gspec = profile.full_build_groups.get(gname)
            if gspec is None:
                continue
            for tname in gspec.target_names:
                target = profile.full_build_targets.get(tname)
                if target and target.tool:
                    tools.add(target.tool)
        for kname in spec.grants_invoke_of_kinds:
            kind = profile.scoped_build_kinds.get(kname) or profile.scoped_test_kinds.get(kname)
            if kind and kind.tool:
                tools.add(kind.tool)
    return tuple(sorted(tools))
