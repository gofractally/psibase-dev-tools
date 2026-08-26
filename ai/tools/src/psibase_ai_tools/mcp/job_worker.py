import argparse
import importlib
import json
import os
import time
from typing import Any

from . import paths
from .jobs import read_state, stderr_path, stdout_path, write_state


def _wait_for_initial_state(job_id: str) -> dict[str, Any]:
    for _ in range(50):
        try:
            return read_state(job_id)
        except FileNotFoundError:
            time.sleep(0.1)
    raise FileNotFoundError(f"Initial state did not appear for job_id: {job_id}")


def _without_large_streams(result: dict[str, Any]) -> dict[str, Any]:
    slim = dict(result)
    slim.pop("stdout", None)
    slim.pop("stderr", None)
    return slim


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one ai-dev tool job for the MCP server.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--payload-json", required=True)
    args = parser.parse_args()

    paths.ensure_ai_tools_importable()
    state = _wait_for_initial_state(args.job_id)
    payload = json.loads(args.payload_json)

    stdout_log = stdout_path(args.job_id)
    stderr_log = stderr_path(args.job_id)
    stdout_log.parent.mkdir(parents=True, exist_ok=True)
    stdout_log.touch(exist_ok=True)
    stderr_log.touch(exist_ok=True)
    # Expose the on-disk log files so that tools using stream_subprocess() (and
    # the chain runner) can write child output directly into them, allowing
    # get_*_logs / get_*_status to surface partial output while the job runs.
    os.environ["AI_TOOLS_JOB_ID"] = args.job_id
    os.environ["AI_TOOLS_JOB_STDOUT_PATH"] = str(stdout_log)
    os.environ["AI_TOOLS_JOB_STDERR_PATH"] = str(stderr_log)
    # Normally already set by jobs.start_tool_job on the worker's env; keep it
    # for direct invocations since chain_psinode and locks read this name.
    os.environ.setdefault("AI_DEV_MCP_JOB_ID", args.job_id)

    started = time.monotonic()
    exit_code = 1
    result: dict[str, Any]

    try:
        module = importlib.import_module(f"psibase_ai_tools.lib.{args.tool}")
        exit_code, result = module.run_with_exit_code(payload)
    except BaseException as exc:
        result = {
            "ok": False,
            "tool": args.tool,
            "status": "error",
            "summary": f"Unexpected MCP job worker failure: {exc}",
            "error_code": "internal_error",
            "error_category": "mcp_worker",
            "exit_code": None,
        }
        exit_code = 1

    # Only fall back to dumping the result-derived stdout/stderr into the log
    # files when the tool did not stream anything. If the log files already
    # have content (streaming or chain runner wrote directly to them), keep
    # that content as-is so the full live transcript is preserved.
    if stdout_log.stat().st_size == 0:
        stdout_log.write_text(str(result.get("stdout", "")), encoding="utf-8")
    if stderr_log.stat().st_size == 0:
        stderr_log.write_text(str(result.get("stderr", "")), encoding="utf-8")

    state["status"] = "succeeded" if result.get("ok") is True and exit_code == 0 else "failed"
    state["finished_at_ms"] = int(time.time() * 1000)
    state["duration_seconds"] = time.monotonic() - started
    state["exit_code"] = exit_code
    state["result"] = _without_large_streams(result)
    write_state(args.job_id, state)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
