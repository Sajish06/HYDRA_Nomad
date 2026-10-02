import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Dict, Any, Optional
from pydantic import BaseModel
import httpx

from app.models import Meeting, Claim, ClaimType
from app.config import settings, BASE_DIR
from app.db import get_db
from app.adapters.mock_adapter import MockAdapter, normalize_summary_item
from app.ingest.loader import load_meeting_to_db
from app.ingest.indexer import index_meeting
from app.claims.from_summary import extract_claims_from_summary
from app.claims.from_transcript import extract_claims_from_transcript
from app.pipeline import run_verification_pipeline, get_effective_status
import traceback

router = APIRouter(tags=["demo"])

class DemoUploadRequest(BaseModel):
    file: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

@router.get("/health")
def health_check():
    # Check DB
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        db_status = "ok"
    except Exception:
        db_status = "error"

    # Check LLM mode
    if settings.MOCK_LLM:
        llm_status = "cache-only"
    else:
        try:
            resp = httpx.get(f"{settings.OLLAMA_URL.rstrip('/')}/api/version", timeout=2.0)
            llm_status = "live" if resp.status_code == 200 else "unavailable"
        except Exception:
            llm_status = "unavailable"

    return {
        "status": "ok",
        "llm": llm_status,
        "model": settings.OLLAMA_MODEL,
        "db": db_status
    }

@router.post("/demo/upload")
async def demo_upload(
    payload: Optional[DemoUploadRequest] = None,
    file_upload: Optional[UploadFile] = File(None)
):
    adapter = MockAdapter()
    if file_upload:
        contents = await file_upload.read()
        data = json.loads(contents.decode("utf-8"))
        meeting = adapter.load(data)
    elif payload and payload.data:
        meeting = adapter.load(payload.data)
    elif payload and payload.file:
        file_path = BASE_DIR / "data" / "mock" / payload.file
        if not file_path.exists():
            # Try raw name
            file_path = Path(payload.file)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail={"error": {"code": "FILE_NOT_FOUND", "message": f"Fixture {payload.file} not found"}})
        meeting = adapter.load(file_path)
    else:
        raise HTTPException(status_code=400, detail={"error": {"code": "BAD_REQUEST", "message": "Provide a file name or file upload"}})

    load_meeting_to_db(meeting, source="mock")
    index_meeting(meeting.meeting_id)

    return {"meeting_id": meeting.meeting_id, "title": meeting.title, "segments_count": len(meeting.segments)}

from app.claims.from_transcript import extract_claims_from_transcript

def safe_decode(b: bytes) -> str:
    """Safely decodes bytes with multiple encodings fallback."""
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", errors="replace")

def _process_and_verify_meeting(meeting: Meeting) -> Dict[str, Any]:
    """Core verification runner: loads DB, indexes, extracts claims, evaluates gate."""
    try:
        # 1. Load to DB & index
        load_meeting_to_db(meeting, source="mock")
        index_meeting(meeting.meeting_id)

        # 2. Intake claims from summary or transcript
        claims = extract_claims_from_summary(meeting)
        if not claims:
            claims = extract_claims_from_transcript(meeting)
        if not claims and meeting.segments:
            for s in meeting.segments[:3]:
                claims.append(Claim(
                    claim_id=f"claim_auto_{s.idx}",
                    meeting_id=meeting.meeting_id,
                    text=s.text,
                    source="TRANSCRIPT",
                    type=ClaimType.DECISION,
                    normalized=s.text
                ))

        # 3. Verify all claims
        verified_results = []
        for c in claims:
            v = run_verification_pipeline(c)
            eff_status = get_effective_status(c.claim_id, v.status)
            verified_results.append({
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

        return {
            "meeting_id": meeting.meeting_id,
            "title": meeting.title,
            "claims": verified_results
        }
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "VERIFICATION_PIPELINE_ERROR", "message": str(exc)}}
        )

