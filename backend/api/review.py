"""Human review loop API endpoints for resolving flagged claims and conflicts."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_repo
from backend.processors.pipeline import PipelineOrchestrator
from backend.schemas.meeting import MeetingSummary, MeetingTranscript
from backend.schemas.release import ReviewDecisionRequest, ReviewItem
from backend.storage.repository import Repository

router = APIRouter(tags=["review"])


@router.get("/api/meetings/{id}/review", response_model=List[ReviewItem])
async def list_meeting_review_items(id: str, repo: Repository = Depends(get_repo)):
    """List pending review items for a meeting."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    items = repo.list_review_items(meeting.id)
    return [
        ReviewItem(
            id=it.id,
            meeting_id=it.meeting_id,
            run_id=it.run_id,
            item_type=it.item_type,
            reference_id=it.reference_id,
            original_text=it.original_text,
            issue_type=it.issue_type,
            suggested_fix=it.suggested_fix,
            status=it.status,
            corrected_text=it.corrected_text,
            reviewer_notes=it.reviewer_notes,
            resolved_at=it.resolved_at,
        )
        for it in items
    ]


@router.post("/api/review/{item_id}/decision")
async def record_review_decision(
    item_id: str,
    decision_req: ReviewDecisionRequest,
    repo: Repository = Depends(get_repo),
):
    """Record reviewer resolution ('approved', 'corrected', or 'rejected'). Resumes pipeline if all items resolved."""
    item = repo.get_review_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")

    updated = repo.update_review_item(
        item_id=item_id,
        status=decision_req.action.value,
        corrected_text=decision_req.corrected_text,
        reviewer_notes=decision_req.reviewer_notes,
    )

    meeting = repo.get_meeting_by_id(item.meeting_id)
    all_items = repo.list_review_items(item.meeting_id)
    all_resolved = all(it.status in ("approved", "corrected", "rejected") for it in all_items)

    pipeline_resumed = False
    release_decision = None

    if all_resolved and meeting:
        # Re-trigger pipeline release loop
        transcript = MeetingTranscript(
            meeting_id=meeting.id,
            segments=[],
            raw_text=meeting.raw_transcript or "",
            sha256_hash=meeting.transcript_sha256 or "hash",
        )
        summary = MeetingSummary(
            meeting_id=meeting.id,
            summary_text=meeting.raw_summary or "",
        )

        orchestrator = PipelineOrchestrator(repo=repo)
        try:
            _, release_dec, _, _ = await orchestrator.resume_after_review(
                meeting_id=meeting.id,
                transcript=transcript,
                summary=summary,
                reviewer_name="Compliance Reviewer",
            )
            pipeline_resumed = True
            release_decision = release_dec.decision.value
        except Exception as e:
            release_decision = f"error: {str(e)}"

    return {
        "item_id": updated.id,
        "status": updated.status,
        "all_items_resolved": all_resolved,
        "pipeline_resumed": pipeline_resumed,
        "release_decision": release_decision,
    }
