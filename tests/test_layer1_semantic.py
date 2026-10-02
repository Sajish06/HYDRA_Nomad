import pytest
from pathlib import Path
from app.masking import (
    SemanticDecomposer,
    PrivacyMaskingEngine,
    MeetingHandoff,
    LeakInspector,
    SecurityLeakException,
    AgentTaskPayload
)

def test_layer1_strict_separation_of_agent_payload_and_audit():
    fixture_path = Path("tests/fixtures/mock_meetings/mock_handoff_from_teammate1.json")
    handoff = MeetingHandoff.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    commitment = handoff.verified_commitments[0]
    
    decomposer = SemanticDecomposer(cache_dir="tests/scratch/llm_cache")
    agent_payload, audit_record = decomposer.process_commitment(commitment, vault_session_id="TEST-01")
    
    # 1. Agent Payload: Must contain only clean technical specs
    assert len(agent_payload.intentions) > 0
    assert len(agent_payload.things_to_implement) == 3
    assert any(t.startswith("BACKEND:") for t in agent_payload.things_to_implement)
    assert any(t.startswith("FRONTEND:") for t in agent_payload.things_to_implement)
    assert any(t.startswith("QA:") for t in agent_payload.things_to_implement)
    
    # 2. Agent Payload: MUST NOT contain business secrets
    payload_dump = " ".join(
        agent_payload.intentions +
        agent_payload.things_to_implement +
        agent_payload.technical_context
    ).lower()
    
    assert "negotiating with another company" not in payload_dump
    assert "expanding into two new markets" not in payload_dump
    assert "internal sales information" not in payload_dump
    assert "arjun:" not in payload_dump
    assert "maya:" not in payload_dump
    
    # 3. Leak Inspector validation
    is_clean, violations = LeakInspector.inspect_agent_payload(agent_payload)
    assert is_clean is True
    assert len(violations) == 0
    
    # 4. Internal Audit Record: Correctly captures the isolated business secrets
    assert audit_record.confidential_context_detected is True
    assert len(audit_record.isolated_business_secrets) > 0
    secret_text = " ".join([e.value for e in audit_record.isolated_business_secrets]).lower()
    assert "negotiating with another company" in secret_text

def test_leak_inspector_catches_violations():
    # Construct a deliberately leaking payload
    leaking_payload = AgentTaskPayload(
        task_id="TASK-BAD",
        intentions=["We are negotiating with another company so restrict revenue metrics."],
        things_to_implement=["BACKEND: Update API endpoints"],
        technical_context=["Enforce at API layer"]
    )
    
    is_clean, violations = LeakInspector.inspect_agent_payload(leaking_payload)
    assert is_clean is False
    assert len(violations) > 0
    
    with pytest.raises(SecurityLeakException):
        LeakInspector.assert_clean_payload(leaking_payload)

def test_engine_generates_clean_agent_markdown():
    fixture_path = Path("tests/fixtures/mock_meetings/mock_handoff_from_teammate1.json")
    output_md = Path("tests/scratch/test_clean_agent_tasks.md")
    
    engine = PrivacyMaskingEngine(
        vault_dir="tests/scratch/vaults",
        cache_dir="tests/scratch/llm_cache"
    )
    result = engine.process_verified_tasks(
        handoff_data=fixture_path,
        output_md_path=output_md
    )
    
    assert len(result.agent_payloads) == 1
    assert len(result.role_briefs) == 3
    assert output_md.exists()
    
    content = output_md.read_text(encoding="utf-8")
    assert "Verified Technical Specifications (Sanitized for Downstream AI)" in content
    assert "1. Intentions (Technical Objective)" in content
    assert "2. Things to Implement (Structured Deliverables)" in content
    assert "3. Technical Context (Prerequisites & Constraints)" in content
    assert "4. Role-Specific Briefs" in content
    assert "BACKEND — Assignee: Ravi" in content
    
    # Assert ZERO confidential leaks in markdown
    assert "negotiating with another company" not in content.lower()
    assert "two new markets" not in content.lower()
    assert "internal sales information" not in content.lower()

if __name__ == "__main__":
    test_layer1_strict_separation_of_agent_payload_and_audit()
    test_leak_inspector_catches_violations()
    test_engine_generates_clean_agent_markdown()
    print("ALL TESTS PASSED SUCCESSFULLY!")
