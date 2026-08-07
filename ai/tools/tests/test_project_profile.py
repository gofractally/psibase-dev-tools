from __future__ import annotations

from pathlib import Path

import yaml

from psibase_ai_tools.project_profile import (
    ProjectProfileError,
    ensure_project_profile_file,
    load_profile,
    packaged_default_profile,
    parse_profile,
    required_full_build_targets,
)


def test_packaged_default_profile_is_psibase() -> None:
    profile = packaged_default_profile()
    assert profile.profile_name == "psibase"
    assert profile.mcp_server_name == "psibase-mcp"
    assert required_full_build_targets(profile) == ("psibase_full_build",)


def test_ensure_project_profile_file_creates_missing(tmp_path: Path) -> None:
    path = tmp_path / "project-profile.yaml"
    assert ensure_project_profile_file(path) is True
    assert path.is_file()
    profile = parse_profile(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert profile.profile_name == "psibase"


def test_ensure_project_profile_file_merges_missing_top_level(tmp_path: Path) -> None:
    path = tmp_path / "project-profile.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "profile_name": "custom",
                "mcp_server": {"name": "custom-mcp", "tools": {"enabled": ["build"]}},
                "build": packaged_default_profile().raw["build"],
                "test": packaged_default_profile().raw["test"],
                "evidence": packaged_default_profile().raw["evidence"],
                "roles": packaged_default_profile().raw["roles"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert ensure_project_profile_file(path) is True
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "capabilities" in data


def test_load_profile_from_worktree(tmp_path: Path) -> None:
    agent_team = tmp_path / ".agent-team"
    agent_team.mkdir()
    ensure_project_profile_file(agent_team / "project-profile.yaml")
    profile = load_profile(tmp_path)
    assert profile.full_build_event_tag == "run_full_build"


def test_invalid_schema_raises() -> None:
    try:
        parse_profile({"schema": 2, "profile_name": "x"})
        assert False, "expected ProjectProfileError"
    except ProjectProfileError as exc:
        assert exc.error_code == "schema_unsupported"