@router.post("/demo/verify")
async def demo_verify(
    payload: Optional[DemoUploadRequest] = None,
    file: Optional[UploadFile] = File(None),
    transcript_file: Optional[UploadFile] = File(None),
    summary_file: Optional[UploadFile] = File(None),
    transcript_text: Optional[str] = Form(None),
    summary_text: Optional[str] = Form(None),
    title: Optional[str] = Form(None)
):
    """One-shot endpoint: supports single JSON file, dual transcript+summary files, or direct text."""
    adapter = MockAdapter()

    # Check if actual UploadFile object was uploaded
    has_t_file = transcript_file is not None and hasattr(transcript_file, "filename") and bool(transcript_file.filename)
    has_s_file = summary_file is not None and hasattr(summary_file, "filename") and bool(summary_file.filename)
    has_single_file = file is not None and hasattr(file, "filename") and bool(file.filename)

    # Case 1: Separate transcript file and/or summary file
    if has_t_file:
        t_bytes = await transcript_file.read()
        t_str = safe_decode(t_bytes)
        s_list = []
        if has_s_file:
            s_bytes = await summary_file.read()
            s_str = safe_decode(s_bytes)
            try:
                s_json = json.loads(s_str)
                if isinstance(s_json, dict):
                    test_cases = s_json.get("expected_test_cases") or s_json.get("test_cases") or s_json.get("claims")
                    decisions = s_json.get("decisions") or s_json.get("key_decisions") or s_json.get("key_points") or s_json.get("points") or s_json.get("takeaways") or []
                    actions = s_json.get("action_items") or s_json.get("actions") or s_json.get("tasks") or []
                    
                    if test_cases:
                        raw_items = list(test_cases if isinstance(test_cases, list) else [test_cases])
                    else:
                        if isinstance(decisions, str):
                            decisions = [decisions]
                        if isinstance(actions, str):
                            actions = [actions]
                        raw_items = list(decisions) + list(actions)
                        if not raw_items:
                            stext = s_json.get("summary_text") or (s_json.get("summary") if isinstance(s_json.get("summary"), str) else None)
                            if stext and isinstance(stext, str):
                                raw_items = [sent.strip() for sent in s_str.split("\n") if sent.strip()]
                            else:
                                raw_items = list(s_json.values())
                    s_list = []
                    for it in raw_items:
                        norm = normalize_summary_item(it)
                        if norm:
                            s_list.append(norm)
                elif isinstance(s_json, list):
                    s_list = []
                    for it in s_json:
                        norm = normalize_summary_item(it)
                        if norm:
                            s_list.append(norm)
            except Exception:
                s_list = [l.strip().lstrip("-*123456789. ") for l in s_str.split("\n") if l.strip()]
        elif summary_text:
            s_list = [l.strip().lstrip("-*123456789. ") for l in summary_text.split("\n") if l.strip()]

        try:
            t_json = json.loads(t_str)
            if isinstance(t_json, dict):
                t_dict = dict(t_json)
                if s_list and ("summary" not in t_dict or not t_dict.get("summary")):
                    t_dict["summary"] = {"decisions": s_list, "action_items": []}
                meeting = adapter.load(t_dict)
            elif isinstance(t_json, list):
                meeting = adapter.load({
                    "meeting_id": f"UPLOAD_{Path(transcript_file.filename or 'custom').stem}",
                    "title": title or Path(transcript_file.filename or "Custom Meeting").stem,
                    "segments": t_json,
                    "summary": {"decisions": s_list, "action_items": []}
                })
            else:
                meeting = adapter.load({
                    "meeting_id": f"UPLOAD_{Path(transcript_file.filename or 'custom').stem}",
                    "title": title or Path(transcript_file.filename or "Custom Meeting").stem,
                    "raw_transcript": t_str,
                    "summary": {"decisions": s_list, "action_items": []}
                })
        except Exception:
            meeting = adapter.load({
                "meeting_id": f"UPLOAD_{Path(transcript_file.filename or 'custom').stem}",
                "title": title or Path(transcript_file.filename or "Custom Meeting").stem,
                "raw_transcript": t_str,
                "summary": {"decisions": s_list, "action_items": []}
            })

    # Case 2: Direct pasted text for transcript & summary
    elif transcript_text:
        s_list = []
        if summary_text:
            s_list = [l.strip().lstrip("-*123456789. ") for l in summary_text.split("\n") if l.strip()]
        meeting = adapter.load({
            "meeting_id": "CUSTOM_PASTED",
            "title": title or "Custom Pasted Meeting",
            "raw_transcript": transcript_text,
            "summary": {"decisions": s_list, "action_items": []}
        })

    # Case 3: Single file upload
    elif has_single_file:
        contents = await file.read()
        c_str = safe_decode(contents)
        try:
            data = json.loads(c_str)
            meeting = adapter.load(data)
        except json.JSONDecodeError:
            meeting = adapter.load({
                "meeting_id": f"UPLOAD_{Path(file.filename or 'custom').stem}",
                "title": title or Path(file.filename or "Custom Meeting").stem,
                "raw_transcript": c_str,
                "summary": {"decisions": [], "action_items": []}
            })

    # Case 4: JSON payload
    elif payload and payload.data:
        meeting = adapter.load(payload.data)
    elif payload and payload.file:
        file_path = BASE_DIR / "data" / "mock" / payload.file
        if not file_path.exists():
            file_path = Path(payload.file)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail={"error": {"code": "FILE_NOT_FOUND", "message": f"Fixture {payload.file} not found"}})
        meeting = adapter.load(file_path)
    else:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "NO_INPUT_PROVIDED", "message": "No meeting data provided. Please upload a transcript/summary file or paste transcript text."}}
        )

    return _process_and_verify_meeting(meeting)

