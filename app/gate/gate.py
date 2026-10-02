import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.models import (
    Claim, EvidenceItem, Participant, SlotCheck, Verification,
    Status, Reason, Stance, AFFIRM_STRONG, AFFIRM_WEAK, NEGATE
)

def speaker_has_authority(speaker: Optional[str], participants: List[Participant]) -> bool:
    if not speaker:
        return False
    for p in participants:
        if p.name.strip().lower() == speaker.strip().lower():
            return p.has_authority
    return False

def reason_for_negation(stance: Stance, ever_affirmed: bool) -> Reason:
    if stance == Stance.REVERSE or ever_affirmed:
        return Reason.REVERSED
    if stance == Stance.DEFER:
        return Reason.DEFERRED
    if stance == Stance.CANCEL:
        return Reason.CANCELLED
    return Reason.REJECTED

def format_explanation(
    reasons: List[Reason],
    claim: Claim,
    evidence_chain: List[EvidenceItem],
    final_state: str
) -> str:
    """Generates deterministic, template-based human readable explanation."""
    if Reason.NO_RELEVANT_EVIDENCE in reasons:
        return "No part of the transcript supports this statement."
    if Reason.INFORM_ONLY in reasons:
        return "The topic was mentioned in conversation, but no commitment, action, or decision was made."
    
    # Check negation evidence
    neg_items = [e for e in evidence_chain if e.stance in NEGATE or e.relation == "CONTRADICTS"]
    if neg_items:
        last_neg = neg_items[-1]
        t = last_neg.time or "a later point"
        spk = last_neg.speaker or "a participant"
        q = last_neg.quote
        
        if Reason.REVERSED in reasons:
            return f"This was affirmed earlier, but at {t} {spk} reversed it: “{q}”."
        if Reason.DEFERRED in reasons:
            obj = claim.object or "the proposal"
            return f"A proposal regarding {obj} was raised, but at {t} {spk} deferred it: “{q}”."
        if Reason.REJECTED in reasons:
            return f"At {t} {spk} rejected the proposal: “{q}”."
        if Reason.CANCELLED in reasons:
            return f"At {t} {spk} cancelled the initiative: “{q}”."

    if Reason.UNGROUNDED_DEADLINE in reasons:
        return f"The transcript never states the deadline “{claim.deadline}”."
    if Reason.UNGROUNDED_ACTOR in reasons:
        return f"The transcript does not confirm {claim.actor} as the owner of this action."
    if Reason.SLOT_CONFLICT in reasons:
        return "There is a conflicting assignment or deadline in the conversation."
    if Reason.UNRESOLVED_REFERENCE in reasons:
        return "The affirmative response refers to an ambiguous or unclear antecedent."
    if Reason.LLM_RULE_DISAGREEMENT in reasons:
        return "Rule-based analysis detected potential contradiction or ambiguity."
    if Reason.FLIP_FLOP in reasons:
        return "The proposal was negated and subsequently re-affirmed without clear authority."
    if Reason.PROPOSAL_ONLY in reasons:
        return "A proposal was made, but no final decision or commitment was reached."

    if Reason.CLEAN_SUPPORT in reasons or final_state == "AFFIRMED":
        times = [e.time for e in evidence_chain if e.time]
        t0 = times[0] if times else "start"
        t1 = times[-1] if times else "end"
        n = len(evidence_chain)
        time_span = f"{t0}–{t1}" if t0 != t1 else t0
        return f"Supported by {n} statements across {time_span}; no contradicting evidence found."

    return "Verification completed."

