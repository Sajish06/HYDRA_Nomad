import io
import json
import asyncio
from fastapi import UploadFile
from app.config import settings
settings.MOCK_LLM = 1
from app.api.routes_pipeline import verify_and_mask_pipeline

def test_critical_claim_local_verification_rules():
    async def _run():
        transcript_json = {
            "meeting_id": "demo-meeting-claim-local-001",
            "meeting_title": "Sprint Planning — Comprehensive Verification Benchmark",
            "transcript": [
                {
                    "speaker": "Maya",
                    "text": "Let's lock down the engineering commitments for this sprint and catalog open investigations."
                },
                {
                    "speaker": "Arjun",
                    "text": "I'll implement the account-lockout flow and add unlock notifications by October 12."
                },
                {
                    "speaker": "Maya",
                    "text": "Yes, that's committed."
                },
                {
                    "speaker": "Priya",
                    "text": "I'll add customer-list pagination and include the required API tests by October 15."
                },
                {
                    "speaker": "Maya",
                    "text": "Agreed, that is part of the sprint commitment."
                },
                {
                    "speaker": "Rahul",
                    "text": "I'll update the deployment pipeline to run the database migration check before release and have it ready by October 18."
                },
                {
                    "speaker": "Maya",
                    "text": "That's committed as well."
                },
                {
                    "speaker": "Arjun",
                    "text": "I'll add structured error responses to the public API and document the error format by October 20."
                },
                {
                    "speaker": "Priya",
                    "text": "Yes, we'll include that in the sprint scope."
                },
                {
                    "speaker": "Priya",
                    "text": "I'll also add a dashboard endpoint for the operations team and return the required status fields by October 22."
                },
                {
                    "speaker": "Maya",
                    "text": "That's another committed item."
                },
                {
                    "speaker": "Rahul",
                    "text": "I'm not sure whether the deployment pipeline should use a separate worker for the migration check. I'll investigate the options before we decide."
                },
                {
                    "speaker": "Arjun",
                    "text": "I'll investigate whether Redis is suitable for API caching."
                },
                {
                    "speaker": "Priya",
                    "text": "I can check whether PostgreSQL or MongoDB is a better fit for the new reporting data, but we haven't selected either one yet."
                },
                {
                    "speaker": "Rahul",
                    "text": "We could potentially use object storage instead of our existing file service for generated reports. I'll evaluate the trade-offs."
                },
                {
                    "speaker": "Maya",
                    "text": "Understood. Keep all four of those as open investigations rather than implementation commitments."
                }
            ]
        }

        summary_json = {
            "meeting_id": "demo-meeting-claim-local-001",
            "meeting_title": "Sprint Planning — Comprehensive Verification Benchmark",
            "summary": {
                "meeting_purpose": "Sprint planning and technical investigation review.",
                "topics_discussed": [
                    "Account-lockout flow and unlock notifications",
                    "Customer-list pagination and API tests",
                    "Deployment pipeline database migration check",
                    "Structured error responses and API documentation",
                    "Operations dashboard endpoint",
                    "Separate worker architecture for migration check",
                    "Redis caching feasibility",
                    "PostgreSQL vs MongoDB for reporting data",
                    "Object storage vs file service for generated reports"
                ],
                "participants": [
                    "Maya",
                    "Arjun",
                    "Priya",
                    "Rahul"
                ]
            }
        }

        t_bytes = json.dumps(transcript_json).encode("utf-8")
        s_bytes = json.dumps(summary_json).encode("utf-8")
        
        t_file = UploadFile(filename="transcript_benchmark.json", file=io.BytesIO(t_bytes))
        s_file = UploadFile(filename="summary_benchmark.json", file=io.BytesIO(s_bytes))
        
        res = await verify_and_mask_pipeline(t_file, s_file)

        assert res["status"] == "SUCCESS"
        assert res["verified_tasks_count"] == 5, f"Expected 5 verified tasks, got {res['verified_tasks_count']}"
        assert res["ambiguous_tasks_count"] == 4, f"Expected 4 ambiguous tasks, got {res['ambiguous_tasks_count']}"

        verified = res["verified_tasks"]
        
        # 1. Arjun — account-lockout flow + unlock notifications — October 12
        assert verified[0]["actor"] == "Arjun"
        assert verified[0]["deadline"] == "October 12"
        assert any("lockout" in t.lower() or "unlock" in t.lower() for t in verified[0]["things_to_implement"])

        # 2. Priya — customer-list pagination + API tests — October 15
        assert verified[1]["actor"] == "Priya"
        assert verified[1]["deadline"] == "October 15"
        assert any("pagination" in t.lower() for t in verified[1]["things_to_implement"])

        # 3. Rahul — deployment migration check — October 18
        assert verified[2]["actor"] == "Rahul"
        assert verified[2]["deadline"] == "October 18"
        assert any("migration" in t.lower() or "deployment" in t.lower() for t in verified[2]["things_to_implement"])

        # 4. Arjun — structured API errors + documentation — October 20
        assert verified[3]["actor"] == "Arjun"
        assert verified[3]["deadline"] == "October 20"
        assert any("error" in t.lower() for t in verified[3]["things_to_implement"])

        # 5. Priya — operations dashboard endpoint — October 22
        assert verified[4]["actor"] == "Priya"
        assert verified[4]["deadline"] == "October 22"
        assert any("dashboard" in t.lower() for t in verified[4]["things_to_implement"])

        # Check Ambiguous tasks
        ambiguous = res["ambiguous_tasks"]
        assert len(ambiguous) == 4
        ambiguous_actors = [a["actor"] for a in ambiguous]
        assert "Rahul" in ambiguous_actors
        assert "Arjun" in ambiguous_actors
        assert "Priya" in ambiguous_actors

    asyncio.run(_run())