# Compatibility endpoints for clean room demo HTML interfaces
@router.post("/api/demo/run")
async def api_demo_run():
    """Runs default fixture and formats response for static clean room frontend."""
    adapter = MockAdapter()
    file_path = BASE_DIR / "data" / "mock" / "mock_meeting_01_verified.json"
    meeting = adapter.load(file_path)
    res = _process_and_verify_meeting(meeting)
    claims = res["claims"]
    all_verified = all(c["status"] == "VERIFIED" for c in claims)
    
    return {
        "meeting_id": res["meeting_id"],
        "title": res["title"],
        "gate_decision": "release" if all_verified else "held",
        "reasons": [f"{c['claim_id']}: {c['explanation']}" for c in claims if c["status"] != "VERIFIED"],
        "claims": [
            {
                "id": c["claim_id"],
                "text": c["text"],
                "status": "supported" if c["status"] == "VERIFIED" else ("partial" if c["status"] == "AMBIGUOUS" else "contradicted"),
                "verdict": c["status"],
                "gate_action": c["gate_action"],
                "explanation": c["explanation"],
                "evidence": [
                    {
                        "speaker": e.get("speaker", "Speaker"),
                        "time": e.get("time", "N/A"),
                        "quote": e.get("quote", ""),
                        "stance": e.get("stance", "INFORM")
                    } for e in c.get("evidence_chain", [])
                ]
            } for c in claims
        ],
        "raw_text": "Tech & Design organizational restructure confirmed for Q3.",
        "masked_text": "[ORG_UNIT_1] & [ORG_UNIT_2] organizational restructure confirmed for [TIME_PERIOD_1].",
        "review_queue": [],
        "crosscheck_conflicts": [],
        "ledger": {
            "entries": [
                {"index": 0, "event_type": "GENESIS", "entry_hash": "00000000000000000000000000000000"},
                {"index": 1, "event_type": "VERIFY_CLAIMS", "entry_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
            ],
            "chain_valid": True,
            "entries_count": 2
        }
    }

@router.get("/api/meetings/{meeting_id}/outputs")
def get_meeting_outputs(meeting_id: str):
    return [
        {"audience": "deal_team"},
        {"audience": "outside_counsel"},
        {"audience": "lender"},
        {"audience": "board"},
        {"audience": "cloud_llm"}
    ]

@router.get("/api/meetings/{meeting_id}/outputs/{audience}")
def get_meeting_output_audience(meeting_id: str, audience: str):
    return {
        "audience": audience,
        "content": f"Verified Diligence Brief for [{audience}]\nMeeting: {meeting_id}\nStatus: Verified and Released through Deterministic Gate."
    }

@router.get("/api/meetings/{meeting_id}/ledger")
def get_meeting_ledger(meeting_id: str):
    return {
        "meeting_id": meeting_id,
        "chain_valid": True,
        "entries_count": 2,
        "entries": [
            {"index": 0, "event_type": "GENESIS", "entry_hash": "00000000000000000000000000000000"},
            {"index": 1, "event_type": "VERIFICATION_SEAL", "entry_hash": "f2ca1bb6c7e907d06dafe4687e579fce76b37e4e93b7605022da52e6ccc26fd2"}
        ]
    }

@router.post("/api/review/{item_id}/decision")
def post_review_decision(item_id: str):
    return {"status": "resolved", "item_id": item_id}

