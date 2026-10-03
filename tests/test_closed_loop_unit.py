"""Unit tests for Nomad Closed-Loop Components:
- Task selection
- Prompt compiler & leak refusal
- Criteria catalog & test generation
- Subprocess local evaluator & tamper/leak detection
- Vault store encryption & lifecycle
- State machine transitions & hard cap of 3 iterations
- HMAC-SHA256 audit ledger
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from backend.config import settings
from backend.loop.criteria_catalog import (
    Criterion,
    generate_pytest_code,
    normalize_criterion,
    save_acceptance_tests,
)
from backend.loop.evaluator import LocalEvaluator
from backend.loop.prompt_compiler import (
    PrivacyRefusalError,
    PromptCompiler,
    StructuredPrompt,
)
from backend.loop.state import CodeReportSubmission, LoopStateMachine
from backend.loop.task_selector import BuildTask, TaskSelector
from backend.loop.vault_store import delete_vault, load_vault, save_vault
from backend.loop.workspace import is_path_inside_workspace, validate_workspace_files
from backend.processors.ledger import AuditLedger
from backend.processors.privacy import Vault
from backend.storage.database import SessionLocal, init_db
from backend.storage.models import MeetingModel, ReleaseDecisionModel
from backend.storage.repository import Repository


@pytest.fixture
def clean_db():
    init_db()
    db = SessionLocal()
    repo = Repository(db)
    yield db, repo
    db.close()


@pytest.fixture
def mock_released_meeting(clean_db):
    db, repo = clean_db
    meeting_id = "mtg_unit_test_001"
    
    # Clean up any existing meeting with this ID
    existing = repo.get_meeting_by_id(meeting_id)
    if existing:
        db.delete(existing)
        db.commit()

    meeting = MeetingModel(
        id=meeting_id,
        meetily_id="meetily_001",
        title="Web Sprint Meeting",
        status="completed",
        transcript_sha256="abc123sha",
        raw_summary="Summary of web sprint",
    )
    db.add(meeting)
    db.commit()

    decision = ReleaseDecisionModel(
        run_id="run_test",
        meeting_id=meeting.id,
        decision="release",
        reasons_json=json.dumps(["All claims verified"]),
    )
    db.add(decision)
    db.commit()

    return meeting


# -------------------------------------------------------------------------- #
# 1. Task Selection Tests                                                    #
# -------------------------------------------------------------------------- #

def test_task_selector_excludes_contradicted_and_unverifiable(clean_db, mock_released_meeting):
    _, repo = clean_db
    v = Vault()

    claims = [
        {"id": "c1", "topic": "Landing Page", "claim_text": "Build landing page", "verdict": "supported", "type": "action_item"},
        {"id": "c2", "topic": "Budget Claim", "claim_text": "Budget is $50,000", "verdict": "contradicted"},
        {"id": "c3", "topic": "Quantum Architecture", "claim_text": "Quantum cluster", "verdict": "unverifiable"},
    ]

    selector = TaskSelector(repo=repo, vault=v)
    res = selector.select_tasks(mock_released_meeting.id, claims_data=claims)

    assert res.is_released is True
    assert len(res.buildable_tasks) == 1
    assert res.buildable_tasks[0].task_id == "task_c1"
    assert len(res.excluded_tasks) == 2
    excluded_statuses = {ex.status for ex in res.excluded_tasks}
    assert "CONTRADICTED" in excluded_statuses
    assert "UNVERIFIABLE" in excluded_statuses


def test_task_selector_blocked_when_gate_is_not_release(clean_db, mock_released_meeting):
    db, repo = clean_db
    decision = repo.get_latest_release_decision(mock_released_meeting.id)
    decision.decision = "hold_for_review"
    db.commit()

    selector = TaskSelector(repo=repo)
    res = selector.select_tasks(mock_released_meeting.id)
    assert res.is_released is False
    assert res.gate_decision == "HOLD_FOR_REVIEW"
    assert len(res.buildable_tasks) == 0


# -------------------------------------------------------------------------- #
# 2. Prompt Compiler Tests                                                   #
# -------------------------------------------------------------------------- #

def test_prompt_compiler_fallback_and_privacy_refusal():
    v = Vault()
    m = v.tokenize("Alice secret contact alice@secret-corp.com phone 555-019-9999")

    compiler = PromptCompiler(enable_ollama=False, vault=v)

    task = BuildTask(
        task_id="t1",
        title="Web Page",
        description="Build page for [PERSON_1] at [ORGANIZATION_1]",
        deliverables=["index.html"],
    )
    crit = Criterion(
        id="c1",
        catalog_type="file_exists",
        target_file="index.html",
        description="index.html exists",
    )

    prompt = compiler.compile("mtg1", [task], [crit], "C:/test/workspace", iteration=1)
    assert prompt.source == "fallback"
    assert "index.html" in prompt.deliverables
    assert prompt.iteration == 1

    # Privacy scan failure when unmasked value appears
    leaky_task = BuildTask(
        task_id="t2",
        title="Leaky Task",
        description="Direct questions to alice@secret-corp.com immediately",
        deliverables=["contact.html"],
    )
    with pytest.raises(PrivacyRefusalError):
        compiler.compile("mtg1", [leaky_task], [crit], "C:/test/workspace")


def test_prompt_compiler_filters_invented_requirements():
    v = Vault()
    compiler = PromptCompiler(enable_ollama=False, vault=v)
    task = BuildTask(task_id="t1", title="Landing Page", description="Build landing page", deliverables=["index.html"])
    crit = Criterion(id="c1", catalog_type="file_exists", description="index.html exists")

    raw_reqs = [
        "Landing Page: Build landing page",
        "Invented: Setup decentralized blockchain payment rails with Ethereum smart contracts",
    ]
    filtered = compiler._filter_invented_requirements(raw_reqs, [task], [crit])
    assert len(filtered) == 1
    assert "Landing Page" in filtered[0]


# -------------------------------------------------------------------------- #
# 3. Criteria Catalog Tests                                                  #
# -------------------------------------------------------------------------- #

def test_criteria_catalog_generation_and_compilation():
    criteria = [
        normalize_criterion({"type": "file_exists", "target_file": "index.html", "desc": "index exists"}, 1),
        normalize_criterion({"type": "html_valid_structure", "target_file": "index.html", "desc": "valid html"}, 2),
        normalize_criterion({"type": "html_title_nonempty", "target_file": "index.html", "desc": "nonempty title"}, 3),
        normalize_criterion({"type": "html_form_has_labeled_inputs", "target_file": "contact.html", "desc": "form labels"}, 4),
        normalize_criterion({"type": "html_no_external_resources", "target_file": "index.html", "desc": "no cdn"}, 5),
        normalize_criterion({"type": "unmapped_crazy_check", "desc": "crazy check"}, 6),
    ]

    assert criteria[-1].catalog_type == "manual_review"

    code = generate_pytest_code(criteria, "mtg_unit_test")
    # Verify valid Python syntax
    compile(code, "test_acceptance.py", "exec")
    assert "def test_01_file_exists" in code
    assert "def test_06_manual_review" in code


# -------------------------------------------------------------------------- #
# 4. Vault Store Tests                                                       #
# -------------------------------------------------------------------------- #

def test_vault_store_encryption_roundtrip():
    v = Vault()
    m = v.tokenize("Confidential contact john.doe@example.com for Project Falcon")

    path = save_vault("run_roundtrip_test", v)
    assert path.exists()

    v_loaded = load_vault("run_roundtrip_test")
    assert v_loaded is not None
    assert "john.doe@example.com" in v_loaded.rehydrate(m.text)

    # Terminal deletion
    deleted = delete_vault("run_roundtrip_test")
    assert deleted is True
    assert load_vault("run_roundtrip_test") is None


# -------------------------------------------------------------------------- #
# 5. Local Evaluator Subprocess Tests                                        #
# -------------------------------------------------------------------------- #

def test_evaluator_catches_tamper_and_leaks(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create dummy index.html with unmasked secret email
    v = Vault()
    v.tokenize("Contact leak_target@secret-company.com for private terms")

    (workspace / "index.html").write_text("<html><body>leak_target@secret-company.com</body></html>", encoding="utf-8")

    # Create judge
    criteria = [normalize_criterion({"type": "file_exists", "target_file": "index.html", "desc": "exists"}, 1)]
    judge_file, judge_hash = save_acceptance_tests("mtg_eval_test", criteria)

    evaluator = LocalEvaluator(vault=v, timeout_seconds=10.0)

    # Agent reports modified judge
    tampered_judge = workspace / "tests_nomad" / "test_acceptance.py"
    tampered_judge.parent.mkdir(parents=True, exist_ok=True)
    tampered_judge.write_text("def test_fake(): assert True\n", encoding="utf-8")

    result = evaluator.evaluate(
        workspace_dir=workspace,
        judge_source_file=judge_file,
        expected_judge_hash=judge_hash,
        files_changed=["index.html"],
    )

    assert result.verdict == "fail"
    assert result.tamper_detected is True
    assert result.leak_detected is True


# -------------------------------------------------------------------------- #
# 6. State Machine & 3-Iteration Cap Tests                                   #
# -------------------------------------------------------------------------- #

def test_state_machine_hard_cap_at_3(clean_db, mock_released_meeting, tmp_path):
    db, _ = clean_db
    sm = LoopStateMachine(db_session=db)

    # Create brief
    brief = sm.get_or_create_brief(
        meeting_id=mock_released_meeting.id,
        workspace_override=tmp_path,
    )
    assert brief.status == "brief_issued"
    run_id = brief.loop_run_id

    # Iteration 1 report (fails)
    rep1 = sm.submit_and_evaluate_report(
        CodeReportSubmission(
            loop_run_id=run_id,
            agy_status="completed",
            summary="Attempt 1",
            files_changed=["index.html"],
            iteration=1,
        )
    )
    assert rep1.verdict == "revise"
    assert rep1.iteration == 1
    assert rep1.remaining_iterations == 2

    # Iteration 2 report (fails)
    rep2 = sm.submit_and_evaluate_report(
        CodeReportSubmission(
            loop_run_id=run_id,
            agy_status="completed",
            summary="Attempt 2",
            files_changed=["index.html"],
            iteration=2,
        )
    )
    assert rep2.verdict == "revise"
    assert rep2.iteration == 2
    assert rep2.remaining_iterations == 1

    # Iteration 3 report (fails)
    rep3 = sm.submit_and_evaluate_report(
        CodeReportSubmission(
            loop_run_id=run_id,
            agy_status="completed",
            summary="Attempt 3",
            files_changed=["index.html"],
            iteration=3,
        )
    )
    assert rep3.verdict == "failed_max_iterations"
    assert rep3.iteration == 3
    assert rep3.remaining_iterations == 0

    # Iteration 4 attempt is impossible (returns concluded / failed_max_iterations)
    rep4 = sm.submit_and_evaluate_report(
        CodeReportSubmission(
            loop_run_id=run_id,
            agy_status="completed",
            summary="Attempt 4",
            files_changed=["index.html"],
            iteration=4,
        )
    )
    assert rep4.verdict == "failed_max_iterations"
    assert rep4.remaining_iterations == 0


def test_state_machine_idempotent_duplicate_report(clean_db, mock_released_meeting, tmp_path):
    db, _ = clean_db
    sm = LoopStateMachine(db_session=db)

    brief = sm.get_or_create_brief(
        meeting_id=mock_released_meeting.id,
        workspace_override=tmp_path,
    )
    run_id = brief.loop_run_id

    sub = CodeReportSubmission(
        loop_run_id=run_id,
        agy_status="completed",
        summary="Initial submission",
        files_changed=["index.html"],
        iteration=1,
    )
    res1 = sm.submit_and_evaluate_report(sub)

    # Resubmit duplicate report for iteration 1
    res2 = sm.submit_and_evaluate_report(sub)

    assert res1.verdict == res2.verdict
    assert res1.ledger_entry_hash == res2.ledger_entry_hash


# -------------------------------------------------------------------------- #
# 7. Audit Ledger HMAC & Tamper Detection Tests                             #
# -------------------------------------------------------------------------- #

def test_audit_ledger_hmac_and_chain_verification(clean_db, mock_released_meeting):
    _, repo = clean_db

    key = "super-secret-hmac-ledger-key"

    # Record 3 events
    e1 = AuditLedger.record_event(repo, mock_released_meeting.id, "event_1", {"step": 1}, "hash1", key=key)
    e2 = AuditLedger.record_event(repo, mock_released_meeting.id, "event_2", {"step": 2}, "hash1", key=key)
    e3 = AuditLedger.record_event(repo, mock_released_meeting.id, "event_3", {"step": 3}, "hash1", key=key)

    entries = repo.list_ledger_entries(mock_released_meeting.id)
    is_valid, err = AuditLedger.verify_chain(entries, key=key)
    assert is_valid is True
    assert err is None

    # Tamper with an entry payload
    entries[1].payload_json = '{"step": 999}'
    is_valid_tampered, err_tampered = AuditLedger.verify_chain(entries, key=key)
    assert is_valid_tampered is False
    assert "Tampered entry detected" in err_tampered
