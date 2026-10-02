import re
from typing import List, Dict, Any, Tuple, Optional
from app.models import Claim, ClaimType, Stance, SegmentStance, StanceAnalysisResponse, Reason, NEGATE, AFFIRM_STRONG
from app.llm.prompts import STANCE_ANALYSIS_SYSTEM
from app.llm.client import query_structured_llm
from app.analysis.cues import detect_primary_cue, detect_cues

PROMPT_VERSION = "v1"

def validate_quote(raw_quote: str, segment_text: str) -> Tuple[str, bool]:
    """Ensures quote is an exact substring of segment text; otherwise returns full segment text."""
    if not raw_quote:
        return segment_text, True

    norm_quote = " ".join(raw_quote.strip().split())
    norm_text = " ".join(segment_text.strip().split())

    if norm_quote.lower() in norm_text.lower():
        # Find exact casing span in original segment_text
        match = re.search(re.escape(norm_quote), segment_text, re.IGNORECASE)
        if match:
            return match.group(0), False
        return raw_quote, False

    # Quote hallucinated / paraphrased: repair by using segment text
    return segment_text, True

from app.analysis.slots import ACTION_SYNONYMS

GENERIC_VERBS = {
    "use", "used", "using", "make", "create", "build", "have", "has", "select", "selected",
    "take", "keep", "stay", "stays", "include", "included", "continue", "work", "support",
    "document", "handle", "prepare", "decide", "agreed", "look", "require", "required",
    "needs", "need", "mandatory"
}

TOPIC_STOPWORDS = {
    "requirement", "requirements", "technical", "session", "database", "store",
    "prototype", "pipeline", "framework", "required", "mandatory", "decided",
    "finalized", "approved", "payment", "payments", "field", "fields", "system"
}

