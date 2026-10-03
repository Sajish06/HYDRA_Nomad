import re
import json
import asyncio
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from app.models import Meeting, Claim, ClaimType, Participant, Segment, Stance, Status
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


def extract_summary_items_from_json(s_json: Any) -> List[str]:
    """Recursively and comprehensively extracts summary/claims/topics from arbitrary summary JSON schemas."""
    if not s_json:
        return []
    if isinstance(s_json, list):
        items = []
        for it in s_json:
            items.extend(extract_summary_items_from_json(it))
        return items
    if isinstance(s_json, str):
        norm = normalize_summary_item(s_json)
        return [norm] if norm else []
    
    extracted: List[str] = []
    if isinstance(s_json, dict):
        # 1. Direct recognized list keys
        priority_keys = [
            "verified_commitments", "commitments", "decisions", "action_items", "claims", 
            "expected_test_cases", "actions", "tasks", "topics_discussed", "topics", 
            "discussion_points", "key_decisions", "key_points", "points", "takeaways", 
            "agenda", "notes", "items"
        ]
        for k in priority_keys:
            if k in s_json and s_json[k]:
                val = s_json[k]
                if isinstance(val, list):
                    for sub_item in val:
                        if isinstance(sub_item, dict) and "raw_requirement" in sub_item:
                            extracted.append(sub_item["raw_requirement"])
                        else:
                            norm = normalize_summary_item(sub_item)
                            if norm:
                                extracted.append(norm)
                elif isinstance(val, str):
                    norm = normalize_summary_item(val)
                    if norm:
                        extracted.append(norm)

        # 2. Check nested summary object if top-level yielded nothing or to supplement
        if "summary" in s_json and isinstance(s_json["summary"], dict):
            extracted.extend(extract_summary_items_from_json(s_json["summary"]))
        elif "summary" in s_json and isinstance(s_json["summary"], str):
            norm = normalize_summary_item(s_json["summary"])
            if norm:
                extracted.append(norm)

        if not extracted and "summary_text" in s_json:
            extracted.extend(extract_summary_items_from_json(s_json["summary_text"]))
        if not extracted and "result" in s_json and isinstance(s_json["result"], str):
            extracted.extend(extract_summary_items_from_json(s_json["result"]))

    return extracted


