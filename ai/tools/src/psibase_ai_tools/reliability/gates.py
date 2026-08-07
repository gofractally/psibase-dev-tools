from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateSet:
    """Rolling verification gates (Ralph-inspired; used by team CLI metadata)."""

    baseline_build: str = "NOT_PASSED"
    have_seen_tests_pass_ever: str = "NOT_PASSED"
    have_seen_tests_pass_for_this_task: str = "NOT_PASSED"
    final_build: str = "NOT_PASSED"
    extra: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, str]:
        base = {
            "baseline_build": self.baseline_build,
            "have_seen_tests_pass_ever": self.have_seen_tests_pass_ever,
            "have_seen_tests_pass_for_this_task": self.have_seen_tests_pass_for_this_task,
            "final_build": self.final_build,
        }
        base.update(self.extra)
        return base


def gate_dict_for_prompt(gates: GateSet) -> dict[str, Any]:
    """Structured blob suitable for JSON/text injection into orchestrator prompts."""
    return {"gates": gates.as_dict()}
