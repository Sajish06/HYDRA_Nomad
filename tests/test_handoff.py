import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import BASE_DIR
from app.adapters.mock_adapter import MockAdapter
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.claims.from_summary import extract_claims_from_summary
from app.pipeline import run_verification_pipeline

client = TestClient(app)

def prepare_fixture(fixture_file: str):
    adapter = MockAdapter()
    path = BASE_DIR / "data" / "mock" / fixture_file
    meeting = adapter.load(path)
    load_meeting_to_db(meeting)
    index_meeting(meeting.meeting_id)
    claims = extract_claims_from_summary(meeting)
    v = run_verification_pipeline(claims[0])
    return claims[0].claim_id

def test_handoff_release_policy():
    # Fixture 1: Verified -> 200
    c1_id = prepare_fixture("mock_meeting_01_verified.json")
    resp1 = client.get(f"/claims/{c1_id}/handoff")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["task_id"] == c1_id
    assert data1["effective_status"] == "VERIFIED"

    # Fixture 3: Verified -> 200
    c3_id = prepare_fixture("mock_meeting_03_implicit.json")
    resp3 = client.get(f"/claims/{c3_id}/handoff")
    assert resp3.status_code == 200

    # Fixture 2: Ambiguous -> 409
    c2_id = prepare_fixture("mock_meeting_02_ambiguous.json")
    resp2 = client.get(f"/claims/{c2_id}/handoff")
    assert resp2.status_code == 409

    # Fixture 4: Unsupported -> 409
    c4_id = prepare_fixture("mock_meeting_04_unsupported.json")
    resp4 = client.get(f"/claims/{c4_id}/handoff")
    assert resp4.status_code == 409

    # Fixture 5: Reversal (Ambiguous) -> 409
    c5_id = prepare_fixture("mock_meeting_05_reversal.json")
    resp5 = client.get(f"/claims/{c5_id}/handoff")
    assert resp5.status_code == 409