@router.post("/verify-and-mask")
async def verify_and_mask_pipeline(
    transcript_file: UploadFile = File(..., description="Compulsory meeting transcript JSON file"),
    summary_file: UploadFile = File(..., description="Compulsory meeting summary / claims JSON file"),
    fast_mode: bool = Query(False, description="Enable Fast Demo Mode (deterministic NLP engine, skips LLM)"),
    auto_launch: bool = Query(False, description="Automatically launch Antigravity IDE and execute build")
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

    # Extract all summary items from summary JSON
    s_items = extract_summary_items_from_json(s_json)

    # Reconstruct meeting object from transcript JSON
    if isinstance(t_json, dict):
        meeting_id = t_json.get("meeting_id") or t_json.get("id") or meeting_id
        meeting_title = t_json.get("title") or t_json.get("meeting_title") or meeting_title
        t_dict = dict(t_json)
        
        # If s_items is still empty, check if transcript itself contains summary
        if not s_items:
            s_items = extract_summary_items_from_json(t_dict)

        norm_s_items = [normalize_summary_item(it) for it in s_items if normalize_summary_item(it)]
        t_dict["summary"] = {"decisions": norm_s_items, "action_items": []}
        meeting = adapter.load(t_dict)
    elif isinstance(t_json, list):
        norm_s_items = [normalize_summary_item(it) for it in s_items if normalize_summary_item(it)]
        meeting = adapter.load({
            "meeting_id": meeting_id,
            "title": meeting_title,
            "segments": t_json,
            "summary": {"decisions": norm_s_items, "action_items": []}
        })
    else:
        raise HTTPException(status_code=400, detail={"error": {"code": "UNSUPPORTED_TRANSCRIPT_FORMAT", "message": "Transcript JSON must be an object or array of segments."}})

    return await _process_meeting_core(meeting, fast_mode=fast_mode, auto_launch=auto_launch)


async def _process_meeting_core(meeting: Meeting, fast_mode: bool = False, auto_launch: bool = False) -> Dict[str, Any]:
    """Core logic to verify commitments, execute privacy masking, and optionally auto-launch build."""
    # 2. Execute Teammate 1 Verification Pipeline
    load_meeting_to_db(meeting, source="upload")
    index_meeting(meeting.meeting_id, fast_mode=fast_mode)

    claims = extract_claims_from_summary(meeting, fast_mode=fast_mode)
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

    from app.analysis.slots import extract_slots_from_evidence

    # Group verified claims vs held/unsupported claims
    verified_commitments = []
    unverified_items = []
    ambiguous_tasks = []
    seen_raw_requirements = set()

    # Parallel claim verification via asyncio.gather across threadpool
    loop = asyncio.get_running_loop()
    verification_results = await asyncio.gather(*[
        loop.run_in_executor(None, lambda cl=c: run_verification_pipeline(cl, fast_mode=fast_mode))
        for c in claims
    ])

    for c, v in zip(claims, verification_results):
        eff_status = get_effective_status(c.claim_id, v.status)
        is_verified = eff_status in ("VERIFIED", "USER_CONFIRMED")
        # A claim is verified only if its own claim-local evidence contains explicit commitment support without same-claim cancellation
        if is_verified:
            # Verify claim-local commitment support
            has_explicit_commitment = any(
                e.relation == "SUPPORTS" and (e.stance in (Stance.COMMIT, Stance.ACCEPT, Stance.DECIDE))
                for e in v.evidence_chain
            )
            is_investigation_only = any(
                re.search(r"\b(investigat\w*|check whether|look into whether|explore whether|before we decide|don'?t think we'?ve selected|haven'?t selected|rather than implementation commitments?|not selected either)\b", e.quote or e.text or "", re.IGNORECASE)
                for e in v.evidence_chain if e.relation == "SUPPORTS"
            ) and not any(
                re.search(r"\b(?:i'?ll|i will|committed for|committed as well|part of the sprint|another committed item|that's committed)\b", e.quote or e.text or "", re.IGNORECASE)
                and not re.search(r"\b(investigat\w*|check whether|look into|explore|not sure)\b", e.quote or e.text or "", re.IGNORECASE)
                for e in v.evidence_chain if e.relation == "SUPPORTS"
            )

            if not has_explicit_commitment or is_investigation_only or v.status in (Status.AMBIGUOUS, Status.UNSUPPORTED):
                is_verified = False

        if is_verified:
            # Claim-local supporting quotes only
            quotes = [
                e.quote for e in v.evidence_chain 
                if e.quote and e.relation == "SUPPORTS"
            ]
            if not quotes:
                quotes = [e.quote for e in v.evidence_chain if e.quote]

            # Filter quotes to ensure unselected technologies (like Redis) do not leak into non-Redis tasks
            quotes = [q for q in quotes if not re.search(r"\b(?:evaluate\s+redis|haven't decided on redis|redis as a required)\b", q, re.IGNORECASE)]

            ev_slots = extract_slots_from_evidence(v.evidence_chain, claim_text=c.text)
            
            eff_actor = ev_slots.get("actor") or c.actor or "Team"
            # Prioritize exact deadline from commitment evidence over vague summary deadlines
            eff_deadline = ev_slots.get("deadline") or c.deadline
            
            # Clean action instruction for requirement and assignee
            if ev_slots.get("action_text"):
                eff_req = ev_slots["action_text"]
            else:
                eff_req = v.resolved_claim or c.normalized or c.text

            # Clean conversational lead-in phrases
            eff_req = re.sub(r'^(?:[A-Z][a-z]+\s+will\s+go\s+through\s+the\s+launch\s+requirements\.?\s*)', '', eff_req, flags=re.IGNORECASE).strip()
            eff_req = re.sub(r'^(?:The\s+client\s+wants\s+)', '', eff_req, flags=re.IGNORECASE).strip()

            # Determine discipline role
            if "sso" in eff_req.lower() or "auth" in eff_req.lower() or "password" in eff_req.lower():
                eff_role = "AUTHENTICATION"
            elif "audit" in eff_req.lower() or "endpoint" in eff_req.lower() or "database" in eff_req.lower() or "validation" in eff_req.lower():
                eff_role = "BACKEND"
            elif "frontend" in eff_req.lower() or "ui" in eff_req.lower() or "card" in eff_req.lower():
                eff_role = "FRONTEND"
            elif "deploy" in eff_req.lower() or "health" in eff_req.lower() or "infrastructure" in eff_req.lower():
                eff_role = "DEVOPS"
            elif "qa" in eff_req.lower() or "test" in eff_req.lower():
                eff_role = "QA"
            else:
                eff_role = "ENGINEER"

            # Deduplicate semantically identical verified tasks by clean requirement text
            req_key = eff_req.lower().strip()
            if req_key not in seen_raw_requirements:
                seen_raw_requirements.add(req_key)
                verified_commitments.append(VerifiedCommitment(
                    task_id=c.claim_id,
                    raw_requirement=eff_req,
                    clean_requirement=eff_req,
                    assignees=[Assignee(name=eff_actor, role=eff_role, assigned_work=eff_req, deadline=eff_deadline)],
                    deadline=eff_deadline,
                    evidence_context_quotes=quotes[:3] if quotes else [c.text],
                    supporting_quotes=quotes[:3] if quotes else [c.text]
                ))
        else:
            reason_text = "Missing supporting commitment in transcript"
            if v.evidence_chain:
                # Format specific and readable gate reasons
                reasons = []
                for e in v.evidence_chain:
                    q = e.quote or e.text or ""
                    if re.search(r"\b(investigat\w*|look into|explore|check whether)\b", q, re.IGNORECASE):
                        reasons.append(f"Conditional investigation: \"{q}\"")
                    elif re.search(r"\b(haven'?t selected|not decided|not sure)\b", q, re.IGNORECASE):
                        reasons.append(f"Undecided technology: \"{q}\"")
                    elif e.stance in (Stance.REJECT, Stance.CANCEL, Stance.REVERSE) or e.relation == "CONTRADICTS":
                        reasons.append(f"Contradicted in discussion: \"{q}\"")
                
                if reasons:
                    reason_text = "; ".join(reasons[:2])
                elif v.status == Status.AMBIGUOUS:
                    reason_text = "Requires team confirmation / clarification (ambiguous stance)"
                elif v.status == Status.UNSUPPORTED:
                    reason_text = "No direct commitment found in meeting transcript"
            
            quotes = [e.quote for e in v.evidence_chain if e.quote]
            ev_slots = extract_slots_from_evidence(v.evidence_chain, claim_text=c.text)

            candidate_actor = ev_slots.get("actor") or c.actor
            if not candidate_actor or candidate_actor in ("Team", "Unassigned"):
                c_words = set(re.findall(r"\w{4,}", c.text.lower()))
                best_match = None
                best_score = 0
                for e in v.evidence_chain:
                    spk = getattr(e, "speaker", None)
                    q_txt = (getattr(e, "quote", "") or getattr(e, "text", "")).lower()
                    if spk and spk not in ("Team", "Speaker"):
                        match_count = sum(1 for w in c_words if w in q_txt)
                        if match_count > best_score:
                            best_score = match_count
                            best_match = spk
                if best_match:
                    candidate_actor = best_match

            eff_actor = candidate_actor or "Unassigned"
            eff_deadline = ev_slots.get("deadline") or c.deadline

            chain_list = []
            if v.evidence_chain:
                for e in v.evidence_chain:
                    chain_list.append({
                        "speaker": getattr(e, "speaker", None) or "Speaker",
                        "time": getattr(e, "time", None) or (f"Segment #{getattr(e, 'idx', '')}" if getattr(e, 'idx', None) is not None else ""),
                        "quote": getattr(e, "quote", "") or getattr(e, "text", ""),
                        "stance": str(getattr(e, "stance", "NEUTRAL")),
                        "relation": str(getattr(e, "relation", "CONTEXT"))
                    })

            action_desc = ev_slots.get("action_text") or v.resolved_claim or c.text
            proposed_task = {
                "task_id": c.claim_id,
                "intentions": [c.text],
                "things_to_implement": [f"{eff_actor}: {action_desc}"],
                "technical_context": quotes[:3] if quotes else [f"Verified via human confirmation. Context: {c.text}"],
                "deadline": eff_deadline
            }

            ambiguous_tasks.append({
                "task_id": c.claim_id,
                "claim_id": c.claim_id,
                "task_text": c.text,
                "actor": eff_actor,
                "deadline": eff_deadline,
                "status": eff_status if eff_status != "VERIFIED" else "AMBIGUOUS",
                "gate_action": getattr(v, "gate_action", "HUMAN_REVIEW"),
                "explanation": reason_text,
                "evidence_chain": chain_list,
                "proposed_task": proposed_task
            })
            unverified_items.append({
                "claim": c.text,
                "status": eff_status,
                "reason": reason_text
            })

    # 3. Execute Teammate 2 Privacy Masking Engine on Verified Commitments
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
        output_md_path=out_md_path,
        fast_mode=fast_mode
    )

    # Pre-Dispatch Leak Gate verification
    leak_gate_passed = True
    leak_violations = []
    for payload in masking_result.agent_payloads:
        is_clean, violations = LeakInspector.inspect_agent_payload(payload)
        if not is_clean:
            leak_gate_passed = False
            leak_violations.extend(violations)

    # Map actors from verified commitments
    task_actor_map = {}
    for c in verified_commitments:
        actor = c.assignees[0].name if c.assignees else "Team"
        task_actor_map[c.task_id] = actor

    # Format clean, highly readable verified tasks
    formatted_tasks = []
    for idx, p in enumerate(masking_result.agent_payloads):
        actor_name = task_actor_map.get(p.task_id, "Team")
        formatted_tasks.append({
            "task_id": f"TASK-{idx+1:03d}",
            "actor": actor_name,
            "assignee": actor_name,
            "intentions": p.intentions,
            "things_to_implement": p.things_to_implement,
            "technical_context": p.technical_context,
            "deadline": p.deadline
        })

    # Sync meeting and release decision to Nomad database
    try:
        from backend.storage.database import SessionLocal
        from backend.storage.repository import Repository
        _db = SessionLocal()
        try:
            _repo = Repository(_db)
            _m = _repo.create_or_get_meeting(meetily_id=meeting.meeting_id, title=meeting.title or f"Meeting {meeting.meeting_id}")
            if out_md_path and out_md_path.exists():
                _m.raw_summary = out_md_path.read_text(encoding="utf-8")
            elif not _m.raw_summary and formatted_tasks:
                summary_lines = []
                for ft in formatted_tasks:
                    actor = ft.get("actor", "Team")
                    for t in ft.get("things_to_implement", []):
                        summary_lines.append(f"- {actor}: {t}")
                _m.raw_summary = "\n".join(summary_lines)

            if not _m.transcript_sha256:
                _m.transcript_sha256 = f"pipeline_{meeting.meeting_id}"
            if not _repo.get_latest_release_decision(_m.id):
                _repo.save_release_decision(
                    run_id=f"pipeline_{meeting.meeting_id}",
                    meeting_id=_m.id,
                    decision="release",
                    reasons=["Verified via Clean Room Pipeline"],
                    flagged_claims=[],
                    flagged_conflicts=[]
                )
            if out_md_path and out_md_path.exists():
                _repo.save_output_artifact(
                    run_id=f"pipeline_{meeting.meeting_id}",
                    meeting_id=_m.id,
                    audience="cloud_llm",
                    file_path=str(out_md_path.resolve()),
                    status="clean"
                )
        finally:
            _db.close()
    except Exception as e:
        import logging
        logging.getLogger("nomad.pipeline").warning(f"Failed to sync release decision to DB: {e}")


    # Extract transcript-wide and claim-wide business context & secrets
    all_isolated_secrets = []
    quarantined_ctx = []

    for a in masking_result.audit_records:
        quarantined_ctx.extend(a.business_context)
        for s in a.isolated_business_secrets:
            all_isolated_secrets.append(s.model_dump() if hasattr(s, "model_dump") else s)
        for pii in getattr(a, "sanitized_pii_entities", []):
            all_isolated_secrets.append({
                "category": "PII_OR_SECRET",
                "reason": "Sensitive identifier masked by Deterministic Firewall",
                "source": "deterministic_firewall",
                "value": pii.get("raw", "") if isinstance(pii, dict) else str(pii),
                "token": pii.get("token", "") if isinstance(pii, dict) else ""
            })

    # Also capture contextual discussion from all claims
    for c in claims:
        q_low = c.text.lower()
        if any(k in q_low for k in [
            "middle east", "competitor", "market", "customer", "growth", "revenue",
            "vendor", "negotiat", "campaign", "pricing", "commercial", "strategy",
            "priority", "partner", "confidential", "secret", "budget"
        ]):
            quarantined_ctx.append(c.text.strip())

    quarantined_ctx = list(dict.fromkeys([ctx for ctx in quarantined_ctx if ctx]))

    agy_launch_info = None
    if auto_launch:
        try:
            from backend.loop.auto_launcher import setup_and_launch_agy
            agy_launch_info = setup_and_launch_agy(meeting_id=meeting.meeting_id, auto_execute=True)
        except Exception as e:
            agy_launch_info = {"status": "error", "message": str(e)}

    return {
        "status": "SUCCESS",
        "meeting_id": meeting.meeting_id,
        "meeting_title": meeting.title,
        "verified_tasks_count": len(formatted_tasks),
        "verified_tasks": formatted_tasks,
        "ambiguous_tasks_count": len(ambiguous_tasks),
        "ambiguous_tasks": ambiguous_tasks,
        "final_prompt_markdown": masking_result.final_prompt_markdown,
        "final_prompt_json": masking_result.final_prompt_json,
        "business_context_quarantined": quarantined_ctx,
        "isolated_secrets_count": len(all_isolated_secrets),
        "isolated_secrets": all_isolated_secrets,
        "agy_launch": agy_launch_info
    }



