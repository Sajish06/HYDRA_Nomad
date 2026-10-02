import pytest
from app.adapters.mock_adapter import MockAdapter
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.retrieval.hybrid import retrieve_candidates
from app.models import Claim, ClaimType
from app.config import BASE_DIR

def test_retrieval_reversal_fixture5():
    adapter = MockAdapter()
    f_path = BASE_DIR / "data" / "mock" / "mock_meeting_05_reversal.json"
    meeting = adapter.load(f_path)
    
    load_meeting_to_db(meeting, source="mock")
    index_meeting(meeting.meeting_id)

    claim = Claim(
        claim_id="test_c5",
        meeting_id="DEMO_005",
        text="Use Redis.",
        source="SUMMARY",
        type=ClaimType.DECISION,
        object="Redis",
        action="use",
        normalized="Use Redis."
    )

    candidates = retrieve_candidates("DEMO_005", claim)
    retrieved_idx = [c["idx"] for c in candidates]
    
    # Crucial acceptance test: segment idx 3 (the reversal at last idx) MUST be retrieved
    assert 3 in retrieved_idx

def test_retrieval_antecedent_fixture3():
    adapter = MockAdapter()
    f_path = BASE_DIR / "data" / "mock" / "mock_meeting_03_implicit.json"
    meeting = adapter.load(f_path)
    
    load_meeting_to_db(meeting, source="mock")
    index_meeting(meeting.meeting_id)

    claim = Claim(
        claim_id="test_c3",
        meeting_id="DEMO_003",
        text="Bob will investigate Redis for rate limiting.",
        source="SUMMARY",
        type=ClaimType.ACTION,
        actor="Bob",
        action="investigate",
        object="Redis for rate limiting",
        normalized="Bob will investigate Redis for rate limiting."
    )

    candidates = retrieve_candidates("DEMO_003", claim)
    retrieved_idx = [c["idx"] for c in candidates]
    
    assert 0 in retrieved_idx
    assert 1 in retrieved_idx
