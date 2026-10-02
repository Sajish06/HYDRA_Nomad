import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.models import (
    Claim, Meeting, Participant, Verification, Status, Reason,
    EvidenceItem, SlotCheck, VerifiedTask, HandoffSegment
)
from app.db import get_db, log_trace
from app.retrieval.hybrid import retrieve_candidates
from app.analysis.stance import analyze_stances
from app.analysis.context import validate_and_resolve_context
from app.analysis.chain import build_evidence_chain
from app.analysis.slots import check_slots
from app.gate.gate import evaluate_gate

def run_verification_pipeline(claim: Claim) -> Verification:
    """Executes the full ReqCopilot Proof verification pipeline on a claim."""
    meeting_id = claim.meeting_id

    # 1. Load meeting details and participants, and ensure claim exists in DB
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO claims (id, meeting_id, text, normalized, source, type, actor, action, object, deadline)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim.claim_id, claim.meeting_id, claim.text, claim.normalized, claim.source, claim.type.value, claim.actor, claim.action, claim.object, claim.deadline)
        )
        p_rows = conn.execute(
            "SELECT name, role, has_authority FROM participants WHERE meeting_id = ?",
            (meeting_id,)
        ).fetchall()
        participants = [
            Participant(name=r["name"], role=r["role"], has_authority=bool(r["has_authority"]))
            for r in p_rows
        ]
        
        all_seg_rows = conn.execute(
            "SELECT idx, speaker, time, t_seconds, text FROM segments WHERE meeting_id = ? ORDER BY idx ASC",
            (meeting_id,)
        ).fetchall()
        seg_dict = {r["idx"]: dict(r) for r in all_seg_rows}

    # 2. Retrieval
    candidates = retrieve_candidates(meeting_id, claim)
    log_trace(claim.claim_id, "retrieval", [{"idx": c["idx"], "relevance_hint": c["relevance_hint"], "via": c["via"]} for c in candidates])

    if not candidates:
        verification = evaluate_gate(
            claim=claim,
            evidence_chain=[],
            participants=participants,
            slot_checks=[],
            flags=[Reason.NO_RELEVANT_EVIDENCE],
            resolved_claim=None
        )
        save_verification_to_db(verification)
        return verification

    # 3. Stance Analysis & Rule Cue Merging
    merged_stances, disagreement_flags = analyze_stances(
        claim=claim,
        candidates=candidates,
        participants=[p.model_dump() for p in participants]
    )
    log_trace(claim.claim_id, "stance_analysis", merged_stances)

    # 4. Context Resolution
    resolved_claim, context_flags = validate_and_resolve_context(
        claim_text=claim.text,
        stances=merged_stances,
        segments_by_idx=seg_dict,
        participants=[p.model_dump() for p in participants]
    )
    log_trace(claim.claim_id, "context_resolution", {"resolved_claim": resolved_claim, "flags": context_flags})

    # 5. Evidence Chain Construction
    evidence_chain = build_evidence_chain(
        claim_id=claim.claim_id,
        meeting_id=meeting_id,
        merged_stances=merged_stances
    )
    log_trace(claim.claim_id, "evidence_chain", [e.model_dump() for e in evidence_chain])

    # 6. Slot Grounding
    slot_checks = check_slots(claim, evidence_chain)
    log_trace(claim.claim_id, "slot_grounding", [s.model_dump() for s in slot_checks])

    # 7. Deterministic Verification Gate
    all_flags = list(set(disagreement_flags + context_flags))
    verification = evaluate_gate(
        claim=claim,
        evidence_chain=evidence_chain,
        participants=participants,
        slot_checks=slot_checks,
        flags=all_flags,
        resolved_claim=resolved_claim
    )
    log_trace(claim.claim_id, "gate_verdict", verification.model_dump())

    # 8. Persist Verification
    save_verification_to_db(verification)

    return verification

def save_verification_to_db(v: Verification):
    with get_db() as conn:
        reasons_json = json.dumps([r.value for r in v.reasons])
        slots_json = json.dumps([s.model_dump() for s in v.slots])
        conn.execute(
            """INSERT OR REPLACE INTO verification 
               (claim_id, status, gate_action, reasons, explanation, final_state, resolved_claim, slots, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (v.claim_id, v.status.value, v.gate_action, reasons_json, v.explanation, v.final_state, v.resolved_claim, slots_json, v.created_at)
        )

def get_effective_status(claim_id: str, machine_status: Status) -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT decision FROM confirmations WHERE claim_id = ? ORDER BY id DESC LIMIT 1",
            (claim_id,)
        ).fetchone()
        if row:
            dec = row["decision"]
            if dec == "CONFIRMED":
                return Status.USER_CONFIRMED.value
            elif dec == "REJECTED":
                return Status.USER_REJECTED.value
    return machine_status.value

def compute_verification_hash(v: Any) -> str:
    status_val = v.status.value if hasattr(v.status, "value") else str(v.status)
    claim_id = getattr(v, "claim_id", "")
    final_state = getattr(v, "final_state", "")
    created_at = getattr(v, "created_at", "")
    resolved_claim = getattr(v, "resolved_claim", "") or ""
    raw = f"{claim_id}:{status_val}:{final_state}:{created_at}:{resolved_claim}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
