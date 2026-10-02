import pytest
from pathlib import Path
import asyncio
import io
import json

from app.models import Meeting, Participant, Segment
from app.adapters.mock_adapter import MockAdapter
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.api.routes_pipeline import verify_and_mask_pipeline
from fastapi import UploadFile

def test_demo_meeting_003_verification_and_isolation():
    async def _run():
        transcript_data = {
            "meeting_id": "demo-meeting-2026-10-02-003",
            "title": "Launch Requirements & Scope Review",
            "segments": [
                {"idx": 0, "speaker": "Maya", "text": "Let's go through the launch requirements. The client wants SSO support added before the November release."},
                {"idx": 1, "speaker": "Arjun", "text": "I can take that. I'll document the SSO requirements and update the authentication service before November 5."},
                {"idx": 2, "speaker": "Maya", "text": "Good. The customer currently has 84 enterprise accounts and the annual contract is worth about $720,000."},
                {"idx": 3, "speaker": "Arjun", "text": "Those numbers came from the commercial sheet, right?"},
                {"idx": 4, "speaker": "Maya", "text": "Yes, but finance has not reconciled the latest numbers yet. Don't use the account count or contract value for engineering decisions."},
                {"idx": 5, "speaker": "Rahul", "text": "For the dashboard, we should investigate whether our current Kubernetes cluster can handle the expected workload."},
                {"idx": 6, "speaker": "Arjun", "text": "I'll ask the platform team to run a capacity check."},
                {"idx": 7, "speaker": "Maya", "text": "That's an investigation only. We are not committing to a Kubernetes scaling change yet."},
                {"idx": 8, "speaker": "Maya", "text": "The largest customer represents roughly 46 percent of our revenue."},
                {"idx": 9, "speaker": "Rahul", "text": "Do we have verified customer-level data for that?"},
                {"idx": 10, "speaker": "Maya", "text": "No. That percentage is from an old account-manager report, so treat it as unconfirmed."},
                {"idx": 11, "speaker": "Arjun", "text": "For the audit logging requirement, I'll add an audit-event endpoint and store the events in the existing backend database by November 8."},
                {"idx": 12, "speaker": "Maya", "text": "Yes, that's part of the committed launch scope."},
                {"idx": 13, "speaker": "Rahul", "text": "For implementation we might use Redis for caching the dashboard data."},
                {"idx": 14, "speaker": "Arjun", "text": "I haven't decided on Redis yet. I'll evaluate Redis against the existing database before choosing."},
                {"idx": 15, "speaker": "Maya", "text": "Fine. Don't treat Redis as a required technology until that evaluation is complete."},
                {"idx": 16, "speaker": "Maya", "text": "Also, the customer's renewal is December 12 and our internal security review is December 3."},
                {"idx": 17, "speaker": "Arjun", "text": "Those dates are operational context only. They don't change the engineering requirements."}
            ]
        }

        summary_data = {
            "meeting_id": "demo-meeting-2026-10-02-003",
            "decisions": [
                "Add SSO support before the November release.",
                "Add an audit-event endpoint and store the events in the existing backend database by November 8."
            ],
            "action_items": [
                {
                    "description": "Document the SSO requirements and update the authentication service.",
                    "assignee": "Arjun",
                    "due_date": "November 5"
                },
                {
                    "description": "Add an audit-event endpoint and store events in existing backend database.",
                    "assignee": "Arjun",
                    "due_date": "November 8"
                },
                {
                    "description": "Ask platform team to run Kubernetes cluster capacity check.",
                    "assignee": "Arjun",
                    "due_date": None
                },
                {
                    "description": "Evaluate Redis for caching.",
                    "assignee": "Arjun",
                    "due_date": None
                }
            ],
            "unconfirmed": [
                "The largest customer represents roughly 46% of revenue."
            ]
        }

        t_bytes = json.dumps(transcript_data).encode("utf-8")
        s_bytes = json.dumps(summary_data).encode("utf-8")

        t_file = UploadFile(filename="transcript_003.json", file=io.BytesIO(t_bytes))
        s_file = UploadFile(filename="summary_003.json", file=io.BytesIO(s_bytes))

        res = await verify_and_mask_pipeline(t_file, s_file)

        assert res["status"] == "SUCCESS"
        verified_tasks = res["verified_tasks"]
        
        # 1. Exactly 2 verified tasks (SSO and Audit logging)
        assert len(verified_tasks) == 2, f"Expected 2 verified tasks, got {len(verified_tasks)}: {verified_tasks}"
        
        sso_task = next((t for t in verified_tasks if "sso" in str(t).lower()), None)
        audit_task = next((t for t in verified_tasks if "audit" in str(t).lower()), None)
        
        assert sso_task is not None, "SSO task missing from verified tasks"
        assert audit_task is not None, "Audit logging task missing from verified tasks"
        
        # 2. SSO Task Isolation and Deadlines
        assert sso_task["deadline"] == "November 5"
        sso_dump = json.dumps(sso_task).lower()
        assert "redis" not in sso_dump, "Redis contaminated into SSO task"
        assert "46 percent" not in sso_dump and "46%" not in sso_dump
        assert "november 8" not in sso_dump, "Audit deadline contaminated into SSO"
        assert "go through the launch requirements" not in sso_dump
        
        # 3. Audit Task Isolation and Deadlines
        assert audit_task["deadline"] == "November 8"
        audit_dump = json.dumps(audit_task).lower()
        assert "redis" not in audit_dump, "Redis contaminated into Audit task"
        assert "46 percent" not in audit_dump and "46%" not in audit_dump
        assert "november 5" not in audit_dump, "SSO deadline contaminated into Audit task"
        
        # 4. Redis and Kubernetes and 46% must NOT be in any verified task
        for task in verified_tasks:
            tdump = json.dumps(task).lower()
            assert "kubernetes" not in tdump, "Kubernetes capacity check must not be verified as a delivery task"
            assert "redis" not in tdump, "Unselected Redis must not appear in verified tasks"
            assert "$720,000" not in tdump and "720,000" not in tdump
            assert "84 enterprise" not in tdump

    asyncio.run(_run())
