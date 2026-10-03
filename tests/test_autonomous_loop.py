"""Unit tests for the Autonomous Loop Orchestrator."""
import pytest
from unittest.mock import MagicMock, patch
from backend.processors.autonomous_loop import AutonomousLoopOrchestrator


def make_repo(decision_value="release"):
    repo = MagicMock()
    decision = MagicMock()
    decision.decision = decision_value
    decision.reasons_json = "[]"
    repo.get_latest_release_decision.return_value = decision
    repo.get_meeting_by_id.return_value = MagicMock(
        id="mtg_001",
        title="Test Meeting",
        raw_summary="- Build a FastAPI endpoint\n- Add PostgreSQL integration",
        transcript_sha256="abc123",
    )
    repo.list_output_artifacts.return_value = []  # No cloud_llm artifact
    return repo


def test_initialize_loop_blocked_when_no_release():
    repo = make_repo(decision_value="hold_for_review")
    orch = AutonomousLoopOrchestrator(repo=repo)
    result = orch.initialize_loop("mtg_001")
    assert result["status"] == "blocked"


def test_evaluate_test_results_pass():
    repo = make_repo()
    orch = AutonomousLoopOrchestrator(repo=repo)
    result = orch._evaluate_test_results(
        agy_status="success",
        test_results="2 passed in 0.03s",
        summary="Implemented the endpoint",
    )
    assert result is True


def test_evaluate_test_results_fail_on_error():
    repo = make_repo()
    orch = AutonomousLoopOrchestrator(repo=repo)
    result = orch._evaluate_test_results(
        agy_status="failure",
        test_results="FAILED test_requirement_01 - AssertionError",
        summary="Partial implementation",
    )
    assert result is False


def test_generate_acceptance_criteria_has_tests():
    repo = make_repo()
    orch = AutonomousLoopOrchestrator(repo=repo)
    criteria = orch._generate_acceptance_criteria(
        "mtg_001",
        "- Build a FastAPI endpoint\n- Add PostgreSQL integration"
    )
    assert "def test_requirement_" in criteria
    assert "pytest" in criteria
    assert "NotImplementedError" in criteria


def test_trip_circuit_breaker():
    repo = make_repo()
    orch = AutonomousLoopOrchestrator(repo=repo)
    meeting = repo.get_meeting_by_id("mtg_001")
    loop_run = MagicMock(id="run_001")
    report = MagicMock(id="rep_001", iteration=2, test_results="FAILED test_01")

    with patch("backend.processors.autonomous_loop.AuditLedger.record_event"):
        result = orch._trip_circuit_breaker(meeting, loop_run, report)

    assert result["status"] == "needs_intervention"
    assert "Circuit breaker triggered" in result["error_summary"]
    repo.update_loop_run.assert_called_once()
    assert meeting.status == "needs_intervention"


def test_generate_corrective_prompt():
    repo = make_repo()
    orch = AutonomousLoopOrchestrator(repo=repo)
    meeting = repo.get_meeting_by_id("mtg_001")
    report = MagicMock(
        summary="Initial attempt",
        test_results="AssertionError: Expected 200 but got 500"
    )
    prompt = orch._generate_corrective_prompt(meeting, report, iteration=0)
    assert "CORRECTIVE INSTRUCTIONS" in prompt
    assert "AssertionError" in prompt
    assert "Build a FastAPI endpoint" in prompt
