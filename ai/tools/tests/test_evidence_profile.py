from __future__ import annotations

from psibase_ai_tools.project_profile import packaged_default_profile
from psibase_ai_tools.reliability.evidence import (
    pre_senior_review_full_build_ok,
    task_complete_evidence_ok,
)


LOG = """
### 2026-01-01T00:00:00Z — junior — task_started
- refs: T-001

### 2026-01-01T00:01:00Z — build_czar — build_completed
- refs: T-001
- tool: run_full_build
- target: psibase_full_build
- group: full_build
- status: success

### 2026-01-01T00:02:00Z — senior — review_completed
- refs: T-001
- verdict: approved
"""


def test_pre_senior_review_accepts_new_target_field() -> None:
    profile = packaged_default_profile()
    ok, reason = pre_senior_review_full_build_ok(LOG, "T-001", profile)
    assert ok is True
    assert reason == "ok"


def test_legacy_tool_only_log_still_passes() -> None:
    profile = packaged_default_profile()
    legacy = """
### 2026-01-01T00:00:00Z — junior — task_started
- refs: T-001
### 2026-01-01T00:01:00Z — build_czar — build_completed
- refs: T-001
- tool: run_full_build
- status: success
### 2026-01-01T00:02:00Z — senior — review_completed
- refs: T-001
- verdict: approved
"""
    ok, _ = pre_senior_review_full_build_ok(legacy, "T-001", profile)
    assert ok is True


def test_gate_disabled_skips_full_build_requirement() -> None:
    raw = dict(packaged_default_profile().raw)
    raw["evidence"] = dict(raw["evidence"])
    raw["evidence"]["require_full_build_before_review"] = False
    from psibase_ai_tools.project_profile import parse_profile

    profile = parse_profile(raw)
    ok, reason = task_complete_evidence_ok(
        "### 2026-01-01T00:00:00Z — junior — build_completed\n- refs: T-001\n- status: success\n",
        "T-001",
        profile,
        require_build=True,
        require_test=False,
    )
    assert ok is True
    assert reason == "ok"
