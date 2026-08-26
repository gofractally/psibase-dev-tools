from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

GUARDS_DIR = Path(__file__).resolve().parents[1] / "src" / "psibase_ai_tools" / "guards"


@pytest.mark.skipif(not (GUARDS_DIR / "cargo").is_file(), reason="guards not present")
def test_cargo_guard_blocks_without_activation() -> None:
    env = os.environ.copy()
    env.pop("AI_DEV_TOOL_ACTIVE", None)
    proc = subprocess.run(
        [str(GUARDS_DIR / "cargo"), "--version"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 97
    assert "ai-tools" in (proc.stderr or "")
