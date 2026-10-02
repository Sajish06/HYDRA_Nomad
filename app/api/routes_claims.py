import json
import hashlib
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.models import (
    Claim, Verification, ConfirmationRequest, VerifiedTask,
    HandoffSegment, ClaimType, Status, MaskedBrief
)
from app.db import get_db
from app.pipeline import run_verification_pipeline, get_effective_status, compute_verification_hash
from app.masking.stub import get_masker

router = APIRouter(prefix="/claims", tags=["claims"])

class HandoffAckRequest(BaseModel):
    recipient: str
    masked_brief_id: str

@router.post("/{claim_id}/verify", response_model=Verification)
def verify_claim(claim_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found"}})
        
        claim = Claim(
            claim_id=row["id"],
            meeting_id=row["meeting_id"],
            text=row["text"],
            source=row["source"],
            type=ClaimType(row["type"]),
            actor=row["actor"],
            action=row["action"],
            object=row["object"],
            deadline=row["deadline"],
            normalized=row["normalized"]
        )

    verification = run_verification_pipeline(claim)
    return verification

@router.get("/{claim_id}")
def get_claim_details(claim_id: str):
    with get_db() as conn:
        c_row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found"}})
        
        v_row = conn.execute("SELECT * FROM verification WHERE claim_id = ?", (claim_id,)).fetchone()
        
        status = None
        eff_status = None
        gate_action = None
        reasons = []
        explanation = None
        final_state = None
        resolved_claim = None
        slots = []

        if v_row:
            status = v_row["status"]
            eff_status = get_effective_status(claim_id, Status(status))
            gate_action = v_row["gate_action"]
            reasons = json.loads(v_row["reasons"]) if v_row["reasons"] else []
            explanation = v_row["explanation"]
            final_state = v_row["final_state"]
            resolved_claim = v_row["resolved_claim"]
            slots = json.loads(v_row["slots"]) if v_row["slots"] else []

        return {
            "claim": dict(c_row),
            "status": status,
            "effective_status": eff_status or status,
            "gate_action": gate_action,
            "reasons": reasons,
            "explanation": explanation,
            "final_state": final_state,
            "resolved_claim": resolved_claim,
            "slots": slots
        }

@router.get("/{claim_id}/evidence")
def get_claim_evidence(claim_id: str):
    with get_db() as conn:
        c_row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found"}})
        
        e_rows = conn.execute("SELECT * FROM evidence WHERE claim_id = ? ORDER BY segment_idx ASC", (claim_id,)).fetchall()
        v_row = conn.execute("SELECT slots, resolved_claim FROM verification WHERE claim_id = ?", (claim_id,)).fetchone()
        
        slots = json.loads(v_row["slots"]) if (v_row and v_row["slots"]) else []
        resolved_claim = v_row["resolved_claim"] if v_row else None

        evidence_items = []
        for e in e_rows:
            seg = conn.execute("SELECT speaker, time, text FROM segments WHERE meeting_id = ? AND idx = ?", (e["meeting_id"], e["segment_idx"])).fetchone()
            evidence_items.append({
                "idx": e["segment_idx"],
                "speaker": seg["speaker"] if seg else None,
                "time": seg["time"] if seg else None,
                "text": seg["text"] if seg else "",
                "quote": e["quote"],
                "stance": e["stance"],
                "relation": e["relation"],
                "resolved_text": e["resolved_text"],
                "source": e["source"]
            })

        return {
            "claim_id": claim_id,
            "resolved_claim": resolved_claim,
            "evidence_chain": evidence_items,
            "slots": slots
        }

@router.get("/{claim_id}/trace")
def get_claim_trace(claim_id: str):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT stage, payload, created_at FROM pipeline_trace WHERE claim_id = ? ORDER BY id ASC",
            (claim_id,)
        ).fetchall()
        return [
            {
                "stage": r["stage"],
                "payload": json.loads(r["payload"]) if r["payload"] else {},
                "created_at": r["created_at"]
            }
            for r in rows
        ]

