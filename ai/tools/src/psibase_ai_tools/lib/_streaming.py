"""Helpers for running subprocesses with optional log streaming.

When invoked under the MCP job worker, the env vars
``AI_TOOLS_JOB_STDOUT_PATH`` / ``AI_TOOLS_JOB_STDERR_PATH`` (or the legacy
``AI_DEV_*`` aliases) point at the on-disk log files for the job. In that case
``stream_subprocess`` runs the child process with its stdout/stderr attached
directly to those files so partial output is visible to ``get_*_logs`` /
``get_*_status`` while the job is still running.

When the env vars are not set (CLI usage, or non-MCP callers), it falls back
to ``subprocess.run(capture_output=True, text=True)`` so behavior is
identical to before.

Either way, the returned ``CompletedProcess`` has ``stdout`` and ``stderr``
populated with the text emitted by *this* call, which preserves the parsing
expectations of the existing build/test tools (each tool reads
``run.stdout`` / ``run.stderr`` to compute its result).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def _job_log_paths() -> tuple[Optional[Path], Optional[Path]]:
    out = os.environ.get("AI_TOOLS_JOB_STDOUT_PATH") or os.environ.get("AI_DEV_JOB_STDOUT_PATH")
    err = os.environ.get("AI_TOOLS_JOB_STDERR_PATH") or os.environ.get("AI_DEV_JOB_STDERR_PATH")
    if not out or not err:
        return None, None
    return Path(out), Path(err)


def streaming_enabled() -> bool:
    out, err = _job_log_paths()
    return out is not None and err is not None


def _read_slice(path: Path, start_offset: int) -> str:
    if not path.is_file():
        return ""
    with open(path, "rb") as f:
        f.seek(start_offset)
        data = f.read()
    return data.decode("utf-8", errors="replace")


def _write_banner(path: Path, banner: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as f:
        f.write(banner.encode("utf-8"))


def stream_subprocess(
    cmd: Sequence[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    check: bool = False,
    section_header: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` and return a CompletedProcess with text stdout/stderr.

    If MCP job log paths are present in the environment, the child's stdout
    and stderr are written directly to those files (line-buffered by the OS)
    so that ``get_*_logs`` reflects partial output while the command runs.
    The returned ``CompletedProcess`` always carries the slice that this
    invocation produced, so the calling tool can parse it the same way
    regardless of streaming.
    """

    out_path, err_path = _job_log_paths()

    if out_path is None or err_path is None:
        return subprocess.run(
            list(cmd),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            check=check,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    err_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.touch(exist_ok=True)
    err_path.touch(exist_ok=True)

    if section_header:
        header_bytes = (section_header.rstrip("\n") + "\n").encode("utf-8")
        with open(out_path, "ab") as f:
            f.write(header_bytes)
        with open(err_path, "ab") as f:
            f.write(header_bytes)

    out_start = out_path.stat().st_size
    err_start = err_path.stat().st_size

    with open(out_path, "ab") as out_f, open(err_path, "ab") as err_f:
        completed = subprocess.run(
            list(cmd),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdout=out_f,
            stderr=err_f,
            check=False,
        )

    stdout_text = _read_slice(out_path, out_start)
    stderr_text = _read_slice(err_path, err_start)

    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode, list(cmd), output=stdout_text, stderr=stderr_text
        )

    return subprocess.CompletedProcess(
        args=list(cmd), returncode=completed.returncode, stdout=stdout_text, stderr=stderr_text
    )


__all__ = ["stream_subprocess", "streaming_enabled"]


# Backwards-compat re-export for callers that already import via Any.
_ = Any  # silence unused import warning when type checkers run
