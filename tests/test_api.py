"""Tests for REST API endpoints and data access controls."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository


@pytest.fixture
def api_test_meeting():
    init_db()
    db = SessionLocal()
    repo = Repository(db)
    mid = f"m_api_{uuid.uuid4().hex[:8]}"
    meeting = repo.create_or_get_meeting(mid, "API Test Deal Call", duration_seconds=1200.0)
    repo.update_meeting_data(
        meeting.id,
        transcript_sha256="testsha256hash",
        raw_transcript="Confidential unmasked raw transcript content here.",
        raw_summary="Sarah Chen confirmed $4.2M EBITDA.",
        status="synced",
    )
    db.close()
    return meeting.id, mid


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_meetings_list_and_get(api_test_meeting):
    meeting_uuid, meetily_id = api_test_meeting

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        list_resp = await ac.get("/api/meetings")
        assert list_resp.status_code == 200
        meetings = list_resp.json()
        assert any(m["id"] == meeting_uuid for m in meetings)

        # GET single meeting
        get_resp = await ac.get(f"/api/meetings/{meeting_uuid}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == meeting_uuid
        assert data["title"] == "API Test Deal Call"
        # Privacy non-negotiable rule: Raw transcript must NOT be exposed by default!
        assert data.get("transcript") is None


@pytest.mark.asyncio
async def test_meeting_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/meetings/non_existent_id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_destinations_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/destinations")
    assert resp.status_code == 200
    assert "destinations" in resp.json()


@pytest.mark.asyncio
async def test_masking_diff_endpoint(api_test_meeting):
    meeting_uuid, _ = api_test_meeting
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/meetings/{meeting_uuid}/masking-diff?audience=outside_counsel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["audience"] == "outside_counsel"
    assert "diff_spans" in data
    assert "masked_text" in data


@pytest.mark.asyncio
async def test_ask_endpoint(api_test_meeting):
    meeting_uuid, _ = api_test_meeting
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/meetings/{meeting_uuid}/ask",
            json={"question": "What was the EBITDA?", "audience": "lender"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "citation" in data
    assert data["audience"] == "lender"


@pytest.mark.asyncio
async def test_tamper_ledger_endpoint(api_test_meeting):
    meeting_uuid, _ = api_test_meeting
    # Add a ledger entry to tamper
    db = SessionLocal()
    repo = Repository(db)
    from backend.processors.ledger import AuditLedger

    AuditLedger.record_event(
        repo=repo,
        meeting_id=meeting_uuid,
        event_type="test_event",
        payload={"data": "original"},
        transcript_sha256="testsha",
    )
    db.close()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"/api/meetings/{meeting_uuid}/tamper-ledger?index=0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "tampered"
    assert data["chain_valid"] is False
