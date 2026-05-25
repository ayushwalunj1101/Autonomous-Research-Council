from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None
MODEL_NAME = "all-MiniLM-L6-v2"


def get_embedder() -> SentenceTransformer:
    """Returns lazily-loaded singleton sentence-transformer model."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-encodes texts into embedding vectors."""
    model = get_embedder()
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()
