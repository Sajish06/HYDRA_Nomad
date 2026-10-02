import json
from typing import List
from app.models import Meeting, Claim, ExtractedClaimsResponse
from app.llm.client import query_structured_llm
from app.llm.prompts import CLAIM_EXTRACTION_SYSTEM
from app.retrieval.embeddings import embed_text
from app.db import get_db
import numpy as np

PROMPT_VERSION = "v1"

def extract_claims_from_transcript(meeting: Meeting) -> List[Claim]:
    """Extracts high-impact claims from raw transcript using sliding windows."""
    segments = meeting.segments
    if not segments:
        return []

    window_size = 12
    stride = 6
    extracted_drafts = []

    for start_i in range(0, len(segments), stride):
        window_segs = segments[start_i:start_i + window_size]
        if not window_segs:
            break

        seg_text = "\n".join([f"[{s.idx}] {s.speaker or 'Speaker'} ({s.time or ''}): {s.text}" for s in window_segs])
        user_prompt = f"Transcript Segments:\n{seg_text}"

        try:
            res = query_structured_llm(
                prompt_name="transcript_claim_extraction",
                prompt_version=PROMPT_VERSION,
                system_prompt=CLAIM_EXTRACTION_SYSTEM,
                user_prompt=user_prompt,
                response_model=ExtractedClaimsResponse,
                input_context={"meeting_id": meeting.meeting_id, "window_start": start_i, "window_size": window_size}
            )
            extracted_drafts.extend(res.claims)
        except Exception:
            pass

    # Deduplicate by embedding similarity > 0.9
    unique_claims = []
    seen_embeddings = []

    for i, draft in enumerate(extracted_drafts):
        norm_text = draft.normalized or draft.text
        emb = embed_text(norm_text)
        is_dup = False
        for prev_emb in seen_embeddings:
            sim = float(np.dot(emb, prev_emb))
            if sim > 0.90:
                is_dup = True
                break
        if not is_dup:
            seen_embeddings.append(emb)
            claim_id = f"claim_tx_{meeting.meeting_id}_{len(unique_claims) + 1}"
            claim = Claim(
                claim_id=claim_id,
                meeting_id=meeting.meeting_id,
                text=draft.text,
                source="TRANSCRIPT",
                type=draft.type,
                actor=draft.actor,
                action=draft.action,
                object=draft.object,
                deadline=draft.deadline,
                normalized=norm_text
            )
            unique_claims.append(claim)

    with get_db() as conn:
        for c in unique_claims:
            conn.execute(
                """INSERT OR REPLACE INTO claims (id, meeting_id, text, normalized, source, type, actor, action, object, deadline)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (c.claim_id, c.meeting_id, c.text, c.normalized, c.source, c.type.value, c.actor, c.action, c.object, c.deadline)
            )

    return unique_claims
