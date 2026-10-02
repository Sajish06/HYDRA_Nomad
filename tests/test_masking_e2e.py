import pytest
from pathlib import Path
from app.masking import PrivacyMaskingEngine

def test_privacy_masking_e2e():
    fixture_path = Path("tests/fixtures/mock_meetings/mock_handoff_from_teammate1.json")
    output_md = Path("tests/scratch/test_verified_tasks.md")
    
    engine = PrivacyMaskingEngine(vault_dir="tests/scratch/vaults", cache_dir="tests/scratch/llm_cache")
    result = engine.process_verified_tasks(
        handoff_data=fixture_path,
        output_md_path=output_md
    )
    
    # Assertions
    assert result.meeting_id == "MEET-20261001-01"
    assert len(result.agent_payloads) == 1
    assert len(result.audit_records) == 1
    assert output_md.exists()

    # Verify deliverables are present in the payload
    payload = result.agent_payloads[0]
    assert len(payload.things_to_implement) == 3
    assert any("BACKEND" in t for t in payload.things_to_implement)
    assert any("FRONTEND" in t for t in payload.things_to_implement)
    assert any("QA" in t for t in payload.things_to_implement)
    
    # Verify confidential business strategy is NOT in the downstream payload
    payload_dump = " ".join(payload.intentions + payload.things_to_implement + payload.technical_context).lower()
    assert "negotiating with another company" not in payload_dump
    assert "two new markets" not in payload_dump

    # Verify audit record kept it locally
    audit = result.audit_records[0]
    assert audit.confidential_context_detected is True
    assert len(audit.isolated_business_secrets) > 0

if __name__ == "__main__":
    test_privacy_masking_e2e()
    print("ALL TESTS PASSED SUCCESSFULLY!")

