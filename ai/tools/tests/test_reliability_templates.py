from psibase_ai_tools.reliability.gates import GateSet, gate_dict_for_prompt
from psibase_ai_tools.reliability.evidence import task_complete_evidence_ok
from psibase_ai_tools.reliability.templates import estimate_instruction_tokens, strip_template_comments


def test_strip_template_comments_strips_percent_lines():
    raw = "%% meta\nkeep\n%% another\n"
    assert strip_template_comments(raw.splitlines(keepends=True)) == "keep\n"


def test_estimate_instruction_tokens_positive():
    assert estimate_instruction_tokens("hello world three words") > 0


def test_gate_set_serializes():
    g = GateSet(baseline_build="PASSED")
    assert gate_dict_for_prompt(g)["gates"]["baseline_build"] == "PASSED"


def test_task_complete_evidence_ok_detects_success_blocks():
    log = """
### 2026-05-04T00:00:00Z — junior — task_started
- refs: T-001

### 2026-05-04T00:00:01Z — junior — build_completed
- refs: T-001
- status: success

### 2026-05-04T00:01:00Z — junior — test_completed
- refs: T-001
- status: success

### 2026-05-04T00:02:00Z — build_czar — build_completed
- refs: T-001
- tool: run_full_build
- status: success

### 2026-05-04T00:03:00Z — senior — review_completed
- refs: T-001
- verdict: approved
"""
    ok, reason = task_complete_evidence_ok(log, "T-001")
    assert ok and reason == "ok"


def test_task_complete_evidence_ok_rejects_full_build_after_review():
    log = """
### 2026-05-04T00:00:00Z — junior — task_started
- refs: T-001

### 2026-05-04T00:00:01Z — junior — build_completed
- refs: T-001
- status: success

### 2026-05-04T00:01:00Z — junior — test_completed
- refs: T-001
- status: success

### 2026-05-04T00:03:00Z — senior — review_completed
- refs: T-001
- verdict: approved

### 2026-05-04T00:03:05Z — build_czar — build_completed
- refs: T-001
- tool: run_full_build
- status: success
"""
    ok, reason = task_complete_evidence_ok(log, "T-001")
    assert not ok and reason == "missing_pre_senior_review_full_build"
