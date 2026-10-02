"""Tests for cross-source document discrepancy checks."""

import pytest

from backend.processors.crosscheck import CrossCheckEngine
from backend.schemas.meeting import MeetingTranscript, TranscriptSegment
from backend.sources.local_folder import LocalFolderSource


@pytest.fixture
def mock_diligence_source(tmp_path):
    cim_content = (
        "# Confidential Information Memorandum\n"
        "## Northwind Analytics\n"
        "Adjusted EBITDA (FY23): $3.8M\n"
        "Revenue: $18.0M\n"
    )
    (tmp_path / "cim.md").write_text(cim_content, encoding="utf-8")
    return LocalFolderSource(directory_path=tmp_path)


def test_ebitda_conflict_found(mock_diligence_source):
    engine = CrossCheckEngine(doc_source=mock_diligence_source)
    # Transcript says EBITDA was 4.2 million, but CIM says $3.8M
    segments = [
        TranscriptSegment(
            segment_index=0,
            speaker="Sarah Chen",
            start_time=15.0,
            end_time=30.0,
            text="EBITDA was 4.2 million for the last fiscal year.",
        )
    ]
    transcript = MeetingTranscript(
        meeting_id="m1",
        segments=segments,
        raw_text="EBITDA was 4.2 million for the last fiscal year.",
        sha256_hash="hash",
    )

    conflicts = engine.cross_check(transcript)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.metric == "EBITDA"
    assert c.doc_name == "cim.md"
    assert "3.8M" in c.doc_value
    assert "4.2 million" in c.transcript_value
    assert "cim.md:line 3" in c.doc_citation


def test_matching_metric_produces_no_conflict(mock_diligence_source):
    engine = CrossCheckEngine(doc_source=mock_diligence_source)
    # Transcript matches CIM: Revenue was 18 million
    segments = [
        TranscriptSegment(
            segment_index=0,
            speaker="Sarah Chen",
            start_time=15.0,
            end_time=30.0,
            text="Revenue was 18.0 million.",
        )
    ]
    transcript = MeetingTranscript(
        meeting_id="m1",
        segments=segments,
        raw_text="Revenue was 18.0 million.",
        sha256_hash="hash",
    )

    conflicts = engine.cross_check(transcript)
    assert len(conflicts) == 0


def test_missing_metric_produces_no_conflict(mock_diligence_source):
    engine = CrossCheckEngine(doc_source=mock_diligence_source)
    # Transcript discusses an unrelated topic (e.g. office lease) not in CIM
    segments = [
        TranscriptSegment(
            segment_index=0,
            speaker="David Vance",
            start_time=5.0,
            end_time=20.0,
            text="We extended the headquarters lease by two years.",
        )
    ]
    transcript = MeetingTranscript(
        meeting_id="m1",
        segments=segments,
        raw_text="We extended the headquarters lease by two years.",
        sha256_hash="hash",
    )

    conflicts = engine.cross_check(transcript)
    assert len(conflicts) == 0
