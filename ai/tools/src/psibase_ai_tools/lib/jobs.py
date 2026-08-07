import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_STATE_DIR = Path(
    os.environ.get(
        "AI_TOOLS_STATE_DIR",
        os.environ.get("AI_DEV_STATE_DIR", "/root/ai-tools/state"),
    )
)


def new_job_id() -> str:
    return uuid.uuid4().hex[:16]


def job_dir(job_id: str, state_dir: Path = DEFAULT_STATE_DIR) -> Path:
    return state_dir / "jobs" / job_id


def write_state(job_id: str, state: Dict[str, object], state_dir: Path = DEFAULT_STATE_DIR) -> Path:
    directory = job_dir(job_id, state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "state.json"
    tmp = directory / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def read_state(job_id: str, state_dir: Path = DEFAULT_STATE_DIR) -> Dict[str, object]:
    path = job_dir(job_id, state_dir) / "state.json"
    return json.loads(path.read_text(encoding="utf-8"))


def start_process_job(command: List[str], *, cwd: Optional[str] = None, state_dir: Path = DEFAULT_STATE_DIR) -> Dict[str, object]:
    job_id = new_job_id()
    directory = job_dir(job_id, state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stdout_path = directory / "stdout.log"
    stderr_path = directory / "stderr.log"
    stdout = stdout_path.open("w", encoding="utf-8")
    stderr = stderr_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr, text=True, start_new_session=True)
    state = {
        "job_id": job_id,
        "status": "running",
        "pid": proc.pid,
        "command": command,
        "cwd": cwd,
        "started_at_ms": int(time.time() * 1000),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    write_state(job_id, state, state_dir)
    return state
