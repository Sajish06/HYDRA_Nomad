import re
from typing import List, Dict, Any, Optional, Tuple
from app.models import Claim, SlotCheck, Stance, EvidenceItem

MONTH_NAMES = {
    1: ["january", "jan"],
    2: ["february", "feb"],
    3: ["march", "mar"],
    4: ["april", "apr"],
    5: ["may"],
    6: ["june", "jun"],
    7: ["july", "jul"],
    8: ["august", "aug"],
    9: ["september", "sep", "sept"],
    10: ["october", "oct"],
    11: ["november", "nov"],
    12: ["december", "dec"],
}

ACTION_SYNONYMS = {
    "implement": {"implement", "do", "build", "create", "prepare", "document", "develop", "setup", "set up", "write", "handle", "take", "ship"},
    "prepare": {"prepare", "document", "write", "draft", "create", "implement", "map"},
    "document": {"document", "prepare", "write", "draft", "map", "record", "detail"},
    "create": {"create", "build", "make", "implement", "set up", "setup", "prepare"},
    "build": {"build", "create", "implement", "develop", "make"},
    "ask": {"ask", "check", "inquire", "reach out", "request"},
    "test": {"test", "verify", "validate", "benchmark"},
    "investigate": {"investigate", "explore", "research", "check", "analyze"},
}

