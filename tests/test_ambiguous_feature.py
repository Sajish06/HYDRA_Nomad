"""Test suite for ambiguous tasks feature, evidence chain display, and acceptance workflow."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_clay_frontend_contains_review_board_and_actions():
    """Verify that the clay neo-morphism UI includes the side-by-side tasks review board."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    
    # Assert side-by-side review board structure
    assert 'id="tasks-board-card"' in html
    assert 'id="verified-tasks-list"' in html
    assert 'id="ambiguous-tasks-list"' in html
    assert 'id="badge-verified-count"' in html
    assert 'id="badge-ambiguous-count"' in html
    
    # Assert JavaScript action handlers and evidence chain logic
    assert "function renderTasksBoard" in html
    assert "function acceptTask" in html
    assert "function rejectTask" in html
    assert "evidence-chain-box" in html
    assert "btn-accept" in html
    assert "btn-reject" in html

def test_pipeline_returns_ambiguous_tasks_with_evidence_chain():
    """Verify that verify-and-mask pipeline returns ambiguous tasks with evidence chain."""
    mock_file = Path("data/mock/mock_meeting_02_ambiguous.json")
    assert mock_file.exists()

    with open(mock_file, "rb") as f_t, open(mock_file, "rb") as f_s:
        resp = client.post(
            "/api/pipeline/verify-and-mask",
            files={
                "transcript_file": ("transcript.json", f_t, "application/json"),
                "summary_file": ("summary.json", f_s, "application/json")
            }
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert "verified_tasks" in data
    assert "ambiguous_tasks" in data
    assert data["ambiguous_tasks_count"] >= 1
    
    ambig = data["ambiguous_tasks"][0]
    assert ambig["status"] == "AMBIGUOUS"
    assert "task_text" in ambig
    assert "explanation" in ambig
    assert "evidence_chain" in ambig
    assert len(ambig["evidence_chain"]) >= 1
    
    # Check evidence chain quotes and attribution
    evidence = ambig["evidence_chain"][0]
    assert "speaker" in evidence
    assert "quote" in evidence
    assert len(evidence["quote"]) > 0
    assert "stance" in evidence

    # Check proposed_task for immediate promotion to verified tasks
    assert "proposed_task" in ambig
    assert "task_id" in ambig["proposed_task"]
    assert "intentions" in ambig["proposed_task"]
    assert "things_to_implement" in ambig["proposed_task"]