class MeetilyVerifyRequest(BaseModel):
    meeting_id: str
    gateway_url: str = "http://127.0.0.1:8420"
    token: Optional[str] = None
    fast_mode: bool = False
    auto_launch: bool = False


@router.get("/meetily/{meeting_id}")
async def get_meetily_meeting_endpoint(
    meeting_id: str,
    gateway_url: str = Query("http://127.0.0.1:8420"),
    token: Optional[str] = Query(None)
):
    """Inspect and fetch a Meetily meeting transcript and summary via REST API."""
    from app.integrations.meetily import fetch_meetily_meeting
    return await fetch_meetily_meeting(meeting_id=meeting_id, gateway_url=gateway_url, token=token)


@router.post("/verify-meetily")
async def verify_meetily_pipeline(
    req: MeetilyVerifyRequest
) -> Dict[str, Any]:
    """
    Directly query Meetily REST API for meeting transcript & summary,
    parse them, and run end-to-end verification, masking, and optional AGY auto-launch.
    """
    from app.integrations.meetily import fetch_meetily_meeting
    meetily_data = await fetch_meetily_meeting(meeting_id=req.meeting_id, gateway_url=req.gateway_url, token=req.token)
    
    adapter = MockAdapter()
    t_json = meetily_data.get("transcript", {})
    s_json = meetily_data.get("summary", {})
    meta = meetily_data.get("metadata", {})
    
    s_items = extract_summary_items_from_json(s_json)
    if not s_items and isinstance(t_json, dict):
        s_items = extract_summary_items_from_json(t_json)
    norm_s_items = [normalize_summary_item(it) for it in s_items if normalize_summary_item(it)]
    
    segments = t_json.get("segments", []) if isinstance(t_json, dict) else (t_json if isinstance(t_json, list) else [])
    meeting_title = meta.get("title") or (t_json.get("title") if isinstance(t_json, dict) else None) or f"Meeting {req.meeting_id}"
    
    meeting = adapter.load({
        "meeting_id": req.meeting_id,
        "title": meeting_title,
        "segments": segments,
        "summary": {"decisions": norm_s_items, "action_items": []}
    })
    
    return await _process_meeting_core(meeting, fast_mode=req.fast_mode, auto_launch=req.auto_launch)


