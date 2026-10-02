from fastapi.testclient import TestClient
from pathlib import Path
import json
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/masking/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["layer_1_semantic"] == "active"
    assert data["layer_2_deterministic_firewall"] == "active"

def test_process_meeting_endpoint():
    fixture_path = Path("tests/fixtures/mock_meetings/mock_handoff_from_teammate1.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    response = client.post("/masking/process-verified-meeting", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["meeting_id"] == "MEET-20261001-01"
    assert len(data["agent_payloads"]) == 1
    assert len(data["role_briefs"]) == 3

    # Assert agent payload has zero leaks
    agent_text = " ".join(data["agent_payloads"][0]["intentions"] + data["agent_payloads"][0]["things_to_implement"]).lower()
    assert "negotiating with another company" not in agent_text
    assert "two new markets" not in agent_text

if __name__ == "__main__":
    test_health_endpoint()
    test_process_meeting_endpoint()
    print("FASTAPI ENDPOINTS TEST PASSED!")
