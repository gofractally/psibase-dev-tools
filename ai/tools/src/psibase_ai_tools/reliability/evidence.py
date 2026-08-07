from __future__ import annotations

import re

from psibase_ai_tools.project_profile import ProjectProfile, packaged_default_profile, required_full_build_targets

_HEADING_RE = re.compile(
    r"^###\s+(?P<ts>\S+)\s+—\s+(?P<role>\S+)\s+—\s+(?P<event>\S+)\s*$",
    re.MULTILINE,
)


def iter_log_blocks(log_text: str) -> list[tuple[str, str, str, str]]:
    """Parse team-log.md into ``(iso_ts, role, event, block_text)`` in file order."""
    lines = log_text.splitlines()
    blocks: list[tuple[str, str, str, str]] = []
    i = 0
    while i < len(lines):
        m = _HEADING_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        ts, role, event = m.group("ts"), m.group("role"), m.group("event")
        chunk = [lines[i]]
        i += 1
        while i < len(lines) and not lines[i].startswith("### "):
            chunk.append(lines[i])
            i += 1
        blocks.append((ts, role, event, "\n".join(chunk)))
    return blocks


def _has_success_for_target(
    chunk: str,
    task_id: str,
    target_name: str,
    profile: ProjectProfile,
) -> bool:
    if task_id and task_id not in chunk:
        return False
    if not re.search(r"status:\s*success", chunk, re.IGNORECASE):
        return False
    if re.search(rf"target:\s*{re.escape(target_name)}\b", chunk):
        return True
    required = required_full_build_targets(profile)
    if (
        len(required) == 1
        and required[0] == target_name
        and profile.full_build_event_tag in chunk
    ):
        return True
    return False


def pre_senior_review_full_build_ok(
    log_text: str,
    task_id: str,
    profile: ProjectProfile | None = None,
) -> tuple[bool, str]:
    """Require required full-build targets green after junior task_started and before latest approved Senior review."""
    profile = profile or packaged_default_profile()
    if not profile.require_full_build_before_review:
        return True, "gate_disabled"

    blocks = iter_log_blocks(log_text)
    last_junior_start = _last_junior_task_started_block_index(log_text, task_id)
    if last_junior_start is None:
        return False, "missing_junior_task_started"

    last_review_idx: int | None = None
    for i, (_ts, _role, event, chunk) in enumerate(blocks):
        if event == "review_completed" and task_id in chunk and "verdict: approved" in chunk:
            last_review_idx = i
    if last_review_idx is None:
        return False, "missing_approved_review"

    targets = required_full_build_targets(profile)
    for target_name in targets:
        found = False
        for _ts, _role, event, chunk in blocks[last_junior_start + 1 : last_review_idx]:
            if event != "build_completed":
                continue
            if _has_success_for_target(chunk, task_id, target_name, profile):
                found = True
                break
        if not found:
            return False, "missing_pre_senior_review_full_build"
    return True, "ok"


def post_review_full_build_ok(log_text: str, task_id: str, profile: ProjectProfile | None = None) -> tuple[bool, str]:
    """Deprecated alias — ordering is Junior → full build → Senior review; use ``pre_senior_review_full_build_ok``."""
    return pre_senior_review_full_build_ok(log_text, task_id, profile)


def junior_owned_tasks_in_flight(tasks: list[dict]) -> list[str]:
    """Task ids owned by Junior that are actively in implementation or awaiting Senior review."""
    out: list[str] = []
    for row in tasks:
        if str(row.get("owner")) != "junior":
            continue
        st = str(row.get("status") or "")
        if st in ("in_progress", "in_review"):
            tid = str(row.get("id") or "").strip()
            if tid:
                out.append(tid)
    return out


def latest_junior_handoff_to_build_czar(log_text: str, task_id: str) -> bool:
    """True if the most recent junior log entry for task_id (after last task_started)
    is a ``handoff --to-role build_czar --status verification``."""
    blocks = iter_log_blocks(log_text)
    last_i = _last_junior_task_started_block_index(log_text, task_id)
    if last_i is None:
        return False
    for _ts, role, event, chunk in reversed(blocks[last_i + 1 :]):
        if task_id not in chunk or role != "junior":
            continue
        if event == "handoff":
            return "to_role: build_czar" in chunk and "status: verification" in chunk
        return False
    return False


