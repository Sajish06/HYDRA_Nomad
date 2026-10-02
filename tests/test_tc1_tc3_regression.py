import pytest
from app.masking import (
    PrivacyMaskingEngine,
    MeetingHandoff,
    VerifiedCommitment,
    Assignee,
    LeakInspector
)

def test_tc1_regression_expectations():
    """
    TC1 Regression Test:
    Customer analytics dashboard with confidential business context & PII.
    """
    meeting = MeetingHandoff(
        meeting_id="MEET-TC1-TEST",
        meeting_title="Customer Analytics Dashboard",
        verified_commitments=[
            VerifiedCommitment(
                task_id="TASK-TC1-01",
                raw_requirement="We need the customer analytics dashboard ready by November 15.",
                assignees=[
                    Assignee(name="Ravi", role="BACKEND", assigned_work="Enforce authorization at the API layer and return HTTP 403 when an unauthorized role accesses restricted endpoints.", deadline="November 15"),
                    Assignee(name="Neha", role="FRONTEND", assigned_work="Hide the revenue and margin sections for users who don't have permission and show an appropriate 403 state when the API rejects the request.", deadline="November 15"),
                    Assignee(name="Arjun", role="QA", assigned_work="Create test cases covering ADMIN, FINANCE, MANAGER and USER access.", deadline="November 15"),
                ],
                evidence_context_quotes=[
                    "Priya (Product Manager): We need the customer analytics dashboard ready by November 15.",
                    "Ravi (Backend): The existing system already has ADMIN, FINANCE, MANAGER and USER roles. I'll enforce authorization at the API layer and return HTTP 403 when an unauthorized role accesses restricted endpoints.",
                    "Neha (Frontend): I'll hide the revenue and margin sections for users who don't have permission and show an appropriate 403 state when the API rejects the request.",
                    "Arjun (QA): I'll create test cases covering ADMIN, FINANCE, MANAGER and USER access.",
                    "Priya: The dashboard needs to support around 10,000 concurrent users during normal operation. That number is a technical capacity requirement, not a customer count.",
                    "Priya: For context, our current customer base is 8,450 and management expects roughly 35% growth after the upcoming campaign. That campaign has not been announced yet, so this information should remain internal.",
                    "Priya: We're also negotiating a new enterprise contract with Bharat Retail Solutions. They are currently considering leaving their existing vendor because of pricing.",
                    "Ravi: Do I need to know any of that for implementation?",
                    "Priya: No. Just make sure the dashboard can handle the required load.",
                    "Neha: I also received a support document containing a customer's personal information: Name: Suresh Nair, Phone: +91 98765 43210, Email: suresh.nair@example.com, Aadhaar: 2345 6789 0123, PAN: ABCDE1234F",
                    "Neha: None of that is required for the dashboard implementation.",
                    "Priya: Correct. Keep those details out of the engineering payload."
                ]
            )
        ]
    )

    engine = PrivacyMaskingEngine(vault_dir="tests/scratch/vaults", cache_dir="tests/scratch/llm_cache")
    result = engine.process_verified_tasks(meeting)

    payload = result.agent_payloads[0]
    audit = result.audit_records[0]

    # Pre-dispatch check passes
    LeakInspector.assert_clean_payload(payload)

    # 1. Technical specifications MUST be preserved
    payload_text = " ".join(payload.intentions + payload.things_to_implement + payload.technical_context)
    assert "10,000 concurrent users" in payload_text or "10000 concurrent users" in payload_text
    assert "HTTP 403" in payload_text or "403" in payload_text or "unauthorized" in payload_text.lower()
    assert "ADMIN" in payload_text and "FINANCE" in payload_text

    # 2. Confidential business information MUST NOT be in the agent payload
    assert "8,450" not in payload_text
    assert "35%" not in payload_text
    assert "Bharat Retail" not in payload_text
    assert "Suresh Nair" not in payload_text
    assert "2345 6789 0123" not in payload_text
    assert "ABCDE1234F" not in payload_text
    assert "suresh.nair@example.com" not in payload_text

    # 3. Confidential items MUST be captured in audit records
    isolated_text = " ".join(s.value for s in audit.isolated_business_secrets)
    assert "Bharat Retail" in isolated_text or "negotiat" in isolated_text.lower()
    assert "8,450" in isolated_text or "35%" in isolated_text or "campaign" in isolated_text.lower()
    assert "Suresh Nair" in isolated_text or "2345 6789 0123" in isolated_text or len(audit.sanitized_pii_entities) > 0


