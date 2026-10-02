import io
import json
import asyncio
from fastapi import UploadFile
from app.api.routes_pipeline import verify_and_mask_pipeline

def test_demo_004_pipeline():
    async def _run():
        transcript_json = {
            "meeting_id": "demo-meeting-2026-10-02-004",
            "meeting_title": "Project Orion — Engineering Sprint Planning",
            "transcript": [
                {
                    "speaker": "Maya",
                    "text": "Let's finalize the authentication work for the next sprint."
                },
                {
                    "speaker": "Arjun",
                    "text": "I'll implement the OAuth callback handling and update the authentication flow by October 15."
                },
                {
                    "speaker": "Maya",
                    "text": "Good. That's part of the sprint commitment."
                },
                {
                    "speaker": "Priya",
                    "text": "I'll also add API rate limiting to the public endpoints by October 18."
                },
                {
                    "speaker": "Maya",
                    "text": "Yes, that's committed for this sprint."
                },
                {
                    "speaker": "Rahul",
                    "text": "What about caching the API responses? We could potentially use Redis."
                },
                {
                    "speaker": "Arjun",
                    "text": "I'll look into whether Redis is suitable for the API caching requirements."
                },
                {
                    "speaker": "Maya",
                    "text": "Okay, but don't treat Redis as a decided implementation yet."
                }
            ]
        }

        summary_json = {
            "meeting_id": "demo-meeting-2026-10-02-004",
            "meeting_title": "Project Orion — Engineering Sprint Planning",
            "summary": {
                "meeting_purpose": "Engineering sprint planning for authentication, API protection, and caching.",
                "topics_discussed": [
                    "OAuth callback handling and authentication flow",
                    "API rate limiting",
                    "API-response caching",
                    "Redis as a possible caching technology"
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
        
        t_file = UploadFile(filename="transcript_004.json", file=io.BytesIO(t_bytes))
        s_file = UploadFile(filename="summary_004.json", file=io.BytesIO(s_bytes))
        
        res = await verify_and_mask_pipeline(t_file, s_file)

        assert res["status"] == "SUCCESS"
        assert res["meeting_id"] == "demo-meeting-2026-10-02-004"
        assert res["verified_tasks_count"] == 2
        
        tasks = res["verified_tasks"]
        assert len(tasks) == 2

        # Task 1 (Arjun)
        assert tasks[0]["actor"] == "Arjun"
        assert tasks[0]["deadline"] == "October 15"
        assert any("OAuth" in item or "authentication" in item for item in tasks[0]["things_to_implement"])
        assert tasks[0]["technical_context"] == []

        # Task 2 (Priya)
        assert tasks[1]["actor"] == "Priya"
        assert tasks[1]["deadline"] == "October 18"
        assert any("rate limiting" in item.lower() for item in tasks[1]["things_to_implement"])
        assert tasks[1]["technical_context"] == []

    asyncio.run(_run())
