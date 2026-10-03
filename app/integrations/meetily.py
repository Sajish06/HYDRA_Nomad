import os
import re
import json
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
import httpx
from fastapi import HTTPException

logger = logging.getLogger("nomad.meetily")

MEETILY_GATEWAY_DEFAULT = os.getenv("MEETILY_GATEWAY", "http://127.0.0.1:8420")
MEETILY_TOKEN_DEFAULT = os.getenv("MEETILY_PRO_TOKEN", "")

# Sample demo meetings for offline/stand-alone testing
MOCK_MEETILY_MEETINGS = {
    "meeting_12345": {
        "metadata": {
            "id": "meeting_12345",
            "title": "Project Nexus — Core Architecture & Infrastructure Review",
            "status": "completed",
            "participants": ["Maya", "Arjun", "Priya", "Rahul"]
        },
        "summary": {
            "meeting_id": "meeting_12345",
            "title": "Project Nexus — Core Architecture & Infrastructure Review",
            "topics_discussed": [
                "Password-reset flow and email verification",
                "Public API request validation and testing",
                "Deployment configuration and application health checks",
                "Whether background jobs should move to a separate worker service",
                "Database options for new audit data"
            ],
            "decisions": [
                "Implement password-reset flow and email verification handling by October 14",
                "Add request validation to public API endpoints and test rules by October 17",
                "Update deployment configuration for health-check endpoint by October 20"
            ],
            "action_items": [
                {"assignee": "Arjun", "text": "Implement password-reset flow by October 14"},
                {"assignee": "Priya", "text": "Add API validation and tests by October 17"},
                {"assignee": "Rahul", "text": "Update deployment configuration by October 20"}
            ]
        },
        "transcript": {
            "meeting_id": "meeting_12345",
            "segments": [
                {"speaker": "Maya", "text": "Let's lock down the engineering work for the next sprint and separate committed work from items that still need investigation."},
                {"speaker": "Arjun", "text": "I'll implement the password-reset flow and add the required email verification handling by October 14."},
                {"speaker": "Maya", "text": "Yes, that's part of the committed sprint scope."},
                {"speaker": "Priya", "text": "I'll add request validation to the public API endpoints and include tests for the validation rules by October 17."},
                {"speaker": "Maya", "text": "Agreed, we'll treat that as committed work for this sprint."},
                {"speaker": "Rahul", "text": "I'll update the deployment configuration so the application uses the new health-check endpoint, and I'll have that ready by October 20."},
                {"speaker": "Maya", "text": "That's also committed for the sprint."},
                {"speaker": "Arjun", "text": "I'm not sure whether we should move the background jobs to a separate worker service. I'll investigate the trade-offs before we decide."},
                {"speaker": "Priya", "text": "I can check whether PostgreSQL or MongoDB is a better fit for the new audit data, but I don't think we've selected either one yet."},
                {"speaker": "Maya", "text": "Correct. Treat both of those as open investigations rather than implementation commitments."}
            ]
        }
    }
}


async def fetch_meetily_meeting(
    meeting_id: str,
    gateway_url: Optional[str] = None,
    token: Optional[str] = None,
    allow_demo_fallback: bool = True
) -> Dict[str, Any]:
    """
    Fetches transcript, summary, and metadata from the local Meetily Gateway.
    Gateway Default: http://127.0.0.1:8420
    Endpoints:
      - GET /v1/meetings/{meeting_id}/summary
      - GET /v1/meetings/{meeting_id}/transcript
      - GET /v1/meetings/{meeting_id}
    """
    clean_id = meeting_id.strip()
    gateway = (gateway_url or MEETILY_GATEWAY_DEFAULT).rstrip("/")
    auth_token = token or MEETILY_TOKEN_DEFAULT

    headers = {
        "Accept": "application/json"
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    summary_data = None
    transcript_data = None
    meta_data = None
    network_error = None

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            summary_task = client.get(f"{gateway}/v1/meetings/{clean_id}/summary", headers=headers)
            transcript_task = client.get(f"{gateway}/v1/meetings/{clean_id}/transcript", headers=headers)
            meta_task = client.get(f"{gateway}/v1/meetings/{clean_id}", headers=headers)

            results = await asyncio.gather(summary_task, transcript_task, meta_task, return_exceptions=True)

            s_res, t_res, m_res = results

            if isinstance(s_res, httpx.Response) and s_res.status_code == 200:
                summary_data = s_res.json()
            elif isinstance(s_res, Exception):
                network_error = str(s_res)

            if isinstance(t_res, httpx.Response) and t_res.status_code == 200:
                transcript_data = t_res.json()
            elif isinstance(t_res, Exception):
                network_error = str(t_res)

            if isinstance(m_res, httpx.Response) and m_res.status_code == 200:
                meta_data = m_res.json()
    except Exception as exc:
        network_error = str(exc)

    # If gateway returned data successfully
    if summary_data and transcript_data:
        return {
            "source": "meetily_live",
            "meeting_id": clean_id,
            "metadata": meta_data or {},
            "summary": summary_data,
            "transcript": transcript_data
        }

    # If gateway unreachable or demo ID requested, check mock demo store
    if allow_demo_fallback and (clean_id in MOCK_MEETILY_MEETINGS or clean_id.startswith("demo") or "test" in clean_id):
        demo_payload = MOCK_MEETILY_MEETINGS.get(clean_id) or MOCK_MEETILY_MEETINGS["meeting_12345"]
        logger.info(f"Using Meetily demo fixture for {clean_id} (gateway {gateway} unreachable)")
        return {
            "source": "meetily_demo_fallback",
            "meeting_id": clean_id,
            "metadata": demo_payload["metadata"],
            "summary": demo_payload["summary"],
            "transcript": demo_payload["transcript"],
            "gateway_status": f"Local Meetily gateway ({gateway}) was offline. Loaded demo fixture."
        }

    # Otherwise report descriptive error
    err_detail = (
        f"Unable to reach Meetily Gateway at {gateway} for meeting '{clean_id}'. "
        f"Ensure Meetily Pro is running locally on port 8420 with your API token configured, "
        f"or use demo meeting ID 'meeting_12345' for offline demonstration."
    )
    if network_error:
        err_detail += f" (Network note: {network_error})"

    raise HTTPException(
        status_code=502,
        detail={
            "error": {
                "code": "MEETILY_GATEWAY_UNAVAILABLE",
                "message": err_detail,
                "suggested_action": "Verify Meetily Gateway at http://127.0.0.1:8420 or test with demo ID 'meeting_12345'."
            }
        }
    )
