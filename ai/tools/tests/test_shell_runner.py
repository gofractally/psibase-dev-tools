from __future__ import annotations

from pathlib import Path

from psibase_ai_tools.lib import shell_runner
from psibase_ai_tools.project_profile import TargetSpec


def test_run_shell_target_success(tmp_path: Path) -> None:
    target = TargetSpec(
        name="echo_ok",
        runner="shell",
        tool=None,
        command=("sh", "-c", "echo hello"),
        cwd=None,
        env={},
        defaults={},
        timeout_seconds=None,
        glob=None,
    )
    result = shell_runner.run_shell_target(
        target=target,
        workspace_root=tmp_path,
        section_header="test",
    )
    assert result["ok"] is True
    assert result["tool"] == "echo_ok"
    assert "hello" in result["stdout"]


def test_run_shell_target_template_substitution(tmp_path: Path) -> None:
    target = TargetSpec(
        name="echo_target",
        runner="shell",
        tool=None,
        command=("sh", "-c", "echo {{target}}"),
        cwd=None,
        env={},
        defaults={},
        timeout_seconds=None,
        glob=None,
    )
    result = shell_runner.run_shell_target(
        target=target,
        workspace_root=tmp_path,
        section_header="test",
        target_arg_value="world",
    )
    assert result["ok"] is True
    assert "world" in result["stdout"]
