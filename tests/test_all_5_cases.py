import json
from pathlib import Path
from app.masking import PrivacyMaskingEngine, MeetingHandoff, LeakInspector

def test_process_all_5_test_cases():
    fixtures_file = Path("tests/fixtures/test_suite/all_5_testcases.json")
    with open(fixtures_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    engine = PrivacyMaskingEngine(
        vault_dir="tests/scratch/vaults",
        cache_dir="tests/scratch/llm_cache"
    )

    results_summary = []

    for idx, case_data in enumerate(cases, 1):
        meeting = MeetingHandoff.model_validate(case_data)
        out_md = Path(f"tests/scratch/verified_tasks_case_{idx}.md")
        
        result = engine.process_verified_tasks(
            handoff_data=meeting,
            output_md_path=out_md
        )

        assert len(result.agent_payloads) == 1
        payload = result.agent_payloads[0]
        audit = result.audit_records[0]

        # 1. Assert pre-dispatch leak gate passes
        LeakInspector.assert_clean_payload(payload)

        # 2. Assert confidential business context was detected and isolated
        assert audit.confidential_context_detected is True
        assert len(audit.isolated_business_secrets) > 0

        # 3. Assert zero business secret keywords leak into the agent payload
        payload_text = " ".join(payload.intentions + payload.things_to_implement + payload.technical_context).lower()
        
        forbidden_keywords_by_case = {
            1: ["negotiating", "two new countries", "40% more customers", "major contract"],
            2: ["competing companies", "adjustments for several senior employees", "significantly above the department average"],
            3: ["competitor is launching", "undercut their enterprise pricing", "15%"],
            4: ["acquisition of a smaller company", "80,000 customer records", "due-diligence"],
            5: ["pricing experiment", "drop in conversions", "finance team doesn't want"]
        }

        for kw in forbidden_keywords_by_case.get(idx, []):
            assert kw not in payload_text, f"Case {idx} leaked keyword '{kw}' in agent payload!"

        results_summary.append({
            "case_id": meeting.meeting_id,
            "title": meeting.meeting_title,
            "agent_payload": payload.model_dump(),
            "audit_isolated_secrets": [s.model_dump() for s in audit.isolated_business_secrets],
            "role_briefs_count": len(result.role_briefs)
        })

    # Save summary report for verification
    with open("tests/scratch/all_5_cases_results.json", "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2)

if __name__ == "__main__":
    test_process_all_5_test_cases()
    print("ALL 5 TEST CASES PROCESSED AND VERIFIED CLEAN!")