def junior_declared_no_scoped_tests(log_text: str, task_id: str) -> bool:
    """True if junior logged engineering_note 'no_scoped_tests' for task after task_started."""
    blocks = iter_log_blocks(log_text)
    last_i = _last_junior_task_started_block_index(log_text, task_id)
    if last_i is None:
        return False
    for _ts, role, event, chunk in blocks[last_i + 1 :]:
        if (
            event == "engineering_note"
            and role == "junior"
            and task_id in chunk
            and "no_scoped_tests" in chunk
        ):
            return True
    return False


def _has_successful_full_build_for_task_after_start(
    log_text: str,
    task_id: str,
    last_start_i: int,
    profile: ProjectProfile | None = None,
) -> bool:
    profile = profile or packaged_default_profile()
    blocks = iter_log_blocks(log_text)
    last_review_idx: int | None = None
    for i, (_ts, _role, event, chunk) in enumerate(blocks):
        if event == "review_completed" and task_id in chunk and "verdict: approved" in chunk:
            last_review_idx = i
    end = last_review_idx if last_review_idx is not None else len(blocks)
    targets = required_full_build_targets(profile)
    for target_name in targets:
        found = False
        for _ts, _role, event, chunk in blocks[last_start_i + 1 : end]:
            if event != "build_completed":
                continue
            if _has_success_for_target(chunk, task_id, target_name, profile):
                found = True
                break
        if not found:
            return False
    return True


def _junior_scoped_verification_ready(log_text: str, task_id: str) -> bool:
    """True when scoped work is done enough to hand off to Build Czar for full build."""
    if latest_junior_handoff_to_build_czar(log_text, task_id):
        return True
    if _has_success_event(log_text, task_id, "build_completed") and _has_success_event(
        log_text, task_id, "test_completed"
    ):
        return True
    if _has_success_event(log_text, task_id, "build_completed") and junior_declared_no_scoped_tests(
        log_text, task_id
    ):
        return True
    return False


def task_needs_build_czar_full_build(
    log_text: str,
    task_id: str,
    profile: ProjectProfile | None = None,
) -> bool:
    """True when Junior has scoped success for the task but no successful full build yet this cycle."""
    profile = profile or packaged_default_profile()
    last_i = _last_junior_task_started_block_index(log_text, task_id)
    if last_i is None:
        return False
    if not _junior_scoped_verification_ready(log_text, task_id):
        return False
    ok, _reason = pre_senior_review_full_build_ok(log_text, task_id, profile)
    if ok:
        return False
    if _has_successful_full_build_for_task_after_start(log_text, task_id, last_i, profile):
        return False
    return True


def _last_junior_task_started_block_index(log_text: str, task_id: str) -> int | None:
    """Index of the latest junior work-cycle start for ``task_id`` (block order).

    A cycle starts on ``task_started`` or on ``task_transition`` from ``pending`` to
    ``in_progress`` (orchestrator/senior sometimes start tasks that way instead of
    ``task-next``).
    """
    blocks = iter_log_blocks(log_text)
    last_i: int | None = None
    for i, (_ts, role, event, chunk) in enumerate(blocks):
        if task_id not in chunk or role != "junior":
            continue
        if event == "task_started":
            last_i = i
            continue
        if event == "task_transition" and re.search(
            r"pending\s*->\s*in_progress", chunk, re.IGNORECASE
        ):
            last_i = i
    return last_i


def senior_review_strikes_after_task_start(log_text: str, task_id: str) -> int:
    """Count ``review_completed`` with ``changes_requested`` for ``task_id`` after latest junior ``task_started``."""
    blocks = iter_log_blocks(log_text)
    last_i = _last_junior_task_started_block_index(log_text, task_id)
    if last_i is None:
        return 0
    n = 0
    for _ts, role, event, chunk in blocks[last_i + 1 :]:
        if event != "review_completed" or task_id not in chunk:
            continue
        if "verdict: changes_requested" in chunk or "verdict:changes_requested" in chunk.replace(" ", ""):
            n += 1
    return n


