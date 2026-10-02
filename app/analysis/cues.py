import re
from typing import Optional, Dict, Any, List
from app.models import Stance

CUE_PATTERNS = [
    # DEFER
    (
        Stance.DEFER,
        re.compile(
            r"\b(hold off|not now|later|next semester|next sprint|next quarter|postpone|push (?:this|it) back|revisit|table (?:this|it)|not yet|park (?:this|it)|unconfirmed|not independently checked|until we receive)\b",
            re.IGNORECASE
        )
    ),
    # REVERSE (checked before generic reject/decide)
    (
        Stance.REVERSE,
        re.compile(
            r"\b(actually,?\s*(?:we|let'?s|i|decided)|changed our mind|we decided not to|instead of|never mind)\b",
            re.IGNORECASE
        )
    ),
    # REJECT
    (
        Stance.REJECT,
        re.compile(
            r"\b(let'?s not|we shouldn'?t|no,?\s*(?:we|let|i)|not a good idea|don'?t (?:do|use|create|build|present|promise)|against (?:it|this)|won'?t work|not independently verified)\b",
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
    # COMMIT (Explicit first-person commitments and task ownership)
    (
        Stance.COMMIT,
        re.compile(
            r"\b(i'?ll\s+[a-z]+|i will\s+[a-z]+|i can\s+(?:take|do|handle|prepare|document|[a-z]+)|i am on it|i'm on it|on it|committed to|that'?s committed|yes,?\s+(?:that'?s committed|i'?ll|i will)|i can take that|i'?ll take care of|i'?ll do|i'?ll handle|i'?ll document|i'?ll prepare|i'?ll test|i'?ll improve|i'?ll add|i'?ll optimize|i'?ll enforce|i'?ll investigate|i will do|i will take)\b",
            re.IGNORECASE
        )
    ),
    # ACCEPT (Explicit confirmations)
    (
        Stance.ACCEPT,
        re.compile(
            r"^(?:yes|yeah|sure|okay|ok|sounds good|agreed|understood)(?:,\s*(?:i'?ll|i will|let'?s|i can|sounds good|we will|definitely|agreed|that'?s committed)|[\.\!\?]|\s*$|\s+(?:i'?ll|i will|let'?s|i can|sounds good|we will|definitely|agreed|that could work))\b",
            re.IGNORECASE
        )
    ),
    # DECIDE
    (
        Stance.DECIDE,
        re.compile(
            r"\b(let'?s\s+(?:definitely\s+)?(?:create|use|go with|do|build|make|set up|split)|we(?:'re|\s+are)\s+going with|we decided to|it'?s decided|approved)\b",
            re.IGNORECASE
        )
    ),
    # QUESTION (Do NOT infer commitment from questions)
    (
        Stance.QUESTION,
        re.compile(
            r"^(?:should we|can we|do we|what if|could we|can you|could you|will you|have we|has|is|are)\b|\?$",
            re.IGNORECASE
        )
    ),
    # SUGGEST / PROPOSE (Do NOT infer commitment from suggestions or possibilities)
    (
        Stance.SUGGEST,
        re.compile(
            r"\b(you need (?:to|separate)|we need to|i suggest|i recommend|please\s+[a-z]+|consider|maybe we|let'?s not)\b",
            re.IGNORECASE
        )
    ),
    (
        Stance.PROPOSE,
        re.compile(
            r"\b(we could\s+(?:create|build|make|set up|use|do|rebuild|launch|split|investigate|adopt|switch)|we should probably|we should\s+(?:create|build|use|do|make|rebuild|split)|i think we should|how about|what if|it might be possible)\b",
            re.IGNORECASE
        )
    ),
]

def detect_cues(text: str) -> List[Dict[str, Any]]:
    """Runs rule-based regex patterns over a segment string to find stance cues."""
    cleaned = text.strip()
    matches = []
    for stance, pattern in CUE_PATTERNS:
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
    # Prioritize NEGATE stances (DEFER, REVERSE, REJECT, CANCEL), then ACCEPT/DECIDE/COMMIT, then others
    priority_order = [
        Stance.REVERSE, Stance.DEFER, Stance.REJECT, Stance.CANCEL,
        Stance.ACCEPT, Stance.DECIDE, Stance.COMMIT,
        Stance.QUESTION, Stance.PROPOSE, Stance.SUGGEST
    ]
    for p_stance in priority_order:
        for c in cues:
            if c["stance"] == p_stance:
                return c
    return cues[0]
