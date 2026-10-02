import numpy as np
from typing import List, Union
from app.config import settings

_model = None

def get_embed_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.EMBED_MODEL)
    return _model

def normalize_vector(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v, axis=-1, keepdims=True)
    norm = np.where(norm == 0, 1e-12, norm)
    return v / norm

def embed_text(text: str) -> np.ndarray:
    model = get_embed_model()
    emb = model.encode(text, convert_to_numpy=True)
    if emb.ndim == 1:
        emb = emb.reshape(1, -1)
    return normalize_vector(emb)[0]

def embed_texts(texts: List[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    model = get_embed_model()
    embs = model.encode(texts, convert_to_numpy=True)
    if embs.ndim == 1:
        embs = embs.reshape(1, -1)
    return normalize_vector(embs)