@router.post("/{claim_id}/confirm")
def confirm_claim(claim_id: str, req: ConfirmationRequest):
    with get_db() as conn:
        v_row = conn.execute("SELECT * FROM verification WHERE claim_id = ?", (claim_id,)).fetchone()
        if not v_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Verification record not found"}})
        
        status = v_row["status"]
        if status == "VERIFIED":
            raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_ACTION", "message": "VERIFIED claims do not require manual confirmation"}})
        
        # Non-empty note required for UNSUPPORTED
        if status == "UNSUPPORTED" and req.decision == "CONFIRMED" and not (req.note and req.note.strip()):
            raise HTTPException(status_code=400, detail={"error": {"code": "NOTE_REQUIRED", "message": "Confirmation of an UNSUPPORTED claim requires a justification note"}})

        conn.execute(
            "INSERT INTO confirmations (claim_id, decision, note) VALUES (?, ?, ?)",
            (claim_id, req.decision, req.note)
        )

        eff_status = "USER_CONFIRMED" if req.decision == "CONFIRMED" else "USER_REJECTED"
        return {"claim_id": claim_id, "decision": req.decision, "effective_status": eff_status, "note": req.note}

@router.get("/{claim_id}/handoff", response_model=VerifiedTask)
def get_task_handoff(claim_id: str):
    """Fails closed: returns 409 if claim is not VERIFIED or USER_CONFIRMED."""
    with get_db() as conn:
        c_row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not c_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Claim {claim_id} not found"}})
        
        v_row = conn.execute("SELECT * FROM verification WHERE claim_id = ?", (claim_id,)).fetchone()
        if not v_row:
            raise HTTPException(status_code=409, detail={"error": {"code": "NOT_RELEASED", "message": "Claim has not been verified"}})

        eff_status = get_effective_status(claim_id, Status(v_row["status"]))
        if eff_status not in ("VERIFIED", "USER_CONFIRMED"):
            raise HTTPException(status_code=409, detail={"error": {"code": "NOT_RELEASED", "message": f"Claim status is {eff_status}; only VERIFIED or USER_CONFIRMED claims may proceed"}})

        meeting_id = c_row["meeting_id"]
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
            claim_type=ClaimType(c_row["type"]),
            task_text=v_row["resolved_claim"] or c_row["normalized"],
            actor=c_row["actor"],
            action=c_row["action"],
            object=c_row["object"],
            deadline=c_row["deadline"],
            effective_status=eff_status,
            verified_at=v_row["created_at"],
            verification_hash=v_hash,
            grounding_segments=grounding_segs
        )
        return task

@router.post("/{claim_id}/handoff/ack")
def ack_task_handoff(claim_id: str, req: HandoffAckRequest):
    with get_db() as conn:
        v_row = conn.execute("SELECT * FROM verification WHERE claim_id = ?", (claim_id,)).fetchone()
        if not v_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Verification record not found"}})
        
        eff_status = get_effective_status(claim_id, Status(v_row["status"]))
        v_hash = compute_verification_hash(type("Obj", (), dict(v_row))())

        conn.execute(
            "INSERT INTO handoff_log (claim_id, status_at_handoff, verification_hash, recipient, masked_brief_id) VALUES (?, ?, ?, ?, ?)",
            (claim_id, eff_status, v_hash, req.recipient, req.masked_brief_id)
        )
        return {"status": "ok", "claim_id": claim_id, "masked_brief_id": req.masked_brief_id}

@router.post("/{claim_id}/mask", response_model=MaskedBrief)
def mask_task_endpoint(claim_id: str):
    task = get_task_handoff(claim_id)
    masker = get_masker()
    brief = masker.mask(task)
    
    # Auto-log handoff
    ack_task_handoff(claim_id, HandoffAckRequest(recipient="local_masker", masked_brief_id=brief.brief_id))
    return brief
