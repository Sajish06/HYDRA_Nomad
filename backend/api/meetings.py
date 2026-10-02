"""Meeting lifecycle, processing, verification, and artifact REST endpoints."""

import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.config import settings
from backend.dependencies import get_repo
from backend.meetily.client import MeetilyClient
from backend.meetily.meetings import MeetingSyncService
from backend.processors.crosscheck import CrossCheckEngine
from backend.processors.leakscan import LeakScanner
from backend.processors.ledger import AuditLedger
from backend.processors.pipeline import PipelineOrchestrator
from backend.processors.policy import PolicyEngine
from backend.processors.privacy import Vault
from backend.schemas.meeting import (
    MeetingResponse,
    MeetingSummary,
    MeetingTranscript,
)
from backend.schemas.policy import MaskingDiffResponse
from backend.storage.repository import Repository

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


@router.get("", response_model=List[MeetingResponse])
async def list_meetings(repo: Repository = Depends(get_repo)):
    """List all registered meetings."""
    meetings = repo.list_meetings()
    return [
        MeetingResponse(
            id=m.id,
            meetily_id=m.meetily_id,
            title=m.title,
            created_at=m.created_at,
            duration_seconds=m.duration_seconds,
            status=m.status,
            transcript_hash=m.transcript_sha256,
        )
        for m in meetings
    ]


@router.get("/{id}", response_model=MeetingResponse)
async def get_meeting(id: str, repo: Repository = Depends(get_repo)):
    """Get meeting metadata and summary. Raw transcript omitted unless EXPOSE_RAW_TRANSCRIPTS=true."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    resp = MeetingResponse(
        id=meeting.id,
        meetily_id=meeting.meetily_id,
        title=meeting.title,
        created_at=meeting.created_at,
        duration_seconds=meeting.duration_seconds,
        status=meeting.status,
        transcript_hash=meeting.transcript_sha256,
        summary=MeetingSummary(
            meeting_id=meeting.id,
            summary_text=meeting.raw_summary or "",
        )
        if meeting.raw_summary
        else None,
    )

    if settings.EXPOSE_RAW_TRANSCRIPTS and meeting.raw_transcript:
        resp.transcript = MeetingTranscript(
            meeting_id=meeting.id,
            segments=[],
            raw_text=meeting.raw_transcript,
            sha256_hash=meeting.transcript_sha256 or "",
        )

    return resp


@router.post("/{id}/sync")
async def sync_meeting_from_gateway(id: str, repo: Repository = Depends(get_repo)):
    """Pull latest meeting metadata, transcript, and summary from Meetily Pro gateway."""
    client = MeetilyClient()
    service = MeetingSyncService(client=client, repo=repo)
    try:
        meeting, transcript, summary = await service.sync_meeting(id)
        return {
            "status": "synced",
            "meeting_id": meeting.id,
            "meetily_id": meeting.meetily_id,
            "segments_count": len(transcript.segments),
            "transcript_hash": transcript.sha256_hash,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to sync with Meetily: {str(e)}") from e


@router.post("/{id}/process")
async def process_meeting(id: str, repo: Repository = Depends(get_repo)):
    """Trigger the Clean Room pipeline on an existing meeting."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.raw_summary and not meeting.transcript_sha256:
        raise HTTPException(
            status_code=400,
            detail="Meeting has no transcript or summary. Call /sync first or use demo data.",
        )

    # Reconstruct transcript and summary models
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
    run, decision, v_res, leak_rep = await orchestrator.execute_run(meeting.id, transcript, summary)

    return {
        "run_id": run.id,
        "meeting_id": meeting.id,
        "status": run.status,
        "current_stage": run.current_stage,
        "gate_decision": decision.decision.value,
        "reasons": decision.reasons,
        "flagged_claims_count": len(decision.flagged_claim_ids),
        "flagged_conflicts_count": len(decision.flagged_conflict_ids),
    }


