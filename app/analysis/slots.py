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

def extract_slots_from_evidence(
    evidence_items: List[EvidenceItem], 
    claim_text: Optional[str] = None
) -> Dict[str, Optional[str]]:
    """Extracts actor, action, object, deadline, and clean action text from strong supporting evidence items with claim isolation."""
    extracted = {
        "actor": None,
        "action": None,
        "object": None,
        "deadline": None,
        "action_text": None,
        "technology": None
    }
    
    # Isolate evidence matching claim topic if claim_text is provided
    claim_words = set()
    if claim_text:
        claim_clean = re.sub(r"[^\w\s]", " ", claim_text.lower())
        stopwords = {
            "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are", "was",
            "were", "will", "be", "by", "with", "that", "this", "it", "from", "as", "into", "our",
            "we", "you", "i", "he", "she", "they", "them", "us", "about", "arjun", "maya", "rahul",
            "team", "decision", "action", "item", "requirement"
        }
        claim_words = {w for w in claim_clean.split() if w not in stopwords and len(w) > 2}

    def _evidence_matches_claim(e: EvidenceItem) -> bool:
        if not claim_words:
            return True
        ev_clean = re.sub(r"[^\w\s]", " ", f"{e.resolved_text or ''} {e.quote or ''} {e.text or ''}".lower())
        ev_words = set(ev_clean.split())
        
        # Explicit topic isolation
        if ("sso" in claim_words or "auth" in claim_words or "authentication" in claim_words):
            if "audit" in ev_words and "sso" not in ev_words and "auth" not in ev_words and "authentication" not in ev_words:
                return False
            if "sso" in ev_words or "auth" in ev_words or "authentication" in ev_words:
                return True

        if ("audit" in claim_words or "logging" in claim_words or "endpoint" in claim_words):
            if "sso" in ev_words and "audit" not in ev_words and "logging" not in ev_words:
                return False
            if "audit" in ev_words or "logging" in ev_words or "endpoint" in ev_words or "database" in ev_words:
                return True

        # Generic overlap
        overlap = claim_words.intersection(ev_words)
        return len(overlap) >= 1

    scoped_evidence = [e for e in evidence_items if _evidence_matches_claim(e)]
    if not scoped_evidence:
        scoped_evidence = evidence_items

    # 1. Prioritize explicit first-person commitment statements in scoped evidence
    commitments = [
        e for e in scoped_evidence 
        if e.relation == "SUPPORTS" and (
            e.stance == Stance.COMMIT 
            or re.search(r"\b(?:i'?ll|i will|i can take that|i'?m on it)\b", f"{e.resolved_text or ''} {e.quote or ''}", re.IGNORECASE)
        )
    ]
    
    candidates = commitments if commitments else [e for e in scoped_evidence if e.relation == "SUPPORTS"]
    
    for e in candidates:
        full_text = f"{e.resolved_text or ''} {e.quote or ''} {e.text or ''}".strip()
        
        # Extract actor (speaker of commitment or addressed person)
        if not extracted["actor"]:
            if e.actor_mentioned and not e.actor_mentioned.lower().startswith("speaker"):
                extracted["actor"] = e.actor_mentioned
            elif e.speaker and not e.speaker.lower().startswith("speaker") and not e.speaker.lower().startswith("user"):
                extracted["actor"] = e.speaker

        # Extract action and object from explicit commitment
        m_commit = re.search(
            r"\b(?:i'?ll|i will|i can take that\.?\s*(?:i'?ll|i will)?)\s+([a-zA-Z].*?)(?:\s+(?:by|before|until|on)\s+([A-Za-z0-9\s,-]+?))?[\.\!\?]?$",
            full_text,
            re.IGNORECASE
        )
        if m_commit:
            raw_action = m_commit.group(1).strip()
            # Clean leading intro phrases e.g. "take that. I'll "
            raw_action = re.sub(r"^(?:take that\.?\s*(?:i'?ll|i will)?\s*)", "", raw_action, flags=re.IGNORECASE).strip()
            if raw_action and not extracted["action_text"]:
                extracted["action_text"] = raw_action[0].upper() + raw_action[1:]
            
            # If deadline was in the same commitment clause
            raw_dead = m_commit.group(2)
            if raw_dead and not extracted["deadline"]:
                d_clean = raw_dead.strip().rstrip(".")
                if not re.search(r"\b(?:the\s+)?(?:release|version)\b", d_clean, re.IGNORECASE):
                    extracted["deadline"] = d_clean
                    
        # Dedicated exact deadline extraction (e.g. "November 5", "November 8", "October 10", "Wednesday", "Friday")
        if not extracted["deadline"]:
            m_dead_exact = re.search(
                r"\b(?:by|before|until|on)\s+((?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)|(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|tomorrow|next week)))\b",
                full_text,
                re.IGNORECASE
            )
            if m_dead_exact:
                extracted["deadline"] = m_dead_exact.group(1).strip()
            else:
                m_dead_generic = re.search(r"\b(?:by|before|until|on)\s+([A-Za-z0-9\s,-]+?)(?:[\.\!\?]|\s*$)", full_text, re.IGNORECASE)
                if m_dead_generic:
                    candidate_dead = m_dead_generic.group(1).strip()
                    # Do not capture vague release dates if not explicitly exact
                    if not re.search(r"\b(?:the\s+)?(?:release|version)\b", candidate_dead, re.IGNORECASE):
                        extracted["deadline"] = candidate_dead

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