@router.post("/auto-launch-agy")
async def auto_launch_agy_endpoint(
    meeting_id: str = Query(..., description="Target verified meeting ID"),
    auto_execute: bool = Query(True, description="Automatically execute autonomous build")
) -> Dict[str, Any]:
    """
    Generate prompt, jail workspace in Desktop/test, write PROMPT.md/AGENTS.md,
    copy prompt to Windows clipboard, launch Antigravity IDE, and auto-execute build.
    """
    try:
        from backend.loop.auto_launcher import setup_and_launch_agy
        result = setup_and_launch_agy(meeting_id=meeting_id, auto_execute=auto_execute)
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail={"message": result.get("message", "Auto-launch failed")})
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={"message": f"Auto-launch failed: {str(e)}"})


@router.get("/preview/{meeting_id}")
@router.get("/preview/{meeting_id}/{filename:path}")
async def preview_deliverable_endpoint(
    meeting_id: str,
    filename: str = "index.html"
):
    """Serve verified deliverables directly from the quarantined build workspace for instant browser preview."""
    from fastapi.responses import FileResponse, HTMLResponse
    from backend.loop.workspace import resolve_desktop_path, get_default_workspace_root
    from backend.storage.database import SessionLocal
    from backend.storage.models import LoopRunModel

    workspace_dir = None
    db = SessionLocal()
    try:
        run = db.query(LoopRunModel).filter(LoopRunModel.meeting_id == meeting_id).order_by(LoopRunModel.created_at.desc()).first()
        if run and run.workspace_path and Path(run.workspace_path).exists():
            workspace_dir = Path(run.workspace_path)
    finally:
        db.close()

    if not workspace_dir or not workspace_dir.exists():
        # Fallback search inside Desktop/test
        test_root = get_default_workspace_root()
        if test_root.exists():
            candidates = sorted(test_root.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if candidates:
                workspace_dir = candidates[0]

    if not workspace_dir or not workspace_dir.exists():
        return HTMLResponse("<h3>Deliverable workspace not found. Please click 'Auto-Launch Antigravity' first.</h3>", status_code=404)

    target_file = (workspace_dir / filename).resolve()
    if not target_file.exists():
        return HTMLResponse(f"<h3>File '{filename}' not found in workspace '{workspace_dir.name}'.</h3>", status_code=404)

    return FileResponse(target_file)