@router.get("/{id}/status")
async def get_processing_status(id: str, repo: Repository = Depends(get_repo)):
    """Check status and stage timings of the latest processing run."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    run = repo.get_latest_run(meeting.id)
    if not run:
        return {"status": "none", "meeting_id": meeting.id}

    timings = {}
    if run.timings_json:
        try:
            timings = json.loads(run.timings_json)
        except Exception:
            pass

    return {
        "run_id": run.id,
        "meeting_id": meeting.id,
        "status": run.status,
        "current_stage": run.current_stage,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "error_message": run.error_message,
        "timings": timings,
    }


@router.post("/{id}/retry")
async def retry_processing(id: str, repo: Repository = Depends(get_repo)):
    """Retry execution of a failed processing run."""
    return await process_meeting(id, repo)


@router.get("/{id}/verification")
async def get_verification_results(id: str, repo: Repository = Depends(get_repo)):
    """Retrieve detailed claims verification results and verdicts."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    data = repo.get_latest_verification(meeting.id)
    if not data:
        raise HTTPException(status_code=404, detail="No verification results found for this meeting")
    return data


@router.get("/{id}/intelligence")
async def get_intelligence_results(id: str, repo: Repository = Depends(get_repo)):
    """Retrieve extracted M&A intelligence findings."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    data = repo.get_latest_intelligence(meeting.id)
    if not data:
        raise HTTPException(status_code=404, detail="No intelligence findings found for this meeting")
    return data


@router.get("/{id}/conflicts")
async def get_cross_source_conflicts(id: str, repo: Repository = Depends(get_repo)):
    """Retrieve cross-source discrepancies between meeting statements and diligence documents."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Run cross-check on current transcript
    transcript = MeetingTranscript(
        meeting_id=meeting.id,
        segments=[],
        raw_text=meeting.raw_transcript or "",
        sha256_hash=meeting.transcript_sha256 or "hash",
    )
    crosschecker = CrossCheckEngine()
    conflicts = crosschecker.cross_check(transcript)
    return [c.model_dump(mode="json") for c in conflicts]


@router.get("/{id}/outputs")
async def list_audience_outputs(id: str, repo: Repository = Depends(get_repo)):
    """List generated audience output artifacts."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    artifacts = repo.list_output_artifacts(meeting.id)
    return [
        {
            "id": a.id,
            "audience": a.audience,
            "file_path": a.file_path,
            "status": a.status,
            "canary_present": a.canary_present,
            "created_at": a.created_at,
        }
        for a in artifacts
    ]


@router.get("/{id}/outputs/{audience}")
async def get_audience_output_content(
    id: str, audience: str, repo: Repository = Depends(get_repo)
):
    """Retrieve the text content of a specific audience output artifact."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    artifacts = repo.list_output_artifacts(meeting.id)
    matching = next((a for a in artifacts if a.audience.lower() == audience.lower()), None)
    if not matching:
        raise HTTPException(status_code=404, detail=f"No output found for audience '{audience}'")

    path = Path(matching.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact file not found on disk: {path}")

    return {
        "audience": audience,
        "status": matching.status,
        "canary_present": matching.canary_present,
        "content": path.read_text(encoding="utf-8"),
    }


@router.get("/{id}/leakscan")
async def get_leak_scan_report(id: str, repo: Repository = Depends(get_repo)):
    """Run/retrieve leak scan report across all generated audience outputs."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    artifacts = repo.list_output_artifacts(meeting.id)
    paths = {a.audience: a.file_path for a in artifacts}

    vault = Vault()
    scanner = LeakScanner(vault=vault)
    report = scanner.scan_output_artifacts(meeting.id, "scan_check", paths)
    return report.model_dump(mode="json")


@router.get("/{id}/masking-diff", response_model=MaskingDiffResponse)
async def get_masking_diff(
    id: str,
    audience: str = Query(default="outside_counsel"),
    repo: Repository = Depends(get_repo),
):
    """Get original vs masked diff spans for UI side-by-side visualization."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    policy = PolicyEngine()
    vault = Vault()
    text = meeting.raw_summary or "Sarah Chen reported $4.2M EBITDA."
    return policy.diff(text, audience, vault)


@router.get("/{id}/ledger")
async def get_ledger(id: str, repo: Repository = Depends(get_repo)):
    """Retrieve chronological audit ledger entries and verify cryptographic integrity."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    entries = repo.list_ledger_entries(meeting.id)
    is_valid, err = AuditLedger.verify_chain(entries)

    return {
        "meeting_id": meeting.id,
        "chain_valid": is_valid,
        "verification_error": err,
        "entries_count": len(entries),
        "entries": [
            {
                "index": e.index,
                "event_type": e.event_type,
                "timestamp": e.timestamp,
                "payload": json.loads(e.payload_json) if e.payload_json else {},
                "prev_hash": e.prev_hash,
                "entry_hash": e.entry_hash,
            }
            for e in entries
        ],
    }
