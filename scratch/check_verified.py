import asyncio, io, json
from app.api.routes_pipeline import verify_and_mask_pipeline
from fastapi import UploadFile

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

async def run():
    t_file = UploadFile(filename="t.json", file=io.BytesIO(json.dumps(transcript_json).encode()))
    s_file = UploadFile(filename="s.json", file=io.BytesIO(json.dumps(summary_json).encode()))
    res = await verify_and_mask_pipeline(t_file, s_file)
    print("VERIFIED COUNT:", len(res["verified_tasks"]))
    for i, v in enumerate(res["verified_tasks"]):
        print(f"  V{i+1}: actor={v.get('actor')} | req={v.get('things_to_implement')}")
    print("AMBIGUOUS COUNT:", len(res["ambiguous_tasks"]))
    for i, a in enumerate(res["ambiguous_tasks"]):
        print(f"  A{i+1}: text={a.get('task_text')} | actor={a.get('actor')}")

if __name__ == "__main__":
    asyncio.run(run())
