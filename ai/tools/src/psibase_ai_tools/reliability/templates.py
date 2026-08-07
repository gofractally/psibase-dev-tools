from __future__ import annotations

import re
from typing import Iterable


def strip_template_comments(lines: Iterable[str]) -> str:
    """Remove %% editorial lines (Ralph / agent-team persona convention)."""
    out: list[str] = []
    for line in lines:
        if line.startswith("%%"):
            continue
        out.append(line)
    return "".join(out)


def estimate_instruction_tokens(text: str) -> float:
    """Rough token estimate when tiktoken is unavailable (PRD FR-029 style)."""
    words = len(re.findall(r"\b\w+\b", text))
    return words * 1.3
