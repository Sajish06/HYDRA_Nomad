"""Unit tests for MeetilyClient and SchemaAdapter with mocked HTTP responses."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from backend.meetily.client import MeetilyClient
from backend.meetily.errors import (
    MeetilyAuthError,
    MeetilyInvalidResponse,
    MeetilyNotFound,
    MeetilyServerError,
)
from backend.meetily.schema_adapter import MeetilySchemaAdapter
from backend.schemas.meeting import MeetingMetadata, MeetingSummary, MeetingTranscript


@pytest.fixture
def mock_client():
    return httpx.AsyncClient(base_url="http://127.0.0.1:8420")


@respx.mock
@pytest.mark.asyncio
async def test_health_check_ok(mock_client):
    respx.get("http://127.0.0.1:8420/health").respond(200, json={"status": "ok", "version": "1.11.0"})
    client = MeetilyClient(client=mock_client)
    res = await client.health()
    assert res["status"] == "ok"


@respx.mock
@pytest.mark.asyncio
async def test_get_meeting_success(mock_client):
    respx.get("http://127.0.0.1:8420/v1/meetings/m_123").respond(
        200,
        json={
            "id": "m_123",
            "title": "M&A Diligence Call",
            "duration": 1800,
            "has_transcript": True,
            "has_summary": True,
        },
    )
    client = MeetilyClient(client=mock_client)
    meta = await client.get_meeting("m_123")
    assert isinstance(meta, MeetingMetadata)
    assert meta.meetily_id == "m_123"
    assert meta.title == "M&A Diligence Call"
    assert meta.duration_seconds == 1800.0


@respx.mock
@pytest.mark.asyncio
async def test_get_transcript_and_summary_success(mock_client):
    respx.get("http://127.0.0.1:8420/v1/meetings/m_123/transcript").respond(
        200,
        json={
            "segments": [
                {"speaker": "Alice", "start": 0.0, "end": 10.5, "text": "Welcome to diligence call."},
                {"speaker": "Bob", "start": 11.0, "end": 20.0, "text": "EBITDA was 4.2 million."},
            ]
        },
    )
    respx.get("http://127.0.0.1:8420/v1/meetings/m_123/summary").respond(
        200,
        json={
            "summary_text": "Discussion on diligence and EBITDA of 4.2M.",
            "action_items": ["Alice to send financial models by Friday."],
            "key_decisions": ["Proceed to phase 2 diligence."],
        },
    )
    client = MeetilyClient(client=mock_client)

    transcript = await client.get_transcript("m_123")
    assert isinstance(transcript, MeetingTranscript)
    assert len(transcript.segments) == 2
    assert transcript.segments[1].speaker == "Bob"
    assert "4.2 million" in transcript.raw_text

    summary = await client.get_summary("m_123")
    assert isinstance(summary, MeetingSummary)
    assert "4.2M" in summary.summary_text
    assert len(summary.action_items) == 1


@respx.mock
@pytest.mark.asyncio
async def test_list_meetings_pagination(mock_client):
    respx.get("http://127.0.0.1:8420/v1/meetings").mock(
        side_effect=[
            httpx.Response(200, json={"items": [{"id": "m1", "title": "Call 1"}], "cursor": "c2"}),
            httpx.Response(200, json={"items": [{"id": "m2", "title": "Call 2"}], "cursor": None}),
        ]
    )
    client = MeetilyClient(client=mock_client)
    meetings = []
    async for m in client.iter_meetings(batch_size=1):
        meetings.append(m)

    assert len(meetings) == 2
    assert meetings[0].meetily_id == "m1"
    assert meetings[1].meetily_id == "m2"


@respx.mock
@pytest.mark.asyncio
async def test_auth_failure_401_403(mock_client):
    respx.get("http://127.0.0.1:8420/v1/meetings/m_unauth").respond(401, json={"error": "Unauthorized"})
    client = MeetilyClient(client=mock_client)
    with pytest.raises(MeetilyAuthError) as exc_info:
        await client.get_meeting("m_unauth")
    assert exc_info.value.status_code == 401


@respx.mock
@pytest.mark.asyncio
async def test_not_found_404(mock_client):
    respx.get("http://127.0.0.1:8420/v1/meetings/m_none").respond(404, json={"error": "Meeting not found"})
    client = MeetilyClient(client=mock_client)
    with pytest.raises(MeetilyNotFound):
        await client.get_meeting("m_none")


@respx.mock
@pytest.mark.asyncio
async def test_invalid_json_response(mock_client):
    respx.get("http://127.0.0.1:8420/v1/meetings/m_bad").respond(
        200, html="<html>Gateway timeout</html>"
    )
    client = MeetilyClient(client=mock_client)
    with pytest.raises(MeetilyInvalidResponse):
        await client.get_meeting("m_bad")


@respx.mock
@pytest.mark.asyncio
async def test_server_error_5xx_retry_and_succeed(mock_client):
    respx.get("http://127.0.0.1:8420/health").mock(
        side_effect=[
            httpx.Response(502, text="Bad Gateway"),
            httpx.Response(200, json={"status": "ok"}),
        ]
    )
    client = MeetilyClient(client=mock_client, backoff_factor=0.01)
    res = await client.health()
    assert res["status"] == "ok"


@respx.mock
@pytest.mark.asyncio
async def test_server_error_5xx_max_retries_fail(mock_client):
    respx.get("http://127.0.0.1:8420/health").respond(503, text="Service Unavailable")
    client = MeetilyClient(client=mock_client, max_retries=2, backoff_factor=0.01)
    with pytest.raises(MeetilyServerError):
        await client.health()


def test_schema_adapter_flat_text_fallback():
    raw_text = "This is a flat unsegmented transcript."
    transcript = MeetilySchemaAdapter.parse_transcript("m_flat", raw_text)
    assert len(transcript.segments) == 1
    assert transcript.segments[0].start_time is None
    assert transcript.segments[0].text == raw_text


def test_schema_snapshot_contract():
    snapshot_file = Path("docs/openapi.snapshot.json")
    if not snapshot_file.exists():
        pytest.skip("No openapi.snapshot.json exists. Run scripts/discover_api.py against live gateway to test.")
    with open(snapshot_file, "r", encoding="utf-8") as f:
        spec = json.load(f)
    assert "/health" in spec.get("paths", {})
