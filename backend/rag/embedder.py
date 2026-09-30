import threading

import numpy as np
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None
_model_lock = threading.Lock()
MODEL_NAME = "all-MiniLM-L6-v2"


def get_embedder() -> SentenceTransformer:
    """Returns lazily-loaded singleton sentence-transformer model (thread-safe)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-encodes texts into embedding vectors."""
    model = get_embedder()
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()


def cosine_scores(query: str, texts: list[str]) -> list[float]:
    """Cosine similarity (x100, like ChromaDB relevance) between query and each text."""
    if not texts:
        return []
    model = get_embedder()
    vectors = model.encode([query] + texts, convert_to_numpy=True, normalize_embeddings=True)
    sims = vectors[1:] @ vectors[0]
    return [round(float(s) * 100, 1) for s in np.clip(sims, -1.0, 1.0)]