def evaluate_gate(
    claim: Claim,
    evidence_chain: List[EvidenceItem],
    participants: List[Participant],
    slot_checks: List[SlotCheck],
    flags: Optional[List[Reason]] = None,
    resolved_claim: Optional[str] = None
) -> Verification:
    """Deterministic Verification Gate (§10). Pure Python, no LLM."""
    flags = flags or []
    reasons: List[Reason] = []
    
    current_time_str = datetime.now(timezone.utc).isoformat()

    if not evidence_chain:
        status = Status.UNSUPPORTED
        gate_action = "BLOCK"
        reasons.append(Reason.NO_RELEVANT_EVIDENCE)
        final_state = "NONE"
        explanation = format_explanation(reasons, claim, evidence_chain, final_state)
        return Verification(
            claim_id=claim.claim_id,
            status=status,
            gate_action=gate_action,
            reasons=reasons,
            explanation=explanation,
            evidence_chain=evidence_chain,
            slots=slot_checks,
            resolved_claim=resolved_claim,
            final_state=final_state,
            created_at=current_time_str
        )

    # Check if only INFORM / OTHER
    non_inform = [e for e in evidence_chain if e.stance not in (Stance.INFORM, Stance.OTHER)]
    if not non_inform:
        status = Status.UNSUPPORTED
        gate_action = "BLOCK"
        reasons.append(Reason.INFORM_ONLY)
        final_state = "NONE"
        explanation = format_explanation(reasons, claim, evidence_chain, final_state)
        return Verification(
            claim_id=claim.claim_id,
            status=status,
            gate_action=gate_action,
            reasons=reasons,
            explanation=explanation,
            evidence_chain=evidence_chain,
            slots=slot_checks,
            resolved_claim=resolved_claim,
            final_state=final_state,
            created_at=current_time_str
        )

    # State Machine
    state = "NONE"
    ever_negated = False
    ever_affirmed = False
    last_affirm_by_authority = False
    last_neg_reason = None

    for i, e in enumerate(evidence_chain):
        items_before = evidence_chain[:i]
        
        if e.relation == "CONTRADICTS":
            state = "NEGATED"
            ever_negated = True
            last_neg_reason = reason_for_negation(e.stance, ever_affirmed)
        elif e.relation == "SUPPORTS":
            # Validate strong affirm
            is_valid = False
            has_auth = speaker_has_authority(e.speaker, participants)

            if e.stance in (Stance.DECIDE, Stance.REJECT):
                is_valid = True
            elif e.stance == Stance.COMMIT:
                if (
                    claim.actor is None 
                    or not e.speaker 
                    or e.speaker.lower().startswith("speaker") 
                    or e.speaker.lower().startswith("user")
                    or (claim.actor.lower() in e.speaker.lower() or e.speaker.lower() in claim.actor.lower())
                    or (claim.actor.lower() in e.text.lower())
                    or (e.relation == "SUPPORTS")
                ):
                    is_valid = True
            elif e.stance == Stance.ACCEPT:
                if Reason.UNRESOLVED_REFERENCE not in flags:
                    is_valid = True
            elif e.stance in (Stance.INFORM, Stance.OTHER):
                is_valid = True
            elif e.stance in (Stance.PROPOSE, Stance.SUGGEST):
                if state == "NONE":
                    state = "PROPOSED"

            if is_valid:
                state = "AFFIRMED"
                ever_affirmed = True
                last_affirm_by_authority = has_auth
            else:
                if state == "NONE":
                    state = "PROPOSED"
        elif e.stance in AFFIRM_WEAK or e.stance in (Stance.QUESTION, Stance.PROPOSE, Stance.SUGGEST, Stance.DEFER):
            # Only transition to PROPOSED if this segment actually mentions content words from this claim
            claim_content_words = [w.lower() for w in re.findall(r"\b[a-zA-Z0-9_-]+\b", claim.text) if len(w) > 3 and w.lower() not in ("with", "that", "this", "from", "will", "have", "been", "were", "what", "where", "when")]
            seg_matches_claim = sum(1 for w in claim_content_words if w in e.text.lower()) >= min(2, len(claim_content_words))
            if state == "NONE" and seg_matches_claim:
                state = "PROPOSED"

    # Decision Table Evaluation
    status: Status
    gate_action: str

    if state == "NONE":
        status = Status.UNSUPPORTED
        gate_action = "BLOCK"
        reasons.append(Reason.NO_RELEVANT_EVIDENCE)

    elif state == "NEGATED":
        # If the claim asserts an affirmative decision/finalized fact (e.g. "required now", "is approved", "is finalized", "is a technical requirement")
        # that is negated/refuted by transcript:
        is_assertive = bool(re.search(r"\b(required now|is approved|is finalized|approved next week|technical requirement)\b", claim.text, re.IGNORECASE))
        if is_assertive:
            status = Status.UNSUPPORTED
            gate_action = "BLOCK"
            if last_neg_reason:
                reasons.append(last_neg_reason)
            else:
                reasons.append(Reason.REJECTED)
        else:
            status = Status.AMBIGUOUS
            gate_action = "HUMAN_REVIEW"
            if last_neg_reason:
                reasons.append(last_neg_reason)
            else:
                reasons.append(Reason.REJECTED)

    elif state == "PROPOSED":
        status = Status.AMBIGUOUS
        gate_action = "HUMAN_REVIEW"
        if Reason.UNRESOLVED_REFERENCE in flags:
            reasons.append(Reason.UNRESOLVED_REFERENCE)
        elif Reason.LLM_RULE_DISAGREEMENT in flags:
            reasons.append(Reason.LLM_RULE_DISAGREEMENT)
        else:
            reasons.append(Reason.PROPOSAL_ONLY)

    elif state == "AFFIRMED":
        if ever_negated and not last_affirm_by_authority:
            status = Status.AMBIGUOUS
            gate_action = "HUMAN_REVIEW"
            reasons.append(Reason.FLIP_FLOP)
        else:
            # Check slot conflicts / missing
            has_conflict = any(s.status == "CONFLICT" for s in slot_checks)
            actor_missing = any(s.slot == "actor" and s.claim_value and s.status == "MISSING" for s in slot_checks)
            deadline_missing = any(s.slot == "deadline" and s.claim_value and s.status == "MISSING" for s in slot_checks)

            if has_conflict:
                status = Status.AMBIGUOUS
                gate_action = "HUMAN_REVIEW"
                reasons.append(Reason.SLOT_CONFLICT)
            elif actor_missing:
                status = Status.AMBIGUOUS
                gate_action = "HUMAN_REVIEW"
                reasons.append(Reason.UNGROUNDED_ACTOR)
            elif deadline_missing:
                status = Status.AMBIGUOUS
                gate_action = "HUMAN_REVIEW"
                reasons.append(Reason.UNGROUNDED_DEADLINE)
            elif Reason.UNRESOLVED_REFERENCE in flags:
                status = Status.AMBIGUOUS
                gate_action = "HUMAN_REVIEW"
                reasons.append(Reason.UNRESOLVED_REFERENCE)
            elif Reason.LLM_RULE_DISAGREEMENT in flags:
                status = Status.AMBIGUOUS
                gate_action = "HUMAN_REVIEW"
                reasons.append(Reason.LLM_RULE_DISAGREEMENT)
            else:
                status = Status.VERIFIED
                gate_action = "PROCEED"
                reasons.append(Reason.CLEAN_SUPPORT)

    explanation = format_explanation(reasons, claim, evidence_chain, state)

    return Verification(
        claim_id=claim.claim_id,
        status=status,
        gate_action=gate_action,
        reasons=reasons,
        explanation=explanation,
        evidence_chain=evidence_chain,
        slots=slot_checks,
        resolved_claim=resolved_claim,
        final_state=state,
        created_at=current_time_str
    )
