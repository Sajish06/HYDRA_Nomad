import re
from typing import List, Dict, Any, Optional, Tuple, Union
from app.models import Reason, Stance

def validate_and_resolve_context(
    claim_text: str,
    stances: List[Dict[str, Any]],
    segments_by_idx: Dict[int, Dict[str, Any]],
    participants: List[Dict[str, Any]]
) -> Tuple[Optional[str], List[Reason]]:
    """Validates antecedent linkages, resolves pronouns/antecedents, and produces resolved_claim."""
    flags: List[Reason] = []
    resolved_claim = None

    for s in stances:
        idx = s.get("idx") if isinstance(s, dict) else getattr(s, "idx", 0)
        seg = segments_by_idx.get(idx, {})
        speaker = seg.get("speaker")
        text = seg.get("text", "")

        antecedent_idx = s.get("antecedent_idx") if isinstance(s, dict) else getattr(s, "antecedent_idx", None)
        resolved_text = s.get("resolved_text") if isinstance(s, dict) else getattr(s, "resolved_text", None)
        relation = s.get("relation") if isinstance(s, dict) else getattr(s, "relation", None)
        stance_val = s.get("stance") if isinstance(s, dict) else getattr(s, "stance", None)

        # If stance is ACCEPT or COMMIT, find antecedent if missing
        if stance_val in ("ACCEPT", "COMMIT", Stance.ACCEPT, Stance.COMMIT) or relation == "SUPPORTS":
            if antecedent_idx is None and idx > 0:
                # Scan backwards for nearest question or proposal
                for prev_i in range(idx - 1, max(-1, idx - 5), -1):
                    if prev_i in segments_by_idx:
                        p_seg = segments_by_idx[prev_i]
                        p_txt = p_seg.get("text", "")
                        if "?" in p_txt or re.search(r"\b(can you|could you|should we|will you|please|investigate|benchmark|check)\b", p_txt, re.IGNORECASE):
                            antecedent_idx = prev_i
                            if isinstance(s, dict):
                                s["antecedent_idx"] = antecedent_idx
                            else:
                                s.antecedent_idx = antecedent_idx
                            break

        if antecedent_idx is not None:
            a_idx = antecedent_idx
            if a_idx >= idx or (idx - a_idx) > 6 or a_idx not in segments_by_idx:
                # Invalid antecedent
                if isinstance(s, dict):
                    s["antecedent_idx"] = None
                else:
                    s.antecedent_idx = None
            else:
                a_seg = segments_by_idx[a_idx]
                a_speaker = a_seg.get("speaker")
                a_text = a_seg.get("text", "")

                # Check if there were multiple ambiguous requests in between
                potential_antecedents = []
                for prev_i in range(max(0, idx - 4), idx):
                    if prev_i in segments_by_idx:
                        p_txt = segments_by_idx[prev_i].get("text", "")
                        if "?" in p_txt or re.search(r"\b(can you|could you|should we)\b", p_txt, re.IGNORECASE):
                            potential_antecedents.append(prev_i)

                if len(potential_antecedents) > 1 and a_idx not in potential_antecedents:
                    flags.append(Reason.UNRESOLVED_REFERENCE)

                # Generate resolved claim sentence if not provided
                addressed_actor = None
                m_addressed = re.search(r"\b([A-Z][a-z]+),\s*(?:can you|could you|will you|please)\b", a_text)
                if m_addressed:
                    addressed_actor = m_addressed.group(1).strip()

                effective_actor = addressed_actor or (speaker if (speaker and not speaker.lower().startswith("speaker")) else "The owner")

                if not resolved_text or resolved_text.strip() == text or resolved_text.strip() == "" or re.search(r"\b(look into it|on it|take care of it)\b", resolved_text, re.IGNORECASE):
                    m_action = re.search(r"(?:can you|could you|should we|will you|please)\s+(.*?)[\?\.]?$", a_text, re.IGNORECASE)
                    if m_action:
                        act_content = m_action.group(1).strip()
                        resolved_text = f"{effective_actor} will {act_content}."
                    else:
                        m_commit = re.search(r"\b(?:i'?ll|i will|i can)\s+(.*)$", text, re.IGNORECASE)
                        if m_commit:
                            resolved_text = f"{effective_actor} will {m_commit.group(1).strip().rstrip('.')}."
                        else:
                            resolved_text = f"{effective_actor} agreed: {a_text}"
                    
                if isinstance(s, dict):
                    s["resolved_text"] = resolved_text
                    if addressed_actor:
                        s["actor_mentioned"] = addressed_actor
                else:
                    s.resolved_text = resolved_text
                    if addressed_actor:
                        s.actor_mentioned = addressed_actor

        # If resolved_text is meaningful on a supporting affirm, use it for resolved_claim
        if (relation == "SUPPORTS" or stance_val in ("ACCEPT", "COMMIT", Stance.ACCEPT, Stance.COMMIT)) and resolved_text:
            if not resolved_claim or len(resolved_text) > len(resolved_claim):
                resolved_claim = resolved_text

    # Global fallback for resolved_claim if implicit commitment exists
    if not resolved_claim:
        for s in stances:
            s_stance = s.get("stance") if isinstance(s, dict) else getattr(s, "stance", None)
            s_idx = s.get("idx") if isinstance(s, dict) else getattr(s, "idx", 0)
            if s_stance in (Stance.ACCEPT, Stance.COMMIT, "ACCEPT", "COMMIT") and s_idx > 0:
                s_seg = segments_by_idx.get(s_idx, {})
                s_speaker = s_seg.get("speaker", "Assignee")
                s_text = s_seg.get("text", "")
                prev_seg = segments_by_idx.get(s_idx - 1, {})
                prev_txt = prev_seg.get("text", "")
                
                addressed = None
                m_addr = re.search(r"\b([A-Z][a-z]+),\s*(?:can you|could you|will you|please)\b", prev_txt)
                if m_addr:
                    addressed = m_addr.group(1).strip()
                eff_spk = addressed or s_speaker

                m_action = re.search(r"(?:can you|could you|should we|will you|please)\s+(.*?)[\?\.]?$", prev_txt, re.IGNORECASE)
                if m_action:
                    resolved_claim = f"{eff_spk} will {m_action.group(1).strip()}."
                else:
                    m_commit = re.search(r"\b(?:i'?ll|i will|i can)\s+(.*)$", s_text, re.IGNORECASE)
                    if m_commit:
                        resolved_claim = f"{eff_spk} will {m_commit.group(1).strip().rstrip('.')}."
                    elif prev_txt:
                        resolved_claim = f"{eff_spk} will handle: {prev_txt}"
                break

    return resolved_claim, flags


