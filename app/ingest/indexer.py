import os
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np

from app.config import settings, BASE_DIR
from app.db import get_db
from app.retrieval.embeddings import embed_texts

def get_indexes_dir() -> Path:
    p = BASE_DIR / "data" / "indexes"
    p.mkdir(parents=True, exist_ok=True)
    return p

def index_meeting(meeting_id: str) -> int:
    """Indexes meeting segments for FAISS vector search and returns count."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT idx, speaker, text FROM segments WHERE meeting_id = ? ORDER BY idx ASC",
            (meeting_id,)
        ).fetchall()

    if not rows:
        return 0

    idx_list = []
    text_to_embed = []
    for i, row in enumerate(rows):
        idx = row["idx"]
        speaker = row["speaker"] or "Speaker"
        text = row["text"]
        words = text.split()
        
        if len(words) < 6 and i > 0:
            prev_text = rows[i-1]["text"]
            contextualized = f"{speaker}: {text} (previous: {prev_text})"
            text_to_embed.append(contextualized)
        else:
            text_to_embed.append(text)
        idx_list.append(idx)

    embeddings = embed_texts(text_to_embed).astype(np.float32)
    dim = embeddings.shape[1]

    indexes_dir = get_indexes_dir()
    faiss_path = indexes_dir / f"{meeting_id}.faiss"
    ids_path = indexes_dir / f"{meeting_id}.ids.json"

    try:
        import faiss
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)
        faiss.write_index(index, str(faiss_path))
    except Exception:
        # Fallback: save numpy array directly if faiss-cpu fails or has C++ runtime issue
        np.save(str(indexes_dir / f"{meeting_id}.npy"), embeddings)

    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(idx_list, f)

    return len(idx_list)

def search_meeting_vectors(meeting_id: str, query_vec: np.ndarray, top_k: int = 8) -> List[Tuple[int, float]]:
    """Searches vectors for a meeting and returns (segment_idx, cosine_similarity) tuples."""
    indexes_dir = get_indexes_dir()
    faiss_path = indexes_dir / f"{meeting_id}.faiss"
    ids_path = indexes_dir / f"{meeting_id}.ids.json"
    npy_path = indexes_dir / f"{meeting_id}.npy"

    if not ids_path.exists():
        index_meeting(meeting_id)

    if not ids_path.exists():
        return []

    with open(ids_path, "r", encoding="utf-8") as f:
        idx_list = json.load(f)

    if not idx_list:
        return []

    top_k = min(top_k, len(idx_list))

    if faiss_path.exists():
        try:
            import faiss
            index = faiss.read_index(str(faiss_path))
            q = np.ascontiguousarray(query_vec.reshape(1, -1), dtype=np.float32)
            distances, indices = index.search(q, top_k)
            results = []
            for d, row_idx in zip(distances[0], indices[0]):
                if row_idx >= 0 and row_idx < len(idx_list):
                    results.append((idx_list[row_idx], float(d)))
            return results
        except Exception:
            pass

    if npy_path.exists():
        embeddings = np.load(str(npy_path))
        scores = np.dot(embeddings, query_vec)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(idx_list[i], float(scores[i])) for i in top_indices]

    return []
