"""Unit tests for Clean Room MCP server tool functions."""

import json
import uuid

import pytest

from backend.mcp_server.server import (
    ask_question_tool,
    get_conflicts_tool,
    get_verification_tool,
    review_decide_tool,
)
from backend.storage.database import SessionLocal, init_db
from backend.storage.repository import Repository


@pytest.fixture
def mcp_test_meeting():
    init_db()
    db = SessionLocal()
    repo = Repository(db)
    mid = f"m_mcp_{uuid.uuid4().hex[:8]}"
    meeting = repo.create_or_get_meeting(mid, "MCP Diligence Call")
    repo.update_meeting_data(
        meeting.id,
        transcript_sha256="mcphash123",
        raw_transcript="Raw transcript text.",
        raw_summary="Sarah Chen confirmed EBITDA of $4.2M.",
        status="synced",
    )
    # Save a verification result
    repo.save_verification_result(
        run_id="run_mcp_1",
        meeting_id=meeting.id,
        overall_status="verified",
        result_dict={
            "claims": [
                {
                    "id": "c1",
                    "text": "EBITDA was $4.2M",
                    "verdict": "supported",
                    "evidence": [],
                }
            ]
        },
    )
    m_id = str(meeting.id)
    db.close()
    return m_id


def test_mcp_get_verification(mcp_test_meeting):
    mid = mcp_test_meeting
    res_str = get_verification_tool(mid)
    data = json.loads(res_str)
    assert "claims" in data
    assert len(data["claims"]) == 1
    assert data["claims"][0]["verdict"] == "supported"


def test_mcp_get_conflicts(mcp_test_meeting):
    mid = mcp_test_meeting
    res_str = get_conflicts_tool(mid)
    conflicts = json.loads(res_str)
    assert isinstance(conflicts, list)


def test_mcp_ask_question_audience_masked(mcp_test_meeting):
    mid = mcp_test_meeting
    # Ask question for outside_counsel audience: should mask Sarah Chen into [PERSON_1]
    res_str = ask_question_tool(mid, "What was the EBITDA?", audience="outside_counsel")
    assert "[AUDIENCE: OUTSIDE_COUNSEL]" in res_str
    assert "Sarah Chen" not in res_str
    assert "[PERSON_" in res_str
    assert "$4.2M" in res_str


def test_mcp_review_decide():
    init_db()
    db = SessionLocal()
    repo = Repository(db)
    mid = f"m_mcp_rev_{uuid.uuid4().hex[:8]}"
    meeting = repo.create_or_get_meeting(mid, "Review Meeting")
    run = repo.create_processing_run(meeting.id)

    items = repo.create_review_items(
        [
            {
                "run_id": run.id,
                "meeting_id": meeting.id,
                "item_type": "claim",
                "reference_id": "c1",
                "original_text": "Bad claim",
                "issue_type": "contradiction",
            }
        ]
    )
    db.close()

    item_id = items[0].id
    res_str = review_decide_tool(item_id, action="approved")
    data = json.loads(res_str)
    assert data["item_id"] == item_id
    assert data["status"] == "approved"
