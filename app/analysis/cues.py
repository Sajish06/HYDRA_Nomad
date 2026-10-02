import re
from typing import Optional, Dict, Any, List
from app.models import Stance

CUE_PATTERNS = [
    # DEFER / UNRESOLVED / INVESTIGATION
    (
        Stance.DEFER,
        re.compile(
            r"\b(leave that for a future version|future version|for a future|hold off|not now|later|next semester|(?:defer (?:to|until)?|hold off until|push (?:to|for)?|postpone until)\s*next sprint|next quarter|postpone|push (?:this|it) back|revisit|table (?:this|it)|not yet|park (?:this|it)|haven'?t decided|hasn'?t been decided|nothing is decided|not decided (?:yet|today)|nobody has been assigned|hasn'?t been finalized|not finalized|hasn'?t been approved|not approved (?:yet|today)|deployment infrastructure hasn'?t|unconfirmed|not independently checked|until we receive|not sure we need|not sure whether|let'?s decide which|need to decide which|open investigations?|open investigation|investigat(?:e|ing|ion)|check whether|look into whether|explore whether|before we decide|don'?t think we'?ve selected|haven'?t selected|rather than implementation commitments?|not selected either|trade-offs? before we decide|look into|check if|investigate whether|investigate if|evaluate whether)\b",
            re.IGNORECASE
        )
    ),
    # REVERSE (checked before generic reject/decide, only if not a question)
    (
        Stance.REVERSE,
        re.compile(
            r"\b(actually,?\s*(?:we|let'?s|i|decided)|changed our mind|we decided not to|instead of\s+[a-z0-9_-]+|never mind)\b",
            re.IGNORECASE
        )
    ),
    # REJECT
    (
        Stance.REJECT,
        re.compile(
            r"\b(must never|never be stored|must not|let'?s not|we shouldn'?t|no,?\s*(?:i only|we|let|i)|not a good idea|don'?t (?:do|use|create|build|present|promise|mention|disclose)|against (?:it|this)|won'?t work|not independently verified|not accepted|not for every field|not a final requirement)\b",
            re.IGNORECASE
        )
    ),
    # CANCEL
    (
        Stance.CANCEL,
        re.compile(
            r"\b(cancel(?:led|ed)?|scrap|drop (?:it|this|that)|call it off|abandon|no longer)\b",
            re.IGNORECASE
        )
    ),
    # ACCEPT (Explicit confirmations and acknowledgments)
    (
        Stance.ACCEPT,
        re.compile(
            r"^(?:yes|yeah|sure|okay|ok|sounds good|agreed|understood|right|correct|i agree)(?:,\s*|[\.\!\?]|\s+|$)|that'?s committed|committed for|part of the sprint|sprint commitment|sprint scope|committed item|committed as well|we('ll| will) include that",
            re.IGNORECASE
        )
    ),
    # COMMIT (Explicit first-person commitments and task ownership, excluding investigations)
    (
        Stance.COMMIT,
        re.compile(
            r"\b(i'?ll\s+(?!investigate\b|check\b|look\b|explore\b|research\b|analyze\b|evaluate\b|compare\b|benchmark\b)[a-z]+|i will\s+(?!investigate\b|check\b|look\b|explore\b|research\b|analyze\b|evaluate\b|compare\b|benchmark\b)[a-z]+|i can\s+(?!investigate\b|check\b|look\b|explore\b|research\b|analyze\b|evaluate\b|compare\b|benchmark\b)(?:take|do|handle|prepare|document|[a-z]+)|i am on it|i'm on it|on it|committed to|i'?ll take care|i will take care|we('ll| will) include|we'll include)\b",
            re.IGNORECASE
        )
    ),
    # DECIDE (Requirements and team agreements when not negated)
    (
        Stance.DECIDE,
        re.compile(
            r"\b(must\s+(?:support|be|use|have|include|never)|is mandatory|mandatory|remains mandatory|let'?s\s+(?:definitely\s+)?(?:create|use|go with|do|build|make|set up|split|keep|finalize|leave)|we(?:'re|\s+are)\s+(?:going with|keeping)|we decided to|decided to|stays|still applies|is required|required before production|only needs|it'?s decided|approved|we should use\s+[A-Za-z0-9_-]+)\b",
            re.IGNORECASE
        )
    ),
    # QUESTION (Questions and inquiries)
    (
        Stance.QUESTION,
        re.compile(
            r"^(?:should we|can we|do we|what if|could we|can you|could you|will you|have we|has|is|are)\b|\?$",
            re.IGNORECASE
        )
    ),
    # SUGGEST
    (
        Stance.SUGGEST,
        re.compile(
            r"\b(you need (?:to|separate)|we need to|i suggest|i recommend|please\s+[a-z]+|consider|maybe we)\b",
            re.IGNORECASE
        )
    ),
    # PROPOSE
    (
        Stance.PROPOSE,
        re.compile(
            r"\b(we could\s+(?:create|build|make|set up|use|do|rebuild|launch|split|investigate|adopt|switch)|we should\s+(?:definitely\s+)?(?:have|deploy|encrypt|create|build|use|do|make|rebuild|split)|i think\s+(?:we should|fastapi|sqlite|[a-z]+)|how about|what if|it might be possible|we might\s+[a-z]+|we need a)\b",
            re.IGNORECASE
        )
    ),
]

def detect_cues(text: str) -> List[Dict[str, Any]]:
    """Runs rule-based regex patterns over a segment string to find stance cues."""
    cleaned = text.strip()
    matches = []
    
    # Check if this is a question first
    is_q = bool(re.search(r"^(?:should we|can we|do we|what if|could we|can you|could you|will you|have we|has|is|are)\b|\?$", cleaned, re.IGNORECASE))
    
    for stance, pattern in CUE_PATTERNS:
        # Prevent "instead of" in a question from being classified as REVERSE
        if stance == Stance.REVERSE and is_q:
            continue
        # Prevent "approved" in negative context from being classified as DECIDE
        if stance == Stance.DECIDE and re.search(r"\b(hasn'?t|haven'?t|not|never|nothing)\s+(?:been\s+)?(?:approved|decided|finalized)\b", cleaned, re.IGNORECASE):
            continue
            
        m = pattern.search(cleaned)
        if m:
            matches.append({
                "stance": stance,
                "cue": m.group(0),
                "span": m.span()
            })
    return matches

def detect_primary_cue(text: str) -> Optional[Dict[str, Any]]:
    """Returns the most significant stance hint for a segment."""
    cues = detect_cues(text)
    if not cues:
        return None
        
    cleaned = text.strip()
    # If text is primarily a question and not an explicit confirmation like "Yes, ..."
    if (cleaned.endswith("?") or re.match(r"^(?:should we|can we|do we|what if|could we|can you|could you)\b", cleaned, re.IGNORECASE)) and not re.match(r"^(?:yes|sure|agreed|okay|ok|right)\b", cleaned, re.IGNORECASE):
        for c in cues:
            if c["stance"] == Stance.QUESTION:
                return c

    # Prioritize NEGATE stances (DEFER, REVERSE, REJECT, CANCEL), then ACCEPT/COMMIT/DECIDE, then others
    priority_order = [
        Stance.REVERSE, Stance.DEFER, Stance.REJECT, Stance.CANCEL,
        Stance.ACCEPT, Stance.COMMIT, Stance.DECIDE,
        Stance.QUESTION, Stance.PROPOSE, Stance.SUGGEST
    ]
    for p_stance in priority_order:
        for c in cues:
            if c["stance"] == p_stance:
                return c
    return cues[0]