def test_tc2_regression_expectations():
    """
    TC2 Regression Test:
    Payment gateway migration with credentials, financial volumes & customer sample.
    """
    meeting = MeetingHandoff(
        meeting_id="MEET-TC2-TEST",
        meeting_title="Payment Gateway Migration",
        verified_commitments=[
            VerifiedCommitment(
                task_id="TASK-TC2-01",
                raw_requirement="We need the payment gateway migration completed by December 5.",
                assignees=[
                    Assignee(name="Vikram", role="BACKEND", assigned_work="The new integration will expose POST /payments/create and POST /payments/refund. Implement retries and idempotency for both endpoints. Support approximately 500 requests per second.", deadline="December 5"),
                    Assignee(name="Meera", role="SECURITY", assigned_work="The webhook must verify the provider's signature before accepting payment status updates.", deadline="December 5"),
                    Assignee(name="Karthik", role="QA", assigned_work="Test successful payments, declined payments, duplicate requests and invalid webhook signatures.", deadline="December 5"),
                ],
                evidence_context_quotes=[
                    "Anita (Engineering Manager): We need the payment gateway migration completed by December 5.",
                    "Vikram (Backend): The new integration will expose POST /payments/create and POST /payments/refund. I'll implement retries and idempotency for both endpoints.",
                    "Meera (Security): The webhook must verify the provider's signature before accepting payment status updates.",
                    "Karthik (QA): I'll test successful payments, declined payments, duplicate requests and invalid webhook signatures.",
                    "Vikram: The API should support approximately 500 requests per second during peak traffic.",
                    "Anita: That's a technical requirement. Keep it in the implementation context.",
                    "Anita: The finance team says our payment volume has crossed ₹2.8 crore per month, and the CFO expects it to reach ₹4 crore after the next quarter. Those figures are internal.",
                    "Anita: We're also discussing a preferential transaction rate with the payment provider. Don't expose the negotiation details to the coding agent.",
                    "Vikram: I have the production credentials here: AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE API_KEY=sk-test-12345678901234567890 DATABASE_URL=postgres://admin:SuperSecretPassword@db.internal:5432/payments",
                    "Meera: Those credentials must never be included in the external task.",
                    "Anita: Correct. The coding agent only needs the API contract and authentication mechanism.",
                    "Karthik: For testing, use the following sample customer: Name: Anjali Menon, Mobile: +91 91234 56789, UPI: anjali@okaxis, Bank account: 123456789012, IFSC: SBIN0001234, GSTIN: 32ABCDE1234F1Z5",
                    "Karthik: These are test records and should not be sent outside the local environment."
                ]
            )
        ]
    )

    engine = PrivacyMaskingEngine(vault_dir="tests/scratch/vaults", cache_dir="tests/scratch/llm_cache")
    result = engine.process_verified_tasks(meeting)

    payload = result.agent_payloads[0]
    audit = result.audit_records[0]

    # Pre-dispatch check passes
    LeakInspector.assert_clean_payload(payload)

    payload_text = " ".join(payload.intentions + payload.things_to_implement + payload.technical_context)

    # 1. Technical requirements MUST be preserved
    assert "POST /payments/create" in payload_text
    assert "POST /payments/refund" in payload_text
    assert "idempotency" in payload_text.lower()
    assert "retries" in payload_text.lower()
    assert "signature" in payload_text.lower()
    assert "500 requests per second" in payload_text

    # 2. ANTI-HALLUCINATION: Must NOT contain invented domain constraints
    assert "domain constraints" not in payload_text.lower()

    # 3. Confidential items MUST NOT be in the agent payload
    assert "2.8 crore" not in payload_text
    assert "4 crore" not in payload_text
    assert "AKIAIOSFODNN7EXAMPLE" not in payload_text
    assert "SuperSecretPassword" not in payload_text
    assert "Anjali Menon" not in payload_text
    assert "anjali@okaxis" not in payload_text
    assert "SBIN0001234" not in payload_text
    assert "32ABCDE1234F1Z5" not in payload_text

    # 4. Confidential items MUST be in audit
    isolated_text = " ".join(s.value for s in audit.isolated_business_secrets)
    assert "2.8 crore" in isolated_text or "4 crore" in isolated_text
    assert "preferential transaction rate" in isolated_text or "negotiat" in isolated_text.lower()


