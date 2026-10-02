import json
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional

from app.models import Meeting, Segment, Participant, Claim, VerifiedTask, HandoffSegment, ClaimType
from app.db import get_db
from app.ingest.indexer import index_meeting
from app.claims.from_summary import extract_claims_from_summary
from app.claims.from_transcript import extract_claims_from_transcript
from app.adapters.mock_adapter import MockAdapter
from app.pipeline import get_effective_status, compute_verification_hash, save_verification_to_db

router = APIRouter(prefix="/meetings", tags=["meetings"])

@router.get("", response_model=List[Dict[str, Any]])
def list_meetings():
    with get_db() as conn:
        rows = conn.execute("SELECT id, title, created_at, source FROM meetings ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

@router.get("/{meeting_id}")
def get_meeting(meeting_id: str):
    with get_db() as conn:
        m_row = conn.execute("SELECT id, title, created_at, source FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not m_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Meeting {meeting_id} not found"}})
        
        p_rows = conn.execute("SELECT name, role, has_authority FROM participants WHERE meeting_id = ?", (meeting_id,)).fetchall()
        s_rows = conn.execute("SELECT idx, speaker, time, t_seconds, text FROM segments WHERE meeting_id = ? ORDER BY idx ASC", (meeting_id,)).fetchall()

    return {
        "meeting_id": m_row["id"],
        "title": m_row["title"],
        "source": m_row["source"],
        "participants": [dict(p) for p in p_rows],
        "segments": [dict(s) for s in s_rows]
    }

@router.post("/{meeting_id}/index")
def index_meeting_endpoint(meeting_id: str):
    count = index_meeting(meeting_id)
    return {"meeting_id": meeting_id, "indexed_segments": count}

@router.post("/{meeting_id}/claims/intake")
def intake_claims_from_summary(meeting_id: str):
    with get_db() as conn:
        m_row = conn.execute("SELECT id, title FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not m_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Meeting not found"}})
        
        # Load mock meeting object if available or reconstruct from DB
        from app.config import BASE_DIR
        for p in (BASE_DIR / "data" / "mock").glob("*.json"):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("meeting_id") == meeting_id:
                    mock_adapter = MockAdapter()
                    meeting = mock_adapter.load(data)
                    claims = extract_claims_from_summary(meeting)
                    return {"meeting_id": meeting_id, "claims": [c.model_dump() for c in claims]}

        # If not found in mock folder, fetch segments from DB
        s_rows = conn.execute("SELECT idx, speaker, time, t_seconds, text FROM segments WHERE meeting_id = ? ORDER BY idx ASC", (meeting_id,)).fetchall()
        p_rows = conn.execute("SELECT name, role, has_authority FROM participants WHERE meeting_id = ?", (meeting_id,)).fetchall()
        meeting = Meeting(
            meeting_id=meeting_id,
            title=m_row["title"],
            participants=[Participant(name=p["name"], role=p["role"], has_authority=bool(p["has_authority"])) for p in p_rows],
            segments=[Segment(idx=s["idx"], speaker=s["speaker"], time=s["time"], t_seconds=s["t_seconds"], text=s["text"]) for s in s_rows]
        )
        claims = extract_claims_from_summary(meeting)
        return {"meeting_id": meeting_id, "claims": [c.model_dump() for c in claims]}

@router.post("/{meeting_id}/claims/extract")
def extract_claims_endpoint(meeting_id: str):
    with get_db() as conn:
        m_row = conn.execute("SELECT id, title FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not m_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Meeting not found"}})
        
        s_rows = conn.execute("SELECT idx, speaker, time, t_seconds, text FROM segments WHERE meeting_id = ? ORDER BY idx ASC", (meeting_id,)).fetchall()
        p_rows = conn.execute("SELECT name, role, has_authority FROM participants WHERE meeting_id = ?", (meeting_id,)).fetchall()
        
        meeting = Meeting(
            meeting_id=meeting_id,
            title=m_row["title"],
            participants=[Participant(name=p["name"], role=p["role"], has_authority=bool(p["has_authority"])) for p in p_rows],
            segments=[Segment(idx=s["idx"], speaker=s["speaker"], time=s["time"], t_seconds=s["t_seconds"], text=s["text"]) for s in s_rows]
        )
        claims = extract_claims_from_transcript(meeting)
        return {"meeting_id": meeting_id, "claims": [c.model_dump() for c in claims]}

@router.get("/{meeting_id}/claims")
def get_meeting_claims(meeting_id: str):
    with get_db() as conn:
        c_rows = conn.execute("SELECT * FROM claims WHERE meeting_id = ? ORDER BY id ASC", (meeting_id,)).fetchall()
        results = []
        for r in c_rows:
            claim_id = r["id"]
            v_row = conn.execute("SELECT * FROM verification WHERE claim_id = ?", (claim_id,)).fetchone()
            eff_status = None
            reasons = []
            gate_action = None
            explanation = None
            status = None
            
            if v_row:
                status = v_row["status"]
                eff_status = get_effective_status(claim_id, status)
                reasons = json.loads(v_row["reasons"]) if v_row["reasons"] else []
                gate_action = v_row["gate_action"]
                explanation = v_row["explanation"]

            results.append({
                "claim": dict(r),
                "status": status,
                "effective_status": eff_status or status,
                "gate_action": gate_action,
                "reasons": reasons,
                "explanation": explanation
            })
        return results

@router.get("/{meeting_id}/verified-tasks")
def list_verified_tasks(meeting_id: str):
    with get_db() as conn:
        c_rows = conn.execute("SELECT * FROM claims WHERE meeting_id = ?", (meeting_id,)).fetchall()
        tasks = []
        for r in c_rows:
            claim_id = r["id"]
            v_row = conn.execute("SELECT * FROM verification WHERE claim_id = ?", (claim_id,)).fetchone()
            if not v_row:
                continue
            
            eff_status = get_effective_status(claim_id, v_row["status"])
            if eff_status in ("VERIFIED", "USER_CONFIRMED"):
                # Get grounding segments
                e_rows = conn.execute(
                    "SELECT segment_idx FROM evidence WHERE claim_id = ? AND relation = 'SUPPORTS'",
                    (claim_id,)
                ).fetchall()
                grounding_idx = [e["segment_idx"] for e in e_rows]
                
                grounding_segs = []
                for g_idx in grounding_idx:
                    s = conn.execute(
                        "SELECT idx, speaker, time, text FROM segments WHERE meeting_id = ? AND idx = ?",
                        (meeting_id, g_idx)
                    ).fetchone()
                    if s:
                        grounding_segs.append(HandoffSegment(idx=s["idx"], speaker=s["speaker"], time=s["time"], text=s["text"]))

                v_hash = compute_verification_hash(type("Obj", (), dict(v_row))())
                task = VerifiedTask(
                    task_id=claim_id,
                    meeting_id=meeting_id,
                    claim_type=ClaimType(r["type"]),
                    task_text=v_row["resolved_claim"] or r["normalized"],
                    actor=r["actor"],
                    action=r["action"],
                    object=r["object"],
                    deadline=r["deadline"],
                    effective_status=eff_status,
                    verified_at=v_row["created_at"],
                    verification_hash=v_hash,
                    grounding_segments=grounding_segs
                )
                tasks.append(task)
        return tasks