def senior_baseline_full_build_needed(
    log_text: str,
    profile: ProjectProfile | None = None,
) -> tuple[bool, str]:
    """True if no successful required full build logged after the last senior ``task_filed``."""
    profile = profile or packaged_default_profile()
    blocks = iter_log_blocks(log_text)
    last_tf_idx: int | None = None
    for i, (_ts, role, event, _chunk) in enumerate(blocks):
        if event == "task_filed" and role == "senior":
            last_tf_idx = i
    if last_tf_idx is None:
        return False, "no_task_filed"

    targets = required_full_build_targets(profile)
    found_targets: set[str] = set()
    for _ts, role, event, chunk in blocks[last_tf_idx + 1 :]:
        if event != "build_completed" or role not in ("senior", "build_czar"):
            continue
        for target_name in targets:
            if _has_success_for_target(chunk, "", target_name, profile) or (
                profile.full_build_event_tag in chunk
                and re.search(r"status:\s*success", chunk, re.IGNORECASE)
                and target_name in chunk
            ):
                found_targets.add(target_name)
    if found_targets >= set(targets):
        return False, "baseline_ok"
    return True, "baseline_required"


def junior_task_started_logged(log_text: str, task_id: str) -> bool:
    """True if a junior ``task_started`` exists for ``task_id`` (any occurrence)."""
    return _last_junior_task_started_block_index(log_text, task_id) is not None


def has_senior_intercede_after_task_start(log_text: str, task_id: str) -> bool:
    """True if a ``senior_intercede`` entry for ``task_id`` exists after the latest junior ``task_started``."""
    blocks = iter_log_blocks(log_text)
    last_i = _last_junior_task_started_block_index(log_text, task_id)
    if last_i is None:
        return False
    for j in range(last_i + 1, len(blocks)):
        _ts, role, event, chunk = blocks[j]
        if event != "senior_intercede" or role != "senior":
            continue
        if f"- refs: {task_id}" in chunk:
            return True
    return False


def junior_failure_count_after_task_start(log_text: str, task_id: str, fail_event: str) -> int:
    """Count Junior ``fail_event`` entries for ``task_id`` after the latest ``task_started`` for that task."""
    blocks = iter_log_blocks(log_text)
    last_i = _last_junior_task_started_block_index(log_text, task_id)
    if last_i is None:
        return 0
    n = 0
    for _ts, role, event, chunk in blocks[last_i + 1 :]:
        if role != "junior" or event != fail_event:
            continue
        if task_id in chunk:
            n += 1
    return n


def evidence_lines_for_task(log_text: str, task_id: str) -> list[str]:
    """Return bullet lines from log entries that reference task_id."""
    lines = log_text.splitlines()
    hits: list[str] = []
    i = 0
    while i < len(lines):
        m = _HEADING_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        block: list[str] = [lines[i]]
        j = i + 1
        while j < len(lines) and not lines[j].startswith("### "):
            block.append(lines[j])
            j += 1
        chunk = "\n".join(block)
        if task_id in chunk:
            hits.extend([ln for ln in block if ln.strip().startswith("- ")])
        i = j
    return hits


def task_complete_evidence_ok(
    log_text: str,
    task_id: str,
    profile: ProjectProfile | None = None,
    *,
    require_build: bool = True,
    require_test: bool = True,
    require_pre_senior_review_full_build: bool | None = None,
) -> tuple[bool, str]:
    """Check team-log for successful build_completed / test_completed referencing task."""
    profile = profile or packaged_default_profile()
    text = log_text
    if require_build and not _has_success_event(text, task_id, "build_completed"):
        return False, "missing_build_completed"
    if require_test and not _has_success_event(text, task_id, "test_completed"):
        if not junior_declared_no_scoped_tests(text, task_id):
            return False, "missing_test_completed"
    need_full = (
        require_pre_senior_review_full_build
        if require_pre_senior_review_full_build is not None
        else profile.require_full_build_before_review
    )
    if need_full:
        ok2, reason = pre_senior_review_full_build_ok(text, task_id, profile)
        if not ok2:
            return False, reason
    return True, "ok"


def _has_success_event(log_text: str, task_id: str, event: str) -> bool:
    """Scan paired headings + bullets for success + refs containing task_id."""
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        m = _HEADING_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        ev = m.group("event")
        block = [lines[i]]
        j = i + 1
        while j < len(lines) and not lines[j].startswith("### "):
            block.append(lines[j])
            j += 1
        chunk = "\n".join(block)
        if ev == event and task_id in chunk:
            if "success" in chunk.lower() or "status: success" in chunk.lower():
                return True
            if re.search(r"status:\s*success", chunk, re.IGNORECASE):
                return True
        i = j
    return False