def heuristic_classify_segment(seg: Dict[str, Any], claim: Claim, prev_seg: Optional[Dict[str, Any]] = None) -> SegmentStance:
    """Heuristic fallback for stance analysis when LLM is unavailable."""
    text = seg.get("text", "")
    idx = seg.get("idx", 0)
    speaker = seg.get("speaker")
    
    cue = detect_primary_cue(text)
    stance = cue["stance"] if cue else Stance.INFORM
    
    # Check relevance to claim
    claim_stopwords = {
        "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are", "was",
        "were", "will", "be", "by", "with", "that", "this", "it", "from", "as", "has", "been", "had",
        "should", "must", "not", "no", "never", "can", "cannot", "could", "would", "do", "does",
        "did", "am", "also", "only", "we", "i", "you", "they", "our", "all", "so", "just"
    }
    raw_claim_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", f"{claim.text} {claim.object or ''} {claim.action or ''} {claim.normalized or ''}".lower())) - claim_stopwords
    
    # Expand with action synonyms for semantic matching
    claim_words = set(raw_claim_words)
    if claim.action:
        act_lower = claim.action.lower().strip()
        for root, syns in ACTION_SYNONYMS.items():
            if act_lower in syns or root in act_lower:
                claim_words.update(syns)

    key_claim_words = {w for w in claim_words if w not in GENERIC_VERBS}
    primary_subject_words = {w for w in key_claim_words if w not in TOPIC_STOPWORDS}

    seg_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())) - claim_stopwords
    
    # Anaphora only applies if segment refers to an antecedent and does NOT introduce its own distinct topic noun
    has_pronoun = bool(re.search(r"\b(that|this|it|so|them|these|those)\b", text, re.IGNORECASE)) or len(text.split()) <= 4
    has_own_topic = bool(re.search(r"\b(database|field|fields|provider|card|payment|tokens|mfa|fastapi|sqlite|redis|aws|framework|biometric|infrastructure)\b", text, re.IGNORECASE))
    is_anaphoric = has_pronoun and not has_own_topic

    prev_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", prev_seg.get("text", "").lower())) - claim_stopwords if (prev_seg and is_anaphoric) else set()
    all_context_words = seg_words | prev_words

    def _words_overlap(set1, set2):
        if not set1 or not set2:
            return False
        for w1 in set1:
            for w2 in set2:
                if (
                    w1 == w2 
                    or w1.rstrip('s') == w2.rstrip('s') 
                    or w1.rstrip('ed') == w2.rstrip('ed') 
                    or w1.rstrip('ing') == w2.rstrip('ing')
                    or (min(len(w1), len(w2)) >= 6 and (w1.startswith(w2[:6]) or w2.startswith(w1[:6])))
                ):
                    return True
        return False

    has_claim_overlap = _words_overlap(claim_words, seg_words)
    has_context_claim_overlap = _words_overlap(claim_words, all_context_words)
    has_key_overlap = _words_overlap(key_claim_words, seg_words)
    has_context_key_overlap = _words_overlap(key_claim_words, all_context_words)
    has_primary_overlap = _words_overlap(primary_subject_words, seg_words) or (is_anaphoric and _words_overlap(primary_subject_words, all_context_words))

    overlap = len(claim_words.intersection(seg_words))
    context_overlap = len(claim_words.intersection(all_context_words))

    relevance = 0.20
    toward = "NEUTRAL"

    # Check if claim is asserting a negative constraint (e.g. "must not", "never", "should not", "not be disclosed")
    claim_is_negative = bool(re.search(r"\b(must not|never|should not|cannot|not be disclosed|don'?t)\b", claim.text, re.IGNORECASE))

    if (has_claim_overlap and (has_key_overlap or not key_claim_words)) or (has_context_claim_overlap and has_context_key_overlap) or (claim.actor and claim.actor.lower() in text.lower()):
        relevance = min(0.95, 0.45 + max(overlap, context_overlap, 1) * 0.15)
        
        # 1. COMMITMENT / ACTION CLAIMS
        if claim.type in (ClaimType.COMMITMENT, ClaimType.ACTION):
            speaker_matches = (
                not claim.actor 
                or not speaker 
                or speaker.lower().startswith("speaker") 
                or speaker.lower().startswith("user")
                or (claim.actor.lower() in speaker.lower() or speaker.lower() in claim.actor.lower())
                or (claim.actor.lower() in text.lower())
                or (prev_seg and claim.actor.lower() in prev_seg.get("text", "").lower())
            )

            # Check if speaker states "only agreed to [different task]" vs [this task]
            if "only agreed to" in text.lower():
                # E.g. "No, I only agreed to handle the embedding pipeline."
                if claim.object and any(w in text.lower() for w in claim.object.lower().split() if len(w) > 3):
                    toward = "SUPPORTS"
                    relevance = 0.95
                else:
                    toward = "CONTRADICTS"
                    relevance = 0.90
            elif stance in (Stance.COMMIT, Stance.ACCEPT):
                # Must match claim action/object or addressed in conversation
                if speaker_matches and ((overlap >= 1 and (has_key_overlap or not key_claim_words)) or (has_context_key_overlap and prev_seg)):
                    toward = "SUPPORTS"
                    relevance = 0.95
                else:
                    toward = "NEUTRAL"
            elif stance in (Stance.CANCEL, Stance.REVERSE):
                if speaker_matches and (overlap >= 2 or has_key_overlap):
                    toward = "CONTRADICTS"
                    relevance = 0.90
                else:
                    toward = "NEUTRAL"
            elif stance == Stance.REJECT:
                if speaker_matches and (overlap >= 1 or has_context_key_overlap):
                    toward = "CONTRADICTS"
                    relevance = 0.90
                else:
                    toward = "NEUTRAL"
            elif stance == Stance.DEFER:
                if has_primary_overlap or (not primary_subject_words and (has_key_overlap or overlap >= 1)):
                    toward = "CONTRADICTS"
                    relevance = 0.85
                else:
                    toward = "NEUTRAL"
            elif stance in (Stance.PROPOSE, Stance.SUGGEST, Stance.QUESTION):
                toward = "NEUTRAL"
            else:
                toward = "NEUTRAL"

        # 2. DECISION / FACTUAL / REQUIREMENT CLAIMS
        else:
            if claim_is_negative:
                # Segment expressing the negative rule supports the negative claim
                if stance in (Stance.REJECT, Stance.DECIDE, Stance.ACCEPT) and (has_key_overlap or overlap >= 1):
                    toward = "SUPPORTS"
                    relevance = max(relevance, 0.90)
                elif stance in (Stance.DEFER, Stance.CANCEL) and (has_primary_overlap or (not primary_subject_words and has_key_overlap)):
                    toward = "CONTRADICTS"
                    relevance = max(relevance, 0.85)
            else:
                # If speaker states "only agreed to <X>", only contradict topics NOT in <X>
                if "only agreed to" in text.lower():
                    m_ag = re.search(r"only agreed to\s+(.*)", text, re.IGNORECASE)
                    agreed_str = m_ag.group(1).lower() if m_ag else ""
                    if primary_subject_words and any(_words_overlap({w}, primary_subject_words) for w in agreed_str.split()):
                        toward = "NEUTRAL"
                    else:
                        toward = "CONTRADICTS"
                        relevance = 0.85
                # A contradiction requires topic overlap
                elif stance in (Stance.DEFER, Stance.REJECT, Stance.REVERSE, Stance.CANCEL):
                    if (has_primary_overlap or (not primary_subject_words and has_context_key_overlap)):
                        toward = "CONTRADICTS"
                        relevance = max(relevance, 0.85)
                    else:
                        toward = "NEUTRAL"
                elif stance in (Stance.DECIDE, Stance.ACCEPT):
                    # Must match primary subject if primary subjects exist
                    if (has_primary_overlap or (not primary_subject_words and has_key_overlap)):
                        toward = "SUPPORTS"
                        relevance = max(relevance, 0.85)
                    else:
                        toward = "NEUTRAL"
                elif stance == Stance.COMMIT:
                    # A commitment to investigate is not a final decision affirmation
                    if (has_primary_overlap or (not primary_subject_words and has_key_overlap)) and not re.search(r"\b(investigate|look into|check|review)\b", text, re.IGNORECASE):
                        toward = "SUPPORTS"
                        relevance = max(relevance, 0.85)
                    else:
                        toward = "NEUTRAL"
                else:
                    toward = "NEUTRAL"

    antecedent_idx = None
    resolved_text = None
    actor_mentioned = None
    deadline_mentioned = None

    # Check for deadline mention
    m_dead = re.search(r"\b(?:by|before|until|on)\s+([A-Za-z0-9\s,-]+)$", text, re.IGNORECASE)
    if m_dead:
        deadline_mentioned = m_dead.group(1).strip().rstrip(".")

    if stance in (Stance.ACCEPT, Stance.COMMIT) and prev_seg:
        antecedent_idx = prev_seg.get("idx")
        prev_txt = prev_seg.get("text", "")
        
        eff_actor = speaker or "Speaker"
        m_addr = re.search(r"\b([A-Z][a-z]+),\s*(?:can you|could you|will you|please)\b", prev_txt)
        if m_addr:
            eff_actor = m_addr.group(1).strip()
            
        m_act = re.search(r"(?:can you|could you|should we|will you|please|let's)\s+(.*?)[\?\.]?$", prev_txt, re.IGNORECASE)
        m_commit = re.search(r"\b(?:i'?ll|i will|i can)\s+(.*)$", text, re.IGNORECASE)
        
        if m_act:
            resolved_text = f"{eff_actor} will {m_act.group(1).strip()}."
            actor_mentioned = eff_actor
        elif m_commit and not re.search(r"\b(it|that|this)\b", m_commit.group(1), re.IGNORECASE):
            resolved_text = f"{eff_actor} will {m_commit.group(1).strip().rstrip('.')}."
            actor_mentioned = eff_actor
        else:
            resolved_text = f"{eff_actor} agrees to: {prev_txt}"
            actor_mentioned = eff_actor

    return SegmentStance(
        idx=idx,
        relevance=relevance,
        stance=stance,
        toward_claim=toward,
        resolved_text=resolved_text or text,
        antecedent_idx=antecedent_idx,
        actor_mentioned=actor_mentioned,
        deadline_mentioned=deadline_mentioned,
        quote=text
    )

