from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from psibase_ai_tools.lib.profile_runner import invoke_full_build, invoke_scoped_build
from psibase_ai_tools.project_profile import packaged_default_profile


def test_invoke_full_build_psibase_profile(tmp_path: Path) -> None:
    profile = packaged_default_profile()
    fake_result = {
        "ok": True,
        "status": "passed",
        "summary": "ok",
        "error_code": None,
        "duration_seconds": 1.0,
    }

    with patch("psibase_ai_tools.lib.profile_runner.run_tool", return_value=(0, fake_result)):
        result = invoke_full_build(profile=profile, workspace_root=tmp_path)
    assert result.ok is True
    assert len(result.targets) == 1
    assert result.targets[0].target_name == "psibase_full_build"
    assert result.primary_log_fields["tool"] == "run_full_build"


def test_invoke_scoped_build_package(tmp_path: Path) -> None:
    profile = packaged_default_profile()
    fake_result = {
        "ok": True,
        "status": "passed",
        "summary": "ok",
        "error_code": None,
        "duration_seconds": 0.5,
    }

    with patch("psibase_ai_tools.lib.profile_runner.run_tool", return_value=(0, fake_result)):
        result = invoke_scoped_build(
            profile=profile,
            workspace_root=tmp_path,
            kind="package",
            target_value="foo",
            payload_overrides={"build_dir": "build", "jobs": 2},
        )
    assert result.ok is True
    assert result.targets[0].target_name.startswith("package:")
