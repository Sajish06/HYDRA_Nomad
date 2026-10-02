"""Webhook receiver for incoming Meetily signed event notifications."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from backend.dependencies import get_repo
from backend.logging import logger
from backend.meetily.client import MeetilyClient
from backend.meetily.errors import MeetilyAuthError, MeetilyInvalidResponse
from backend.meetily.meetings import MeetingSyncService
from backend.meetily.webhooks import WebhookVerifier
from backend.processors.pipeline import PipelineOrchestrator
from backend.storage.database import SessionLocal
from backend.storage.repository import Repository

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def process_webhook_background(event_id: str, meeting_id: str):
    """Background task pulling meeting data from Meetily and running clean room pipeline."""
    db = SessionLocal()
    try:
        repo = Repository(db)
        client = MeetilyClient()
        sync_service = MeetingSyncService(client=client, repo=repo)

        logger.info(f"Syncing meeting {meeting_id} for webhook event {event_id}...")
        meeting, transcript, summary = await sync_service.sync_meeting(meeting_id)

        orchestrator = PipelineOrchestrator(repo=repo)
        logger.info(f"Executing pipeline for meeting {meeting.id}...")
        await orchestrator.execute_run(meeting.id, transcript, summary)

        repo.update_webhook_event(event_id, "processed")
        logger.info(f"Webhook event {event_id} processed successfully.")

    except Exception as e:
        logger.error(f"Pipeline background execution failed for webhook {event_id}: {str(e)}", exc_info=True)
        try:
            repo.update_webhook_event(event_id, "failed", error_message=str(e))
        except Exception:
            pass
    finally:
        db.close()


@router.post("/meetily")
async def meetily_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    repo: Repository = Depends(get_repo),
):
    """Receive and verify incoming Meetily Pro webhook notifications."""
    raw_body = await request.body()
    headers_dict = dict(request.headers)

    # 1. Signature verification
    verifier = WebhookVerifier()
    try:
        verifier.verify(raw_body, headers_dict)
    except MeetilyAuthError as e:
        logger.warning(f"Webhook authentication rejected: {e.message}")
        raise HTTPException(status_code=401, detail=e.message) from e

    # 2. Envelope parsing
    try:
        event_id, event_type, resource_id, payload = WebhookVerifier.parse_envelope(raw_body)
    except MeetilyInvalidResponse as e:
        raise HTTPException(status_code=422, detail=e.message) from e

    if not resource_id:
        raise HTTPException(status_code=422, detail="Missing required meeting resource.id in webhook envelope")

    # 3. Deduplication check
    existing = repo.get_webhook_event(event_id)
    if existing:
        logger.info(f"Duplicate webhook received: {event_id}")
        return {"status": "duplicate", "event_id": event_id, "message": "Event already processed or recorded"}

    # 4. Filter for supported event trigger (summary.completed)
    if event_type != "summary.completed":
        repo.record_webhook_event(event_id, event_type, resource_id, payload)
        repo.update_webhook_event(event_id, "ignored", error_message=f"Event type '{event_type}' not handled")
        return {"status": "ignored", "event_type": event_type, "message": "Only summary.completed triggers pipeline"}

    # 5. Record new event
    repo.record_webhook_event(event_id, event_type, resource_id, payload)

    # 6. Dispatch background task
    background_tasks.add_task(process_webhook_background, event_id, resource_id)

    # 7. Return 202 Accepted quickly
    return Response(
        content='{"status":"accepted","event_id":"' + event_id + '","resource_id":"' + resource_id + '"}',
        status_code=202,
        media_type="application/json",
    )
