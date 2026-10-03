import asyncio, io, json
from app.models import Claim, ClaimType
from app.pipeline import run_verification_pipeline
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.models import Meeting, Segment as TranscriptSegment

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

segments = [TranscriptSegment(idx=i, speaker=s["speaker"], text=s["text"]) for i, s in enumerate(transcript_json["transcript"])]
meeting = Meeting(meeting_id="demo-meeting-claim-local-001", meeting_title="Sprint Planning", segments=segments)
load_meeting_to_db(meeting, source="upload")
index_meeting("demo-meeting-claim-local-001")

claim = Claim(
    claim_id="c5",
    meeting_id="demo-meeting-claim-local-001",
    text="Operations dashboard endpoint",
    normalized="Operations dashboard endpoint",
    source="SUMMARY",
    type=ClaimType.COMMITMENT
)

v = run_verification_pipeline(claim)
print("STATUS:", v.status)
print("EXPLANATION:", v.explanation)
for e in v.evidence_chain:
    print(f"[{e.relation}] [{e.stance}] {e.speaker}: {e.quote[:70]}")
