import io
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_frontend_clay_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "NOMAD" in resp.text or "Verification" in resp.text

def test_pipeline_missing_files_error():
    # Attempting to call without compulsory files
    resp = client.post("/api/pipeline/verify-and-mask")
    assert resp.status_code == 422

def test_pipeline_verify_and_mask_e2e():
    transcript_path = Path("tests/fixtures/mock_meetings/transcript_1_customer_analytics.json")
    summary_path = Path("tests/fixtures/mock_meetings/mock_handoff_from_teammate1.json")

    with open(transcript_path, "rb") as t_f, open(summary_path, "rb") as s_f:
        resp = client.post(
            "/api/pipeline/verify-and-mask",
            files={
                "transcript_file": ("transcript.json", t_f, "application/json"),
                "summary_file": ("summary.json", s_f, "application/json")
            }
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert "verified_tasks" in data
    assert len(data["verified_tasks"]) > 0
