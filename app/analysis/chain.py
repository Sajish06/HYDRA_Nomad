from typing import List, Dict, Any
from app.models import EvidenceItem, Stance
from app.db import get_db

def build_evidence_chain(
    claim_id: str,
    meeting_id: str,
    merged_stances: List[Dict[str, Any]]
) -> List[EvidenceItem]:
    """Constructs the canonical, ordered list of EvidenceItems from DB-grounded segment text."""
    evidence_chain = []
    
    # Query segments from DB for full ground-truth text
    with get_db() as conn:
        rows = conn.execute(
            "SELECT idx, speaker, time, text FROM segments WHERE meeting_id = ? ORDER BY idx ASC",
            (meeting_id,)
        ).fetchall()
    
    db_seg_map = {r["idx"]: r for r in rows}

    for item in merged_stances:
        idx = item["idx"]
        db_seg = db_seg_map.get(idx)
        if not db_seg:
            continue

        e_item = EvidenceItem(
            idx=idx,
            speaker=db_seg["speaker"],
            time=db_seg["time"],
            text=db_seg["text"],
            quote=item["quote"],
            stance=item["stance"],
            relation=item["relation"],
            resolved_text=item.get("resolved_text"),
            source=item.get("source", "LLM")
        )
        evidence_chain.append(e_item)

    # Sort strictly by idx
    evidence_chain.sort(key=lambda x: x.idx)

    # Persist to evidence table
    with get_db() as conn:
        conn.execute("DELETE FROM evidence WHERE claim_id = ?", (claim_id,))
        for e in evidence_chain:
            rel_score = next((s.get("relevance", 1.0) for s in merged_stances if s["idx"] == e.idx), 1.0)
            conn.execute(
                """INSERT INTO evidence (claim_id, meeting_id, segment_idx, stance, relation, quote, resolved_text, source, relevance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (claim_id, meeting_id, e.idx, e.stance.value, e.relation, e.quote, e.resolved_text, e.source, rel_score)
            )

    return evidence_chain
