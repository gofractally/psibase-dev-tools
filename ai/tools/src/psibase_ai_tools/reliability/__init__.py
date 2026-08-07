"""Shared reliability primitives for agent workflows (team CLI, future Ralph reuse).

See ai-dev/ralph-dev/agentic-tool-reliability-guide.md for design intent.
"""

from .evidence import evidence_lines_for_task, task_complete_evidence_ok
from .gates import GateSet, gate_dict_for_prompt
from .templates import estimate_instruction_tokens, strip_template_comments

__all__ = [
    "estimate_instruction_tokens",
    "strip_template_comments",
    "GateSet",
    "gate_dict_for_prompt",
    "evidence_lines_for_task",
    "task_complete_evidence_ok",
]
