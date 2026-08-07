from pathlib import Path
from typing import Dict, Optional


def read_line_range(path: str, *, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, object]:
    log_path = Path(path)
    if not log_path.is_file():
        return {"ok": False, "path": str(log_path), "error": "Log file does not exist.", "lines": [], "total_lines": 0}

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    start = 1 if start_line is None else max(1, start_line)
    end = total if end_line is None else min(total, end_line)
    if end < start:
        selected = []
    else:
        selected = lines[start - 1 : end]
    return {
        "ok": True,
        "path": str(log_path),
        "start_line": start,
        "end_line": end,
        "total_lines": total,
        "lines": selected,
    }