def analyze_stances(
    claim: Claim,
    candidates: List[Dict[str, Any]],
    participants: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Reason]]:
    """Runs stance classification, quote validation, and merges with rule cues."""
    if not candidates:
        return [], [Reason.NO_RELEVANT_EVIDENCE]

    cand_map = {c["idx"]: c for c in candidates}
    prompt_segments = [
        {"idx": c["idx"], "speaker": c.get("speaker"), "time": c.get("time"), "text": c.get("text")}
        for c in candidates
    ]
    user_prompt = f"Claim: {claim.model_dump_json()}\nParticipants: {participants}\nCandidate Segments:\n"
    for s in prompt_segments:
        user_prompt += f"[{s['idx']}] {s.get('speaker') or 'Speaker'} ({s.get('time') or ''}): {s.get('text')}\n"

    try:
        res = query_structured_llm(
            prompt_name="stance_analysis",
            prompt_version=PROMPT_VERSION,
            system_prompt=STANCE_ANALYSIS_SYSTEM,
            user_prompt=user_prompt,
            response_model=StanceAnalysisResponse,
            input_context={"claim_id": claim.claim_id, "candidates": prompt_segments}
        )
        llm_stances = res.stances
    except Exception:
        llm_stances = []
        for i, c in enumerate(candidates):
            prev = candidates[i-1] if i > 0 else None
            llm_stances.append(heuristic_classify_segment(c, claim, prev))

    llm_stance_map = {s.idx: s for s in llm_stances}
    merged_results = []
    disagreement_flags = []
    claim_is_neg = bool(re.search(r"\b(must not|never|should not|cannot|not be disclosed|don'?t)\b", claim.text, re.IGNORECASE))

    for c in candidates:
        idx = c["idx"]
        text = c["text"]
        cue = detect_primary_cue(text)

        s_obj = llm_stance_map.get(idx)
        if not s_obj:
            prev = cand_map.get(idx - 1)
            s_obj = heuristic_classify_segment(c, claim, prev)

        # 1. Quote validation
        validated_quote, repaired = validate_quote(s_obj.quote, text)
        s_obj.quote = validated_quote

        # 2. Rule cue merging & conservative arbitration
        source = "LLM"
        final_stance = s_obj.stance
        final_toward = s_obj.toward_claim
        final_rel = s_obj.relevance

        prev = cand_map.get(idx - 1)
        h_obj = heuristic_classify_segment(c, claim, prev)

        if cue:
            cue_stance = cue["stance"]
            final_stance = cue_stance
            if h_obj.toward_claim != "NEUTRAL":
                final_toward = h_obj.toward_claim
                final_rel = max(final_rel, h_obj.relevance)
                source = "BOTH"
            elif final_stance in NEGATE and not claim_is_neg:
                if h_obj.toward_claim == "CONTRADICTS":
                    final_toward = "CONTRADICTS"
                    final_rel = max(final_rel, 0.85)
                    source = "BOTH"
        elif final_stance in (Stance.INFORM, Stance.OTHER):
            if h_obj.stance not in (Stance.INFORM, Stance.OTHER):
                final_stance = h_obj.stance
                final_toward = h_obj.toward_claim
                final_rel = max(final_rel, h_obj.relevance)
                source = "BOTH"

        # Determine relation
        if final_toward == "SUPPORTS":
            relation = "SUPPORTS"
        elif final_toward == "CONTRADICTS":
            relation = "CONTRADICTS"
        else:
            relation = "CONTEXT"

        merged_results.append({
            "idx": idx,
            "speaker": c.get("speaker"),
            "time": c.get("time"),
            "text": text,
            "quote": validated_quote,
            "stance": final_stance,
            "relation": relation,
            "relevance": final_rel,
            "resolved_text": s_obj.resolved_text,
            "antecedent_idx": s_obj.antecedent_idx,
            "actor_mentioned": s_obj.actor_mentioned,
            "deadline_mentioned": s_obj.deadline_mentioned,
            "source": source
        })

    return merged_results, disagreement_flags
