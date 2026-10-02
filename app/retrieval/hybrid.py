import re
import sqlite3
from typing import List, Dict, Any, Set
from collections import defaultdict

from app.config import settings
from app.db import get_db
from app.models import Claim, Stance, NEGATE
from app.retrieval.embeddings import embed_text
from app.ingest.indexer import search_meeting_vectors
from app.analysis.cues import detect_primary_cue

STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are", "was",
    "were", "will", "be", "by", "with", "that", "this", "it", "from", "as", "into", "our",
    "we", "you", "i", "he", "she", "they", "them", "us", "about"
}

def extract_keywords(text: str) -> List[str]:
    words = re.findall(r"\b[A-Za-z0-9_-]+\b", text)
    return [w for w in words if w.lower() not in STOPWORDS and len(w) > 1]

def extract_named_entities(text: str) -> List[str]:
    # Find Capitalized words or acronyms
    tokens = re.findall(r"\b[A-Z][a-zA-Z0-9_-]*\b", text)
    return [t for t in tokens if t.lower() not in STOPWORDS]

def retrieve_candidates(meeting_id: str, claim: Claim) -> List[Dict[str, Any]]:
    """Hybrid retrieval with RRF, window expansion, follow-up expansion, and tail scan."""
    with get_db() as conn:
        all_segments_rows = conn.execute(
            "SELECT idx, speaker, time, t_seconds, text FROM segments WHERE meeting_id = ? ORDER BY idx ASC",
            (meeting_id,)
        ).fetchall()

    if not all_segments_rows:
        return []

    seg_map = {row["idx"]: dict(row) for row in all_segments_rows}
    max_idx = max(seg_map.keys())

    # 1. Semantic Retrieval
    query_text = claim.normalized or claim.text
    query_vec = embed_text(query_text)
    semantic_hits = search_meeting_vectors(meeting_id, query_vec, top_k=settings.RETRIEVAL_TOP_K)
    semantic_ranked_idx = [idx for idx, _ in semantic_hits]

    # 2. Lexical Retrieval (FTS5)
    lexical_ranked_idx = []
    keywords = extract_keywords(f"{claim.object or ''} {claim.action or ''} {claim.normalized or ''} {claim.text}")
    named_entities = extract_named_entities(f"{claim.object or ''} {claim.actor or ''} {claim.text}")

    with get_db() as conn:
        # Query 1: OR terms
        if keywords:
            # Escape quotes
            sanitized_terms = [f'"{re.sub(r"[^a-zA-Z0-9_-]", "", kw)}"' for kw in keywords if kw]
            fts_query = " OR ".join(sanitized_terms)
            try:
                rows = conn.execute(
                    "SELECT idx, rank FROM segments_fts WHERE meeting_id = ? AND segments_fts MATCH ? ORDER BY rank ASC LIMIT ?",
                    (meeting_id, fts_query, settings.RETRIEVAL_TOP_K)
                ).fetchall()
                for r in rows:
                    lexical_ranked_idx.append(int(r["idx"]))
            except sqlite3.OperationalError:
                pass

        # Query 2: Named entities/nouns matching
        if named_entities:
            for ent in named_entities:
                try:
                    rows = conn.execute(
                        "SELECT idx FROM segments_fts WHERE meeting_id = ? AND segments_fts MATCH ? ORDER BY rank ASC LIMIT 5",
                        (meeting_id, f'"{ent}"')
                    ).fetchall()
                    for r in rows:
                        idx_val = int(r["idx"])
                        if idx_val not in lexical_ranked_idx:
                            lexical_ranked_idx.append(idx_val)
                except sqlite3.OperationalError:
                    pass

    # 3. Reciprocal Rank Fusion
    rrf_scores = defaultdict(float)
    rrf_k = settings.RRF_K

    for rank, idx in enumerate(semantic_ranked_idx):
        rrf_scores[idx] += 1.0 / (rrf_k + (rank + 1))

    for rank, idx in enumerate(lexical_ranked_idx):
        rrf_scores[idx] += 1.0 / (rrf_k + (rank + 1))

    # Sort candidates by fused score
    sorted_fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    top_fused_idx = [idx for idx, _ in sorted_fused[:5]]

    # 4. Window expansion & Tracking candidates
    candidates: Dict[int, Dict[str, Any]] = {}

    for idx, score in sorted_fused:
        if idx in seg_map:
            candidates[idx] = {
                **seg_map[idx],
                "relevance_hint": score,
                "via": "fused"
            }

    # Add window for top 5
    for idx in top_fused_idx:
        for offset in range(1, settings.WINDOW_BEFORE + 1):
            w_idx = idx - offset
            if w_idx in seg_map and w_idx not in candidates:
                candidates[w_idx] = {
                    **seg_map[w_idx],
                    "relevance_hint": rrf_scores.get(w_idx, 0.1),
                    "via": "window"
                }
        for offset in range(1, settings.WINDOW_AFTER + 1):
            w_idx = idx + offset
            if w_idx in seg_map and w_idx not in candidates:
                candidates[w_idx] = {
                    **seg_map[w_idx],
                    "relevance_hint": rrf_scores.get(w_idx, 0.1),
                    "via": "window"
                }

    # 5. Same-speaker follow-up & short reply expansion
    for idx in list(candidates.keys()):
        text = seg_map[idx]["text"]
        speaker = seg_map[idx]["speaker"]
        cue = detect_primary_cue(text)
        
        # If question/request, look ahead for different speaker's reply
        if cue and cue["stance"] in (Stance.QUESTION, Stance.REQUEST) or text.endswith("?"):
            for next_idx in range(idx + 1, min(max_idx + 1, idx + 4)):
                if next_idx in seg_map:
                    if seg_map[next_idx]["speaker"] != speaker:
                        if next_idx not in candidates:
                            candidates[next_idx] = {
                                **seg_map[next_idx],
                                "relevance_hint": 0.25,
                                "via": "followup"
                            }
                        break
        
        # If short reply (e.g. "Yes, I'll look into it" or "Sure"), look back at previous segment
        words = text.split()
        if len(words) <= 7 or (cue and cue["stance"] in (Stance.ACCEPT, Stance.COMMIT)):
            prev_idx = idx - 1
            if prev_idx in seg_map and prev_idx not in candidates:
                candidates[prev_idx] = {
                    **seg_map[prev_idx],
                    "relevance_hint": 0.25,
                    "via": "antecedent_window"
                }

    # 6. Tail scan for reversals and entity mentions
    key_entities = set(w.lower() for w in named_entities + keywords if len(w) > 2)
    last_hit_idx = max(candidates.keys()) if candidates else 0

    for idx in range(last_hit_idx + 1, max_idx + 1):
        if idx in seg_map:
            text = seg_map[idx]["text"]
            cue = detect_primary_cue(text)
            has_negation = cue and (cue["stance"] in NEGATE or cue["stance"] == Stance.REVERSE)
            
            # Check for shared key entities
            seg_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower()))
            shares_entity = bool(key_entities.intersection(seg_words))

            if shares_entity:
                candidates[idx] = {
                    **seg_map[idx],
                    "relevance_hint": 0.3 if has_negation else 0.2,
                    "via": "tail_scan"
                }

    # If candidates is empty, return initial segments up to top_k
    if not candidates:
        for idx in range(min(len(all_segments_rows), settings.RETRIEVAL_TOP_K)):
            candidates[idx] = {
                **seg_map[idx],
                "relevance_hint": 0.1,
                "via": "fallback"
            }

    # Sort by idx and cap at 20 segments
    sorted_candidates = [candidates[k] for k in sorted(candidates.keys())]
    return sorted_candidates[:20]
