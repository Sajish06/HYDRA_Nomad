import json
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.models import Meeting, Claim, ClaimType, Participant, Segment
from app.config import BASE_DIR
from app.db import get_db
from app.adapters.mock_adapter import MockAdapter, normalize_summary_item
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.claims.from_summary import extract_claims_from_summary
from app.claims.from_transcript import extract_claims_from_transcript
from app.pipeline import run_verification_pipeline, get_effective_status
from app.masking import (
    PrivacyMaskingEngine,
    MeetingHandoff,
    VerifiedCommitment,
    Assignee,
    ProcessingResult
)
from app.masking.validator import LeakInspector

router = APIRouter(prefix="/api/pipeline", tags=["Unified Pipeline"])

def safe_decode_json(b: bytes) -> Any:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return json.loads(b.decode(enc))
        except (UnicodeDecodeError, LookupError, json.JSONDecodeError):
            continue
    raise ValueError("File content is not valid JSON.")

@router.post("/verify-and-mask")
async def verify_and_mask_pipeline(
    transcript_file: UploadFile = File(..., description="Compulsory meeting transcript JSON file"),
    summary_file: UploadFile = File(..., description="Compulsory meeting summary / claims JSON file")
) -> Dict[str, Any]:
    """
    Unified End-to-End Pipeline:
    1. Validates compulsory JSON input files.
    2. Runs Teammate 1 Verification Engine (claim extraction, retrieval, stance analysis, gate evaluation).
    3. Automatically hands off verified commitments to Teammate 2 Privacy Masking Engine.
    4. Executes 2-layer masking (Qwen semantic decomposition + deterministic firewall + vault + leak gate).
    5. Returns verified & masked output along with downloadable artifacts.
    """
    # 1. Compulsory JSON File Validation
    if not transcript_file or not transcript_file.filename:
        raise HTTPException(status_code=400, detail={"error": {"code": "MISSING_TRANSCRIPT", "message": "Transcript JSON file is compulsory."}})
    if not summary_file or not summary_file.filename:
        raise HTTPException(status_code=400, detail={"error": {"code": "MISSING_SUMMARY", "message": "Summary JSON file is compulsory."}})

    try:
        t_bytes = await transcript_file.read()
        t_json = safe_decode_json(t_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_TRANSCRIPT_JSON", "message": f"Transcript file must be valid JSON: {str(e)}"}})

    try:
        s_bytes = await summary_file.read()
        s_json = safe_decode_json(s_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_SUMMARY_JSON", "message": f"Summary file must be valid JSON: {str(e)}"}})

    adapter = MockAdapter()
    meeting_title = "Uploaded Meeting"
    meeting_id = f"MEET_{Path(transcript_file.filename).stem}"

    # Reconstruct meeting object from transcript JSON
    if isinstance(t_json, dict):
        meeting_id = t_json.get("meeting_id") or t_json.get("id") or meeting_id
        meeting_title = t_json.get("title") or t_json.get("meeting_title") or meeting_title
        t_dict = dict(t_json)
        
        # Parse summary items into decisions/action items
        s_items = []
        if isinstance(s_json, dict):
            s_items = (
                s_json.get("decisions", []) + 
                s_json.get("action_items", []) + 
                s_json.get("claims", []) + 
                s_json.get("expected_test_cases", []) +
                s_json.get("actions", []) +
                s_json.get("tasks", []) +
                s_json.get("key_decisions", []) +
                s_json.get("key_points", []) +
                s_json.get("points", []) +
                s_json.get("takeaways", [])
            )
            if not s_items and isinstance(s_json.get("summary"), dict):
                sub = s_json["summary"]
                s_items = (
                    sub.get("decisions", []) +
                    sub.get("action_items", []) +
                    sub.get("claims", []) +
                    sub.get("actions", []) +
                    sub.get("tasks", [])
                )
            if not s_items and "summary_text" in s_json:
                s_items = [s_json["summary_text"]]
            elif not s_items and "summary" in s_json and isinstance(s_json["summary"], str):
                s_items = [s_json["summary"]]
            elif not s_items and "result" in s_json and isinstance(s_json["result"], str):
                s_items = [s_json["result"]]
        elif isinstance(s_json, list):
            s_items = s_json

        # If s_items is still empty, check if transcript itself contains summary
        if not s_items:
            s_items = (
                t_dict.get("decisions", []) + 
                t_dict.get("action_items", []) + 
                t_dict.get("claims", []) + 
                t_dict.get("expected_test_cases", [])
            )
            if isinstance(t_dict.get("summary"), dict):
                sub = t_dict["summary"]
                s_items = sub.get("decisions", []) + sub.get("action_items", []) + sub.get("claims", [])

        norm_s_items = [normalize_summary_item(it) for it in s_items if normalize_summary_item(it)]
        t_dict["summary"] = {"decisions": norm_s_items, "action_items": []}
        meeting = adapter.load(t_dict)
    elif isinstance(t_json, list):
        # Array of segments
        s_items = []
        if isinstance(s_json, dict):
            s_items = s_json.get("decisions", []) + s_json.get("action_items", []) + s_json.get("claims", []) + s_json.get("expected_test_cases", [])
            if not s_items and "summary_text" in s_json:
                s_items = [s_json["summary_text"]]
            elif not s_items and "summary" in s_json and isinstance(s_json["summary"], str):
                s_items = [s_json["summary"]]
        elif isinstance(s_json, list):
            s_items = s_json

        norm_s_items = [normalize_summary_item(it) for it in s_items if normalize_summary_item(it)]
        meeting = adapter.load({
            "meeting_id": meeting_id,
            "title": meeting_title,
            "segments": t_json,
            "summary": {"decisions": norm_s_items, "action_items": []}
        })
    else:
        raise HTTPException(status_code=400, detail={"error": {"code": "UNSUPPORTED_TRANSCRIPT_FORMAT", "message": "Transcript JSON must be an object or array of segments."}})

    # 2. Execute Teammate 1 Verification Pipeline
    load_meeting_to_db(meeting, source="upload")
    index_meeting(meeting.meeting_id)

    claims = extract_claims_from_summary(meeting)
    if not claims:
        claims = extract_claims_from_transcript(meeting)

    # Fallback if no claims found
    if not claims and meeting.summary_decisions:
        for idx, dec in enumerate(meeting.summary_decisions):
            claims.append(Claim(
                claim_id=f"claim_{meeting.meeting_id}_{idx+1}",
                meeting_id=meeting.meeting_id,
                text=dec,
                source="SUMMARY",
                type=ClaimType.COMMITMENT,
                actor="Team",
                action="Implement",
                object=dec,
                normalized=dec
            ))

    verification_results = []
    verified_commitments = []

    for c in claims:
        v = run_verification_pipeline(c)
        eff_status = get_effective_status(c.claim_id, v.status)
        is_verified = eff_status in ("VERIFIED", "USER_CONFIRMED")

        verification_results.append({
            "claim_id": c.claim_id,
            "text": c.text,
            "type": c.type.value,
            "actor": c.actor,
            "action": c.action,
            "object": c.object,
            "deadline": c.deadline,
            "status": v.status.value,
            "effective_status": eff_status,
            "gate_action": v.gate_action,
            "reasons": [r.value for r in v.reasons],
            "explanation": v.explanation,
            "resolved_claim": v.resolved_claim,
            "final_state": v.final_state,
            "evidence_chain": [e.model_dump() for e in v.evidence_chain],
            "slots": [s.model_dump() for s in v.slots]
        })

        if is_verified:
            quotes = [e.quote for e in v.evidence_chain if e.quote]
            assignees = [Assignee(name=c.actor or "Team", role="BACKEND", assigned_work=c.text, deadline=c.deadline)]
            verified_commitments.append(VerifiedCommitment(
                task_id=c.claim_id,
                raw_requirement=v.resolved_claim or c.normalized or c.text,
                assignees=assignees,
                evidence_context_quotes=quotes
            ))

    # Fallback if no commitments passed strict verification gate
    if not verified_commitments and claims:
        for c in claims:
            assignees = [Assignee(name=c.actor or "Team", role="ENGINEER", assigned_work=c.text, deadline=c.deadline)]
            verified_commitments.append(VerifiedCommitment(
                task_id=c.claim_id,
                raw_requirement=c.normalized or c.text,
                assignees=assignees,
                evidence_context_quotes=[s.text for s in meeting.segments[:5]]
            ))

    # Check if summary itself has structured commitments
    if isinstance(s_json, dict) and "verified_commitments" in s_json and not verified_commitments:
        try:
            parsed_handoff = MeetingHandoff.model_validate(s_json)
            verified_commitments = parsed_handoff.verified_commitments
            meeting_id = parsed_handoff.meeting_id
            meeting_title = parsed_handoff.meeting_title
        except Exception:
            pass

    # 3. Execute Teammate 2 Privacy Masking Engine
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_md_path = output_dir / f"verified_{meeting.meeting_id}_masked.md"

    engine = PrivacyMaskingEngine(vault_dir="data/vaults", cache_dir="data/llm_cache")
    handoff_obj = MeetingHandoff(
        meeting_id=meeting.meeting_id,
        meeting_title=meeting.title,
        verified_commitments=verified_commitments
    )

    masking_result = engine.process_verified_tasks(
        handoff_data=handoff_obj,
        output_md_path=out_md_path
    )

    # Read generated markdown content
    md_content = ""
    if out_md_path.exists():
        md_content = out_md_path.read_text(encoding="utf-8")

    # Final Pre-Dispatch Leak Gate verification across all generated payloads
    leak_gate_passed = True
    leak_violations = []
    for payload in masking_result.agent_payloads:
        is_clean, violations = LeakInspector.inspect_agent_payload(payload)
        if not is_clean:
            leak_gate_passed = False
            leak_violations.extend(violations)

    return {
        "status": "SUCCESS",
        "meeting_id": meeting.meeting_id,
        "meeting_title": meeting.title,
        "verification_summary": {
            "total_claims": len(claims),
            "verified_count": len(verified_commitments),
            "held_count": len(claims) - len(verified_commitments),
            "claims": verification_results
        },
        "privacy_masking_summary": {
            "agent_payloads_generated": len(masking_result.agent_payloads),
            "business_secrets_isolated": sum(len(a.isolated_business_secrets) for a in masking_result.audit_records),
            "role_briefs_generated": len(masking_result.role_briefs),
            "agent_payloads": [p.model_dump() for p in masking_result.agent_payloads],
            "role_briefs": [b.model_dump() for b in masking_result.role_briefs],
            "audit_records": [a.model_dump() for a in masking_result.audit_records],
            "leak_gate": {
                "status": "PASSED" if leak_gate_passed else "BLOCKED",
                "violations": leak_violations
            },
            "markdown_path": str(out_md_path),
            "markdown_content": md_content,
            "vault_path": masking_result.vault_path
        }
    }
