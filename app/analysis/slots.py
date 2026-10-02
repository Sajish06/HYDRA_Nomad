import re
from typing import List, Dict, Any, Optional
from app.models import Claim, SlotCheck, Stance, EvidenceItem

def normalize_slot_string(s: Optional[str]) -> str:
    if not s:
        return ""
    # Lowercase, remove punctuation and articles
    s = s.lower()
    s = re.sub(r"\b(a|an|the|by|on|before|until|to)\b", "", s)
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.split())

def check_slots(claim: Claim, evidence_items: List[EvidenceItem]) -> List[SlotCheck]:
    """Checks grounding status for actor, action, object, deadline against verified evidence."""
    slot_results = []
    
    # 1. ACTOR
    if claim.actor:
        c_actor_norm = normalize_slot_string(claim.actor)
        grounded_idx = []
        conflict_idx = []

        for e in evidence_items:
            spk_norm = normalize_slot_string(e.speaker)
            # If speaker matches claim actor and has strong affirmative stance
            if spk_norm == c_actor_norm and e.stance in (Stance.COMMIT, Stance.ACCEPT, Stance.DECIDE):
                grounded_idx.append(e.idx)
            elif e.speaker and spk_norm != c_actor_norm and e.stance == Stance.COMMIT:
                conflict_idx.append(e.idx)
            elif c_actor_norm in normalize_slot_string(e.resolved_text or ""):
                grounded_idx.append(e.idx)

        if grounded_idx:
            status = "GROUNDED"
            idx_list = grounded_idx
        elif conflict_idx:
            status = "CONFLICT"
            idx_list = conflict_idx
        else:
            status = "MISSING"
            idx_list = []

        slot_results.append(SlotCheck(
            slot="actor",
            claim_value=claim.actor,
            status=status,
            evidence_idx=idx_list
        ))
    else:
        slot_results.append(SlotCheck(
            slot="actor",
            claim_value=None,
            status="NOT_APPLICABLE",
            evidence_idx=[]
        ))

    # 2. ACTION
    if claim.action:
        c_act_norm = normalize_slot_string(claim.action)
        grounded_idx = []
        for e in evidence_items:
            res_norm = normalize_slot_string(e.resolved_text or e.text)
            if c_act_norm in res_norm or any(w in res_norm for w in c_act_norm.split() if len(w) > 2):
                grounded_idx.append(e.idx)
        
        status = "GROUNDED" if grounded_idx else "MISSING"
        slot_results.append(SlotCheck(
            slot="action",
            claim_value=claim.action,
            status=status,
            evidence_idx=grounded_idx
        ))
    else:
        slot_results.append(SlotCheck(
            slot="action",
            claim_value=None,
            status="NOT_APPLICABLE",
            evidence_idx=[]
        ))

    # 3. OBJECT
    if claim.object:
        c_obj_norm = normalize_slot_string(claim.object)
        grounded_idx = []
        for e in evidence_items:
            res_norm = normalize_slot_string(e.resolved_text or e.text)
            # Check overlap
            obj_words = [w for w in c_obj_norm.split() if len(w) > 2]
            if obj_words and any(w in res_norm for w in obj_words):
                grounded_idx.append(e.idx)

        status = "GROUNDED" if grounded_idx else "MISSING"
        slot_results.append(SlotCheck(
            slot="object",
            claim_value=claim.object,
            status=status,
            evidence_idx=grounded_idx
        ))
    else:
        slot_results.append(SlotCheck(
            slot="object",
            claim_value=None,
            status="NOT_APPLICABLE",
            evidence_idx=[]
        ))

    # 4. DEADLINE
    if claim.deadline:
        c_dead_norm = normalize_slot_string(claim.deadline)
        grounded_idx = []
        conflict_idx = []

        for e in evidence_items:
            text_norm = normalize_slot_string(e.text)
            if c_dead_norm in text_norm:
                grounded_idx.append(e.idx)
            elif any(w in text_norm for w in ["friday", "monday", "tuesday", "wednesday", "thursday", "tomorrow", "next week"]) and c_dead_norm not in text_norm:
                conflict_idx.append(e.idx)

        if grounded_idx:
            status = "GROUNDED"
            idx_list = grounded_idx
        elif conflict_idx:
            status = "CONFLICT"
            idx_list = conflict_idx
        else:
            status = "MISSING"
            idx_list = []

        slot_results.append(SlotCheck(
            slot="deadline",
            claim_value=claim.deadline,
            status=status,
            evidence_idx=idx_list
        ))
    else:
        slot_results.append(SlotCheck(
            slot="deadline",
            claim_value=None,
            status="NOT_APPLICABLE",
            evidence_idx=[]
        ))

    return slot_results
