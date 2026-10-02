import pytest
from app.config import BASE_DIR
from app.adapters.mock_adapter import MockAdapter
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.claims.from_summary import extract_claims_from_summary
from app.pipeline import run_verification_pipeline
from app.models import Status, Reason

def run_fixture(fixture_name: str):
    adapter = MockAdapter()
    f_path = BASE_DIR / "data" / "mock" / fixture_name
    meeting = adapter.load(f_path)
    
    load_meeting_to_db(meeting, source="mock")
    index_meeting(meeting.meeting_id)
    
    claims = extract_claims_from_summary(meeting)
    assert len(claims) >= 1
    
    v = run_verification_pipeline(claims[0])
    return claims[0], v

def test_fixture_1_verified():
    claim, v = run_fixture("mock_meeting_01_verified.json")
    assert v.status == Status.VERIFIED
    assert v.gate_action == "PROCEED"
    assert Reason.CLEAN_SUPPORT in v.reasons
    assert v.final_state == "AFFIRMED"
    assert len(v.evidence_chain) >= 2

def test_fixture_2_ambiguous():
    claim, v = run_fixture("mock_meeting_02_ambiguous.json")
    assert v.status == Status.AMBIGUOUS
    assert v.gate_action == "HUMAN_REVIEW"
    assert Reason.DEFERRED in v.reasons
    assert v.final_state == "NEGATED"

def test_fixture_3_implicit():
    claim, v = run_fixture("mock_meeting_03_implicit.json")
    assert v.status == Status.VERIFIED
    assert v.gate_action == "PROCEED"
    assert v.resolved_claim is not None
    assert "investigate" in v.resolved_claim.lower()
    
    actor_slot = next((s for s in v.slots if s.slot == "actor"), None)
    assert actor_slot is not None
    assert actor_slot.status == "GROUNDED"

def test_fixture_4_unsupported():
    claim, v = run_fixture("mock_meeting_04_unsupported.json")
    assert v.status == Status.UNSUPPORTED
    assert v.gate_action == "BLOCK"
    assert (Reason.INFORM_ONLY in v.reasons or Reason.NO_RELEVANT_EVIDENCE in v.reasons)

def test_fixture_5_reversal():
    claim, v = run_fixture("mock_meeting_05_reversal.json")
    assert v.status == Status.AMBIGUOUS
    assert v.gate_action == "HUMAN_REVIEW"
    assert Reason.REVERSED in v.reasons
    assert v.final_state == "NEGATED"
    chain_idx = [e.idx for e in v.evidence_chain]
    assert 3 in chain_idx
