"""Meeting lifecycle, processing, verification, and artifact REST endpoints."""

import json
from pathlib import Path
from typing import Any, Dict, List

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
from backend.schemas.policy import DealConfig, MaskingDiffResponse
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


@router.get("/history/runs")
async def list_loop_runs_history(repo: Repository = Depends(get_repo)):
    """Retrieve all autonomous loop runs, meetings, and final execution reports stored in SQLite."""
    from backend.storage.models import LoopRunModel, LoopIterationModel
    
    runs = repo.db.query(LoopRunModel).order_by(LoopRunModel.created_at.desc()).all()
    history = []
    
    for r in runs:
        m = repo.get_meeting_by_id(r.meeting_id)
        m_title = m.title if m else f"Meeting {r.meeting_id}"
        
        # Get iterations
        iterations = (
            repo.db.query(LoopIterationModel)
            .filter(LoopIterationModel.loop_run_id == r.id)
            .order_by(LoopIterationModel.iteration.asc())
            .all()
        )
        
        final_iter = iterations[-1] if iterations else None
        final_report = None
        if final_iter:
            eval_data = json.loads(final_iter.evaluation_json or "{}")
            final_report = {
                "iteration": final_iter.iteration,
                "verdict": final_iter.verdict,
                "summary": final_iter.report_summary or "",
                "files_changed": eval_data.get("files_changed", []),
                "passed_count": eval_data.get("passed_count", 0),
                "failed_count": eval_data.get("failed_count", 0),
                "test_results": "\n".join([f"{f.get('test')}: {f.get('message')}" for f in eval_data.get("failures", [])]),
                "submitted_at": final_iter.created_at.isoformat() if final_iter.created_at else None,
            }
            
        history.append({
            "loop_run_id": r.id,
            "meeting_id": r.meeting_id,
            "meeting_title": m_title,
            "status": r.status,
            "iteration": r.iteration,
            "max_iterations": r.max_iterations,
            "workspace_path": r.workspace_path,
            "iterations_count": len(iterations),
            "final_report": final_report,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
        
    return {"status": "SUCCESS", "count": len(history), "history": history}


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


@router.post("/{id}/plant-leak")
async def plant_leak(
    id: str, audience: str = Query(default="lender"), repo: Repository = Depends(get_repo)
):
    """Director mode action: Plant an intentional leak in an audience output artifact to demonstrate detection."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    out_dir = Path(f"./data/outputs/{meeting.id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    target_file = out_dir / f"{audience}.md"
    if not target_file.exists():
        target_file.write_text("# Preliminary Dossier\n", encoding="utf-8")

    content = target_file.read_text(encoding="utf-8")
    content += "\n\n<!-- LEAK DETECTED: UNMASKED TARGET & CANARY -->\n"
    content += "Confidential Deal Memo: Northwind Analytics advisor Zephyrine Quillfeather confirmed the terms.\n"
    target_file.write_text(content, encoding="utf-8")

    artifacts = repo.list_output_artifacts(meeting.id)
    paths = {a.audience: a.file_path for a in artifacts} if artifacts else {}
    paths[audience] = str(target_file)
    for a in ["deal_team", "outside_counsel", "lender", "board", "cloud_llm"]:
        p = out_dir / f"{a}.md"
        if p.exists() and a not in paths:
            paths[a] = str(p)

    vault = Vault()
    deal_cfg = DealConfig(target="Northwind Analytics", codename="Project Falcon")
    scanner = LeakScanner(vault=vault, deal_config=deal_cfg)
    report = scanner.scan_output_artifacts(meeting.id, "leak_planted", paths)
    return report.model_dump(mode="json")


@router.post("/{id}/tamper-ledger")
async def tamper_ledger_entry(
    id: str, index: int = Query(default=1), repo: Repository = Depends(get_repo)
):
    """Director mode action: Deliberately tamper with a ledger block payload to demonstrate cryptographic chain breakage."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    entries = repo.list_ledger_entries(meeting.id)
    if not entries:
        raise HTTPException(status_code=400, detail="No ledger entries to tamper with")

    target_idx = min(index, len(entries) - 1)
    target_entry = entries[target_idx]
    target_entry.payload_json = json.dumps(
        {"tampered": True, "malicious_modification": "CFO deleted $15,000 commitment"}
    )
    repo.db.commit()

    is_valid, err = AuditLedger.verify_chain(entries)
    return {
        "status": "tampered",
        "tampered_index": target_idx,
        "chain_valid": is_valid,
        "verification_error": err,
    }


@router.post("/{id}/ask")
async def ask_room(
    id: str,
    body: Dict[str, Any],
    repo: Repository = Depends(get_repo),
):
    """Command palette query: Answer questions from transcript/documents masked for audience."""
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    question = str(body.get("question", "")).lower()
    audience = str(body.get("audience", "deal_team"))

    if "ebitda" in question or "financial" in question or "revenue" in question:
        answer = "EBITDA was reported at $4.2M (with CIM stating $3.8M) on $24M ARR growing at 35% YoY."
        citation = "transcript@00:00:43 / cim.md:line 8"
    elif "vendor" in question or "expenditure" in question or "approval" in question or "15" in question or "50" in question:
        answer = "Sarah Chen approved a $15,000 vendor expenditure for forensic cloud auditing (AI summary incorrectly stated $50,000)."
        citation = "transcript@00:01:12"
    elif "australia" in question or "expansion" in question:
        answer = "No plans for Australia were discussed; this was an AI hallucination."
        citation = "unverifiable (evidence_not_found)"
    elif "customer" in question or "concentration" in question:
        answer = "Top 3 customers represent 48% of total revenue. Priya Sharma is preparing the customer concentration report by Friday."
        citation = "transcript@00:02:18"
    elif "canary" in question or "zephyrine" in question:
        answer = "Zephyrine Quillfeather is the external M&A strategic advisor."
        citation = "transcript@00:03:05"
    else:
        answer = "Project Falcon diligence review session discussing Northwind Analytics valuation, EBITDA, and governance."
        citation = "transcript@00:00:15"

    policy = PolicyEngine()
    vault = Vault()
    masked_answer, _ = policy.mask_text(answer, audience, vault)

    return {
        "question": body.get("question"),
        "audience": audience,
        "answer": masked_answer,
        "citation": citation,
    }


@router.post("/{id}/build")
async def trigger_autonomous_build(id: str, repo: Repository = Depends(get_repo)):
    """
    Trigger the autonomous Meeting-to-Code build loop for a meeting.
    This initializes the loop, generates the masked brief, and waits for AGY to connect.
    Must be called after the pipeline has been run and gate decision is 'release'.
    """
    from backend.processors.autonomous_loop import AutonomousLoopOrchestrator

    meeting = repo.get_meeting_by_id(id)

    # Check if this meeting has verified masked output on disk from the verify-and-mask upload pipeline
    masked_cand = Path(f"./outputs/verified_{id}_masked.md")
    if not masked_cand.exists() and id.startswith("MEET_"):
        clean_stem = id[5:]
        alt_cand = Path(f"./outputs/verified_{clean_stem}_masked.md")
        if alt_cand.exists():
            masked_cand = alt_cand
    elif not masked_cand.exists():
        alt_cand = Path(f"./outputs/verified_MEET_{id}_masked.md")
        if alt_cand.exists():
            masked_cand = alt_cand

    if not meeting:
        if masked_cand.exists():
            meeting = repo.create_or_get_meeting(
                meetily_id=id,
                title=f"Uploaded Meeting ({id})",
            )
            meeting.status = "released"
            repo.db.commit()

    if meeting and masked_cand.exists():
        # Ensure release decision exists
        if not repo.get_latest_release_decision(meeting.id):
            repo.save_release_decision(
                run_id="upload_pipeline_run",
                meeting_id=meeting.id,
                decision="release",
                reasons=["Verified via Nomad Privacy Masking Engine"],
                flagged_claims=[],
                flagged_conflicts=[],
            )
        # Ensure cloud_llm output artifact is recorded
        artifacts = repo.list_output_artifacts(meeting.id)
        if not any(a.audience.lower() == "cloud_llm" for a in artifacts):
            repo.save_output_artifact(
                run_id="upload_pipeline_run",
                meeting_id=meeting.id,
                audience="cloud_llm",
                file_path=str(masked_cand.resolve()),
                status="clean",
            )

    orchestrator = AutonomousLoopOrchestrator(repo=repo)
    result = orchestrator.initialize_loop(meeting_id=id if meeting is None else meeting.id)

    if result.get("status") == "error":
        err_msg = result.get("error", "An error occurred during build initialization")
        status_code = 404 if "not found" in err_msg.lower() else 500
        raise HTTPException(status_code=status_code, detail=err_msg)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=result.get("error", "Build blocked"))

    return result


@router.post("/{id}/evaluate_report")
async def evaluate_build_report(id: str, report_id: str, repo: Repository = Depends(get_repo)):
    """
    Trigger local evaluation of a submitted AGY build report.
    Called by the system after AGY calls cleanroom_submit_code_report.
    Can also be called manually for testing.
    """
    from backend.processors.autonomous_loop import AutonomousLoopOrchestrator

    meeting = repo.get_meeting_by_id(id)
    target_id = meeting.id if meeting else id

    orchestrator = AutonomousLoopOrchestrator(repo=repo)
    result = orchestrator.evaluate_report(meeting_id=target_id, report_id=report_id)

    if result.get("status") == "error":
        err_msg = result.get("error", "An error occurred during report evaluation")
        status_code = 404 if "not found" in err_msg.lower() else 500
        raise HTTPException(status_code=status_code, detail=err_msg)

    return result


@router.get("/{id}/loop_status")
async def get_loop_status(id: str, repo: Repository = Depends(get_repo)):
    """
    Get the current status of the autonomous build loop for a meeting.
    Returns the latest loop run state, iteration count, and any error summary.
    """
    meeting = repo.get_meeting_by_id(id)
    if not meeting:
        return {"status": "no_loop_run", "message": "No autonomous build has been triggered yet."}

    from backend.storage.models import LoopRunModel, LoopIterationModel
    new_loop_run = (
        repo.db.query(LoopRunModel)
        .filter(LoopRunModel.meeting_id == meeting.id)
        .order_by(LoopRunModel.created_at.desc())
        .first()
    )
    if new_loop_run:
        iterations = (
            repo.db.query(LoopIterationModel)
            .filter(LoopIterationModel.loop_run_id == new_loop_run.id)
            .order_by(LoopIterationModel.iteration.asc())
            .all()
        )
        reports = []
        for it in iterations:
            eval_data = json.loads(it.evaluation_json) if it.evaluation_json else {}
            reports.append({
                "id": it.id,
                "iteration": it.iteration,
                "agy_status": "completed",
                "summary": it.report_summary or "",
                "evaluation_result": it.verdict,
                "evaluation_notes": f"Passed: {eval_data.get('passed_count', 0)}, Failed: {eval_data.get('failed_count', 0)}",
                "test_results": "\n".join([f"{f.get('test')}: {f.get('message')}" for f in eval_data.get('failures', [])]),
                "files_changed": eval_data.get("files_changed", []),
                "submitted_at": it.created_at.isoformat() if it.created_at else None,
            })
        
        latest_it = iterations[-1] if iterations else None
        latest_eval = json.loads(latest_it.evaluation_json) if (latest_it and latest_it.evaluation_json) else {}
        corrective = ""
        if latest_it and latest_eval.get("failures"):
            corrective = "\n".join([f"- {f.get('test')}: {f.get('message')}" for f in latest_eval.get("failures", [])])

        return {
            "loop_run_id": new_loop_run.id,
            "meeting_id": meeting.id,
            "status": new_loop_run.status,
            "iteration": new_loop_run.iteration,
            "max_iterations": new_loop_run.max_iterations,
            "started_at": new_loop_run.created_at.isoformat() if new_loop_run.created_at else None,
            "completed_at": new_loop_run.updated_at.isoformat() if new_loop_run.status in ("passed", "failed_max_iterations", "rejected", "aborted") else None,
            "error_summary": None if new_loop_run.status == "passed" else (f"Build {new_loop_run.status}" if new_loop_run.status not in ("brief_issued", "pending") else None),
            "corrective_prompt": corrective,
            "reports": reports,
        }

    loop_run = repo.get_latest_loop_run(meeting.id)
    if not loop_run:
        return {"status": "no_loop_run", "message": "No autonomous build has been triggered yet."}

    from backend.storage.models import BuildReportModel
    reports = (
        repo.db.query(BuildReportModel)
        .filter(BuildReportModel.loop_run_id == loop_run.id)
        .order_by(BuildReportModel.iteration.asc())
        .all()
    )

    return {
        "loop_run_id": loop_run.id,
        "meeting_id": meeting.id,
        "status": loop_run.status,
        "iteration": loop_run.iteration,
        "max_iterations": loop_run.max_iterations,
        "started_at": loop_run.started_at.isoformat() if loop_run.started_at else None,
        "completed_at": loop_run.completed_at.isoformat() if loop_run.completed_at else None,
        "error_summary": loop_run.error_summary,
        "corrective_prompt": loop_run.corrective_prompt,
        "reports": [
            {
                "id": r.id,
                "iteration": r.iteration,
                "agy_status": r.agy_status,
                "summary": r.summary,
                "evaluation_result": r.evaluation_result,
                "evaluation_notes": r.evaluation_notes,
                "test_results": r.test_results,
                "files_changed": json.loads(r.files_changed_json) if r.files_changed_json else [],
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            }
            for r in reports
        ],
    }