def normalize_slot_string(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"\b(a|an|the|by|on|before|until|to|of|in|for|with)\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())

def parse_date_components(date_str: str) -> Dict[str, Any]:
    """Parses ISO dates, month names, days, and years for semantic comparison."""
    if not date_str:
        return {}
    
    clean = date_str.lower().strip()
    
    # 1. Check ISO format YYYY-MM-DD
    m_iso = re.search(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b", clean)
    if m_iso:
        year = int(m_iso.group(1))
        month = int(m_iso.group(2))
        day = int(m_iso.group(3))
        month_words = MONTH_NAMES.get(month, [])
        return {"year": year, "month": month, "day": day, "month_words": month_words, "type": "iso"}
    
    # 2. Check MM-DD-YYYY or DD-MM-YYYY
    m_us = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", clean)
    if m_us:
        first = int(m_us.group(1))
        second = int(m_us.group(2))
        year = int(m_us.group(3))
        # if first > 12, it's day-month-year
        if first > 12:
            day, month = first, second
        else:
            month, day = first, second
        month_words = MONTH_NAMES.get(month, [])
        return {"year": year, "month": month, "day": day, "month_words": month_words, "type": "iso"}

    # 3. Check Month name + Day (e.g. "October 10", "10th of October", "Oct 10")
    for m_num, m_variants in MONTH_NAMES.items():
        for variant in m_variants:
            if re.search(r"\b" + variant + r"\b", clean):
                m_day = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", clean)
                day = int(m_day.group(1)) if m_day else None
                m_year = re.search(r"\b(20\d{2})\b", clean)
                year = int(m_year.group(1)) if m_year else None
                return {"year": year, "month": m_num, "day": day, "month_words": m_variants, "type": "month_day"}

    # 4. Relative / named keywords (e.g. "friday", "tomorrow", "end of month")
    keywords = ["friday", "monday", "tuesday", "wednesday", "thursday", "saturday", "sunday", "tomorrow", "next week", "eod", "end of month", "end of the month", "sprint"]
    found = [k for k in keywords if k in clean]
    if found:
        return {"keywords": found, "type": "keyword"}

    return {"raw": clean, "type": "raw"}

def dates_match_semantically(claim_date_str: str, text: str) -> bool:
    """Semantically verifies if a claim deadline matches dialogue evidence text."""
    c_info = parse_date_components(claim_date_str)
    if not c_info:
        return False
    
    text_lower = text.lower()
    
    if c_info.get("type") in ("iso", "month_day"):
        day = c_info.get("day")
        month_words = c_info.get("month_words", [])
        
        has_month = any(re.search(r"\b" + re.escape(w) + r"\b", text_lower) for w in month_words)
        if day is not None:
            # Check for day number in text (e.g. 10 or 10th)
            has_day = bool(re.search(r"\b" + str(day) + r"(?:st|nd|rd|th)?\b", text_lower))
            if has_month and has_day:
                return True
        elif has_month:
            return True

    if c_info.get("type") == "keyword":
        for kw in c_info.get("keywords", []):
            if kw in text_lower:
                return True

    # Fallback to normalized substring containment
    claim_norm = normalize_slot_string(claim_date_str)
    text_norm = normalize_slot_string(text)
    if claim_norm and claim_norm in text_norm:
        return True
        
    return False

def extract_slots_from_evidence(evidence_items: List[EvidenceItem]) -> Dict[str, Optional[str]]:
    """Extracts actor, action, object, and deadline from strong supporting evidence items."""
    extracted = {
        "actor": None,
        "action": None,
        "object": None,
        "deadline": None
    }
    
    for e in evidence_items:
        if e.relation != "SUPPORTS" and e.stance not in (Stance.COMMIT, Stance.ACCEPT, Stance.DECIDE):
            continue
            
        full_text = f"{e.resolved_text or ''} {e.quote or ''} {e.text or ''}".strip()
        
        # 1. Extract deadline
        if not extracted["deadline"]:
            m_dead = re.search(r"\b(?:by|before|until|on)\s+([A-Za-z0-9\s,-]+?)(?:[\.\!\?]|\s*$)", full_text, re.IGNORECASE)
            if m_dead:
                extracted["deadline"] = m_dead.group(1).strip()

        # 2. Extract actor
        if not extracted["actor"]:
            if e.actor_mentioned:
                extracted["actor"] = e.actor_mentioned
            elif e.speaker and not e.speaker.lower().startswith("speaker") and not e.speaker.lower().startswith("user"):
                extracted["actor"] = e.speaker

        # 3. Extract action and object from first-person commitments e.g. "I'll document the SSO requirements..."
        if not extracted["action"] or not extracted["object"]:
            m_commit = re.search(r"\b(?:i'?ll|i will|i can)\s+([a-z]+)\s+(.*?)(?:\s+by\s+[A-Za-z0-9\s,-]+|[\.\!\?]|$)", full_text, re.IGNORECASE)
            if m_commit:
                extracted["action"] = m_commit.group(1).strip()
                extracted["object"] = m_commit.group(2).strip()

    return extracted

def check_slots(claim: Claim, evidence_items: List[EvidenceItem]) -> List[SlotCheck]:
    """Checks grounding status for actor, action, object, deadline against verified evidence semantically."""
    slot_results = []
    
    # 1. ACTOR
    if claim.actor:
        c_actor_norm = normalize_slot_string(claim.actor)
        grounded_idx = []
        conflict_idx = []

        for e in evidence_items:
            spk_norm = normalize_slot_string(e.speaker)
            txt_norm = normalize_slot_string(f"{e.resolved_text or ''} {e.quote or ''} {e.text or ''}")
            
            # Grounded if speaker matches, actor mentioned in evidence, or actor was addressed
            if (
                spk_norm == c_actor_norm 
                or c_actor_norm in txt_norm 
                or (e.actor_mentioned and normalize_slot_string(e.actor_mentioned) == c_actor_norm)
            ) and e.stance in (Stance.COMMIT, Stance.ACCEPT, Stance.DECIDE, Stance.INFORM, Stance.QUESTION):
                grounded_idx.append(e.idx)
            elif c_actor_norm in txt_norm:
                grounded_idx.append(e.idx)
            elif e.speaker and spk_norm != c_actor_norm and not spk_norm.startswith("speaker") and e.stance == Stance.COMMIT:
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
        act_root = c_act_norm.split()[0] if c_act_norm.split() else c_act_norm
        synonyms = ACTION_SYNONYMS.get(act_root, {act_root})
        
        grounded_idx = []
        for e in evidence_items:
            res_norm = normalize_slot_string(f"{e.resolved_text or ''} {e.quote or ''} {e.text or ''}")
            # Check root, synonyms, or word overlap
            if any(syn in res_norm for syn in synonyms) or any(w in res_norm for w in c_act_norm.split() if len(w) > 2):
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
        obj_words = [w for w in c_obj_norm.split() if len(w) > 2]
        grounded_idx = []
        
        for e in evidence_items:
            res_norm = normalize_slot_string(f"{e.resolved_text or ''} {e.quote or ''} {e.text or ''}")
            if not obj_words:
                grounded_idx.append(e.idx)
            else:
                matched_words = [w for w in obj_words if w in res_norm]
                # Grounded if at least 1 key word matches or >= 25% overlap
                if len(matched_words) >= 1:
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
        grounded_idx = []
        conflict_idx = []

        for e in evidence_items:
            full_evidence = f"{e.resolved_text or ''} {e.quote or ''} {e.text or ''}"
            if dates_match_semantically(claim.deadline, full_evidence):
                grounded_idx.append(e.idx)
            elif any(w in normalize_slot_string(full_evidence) for w in ["friday", "monday", "tuesday", "wednesday", "thursday", "tomorrow", "next week"]) and not dates_match_semantically(claim.deadline, full_evidence):
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

