import pytest
from app.masking import (
    DeterministicFirewall,
    EntityVault,
    AgentTaskPayload,
    mask_text_with_rules
)

def test_layer2_credential_and_pii_regex_scrubbing():
    vault = EntityVault(session_id="REGEX_TEST_01", storage_dir="tests/scratch/vaults")

    raw_text = (
        "Connect using postgres://user:secretpass@db.corp.lan:5432/prod and AWS key AKIAIOSFODNN7EXAMPLE. "
        "Use OpenAI key sk-1234567890abcdef1234567890abcdef. "
        "Send logs to security-team@company.com or call +919876543210. "
        "Host at 10.0.4.15 on api.internal. "
        "Target compensation is $185,000 with a 15% discount."
    )

    clean_text, entries = mask_text_with_rules(raw_text, vault)

    # 1. Assert all sensitive values are masked
    assert "AKIAIOSFODNN7EXAMPLE" not in clean_text
    assert "sk-1234567890abcdef1234567890abcdef" not in clean_text
    assert "postgres://user:secretpass@db.corp.lan:5432/prod" not in clean_text
    assert "security-team@company.com" not in clean_text
    assert "+919876543210" not in clean_text
    assert "10.0.4.15" not in clean_text
    assert "$185,000" not in clean_text
    assert "15% discount" not in clean_text

    # 2. Assert tokens were inserted
    assert "[AWS_ACCESS_KEY_1]" in clean_text
    assert "[API_KEY_1]" in clean_text
    assert "[DB_CONNECTION_URI_1]" in clean_text
    assert "[EMAIL_1]" in clean_text
    assert "[PHONE_1]" in clean_text
    assert "[IP_ADDR_1]" in clean_text
    assert "[FINANCIAL_AMOUNT_1]" in clean_text
    assert "[STRATEGIC_PERCENTAGE_1]" in clean_text

    # 3. Assert Vault can perfectly re-hydrate (unmask)
    unmasked = vault.unmask_text(clean_text)
    assert "AKIAIOSFODNN7EXAMPLE" in unmasked
    assert "security-team@company.com" in unmasked
    assert "$185,000" in unmasked

def test_deterministic_firewall_sanitizes_agent_payload():
    vault = EntityVault(session_id="FIREWALL_TEST_02", storage_dir="tests/scratch/vaults")

    # Construct payload with sensitive credentials accidentally left in requirements
    payload = AgentTaskPayload(
        task_id="TASK-FIREWALL-001",
        intentions=["Update analytics API for user bob.smith@example.com with salary $210,000."],
        things_to_implement=[
            "BACKEND: Deploy DB migration on postgres://admin:P@ssw0rd1@db.internal:5432/metrics",
            "FRONTEND: Update dashboard component on 192.168.1.10"
        ],
        technical_context=["Use service account with key AKIA1111222233334444 on api.internal."],
        deadline="Friday"
    )

    clean_payload, audit_entries = DeterministicFirewall.sanitize_agent_payload(payload, vault)

    assert len(audit_entries) > 0

    # Assert no secrets in intentions
    assert "bob.smith@example.com" not in clean_payload.intentions[0]
    assert "$210,000" not in clean_payload.intentions[0]
    assert "[EMAIL_1]" in clean_payload.intentions[0]
    assert "[FINANCIAL_AMOUNT_1]" in clean_payload.intentions[0]

    # Assert no secrets in things_to_implement
    assert "postgres://admin:P@ssw0rd1@db.internal:5432/metrics" not in clean_payload.things_to_implement[0]
    assert "[DB_CONNECTION_URI_1]" in clean_payload.things_to_implement[0]
    assert "192.168.1.10" not in clean_payload.things_to_implement[1]
    assert "[IP_ADDR_1]" in clean_payload.things_to_implement[1]

    # Assert no secrets in technical_context
    assert "AKIA1111222233334444" not in clean_payload.technical_context[0]
    assert "[AWS_ACCESS_KEY_1]" in clean_payload.technical_context[0]

if __name__ == "__main__":
    test_layer2_credential_and_pii_regex_scrubbing()
    test_deterministic_firewall_sanitizes_agent_payload()
    print("ALL LAYER 2 DETERMINISTIC FIREWALL TESTS PASSED!")
