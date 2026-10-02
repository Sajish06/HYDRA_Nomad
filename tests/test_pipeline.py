"""End-to-end integration tests for the processing pipeline and review loop."""

import uuid

import pytest

from backend.processors.pipeline import PipelineOrchestrator
from backend.schemas.meeting import MeetingSummary, MeetingTranscript, TranscriptSegment
from backend.schemas.release import GateDecisionType
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository


@pytest.fixture
def pipeline_db():
    init_db()
    db = SessionLocal()
    yield db
    db.close()


@pytest.mark.asyncio
async def test_pipeline_end_to_end_hold_then_resume(pipeline_db):
    repo = Repository(pipeline_db)
    mid = f"m_pipe_{uuid.uuid4().hex[:8]}"
    meeting = repo.create_or_get_meeting(mid, "Pipeline Test Meeting")

    # Transcript with EBITDA 4.2M and $15,000 approval
    segments = [
        TranscriptSegment(
            segment_index=0,
            speaker="Sarah Chen",
            start_time=10.0,
            end_time=25.0,
            text="EBITDA was 4.2 million for the last fiscal year.",
        ),
        TranscriptSegment(
            segment_index=1,
            speaker="Sarah Chen",
            start_time=26.0,
            end_time=38.0,
            text="I approve the fifteen thousand dollars vendor expenditure.",
        ),
        TranscriptSegment(
            segment_index=2,
            speaker="David Vance",
            start_time=40.0,
            end_time=55.0,
            text="Priya sends customer concentration data by Friday.",
        ),
    ]
    raw_t = " ".join(s.text for s in segments)
    transcript = MeetingTranscript(
        meeting_id=meeting.id,
        segments=segments,
        raw_text=raw_t,
        sha256_hash="pipe_test_sha256",
    )

    # Summary with intentional error ($50,000 instead of fifteen thousand)
    summary = MeetingSummary(
        meeting_id=meeting.id,
        summary_text="EBITDA was 4.2 million. Sarah Chen approved $50,000 for vendor.",
        action_items=["Priya sends customer concentration data by Friday."],
    )

    orchestrator = PipelineOrchestrator(repo=repo)

    # 1. First execution: should result in HOLD_FOR_REVIEW due to $50,000 contradiction
    run, decision, v_res, leak_rep = await orchestrator.execute_run(
        meeting.id, transcript, summary
    )

    assert decision.decision == GateDecisionType.HOLD_FOR_REVIEW
    assert len(decision.flagged_claim_ids) >= 1
    # Check review items created in database
    review_items = repo.list_review_items(meeting.id)
    assert len(review_items) >= 1

    # 2. Human reviewer corrects the claim: replaces $50,000 with $15,000
    for it in review_items:
        repo.update_review_item(
            item_id=it.id,
            status="corrected",
            corrected_text="Sarah Chen approved $15,000 for vendor.",
            reviewer_notes="Corrected $50,000 to $15,000 per transcript quote.",
        )

    # 3. Resume pipeline after human review
    run2, decision2, v_res2, leak_rep2 = await orchestrator.resume_after_review(
        meeting_id=meeting.id,
        transcript=transcript,
        summary=summary,
        reviewer_name="Partner Reviewer",
    )

    assert decision2.decision == GateDecisionType.RELEASE
    assert decision2.overridden is True
    assert leak_rep2 is not None
    assert leak_rep2.all_passed is True

    # Verify 5 audience outputs were produced
    artifacts = repo.list_output_artifacts(meeting.id)
    assert len(artifacts) == 5

    # Verify ledger entries exist and verify cleanly
    entries = repo.list_ledger_entries(meeting.id)
    assert len(entries) >= 4
    from backend.processors.ledger import AuditLedger

    is_valid, err = AuditLedger.verify_chain(entries)
    assert is_valid is True
    assert err is None
