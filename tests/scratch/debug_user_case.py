import sys
sys.path.insert(0, ".")
import json
from pathlib import Path
from app.models import Meeting
from app.adapters.mock_adapter import MockAdapter, normalize_summary_item
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.claims.from_summary import extract_claims_from_summary
from app.pipeline import run_verification_pipeline, get_effective_status

t_json = {
  "meeting_id": "demo-meeting-2026-10-02-002",
  "title": "Project Atlas — Product Launch and Client Operations",
  "created_at": "2026-10-02T14:00:00+05:30",
  "duration_seconds": 1380,
  "language": "en",
  "transcript": [
    {"id": 1, "start_time": 0.0, "end_time": 8.2, "speaker": "Speaker 1", "text": "Let's review the October launch plan. The client wants the new dashboard available before the end of the month."},
    {"id": 2, "start_time": 8.6, "end_time": 20.1, "speaker": "Speaker 2", "text": "The current contract is worth about 480,000 dollars annually, and the client currently has 37 active enterprise accounts."},
    {"id": 3, "start_time": 20.5, "end_time": 31.7, "speaker": "Speaker 1", "text": "Those numbers are from the account manager's spreadsheet, right? Have finance and CRM data been reconciled?"},
    {"id": 4, "start_time": 32.0, "end_time": 42.5, "speaker": "Speaker 2", "text": "Not yet. The 480,000 figure is from the latest commercial sheet, but finance has not reconciled it with the invoices."},
    {"id": 5, "start_time": 43.0, "end_time": 53.4, "speaker": "Speaker 3", "text": "Also, the largest enterprise customer currently represents roughly 41 percent of this account's revenue."},
    {"id": 6, "start_time": 53.8, "end_time": 65.0, "speaker": "Speaker 1", "text": "Do we have the customer-level export to verify that concentration number?"},
    {"id": 7, "start_time": 65.4, "end_time": 75.2, "speaker": "Speaker 3", "text": "No. That 41 percent is only from the account manager's schedule, so it should stay unconfirmed."},
    {"id": 8, "start_time": 75.7, "end_time": 84.9, "speaker": "Speaker 2", "text": "The client also has a renewal coming up on November 18, and their procurement team asked for SSO and audit-log support."},
    {"id": 9, "start_time": 85.3, "end_time": 96.8, "speaker": "Speaker 1", "text": "Okay. Priya, can you prepare the SSO requirements and map them against the current authentication service?"},
    {"id": 10, "start_time": 97.2, "end_time": 107.4, "speaker": "Speaker 4", "text": "Yes. I'll document the SSO requirements and identify the changes needed in the authentication service by October 10."},
    {"id": 11, "start_time": 108.0, "end_time": 119.6, "speaker": "Speaker 1", "text": "Good. For the dashboard, let's not promise real-time analytics yet. We only know the client asked for it; engineering has not confirmed the infrastructure capacity."},
    {"id": 12, "start_time": 120.0, "end_time": 130.7, "speaker": "Speaker 2", "text": "Understood. I'll ask the platform team whether the current cluster can support the expected dashboard workload."},
    {"id": 13, "start_time": 131.1, "end_time": 141.8, "speaker": "Speaker 1", "text": "That is a request, not a commitment to ship real-time analytics. Keep that distinction in the task record."},
    {"id": 14, "start_time": 142.2, "end_time": 153.9, "speaker": "Speaker 3", "text": "For context, the client's internal security review is scheduled for November 5, and their security team requires evidence of audit logging."},
    {"id": 15, "start_time": 154.3, "end_time": 167.0, "speaker": "Speaker 1", "text": "Please don't send any customer names, contract values, account counts, or internal security dates to the coding agent. The engineering payload should contain only what is required to implement the verified work."}
  ]
}

s_json = {
  "meeting_id": "demo-meeting-2026-10-02-002",
  "title": "Project Atlas — Product Launch and Client Operations",
  "created_at": "2026-10-02T14:00:00+05:30",
  "summary": "The team reviewed an October dashboard launch for a client...",
  "key_points": [
    "The dashboard is targeted for the end of October, but real-time analytics has not been approved as a committed deliverable.",
    "The commercial sheet reports an annual contract value of approximately $480,000 and 37 active enterprise accounts; finance reconciliation is still pending.",
    "The largest enterprise customer is reported to represent roughly 41% of revenue, but the figure is explicitly unconfirmed.",
    "The client requested SSO and audit-log support.",
    "Priya committed to document SSO requirements and identify required authentication-service changes by October 10.",
    "The platform team will be asked about infrastructure capacity; this should not be treated as a commitment to ship real-time analytics.",
    "The client renewal is November 18 and the internal security review is November 5."
  ],
  "action_items": [
    {
      "description": "Document the SSO requirements and identify changes needed in the authentication service.",
      "assignee": "Priya",
      "due_date": "2026-10-10",
      "status": "open"
    },
    {
      "description": "Ask the platform team whether the current cluster can support the expected dashboard workload.",
      "assignee": "Speaker 2",
      "due_date": None,
      "status": "open",
      "note": "This is an investigation request, not a commitment to ship real-time analytics."
    }
  ]
}

adapter = MockAdapter()
meeting_id = t_json.get("meeting_id")
meeting_title = t_json.get("title")
t_dict = dict(t_json)

s_items = (
    s_json.get("action_items", []) + 
    s_json.get("decisions", []) + 
    s_json.get("key_points", []) +
    s_json.get("claims", [])
)
norm_s_items = [normalize_summary_item(it) for it in s_items if normalize_summary_item(it)]
t_dict["summary"] = {"decisions": norm_s_items, "action_items": []}
meeting = adapter.load(t_dict)

load_meeting_to_db(meeting, source="upload")
index_meeting(meeting.meeting_id)

claims = extract_claims_from_summary(meeting)
print(f"Total claims extracted: {len(claims)}")

for c in claims:
    v = run_verification_pipeline(c)
    eff = get_effective_status(c.claim_id, v.status)
    print(f"\nClaim ID: {c.claim_id}")
    print(f"Text: {c.text}")
    print(f"Type: {c.type}, Actor: {c.actor}, Action: {c.action}, Deadline: {c.deadline}")
    print(f"Status: {v.status}, EffStatus: {eff}, GateAction: {v.gate_action}, Reasons: {[r.value for r in v.reasons]}")
    print(f"Explanation: {v.explanation}")
    print(f"Evidence Chain ({len(v.evidence_chain)} items):")
    for e in v.evidence_chain:
        print(f"  [{e.idx}] {e.speaker} | Stance: {e.stance} | Relation: {e.relation} | Quote: {e.quote}")
