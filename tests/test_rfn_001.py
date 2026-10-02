import io
import json
import asyncio
from fastapi import UploadFile
from app.api.routes_pipeline import verify_and_mask_pipeline

def test_rfn_meeting_001_verification():
    async def _run():
        transcript_json = {
            "meeting_id": "rfn-meeting-2026-10-03-001",
            "meeting_title": "Project Atlas — Sprint Scope and Infrastructure Review",
            "transcript": [
                {
                    "speaker": "Maya",
                    "text": "Let's lock down the engineering work for the next sprint and separate committed work from items that still need investigation."
                },
                {
                    "speaker": "Arjun",
                    "text": "I'll implement the password-reset flow and add the required email verification handling by October 14."
                },
                {
                    "speaker": "Maya",
                    "text": "Yes, that's part of the committed sprint scope."
                },
                {
                    "speaker": "Priya",
                    "text": "I'll add request validation to the public API endpoints and include tests for the validation rules by October 17."
                },
                {
                    "speaker": "Maya",
                    "text": "Agreed, we'll treat that as committed work for this sprint."
                },
                {
                    "speaker": "Rahul",
                    "text": "I'll update the deployment configuration so the application uses the new health-check endpoint, and I'll have that ready by October 20."
                },
                {
                    "speaker": "Maya",
                    "text": "That's also committed for the sprint."
                },
                {
                    "speaker": "Arjun",
                    "text": "I'm not sure whether we should move the background jobs to a separate worker service. I'll investigate the trade-offs before we decide."
                },
                {
                    "speaker": "Priya",
                    "text": "I can check whether PostgreSQL or MongoDB is a better fit for the new audit data, but I don't think we've selected either one yet."
                },
                {
                    "speaker": "Maya",
                    "text": "Correct. Treat both of those as open investigations rather than implementation commitments."
                }
            ]
        }

        summary_json = {
            "meeting_id": "rfn-meeting-2026-10-03-001",
            "meeting_title": "Project Atlas — Sprint Scope and Infrastructure Review",
            "summary": {
                "meeting_purpose": "Finalize the next sprint's engineering scope and distinguish committed implementation work from items that require further investigation.",
                "topics_discussed": [
                    "Password-reset flow and email verification",
                    "Public API request validation and testing",
                    "Deployment configuration and application health checks",
                    "Whether background jobs should move to a separate worker service",
                    "Database options for new audit data"
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
        
        t_file = UploadFile(filename="rfn_transcript_001.json", file=io.BytesIO(t_bytes))
        s_file = UploadFile(filename="rfn_summary_001.json", file=io.BytesIO(s_bytes))
        
        res = await verify_and_mask_pipeline(t_file, s_file)

        assert res["status"] == "SUCCESS"
        assert res["meeting_id"] == "rfn-meeting-2026-10-03-001"
        assert res["verified_tasks_count"] == 3
        
        verified = res["verified_tasks"]
        assert len(verified) == 3

        # Task 1: Arjun (Password reset)
        assert verified[0]["actor"] == "Arjun"
        assert verified[0]["deadline"] == "October 14"
        assert any("password" in t.lower() for t in verified[0]["things_to_implement"])

        # Task 2: Priya (API validation)
        assert verified[1]["actor"] == "Priya"
        assert verified[1]["deadline"] == "October 17"
        assert any("validation" in t.lower() for t in verified[1]["things_to_implement"])

        # Task 3: Rahul (Deployment + health check)
        assert verified[2]["actor"] == "Rahul"
        assert verified[2]["deadline"] == "October 20"
        assert any("deployment" in t.lower() or "health" in t.lower() for t in verified[2]["things_to_implement"])

        # Ambiguous tasks
        assert res["ambiguous_tasks_count"] == 2
        ambiguous = res["ambiguous_tasks"]
        assert len(ambiguous) == 2

        # Check actors for investigations
        ambiguous_actors = {a["actor"] for a in ambiguous}
        assert "Arjun" in ambiguous_actors
        assert "Priya" in ambiguous_actors

    asyncio.run(_run())