def test_tc3_regression_expectations():
    """
    TC3 Regression Test:
    Privileged-operation audit system with M&A, HR compensation, legal & security incidents.
    """
    meeting = MeetingHandoff(
        meeting_id="MEET-TC3-TEST",
        meeting_title="Privileged-Operation Audit System",
        verified_commitments=[
            VerifiedCommitment(
                task_id="TASK-TC3-01",
                raw_requirement="We need the privileged-operation audit system completed before the January release.",
                assignees=[
                    Assignee(name="Dev", role="BACKEND", assigned_work="Add middleware that checks authorization before privileged operations and records the user ID, operation, timestamp and result. Ensure failed authorization attempts don't expose internal details.", deadline="January release"),
                    Assignee(name="Fatima", role="SECURITY", assigned_work="Audit events should be immutable and capture both successful and denied privileged actions.", deadline="January release"),
                    Assignee(name="Rahul", role="QA", assigned_work="Test access for administrator, manager and regular employee roles and verify that denied actions generate audit events.", deadline="January release"),
                ],
                evidence_context_quotes=[
                    "Maya (CTO): We need the privileged-operation audit system completed before the January release.",
                    "Dev (Backend): I'll add middleware that checks authorization before privileged operations and records the user ID, operation, timestamp and result.",
                    "Fatima (Security): Audit events should be immutable and capture both successful and denied privileged actions.",
                    "Rahul (QA): I'll test access for administrator, manager and regular employee roles and verify that denied actions generate audit events.",
                    "Maya: The engineering requirement is that audit records remain available for at least 180 days.",
                    "Dev: I'll also make sure failed authorization attempts don't expose internal implementation details to the client.",
                    "Maya: One additional piece of context: the board approved entering the Middle East market next year, but the announcement has not been made yet.",
                    "Maya: We're also evaluating whether to acquire a smaller competitor. There have been preliminary discussions but nothing has been announced.",
                    "Fatima: There was a security incident last month involving an internal service. The investigation is still ongoing, so don't include those details in the engineering agent context.",
                    "Maya: Our current employee compensation range for the engineering team is between ₹8 lakh and ₹24 lakh per year. That is HR-confidential.",
                    "Rahul: There is also a pending legal dispute with one of our former vendors. The legal team doesn't want the details distributed internally.",
                    "Dev: None of those details are needed to implement the access-control system.",
                    "Maya: Correct.",
                    "Maya: For the actual implementation, use the existing PostgreSQL database and FastAPI service. The authentication layer already provides user IDs and role information."
                ]
            )
        ]
    )

    engine = PrivacyMaskingEngine(vault_dir="tests/scratch/vaults", cache_dir="tests/scratch/llm_cache")
    result = engine.process_verified_tasks(meeting)

    payload = result.agent_payloads[0]
    audit = result.audit_records[0]

    # Pre-dispatch check passes
    LeakInspector.assert_clean_payload(payload)

    payload_text = " ".join(payload.intentions + payload.things_to_implement + payload.technical_context)

    # 1. Technical requirements MUST be preserved
    assert "middleware" in payload_text.lower()
    assert "180 days" in payload_text
    assert "PostgreSQL" in payload_text or "postgresql" in payload_text.lower()
    assert "FastAPI" in payload_text or "fastapi" in payload_text.lower()

    # 2. Confidential items MUST NOT leak
    assert "Middle East" not in payload_text
    assert "acquire" not in payload_text.lower()
    assert "competitor" not in payload_text.lower()
    assert "security incident" not in payload_text.lower()
    assert "8 lakh" not in payload_text
    assert "24 lakh" not in payload_text
    assert "legal dispute" not in payload_text.lower()

    # 3. Confidential items MUST be isolated in audit
    isolated_text = " ".join(s.value for s in audit.isolated_business_secrets)
    assert len(audit.isolated_business_secrets) > 0
    assert any(term in isolated_text.lower() for term in ["acqui", "competitor", "legal", "middle east", "incident", "lakh"])
