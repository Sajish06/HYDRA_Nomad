"""Tests for M&A business intelligence extraction and evidence relocation."""

import pytest

from backend.processors.extraction import IntelligenceExtractor
from backend.schemas.meeting import MeetingSummary, MeetingTranscript, TranscriptSegment


@pytest.fixture
def diligence_transcript():
    segments = [
        TranscriptSegment(
            segment_index=0,
            speaker="Sarah Chen",
            start_time=10.0,
            end_time=25.0,
            text="EBITDA was 4.2 million for the trailing twelve months, and revenue was 18 million.",
        ),
        TranscriptSegment(
            segment_index=1,
            speaker="Marcus Brody",
            start_time=30.0,
            end_time=50.0,
            text="We structured the deal as an asset purchase with a 10% holdback for indemnity.",
        ),
        TranscriptSegment(
            segment_index=2,
            speaker="David Vance",
            start_time=55.0,
            end_time=75.0,
            text="Our primary risk is customer concentration: two enterprise accounts make up 45% of ARR.",
        ),
        TranscriptSegment(
            segment_index=3,
            speaker="Priya Sharma",
            start_time=80.0,
            end_time=95.0,
            text="I will send the updated customer cohort analysis by Friday.",
        ),
    ]
    raw = " ".join(s.text for s in segments)
    return MeetingTranscript(
        meeting_id="m_diligence",
        segments=segments,
        raw_text=raw,
        sha256_hash="hash-123",
    )


def test_baseline_extraction(diligence_transcript):
    extractor = IntelligenceExtractor()
    summary = MeetingSummary(meeting_id="m_diligence", summary_text="Diligence overview")

    intel = extractor.extract_baseline(diligence_transcript, summary, run_id="run_intel_1")

    # Financial checks
    assert len(intel.financial) >= 1
    ebitda_item = next(f for f in intel.financial if f.metric_or_topic == "EBITDA")
    assert "4.2 million" in ebitda_item.value_description
    assert ebitda_item.evidence_verified is True

    # Deal checks
    assert len(intel.deal) >= 1
    assert any("asset purchase" in d.value_description.lower() for d in intel.deal)

    # Risk checks
    assert len(intel.risks) >= 1
    assert any("concentration" in r.value_description.lower() for r in intel.risks)

    # Actions checks
    assert len(intel.decisions_actions) >= 1
    assert any("will send" in a.value_description.lower() for a in intel.decisions_actions)


def test_ai_draft_extraction_validation(diligence_transcript):
    extractor = IntelligenceExtractor()
    draft = {
        "financial": [
            {
                "metric_or_topic": "EBITDA",
                "value_description": "4.2 million",
                "period": "TTM",
                "confidence": 0.95,
                "evidence_quote": "EBITDA was 4.2 million for the trailing twelve months",
            }
        ],
        "risks": [
            {
                "metric_or_topic": "Customer Concentration",
                "value_description": "Two accounts represent 45% ARR",
                "confidence": 0.9,
                "evidence_quote": "Our primary risk is customer concentration: two enterprise accounts make up 45% of ARR.",
            }
        ],
    }

    result = extractor.process_ai_draft(draft, diligence_transcript, "m_diligence", "run_ai_intel")
    assert len(result.financial) == 1
    assert result.financial[0].evidence_verified is True
    assert result.financial[0].evidence.speaker == "Sarah Chen"
    assert len(result.risks) == 1
    assert result.risks[0].evidence_verified is True
    assert result.risks[0].evidence.speaker == "David Vance"
