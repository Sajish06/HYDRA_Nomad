"""Demo execution endpoint and static demo dashboard serving."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from backend.dependencies import get_repo
from backend.meetily.schema_adapter import MeetilySchemaAdapter
from backend.processors.ledger import AuditLedger
from backend.processors.pipeline import PipelineOrchestrator
from backend.storage.repository import Repository

router = APIRouter(tags=["demo"])


@router.post("/api/demo/run")
async def run_demo_pipeline(repo: Repository = Depends(get_repo)):
    """Run the complete M&A diligence synthetic demo offline."""
    demo_dir = Path("./data/demo")
    transcript_file = demo_dir / "sample_transcript.json"
    summary_file = demo_dir / "sample_summary.json"

    if not transcript_file.exists() or not summary_file.exists():
        raise HTTPException(
            status_code=500, detail="Synthetic demo data not found in data/demo/"
        )

    # 1. Load synthetic data
    with open(transcript_file, "r", encoding="utf-8") as f:
        t_data = json.load(f)
    with open(summary_file, "r", encoding="utf-8") as f:
        s_data = json.load(f)

    # 2. Parse into domain models
    meeting_id = "demo_falcon_diligence"
    transcript = MeetilySchemaAdapter.parse_transcript(meeting_id, t_data)
    summary = MeetilySchemaAdapter.parse_summary(meeting_id, s_data)

    # 3. Store in DB
    meeting = repo.create_or_get_meeting(
        meetily_id=meeting_id,
        title="Project Falcon: Northwind Analytics Diligence Session",
        duration_seconds=1800.0,
    )
    repo.update_meeting_data(
        meeting_id=meeting.id,
        transcript_sha256=transcript.sha256_hash,
        raw_transcript=transcript.raw_text,
        raw_summary=summary.summary_text,
        status="synced",
    )

    # 4. Execute Clean Room pipeline
    orchestrator = PipelineOrchestrator(repo=repo)
    run, decision, v_res, leak_rep = await orchestrator.execute_run(
        meeting.id, transcript, summary
    )

    # 5. Cross-check conflicts
    conflicts = orchestrator.crosschecker.cross_check(transcript)

    # 6. Fetch review items & ledger
    review_items = repo.list_review_items(meeting.id)
    ledger_entries = repo.list_ledger_entries(meeting.id)
    is_valid, err = AuditLedger.verify_chain(ledger_entries)

    # 7. Check egress log
    egress_file = Path(f"./data/outputs/{meeting.id}/ai_egress.jsonl")
    egress_lines = []
    if egress_file.exists():
        for line in egress_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    egress_lines.append(json.loads(line))
                except Exception:
                    pass

    # 8. Format preview audience outputs and compute diffs
    policy = orchestrator.policy
    audience_outputs = {}
    masking_diffs = {}
    preview_paths = {}
    out_dir = Path(f"./data/outputs/{meeting.id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    for aud in ["deal_team", "outside_counsel", "lender", "board", "cloud_llm"]:
        m_sum = policy.apply_to_summary(summary, aud, orchestrator.vault)
        m_cls = policy.apply_to_claims(v_res.claims, aud, orchestrator.vault)
        md_text = orchestrator.distributor.format_audience_markdown(aud, m_sum, m_cls)
        audience_outputs[aud] = md_text
        masking_diffs[aud] = policy.diff(summary.summary_text, aud, orchestrator.vault).model_dump(mode="json")
        fpath = out_dir / f"{aud}.md"
        fpath.write_text(md_text, encoding="utf-8")
        preview_paths[aud] = str(fpath)

    preview_scan = orchestrator.scanner.scan_output_artifacts(meeting.id, "preview_scan", preview_paths)

    return {
        "status": "success",
        "meeting_id": meeting.id,
        "run_id": run.id,
        "gate_decision": decision.decision.value,
        "reasons": decision.reasons,
        "verification": v_res.model_dump(mode="json"),
        "conflicts": [c.model_dump(mode="json") for c in conflicts],
        "review_items": [
            {
                "id": it.id,
                "item_type": it.item_type,
                "reference_id": it.reference_id,
                "original_text": it.original_text,
                "issue_type": it.issue_type,
                "status": it.status,
            }
            for it in review_items
        ],
        "ledger": {
            "chain_valid": is_valid,
            "verification_error": err,
            "entries_count": len(ledger_entries),
            "entries": [
                {
                    "index": e.index,
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                    "payload": json.loads(e.payload_json) if e.payload_json else {},
                    "prev_hash": e.prev_hash,
                    "entry_hash": e.entry_hash,
                }
                for e in ledger_entries
            ],
        },
        "egress_logs": egress_lines,
        "transcript": transcript.model_dump(mode="json"),
        "summary": summary.model_dump(mode="json"),
        "audience_outputs": audience_outputs,
        "masking_diffs": masking_diffs,
        "leak_report": (leak_rep or preview_scan).model_dump(mode="json"),
        "deal": {
            "target": "Northwind Analytics",
            "codename": "Project Falcon",
            "canary": "Zephyrine Quillfeather",
        },
    }


from fastapi.responses import RedirectResponse

@router.get("/demo")
async def serve_demo_ui():
    """Redirect to unified NOMAD Verification & Privacy Masking frontend."""
    return RedirectResponse(url="/")

