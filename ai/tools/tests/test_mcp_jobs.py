from __future__ import annotations

import os
from pathlib import Path

from psibase_ai_tools.mcp import jobs as mcp_jobs


def test_workspace_hash_differs() -> None:
    assert mcp_jobs.workspace_hash("/root/a") != mcp_jobs.workspace_hash("/root/b")


def test_cancel_refuses_workspace_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "state"
    os.environ["AI_TOOLS_STATE_DIR"] = str(root)
    mcp_jobs._job_dir_cache.clear()
    try:
        job_id = "aaaaaaaaaaaaaaaa"
        mcp_jobs.write_state(
            job_id,
            {
                "job_id": job_id,
                "family": "build",
                "tool": "run_full_build",
                "version": "1.0.0",
                "status": "running",
                "started_at_ms": 0,
                "pid": -1,
                "arguments": {"workspace_root": "/root/ws-foo"},
                "result": None,
            },
        )
        refused = mcp_jobs.cancel(job_id, caller_workspace_root="/root/ws-bar", force=False)
        assert refused.get("error_code") == "workspace_mismatch"
    finally:
        os.environ.pop("AI_TOOLS_STATE_DIR", None)
        mcp_jobs._job_dir_cache.clear()


def test_tool_specs_include_expected_tools() -> None:
    from psibase_ai_tools.mcp.server import tool_specs

    names = {t.name for t in tool_specs()}
    assert "start_full_build" in names
    assert "start_service_tests" in names
