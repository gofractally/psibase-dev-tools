import re
from typing import Dict


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ERROR_WORD_RE = re.compile(r"\berror\b", re.IGNORECASE)
WARNING_WORD_RE = re.compile(r"\bwarning\b", re.IGNORECASE)

ERROR_LINE_PATTERNS = [
    re.compile(r"^\s*error(?:\[[A-Za-z0-9_-]+\])?:", re.IGNORECASE),
    re.compile(r"^\s*fatal error:", re.IGNORECASE),
    re.compile(r"^\s*cmake error\b", re.IGNORECASE),
    re.compile(r"^\s*FAILED:", re.IGNORECASE),
    re.compile(r"^\s*make(?:\[\d+\])?:\s+\*\*\*", re.IGNORECASE),
    re.compile(r"^\s*[^:\s][^:]*:\d+(?::\d+)?:\s*(?:fatal\s+)?error:", re.IGNORECASE),
]

WARNING_LINE_PATTERNS = [
    re.compile(r"^\s*warning(?:\[[A-Za-z0-9_-]+\])?:", re.IGNORECASE),
    re.compile(r"^\s*cmake warning\b", re.IGNORECASE),
    re.compile(r"^\s*[^:\s][^:]*:\d+(?::\d+)?:\s*warning:", re.IGNORECASE),
]


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def count_build_diagnostics(text: str) -> Dict[str, object]:
    clean = strip_ansi(text)
    error_count = 0
    warning_count = 0

    for line in clean.splitlines():
        if any(pattern.search(line) for pattern in ERROR_LINE_PATTERNS):
            error_count += 1
        if any(pattern.search(line) for pattern in WARNING_LINE_PATTERNS):
            warning_count += 1

    return {
        "parse_quality": "strict_prefix",
        "error_count": error_count,
        "warning_count": warning_count,
        "error_word_hits": len(ERROR_WORD_RE.findall(clean)),
        "warning_word_hits": len(WARNING_WORD_RE.findall(clean)),
    }
