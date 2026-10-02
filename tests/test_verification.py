"""Tests for claim verification, spoken-number normalization, and local transcript relocation."""

import pytest

from backend.processors.verification import VerificationEngine
from backend.schemas.meeting import MeetingSummary, MeetingTranscript, TranscriptSegment
from backend.schemas.verification import OverallVerificationStatus, Verdict


@pytest.fixture
def sample_transcript():
    segments = [
        TranscriptSegment(
            segment_index=0,
            speaker="Sarah Chen",
            start_time=12.0,
            end_time=25.0,
            text="Our EBITDA was 4.2 million for the last fiscal year.",
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
        TranscriptSegment(
            segment_index=3,
            speaker="David Vance",
            start_time=60.0,
            end_time=80.0,
            text="Our top two enterprise clients represent significant concentration risk.",
        ),
    ]
    raw = " ".join(s.text for s in segments)
    return MeetingTranscript(
        meeting_id="m_test",
        segments=segments,
        raw_text=raw,
        sha256_hash="fake-hash",
    )


def test_verification_supported_claim(sample_transcript):
    summary = MeetingSummary(
        meeting_id="m_test",
        summary_text="The company generated $4.2M EBITDA last year.",
        action_items=[],
    )
    engine = VerificationEngine()
    result = engine.verify_baseline(summary, sample_transcript, run_id="run_1")

    assert len(result.claims) >= 1
    c1 = result.claims[0]
    assert c1.verdict == Verdict.SUPPORTED
    assert c1.evidence_verified is True
    assert "preliminary" in c1.flags


def test_verification_contradicted_number_mismatch_spoken(sample_transcript):
    # Summary claims $50,000, while transcript stated "fifteen thousand"
    summary = MeetingSummary(
        meeting_id="m_test",
        summary_text="Sarah Chen approved $50,000 for vendor expenditures.",
        action_items=[],
    )
    engine = VerificationEngine()
    result = engine.verify_baseline(summary, sample_transcript, run_id="run_2")

    c1 = result.claims[0]
    assert c1.verdict == Verdict.CONTRADICTED
    assert "number_mismatch" in c1.flags
    assert result.overall_status == OverallVerificationStatus.REVIEW_REQUIRED


def test_invented_ai_quote_downgraded_by_local_relocation(sample_transcript):
    engine = VerificationEngine()
    draft_claims = [
        {
            "id": "c_ai_1",
            "text": "The company operates 500 global offices.",
            "claim_type": "claim",
            "verdict": "supported",
            "confidence": 0.99,
            "explanation": "Claimed by AI verifier.",
            "evidence": [
                {
                    "text": "We operate over 500 offices in London and Tokyo.",
                    "speaker": "Sarah Chen",
                    "timestamp": "00:01:00",
                }
            ],
        }
    ]
    summary = MeetingSummary(meeting_id="m_test", summary_text="500 global offices")

    result = engine.process_ai_draft(draft_claims, summary, sample_transcript, run_id="run_3")
    c1 = result.claims[0]
    # Local relocation must catch that "We operate over 500 offices in London..." does not exist in local transcript!
    assert c1.verdict == Verdict.UNVERIFIABLE
    assert "evidence_not_found" in c1.flags
    assert c1.evidence_verified is False


def test_mandatory_number_override_on_ai_hallucination(sample_transcript):
    engine = VerificationEngine()
    # AI draft falsely claims $50,000 is supported
    draft_claims = [
        {
            "id": "c_ai_2",
            "text": "$50,000 approved for software vendors.",
            "claim_type": "claim",
            "verdict": "supported",  # Hallucinated verdict
            "confidence": 0.95,
            "evidence": [
                {
                    "text": "I approve the fifteen thousand dollars vendor expenditure.",
                    "speaker": "Sarah Chen",
                    "timestamp": "00:00:26",
                }
            ],
        }
    ]
    summary = MeetingSummary(meeting_id="m_test", summary_text="$50,000 approved")

    result = engine.process_ai_draft(draft_claims, summary, sample_transcript, run_id="run_4")
    c1 = result.claims[0]
    # Mandatory deterministic number check must override AI's "supported" to "contradicted"!
    assert c1.verdict == Verdict.CONTRADICTED
    assert "number_mismatch" in c1.flags


def test_action_item_wrong_owner_flagged(sample_transcript):
    # Transcript says: "Priya sends customer concentration data by Friday"
    # Summary says: "David Vance sends customer concentration data by Friday"
    summary = MeetingSummary(
        meeting_id="m_test",
        summary_text="Diligence review meeting.",
        action_items=["David Vance sends customer concentration data by Friday."],
    )
    engine = VerificationEngine()
    result = engine.verify_baseline(summary, sample_transcript, run_id="run_5")

    # Find action item claim
    action_claims = [c for c in result.claims if c.claim_type == "action_item"]
    assert len(action_claims) == 1
    ac = action_claims[0]
    assert "owner_unverified" in ac.flags
    assert ac.owner_verified is False


def test_omissions_detected(sample_transcript):
    # Summary omits customer concentration risk
    summary = MeetingSummary(
        meeting_id="m_test",
        summary_text="The company generated $4.2M EBITDA.",
        action_items=[],
    )
    engine = VerificationEngine()
    result = engine.verify_baseline(summary, sample_transcript, run_id="run_6")

    assert len(result.omissions) >= 1
    assert any("concentration" in o.text.lower() for o in result.omissions)
