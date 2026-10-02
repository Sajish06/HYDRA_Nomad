"""Tests for Gatekeeper release decisions and reviewer loop."""

import pytest

from backend.processors.gate import Gatekeeper
from backend.schemas.release import CrossSourceConflict, GateDecisionType
from backend.schemas.verification import (
    ClaimItem,
    OverallVerificationStatus,
    Verdict,
    VerificationResult,
)
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository


@pytest.fixture
def clean_db():
    init_db()
    db = SessionLocal()
    yield db
    db.close()


def test_gate_holds_on_contradiction():
    claim = ClaimItem(
        id="c1",
        text="$50,000 approved",
        verdict=Verdict.CONTRADICTED,
        explanation="Transcript says fifteen thousand",
    )
    v_res = VerificationResult(
        meeting_id="m1",
        run_id="r1",
        overall_status=OverallVerificationStatus.REVIEW_REQUIRED,
        claims=[claim],
    )
    decision = Gatekeeper.evaluate("m1", "r1", v_res, conflicts=[])

    assert decision.decision == GateDecisionType.HOLD_FOR_REVIEW
    assert "c1" in decision.flagged_claim_ids
    assert len(decision.reasons) >= 1


def test_gate_holds_on_cross_source_conflict():
    claim = ClaimItem(id="c1", text="Clean claim", verdict=Verdict.SUPPORTED)
    v_res = VerificationResult(
        meeting_id="m1",
        run_id="r1",
        overall_status=OverallVerificationStatus.VERIFIED,
        claims=[claim],
    )
    conflict = CrossSourceConflict(
        id="conf_1",
        metric="EBITDA",
        transcript_value="4.2M",
        transcript_citation="transcript@00:01",
        doc_name="cim.md",
        doc_value="3.8M",
        doc_citation="cim.md:line 8",
        explanation="Discrepancy on EBITDA",
    )
    decision = Gatekeeper.evaluate("m1", "r1", v_res, conflicts=[conflict])

    assert decision.decision == GateDecisionType.HOLD_FOR_REVIEW
    assert "conf_1" in decision.flagged_conflict_ids


def test_gate_releases_when_clean():
    claim = ClaimItem(id="c1", text="Clean claim", verdict=Verdict.SUPPORTED)
    v_res = VerificationResult(
        meeting_id="m1",
        run_id="r1",
        overall_status=OverallVerificationStatus.VERIFIED,
        claims=[claim],
    )
    decision = Gatekeeper.evaluate("m1", "r1", v_res, conflicts=[])

    assert decision.decision == GateDecisionType.RELEASE
    assert len(decision.flagged_claim_ids) == 0


def test_gate_override_manual_approval():
    claim = ClaimItem(id="c1", text="Contradicted", verdict=Verdict.CONTRADICTED)
    v_res = VerificationResult(
        meeting_id="m1",
        run_id="r1",
        overall_status=OverallVerificationStatus.REVIEW_REQUIRED,
        claims=[claim],
    )
    decision = Gatekeeper.evaluate("m1", "r1", v_res, conflicts=[], human_approval="lead_partner@acme.com")

    assert decision.decision == GateDecisionType.RELEASE
    assert decision.overridden is True
    assert decision.approved_by == "lead_partner@acme.com"


def test_review_item_lifecycle_in_repository(clean_db):
    repo = Repository(clean_db)
    meeting = repo.create_or_get_meeting("m_rev_test", "Review Test Meeting")
    run = repo.create_processing_run(meeting.id)

    items = repo.create_review_items(
        [
            {
                "run_id": run.id,
                "meeting_id": meeting.id,
                "item_type": "claim",
                "reference_id": "c_bad_number",
                "original_text": "$50,000 approved for vendor.",
                "issue_type": "number_mismatch",
                "suggested_fix": "$15,000 approved for vendor.",
            }
        ]
    )
    assert len(items) == 1
    rev_id = items[0].id

    # Reviewer corrects the claim
    updated = repo.update_review_item(
        item_id=rev_id,
        status="corrected",
        corrected_text="$15,000 approved for vendor.",
        reviewer_notes="Verified against audio segment 1: 15k is the accurate number.",
    )
    assert updated.status == "corrected"
    assert updated.corrected_text == "$15,000 approved for vendor."
    assert updated.resolved_at is not None
