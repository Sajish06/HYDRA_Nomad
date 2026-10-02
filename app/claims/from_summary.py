import re
import uuid
from typing import List, Optional
from app.models import Meeting, Claim, ClaimType, ClaimDraft
from app.llm.client import query_structured_llm, LLMUnavailable
from app.llm.prompts import CLAIM_STRUCTURING_SYSTEM
from app.db import get_db

PROMPT_VERSION = "v1"

def parse_bullet_heuristic(bullet: str, is_action: bool = False) -> ClaimDraft:
    """Deterministic fallback for parsing summary bullets into ClaimDraft."""
    text = bullet.strip()
    
    # Check deadline (e.g. "by October 6", "by Friday", "until EOD", "before tomorrow")
    deadline = None
    m_dead = re.search(r"\b(?:by|before|until|on)\s+([A-Za-z0-9\s,-]+)$", text, re.IGNORECASE)
    if m_dead:
        deadline_candidate = m_dead.group(1).strip().rstrip(".")
        date_keywords = [
            "friday", "monday", "tuesday", "wednesday", "thursday", "saturday", "sunday",
            "tomorrow", "next week", "eod", "semester", "sprint", "end of",
            "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
            "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"
        ]
        if any(w in deadline_candidate.lower() for w in date_keywords) or re.search(r"\d{1,4}", deadline_candidate):
            deadline = deadline_candidate
            text_without_deadline = text[:m_dead.start()].strip()
        else:
            text_without_deadline = text
    else:
        text_without_deadline = text

    # Check actor e.g. "Omar will request...", "Omar committed to request...", "Alice to create..."
    actor = None
    action = None
    obj = None
    
    m_actor = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:will|to|should|must|agreed to|committed to|agreed|committed|plans to|will be responsible for)\s+(?:to\s+)?([a-z]+)\s+(.*)$", text_without_deadline, re.IGNORECASE)
    if m_actor:
        raw_actor = m_actor.group(1).strip()
        # Clean trailing helper words from actor name
        actor = re.sub(r"\s+(?:committed|agreed|plans|responsible)$", "", raw_actor, flags=re.IGNORECASE).strip()
        action = m_actor.group(2).strip()
        obj = m_actor.group(3).strip()
    else:
        if is_action:
            m_verb = re.match(r"^([A-Za-z]+)\s+(.*)$", text_without_deadline)
            if m_verb and m_verb.group(1).lower() not in {"the", "a", "an", "this", "that", "arr", "it", "we", "they", "our"}:
                action = m_verb.group(1).strip()
                obj = m_verb.group(2).strip()
            else:
                obj = text_without_deadline
        else:
            obj = text_without_deadline

    c_type = ClaimType.COMMITMENT if (actor and (action or deadline)) else (ClaimType.ACTION if is_action else ClaimType.DECISION)
    
    # Build clean normalized sentence
    if actor and action and obj:
        norm = f"{actor} will {action} {obj}"
    elif action and obj:
        norm = f"{action} {obj}"
    else:
        norm = bullet.strip()
        
    if deadline and not norm.endswith(deadline):
        norm = f"{norm} by {deadline}"

    return ClaimDraft(
        type=c_type,
        actor=actor,
        action=action,
        object=obj,
        deadline=deadline,
        normalized=norm.rstrip(".")
    )

def extract_claims_from_summary(meeting: Meeting) -> List[Claim]:
    """Generates structured Claim objects from meeting summary decisions and action items."""
    claims = []
    
    raw_bullets = []
    for d in meeting.summary_decisions:
        raw_bullets.append((d, False))
    for a in meeting.summary_actions:
        raw_bullets.append((a, True))

    for idx, (bullet, is_action) in enumerate(raw_bullets):
        bullet_text = bullet.strip()
        if not bullet_text:
            continue

        user_prompt = f"Meeting Summary Bullet: \"{bullet_text}\"\nBullet Category: {'Action Item' if is_action else 'Decision'}"
        
        try:
            draft = query_structured_llm(
                prompt_name="claim_structuring",
                prompt_version=PROMPT_VERSION,
                system_prompt=CLAIM_STRUCTURING_SYSTEM,
                user_prompt=user_prompt,
                response_model=ClaimDraft,
                input_context={"bullet": bullet_text, "is_action": is_action}
            )
        except Exception:
            draft = parse_bullet_heuristic(bullet_text, is_action=is_action)

        h_draft = parse_bullet_heuristic(bullet_text, is_action=is_action)
        if not draft.actor and h_draft.actor:
            draft.actor = h_draft.actor
        if not draft.action and h_draft.action:
            draft.action = h_draft.action
        if not draft.deadline and h_draft.deadline:
            draft.deadline = h_draft.deadline
        if not draft.object and h_draft.object:
            draft.object = h_draft.object
        if h_draft.type == ClaimType.COMMITMENT or (draft.actor and (draft.action or draft.deadline)):
            draft.type = ClaimType.COMMITMENT

        # Force null for generic pronouns
        if draft.actor and draft.actor.lower() in {"we", "they", "someone", "team", "all", "us", "you", "i"}:
            draft.actor = None

        claim_id = f"claim_{meeting.meeting_id}_{idx+1}"
        claim = Claim(
            claim_id=claim_id,
            meeting_id=meeting.meeting_id,
            text=bullet_text,
            source="SUMMARY",
            type=draft.type,
            actor=draft.actor,
            action=draft.action,
            object=draft.object,
            deadline=draft.deadline,
            normalized=draft.normalized or bullet_text
        )
        claims.append(claim)

    # Persist claims to DB
    with get_db() as conn:
        for c in claims:
            conn.execute(
                """INSERT OR REPLACE INTO claims (id, meeting_id, text, normalized, source, type, actor, action, object, deadline)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (c.claim_id, c.meeting_id, c.text, c.normalized, c.source, c.type.value, c.actor, c.action, c.object, c.deadline)
            )

    return claims
