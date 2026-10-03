import asyncio, io, json
from app.claims.from_summary import extract_claims_from_summary
from app.models import Meeting, Segment, ClaimType, Stance, Status
from app.pipeline import run_verification_pipeline, get_effective_status
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.adapters.mock_adapter import MockAdapter, normalize_summary_item
import re

transcript_json = {
    "meeting_id": "demo-meeting-claim-local-001",
    "meeting_title": "Sprint Planning",
    "transcript": [
        {"speaker": "Maya", "text": "Let's lock down engineering commitments and open investigations."},
        {"speaker": "Arjun", "text": "I'll implement the account-lockout flow and add unlock notifications by October 12."},
        {"speaker": "Maya", "text": "Yes, that's committed."},
        {"speaker": "Priya", "text": "I'll add customer-list pagination and include the required API tests by October 15."},
        {"speaker": "Maya", "text": "Agreed, that is part of the sprint commitment."},
        {"speaker": "Rahul", "text": "I'll update the deployment pipeline to run the database migration check before release and have it ready by October 18."},
        {"speaker": "Maya", "text": "That's committed as well."},
        {"speaker": "Arjun", "text": "I'll add structured error responses to the public API and document the error format by October 20."},
        {"speaker": "Priya", "text": "Yes, we'll include that in the sprint scope."},
        {"speaker": "Priya", "text": "I'll also add a dashboard endpoint for the operations team and return the required status fields by October 22."},
        {"speaker": "Maya", "text": "That's another committed item."},
        {"speaker": "Rahul", "text": "I'm not sure whether the deployment pipeline should use a separate worker for the migration check. I'll investigate the options before we decide."},
        {"speaker": "Arjun", "text": "I'll investigate whether Redis is suitable for API caching."},
        {"speaker": "Priya", "text": "I can check whether PostgreSQL or MongoDB is a better fit for the new reporting data, but we haven't selected either one yet."},
        {"speaker": "Rahul", "text": "We could potentially use object storage instead of our existing file service for generated reports. I'll evaluate the trade-offs."},
        {"speaker": "Maya", "text": "Understood. Keep all four of those as open investigations rather than implementation commitments."}
    ]
}

summary_json = {
    "meeting_id": "demo-meeting-claim-local-001",
    "summary": {
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
        ]
    }
}

s_items = summary_json["summary"]["topics_discussed"]
norm_s_items = [normalize_summary_item(it) for it in s_items]
meeting = MockAdapter().load({
    "meeting_id": "demo-meeting-claim-local-001",
    "title": "Sprint Planning",
    "segments": transcript_json["transcript"],
    "summary": {"decisions": norm_s_items, "action_items": []}
})
load_meeting_to_db(meeting, source="upload")
index_meeting(meeting.meeting_id)

claims = extract_claims_from_summary(meeting)
for c in claims:
    if "dashboard" in c.text.lower():
        v = run_verification_pipeline(c)
        eff_status = get_effective_status(c.claim_id, v.status)
        has_commit = any(e.relation == "SUPPORTS" and (e.stance in (Stance.COMMIT, Stance.ACCEPT, Stance.DECIDE)) for e in v.evidence_chain)
        print(f"CLAIM: {c.text}")
        print(f"  v.status: {v.status}")
        print(f"  eff_status: {eff_status}")
        print(f"  has_commit: {has_commit}")
        for e in v.evidence_chain:
            print(f"    [{e.relation}] [{e.stance}] {e.speaker}: {e.quote[:60]}")
