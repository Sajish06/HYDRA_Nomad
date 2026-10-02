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
        "were", "will", "be", "by", "with", "that", "this", "it", "from", "as", "has", "been", "had", "should", "must"
    }
    raw_claim_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", f"{claim.text} {claim.object or ''} {claim.action or ''} {claim.normalized or ''}".lower())) - claim_stopwords
    
    # Expand with action synonyms for semantic matching
    claim_words = set(raw_claim_words)
    if claim.action:
        act_lower = claim.action.lower().strip()
        for root, syns in ACTION_SYNONYMS.items():
            if act_lower in syns or root in act_lower:
                claim_words.update(syns)

    seg_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())) - claim_stopwords
    overlap = len(claim_words.intersection(seg_words))
    relevance = 0.20
    toward = "NEUTRAL"

    if overlap >= 1 or (claim.actor and claim.actor.lower() in text.lower()):
        relevance = min(0.95, 0.45 + overlap * 0.15)
        
        # 1. COMMITMENT / ACTION CLAIMS
        if claim.type in (ClaimType.COMMITMENT, ClaimType.ACTION):
            act_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", f"{claim.actor or ''} {claim.action or ''}".lower())) - claim_stopwords
            if claim.action:
                for root, syns in ACTION_SYNONYMS.items():
                    if claim.action.lower() in syns or root in claim.action.lower():
                        act_words.update(syns)
            act_overlap = len(act_words.intersection(seg_words))

            # Explicit first-person commitment or confirmation -> SUPPORTS
            if stance in (Stance.COMMIT, Stance.ACCEPT):
                if (
                    not claim.actor 
                    or not speaker 
                    or speaker.lower().startswith("speaker") 
                    or speaker.lower().startswith("user")
                    or (claim.actor.lower() in speaker.lower() or speaker.lower() in claim.actor.lower())
                    or (claim.actor.lower() in text.lower())
                    or (prev_seg and claim.actor.lower() in prev_seg.get("text", "").lower())
                    or (overlap >= 1)
                ):
                    toward = "SUPPORTS"
                    relevance = 0.95
                else:
                    toward = "NEUTRAL"
            elif stance in (Stance.CANCEL, Stance.REVERSE):
                toward = "CONTRADICTS"
                relevance = 0.85
            elif stance in (Stance.REJECT, Stance.DEFER):
                if re.search(r"\b(don'?t (?:request|send|do|ask|reach|prepare)|cancel|drop|won'?t (?:request|send|do|ask)|let'?s not)\b", text, re.IGNORECASE):
                    toward = "CONTRADICTS"
                    relevance = 0.85
                else:
                    toward = "NEUTRAL"
            else:
                # Do NOT infer commitments from suggestions, possibilities, questions, or informational statements
                toward = "NEUTRAL"

        # 2. DECISION / FACTUAL CLAIMS
        else:
            if stance in (Stance.DEFER, Stance.REJECT, Stance.REVERSE, Stance.CANCEL):
                toward = "CONTRADICTS"
                relevance = max(relevance, 0.85)
            elif stance in (Stance.DECIDE, Stance.ACCEPT, Stance.COMMIT):
                toward = "SUPPORTS"
                relevance = max(relevance, 0.85)
            elif stance in (Stance.PROPOSE, Stance.SUGGEST, Stance.QUESTION):
                toward = "NEUTRAL"
            elif stance == Stance.INFORM and overlap >= 2:
                toward = "SUPPORTS"
                relevance = max(relevance, 0.80)

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
        m_act = re.search(r"(?:can you|could you|should we|let's)\s+(.*?)[\?\.]?$", prev_txt, re.IGNORECASE)
        if m_act:
            resolved_text = f"{speaker or 'Speaker'} will {m_act.group(1).strip()}."
            actor_mentioned = speaker
        else:
            resolved_text = f"{speaker or 'Speaker'} agrees to: {prev_txt}"
            actor_mentioned = speaker

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

        if cue:
            cue_stance = cue["stance"]
            # If cue detects explicit reversal, honor it when relevant
            if cue_stance == Stance.REVERSE and final_toward != "NEUTRAL":
                final_stance = Stance.REVERSE
                final_toward = "CONTRADICTS"
                final_rel = max(final_rel, 0.9)
                source = "BOTH"
            # If cue says NEGATE and LLM didn't assign a negation stance
            elif cue_stance in NEGATE and final_toward not in ("NEUTRAL", "CONTRADICTS"):
                if claim.type not in (ClaimType.COMMITMENT, ClaimType.ACTION):
                    final_stance = cue_stance
                    final_toward = "CONTRADICTS"
                    final_rel = max(final_rel, 0.8)
                    source = "BOTH"
                    if Reason.LLM_RULE_DISAGREEMENT not in disagreement_flags:
                        disagreement_flags.append(Reason.LLM_RULE_DISAGREEMENT)
            elif cue_stance in AFFIRM_STRONG and final_stance in NEGATE:
                source = "BOTH"
                if Reason.LLM_RULE_DISAGREEMENT not in disagreement_flags:
                    disagreement_flags.append(Reason.LLM_RULE_DISAGREEMENT)
            elif cue_stance == final_stance:
                source = "BOTH"
            elif final_stance in (Stance.INFORM, Stance.OTHER):
                final_stance = cue_stance
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
